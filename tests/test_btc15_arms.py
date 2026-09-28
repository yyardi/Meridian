"""Strategy arms for the Bitcoin Up-or-Down harness: price-aware entries, paper-traded side by side.

Iteration 1 bought the model's favourite at whatever the ask was; 98 % of its fills cost
more than the model's own probability said they were worth. These pin the rules that
replace it: a taker trades only when p - ask - fee beats its margin; a maker rests a
zero-fee bid below fair value and is filled only when the book trades THROUGH it; each
arm keeps its own ledger and allocation, records the windows it declines, and settles
off the venue's result like the model's own ledger.
"""
from __future__ import annotations

import json
import math

import pytest

from core.btc15 import quant as Q
from core.btc15.arms import Arm, ArmSpec, specs_from_env
from core.btc15.ledger import UNIT, Ledger

OPEN = 1_790_600_000.0
COEF = 0.0695


def _m(bid, ask, ticker="W1", strike=84000.0):
    return {"ticker": ticker, "status": "active", "open_ts": OPEN, "close_ts": OPEN + 900,
            "open_time": None, "close_time": None, "strike": strike,
            "yes_bid": bid, "yes_ask": ask,
            "yes_bid_u": None if bid is None else int(round(bid * UNIT)),
            "yes_ask_u": None if ask is None else int(round(ask * UNIT))}


@pytest.fixture
def led(tmp_path):
    return Ledger(str(tmp_path / "arm.sqlite"))


def test_fee_and_edge_pick_the_better_side_net_of_the_fee():
    assert Q.fee(0.50, COEF) == 0.02                     # 0.0695*0.25 = 1.74c -> 2c
    side, ev, price = Q.edge(0.70, yes_ask=0.60, yes_bid=0.58, coefficient=COEF)
    assert side == "YES" and price == 0.60 and ev == pytest.approx(0.70 - 0.60 - 0.02)
    side, ev, price = Q.edge(0.30, yes_ask=0.45, yes_bid=0.44, coefficient=COEF)
    assert side == "NO" and price == pytest.approx(0.56) and ev == pytest.approx(0.70 - 0.56 - 0.02)


def test_walk_probability_is_signed_by_the_distance_and_sharpens_as_time_runs_out():
    closes = [84000.0 * math.exp(0.0005 * math.sin(i)) for i in range(62)]
    above_early = Q.walk_p(Q.inputs(84100.0, 84000.0, 800.0, closes[:-1] + [84100.0]))
    above_late = Q.walk_p(Q.inputs(84100.0, 84000.0, 90.0, closes[:-1] + [84100.0]))
    below = Q.walk_p(Q.inputs(83900.0, 84000.0, 800.0, closes[:-1] + [83900.0]))
    assert 0.5 < above_early < above_late and below < 0.5
    assert Q.tau_eff(120) == 80 and Q.tau_eff(30) == 10


def test_quant_probability_needs_its_fitted_coefficients():
    qi = Q.QuantInputs(z=0.5, r1=0, r5=0, r15=0, vr=1, sigma_1m=0.001)
    assert Q.quant_p(qi, 0.6, 0.3, coef={}) is None
    c = {"intercept": 0.0, "coef": [1.0, 0, 0, 0, 0, 0, 0]}     # = the market's own logit
    assert Q.quant_p(qi, 0.6, 0.3, coef=c) == pytest.approx(0.6, abs=1e-6)


def test_a_taker_trades_only_when_the_edge_beats_the_margin(led):
    arm = Arm(ArmSpec("t", "walk", "taker", 0.04, start_s=30), led, 10 * UNIT)
    now = OPEN + 60
    arm.tick(now, _m(0.58, 0.60), {"walk": 0.63}, COEF, 90)          # EV 0.63-0.60-0.02 = 0.01 < 0.04
    assert led.decision("W1")["status"] == "watching" and not led.unsettled_fills()
    arm.tick(now + 3, _m(0.58, 0.60), {"walk": 0.70}, COEF, 90)      # EV 0.08 > 0.04
    f = led.unsettled_fills()[0]
    assert f["side"] == "YES" and f["price_u"] == 6000 and f["fee_u"] == 200
    arm.tick(now + 6, _m(0.58, 0.60), {"walk": 0.90}, COEF, 90)      # one contract per window
    assert len(led.unsettled_fills()) == 1 and led.decision("W1")["status"] == "filled"


def test_a_taker_that_never_sees_an_edge_records_no_edge_at_the_close(led):
    arm = Arm(ArmSpec("t", "walk", "taker", 0.04), led, 10 * UNIT)
    arm.tick(OPEN + 60, _m(0.49, 0.51), {"walk": 0.50}, COEF, 90)
    arm.tick(OPEN + 900 - 80, _m(0.49, 0.51), {"walk": 0.50}, COEF, 90)
    assert led.decision("W1")["status"] == "no_edge" and not led.unsettled_fills()


def test_a_maker_rests_below_fair_and_fills_only_when_traded_through_at_no_fee(led):
    arm = Arm(ArmSpec("mk", "walk", "maker", 0.02, start_s=300), led, 10 * UNIT)
    arm.tick(OPEN + 100, _m(0.50, 0.52), {"walk": 0.60}, COEF, 90)   # before start_s: nothing
    assert led.decision("W1") is None
    arm.tick(OPEN + 300, _m(0.50, 0.52), {"walk": 0.55}, COEF, 90)   # fair 0.55 -> bid at 0.53? capped at ask - 1c = 0.51
    d = led.decision("W1")
    assert d["status"] == "resting" and d["side"] == "YES" and json.loads(d["response"])["resting_price"] == 0.51
    arm.tick(OPEN + 303, _m(0.49, 0.51), {"walk": 0.55}, COEF, 90)   # the ask TOUCHES 0.51: not through
    assert led.decision("W1")["status"] == "resting"
    arm.tick(OPEN + 306, _m(0.48, 0.50), {"walk": 0.55}, COEF, 90)   # the ask trades through 0.51
    f = led.unsettled_fills()[0]
    assert f["side"] == "YES" and f["price_u"] == 5100 and f["fee_u"] == 0


def test_a_no_side_maker_is_a_yes_offer_filled_when_the_bid_crosses_it(led):
    arm = Arm(ArmSpec("mk", "walk", "maker", 0.02, start_s=300), led, 10 * UNIT)
    arm.tick(OPEN + 300, _m(0.40, 0.42), {"walk": 0.30}, COEF, 90)   # NO fair 0.70 -> NO bid at min(0.68, 0.59) = 0.59
    d = led.decision("W1")
    assert d["side"] == "NO" and json.loads(d["response"])["resting_price"] == 0.59
    arm.tick(OPEN + 303, _m(0.41, 0.43), {"walk": 0.30}, COEF, 90)   # yes bid 0.41 = our offer at 0.41: touch only
    assert led.decision("W1")["status"] == "resting"
    arm.tick(OPEN + 306, _m(0.42, 0.44), {"walk": 0.30}, COEF, 90)   # yes bid 0.42 crosses 0.41
    f = led.unsettled_fills()[0]
    assert f["side"] == "NO" and f["price_u"] == 5900 and f["fee_u"] == 0


def test_an_unfilled_maker_expires_before_the_close(led):
    arm = Arm(ArmSpec("mk", "walk", "maker", 0.02, start_s=300), led, 10 * UNIT)
    arm.tick(OPEN + 300, _m(0.50, 0.52), {"walk": 0.55}, COEF, 90)
    arm.tick(OPEN + 900 - 80, _m(0.50, 0.52), {"walk": 0.55}, COEF, 90)
    assert led.decision("W1")["status"] == "expired" and not led.unsettled_fills()


def test_the_llm_probability_is_used_by_a_taker_only_while_fresh(led):
    arm = Arm(ArmSpec("l", "llm", "taker", 0.02, llm_fresh_s=60), led, 10 * UNIT)
    arm.tick(OPEN + 200, _m(0.50, 0.52), {"llm": 0.80, "llm_at": OPEN + 100}, COEF, 90)   # 100 s old
    assert not led.unsettled_fills()
    arm.tick(OPEN + 203, _m(0.50, 0.52), {"llm": 0.80, "llm_at": OPEN + 180}, COEF, 90)   # 23 s old
    assert led.unsettled_fills()[0]["side"] == "YES"


def test_arms_settle_off_the_venue_result_and_keep_their_own_allocation(led):
    arm = Arm(ArmSpec("t", "walk", "taker", 0.0), led, 10 * UNIT)
    arm.tick(OPEN + 60, _m(0.58, 0.60), {"walk": 0.70}, COEF, 90)
    arm.settle({"W1": "yes"}, {"W1": ("yes", 84010.0, 84009.0)})
    a = led.account("paper")
    assert a["settled"] == 1 and a["realized_u"] == UNIT - 6000 - 200
    assert led._conn.execute("SELECT result FROM windows WHERE ticker='W1'").fetchone()["result"] == "yes"


def test_arm_specs_from_the_environment():
    assert specs_from_env("none") == ()
    s = specs_from_env('[{"name": "x", "prob": "walk", "kind": "maker", "margin": 0.03}]')
    assert s[0].name == "x" and s[0].margin == 0.03 and "zero-fee bid" in s[0].describe()
    assert len(specs_from_env(None)) >= 4


def test_the_market_mid_control_rests_on_both_sides_by_a_coin_keyed_on_the_window(tmp_path):
    sides = set()
    for i in range(12):
        led = Ledger(str(tmp_path / f"c{i}.sqlite"))
        arm = Arm(ArmSpec("c", "mid", "maker", 0.02, start_s=300), led, 10 * UNIT)
        arm.tick(OPEN + 300, _m(0.50, 0.52, ticker=f"W{i}"), {"mid": 0.51}, COEF, 90)
        sides.add(led.decision(f"W{i}")["side"])
    assert sides == {"YES", "NO"}
