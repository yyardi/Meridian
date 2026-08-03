"""Tick-by-tick game replay — the test harness every in-game strategy needs.

Why this exists
---------------
PULSE and QUOTE are both unbuilt, and neither can be *evaluated* without a way
to run a strategy against a game that has already happened. Without it the only
way to test an in-game idea is to trade it live, which is how people discover
their edge was noise using real money.

The engine replays recorded snapshots in captured_at order and hands a strategy
one tick at a time. It does not know or care what the strategy does; it only
guarantees the three things that make a result mean something.

The three guarantees
--------------------
**1. No lookahead, structurally.** A strategy receives a `Tick` and a
`ReplayContext`, and neither exposes the future. There is no "the rest of the
game" object to accidentally index into. This is the same discipline `as_of`
enforces in the pregame feature layer, for the same reason: a lookahead bug
does not crash, it produces a beautiful backtest that evaporates on live money.

**2. Fills are earned, not assumed.** A resting limit order fills only when the
book actually trades through it on a *later* tick:

    BUY  at P fills when the best ask falls to <= P   (a seller crosses down)
    SELL at P fills when the best bid rises to >= P   (a buyer crosses up)

Never on the tick that placed it — that would be a taker fill wearing a maker's
clothes, and taker fills are measured to turn +1.34% into -4.0%.

**3. Sample size is games.** One game emits ~130 markets x 5 ticks a second, so
a three-game backtest can contain a million rows and still be three
observations. Every result reports `n_games`, and intervals come from
`clustered_mean`. The engine refuses to produce a verdict below a game
threshold rather than dressing up noise.

What it deliberately does not do
--------------------------------
No strategy, no model, no sizing. Those are separate and each needs its own
pre-registered gate. This is the instrument.

    python -m core.pulse.replay --list
    python -m core.pulse.replay --game wnba-la-por-2026-08-02
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass, field

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.storage import MarketSnapshot, get_engine, get_sessionmaker

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc

#: Below this many games a result is noise dressed as a finding. Matches the
#: bar the three microstructure experiments already use.
MIN_GAMES_FOR_VERDICT = 10


@dataclass(frozen=True)
class Tick:
    """One market's state at one instant. All a strategy ever sees."""

    captured_at: dt.datetime
    event_slug: str
    market_slug: str
    sports_market_type: str | None
    line: float | None
    bid: float | None
    ask: float | None
    is_live: bool
    score: str | None
    period: str | None

    @property
    def mid(self) -> float | None:
        if self.bid is None or self.ask is None:
            return None
        return (self.bid + self.ask) / 2.0

    @property
    def spread(self) -> float | None:
        if self.bid is None or self.ask is None:
            return None
        return self.ask - self.bid

    @property
    def points(self) -> tuple[int, int] | None:
        """(first, second) from the score string, or None if unparseable."""
        if not self.score or "-" not in self.score:
            return None
        try:
            a, b = self.score.split("-", 1)
            return int(a.strip()), int(b.strip())
        except ValueError:
            return None

    @property
    def total_points(self) -> int | None:
        pts = self.points
        return None if pts is None else pts[0] + pts[1]


@dataclass
class Order:
    """A resting limit order. Fills only when the book trades through it."""

    market_slug: str
    side: str                       # 'buy' | 'sell'
    limit_price: float
    quantity: float
    placed_at: dt.datetime
    filled_at: dt.datetime | None = None
    fill_price: float | None = None
    cancelled_at: dt.datetime | None = None
    note: str = ""

    @property
    def is_open(self) -> bool:
        return self.filled_at is None and self.cancelled_at is None

    def would_fill(self, tick: Tick) -> bool:
        """Did the book trade through this order on `tick`?

        Buying rests on the bid side and is lifted when a seller crosses down
        to it, i.e. when the best ask reaches the limit. Selling is the mirror.
        Equality counts: resting at the touch does get hit.
        """
        if self.side == "buy":
            return tick.ask is not None and tick.ask <= self.limit_price
        return tick.bid is not None and tick.bid >= self.limit_price


class ReplayContext:
    """What a strategy may do. Deliberately small, and past-only.

    There is no method here that returns a future tick, which is what makes
    lookahead unexpressible rather than merely discouraged.
    """

    def __init__(self) -> None:
        self.orders: list[Order] = []
        self._now: dt.datetime | None = None

    @property
    def now(self) -> dt.datetime | None:
        """The timestamp of the tick currently being processed."""
        return self._now

    def place(self, *, market_slug: str, side: str, limit_price: float,
              quantity: float, note: str = "") -> Order:
        if side not in {"buy", "sell"}:
            raise ValueError(f"side must be buy|sell, got {side!r}")
        if self._now is None:
            raise RuntimeError("place() called outside a tick")
        order = Order(
            market_slug=market_slug, side=side, limit_price=limit_price,
            quantity=quantity, placed_at=self._now, note=note,
        )
        self.orders.append(order)
        return order

    def cancel(self, order: Order) -> None:
        if order.is_open and self._now is not None:
            order.cancelled_at = self._now

    def open_orders(self, market_slug: str | None = None) -> list[Order]:
        return [
            o for o in self.orders
            if o.is_open and (market_slug is None or o.market_slug == market_slug)
        ]

    @property
    def fills(self) -> list[Order]:
        return [o for o in self.orders if o.filled_at is not None]


@dataclass
class GameReplay:
    """The result of replaying one game."""

    event_slug: str
    n_ticks: int = 0
    n_markets: int = 0
    first_tick: dt.datetime | None = None
    last_tick: dt.datetime | None = None
    orders: list[Order] = field(default_factory=list)

    @property
    def duration_minutes(self) -> float:
        if self.first_tick is None or self.last_tick is None:
            return 0.0
        return (self.last_tick - self.first_tick).total_seconds() / 60.0

    @property
    def ticks_per_minute(self) -> float:
        return self.n_ticks / self.duration_minutes if self.duration_minutes else 0.0

    @property
    def fills(self) -> list[Order]:
        return [o for o in self.orders if o.filled_at is not None]

    @property
    def fill_rate(self) -> float | None:
        placed = [o for o in self.orders if o.cancelled_at is None or o.filled_at]
        return len(self.fills) / len(placed) if placed else None


def load_ticks(
    session: Session, *, event_slug: str, live_only: bool = True
) -> list[Tick]:
    """Every recorded tick for one game, oldest first.

    Ordered by `captured_at` then `market_slug` so a replay is deterministic:
    ties are common at 200ms and Postgres returns them in physical order, which
    changes as rows are updated. A seeded strategy must not depend on heap
    layout — the same lesson the pregame backtest learned.
    """
    stmt = (
        select(
            MarketSnapshot.captured_at,
            MarketSnapshot.event_slug,
            MarketSnapshot.market_slug,
            MarketSnapshot.sports_market_type,
            MarketSnapshot.line,
            MarketSnapshot.best_bid,
            MarketSnapshot.best_ask,
            MarketSnapshot.is_live,
            MarketSnapshot.event_score,
            MarketSnapshot.event_period,
        )
        .where(MarketSnapshot.event_slug == event_slug)
        .order_by(MarketSnapshot.captured_at, MarketSnapshot.market_slug)
    )
    if live_only:
        stmt = stmt.where(MarketSnapshot.is_live.is_(True))

    return [
        Tick(
            captured_at=r.captured_at,
            event_slug=r.event_slug,
            market_slug=r.market_slug,
            sports_market_type=r.sports_market_type,
            line=float(r.line) if r.line is not None else None,
            bid=float(r.best_bid) if r.best_bid is not None else None,
            ask=float(r.best_ask) if r.best_ask is not None else None,
            is_live=r.is_live,
            score=r.event_score,
            period=r.event_period,
        )
        for r in session.execute(stmt).all()
    ]


def replay_game(ticks: list[Tick], strategy, *, event_slug: str) -> GameReplay:
    """Feed `ticks` to `strategy` one at a time, resolving fills honestly.

    `strategy` is any object with `on_tick(tick, ctx)`. Fills are checked
    *before* the strategy sees the tick, so an order placed on tick N is
    eligible from tick N+1 onward and never on the tick that created it.
    """
    ctx = ReplayContext()
    result = GameReplay(event_slug=event_slug)
    seen_markets: set[str] = set()

    for tick in ticks:
        ctx._now = tick.captured_at

        # Resolve resting orders BEFORE the strategy acts. An order placed on
        # this tick cannot fill on it: `placed_at == captured_at` is excluded,
        # which is what keeps a maker order from silently becoming a taker.
        for order in ctx.orders:
            if not order.is_open or order.placed_at >= tick.captured_at:
                continue
            if order.market_slug != tick.market_slug:
                continue
            if order.would_fill(tick):
                order.filled_at = tick.captured_at
                order.fill_price = order.limit_price

        strategy.on_tick(tick, ctx)

        result.n_ticks += 1
        seen_markets.add(tick.market_slug)
        if result.first_tick is None:
            result.first_tick = tick.captured_at
        result.last_tick = tick.captured_at

    result.n_markets = len(seen_markets)
    result.orders = ctx.orders
    return result


def available_games(session: Session, *, min_ticks: int = 1) -> list[tuple[str, int]]:
    """(event_slug, tick count) for games with live data, richest first."""
    counts: dict[str, int] = defaultdict(int)
    for slug, in session.execute(
        select(MarketSnapshot.event_slug).where(MarketSnapshot.is_live.is_(True))
    ).all():
        if slug:
            counts[slug] += 1
    return sorted(
        ((k, v) for k, v in counts.items() if v >= min_ticks),
        key=lambda kv: -kv[1],
    )


def replay_all(
    session: Session, strategy_factory, *, min_ticks: int = 100
) -> list[GameReplay]:
    """Replay every game with usable tick data, one fresh strategy each.

    `strategy_factory` is called per game so state cannot leak between them —
    a strategy that carried its fitted parameters across games would be reading
    the future of game N from game N+1.
    """
    out: list[GameReplay] = []
    for event_slug, _ in available_games(session, min_ticks=min_ticks):
        ticks = load_ticks(session, event_slug=event_slug)
        out.append(replay_game(ticks, strategy_factory(), event_slug=event_slug))
    return out


def format_report(replays: list[GameReplay], *, label: str = "replay") -> str:
    """Report a replay run, refusing a verdict below the game threshold."""
    lines: list[str] = []
    add = lines.append

    add(f"REPLAY — {label}")
    add("=" * 74)
    add(f"games replayed: {len(replays)}")
    add("")

    if not replays:
        add("NO DATA — no game has usable tick data yet.")
        return "\n".join(lines)

    add(f"{'game':<32}{'ticks':>9}{'mkts':>6}{'min':>7}{'ticks/min':>11}")
    add("-" * 74)
    for r in sorted(replays, key=lambda x: -x.n_ticks):
        add(f"{r.event_slug:<32}{r.n_ticks:>9,}{r.n_markets:>6}"
            f"{r.duration_minutes:>7.0f}{r.ticks_per_minute:>11,.0f}")
    add("")

    total_orders = sum(len(r.orders) for r in replays)
    total_fills = sum(len(r.fills) for r in replays)
    add(f"orders placed: {total_orders}   filled: {total_fills}"
        + (f"   ({total_fills / total_orders:.0%})" if total_orders else ""))
    add("")

    if len(replays) < MIN_GAMES_FOR_VERDICT:
        add(f"NO VERDICT — {len(replays)} games against a minimum of "
            f"{MIN_GAMES_FOR_VERDICT}.")
        add("  Rows are not the sample. One game emits ~130 markets x 5 ticks a")
        add("  second, so a three-game run can hold a million rows and still be")
        add("  three observations. Any interval computed here would be a lie of")
        add("  roughly sqrt(rows per game).")
    return "\n".join(lines)


class _NullStrategy:
    """Places nothing. Used to measure the data itself."""

    def on_tick(self, tick: Tick, ctx: ReplayContext) -> None:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(prog="meridian-replay")
    parser.add_argument("--list", action="store_true", help="show replayable games")
    parser.add_argument("--game", type=str, default=None)
    parser.add_argument("--min-ticks", type=int, default=100)
    args = parser.parse_args()

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.WARNING)
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))

    Session = get_sessionmaker(get_engine())
    with Session() as session:
        if args.list:
            print(f"{'game':<34}{'live ticks':>12}")
            print("-" * 46)
            for slug, n in available_games(session):
                print(f"{slug:<34}{n:>12,}")
            return 0

        if args.game:
            ticks = load_ticks(session, event_slug=args.game)
            replays = [replay_game(ticks, _NullStrategy(), event_slug=args.game)]
        else:
            replays = replay_all(session, _NullStrategy, min_ticks=args.min_ticks)

    print(format_report(replays, label=args.game or "all games"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
