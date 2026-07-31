"""Recover the market's implied distribution from a ladder of totals.

Polymarket lists many totals markets on one game (Over 173.5, 176.5, ...).
Each price is a point on the survival function of the game total; together they
trace a distribution. Fitting a normal recovers *the market's* implied mean and
sigma.

Why bother: without this you are comparing a point estimate (your projected
total, in points) against a price (0.52). After the fit both sides are in
points, so "the market is 4 points high" is a claim you can sanity-check
against basketball intuition. "Our probability is 5.8% higher" is not.

See docs/math/ladder-curve-fit.md.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import minimize
from scipy.stats import norm


@dataclass(frozen=True)
class LadderRung:
    """One totals market on the ladder."""

    line: float
    bid: float | None
    ask: float | None

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


@dataclass(frozen=True)
class LadderFit:
    """Result of fitting a normal to a ladder."""

    implied_mean: float | None
    implied_stdev: float | None
    rmse: float | None
    r_squared: float | None
    rungs_used: int
    rungs_dropped: int
    ok: bool
    reason: str = ""
    dropped_reasons: tuple[str, ...] = field(default_factory=tuple)


#: Rungs wider than this carry no usable information. One real rung was
#: observed quoting bid 0.03 / ask 0.39.
DEFAULT_MAX_SPREAD = 0.10
#: Two points fit a two-parameter model exactly and tell you nothing.
DEFAULT_MIN_RUNGS = 4
#: Bounds keep the optimiser in physically sensible territory.
SIGMA_BOUNDS = (3.0, 60.0)


def clean_rungs(
    rungs: list[LadderRung],
    *,
    max_spread: float = DEFAULT_MAX_SPREAD,
) -> tuple[list[tuple[float, float]], list[str]]:
    """Filter a ladder down to usable (line, prob_over) points.

    Drops rungs with a missing or implausible mid, and rungs whose bid/ask
    spread is too wide to carry information.
    """
    kept: list[tuple[float, float]] = []
    dropped: list[str] = []

    for r in rungs:
        mid = r.mid
        if mid is None:
            dropped.append(f"{r.line}: missing quote")
            continue
        spread = r.spread
        if spread is not None and spread > max_spread:
            dropped.append(f"{r.line}: spread {spread:.2f} > {max_spread:.2f}")
            continue
        if not (0.0 < mid < 1.0):
            dropped.append(f"{r.line}: mid {mid:.3f} out of range")
            continue
        kept.append((float(r.line), float(mid)))

    kept.sort(key=lambda p: p[0])
    return kept, dropped


def check_monotonic(points: list[tuple[float, float]], tolerance: float = 0.02) -> list[str]:
    """P(Over) must be non-increasing as the line rises.

    Over 176.5 cannot be *more* likely than Over 173.5. A violation means stale
    or crossed quotes. Small tolerance absorbs tick-level noise.
    """
    violations = []
    for (l1, p1), (l2, p2) in zip(points, points[1:]):
        if p2 > p1 + tolerance:
            violations.append(f"P(Over {l2})={p2:.3f} > P(Over {l1})={p1:.3f}")
    return violations


def fit_ladder(
    points: list[tuple[float, float]],
    *,
    min_rungs: int = DEFAULT_MIN_RUNGS,
    monotonic_tolerance: float = 0.02,
) -> LadderFit:
    """Fit Normal(mu, sigma) to [(line, P(Over line)), ...].

    Minimises squared error between observed probabilities and
    ``1 - Phi((line - mu) / sigma)``.
    """
    n = len(points)
    if n < min_rungs:
        return LadderFit(None, None, None, None, n, 0, False, f"only {n} rungs (need {min_rungs})")

    violations = check_monotonic(points, monotonic_tolerance)
    if violations:
        return LadderFit(
            None, None, None, None, n, 0, False,
            f"non-monotonic ladder: {'; '.join(violations[:3])}",
        )

    lines = np.array([p[0] for p in points], dtype=float)
    probs = np.array([p[1] for p in points], dtype=float)

    def objective(params: np.ndarray) -> float:
        mu, sigma = params
        if sigma <= 0:
            return 1e9
        implied = 1.0 - norm.cdf(lines, loc=mu, scale=sigma)
        return float(np.sum((probs - implied) ** 2))

    # Seed from the data: the line where P(Over) crosses 0.5 approximates the
    # mean, and the ladder's own width bounds a sensible starting sigma.
    mu0 = float(np.interp(0.5, probs[::-1], lines[::-1]))
    sigma0 = max(5.0, float(lines.max() - lines.min()) / 2.0)

    result = minimize(
        objective,
        x0=np.array([mu0, sigma0]),
        method="Nelder-Mead",
        options={"xatol": 1e-4, "fatol": 1e-8, "maxiter": 2000},
    )
    if not result.success:
        return LadderFit(None, None, None, None, n, 0, False, f"optimiser failed: {result.message}")

    mu, sigma = float(result.x[0]), float(result.x[1])
    if not (SIGMA_BOUNDS[0] <= sigma <= SIGMA_BOUNDS[1]):
        return LadderFit(None, None, None, None, n, 0, False, f"sigma {sigma:.1f} implausible")

    implied = 1.0 - norm.cdf(lines, loc=mu, scale=sigma)
    residuals = probs - implied
    rmse = float(math.sqrt(np.mean(residuals**2)))
    ss_res = float(np.sum(residuals**2))
    ss_tot = float(np.sum((probs - probs.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    return LadderFit(
        implied_mean=mu,
        implied_stdev=sigma,
        rmse=rmse,
        r_squared=r2,
        rungs_used=n,
        rungs_dropped=0,
        ok=True,
    )


def fit_from_rungs(
    rungs: list[LadderRung],
    *,
    max_spread: float = DEFAULT_MAX_SPREAD,
    min_rungs: int = DEFAULT_MIN_RUNGS,
) -> LadderFit:
    """Clean a raw ladder then fit it."""
    points, dropped = clean_rungs(rungs, max_spread=max_spread)
    fit = fit_ladder(points, min_rungs=min_rungs)
    return LadderFit(
        implied_mean=fit.implied_mean,
        implied_stdev=fit.implied_stdev,
        rmse=fit.rmse,
        r_squared=fit.r_squared,
        rungs_used=fit.rungs_used,
        rungs_dropped=len(dropped),
        ok=fit.ok,
        reason=fit.reason,
        dropped_reasons=tuple(dropped),
    )
