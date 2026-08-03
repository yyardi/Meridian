"""Experiment 2 — market shrinkage on spreads and moneylines.

What the ledger asked for, and why it was the wrong fix
------------------------------------------------------
The v4 ledger prescribed isotonic/Platt recalibration for the moneyline's
"~10 point overconfidence". Measured first, the premise does not hold: across
all games the model's win probability is already well calibrated.

    p_model   0.45   0.55   0.65   0.75   0.85
    realised  0.436  0.553  0.663  0.772  0.847

There is nothing wrong with the probability scale, so a monotone recalibration
of it has nothing to fix. The failure is in **selection**, and it shows up as a
uniform collapse — every bucket underperforms once you condition on having bet:

    p_model   0.25   0.35   0.45   0.55   0.65
    realised  0.14   0.25   0.32   0.30   0.57

Measured on 2024-2026 (n=677), the incremental slope of (actual − market) on
(model − market) is **+0.18, CI [−0.03, +0.38]**, and the market's own margin
MAE (9.65) beats the model's (10.19). The model is dominated by the market.
Betting the raw gap treats a 0.18-weight signal as weight 1.0 — overbetting it
roughly fivefold — which is exactly how a calibrated model hits 33%.

So the real Experiment 2 is the correction totals already uses: shrink the
model-vs-market gap by the walk-forward incremental slope before selecting.

Why the two markets can disagree
--------------------------------
After shrinkage both markets select the same extreme-disagreement tail, which
is mostly large underdogs. A big underdog *covers* far more often than it
*wins outright*, so a rule that helps the spread can still lose on the
moneyline. They are different bets on the same opinion.

    python -m core.backtest.exp_margin_shrinkage
"""

from __future__ import annotations

import argparse
import logging
import math
import sys

import structlog

from core.backtest.fills import FillModel
from core.backtest.margin import MarginBacktestConfig, MarginResult, run_margin_backtest
from core.storage import get_engine, get_sessionmaker

Z95 = 1.96

#: A -110 two-way market needs this to break even.
BREAKEVEN = 0.5238


def wilson(wins: int, n: int) -> tuple[float, float, float] | None:
    """Wilson score interval for a hit rate.

    Wilson rather than the normal approximation: at n=55 with p near 0.5 the
    normal interval is already visibly wrong at the tails, and the whole point
    of this report is to stop a small sample reading as a result.
    """
    if n == 0:
        return None
    p = wins / n
    z2 = Z95 * Z95
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = Z95 * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return p, centre - half, centre + half


def _line(label: str, wins: int, n: int, pnl: float, staked: float) -> str:
    ci = wilson(wins, n)
    if ci is None:
        return f"  {label:<28s} no bets"
    p, lo, hi = ci
    roi = pnl / staked if staked else float("nan")
    beats = "yes" if lo > BREAKEVEN else "no"
    return (
        f"  {label:<28s} n={n:<4d} hit {p:.3f} [{lo:.3f}, {hi:.3f}]  "
        f"ROI {roi:+.2%}   CI clears breakeven: {beats}"
    )


def run(*, start: int = 2024, end: int = 2026, fill: FillModel = FillModel.REALISTIC) -> str:
    Session = get_sessionmaker(get_engine())
    out: list[str] = []
    add = out.append

    with Session() as session:
        arms: dict[str, MarginResult] = {}
        for name, shrink in (("raw", False), ("shrunk", True)):
            arms[name] = run_margin_backtest(
                session=session,
                config=MarginBacktestConfig(
                    start_season=start, end_season=end,
                    fill_model=fill, shrink_to_market=shrink,
                ),
            )

    add("EXPERIMENT 2 — market shrinkage on spread and moneyline")
    add(f"seasons {start}-{end} · {fill.value} fills · breakeven {BREAKEVEN:.3f}")
    add(f"walk-forward incremental slope (final): {arms['shrunk'].final_slope:.3f}")
    add("")
    add("The slope IS the finding: the model retains ~18% of its stated")
    add("disagreement with the market. The other ~82% is its own error.")
    add("")

    add("SPREAD")
    add("-" * 78)
    for name in ("raw", "shrunk"):
        r = arms[name]
        add(_line(name, r.spread_wins, r.spread_resolved, r.spread_pnl, r.spread_staked))
    add("")

    add("MONEYLINE")
    add("-" * 78)
    for name in ("raw", "shrunk"):
        r = arms[name]
        add(_line(name, r.winner_wins, r.winner_resolved, r.winner_pnl, r.winner_staked))
    add("")

    # --- verdicts, stated separately because the markets disagree --- #
    s = arms["shrunk"]
    spread_ci = wilson(s.spread_wins, s.spread_resolved)
    ml_ci = wilson(s.winner_wins, s.winner_resolved)

    add("VERDICT")
    add("-" * 78)
    if spread_ci and spread_ci[1] > BREAKEVEN:
        add("  SPREAD: shrinkage passes — hit-rate CI clears breakeven.")
    elif spread_ci and spread_ci[0] > BREAKEVEN:
        add(
            f"  SPREAD: shrinkage IMPROVES the point estimate to {spread_ci[0]:.3f} "
            f"(above the {BREAKEVEN:.3f} breakeven) and turns ROI positive, but the "
            f"interval [{spread_ci[1]:.3f}, {spread_ci[2]:.3f}] still includes it. "
            "Promising, NOT proven — the shrinkage cuts the bet count hard, and the "
            "sample is too small to call. Adopt the correction, do not size on it."
        )
    else:
        add("  SPREAD: shrinkage does not lift the hit rate above breakeven.")

    if ml_ci and ml_ci[2] < BREAKEVEN:
        add(
            f"  MONEYLINE: dead. Even shrunk, the hit rate is {ml_ci[0]:.3f} with the "
            f"whole interval [{ml_ci[1]:.3f}, {ml_ci[2]:.3f}] below breakeven. Shrinkage "
            "makes it worse, not better, because what survives the filter is the "
            "extreme-disagreement tail: large underdogs, which cover far more often "
            "than they win outright. Stop pricing this market for money."
        )
    elif ml_ci:
        add(f"  MONEYLINE: hit {ml_ci[0]:.3f}, interval [{ml_ci[1]:.3f}, {ml_ci[2]:.3f}].")

    add("")
    add("  Neither result is a CLV result — ESPN keeps no open/close pair for")
    add("  spreads or moneylines, so these are outcome-based and converge slowly.")
    return "\n".join(out)


def main() -> int:
    p = argparse.ArgumentParser(prog="exp-margin-shrinkage")
    p.add_argument("--start", type=int, default=2024)
    p.add_argument("--end", type=int, default=2026)
    p.add_argument("--fill", type=str, default="realistic",
                   choices=[m.value for m in FillModel])
    args = p.parse_args()

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.WARNING)
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))
    print(run(start=args.start, end=args.end, fill=FillModel(args.fill)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
