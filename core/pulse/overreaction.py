"""Experiment 6 — do prices overreact to scoring runs and then revert?

The one question that decides whether PULSE exists
--------------------------------------------------
In-game directional trading needs an edge, and there are only two candidates:
a better live model, or a behavioural one. The behavioural one is cheaper to
test and, if it fails, the modelling one almost certainly fails too — because
a market that does not overshoot is a market pricing runs correctly, and
out-pricing it live is a much harder bar than out-pricing a stale line.

So: a team goes on a run. The price lurches. **Does it come back?** And does it
come back by more than it costs to go there and return?

Do not build a live model before this answers yes. From the handoff brief and
already measured: Q1 combined total correlates +0.55 with the final total
(n=787), and each extra Q1 point is worth **1.32** on the final, not 4.0. Hot
starts regress ~3x. If the market prices a run closer to 4.0 than to 1.32,
there is an overreaction to trade. This module measures whether it does.


PRE-REGISTERED GATE — fixed before any number was computed
----------------------------------------------------------
Written 2026-08-02, prior to running this against any data.

    PASS  requires ALL of:
      (1) mean reversion at the +5 min mark > ROUND_TRIP_COST (6c)
      (2) the 95% confidence interval on mean reversion, clustered by game,
          lies entirely above ROUND_TRIP_COST
      (3) n >= 30 runs
      (4) those runs spread across >= 10 distinct games

    FAIL  if (3) and (4) are met but (1) or (2) is not.

    NO DATA  if (3) or (4) is not met. Zero triggers is NOT a null result.

Note what condition (2) does: the interval must clear the **cost**, not zero.
A statistically real 2c reversion against a 6c round trip is a confirmed
phenomenon and a losing trade, and this project has been burned before by
edges that were real and smaller than their costs.

The +5 min mark is the pre-registered primary. +2 and +10 are reported as
secondaries and carry no gate — nominating the best of three after the fact is
how a 5% test becomes a 14% one.


How a run is defined
--------------------
Two independent triggers, both from the brief, either of which opens a window:

* **Score run.** One team scores >= `RUN_POINTS` unanswered points, read from
  the `event_score` string recorded on each snapshot.
* **Price run.** The mid moves >= `PRICE_MOVE` (10%) in under `RUN_MINUTES`
  (2 min) on a quotable rung.

The price trigger exists because the score trigger is only as good as the
score feed: `event_score` updates on the venue's own cadence, and a run that
the venue smoothed over is invisible to it. The price trigger sees the market's
reaction directly, which is the thing we would be trading anyway — the same
reasoning `core/window_detector.py` uses for observing news through the book
rather than through a headline.

**Reversion** is measured in the direction that would have been profitable:

    reversion(H) = -sign(run move) * (mid(t_end + H) - mid(t_end))

so a positive number always means "it came back", whichever way it went.


Honesty constraints
-------------------
**Non-overlapping windows only.** Runs inside another run's horizon are
dropped. Overlapping windows share price path, and counting them separately
inflates n against a gate that is stated in independent observations.

**Reversion must beat the round trip, not zero.** See the gate.

**Cadence bounds what is observable.** A run lasts a couple of minutes. At the
~30-60s sampling that existed before 2026-08-02, the overshoot and the
reversion can land in the same frame and the question is unanswerable by
construction. The report states the regime the data came from.

    python -m core.pulse.overreaction
    python -m core.pulse.overreaction --run-points 8 --days 7
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.quote.adverse_selection import Cadence, cadence, clustered_mean
from core.storage import MarketSnapshot

UTC = dt.timezone.utc

# --------------------------------------------------------------------- #
# Pre-registered constants
# --------------------------------------------------------------------- #

#: Unanswered points that constitute a run.
DEFAULT_RUN_POINTS = 8

#: A mid move this large inside RUN_MINUTES is a price run.
DEFAULT_PRICE_MOVE = 0.10

#: The window a run has to happen in.
RUN_MINUTES = 2.0

#: Cost of going in and coming back out at the money: ~3c spread each way.
#: This is the bar, not zero.
ROUND_TRIP_COST = 0.06

#: Horizons measured after the run ends. The gate is on the primary only.
PRIMARY_HORIZON_MINUTES = 5.0
HORIZON_MINUTES = (2.0, 5.0, 10.0)

#: Pair a run end with the observation nearest `t+H` inside this band.
HORIZON_TOLERANCE = (0.5, 2.0)

#: Only rungs anyone would trade. Same band as the adverse-selection study, and
#: for the same reason: a 22-26c-spread rung's "move" is quote noise.
MIN_MID, MAX_MID = 0.20, 0.80
MAX_SPREAD = 0.15

# -- the gate --------------------------------------------------------- #
GATE_MIN_RUNS = 30
GATE_MIN_GAMES = 10


@dataclass(frozen=True)
class Tick:
    """One market observation."""

    game_id: str
    market_slug: str
    captured_at: dt.datetime
    mid: float
    spread: float
    score: str | None
    period: str | None

    @property
    def is_quotable(self) -> bool:
        return self.spread <= MAX_SPREAD and MIN_MID <= self.mid <= MAX_MID


@dataclass(frozen=True)
class Run:
    """A detected run and the price path after it."""

    game_id: str
    market_slug: str
    trigger: str            # 'score' | 'price'
    started_at: dt.datetime
    ended_at: dt.datetime
    mid_start: float
    mid_end: float
    #: mid at each horizon, keyed by minutes. Missing if unobserved.
    after: dict[float, float]

    @property
    def move(self) -> float:
        return self.mid_end - self.mid_start

    @property
    def direction(self) -> float:
        return 1.0 if self.move > 0 else -1.0

    def reversion(self, horizon: float) -> float | None:
        """How far the price came back, signed so positive = reverted."""
        after = self.after.get(horizon)
        if after is None:
            return None
        return -self.direction * (after - self.mid_end)


# --------------------------------------------------------------------- #
# Score parsing
# --------------------------------------------------------------------- #

_SCORE = re.compile(r"^\s*(\d{1,3})\s*-\s*(\d{1,3})\s*$")


def parse_score(value: str | None) -> tuple[int, int] | None:
    """`"46-34"` -> `(46, 34)`. Anything else -> None."""
    if not value:
        return None
    m = _SCORE.match(value)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def unanswered_run(
    before: tuple[int, int], after: tuple[int, int]
) -> tuple[int, int] | None:
    """Points scored by each side between two score readings.

    Returns `(margin_swing, points)` where `points` is the larger side's
    scoring and `margin_swing` is signed toward the home side. A run requires
    the other side to have scored nothing — that is what "unanswered" means,
    and relaxing it to "outscored" would count ordinary trading of baskets.
    """
    dh, da = after[0] - before[0], after[1] - before[1]
    if dh < 0 or da < 0:
        return None  # score went backwards: a correction, not a run
    if dh > 0 and da > 0:
        return None  # both scored: not unanswered
    if dh == 0 and da == 0:
        return None
    return (dh - da, max(dh, da))


# --------------------------------------------------------------------- #
# Detection — pure, so it is testable without a database
# --------------------------------------------------------------------- #


def detect_runs(
    series: dict[str, list[Tick]],
    *,
    run_points: int = DEFAULT_RUN_POINTS,
    price_move: float = DEFAULT_PRICE_MOVE,
    run_minutes: float = RUN_MINUTES,
    horizons: tuple[float, ...] = HORIZON_MINUTES,
) -> list[Run]:
    """Per-market tick series -> non-overlapping runs with their price paths."""
    runs: list[Run] = []
    for slug, ticks in series.items():
        ordered = sorted(ticks, key=lambda t: t.captured_at)
        runs.extend(
            _detect_one_market(
                ordered,
                run_points=run_points,
                price_move=price_move,
                run_minutes=run_minutes,
                horizons=horizons,
            )
        )
    return runs


def _detect_one_market(
    ticks: list[Tick],
    *,
    run_points: int,
    price_move: float,
    run_minutes: float,
    horizons: tuple[float, ...],
) -> list[Run]:
    out: list[Run] = []
    window = dt.timedelta(minutes=run_minutes)
    #: End of the last accepted run's longest horizon. Runs starting before
    #: this are dropped as overlapping.
    blocked_until: dt.datetime | None = None

    for i, start in enumerate(ticks):
        if blocked_until is not None and start.captured_at < blocked_until:
            continue
        if not start.is_quotable:
            continue

        trigger: str | None = None
        end: Tick | None = None

        for j in range(i + 1, len(ticks)):
            candidate = ticks[j]
            if candidate.captured_at - start.captured_at > window:
                break
            if not candidate.is_quotable:
                continue

            # Score trigger.
            a, b = parse_score(start.score), parse_score(candidate.score)
            if a and b:
                run = unanswered_run(a, b)
                if run and run[1] >= run_points:
                    trigger, end = "score", candidate
                    break

            # Price trigger.
            if abs(candidate.mid - start.mid) >= price_move:
                trigger, end = "price", candidate
                break

        if trigger is None or end is None:
            continue

        after: dict[float, float] = {}
        for h in horizons:
            mark = _nearest(ticks, end.captured_at, h)
            if mark is not None:
                after[h] = mark.mid

        out.append(
            Run(
                game_id=start.game_id,
                market_slug=start.market_slug,
                trigger=trigger,
                started_at=start.captured_at,
                ended_at=end.captured_at,
                mid_start=start.mid,
                mid_end=end.mid,
                after=after,
            )
        )
        blocked_until = end.captured_at + dt.timedelta(minutes=max(horizons))
    return out


def _nearest(ticks: list[Tick], origin: dt.datetime, horizon_minutes: float) -> Tick | None:
    """The observation nearest `origin + horizon`, inside the tolerance band."""
    lo, hi = HORIZON_TOLERANCE
    target = origin + dt.timedelta(minutes=horizon_minutes)
    best: Tick | None = None
    best_gap = float("inf")
    for tick in ticks:
        elapsed = (tick.captured_at - origin).total_seconds() / 60.0
        if elapsed <= 0:
            continue
        if elapsed < horizon_minutes * lo or elapsed > horizon_minutes * hi:
            continue
        gap = abs((tick.captured_at - target).total_seconds())
        if gap < best_gap:
            best, best_gap = tick, gap
    return best


# --------------------------------------------------------------------- #
# Database
# --------------------------------------------------------------------- #


def load_ticks(
    session: Session,
    *,
    as_of: dt.datetime | None,
    since: dt.datetime | None = None,
) -> dict[str, list[Tick]]:
    """Live two-sided quotes per market, with the score attached.

    `as_of` is keyword-only with no default, per the project's point-in-time
    rule.
    """
    stmt = select(
        MarketSnapshot.game_id,
        MarketSnapshot.market_slug,
        MarketSnapshot.captured_at,
        MarketSnapshot.best_bid,
        MarketSnapshot.best_ask,
        MarketSnapshot.event_score,
        MarketSnapshot.event_period,
    ).where(
        MarketSnapshot.is_live.is_(True),
        MarketSnapshot.best_bid.is_not(None),
        MarketSnapshot.best_ask.is_not(None),
        MarketSnapshot.game_id.is_not(None),
    )
    if as_of is not None:
        stmt = stmt.where(MarketSnapshot.captured_at < as_of)
    if since is not None:
        stmt = stmt.where(MarketSnapshot.captured_at >= since)

    out: dict[str, list[Tick]] = defaultdict(list)
    for game_id, slug, at, bid, ask, score, period in session.execute(stmt).all():
        b, a = float(bid), float(ask)
        if a <= b:
            continue
        out[slug].append(
            Tick(
                game_id=str(game_id),
                market_slug=slug,
                captured_at=at,
                mid=(a + b) / 2.0,
                spread=a - b,
                score=score,
                period=period,
            )
        )
    return dict(out)


def score_change_count(series: dict[str, list[Tick]]) -> int:
    """How often the recorded score changed between consecutive snapshots.

    Reported because zero triggers has two very different causes — no runs
    happened, or the score feed never moved — and they demand different
    responses.
    """
    changes = 0
    for ticks in series.values():
        ordered = sorted(ticks, key=lambda t: t.captured_at)
        for a, b in zip(ordered, ordered[1:]):
            sa, sb = parse_score(a.score), parse_score(b.score)
            if sa and sb and sa != sb:
                changes += 1
    return changes


# --------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------- #


def format_report(
    runs: list[Run],
    *,
    run_points: int,
    price_move: float,
    ticks_examined: int,
    score_changes: int,
    sampling: Cadence | None = None,
    near_misses: dict[int, int] | None = None,
) -> str:
    out: list[str] = []
    add = out.append

    add("EXPERIMENT 6 — run overreaction and reversion")
    add("=" * 78)
    add(f"score trigger                  : >= {run_points} unanswered pts in "
        f"< {RUN_MINUTES:.0f} min")
    add(f"price trigger                  : >= {price_move:.0%} mid move in "
        f"< {RUN_MINUTES:.0f} min")
    add(f"live ticks examined            : {ticks_examined:,}")
    add(f"observed score changes         : {score_changes:,}")
    add(f"runs detected (non-overlapping): {len(runs):,}")
    if sampling is not None:
        add(f"snapshot cadence               : median {sampling.median:.0f}s "
            f"(p10 {sampling.p10:.0f}s, p90 {sampling.p90:.0f}s), "
            f"{sampling.under_2min:.0%} under 2 min")
    add("")

    add("PRE-REGISTERED GATE (fixed 2026-08-02, before computing)")
    add("-" * 78)
    add(f"  PASS requires mean reversion at +{PRIMARY_HORIZON_MINUTES:.0f} min "
        f"> {ROUND_TRIP_COST:.2f} (the round-trip cost),")
    add("  with a 95% CI clustered by game lying entirely above it, at")
    add(f"  n >= {GATE_MIN_RUNS} runs across >= {GATE_MIN_GAMES} games.")
    add("")

    if near_misses:
        add("How close the data comes to triggering at all")
        add("-" * 78)
        for threshold in sorted(near_misses, reverse=True):
            add(f"  runs at >= {threshold:>2} unanswered pts : {near_misses[threshold]}")
        add("")

    if not runs:
        add("VERDICT: NO DATA — the experiment has not run.")
        add("")
        add("  Not a null result. Zero triggers means the hypothesis was never")
        add("  tested, which is different from being tested and failing.")
        if score_changes == 0:
            add("")
            add("  Note: the recorded score never changed in this sample either,")
            add("  so the score trigger could not have fired regardless of what")
            add("  happened on the floor. That is a data-coverage problem, not")
            add("  evidence about how prices behave.")
        return "\n".join(out)

    games = {r.game_id for r in runs}
    by_trigger: dict[str, int] = defaultdict(int)
    for r in runs:
        by_trigger[r.trigger] += 1

    add("What the runs looked like")
    add("-" * 78)
    add("  by trigger                   : " + ", ".join(
        f"{k}={v}" for k, v in sorted(by_trigger.items())))
    moves = [abs(r.move) for r in runs]
    add(f"  mean |price move| in the run : {sum(moves) / len(moves):.4f}")
    add(f"  distinct games               : {len(games)}")
    add("")

    add("Reversion after the run ends (positive = came back)")
    add("-" * 78)
    add(f"  {'horizon':<10}{'n':>6}{'mean':>10}{'95% CI (clustered)':>28}"
        f"{'vs cost':>10}")
    primary: tuple[float, object] | None = None
    for h in HORIZON_MINUTES:
        by_game: dict[str, list[float]] = defaultdict(list)
        for r in runs:
            rev = r.reversion(h)
            if rev is not None:
                by_game[r.game_id].append(rev)
        values = [x for v in by_game.values() for x in v]
        if not values:
            add(f"  +{h:<9.0f}{'0':>6}{'—':>10}{'—':>28}{'—':>10}")
            continue
        mean = sum(values) / len(values)
        cl = clustered_mean(by_game)
        ci = f"[{cl.lo:+.4f}, {cl.hi:+.4f}]" if cl else "n/a (<2 games)"
        beats = "yes" if mean > ROUND_TRIP_COST else "no"
        marker = "  <- gate" if h == PRIMARY_HORIZON_MINUTES else ""
        add(f"  +{h:<9.0f}{len(values):>6}{mean:>+10.4f}{ci:>28}{beats:>10}{marker}")
        if h == PRIMARY_HORIZON_MINUTES:
            primary = (mean, cl)
    add("")
    add(f"  round-trip cost to beat      : {ROUND_TRIP_COST:.4f}")
    add("")

    add("VERDICT")
    add("-" * 78)
    if len(runs) < GATE_MIN_RUNS or len(games) < GATE_MIN_GAMES:
        add(f"  NO DATA — {len(runs)} runs across {len(games)} games, against a")
        add(f"  pre-registered minimum of {GATE_MIN_RUNS} runs across "
            f"{GATE_MIN_GAMES} games.")
        add("")
        missing = []
        if len(runs) < GATE_MIN_RUNS:
            missing.append(f"{GATE_MIN_RUNS - len(runs)} more runs")
        if len(games) < GATE_MIN_GAMES:
            missing.append(f"{GATE_MIN_GAMES - len(games)} more games")
        add(f"  Needs {' and '.join(missing)}. This is NOT a null result: the")
        add("  detector is built and will accrue. What it needs is games.")
    elif primary is None or primary[1] is None:
        add("  NO DATA — no reversion observable at the primary horizon.")
    else:
        mean, cl = primary
        if mean > ROUND_TRIP_COST and cl.lo > ROUND_TRIP_COST:
            add(f"  PASS — reversion {mean:+.4f} at +{PRIMARY_HORIZON_MINUTES:.0f} "
                f"min, 95% CI [{cl.lo:+.4f}, {cl.hi:+.4f}]")
            add(f"  lies entirely above the {ROUND_TRIP_COST:.2f} round trip.")
        elif mean > 0 and cl.lo > 0:
            add(f"  FAIL — reversion {mean:+.4f} is real (CI [{cl.lo:+.4f}, "
                f"{cl.hi:+.4f}] excludes zero)")
            add(f"  but does not clear the {ROUND_TRIP_COST:.2f} round-trip cost. "
                "A confirmed")
            add("  phenomenon and a losing trade. PULSE stays unbuilt.")
        else:
            add(f"  FAIL — reversion {mean:+.4f} at +{PRIMARY_HORIZON_MINUTES:.0f} "
                f"min, 95% CI [{cl.lo:+.4f}, {cl.hi:+.4f}].")
            add("  Prices do not measurably overshoot runs. PULSE stays unbuilt,")
            add("  and no live model rescues it.")

    if sampling is not None and not sampling.is_fast:
        add("")
        add(f"  Cadence caveat: at a {sampling.median:.0f}s median gap, a "
            "2-minute run and")
        add("  its reversion can land in the same frame — the question is close")
        add("  to unanswerable by construction. The 1s recorder shipped")
        add("  2026-08-02; re-run once a slate has accrued under it.")
    return "\n".join(out)


def run(
    session: Session,
    *,
    as_of: dt.datetime | None = None,
    run_points: int = DEFAULT_RUN_POINTS,
    price_move: float = DEFAULT_PRICE_MOVE,
    since: dt.datetime | None = None,
) -> str:
    series = load_ticks(session, as_of=as_of, since=since)
    ticks = sum(len(v) for v in series.values())
    runs = detect_runs(series, run_points=run_points, price_move=price_move)

    # How near the data comes to firing at all — the difference between "tested
    # and found nothing" and "never had an event to test". Score trigger only,
    # so the price trigger does not mask a dead score feed.
    near_misses = {
        t: len(detect_runs(series, run_points=t, price_move=1.01))
        for t in (4, 6, 8, 10, 12)
    }

    return format_report(
        runs,
        run_points=run_points,
        price_move=price_move,
        ticks_examined=ticks,
        score_changes=score_change_count(series),
        sampling=cadence(series),
        near_misses=near_misses,
    )


def main() -> int:
    from core.storage import get_engine, get_sessionmaker

    parser = argparse.ArgumentParser(prog="meridian-overreaction")
    parser.add_argument("--run-points", type=int, default=DEFAULT_RUN_POINTS)
    parser.add_argument("--price-move", type=float, default=DEFAULT_PRICE_MOVE)
    parser.add_argument("--days", type=int, default=None)
    args = parser.parse_args()

    since = dt.datetime.now(UTC) - dt.timedelta(days=args.days) if args.days else None
    Session = get_sessionmaker(get_engine())
    with Session() as session:
        print(
            run(
                session,
                run_points=args.run_points,
                price_move=args.price_move,
                since=since,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
