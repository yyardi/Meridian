"""Backtest metrics.

CLV is the headline. At a $25-40 bankroll over a few dozen bets, win rate is
nearly pure noise — a 55% edge and a 45% loser produce overlapping observed
win rates. CLV is measured on *every* bet rather than only on outcomes, so it
converges far faster. See docs/math/clv.md.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field


@dataclass
class CalibrationBucket:
    lower: float
    upper: float
    n: int = 0
    n_hit: int = 0

    @property
    def predicted(self) -> float:
        return (self.lower + self.upper) / 2

    @property
    def realised(self) -> float | None:
        return self.n_hit / self.n if self.n else None


@dataclass
class BacktestMetrics:
    n_bets: int = 0
    n_filled: int = 0
    n_wins: int = 0
    n_resolved: int = 0

    total_pnl: float = 0.0
    total_staked: float = 0.0
    total_fees: float = 0.0

    # CLV in line points (the natural unit for totals) and how often we beat it.
    clv_points: list[float] = field(default_factory=list)
    n_with_closing_line: int = 0

    equity_curve: list[float] = field(default_factory=list)
    returns: list[float] = field(default_factory=list)
    edges: list[float] = field(default_factory=list)
    realised: list[float] = field(default_factory=list)
    calibration: list[CalibrationBucket] = field(default_factory=list)

    @property
    def hit_rate(self) -> float | None:
        return self.n_wins / self.n_resolved if self.n_resolved else None

    @property
    def roi(self) -> float | None:
        return self.total_pnl / self.total_staked if self.total_staked else None

    @property
    def mean_clv(self) -> float | None:
        return statistics.mean(self.clv_points) if self.clv_points else None

    @property
    def clv_stderr(self) -> float | None:
        """Standard error of mean CLV — the honest uncertainty band."""
        n = len(self.clv_points)
        if n < 2:
            return None
        return statistics.pstdev(self.clv_points) / math.sqrt(n)

    @property
    def pct_beating_close(self) -> float | None:
        if not self.clv_points:
            return None
        return sum(1 for c in self.clv_points if c > 0) / len(self.clv_points)

    @property
    def max_drawdown(self) -> float:
        """Largest peak-to-trough fall in the equity curve."""
        if not self.equity_curve:
            return 0.0
        peak = self.equity_curve[0]
        worst = 0.0
        for value in self.equity_curve:
            peak = max(peak, value)
            if peak > 0:
                worst = max(worst, (peak - value) / peak)
        return worst

    @property
    def sharpe(self) -> float | None:
        """Per-bet Sharpe. Not annualised — bet frequency is irregular."""
        if len(self.returns) < 2:
            return None
        sd = statistics.pstdev(self.returns)
        if sd == 0:
            return None
        return statistics.mean(self.returns) / sd

    @property
    def edge_vs_realised_correlation(self) -> float | None:
        """Does predicted edge actually predict realised return?

        The single most informative diagnostic: a model can have positive ROI
        by luck, but a positive edge/return correlation means the *magnitude*
        of its edge estimate carries information.
        """
        if len(self.edges) < 3:
            return None
        try:
            return statistics.correlation(self.edges, self.realised)
        except (statistics.StatisticsError, ValueError):
            return None


def build_calibration(
    pairs: list[tuple[float, int]], buckets: int = 10
) -> list[CalibrationBucket]:
    """(predicted_probability, outcome 0/1) -> calibration table."""
    out = [
        CalibrationBucket(lower=i / buckets, upper=(i + 1) / buckets)
        for i in range(buckets)
    ]
    for prob, outcome in pairs:
        idx = min(int(prob * buckets), buckets - 1)
        out[idx].n += 1
        if outcome == 1:
            out[idx].n_hit += 1
    return out


def sample_size_verdict(n: int) -> str:
    """Plain statement about whether a sample supports any conclusion.

    An n=40 backtest with 8% ROI means nothing, and the report should say so
    rather than let the number stand unqualified.
    """
    if n == 0:
        return "No bets placed — nothing to conclude."
    if n < 50:
        return (
            f"n={n} is far too small to conclude anything. Win rate at this size is "
            "indistinguishable from noise; treat every number here as a smoke test "
            "of the machinery, not evidence of edge."
        )
    if n < 200:
        return (
            f"n={n} is small. ROI and hit rate remain noise-dominated; CLV is the "
            "only metric worth reading at this size."
        )
    if n < 1000:
        return (
            f"n={n} supports a tentative read on CLV, but ROI confidence intervals "
            "are still wide. Do not size up on this alone."
        )
    return f"n={n} is a usable sample for CLV; ROI still carries meaningful variance."
