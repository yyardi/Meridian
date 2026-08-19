"""The pregame ML/spread backtest, and chiefly its SIGN.

The bug these pin
-----------------
`sportsbook_odds.spread` is the home HANDICAP — negative when home is favoured
(measured: mean −1.82 against a mean home margin of +1.55, corr −0.49 over
1,642 games). `prob_cover` is documented as `P(home margin > line)` — it wants
the number the margin must EXCEED. Those are negatives of each other.

The first draft passed the handicap straight through, so the model priced
`P(margin > −5)` — home losing by fewer than 5 — while settlement scored
`margin > +5`. The model bet the opposite side of the one it was graded on, in
every game. It did not look like a bug. It looked like a **result**: spread ROI
−7.27% with a game-clustered CI of [−14.3%, −0.26%] that excluded zero, which
would have been reported as "the executor trades a market that measurably
loses". Correcting the sign moved it to −3.95% [−11.1%, +3.5%], crossing zero.

A wrong sign is not a missing value (V19). It produces a confident answer of
the wrong shape, which is why the convention is asserted here directly rather
than being implied by an end-to-end number.
"""

from __future__ import annotations

import datetime as dt

import pytest

from core.backtest.moneyline import (
    CLV_UNAVAILABLE,
    MARKET_ML,
    MARKET_SPREAD,
    MarketBet,
    MarketSummary,
    _maybe_bet,
)
from strategies.wnba_totals.model.fair_value import prob_cover

UTC = dt.timezone.utc


class _Row:
    espn_game_id = "g1"
    game_date = dt.datetime(2026, 7, 1, tzinfo=UTC)
    season = 2026


# ------------------------------------------------------------------ #
# The sign
# ------------------------------------------------------------------ #


def test_prob_cover_wants_the_threshold_not_the_handicap():
    """Pins the asymmetry that caused the bug. Home favoured by 5 is
    `spread = -5`; the margin must exceed `+5`."""
    handicap = -5.0
    threshold = -handicap

    # A team projected to win by exactly the threshold is a coin flip to cover.
    assert prob_cover(threshold, threshold, 10.0) == pytest.approx(0.5)

    # Passing the handicap instead asks a different, much easier question.
    wrong = prob_cover(threshold, handicap, 10.0)
    assert wrong > 0.8, "handicap-as-threshold should look near-certain"
    assert wrong != pytest.approx(0.5)


def test_settlement_and_model_use_the_same_convention():
    """`margin + spread > 0` (settlement) and `prob_cover(margin, -spread)`
    (model) must agree about who covered."""
    for handicap, margin in [(-5.0, 9.0), (-5.0, 1.0), (3.5, 5.0), (3.5, -6.0)]:
        settled_home_covered = (margin + handicap) > 0
        # sigma tiny => the model is effectively certain, so its probability
        # collapses to the same boolean the settlement computes.
        p = prob_cover(margin, -handicap, 0.01)
        model_says_home = p > 0.5
        assert model_says_home == settled_home_covered, (
            f"handicap={handicap} margin={margin}: settlement said "
            f"{settled_home_covered}, model said {model_says_home}"
        )


# ------------------------------------------------------------------ #
# Bet selection
# ------------------------------------------------------------------ #


def test_no_bet_when_edge_is_below_threshold():
    assert _maybe_bet(row=_Row(), market=MARKET_ML, line=None,
                      p_model_home=0.52, p_book_home=0.50,
                      price_home=0.50, price_away=0.50,
                      home_won=True, min_edge=0.03) is None


def test_takes_the_away_side_when_that_is_where_the_edge_is():
    """Both sides are considered. Only ever taking home would halve the sample
    and bias the result toward whatever the home-field term does."""
    bet = _maybe_bet(row=_Row(), market=MARKET_ML, line=None,
                     p_model_home=0.30, p_book_home=0.50,
                     price_home=0.50, price_away=0.50,
                     home_won=True, min_edge=0.03)
    assert bet is not None
    assert bet.side == "away"
    assert bet.won is False, "home won, so the away bet lost"
    assert bet.edge == pytest.approx(0.20)


def test_money_at_price_pnl():
    """Buy at 0.40, win -> +0.60. Buy at 0.40, lose -> -0.40 (C11)."""
    win = _maybe_bet(row=_Row(), market=MARKET_ML, line=None,
                     p_model_home=0.60, p_book_home=0.40,
                     price_home=0.40, price_away=0.60,
                     home_won=True, min_edge=0.03)
    assert win.pnl == pytest.approx(0.60)
    lose = _maybe_bet(row=_Row(), market=MARKET_ML, line=None,
                      p_model_home=0.60, p_book_home=0.40,
                      price_home=0.40, price_away=0.60,
                      home_won=False, min_edge=0.03)
    assert lose.pnl == pytest.approx(-0.40)


# ------------------------------------------------------------------ #
# Reporting discipline
# ------------------------------------------------------------------ #


def _bet(game: str, price: float, won: bool) -> MarketBet:
    return MarketBet(
        espn_game_id=game, game_date=_Row.game_date, season=2026,
        market=MARKET_ML, side="home", line=None,
        model_probability=0.5, book_probability=0.5, entry_price=price,
        edge=0.05, won=won, pnl=(1 - price) if won else -price, fee=0.0,
    )


def test_hit_rate_is_reported_with_its_breakeven():
    """C11: a 40% hit rate on 0.40 entries is breakeven, not failure. The two
    numbers are meaningless apart, so `entry_cost` must always be present."""
    s = MarketSummary(market=MARKET_ML)
    s.bets = [_bet(f"g{i}", 0.40, i < 4) for i in range(10)]
    d = s.as_dict()
    assert d["hit_rate"] == pytest.approx(0.40)
    assert d["entry_cost_stake_weighted"] == pytest.approx(0.40)
    assert d["roi"] == pytest.approx(0.0, abs=1e-9)


def test_clv_is_absent_with_a_stated_reason_never_a_number():
    """No open->close pair exists for these markets. A fabricated CLV would sit
    in the same column as the totals engine's real one."""
    s = MarketSummary(market=MARKET_SPREAD)
    s.bets = [_bet("g1", 0.5, True)]
    d = s.as_dict()
    assert d["mean_clv"] is None
    assert "fabricat" in d["clv_unavailable_because"].lower()
    assert d["clv_unavailable_because"] == CLV_UNAVAILABLE


def test_roi_ci_is_clustered_by_game_not_by_bet():
    """One game contributing many bets must not count as many clusters — the
    moneyline and the spread on one game are the same disagreement twice."""
    s = MarketSummary(market=MARKET_ML)
    s.bets = [_bet("same-game", 0.5, True) for _ in range(50)]
    assert s.n == 50 and s.games == 1
    assert s.roi_interval() is None, "one cluster cannot support an interval"
