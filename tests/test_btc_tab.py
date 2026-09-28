"""The dashboard's BTC tab reads the bot's ledger and never writes it.

The bot (core/btc15/harness.py) is the only writer of its SQLite ledger; the
api container mounts the directory read-only and core/btc15/desk.py opens it
with mode=ro. These tests build a ledger the way the harness does, then read
it through the desk and through the api routes.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time

import pytest

os.environ.setdefault("MERIDIAN_BTC15_DB", ":memory:")

from core.btc15 import desk  # noqa: E402
from core.btc15.ledger import Ledger  # noqa: E402

NOW = 1_790_557_500.0            # inside the 01:00Z window of 2026-09-28


def _build(root):
    led = Ledger(str(root / "polymarket-15m.sqlite"))
    for i, (tk, o, strike, res, settle) in enumerate([
            ("cpc-btc-updown-15m-2026-09-28-0045z", 1_790_556_300.0, 84272.52, "no", 84142.39),
            ("cpc-btc-updown-15m-2026-09-28-0100z", 1_790_557_200.0, 84142.39, None, None)]):
        led.upsert_window({"ticker": tk, "open_time": None, "close_time": None, "open_ts": o,
                           "close_ts": o + 900, "strike": strike})
        feats = {"baselines": {"market_p_up": 0.415, "brownian_p_up": 0.4219},
                 "price": {"btc_usd_now": 84095.58, "distance_in_sigma_to_close": -0.192},
                 "market": {"other_venue_p_up": 0.445}}
        assert led.start_decision(tk, "gpt-6-astra", feats)
        usage = {"prompt_tokens": 1427, "completion_tokens": 191,
                 "prompt_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 1424}}
        led.finish_decision(tk, status="filled", p_up=0.42, side="NO", confidence="medium",
                            rationale="below the line", response=json.dumps({"key_factors": ["a", "b"]}),
                            usage=json.dumps(usage), answered_at="2026-09-28T01:00:37+00:00", latency_s=6.4)
        fid, why = led.record_fill("paper", tk, "NO", 5900, 200)
        assert fid, why
        if res:
            led.finalize_window(tk, res, settle, 84139.55)
            led.settle(fid, res)
            led.finish_decision(tk, lesson="keep anchoring to the strike distance")
    led.add_ticks([(NOW - 60 + i, 84100.0 + i, 4, 0.5) for i in range(60)])
    (root / "status-15m.json").write_text(json.dumps(
        {"at": "2026-09-28T01:04:30+00:00", "mode": "paper", "model": "gpt-6-astra",
         "openai_today": {"cap_usd": 10.0}}))
    return led


def test_the_desk_reads_the_call_the_fill_and_the_settlement(tmp_path):
    _build(tmp_path)
    s = desk.summary(tmp_path, "15m", now=NOW)
    cur = s["current"]
    assert cur["ticker"].endswith("0100z") and cur["strike"] == 84142.39
    d = cur["decision"]
    assert d["p_up"] == 0.42 and d["side"] == "NO" and d["key_factors"] == ["a", "b"]
    assert d["market_p_up"] == 0.415 and d["random_walk_p_up"] == 0.4219 and d["other_venue_p_up"] == 0.445
    assert d["cost_usd"] == pytest.approx((3 * 10 + 1424 * 12.5 + 191 * 50) / 1e6)
    assert cur["fill"]["price"] == 0.59 and cur["fill"]["fee"] == 0.02 and cur["fill"]["pnl"] is None
    assert s["last_tick"]["px"] == 84159.0 and s["mode"] == "paper"
    # the 00:45Z window settled Down; the bot held Down at 59c + 2c: +$0.39
    assert s["account"]["settled"] == 1 and s["account"]["pnl"] == pytest.approx(0.39)
    assert s["pnl_curve"][-1]["cum"] == pytest.approx(0.39)
    assert [x["lesson"] for x in s["lessons"]] == ["keep anchoring to the strike distance"]
    assert s["lessons"][0]["result"] == "no" and s["lessons"][0]["side"] == "NO"
    rows = desk.history(tmp_path, "15m")
    assert [r["ticker"][-5:] for r in rows] == ["0100z", "0045z"]
    assert rows[1]["result"] == "no" and rows[1]["fill"]["pnl"] == pytest.approx(0.39)


def test_the_desk_cannot_write_the_ledger(tmp_path):
    _build(tmp_path)
    led = desk._ro(tmp_path / "polymarket-15m.sqlite")
    with pytest.raises(sqlite3.OperationalError):
        led._conn.execute("DELETE FROM fills")


def test_ticks_are_bucketed_to_the_last_price(tmp_path):
    _build(tmp_path)
    out = desk.ticks(tmp_path, "15m", NOW - 600, points=6)
    assert out["px"] and out["px"][-1][1] == 84159.0
    assert len(out["windows"]) == 2 and out["windows"][-1]["side"] == "NO"


def test_a_missing_ledger_is_not_found_and_an_unknown_horizon_is_refused(tmp_path):
    with pytest.raises(FileNotFoundError):
        desk.summary(tmp_path, "15m")
    with pytest.raises(ValueError):
        desk.paths(tmp_path, "5m")


def test_the_routes_answer_from_the_mounted_directory(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from core.api import app
    _build(tmp_path)
    monkeypatch.setenv("MERIDIAN_BTC_DIR", str(tmp_path))
    monkeypatch.setattr(desk, "live_book", lambda h, **k: None)     # no venue call in a test
    c = TestClient(app)
    s = c.get("/api/btc/summary?h=15m")
    assert s.status_code == 200 and s.json()["current"]["decision"]["side"] == "NO"
    assert c.get("/api/btc/history?h=15m&limit=5").json()["rows"][0]["ticker"].endswith("0100z")
    assert c.get("/api/btc/ticks?h=15m&minutes=5").status_code == 200
    assert c.get("/api/btc/summary?h=1h").status_code == 404          # no hourly ledger here
    assert c.get("/api/btc/summary?h=5m").status_code == 422          # not a horizon
    assert c.get("/btc").status_code == 200


def test_the_book_cache_asks_the_venue_once_per_ttl():
    calls = []

    class V:
        def current(self, now):
            calls.append(now)
            return {"ticker": "t", "yes_bid": 0.41, "yes_ask": 0.42}
    desk._BOOK.clear()
    t = time.time()
    assert desk.live_book("15m", venue=V(), now=t)["yes_ask"] == 0.42
    desk.live_book("15m", venue=V(), now=t + 1)
    assert len(calls) == 1
    desk.live_book("15m", venue=V(), now=t + desk._BOOK_TTL_S + 0.1)
    assert len(calls) == 2
