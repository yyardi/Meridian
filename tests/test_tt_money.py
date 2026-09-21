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

#: The LATEST measurement of the TT cost bar, kept HERE and not in the module:
#: 1,339 last-pregame quotes over 2026-09-18..09-21 at the venue's own
#: coefficient (0.0695), median total 2.238c and mean total 6.065c. The
#: previous window (724 markets, 09-13..09-15, fee 0.06) gave 2.260c and
#: 3.728c -- the median barely moved while the mean grew 63%, because the board
#: nearly doubled and its tail of wide-quoted matches grew with it. A test may
#: hardcode a measurement to exercise arithmetic at a realistic magnitude; the
#: production path may not, which is what `test_the_module_carries_no_bar`
#: pins.
MEASURED_MEDIAN = 0.02238
MEASURED_MEAN = 0.06065


def test_fee_is_the_venues_not_ours():
    """A rate restated here instead of imported is the drift this pins."""
    for p in (0.05, 0.25, 0.5, 0.74, 0.95):
        assert money.fee(p) == fee_per_contract(p, is_maker=False)
    # and it is the quadratic, not a flat rate
    assert money.fee(0.5) > money.fee(0.1)


def test_the_module_carries_no_bar():
    """The cost bar is a property of a window, so the module holds none.

    It has been measured four times in nine days and moved every time, twice by
    a published constant that was then retracted (2.22c, a median of a sum with
    a fee back-derived out of it; 2.39c, a median half-spread plus a mean fee)
    and twice because the board and the venue's coefficient both changed. The
    gate's target now comes from what the arm actually paid.
    """
    for gone in ("COST_BAR", "BAR_MEDIAN", "BAR_MEAN", "HALF_SPREAD",
                 "MEAN_FEE"):
        assert not hasattr(money, gone), (
            f"money.{gone} is a population constant and will go stale; the "
            f"runner gates on MoneyResult.cost_median instead")


def test_the_mean_cost_is_the_tail_not_a_rounding():
    """The mean total is 2.7x the median on the latest window because the mean
    HALF-SPREAD is 9x its median (4.499c vs 0.500c). A gap that wide is a fact
    about the book, so a strategy's cost has to be measured, not chosen."""
    assert MEASURED_MEAN / MEASURED_MEDIAN > 2.0


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
        assert b.pnl != pytest.approx(1 - 0.40 - money.fee(0.40) - MEASURED_MEDIAN)

    def test_a_lost_bet_loses_the_stake_and_still_pays_the_fee(self):
        b = money.bet("s", 0.95, 0.39, 0.40, 0)
        assert b.pnl == pytest.approx(-0.40 - money.fee(0.40))

    def test_no_bet_when_the_model_agrees_with_the_book(self):
        assert money.bet("s", 0.50, 0.49, 0.51, 1) is None

    def test_crossed_or_impossible_quote_is_refused_not_guessed(self):
        assert money.bet("s", 0.9, 0.60, 0.40, 1) is None      # bid > ask
        assert money.bet("s", 0.9, -0.1, 0.40, 1) is None


class TestPower:
    def test_required_n_refuses_an_unnamed_target(self):
        """A bare match count reads as a property of the data. It is a choice
        of X, and across the bar's own range X moves the floor 2.7x."""
        with pytest.raises(TypeError):
            money.required_n()

    def test_required_n_resolves_the_bar_it_is_given(self):
        for bar in (MEASURED_MEDIAN, MEASURED_MEAN):
            n = money.required_n(resolution=bar)
            assert money.Z95 * money.PNL_SD / math.sqrt(n) <= bar
            assert money.Z95 * money.PNL_SD / math.sqrt(n - 1) > bar   # smallest

    def test_the_target_dominates_the_noise_estimate(self):
        """Choosing the bar moves the floor 2.7x; the sd's own rounding moves it
        4%. So the unnamed number to insist on is X, not sd."""
        by_target = (money.required_n(resolution=MEASURED_MEDIAN)
                     / money.required_n(resolution=MEASURED_MEAN))
        by_sd = (money.required_n(resolution=MEASURED_MEDIAN, sd=0.4995)
                 / money.required_n(resolution=MEASURED_MEDIAN, sd=0.49))
        assert by_target > 2.5 > 1.1 > by_sd

    def test_a_tighter_resolution_costs_quadratically(self):
        assert money.required_n(resolution=0.02) > money.required_n(resolution=0.04)
        ratio = money.required_n(resolution=0.01) / money.required_n(resolution=0.02)
        assert 3.9 < ratio < 4.1

    def test_the_interval_at_the_signal_floor_exceeds_either_bar(self):
        """The achievable-image claim, restated on what the gate actually uses.

        The 200-match interval half-width is 6.81c against a median cost of
        2.238c and a mean of 6.065c, and the MDE at 80% power is 9.73c. The
        earlier version of this test asserted MDE > 2x the mean bar, which was
        calibrated to a bar of 3.728c and started failing when the mean cost
        grew to 6.065c -- a threshold tuned to a number that moves.

        Worth noting how close the mean end now is: ~252 matches resolve 6.065c,
        against ~1,814 for 2.238c. At the mean cost this arm can speak far
        sooner than the 667 I quoted three days ago.
        """
        half = money.Z95 * money.PNL_SD / math.sqrt(rule.MIN_PREDICTED)
        assert half > MEASURED_MEDIAN
        assert half > MEASURED_MEAN
        assert money.mde(rule.MIN_PREDICTED) > MEASURED_MEAN
        assert money.required_n(resolution=MEASURED_MEAN) < 400
        assert money.required_n(resolution=MEASURED_MEDIAN) > 1500


class TestVerdict:
    def _at(self, n, mean, bar=MEASURED_MEDIAN):
        se = money.PNL_SD / math.sqrt(n)
        return rule.money_verdict(
            n=n, lo=mean - money.Z95 * se, hi=mean + money.Z95 * se,
            resolution=bar, required=money.required_n(resolution=bar))

    def test_money_arm_has_one_reachable_verdict_at_the_signal_floor(self):
        """Every achievable mean at n=200 returns NOT YET. A design with one
        reachable branch is not a decision (`check-a-decision-rule-against-
        its-achievable-image`)."""
        got = {self._at(rule.MIN_PREDICTED, m)[0]
               for m in (-0.50, -0.05, -0.024, 0.0, 0.024, 0.05, 0.50)}
        assert got == {rule.NOT_YET}

    def test_both_branches_open_once_the_interval_resolves_the_bar(self):
        n = money.required_n(resolution=MEASURED_MEDIAN)
        assert self._at(n, +0.05)[0] == rule.PASS
        assert self._at(n, 0.0)[0] == rule.FAIL
        assert self._at(n, -0.05)[0] == rule.FAIL

    def test_no_qualifying_bet_is_not_yet_not_fail(self):
        assert rule.money_verdict(n=0, lo=float("nan"), hi=float("nan"),
                                  resolution=MEASURED_MEDIAN, required=10)[0] \
            == rule.NOT_YET

    def test_not_estimable_interval_is_not_yet(self):
        assert rule.money_verdict(n=3, lo=float("nan"), hi=float("nan"),
                                  resolution=MEASURED_MEDIAN, required=10)[0] \
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
        return [money.Bet(f"s{i}", "YES", 0.5, v, 0.02)
                for i, v in enumerate(pnls)]

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
        assert r.n == 0
        assert math.isnan(r.mean)                     # NaN, not 0.0
        assert math.isnan(r.cost_mean)                # and no assumed cost


class TestRealisedCost:
    """What the arm actually paid, which is the number that decides the sign.

    The population bar spans 2.260c to 3.728c because of a tail of wide-quoted
    matches. Where a strategy lands inside that range is a property of its
    SELECTION, so it is measured on the bets placed and never assumed.
    """

    def test_cost_is_the_half_spread_paid_plus_the_fee_paid(self):
        b = money.bet("s", 0.99, 0.40, 0.44, 1)          # YES at 0.44, 4c wide
        assert b.side == "YES"
        assert b.cost == pytest.approx(0.02 + money.fee(0.44))

    def test_cost_on_the_no_side_uses_the_same_half_spread(self):
        b = money.bet("s", 0.01, 0.40, 0.44, 0)          # NO at 0.60
        assert b.side == "NO"
        assert b.cost == pytest.approx(0.02 + money.fee(0.60))

    def _placed(self, quotes):
        bets, a, bb = [], [], []
        for i, (bid, ask) in enumerate(quotes):
            b = money.bet(f"s{i}", 0.99, bid, ask, 1)
            assert b is not None
            bets.append(b)
            a.append(f"a{i}")
            bb.append(f"b{i}")
        return money.summarise(bets, a, bb)

    def test_a_wide_quote_selection_pays_the_tail(self):
        """If the model prefers wide-quoted matches it pays more than either
        population statistic, so even the mean bar would be optimistic."""
        tight = self._placed([(0.49, 0.50)] * 8)
        wide = self._placed([(0.40, 0.55)] * 8)
        assert wide.cost_mean > tight.cost_mean
        assert tight.cost_mean < MEASURED_MEAN < wide.cost_mean

    def test_realised_cost_is_reported_not_assumed(self):
        r = self._placed([(0.49, 0.50), (0.30, 0.45), (0.48, 0.52)])
        assert not math.isnan(r.cost_mean)
        assert not math.isnan(r.cost_median)
        assert r.cost_mean != pytest.approx(MEASURED_MEDIAN)
        assert r.cost_mean != pytest.approx(MEASURED_MEAN)

    def test_required_needs_its_target_named_even_from_a_result(self):
        r = self._placed([(0.49, 0.50)] * 4)
        assert r.required(r.cost_mean) == money.required_n(resolution=r.cost_mean)
        with pytest.raises(TypeError):
            r.required()


class TestCollapsedVariance:
    """A zero-width interval is no information wearing perfect precision.

    Found by driving the runner with 40 identical losing bets: the variance is
    genuinely zero, the interval half-width is 0, and every width gate lets
    that through as if the estimate were exact. `a-rescue-you-did-not-design`
    -- ask what a statistic prints when nothing is true.
    """

    def test_zero_width_interval_is_not_yet(self):
        for point in (-0.515, 0.0, +0.515):
            v, why = rule.money_verdict(n=40, lo=point, hi=point,
                                        resolution=MEASURED_MEDIAN,
                                        required=1814)
            assert v == rule.NOT_YET
            assert "collapsed" in why

    def test_a_real_narrow_interval_still_decides(self):
        v, _ = rule.money_verdict(n=1814, lo=0.001, hi=0.02,
                                  resolution=MEASURED_MEDIAN, required=1814)
        assert v == rule.PASS
