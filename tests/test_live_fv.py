"""Live FV strip tests.

Three things carry the weight:

* **It stays display-only.** The strip must have no path to an order. That is
  a property of the code, so it is asserted against the source rather than
  trusted to review.
* **Frame conventions.** The margin is computed in the first team's frame
  because that is the frame the YES side of the book is quoted in. Mixing them
  is the V15 bug and it produces numbers that pass every individual check.
* **Interpolation edges.** There is no game clock, so minutes-remaining is
  interpolated; period start, halftime, overtime and a quarter that runs long
  are each capable of producing a negative time and an imaginary square root.
"""

from __future__ import annotations

import inspect
import math

import pytest

from core.live_fv import (
    DEFAULT_SIGMA,
    GAP_HIGHLIGHT,
    OT_MINUTES,
    REGULATION_MINUTES,
    LiveFV,
    fair_value,
    minutes_remaining,
    parse_score,
)


def _row(**kw) -> LiveFV:
    base = dict(
        event_slug="wnba-aaa-bbb-2026-08-06", market_slug="aec-wnba-aaa-bbb-2026-08-06",
        label="AAA to win", period="Q2", score="40-42", margin=-2,
        minutes_left=20.0, minutes_left_is_estimate=True, pregame_price=0.50,
        fair_value=0.45, bid=0.40, ask=0.42,
    )
    base.update(kw)
    return LiveFV(**base)


# --------------------------------------------------------------------- #
# Display only — asserted, not assumed
# --------------------------------------------------------------------- #


def test_the_module_never_imports_the_executor():
    """No path from a displayed number to a sent order."""
    import core.live_fv as m

    source = inspect.getsource(m)
    for forbidden in ("core.executor", "build_order", "LimitOrder",
                      "ShadowOrder", "place_order", "kelly"):
        assert forbidden not in source, f"{forbidden} must not reach the FV strip"


def test_the_serialised_row_carries_no_order_or_size_fields():
    from core.live_fv import as_dict

    keys = set(as_dict(_row()))
    assert not keys & {"order", "quantity", "size", "ticket", "intent", "side"}


def test_the_strip_markup_has_no_ticket_handler():
    """The picks page opens tickets from other tables; not from this one."""
    from pathlib import Path

    html = Path("static/picks.html").read_text()
    start = html.index("async function loadLiveFV")
    block = html[start:html.index("setInterval(loadLiveFV", start)]
    for forbidden in ("openTicket", "sendCell", "PICKS[", "confirmBtn"):
        assert forbidden not in block, f"{forbidden} must not appear in the FV strip"


# --------------------------------------------------------------------- #
# Frame conventions
# --------------------------------------------------------------------- #


def test_score_parses_as_first_team_then_second_team():
    assert parse_score("46-34") == (46, 34)


def test_an_unparseable_score_is_none_not_a_guess():
    assert parse_score(None) is None
    assert parse_score("") is None
    assert parse_score("live") is None


def test_fair_value_is_quoted_in_the_yes_frame_so_it_compares_to_the_book():
    """A leading first team must price above 0.5, matching a YES quote."""
    fv = fair_value(margin=+8, minutes_left=10.0, pregame_price=0.50)
    assert fv > 0.5


def test_the_gap_is_model_minus_market_in_one_frame():
    row = _row(fair_value=0.60, bid=0.40, ask=0.42)
    assert row.mid == pytest.approx(0.41)
    assert row.gap == pytest.approx(0.19)


def test_a_trailing_first_team_prices_below_a_leading_one_on_the_same_book():
    up = fair_value(margin=+5, minutes_left=20.0, pregame_price=0.50)
    down = fair_value(margin=-5, minutes_left=20.0, pregame_price=0.50)
    assert up + down == pytest.approx(1.0)
    assert down < 0.5 < up


def test_the_pregame_price_moves_the_fair_value_in_its_own_direction():
    """A favourite tied at the half must price above an underdog tied."""
    fav = fair_value(margin=0, minutes_left=20.0, pregame_price=0.80)
    dog = fair_value(margin=0, minutes_left=20.0, pregame_price=0.20)
    assert fav > 0.5 > dog


def test_no_pregame_price_yields_no_fair_value_rather_than_a_coin_flip():
    """A 50/50 prior on a mismatch is a wrong assumption, not a neutral one.

    This is the assumption that made hypothesis #16 look like a 6.8c edge.
    """
    assert fair_value(margin=-2, minutes_left=20.0, pregame_price=None) is None


# --------------------------------------------------------------------- #
# Interpolation edges
# --------------------------------------------------------------------- #


def test_period_start_is_exact_not_an_estimate():
    """The only instant the clock is known. win_curve.py measures here."""
    for period, expected in (("Q2", 30.0), ("Q3", 20.0), ("Q4", 10.0)):
        left, is_estimate, _ = minutes_remaining(period, seconds_into_period=0.0)
        assert left == pytest.approx(expected)
        assert is_estimate is False


def test_mid_period_is_interpolated_and_flagged_as_an_estimate():
    left, is_estimate, _ = minutes_remaining("Q1", seconds_into_period=300.0)
    assert left == pytest.approx(35.0)      # 5 of Q1's 10 minutes used
    assert is_estimate is True


def test_a_quarter_that_runs_long_is_clamped_not_allowed_to_go_negative():
    """Wall clock overruns game clock constantly — timeouts, fouls, reviews.

    Without the clamp this drives minutes_left negative and sqrt() raises.
    """
    clock = minutes_remaining("Q4", seconds_into_period=45 * 60.0)
    assert clock.minutes_left == 0.0


def test_an_exhausted_clock_is_marked_unusable_rather_than_zero_minutes():
    """The failure this exists to prevent: FV 1.000 on a three-point game.

    A WNBA quarter takes 15-20 wall-clock minutes, so the estimate saturates
    every game. At `minutes_left = 0` the formula stops being a probability
    and becomes a step function, printing certainty exactly where the estimate
    is least trustworthy.
    """
    clock = minutes_remaining("Q4", seconds_into_period=45 * 60.0)
    assert clock.usable is False
    assert "exhausted" in clock.note
    # And the step function it would have produced:
    assert fair_value(margin=3, minutes_left=0.0, pregame_price=0.5) == 1.0


def test_a_normal_in_period_estimate_stays_usable():
    clock = minutes_remaining("Q3", seconds_into_period=240.0)
    assert clock.usable is True
    assert clock.is_estimate is True


def test_overtime_is_unusable_so_no_number_is_shown_under_a_does_not_apply_note():
    assert minutes_remaining("OT", seconds_into_period=60.0).usable is False


def test_an_unknown_or_missing_period_is_unusable():
    assert minutes_remaining("Q7", seconds_into_period=0.0).usable is False
    assert minutes_remaining(None, seconds_into_period=0.0).usable is False


def test_halftime_stays_usable_because_its_clock_is_exact():
    assert minutes_remaining("HT", seconds_into_period=900.0).usable is True


def test_the_clock_still_unpacks_as_a_three_tuple():
    left, is_estimate, note = minutes_remaining("Q2", seconds_into_period=0.0)
    assert (left, is_estimate, note) == (30.0, False, None)


def test_halftime_is_exact_and_does_not_burn_clock():
    left, is_estimate, note = minutes_remaining("HT", seconds_into_period=900.0)
    assert left == pytest.approx(20.0)
    assert is_estimate is False
    assert note == "halftime"


def test_overtime_uses_the_ot_clock_and_says_the_model_does_not_apply():
    left, is_estimate, note = minutes_remaining("OT", seconds_into_period=0.0)
    assert left == pytest.approx(OT_MINUTES)
    assert is_estimate is True
    assert "overtime" in note.lower()


def test_overtime_never_produces_a_negative_or_regulation_length_clock():
    for secs in (0.0, 120.0, 300.0, 3600.0):
        left, _, _ = minutes_remaining("OT2", seconds_into_period=secs)
        assert 0.0 <= left <= OT_MINUTES


def test_a_final_game_has_no_time_left_and_a_step_function_value():
    left, is_estimate, note = minutes_remaining("FT", seconds_into_period=0.0)
    assert left == 0.0 and is_estimate is False and note == "final"
    assert fair_value(margin=-1, minutes_left=0.0, pregame_price=0.9) == 0.0


def test_an_unknown_period_falls_back_loudly_rather_than_silently():
    left, is_estimate, note = minutes_remaining("Q7", seconds_into_period=0.0)
    assert left == REGULATION_MINUTES
    assert is_estimate is True
    assert "unrecognised" in note


def test_a_missing_period_is_flagged_rather_than_assumed_to_be_q1():
    _, is_estimate, note = minutes_remaining(None, seconds_into_period=0.0)
    assert is_estimate is True
    assert "no period" in note


def test_negative_elapsed_time_cannot_add_minutes_to_the_clock():
    """Clock skew between writers must not manufacture extra game."""
    left, _, _ = minutes_remaining("Q2", seconds_into_period=-600.0)
    assert left == pytest.approx(30.0)


# --------------------------------------------------------------------- #
# Highlighting
# --------------------------------------------------------------------- #


def test_a_small_gap_is_not_highlighted():
    row = _row(fair_value=0.42, bid=0.40, ask=0.42)     # mid 0.41, gap 1c
    assert abs(row.gap) < GAP_HIGHLIGHT
    assert row.highlight is False


def test_a_large_gap_is_highlighted_in_both_directions():
    assert _row(fair_value=0.60, bid=0.40, ask=0.42).highlight is True
    assert _row(fair_value=0.20, bid=0.40, ask=0.42).highlight is True


def test_a_missing_quote_is_not_a_gap_of_zero():
    row = _row(bid=None, ask=None)
    assert row.mid is None and row.gap is None and row.highlight is False


def test_fair_value_stays_finite_across_the_whole_price_range():
    for price in (0.0, 0.01, 0.5, 0.99, 1.0):
        for minutes in (0.1, 10.0, 40.0):
            fv = fair_value(margin=0, minutes_left=minutes, pregame_price=price)
            assert fv is not None and math.isfinite(fv) and 0.0 <= fv <= 1.0
