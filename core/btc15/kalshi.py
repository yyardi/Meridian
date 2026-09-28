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
from decimal import Decimal

import httpx

SERIES = "KXBTC15M"
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


class KalshiBTC:
    def __init__(self, client: httpx.Client | None = None, base: str = BASE) -> None:
        self._http = client or httpx.Client(timeout=10.0, headers={"User-Agent": "meridian-btc15/1"})
        self._base = base.rstrip("/")

    def _get(self, path: str, params: dict | None = None) -> dict:
        r = self._http.get(self._base + path, params=params)
        r.raise_for_status()
        return r.json()

    def current(self, now: float) -> dict | None:
        """The window trading now: active, open_time <= now < close_time."""
        ms = self._get("/markets", {"series_ticker": SERIES, "status": "open", "limit": 10}).get("markets") or []
        live = [normalize(m) for m in ms]
        live = [m for m in live if m["open_ts"] and m["close_ts"] and m["open_ts"] <= now < m["close_ts"]]
        return min(live, key=lambda m: m["close_ts"]) if live else None

    def market(self, ticker: str) -> dict:
        return normalize(self._get(f"/markets/{ticker}")["market"])

    def recent_results(self, n: int = 12) -> list[dict]:
        ms = self._get("/markets", {"series_ticker": SERIES, "status": "settled", "limit": n}).get("markets") or []
        out = [normalize(m) for m in ms]
        out.sort(key=lambda m: m["close_ts"] or 0)
        return out

    def fee_multiplier(self) -> Decimal:
        s = self._get(f"/series/{SERIES}").get("series") or {}
        if s.get("fee_type") != "quadratic":
            raise RuntimeError(f"{SERIES} fee_type is {s.get('fee_type')!r}, not the quadratic schedule this ledger charges")
        return Decimal(str(s.get("fee_multiplier") or 1))
