"""Experiment 4 — the news-window detector.

The thesis in one line
----------------------
Sportsbooks reprice on news within seconds. A thin venue like Polymarket US
may still be showing the old number minutes later. If so, a resting (maker)
order at the stale price captures the move for free.

This module does not assume that lag exists. It measures it.

How a window is defined
-----------------------
1. **Trigger.** Between two consecutive book polls for the same game, the
   multi-book consensus total moves by at least `trigger_points`. That is the
   news arriving, observed indirectly — we never see the headline, only the
   market's reaction to it, which is the part we could trade anyway.
2. **Response.** Take Polymarket snapshots of the same game and fit the totals
   ladder to an implied mean at each cycle. Compare that implied mean against
   the *new* book number.
3. **Staleness.** If PM's implied mean is still sitting near the *old* book
   number after the move, the venue has not repriced and the gap is tradable.

    staleness = |PM implied mean − new book line|

   A staleness near the size of the move means PM has not moved at all; a
   staleness near zero means it repriced before we could look.

Two honesty constraints, both structural
----------------------------------------
**Cadence bounds what is observable.** The book leg is polled every ~20 min and
the PM leg every 15 min near tip-off but only every 60 min when idle. A lag the
literature describes in *minutes* cannot be resolved by samples an hour apart.
So a null result from this detector is ambiguous in a specific way: it cannot
distinguish "PM repriced quickly" from "PM repriced slowly and we blinked". The
report says so rather than reading silence as evidence of efficiency.

**The gap must survive costs.** A 2-point stale line is not 2 points of profit.
It is converted to a probability edge through the same sigma the model prices
with, and then the venue's fee is subtracted. Only what is left counts.

    python -m core.window_detector
"""

from __future__ import annotations

import argparse
import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field

from scipy.stats import norm
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.backtest.engine import _is_live_provider
from core.storage import MarketSnapshot, SportsbookOdds
from strategies.wnba_totals.model.curve_fit import LadderRung, fit_from_rungs

UTC = dt.timezone.utc

#: A consensus move at least this large is treated as news arriving. 1.5 points
#: is the pre-registered trigger: real same-provider pregame drift averages
#: 0.3-0.6 points, so this is comfortably outside ordinary noise.
DEFAULT_TRIGGER_POINTS = 1.5

#: Ignore "moves" separated by more than this — two polls six hours apart say
#: nothing about a minutes-scale reaction, and calling that a window would
#: invent an event the data cannot support.
MAX_TRIGGER_GAP_MINUTES = 45.0

#: Polymarket US taker fee is levied on the notional; a maker order earns a
#: rebate, but assume zero rather than a credit so the gate cannot be passed
#: by an accounting assumption.
DEFAULT_FEE = 0.0

#: Below this the edge is inside the ladder fit's own error.
MIN_TRADABLE_EDGE_PROB = 0.01


@dataclass(frozen=True)
class BookMove:
    """A consensus move between two consecutive polls of the same game."""

    espn_game_id: str
    from_at: dt.datetime
    to_at: dt.datetime
    from_line: float
    to_line: float

    @property
    def delta(self) -> float:
        return self.to_line - self.from_line

    @property
    def minutes(self) -> float:
        return (self.to_at - self.from_at).total_seconds() / 60.0


@dataclass(frozen=True)
class PMReading:
    """Polymarket's implied total at one instant."""

    captured_at: dt.datetime
    implied_mean: float
    implied_stdev: float


@dataclass
class WindowObservation:
    """One trigger and what Polymarket did afterwards."""

    move: BookMove
    before: PMReading | None = None
    after: list[PMReading] = field(default_factory=list)

    @property
    def first_after(self) -> PMReading | None:
        return self.after[0] if self.after else None

    @property
    def lag_minutes(self) -> float | None:
        """How long after the book move we first observed PM."""
        first = self.first_after
        if first is None:
            return None
        return (first.captured_at - self.move.to_at).total_seconds() / 60.0

    @property
    def staleness_points(self) -> float | None:
        """How far PM still sat from the NEW book number when next observed.

        This is the tradable quantity: the venue showing an old opinion.
        """
        first = self.first_after
        if first is None:
            return None
        return first.implied_mean - self.move.to_line

    def edge_probability(self, fee: float = DEFAULT_FEE) -> float | None:
        """Staleness converted to a net probability edge.

        Points are not money — the same conversion [what-the-edge-is-worth.md]
        uses. A stale line of `s` points under a scoring environment of sigma is
        worth Φ(s/σ) − 0.5 of probability on the correct side, less fees.
        """
        stale = self.staleness_points
        first = self.first_after
        if stale is None or first is None or first.implied_stdev <= 0:
            return None
        gross = abs(float(norm.cdf(abs(stale) / first.implied_stdev)) - 0.5)
        return gross - fee

    def is_tradable(self, fee: float = DEFAULT_FEE) -> bool:
        edge = self.edge_probability(fee)
        return edge is not None and edge >= MIN_TRADABLE_EDGE_PROB


# --------------------------------------------------------------------- #
# Detection — pure functions, so the logic is testable without a database
# --------------------------------------------------------------------- #


def detect_moves(
    series: dict[str, list[tuple[dt.datetime, float]]],
    *,
    trigger_points: float = DEFAULT_TRIGGER_POINTS,
    max_gap_minutes: float = MAX_TRIGGER_GAP_MINUTES,
) -> list[BookMove]:
    """Consensus time series per game -> the moves that count as news.

    Pairs separated by more than `max_gap_minutes` are skipped: a move observed
    across a six-hour hole is not an event, it is two unrelated observations.
    """
    moves: list[BookMove] = []
    for game_id, points in series.items():
        ordered = sorted(points, key=lambda p: p[0])
        for (t0, l0), (t1, l1) in zip(ordered, ordered[1:]):
            gap = (t1 - t0).total_seconds() / 60.0
            if gap > max_gap_minutes:
                continue
            if abs(l1 - l0) >= trigger_points:
                moves.append(
                    BookMove(
                        espn_game_id=game_id, from_at=t0, to_at=t1,
                        from_line=l0, to_line=l1,
                    )
                )
    return moves


def attach_pm_readings(
    moves: list[BookMove],
    readings: dict[str, list[PMReading]],
    *,
    horizon_minutes: float = 90.0,
) -> list[WindowObservation]:
    """Pair each trigger with the PM readings either side of it."""
    out: list[WindowObservation] = []
    for move in moves:
        series = sorted(readings.get(move.espn_game_id, []), key=lambda r: r.captured_at)
        before = [r for r in series if r.captured_at <= move.from_at]
        after = [
            r for r in series
            if move.to_at <= r.captured_at
            <= move.to_at + dt.timedelta(minutes=horizon_minutes)
        ]
        out.append(
            WindowObservation(
                move=move,
                before=before[-1] if before else None,
                after=after,
            )
        )
    return out


# --------------------------------------------------------------------- #
# Database-backed loaders
# --------------------------------------------------------------------- #


def load_book_series(
    session: Session, *, since: dt.datetime | None = None
) -> dict[str, list[tuple[dt.datetime, float]]]:
    """Per-game median consensus total at each poll instant.

    Live-odds providers are excluded for the same reason the backtest excludes
    them: their lines are set during the game and would register as enormous
    "news" every time the score changed.
    """
    stmt = select(
        SportsbookOdds.espn_game_id,
        SportsbookOdds.captured_at,
        SportsbookOdds.over_under,
        SportsbookOdds.provider_name,
    ).where(SportsbookOdds.over_under.is_not(None))
    if since is not None:
        stmt = stmt.where(SportsbookOdds.captured_at >= since)

    grouped: dict[tuple[str, dt.datetime], list[float]] = defaultdict(list)
    for game_id, captured_at, over_under, provider in session.execute(stmt).all():
        if _is_live_provider(provider):
            continue
        grouped[(game_id, captured_at)].append(float(over_under))

    series: dict[str, list[tuple[dt.datetime, float]]] = defaultdict(list)
    for (game_id, captured_at), values in grouped.items():
        values.sort()
        series[game_id].append((captured_at, values[len(values) // 2]))
    return dict(series)


def load_pm_readings(
    session: Session, *, since: dt.datetime | None = None
) -> dict[str, list[PMReading]]:
    """Fit the Polymarket totals ladder to an implied mean at each cycle.

    Keyed by `game_id` as the recorder stored it. Live cycles are dropped: once
    a game tips, the ladder reflects the score, not a pregame opinion.
    """
    stmt = select(
        MarketSnapshot.game_id,
        MarketSnapshot.captured_at,
        MarketSnapshot.line,
        MarketSnapshot.best_bid,
        MarketSnapshot.best_ask,
        MarketSnapshot.is_live,
    ).where(MarketSnapshot.sports_market_type == "basketball_team_full_game_total")
    if since is not None:
        stmt = stmt.where(MarketSnapshot.captured_at >= since)

    cycles: dict[tuple[str, dt.datetime], list[LadderRung]] = defaultdict(list)
    for game_id, captured_at, line, bid, ask, is_live in session.execute(stmt).all():
        if is_live or line is None or game_id is None:
            continue
        cycles[(game_id, captured_at)].append(
            LadderRung(
                float(line),
                float(bid) if bid is not None else None,
                float(ask) if ask is not None else None,
            )
        )

    out: dict[str, list[PMReading]] = defaultdict(list)
    for (game_id, captured_at), rungs in cycles.items():
        fit = fit_from_rungs(rungs)
        if not fit.ok or fit.implied_mean is None or fit.implied_stdev is None:
            continue
        out[game_id].append(
            PMReading(
                captured_at=captured_at,
                implied_mean=fit.implied_mean,
                implied_stdev=fit.implied_stdev,
            )
        )
    return dict(out)


# --------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------- #


#: The pre-registered sample size. Below this the experiment has no verdict.
GATE_MIN_WINDOWS = 30


def format_report(
    observations: list[WindowObservation],
    *,
    trigger_points: float,
    book_pairs: int,
    fee: float = DEFAULT_FEE,
    near_misses: dict[float, int] | None = None,
) -> str:
    out: list[str] = []
    add = out.append

    add("EXPERIMENT 4 — news-window detector")
    add("=" * 78)
    add(f"trigger: book consensus moves >= {trigger_points} pts between "
        f"consecutive polls (<= {MAX_TRIGGER_GAP_MINUTES:.0f} min apart)")
    add(f"consecutive book-poll pairs examined : {book_pairs}")
    add(f"windows triggered                    : {len(observations)}")
    add("")

    if near_misses:
        add("How close the data comes to triggering at all")
        add("-" * 78)
        for threshold in sorted(near_misses, reverse=True):
            add(f"  moves >= {threshold:.1f} pts : {near_misses[threshold]}")
        add("")

    if not observations:
        add("VERDICT: NO DATA — the experiment has not run.")
        add("")
        add("  Not a null result. Zero triggers means the hypothesis was never")
        add("  tested, which is different from being tested and failing. The")
        add("  detector is built, tested and will accrue; what it needs is time")
        add("  and a faster book cadence, not a different analysis.")
        return "\n".join(out)

    resolved = [o for o in observations if o.first_after is not None]
    add(f"windows with a PM reading afterwards : {len(resolved)}")
    add("")

    if resolved:
        add(f"{'game':<14}{'move':>8}{'lag min':>9}{'stale pts':>11}{'net edge':>10}")
        add("-" * 78)
        for o in sorted(resolved, key=lambda x: x.move.to_at):
            edge = o.edge_probability(fee)
            add(
                f"{o.move.espn_game_id:<14}{o.move.delta:>+8.1f}"
                f"{o.lag_minutes or 0:>9.0f}{o.staleness_points or 0:>+11.2f}"
                f"{(edge if edge is not None else 0):>+10.3f}"
            )
        add("")

        tradable = [o for o in resolved if o.is_tradable(fee)]
        add(f"windows with a net edge >= {MIN_TRADABLE_EDGE_PROB:.0%} : "
            f"{len(tradable)}/{len(resolved)}")
        add("")

    add("VERDICT")
    add("-" * 78)
    if len(resolved) < GATE_MIN_WINDOWS:
        add(f"  INCONCLUSIVE — {len(resolved)} windows against a pre-registered "
            f"minimum of {GATE_MIN_WINDOWS}.")
        add("  Reporting an edge from this many would be reading noise.")
    else:
        tradable = [o for o in resolved if o.is_tradable(fee)]
        rate = len(tradable) / len(resolved)
        if rate >= 0.5:
            add(f"  PASS — {rate:.0%} of windows left a net edge after fees.")
        else:
            add(f"  FAIL — only {rate:.0%} of windows left a net edge after fees; "
                "the venue reprices faster than we can act at this cadence.")

    add("")
    add("  Cadence caveat: the book leg is sampled every ~20 min and the PM leg")
    add("  every 15 min near tip-off but hourly when idle. A lag measured in")
    add("  minutes cannot be resolved by samples that far apart, so a null here")
    add("  cannot distinguish a fast venue from a slow camera.")
    return "\n".join(out)


def run(
    session: Session,
    *,
    trigger_points: float = DEFAULT_TRIGGER_POINTS,
    since: dt.datetime | None = None,
    fee: float = DEFAULT_FEE,
) -> str:
    book = load_book_series(session, since=since)
    pm = load_pm_readings(session, since=since)

    pairs = sum(max(0, len(v) - 1) for v in book.values())
    moves = detect_moves(book, trigger_points=trigger_points)
    observations = attach_pm_readings(moves, pm)

    # How near the data comes to firing at all — the difference between "tested
    # and found nothing" and "never had an event to test".
    near_misses = {
        t: len(detect_moves(book, trigger_points=t))
        for t in (0.5, 1.0, 1.5, 2.0, 3.0)
    }

    return format_report(
        observations, trigger_points=trigger_points,
        book_pairs=pairs, fee=fee, near_misses=near_misses,
    )


def main() -> int:
    from core.storage import get_engine, get_sessionmaker

    parser = argparse.ArgumentParser(prog="meridian-window-detector")
    parser.add_argument("--trigger", type=float, default=DEFAULT_TRIGGER_POINTS)
    parser.add_argument("--days", type=int, default=None,
                        help="only look this many days back")
    parser.add_argument("--fee", type=float, default=DEFAULT_FEE)
    args = parser.parse_args()

    since = (
        dt.datetime.now(UTC) - dt.timedelta(days=args.days) if args.days else None
    )
    Session = get_sessionmaker(get_engine())
    with Session() as session:
        print(run(session, trigger_points=args.trigger, since=since, fee=args.fee))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
