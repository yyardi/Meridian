"""The stream client speaks RFC 6455 correctly and the freshness runner can't trade."""
from __future__ import annotations

import importlib
import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
ws = importlib.import_module("core.polymarket.ws_min")
FR = importlib.import_module("cfb.run_ws_freshness")
FR_SRC = pathlib.Path(FR.__file__).read_text(encoding="utf-8")
WS_SRC = pathlib.Path(ws.__file__).read_text(encoding="utf-8")


def _reader(buf: bytes):
    pos = [0]

    def read_exact(n):
        out = buf[pos[0]:pos[0] + n]
        assert len(out) == n, "truncated"
        pos[0] += n
        return out
    return read_exact


def test_accept_key_matches_the_rfc_example():
    assert ws.accept_key("dGhlIHNhbXBsZSBub25jZQ==") == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="


def test_frames_round_trip_masked_and_unmasked_at_every_length_class():
    for n in (0, 5, 125, 126, 300, 65535, 65536, 70000):
        payload = bytes(i % 251 for i in range(n))
        for mask in (True, False):
            fin, op, data = ws.read_frame(_reader(ws.encode_frame(ws.OP_TEXT, payload, mask=mask)))
            assert fin and op == ws.OP_TEXT and data == payload


def test_client_frames_are_masked_with_a_random_key():
    a, b = ws.encode_frame(ws.OP_TEXT, b"hello"), ws.encode_frame(ws.OP_TEXT, b"hello")
    assert a[1] & 0x80 and b[1] & 0x80 and a != b


def test_extended_length_headers_are_network_order():
    f = ws.encode_frame(ws.OP_BIN, b"x" * 300, mask=False)
    assert f[1] & 0x7F == 126 and struct.unpack("!H", f[2:4]) == (300,)
    f = ws.encode_frame(ws.OP_BIN, b"x" * 70000, mask=False)
    assert f[1] & 0x7F == 127 and struct.unpack("!Q", f[2:10]) == (70000,)


def test_subscribe_messages_cover_both_documented_spellings():
    msgs = FR.subscribe_msgs("md", "SUBSCRIPTION_TYPE_MARKET_DATA", ["a", "b"])
    assert msgs[0]["subscribe"]["subscriptionType"] == "SUBSCRIPTION_TYPE_MARKET_DATA"
    assert msgs[1]["subscribe"]["subscription_type"] == 1 and msgs[1]["subscribe"]["market_slugs"] == ["a", "b"]
    assert FR.subscribe_msgs("tr", "SUBSCRIPTION_TYPE_TRADE", ["a"])[1]["subscribe"]["subscription_type"] == 3


def test_compare_reports_touch_equality_and_rest_lag():
    now = 1_800_000_000.0
    stamp = lambda ago: __import__("datetime").datetime.fromtimestamp(now - ago, __import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + ".000000000Z"
    rungs = {3.5: (0.40, 0.42, 100.0, 50.0)}
    meta = {3.5: stamp(30)}
    stream = {"s-pos-3pt5": {"tt": stamp(2), "touch": (0.41, 0.43, 10.0, 5.0), "recv": now - 1}}
    rows = FR.compare(rungs, meta, stream, {"s-pos-3pt5": 3.5}, now)
    assert len(rows) == 1 and rows[0]["touch_equal"] is False
    assert abs(rows[0]["rest_behind_s"] - 28.0) < 0.01, "REST book is 28s older than the stream's"
    rows = FR.compare(rungs, meta, {}, {"s-pos-3pt5": 3.5}, now)
    assert "ws" not in rows[0], "no stream yet: rest-only row, no comparison invented"


def test_neither_module_can_place_an_order_or_open_the_private_stream():
    for src in (FR_SRC, WS_SRC):
        for bad in ("place_order", "submit_order", "create_order", "MERIDIAN_ORDER_TOKEN", "/orders", "ws/private"):
            assert bad not in src
    assert "/v1/ws/markets" in FR_SRC
