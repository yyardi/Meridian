"""Exchange quotes over the exchanges' own websockets: Coinbase and Kraken tickers, one thread each.

The composite in ``core.btc15.prices`` polled four REST tickers once a second with a 2.5-s
timeout, on the harness's main thread. Measured on the ledger's ``ticks`` (2026-09-30): the
median gap was 1.00 s but 13-17 % of gaps exceeded 1.5 s (max 3.8 s), one stalled ticker at a
time. A socket delivers a quote at the exchange's own cadence -- Coinbase's ``ticker`` channel on
every trade, Kraken's ``ticker`` on every top-of-book change with a heartbeat each second -- on
its own thread, so the main loop never waits on an exchange and spot is known to the
sub-second for the microtape and the arms.

Public channels, no credentials (both read 2026-09-30):

    wss://ws-feed.exchange.coinbase.com   {"type":"subscribe","product_ids":["BTC-USD"],"channels":["ticker"]}
        -> {"type":"ticker","product_id":"BTC-USD","price","best_bid","best_ask","time", ...}
    wss://ws.kraken.com/v2                {"method":"subscribe","params":{"channel":"ticker","symbol":["BTC/USD"]}}
        -> {"channel":"ticker","type":"snapshot"|"update","data":[{"symbol":"BTC/USD","bid","ask","last", ...}]}

Bitstamp and Gemini stay on REST (their sockets carry full books, which is more than a
composite of mids needs). A socket that dies reconnects with doubling backoff; while it is
down its REST poll resumes, so the composite never loses an exchange to a socket outage.
"""
from __future__ import annotations

import json
import logging
import threading
import time

from core.polymarket.ws_min import ConnectionClosed, WSClient

log = logging.getLogger("btc15.spot_ws")

COINBASE_URL = "wss://ws-feed.exchange.coinbase.com"
COINBASE_SUBSCRIBE = {"type": "subscribe", "product_ids": ["BTC-USD"], "channels": ["ticker"]}
KRAKEN_URL = "wss://ws.kraken.com/v2"
KRAKEN_SUBSCRIBE = {"method": "subscribe", "params": {"channel": "ticker", "symbol": ["BTC/USD"]}}


def parse_coinbase(msg) -> tuple[float, float, float] | None:
    """(bid, ask, last) from a ticker message; None for anything else (acks, heartbeats)."""
    if not isinstance(msg, dict) or msg.get("type") != "ticker" or msg.get("product_id") != "BTC-USD":
        return None
    try:
        return float(msg["best_bid"]), float(msg["best_ask"]), float(msg["price"])
    except (KeyError, TypeError, ValueError):
        return None


def parse_kraken(msg) -> tuple[float, float, float] | None:
    if not isinstance(msg, dict) or msg.get("channel") != "ticker" or not msg.get("data"):
        return None
    d = msg["data"][0] if isinstance(msg["data"], list) else None
    if not isinstance(d, dict) or d.get("symbol") != "BTC/USD":
        return None
    try:
        return float(d["bid"]), float(d["ask"]), float(d["last"])
    except (KeyError, TypeError, ValueError):
        return None


FEEDS = {
    "coinbase": (COINBASE_URL, COINBASE_SUBSCRIBE, parse_coinbase),
    "kraken": (KRAKEN_URL, KRAKEN_SUBSCRIBE, parse_kraken),
}


class SpotSocket:
    """One exchange's socket on its own thread. ``on_quote(name, bid, ask, last, at)`` is called
    for every parsed quote, stamped at receipt on ``clock``."""

    def __init__(self, name: str, url: str, subscribe: dict, parse, on_quote, *, open_socket=None,
                 clock=time.time, sleep=time.sleep, max_backoff: float = 30.0, timeout: float = 30.0) -> None:
        self.name, self.url, self.subscribe, self.parse, self.on_quote = name, url, subscribe, parse, on_quote
        self._open_socket = open_socket or (lambda: self._default_socket(timeout))
        self._clock, self._sleep, self.max_backoff = clock, sleep, max_backoff
        self.stop = threading.Event()
        self._lock = threading.Lock()
        self._ws = None
        self.msgs = self.quotes = self.reconnects = 0
        self.last_msg_at: float | None = None
        self.last_quote_at: float | None = None
        self.last_error = ""
        self._thread: threading.Thread | None = None

    def _default_socket(self, timeout: float):
        ws = WSClient(self.url, {}, timeout=timeout)
        ws.connect()
        return ws

    def start(self) -> "SpotSocket":
        self._thread = threading.Thread(target=self.run, name=f"spot-{self.name}", daemon=True)
        self._thread.start()
        return self

    def request_stop(self) -> None:
        self.stop.set()
        with self._lock:
            ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except OSError:
                pass

    def live(self, now: float | None = None, within: float = 5.0) -> bool:
        """A quote within ``within`` seconds: this exchange's socket is the price, not its REST poll."""
        if self.last_quote_at is None:
            return False
        now = self._clock() if now is None else now
        return now - self.last_quote_at <= within

    def run(self) -> None:
        backoff = 1.0
        while not self.stop.is_set():
            try:
                self._session()
                backoff = 1.0
            except (ConnectionClosed, OSError, ValueError, json.JSONDecodeError) as e:    # noqa: PERF203
                with self._lock:
                    self.last_error = f"{type(e).__name__}: {str(e)[:100]}"
                    self.reconnects += 1
                if self.stop.is_set():
                    return
                self._sleep(backoff)
                backoff = min(backoff * 2, self.max_backoff)

    def _session(self) -> None:
        ws = self._open_socket()
        with self._lock:
            self._ws = ws
        try:
            ws.send_json(self.subscribe)
            while not self.stop.is_set():
                msg = ws.recv_json()
                self.handle(msg)
        finally:
            with self._lock:
                self._ws = None
            try:
                ws.close()
            except OSError:
                pass

    def handle(self, msg) -> None:
        now = self._clock()
        with self._lock:
            self.msgs += 1
            self.last_msg_at = now
        q = self.parse(msg)
        if q is None:
            return
        with self._lock:
            self.quotes += 1
            self.last_quote_at = now
        try:
            self.on_quote(self.name, q[0], q[1], q[2], now)
        except Exception:                                    # noqa: BLE001 -- a consumer error never drops the socket
            log.exception("spot quote handler")

    def counters(self, now: float | None = None) -> dict:
        now = self._clock() if now is None else now
        with self._lock:
            return {"name": self.name, "messages": self.msgs, "quotes": self.quotes, "reconnects": self.reconnects,
                    "last_quote_age_s": None if self.last_quote_at is None else round(now - self.last_quote_at, 2),
                    "live": self.live(now), "last_error": self.last_error}
