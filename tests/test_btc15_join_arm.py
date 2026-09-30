"""The join-the-touch maker arms and the fill model that prints decide (2026-09-30).

The retired mid_maker rested one bid and was filled only when the book traded THROUGH it, so
every fill was adverse (-13c a contract). These arms join the venue's own touch on both sides,
re-join it when it moves, and are filled the way a resting order is: by prints at their price
beyond the size that was ahead of them, or by a trade-through. The queue model is pinned here;
so is the ledger's markout record that scores a fill by the touch a few seconds later.
"""
from __future__ import annotations

import datetime as dt
import json

from core.btc15.arms import Arm, ArmSpec, DEFAULT_ARMS
from core.btc15.ledger import UNIT, Ledger

T = "cpc-btc-updown-15m-2026-09-30-2015z"
O = dt.datetime(2026, 9, 30, 20, 15, tzinfo=dt.timezone.utc).timestamp()
C = O + 900


def _m(yb, ya, ybs=500.0, yas=600.0):
    return {"ticker": T, "open_ts": O, "close_ts": C, "open_time": "2026-09-30T20:15:00Z", "close_time": "2026-09-30T20:30:00Z",
            "strike": 84000.0, "status": "active", "yes_bid": yb, "yes_ask": ya, "yes_bid_size": ybs, "yes_ask_size": yas,
            "yes_bid_u": None if yb is None else int(round(yb * UNIT)), "yes_ask_u": None if ya is None else int(round(ya * UNIT)),
            "no_bid_u": None, "no_ask_u": None}


def _arm(tmp_path, spec=ArmSpec("touch_maker", "mid", "join", 0.0), prints=None):
    return Arm(spec, Ledger(str(tmp_path / f"{spec.name}.sqlite")), 10 * UNIT, prints=prints)


def _state(arm):
    d = arm.ledger.decision(T)
    return d["status"], json.loads(d["response"] or "{}")


def test_the_arm_joins_both_sides_of_the_touch_behind_the_displayed_size(tmp_path):
    a = _arm(tmp_path)
    a.tick(O + 40, _m(0.44, 0.45, 500.0, 600.0), {"mid": 0.445}, 0.0695, 90)
    st, r = _state(a)
    assert st == "resting" and (r["bid"], r["offer"]) == (0.44, 0.45)
    assert (r["bid_ahead"], r["offer_ahead"]) == (500.0, 600.0) and r["bid_since"] == O + 40
    a.tick(O + 41, _m(0.44, 0.45, 300.0, 700.0), {"mid": 0.445}, 0.0695, 90)     # touch unchanged: queue kept
    _, r2 = _state(a)
    assert (r2["bid_ahead"], r2["bid_since"]) == (500.0, O + 40)                 # size that left without printing is not credited


def test_prints_at_our_price_fill_only_once_they_exceed_the_size_ahead_and_on_our_side(tmp_path):
    prints = []
    a = _arm(tmp_path, prints=lambda t, since: [p for p in prints if p[0] > since])
    a.tick(O + 40, _m(0.44, 0.45, 100.0, 600.0), {"mid": 0.445}, 0.0695, 90)
    prints += [(O + 39, 0.44, 500.0, "ORDER_INTENT_BUY_SHORT", "ORDER_INTENT_UNDEFINED")]     # before we joined
    prints += [(O + 42, 0.44, 60.0, "ORDER_INTENT_BUY_SHORT", "ORDER_INTENT_UNDEFINED")]      # 60 of 100 ahead
    prints += [(O + 43, 0.45, 500.0, "ORDER_INTENT_BUY_LONG", "ORDER_INTENT_UNDEFINED")]      # lifts the offer (500 < 600 ahead): not our bid
    a.tick(O + 44, _m(0.44, 0.45, 40.0, 600.0), {"mid": 0.445}, 0.0695, 90)
    assert _state(a)[0] == "resting" and not a.ledger.unsettled_fills()
    prints += [(O + 45, 0.44, 41.0, "ORDER_INTENT_UNDEFINED", "ORDER_INTENT_BUY_LONG")]       # maker was the bid: counts
    a.tick(O + 46, _m(0.44, 0.45, 0.0, 600.0), {"mid": 0.445}, 0.0695, 90)
    f = a.ledger.unsettled_fills()
    assert len(f) == 1 and (f[0]["side"], f[0]["price_u"], f[0]["fee_u"]) == ("YES", 4400, 0)
    assert "prints 101 > 100 ahead" in a.ledger.decision(T)["rationale"]


def test_prints_lifting_the_offer_fill_the_no_side_at_one_minus_the_offer(tmp_path):
    prints = []
    a = _arm(tmp_path, prints=lambda t, since: [p for p in prints if p[0] > since])
    a.tick(O + 40, _m(0.44, 0.45, 100.0, 10.0), {"mid": 0.445}, 0.0695, 90)
    prints += [(O + 41, 0.45, 5.0, "ORDER_INTENT_SELL_SHORT", "ORDER_INTENT_UNDEFINED"),
               (O + 42, 0.46, 6.0, "ORDER_INTENT_BUY_LONG", "ORDER_INTENT_UNDEFINED")]       # 11 > 10 ahead, at or through 0.45
    a.tick(O + 43, _m(0.44, 0.45, 100.0, 0.0), {"mid": 0.445}, 0.0695, 90)
    f = a.ledger.unsettled_fills()
    assert len(f) == 1 and (f[0]["side"], f[0]["price_u"]) == ("NO", 5500)


def test_a_trade_through_fills_without_any_print(tmp_path):
    a = _arm(tmp_path)
    a.tick(O + 40, _m(0.44, 0.45), {"mid": 0.445}, 0.0695, 90)
    a.tick(O + 41, _m(0.42, 0.43), {"mid": 0.425}, 0.0695, 90)                     # the ask crossed our 0.44 bid
    f = a.ledger.unsettled_fills()
    assert len(f) == 1 and (f[0]["side"], f[0]["price_u"]) == ("YES", 4400)
    assert "traded through" in a.ledger.decision(T)["rationale"]


def test_when_the_touch_moves_the_arm_rejoins_it_and_the_queue_restarts(tmp_path):
    prints = []
    a = _arm(tmp_path, prints=lambda t, since: [p for p in prints if p[0] > since])
    a.tick(O + 40, _m(0.44, 0.45, 100.0, 100.0), {"mid": 0.445}, 0.0695, 90)
    a.tick(O + 41, _m(0.45, 0.46, 250.0, 300.0), {"mid": 0.455}, 0.0695, 90)     # the bid moved up: we follow
    st, r = _state(a)
    assert st == "resting" and (r["bid"], r["bid_ahead"], r["bid_since"]) == (0.45, 250.0, O + 41)
    assert (r["offer"], r["offer_ahead"], r["offer_since"]) == (0.46, 300.0, O + 41)
    prints += [(O + 40.5, 0.44, 999.0, "ORDER_INTENT_BUY_SHORT", "ORDER_INTENT_UNDEFINED")]  # at the old level, before the re-join
    a.tick(O + 42, _m(0.45, 0.46, 250.0, 300.0), {"mid": 0.455}, 0.0695, 90)
    assert not a.ledger.unsettled_fills()
    a.tick(O + 43, _m(0.43, 0.44, 250.0, 300.0), {"mid": 0.435}, 0.0695, 90)     # the market maker dropped: the ask 0.44 < our 0.45 bid
    assert a.ledger.unsettled_fills()[0]["price_u"] == 4500                       # adverse: filled at our stale 0.45 through-trade


def test_a_wide_or_one_sided_book_pulls_the_quotes(tmp_path):
    a = _arm(tmp_path)
    a.tick(O + 40, _m(0.44, 0.45), {"mid": 0.445}, 0.0695, 90)
    a.tick(O + 41, _m(0.40, 0.45), {"mid": 0.425}, 0.0695, 90)                     # 5c wide: the maker is gone
    st, r = _state(a)
    assert st == "watching" and r == {}
    a.tick(O + 42, _m(0.44, None), {"mid": None}, 0.0695, 90)
    assert _state(a)[0] == "watching"
    a.tick(O + 43, _m(0.44, 0.45), {"mid": 0.445}, 0.0695, 90)
    assert _state(a)[0] == "resting"
    a.tick(C - 89, _m(0.44, 0.45), {"mid": 0.445}, 0.0695, 90)                     # inside min_lead: pulled for the window
    assert _state(a)[0] == "expired"


def test_the_kalshi_gated_arm_quotes_a_side_only_when_kalshi_says_it_is_cheap(tmp_path):
    a = _arm(tmp_path, ArmSpec("touch_maker_k", "kalshi", "join", 0.01))
    a.tick(O + 40, _m(0.44, 0.45), {"mid": 0.445, "kalshi": 0.452}, 0.0695, 90)  # Kalshi 45.2: bid 44 is 1.2c cheap, offer 45 is not 1c dear
    st, r = _state(a)
    assert st == "resting" and (r["bid"], r["offer"]) == (0.44, None)
    a.tick(O + 41, _m(0.44, 0.45), {"mid": 0.445, "kalshi": 0.438}, 0.0695, 90)  # Kalshi 43.8: only the offer at 45 is 1.2c dear
    st, r = _state(a)
    assert (r["bid"], r["offer"]) == (None, 0.45) and r["offer_since"] == O + 41
    a.tick(O + 42, _m(0.44, 0.45), {"mid": 0.445, "kalshi": 0.445}, 0.0695, 90)  # inside the margin both ways: pulled
    assert _state(a)[0] == "watching"
    a.tick(O + 43, _m(0.44, 0.45), {"mid": 0.445, "kalshi": None}, 0.0695, 90)   # no Kalshi price: nothing quoted
    assert _state(a)[0] == "watching"


def test_the_join_arms_are_in_the_default_set_one_contract_each_and_describe_their_queue_model():
    names = [a.name for a in DEFAULT_ARMS]
    assert names[-2:] == ["touch_maker", "touch_maker_k"]
    control, gated = DEFAULT_ARMS[-2], DEFAULT_ARMS[-1]
    assert "joined to the venue's own touch" in control.describe() and "the control" in control.describe()
    assert "Kalshi's mid is 1¢ better" in gated.describe()


# ------------------------------------------------------------------ markouts
def test_markouts_come_due_at_each_horizon_after_the_fill_and_never_past_the_close(tmp_path):
    led = Ledger(str(tmp_path / "m.sqlite"))
    led.upsert_window(_m(0.44, 0.45))
    fid, _ = led.record_fill("paper", T, "YES", 4400, 0, 10 * UNIT)
    filled = dt.datetime.fromisoformat(led._conn.execute("SELECT filled_at FROM fills").fetchone()[0]).timestamp()
    close_of = led.window_close_ts
    assert led.markouts_due(filled + 1, close_of) == []
    assert led.markouts_due(filled + 31, close_of) == [(fid, T, 5), (fid, T, 30)]
    led.add_markout(fid, 5, 0.44, 0.45)
    assert led.markouts_due(filled + 31, close_of) == [(fid, T, 30)]
    led._conn.execute("UPDATE windows SET close_ts=? WHERE ticker=?", (filled + 100, T))    # the window closes before 300 s
    assert led.markouts_due(filled + 400, close_of) == [(fid, T, 30), (fid, T, 60)]        # 300 s is past the close: never asked
    led.add_markout(fid, 30, None, None)                                                  # missed (a restart): recorded empty once
    assert led.markouts_due(filled + 400, close_of) == [(fid, T, 60)]
