"""Kalshi's relay of BRTI, the settlement index (2026-09-30): the handshake signature is the one the
venue documents, the documented message shape parses into a tick with both averages, the socket
delivers ticks to the microtape and reconnects after a drop, and without a Kalshi key the harness
runs as before and says so once."""
from __future__ import annotations

import base64
import json
import queue
import sqlite3
import threading

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, padding, rsa

from core.btc15.brti_relay import (BRTIRelay, BRTITick, MissingKalshiCredentials, SUBSCRIBE, auth_headers,
                                   credentials_from_env, load_private_key, parse_tick)
from core.btc15.microtape import Microtape
from core.polymarket.ws_min import ConnectionClosed

DOC_MSG = {"type": "cfbenchmarks_value", "sending_ts_ms": 1669149841234, "sid": 1, "seq": 42,
           "msg": {"index_id": "BRTI", "received_at": 1710000000123,
                   "data": "{\"type\":\"value\",\"id\":\"BRTI\",\"time\":1710000000123,\"value\":\"68000.12\"}",
                   "avg_60s_data": {"value": "68000.12000000", "window_size": 3,
                                    "window_start_ts_ms": 1709999940123, "window_end_ts_exclusive": 1710000000123},
                   "last_60s_windowed_average_15min": {"value": "68000.23000000", "window_size": 14,
                                                       "window_start_ts_ms": 1709999980000,
                                                       "window_end_ts_exclusive": 1710000000123}}}


def test_the_signature_is_rsa_pss_sha256_over_timestamp_method_path_and_verifies_with_the_public_key():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    h = auth_headers("kid-1", key, "/cfbenchmarks_value?x=1", ts_ms=1710000000123)
    assert h["KALSHI-ACCESS-KEY"] == "kid-1" and h["KALSHI-ACCESS-TIMESTAMP"] == "1710000000123"
    key.public_key().verify(base64.b64decode(h["KALSHI-ACCESS-SIGNATURE"]), b"1710000000123GET/cfbenchmarks_value",
                            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
                            hashes.SHA256())                       # the query string is not signed


def test_an_ed25519_key_signs_directly_and_a_pem_loads_either_kind(tmp_path, monkeypatch):
    key = ed25519.Ed25519PrivateKey.generate()
    h = auth_headers("kid-2", key, "/trade-api/ws/v2", ts_ms=5)
    key.public_key().verify(base64.b64decode(h["KALSHI-ACCESS-SIGNATURE"]), b"5GET/trade-api/ws/v2")
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    assert isinstance(load_private_key(pem), ed25519.Ed25519PrivateKey)
    (tmp_path / "k.pem").write_bytes(pem)
    monkeypatch.setenv("KALSHI_API_KEY_ID", "kid-2")
    monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", str(tmp_path / "k.pem"))
    monkeypatch.delenv("KALSHI_PRIVATE_KEY", raising=False)
    kid, pk = credentials_from_env()
    assert kid == "kid-2" and isinstance(pk, ed25519.Ed25519PrivateKey)
    monkeypatch.delenv("KALSHI_API_KEY_ID")
    try:
        credentials_from_env()
        raise AssertionError("no credentials must raise")
    except MissingKalshiCredentials:
        pass


def test_the_documented_message_parses_into_a_tick_with_both_averages_and_nothing_else_does():
    t = parse_tick(DOC_MSG, recv=1_790_700_000.5)
    assert t == BRTITick(recv=1_790_700_000.5, source_ts_ms=1710000000123, value=68000.12, avg_60s=68000.12,
                         last_60s_15m=68000.23, seq=42)
    early = json.loads(json.dumps(DOC_MSG)); early["msg"].pop("last_60s_windowed_average_15min")
    assert parse_tick(early, 1.0).last_60s_15m is None                # outside the final minute
    other = json.loads(json.dumps(DOC_MSG)); other["msg"]["index_id"] = "ETHUSD_RTI"
    assert parse_tick(other, 1.0) is None
    assert parse_tick({"id": 1, "type": "subscribed", "msg": {"channel": "cfbenchmarks_value"}}, 1.0) is None
    assert parse_tick({"type": "error", "msg": {"code": 6, "msg": "not authorized"}}, 1.0) is None


class FakeWS:
    def __init__(self, msgs):
        self.q = queue.Queue()
        for m in msgs:
            self.q.put(m)
        self.closed = threading.Event()
        self.sent = []

    def send_json(self, obj):
        self.sent.append(obj)

    def recv_json(self):
        while not self.closed.is_set():
            try:
                return self.q.get(timeout=0.02)
            except queue.Empty:
                continue
        raise ConnectionClosed("closed")

    def close(self):
        self.closed.set()


def test_the_relay_subscribes_delivers_ticks_to_the_microtape_and_reconnects_after_a_drop(tmp_path):
    clock = [1_790_700_000.0]
    tape = Microtape(str(tmp_path / "micro.sqlite"), clock=lambda: clock[0])
    second = json.loads(json.dumps(DOC_MSG)); second["seq"] = 43; second["msg"]["data"] = json.dumps({"type": "value", "id": "BRTI", "time": 1710000001123, "value": "68001.00"})
    sockets = [FakeWS([{"id": 1, "type": "subscribed"}, DOC_MSG]), FakeWS([second])]
    slept = []
    r = BRTIRelay("kid", None, on_tick=tape.brti, open_socket=lambda: sockets.pop(0), clock=lambda: clock[0],
                  sleep=lambda s: slept.append(s))
    assert r.sign_path == "/cfbenchmarks_value"
    r.start()
    for _ in range(200):
        if r.ticks >= 1:
            break
        threading.Event().wait(0.01)
    assert r.latest.value == 68000.12 and r.live(clock[0]) and r.counters()["last_60s_15m"] == 68000.23
    first = r._ws
    assert first.sent == [SUBSCRIBE]
    first.close()
    for _ in range(300):
        if r.ticks >= 2:
            break
        threading.Event().wait(0.01)
    assert r.latest.value == 68001.0 and r.reconnects == 1 and slept == [1.0]
    r.request_stop()
    tape.drain()
    rows = sqlite3.connect(tape.path).execute("SELECT recv, source_ts_ms, value, avg_60s, last_60s_15m, seq FROM brti ORDER BY seq").fetchall()
    assert rows == [(clock[0], 1710000000123, 68000.12, 68000.12, 68000.23, 42), (clock[0], 1710000001123, 68001.0, 68000.12, 68000.23, 43)]


def test_the_key_can_arrive_as_base64_pem_in_the_environment(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    monkeypatch.setenv("KALSHI_API_KEY_ID", "kid-3")
    monkeypatch.setenv("KALSHI_PRIVATE_KEY_B64", base64.b64encode(pem).decode() + "\n")
    for k in ("KALSHI_PRIVATE_KEY", "KALSHI_PRIVATE_KEY_PATH"):
        monkeypatch.delenv(k, raising=False)
    kid, pk = credentials_from_env()
    assert kid == "kid-3" and pk.public_key().public_numbers() == key.public_key().public_numbers()
    monkeypatch.setenv("KALSHI_PRIVATE_KEY_B64", "not base64!!")
    try:
        credentials_from_env()
        raise AssertionError("bad base64 must raise ValueError")
    except ValueError:
        pass


def test_a_key_that_does_not_load_leaves_the_harness_running_without_the_relay(tmp_path, monkeypatch, caplog):
    from core.btc15 import harness as H
    for k in ("KALSHI_PRIVATE_KEY_B64", "KALSHI_PRIVATE_KEY", "OPENAI_API_KEY", "MERIDIAN_BTC15_MODEL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("POLYMARKET_KEY_ID", "k")
    monkeypatch.setenv("POLYMARKET_SECRET", "s")
    monkeypatch.setattr(H, "KalshiBTC", lambda: None)
    monkeypatch.setenv("KALSHI_API_KEY_ID", "kid-4")
    for bad in (str(tmp_path / "missing.pem"), str(tmp_path)):                 # a wrong path; a directory
        monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", bad)
        with caplog.at_level("ERROR", logger="btc15"):
            h = H.build(H.Settings(db_path=str(tmp_path / f"p{len(bad)}.sqlite"), status_path="/dev/null", horizon="15m"))
        assert h.brti is None and h.microtape is not None and h.arms
        h.microtape.stop()
    (tmp_path / "bad.pem").write_bytes(b"this is not a pem at all\n")          # a file that is there but is no key
    monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", str(tmp_path / "bad.pem"))
    h = H.build(H.Settings(db_path=str(tmp_path / "p3.sqlite"), status_path="/dev/null", horizon="15m"))
    assert h.brti is None
    h.microtape.stop()
    assert all(bad not in rec.message for rec in caplog.records for bad in (str(tmp_path),))   # never the path itself


def test_without_a_kalshi_key_the_harness_builds_with_no_relay(tmp_path, monkeypatch, caplog):
    from core.btc15 import harness as H
    for k in ("KALSHI_API_KEY_ID", "KALSHI_PRIVATE_KEY_PATH", "KALSHI_PRIVATE_KEY", "KALSHI_PRIVATE_KEY_B64", "OPENAI_API_KEY", "MERIDIAN_BTC15_MODEL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("POLYMARKET_KEY_ID", "k")
    monkeypatch.setenv("POLYMARKET_SECRET", "s")
    monkeypatch.setattr(H, "KalshiBTC", lambda: None)
    with caplog.at_level("INFO", logger="btc15"):
        h = H.build(H.Settings(db_path=str(tmp_path / "polymarket-15m.sqlite"), status_path="/dev/null", horizon="15m"))
    assert h.brti is None and h.microtape is not None
    assert any("BRTI relay off" in rec.message for rec in caplog.records)
    h.microtape.stop()
