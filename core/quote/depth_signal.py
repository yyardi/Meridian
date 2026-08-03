"""Experiment 7 — does a whale in the book predict the next move?

The question
-----------
Median top-of-book on this venue is **$177**. Against that, a $5,000 resting
order is not a nuance — it is unmistakable, and there is no plausible reading
in which it is noise. Somebody with size has an opinion and has left it on the
screen.

So: **when a large resting order appears, does the price subsequently move
toward the side it appeared on?**

Why it matters for QUOTE. A market maker does not have to forecast games; it
has to avoid being run over. If a whale appearing on the bid predicts the mid
rising, that is a reason to skew quotes up — lift the offer, keep the bid — and
skewing is free, unlike taking. If it predicts nothing, the book is decoration
and quotes should ignore it.

This is a measurement. It places no orders and prices nothing.


PRE-REGISTERED GATE — fixed before any number was computed
----------------------------------------------------------
Written 2026-08-02, prior to running this against any data.

    PASS  requires ALL of:
      (1) mean signed move toward the whale's side, at +60s, > 0
      (2) the 95% CI on that mean, clustered by game, excludes zero
      (3) n >= 100 whale appearances
      (4) those appearances spread across >= 10 distinct games

    FAIL  if (3) and (4) are met but (1) or (2) is not.

    NO DATA  if (3) or (4) is not met.

Note the economic bar is deliberately **not** the 6c round trip here, unlike
`core.pulse.overreaction`. A depth signal would be used to *skew a resting
quote*, which costs nothing — not to cross the spread. The right test is
therefore whether the signal is real, with its size reported against the ~3c
half-spread so its usefulness is visible rather than asserted. A signal worth
0.2c is real and useless, and the report says which it is.

The +60s mark is the pre-registered primary. +30s and +300s are secondaries
with no gate attached.


What counts as a whale, and what counts as "appearing"
------------------------------------------------------
A whale is a single resting level with notional `price * quantity >=
WHALE_NOTIONAL` ($5,000). Notional, not contracts: 10,000 contracts at 2c and
200 at 99c are very different objects and only one of them is a bet.

**Appearing** means it was not there before. A whale present at `t` on a market
side that had no whale at the previous observation is an appearance; a whale
that has been sitting there for ten minutes is not. This matters because the
hypothesis is about *new* information arriving, and a permanent wall would
otherwise contribute one observation per snapshot — thousands of copies of a
single event, which at 1s sampling would dominate the sample entirely.

    signal(H) = side_sign * (mid(t+H) - mid(t))

with `side_sign` +1 for a bid whale and -1 for an ask whale, so a positive
number always means "the price moved toward the size", whichever side it was.


Honesty constraints
-------------------
**Strictly point-in-time.** The whale must be observed before the move it is
credited with predicting. Depth rows written by the tiered live recorder carry
their own `captured_at` — depth runs on a slower loop than price, so inheriting
the parent snapshot's timestamp would backdate them by up to several seconds
and let a book fetched *after* a move appear to have preceded it. Rows written
before that column existed fall back to the snapshot timestamp, which was
correct for them because price and depth were fetched together.

**Sampling is sparse by design and that is recorded.** The live recorder
samples depth on the rungs nearest the money often and the deep rungs rarely.
`market_snapshots.book_tier` records which, so "no whale" can be distinguished
from "not looked at" — without it, an unsampled market reads as an empty book
and every deep rung would silently count as whale-free.

    python -m core.quote.depth_signal
    python -m core.quote.depth_signal --whale 5000 --days 7
"""

from __future__ import annotations

import argparse
import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.quote.adverse_selection import Cadence, cadence, clustered_mean
from core.storage import BookLevel, MarketSnapshot

UTC = dt.timezone.utc

# --------------------------------------------------------------------- #
# Pre-registered constants
# --------------------------------------------------------------------- #

#: Dollars of resting notional that make an order unmistakable against a $177
#: median top-of-book.
DEFAULT_WHALE_NOTIONAL = 5_000.0

#: Horizons after the appearance. The gate is on the primary only.
PRIMARY_HORIZON_SECONDS = 60.0
HORIZON_SECONDS = (30.0, 60.0, 300.0)

HORIZON_TOLERANCE = (0.5, 2.0)

#: Only rungs anyone would trade, same band as the other two experiments.
MIN_MID, MAX_MID = 0.20, 0.80
MAX_SPREAD = 0.15

#: Reported alongside the result so "real" and "useful" stay distinguishable.
HALF_SPREAD_REFERENCE = 0.015

# -- the gate --------------------------------------------------------- #
GATE_MIN_EVENTS = 100
GATE_MIN_GAMES = 10


@dataclass(frozen=True)
class BookState:
    """One market's book at one instant, reduced to what the question needs."""

    game_id: str
    market_slug: str
    captured_at: dt.datetime
    mid: float
    spread: float
    #: Largest single resting notional on each side.
    top_bid_notional: float
    top_ask_notional: float
    #: True when depth was actually fetched for this instant.
    sampled: bool

    @property
    def is_quotable(self) -> bool:
        return self.spread <= MAX_SPREAD and MIN_MID <= self.mid <= MAX_MID

    def whale_side(self, threshold: float) -> int:
        """+1 bid whale, -1 ask whale, 0 none. Both sides -> the larger."""
        bid = self.top_bid_notional >= threshold
        ask = self.top_ask_notional >= threshold
        if bid and ask:
            return 1 if self.top_bid_notional >= self.top_ask_notional else -1
        if bid:
            return 1
        if ask:
            return -1
        return 0


@dataclass(frozen=True)
class WhaleEvent:
    """A whale appearing, and what the mid did afterwards."""

    game_id: str
    market_slug: str
    at: dt.datetime
    side: int              # +1 bid, -1 ask
    notional: float
    mid: float
    after: dict[float, float]

    def signal(self, horizon: float) -> float | None:
        """Signed move toward the whale's side. Positive = moved toward it."""
        mark = self.after.get(horizon)
        if mark is None:
            return None
        return self.side * (mark - self.mid)


# --------------------------------------------------------------------- #
# Detection — pure, so it is testable without a database
# --------------------------------------------------------------------- #


def detect_appearances(
    series: dict[str, list[BookState]],
    *,
    threshold: float = DEFAULT_WHALE_NOTIONAL,
    horizons: tuple[float, ...] = HORIZON_SECONDS,
) -> list[WhaleEvent]:
    """Per-market book series -> whales appearing, with their price paths.

    Only transitions count. A whale already resting at the previous sampled
    observation is the same whale, not a new one; counting it again would emit
    one observation per snapshot for a wall that never moved, which at 1s
    sampling is thousands of copies of a single event.
    """
    events: list[WhaleEvent] = []
    for states in series.values():
        ordered = sorted(states, key=lambda s: s.captured_at)
        previous_side = 0
        previous_sampled = False

        for state in ordered:
            if not state.sampled:
                # Depth was not fetched here. Do not let a gap in sampling read
                # as the whale having left — that would manufacture a fresh
                # "appearance" the moment sampling resumed.
                continue

            side = state.whale_side(threshold)
            appeared = side != 0 and (previous_side != side) and previous_sampled

            if appeared and state.is_quotable:
                after: dict[float, float] = {}
                for h in horizons:
                    mark = _nearest(ordered, state.captured_at, h)
                    if mark is not None:
                        after[h] = mark.mid
                notional = (
                    state.top_bid_notional if side > 0 else state.top_ask_notional
                )
                events.append(
                    WhaleEvent(
                        game_id=state.game_id,
                        market_slug=state.market_slug,
                        at=state.captured_at,
                        side=side,
                        notional=notional,
                        mid=state.mid,
                        after=after,
                    )
                )

            previous_side = side
            previous_sampled = True
    return events


def _nearest(
    states: list[BookState], origin: dt.datetime, horizon_seconds: float
) -> BookState | None:
    lo, hi = HORIZON_TOLERANCE
    target = origin + dt.timedelta(seconds=horizon_seconds)
    best: BookState | None = None
    best_gap = float("inf")
    for state in states:
        elapsed = (state.captured_at - origin).total_seconds()
        if elapsed <= 0:
            continue
        if elapsed < horizon_seconds * lo or elapsed > horizon_seconds * hi:
            continue
        gap = abs((state.captured_at - target).total_seconds())
        if gap < best_gap:
            best, best_gap = state, gap
    return best


# --------------------------------------------------------------------- #
# Database
# --------------------------------------------------------------------- #


def load_book_states(
    session: Session,
    *,
    as_of: dt.datetime | None,
    since: dt.datetime | None = None,
    live_only: bool = True,
) -> dict[str, list[BookState]]:
    """Per-market book states, with the largest resting notional on each side.

    The depth timestamp is `COALESCE(book_levels.captured_at,
    market_snapshots.captured_at)`. Depth now runs on a slower loop than price,
    so its own timestamp is the correct one; rows predating that column were
    fetched together with their snapshot, where the parent's timestamp was
    correct. Using the parent unconditionally would backdate modern depth rows
    and let a book fetched after a move appear to have preceded it.

    `as_of` is keyword-only with no default, per the project's point-in-time
    rule.
    """
    depth_at = func.coalesce(BookLevel.captured_at, MarketSnapshot.captured_at)

    stmt = (
        select(
            MarketSnapshot.id,
            MarketSnapshot.game_id,
            MarketSnapshot.market_slug,
            MarketSnapshot.captured_at,
            MarketSnapshot.best_bid,
            MarketSnapshot.best_ask,
            func.max(depth_at).label("depth_at"),
            func.max(
                func.coalesce(BookLevel.price * BookLevel.quantity, 0)
            ).filter(BookLevel.side == "bid").label("top_bid"),
            func.max(
                func.coalesce(BookLevel.price * BookLevel.quantity, 0)
            ).filter(BookLevel.side == "offer").label("top_ask"),
            func.count(BookLevel.id).label("n_levels"),
        )
        .select_from(MarketSnapshot)
        .outerjoin(BookLevel, BookLevel.snapshot_id == MarketSnapshot.id)
        .where(
            MarketSnapshot.best_bid.is_not(None),
            MarketSnapshot.best_ask.is_not(None),
            MarketSnapshot.game_id.is_not(None),
        )
        .group_by(MarketSnapshot.id)
    )
    if live_only:
        stmt = stmt.where(MarketSnapshot.is_live.is_(True))
    if as_of is not None:
        stmt = stmt.where(MarketSnapshot.captured_at < as_of)
    if since is not None:
        stmt = stmt.where(MarketSnapshot.captured_at >= since)

    out: dict[str, list[BookState]] = defaultdict(list)
    for (
        _id, game_id, slug, captured_at, bid, ask, depth_ts, top_bid, top_ask, n_levels
    ) in session.execute(stmt).all():
        b, a = float(bid), float(ask)
        if a <= b:
            continue
        out[slug].append(
            BookState(
                game_id=str(game_id),
                market_slug=slug,
                captured_at=depth_ts or captured_at,
                mid=(a + b) / 2.0,
                spread=a - b,
                top_bid_notional=float(top_bid or 0.0),
                top_ask_notional=float(top_ask or 0.0),
                sampled=bool(n_levels),
            )
        )
    return dict(out)


def notional_percentiles(series: dict[str, list[BookState]]) -> dict[str, float]:
    """Distribution of top-of-book notional, to sanity-check the threshold."""
    values = [
        max(s.top_bid_notional, s.top_ask_notional)
        for states in series.values()
        for s in states
        if s.sampled
    ]
    if not values:
        return {}
    values.sort()

    def pct(p: float) -> float:
        return values[min(len(values) - 1, int(p * len(values)))]

    return {
        "n": float(len(values)),
        "p50": pct(0.50),
        "p90": pct(0.90),
        "p99": pct(0.99),
        "max": values[-1],
    }


# --------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------- #


def format_report(
    events: list[WhaleEvent],
    *,
    threshold: float,
    states_examined: int,
    sampled_states: int,
    percentiles: dict[str, float],
    sampling: Cadence | None = None,
) -> str:
    out: list[str] = []
    add = out.append

    add("EXPERIMENT 7 — does resting size predict the next move?")
    add("=" * 78)
    add(f"whale threshold                : ${threshold:,.0f} resting notional "
        f"on one level")
    add(f"book states examined           : {states_examined:,}")
    add(f"  of which depth was sampled   : {sampled_states:,}")
    add(f"whale appearances detected     : {len(events):,}")
    if sampling is not None:
        add(f"snapshot cadence               : median {sampling.median:.0f}s "
            f"(p10 {sampling.p10:.0f}s, p90 {sampling.p90:.0f}s), "
            f"{sampling.under_2min:.0%} under 2 min")
    add("")

    add("PRE-REGISTERED GATE (fixed 2026-08-02, before computing)")
    add("-" * 78)
    add(f"  PASS requires mean signed move toward the whale > 0 at "
        f"+{PRIMARY_HORIZON_SECONDS:.0f}s,")
    add(f"  95% CI clustered by game excluding zero, at n >= {GATE_MIN_EVENTS} "
        f"appearances")
    add(f"  across >= {GATE_MIN_GAMES} games. Economic relevance is reported "
        "against the")
    add(f"  {HALF_SPREAD_REFERENCE:.3f} half-spread, not gated on it: this "
        "signal would skew a")
    add("  resting quote, which is free, rather than cross the spread.")
    add("")

    if percentiles:
        add("Top-of-book notional, for context")
        add("-" * 78)
        add(f"  n={percentiles['n']:,.0f}   median=${percentiles['p50']:,.0f}   "
            f"p90=${percentiles['p90']:,.0f}   p99=${percentiles['p99']:,.0f}   "
            f"max=${percentiles['max']:,.0f}")
        add("")

    if not events:
        add("VERDICT: NO DATA — the experiment has not run.")
        add("")
        add("  Not a null result. Zero whale appearances means the hypothesis")
        add("  was never tested, which is different from being tested and")
        add("  failing.")
        if percentiles and percentiles.get("max", 0) < threshold:
            add("")
            add("  Note: the largest single resting level observed anywhere in")
            add(f"  this sample was ${percentiles['max']:,.0f}, below the "
                f"${threshold:,.0f} threshold.")
            add("  No whale has been seen yet, so none could have been tested.")
        return "\n".join(out)

    games = {e.game_id for e in events}
    by_side: dict[int, int] = defaultdict(int)
    for e in events:
        by_side[e.side] += 1

    add("What the whales looked like")
    add("-" * 78)
    add(f"  bid-side / ask-side          : {by_side[1]} / {by_side[-1]}")
    add(f"  mean notional                : "
        f"${sum(e.notional for e in events) / len(events):,.0f}")
    add(f"  distinct games               : {len(games)}")
    add("")

    add("Signed move toward the whale (positive = price moved to the size)")
    add("-" * 78)
    add(f"  {'horizon':<10}{'n':>6}{'mean':>10}{'95% CI (clustered)':>28}"
        f"{'vs half-spr':>13}")
    primary: tuple[float, object] | None = None
    for h in HORIZON_SECONDS:
        by_game: dict[str, list[float]] = defaultdict(list)
        for e in events:
            sig = e.signal(h)
            if sig is not None:
                by_game[e.game_id].append(sig)
        values = [x for v in by_game.values() for x in v]
        if not values:
            add(f"  +{h:<9.0f}{'0':>6}{'—':>10}{'—':>28}{'—':>13}")
            continue
        mean = sum(values) / len(values)
        cl = clustered_mean(by_game)
        ci = f"[{cl.lo:+.4f}, {cl.hi:+.4f}]" if cl else "n/a (<2 games)"
        ratio = f"{mean / HALF_SPREAD_REFERENCE:+.2f}x"
        marker = "  <- gate" if h == PRIMARY_HORIZON_SECONDS else ""
        add(f"  +{h:<9.0f}{len(values):>6}{mean:>+10.4f}{ci:>28}{ratio:>13}{marker}")
        if h == PRIMARY_HORIZON_SECONDS:
            primary = (mean, cl)
    add("")

    add("VERDICT")
    add("-" * 78)
    if len(events) < GATE_MIN_EVENTS or len(games) < GATE_MIN_GAMES:
        add(f"  NO DATA — {len(events)} appearances across {len(games)} games, "
            "against a")
        add(f"  pre-registered minimum of {GATE_MIN_EVENTS} across "
            f"{GATE_MIN_GAMES} games.")
        add("")
        missing = []
        if len(events) < GATE_MIN_EVENTS:
            missing.append(f"{GATE_MIN_EVENTS - len(events)} more appearances")
        if len(games) < GATE_MIN_GAMES:
            missing.append(f"{GATE_MIN_GAMES - len(games)} more games")
        add(f"  Needs {' and '.join(missing)}. This is NOT a null result: the")
        add("  detector is built and will accrue. What it needs is games.")
        if sampling is not None and not sampling.is_fast:
            add("")
            add(f"  Cadence caveat: at a {sampling.median:.0f}s median gap, most")
            add("  appearances have no observation at all inside the +30s and")
            add("  +60s horizons, so the primary mark is mostly unmeasurable.")
            add("  The 1s recorder shipped 2026-08-02.")
    elif primary is None or primary[1] is None:
        add("  NO DATA — no move observable at the primary horizon.")
    else:
        mean, cl = primary
        if mean > 0 and cl.lo > 0:
            add(f"  PASS — price moves {mean:+.4f} toward the size at "
                f"+{PRIMARY_HORIZON_SECONDS:.0f}s,")
            add(f"  95% CI [{cl.lo:+.4f}, {cl.hi:+.4f}] excludes zero.")
            add("")
            if abs(mean) < HALF_SPREAD_REFERENCE / 2:
                add(f"  But it is {mean / HALF_SPREAD_REFERENCE:.2f}x the "
                    "half-spread — real and probably")
                add("  too small to skew a quote by. Real is not the same as useful.")
        else:
            add(f"  FAIL — {mean:+.4f} at +{PRIMARY_HORIZON_SECONDS:.0f}s, "
                f"95% CI [{cl.lo:+.4f}, {cl.hi:+.4f}].")
            add("  Resting size does not predict the next move. Quotes should")
            add("  ignore the book beyond the top.")
    return "\n".join(out)


def run(
    session: Session,
    *,
    as_of: dt.datetime | None = None,
    threshold: float = DEFAULT_WHALE_NOTIONAL,
    since: dt.datetime | None = None,
    live_only: bool = True,
) -> str:
    series = load_book_states(session, as_of=as_of, since=since, live_only=live_only)
    states = sum(len(v) for v in series.values())
    sampled = sum(1 for v in series.values() for s in v if s.sampled)
    events = detect_appearances(series, threshold=threshold)
    return format_report(
        events,
        threshold=threshold,
        states_examined=states,
        sampled_states=sampled,
        percentiles=notional_percentiles(series),
        sampling=cadence(series),
    )


def main() -> int:
    from core.storage import get_engine, get_sessionmaker

    parser = argparse.ArgumentParser(prog="meridian-depth-signal")
    parser.add_argument("--whale", type=float, default=DEFAULT_WHALE_NOTIONAL,
                        help="resting notional in dollars that counts as a whale")
    parser.add_argument("--days", type=int, default=None)
    parser.add_argument("--include-pregame", action="store_true")
    args = parser.parse_args()

    since = dt.datetime.now(UTC) - dt.timedelta(days=args.days) if args.days else None
    Session = get_sessionmaker(get_engine())
    with Session() as session:
        print(
            run(
                session,
                threshold=args.whale,
                since=since,
                live_only=not args.include_pregame,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
