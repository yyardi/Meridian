"""Kelly sizing and guardrails.

Kelly is a ceiling, never a floor — every test here checks that the *smallest*
constraint wins.
"""

from __future__ import annotations

import pytest

from core.kelly_sizing import (
    BasketLeg,
    Constraint,
    kelly_fraction,
    net_edge,
    size_game_basket,
    size_position,
)
from strategies.wnba_totals.config import WNBATotalsConfig

BIG = 10_000.0   # large bankroll so venue minimums never bind


def _cfg(**kw) -> WNBATotalsConfig:
    base = dict(
        kelly_fraction=0.25, max_position_size_pct=1.0, max_game_exposure_pct=1.0,
        max_daily_exposure_pct=1.0, min_edge_threshold=0.0, min_bankroll=0.0,
        max_position_dollars=1e9,
    )
    base.update(kw)
    return WNBATotalsConfig(**base)


# ---------------------------------------------------------------- #
# The formula
# ---------------------------------------------------------------- #

def test_kelly_matches_hand_computation():
    #  buy at 0.52 with true p=0.57  ->  (0.57-0.52)/(1-0.52) = 0.10417
    assert kelly_fraction(0.57, 0.52) == pytest.approx(0.05 / 0.48)


def test_quarter_kelly_is_exactly_a_quarter_of_full():
    full = size_position(probability=0.60, price=0.50, bankroll=BIG,
                         config=_cfg(kelly_fraction=1.0))
    quarter = size_position(probability=0.60, price=0.50, bankroll=BIG,
                            config=_cfg(kelly_fraction=0.25))
    assert quarter.dollars == pytest.approx(full.dollars * 0.25)


def test_negative_edge_gives_zero_never_a_reverse_bet():
    s = size_position(probability=0.40, price=0.50, bankroll=BIG, config=_cfg())
    assert s.dollars == 0 and s.contracts == 0
    assert s.binding_constraint is Constraint.NEGATIVE_EDGE
    assert kelly_fraction(0.40, 0.50) == 0.0


def test_edge_below_threshold_is_not_traded():
    s = size_position(probability=0.52, price=0.50, bankroll=BIG,
                      config=_cfg(min_edge_threshold=0.05))
    assert s.dollars == 0
    assert s.binding_constraint is Constraint.MIN_EDGE


# ---------------------------------------------------------------- #
# Fees
# ---------------------------------------------------------------- #

def test_fee_adjusted_edge_is_below_gross_for_a_taker():
    gross = 0.60 - 0.50
    assert net_edge(0.60, 0.50, is_maker=False) < gross


def test_maker_pays_no_fee_and_books_no_rebate():
    """Maker fee is zero: the advertised rebate is unverified (findings C7)."""
    gross = 0.60 - 0.50
    assert net_edge(0.60, 0.50, is_maker=True) == pytest.approx(gross)


def test_taker_sizes_smaller_than_maker():
    maker = size_position(probability=0.60, price=0.50, bankroll=BIG,
                          config=_cfg(), is_maker=True)
    taker = size_position(probability=0.60, price=0.50, bankroll=BIG,
                          config=_cfg(), is_maker=False)
    assert taker.dollars < maker.dollars
    assert any("taker" in n for n in taker.notes)


# ---------------------------------------------------------------- #
# Guardrails — each must clamp under adversarial input
# ---------------------------------------------------------------- #

def test_max_position_pct_clamps():
    s = size_position(probability=0.99, price=0.50, bankroll=BIG,
                      config=_cfg(max_position_size_pct=0.05))
    assert s.kelly_fraction_used == pytest.approx(0.05)
    assert s.binding_constraint is Constraint.MAX_POSITION_PCT


def test_game_exposure_cap_clamps():
    s = size_position(probability=0.99, price=0.50, bankroll=BIG,
                      config=_cfg(max_game_exposure_pct=0.08),
                      game_exposure_used=0.06)
    assert s.kelly_fraction_used == pytest.approx(0.02)
    assert s.binding_constraint is Constraint.MAX_GAME_PCT


def test_daily_exposure_cap_clamps():
    s = size_position(probability=0.99, price=0.50, bankroll=BIG,
                      config=_cfg(max_daily_exposure_pct=0.20),
                      daily_exposure_used=0.19)
    assert s.kelly_fraction_used == pytest.approx(0.01)
    assert s.binding_constraint is Constraint.MAX_DAILY_PCT


def test_absolute_dollar_cap_is_the_final_backstop():
    s = size_position(probability=0.99, price=0.50, bankroll=BIG,
                      config=_cfg(max_position_dollars=5.0))
    assert s.dollars == pytest.approx(5.0)
    assert s.binding_constraint is Constraint.MAX_DOLLARS


def test_min_bankroll_stops_trading():
    s = size_position(probability=0.99, price=0.50, bankroll=5.0,
                      config=_cfg(min_bankroll=10.0))
    assert s.dollars == 0
    assert s.binding_constraint is Constraint.MIN_BANKROLL


def test_adversarial_edge_never_escapes_every_guardrail():
    """edge = 0.99 must still respect the caps."""
    cfg = WNBATotalsConfig()   # production defaults
    s = size_position(probability=0.999, price=0.01, bankroll=40.0, config=cfg)
    assert s.dollars <= cfg.max_position_dollars
    assert s.kelly_fraction_used <= cfg.max_position_size_pct + 1e-9


def test_binding_constraint_is_always_reported():
    s = size_position(probability=0.60, price=0.50, bankroll=BIG, config=_cfg())
    assert isinstance(s.binding_constraint, Constraint)


# ---------------------------------------------------------------- #
# Correlation-aware baskets
# ---------------------------------------------------------------- #

def test_same_game_basket_sizes_below_the_independent_sum():
    """The whole point: same-game bets are not independent."""
    cfg = _cfg()
    legs = [
        BasketLeg("aec-x", "basketball_team_full_game_winner", 0.60, 0.50),
        BasketLeg("tsc-x-165", "basketball_team_full_game_total", 0.60, 0.50, side="over"),
    ]
    basket = size_game_basket(legs, bankroll=BIG, config=cfg)
    basket_total = sum(s.dollars for s in basket.values())

    independent = sum(
        size_position(probability=l.probability, price=l.price, bankroll=BIG, config=cfg).dollars
        for l in legs
    )
    assert basket_total < independent


def test_same_side_ladder_rungs_are_treated_as_nearly_one_bet():
    """Over 176.5 and Over 179.5 are almost literally the same position."""
    cfg = _cfg()
    legs = [
        BasketLeg("tsc-x-176", "basketball_team_full_game_total", 0.60, 0.50, side="over"),
        BasketLeg("tsc-x-179", "basketball_team_full_game_total", 0.60, 0.50, side="over"),
    ]
    basket = size_game_basket(legs, bankroll=BIG, config=cfg)
    sizes = sorted(s.dollars for s in basket.values())
    # The second rung gets a ~95% haircut.
    assert sizes[0] < sizes[1] * 0.15


def test_game_cap_binds_across_the_basket():
    cfg = _cfg(max_game_exposure_pct=0.04)
    legs = [
        BasketLeg(f"tsc-x-{i}", "basketball_team_full_game_total", 0.75, 0.50, side=str(i))
        for i in range(5)
    ]
    basket = size_game_basket(legs, bankroll=BIG, config=cfg)
    total_fraction = sum(s.kelly_fraction_used for s in basket.values())
    assert total_fraction <= 0.04 + 1e-9


# ---------------------------------------------------------------- #
# Small-bankroll reality
# ---------------------------------------------------------------- #

def test_below_venue_minimum_is_flagged_not_rounded_up():
    s = size_position(probability=0.55, price=0.50, bankroll=30.0,
                      config=WNBATotalsConfig(), minimum_trade_qty=100.0)
    assert s.dollars == 0
    assert s.binding_constraint is Constraint.BELOW_MIN_TRADE_QTY


def test_small_bankroll_is_called_out_honestly():
    s = size_position(probability=0.60, price=0.50, bankroll=35.0,
                      config=WNBATotalsConfig())
    assert any("variance dominates" in n for n in s.notes)
