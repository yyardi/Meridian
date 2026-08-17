"""Live totals FV tests.

Four things carry the weight, and three of them are corrections to the
original skeleton:

* **Frames.** YES = OVER (V14), so FV compares to the book without conversion.
  A flipped frame prices the opposite bet and stays inside [0, 1].
* **The update math.** The projection must move by a *fraction* of the
  divergence from the pregame anchor and must never extrapolate raw pace.
* **Period-appropriate coefficients.** 1.32 is a Q1 number, not a constant,
  and it must decay to 1.0 as points bank.
* **Period-appropriate sigma, from the TOTALS fit** — not the win curve's
  margin sigmas, which describe a different distribution and drift the other
  way.
"""

from __future__ import annotations

import inspect
import math

import pytest

from core.live_totals_fv import (
    GAP_HIGHLIGHT,
    REGULATION_MINUTES,
    TOTALS_ANCHORS,
    TotalsFV,
    expected_share,
    over_probability,
    project_total,
    remaining_sigma,
    surprise_coefficient,
)


def _row(**kw) -> TotalsFV:
    base = dict(
        event_slug="wnba-aaa-bbb-2026-08-07", market_slug="tsc-wnba-aaa-bbb-170pt5",
        label="Total 170.5", line=170.5, period="Q3", score="80-78",
        total_so_far=158, elapsed_minutes=30.0, minutes_left=10.0,
        minutes_left_is_estimate=False, pregame_mu=168.0,
        projected_total=172.0, sigma=9.67, fair_value=0.56, bid=0.52, ask=0.55,
    )
    base.update(kw)
    return TotalsFV(**base)


# --------------------------------------------------------------------- #
# Display only
# --------------------------------------------------------------------- #


def test_the_module_never_imports_the_executor():
    import core.live_totals_fv as m

    source = inspect.getsource(m)
    for forbidden in ("core.executor", "build_order", "LimitOrder",
                      "ShadowOrder", "place_order", "kelly"):
        assert forbidden not in source


def test_the_serialised_row_carries_no_order_or_size():
    from core.live_totals_fv import as_dict

    keys = set(as_dict(_row()))
    assert not keys & {"order", "quantity", "size", "ticket", "intent", "side"}


# --------------------------------------------------------------------- #
# Frames — YES = OVER
# --------------------------------------------------------------------- #


def test_a_projection_above_the_line_prices_over_above_a_half():
    """YES = OVER (V14), so FV compares to the YES book directly."""
    assert over_probability(projected_total=180.0, line=170.5, sigma=10.0) > 0.5


def test_a_projection_below_the_line_prices_over_below_a_half():
    assert over_probability(projected_total=160.0, line=170.5, sigma=10.0) < 0.5


def test_over_and_under_are_complements():
    over = over_probability(projected_total=175.0, line=170.5, sigma=12.0)
    under = over_probability(projected_total=170.5 * 2 - 175.0, line=170.5, sigma=12.0)
    assert over + under == pytest.approx(1.0)


def test_the_gap_is_model_minus_market_in_one_frame():
    row = _row(fair_value=0.60, bid=0.50, ask=0.52)
    assert row.mid == pytest.approx(0.51)
    assert row.gap == pytest.approx(0.09)
    assert row.highlight is True


def test_a_small_gap_is_not_highlighted():
    row = _row(fair_value=0.52, bid=0.50, ask=0.52)
    assert abs(row.gap) < GAP_HIGHLIGHT and row.highlight is False


def test_a_missing_quote_is_not_a_gap_of_zero():
    row = _row(bid=None, ask=None)
    assert row.mid is None and row.gap is None and row.highlight is False


def test_a_finished_game_prices_as_a_step_not_a_division_by_zero():
    assert over_probability(projected_total=175.0, line=170.5, sigma=0.0) == 1.0
    assert over_probability(projected_total=165.0, line=170.5, sigma=0.0) == 0.0


# --------------------------------------------------------------------- #
# The update math
# --------------------------------------------------------------------- #


def test_scoring_exactly_on_pace_leaves_the_projection_at_the_anchor():
    mu = 168.0
    on_pace = mu * expected_share(20.0)
    projected = project_total(pregame_mu=mu, total_so_far=round(on_pace),
                              elapsed_minutes=20.0)
    assert projected == pytest.approx(mu, abs=0.7)


def test_the_projection_moves_by_a_fraction_of_the_surprise_not_all_of_it():
    mu = 168.0
    expected = mu * expected_share(20.0)
    projected = project_total(pregame_mu=mu, total_so_far=round(expected + 10),
                              elapsed_minutes=20.0)
    moved = projected - mu
    assert 0 < moved < 10 * 1.5
    assert moved == pytest.approx(10 * surprise_coefficient(20.0), abs=0.7)


def test_raw_pace_is_never_extrapolated():
    """12-12 after three minutes must not imply a 320-point game.

    The failure this whole functional form exists to prevent.
    """
    mu = 168.0
    projected = project_total(pregame_mu=mu, total_so_far=24, elapsed_minutes=3.0)
    naive_pace = 24 * (REGULATION_MINUTES / 3.0)      # 320
    assert naive_pace == pytest.approx(320.0)
    assert projected < 200.0, "projection must stay near the anchor, not chase pace"


def test_a_high_scoring_game_projects_higher_and_a_low_one_lower():
    mu = 168.0
    hot = project_total(pregame_mu=mu, total_so_far=110, elapsed_minutes=20.0)
    cold = project_total(pregame_mu=mu, total_so_far=60, elapsed_minutes=20.0)
    assert hot > mu > cold


# --------------------------------------------------------------------- #
# The coefficient is a Q1 number, not a constant
# --------------------------------------------------------------------- #


def test_the_q1_coefficient_reproduces_the_projects_long_standing_1_32():
    assert surprise_coefficient(10.0) == pytest.approx(1.318, abs=0.005)


def test_the_coefficient_decays_through_the_game():
    """A point scored is 1.0 banked plus what it says about the rest.

    As the game runs out the second term goes to zero, so using 1.32 at the
    half over-weights the surprise by ~9% and at end-Q3 by ~17%.
    """
    q1 = surprise_coefficient(10.0)
    half = surprise_coefficient(20.0)
    q3 = surprise_coefficient(30.0)
    assert q1 > half > q3 > 1.0
    assert half == pytest.approx(1.208, abs=0.005)
    assert q3 == pytest.approx(1.128, abs=0.005)


def test_at_full_time_every_point_is_banked_and_nothing_informs():
    assert surprise_coefficient(REGULATION_MINUTES) == pytest.approx(1.0)


def test_the_coefficient_is_interpolated_between_period_anchors():
    mid = surprise_coefficient(25.0)
    assert surprise_coefficient(30.0) < mid < surprise_coefficient(20.0)


# --------------------------------------------------------------------- #
# Sigma is the TOTALS fit, not the win curve's margin sigma
# --------------------------------------------------------------------- #


def test_sigma_is_the_fitted_totals_residual_not_the_margin_sigma():
    """The win curve's 2.98/2.77/2.40 describe the score DIFFERENCE.

    Borrowing them for totals would understate remaining uncertainty by ~27%
    at end-Q3 — overconfidence exactly where someone would act on it.
    """
    assert remaining_sigma(10.0) == pytest.approx(15.88, abs=0.02)
    assert remaining_sigma(20.0) == pytest.approx(13.03, abs=0.02)
    assert remaining_sigma(30.0) == pytest.approx(9.67, abs=0.02)

    # What the borrowed margin sigmas would have given at end Q3:
    borrowed = 2.40 * math.sqrt(REGULATION_MINUTES - 30.0)
    assert borrowed < remaining_sigma(30.0)
    assert borrowed / remaining_sigma(30.0) < 0.80


def test_sigma_shrinks_monotonically_as_the_game_runs_out():
    values = [remaining_sigma(e) for e in (0.0, 10.0, 20.0, 30.0, 40.0)]
    assert values == sorted(values, reverse=True)


def test_pregame_sigma_matches_the_models_own_total_sigma():
    assert remaining_sigma(0.0) == pytest.approx(19.0, abs=0.5)


def test_sigma_is_zero_at_full_time():
    assert remaining_sigma(REGULATION_MINUTES) == pytest.approx(0.0)


def test_per_sqrt_minute_totals_sigma_does_not_decay_like_the_margin_one():
    """The measured direction, which is why sqrt-t was not imposed."""
    per_sqrt = [remaining_sigma(e) / math.sqrt(REGULATION_MINUTES - e)
                for e in (10.0, 20.0, 30.0)]
    assert per_sqrt[2] > per_sqrt[0], "totals sigma per sqrt-minute rises, margin falls"


# --------------------------------------------------------------------- #
# Shares, and the endpoints
# --------------------------------------------------------------------- #


def test_expected_share_is_measured_and_near_uniform():
    assert expected_share(10.0) == pytest.approx(0.2541, abs=0.001)
    assert expected_share(20.0) == pytest.approx(0.5022, abs=0.001)
    assert expected_share(30.0) == pytest.approx(0.7566, abs=0.001)


def test_share_runs_from_nothing_to_everything():
    assert expected_share(0.0) == pytest.approx(0.0)
    assert expected_share(REGULATION_MINUTES) == pytest.approx(1.0)


def test_anchors_are_ordered_and_cover_regulation():
    elapsed = [a[0] for a in TOTALS_ANCHORS]
    assert elapsed == sorted(elapsed)
    assert elapsed[0] == 0.0 and elapsed[-1] == REGULATION_MINUTES


def test_values_outside_regulation_are_clamped_not_extrapolated():
    """OT is suppressed upstream; the maths must not blow up regardless."""
    assert surprise_coefficient(90.0) == pytest.approx(1.0)
    assert remaining_sigma(90.0) == pytest.approx(0.0)
    assert expected_share(-5.0) == pytest.approx(0.0)


# --------------------------------------------------------------------- #
# Overtime
# --------------------------------------------------------------------- #


def test_overtime_yields_no_fair_value():
    """A regulation projection cannot price a game still adding points.

    `Clock.usable` is False in OT, and `build_live_totals_fv` suppresses on it
    — the same treatment the moneyline strip gives.
    """
    from core.live_fv import minutes_remaining

    assert minutes_remaining("OT", seconds_into_period=60.0).usable is False


def test_an_exhausted_clock_yields_no_fair_value():
    from core.live_fv import minutes_remaining

    assert minutes_remaining("Q4", seconds_into_period=45 * 60.0).usable is False
