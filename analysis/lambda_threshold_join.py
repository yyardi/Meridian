"""Join lambda* to the taker threshold. Shared so D and B run one implementation.

★ READ THIS BEFORE USING IT ON PULSE. The threshold prices CROSSING, and PULSE
does not cross: Quant B measured it 100% passive — side=yes posts at
`market_bid` on 100.0% of 1,342 entries, side=no at `market_ask` on 100.0% of
1,632, both arms joining the touch. So this module is the bar for a
hypothetical TAKER strategy. Applying it to PULSE compares a maker engine
against a taker bar.

★ AND THE ANSWER IS CONVENTION-DEPENDENT. On one tape, lambda* is +0.364
(earliest row per market), +0.219 (all rows) or +0.217 (entries, all rows) — and
the required 0.337 sits INSIDE that range, so the dedupe choice decides whether
the point estimate clears. Every one of those intervals also contains zero.
Pin the convention and quote the interval, or do not quote the comparison.

    from analysis.lambda_threshold_join import threshold, table
    table()

The threshold is builder-d5's (docs/math/taker-edge-threshold.md); the
conversion edge = lambda* x |fv - mid| is Quant B's. Neither is re-derived here.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize_scalar

#: Measured NEAR-MONEY half-spread. The curve is only valid for 0.15 <~ p <~ 0.85:
#: the 0.95/0.05 rungs carry measured 22-26c spreads, so a constant half-spread
#: is wrong in the tails and the threshold RISES there rather than falling.
HALF_SPREAD = 0.01193
_E = 1e-6


def threshold(p: float = 0.50) -> float:
    """Minimum taker edge at mid price `p`, in probability units.

    Hold-to-settlement: one spread, one fee, NO exit leg (a binary settles 0/1
    and is never sold).
    """
    ask = p + HALF_SPREAD
    return HALF_SPREAD + 0.06 * ask * (1.0 - ask)


def _logit(x):
    x = np.clip(x, _E, 1 - _E)
    return np.log(x / (1 - x))


def lam_star(frame) -> float:
    """Blend weight on the model against the mid, by log-loss."""
    y = frame.y.values.astype(float)
    m, v = _logit(frame["mid"].values), _logit(frame.fair_value.values)

    def ll(L):
        q = np.clip(1 / (1 + np.exp(-((1 - L) * m + L * v))), _E, 1 - _E)
        return -np.mean(y * np.log(q) + (1 - y) * np.log(1 - q))

    return float(minimize_scalar(ll, bounds=(-1.0, 2.0), method="bounded").x)


def games_to_settle(lam: float, half_width: float, G: int,
                    target: float | None = None) -> dict:
    """What sample would settle `lam` against the threshold's required lambda*.

    The asymmetry that matters: while the point estimate sits BELOW the target,
    tightening moves the interval toward the point and therefore AWAY from
    clearing. More data can then only ever confirm failure — it cannot confirm
    success. Reported explicitly rather than left as a sample-size number.
    """
    target = threshold() / 0.08 if target is None else target
    if lam >= target:
        gap = lam - target
        return {"direction": "could confirm CLEARING",
                "games": G * (half_width / gap) ** 2 if gap else float("inf")}
    gap = target - lam
    return {"direction": "can only ever confirm FAILURE — the point is below target",
            "games": G * (half_width / gap) ** 2}
