"""The sub-second instruments: the microtape, the stream's print record, the exchange sockets and
the non-blocking price feed (2026-09-30).

Measured before this: the ledger's once-a-second tape was written every 1.85-3.7 s and 13-17 % of
the composite's seconds were skipped waiting on a REST ticker. These pin what replaces it: every
book message and print recorded at receipt on one clock, spot at the exchanges' own cadence, and
a ``tick`` that never waits on the network.
"""
from __future__ import annotations

import json
import queue
import sqlite3
import threading

import httpx

from core.btc15.microtape import Microtape
from core.btc15.prices import EXCHANGES, PriceFeed, Quote, SOCKET_FRESH_S
from core.btc15.spot_ws import SpotSocket, parse_coinbase, parse_kraken
from core.btc15.stream_book import StreamBook
from core.polymarket.ws_min import ConnectionClosed

SLUG = "cpc-btc-updown-15m-2026-09-30-2015z"


# ------------------------------------------------------------------ the microtape
def test_every_book_message_print_and_spot_quote_lands_with_its_receive_time(tmp_path):
    tape = Microtape(str(tmp_path / "micro.sqlite"), clock=lambda: 1_790_700_000.0)
    tape.book({"slug": SLUG, "bid": 0.44, "ask": 0.45, "bid_size": 500.0, "ask_size": 610.0,
               "tt": "2026-09-30T20:16:01.123Z", "state": "MARKET_STATE_OPEN"}, at=1_790_700_001.25)
    tape.trade({"slug": SLUG, "price": 0.45, "quantity": 12.0, "tradeTime": "2026-09-30T20:16:01.5Z",
                "taker_intent": "ORDER_INTENT_BUY_LONG", "maker_intent": "ORDER_INTENT_UNDEFINED"}, at=1_790_700_001.55)
    tape.spot("coinbase", 84000.1, 84000.2, 84000.15, 1_790_700_001.31)
    tape.spot("coinbase", 84000.1, 84000.2, 84000.10, 1_790_700_001.35)      # same touch, another trade: not a new row
    tape.spot("coinbase", 84000.1, 84000.3, 84000.10, 1_790_700_001.40)      # the ask moved: a row
    assert tape.drain() == 4
    c = sqlite3.connect(tape.path)
    assert c.execute("SELECT recv, slug, bid, ask, bid_size, ask_size, tt, state FROM book_msgs").fetchall() == [
        (1_790_700_001.25, SLUG, 0.44, 0.45, 500.0, 610.0, "2026-09-30T20:16:01.123Z", "MARKET_STATE_OPEN")]
    assert c.execute("SELECT recv, slug, price, quantity, taker_intent, maker_intent FROM trades").fetchall() == [
        (1_790_700_001.55, SLUG, 0.45, 12.0, "ORDER_INTENT_BUY_LONG", "ORDER_INTENT_UNDEFINED")]
    assert c.execute("SELECT recv, exchange, bid, ask, last FROM spot ORDER BY recv").fetchall() == [
        (1_790_700_001.31, "coinbase", 84000.1, 84000.2, 84000.15), (1_790_700_001.40, "coinbase", 84000.1, 84000.3, 84000.10)]
    assert tape.counters()["written"] == {"book": 1, "trade": 1, "spot": 2}


def test_a_full_queue_drops_and_counts_and_old_rows_are_pruned(tmp_path):
    now = 1_790_700_000.0
    tape = Microtape(str(tmp_path / "micro.sqlite"), clock=lambda: now, max_queue=2, keep_days=1.0)
    for i in range(3):
        tape.spot("kraken", 1.0 + i, 2.0, 1.5, now - 2 * 86400 + i)  # older than keep_days
    assert tape.dropped == 1 and tape.drain() == 2
    tape.spot("kraken", 9.0, 2.0, 1.5, now)
    tape.drain()
    tape.prune(now)
    assert sqlite3.connect(tape.path).execute("SELECT COUNT(*) FROM spot").fetchone()[0] == 1


def test_the_writer_thread_drains_on_its_own_and_prunes_only_old_rows(tmp_path):
    import time
    tape = Microtape(str(tmp_path / "micro.sqlite"), flush_s=0.02).start()
    tape.spot("coinbase", 1.0, 2.0, 1.5, time.time())              # a row stamped 1970 would be pruned as 56 years old
    tape.stop(timeout=2.0)
    assert sqlite3.connect(tape.path).execute("SELECT COUNT(*) FROM spot").fetchone()[0] == 1


# ------------------------------------------------------------------ the stream keeps prints and hands rows to the tape
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


def _book_msg(bid, ask, bid_size=100.0, ask_size=100.0):
    return {"marketData": {"marketSlug": SLUG, "bids": [{"px": {"value": str(bid)}, "qty": str(bid_size)}],
                           "offers": [{"px": {"value": str(ask)}, "qty": str(ask_size)}],
                           "state": "MARKET_STATE_OPEN", "transactTime": "2026-09-30T20:16:01.1Z"}}


def _trade_msg(price, qty, taker, maker):
    return {"trade": {"marketSlug": SLUG, "price": {"value": str(price)}, "quantity": {"value": str(qty)},
                      "tradeTime": "2026-09-30T20:16:02.2Z", "taker": {"intent": taker}, "maker": {"intent": maker}}}


def test_the_stream_records_prints_at_receipt_and_calls_the_tape_hooks_before_the_arms():
    clock = [1_790_700_000.0]
    seen = []
    ws = FakeWS([{"ok": True}, _book_msg(0.44, 0.45), _trade_msg(0.44, 7.0, "ORDER_INTENT_BUY_SHORT", "ORDER_INTENT_UNDEFINED")])
    sb = StreamBook(open_socket=lambda: ws, clock=lambda: clock[0],
                    on_update=lambda slug: seen.append(("update", slug)),
                    on_book=lambda row, at: seen.append(("book", row["bid"], at)),
                    on_trade=lambda row, at: seen.append(("trade", row["price"], row["quantity"], at)))
    sb.ensure(SLUG)
    for _ in range(200):
        if len(seen) >= 3:
            break
        threading.Event().wait(0.01)
    assert seen[:3] == [("book", 0.44, clock[0]), ("update", SLUG), ("trade", 0.44, 7.0, clock[0])]
    assert sb.prints(SLUG, since=clock[0] - 1) == [(clock[0], 0.44, 7.0, "ORDER_INTENT_BUY_SHORT", "ORDER_INTENT_UNDEFINED")]
    assert sb.prints(SLUG, since=clock[0]) == []                       # strictly after
    assert sb.prints("another-window", since=0) == []                 # not the window on the socket
    sb.stop()


def test_a_hook_that_raises_never_drops_the_socket():
    clock = [1_790_700_000.0]
    ws = FakeWS([_book_msg(0.44, 0.45), _book_msg(0.45, 0.46)])
    sb = StreamBook(open_socket=lambda: ws, clock=lambda: clock[0], on_book=lambda row, at: 1 / 0)
    sb.ensure(SLUG)
    for _ in range(200):
        t = sb.touch(SLUG)
        if t and t["bid"] == 0.45:
            break
        threading.Event().wait(0.01)
    assert sb.touch(SLUG)["bid"] == 0.45 and sb.conn.reconnects == 0
    sb.stop()


# ------------------------------------------------------------------ the exchange sockets
def test_the_ticker_parsers_read_the_exchanges_shapes_and_nothing_else():
    assert parse_coinbase({"type": "ticker", "product_id": "BTC-USD", "price": "84001.5", "best_bid": "84001.0",
                           "best_ask": "84002.0", "time": "2026-09-30T20:16:01.1Z"}) == (84001.0, 84002.0, 84001.5)
    assert parse_coinbase({"type": "subscriptions", "channels": []}) is None
    assert parse_coinbase({"type": "ticker", "product_id": "ETH-USD", "price": "1", "best_bid": "1", "best_ask": "1"}) is None
    assert parse_kraken({"channel": "ticker", "type": "update", "data": [{"symbol": "BTC/USD", "bid": 84000.5, "ask": 84001.5,
                                                                          "last": 84001.0}]}) == (84000.5, 84001.5, 84001.0)
    assert parse_kraken({"channel": "heartbeat"}) is None
    assert parse_kraken({"method": "subscribe", "success": True}) is None


def test_a_socket_delivers_each_quote_stamped_at_receipt_and_reconnects_after_a_drop():
    clock = [1_790_700_000.0]
    got = []
    sockets = [FakeWS([{"type": "subscriptions"}, {"type": "ticker", "product_id": "BTC-USD", "price": "3", "best_bid": "2", "best_ask": "4"}]),
               FakeWS([{"type": "ticker", "product_id": "BTC-USD", "price": "6", "best_bid": "5", "best_ask": "7"}])]
    slept = []

    def open_socket():
        return sockets.pop(0)
    s = SpotSocket("coinbase", "wss://x", {"type": "subscribe"}, parse_coinbase,
                   lambda name, b, a, last, at: got.append((name, b, a, last, at)),
                   open_socket=open_socket, clock=lambda: clock[0], sleep=lambda x: slept.append(x))
    s.start()
    for _ in range(200):
        if len(got) >= 1:
            break
        threading.Event().wait(0.01)
    assert got == [("coinbase", 2.0, 4.0, 3.0, clock[0])] and s.live(clock[0])
    assert sockets[0].sent == [] and s.counters()["quotes"] == 1
    first = s._ws
    first.close()                                                   # the socket drops: reconnect, resubscribe
    for _ in range(300):
        if len(got) >= 2:
            break
        threading.Event().wait(0.01)
    assert got[1] == ("coinbase", 5.0, 7.0, 6.0, clock[0]) and s.reconnects == 1 and slept == [1.0]
    s.request_stop()


# ------------------------------------------------------------------ the feed never waits on the network
def _feed(clock, handler):
    return PriceFeed(client=httpx.Client(transport=httpx.MockTransport(handler)), clock=lambda: clock[0])


def _rest(req):
    body = {"api.exchange.coinbase.com": {"bid": "100", "ask": "102", "price": "101"},
            "api.kraken.com": {"result": {"XXBTZUSD": {"b": ["200"], "a": ["202"], "c": ["201"]}}},
            "www.bitstamp.net": {"bid": "300", "ask": "302", "last": "301"},
            "api.gemini.com": {"bid": "400", "ask": "402", "last": "401"}}[req.url.host]
    return httpx.Response(200, json=body)


def test_a_socket_quote_is_stored_stamped_at_receipt_and_beats_the_slower_rest_poll_for_that_exchange():
    clock = [1_790_700_000.0]
    spot = []
    f = _feed(clock, _rest)
    f.on_spot = lambda *a: spot.append(a)

    class Live:                                       # a socket that says it delivered just now
        def live(self, now, within):
            return True
    f.sockets["coinbase"] = Live()
    f.socket_quote("coinbase", 84000.0, 84001.0, 84000.5, clock[0] - 0.2)
    assert f.snapshot()["coinbase"] == Quote("coinbase", 84000.0, 84001.0, 84000.5, clock[0] - 0.2)
    assert spot == [("coinbase", 84000.0, 84001.0, 84000.5, clock[0] - 0.2)]
    f.store(Quote("coinbase", 1.0, 2.0, 1.5, clock[0]), from_socket=False)     # the REST poll, later but staler
    assert f.snapshot()["coinbase"].bid == 84000.0
    f.store(Quote("kraken", 1.0, 2.0, 1.5, clock[0]), from_socket=False)       # no socket for kraken: the poll stands
    assert f.snapshot()["kraken"].bid == 1.0


def test_tick_reads_the_latest_quotes_and_polls_inline_only_before_start():
    clock = [1_790_700_000.0]
    f = _feed(clock, _rest)
    t, px, n, disp = f.tick()                                       # never started: the old inline poll
    assert (t, n) == (clock[0], 4) and px == (201 + 301) / 2       # median of the four mids 101/201/301/401
    f._pollers.append(threading.current_thread())                   # "started": tick must not touch the network
    calls = []
    f._fetch = lambda name: calls.append(name)
    clock[0] += 1
    t2, px2, n2, _ = f.tick()
    assert calls == [] and (t2, n2, px2) == (clock[0], 4, px)
    assert list(f.ring) == [(t, px), (t2, px2)]


def test_a_poller_skips_the_exchange_whose_socket_is_live_and_polls_it_when_the_socket_is_not():
    clock = [1_790_700_000.0]
    f = _feed(clock, _rest)
    fetched = []
    f._fetch = lambda name: (fetched.append(name), Quote(name, 1.0, 2.0, 1.5, clock[0]))[1]

    class Sock:
        def __init__(self, live):
            self._live = live

        def live(self, now, within):
            return self._live
    f.sockets["coinbase"] = Sock(True)
    assert f._poll_once("coinbase", clock[0]) is False and f._poll_once("gemini", clock[0]) is True
    assert fetched == ["gemini"] and "gemini" in f.snapshot() and "coinbase" not in f.snapshot()
    f.sockets["coinbase"] = Sock(False)
    assert f._poll_once("coinbase", clock[0]) is True and fetched == ["gemini", "coinbase"]


def test_two_threads_seeing_a_new_window_at_once_start_exactly_one_socket():
    """At a window boundary the main loop, the markout thread and a stream callback can all call
    ensure(new_slug) within microseconds; without a lock each starts its own socket and every
    message drives the arms twice (review, 2026-09-30)."""
    opened = []
    lock = threading.Lock()

    def open_socket():
        with lock:
            opened.append(1)
        return FakeWS([])
    sb = StreamBook(open_socket=open_socket, clock=lambda: 1_790_700_000.0)
    sb.ensure("cpc-btc-updown-15m-2026-09-30-2000z")
    for _ in range(100):
        if opened:
            break
        threading.Event().wait(0.01)
    assert len(opened) == 1
    go = threading.Event()

    def race():
        go.wait()
        sb.ensure("cpc-btc-updown-15m-2026-09-30-2015z")
    ts = [threading.Thread(target=race) for _ in range(8)]
    for t in ts:
        t.start()
    go.set()
    for t in ts:
        t.join(2)
    for _ in range(100):
        if len(opened) >= 2:
            break
        threading.Event().wait(0.01)
    threading.Event().wait(0.05)
    assert len(opened) == 2 and sb.slug.endswith("2015z")            # one socket per window, never two
    sb.stop()


def test_kalshi_depth_lands_one_row_per_level_per_side(tmp_path):
    tape = Microtape(str(tmp_path / "micro.sqlite"), clock=lambda: 1_790_700_000.0)
    tape.kalshi_book("KXBTC15M-26SEP302015-15", {"yes": [(0.44, 500.0), (0.43, 1200.0)], "no": [(0.55, 300.0)]}, at=1_790_700_001.0)
    tape.kalshi_book("KXBTC15M-26SEP302015-15", None, at=1_790_700_002.0)                 # nothing read: nothing written
    assert tape.drain() == 3
    rows = sqlite3.connect(tape.path).execute("SELECT recv, ticker, side, level, price, size FROM kalshi_book ORDER BY side DESC, level").fetchall()
    assert rows == [(1_790_700_001.0, "KXBTC15M-26SEP302015-15", "yes", 0, 0.44, 500.0), (1_790_700_001.0, "KXBTC15M-26SEP302015-15", "yes", 1, 0.43, 1200.0),
                    (1_790_700_001.0, "KXBTC15M-26SEP302015-15", "no", 0, 0.55, 300.0)]
