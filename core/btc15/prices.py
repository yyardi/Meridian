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

    def __init__(self, client: httpx.Client | None = None, timeout: float = 2.5) -> None:
        self._http = client or httpx.Client(timeout=timeout, headers={"User-Agent": "meridian-btc15/1"})
        self._pool = ThreadPoolExecutor(max_workers=len(EXCHANGES))
        self.quotes: dict[str, Quote] = {}
        self.ring: collections.deque = collections.deque(maxlen=RING_S)
        self.c1m: list = []
        self.c5m: list = []
        self.c1h: list = []
        self.funding: dict | None = None
        self._next = {"c1m": 0.0, "c5m": 0.0, "c1h": 0.0, "funding": 0.0}
        self._lock = threading.Lock()
        self.errors: collections.Counter = collections.Counter()

    def _fetch(self, name: str) -> Quote | None:
        url, parse = EXCHANGES[name]
        try:
            r = self._http.get(url)
            r.raise_for_status()
            bid, ask, last = parse(r.json())
            return Quote(name, bid, ask, last, time.time())
        except Exception:                                  # noqa: BLE001 -- one exchange down is not the feed down
            self.errors[name] += 1
            return None

    def tick(self) -> tuple[float, float | None, int, float]:
        """Poll every exchange once; append the composite. Returns (t, px, n, dispersion)."""
        for q in self._pool.map(self._fetch, list(EXCHANGES)):
            if q is not None:
                self.quotes[q.exchange] = q
        now = time.time()
        px, n, disp = composite(self.quotes, now)
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
