"""The reversion-shrink eval arm (docs/math/pulse-reversion-shrink.md).

What is defended:

* s(elapsed) is the registered piecewise-linear curve through the measured
  knots — held before 10', exact at every boundary, forced to zero at 40'
  (banked points cannot revert), never negative;
* the shrunk FV is the incumbent's own math whenever there is nothing to
  shrink: zero deviation, the game's end, and the incumbent's refusals
  (no pregame price, whole-number spread lines) all reproduce exactly;
* the shrink moves probabilities TOWARD the pregame expectation — a team
  ahead of its expected pace is trimmed, one behind is lifted;
* the verdict implements both registered clauses and the floors, and its
  gate cutoff is the registration's corrected commit instant.
"""

from __future__ import annotations

import datetime as dt
import itertools
import math

import pytest
from scipy import stats as scipy_stats

from core.live_fv import DEFAULT_SIGMA, REGULATION_MINUTES, fair_value
from core.pulse.live import MARKET_SPREAD, MARKET_TOTAL, MARKET_WINNER
from core.pulse.replay_eval import (
    REVERSION_SHRINK_REGISTERED_AT,
    ShrinkGameRead,
    reversion_shrink_fraction,
    shrink_verdict,
    shrunk_margin_fv,
)

UTC = dt.timezone.utc
GATE_TS = dt.datetime(2026, 8, 26, 12, 0, tzinfo=UTC)


def _price_for_edge(edge: float) -> float:
    """Invert pregame_margin_from_price: the price whose implied full-game
    margin is exactly `edge`."""
    return float(scipy_stats.norm.cdf(
        edge / (DEFAULT_SIGMA * math.sqrt(REGULATION_MINUTES))))


# ------------------------------------------------------------------ #
# s(elapsed)
# ------------------------------------------------------------------ #


def test_shrink_fraction_is_the_registered_curve():
    assert reversion_shrink_fraction(0.0) == 0.28      # held before 10'
    assert reversion_shrink_fraction(10.0) == 0.28
    assert reversion_shrink_fraction(20.0) == 0.157
    assert reversion_shrink_fraction(30.0) == 0.137
    assert reversion_shrink_fraction(40.0) == 0.0      # banked points
    assert reversion_shrink_fraction(45.0) == 0.0
    assert reversion_shrink_fraction(15.0) == pytest.approx((0.28 + 0.157) / 2)
    assert reversion_shrink_fraction(35.0) == pytest.approx(0.137 / 2)
    # Monotone non-increasing after the hold, never negative.
    xs = [reversion_shrink_fraction(x / 2) for x in range(20, 90)]
    assert all(a >= b >= 0.0 for a, b in itertools.pairwise(xs))


# ------------------------------------------------------------------ #
# The shrunk FV vs the incumbent
# ------------------------------------------------------------------ #


def test_zero_deviation_reproduces_the_incumbent_exactly():
    """A team exactly on its expected pace has nothing to shrink: with
    E=8 and 20 of 40 minutes gone, margin 4 IS the prorated expectation."""
    price = _price_for_edge(8.0)
    inc = fair_value(margin=4, minutes_left=20.0, pregame_price=price)
    shr = shrunk_margin_fv(market_type=MARKET_WINNER, line=None, margin=4,
                           minutes_left=20.0, pregame_price=price)
    assert shr == pytest.approx(inc, abs=1e-12)


def test_shrink_pulls_toward_the_pregame_expectation():
    price = _price_for_edge(8.0)
    common = {"market_type": MARKET_WINNER, "line": None,
              "minutes_left": 20.0, "pregame_price": price}
    # Ahead of pace (margin 14 vs expected 4): trimmed toward the prior.
    inc_hot = fair_value(margin=14, minutes_left=20.0, pregame_price=price)
    assert shrunk_margin_fv(**common, margin=14) < inc_hot
    # Behind pace (margin -6): lifted toward the prior.
    inc_cold = fair_value(margin=-6, minutes_left=20.0, pregame_price=price)
    assert shrunk_margin_fv(**common, margin=-6) > inc_cold


def test_endpoint_and_refusals_match_the_incumbent():
    price = _price_for_edge(5.0)
    # Game over: settled by the margin alone, same as fair_value.
    assert shrunk_margin_fv(market_type=MARKET_WINNER, line=None, margin=3,
                            minutes_left=0.0, pregame_price=price) == 1.0
    assert fair_value(margin=3, minutes_left=0.0, pregame_price=price) == 1.0
    # No pregame price: refuse, never a coin flip.
    assert shrunk_margin_fv(market_type=MARKET_WINNER, line=None, margin=3,
                            minutes_left=20.0, pregame_price=None) is None
    # Whole-number spread line: push semantics unverified, refuse.
    assert shrunk_margin_fv(market_type=MARKET_SPREAD, line=7.0, margin=3,
                            minutes_left=20.0, pregame_price=price) is None
    # Totals are not this function's to price — the registration leaves
    # them untouched and the caller keeps the incumbent's estimate.
    assert shrunk_margin_fv(market_type=MARKET_TOTAL, line=160.5, margin=3,
                            minutes_left=20.0, pregame_price=price) is None


def test_spread_shrinks_the_same_expected_margin():
    price = _price_for_edge(8.0)
    # Ahead of pace: the shrunk expected margin is smaller, so the YES
    # side of any half-point rung prices lower too.
    from core.pulse.live import spread_fair_value
    inc = spread_fair_value(margin=14, minutes_left=20.0, line=-9.5,
                            pregame_price=price)
    shr = shrunk_margin_fv(market_type=MARKET_SPREAD, line=-9.5, margin=14,
                           minutes_left=20.0, pregame_price=price)
    assert shr < inc


# ------------------------------------------------------------------ #
# Verdict — both clauses, the corrected cutoff
# ------------------------------------------------------------------ #


def test_gate_cutoff_is_the_corrected_commit_instant():
    assert REVERSION_SHRINK_REGISTERED_AT == "2026-08-25T23:08:20+00:00"


def _read(i: int, *, diffs, inc_roi, shr_roi, n_points=300) -> ShrinkGameRead:
    r = ShrinkGameRead(event_slug=f"g{i}", first_seen=GATE_TS)
    r.n_points = n_points
    r.diffs = diffs
    r.rois["incumbent"] = inc_roi
    r.rois["shrunk"] = shr_roi
    return r


def test_shrink_verdict_branches():
    def jitter(i: int) -> float:
        return 0.001 * (i % 3)

    below = [_read(i, diffs=[0.01], inc_roi=[0.0], shr_roi=[0.01])
             for i in range(9)]        # 9 games / 2,700 points: below floor
    assert shrink_verdict(below) == "NO DATA"

    passing = [_read(i, diffs=[0.010 + jitter(i)], inc_roi=[0.02],
                     shr_roi=[0.03 + jitter(i)]) for i in range(12)]
    assert shrink_verdict(passing).startswith("PASS")

    not_separable = [_read(i, diffs=[0.01 if i % 2 else -0.01],
                           inc_roi=[0.02], shr_roi=[0.03])
                     for i in range(12)]
    assert shrink_verdict(not_separable) == "FAIL"

    money_worse = [_read(i, diffs=[0.010 + jitter(i)], inc_roi=[0.05],
                         shr_roi=[-0.20 + jitter(i)]) for i in range(12)]
    v = shrink_verdict(money_worse)
    assert v.startswith("FAIL") and "second clause" in v
