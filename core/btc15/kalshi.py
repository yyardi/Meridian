"""Read-only client for Kalshi's KXBTC15M series: the current window, one market, recent results.

Verified against the venue 2026-09-28: a market is listed ahead as
``initialized``, trades as ``active`` from ``open_time`` to ``close_time``, and
is ``finalized`` about one second after close with ``result`` in {"yes","no"}
and ``expiration_value`` = the closing 60-second BRTI average (which is the
next window's ``floor_strike``). Prices are dollar strings with four decimals
("0.8200"; the series uses deci-cent tick structure near the extremes) and
sizes are float strings. Prices are converted here to integer units of
$0.0001 so no float ever touches money.
"""
from __future__ import annotations

import datetime as dt
import os
import time
from decimal import Decimal

import httpx

SERIES = "KXBTC15M"
#: The /markets list names the window and its strike and changes only at window boundaries;
#: it is re-read this often, and at once when it names no window for now. The touch is the
#: order book's, read every call.
LIST_CACHE_S = 10.0
BASE = os.environ.get("KALSHI_API_URL", "https://api.elections.kalshi.com/trade-api/v2")
UNITS_PER_DOLLAR = 10_000


def to_units(dollars) -> int | None:
    """"0.8200" -> 8200. None and empty stay None."""
    if dollars in (None, ""):
        return None
    return int((Decimal(str(dollars)) * UNITS_PER_DOLLAR).to_integral_value())


def _ts(s: str | None) -> float | None:
    if not s:
        return None
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def normalize(m: dict) -> dict:
    """The fields the harness uses, in units, with epoch timestamps."""
    def f(k):
        v = m.get(k)
        return float(v) if v not in (None, "") else None
    yb, ya = to_units(m.get("yes_bid_dollars")), to_units(m.get("yes_ask_dollars"))
    nb, na = to_units(m.get("no_bid_dollars")), to_units(m.get("no_ask_dollars"))
    return {
        "ticker": m["ticker"], "status": m.get("status"),
        "open_ts": _ts(m.get("open_time")), "close_ts": _ts(m.get("close_time")),
        "open_time": m.get("open_time"), "close_time": m.get("close_time"),
        "strike": m.get("floor_strike"),
        "yes_bid_u": yb, "yes_ask_u": ya, "no_bid_u": nb, "no_ask_u": na,
        # the probability form the model reads
        "yes_bid": None if yb is None else yb / UNITS_PER_DOLLAR,
        "yes_ask": None if ya is None else ya / UNITS_PER_DOLLAR,
        "no_bid": None if nb is None else nb / UNITS_PER_DOLLAR,
        "no_ask": None if na is None else na / UNITS_PER_DOLLAR,
        "yes_bid_size": f("yes_bid_size_fp"), "yes_ask_size": f("yes_ask_size_fp"),
        "last_price": f("last_price_dollars"), "volume": f("volume_fp"),
        "result": m.get("result") or None, "expiration_value": f("expiration_value"),
    }


NO_TOUCH = {k: None for k in ("yes_bid_u", "yes_ask_u", "no_bid_u", "no_ask_u", "yes_bid", "yes_ask",
                              "no_bid", "no_ask", "yes_bid_size", "yes_ask_size")}


def book_touch(resp: dict | None) -> dict | None:
    """The touch from /markets/<t>/orderbook: the best YES bid, and the YES ask as $1 minus the
    best NO bid (Kalshi books only bids on each side). None if either side is empty."""
    ob = (resp or {}).get("orderbook_fp") or (resp or {}).get("orderbook") or {}
    def best(levels):
        live = [(to_units(p), float(q)) for p, q in (levels or []) if float(q) > 0]
        return max(live) if live else None
    yb, nb = best(ob.get("yes_dollars")), best(ob.get("no_dollars"))
    if yb is None or nb is None:
        return None
    ya = UNITS_PER_DOLLAR - nb[0]
    return {"yes_bid_u": yb[0], "yes_ask_u": ya, "no_bid_u": nb[0], "no_ask_u": UNITS_PER_DOLLAR - yb[0],
            "yes_bid": yb[0] / UNITS_PER_DOLLAR, "yes_ask": ya / UNITS_PER_DOLLAR,
            "no_bid": nb[0] / UNITS_PER_DOLLAR, "no_ask": (UNITS_PER_DOLLAR - yb[0]) / UNITS_PER_DOLLAR,
            "yes_bid_size": yb[1], "yes_ask_size": nb[1]}


class KalshiBTC:
    venue = "kalshi"

    def __init__(self, client: httpx.Client | None = None, base: str = BASE) -> None:
        self._http = client or httpx.Client(timeout=10.0, headers={"User-Agent": "meridian-btc15/1"})
        self._base = base.rstrip("/")
        self._mult: tuple[float, Decimal] | None = None
        self._list: tuple[float, list] | None = None

    def _get(self, path: str, params: dict | None = None) -> dict:
        r = self._http.get(self._base + path, params=params)
        r.raise_for_status()
        return r.json()

    def current(self, now: float) -> dict | None:
        """The window trading now: active, open_time <= now < close_time, priced off its ORDER BOOK.

        The /markets list names the window and its strike, but its touch lags the book: measured
        2026-09-30, it held one price for a mean of 32 s (longest 58 s) while the order book
        changed every second, a median 4c apart (analysis/btc15/quote_freshness_probe.py). The
        touch here is the book's; if the book cannot be read, there is no touch, never the list's."""
        live = self._live_windows(now, fresh=False)
        if not live:
            live = self._live_windows(now, fresh=True)       # a window just opened: the cached list predates it
        if not live:
            return None
        m = min(live, key=lambda m: m["close_ts"])
        try:
            touch = book_touch(self._get(f"/markets/{m['ticker']}/orderbook"))
        except (httpx.HTTPError, ValueError):
            touch = None
        return {**m, **(touch or NO_TOUCH), "touch_source": "orderbook" if touch else "none"}

    def _live_windows(self, now: float, fresh: bool) -> list[dict]:
        t = time.time()
        if fresh or self._list is None or t - self._list[0] > LIST_CACHE_S:
            self._list = (t, self._get("/markets", {"series_ticker": SERIES, "status": "open", "limit": 10}).get("markets") or [])
        live = [normalize(m) for m in self._list[1]]
        return [m for m in live if m["open_ts"] and m["close_ts"] and m["open_ts"] <= now < m["close_ts"]]

    def market(self, ticker: str) -> dict:
        return normalize(self._get(f"/markets/{ticker}")["market"])

    def recent_results(self, n: int = 12) -> list[dict]:
        ms = self._get("/markets", {"series_ticker": SERIES, "status": "settled", "limit": n}).get("markets") or []
        out = [normalize(m) for m in ms]
        out.sort(key=lambda m: m["close_ts"] or 0)
        return out

    def owns(self, ticker: str) -> bool:
        return ticker.startswith(f"{SERIES}-")

    def outcome(self, ticker: str) -> dict:
        m = self.market(ticker)
        return {"final": m["status"] in ("finalized", "settled") and m["result"] in ("yes", "no"),
                "result": m["result"], "expiration_value": m["expiration_value"]}

    def fee_units(self, price_u: int, market: dict) -> int:
        """Kalshi's quadratic schedule with the series multiplier, re-read hourly."""
        import time
        from core.btc15.ledger import fee_units
        if self._mult is None or time.time() - self._mult[0] > 3600:
            self._mult = (time.time(), self.fee_multiplier())
        return fee_units(price_u, 1, self._mult[1])

    def fee_multiplier(self) -> Decimal:
        s = self._get(f"/series/{SERIES}").get("series") or {}
        if s.get("fee_type") != "quadratic":
            raise RuntimeError(f"{SERIES} fee_type is {s.get('fee_type')!r}, not the quadratic schedule this ledger charges")
        return Decimal(str(s.get("fee_multiplier") or 1))
