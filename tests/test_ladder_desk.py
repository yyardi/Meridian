"""The desk speaks the venue's screen language, flips the lock, and cannot trade."""
from __future__ import annotations

import importlib
import json
import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core.ladder import ui  # noqa: E402


def test_teams_come_from_the_slug_in_screen_case():
    assert ui.teams_of("cfb-mia-wake-2026-09-18") == ("MIA", "WAKE")
    assert ui.teams_of("aec-nfl-det-buf-2026-09-17") == ("DET", "BUF")
    assert ui.teams_of("cfb-portst-ore-2026-09-18") == ("PORTST", "ORE")


def test_wording_matches_the_venue_screen_on_both_sides_of_the_ladder():
    # pos line: the row belongs to the SECOND team; our YES (first team +N) is the screen's No
    assert ui.ui_wording("cfb-mia-wake-2026-09-18", 10.5, "BUY YES") == ("WAKE to win by over 10.5 points", "No")
    assert ui.ui_wording("cfb-mia-wake-2026-09-18", 10.5, "BUY NO") == ("WAKE to win by over 10.5 points", "Yes")
    # neg line: the row belongs to the FIRST team; our YES is the screen's Yes
    assert ui.ui_wording("cfb-mia-wake-2026-09-18", -3.5, "BUY YES") == ("MIA to win by over 3.5 points", "Yes")
    assert ui.ui_wording("cfb-mia-wake-2026-09-18", -3.5, "BUY NO") == ("MIA to win by over 3.5 points", "No")
    # the DET-BUF $1,222 pair, as the operator would have seen it
    assert ui.ui_wording("nfl-det-buf-2026-09-17", 13.5, "BUY YES") == ("BUF to win by over 13.5 points", "No")
    assert ui.ui_wording("nfl-det-buf-2026-09-17", 10.5, "BUY NO") == ("BUF to win by over 10.5 points", "Yes")
    with pytest.raises(ValueError):
        ui.ui_wording("cfb-mia-wake-2026-09-18", 0.0, "BUY YES")


@pytest.fixture
def desk(tmp_path, monkeypatch):
    monkeypatch.setenv("LADDER_OUT", str(tmp_path))
    mod = importlib.import_module("cfb.ladder_desk_app")
    mod = importlib.reload(mod)
    from fastapi.testclient import TestClient
    intent = {"ts": "23:41:07", "game": "cfb-mia-wake-2026-09-18",
              "leg1": {"market_line": 10.5, "side": "BUY YES", "price": 0.41, "qty": 2},
              "leg2": {"market_line": 7.5, "side": "BUY NO", "price": 0.53, "qty": 2},
              "displayed_size": 966.0, "edge_c": 2.1, "cost_usd": 1.88, "leg1_book_age_s": 412.0, "leg2_book_age_s": 3.0,
              "meridian_placed": False}
    (tmp_path / "ladder_intents_aec-cfb-mia-wake-2026-09-18.jsonl").write_text(json.dumps(intent) + "\n")
    return mod, TestClient(mod.app), tmp_path


def test_lock_is_a_file_the_desk_creates_and_removes(desk):
    mod, c, out = desk
    assert "ARMED" in c.get("/").text and not (out / "ladder_lock").exists()
    r = c.post("/lock", follow_redirects=False)
    assert r.status_code == 303 and (out / "ladder_lock").exists()
    assert "LOCKED" in c.get("/").text
    c.post("/arm", follow_redirects=False)
    assert not (out / "ladder_lock").exists() and "ARMED" in c.get("/").text


def test_ticket_is_shown_in_screen_words_and_records_the_operators_actions(desk):
    mod, c, out = desk
    page = c.get("/").text
    assert "WAKE to win by over 10.5 points" in page and "tap <b>No</b>" in page
    assert "WAKE to win by over 7.5 points" in page and "tap <b>Yes</b>" in page
    assert "I placed it" in page
    tid = mod.load_tickets()[0]["id"]
    c.post("/ticket", data={"id": tid, "action": "placed"}, follow_redirects=False)
    page = c.get("/").text
    assert "Save fills" in page and "1 / 5" in page
    c.post("/ticket", data={"id": tid, "action": "record", "l1q": "2", "l1p": "0.41", "l1s": "4", "l2q": "2", "l2p": "0.53", "l2s": "9"}, follow_redirects=False)
    t = mod.tally(mod.load_tickets())
    assert t["recorded"] == 1 and t["both"] == 1 and t["none"] == 0
    rows = [json.loads(x) for x in (out / "ladder_attempts.jsonl").read_text().splitlines()]
    assert rows[-1]["status"] == "recorded" and rows[-1]["l1q"] == 2.0


def test_desk_has_no_venue_call_and_no_order_path():
    src = pathlib.Path(importlib.import_module("cfb.ladder_desk_app").__file__).read_text(encoding="utf-8")
    for bad in ("PolymarketGatewayClient", "place_order", "create_order", "/orders", "httpx", "MERIDIAN_ORDER_TOKEN", "api.polymarket"):
        assert bad not in src


def test_instructions_page_is_one_tap_from_the_desk_and_says_which_leg_first(desk):
    mod, c, out = desk
    assert "href='/instructions'" in c.get("/").text
    page = c.get("/instructions").text
    assert page.count("Leg 1 first") >= 1 and "within 60 seconds" in page and "cannot both lose" in page
    assert "BUF to win by over 13.5 points" in page and "tap <b>No</b>" in page
