"""Backtest engine tests.

The lookahead test is the most important test in the repository — a backtest
that reads the future does not crash, it just reports a fictional edge.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import delete

from core.backtest.engine import (
    MAX_PLAUSIBLE_LINE_MOVE,
    BacktestConfig,
    _is_live_provider,
    run_backtest,
)
from core.backtest.fills import (
    THETA_MAKER,
    THETA_MAKER_REBATE,
    THETA_TAKER,
    FillModel,
    american_to_price,
    fee_per_contract,
    pnl_for_contract,
    simulate_fill,
)
from core.backtest.metrics import BacktestMetrics, build_calibration, sample_size_verdict
from core.storage import SportsbookOdds, TeamGameLog, get_engine, get_sessionmaker
from strategies.wnba_totals.config import WNBATotalsConfig

UTC = dt.timezone.utc


# ------------------------------------------------------------------ #
# Fees
# ------------------------------------------------------------------ #

def test_fee_formula_matches_the_schedule():
    """fee = theta * price * (1 - price), per contract."""
    assert fee_per_contract(0.50, is_maker=False) == pytest.approx(THETA_TAKER * 0.25)
    assert fee_per_contract(0.50, is_maker=True) == pytest.approx(THETA_MAKER * 0.25)


def test_maker_default_is_zero_no_rebate_booked():
    """The advertised rebate is unverified (findings C7): default maker fee is 0."""
    assert THETA_MAKER == 0.0
    taker = fee_per_contract(0.50, is_maker=False)
    maker = fee_per_contract(0.50, is_maker=True)
    assert taker > 0         # a cost
    assert maker == 0.0      # no fee, and no rebate booked


def test_rebate_sensitivity_arm_is_explicit_and_off_by_default():
    """assume_rebate=True books the old -0.0125 coefficient; nothing else does."""
    arm = fee_per_contract(0.50, is_maker=True, assume_rebate=True)
    assert arm == pytest.approx(THETA_MAKER_REBATE * 0.25)
    assert arm < 0
    # The arm must not leak into taker fees.
    assert fee_per_contract(0.50, is_maker=False, assume_rebate=True) == pytest.approx(
        THETA_TAKER * 0.25
    )


def test_fees_vanish_at_the_extremes():
    """p(1-p) is maximised at 0.50 and ~0 at the wings."""
    assert fee_per_contract(0.99, is_maker=False) < fee_per_contract(0.50, is_maker=False) / 10


def test_american_to_price():
    assert american_to_price(-110) == pytest.approx(110 / 210)
    assert american_to_price(+150) == pytest.approx(100 / 250)


def test_pnl_per_contract():
    assert pnl_for_contract(0.40, won=True) == pytest.approx(0.60)
    assert pnl_for_contract(0.40, won=False) == pytest.approx(-0.40)


# ------------------------------------------------------------------ #
# Fill models
# ------------------------------------------------------------------ #

def test_optimistic_always_fills_pessimistic_pays_taker():
    opt = simulate_fill(quoted_price=0.5, contracts=10, model=FillModel.OPTIMISTIC, rng_value=0.99)
    pes = simulate_fill(quoted_price=0.5, contracts=10, model=FillModel.PESSIMISTIC, rng_value=0.99)
    assert opt.filled and opt.is_maker and opt.fee == 0.0   # no rebate booked
    assert pes.filled and not pes.is_maker and pes.fee > 0  # fee


def test_rebate_arm_threads_through_simulate_fill():
    fill = simulate_fill(quoted_price=0.5, contracts=10, model=FillModel.OPTIMISTIC,
                         rng_value=0.99, assume_rebate=True)
    assert fill.fee < 0  # the sensitivity arm, asked for explicitly


def test_realistic_can_miss_a_fill():
    """Resting orders do not always fill."""
    missed = simulate_fill(quoted_price=0.5, contracts=10, model=FillModel.REALISTIC, rng_value=0.99)
    hit = simulate_fill(quoted_price=0.5, contracts=10, model=FillModel.REALISTIC, rng_value=0.01)
    assert missed.filled is False and hit.filled is True


def test_adverse_selection_worsens_the_price():
    hit = simulate_fill(quoted_price=0.5, contracts=10, model=FillModel.REALISTIC, rng_value=0.0)
    assert hit.price > 0.5


# ------------------------------------------------------------------ #
# Data hygiene — the bugs that produced a fake edge
# ------------------------------------------------------------------ #

def test_live_odds_providers_are_excluded():
    """In-game lines reflect the score so far — including them is lookahead.

    `ESPN Bet - Live Odds` carries 502 'open' values and zero closes; feeding
    those in as entry prices manufactured a +4.2% ROI that was pure lookahead.
    """
    assert _is_live_provider("ESPN Bet - Live Odds")
    assert _is_live_provider("Caesars (New Jersey) - Live Odds")
    assert not _is_live_provider("ESPN BET")
    assert not _is_live_provider("DraftKings")


def test_implausible_line_moves_are_rejected():
    """Real same-provider WNBA moves average ~0.3-0.6 points.

    A 15-point 'move' is mismatched data (provider A's open vs provider B's
    close), not a market event.
    """
    assert MAX_PLAUSIBLE_LINE_MOVE <= 10.0


# ------------------------------------------------------------------ #
# Metrics
# ------------------------------------------------------------------ #

def test_max_drawdown():
    m = BacktestMetrics()
    m.equity_curve = [100, 120, 90, 110]
    assert m.max_drawdown == pytest.approx(0.25)   # 120 -> 90


def test_calibration_buckets():
    pairs = [(0.15, 0), (0.15, 0), (0.85, 1), (0.85, 1), (0.85, 0)]
    buckets = build_calibration(pairs, buckets=10)
    low = next(b for b in buckets if b.lower == 0.1)
    high = next(b for b in buckets if b.lower == 0.8)
    assert low.n == 2 and low.realised == 0.0
    assert high.n == 3 and high.realised == pytest.approx(2 / 3)


def test_sample_size_verdict_is_blunt_about_small_n():
    assert "too small" in sample_size_verdict(40)
    assert "noise" in sample_size_verdict(120)
    assert sample_size_verdict(0).startswith("No bets")


# ------------------------------------------------------------------ #
# Engine: lookahead, determinism, config isolation
# ------------------------------------------------------------------ #

SEASON = 1998   # fictional, cannot collide with real data


@pytest.fixture
def seeded_session():
    Session = get_sessionmaker(get_engine())
    with Session() as s:
        s.execute(delete(SportsbookOdds).where(SportsbookOdds.espn_game_id.like("bt-%")))
        s.execute(delete(TeamGameLog).where(TeamGameLog.season == SEASON))
        s.commit()

        for i in range(30):
            gid = f"bt-{i}"
            day = dt.datetime(SEASON, 6, 1, tzinfo=UTC) + dt.timedelta(days=i)
            for team, opp, home, scored, allowed in (
                ("BT_H", "BT_A", True, 85, 80),
                ("BT_A", "BT_H", False, 80, 85),
            ):
                s.add(TeamGameLog(
                    game_date=day, season=SEASON, espn_game_id=gid,
                    team_id=team, team_abbrev=team, opponent_id=opp, opponent_abbrev=opp,
                    is_home=home, points_scored=scored, points_allowed=allowed,
                    is_completed=True, season_type=2,
                ))
            s.add(SportsbookOdds(
                espn_game_id=gid, game_date=day, provider_name="TestBook",
                captured_at=day, over_under=150.0, open_total=150.0,
                close_total=151.0, is_closing_line=True,
            ))
        s.commit()
        yield s
        s.execute(delete(SportsbookOdds).where(SportsbookOdds.espn_game_id.like("bt-%")))
        s.execute(delete(TeamGameLog).where(TeamGameLog.season == SEASON))
        s.commit()


def _cfg() -> BacktestConfig:
    return BacktestConfig(start_season=SEASON, end_season=SEASON, min_edge_points=1.0)


def test_future_games_cannot_change_past_results(seeded_session):
    """THE critical test: inject a game after the window; results must not move."""
    s = seeded_session
    before = run_backtest(session=s, config=_cfg())

    later = dt.datetime(SEASON, 9, 1, tzinfo=UTC)
    for team, opp, home, scored, allowed in (
        ("BT_H", "BT_A", True, 200, 10), ("BT_A", "BT_H", False, 10, 200),
    ):
        s.add(TeamGameLog(
            game_date=later, season=SEASON, espn_game_id="bt-future",
            team_id=team, team_abbrev=team, opponent_id=opp, opponent_abbrev=opp,
            is_home=home, points_scored=scored, points_allowed=allowed,
            is_completed=True, season_type=2,
        ))
    s.commit()

    after = run_backtest(session=s, config=_cfg())
    n = min(len(before.bets), len(after.bets))
    for x, y in zip(before.bets[:n], after.bets[:n]):
        assert x.projected_total == pytest.approx(y.projected_total), (
            "a future game changed an earlier projection — lookahead"
        )


def test_backtest_is_deterministic(seeded_session):
    a = run_backtest(session=seeded_session, config=_cfg())
    b = run_backtest(session=seeded_session, config=_cfg())
    assert a.metrics.n_bets == b.metrics.n_bets
    assert a.metrics.total_pnl == pytest.approx(b.metrics.total_pnl)
    assert [x.pnl for x in a.bets] == pytest.approx([x.pnl for x in b.bets])


def test_config_hash_distinguishes_generations(seeded_session):
    a = run_backtest(session=seeded_session, config=_cfg(),
                     model_config=WNBATotalsConfig(record_beta=0.0))
    b = run_backtest(session=seeded_session, config=_cfg(),
                     model_config=WNBATotalsConfig(record_beta=0.5))
    assert a.config_hash != b.config_hash


def test_record_modifier_does_not_touch_totals(seeded_session):
    """beta=0 must reproduce the beta-fitted run exactly on a totals backtest.

    Clutch execution has no mechanism for moving a game's combined score.
    """
    a = run_backtest(session=seeded_session, config=_cfg(),
                     model_config=WNBATotalsConfig(record_beta=0.0))
    b = run_backtest(session=seeded_session, config=_cfg(),
                     model_config=WNBATotalsConfig(record_beta=5.0))
    assert a.metrics.n_bets == b.metrics.n_bets
    assert a.metrics.total_pnl == pytest.approx(b.metrics.total_pnl)
