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


# --------------------------------------------------------------------------- #
# analyse() — the function every CLV number in the project comes out of
# --------------------------------------------------------------------------- #
#
# It had no test. The two above this headed "Buchdahl's rule, end to end"
# assert `0.55 / 0.50 - 1 == approx(0.10)` and `0.52 / 0.52 - 1 == approx(0.0)`
# — facts about floating-point division, in a file that did not import
# `analyse`. Deleting the function left the whole file green.
#
# What that left unguarded, at exp_devigged_clv.py:133:
#
#     p_entry_novig = devigged[0] if b.side == "over" else devigged[1]
#
# Swap the index and every CLV probability in the project flips. The pair
# below is asymmetric ON PURPOSE: with over_price == under_price the de-vigged
# halves are equal, the swap is invisible, and a symmetric fixture would
# reproduce the blind spot rather than close it.


def _bet(**kw):
    """A filled, analysable BetRecord. Defaults are the analysable case; each
    test overrides exactly the field it is about."""
    import datetime as dt

    from core.backtest.engine import BetRecord

    base = dict(
        game_date=dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc),
        espn_game_id="clvtest-1", season=2026, season_type=2,
        side="over", entry_line=160.0, closing_line=164.0,
        projected_total=170.0, model_probability=0.60, entry_price=0.50,
        edge=4.0, contracts=1.0, filled=True, fee=0.0,
        actual_total=170, won=True, pnl=1.0, clv_points=4.0,
        is_playoff=False, sigma=10.0,
        over_price=0.55, under_price=0.50,
    )
    base.update(kw)
    return BetRecord(**base)


def _result(bets):
    from core.backtest.engine import BacktestConfig, BacktestResult

    return BacktestResult(config=BacktestConfig(), model_version="test",
                          config_hash="test", bets=list(bets))


#: Hand-computed, and the derivation is the point of writing them out:
#:   devig(0.55, 0.50)      = (0.55/1.05, 0.50/1.05) = (0.5238095, 0.4761905)
#:   p_over = Phi((164-160)/10) = Phi(0.4)           =  0.6554217
#:   over : expected = 0.6554217/0.50 - 1            = +0.3108435
#:          clv      = 0.6554217 - 0.5238095         = +0.1316122
#:   under: p_close  = 1 - 0.6554217                 =  0.3445783
#:          expected = 0.3445783/0.50 - 1            = -0.3108435
#:          clv      = 0.3445783 - 0.4761905         = -0.1316122
_OVER_EXPECTED, _OVER_CLV = 0.3108435, 0.1316122
_UNDER_EXPECTED, _UNDER_CLV = -0.3108435, -0.1316122


def test_analyse_prices_an_over_and_an_under_against_hand_values():
    from core.backtest.exp_devigged_clv import analyse

    expected, realised, clv = analyse(_result([
        _bet(side="over"), _bet(side="under", won=False, pnl=-0.5),
    ]))
    assert expected == pytest.approx([_OVER_EXPECTED, _UNDER_EXPECTED], abs=1e-6)
    assert clv == pytest.approx([_OVER_CLV, _UNDER_CLV], abs=1e-6)
    assert realised == pytest.approx([1.0, -0.5])


def test_the_side_picks_its_own_half_of_the_devigged_market():
    """The index at line 133, pinned directly.

    Swapping it gives the over 0.4761905 and the under 0.5238095, i.e. CLV of
    +0.1792313 / -0.1792313 instead of +0.1316122 / -0.1316122 — a 36% error
    in the same direction on every bet, which is exactly the kind of thing a
    plausible-looking ledger absorbs without complaint."""
    from core.backtest.exp_devigged_clv import analyse, devig_two_sided

    over_novig, under_novig = devig_two_sided(0.55, 0.50)
    assert over_novig != under_novig, (
        "an asymmetric market is the whole point of this fixture — with equal "
        "prices the swap is undetectable")

    _, _, clv = analyse(_result([_bet(side="over"), _bet(side="under")]))
    # clv = p_close - p_entry_novig, so the novig half each side used is
    # recoverable from the result without trusting the implementation.
    p_close_over = 0.6554217
    assert p_close_over - clv[0] == pytest.approx(over_novig, abs=1e-6)
    assert (1 - p_close_over) - clv[1] == pytest.approx(under_novig, abs=1e-6)


@pytest.mark.parametrize("kw,why", [
    ({"closing_line": None}, "no close to compare against"),
    ({"sigma": 0.0}, "sigma 0 makes the close's probability undefined"),
    ({"filled": False}, "an unfilled bet was never struck"),
    ({"over_price": 0.0}, "de-vig refuses a non-positive price"),
    ({"under_price": 0.0}, "de-vig refuses a non-positive price"),
    ({"entry_price": 0.0}, "E[ROI] divides by the price paid"),
])
def test_unanalysable_bets_are_dropped_not_defaulted(kw, why):
    """Each arm of the filter chain at 128-140. A bet that cannot be priced
    must leave NO row — a zero would read as 'no edge' rather than 'unknown'."""
    from core.backtest.exp_devigged_clv import analyse

    expected, realised, clv = analyse(_result([_bet(**kw)]))
    assert (expected, realised, clv) == ([], [], []), why


def test_an_unsettled_bet_scores_clv_but_not_pnl():
    """`won is None` is a bet whose game has not resolved. Its CLV is known
    the moment the market closes; its P&L is not, and counting 0.0 would
    silently dilute realised ROI toward zero with every open position."""
    from core.backtest.exp_devigged_clv import analyse

    expected, realised, clv = analyse(_result([_bet(won=None, pnl=0.0)]))
    assert len(expected) == 1 and len(clv) == 1
    assert realised == []
