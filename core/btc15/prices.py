"""BTC/USD from the free constituents of CF Benchmarks' BRTI, one composite a second.

Kalshi settles KXBTC15M on CF Benchmarks' Real Time Index (BRTI), which has no
free API. BRTI is built from the order books of a set of constituent exchanges;
four of them publish free public tickers that answer from the production host
(verified 2026-09-28): Coinbase, Kraken, Bitstamp, Gemini. The composite here is
the MEDIAN of their mid prices among those quoted in the last few seconds -- a
proxy, not the index. Its error against the official value is measured every
window: Kalshi reports each window's closing BRTI average as ``expiration_value``
and the harness stores the proxy's own 60-second average beside it.

Candles (Coinbase, public) give the history a feature set needs from the first
second: 1-minute bars for the last ~5.8 hours, 5-minute for ~25 hours, 1-hour
for ~12 days. OKX's public funding rate is the one derivatives input.

How the quotes arrive (2026-09-30). The REST tickers used to be polled on the
caller's thread, four at a time with a 2.5-s timeout; the ledger's ``ticks``
show 13-17 % of the harness's seconds skipped waiting on one of them. Now each
exchange is polled on its own thread once a second (``start``), Coinbase and
Kraken also stream over their websockets (``core.btc15.spot_ws``), and
``tick`` only reads the latest quote per exchange -- it never waits on the
network. An exchange whose socket delivered within ``SOCKET_FRESH_S`` is not
overwritten by its slower REST poll. The composite's definition is unchanged:
the median mid of the exchanges quoted in the last QUOTE_FRESH_S, once a second.
Every socket quote is also handed to ``on_spot`` (the microtape).
"""
from __future__ import annotations

import collections
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import httpx

#: A quote older than this is not part of the composite.
QUOTE_FRESH_S = 5.0
#: An exchange whose socket delivered this recently is the socket's price, not its REST poll's.
SOCKET_FRESH_S = 3.0
#: Seconds of 1 Hz composite kept in memory (6 hours).
RING_S = 6 * 3600


@dataclass(frozen=True)
class Quote:
    exchange: str
    bid: float
    ask: float
    last: float
    t: float

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0


def _coinbase(d: dict) -> tuple[float, float, float]:
    return float(d["bid"]), float(d["ask"]), float(d["price"])


def _kraken(d: dict) -> tuple[float, float, float]:
    r = next(iter(d["result"].values()))
    return float(r["b"][0]), float(r["a"][0]), float(r["c"][0])


def _bitstamp(d: dict) -> tuple[float, float, float]:
    return float(d["bid"]), float(d["ask"]), float(d["last"])


def _gemini(d: dict) -> tuple[float, float, float]:
    return float(d["bid"]), float(d["ask"]), float(d["last"])


EXCHANGES = {
    "coinbase": ("https://api.exchange.coinbase.com/products/BTC-USD/ticker", _coinbase),
    "kraken": ("https://api.kraken.com/0/public/Ticker?pair=XBTUSD", _kraken),
    "bitstamp": ("https://www.bitstamp.net/api/v2/ticker/btcusd/", _bitstamp),
    "gemini": ("https://api.gemini.com/v1/pubticker/btcusd", _gemini),
}
CANDLES_URL = "https://api.exchange.coinbase.com/products/BTC-USD/candles"
FUNDING_URL = "https://www.okx.com/api/v5/public/funding-rate?instId=BTC-USDT-SWAP"


def composite(quotes: dict[str, Quote], now: float, fresh_s: float = QUOTE_FRESH_S) -> tuple[float | None, int, float]:
    """(median mid of fresh quotes, how many, max-min spread of those mids)."""
    mids = [q.mid for q in quotes.values() if now - q.t <= fresh_s and q.bid > 0 and q.ask >= q.bid]
    if not mids:
        return None, 0, 0.0
    return statistics.median(mids), len(mids), (max(mids) - min(mids))


def candles_ascending(raw: list) -> list[tuple[float, float, float, float, float, float]]:
    """Coinbase returns [time, low, high, open, close, volume], newest first."""
    rows = [(float(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])) for r in raw]
    rows.sort(key=lambda r: r[0])
    return rows


class PriceFeed:
    """Polls the four tickers concurrently once a second; keeps the composite
    in a ring buffer; refreshes candles and funding on their own clocks."""

    def __init__(self, client: httpx.Client | None = None, timeout: float = 2.5, clock=time.time) -> None:
        self._http = client or httpx.Client(timeout=timeout, headers={"User-Agent": "meridian-btc15/1"})
        self._pool = ThreadPoolExecutor(max_workers=len(EXCHANGES))
        self._clock = clock
        self.quotes: dict[str, Quote] = {}
        self.ring: collections.deque = collections.deque(maxlen=RING_S)
        self.c1m: list = []
        self.c5m: list = []
        self.c1h: list = []
        self.funding: dict | None = None
        self._next = {"c1m": 0.0, "c5m": 0.0, "c1h": 0.0, "funding": 0.0}
        self._lock = threading.Lock()
        self.errors: collections.Counter = collections.Counter()
        #: Called with (exchange, bid, ask, last, at) for every SOCKET quote (the microtape).
        self.on_spot = None
        self.sockets: dict = {}                  # exchange -> core.btc15.spot_ws.SpotSocket
        self._pollers: list[threading.Thread] = []
        self._stop = threading.Event()

    def _fetch(self, name: str) -> Quote | None:
        url, parse = EXCHANGES[name]
        try:
            r = self._http.get(url)
            r.raise_for_status()
            bid, ask, last = parse(r.json())
            return Quote(name, bid, ask, last, self._clock())
        except Exception:                                  # noqa: BLE001 -- one exchange down is not the feed down
            self.errors[name] += 1
            return None

    # ------------------------------------------------------------------ background feeds
    def start(self, sockets: bool = True, feeds: dict | None = None) -> "PriceFeed":
        """Poll each exchange on its own thread; open the exchange sockets. After this,
        ``tick`` never touches the network."""
        if sockets:
            from core.btc15 import spot_ws
            for name, (url, sub, parse) in (feeds or spot_ws.FEEDS).items():
                if name not in self.sockets:
                    self.sockets[name] = spot_ws.SpotSocket(name, url, sub, parse, self.socket_quote,
                                                            clock=self._clock).start()
        if not self._pollers:
            for name in EXCHANGES:
                t = threading.Thread(target=self._poll_forever, args=(name,), name=f"poll-{name}", daemon=True)
                t.start()
                self._pollers.append(t)
        return self

    def stop(self) -> None:
        self._stop.set()
        for s in self.sockets.values():
            s.request_stop()

    def _poll_forever(self, name: str) -> None:
        while not self._stop.is_set():
            t0 = self._clock()
            self._poll_once(name, t0)
            self._stop.wait(max(0.0, 1.0 - (self._clock() - t0)))

    def _poll_once(self, name: str, now: float) -> bool:
        """One REST read of ``name`` unless its socket delivered within SOCKET_FRESH_S. True if read."""
        s = self.sockets.get(name)
        if s is not None and s.live(now, SOCKET_FRESH_S):
            return False
        q = self._fetch(name)
        if q is not None:
            self.store(q, from_socket=False)
        return True

    def socket_quote(self, name: str, bid: float, ask: float, last: float, at: float) -> None:
        """A socket's quote: stored, and handed to on_spot."""
        self.store(Quote(name, bid, ask, last, at), from_socket=True)
        if self.on_spot is not None:
            try:
                self.on_spot(name, bid, ask, last, at)
            except Exception:                              # noqa: BLE001 -- the tape never stops the feed
                pass

    def store(self, q: Quote, from_socket: bool) -> None:
        with self._lock:
            s = self.sockets.get(q.exchange)
            if not from_socket and s is not None and s.live(q.t, SOCKET_FRESH_S):
                return                                     # the socket's price is fresher than this poll
            self.quotes[q.exchange] = q

    def snapshot(self) -> dict[str, Quote]:
        with self._lock:
            return dict(self.quotes)

    # ------------------------------------------------------------------ the second
    def tick(self) -> tuple[float, float | None, int, float]:
        """The composite from the latest quote per exchange; appended to the ring. Returns
        (t, px, n, dispersion). Polls inline only if ``start`` was never called."""
        if not self._pollers and not self.sockets:
            for q in self._pool.map(self._fetch, list(EXCHANGES)):
                if q is not None:
                    self.store(q, from_socket=False)
        now = self._clock()
        px, n, disp = composite(self.snapshot(), now)
        if px is not None:
            with self._lock:
                self.ring.append((now, px))
        return now, px, n, disp

    def _candles(self, granularity: int) -> list:
        r = self._http.get(CANDLES_URL, params={"granularity": granularity})
        r.raise_for_status()
        return candles_ascending(r.json())

    def refresh(self, now: float | None = None) -> None:
        """Candles and funding on their own clocks; a failure keeps the last good set."""
        now = now or time.time()
        for key, gran, every in (("c1m", 60, 60), ("c5m", 300, 300), ("c1h", 3600, 3600)):
            if now >= self._next[key]:
                try:
                    setattr(self, key, self._candles(gran))
                    self._next[key] = now + every
                except Exception:                          # noqa: BLE001
                    self.errors[key] += 1
                    self._next[key] = now + 15
        if now >= self._next["funding"]:
            try:
                d = self._http.get(FUNDING_URL).json()["data"][0]
                self.funding = {"rate": float(d["fundingRate"]), "next_ms": int(d["fundingTime"]), "t": now}
                self._next["funding"] = now + 600
            except Exception:                              # noqa: BLE001
                self.errors["funding"] += 1
                self._next["funding"] = now + 60

    def seconds(self) -> list[tuple[float, float]]:
        with self._lock:
            return list(self.ring)

    def average(self, t0: float, t1: float) -> float | None:
        """Simple average of the composite over [t0, t1): the proxy of the
        60-second BRTI average the contract settles on."""
        with self._lock:
            xs = [px for t, px in self.ring if t0 <= t < t1]
        return sum(xs) / len(xs) if xs else None
