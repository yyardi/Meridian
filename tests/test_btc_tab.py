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
    # return on what was staked: +$0.39 on 59c + 2c
    assert s["pnl_curve"][-1]["cost"] == pytest.approx(0.61) and s["account"]["staked"] == pytest.approx(0.61)
    assert s["account"]["roi"] == pytest.approx(0.39 / 0.61, abs=1e-4)
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
    assert isinstance(s.json()["page_version"], int)          # the open tab reloads when this changes
    assert c.get("/btc").headers["cache-control"] == "no-cache"
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


def test_the_arms_table_reads_every_arm_ledger_beside_the_models(tmp_path, monkeypatch):
    from core.btc15.arms import Arm, ArmSpec
    from core.btc15.ledger import UNIT
    _build(tmp_path)
    led = Ledger(str(tmp_path / "polymarket-15m-arm-walk_taker.sqlite"))
    arm = Arm(ArmSpec("walk_taker", "walk", "taker", 0.04), led, 10 * UNIT)
    m = {"ticker": "cpc-btc-updown-15m-2026-09-28-0045z", "status": "active", "open_ts": 1_790_556_300.0,
         "close_ts": 1_790_557_200.0, "open_time": None, "close_time": None, "strike": 84272.52,
         "yes_bid": 0.30, "yes_ask": 0.32, "yes_bid_u": 3000, "yes_ask_u": 3200}
    arm.tick(m["open_ts"] + 60, m, {"walk": 0.10}, 0.0695, 90)       # NO at 0.70: EV 0.90-0.70-0.02 = 0.18
    arm.settle({m["ticker"]: "no"}, {m["ticker"]: ("no", 84142.39, None)})
    rows = desk.arms(tmp_path, "15m", now=NOW, include_v1=True)
    names = [r["name"] for r in rows]
    assert names[0] == "favourite" and "walk_taker" in names
    assert [r["name"] for r in desk.arms(tmp_path, "15m", now=NOW)] == ["walk_taker"]   # v1 hidden by default
    w = next(r for r in rows if r["name"] == "walk_taker")
    assert w["settled"] == 1 and w["wins"] == 1 and w["pnl"] == pytest.approx(1 - 0.70 - 0.02)
    assert w["roi"] == pytest.approx(0.28 / 0.72, abs=1e-4) and w["spec"]["kind"] == "taker"


def test_the_page_can_show_one_strategys_own_record_and_calls(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from core.api import app
    from core.btc15.arms import Arm, ArmSpec
    from core.btc15.ledger import UNIT
    _build(tmp_path)
    led = Ledger(str(tmp_path / "polymarket-15m-arm-llm_agent.sqlite"))
    arm = Arm(ArmSpec("llm_agent", "llm", "agent", 0.0), led, 10 * UNIT)
    old = {"ticker": "cpc-btc-updown-15m-2026-09-28-0045z", "status": "active", "open_ts": 1_790_556_300.0,
           "close_ts": 1_790_557_200.0, "open_time": None, "close_time": None, "strike": 84272.52,
           "yes_bid": 0.30, "yes_ask": 0.32, "yes_bid_u": 3000, "yes_ask_u": 3200}
    arm.tick(old["open_ts"] + 60, old, {"llm_action": {"action": "buy_down", "limit_price": 0.75, "p_up": 0.2}}, 0.0695, 90)
    arm.settle({old["ticker"]: "no"}, {old["ticker"]: ("no", 84142.39, None)})

    s = desk.summary(tmp_path, "15m", now=NOW, arm="llm_agent")
    assert s["arm"] == "llm_agent" and s["arm_spec"]["kind"] == "agent"
    assert s["account"]["settled"] == 1 and s["account"]["pnl"] == pytest.approx(1 - 0.70 - 0.02)
    # the agent has not reached the window in play: the window shows, with no call
    assert s["current"]["ticker"].endswith("0100z") and s["current"]["decision"] is None
    assert s["last_tick"]["px"] == 84159.0                        # the price feed is the model's ledger's
    rows = desk.history(tmp_path, "15m", arm="llm_agent")
    assert [r["ticker"][-5:] for r in rows] == ["0045z"] and rows[0]["fill"]["side"] == "NO"
    with pytest.raises(FileNotFoundError):
        desk.summary(tmp_path, "15m", arm="nope")

    monkeypatch.setenv("MERIDIAN_BTC_DIR", str(tmp_path))
    monkeypatch.setattr(desk, "live_book", lambda h, **k: None)
    c = TestClient(app)
    assert c.get("/api/btc/summary?h=15m&arm=llm_agent").json()["account"]["settled"] == 1
    assert c.get("/api/btc/history?h=15m&arm=llm_agent").json()["rows"][0]["fill"]["side"] == "NO"
    assert c.get("/api/btc/summary?h=15m&arm=nope").status_code == 404
    assert c.get("/api/btc/summary?h=15m&arm=../x").status_code == 422


# ------------------------------------------------------------------ the edge estimate
def _arm_ledger(root, name, trades):
    """An arm ledger with one settled contract per (side, price, fee, p_up, result)."""
    from core.btc15.ledger import UNIT
    led = Ledger(str(root / f"polymarket-15m-arm-{name}.sqlite"))
    led.put("arm_spec", json.dumps({"name": name, "prob": "kalshi", "kind": "taker", "margin": 0.04}))
    for i, (side, price, fee, p_up, res) in enumerate(trades):
        tk = f"W{i}"
        led.upsert_window({"ticker": tk, "open_time": None, "close_time": None, "open_ts": 1_790_000_000.0 + 900 * i,
                           "close_ts": 1_790_000_900.0 + 900 * i, "strike": 1.0})
        assert led.start_decision(tk, None, {})
        led.finish_decision(tk, status="filled", side=side, p_up=p_up)
        fid, why = led.record_fill("paper", tk, side, int(round(price * UNIT)), int(round(fee * UNIT)), 100 * UNIT)
        assert fid, why
        led.finalize_window(tk, res, 2.0, None)
        led.settle(fid, res)
    return led


def test_the_edge_is_the_mean_pnl_per_contract_with_its_interval_and_the_edge_claimed_at_entry(tmp_path):
    import statistics
    trades = [("YES", 0.60, 0.02, 0.70, "yes"),       # +0.38 realised; claimed 0.70 - 0.62 = 0.08
              ("NO", 0.55, 0.02, 0.30, "yes"),        # -0.57; claimed (1 - 0.30) - 0.57 = 0.13
              ("YES", 0.40, 0.02, 0.50, "yes")]       # +0.58; claimed 0.50 - 0.42 = 0.08
    led = _arm_ledger(tmp_path, "kalshi_taker_wide", trades)
    # the first fill predates the checkpoint: it chose the arm and does not count toward the read
    led._conn.execute("UPDATE fills SET filled_at = '2026-09-29T19:00:00+00:00' WHERE ticker = 'W0'")
    pnl = [0.38, -0.57, 0.58]
    m, se = statistics.mean(pnl), statistics.stdev(pnl) / 3 ** 0.5
    e = desk.edge(desk._ro(tmp_path / "polymarket-15m-arm-kalshi_taker_wide.sqlite"))
    a = e["all"]
    assert a["n"] == 3 and a["mean_c"] == pytest.approx(100 * m, abs=0.01)
    assert a["se_c"] == pytest.approx(100 * se, abs=0.01) and a["t"] == pytest.approx(m / se, abs=0.01)
    assert a["lo_c"] == pytest.approx(100 * (m - 1.96 * se), abs=0.01)
    assert a["hi_c"] == pytest.approx(100 * (m + 1.96 * se), abs=0.01)
    assert e["entry_c"] == pytest.approx(100 * (0.08 + 0.13 + 0.08) / 3, abs=0.01) and e["entry_n"] == 3
    assert e["since"]["n"] == 2 and e["since"]["mean_c"] == pytest.approx(100 * (-0.57 + 0.58) / 2, abs=0.01)
    # the running curve ends where the whole-sample estimate is, and has no interval at n = 1
    assert [p[1] for p in e["curve"]] == [1, 2, 3]
    assert e["curve"][0][3] is None and e["curve"][0][2] == pytest.approx(38.0)
    assert e["curve"][-1][2:5] == pytest.approx([a["mean_c"], a["lo_c"], a["hi_c"]], abs=0.01)
    assert e["curve"][-1][5] == pytest.approx(e["entry_c"], abs=0.01)


def test_the_tab_names_the_4c_arm_by_its_margin_and_keeps_its_ledger_key(tmp_path):
    _build(tmp_path)
    _arm_ledger(tmp_path, "kalshi_taker_wide", [("YES", 0.60, 0.02, 0.70, "yes")])
    rows = desk.arms(tmp_path, "15m", now=NOW)
    assert [(r["name"], r["label"]) for r in rows] == [("kalshi_taker_wide", "kalshi_taker_4c")]
    assert rows[0]["edge"]["all"]["n"] == 1 and len(rows[0]["edge_curve"]) == 1
    s = desk.summary(tmp_path, "15m", now=NOW, arm="kalshi_taker_wide")
    assert s["arm_label"] == "kalshi_taker_4c" and s["edge"]["all"]["mean_c"] == pytest.approx(38.0)


# ------------------------------------------------------------------ a fresh allocation (2026-09-30)
def test_a_new_epoch_shows_only_the_fresh_record_and_keeps_the_old_one_in_the_file(tmp_path):
    from core.btc15.ledger import UNIT
    _build(tmp_path)
    led = _arm_ledger(tmp_path, "kalshi_taker_wide", [("YES", 0.60, 0.02, 0.70, "no")])     # old: -0.62
    led.new_epoch("paper")
    assert led.epoch("paper") == 2 and led.epoch_from("paper") is not None
    tk, o = "W-fresh", time.time() - 60
    led.upsert_window({"ticker": tk, "open_time": None, "close_time": None, "open_ts": o, "close_ts": o + 900, "strike": 1.0})
    assert led.start_decision(tk, None, {})
    led.finish_decision(tk, status="filled", side="YES", p_up=0.70)
    fid, why = led.record_fill("paper", tk, "YES", int(0.60 * UNIT), int(0.02 * UNIT), 100 * UNIT)
    led.finalize_window(tk, "yes", 2.0, None)
    led.settle(fid, "yes")                                                                  # fresh: +0.38
    row = desk.arms(tmp_path, "15m", now=NOW)[0]
    assert row["settled"] == 1 and row["pnl"] == pytest.approx(0.38) and row["edge"]["all"]["n"] == 1
    assert [r["ticker"] for r in desk.history(tmp_path, "15m", arm="kalshi_taker_wide")] == [tk]
    s = desk.summary(tmp_path, "15m", now=o + 120, arm="kalshi_taker_wide")
    assert s["account"]["settled"] == 1 and s["epoch_from"] == led.epoch_from("paper")
    # nothing was deleted: the old epoch is still in the file
    assert led.account("paper", epoch=1)["settled"] == 1 and led._conn.execute("SELECT COUNT(*) FROM fills").fetchone()[0] == 2


def test_the_arms_new_epoch_command_leaves_the_models_own_ledger_alone(tmp_path, monkeypatch):
    from core.btc15 import harness
    _build(tmp_path)
    for name in ("kalshi_taker_wide", "llm_agent"):
        _arm_ledger(tmp_path, name, [("YES", 0.60, 0.02, 0.70, "yes")])
    monkeypatch.setenv("MERIDIAN_BTC15_DB", str(tmp_path / "polymarket-15m.sqlite"))
    assert harness.main(["--new-epoch", "paper", "--arms"]) == 0
    for name in ("kalshi_taker_wide", "llm_agent"):
        assert Ledger(str(tmp_path / f"polymarket-15m-arm-{name}.sqlite")).epoch("paper") == 2
    assert Ledger(str(tmp_path / "polymarket-15m.sqlite")).epoch("paper") == 1
