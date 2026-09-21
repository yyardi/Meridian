"""The ARB tab's routes and rules, without a database or a venue.

What is pinned here: the state route is file-backed and never a 500; the
ladder route serves the sampler's cache and never calls the venue; the
dominance bounds and the fee-netted violation on a fixture ladder; every
gate on SEND that runs before the first row is written, in the order the
module lists them; the synchronous-reply parser on the shapes the venue doc
describes; and the fill watcher's new average-price read.

The gates that need the orders table (the idempotency rows, the venue's
answer on the row, the unwind) are in tests/test_arb_send.py.
"""
from __future__ import annotations

import ast
import datetime as dt
import inspect
import json
import os
import pathlib
import re
import sys
import time
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core import api as api_module  # noqa: E402
from core import fill_watcher as fw  # noqa: E402
from core.ladder import desk  # noqa: E402

GAME = "cfb-mia-wake-2026-09-18"
PREFIX = "aec-" + GAME
SLUGS = [PREFIX, f"asc-{GAME}-pos-10pt5", f"asc-{GAME}-pos-7pt5", f"asc-{GAME}-neg-3pt5"]
INTENT = {"ts": "23:41:07", "game": GAME,
          "leg1": {"market_line": 10.5, "side": "BUY YES", "price": 0.41, "qty": 2},
          "leg2": {"market_line": 7.5, "side": "BUY NO", "price": 0.53, "qty": 2},
          "displayed_size": 966.0, "edge_c": 3.05, "cost_usd": 1.88, "meridian_placed": False}
TICKET_ID = f"{GAME}|23:41:07|10.5/7.5"
TOKEN = {"X-Meridian-Order-Token": "test-token"}

#: Four rungs, one fee-netted violation: 7.5 bids 0.47 while 10.5 asks 0.41.
RUNGS = {3.5: (0.30, 0.32, 100.0, 50.0), 7.5: (0.47, 0.49, 966.0, 40.0),
         10.5: (0.40, 0.41, 20.0, 966.0), 13.5: (0.60, 0.62, 10.0, 10.0)}


def _legs(**over) -> list[dict]:
    legs = [{"market_slug": SLUGS[1], "side": "BUY YES", "cost_price": "0.41", "quantity": "2"},
            {"market_slug": SLUGS[2], "side": "BUY NO", "cost_price": "0.53", "quantity": "2"}]
    for k, v in over.items():
        n, field = int(k[1]) - 1, k[3:]         # l1_cost_price -> legs[0]["cost_price"]
        legs[n][field] = v
    return legs


def _send_body(**over) -> dict:
    body = {"ticket_id": TICKET_ID, "mode": "HUMAN_CONFIRM", "legs": _legs(), "acknowledge": True}
    body.update(over)
    return body


@pytest.fixture
def reads(tmp_path, monkeypatch):
    monkeypatch.setenv("MERIDIAN_READS_DIR", str(tmp_path))
    (tmp_path / f"ladder_intents_{PREFIX}.jsonl").write_text(json.dumps(INTENT) + "\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("MERIDIAN_ORDER_TOKEN", "test-token")
    return TestClient(api_module.app)


@pytest.fixture
def no_db_no_venue(monkeypatch):
    """The recorder's slug listing and the bankroll are the two things the
    send reads before the first row; both stubbed so nothing here connects."""
    import core.bankroll as bk

    monkeypatch.setattr(api_module, "slugs_for", lambda game, engine=None: list(SLUGS))

    def _unavailable(*_a, **_k):
        raise bk.BankrollUnavailable("stubbed")
    monkeypatch.setattr(bk, "current", _unavailable)
    monkeypatch.setattr(api_module, "_arb_ensure_sampler", lambda: None)
    monkeypatch.setitem(api_module._ARB_LADDER, "cache", {})
    monkeypatch.setitem(api_module._ARB_LADDER, "watch", {})


# --------------------------------------------------------------------------- #
# Routes exist, and the api still imports nothing from cfb/
# --------------------------------------------------------------------------- #

def test_every_arb_route_is_declared():
    paths = {r.path for r in api_module.app.routes if hasattr(r, "methods")}
    assert {"/arb", "/api/arb/state", "/api/arb/ladder", "/api/arb/lock", "/api/arb/arm",
            "/api/arb/record", "/api/arb/send", "/api/arb/unwind"} <= paths
    assert {r.path for r in api_module.app.routes if hasattr(r, "methods") and "GET" in r.methods
            } >= {"/arb", "/api/arb/state", "/api/arb/ladder"}


def test_the_api_never_imports_cfb():
    """The api image COPYs core/ and not cfb/: an import of cfb.* is a
    container that dies at start-up."""
    tree = ast.parse(pathlib.Path(api_module.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("cfb"), node.module
        if isinstance(node, ast.Import):
            assert not any(a.name.startswith("cfb") for a in node.names)


def test_the_ladder_handler_serves_the_cache_and_never_samples():
    src = inspect.getsource(api_module.arb_ladder)
    for bad in ("get_book", "sample(", "PolymarketGatewayClient", "slugs_for"):
        assert bad not in src
    assert "_ARB_LADDER[\"cache\"]" in src


def test_send_uses_the_arb_payload_and_writes_rows_before_the_venue():
    src = inspect.getsource(api_module.arb_send)
    assert src.count("to_payload(post_only=False, tif=ARB_TIF, synchronous=True)") == 2
    assert src.index("s.add_all(rows)") < src.index("submit_limit_order(payload1)")
    assert src.index("submit_limit_order(payload1)") < src.index("submit_limit_order(payload2)")
    # every gate before the first row, in the module's order
    order = ["_require_order_token", "_arb_require_mode", "_arb_resolve_ticket", '!= "open"',
             "_arb_check_legs", "_arb_check_stakes", "req.acknowledge", "_ladder_desk.armed",
             "leg 1\")).first() is not None", "s.add_all(rows)"]
    positions = [src.index(name) for name in order]
    assert positions == sorted(positions), order


def test_status_reports_the_cfb_quote_engine_overlay():
    src = inspect.getsource(api_module.status)
    assert '"quote_engine_cfb"' in src and '"quote_engine_nfl"' in src


# --------------------------------------------------------------------------- #
# /api/arb/state
# --------------------------------------------------------------------------- #

def test_state_without_the_directory_is_unavailable_not_500(client, monkeypatch, tmp_path):
    monkeypatch.setenv("MERIDIAN_READS_DIR", str(tmp_path / "absent"))
    body = client.get("/api/arb/state").json()
    assert body["available"] is False and body["dir"].endswith("absent")


def test_state_reads_the_desk_files(client, reads):
    now = time.time()
    log = reads / f"live_ladder_{PREFIX}.txt"
    log.write_text("live ladder\n=== 1\n  x\n=== 2\n", encoding="utf-8")
    desk.record_attempt(str(reads), TICKET_ID, "placed")
    body = client.get("/api/arb/state").json()
    assert body["available"] is True and body["armed"] is True
    assert body["games"] == [PREFIX]
    t = body["tickets"][0]
    assert t["id"] == TICKET_ID and t["status"] == "placed" and t["sendable"] is False
    assert t["leg1"]["screen_row"] == "WAKE to win by over 10.5 points" and t["leg1"]["screen_button"] == "No"
    assert t["leg2"]["screen_row"] == "WAKE to win by over 7.5 points" and t["leg2"]["screen_button"] == "Yes"
    assert body["tally"]["placed"] == 1 and body["tally"]["issued"] == pytest.approx(1.88)
    assert body["tails"]["executor"] == [{"file": log.name, "lines": ["=== 1", "=== 2"]}]
    assert body["tails"]["freshness"] == []
    assert body["filters"]["floor_usd"] == 25.0 and body["filters"]["spread_only"] is True
    assert body["max_pair_usd"] == 25.0 and body["allow_size_up"] is False
    assert abs(now - time.time()) < 5


def test_an_open_spread_ticket_is_sendable_and_a_winner_leg_is_not(client, reads):
    assert client.get("/api/arb/state").json()["tickets"][0]["sendable"] is True
    winner = dict(INTENT, ts="23:50:00", leg2=dict(INTENT["leg2"], market_line=0.0))
    with open(reads / f"ladder_intents_{PREFIX}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(winner) + "\n")
    by_ts = {t["ts"]: t for t in client.get("/api/arb/state").json()["tickets"]}
    assert by_ts["23:50:00"]["sendable"] is False and by_ts["23:50:00"]["spread_pair"] is False


# --------------------------------------------------------------------------- #
# The ladder rendering: bounds, flags, the violation and its ticket
# --------------------------------------------------------------------------- #

def test_bounds_are_max_harder_bid_and_min_easier_ask():
    now = 1_800_000_000.0
    snap = api_module._arb_ladder_snapshot(GAME, RUNGS, {}, 1.2, now)
    b = snap["bounds"]
    assert b["3.5"] == {"lo": None, "hi": 0.41}
    assert b["7.5"] == {"lo": 0.30, "hi": 0.41}
    assert b["10.5"] == {"lo": 0.47, "hi": 0.62}
    assert b["13.5"] == {"lo": 0.47, "hi": None}
    r = snap["rungs"]
    assert r["10.5"]["flags"] == ["ask below a harder rung's bid"]
    assert r["7.5"]["flags"] == ["bid above an easier rung's ask"]
    assert r["3.5"]["flags"] == [] and r["13.5"]["flags"] == []
    assert r["10.5"]["row"] == "WAKE to win by over 10.5 points"
    assert r["3.5"]["age_s"] is None and r["3.5"]["tt"] is None
    assert snap["n_rungs"] == 4 and snap["took_s"] == 1.2 and snap["available"] is True


def test_the_one_violation_carries_the_executors_ticket():
    now = 1_800_000_000.0
    stamp = dt.datetime.fromtimestamp(now - 90, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + ".000000000Z"
    snap = api_module._arb_ladder_snapshot(GAME, RUNGS, {10.5: stamp}, 0.9, now)
    assert snap["rungs"]["10.5"]["age_s"] == pytest.approx(90.0, abs=0.2)
    assert len(snap["violations"]) == 1
    v = snap["violations"][0]
    assert (v["high_line"], v["low_line"]) == (10.5, 7.5)
    assert v["edge_c"] == pytest.approx(3.05, abs=0.01) and v["size"] == 966.0
    assert v["dollars"] == pytest.approx(29.5, abs=0.05)
    assert v["candidate"] is True and v["mid_ladder"] is True and v["spread_pair"] is True
    t = v["ticket"]
    assert t["leg1"] == {"market_line": 10.5, "side": "BUY YES", "price": 0.41, "qty": 1,
                         "screen_row": "WAKE to win by over 10.5 points", "screen_button": "No"}
    assert t["leg2"]["market_line"] == 7.5 and t["leg2"]["side"] == "BUY NO" and t["leg2"]["price"] == 0.53
    assert t["cost_usd"] == pytest.approx(0.94) and t["game"] == GAME
    assert snap["best_per_game"] == {GAME: pytest.approx(29.5, abs=0.05)}


def test_a_clean_ladder_has_no_violation_and_no_flags():
    clean = {3.5: (0.30, 0.32, 1, 1), 7.5: (0.40, 0.42, 1, 1), 10.5: (0.50, 0.52, 1, 1)}
    snap = api_module._arb_ladder_snapshot(GAME, clean, {}, 0.5, 1_800_000_000.0)
    assert snap["violations"] == [] and snap["best_per_game"] == {}
    assert all(r["flags"] == [] for r in snap["rungs"].values())


def test_a_sub_floor_or_winner_pair_is_a_violation_but_not_a_candidate():
    tiny = {7.5: (0.47, 0.49, 3.0, 40.0), 10.5: (0.40, 0.41, 20.0, 3.0)}
    v = api_module._arb_ladder_snapshot(GAME, tiny, {}, 0.5, 1_800_000_000.0)["violations"][0]
    assert v["dollars"] < 25 and v["candidate"] is False and v["spread_pair"] is True
    winner = {0.0: (0.47, 0.49, 900.0, 900.0), 2.5: (0.40, 0.41, 900.0, 900.0)}
    v = api_module._arb_ladder_snapshot(GAME, winner, {}, 0.5, 1_800_000_000.0)["violations"][0]
    assert v["dollars"] > 25 and v["spread_pair"] is False and v["candidate"] is False


# --------------------------------------------------------------------------- #
# /api/arb/ladder: the cache, the watch, never the venue
# --------------------------------------------------------------------------- #

def test_ladder_registers_a_watch_and_reports_pending_then_serves_the_cache(client, no_db_no_venue):
    body = client.get("/api/arb/ladder", params={"game": GAME}).json()
    assert body["available"] is False and body["reason"] == "first sample pending"
    assert body["prefix"] == PREFIX and PREFIX in api_module._ARB_LADDER["watch"]
    # 45 s, not 30 min: the page re-asks every 5 s while the game is on
    # screen, and a 30-minute watch is what turned an NFL Sunday into a
    # serial minute-long sampler rotation (tests/test_arb_sampler_latency.py).
    assert time.time() + 30 < body["watching_until"] < time.time() + 120
    snap = api_module._arb_ladder_snapshot(GAME, RUNGS, {}, 1.0, time.time() - 4)
    api_module._ARB_LADDER["cache"][PREFIX] = snap
    body = client.get("/api/arb/ladder", params={"game": PREFIX}).json()
    assert body["available"] is True and 3.5 <= body["age_s"] <= 6
    assert body["rungs"]["10.5"]["flags"] and body["sample_seconds"] == 10.0


def test_ladder_refuses_a_non_game(client, no_db_no_venue):
    assert client.get("/api/arb/ladder", params={"game": "not a game"}).status_code == 422
    assert client.get("/api/arb/ladder").status_code == 422


def test_sample_seconds_comes_from_the_env_with_a_floor(monkeypatch):
    monkeypatch.setenv("MERIDIAN_ARB_SAMPLE_SECONDS", "4")
    assert api_module._arb_sample_seconds() == 4.0
    monkeypatch.setenv("MERIDIAN_ARB_SAMPLE_SECONDS", "0.1")
    assert api_module._arb_sample_seconds() == 2.0
    monkeypatch.setenv("MERIDIAN_ARB_SAMPLE_SECONDS", "ten")
    assert api_module._arb_sample_seconds() == 10.0


def test_sample_one_writes_the_cache_for_a_sample_an_empty_listing_and_a_failure(monkeypatch):
    """The sampler thread's body, run inline with the venue and the recorder
    stubbed: a sample becomes a rendered snapshot, a game with no recorded
    rungs becomes a reason, and a raising venue becomes a reason -- never an
    exception out of the thread."""
    monkeypatch.setitem(api_module._ARB_LADDER, "cache", {})
    monkeypatch.setitem(api_module._ARB_LADDER, "slugs", {})
    monkeypatch.setattr(api_module, "slugs_for", lambda game, engine=None: list(SLUGS))
    # The api passes on_error so a failed rung is a structlog warning, not a
    # print on the container's stdout; the stub must accept it.
    monkeypatch.setattr(api_module, "sample",
                        lambda client, slugs, prefix, meta, on_error=None: (dict(RUNGS), 0.3))
    api_module._arb_sample_one(object(), PREFIX)
    snap = api_module._ARB_LADDER["cache"][PREFIX]
    assert snap["available"] is True and snap["n_slugs"] == 4 and snap["took_s"] == 0.3
    assert snap["violations"][0]["ticket"]["game"] == GAME and snap["prefix"] == PREFIX

    def _boom(client, slugs, prefix, meta, on_error=None):
        raise RuntimeError("venue down")
    monkeypatch.setattr(api_module, "sample", _boom)
    api_module._arb_sample_one(object(), PREFIX)
    snap = api_module._ARB_LADDER["cache"][PREFIX]
    assert snap["available"] is False and "venue down" in snap["reason"]

    monkeypatch.setitem(api_module._ARB_LADDER, "slugs", {})
    monkeypatch.setattr(api_module, "slugs_for", lambda game, engine=None: [])
    api_module._arb_sample_one(object(), PREFIX)
    assert "no rungs recorded" in api_module._ARB_LADDER["cache"][PREFIX]["reason"]


def test_expired_watches_are_dropped():
    api_module._ARB_LADDER["watch"] = {"aec-old-1": time.time() - 1, "aec-new-1": time.time() + 100}
    assert api_module._arb_watched(time.time()) == ["aec-new-1"]
    api_module._ARB_LADDER["watch"] = {}


# --------------------------------------------------------------------------- #
# Lock, arm, record: token-gated, the desk's own files
# --------------------------------------------------------------------------- #

def test_lock_and_arm_need_the_token_and_write_the_executors_lock_file(client, reads):
    assert client.post("/api/arb/lock").status_code == 403
    assert client.post("/api/arb/arm").status_code == 403
    r = client.post("/api/arb/lock", headers=TOKEN)
    assert r.status_code == 200 and r.json()["armed"] is False
    assert (reads / "ladder_lock").exists() and "the dashboard" in (reads / "ladder_lock").read_text()
    assert client.get("/api/arb/state").json()["armed"] is False
    assert client.post("/api/arb/arm", headers=TOKEN).json()["armed"] is True
    assert not (reads / "ladder_lock").exists()


def test_record_writes_the_attempts_file_the_desk_reads(client, reads):
    body = {"ticket_id": TICKET_ID, "status": "placed"}
    assert client.post("/api/arb/record", json=body).status_code == 403
    assert client.post("/api/arb/record", json=body, headers=TOKEN).status_code == 200
    assert desk.load_tickets(str(reads))[0]["status"] == "placed"
    fills = {"l1q": 2, "l1p": 0.41, "l1s": 3, "l2q": 0, "l2p": None, "l2s": None}
    r = client.post("/api/arb/record", json={"ticket_id": TICKET_ID, "status": "recorded", "fills": fills},
                    headers=TOKEN)
    # A hand record is marked as the desk's, never as the send's: the page
    # offers UNWIND and says "sent from this page" only on the send's mark,
    # and a phone-placed ticket has no rows to sell from.
    assert r.status_code == 200 and r.json()["record"]["via"] == api_module._ARB_VIA_DESK
    assert r.json()["record"]["via"] != api_module._ARB_VIA_SEND
    t = desk.load_tickets(str(reads))[0]
    assert t["status"] == "recorded" and t["record"]["l1q"] == 2 and t["record"]["l2q"] == 0
    assert client.post("/api/arb/record", json={"ticket_id": TICKET_ID, "status": "reopen"},
                       headers=TOKEN).json()["status"] == "open"
    assert desk.load_tickets(str(reads))[0]["status"] == "open"


def test_record_refuses_an_unknown_ticket_a_bad_status_and_fills_less_recorded(client, reads):
    assert client.post("/api/arb/record", json={"ticket_id": "nope", "status": "placed"},
                       headers=TOKEN).status_code == 404
    assert client.post("/api/arb/record", json={"ticket_id": TICKET_ID, "status": "sent"},
                       headers=TOKEN).status_code == 422
    assert client.post("/api/arb/record", json={"ticket_id": TICKET_ID, "status": "recorded"},
                       headers=TOKEN).status_code == 422
    assert client.post("/api/arb/record", json={"ticket_id": TICKET_ID, "status": "placed", "x": 1},
                       headers=TOKEN).status_code == 422


# --------------------------------------------------------------------------- #
# SEND: every gate before the first row, in order
# --------------------------------------------------------------------------- #

def test_send_without_token_is_403_before_anything_is_read(client, monkeypatch, tmp_path):
    monkeypatch.setenv("MERIDIAN_READS_DIR", str(tmp_path / "absent"))
    assert client.post("/api/arb/send", json=_send_body()).status_code == 403


def test_send_refuses_every_mode_but_the_literal(client, reads, no_db_no_venue):
    for mode in ("SHADOW", "human_confirm", "AUTONOMOUS", ""):
        r = client.post("/api/arb/send", json=_send_body(mode=mode), headers=TOKEN)
        assert r.status_code == 403 and "HUMAN_CONFIRM" in r.json()["detail"]


def test_send_refuses_a_ticket_the_executor_did_not_write(client, reads, no_db_no_venue):
    r = client.post("/api/arb/send", json=_send_body(ticket_id=f"{GAME}|00:00:00|10.5/7.5"), headers=TOKEN)
    assert r.status_code == 404


def test_a_ticket_that_left_open_is_refused_before_its_legs_are_read(client, reads, no_db_no_venue):
    """Placed by hand, skipped, or recorded: the desk's record closes the
    ticket, and SEND refuses it before looking at the legs (a garbage slug
    would be a 422 past this gate). The operator's reopen puts it back."""
    garbage = _send_body(legs=_legs(l1_market_slug="garbage"))
    for status in ("placed", "skipped", "recorded"):
        desk.record_attempt(str(reads), TICKET_ID, status)
        r = client.post("/api/arb/send", json=garbage, headers=TOKEN)
        assert r.status_code == 409 and "not open" in r.json()["detail"], status
    desk.record_attempt(str(reads), TICKET_ID, "open")
    assert client.post("/api/arb/send", json=garbage, headers=TOKEN).status_code == 422


def test_the_arb_page_answers_404_not_500_without_its_file(client, monkeypatch, tmp_path):
    monkeypatch.setattr(api_module, "STATIC", tmp_path)
    assert client.get("/arb").status_code == 404
    (tmp_path / "arb.html").write_text("<html><header id=\"lgtabs\"></header></html>", encoding="utf-8")
    assert client.get("/arb").status_code == 200


def test_send_refuses_extra_fields_and_a_one_leg_ticket(client, reads, no_db_no_venue):
    assert client.post("/api/arb/send", json=_send_body(size=1), headers=TOKEN).status_code == 422
    assert client.post("/api/arb/send", json=_send_body(legs=_legs()[:1]), headers=TOKEN).status_code == 422


@pytest.mark.parametrize("over, fragment", [
    ({"l1_market_slug": SLUGS[2]}, "not the ticket's line"),
    ({"l2_market_slug": f"asc-{GAME}-pos-7pt5-x"}, "not the ticket's line"),
    ({"l1_side": "BUY NO"}, "not the ticket's"),
    ({"l2_side": "SELL NO"}, "must be BUY YES or BUY NO"),
    ({"l1_cost_price": "0.43"}, "more than 0.01 from the ticket's"),
    ({"l2_cost_price": "0.51"}, "more than 0.01 from the ticket's"),
    ({"l1_cost_price": "0.415"}, "not on the 1"),
    ({"l1_cost_price": "1.00"}, "outside the venue"),
    ({"l1_quantity": "3"}, "exceeds the ticket's 2"),
    ({"l2_quantity": "0.001"}, "below the venue minimum"),
])
def test_send_refuses_a_leg_that_is_not_the_tickets(client, reads, no_db_no_venue, over, fragment):
    r = client.post("/api/arb/send", json=_send_body(legs=_legs(**over)), headers=TOKEN)
    assert r.status_code == 422, r.text
    assert fragment in r.json()["detail"], r.json()["detail"]


def test_a_one_tick_nudge_passes_the_price_gate(client, reads, no_db_no_venue):
    """0.42 against a 0.41 ticket is a nudge; the request then fails on the
    NEXT gate (the lock), which proves the price gate let it through."""
    desk.lock(str(reads))
    r = client.post("/api/arb/send", json=_send_body(legs=_legs(l1_cost_price="0.42")), headers=TOKEN)
    assert r.status_code == 409 and "LOCKED" in r.json()["detail"]


def test_size_up_needs_the_env_and_is_capped_by_displayed_size(client, reads, no_db_no_venue, monkeypatch):
    body = _send_body(legs=_legs(l1_quantity="20", l2_quantity="20"))
    r = client.post("/api/arb/send", json=body, headers=TOKEN)
    assert r.status_code == 422 and "ALLOW_SIZE_UP" in r.json()["detail"]
    monkeypatch.setenv("MERIDIAN_ARB_ALLOW_SIZE_UP", "1")
    desk.lock(str(reads))
    r = client.post("/api/arb/send", json=body, headers=TOKEN)
    assert r.status_code == 409, r.text                         # past the size gate, stopped by the lock
    body = _send_body(legs=_legs(l1_quantity="967", l2_quantity="967"))
    r = client.post("/api/arb/send", json=body, headers=TOKEN)
    assert r.status_code == 422 and "exceeds the ticket's 966" in r.json()["detail"]


def test_the_pair_stake_is_capped_by_the_pair_cap_or_the_account(client, reads, no_db_no_venue, monkeypatch):
    monkeypatch.setenv("MERIDIAN_ARB_ALLOW_SIZE_UP", "1")
    body = _send_body(legs=_legs(l1_quantity="30", l2_quantity="30"))     # 12.30 + 15.90 = 28.20
    r = client.post("/api/arb/send", json=body, headers=TOKEN)
    assert r.status_code == 422 and "pair stake $28.20 exceeds $25" in r.json()["detail"]
    monkeypatch.setenv("MERIDIAN_ARB_MAX_PAIR_USD", "10")
    body = _send_body(legs=_legs(l1_quantity="25", l2_quantity="2"))      # leg 1 alone 10.25
    r = client.post("/api/arb/send", json=body, headers=TOKEN)
    assert r.status_code == 422 and "leg 1 stake $10.25 exceeds the per-leg cap $10" in r.json()["detail"]


def test_a_raised_pair_cap_cannot_lift_one_leg_over_the_per_order_cap(client, reads, no_db_no_venue, monkeypatch):
    """MERIDIAN_ARB_MAX_PAIR_USD=100 with the per-order fat-finger cap at $25:
    a $30.75 leg is refused as /api/orders/confirm would refuse the same
    order, and the detail names the env that did it."""
    monkeypatch.setenv("MERIDIAN_ARB_ALLOW_SIZE_UP", "1")
    monkeypatch.setenv("MERIDIAN_ARB_MAX_PAIR_USD", "100")
    monkeypatch.setenv("MERIDIAN_MAX_ORDER_STAKE_USD", "25")
    body = _send_body(legs=_legs(l1_quantity="75", l2_quantity="2"))      # leg 1 alone 30.75
    r = client.post("/api/arb/send", json=body, headers=TOKEN)
    assert r.status_code == 422
    assert "per-leg cap $25" in r.json()["detail"] and "MERIDIAN_MAX_ORDER_STAKE_USD" in r.json()["detail"]


def test_a_pair_whose_cost_plus_fees_reaches_a_dollar_is_refused(client, reads, no_db_no_venue):
    """One tick of slack per leg on a thin ticket: 0.42 + 0.54 = 0.96 plus the
    scanner's taker fees at those prices is not under $1.00, so both legs
    filled at the limits would lock a loss. The nudged pair passes every
    per-leg gate and is refused on the pair."""
    intent = dict(INTENT, ts="23:55:00", leg1=dict(INTENT["leg1"], price=0.47),
                  leg2=dict(INTENT["leg2"], price=0.51))
    with open(reads / f"ladder_intents_{PREFIX}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(intent) + "\n")
    tid = f"{GAME}|23:55:00|10.5/7.5"
    body = _send_body(ticket_id=tid, legs=_legs(l1_cost_price="0.48", l2_cost_price="0.52"))
    r = client.post("/api/arb/send", json=body, headers=TOKEN)
    assert r.status_code == 422 and "not under $1.00" in r.json()["detail"]
    # The pure bound: cost 1.00 is refused before fees; 0.94 with fees clears.
    cost, fees = api_module._arb_pair_cost_bound([Decimal("0.48"), Decimal("0.52")])
    assert cost == Decimal("1.00") and fees > 0
    cost, fees = api_module._arb_pair_cost_bound([Decimal("0.41"), Decimal("0.53")])
    assert cost + fees < Decimal("1")


def test_the_account_caps_the_pair_when_it_is_smaller(client, reads, no_db_no_venue, monkeypatch):
    from types import SimpleNamespace

    import core.bankroll as bk

    monkeypatch.setattr(bk, "current", lambda **_k: SimpleNamespace(bankroll=Decimal("1.50")))
    r = client.post("/api/arb/send", json=_send_body(), headers=TOKEN)          # 0.82 + 1.06 = 1.88
    assert r.status_code == 422 and "the account balance" in r.json()["detail"]


def test_acknowledge_then_the_lock_are_the_last_gates_before_a_row(client, reads, no_db_no_venue):
    r = client.post("/api/arb/send", json=_send_body(acknowledge=False), headers=TOKEN)
    assert r.status_code == 422 and "acknowledge" in r.json()["detail"]
    desk.lock(str(reads))
    r = client.post("/api/arb/send", json=_send_body(), headers=TOKEN)
    assert r.status_code == 409 and "LOCKED" in r.json()["detail"]


def test_a_winner_leg_ticket_is_refused_even_if_the_executor_wrote_it(client, reads, no_db_no_venue):
    winner = dict(INTENT, ts="23:50:00", leg2=dict(INTENT["leg2"], market_line=0.0))
    with open(reads / f"ladder_intents_{PREFIX}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(winner) + "\n")
    body = _send_body(ticket_id=f"{GAME}|23:50:00|10.5/0.0", legs=_legs(l2_market_slug=PREFIX))
    r = client.post("/api/arb/send", json=body, headers=TOKEN)
    assert r.status_code == 422 and "winner market" in r.json()["detail"]


def test_unwind_gates_before_the_database(client, reads, no_db_no_venue):
    body = {"ticket_id": TICKET_ID, "mode": "HUMAN_CONFIRM", "leg": 1, "acknowledge": True}
    assert client.post("/api/arb/unwind", json=body).status_code == 403
    assert client.post("/api/arb/unwind", json=dict(body, mode="SHADOW"), headers=TOKEN).status_code == 403
    assert client.post("/api/arb/unwind", json=dict(body, acknowledge=False), headers=TOKEN).status_code == 422
    assert client.post("/api/arb/unwind", json=dict(body, leg=3), headers=TOKEN).status_code == 422
    assert client.post("/api/arb/unwind", json=dict(body, ticket_id="nope"), headers=TOKEN).status_code == 404
    assert client.post("/api/arb/unwind", json=dict(body, limit_cost_price="0.415"),
                       headers=TOKEN).status_code == 422


# --------------------------------------------------------------------------- #
# The pure pieces of the send
# --------------------------------------------------------------------------- #

def test_decided_at_is_the_games_date_plus_the_tickets_clock():
    when = api_module._arb_decided_at(INTENT)
    assert when == dt.datetime(2026, 9, 18, 23, 41, 7, tzinfo=dt.timezone.utc)
    assert api_module._arb_decided_at(dict(INTENT, ts="garbage")).time() == dt.time(0)
    assert api_module._arb_decided_at(dict(INTENT, game="x")).date() == dt.datetime.now(dt.timezone.utc).date()


def _sync(order_id, state, cum, avg=None, last=None, extra_execs=()):
    ex = {"id": f"E-{order_id}", "order": {"id": order_id, "state": state, "cumQuantity": cum,
                                          "leavesQuantity": 0}}
    if avg is not None:
        ex["avgPx"] = {"value": str(avg)}
    if last is not None:
        ex["lastPx"], ex["lastShares"] = {"value": str(last[0])}, str(last[1])
    return json.dumps({"orderId": order_id, "executions": [ex, *extra_execs]})


def test_parse_sync_reads_id_state_max_cum_and_avg():
    p = api_module._arb_parse_sync(_sync("v-1", "ORDER_STATE_FILLED", 2, avg="0.41"))
    assert p == {"venue_id": "v-1", "state": "ORDER_STATE_FILLED", "filled": Decimal("2"),
                 "avg_yes": Decimal("0.41"), "executions": 1,
                 "avg_reported": Decimal("0.41"), "avg_vwap": None}
    # two executions: the max cumQuantity wins, never the sum of shares
    first = {"order": {"id": "v-2", "state": "ORDER_STATE_PARTIALLY_FILLED", "cumQuantity": 1},
             "lastPx": {"value": "0.40"}, "lastShares": "1"}
    p = api_module._arb_parse_sync(_sync("v-2", "ORDER_STATE_FILLED", 2, last=("0.42", 1), extra_execs=[first]))
    assert p["filled"] == Decimal("2") and p["state"] == "ORDER_STATE_FILLED"
    assert p["avg_yes"] == Decimal("0.4100"), "VWAP of lastPx x lastShares when avgPx is absent"


def test_parse_sync_on_a_zero_fill_a_rejection_and_garbage():
    p = api_module._arb_parse_sync(_sync("v-3", "ORDER_STATE_CANCELED", 0))
    assert p["filled"] == Decimal("0") and p["avg_yes"] is None and p["venue_id"] == "v-3"
    p = api_module._arb_parse_sync('{"code":3,"message":"price out of range"}')
    assert p == {"venue_id": None, "state": None, "filled": Decimal("0"), "avg_yes": None, "executions": 0,
                 "avg_reported": None, "avg_vwap": None}
    p = api_module._arb_parse_sync("<html>bad gateway</html>")
    assert p["filled"] == Decimal("0") and p["venue_id"] is None
    p = api_module._arb_parse_sync('{"id":"v-4","state":"ORDER_STATE_NEW","cumQuantity":"0"}')
    assert p["venue_id"] == "v-4" and p["state"] == "ORDER_STATE_NEW" and p["filled"] == Decimal("0")


def test_fill_status_agrees_with_the_fill_watcher_mapping():
    st = api_module._arb_fill_status
    assert st({"state": "ORDER_STATE_FILLED", "filled": Decimal("2")}, Decimal("2")) == fw.FILLED
    assert st({"state": "ORDER_STATE_PARTIALLY_FILLED", "filled": Decimal("1")}, Decimal("2")) == fw.PARTIAL
    assert st({"state": "ORDER_STATE_CANCELED", "filled": Decimal("1")}, Decimal("2")) == fw.CANCELLED
    assert st({"state": "ORDER_STATE_NEW", "filled": Decimal("0")}, Decimal("2")) == fw.OPEN
    assert st({"state": None, "filled": Decimal("2")}, Decimal("2")) == fw.FILLED
    assert st({"state": None, "filled": Decimal("1")}, Decimal("2")) == fw.PARTIAL
    assert st({"state": None, "filled": Decimal("0")}, Decimal("2")) is None


def _leg(n, filled, cost, sent=True, avg=None, error=None):
    return {"leg": n, "sent": sent, "filled_quantity": filled, "avg_cost_price": avg,
            "limit_cost_price": cost, "side": "BUY YES" if n == 1 else "BUY NO",
            "line": 10.5 if n == 1 else 7.5, "error": error}


def test_pair_summary_names_the_one_way_to_lose():
    both = api_module._arb_pair_summary([_leg(1, 2.0, 0.41), _leg(2, 2.0, 0.53)])
    assert both["outcome"] == "both legs filled" and both["paired_quantity"] == 2.0
    assert both["cost_usd_filled"] == pytest.approx(1.88) and both["guaranteed_usd"] == pytest.approx(0.12)
    lost = api_module._arb_pair_summary([_leg(1, 2.0, 0.41), _leg(2, 0.0, 0.53)])
    assert lost["outcome"] == "leg 1 filled, leg 2 unfilled" and "UNWIND" in lost["note"]
    assert lost["guaranteed_usd"] == 0.0 and lost["cost_usd_filled"] == pytest.approx(0.82)
    none = api_module._arb_pair_summary([_leg(1, 0.0, 0.41), _leg(2, 0.0, 0.53, sent=False, error="leg 1 unfilled")])
    assert none["outcome"] == "leg 1 unfilled" and none["cost_usd_filled"] == 0.0
    part = api_module._arb_pair_summary([_leg(1, 2.0, 0.41, avg=0.40), _leg(2, 1.0, 0.53, avg=0.52)])
    assert part["outcome"] == "partially paired" and part["paired_quantity"] == 1.0
    assert part["pair_cost"] == pytest.approx(0.92) and part["guaranteed_usd"] == pytest.approx(0.08)
    unsent = api_module._arb_pair_summary([_leg(1, 2.0, 0.41), _leg(2, 0.0, 0.53, sent=False, error="transport error: x")])
    assert unsent["outcome"] == "leg 1 filled, leg 2 unsent"


# --------------------------------------------------------------------------- #
# The fill watcher's new read: avgPx
# --------------------------------------------------------------------------- #

def test_the_watcher_reads_avg_px_when_present_and_leaves_none_otherwise():
    ex = {"id": "E", "order": {"id": "v-9", "state": "ORDER_STATE_FILLED", "cumQuantity": 1.46},
          "lastShares": "1", "transactTime": "2026-09-18T02:05:51.436320896Z", "avgPx": {"value": "0.2150"}}
    events, _, ok = fw.extract_order_events({"type": "ACTIVITY_TYPE_TRADE", "trade": {"passiveExecution": ex}})
    assert ok and events[0].avg_price == Decimal("0.2150")
    assert fw.reconcile_order(events) == (fw.FILLED, Decimal("1.46")), "the (status, filled) contract is unchanged"
    assert fw.latest_avg_price(events) == Decimal("0.2150")
    del ex["avgPx"]
    events, _, _ = fw.extract_order_events({"type": "ACTIVITY_TYPE_TRADE", "trade": {"passiveExecution": ex}})
    assert events[0].avg_price is None and fw.latest_avg_price(events) is None
    assert fw.latest_avg_price([]) is None
    ex["order"]["avgPx"] = {"value": "0.2200"}
    events, _, _ = fw.extract_order_events({"type": "ACTIVITY_TYPE_TRADE", "trade": {"passiveExecution": ex}})
    assert events[0].avg_price == Decimal("0.2200"), "the embedded order's avgPx is the fallback"
    older = fw.OrderEvent("v-9", "ORDER_STATE_PARTIALLY_FILLED", Decimal("1"),
                          "2026-09-18T01:00:00.000000000Z", Decimal("0.2000"))
    assert fw.latest_avg_price([older, events[0]]) == Decimal("0.2200"), "the latest execution's price"


def test_orders_row_has_the_avg_fill_price_column_and_the_migration_adds_it_safely():
    from core.storage import PlacedOrder

    assert "avg_fill_price" in PlacedOrder.__table__.columns
    root = pathlib.Path(__file__).resolve().parents[1]
    mig = next(root.glob("alembic/versions/*avg_fill_price*.py")).read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS avg_fill_price" in mig and "DROP COLUMN IF EXISTS avg_fill_price" in mig
    assert "down_revision: str | None = 'b4e9f1c73d85'" in mig
    src = inspect.getsource(api_module._arb_persist_leg)
    assert "stored.avg_fill_price = avg_yes" in src, "the send stores the venue's YES-frame average"


def test_ticket_id_matches_the_desk_and_the_state_route(reads):
    assert desk.ticket_id(INTENT) == TICKET_ID
    assert os.path.isdir(str(reads))


# --------------------------------------------------------------------------- #
# The page: static/arb.html and the nav of the pages around it
# --------------------------------------------------------------------------- #

REPO = pathlib.Path(__file__).resolve().parents[1]
STATIC = REPO / "static"
#: The five pages whose nav changed with the ARB tab, plus the tab itself.
NAV_PAGES = ("index.html", "quote.html", "wallet.html", "analytics.html", "scoreboard.html", "arb.html")


def _fn(html: str, signature: str) -> str:
    """The body of exactly one function, found by matching its braces (the
    landing page's helper: a slice to the next known function grows whenever
    somebody inserts one between)."""
    i = html.index(signature)
    depth, j = 0, html.index("{", i)
    for k in range(j, len(html)):
        if html[k] == "{":
            depth += 1
        elif html[k] == "}":
            depth -= 1
            if depth == 0:
                return html[i:k + 1]
    raise AssertionError(f"unbalanced braces after {signature!r}")


@pytest.fixture(scope="module")
def page() -> str:
    return (STATIC / "arb.html").read_text(encoding="utf-8")


def test_the_arb_page_is_served_with_league_tabs_in_its_header(client, page):
    r = client.get("/arb")
    assert r.status_code == 200 and r.text == page
    head = page.split("</header>")[0]
    assert 'id="lgtabs"' in head, "test_leagues requires the tabs inside <header>"
    assert 'id="tok"' in head, "the token box is in the header, as on the landing page"
    assert '"wnba-"' not in page and "-wnba-/" not in page


def test_every_url_the_page_fetches_is_a_declared_route(page):
    """The route smoke test's own rule, applied here before it runs: a page
    pointing at a route that does not exist renders 'unavailable' forever."""
    # The page's POSTs go through its post() helper, which the repo-wide
    # sweep in test_every_route_answers (fetch( only) cannot see; matched here.
    fetch = re.compile(r"""(?:fetch|post)\(\s*[`'"]([^`'"?]+)""")
    routes = {r.path for r in api_module.app.routes if hasattr(r, "methods")}
    # "/api/arb/" + which is the lock/arm pair, composed; asserted by name below.
    urls = {m.group(1) for m in fetch.finditer(page)
            if m.group(1).startswith("/") and not m.group(1).endswith("/")}
    assert urls, "the page fetches nothing?"
    missing = [u for u in urls if u not in routes and u.split("${")[0].rstrip("/") not in routes]
    assert not missing, f"arb.html fetches routes that do not exist: {missing}"
    # The two the page builds from a variable: both are real routes.
    assert 'post("/api/arb/" + which)' in page and {"/api/arb/lock", "/api/arb/arm"} <= routes
    for url in ("/api/arb/state", "/api/arb/ladder", "/api/arb/record", "/api/arb/send",
                "/api/arb/unwind", "/api/status", "/api/leagues"):
        assert url in urls, url


def test_send_is_two_clicks_on_two_different_elements(page):
    """The card button opens the ticket and sends nothing; the modal's own
    button is the only element that posts to /api/arb/send. Same for UNWIND.
    Pinned as the landing page pins its SEND: by the function bodies."""
    card = _fn(page, "function ticketActions(t){")
    assert "fetch(" not in card and "post(" not in card and "/api/arb/send" not in card
    assert 'data-act="send"' in card and 'data-act="unwind"' in card
    opener = _fn(page, "function openSend(t){")
    assert "fetch(" not in opener and "post(" not in opener
    assert '$("#confirmBtn").onclick = sendPair' in opener
    sender = _fn(page, "async function sendPair(){")
    assert 'post("/api/arb/send"' in sender and 'mode: "HUMAN_CONFIRM"' in sender
    assert page.count('"/api/arb/send"') == 1, "one place on the page can send"
    assert "AUTONOMOUS" not in page
    unwinder = _fn(page, "async function sendUnwind(){")
    assert 'post("/api/arb/unwind"' in unwinder and 'mode: "HUMAN_CONFIRM"' in unwinder
    assert page.count('"/api/arb/unwind"') == 1
    uopener = _fn(page, "function openUnwind(t){")
    assert "post(" not in uopener and '$("#confirmBtn").onclick = sendUnwind' in uopener
    # The acknowledgement is a checkbox the modal's button waits on, both ways.
    assert "acknowledge: !!$(\"#ackbox\").checked" in sender
    assert "acknowledge: !!$(\"#ackbox\").checked" in unwinder


def test_the_send_body_is_derived_from_the_ticket_never_typed(page):
    """Slugs come from game + line through the page's port of the recorder's
    spelling; sides come from the intent; only price (one tick) and quantity
    are the operator's. The server rebuilds and refuses a mismatch."""
    sender = _fn(page, "async function sendPair(){")
    assert sender.count("slugOf(t.game, t.leg") == 2
    assert "side: t.leg1.side" in sender and "side: t.leg2.side" in sender
    builder = _fn(page, "function slugOf(game, line){")
    assert '"aec-" + g' in builder and '"neg" : "pos"' in builder and "pt${" in builder


def test_the_token_lives_in_session_storage_under_the_landing_pages_key(page):
    assert '"X-Meridian-Order-Token": $("#tok").value.trim()' in page
    assert 'sessionStorage.getItem("meridian_order_token")' in page
    for m in re.finditer(r'(\w+Storage)\.\w+\(\s*"meridian_order_token"', page):
        assert m.group(1) == "sessionStorage", f"the order token must not touch {m.group(1)}"


def test_the_page_polls_the_desk_and_the_ladder_at_the_designed_cadence(page):
    assert "setInterval(loadState, 10000)" in page
    assert "setInterval(loadLadder, 5000)" in page
    ladder = _fn(page, "async function loadLadder(){")
    assert "if(asked !== GAME) return;" in ladder, "a response for a game the operator left is dropped"


def test_the_ladder_table_reads_the_servers_bounds_and_flags(page):
    """Rendered, not recomputed: lo/hi/flags/violations are the api's."""
    body = _fn(page, "function renderLadder(){")
    for read in ("r.lo", "r.hi", "r.flags", "L.violations", "v.candidate", "v.ticket"):
        assert read in body, read
    for machinery in ("Math.max(", "Math.min(", "scan"):
        assert machinery not in body, f"{machinery} is the server's job"


def test_every_nav_carries_arb_and_none_carries_the_archived_strategies():
    for name in NAV_PAGES:
        head = (STATIC / name).read_text(encoding="utf-8").split("</header>")[0]
        assert 'href="/arb"' in head, name
        assert 'href="/quote"' not in head, name
        assert ">PULSE</a>" not in head and ">QUOTE</a>" not in head, name
        assert "strategy</span>" in head, name


def test_the_archived_pages_say_so_at_the_top_without_the_old_phrase():
    for name in ("index.html", "quote.html"):
        html = (STATIC / name).read_text(encoding="utf-8")
        body = html.split("</header>", 1)[1]
        assert 'id="archived"' in body and "ARCHIVED" in body, name
        assert 'href="/arb"' in body, name
        assert "These are shadow picks, not advice." not in html, name
        # At the top: before the first data-bearing container of each page.
        first = body.index('id="archived"')
        assert first < body.index('<details class="explain">' if name == "quote.html" else 'id="modal"'), name


def test_the_wallet_names_every_league_it_orders():
    html = (STATIC / "wallet.html").read_text(encoding="utf-8")
    names = re.search(r"const NAMES = \{([^}]*)\}", html).group(1)
    order = re.search(r'const ORDER = \[([^\]]*)\]', html).group(1)
    named = {k.strip() for k in re.findall(r"(\w+):", names)}
    ordered = {k.strip('" ') for k in order.split(",")}
    assert ordered <= named, f"wallet ORDER has leagues NAMES does not: {ordered - named}"


def test_the_fill_test_doc_carries_the_dashboard_amendment():
    doc = (REPO / "docs/math/ladder-fill-test.md").read_text(encoding="utf-8")
    i = doc.index("Placement via the dashboard (operator's instruction 2026-09-18)")
    amendment = " ".join(doc[i:].split())        # wrapped prose: normalise before matching
    for phrase in ("IMMEDIATE_OR_CANCEL", "synchronous", "leg 1", "quantity leg 1 filled",
                   "unchanged", "never sends without",
                   # the review's three mismatches, now stated as the code does them
                   "Quantity is at most the ticket's", "last-read account balance",
                   "whole reply body is logged", "`l1_sent`, `l2_sent`",
                   "only when every sent leg's fill was observed", "UNWIND is deliberately exempt",
                   "cost plus the scanner's taker fees must be under $1.00"):
        assert phrase in amendment, phrase


# --------------------------------------------------------------------------- #
# The review's pins: quantities, states, frames, the record and the page gates
# --------------------------------------------------------------------------- #

def test_a_venue_decimal_is_spelled_as_the_venue_has_always_seen_it():
    """Decimal('2.0000') - Decimal('1.0000') is '1.0000' and float(1) is '1.0';
    every quantity ever sent read "1". The one normaliser every derived
    quantity goes through."""
    q = api_module._arb_qty
    assert str(q(Decimal("1.0"))) == "1" and str(q(Decimal("1.0000"))) == "1"
    assert str(q(Decimal("1.46"))) == "1.46" and str(q(Decimal("2.5"))) == "2.5"
    assert str(q(Decimal("2.0000") - Decimal("1.0000"))) == "1"
    assert str(q(Decimal("100"))) == "100", "normalize() alone would give 1E+2"
    assert str(q(Decimal("0.010"))) == "0.01"
    assert str(q(Decimal("1.999"))) == "2", "to the venue's cent"


def test_fill_status_treats_reject_as_a_refusal_and_pending_as_open():
    """status_from_state has no REJECTED branch and reads any CANCEL as
    CANCELLED; the send must not write a PENDING_CANCEL as terminal (the
    watcher would never re-poll it) nor a REJECTED as a fill state."""
    st = api_module._arb_fill_status
    assert st({"state": "ORDER_STATE_REJECTED", "filled": Decimal("0")}, Decimal("2")) is None
    assert st({"state": "ORDER_STATE_PENDING_NEW", "filled": Decimal("0")}, Decimal("2")) == fw.OPEN
    assert st({"state": "ORDER_STATE_PENDING_RISK", "filled": Decimal("0")}, Decimal("2")) == fw.OPEN
    assert st({"state": "ORDER_STATE_PENDING_CANCEL", "filled": Decimal("1")}, Decimal("2")) == fw.OPEN
    assert fw.OPEN not in fw.TERMINAL


def test_parse_sync_orders_executions_by_transact_time_and_prefers_the_vwap():
    """A newest-first list [CANCELED cum 1, PARTIALLY_FILLED cum 1] must read
    as CANCELED (the latest by transactTime), never as still open; and over
    two priced executions the VWAP, not the last execution's avgPx, is the
    leg's average."""
    newest = {"order": {"id": "v-t", "state": "ORDER_STATE_CANCELED", "cumQuantity": 1},
              "transactTime": "2026-09-18T02:05:52.000000000Z"}
    older = {"order": {"id": "v-t", "state": "ORDER_STATE_PARTIALLY_FILLED", "cumQuantity": 1},
             "transactTime": "2026-09-18T02:05:51.000000000Z"}
    p = api_module._arb_parse_sync(json.dumps({"executions": [newest, older]}))
    assert p["state"] == "ORDER_STATE_CANCELED" and p["filled"] == Decimal("1")
    first = {"order": {"id": "v-w", "state": "ORDER_STATE_PARTIALLY_FILLED", "cumQuantity": 1},
             "lastPx": {"value": "0.40"}, "lastShares": "1", "avgPx": {"value": "0.40"}}
    second = {"order": {"id": "v-w", "state": "ORDER_STATE_FILLED", "cumQuantity": 2},
              "lastPx": {"value": "0.42"}, "lastShares": "1", "avgPx": {"value": "0.42"}}
    p = api_module._arb_parse_sync(json.dumps({"executions": [first, second]}))
    assert p["avg_yes"] == Decimal("0.4100") and p["avg_vwap"] == Decimal("0.4100")
    assert p["avg_reported"] == Decimal("0.42"), "kept beside it so the disagreement can be logged"


def _sent(n, filled, cost, *, accepted=True, observed=None, state="ORDER_STATE_FILLED", http=200,
          error=None, transport=False):
    leg = _leg(n, filled, cost, sent=not transport, error=error)
    leg.update({"accepted": accepted, "state": state, "http_status": http, "transport_error": transport,
                "observed": (filled > 0 or state in ("ORDER_STATE_FILLED", "ORDER_STATE_CANCELED"))
                if observed is None else observed})
    if not accepted:
        leg["observed"] = False
    return leg


def test_pair_summary_tells_a_refusal_a_pending_and_an_unknown_from_a_zero_fill():
    """Three non-observations reach the same action (nothing more is sent)
    and must not reach the tally as "leg 1 filled nothing"."""
    ps = api_module._arb_pair_summary
    unfilled = ps([_sent(1, 0.0, 0.41, state="ORDER_STATE_CANCELED"), _leg(2, 0.0, 0.53, sent=False, error="x")])
    assert unfilled["outcome"] == "leg 1 unfilled" and unfilled["settled"] is True and unfilled["pending"] is False
    rejected = ps([_sent(1, 0.0, 0.41, accepted=False, state=None, http=400, error="price out of range"),
                   _leg(2, 0.0, 0.53, sent=False, error="x")])
    assert rejected["outcome"] == "leg 1 rejected" and rejected["settled"] is False
    assert "400" in rejected["note"] and "record says placed" in rejected["note"]
    pending = ps([_sent(1, 0.0, 0.41, state="ORDER_STATE_PENDING_NEW", observed=False),
                  _leg(2, 0.0, 0.53, sent=False, error="x")])
    assert pending["outcome"] == "leg 1 pending at the venue" and pending["pending"] is True
    assert pending["settled"] is False and "fill watcher" in pending["note"]
    unknown = ps([_sent(1, 0.0, 0.41, state=None, observed=False), _leg(2, 0.0, 0.53, sent=False, error="x")])
    assert unknown["outcome"] == "leg 1 unknown" and unknown["settled"] is False
    l2_unknown = ps([_sent(1, 2.0, 0.41), _sent(2, 0.0, 0.53, accepted=False, http=None, error="timeout", transport=True)])
    assert l2_unknown["outcome"] == "leg 1 filled, leg 2 unknown" and l2_unknown["pending"] is True
    assert l2_unknown["settled"] is False and "Reconcile leg 2" in l2_unknown["note"]
    l2_rejected = ps([_sent(1, 2.0, 0.41), _sent(2, 0.0, 0.53, accepted=False, http=400, error="bad")])
    assert l2_rejected["outcome"] == "leg 1 filled, leg 2 rejected" and "UNWIND" in l2_rejected["note"]
    both = ps([_sent(1, 2.0, 0.41), _sent(2, 2.0, 0.53)])
    assert both["outcome"] == "both legs filled" and both["settled"] is True


def test_every_rung_carries_the_screen_pair_in_the_rows_own_frame():
    """A pos rung's row is the SECOND team's and its Yes is our NO: the venue
    shows (1 - ask, 1 - bid) there. A neg rung's row is the first team's and
    shows our bid/ask as they are. The winner market has no screen pair."""
    snap = api_module._arb_ladder_snapshot(GAME, {**RUNGS, 0.0: (0.55, 0.57, 5.0, 5.0)}, {}, 0.2, time.time())
    pos = snap["rungs"]["10.5"]
    assert pos["our_yes_is"] == "No" and pos["screen_ask"] == round(1 - pos["bid"], 2)
    assert pos["screen_bid"] == round(1 - pos["ask"], 2) and pos["screen_bid"] <= pos["screen_ask"]
    neg = snap["rungs"]["-3.5"] if "-3.5" in snap["rungs"] else None
    if neg is None:
        neg_snap = api_module._arb_ladder_snapshot(GAME, {-3.5: (0.30, 0.32, 1.0, 1.0)}, {}, 0.2, time.time())
        neg = neg_snap["rungs"]["-3.5"]
    assert neg["our_yes_is"] == "Yes" and (neg["screen_bid"], neg["screen_ask"]) == (neg["bid"], neg["ask"])
    winner = snap["rungs"]["0"]
    assert winner["screen_bid"] is None and winner["screen_ask"] is None and winner["row"] == "winner"


def test_a_stale_cached_touch_is_no_touch(monkeypatch):
    """The cache is never evicted; only the watch expires. A sample older
    than two intervals must not price a SELL."""
    now = time.time()
    snap = api_module._arb_ladder_snapshot(GAME, RUNGS, {}, 0.2, now)
    monkeypatch.setitem(api_module._ARB_LADDER, "cache", {PREFIX: snap})
    monkeypatch.setenv("MERIDIAN_ARB_SAMPLE_SECONDS", "10")
    assert api_module._arb_book_at(PREFIX, 10.5) == (Decimal("0.4"), Decimal("0.41"))
    snap["sampled_ts"] = now - 21
    assert api_module._arb_book_at(PREFIX, 10.5) == (None, None)
    assert api_module._arb_book_at(PREFIX, 99.5) == (None, None)


def test_the_tally_measures_eighty_percent_of_what_was_sent(tmp_path):
    """Ticket qty 5, sent 1, filled 1: 100 % of what went. Against the
    ticket it would be neither `both` nor `none`; and a `placed` record with
    an outcome (a refusal) is not a recorded zero."""
    out = str(tmp_path)
    big = dict(INTENT, leg1=dict(INTENT["leg1"], qty=5), leg2=dict(INTENT["leg2"], qty=5))
    (tmp_path / f"ladder_intents_{PREFIX}.jsonl").write_text(json.dumps(big) + "\n", encoding="utf-8")
    tid = desk.ticket_id(big)
    desk.record_attempt(out, tid, "recorded", {"l1q": 1, "l1p": 0.41, "l2q": 1, "l2p": 0.53},
                        via=api_module._ARB_VIA_SEND, l1_sent=1.0, l2_sent=1.0)
    t = desk.tally(desk.load_tickets(out))
    assert t["both"] == 1 and t["none"] == 0
    desk.record_attempt(out, tid, "placed", None, via=api_module._ARB_VIA_SEND, outcome="leg 1 rejected",
                        error="401", l1_sent=5.0)
    t = desk.tally(desk.load_tickets(out))
    assert t["placed"] == 1 and t["recorded"] == 0 and t["none"] == 0


def test_every_order_client_constructor_in_the_api_is_token_gated():
    """The allowlist admits the whole of core/api.py; this pins that every
    function in it constructing PolymarketOrderClient opens with the token
    check, and that the ARB pair also demands the HUMAN_CONFIRM literal
    before the constructor. The set of such functions is closed."""
    tree = ast.parse(pathlib.Path(api_module.__file__).read_text(encoding="utf-8"))
    sites = {}
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef):
            continue
        calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id == "PolymarketOrderClient"]
        if calls:
            sites[fn.name] = fn
    assert set(sites) == {"submit_order", "cancel_order", "arb_send", "arb_unwind"}
    for name, fn in sites.items():
        body = [s for s in fn.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
        first = body[0]
        assert (isinstance(first, ast.Expr) and isinstance(first.value, ast.Call)
                and getattr(first.value.func, "id", None) == "_require_order_token"), name
    for name in ("arb_send", "arb_unwind"):
        src = ast.unparse(sites[name])
        assert src.index("_arb_require_mode(") < src.index("PolymarketOrderClient("), name


def test_the_page_gates_send_on_armed_and_unwind_on_the_send_mark(page):
    """The desk stat's words must be what the page does: SEND is offered
    only on an ARMED desk; 'sent from this page' and UNWIND appear only on
    the send's own `via` mark, never on a hand record; and recalc refuses a
    pair whose cost plus fees reaches a dollar before the confirm."""
    acts = _fn(page, "function ticketActions(t){")
    assert "STATE.armed === true" in acts and "SEND (locked)" in acts
    assert f'rec.via === "{api_module._ARB_VIA_SEND}"' in acts
    assert f'rec.via === "{api_module._ARB_VIA_DESK}"' not in acts
    card = _fn(page, "function ticketCard(t){")
    assert f'rec.via === "{api_module._ARB_VIA_SEND}" ? " · sent from this page"' in card
    assert "cost ${num(leg.price, 3)}" in _fn(page, "function legLine(n, leg, game, first){")
    assert "YES frame" in _fn(page, "function legLine(n, leg, game, first){")
    ladder = _fn(page, "function renderLadder(){")
    assert "r.screen_bid" in ladder and "r.screen_ask" in ladder and "r.our_yes_is" in ladder
    send = _fn(page, "function openSend(t){")
    assert "pc + fees >= 1) return bad(" in send
    tip = re.search(r'title="The executor\'s lock file[^"]*"', page).group(0)
    assert "SEND is not offered" in tip and "server refuses every send" in tip


# --------------------------------------------------------------------------- #
# Ticket liveness: a ticket is a snapshot of one instant, not a standing offer
# --------------------------------------------------------------------------- #

def _snap(rungs=None, at=None):
    return api_module._arb_ladder_snapshot(GAME, dict(rungs or RUNGS), {}, 1.0,
                                           time.time() if at is None else at)


def _tick(rungs, line, *, bid=None, ask=None):
    """One rung re-quoted, the rest of the ladder untouched."""
    out = dict(rungs)
    b, a, bs, asz = out[line]
    out[line] = (b if bid is None else bid, a if ask is None else ask, bs, asz)
    return out


def test_a_ticket_is_live_at_the_ticketed_price_and_moves_one_tick_later():
    """The boundary is the whole point: the ticket asks for 0.41 and the rung
    asks 0.41, so it is LIVE — not MOVED for a float's sake. One tick dearer
    it still clears fee-netted (MOVED); five ticks dearer it does not (GONE),
    and the block names the leg that moved and by how much."""
    now = time.time()
    live = api_module._arb_live_block(INTENT, _snap(at=now), now)
    assert live["state"] == "LIVE" and live["moved_leg"] is None
    assert (live["leg1_now"], live["leg2_now"]) == (0.41, 0.53)
    assert live["leg1_delta_c"] == 0.0 and live["leg2_delta_c"] == 0.0

    moved = api_module._arb_live_block(INTENT, _snap(_tick(RUNGS, 10.5, ask=0.42), now), now)
    assert moved["state"] == "MOVED" and moved["moved_leg"] == "leg 1"
    assert moved["leg1_now"] == 0.42 and moved["leg1_delta_c"] == 1.0
    assert 0 < moved["edge_now_c"] < INTENT["edge_c"]

    gone = api_module._arb_live_block(INTENT, _snap(_tick(RUNGS, 10.5, ask=0.46), now), now)
    assert gone["state"] == "GONE" and gone["moved_leg"] == "leg 1"
    assert gone["leg1_delta_c"] == 5.0 and gone["edge_now_c"] < 0


def test_the_second_leg_is_read_in_the_cost_frame_and_both_can_move():
    """Leg 2 buys NO at the harder line: its ticketed 0.53 is 1 - the rung's
    YES bid of 0.47, so the bid falling to 0.46 makes the leg cost 0.54."""
    now = time.time()
    one = api_module._arb_live_block(INTENT, _snap(_tick(RUNGS, 7.5, bid=0.46), now), now)
    assert one["leg2_now"] == 0.54 and one["leg2_delta_c"] == 1.0 and one["moved_leg"] == "leg 2"
    both = api_module._arb_live_block(
        INTENT, _snap(_tick(_tick(RUNGS, 7.5, bid=0.46), 10.5, ask=0.42), now), now)
    assert both["moved_leg"] == "both" and both["state"] == "MOVED"
    dead = api_module._arb_live_block(
        INTENT, _snap(_tick(_tick(RUNGS, 7.5, bid=0.44), 10.5, ask=0.44), now), now)
    assert dead["moved_leg"] == "both" and dead["state"] == "GONE"


def test_the_live_edge_is_scan_ladders_own_fee_model_not_a_second_copy():
    """`1 - c1 - c2 - fee(c1) - fee(c2)` in the cost frame IS
    `sell - buy - fee(buy) - fee(sell)`: the fee curve is symmetric about
    0.5, so the two frames agree to the cent the page prints. If they ever
    diverge, the page and the executor are pricing different trades."""
    from core.ladder.scan import scan_ladder
    now = time.time()
    for ask in (0.41, 0.42, 0.44, 0.46):
        rungs = _tick(RUNGS, 10.5, ask=ask)
        live = api_module._arb_live_block(INTENT, _snap(rungs, now), now)
        pair = [v for v in scan_ladder(GAME, rungs, max_size=1e12)
                if (v.high_line, v.low_line) == (10.5, 7.5)]
        if pair:
            assert live["edge_now_c"] == pytest.approx(round(pair[0].edge * 100, 2), abs=0.01)
        else:
            assert live["edge_now_c"] <= 0, "no violation means the pair does not clear"


def _resize(rungs, line, *, bid_sz=None, ask_sz=None):
    """One rung's displayed SIZE changed, every price untouched."""
    out = dict(rungs)
    b, a, bs, asz = out[line]
    out[line] = (b, a, bs if bid_sz is None else bid_sz, asz if ask_sz is None else ask_sz)
    return out


def test_a_price_with_no_size_behind_it_is_thin_not_live():
    """LIVE used to be a price-only test. With the ticketed prices intact and
    NOTHING displayed on either side we take, the ticket panel said "live —
    both legs still available" while the SAME snapshot's violation row said
    $0.00 and not a candidate. The executor's own rule is size-based
    (edge x min displayed size >= the floor), so the panel must be too."""
    now = time.time()
    empty = _resize(_resize(RUNGS, 10.5, ask_sz=0.0), 7.5, bid_sz=0.0)
    snap = _snap(empty, now)
    live = api_module._arb_live_block(INTENT, snap, now)
    assert live["state"] == "THIN", "priced there with nothing behind it is not live"
    assert live["thin_leg"] == "both" and live["size_now"] == 0.0
    # Unchanged prices: this is a size finding, not a price one.
    assert (live["leg1_now"], live["leg2_now"]) == (0.41, 0.53)
    assert live["edge_now_c"] == pytest.approx(3.05, abs=0.01)
    # One leg is enough, and the block names which.
    one = api_module._arb_live_block(INTENT, _snap(_resize(RUNGS, 7.5, bid_sz=1.0), now), now)
    assert one["state"] == "THIN" and one["thin_leg"] == "leg 2" and one["size_now"] == 1.0
    # The ticket's own quantity is the bar, and the boundary is LIVE.
    at = api_module._arb_live_block(INTENT, _snap(_resize(RUNGS, 7.5, bid_sz=2.0), now), now)
    assert at["state"] == "LIVE" and at["size_now"] == 2.0
    # A ticket written off an empty book asks for nothing; an empty book
    # still is not an offer, so asking for nothing does not make it live.
    nil = {**INTENT, "leg1": {**INTENT["leg1"], "qty": 0},
           "leg2": {**INTENT["leg2"], "qty": 0}}
    assert api_module._arb_live_block(nil, snap, now)["state"] == "THIN"


def test_the_ticket_panels_size_is_the_centre_panes_violation_row():
    """One number, not two: `size_now`/`dollars_now` are the MIN of the two
    legs under scan_ladder's own cap, which is `Violation.size`/`.dollars`
    for that pair in the same snapshot. If these ever diverge the two panes
    are describing different trades."""
    now = time.time()
    for rungs in (RUNGS,
                  _resize(RUNGS, 10.5, ask_sz=0.0),
                  _resize(RUNGS, 10.5, ask_sz=7.0),
                  _resize(RUNGS, 7.5, bid_sz=40_000.0)):
        snap = _snap(rungs, now)
        live = api_module._arb_live_block(INTENT, snap, now)
        row = [v for v in snap["violations"]
               if (v["high_line"], v["low_line"]) == (10.5, 7.5)]
        assert row, "the fixture pair clears; the violation row must exist"
        assert live["size_now"] == row[0]["size"]
        assert live["dollars_now"] == pytest.approx(row[0]["dollars"], abs=0.01)
        # And the floor the executor trades by is read off the same number.
        assert (live["dollars_now"] >= api_module._ARB_FLOOR_USD) is row[0]["candidate"]


def test_an_edge_past_the_scan_modules_bound_is_stale_not_the_best_thing_on_the_page():
    """scan.py rejects an "edge" above MAX_PLAUSIBLE_EDGE as a deep rung
    nobody re-quoted (USC -17.5 at 0.930 beside USC -10.5 at 0.040). The
    ticket panel dropped that guard, so the same ladder rendered as LIVE with
    the biggest edge on the page beside an EMPTY violations table — and the
    page's default selection prefers a live ticket, so it selected itself."""
    from core.ladder.scan import MAX_PLAUSIBLE_EDGE, scan_ladder
    now = time.time()
    stale = dict(RUNGS)
    stale[10.5] = (0.01, 0.02, 966.0, 966.0)
    snap = _snap(stale, now)
    live = api_module._arb_live_block(INTENT, snap, now)
    assert live["edge_now_c"] / 100 > MAX_PLAUSIBLE_EDGE
    assert live["state"] == "STALE" and live["implausible"] is True
    assert live["state"] != "LIVE", "the page selects LIVE by default"
    # The guard is the scanner's, so the two agree on the same ladder: the
    # centre pane shows no violation for a pair the panel must not call live.
    assert scan_ladder(GAME, stale, max_size=1e12) == []
    assert snap["violations"] == []
    # And a plausible edge is untouched by the guard.
    assert api_module._arb_live_block(INTENT, _snap(RUNGS, now), now)["implausible"] is False


@pytest.mark.parametrize("snap, why", [
    (None, "the game is not sampled at all"),
    ({"available": False, "reason": "first sample pending"}, "the sample failed"),
    ({"available": True, "sampled_ts": None, "rungs": {}}, "the sample carries no clock"),
])
def test_no_current_sample_is_unknown_and_never_live(snap, why):
    assert api_module._arb_live_block(INTENT, snap, time.time()) is None, why


def test_a_stale_sample_and_a_missing_rung_are_unknown_not_live(monkeypatch):
    """Two ways to be told nothing: a sample older than the unwind's own
    staleness bound, and a ladder that does not carry one of the legs. Both
    answer UNKNOWN. A ticket is never LIVE for want of data."""
    monkeypatch.setenv("MERIDIAN_ARB_SAMPLE_SECONDS", "10")
    now = time.time()
    assert api_module._arb_live_block(INTENT, _snap(at=now - 19), now)["state"] == "LIVE"
    assert api_module._arb_live_block(INTENT, _snap(at=now - 21), now) is None
    thin = {k: v for k, v in RUNGS.items() if k != 10.5}
    assert api_module._arb_live_block(INTENT, _snap(thin, now), now) is None


def test_state_attaches_the_live_block_from_the_cache_the_ladder_serves(client, reads, monkeypatch):
    """Same cache, so the centre pane and the ticket panel cannot disagree —
    and only an open ticket carries the block, because only an open ticket
    can be sent."""
    monkeypatch.setitem(api_module._ARB_LADDER, "cache", {PREFIX: _snap()})
    t = client.get("/api/arb/state").json()["tickets"][0]
    assert t["live"]["state"] == "LIVE" and t["live"]["age_s"] < 5
    assert t["live"]["leg1_now"] == 0.41 and t["live"]["edge_now_c"] == pytest.approx(3.05, abs=0.01)
    desk.record_attempt(str(reads), TICKET_ID, "placed")
    assert "live" not in client.get("/api/arb/state").json()["tickets"][0]


def test_state_without_a_sample_leaves_the_block_off_entirely(client, reads, monkeypatch):
    monkeypatch.setitem(api_module._ARB_LADDER, "cache", {})
    t = client.get("/api/arb/state").json()["tickets"][0]
    assert "live" not in t and t["sendable"] is True, "unknown liveness does not block a send"


# --------------------------------------------------------------------------- #
# Over-cap tickets: the cap limits placing, not detection
# --------------------------------------------------------------------------- #

def test_an_over_cap_ticket_is_shown_in_full_and_is_not_sendable(client, reads):
    """The executor now writes a ticket past the game's cap, flags it and
    does not push it; the send route refuses it. It must still arrive on the
    page with every term, because seeing what went by is the point."""
    over = dict(INTENT, ts="23:52:00", over_budget=True)
    with open(reads / f"ladder_intents_{PREFIX}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(over) + "\n")
    by_ts = {t["ts"]: t for t in client.get("/api/arb/state").json()["tickets"]}
    flagged, plain = by_ts["23:52:00"], by_ts["23:41:07"]
    assert flagged["over_budget"] is True and flagged["sendable"] is False
    assert flagged["status"] == "open" and flagged["spread_pair"] is True
    assert flagged["leg1"]["price"] == 0.41 and flagged["cost_usd"] == 1.88
    assert plain["over_budget"] is False and plain["sendable"] is True


def test_the_send_route_refuses_an_over_cap_ticket_before_the_venue(client, reads, no_db_no_venue):
    over = dict(INTENT, ts="23:52:00", over_budget=True)
    with open(reads / f"ladder_intents_{PREFIX}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(over) + "\n")
    body = _send_body(ticket_id=f"{GAME}|23:52:00|10.5/7.5")
    r = client.post("/api/arb/send", json=body, headers=TOKEN)
    assert r.status_code == 409 and "past its ticket cap" in r.json()["detail"]


# --------------------------------------------------------------------------- #
# The page renders the block; it does not recompute it
# --------------------------------------------------------------------------- #

def test_the_page_renders_the_live_block_and_carries_no_second_fee_model(page):
    """The states are the server's word, rendered. The fee arithmetic
    stays in core.ladder.scan: the page's only 0.06 is the confirm modal's
    own pre-existing guard, and the liveness functions have none."""
    for fn in ("function liveChip(t){", "function liveBanner(t){"):
        body = _fn(page, fn)
        assert "t.live" in body and "LIVE_WORDS" in body
        for machinery in ("0.06", "fee", "Math."):
            assert machinery not in body, f"{machinery} is the server's job"
    assert '"lv unknown"' in _fn(page, "function liveChip(t){")
    assert '"lv unknown"' in _fn(page, "function liveBanner(t){")
    send = _fn(page, "function openSend(t){")
    for m in re.finditer(r"0\.06", page):
        assert page.index(send) <= m.start() < page.index(send) + len(send), \
            "a second fee model on the page is a second answer"
    # Every state the server can return has words on the page, and UNKNOWN is
    # the default rather than a fourth branch that could fall through to LIVE.
    words = _fn(page, "const LIVE_WORDS = {")
    for state in ("LIVE:", "THIN:", "MOVED:", "STALE:", "GONE:"):
        assert state in words, state
    assert "UNKNOWN" not in words, "UNKNOWN is the absence of a block, not a value"
    # A state with no words renders as UNKNOWN, so every state the server can
    # return must be here: a missing one would read "?" on a real ticket.
    src = inspect.getsource(api_module._arb_live_block)
    served = set(re.findall(r'state = "([A-Z]+)"', src)) | {"LIVE", "MOVED", "GONE"}
    assert served <= {w.strip(" :") for w in re.findall(r"\n  ([A-Z]+):", words)}
    # Size is on the banner and in the chip's hover, so LIVE can never mean
    # "priced there with nothing behind it" and a thin pair says so in words.
    assert "lv.size_now" in _fn(page, "function liveBanner(t){")
    assert "lv.size_now" in _fn(page, "function liveChip(t){")


def test_the_ticket_panel_shows_liveness_on_the_row_and_the_card(page):
    row = _fn(page, "function ticketRow(t, g){")
    assert "liveChip(t)" in row and 'class="st cap"' in row and "over cap" in row
    card = _fn(page, "function ticketCard(t){")
    assert "liveBanner(t)" in card
    assert "capnote" in card and "not what is detected" in card
    # The card hands each leg its current price; legLine prints it beside the
    # ticketed one rather than in place of it.
    assert "now: lv.leg1_now" in card and "now: lv.leg2_now" in card
    leg = _fn(page, "function legLine(n, leg, game, first){")
    assert "cost ${num(leg.price, 3)}" in leg and "leg.now" in leg


def test_a_send_on_a_pair_that_no_longer_clears_is_offered_not_recommended(page):
    """GONE, THIN and STALE de-emphasise the button and put the reason on it;
    none of them removes it — the operator may still choose, and a page that
    hides the choice teaches nothing about why."""
    acts = _fn(page, "function ticketActions(t){")
    assert 'lv.state === "GONE"' in acts and 'doubt ? "faded" : "go"' in acts
    assert '["GONE", "THIN", "STALE"].includes(lv.state)' in acts
    assert "no longer clears on the current sample" in acts
    assert "less size behind it than the ticket asks for" in acts
    assert "past the plausibility bound" in acts
    assert "size now ${num(lv.size_now, 0)}" in acts, "the reason carries the size"
    assert 'data-act="send"' in acts, "the button is still there"
    assert "SEND (over cap)" in acts and "t.over_budget" in acts
    assert "button.faded" in page, "the de-emphasis has a style"
    # The last screen before the money says what the pair is doing now.
    assert "liveBanner(t)" in _fn(page, "function openSend(t){")


def test_the_leg_colours_follow_the_easier_and_harder_line_not_the_leg_order(page):
    """Green is the line we BUY (the easier, higher one) and red the line we
    SELL, whichever leg number carries it. Pinned at the one place the page
    decides it: a ticket whose leg 1 held the LOWER line would come out red.
    (Source-level: there is no JS runtime in this suite.)"""
    fn = _fn(page, "function legCls(t){")
    assert 'a > b ? ["buy", "sell"] : ["sell", "buy"]' in fn
    assert "market_line" in fn and "isFinite(a) && isFinite(b)" in fn
    for caller in ("function ticketRow(t, g){", "function ticketCard(t){"):
        assert "legCls(t)" in _fn(page, caller), caller
    # Both callers take the pair in the order legCls returns it; neither
    # hands "buy" to leg 1 by name.
    for caller in ("function ticketRow(t, g){", "function ticketCard(t){"):
        body = _fn(page, caller)
        assert "[c1, c2] = legCls(t)" in body, caller
        assert '"buy"' not in body and '"sell"' not in body, caller


def test_the_ladder_lights_the_side_it_would_touch_and_keeps_the_accent(page):
    """Three meanings, three marks: green on the rung bought at its ask, red
    on the rung sold at its bid, and the accent still saying 'this rung
    breaks its bound'. The bounds and the pair remain the server's."""
    body = _fn(page, "function renderLadder(){")
    assert "tkt.high_line" in body and "tkt.low_line" in body
    assert "tkbuy" in body and "tksell" in body
    assert "actbuy" in body and "actsell" in body
    # The SIDE colour is on every crossed rung, not only the selected ticket's
    # two: a ladder whose lit rungs went grey whenever the chosen ticket was
    # dead or belonged to another game was the complaint that prompted this.
    assert 'askLit ? "litbuy"' in body and 'bidLit ? "litsell"' in body
    # "breaks its bound" keeps a mark of its own -- it moved from the price to
    # the row, so the two statements stay separable.
    assert 'viol ? " viol"' in body
    for machinery in ("Math.max(", "Math.min(", "scan"):
        assert machinery not in body, f"{machinery} is the server's job"
    # inBuy is the ask side, inSell the bid side, and not the other way round.
    assert "inBuy = !!tkt && r.line === tkt.high_line" in body
    assert "inSell = !!tkt && r.line === tkt.low_line" in body
    assert body.index("inSell ? \" act actsell\"") < body.index("inBuy ? \" act actbuy\"")
    # and the three colours are named once, under the ladder's own header
    legend = page[page.index('<div class="legend">'):page.index('<div id="ladder">')]
    for word in ("buy · easier line · at its ask", "sell · harder line · at its bid",
                 "breaks its bound", "EVERY crossed rung"):
        assert word in legend, word


def test_the_panel_leads_with_the_newest_and_never_opens_on_a_stale_ticket(page):
    """The executor appends, so file order put the OLDEST ticket at the top
    of the list and under the cursor — which is how a 62-minute-old pair came
    to be the one on screen. Newest first, and the default selection prefers
    a ticket that is both sendable and LIVE on the current sample. A ticket
    with no live block never wins it: unknown is not live."""
    body = _fn(page, "function renderTickets(){")
    # It used to `.reverse()` the server's list here, which was right only
    # while the server handed over raw file order. The server now sorts
    # newest-first on a real dated instant (core/ladder/desk.stamp_instants);
    # two places ordering one list is what put Friday night at the top of a
    # live Saturday desk. Ordering happens once, on the server.
    assert "const newest = heads" in body
    assert ".reverse()" not in re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    assert "groups.map(g => ticketRow(g.head, g))" in body and "mine.map(ticketRow)" not in body
    assert 't.sendable && (t.live || {}).state === "LIVE"' in body
    assert body.index('state === "LIVE"') < body.index("newest.find(t => t.sendable) ||"), \
        "live-and-sendable is preferred to merely sendable"


def test_the_violations_table_colours_its_legs_by_the_line_too(page):
    ladder = _fn(page, "function renderLadder(){")
    assert 'Number(l1.market_line) > Number(l2.market_line) ? ["buyc", "sellc"] : ["sellc", "buyc"]' in ladder
    assert "${vc1}" in ladder and "${vc2}" in ladder
