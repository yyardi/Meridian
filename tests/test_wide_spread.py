"""The wide-spread maker analysis, and the identity it rests on.

The whole analysis depends on one derivation: a filled resting quote nets
`h - |d|`, where h is the half-spread and d the mid move over the horizon. If
that is wrong, every number is wrong — so it is checked against
`core/quote/adverse_selection.py`'s own arithmetic rather than asserted.
"""

from __future__ import annotations

import datetime as dt
import random

import pytest

from cfb.run_wide_spread import clustered_mean, geometry_null
from core.quote.adverse_selection import Quote, QuoteWindow

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 9, 15, 12, 0, tzinfo=UTC)


def _win(mid: float, spread: float, dmid: float) -> QuoteWindow:
    q = Quote("g", "s", T0, bid=mid - spread / 2, ask=mid + spread / 2)
    return QuoteWindow(quote=q, horizon_seconds=30.0, mid_at_horizon=mid + dmid)


@pytest.mark.parametrize("spread,dmid", [
    (0.02, -0.03), (0.02, +0.03), (0.10, -0.20), (0.30, +0.40), (0.04, -0.02),
])
def test_the_net_identity_matches_the_modules_own_arithmetic(spread, dmid):
    """★ net = h - |d| on whichever side filled. Derived by hand and checked
    against the module, because the analysis is built on it."""
    w = _win(0.50, spread, dmid)
    h = spread / 2.0
    fills = w.fills(fee=0.0)
    assert fills, "the fixture should fill: |dmid| >= h by construction"
    for got in fills:
        assert got == pytest.approx(h - abs(dmid)), (
            f"module says {got:+.4f}, identity says {h - abs(dmid):+.4f}")


def test_a_filled_quote_can_never_net_positive():
    """★ THE REASON "MAKING LOSES IN EVERY BUCKET" IS NOT A MEASUREMENT.
    The fill rule and the P&L mark are the same variable: you are filled
    exactly when the mid has passed your price, and you are marked at that
    mid. So net <= 0 by identity, in every band, at every spread."""
    rng = random.Random(4)
    for _ in range(500):
        spread = rng.uniform(0.01, 0.50)
        dmid = rng.uniform(-0.4, 0.4)
        w = _win(0.50, spread, dmid)
        for got in w.fills(fee=0.0):
            assert got <= 1e-12, f"a filled quote netted {got:+.4f} > 0"


def test_an_unfilled_quote_is_not_counted_at_all():
    """|d| < h means neither side is touched, so the window contributes
    nothing. The conditioning is what makes net negative, and it has to be
    visible."""
    w = _win(0.50, 0.20, 0.05)
    assert w.fills(fee=0.0) == []


# ------------------------------------------------------- the null itself #

def test_the_nulls_DIRECTION_depends_on_the_tail_not_on_the_spread():
    """★ THE FINDING THIS WHOLE ANALYSIS RESTS ON, and my first version of this
    test asserted the opposite.

    I wrote that the null "must get MORE negative with h" because a wider
    quote needs a bigger move to fill it. That is wrong for a thin tail: the
    conditional mean of |d| given |d| >= h exceeds h by a SHRINKING margin as
    h grows, so net -> 0 from below. Measured on 200k draws:

        normal sd .05  h=.01 -3.65c  h=.05 -2.62c  h=.20  -1.09c   (improves)
        fat-tailed     h=.01 -5.27c  h=.05 -6.23c  h=.20 -26.02c   (worsens)

    So the SIGN of the net-versus-spread gradient under pure geometry is set
    by the tail of the move distribution and can point either way. A gradient
    read without the null is uninterpretable in principle rather than merely
    underpowered: the same picture is consistent with "wide quoting pays" and
    with "the moves are thin-tailed", and those have opposite consequences.
    """
    rng = random.Random(1)
    thin = [rng.gauss(0, 0.05) for _ in range(40000)]
    fat = [rng.gauss(0, 0.05) * (1 if rng.random() > 0.05 else 8)
           for _ in range(40000)]

    thin_narrow, thin_wide = geometry_null(thin, [0.01]), geometry_null(thin, [0.20])
    fat_narrow, fat_wide = geometry_null(fat, [0.01]), geometry_null(fat, [0.20])

    assert thin_wide > thin_narrow, (
        "a thin tail must make net LESS negative as h grows -- geometry alone "
        "then looks like 'wide spreads pay'")
    assert fat_wide < fat_narrow, (
        "a fat tail must make net MORE negative as h grows")
    assert thin_wide > fat_wide, "the two tails must be separable at wide h"


def test_when_moves_are_independent_of_spread_the_observed_equals_the_null():
    """★ THE POSITIVE CONTROL FOR THE NULL. Generate windows whose move
    distribution is IDENTICAL in every band; the observed per-band net must
    then land on the null, because there is nothing else in the data."""
    rng = random.Random(7)
    d_all = [rng.gauss(0, 0.06) for _ in range(6000)]
    for h in (0.01, 0.03, 0.08):
        observed = [h - abs(x) for x in d_all if abs(x) >= h]
        null = geometry_null(d_all, [h])
        assert null is not None and observed
        assert sum(observed) / len(observed) == pytest.approx(null, abs=1e-9), (
            "the null does not reproduce its own generating process, so a "
            "departure from it would not mean what the report says it means")


def test_the_clustered_interval_widens_as_clusters_shrink():
    """Named estimator: pooled mean, t interval on CLUSTER means. Two games
    must not produce the interval that fifty do."""
    rng = random.Random(3)
    many = {f"g{i}": [rng.gauss(-0.01, 0.02) for _ in range(20)]
            for i in range(50)}
    few = {k: many[k] for k in list(many)[:3]}
    _, lo_m, hi_m, g_m, _ = clustered_mean(many)
    _, lo_f, hi_f, g_f, _ = clustered_mean(few)
    assert g_m == 50 and g_f == 3
    assert (hi_f - lo_f) > (hi_m - lo_m) * 2


def test_one_game_returns_no_interval_rather_than_a_within_game_one():
    got = clustered_mean({"g": [0.1, 0.2, 0.3]})
    assert got is not None
    point, lo, hi, g, n = got
    assert lo is None and hi is None and g == 1, (
        "a one-game interval is a within-game interval wearing the word "
        "'clustered'")


def test_mean_excess_is_the_parameter_that_sets_the_nulls_direction():
    """★ THE TAIL IS THE PARAMETER, not a diagnostic beside the result.

    net-by-band is -e(h) under the null, so e(h)'s SLOPE is the null's
    direction. A monotone net column means opposite things in the two regimes,
    and this is the number that says which one you are in.
    """
    from cfb.run_wide_spread import mean_excess

    rng = random.Random(5)
    thin = [rng.gauss(0, 0.05) for _ in range(40000)]
    fat = [rng.gauss(0, 0.05) * (1 if rng.random() > 0.05 else 8)
           for _ in range(40000)]

    # h values chosen INSIDE the thin sample's support. At h=0.20 the thin
    # draw has zero tail observations (max |d| = 0.1999 over 40k), which is
    # not a bug -- see the next test -- but it is not a place to compare
    # slopes from.
    e_thin = [mean_excess(thin, h) for h in (0.01, 0.05, 0.12)]
    e_fat = [mean_excess(fat, h) for h in (0.01, 0.05, 0.12)]
    assert all(x is not None for x in e_thin + e_fat)

    assert e_thin[0] > e_thin[1] > e_thin[2], (
        f"thin tail must have DECREASING mean excess, got {e_thin}")
    assert e_fat[2] > e_fat[0], (
        f"heavy tail must have INCREASING mean excess, got {e_fat}")


def test_a_half_spread_beyond_the_moves_support_returns_none_not_a_number():
    """★ AND THIS IS AN OPERATIONAL ANSWER, not an edge case. With a thin move
    distribution, a wide enough quote is NEVER FILLED: over 40,000 draws at
    sd 0.05 the largest |d| is 0.1999, so a 20c half-spread (a 40c spread) has
    an empty tail. e(h) is then undefined and the band reports "no fills"
    rather than a fabricated net.

    "Can you make money quoting wide" has an answer that is not about edge:
    not if nothing ever comes to you.
    """
    from cfb.run_wide_spread import geometry_null, mean_excess

    rng = random.Random(5)
    thin = [rng.gauss(0, 0.05) for _ in range(40000)]
    assert max(abs(x) for x in thin) < 0.20
    assert mean_excess(thin, 0.20) is None
    assert geometry_null(thin, [0.20]) is None


def test_net_under_the_null_is_exactly_minus_the_mean_excess():
    """The identity that makes e(h) load-bearing rather than decorative: the
    null's per-band net IS -e(h), so reporting both is reporting one quantity
    twice — deliberately, because readers trust a 'net' column and interrogate
    a 'tail' one."""
    from cfb.run_wide_spread import geometry_null, mean_excess

    # A NEW Random(9) PER ITERATION GIVES 20,000 IDENTICAL VALUES. That bug
    # was in this file twice; the second copy is what caught it, because a
    # degenerate sample makes mean_excess None at any h above the single
    # value and the TypeError was unmissable. The first copy failed silently
    # in the sense that matters: it failed for the wrong reason.
    rng = random.Random(9)
    d = [rng.gauss(0, 0.04) for _ in range(20000)]
    for h in (0.01, 0.03, 0.10):
        assert geometry_null(d, [h]) == pytest.approx(-mean_excess(d, h),
                                                      abs=1e-12)
