"""The BTC arms price off fresh books only.

Measured 2026-09-30 (analysis/btc15/quote_freshness_probe.py): the venue's REST book is a
Cloudflare cache (``cache-control: public, max-age=30``) that held one state for a mean of
24 s, and Kalshi's /markets list touch held one price for a mean of 32 s, while Kalshi's
order book changed every second. These pin the replacements: Kalshi's touch comes from its
order book (or there is none); the venue's comes from its market-data stream (or there is
none), and a stream is only a price while its socket is live on that window.
"""
from __future__ import annotations

import queue
import threading
import time

import httpx
import pytest

from core.btc15.kalshi import KalshiBTC, book_touch
from core.btc15.polymarket import PolymarketBTC, window_of
from core.btc15.stream_book import StreamBook
from core.polymarket.ws_min import ConnectionClosed

SLUG = "cpc-btc-updown-15m-2026-09-30-0215z"
O, C = window_of(SLUG)


# ------------------------------------------------------------------ Kalshi: the order book, not the list
def _kalshi(book_status=200, book=None):
    listed = {"ticker": "KXBTC15M-26SEP292230-30", "status": "active", "floor_strike": 83410.72,
              "open_time": "2026-09-30T02:15:00Z", "close_time": "2026-09-30T02:30:00Z",
              "yes_bid_dollars": "0.4300", "yes_ask_dollars": "0.4400"}          # the lagging list touch
    book = book if book is not None else {"orderbook_fp": {
        "yes_dollars": [["0.3000", "100.00"], ["0.3300", "50.00"], ["0.3400", "0.00"]],
        "no_dollars": [["0.6500", "10.00"], ["0.6600", "20.00"]]}}

    def handler(req):
        if req.url.path.endswith("/orderbook"):
            return httpx.Response(book_status, json=book)
        if req.url.path.endswith("/markets"):
            return httpx.Response(200, json={"markets": [listed]})
        return httpx.Response(404, json={})
    return KalshiBTC(client=httpx.Client(transport=httpx.MockTransport(handler)), base="https://k.test/v2")


def test_kalshis_touch_is_its_order_books_best_bid_and_one_minus_the_best_no_bid():
    k = _kalshi().current(O + 60)
    assert k["touch_source"] == "orderbook" and k["strike"] == 83410.72
    assert (k["yes_bid"], k["yes_ask"]) == (0.33, 0.34)                  # not the list's 0.43 / 0.44
    assert (k["yes_bid_size"], k["yes_ask_size"]) == (50.0, 20.0)        # an empty level is not the touch
    assert (k["no_bid"], k["no_ask"]) == (0.66, 0.67)


def test_an_unreadable_or_one_sided_kalshi_book_is_no_price_never_the_lists():
    for bad in (_kalshi(book_status=500), _kalshi(book={"orderbook_fp": {"yes_dollars": [["0.3300", "5"]], "no_dollars": []}})):
        k = bad.current(O + 60)
        assert k["touch_source"] == "none" and k["yes_bid"] is None and k["yes_ask"] is None
    assert book_touch(None) is None


# ------------------------------------------------------------------ the venue: the stream, not the cache
class FakeWS:
    """A socket the StreamConnection can drive: queued messages, then blocks until closed."""

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


def _md(slug, bid, ask):
    return {"marketData": {"marketSlug": slug, "state": "MARKET_STATE_OPEN",
                           "bids": [{"px": {"value": bid}, "qty": "120"}], "offers": [{"px": {"value": ask}, "qty": "80"}]}}


def _wait(pred, s=2.0):
    end = time.time() + s
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.01)
    return False


def test_the_stream_book_holds_the_last_touch_for_the_window_it_is_subscribed_to():
    ws = FakeWS([{"heartbeat": {}}, _md(SLUG, "0.4100", "0.4300"), _md(SLUG, "0.4500", "0.4700")])
    sb = StreamBook(open_socket=lambda: ws)
    sb.ensure(SLUG)
    try:
        assert _wait(lambda: (sb.touch(SLUG) or {}).get("bid") == 0.45)
        t = sb.touch(SLUG)
        assert (t["bid"], t["ask"], t["bid_size"], t["ask_size"]) == (0.45, 0.47, 120.0, 80.0)
        assert ws.sent and "subscribe" in ws.sent[0]                   # it subscribed before reading
        assert sb.touch("cpc-btc-updown-15m-2026-09-30-0230z") is None  # another window is not this one
        assert sb.touch(SLUG, now=time.time() + 60) is None             # a silent socket is not a price
    finally:
        sb.stop()
    assert sb.touch(SLUG) is None


def test_a_stream_without_credentials_never_subscribes_and_is_never_a_price():
    sb = StreamBook(enabled=False, open_socket=lambda: pytest.fail("must not open"))
    sb.ensure(SLUG)
    assert sb.conn is None and sb.touch(SLUG) is None


class FakeStream:
    def __init__(self, touch):
        self._touch, self.ensured = touch, []

    def ensure(self, slug):
        self.ensured.append(slug)

    def touch(self, slug, now=None):
        return self._touch


def _venue(stream):
    def handler(req):
        path = req.url.path
        if path == "/v1/markets":
            return httpx.Response(200, json={"markets": []})
        if path.endswith("/book"):                                      # the cached REST book
            return httpx.Response(200, json={"marketData": {"state": "MARKET_STATE_OPEN",
                                  "bids": [{"px": {"value": "0.4100"}, "qty": "10"}], "offers": [{"px": {"value": "0.4300"}, "qty": "12"}]}})
        return httpx.Response(404, json={})
    return PolymarketBTC(client=httpx.Client(transport=httpx.MockTransport(handler), base_url="https://gateway.polymarket.us"),
                         strike_source=lambda a, b: 83000.0, clock=lambda: O + 60, stream=stream)


def test_with_a_stream_the_venue_prices_off_it_and_never_falls_back_to_the_cache():
    s = FakeStream({"bid": 0.50, "ask": 0.52, "bid_size": 5.0, "ask_size": 7.0, "state": "MARKET_STATE_OPEN"})
    v = _venue(s)
    m = v.current(O + 60)
    assert m["book_source"] == "stream" and (m["yes_bid"], m["yes_ask"]) == (0.50, 0.52) and s.ensured == [SLUG]
    q = v.quote(SLUG)
    assert q["book_source"] == "stream" and q["yes_ask_u"] == 5200 and q["yes_ask_size"] == 7.0
    down = _venue(FakeStream(None))
    m = down.current(O + 60)
    assert m["book_source"] == "stream_down" and m["yes_bid"] is None and m["yes_ask"] is None
    rest = _venue(None).current(O + 60)
    assert rest["book_source"] == "rest" and rest["yes_bid"] == 0.41


# ------------------------------------------------------------------ every message ticks the arms (2026-09-30)
def test_the_stream_book_reports_every_update_to_its_handler():
    seen = []
    ws = FakeWS([_md(SLUG, "0.4100", "0.4300"), _md(SLUG, "0.4200", "0.4400")])
    sb = StreamBook(open_socket=lambda: ws, on_update=seen.append)
    sb.ensure(SLUG)
    try:
        assert _wait(lambda: len(seen) == 2)
        assert seen == [SLUG, SLUG] and sb.touch(SLUG)["bid"] == 0.42
    finally:
        sb.stop()


def test_kalshi_rereads_its_list_every_ten_seconds_and_its_book_every_call(monkeypatch):
    import core.btc15.kalshi as K
    calls = {"list": 0, "book": 0}
    listed = {"ticker": "KXBTC15M-26SEP301200-00", "status": "active", "floor_strike": 1.0,
              "open_time": "2026-09-30T02:15:00Z", "close_time": "2026-09-30T02:30:00Z",
              "yes_bid_dollars": "0.4300", "yes_ask_dollars": "0.4400"}

    def handler(req):
        if req.url.path.endswith("/orderbook"):
            calls["book"] += 1
            return httpx.Response(200, json={"orderbook_fp": {"yes_dollars": [["0.3300", "5"]], "no_dollars": [["0.6600", "5"]]}})
        calls["list"] += 1
        return httpx.Response(200, json={"markets": [listed]})
    k = K.KalshiBTC(client=httpx.Client(transport=httpx.MockTransport(handler)), base="https://k.test/v2")
    clock = [1000.0]
    monkeypatch.setattr(K.time, "time", lambda: clock[0])
    for i in range(5):
        clock[0] += 1
        assert k.current(O + 60)["yes_bid"] == 0.33
    assert calls == {"list": 1, "book": 5}
    clock[0] += 11
    k.current(O + 60)
    assert calls["list"] == 2
    assert k.current(O + 5000) is None and calls["list"] == 3                # no window for that instant: one fresh read
