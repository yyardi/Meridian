"""Run-overreaction event study: triggers, non-overlap, reversion sign, gates.

Two tests carry most of the weight:

* `test_runs_do_not_overlap` — overlapping windows share a price path, so
  counting them separately inflates n against a gate stated in independent
  observations.
* `test_reversion_is_signed_toward_profit` — the sign convention is the whole
  measurement. Get it backwards and a market that trends reads as a market
  that reverts.
"""

from __future__ import annotations

import datetime as dt

import pytest

from core.pulse.overreaction import (
    GATE_MIN_GAMES,
    GATE_MIN_RUNS,
    ROUND_TRIP_COST,
    Run,
    Tick,
    detect_runs,
    format_report,
    parse_score,
    unanswered_run,
)

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 8, 2, 1, 0, tzinfo=UTC)


def _t(seconds: float, mid: float, score: str | None = None, *,
       game: str = "g1", slug: str = "m1", spread: float = 0.02) -> Tick:
    return Tick(
        game_id=game,
        market_slug=slug,
        captured_at=T0 + dt.timedelta(seconds=seconds),
        mid=mid,
        spread=spread,
        score=score,
        period="Q3",
    )


# ------------------------------------------------------------------ #
# Score parsing
# ------------------------------------------------------------------ #


def test_parse_score():
    assert parse_score("46-34") == (46, 34)
    assert parse_score(" 100 - 98 ") == (100, 98)
    assert parse_score(None) is None
    assert parse_score("") is None
    assert parse_score("Q3") is None
    assert parse_score("46-34-12") is None


def test_unanswered_run_requires_one_side_to_score_nothing():
    assert unanswered_run((40, 30), (48, 30)) == (8, 8)
    assert unanswered_run((40, 30), (40, 38)) == (-8, 8)
    # Both scored: trading baskets, not a run.
    assert unanswered_run((40, 30), (48, 32)) is None
    # No change.
    assert unanswered_run((40, 30), (40, 30)) is None


def test_score_going_backwards_is_a_correction_not_a_run():
    """Venues do revise scores. A revision must not read as a 10-0 run."""
    assert unanswered_run((40, 30), (30, 30)) is None


# ------------------------------------------------------------------ #
# Detection
# ------------------------------------------------------------------ #


def test_score_trigger_fires_on_an_unanswered_run():
    ticks = [
        _t(0, 0.50, "40-30"),
        _t(30, 0.58, "48-30"),          # 8-0 run
        _t(330, 0.54, "50-34"),         # +5 min
    ]
    runs = detect_runs({"m1": ticks}, run_points=8, price_move=1.01)
    assert len(runs) == 1
    assert runs[0].trigger == "score"
    assert runs[0].mid_end == pytest.approx(0.58)


def test_price_trigger_fires_without_a_score_feed():
    """The score feed can smooth a run away; the price reaction cannot hide."""
    ticks = [_t(0, 0.50), _t(60, 0.62), _t(360, 0.55)]
    runs = detect_runs({"m1": ticks}, run_points=99, price_move=0.10)
    assert len(runs) == 1
    assert runs[0].trigger == "price"


def test_a_slow_drift_is_not_a_run():
    """10c over an hour is not a run, however large the total move."""
    ticks = [_t(600 * i, 0.30 + 0.02 * i) for i in range(8)]
    assert detect_runs({"m1": ticks}, run_points=99, price_move=0.10) == []


def test_untradable_rungs_never_trigger():
    """A 22c-spread rung's 'move' is quote noise, not a run."""
    ticks = [_t(0, 0.50, spread=0.25), _t(60, 0.65, spread=0.25)]
    assert detect_runs({"m1": ticks}, run_points=99, price_move=0.10) == []

    deep = [_t(0, 0.95), _t(60, 0.80)]
    assert detect_runs({"m1": deep}, run_points=99, price_move=0.10) == []


def test_runs_do_not_overlap():
    """Overlapping windows share a price path and would inflate n."""
    ticks = [_t(30 * i, 0.50 + 0.12 * (i % 2)) for i in range(40)]
    runs = detect_runs({"m1": ticks}, run_points=99, price_move=0.10)

    horizon = dt.timedelta(minutes=10)
    for a, b in zip(runs, runs[1:]):
        assert b.started_at >= a.ended_at + horizon, (
            "a run started inside the previous run's horizon"
        )


# ------------------------------------------------------------------ #
# The sign convention
# ------------------------------------------------------------------ #


def test_reversion_is_signed_toward_profit():
    """Positive always means 'it came back', whichever way the run went."""
    up = Run(
        game_id="g1", market_slug="m1", trigger="price",
        started_at=T0, ended_at=T0 + dt.timedelta(minutes=1),
        mid_start=0.50, mid_end=0.62, after={5.0: 0.56},
    )
    # Ran up to 0.62, fell back to 0.56: 6c of reversion.
    assert up.reversion(5.0) == pytest.approx(0.06)

    down = Run(
        game_id="g1", market_slug="m1", trigger="price",
        started_at=T0, ended_at=T0 + dt.timedelta(minutes=1),
        mid_start=0.50, mid_end=0.38, after={5.0: 0.44},
    )
    # Ran down to 0.38, came back up to 0.44: also 6c of reversion.
    assert down.reversion(5.0) == pytest.approx(0.06)


def test_continuation_is_negative_reversion():
    run = Run(
        game_id="g1", market_slug="m1", trigger="price",
        started_at=T0, ended_at=T0 + dt.timedelta(minutes=1),
        mid_start=0.50, mid_end=0.62, after={5.0: 0.70},
    )
    assert run.reversion(5.0) == pytest.approx(-0.08)


def test_unobserved_horizon_is_none_not_zero():
    """A missing mark must not be averaged in as 'no reversion'."""
    run = Run(
        game_id="g1", market_slug="m1", trigger="price",
        started_at=T0, ended_at=T0, mid_start=0.5, mid_end=0.6, after={},
    )
    assert run.reversion(5.0) is None


# ------------------------------------------------------------------ #
# Verdicts
# ------------------------------------------------------------------ #


def _runs(n: int, games: int, reversion: float) -> list[Run]:
    out = []
    for i in range(n):
        out.append(
            Run(
                game_id=f"g{i % games}", market_slug=f"m{i}", trigger="price",
                started_at=T0, ended_at=T0,
                mid_start=0.50, mid_end=0.62,
                after={h: 0.62 - reversion for h in (2.0, 5.0, 10.0)},
            )
        )
    return out


def test_zero_runs_reports_no_data_not_a_null():
    report = format_report(
        [], run_points=8, price_move=0.10, ticks_examined=5000, score_changes=800
    )
    assert "NO DATA" in report
    assert "Not a null result" in report


def test_a_dead_score_feed_is_called_out_separately():
    """Zero score changes and zero runs have different remedies."""
    report = format_report(
        [], run_points=8, price_move=0.10, ticks_examined=5000, score_changes=0
    )
    assert "data-coverage problem" in report


def test_real_but_uneconomic_reversion_reports_fail():
    """The bar is the round trip, not zero. This project has been burned by
    edges that were real and smaller than their costs."""
    runs = _runs(GATE_MIN_RUNS + 20, GATE_MIN_GAMES + 2, reversion=ROUND_TRIP_COST / 2)
    report = format_report(
        runs, run_points=8, price_move=0.10, ticks_examined=9000, score_changes=900
    )
    assert "FAIL" in report
    assert "losing trade" in report


def test_reversion_clearing_the_round_trip_reports_pass():
    runs = _runs(GATE_MIN_RUNS + 20, GATE_MIN_GAMES + 2, reversion=ROUND_TRIP_COST * 3)
    report = format_report(
        runs, run_points=8, price_move=0.10, ticks_examined=9000, score_changes=900
    )
    assert "PASS —" in report


def test_enough_runs_but_too_few_games_is_no_data():
    """Sample size is games, not rows."""
    runs = _runs(GATE_MIN_RUNS + 100, 3, reversion=ROUND_TRIP_COST * 3)
    report = format_report(
        runs, run_points=8, price_move=0.10, ticks_examined=9000, score_changes=900
    )
    assert "NO DATA" in report
    assert "PASS —" not in report
