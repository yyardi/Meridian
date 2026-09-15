"""The money arm: its arithmetic, and the fact that it cannot speak yet.

The test that matters most here is `test_money_arm_has_one_reachable_verdict`:
at the registered 200-match signal floor the money arm returns NOT YET for
every possible mean, so a PASS on the signal arm can never be accompanied by a
money answer on day one. That is the same dead-branch finding the harness
already records for setkawoua, one arm over.
"""

from __future__ import annotations

import math

import pytest

from core.backtest.fills import fee_per_contract
from core.tt import money, rule


def test_fee_is_the_venues_not_ours():
    """A rate restated here instead of imported is the drift this pins."""
    for p in (0.05, 0.25, 0.5, 0.74, 0.95):
        assert money.fee(p) == fee_per_contract(p, is_maker=False)
    # and it is the quadratic, not a flat rate
    assert money.fee(0.5) > money.fee(0.1)


def test_cost_bar_is_the_last_quote_population():
    """1.00c + 1.388c = 2.39c, both measured on the 724 last pregame quotes.

    STATUS §0bc published 1.22c for the fee term; on that population every
    statistic of it is 1.39-1.46c (harness §7), so the bar was 0.17c low --
    less than one tick, and the whole distance between "marginal" and
    "negative" for the programme's last live path.
    """
    assert money.HALF_SPREAD == pytest.approx(0.0100)
    assert money.MEAN_FEE == pytest.approx(0.01388)
    assert money.COST_BAR == pytest.approx(0.02388)
    assert money.COST_BAR > 0.0222            # not the published bar


class TestBet:
    def test_yes_needs_to_clear_the_ask_AND_the_fee(self):
        ask, bid = 0.50, 0.49
        just_over_ask = ask + money.fee(ask) / 2.0     # clears ask, not the fee
        assert money.bet("s", just_over_ask, bid, ask, 1) is None
        assert money.bet("s", ask + money.fee(ask) + 1e-9, bid, ask, 1) is not None

    def test_no_side_is_priced_at_one_minus_the_bid(self):
        b = money.bet("s", 0.10, 0.40, 0.42, 0)
        assert b is not None and b.side == "NO"
        assert b.entry == pytest.approx(0.60)
        # won the NO: 1 - 0.60 - fee(0.60)
        assert b.pnl == pytest.approx(1 - 0.60 - money.fee(0.60))

    def test_the_cost_is_charged_once(self):
        """The bar is NOT subtracted from the P&L: the entry price and its fee
        ARE the cost. Subtracting COST_BAR again is `anchor-is-bookkeeping`."""
        b = money.bet("s", 0.95, 0.39, 0.40, 1)
        assert b.pnl == pytest.approx(1 - 0.40 - money.fee(0.40))
        assert b.pnl != pytest.approx(1 - 0.40 - money.fee(0.40) - money.COST_BAR)

    def test_a_lost_bet_loses_the_stake_and_still_pays_the_fee(self):
        b = money.bet("s", 0.95, 0.39, 0.40, 0)
        assert b.pnl == pytest.approx(-0.40 - money.fee(0.40))

    def test_no_bet_when_the_model_agrees_with_the_book(self):
        assert money.bet("s", 0.50, 0.49, 0.51, 1) is None

    def test_crossed_or_impossible_quote_is_refused_not_guessed(self):
        assert money.bet("s", 0.9, 0.60, 0.40, 1) is None      # bid > ask
        assert money.bet("s", 0.9, -0.1, 0.40, 1) is None


class TestPower:
    def test_required_n_resolves_the_bar_it_is_given(self):
        n = money.required_n(resolution=money.COST_BAR)
        se = money.PNL_SD / math.sqrt(n)
        assert money.Z95 * se <= money.COST_BAR
        se_short = money.PNL_SD / math.sqrt(n - 1)
        assert money.Z95 * se_short > money.COST_BAR      # and it is the SMALLEST such n

    def test_a_tighter_resolution_costs_quadratically(self):
        assert money.required_n(resolution=0.02) > money.required_n(resolution=0.04)
        ratio = money.required_n(resolution=0.01) / money.required_n(resolution=0.02)
        assert 3.9 < ratio < 4.1

    def test_mde_at_the_signal_floor_is_far_above_the_bar(self):
        """~9.7c against a 2.39c bar. Stated before any fit, not after."""
        assert money.mde(rule.MIN_PREDICTED) > 4 * money.COST_BAR


class TestVerdict:
    def _at(self, n, mean):
        se = money.PNL_SD / math.sqrt(n)
        return rule.money_verdict(
            n=n, lo=mean - money.Z95 * se, hi=mean + money.Z95 * se,
            resolution=money.COST_BAR, required=money.required_n())

    def test_money_arm_has_one_reachable_verdict_at_the_signal_floor(self):
        """Every achievable mean at n=200 returns NOT YET. A design with one
        reachable branch is not a decision (`check-a-decision-rule-against-
        its-achievable-image`)."""
        got = {self._at(rule.MIN_PREDICTED, m)[0]
               for m in (-0.50, -0.05, -0.024, 0.0, 0.024, 0.05, 0.50)}
        assert got == {rule.NOT_YET}

    def test_both_branches_open_once_the_interval_resolves_the_bar(self):
        n = money.required_n()
        assert self._at(n, +0.05)[0] == rule.PASS
        assert self._at(n, 0.0)[0] == rule.FAIL
        assert self._at(n, -0.05)[0] == rule.FAIL

    def test_no_qualifying_bet_is_not_yet_not_fail(self):
        assert rule.money_verdict(n=0, lo=float("nan"), hi=float("nan"),
                                  resolution=money.COST_BAR, required=10)[0] \
            == rule.NOT_YET

    def test_not_estimable_interval_is_not_yet(self):
        assert rule.money_verdict(n=3, lo=float("nan"), hi=float("nan"),
                                  resolution=money.COST_BAR, required=10)[0] \
            == rule.NOT_YET

    def test_the_two_verdicts_are_never_collapsed(self):
        line = rule.report((rule.PASS, "coefficient excludes zero"),
                           (rule.NOT_YET, "underpowered"))
        assert "SIGNAL PASS" in line and "MONEY NOT YET" in line

    def test_the_signal_rule_is_untouched_by_this_registration(self):
        assert rule.verdict(predicted=200, players=25,
                            interval_excludes_zero=True)[0] == rule.PASS
        assert rule.verdict(predicted=199, players=25,
                            interval_excludes_zero=True)[0] == rule.NOT_YET


class TestClustering:
    def _bets(self, pnls):
        return [money.Bet(f"s{i}", "YES", 0.5, v) for i, v in enumerate(pnls)]

    def test_game_clustering_is_a_no_op_so_players_are_the_clusters(self):
        """One bet per match: a 'game-clustered' SE is the iid one relabelled."""
        pnls = [0.5, -0.5, 0.4, -0.6, 0.5, -0.5]
        a = [f"a{i}" for i in range(6)]
        b = [f"b{i}" for i in range(6)]
        r = money.summarise(self._bets(pnls), a, b)
        assert r.se_player == pytest.approx(r.se_iid, rel=0.2)

    def test_a_recurring_player_widens_the_interval(self):
        pnls = [0.5] * 5 + [-0.5] * 5
        a_distinct = [f"a{i}" for i in range(10)]
        b_distinct = [f"b{i}" for i in range(10)]
        a_shared = ["winner"] * 5 + ["loser"] * 5
        wide = money.summarise(self._bets(pnls), a_shared, b_distinct)
        narrow = money.summarise(self._bets(pnls), a_distinct, b_distinct)
        assert wide.se_player > narrow.se_player

    def test_empty_summary_states_the_requirement_rather_than_zero(self):
        r = money.summarise([], [], [])
        assert r.n == 0 and r.mean != r.mean          # NaN, not 0.0
        assert r.required == money.required_n()
