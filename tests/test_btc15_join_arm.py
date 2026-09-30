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
    r = json.loads(a.ledger.decision(T)["response"])                 # the fill's own instant and evidence, for the tape
    assert (r["filled_ts"], r["filled_by"], r["filled_side"], r["filled_price"], r["ahead"], r["printed"]) == (O + 46, "prints", "bid", 0.44, 100.0, 101.0)


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
    assert json.loads(a.ledger.decision(T)["response"])["filled_by"] == "through"


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
    assert names[-4:] == ["touch_maker", "touch_maker_k", "touch_maker_t", "touch_maker_kt"]
    assert [a.spot_pull_usd for a in DEFAULT_ARMS[-4:]] == [0.0, 0.0, 10.0, 10.0]          # the controls untouched
    assert DEFAULT_ARMS[-1].margin == DEFAULT_ARMS[-3].margin and DEFAULT_ARMS[-1].prob == "kalshi"
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


# ------------------------------------------------------------------ the spot trigger (off by default)
def _trig(tmp_path, prints=None, usd=10.0):
    return _arm(tmp_path, ArmSpec("touch_maker_p", "mid", "join", 0.0, spot_pull_usd=usd, spot_pull_ms=250, spot_repost_s=2.0), prints=prints)


def test_the_trigger_is_off_on_the_controls_and_described_when_on():
    assert all(a.spot_pull_usd == 0 for a in DEFAULT_ARMS if not a.name.endswith("t"))
    on = ArmSpec("x", "mid", "join", 0.0, spot_pull_usd=10)
    assert "the threatened side pulled when coinbase moves $10 in 250 ms, re-joined after the book re-prices" in on.describe()
    both = ArmSpec("x", "mid", "join", 0.0, spot_pull_usd=10, spot_pull_sides="both", spot_rejoin="calm")
    assert "both sides pulled" in both.describe() and "once spot is calm" in both.describe()
    assert "pulled" not in ArmSpec("x", "mid", "join", 0.0).describe()


def test_the_both_sides_variant_pulls_both_and_the_calm_variant_rejoins_when_spot_settles(tmp_path):
    a = _arm(tmp_path, ArmSpec("touch_maker_b", "mid", "join", 0.0, spot_pull_usd=10, spot_pull_ms=500,
                               spot_repost_s=5.0, spot_pull_sides="both", spot_rejoin="calm"))
    a.tick(O + 40, _m(0.44, 0.45), {"mid": 0.445, "spot_move": {500: 1.0}}, 0.0695, 90)
    assert a.spot_pull(O + 41, T, "up", 14.0, 0.445) is True
    r = _state(a)[1]
    assert r["bid"] is None and r["offer"] is None and set(r["pulled"]) == {"bid", "offer"}
    a.tick(O + 41.4, _m(0.45, 0.46), {"mid": 0.455, "spot_move": {500: 13.0}}, 0.0695, 90)   # book re-priced but spot still moving: stay out
    assert _state(a)[1]["bid"] is None and _state(a)[1]["offer"] is None
    a.tick(O + 41.9, _m(0.45, 0.46), {"mid": 0.455, "spot_move": {500: 3.0}}, 0.0695, 90)    # spot calm: re-join both
    r = _state(a)[1]
    assert (r["bid"], r["offer"], r["bid_since"]) == (0.45, 0.46, O + 41.9) and "pulled" not in r


def test_an_up_move_pulls_the_offer_only_and_a_print_there_no_longer_fills(tmp_path):
    prints = []
    a = _trig(tmp_path, prints=lambda t, since: [p for p in prints if p[0] > since])
    a.tick(O + 40, _m(0.44, 0.45, 100.0, 10.0), {"mid": 0.445}, 0.0695, 90)
    assert a.spot_pull(O + 40.3, T, "up", 12.0, 0.445) is True
    st, r = _state(a)
    assert st == "resting" and r["offer"] is None and r["bid"] == 0.44 and r["bid_since"] == O + 40     # bid keeps its queue
    assert r["pulled"]["offer"]["dir"] == "up" and r["pulled"]["offer"]["was"] == 0.45
    assert a.spot_pull(O + 40.4, T, "up", 15.0, 0.445) is False                                        # already pulled
    prints += [(O + 40.5, 0.45, 500.0, "ORDER_INTENT_BUY_LONG", "ORDER_INTENT_UNDEFINED")]                # lifts 0.45: not us
    a.tick(O + 40.6, _m(0.44, 0.45, 100.0, 10.0), {"mid": 0.445}, 0.0695, 90)
    assert not a.ledger.unsettled_fills() and _state(a)[1]["offer"] is None
    a.tick(O + 40.8, _m(0.45, 0.46, 80.0, 90.0), {"mid": 0.455}, 0.0695, 90)     # the book re-priced up a tick: re-join
    st, r = _state(a)
    assert (r["offer"], r["offer_since"], r["offer_ahead"]) == (0.46, O + 40.8, 90.0) and "pulled" not in r
    assert (r["bid"], r["bid_since"], r["bid_ahead"]) == (0.45, O + 40.8, 80.0)   # the bid followed the touch as usual


def test_a_down_move_pulls_the_bid_and_a_book_that_trades_through_the_old_bid_rejoins_without_filling(tmp_path):
    a = _trig(tmp_path)
    a.tick(O + 40, _m(0.44, 0.45), {"mid": 0.445}, 0.0695, 90)
    assert a.spot_pull(O + 41, T, "down", -11.0, 0.445) is True
    r = _state(a)[1]
    assert r["bid"] is None and r["offer"] == 0.45
    a.tick(O + 41.5, _m(0.44, 0.45), {"mid": 0.445}, 0.0695, 90)                 # book unchanged: still pulled
    assert _state(a)[1]["bid"] is None
    a.tick(O + 41.7, _m(0.42, 0.43), {"mid": 0.425}, 0.0695, 90)                 # the ask crossed the OLD 0.44 -- pulled, so no fill; re-priced down: re-join
    assert not a.ledger.unsettled_fills()
    r = _state(a)[1]
    assert (r["bid"], r["bid_since"]) == (0.42, O + 41.7) and "pulled" not in r


def test_a_pulled_side_rejoins_after_the_repost_timeout_when_the_book_never_repriced(tmp_path):
    prints = []
    a = _trig(tmp_path, prints=lambda t, since: [p for p in prints if p[0] > since])
    a.tick(O + 40, _m(0.44, 0.45, 100.0, 100.0), {"mid": 0.445}, 0.0695, 90)
    assert a.spot_pull(O + 41, T, "down", -11.0, 0.445) is True
    prints += [(O + 41.2, 0.44, 999.0, "ORDER_INTENT_BUY_SHORT", "ORDER_INTENT_UNDEFINED")]   # hits 0.44 while we are pulled
    a.tick(O + 41.5, _m(0.44, 0.45, 100.0, 100.0), {"mid": 0.445}, 0.0695, 90)
    assert not a.ledger.unsettled_fills() and _state(a)[1]["bid"] is None
    a.tick(O + 42.5, _m(0.44, 0.45, 100.0, 100.0), {"mid": 0.445}, 0.0695, 90)   # 1.5 s: still pulled
    assert _state(a)[1]["bid"] is None
    a.tick(O + 43.1, _m(0.44, 0.45, 70.0, 100.0), {"mid": 0.445}, 0.0695, 90)    # 2.1 s after the pull: re-joined, fresh queue
    r = _state(a)[1]
    assert (r["bid"], r["bid_since"], r["bid_ahead"]) == (0.44, O + 43.1, 70.0) and "pulled" not in r
    assert r["offer_since"] == O + 40                                              # the offer kept its place throughout


def test_a_move_below_the_threshold_or_on_a_control_arm_pulls_nothing(tmp_path):
    a = _trig(tmp_path)
    a.tick(O + 40, _m(0.44, 0.45), {"mid": 0.445}, 0.0695, 90)
    assert a.spot_pull(O + 41, T, "up", 9.9, 0.445) is False and _state(a)[1]["offer"] == 0.45
    c = _arm(tmp_path)                                                              # spot_pull_usd = 0: the control
    c.tick(O + 40, _m(0.44, 0.45), {"mid": 0.445}, 0.0695, 90)
    assert c.spot_pull(O + 41, T, "up", 50.0, 0.445) is False and _state(c)[1]["offer"] == 0.45
    assert a.spot_pull(O + 41, "another-window", "up", 50.0, 0.445) is False


def test_a_pulled_side_is_filled_by_neither_prints_nor_a_trade_through_until_it_rejoins(tmp_path):
    prints = []
    a = _trig(tmp_path, prints=lambda t, since: [p for p in prints if p[0] > since])
    a.tick(O + 40, _m(0.44, 0.45, 10.0, 10.0), {"mid": 0.445}, 0.0695, 90)
    assert a.spot_pull(O + 41, T, "up", 20.0, 0.445) is True                       # the offer at 0.45 is pulled
    prints += [(O + 41.1, 0.45, 5000.0, "ORDER_INTENT_BUY_LONG", "ORDER_INTENT_UNDEFINED")]   # prints far beyond the 10 ahead
    a.tick(O + 41.2, _m(0.44, 0.45, 10.0, 10.0), {"mid": 0.445}, 0.0695, 90)
    assert not a.ledger.unsettled_fills()
    a.tick(O + 41.3, _m(0.47, 0.48, 10.0, 10.0), {"mid": 0.475}, 0.0695, 90)     # the bid crossed the OLD 0.45 offer: a trade-through, while pulled
    assert not a.ledger.unsettled_fills()
    r = _state(a)[1]
    assert (r["offer"], r["offer_since"]) == (0.48, O + 41.3) and "pulled" not in r  # re-priced up: re-joined at the new touch
    prints += [(O + 41.5, 0.48, 11.0, "ORDER_INTENT_BUY_LONG", "ORDER_INTENT_UNDEFINED")]     # now a print beyond the 10 ahead fills
    a.tick(O + 41.6, _m(0.47, 0.48, 10.0, 0.0), {"mid": 0.475}, 0.0695, 90)
    f = a.ledger.unsettled_fills()
    assert len(f) == 1 and (f[0]["side"], f[0]["price_u"]) == ("NO", 5200)
