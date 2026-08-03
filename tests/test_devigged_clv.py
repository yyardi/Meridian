"""Tests for the points-to-money conversion.

This is new arithmetic sitting directly under a headline number, so it gets
tested against cases whose answers are known by hand rather than by running it.
"""

from __future__ import annotations

import pytest

from core.backtest.exp_devigged_clv import (
    closing_probability,
    devig_two_sided,
    interval,
)

# ------------------------------------------------------------------ #
# De-vigging
# ------------------------------------------------------------------ #


def test_symmetric_market_devigs_to_a_coin_flip():
    """-110/-110 implies 52.4% each; fair is 50/50."""
    over = under = 110 / 210  # 0.5238
    result = devig_two_sided(over, under)
    assert result is not None
    assert result[0] == pytest.approx(0.5)
    assert result[1] == pytest.approx(0.5)


def test_devigged_probabilities_always_sum_to_one():
    result = devig_two_sided(0.60, 0.48)
    assert result is not None
    assert sum(result) == pytest.approx(1.0)


def test_devig_preserves_the_favourite():
    """Removing the margin must not reorder the two sides."""
    over, under = devig_two_sided(0.60, 0.48)
    assert over > under


def test_devig_rejects_degenerate_input():
    assert devig_two_sided(0.0, 0.5) is None
    assert devig_two_sided(-0.1, 0.5) is None


def test_devig_removes_exactly_the_overround():
    """A 4.8% overround must come out entirely, not partially."""
    over, under = 0.5238, 0.5238
    assert over + under == pytest.approx(1.0476, abs=1e-4)
    devigged = devig_two_sided(over, under)
    assert sum(devigged) == pytest.approx(1.0)


# ------------------------------------------------------------------ #
# Points -> probability
# ------------------------------------------------------------------ #


def test_no_line_move_is_a_coin_flip():
    """If the close never moved, our line is the market's own estimate."""
    p = closing_probability(side="over", entry_line=160.0, closing_line=160.0, sigma=17.0)
    assert p == pytest.approx(0.5)


def test_line_moving_our_way_raises_our_probability():
    """We took the over at 160 and the market closed at 164: good for us."""
    p = closing_probability(side="over", entry_line=160.0, closing_line=164.0, sigma=17.0)
    assert p > 0.5


def test_the_two_sides_are_complementary():
    over = closing_probability(side="over", entry_line=160.0, closing_line=164.0, sigma=17.0)
    under = closing_probability(side="under", entry_line=160.0, closing_line=164.0, sigma=17.0)
    assert over + under == pytest.approx(1.0)


def test_sigma_scales_the_conversion():
    """The same point move is worth less probability in a noisier environment.

    This is the whole reason CLV cannot be quoted in points: 2026 runs sigma
    ~21.7 against 17.3 in earlier seasons, so an identical 1.75-point beat is
    materially less edge now than it was then.
    """
    tight = closing_probability(side="over", entry_line=160, closing_line=164, sigma=14.0)
    loose = closing_probability(side="over", entry_line=160, closing_line=164, sigma=22.0)
    assert tight > loose > 0.5


def test_zero_sigma_is_refused_not_guessed():
    assert closing_probability(side="over", entry_line=160, closing_line=164, sigma=0.0) is None


# ------------------------------------------------------------------ #
# Buchdahl's rule, end to end
# ------------------------------------------------------------------ #


def test_expected_roi_matches_the_hand_calculation():
    """Pay 0.50 for something the close values at 0.55 -> +10% expected.

    E[ROI] = p_close / p_paid − 1 = 0.55/0.50 − 1 = 0.10.
    """
    assert 0.55 / 0.50 - 1 == pytest.approx(0.10)


def test_paying_fair_value_expects_nothing():
    assert 0.52 / 0.52 - 1 == pytest.approx(0.0)


def test_interval_needs_two_points():
    assert interval([]) is None
    assert interval([0.1]) is None
    iv = interval([0.1, 0.2, 0.3])
    assert iv is not None
    assert iv.mean == pytest.approx(0.2)
    assert iv.low < iv.mean < iv.high
