"""Experiment 3 — de-vigged CLV, and what ROI it actually implies.

The problem this fixes
----------------------
The champion's headline is "+1.75 points of CLV". That is a real edge signal,
but *points are not money*. A 1.75-point beat on a total with sigma 17 is worth
something quite different from 1.75 points on a total with sigma 21, and neither
number can be compared against a realised ROI. Until CLV is expressed in price
terms, "does the edge survive costs?" is unanswerable.

The conversion
--------------
Buchdahl's rule: beat the **no-vig** closing price by X% and expected ROI is
about X%. In price terms, for a bet struck at price `p_paid` whose true
probability the close puts at `p_close`,

    E[ROI] = p_close / p_paid − 1

`p_paid` is the vig-included price, because that is what determines the payout.
`p_close` must be de-vigged, because the book's margin is not part of anyone's
true probability — leaving it in would understate our edge on every bet, which
is the mirror of the error [odds_math](../feeds/odds_math.py) warns about.

Getting `p_close` from a closing *line* needs a distribution. The close says the
market's central estimate of the total is `close_line`, so our over at
`entry_line` has fair probability

    p_close = Φ((close_line − entry_line) / sigma)

with sigma the same walk-forward scoring-environment estimate the bet was priced
with. This is where the points-to-probability conversion actually happens, and
it is why `sigma` is stored on every bet.

What this is and is not
-----------------------
This is an *accounting* change, not a model change. It cannot improve the edge;
it can only state it in units that can be checked against the P&L. The gate is
agreement, not magnitude: if de-vigged CLV predicts an ROI the maker-only ledger
does not deliver, then either the fills are worse than modelled or the closing
line is not the ground truth we treat it as — and both of those are worth
knowing before real money.

    python -m core.backtest.exp_devigged_clv
"""

from __future__ import annotations

import argparse
import logging
import math
import statistics
import sys
from dataclasses import dataclass

import structlog
from scipy.stats import norm

from core.backtest.engine import BacktestConfig, BacktestResult, run_backtest
from core.backtest.fills import FillModel
from core.storage import get_engine, get_sessionmaker

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

    def __str__(self) -> str:
        return f"{self.mean:+.2%} [{self.low:+.2%}, {self.high:+.2%}]  n={self.n}"


def interval(values: list[float]) -> Interval | None:
    if len(values) < 2:
        return None
    return Interval(
        mean=statistics.mean(values),
        stderr=statistics.stdev(values) / math.sqrt(len(values)),
        n=len(values),
    )


def devig_two_sided(over: float, under: float) -> tuple[float, float] | None:
    """Proportional (equal-margin) de-vig of a two-way market.

    Both prices are scaled by the same factor so they sum to 1. The main
    alternative, Shin, additionally models insider money and shifts probability
    away from longshots; on a two-sided total at near-symmetric juice the two
    barely differ, and proportional has no free parameter to fit.
    """
    total = over + under
    if total <= 0 or over <= 0 or under <= 0:
        return None
    return over / total, under / total


def closing_probability(
    *, side: str, entry_line: float, closing_line: float, sigma: float
) -> float | None:
    """The close's own probability for the bet we actually struck.

    Our bet is at `entry_line`. The close's central estimate is `closing_line`.
    So the close prices our over at Φ((close − entry) / sigma).
    """
    if sigma <= 0:
        return None
    p_over = float(norm.cdf((closing_line - entry_line) / sigma))
    return p_over if side == "over" else 1.0 - p_over


def analyse(result: BacktestResult) -> tuple[list[float], list[float], list[float]]:
    """(expected_roi, realised_roi, clv_prob) over bets with a genuine close."""
    expected: list[float] = []
    realised: list[float] = []
    clv_prob: list[float] = []

    for b in result.bets:
        if b.closing_line is None or b.sigma <= 0 or not b.filled:
            continue
        devigged = devig_two_sided(b.over_price, b.under_price)
        if devigged is None:
            continue
        p_entry_novig = devigged[0] if b.side == "over" else devigged[1]

        p_close = closing_probability(
            side=b.side, entry_line=b.entry_line,
            closing_line=b.closing_line, sigma=b.sigma,
        )
        if p_close is None or b.entry_price <= 0:
            continue

        # Buchdahl: expected ROI = fair probability / price paid − 1.
        expected.append(p_close / b.entry_price - 1.0)
        clv_prob.append(p_close - p_entry_novig)
        if b.won is not None:
            realised.append(b.pnl)

    return expected, realised, clv_prob


def run(*, start: int = 2024, end: int = 2026, min_edge: float = 3.0) -> str:
    Session = get_sessionmaker(get_engine())
    out: list[str] = []
    add = out.append

    add("EXPERIMENT 3 — de-vigged CLV ledger and maker-only ROI")
    add(f"seasons {start}-{end} · min edge {min_edge} pts")
    add("")
    add(f"{'fill model':<14s} {'CLV (points)':>16s} {'CLV (no-vig prob)':>22s}"
        f" {'E[ROI] from CLV':>26s} {'realised ROI':>26s}")
    add("-" * 110)

    with Session() as session:
        for fill in (FillModel.OPTIMISTIC, FillModel.REALISTIC, FillModel.PESSIMISTIC):
            r = run_backtest(
                session=session,
                config=BacktestConfig(
                    start_season=start, end_season=end,
                    min_edge_points=min_edge, fill_model=fill,
                ),
            )
            expected, realised, clv_p = analyse(r)
            pts = [b.clv_points for b in r.bets if b.clv_points is not None]

            ev = interval(expected)
            rv = interval(realised)
            add(
                f"{fill.value:<14s} {statistics.mean(pts):>+15.3f}  "
                f"{statistics.mean(clv_p):>+21.4f} "
                f"{str(ev) if ev else 'n/a':>26s} {str(rv) if rv else 'n/a':>26s}"
            )

            if fill is FillModel.REALISTIC and ev and rv:
                gap = ev.mean - rv.mean
                agree = rv.low <= ev.mean <= rv.high
                add("")
                add("GATE (realistic fills)")
                add("-" * 110)
                add(f"  de-vigged CLV predicts   : {ev.mean:+.2%} per unit staked")
                add(f"  maker-only ledger paid   : {rv.mean:+.2%}  [{rv.low:+.2%}, {rv.high:+.2%}]")
                add(f"  gap                      : {gap:+.2%}")
                if agree:
                    add(
                        "  PASS — the predicted ROI sits inside the realised interval. CLV and "
                        "P&L are telling the same story, so CLV can be used as the fast proxy "
                        "for money it is meant to be."
                    )
                else:
                    add(
                        "  FAIL — the predicted ROI falls outside the realised interval. Either "
                        "fills are worse than modelled or the closing line is not the ground "
                        "truth we treat it as. Do not scale on CLV until this is resolved."
                    )
                add("")
                add("  Note the direction of the realised interval: at this n it is wide")
                add("  enough that agreement is weak evidence. It rules out a gross")
                add("  accounting error, not a small persistent one.")

    add("")
    add("Points are not money: a 1.75-point beat converts to the probability")
    add("figure above, and that is the number comparable against ROI.")
    return "\n".join(out)


def main() -> int:
    p = argparse.ArgumentParser(prog="exp-devigged-clv")
    p.add_argument("--start", type=int, default=2024)
    p.add_argument("--end", type=int, default=2026)
    p.add_argument("--min-edge", type=float, default=3.0)
    args = p.parse_args()

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.WARNING)
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))
    print(run(start=args.start, end=args.end, min_edge=args.min_edge))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
