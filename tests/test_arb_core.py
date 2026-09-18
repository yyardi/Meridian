"""The pieces the ARB tab is built on: core.ladder.live, core.ladder.desk,
and the two additive keyword arguments on LimitOrder.to_payload.

DB-free. The order-payload tests pin that the DEFAULT payload is byte-for-byte
what every order ever sent carried, and that the arbitrage variant differs in
exactly the three places the venue doc names (post-only off, IOC, synchronous).
"""
from __future__ import annotations

import datetime as dt
import inspect
import json
import os
import pathlib
import sys
import time
from decimal import Decimal

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core import executor as ex  # noqa: E402
from core.ladder import desk, live  # noqa: E402

NOW = dt.datetime(2026, 9, 18, 23, 41, 7, tzinfo=dt.timezone.utc)


# --------------------------------------------------------------------------- #
# to_payload: the default is unchanged; the arb variant is additive
# --------------------------------------------------------------------------- #

def _order(outcome=ex.OutcomeSide.YES, side=ex.OrderSide.BUY):
    return ex.build_order(market_slug="asc-cfb-mia-wake-2026-09-18-pos-10pt5", side=side,
                          limit_price=Decimal("0.41"), quantity=Decimal("2"),
                          decided_at=NOW, outcome=outcome)


def test_default_payload_is_the_one_every_order_ever_sent():
    """Spelled out as a literal, not derived: post-only GTC with no
    synchronousExecution key, in this key order (the body is signed)."""
    o = _order()
    assert o.to_payload() == {
        "marketSlug": "asc-cfb-mia-wake-2026-09-18-pos-10pt5",
        "type": "ORDER_TYPE_LIMIT",
        "price": {"value": "0.41", "currency": "USD"},
        "quantity": "2",
        "tif": "TIME_IN_FORCE_GOOD_TILL_CANCEL",
        "intent": "ORDER_INTENT_BUY_LONG",
        "outcomeSide": "OUTCOME_SIDE_YES",
        "action": "ORDER_ACTION_BUY",
        "manualOrderIndicator": "MANUAL_ORDER_INDICATOR_MANUAL",
        "participateDontInitiate": True,
        "clientOrderId": o.idempotency_key,
    }
    assert list(o.to_payload()) == list(o.to_payload(post_only=True, tif=ex.DEFAULT_TIF, synchronous=False))
    assert json.dumps(o.to_payload()) == json.dumps(o.to_payload(tif=ex.DEFAULT_TIF))


def test_arb_variant_differs_in_exactly_three_fields():
    o = _order(outcome=ex.OutcomeSide.NO)
    base = o.to_payload()
    arb = o.to_payload(post_only=False, tif=ex.ARB_TIF, synchronous=True)
    assert arb["tif"] == "TIME_IN_FORCE_IMMEDIATE_OR_CANCEL"
    assert arb["participateDontInitiate"] is False
    assert arb["synchronousExecution"] is True
    changed = {k for k in set(base) | set(arb) if base.get(k) != arb.get(k)}
    assert changed == {"tif", "participateDontInitiate", "synchronousExecution"}
    assert arb["type"] == "ORDER_TYPE_LIMIT", "still a limit: the price is the ticket's, IOC just refuses to rest"
    assert arb["intent"] == "ORDER_INTENT_BUY_SHORT" and arb["price"]["value"] == "0.41"
    assert list(arb)[:-1] == list(base), "the new key is appended; the signed prefix is unchanged"


def test_synchronous_false_leaves_no_key_behind():
    o = _order()
    assert "synchronousExecution" not in o.to_payload(synchronous=False)
    assert "synchronousExecution" not in o.to_payload(tif=ex.ARB_TIF)


@pytest.mark.parametrize("tif", sorted(ex.VENUE_TIFS))
def test_every_venue_tif_is_accepted_verbatim(tif):
    assert _order().to_payload(tif=tif)["tif"] == tif


@pytest.mark.parametrize("bad", ["IOC", "GTC", "TIME_IN_FORCE_IOC", "", "time_in_force_good_till_cancel"])
def test_a_tif_the_venue_does_not_define_is_refused_here(bad):
    with pytest.raises(ValueError):
        _order().to_payload(tif=bad)


def test_arb_tif_is_the_documented_ioc_and_says_it_is_untested_live():
    assert ex.ARB_TIF == "TIME_IN_FORCE_IMMEDIATE_OR_CANCEL" and ex.ARB_TIF in ex.VENUE_TIFS
    assert ex.VENUE_TIFS == {"TIME_IN_FORCE_DAY", "TIME_IN_FORCE_GOOD_TILL_CANCEL", "TIME_IN_FORCE_GOOD_TILL_DATE",
                             "TIME_IN_FORCE_IMMEDIATE_OR_CANCEL", "TIME_IN_FORCE_FILL_OR_KILL"}
    src = pathlib.Path(ex.__file__).read_text(encoding="utf-8")
    at = src.index('\nARB_TIF = "TIME_IN_FORCE_IMMEDIATE_OR_CANCEL"')
    doc = src[src.rindex("\n\n", 0, at):at]           # the #: comment block directly above the constant
    assert doc.strip().startswith("#:") and "create-order" in doc and "NOT yet exercised live" in doc


def test_order_type_is_still_not_a_parameter():
    assert "order_type" not in inspect.signature(ex.LimitOrder.to_payload).parameters
    assert set(inspect.signature(ex.LimitOrder.to_payload).parameters) == {"self", "post_only", "tif", "synchronous"}


# --------------------------------------------------------------------------- #
# core.ladder.live
# --------------------------------------------------------------------------- #

def test_line_of_is_the_settled_convention():
    assert live.line_of("asc-nfl-det-buf-2026-09-17-neg-10pt5", "aec-nfl-det-buf-2026-09-17") == -10.5
    assert live.line_of("asc-nfl-det-buf-2026-09-17-pos-3pt5", "aec-nfl-det-buf-2026-09-17") == 3.5
    assert live.line_of("aec-nfl-det-buf-2026-09-17", "aec-nfl-det-buf-2026-09-17") == 0.0
    assert live.line_of("tsc-nfl-det-buf-2026-09-17-44pt5", "aec-nfl-det-buf-2026-09-17") is None


def test_sample_returns_the_scan_shape_and_the_venue_stamp():
    from types import SimpleNamespace as NS
    lvl = lambda px, qty: NS(px=NS(value=str(px)), qty=str(qty))

    class Client:
        calls: list = []

        def get_book(self, slug):
            self.calls.append(slug)
            md = NS(bids=[lvl(0.40, 100)], offers=[lvl(0.42, 50)])
            return NS(market_data=md), {"marketData": {"transactTime": "2026-09-18T13:17:58.280016334Z"}}
    meta: dict = {}
    rungs, took = live.sample(Client(), ["asc-x-2026-09-18-pos-3pt5", "aec-x-2026-09-18", "tsc-x-2026-09-18-44pt5"],
                              "aec-x-2026-09-18", meta)
    assert rungs == {3.5: (0.40, 0.42, 100.0, 50.0), 0.0: (0.40, 0.42, 100.0, 50.0)}, "a total is not a rung"
    assert meta == {3.5: "2026-09-18T13:17:58.280016334Z", 0.0: "2026-09-18T13:17:58.280016334Z"}
    assert took >= 0.0
    assert live.sample(Client(), ["asc-x-2026-09-18-pos-3pt5"], "aec-x-2026-09-18")[0] == {3.5: (0.40, 0.42, 100.0, 50.0)}
    assert live.sample(Client(), ["aec-x-2026-09-18-pos-3pt5"], "aec-x-2026-09-18")[0] == {0.0: (0.40, 0.42, 100.0, 50.0)}, \
        "a slug that STARTS WITH the winner slug is read as the winner: spread slugs are asc-, never aec-"


def test_an_empty_side_is_not_a_rung():
    from types import SimpleNamespace as NS
    lvl = lambda px, qty: NS(px=NS(value=str(px)), qty=str(qty))

    class Client:
        def get_book(self, slug):
            return NS(market_data=NS(bids=[], offers=[lvl(0.42, 50)])), {}
    assert live.sample(Client(), ["asc-x-2026-09-18-pos-3pt5"], "aec-x-2026-09-18")[0] == {}


def test_book_age_reads_nanosecond_stamps_and_refuses_garbage():
    now = 1_800_000_000.0
    stamp = dt.datetime.fromtimestamp(now - 413, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + ".750000000Z"
    assert abs(live.book_age_s(stamp, now) - 412.25) < 0.06, "412.2 after rounding to a tenth: the fraction is read, not dropped (dropped would be 413.0)"
    assert live.book_age_s(None, now) is None and live.book_age_s("", now) is None
    assert live.book_age_s("garbage", now) is None
    assert live.book_age_s("2026-09-18T13:17:58Z", 1_789_000_000.0) is not None, "no fraction is fine too"


def test_live_module_is_handed_a_client_and_makes_none():
    src = pathlib.Path(live.__file__).read_text(encoding="utf-8")
    for bad in ("PolymarketGatewayClient", "PolymarketOrderClient", "place_order", "submit_limit_order",
                "create_order", "/orders", "httpx", "MERIDIAN_ORDER_TOKEN", "requests.post"):
        assert bad not in src
    assert "def slugs_for(prefix: str, engine=None)" in src


# --------------------------------------------------------------------------- #
# core.ladder.desk
# --------------------------------------------------------------------------- #

INTENT = {"ts": "23:41:07", "game": "cfb-mia-wake-2026-09-18",
          "leg1": {"market_line": 10.5, "side": "BUY YES", "price": 0.41, "qty": 2},
          "leg2": {"market_line": 7.5, "side": "BUY NO", "price": 0.53, "qty": 2},
          "displayed_size": 966.0, "edge_c": 2.1, "cost_usd": 1.88, "meridian_placed": False}


def test_default_directories_for_the_two_processes(monkeypatch, tmp_path):
    monkeypatch.setenv("LADDER_OUT", str(tmp_path))
    assert desk.default_out_dir() == str(tmp_path)
    monkeypatch.delenv("LADDER_OUT")
    assert desk.default_out_dir() in ("/out", "artifacts/reads")
    assert desk.default_out_dir() == ("/out" if os.path.isdir("/out") else "artifacts/reads")
    monkeypatch.delenv("MERIDIAN_READS_DIR", raising=False)
    assert desk.api_out_dir() == "/opt/meridian/artifacts/reads"
    monkeypatch.setenv("MERIDIAN_READS_DIR", " /srv/reads ")
    assert desk.api_out_dir() == "/srv/reads"
    monkeypatch.setenv("MERIDIAN_READS_DIR", "   ")
    assert desk.api_out_dir() == "/opt/meridian/artifacts/reads", "blank is unset, not a directory called ' '"


def test_lock_is_a_file_and_arming_removes_it(tmp_path):
    out = str(tmp_path)
    assert desk.armed(out)
    p = desk.lock(out, "the dashboard")
    assert p == os.path.join(out, "ladder_lock") and not desk.armed(out)
    desk.lock(out)                                  # a second lock appends, never truncates
    assert len(open(p, encoding="utf-8").read().splitlines()) == 2
    assert "the dashboard" in open(p, encoding="utf-8").read()
    desk.arm(out)
    assert desk.armed(out) and not os.path.exists(p)
    desk.arm(out)                                   # arming an armed desk is not an error


def test_tickets_carry_the_latest_record_and_a_torn_line_is_skipped(tmp_path):
    out = str(tmp_path)
    assert desk.load_tickets(out) == []
    with open(os.path.join(out, "ladder_intents_aec-cfb-mia-wake-2026-09-18.jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps(INTENT) + "\n{not json\n" + json.dumps({"ts": "x", "no_legs": 1}) + "\n")
    ts = desk.load_tickets(out)
    assert len(ts) == 1 and ts[0]["status"] == "open" and ts[0]["id"] == "cfb-mia-wake-2026-09-18|23:41:07|10.5/7.5"
    tid = ts[0]["id"]
    desk.record_attempt(out, tid, "placed")
    assert desk.load_tickets(out)[0]["status"] == "placed"
    desk.record_attempt(out, tid, "recorded", {"l1q": 2, "l1p": 0.41, "l1s": 4, "l2q": 2, "l2p": 0.53, "l2s": 9})
    t = desk.load_tickets(out)[0]
    assert t["status"] == "recorded" and t["record"]["l1q"] == 2 and t["record"]["l2s"] == 9
    rows = desk.read_jsonl(os.path.join(out, "ladder_attempts.jsonl"))
    assert [r["status"] for r in rows] == ["placed", "recorded"]
    assert rows[-1]["at"].endswith("+00:00")


def test_record_attempt_treats_missing_qty_as_zero_and_keeps_extras(tmp_path):
    row = desk.record_attempt(str(tmp_path), "t", "recorded", {"l1p": 0.41}, via="dashboard", venue_order_ids=["a", "b"])
    assert row["l1q"] == 0.0 and row["l2q"] == 0.0 and row["l1p"] == 0.41 and row["l2p"] is None
    assert row["via"] == "dashboard" and row["venue_order_ids"] == ["a", "b"]
    assert desk.read_jsonl(os.path.join(str(tmp_path), "ladder_attempts.jsonl")) == [row]


def _ticket(i, status, l1q=None, l2q=None, at=None):
    t = dict(INTENT, ts=f"00:00:{i:02d}", leg1=dict(INTENT["leg1"]), leg2=dict(INTENT["leg2"]))
    t["id"] = f"t{i}"
    t["status"] = status
    if status in ("placed", "recorded"):
        t["record"] = {"id": t["id"], "status": status, "at": at or f"2026-09-18T00:00:{i:02d}",
                       "l1q": l1q, "l2q": l2q}
    return t


def test_tally_is_the_registered_rule_over_the_first_five_placed():
    t = desk.tally([_ticket(i, "open") for i in range(3)])
    assert t == {"placed": 0, "recorded": 0, "both": 0, "none": 0, "open": 3,
                 "verdict": "Not yet -- needs five recorded attempts.", "issued": pytest.approx(3 * 1.88)}
    real = [_ticket(i, "recorded", 2, 2) for i in range(3)] + [_ticket(9, "placed")]
    assert desk.tally(real)["both"] == 3 and desk.tally(real)["verdict"].startswith("Displayed size is real")
    phantom = [_ticket(i, "recorded", 0, 0) for i in range(3)]
    assert desk.tally(phantom)["none"] == 3 and desk.tally(phantom)["verdict"].startswith("Resting size is phantom")
    partial = [_ticket(i, "recorded", 1, 1) for i in range(5)]       # 50% filled: neither both nor none
    assert desk.tally(partial) == dict(desk.tally(partial), both=0, none=0, recorded=5,
                                       verdict="Mixed -- extend to ten attempts before reading it.")
    # the SIXTH placed attempt is outside the rule, in placement order not file order
    six = [_ticket(i, "recorded", 2, 2, at=f"2026-09-18T01:00:{5 - i:02d}") for i in range(6)]
    tl = desk.tally(six)
    assert tl["placed"] == 5 and tl["recorded"] == 5


def test_tail_keeps_only_cycle_lines(tmp_path):
    p = tmp_path / "live_ladder_aec-cfb-mia-wake-2026-09-18.txt"
    p.write_text("live ladder prefix=...\n=== 1\n  $1.00 = ...\n=== 2\n=== 3\n=== 4\n", encoding="utf-8")
    assert desk.tail(str(p)) == ["=== 2", "=== 3", "=== 4"]
    assert desk.tail(str(p), 1) == ["=== 4"]
    assert desk.tail(str(tmp_path / "missing.txt")) == []


def test_log_files_and_recent_games_read_mtimes_not_contents(tmp_path):
    out = str(tmp_path)
    now = time.time()
    for name, age in (("live_ladder_aec-cfb-mia-wake-2026-09-18.txt", 60),
                      ("live_ladder_aec-nfl-det-buf-2026-09-17.txt", 7 * 3600),
                      ("ladder_intents_aec-cfb-hou-ttu-2026-09-18.jsonl", 600),
                      ("ws_freshness_aec-cfb-mia-wake-2026-09-18.txt", 10),
                      ("ladder_attempts.jsonl", 1)):
        p = tmp_path / name
        p.write_text("", encoding="utf-8")
        os.utime(p, (now - age, now - age))
    assert desk.recent_games(out, now=now) == ["aec-cfb-mia-wake-2026-09-18", "aec-cfb-hou-ttu-2026-09-18"]
    assert desk.recent_games(out, within_s=8 * 3600, now=now)[-1] == "aec-nfl-det-buf-2026-09-17"
    assert desk.recent_games(out, within_s=30, now=now) == [], "the freshness log is not a game listing"
    assert [os.path.basename(p) for p in desk.log_files(out, "executor")] == [
        "live_ladder_aec-cfb-mia-wake-2026-09-18.txt", "live_ladder_aec-nfl-det-buf-2026-09-17.txt"]
    assert [os.path.basename(p) for p in desk.log_files(out, "freshness")] == ["ws_freshness_aec-cfb-mia-wake-2026-09-18.txt"]
    assert desk.log_files(out, "executor", last=1) == [os.path.join(out, "live_ladder_aec-nfl-det-buf-2026-09-17.txt")]
    with pytest.raises(KeyError):
        desk.log_files(out, "orders")


def test_desk_module_has_no_venue_call():
    src = pathlib.Path(desk.__file__).read_text(encoding="utf-8")
    for bad in ("PolymarketGatewayClient", "PolymarketOrderClient", "place_order", "create_order", "/orders",
                "httpx", "MERIDIAN_ORDER_TOKEN", "api.polymarket", "urllib"):
        assert bad not in src
