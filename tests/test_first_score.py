"""First-score fade tests.

The weight is on the things that would silently turn a null into a finding:
a trade counted that never filled, a first score believed without ever seeing
0-0, an exit that forgot to pay the spread, and a verdict computed on rows
instead of games.
"""

from __future__ import annotations

import datetime as dt

import pytest

from core.pulse.first_score import (
    ENTRY_PATIENCE_MINUTES,
    GATE_MIN_GAMES,
    REACTION_SECONDS,
    FadeFirstScore,
    StudyResult,
    Trade,
    format_report,
)
from core.pulse.replay import Order, Tick, replay_game

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 8, 2, 19, 30, tzinfo=UTC)
GAME = "wnba-test-2026-08-02"


def _tick(sec: float, bid: float, ask: float, *, score: str = "0-0",
          slug: str = "m1", game: str = GAME) -> Tick:
    return Tick(
        captured_at=T0 + dt.timedelta(seconds=sec),
        event_slug=game, market_slug=slug,
        sports_market_type="basketball_team_full_game_total", line=170.5,
        bid=bid, ask=ask, is_live=True, score=score, period="Q1",
    )


def _run(ticks):
    strategy = FadeFirstScore()
    replay_game(ticks, strategy, event_slug=GAME)
    return strategy


# --------------------------------------------------------------------- #
# The signal
# --------------------------------------------------------------------- #


def test_an_up_lurch_is_faded_by_resting_an_offer():
    """Price jumps on the first basket -> we sell it, at the ask, as a maker."""
    ticks = [
        _tick(0, 0.48, 0.50),                      # 0-0 baseline, mid 0.49
        _tick(10, 0.58, 0.60, score="2-0"),        # first score
        _tick(10 + REACTION_SECONDS, 0.58, 0.60, score="2-0"),
    ]
    s = _run(ticks)
    assert len(s.trades) == 1
    trade = s.trades[0]
    assert trade.side == "sell"
    assert trade.order.limit_price == 0.60          # rested at the touch
    assert trade.lurch > 0


def test_a_down_lurch_is_faded_by_resting_a_bid():
    ticks = [
        _tick(0, 0.58, 0.60),
        _tick(10, 0.48, 0.50, score="0-2"),
        _tick(10 + REACTION_SECONDS, 0.48, 0.50, score="0-2"),
    ]
    s = _run(ticks)
    assert s.trades[0].side == "buy"
    assert s.trades[0].order.limit_price == 0.48


def test_nothing_fires_before_the_reaction_window_elapses():
    ticks = [
        _tick(0, 0.48, 0.50),
        _tick(10, 0.58, 0.60, score="2-0"),
        _tick(10 + REACTION_SECONDS - 1, 0.58, 0.60, score="2-0"),
    ]
    assert _run(ticks).trades == []


# --------------------------------------------------------------------- #
# The first score has to be *observed*
# --------------------------------------------------------------------- #


def test_a_game_already_in_progress_is_skipped_not_backfilled():
    """No 0-0 tick was ever seen, so there is no first score to trade.

    This is the failure that would otherwise be invisible: the recorder starts
    after tip-off, the earliest score we see is 21-24, and treating that as
    'the first score' would manufacture a signal out of a coverage gap.
    """
    ticks = [
        _tick(0, 0.48, 0.50, score="21-24"),
        _tick(10, 0.58, 0.60, score="23-24"),
        _tick(10 + REACTION_SECONDS, 0.58, 0.60, score="23-24"),
    ]
    s = _run(ticks)
    assert s.trades == []
    assert s.first_score_at is None
    assert s.skips["first_score_not_observed"] > 0


def test_a_scoreless_row_is_not_counted_as_a_missed_first_score():
    """A row with no score at all is not evidence about first-score coverage.

    It still carries a quote and must keep marking open trades, but counting it
    under `first_score_not_observed` inflated that reason by exactly the number
    of scoreless rows.
    """
    ticks = [
        Tick(captured_at=T0, event_slug=GAME, market_slug="m1",
             sports_market_type="total", line=170.5, bid=0.48, ask=0.50,
             is_live=False, score=None, period=None),
        Tick(captured_at=T0 + dt.timedelta(seconds=10), event_slug=GAME,
             market_slug="m1", sports_market_type="total", line=170.5,
             bid=0.48, ask=0.50, is_live=False, score=None, period=None),
    ]
    s = _run(ticks)
    assert s.skips["tick_without_a_parseable_score"] == 2
    assert s.skips.get("first_score_not_observed", 0) == 0


def test_a_fade_is_not_opened_long_after_the_first_score():
    """A rung that only becomes quotable in Q3 is not reacting to tip-off."""
    ticks = [
        _tick(0, 0.48, 0.50),
        _tick(10, 0.58, 0.60, score="2-0"),
        # First quotable tick after the score is 40 minutes later.
        _tick(10 + 2400, 0.58, 0.60, score="61-58"),
    ]
    s = _run(ticks)
    assert s.trades == []
    assert s.skips["first_quotable_tick_came_too_late_to_be_a_reaction"] > 0


def test_a_first_score_with_no_quotable_baseline_is_skipped():
    """0-0 was seen, but only at an untradable price. Not a baseline."""
    ticks = [
        _tick(0, 0.02, 0.30),                       # spread 0.28 > MAX_SPREAD
        _tick(10, 0.58, 0.60, score="2-0"),
        _tick(10 + REACTION_SECONDS, 0.58, 0.60, score="2-0"),
    ]
    s = _run(ticks)
    assert s.trades == []
    assert s.skips["no_quotable_baseline_before_first_score"] > 0


def test_a_first_score_that_moved_no_price_is_recorded_not_traded():
    ticks = [
        _tick(0, 0.48, 0.50),
        _tick(10, 0.48, 0.50, score="2-0"),
        _tick(10 + REACTION_SECONDS, 0.48, 0.50, score="2-0"),
    ]
    s = _run(ticks)
    assert s.trades == []
    assert s.skips["no_price_move_on_the_first_score"] > 0


# --------------------------------------------------------------------- #
# Fills are earned
# --------------------------------------------------------------------- #


def test_the_entry_does_not_fill_on_the_tick_that_placed_it():
    ticks = [
        _tick(0, 0.48, 0.50),
        _tick(10, 0.58, 0.60, score="2-0"),
        _tick(10 + REACTION_SECONDS, 0.58, 0.60, score="2-0"),
    ]
    s = _run(ticks)
    assert s.trades[0].order.filled_at is None


def test_the_offer_fills_only_when_the_bid_rises_to_it():
    ticks = [
        _tick(0, 0.48, 0.50),
        _tick(10, 0.58, 0.60, score="2-0"),
        _tick(40, 0.58, 0.60, score="2-0"),         # place: sell at 0.60
        _tick(50, 0.59, 0.61, score="2-0"),         # bid 0.59 < 0.60: no fill
        _tick(60, 0.60, 0.62, score="2-0"),         # bid 0.60 >= 0.60: fill
    ]
    s = _run(ticks)
    order = s.trades[0].order
    assert order.filled_at == T0 + dt.timedelta(seconds=60)
    assert order.fill_price == 0.60


def test_an_entry_that_never_fills_is_cancelled_and_is_not_a_trade():
    patience = ENTRY_PATIENCE_MINUTES * 60
    ticks = [
        _tick(0, 0.48, 0.50),
        _tick(10, 0.58, 0.60, score="2-0"),
        _tick(40, 0.58, 0.60, score="2-0"),                 # place
        _tick(40 + patience + 10, 0.50, 0.52, score="2-0"),  # patience blown
    ]
    s = _run(ticks)
    order = s.trades[0].order
    assert order.filled_at is None
    assert order.cancelled_at is not None
    assert s.trades[0].filled is False
    assert s.trades[0].pnl(5.0) is None


# --------------------------------------------------------------------- #
# The money
# --------------------------------------------------------------------- #


def _filled_trade(side: str, fill: float) -> Trade:
    order = Order(market_slug="m1", side=side, limit_price=fill, quantity=1.0,
                  placed_at=T0, filled_at=T0 + dt.timedelta(seconds=10),
                  fill_price=fill)
    return Trade(
        game_id=GAME, market_slug="m1", market_type="total",
        baseline_mid=0.49, baseline_age_seconds=10.0, signal_mid=0.59,
        signal_at=T0, side=side, order=order,
    )


def test_pnl_on_a_short_pays_the_exit_half_spread():
    trade = _filled_trade("sell", 0.60)
    trade.after_fill[5.0] = (0.50, 0.04)     # mid 0.50, spread 4c
    # sold at 0.60, mid back to 0.50 -> +0.10 gross, less 2c exit half-spread
    assert trade.pnl(5.0) == pytest.approx(0.08)


def test_pnl_on_a_long_pays_the_exit_half_spread():
    trade = _filled_trade("buy", 0.40)
    trade.after_fill[5.0] = (0.50, 0.04)
    assert trade.pnl(5.0) == pytest.approx(0.08)


def test_the_exit_charge_uses_the_spread_observed_at_exit_not_at_entry():
    """A blown-out spread at exit must cost more, not be averaged away."""
    tight = _filled_trade("sell", 0.60)
    tight.after_fill[5.0] = (0.50, 0.02)
    wide = _filled_trade("sell", 0.60)
    wide.after_fill[5.0] = (0.50, 0.20)
    assert wide.pnl(5.0) < tight.pnl(5.0)
    assert wide.pnl(5.0) == pytest.approx(0.10 - 0.10)


def test_a_losing_fade_is_reported_as_losing():
    trade = _filled_trade("sell", 0.60)
    trade.after_fill[5.0] = (0.70, 0.04)     # it kept going
    assert trade.pnl(5.0) < 0


def test_signal_reversion_is_recorded_even_without_a_fill():
    """The ungated diagnostic must survive the fill proxy discarding a trade."""
    patience = ENTRY_PATIENCE_MINUTES * 60
    ticks = [
        _tick(0, 0.48, 0.50),
        _tick(10, 0.58, 0.60, score="2-0"),
        _tick(40, 0.58, 0.60, score="2-0"),                 # place, signal mid 0.59
        _tick(40 + patience + 10, 0.48, 0.50, score="2-0"),  # cancelled
        _tick(40 + 300, 0.48, 0.50, score="2-0"),            # +5 min from signal
    ]
    s = _run(ticks)
    trade = s.trades[0]
    assert trade.filled is False
    # Lurched up, came back down 0.10 -> positive reversion.
    assert trade.signal_reversion(5.0) == 0.10000000000000003 or (
        abs(trade.signal_reversion(5.0) - 0.10) < 1e-9)


def test_the_horizon_mark_is_the_nearest_observation_not_the_first_in_band():
    """A +5 min mark must be near 5 minutes, not at the band's 2.5-min floor.

    The tolerance band is [0.5h, 2h]. Taking the first tick inside it would
    label a 2.5-minute observation "+5 min" and quietly report a horizon half
    the length of the one in the gate.
    """
    ticks = [
        _tick(0, 0.48, 0.50),
        _tick(10, 0.58, 0.60, score="2-0"),
        _tick(40, 0.58, 0.60, score="2-0"),          # place, signal at t=40s
        _tick(40 + 150, 0.55, 0.57, score="2-0"),    # +2.5 min: in band, far
        _tick(40 + 300, 0.40, 0.42, score="2-0"),    # +5.0 min: the target
        _tick(40 + 400, 0.30, 0.32, score="2-0"),    # +6.7 min: worse again
    ]
    s = _run(ticks)
    mid, _ = s.trades[0].after_signal[5.0]
    assert mid == pytest.approx(0.41)                # the +5.0 min tick


def test_signal_reversion_is_signed_so_positive_always_means_it_came_back():
    trade = _filled_trade("buy", 0.40)
    trade.signal_mid = 0.39
    trade.baseline_mid = 0.49                # lurched down
    trade.after_signal[5.0] = (0.44, 0.03)   # came back up
    assert trade.signal_reversion(5.0) > 0


# --------------------------------------------------------------------- #
# The verdict counts games, not rows
# --------------------------------------------------------------------- #


def _verdict(report: str) -> str:
    """Just the verdict block.

    The gate is also *quoted* near the top of every report, so asserting on the
    whole string would match the word PASS in the pre-registration text and
    pass a test that should fail.
    """
    tail = report.split("VERDICT")[-1]
    # Stop at the standing caveats, which also name both outcomes.
    return tail.split("Fill-rule caveat")[0]


def test_no_signals_reports_no_data_rather_than_a_null_result():
    report = format_report(
        StudyResult(trades=[], n_games_replayed=6, n_games_with_first_score=0,
                    skips={"first_score_not_observed": 900}, ticks=5000,
                    sampling=None)
    )
    assert "VERDICT: NO DATA" in report
    assert "never" in report and "tested" in report
    assert "coverage" in report


def test_many_trades_in_few_games_is_still_no_data():
    """40 filled trades across 2 games must not become a verdict."""
    trades = []
    for i in range(40):
        t = _filled_trade("sell", 0.60)
        t.game_id = f"game-{i % 2}"
        t.after_fill[5.0] = (0.50, 0.04)       # every one a winner
        trades.append(t)
    report = format_report(
        StudyResult(trades=trades, n_games_replayed=2,
                    n_games_with_first_score=2, skips={}, ticks=10_000,
                    sampling=None)
    )
    assert "NO DATA" in _verdict(report)
    assert f"{GATE_MIN_GAMES - 2} more games" in report
    assert "PASS" not in _verdict(report)


def test_a_clean_win_across_enough_games_passes():
    trades = []
    for i in range(40):
        t = _filled_trade("sell", 0.60)
        t.game_id = f"game-{i % 12}"
        t.after_fill[5.0] = (0.50, 0.04)
        trades.append(t)
    report = format_report(
        StudyResult(trades=trades, n_games_replayed=12,
                    n_games_with_first_score=12, skips={}, ticks=10_000,
                    sampling=None)
    )
    assert "PASS" in _verdict(report)


def test_a_clean_loss_across_enough_games_fails():
    trades = []
    for i in range(40):
        t = _filled_trade("sell", 0.60)
        t.game_id = f"game-{i % 12}"
        t.after_fill[5.0] = (0.70, 0.04)
        trades.append(t)
    report = format_report(
        StudyResult(trades=trades, n_games_replayed=12,
                    n_games_with_first_score=12, skips={}, ticks=10_000,
                    sampling=None)
    )
    assert "FAIL" in _verdict(report)


# --------------------------------------------------------------------- #
# State does not leak between games
# --------------------------------------------------------------------- #


def test_each_market_is_tracked_independently():
    ticks = sorted(
        [
            _tick(0, 0.48, 0.50, slug="m1"),
            _tick(0, 0.30, 0.32, slug="m2"),
            _tick(10, 0.58, 0.60, score="2-0", slug="m1"),
            _tick(10, 0.25, 0.27, score="2-0", slug="m2"),
            _tick(40, 0.58, 0.60, score="2-0", slug="m1"),
            _tick(40, 0.25, 0.27, score="2-0", slug="m2"),
        ],
        key=lambda t: (t.captured_at, t.market_slug),
    )
    s = _run(ticks)
    assert {t.market_slug for t in s.trades} == {"m1", "m2"}
    sides = {t.market_slug: t.side for t in s.trades}
    assert sides["m1"] == "sell"      # lurched up
    assert sides["m2"] == "buy"       # lurched down
