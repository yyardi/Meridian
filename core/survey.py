"""Board survey — is a league's board worth trading, measured the same way twice.

    python -m core.survey --league nba              # the October decision
    python -m core.survey --league mlb              # reproduce V7
    python -m core.survey --league wnba --source recorded

Why this exists
---------------
MLB was killed in a single afternoon by five numbers: spread width, tick size,
depth at the touch, the fee coefficient, and how many rungs a game carries
(finding **V7** — *"Polymarket US MLB is 1c wide with half-cent ticks, 30
events, 405 markets. No venue gap. Decided we stay WNBA."*).

That was done by hand and the numbers were never persisted. When Polymarket US
lists NBA preseason boards in October the same question arrives with real money
behind it, and re-deriving the method under time pressure is how a decision
gets made on whichever statistic is easiest to compute that day. So the method
is a module now, runnable the day the board appears.

**This module reaches no conclusions, and that is deliberate.**
--------------------------------------------------------------
There is no PASS, no FAIL, no gate and no threshold anywhere in this file, and
none should be added. Every other measurement in this project carries a
pre-registered gate because it tests a stated hypothesis. This one is a
*survey*: it describes a board nobody has seen yet. A threshold written today
would be a guess about October dressed as a criterion, and the moment it
existed the decision would be made by whoever chose the number rather than by
someone looking at the board.

What it does instead is print the target league beside the **recorded WNBA
board** as a baseline, because "1c wide" means nothing until you know the
number it is being compared with. The verdict is the October run plus a doc
entry, written by a human who has looked at both columns.

The comparison that killed MLB, restated
----------------------------------------
The venue gap this project trades exists because WNBA is a *thin* corner of the
venue. Thinness is the edge. A board that is tighter, deeper and more liquid
than WNBA's is a board with no gap to trade — which is why MLB's 1c spread was
a rejection rather than an attraction.

So every statistic here should be read as *"how much worse than WNBA is this,
and is that the direction we need?"* — and the direction we need is **worse**.

Two sources, and they are not interchangeable
---------------------------------------------
**`--source live`** hits the venue. One request returns the whole board with
best bid/ask embedded for every market ([infra/live-cadence.md](../docs/infra/live-cadence.md)),
so spreads, ticks, fees and ladder counts cost a single call. **Depth at the
touch does not** — it needs one book call per market, which is why depth is
sampled rather than exhaustive and the sample size is always printed.

**`--source recorded`** reads `market_snapshots` / `book_levels`. Only WNBA is
recorded (measured 2026-08-07: 3,582,007 rows, all `wnba`), so this is the
baseline path and nothing else.

**V7's MLB numbers were never persisted.** There is no recorded MLB data in
this database to validate against — `--league mlb` therefore re-measures the
live MLB board, which is exactly how V7 itself was produced. If the tool
reproduces ~1c spreads and half-cent ticks, it works.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import random
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass, field

import structlog

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc

#: The board we compare everything against. Not a parameter: the whole point is
#: that one side of the table is the market this project already knows.
BASELINE_LEAGUE = "wnba"

#: How many markets to pull depth for when surveying live. Depth is the only
#: statistic that costs one request per market, and at ~5 req/s a 405-market
#: board is 80 seconds. A sample answers the shape question; the count is
#: always reported so nobody reads it as exhaustive.
DEFAULT_DEPTH_SAMPLE = 40

#: Contracts near the money are the only ones whose spread means anything —
#: a 0.02 rung quoting 0.01/0.05 is not a 4c market, it is an empty one.
#: Same band the microstructure studies use, imported in spirit rather than by
#: import: this module must run against leagues those studies never saw.
NEAR_MONEY_LO, NEAR_MONEY_HI = 0.20, 0.80

#: Hours-to-tip-off buckets. **The most important control in this module.**
#:
#: Measured on the recorded WNBA board 2026-08-07, near-money markets only:
#:
#:     inside 3h   1.00c median spread   (n=103)
#:     12-24h     12.00c median spread   (n=46)
#:
#: A **12x** difference from timing alone. An October NBA preseason board will
#: be days from tip-off; the recorded WNBA baseline is dominated by snapshots
#: taken near it. Compared at face value, NBA would look ~12x wider than it is
#: — and "wider" reads as "thinner", which reads as "tradable". That is the
#: exact shape of a confounded comparison talking someone into a market.
#:
#: So every spread number is also reported per horizon bucket, and the columns
#: must be compared row by row rather than headline to headline.
HORIZON_BUCKETS: tuple[tuple[str, float, float], ...] = (
    ("live/past", -1e9, 0.0),
    ("0-3h", 0.0, 3.0),
    ("3-6h", 3.0, 6.0),
    ("6-12h", 6.0, 12.0),
    ("12-24h", 12.0, 24.0),
    ("24-72h", 24.0, 72.0),
    (">72h", 72.0, 1e9),
)


@dataclass
class MarketObs:
    """One market's top of book at one instant."""

    market_slug: str
    event_slug: str | None
    market_type: str | None
    bid: float | None
    ask: float | None
    tick_size: float | None
    fee_coefficient: float | None
    #: Hours from this observation to tip-off. Negative once the game started.
    hours_to_tipoff: float | None = None

    @property
    def horizon_bucket(self) -> str | None:
        h = self.hours_to_tipoff
        if h is None:
            return None
        for label, lo, hi in HORIZON_BUCKETS:
            if lo <= h < hi:
                return label
        return None

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
    def is_near_money(self) -> bool:
        m = self.mid
        return m is not None and NEAR_MONEY_LO <= m <= NEAR_MONEY_HI

    @property
    def tick_pct_of_value(self) -> float | None:
        """The tick as a fraction of what a contract costs.

        This is the statistic that makes a "1c tick" mean two different things.
        At 0.50 a 1c tick is 2% of value; at 0.16 it is 6.25% (finding V2). A
        board quoted in the same absolute tick is a coarser board wherever its
        contracts are cheap.
        """
        m = self.mid
        if m is None or self.tick_size is None or m <= 0:
            return None
        return self.tick_size / m


@dataclass
class DepthObs:
    """Resting size at the touch, one side of one market."""

    market_slug: str
    side: str
    price: float
    quantity: float

    @property
    def notional(self) -> float:
        return self.price * self.quantity


@dataclass
class Survey:
    """Everything measured for one league. No verdict field, on purpose."""

    league: str
    source: str
    captured_at: dt.datetime
    markets: list[MarketObs] = field(default_factory=list)
    depth: list[DepthObs] = field(default_factory=list)
    #: Why markets were skipped, so a thin table is never mistaken for a thin
    #: board.
    skips: dict[str, int] = field(default_factory=dict)
    depth_markets_sampled: int = 0
    depth_markets_available: int = 0

    @property
    def n_events(self) -> int:
        return len({m.event_slug for m in self.markets if m.event_slug})

    @property
    def n_markets(self) -> int:
        return len({m.market_slug for m in self.markets})

    @property
    def quoted(self) -> list[MarketObs]:
        return [m for m in self.markets if m.spread is not None]

    @property
    def near_money(self) -> list[MarketObs]:
        return [m for m in self.quoted if m.is_near_money]


def _pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(p * len(ordered)))]


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _hours_until(start_time, now: dt.datetime) -> float | None:
    """Hours from `now` to a venue-supplied ISO start time. None if unusable."""
    if not start_time:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(start_time).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return (parsed - now).total_seconds() / 3600.0


def spread_by_horizon(survey: Survey) -> dict[str, tuple[int, float | None]]:
    """Near-money median spread per hours-to-tip-off bucket.

    The control that makes two boards comparable. See `HORIZON_BUCKETS`.
    """
    buckets: dict[str, list[float]] = defaultdict(list)
    for m in survey.near_money:
        label = m.horizon_bucket
        if label is not None and m.spread is not None:
            buckets[label].append(m.spread)
    return {label: (len(v), _median(v)) for label, v in buckets.items()}


# --------------------------------------------------------------------- #
# Source: the live venue
# --------------------------------------------------------------------- #


def survey_live(
    client,
    league: str,
    *,
    depth_sample: int = DEFAULT_DEPTH_SAMPLE,
    seed: int = 0,
) -> Survey:
    """Survey a league's live board.

    One request gets the whole board with best bid/ask embedded. Depth costs
    one request per market, so it is sampled — `seed` is fixed so two runs on
    the same board sample the same markets and can be diffed.
    """
    skips: dict[str, int] = defaultdict(int)
    parsed, _raw = client.get_league_events(league=league)

    markets: list[MarketObs] = []
    now = dt.datetime.now(UTC)
    for event in parsed.events:
        hours = _hours_until(getattr(event, "start_time", None), now)
        for market in event.markets:
            slug = getattr(market, "slug", None)
            if not slug:
                skips["market with no slug"] += 1
                continue
            bid, ask = market.best_bid, market.best_ask
            markets.append(MarketObs(
                market_slug=slug,
                event_slug=event.slug,
                market_type=getattr(market, "sports_market_type", None),
                bid=float(bid) if bid is not None else None,
                ask=float(ask) if ask is not None else None,
                tick_size=(float(market.order_price_min_tick_size)
                           if getattr(market, "order_price_min_tick_size", None) is not None
                           else None),
                fee_coefficient=(float(market.fee_coefficient)
                                 if getattr(market, "fee_coefficient", None) is not None
                                 else None),
                hours_to_tipoff=hours,
            ))

    # Depth, sampled. Prefer near-money markets: depth on a 0.02 rung is not
    # the number anyone is deciding on, and spending the request budget there
    # would answer a question nobody asked.
    candidates = [m for m in markets if m.is_near_money] or [m for m in markets if m.spread is not None]
    rng = random.Random(seed)
    chosen = candidates if len(candidates) <= depth_sample else rng.sample(candidates, depth_sample)

    depth: list[DepthObs] = []
    sampled = 0
    for market in chosen:
        try:
            book, _ = client.get_book(market.market_slug)
        except Exception as exc:                       # noqa: BLE001
            skips[f"book call failed ({type(exc).__name__})"] += 1
            continue
        data = book.market_data
        if data is None:
            skips["book call returned no marketData"] += 1
            continue
        sampled += 1
        for side, entries in (("bid", data.bids), ("offer", data.offers)):
            if not entries:
                continue
            top = entries[0]
            price = top.px.value if top.px else None
            if price is None or top.qty is None:
                continue
            depth.append(DepthObs(market_slug=market.market_slug, side=side,
                                  price=float(price), quantity=float(top.qty)))

    return Survey(
        league=league, source="live", captured_at=dt.datetime.now(UTC),
        markets=markets, depth=depth, skips=dict(skips),
        depth_markets_sampled=sampled, depth_markets_available=len(candidates),
    )


# --------------------------------------------------------------------- #
# Source: our own recording
# --------------------------------------------------------------------- #


def survey_recorded(session, league: str) -> Survey:
    """Survey a league from `market_snapshots` / `book_levels`.

    One observation per market — its most recent **pregame** snapshot. Pregame
    because that is the board a survey is about: whether the league is worth
    trading at all, not how it behaves once a game is running. Taking every
    tick instead would weight the answer by how long each market happened to be
    recorded, which is a fact about the recorder.
    """
    from sqlalchemy import text

    skips: dict[str, int] = {}

    rows = session.execute(text("""
        SELECT DISTINCT ON (market_slug)
               id, market_slug, event_slug, sports_market_type,
               best_bid, best_ask, min_tick_size, fee_coefficient,
               EXTRACT(EPOCH FROM (game_start_time - captured_at)) / 3600.0 AS hours_to_tipoff
        FROM market_snapshots
        WHERE event_slug LIKE :prefix
          AND is_live IS FALSE
        ORDER BY market_slug, captured_at DESC
    """), {"prefix": f"{league}-%"}).all()

    markets = [
        MarketObs(
            market_slug=r.market_slug, event_slug=r.event_slug,
            market_type=r.sports_market_type,
            bid=float(r.best_bid) if r.best_bid is not None else None,
            ask=float(r.best_ask) if r.best_ask is not None else None,
            tick_size=float(r.min_tick_size) if r.min_tick_size is not None else None,
            fee_coefficient=(float(r.fee_coefficient)
                             if r.fee_coefficient is not None else None),
            hours_to_tipoff=(float(r.hours_to_tipoff)
                             if r.hours_to_tipoff is not None else None),
        )
        for r in rows
    ]

    snapshot_ids = [r.id for r in rows]
    depth: list[DepthObs] = []
    sampled = 0
    if snapshot_ids:
        levels = session.execute(text("""
            SELECT m.market_slug, b.side, b.price, b.quantity
            FROM book_levels b
            JOIN market_snapshots m ON m.id = b.snapshot_id
            WHERE b.snapshot_id = ANY(:ids) AND b.level_index = 0
        """), {"ids": snapshot_ids}).all()
        depth = [DepthObs(market_slug=l.market_slug, side=l.side,
                          price=float(l.price), quantity=float(l.quantity))
                 for l in levels]
        sampled = len({l.market_slug for l in levels})

    if not markets:
        skips[f"no recorded pregame rows for league '{league}'"] = 1

    return Survey(
        league=league, source="recorded", captured_at=dt.datetime.now(UTC),
        markets=markets, depth=depth, skips=skips,
        depth_markets_sampled=sampled, depth_markets_available=len(markets),
    )


# --------------------------------------------------------------------- #
# Statistics
# --------------------------------------------------------------------- #


@dataclass(frozen=True)
class TypeStat:
    market_type: str
    n: int
    n_near: int
    spread_median: float | None
    spread_p10: float | None
    tick_pct_median: float | None


def stats_by_type(survey: Survey) -> list[TypeStat]:
    """Spread and tick statistics per market type.

    Spread percentiles are computed on **near-money markets only**. A deep rung
    quoting 0.01/0.26 is not a 25c market, it is an empty book with two stale
    orders in it, and letting those into a median makes any board look wide.
    """
    by_type: dict[str, list[MarketObs]] = defaultdict(list)
    for m in survey.quoted:
        by_type[m.market_type or "unknown"].append(m)

    out: list[TypeStat] = []
    for market_type, group in sorted(by_type.items()):
        near = [m for m in group if m.is_near_money]
        spreads = [m.spread for m in near if m.spread is not None]
        ticks = [m.tick_pct_of_value for m in near if m.tick_pct_of_value is not None]
        out.append(TypeStat(
            market_type=market_type, n=len(group), n_near=len(near),
            spread_median=_median(spreads), spread_p10=_pct(spreads, 0.10),
            tick_pct_median=_median(ticks),
        ))
    return out


def ladders_per_event(survey: Survey) -> tuple[float | None, int]:
    """Median markets per event, and the number of events it is over."""
    per_event: dict[str, set[str]] = defaultdict(set)
    for m in survey.markets:
        if m.event_slug:
            per_event[m.event_slug].add(m.market_slug)
    counts = [float(len(v)) for v in per_event.values()]
    return _median(counts), len(counts)


def fee_coefficients(survey: Survey) -> dict[float, int]:
    """Every distinct fee coefficient on the board, with counts.

    A dict rather than a mean: V9 found a single value across 874,267 rows, and
    the useful signal here is whether that is still true, not what the average
    of a mixture would be.
    """
    out: dict[float, int] = defaultdict(int)
    for m in survey.markets:
        if m.fee_coefficient is not None:
            out[round(m.fee_coefficient, 6)] += 1
    return dict(out)


def tick_sizes(survey: Survey) -> dict[float, int]:
    out: dict[float, int] = defaultdict(int)
    for m in survey.markets:
        if m.tick_size is not None:
            out[round(m.tick_size, 6)] += 1
    return dict(out)


def depth_notionals(survey: Survey) -> list[float]:
    return [d.notional for d in survey.depth]


# --------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------- #


def _fmt_cents(v: float | None) -> str:
    return "—" if v is None else f"{v * 100:.2f}c"


def _fmt_pct(v: float | None) -> str:
    return "—" if v is None else f"{v * 100:.2f}%"


def _fmt_money(v: float | None) -> str:
    return "—" if v is None else f"${v:,.0f}"


def _fmt_num(v: float | None, dp: int = 0) -> str:
    return "—" if v is None else f"{v:,.{dp}f}"


def _counts_line(counts: dict[float, int]) -> str:
    if not counts:
        return "—"
    total = sum(counts.values())
    parts = [f"{k:g} ({v / total:.0%})" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])]
    return ", ".join(parts[:3])


def format_report(target: Survey, baseline: Survey | None) -> str:
    """Target beside baseline. Describes; does not decide."""
    out: list[str] = []
    add = out.append
    cols = (target, baseline) if baseline is not None else (target,)
    head = [f"{s.league.upper()} ({s.source})" for s in cols]

    add("BOARD SURVEY")
    add("=" * 78)
    for s in cols:
        add(f"{s.league.upper():<6} source={s.source:<9} "
            f"captured={s.captured_at:%Y-%m-%d %H:%M}Z  "
            f"events={s.n_events}  markets={s.n_markets}  "
            f"quoted={len(s.quoted)}  near-money={len(s.near_money)}")
    add("")
    add("This report reaches NO conclusion. It has no gate and no threshold, by")
    add("design — see the module docstring. The decision is a human reading both")
    add("columns and writing it down.")
    add("")

    def row(label: str, values: list[str], indent: int = 2) -> None:
        cells = "".join(f"{v:>22}" for v in values)
        add(f"{' ' * indent}{label:<30}{cells}")

    add("Board shape")
    add("-" * 78)
    row("", head)
    row("events", [_fmt_num(s.n_events) for s in cols])
    row("markets", [_fmt_num(s.n_markets) for s in cols])
    med = [ladders_per_event(s) for s in cols]
    row("median markets per event", [_fmt_num(m[0], 1) for m in med])
    row("tick sizes on the board", [_counts_line(tick_sizes(s)) for s in cols])
    row("fee coefficients", [_counts_line(fee_coefficients(s)) for s in cols])
    add("")

    add("Spread, near-money markets only (mid in [0.20, 0.80])")
    add("-" * 78)
    add("  A deep rung quoting 0.01/0.26 is an empty book, not a 25c market.")
    all_types = sorted({t.market_type for s in cols for t in stats_by_type(s)})
    row("", head)
    for market_type in all_types:
        per_col = []
        for s in cols:
            match = next((t for t in stats_by_type(s) if t.market_type == market_type), None)
            per_col.append("—" if match is None
                           else f"{_fmt_cents(match.spread_median)} (n={match.n_near})")
        row(market_type.replace("basketball_team_full_game_", "")[:28], per_col)
    add("")
    row("ALL near-money, median", [
        _fmt_cents(_median([m.spread for m in s.near_money if m.spread is not None]))
        for s in cols])
    row("ALL near-money, p10", [
        _fmt_cents(_pct([m.spread for m in s.near_money if m.spread is not None], 0.10))
        for s in cols])
    add("")

    add("Spread by hours to tip-off — COMPARE THESE ROWS, NOT THE HEADLINES")
    add("-" * 78)
    add("  Measured on WNBA: 1.00c inside 3h against 12.00c at 12-24h. A 12x")
    add("  swing from timing alone. A far-dated board looks thin when it is only")
    add("  early, and 'thin' is what this project buys — so an unmatched")
    add("  comparison argues for entering a market on a clock artifact.")
    row("", head)
    per_col_h = [spread_by_horizon(s_) for s_ in cols]
    for label, _lo, _hi in HORIZON_BUCKETS:
        cells = []
        for h in per_col_h:
            n, med = h.get(label, (0, None))
            cells.append("—" if not n else f"{_fmt_cents(med)} (n={n})")
        if any(c != "—" for c in cells):
            row(label, cells)
    add("")
    medians = [
        _median([m.hours_to_tipoff for m in s_.near_money
                 if m.hours_to_tipoff is not None])
        for s_ in cols
    ]
    row("median hours to tip-off", [
        "—" if v is None else f"{v:+.1f}h" for v in medians])
    if len(cols) == 2:
        shared = [label for label, _lo, _hi in HORIZON_BUCKETS
                  if all(h.get(label, (0, None))[0] for h in per_col_h)]
        if all(v is not None for v in medians):
            gap = abs(medians[0] - medians[1])
            if gap >= 6.0:
                add("")
                add(f"  !! The two columns sit {gap:.1f}h apart in median time to tip-off.")
                add("     Their headline spreads are NOT comparable at face value.")
        if shared:
            add("")
            add(f"  Buckets with data on BOTH sides: {', '.join(shared)}. Those rows are")
            add("  the only like-for-like comparison in this table.")
        else:
            add("")
            add("  !! NO horizon bucket has data on both sides. There is currently no")
            add("     like-for-like row in this table at all — the two boards were")
            add("     observed at non-overlapping distances from tip-off. Do not read")
            add("     adjacent rows as a comparison; re-run when the horizons overlap,")
            add("     or record the target board across a full pregame cycle first.")
    add("")

    add("Tick as a share of contract value, near-money")
    add("-" * 78)
    add("  The number that makes '1c tick' mean two different things: 1c is 2%")
    add("  of a 50c contract and 6.25% of a 16c one (V2).")
    row("", head)
    row("median tick / mid", [
        _fmt_pct(_median([m.tick_pct_of_value for m in s.near_money
                          if m.tick_pct_of_value is not None]))
        for s in cols])
    add("")

    add("Depth at the touch")
    add("-" * 78)
    row("", head)
    row("markets sampled", [
        f"{s.depth_markets_sampled} of {s.depth_markets_available}" for s in cols])
    row("top-of-book notional, median", [_fmt_money(_median(depth_notionals(s))) for s in cols])
    row("  p10", [_fmt_money(_pct(depth_notionals(s), 0.10)) for s in cols])
    row("  p90", [_fmt_money(_pct(depth_notionals(s), 0.90)) for s in cols])
    row("observations", [_fmt_num(len(s.depth)) for s in cols])
    add("")

    for s in cols:
        if s.skips:
            add(f"Skipped — {s.league.upper()}")
            add("-" * 78)
            for reason, n in sorted(s.skips.items(), key=lambda kv: -kv[1]):
                add(f"  {reason:<56}: {n:>8,}")
            add("")

    add("How to read this")
    add("-" * 78)
    add("  The edge this project trades is the venue gap, and the gap exists")
    add("  because WNBA is a THIN corner of the venue. Thinness is the product.")
    add("  A board that is TIGHTER, DEEPER and better quoted than the baseline is")
    add("  a board with less to trade, not more — which is why MLB's 1c spread")
    add("  was a rejection (V7) and not an attraction.")
    add("")
    add("  Nothing here decides that. Run it, read both columns, write the")
    add("  finding down with a date.")
    return "\n".join(out)


# --------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------- #


def _load_baseline(league: str) -> Survey | None:
    """The recorded WNBA board, or None if it is the target itself."""
    from core.storage import get_engine, get_sessionmaker

    if league == BASELINE_LEAGUE:
        return None
    Session = get_sessionmaker(get_engine())
    with Session() as session:
        return survey_recorded(session, BASELINE_LEAGUE)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="meridian-survey")
    parser.add_argument("--league", required=True,
                        help="league slug as the venue names it, e.g. nba, mlb, wnba")
    parser.add_argument("--source", choices=("live", "recorded"), default="live",
                        help="'live' hits the venue; 'recorded' reads our own "
                             "snapshots (only wnba is recorded)")
    parser.add_argument("--depth-sample", type=int, default=DEFAULT_DEPTH_SAMPLE,
                        help="markets to pull depth for when live (one request each)")
    parser.add_argument("--no-baseline", action="store_true",
                        help="skip the recorded WNBA comparison column")
    args = parser.parse_args(argv)

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.WARNING)
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))

    if args.source == "recorded":
        from core.storage import get_engine, get_sessionmaker
        Session = get_sessionmaker(get_engine())
        with Session() as session:
            target = survey_recorded(session, args.league)
    else:
        from core.polymarket.client import PolymarketGatewayClient
        client = PolymarketGatewayClient()
        target = survey_live(client, args.league, depth_sample=args.depth_sample)

    baseline = None if args.no_baseline else _load_baseline(args.league)
    print(format_report(target, baseline))

    # A survey that found nothing must say so rather than printing empty
    # columns that read like a thin board.
    if not target.markets:
        print()
        print(f"NOTE: no markets were returned for league '{args.league}'. That is a")
        print("statement about the request, not about the board — check the league")
        print("slug and whether the venue lists it yet.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
