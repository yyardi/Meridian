"""Spread/moneyline backtest: the pure logic that would invert results if wrong."""

from __future__ import annotations

import pytest

from core.backtest.margin import MarginOdds, home_covers


class TestHomeCovers:
    """ESPN convention: `spread` is the HOME handicap, negative = home favoured."""

    def test_home_favourite_covers_when_winning_big(self):
        # Home -4.5, wins by 5 -> covers.
        assert home_covers(home_margin=5, home_spread=-4.5) is True

    def test_home_favourite_fails_cover_on_narrow_win(self):
        # Home -5.5, wins by 5 -> does not cover.
        assert home_covers(home_margin=5, home_spread=-5.5) is False

    def test_home_underdog_covers_by_losing_narrowly(self):
        # Home +4.5, loses by 3 -> covers.
        assert home_covers(home_margin=-3, home_spread=4.5) is True

    def test_home_underdog_fails_on_blowout(self):
        assert home_covers(home_margin=-10, home_spread=4.5) is False

    def test_push_is_none_not_a_result(self):
        assert home_covers(home_margin=4, home_spread=-4) is None

    def test_the_validated_convention_example(self):
        """774/775 real games agreed with this convention.

        MIN -12.5 as away favourite means the HOME side carries +12.5.
        Home loses by 10 -> home covers, the MIN -12.5 bet loses.
        """
        assert home_covers(home_margin=-10, home_spread=12.5) is True


def test_margin_odds_holds_none_for_missing_markets():
    o = MarginOdds(home_spread=None, home_ml=-150.0, away_ml=130.0)
    assert o.home_spread is None and o.home_ml == -150.0
