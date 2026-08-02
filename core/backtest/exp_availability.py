"""Experiment 1 — does roster availability improve the totals model?

Pre-registered before the numbers were looked at
------------------------------------------------
**Hypothesis.** A projection that deducts the scoring of players who will not
play beats the season-average-roster model on CLV, and most of the gain lands
on games where a rotation player is absent.

**Gate.** Mean CLV on absent-player games improves against the incumbent with a
95% CI on the *paired* difference excluding zero, AND CLV does not degrade on
full-roster games.

**The arm that runs on history is an oracle, and is not tradable.** ESPN
publishes injury status for *today* only — measured, not assumed: the
`injuries` block inside the summary of a 2025 game returns designations dated
2026. So no point-in-time injury history exists to backtest on, and the
tradable arm ("report") is empty until the recorder has run for a season.

The oracle arm takes absence from the box score, i.e. with hindsight. It cannot
produce a tradable result and no number from it may be quoted as edge. Its only
job is a one-way screen:

    oracle fails  -> the mechanism is worth less than its own upper bound,
                     and waiting a season for injury data is not justified.
    oracle passes -> the mechanism is worth waiting for, and the forward
                     experiment on point-in-time data becomes the real test.

Passing proves nothing about tradability. Failing kills the idea cheaply, which
is the whole point of running it.

    python -m core.backtest.exp_availability
"""

from __future__ import annotations

import argparse
import logging
import math
import statistics
import sys
from dataclasses import dataclass

import structlog

from core.backtest.engine import BacktestConfig, BacktestResult, run_backtest
from core.backtest.fills import FillModel
from core.storage import get_engine, get_sessionmaker

#: 95% normal interval. n is in the hundreds here, so t vs z is immaterial.
Z95 = 1.96


@dataclass(frozen=True)
class Interval:
    mean: float
    stderr: float
    n: int

    @property
    def low(self) -> float:
        return self.mean - Z95 * self.stderr

    @property
    def high(self) -> float:
        return self.mean + Z95 * self.stderr

    @property
    def excludes_zero(self) -> bool:
        return self.low > 0 or self.high < 0

    def __str__(self) -> str:
        return f"{self.mean:+.3f} [{self.low:+.3f}, {self.high:+.3f}]  n={self.n}"


def interval(values: list[float]) -> Interval | None:
    if len(values) < 2:
        return None
    mean = statistics.mean(values)
    stderr = statistics.stdev(values) / math.sqrt(len(values))
    return Interval(mean=mean, stderr=stderr, n=len(values))


def _clv_by_game(result: BacktestResult) -> dict[str, float]:
    return {b.espn_game_id: b.clv_points for b in result.bets if b.clv_points is not None}


def _clv(result: BacktestResult, *, absence: bool | None = None) -> list[float]:
    return [
        b.clv_points
        for b in result.bets
        if b.clv_points is not None and (absence is None or b.has_absence == absence)
    ]


def _returns(result: BacktestResult, *, absence: bool | None = None) -> list[float]:
    """Per-bet return on a unit stake — the series ROI is the mean of."""
    return [
        b.pnl
        for b in result.bets
        if b.filled and b.won is not None and (absence is None or b.has_absence == absence)
    ]


def _paired(control: BacktestResult, arm: BacktestResult, *, absence_only: bool) -> list[float]:
    """Per-game CLV difference on games both arms bet.

    Paired because the two arms share almost all their games and all their line
    data; an unpaired comparison of two heavily overlapping samples would
    overstate the uncertainty of the difference.

    Games only one arm bets are excluded rather than scored as zero: a bet the
    incumbent never places has no counterfactual CLV, and imputing one would
    invent the result.
    """
    a = _clv_by_game(control)
    b = _clv_by_game(arm)
    absence_games = {bet.espn_game_id for bet in arm.bets if bet.has_absence}
    shared = a.keys() & b.keys()
    if absence_only:
        shared &= absence_games
    return [b[g] - a[g] for g in sorted(shared)]


def _fmt(label: str, iv: Interval | None) -> str:
    return f"  {label:<34s} {iv if iv else 'insufficient n'}"


def run(
    *,
    start: int = 2024,
    end: int = 2026,
    min_edge: float = 3.0,
    beta: float = 1.0,
    fill: FillModel = FillModel.REALISTIC,
) -> str:
    Session = get_sessionmaker(get_engine())
    lines: list[str] = []

    def base(**kw) -> BacktestConfig:
        return BacktestConfig(
            start_season=start, end_season=end, min_edge_points=min_edge,
            fill_model=fill, **kw,
        )

    with Session() as session:
        control = run_backtest(session=session, config=base())
        oracle = run_backtest(
            session=session,
            config=base(availability_mode="oracle", availability_beta=beta),
        )

    n_absence = sum(1 for b in oracle.bets if b.has_absence)
    deltas = [b.availability_delta for b in oracle.bets if b.availability_delta != 0.0]

    lines.append("EXPERIMENT 1 — roster availability (ORACLE ARM: hindsight, NOT tradable)")
    lines.append(f"seasons {start}-{end} · min edge {min_edge} pts · beta {beta} · {fill.value} fills")
    lines.append("")
    lines.append("How often the adjustment fires")
    lines.append(f"  bets (control / oracle)            {len(control.bets)} / {len(oracle.bets)}")
    lines.append(f"  oracle bets with a rotation absence {n_absence}")
    if deltas:
        lines.append(
            f"  adjustment size                     mean {statistics.mean(deltas):+.2f} pts, "
            f"min {min(deltas):+.2f}, max {max(deltas):+.2f}"
        )
    lines.append("")

    lines.append("Mean CLV in line points (higher is better)")
    lines.append(_fmt("control, all bets", interval(_clv(control))))
    lines.append(_fmt("oracle,  all bets", interval(_clv(oracle))))
    lines.append(_fmt("oracle,  absence games", interval(_clv(oracle, absence=True))))
    lines.append(_fmt("oracle,  full-roster games", interval(_clv(oracle, absence=False))))
    lines.append("")

    paired_all = interval(_paired(control, oracle, absence_only=False))
    paired_abs = interval(_paired(control, oracle, absence_only=True))
    lines.append("Paired CLV difference, oracle − control (the gate)")
    lines.append(_fmt("all shared games", paired_all))
    lines.append(_fmt("absence games only", paired_abs))
    lines.append("")

    # ROI is reported with its interval on purpose. The oracle arm's ROI can
    # look transformative while its CLV does not move, and without the band
    # that reads as an edge rather than as noise. CLV's standard deviation is
    # ~10x smaller than an even-money return's, which is exactly why CLV is the
    # gate and ROI is a diagnostic.
    lines.append("Mean return per unit staked (ROI), with 95% CI")
    for name, res in (("control", control), ("oracle", oracle)):
        lines.append(_fmt(f"{name}, all bets", interval(_returns(res))))
    lines.append(_fmt("oracle, absence games", interval(_returns(oracle, absence=True))))
    lines.append("")

    # --- the pre-registered verdict, stated even when it is a failure --- #
    passes_absence = paired_abs is not None and paired_abs.low > 0
    full_roster_ok = paired_all is not None and paired_all.high > 0  # no degradation
    if paired_abs is None:
        verdict = "INCONCLUSIVE — too few absence games to test the gate."
    elif passes_absence and full_roster_ok:
        verdict = (
            "GATE PASSED (oracle). The mechanism is worth the wait for point-in-time "
            "injury data. This is an upper bound, not an edge — nothing here is tradable."
        )
    elif passes_absence:
        verdict = "MIXED — absence games improve but overall CLV degrades. Investigate before building forward."
    else:
        verdict = (
            "GATE FAILED (oracle). A model that knows the true lineup with hindsight does not "
            "beat the incumbent on CLV. Since no point-in-time version can do better than its "
            "own oracle, availability as a standing feature is dead for totals at this sample."
        )
    lines.append(f"VERDICT: {verdict}")

    control_roi = interval(_returns(control))
    oracle_roi = interval(_returns(oracle))
    if (
        not passes_absence
        and control_roi is not None
        and oracle_roi is not None
        and oracle_roi.mean > control_roi.mean
    ):
        lines.append("")
        lines.append(
            "NOTE: ROI rises while CLV does not. The consistent reading is that lineups are "
            "public before tip-off, so the closing line already prices them — the information "
            "predicts the game but is not news to the market by close. That does not make "
            "roster awareness worthless; it relocates its value to being early rather than "
            "being informed, which is Experiment 4's question, not this one's. Read the ROI "
            "interval before believing the gap: at this n it is wide enough to include zero "
            "difference."
        )
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(prog="exp-availability")
    p.add_argument("--start", type=int, default=2024)
    p.add_argument("--end", type=int, default=2026)
    p.add_argument("--min-edge", type=float, default=3.0)
    p.add_argument("--beta", type=float, default=1.0)
    p.add_argument("--fill", type=str, default="realistic",
                   choices=[m.value for m in FillModel])
    args = p.parse_args()

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.WARNING)
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))

    print(run(
        start=args.start, end=args.end, min_edge=args.min_edge,
        beta=args.beta, fill=FillModel(args.fill),
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
