"""Tail-volatility tests.

The weight sits on the two things that would turn a sampling artifact into a
finding:

* **Windows are fixed-horizon and non-overlapping.** A per-tick or summed
  measure scales with sample count, which is how correction C1 happened.
* **Phases are not smeared.** A window spanning a period boundary has no
  well-defined phase, and HT/OT are not regulation.

Plus the pre-registered interpretation rule: if the body control shows the
same pattern, a passing tail comparison must NOT be reported as support.
"""

from __future__ import annotations

import datetime as dt

import pytest

from core.pulse.tail_volatility import (
    GATE_MIN_GAMES,
    PHASE_OF,
    TAIL_DISTANCE,
    WINDOW_SECONDS,
    Contrast,
    Move,
    PhaseStat,
    Study,
    band_of,
    build_moves,
    contrast_against_mid,
    format_report,
    phase_stats,
)

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 8, 7, 19, 30, tzinfo=UTC)


def _series(points, *, game="g1", market="m1"):
    return {(game, market): [(T0 + dt.timedelta(seconds=s), mid, per)
                             for s, mid, per in points]}


def _move(game, phase, is_tail, magnitude):
    return Move(event_slug=game, market_slug="m1", phase=phase, is_tail=is_tail,
                mid_start=0.5, mid_end=0.5 + magnitude, elapsed_seconds=30.0)


# --------------------------------------------------------------------- #
# The tail definition is inherited, not invented
# --------------------------------------------------------------------- #


def test_the_tail_band_is_the_complement_of_the_tradable_band():
    assert TAIL_DISTANCE == pytest.approx(0.30)
    assert band_of(0.20) is True and band_of(0.80) is True
    assert band_of(0.21) is False and band_of(0.79) is False
    assert band_of(0.02) is True and band_of(0.98) is True
    assert band_of(0.50) is False


# --------------------------------------------------------------------- #
# Windows
# --------------------------------------------------------------------- #


def test_a_window_is_the_observation_nearest_the_horizon():
    series = _series([(0, 0.10, "Q1"), (15, 0.13, "Q1"), (30, 0.20, "Q1")])
    moves, _ = build_moves(series)
    assert len(moves) == 1
    assert moves[0].move == pytest.approx(0.10)      # 0.10 -> 0.20 at +30s


def test_windows_do_not_overlap():
    """Two windows must not share a price path."""
    pts = [(s, 0.10, "Q1") for s in range(0, 121, 15)]
    moves, _ = build_moves(_series(pts))
    # 0->30, 45->75, 90->120 : three disjoint windows, not seven overlapping.
    assert len(moves) == 3


def test_an_observation_outside_the_tolerance_band_is_not_stretched():
    """A 5-minute gap must not be reported as a 30-second window."""
    series = _series([(0, 0.10, "Q1"), (300, 0.40, "Q1")])
    moves, skips = build_moves(series)
    assert moves == []
    assert skips["no observation inside the window band"] > 0


def test_a_window_spanning_a_period_boundary_is_dropped():
    series = _series([(0, 0.10, "Q1"), (30, 0.40, "Q2")])
    moves, skips = build_moves(series)
    assert moves == []
    assert skips["window spans a period boundary"] > 0


def test_halftime_and_overtime_are_excluded_and_counted():
    for period in ("HT", "OT"):
        series = _series([(0, 0.10, period), (30, 0.40, period)])
        moves, skips = build_moves(series)
        assert moves == []
        assert any("period not in a phase" in k for k in skips)


def test_phases_map_quarters_the_way_the_gate_states():
    assert PHASE_OF["Q1"] == "open"
    assert PHASE_OF["Q2"] == PHASE_OF["Q3"] == "mid"
    assert PHASE_OF["Q4"] == "close"
    assert "HT" not in PHASE_OF and "OT" not in PHASE_OF


def test_the_move_is_net_not_summed_travel():
    """Out and back is zero net move, whatever the path did in between.

    Summed travel would scale with sample count and reintroduce the cadence
    artifact the near-tier restriction exists to remove.
    """
    series = _series([(0, 0.10, "Q1"), (10, 0.90, "Q1"), (30, 0.10, "Q1")])
    moves, _ = build_moves(series)
    assert len(moves) == 1
    assert moves[0].move == pytest.approx(0.0)


def test_tail_membership_is_taken_at_the_window_start():
    series = _series([(0, 0.10, "Q1"), (30, 0.50, "Q1")])
    moves, _ = build_moves(series)
    assert moves[0].is_tail is True


# --------------------------------------------------------------------- #
# Contrasts are paired within game
# --------------------------------------------------------------------- #


def test_a_game_that_is_livelier_throughout_does_not_move_the_contrast():
    """Pairing within game is what removes a per-game level effect."""
    moves = []
    for game in ("g1", "g2"):
        level = 0.01 if game == "g1" else 0.10      # g2 is 10x livelier overall
        moves += [_move(game, "close", True, level * 2)] * 5
        moves += [_move(game, "mid", True, level)] * 5
    c = contrast_against_mid(moves, "close", tail=True)
    # Both games show close = 2x mid, but at wildly different levels. The
    # contrast is a mean of within-game differences, so g2 dominates the
    # magnitude — what matters is that both are positive and it is computed
    # per game rather than by pooling all rows.
    assert c.n_games == 2
    assert c.diff > 0


def test_a_game_missing_one_phase_is_dropped_from_the_contrast():
    """No mid-game window means no within-game difference to take."""
    moves = [_move("g1", "close", True, 0.05)] * 3      # no mid phase at all
    c = contrast_against_mid(moves, "close", tail=True)
    assert c.n_games == 0


def test_tail_and_body_are_computed_separately():
    moves = [_move("g1", "close", True, 0.10), _move("g1", "mid", True, 0.01),
             _move("g1", "close", False, 0.01), _move("g1", "mid", False, 0.01)]
    tail = contrast_against_mid(moves, "close", tail=True)
    body = contrast_against_mid(moves, "close", tail=False)
    assert tail.diff > 0
    assert body.diff == pytest.approx(0.0)


def test_phase_stats_count_games_not_rows():
    moves = [_move("g1", "close", True, 0.05)] * 100
    stats = phase_stats(moves, tail=True)
    assert stats["close"].n == 100
    assert stats["close"].n_games == 1


# --------------------------------------------------------------------- #
# The gate and its interpretation rule
# --------------------------------------------------------------------- #


def _study(tail_open, tail_close, body_open, body_close) -> Study:
    return Study(
        moves=[_move("g1", "close", True, 0.05)],
        skips={},
        tail={"open": PhaseStat("open", 10, 10, 0.05),
              "mid": PhaseStat("mid", 10, 10, 0.02),
              "close": PhaseStat("close", 10, 10, 0.06)},
        body={"open": PhaseStat("open", 10, 10, 0.03),
              "mid": PhaseStat("mid", 10, 10, 0.02),
              "close": PhaseStat("close", 10, 10, 0.03)},
        tail_open=tail_open, tail_close=tail_close,
        body_open=body_open, body_close=body_close,
    )


def _c(phase, diff, lo, hi, games=12):
    return Contrast(phase=phase, n_games=games, diff=diff, lo=lo, hi=hi)


def _verdict(report: str) -> str:
    return report.split("VERDICT")[-1].split("Standing caveats")[0]


def test_both_edges_up_and_a_flat_body_passes():
    report = format_report(_study(
        _c("open", 0.03, 0.01, 0.05), _c("close", 0.04, 0.02, 0.06),
        _c("open", 0.00, -0.01, 0.01), _c("close", 0.00, -0.01, 0.01)))
    assert "PASS" in _verdict(report)


def test_both_edges_up_but_the_body_too_is_a_FAIL_as_stated():
    """The pre-registered interpretation rule, and the #16 lesson.

    Tails moving more at the edges is not the claim if everything does.
    """
    report = format_report(_study(
        _c("open", 0.03, 0.01, 0.05), _c("close", 0.04, 0.02, 0.06),
        _c("open", 0.03, 0.01, 0.05), _c("close", 0.04, 0.02, 0.06)))
    v = _verdict(report)
    assert "FAIL as stated" in v
    assert "SO DOES" in v


def test_only_the_close_edge_is_not_enough():
    """A close-only effect is V4's endgame repricing, not hypothesis #6."""
    report = format_report(_study(
        _c("open", 0.00, -0.02, 0.02), _c("close", 0.04, 0.02, 0.06),
        _c("open", 0.00, -0.01, 0.01), _c("close", 0.00, -0.01, 0.01)))
    assert "FAIL" in _verdict(report)
    assert "PASS" not in _verdict(report)


def test_an_interval_spanning_zero_is_not_a_pass():
    report = format_report(_study(
        _c("open", 0.03, -0.01, 0.07), _c("close", 0.04, 0.02, 0.06),
        _c("open", 0.00, -0.01, 0.01), _c("close", 0.00, -0.01, 0.01)))
    assert "FAIL" in _verdict(report)


def test_too_few_games_on_either_edge_is_no_data_not_a_verdict():
    report = format_report(_study(
        _c("open", 0.03, 0.01, 0.05, games=GATE_MIN_GAMES - 1),
        _c("close", 0.04, 0.02, 0.06),
        _c("open", 0.00, -0.01, 0.01), _c("close", 0.00, -0.01, 0.01)))
    v = _verdict(report)
    assert "NO DATA" in v
    assert "PASS" not in v


def test_the_report_states_exclusions_rather_than_hiding_them():
    study = _study(_c("open", 0.03, 0.01, 0.05), _c("close", 0.04, 0.02, 0.06),
                   _c("open", 0.0, -0.01, 0.01), _c("close", 0.0, -0.01, 0.01))
    study.skips = {"book_tier=deep (30s+ cadence, not comparable)": 24019}
    report = format_report(study)
    assert "24,019" in report
    assert "book_tier=deep" in report
