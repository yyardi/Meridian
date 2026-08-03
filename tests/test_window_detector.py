"""News-window detector tests.

The detector's job is to be *believable when it fires*. Most of these tests are
about refusing to fire: a detector that manufactures windows out of sampling
gaps would send us hunting an edge that was never there.
"""

from __future__ import annotations

import datetime as dt

import pytest

from core.window_detector import (
    GATE_MIN_WINDOWS,
    BookMove,
    PMReading,
    WindowObservation,
    attach_pm_readings,
    detect_moves,
    format_report,
)

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 8, 1, 18, 0, tzinfo=UTC)


def _at(minutes: float) -> dt.datetime:
    return T0 + dt.timedelta(minutes=minutes)


# ------------------------------------------------------------------ #
# Trigger detection
# ------------------------------------------------------------------ #


def test_a_big_move_between_adjacent_polls_triggers():
    moves = detect_moves({"g1": [(_at(0), 170.0), (_at(20), 172.0)]})
    assert len(moves) == 1
    assert moves[0].delta == pytest.approx(2.0)
    assert moves[0].minutes == pytest.approx(20.0)


def test_ordinary_drift_does_not_trigger():
    """Same-provider pregame drift averages 0.3-0.6 points."""
    assert detect_moves({"g1": [(_at(0), 170.0), (_at(20), 170.5)]}) == []


def test_downward_moves_trigger_too():
    moves = detect_moves({"g1": [(_at(0), 170.0), (_at(20), 168.0)]})
    assert len(moves) == 1
    assert moves[0].delta == pytest.approx(-2.0)


def test_a_move_across_a_sampling_hole_is_not_an_event():
    """Six hours apart is two observations, not a reaction to news.

    Without this guard every overnight gap would register as a window and the
    detector would report edges it never observed.
    """
    assert detect_moves({"g1": [(_at(0), 170.0), (_at(360), 176.0)]}) == []


def test_the_gap_guard_boundary_is_respected():
    inside = detect_moves({"g1": [(_at(0), 170.0), (_at(44), 172.0)]})
    outside = detect_moves({"g1": [(_at(0), 170.0), (_at(46), 172.0)]})
    assert len(inside) == 1
    assert outside == []


def test_moves_are_detected_per_game_not_across_games():
    """Two different games at different numbers must not look like a move."""
    series = {"g1": [(_at(0), 150.0)], "g2": [(_at(10), 190.0)]}
    assert detect_moves(series) == []


def test_unsorted_input_is_ordered_before_differencing():
    moves = detect_moves({"g1": [(_at(20), 172.0), (_at(0), 170.0)]})
    assert len(moves) == 1
    assert moves[0].from_line == pytest.approx(170.0)


# ------------------------------------------------------------------ #
# Response measurement
# ------------------------------------------------------------------ #


def _obs(stale_points: float, sigma: float = 19.0, lag: float = 10.0) -> WindowObservation:
    move = BookMove(
        espn_game_id="g1", from_at=_at(0), to_at=_at(20),
        from_line=170.0, to_line=173.0,
    )
    reading = PMReading(
        captured_at=_at(20 + lag),
        implied_mean=move.to_line + stale_points,
        implied_stdev=sigma,
    )
    return WindowObservation(move=move, after=[reading])


def test_staleness_is_measured_against_the_new_book_number():
    """PM still showing the OLD line is the tradable state."""
    o = _obs(stale_points=-3.0)     # PM sits 3 pts below the new line
    assert o.staleness_points == pytest.approx(-3.0)
    assert o.lag_minutes == pytest.approx(10.0)


def test_a_venue_that_repriced_leaves_no_edge():
    o = _obs(stale_points=0.0)
    assert o.edge_probability() == pytest.approx(0.0, abs=1e-9)
    assert not o.is_tradable()


def test_a_stale_venue_leaves_an_edge():
    o = _obs(stale_points=-3.0)
    edge = o.edge_probability()
    assert edge is not None and edge > 0.05
    assert o.is_tradable()


def test_fees_are_subtracted_from_the_edge():
    """A gap that does not survive costs is not an opportunity."""
    o = _obs(stale_points=-1.0)
    gross = o.edge_probability(fee=0.0)
    net = o.edge_probability(fee=0.05)
    assert net == pytest.approx(gross - 0.05)
    assert not o.is_tradable(fee=0.05)


def test_edge_scales_with_the_scoring_environment():
    """The same stale points are worth less when games are noisier."""
    tight = _obs(stale_points=-3.0, sigma=14.0).edge_probability()
    loose = _obs(stale_points=-3.0, sigma=24.0).edge_probability()
    assert tight > loose


def test_no_pm_reading_after_the_move_yields_nothing():
    move = BookMove("g1", _at(0), _at(20), 170.0, 173.0)
    o = WindowObservation(move=move)
    assert o.staleness_points is None
    assert o.edge_probability() is None
    assert not o.is_tradable()


def test_readings_outside_the_horizon_are_ignored():
    move = BookMove("g1", _at(0), _at(20), 170.0, 173.0)
    far = PMReading(captured_at=_at(20 + 200), implied_mean=170.0, implied_stdev=19.0)
    (obs,) = attach_pm_readings([move], {"g1": [far]}, horizon_minutes=90.0)
    assert obs.after == []


def test_the_reading_before_the_move_is_the_latest_prior_one():
    move = BookMove("g1", _at(0), _at(20), 170.0, 173.0)
    readings = [
        PMReading(_at(-60), 168.0, 19.0),
        PMReading(_at(-5), 170.0, 19.0),
        PMReading(_at(30), 173.0, 19.0),
    ]
    (obs,) = attach_pm_readings([move], {"g1": readings})
    assert obs.before is not None
    assert obs.before.implied_mean == pytest.approx(170.0)
    assert len(obs.after) == 1


# ------------------------------------------------------------------ #
# Reporting honesty
# ------------------------------------------------------------------ #


def test_zero_triggers_reports_no_data_not_a_null_result():
    """The distinction the whole experiment turns on."""
    text = format_report([], trigger_points=1.5, book_pairs=61)
    assert "NO DATA" in text
    assert "Not a null result" in text


def test_a_thin_sample_is_inconclusive_not_a_pass():
    observations = [_obs(stale_points=-4.0) for _ in range(3)]
    text = format_report(observations, trigger_points=1.5, book_pairs=100)
    assert "INCONCLUSIVE" in text
    assert str(GATE_MIN_WINDOWS) in text


def test_the_report_always_states_the_cadence_caveat():
    """A null here cannot distinguish a fast venue from a slow camera."""
    text = format_report(
        [_obs(stale_points=-4.0)], trigger_points=1.5, book_pairs=100
    )
    assert "Cadence caveat" in text
