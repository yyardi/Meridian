"""Read-only client for Polymarket US's "BTC Up or Down: 15 min" markets -- the traded venue.

Verified against the venue 2026-09-28 (the operator's account is here). One
market per quarter hour, slug ``cpc-btc-updown-15m-YYYY-MM-DD-HHMMz`` where
HHMM is the window START in UTC, listed about twelve hours ahead:

* ``GET /v1/markets?slug=<slug>`` -> ``markets[0]`` with ``status``
  (MARKET_STATUS_OPEN / MARKET_STATUS_RESOLVED), ``feeCoefficient`` (0.0695),
  ``orderPriceMinTickSize`` 0.01, and ``assetPriceTerms``: ``windowStart``,
  ``windowEnd``, ``priceToBeat`` (the strike, the 60-second BRTI average before
  the start) and ``settlementPrice`` (the same average before the end, once
  resolved). ``outcomePrices`` becomes ["1","0"] (Up) or ["0","1"] (Down).
* ``GET /v1/markets/<slug>/book`` -> ``marketData.bids`` / ``offers`` for YES
  (Up), best first. Buying NO (Down) costs 1 - the best YES bid.
* ``GET /v1/markets/<slug>/settlement`` -> ``{"settlement": 1 | 0}``.

**The venue hid these markets' metadata on 2026-09-28 between 19:19Z and 19:30Z**:
``/v1/markets?slug=`` and search return nothing for them, while ``/book`` and
``/settlement`` still answer. ``meta()`` therefore falls back to a REBUILT record
(``"rebuilt": true``): the window from the slug, the status from the book's state
(MARKET_STATE_OPEN while it trades, EXPIRED after) and the settlement endpoint
(1 = Up, 0 = Down), the price to beat from ``strike_source`` (Kalshi's same window,
identical by construction) when one is given, and the fee coefficient as this
period's constant (core.fees) -- the one field the venue no longer states.

The contract is Kalshi's KXBTC15M's to the cent: both settle on the same BRTI
averages (Polymarket's 23:30Z window of 2026-09-27 resolved at 84,337.75, Kalshi's
``expiration_value`` for that window). The fee is the venue's
``feeCoefficient x p x (1 - p)`` per contract, read off each market -- the fee
is a constant of a period, not of the venue -- charged here rounded UP to the
cent, the conservative reading for a drawdown ledger.
"""
from __future__ import annotations

import datetime as dt
import os
import time
from decimal import ROUND_CEILING, Decimal

import httpx

from core.btc15.kalshi import UNITS_PER_DOLLAR, to_units
from core.fees import POLYMARKET_TAKER  # fee-now: only a REBUILT market (the venue stopped stating it) uses the period's constant

GATEWAY = os.environ.get("POLYMARKET_GATEWAY_URL", "https://gateway.polymarket.us")
#: The venue lists BTC Up or Down at these horizons (read 2026-09-28: 15 min and
#: 60 min; there is no 5-minute market). The slug carries the horizon token.
HORIZONS = {"15m": 900, "1h": 3600}
#: RESOLVING sits between the close and the result: 30 s to ~3 min, measured
#: 2026-09-28 (the 01:45Z window resolved 2 min 48 s after its close).
STATUS = {"MARKET_STATUS_OPEN": "active", "MARKET_STATUS_RESOLVING": "resolving",
          "MARKET_STATUS_RESOLVED": "finalized"}


def slug_at(ts: float, horizon: str = "15m") -> str:
    """The window containing ``ts``: cpc-btc-updown-<horizon>-YYYY-MM-DD-HHMMz, HHMM its start in UTC."""
    w = HORIZONS[horizon]
    start = int(ts // w) * w
    return f"cpc-btc-updown-{horizon}-" + dt.datetime.fromtimestamp(start, dt.timezone.utc).strftime("%Y-%m-%d-%H%Mz")


def window_of(slug: str) -> tuple[float, float]:
    """cpc-btc-updown-<h>-YYYY-MM-DD-HHMMz -> (open_ts, close_ts)."""
    head, _, stamp = slug.rpartition("-")
    date = head[-10:]
    horizon = head.split("cpc-btc-updown-")[1].split("-")[0]
    o = dt.datetime.strptime(f"{date} {stamp.rstrip('z')}", "%Y-%m-%d %H%M").replace(tzinfo=dt.timezone.utc).timestamp()
    return o, o + HORIZONS[horizon]


def _ts(s: str | None) -> float | None:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() if s else None


def _px(level: dict | None) -> int | None:
    return to_units(((level or {}).get("px") or {}).get("value")) if level else None


def _money(d: dict | None) -> float | None:
    v = (d or {}).get("value")
    return float(v) if v not in (None, "") else None


def result_of(outcome_prices) -> str | None:
    """["1","0"] -> "yes" (Up); ["0","1"] -> "no" (Down); anything else -> None."""
    if isinstance(outcome_prices, str):
        import json
        try:
            outcome_prices = json.loads(outcome_prices)
        except ValueError:
            return None
    if not outcome_prices or len(outcome_prices) != 2:
        return None
    y, n = str(outcome_prices[0]), str(outcome_prices[1])
    return "yes" if (y, n) == ("1", "0") else "no" if (y, n) == ("0", "1") else None


def normalize(meta: dict, book: dict | None) -> dict:
    """The fields the harness uses, in the same shape as the Kalshi adapter."""
    terms = meta.get("assetPriceTerms") or {}
    bids = (book or {}).get("bids") or []
    offers = (book or {}).get("offers") or []
    yb, ya = _px(bids[0] if bids else None), _px(offers[0] if offers else None)
    nb = None if ya is None else UNITS_PER_DOLLAR - ya
    na = None if yb is None else UNITS_PER_DOLLAR - yb
    status = STATUS.get(meta.get("status"), (meta.get("status") or "").lower() or None)
    return {
        "ticker": meta["slug"], "status": status,
        "open_ts": _ts(terms.get("windowStart")), "close_ts": _ts(terms.get("windowEnd")),
        "open_time": terms.get("windowStart"), "close_time": terms.get("windowEnd"),
        "strike": _money(terms.get("priceToBeat")),
        "yes_bid_u": yb, "yes_ask_u": ya, "no_bid_u": nb, "no_ask_u": na,
        "yes_bid": None if yb is None else yb / UNITS_PER_DOLLAR,
        "yes_ask": None if ya is None else ya / UNITS_PER_DOLLAR,
        "no_bid": None if nb is None else nb / UNITS_PER_DOLLAR,
        "no_ask": None if na is None else na / UNITS_PER_DOLLAR,
        "yes_bid_size": float(bids[0]["qty"]) if bids else None,
        "yes_ask_size": float(offers[0]["qty"]) if offers else None,
        "last_price": _money(((book or {}).get("stats") or {}).get("lastTradePx")),
        "volume": None,
        "book_state": (book or {}).get("state"),
        "fee_coefficient": meta.get("feeCoefficient"),
        "result": result_of(meta.get("outcomePrices")) if status == "finalized" else None,
        "expiration_value": _money(terms.get("settlementPrice")),
    }


class PolymarketBTC:
    venue = "polymarket"

    def __init__(self, client: httpx.Client | None = None, base: str = GATEWAY, horizon: str = "15m",
                 strike_source=None, clock=time.time) -> None:
        if horizon not in HORIZONS:
            raise ValueError(f"horizon {horizon!r}: one of {sorted(HORIZONS)}")
        self.strike_source = strike_source          # (open_ts, close_ts) -> price to beat, or None
        self._clock = clock
        self._http = client or httpx.Client(timeout=10.0, headers={"User-Agent": "meridian-btc15/1"})
        self._base = base.rstrip("/")
        self.horizon = horizon

    def _get(self, path: str, params: dict | None = None) -> dict:
        r = self._http.get(self._base + path, params=params)
        r.raise_for_status()
        return r.json()

    last_meta: dict | None = None

    def quote(self, slug: str) -> dict | None:
        """The window's book only (one request), on the metadata the last current() read."""
        meta = self.last_meta
        if not meta or meta.get("slug") != slug:
            return None
        return normalize(meta, self.book(slug))

    def owns(self, ticker: str) -> bool:
        return ticker.startswith(f"cpc-btc-updown-{self.horizon}-")

    def meta(self, slug: str) -> dict | None:
        ms = self._get("/v1/markets", {"slug": slug}).get("markets") or []
        return ms[0] if ms else self.rebuilt_meta(slug)

    def settlement(self, slug: str) -> int | None:
        try:
            s = self._get(f"/v1/markets/{slug}/settlement").get("settlement")
        except httpx.HTTPStatusError:
            return None
        return int(s) if s in (0, 1, "0", "1") else None

    def rebuilt_meta(self, slug: str) -> dict | None:
        """The market record the venue no longer lists, from what it still serves."""
        try:
            o, c = window_of(slug)
        except (ValueError, KeyError, IndexError):
            return None
        book = self.book(slug)
        state = (book or {}).get("state")
        status, prices = None, None
        if state == "MARKET_STATE_OPEN":
            status = "MARKET_STATUS_OPEN"
        elif book is not None or self._clock() >= c:
            s = self.settlement(slug)
            if s is not None:
                status, prices = "MARKET_STATUS_RESOLVED", (["1", "0"] if s == 1 else ["0", "1"])
            elif book is not None:
                status = "MARKET_STATUS_RESOLVING"
        if status is None:
            return None
        strike = None
        if status == "MARKET_STATUS_OPEN" and self.strike_source is not None:
            try:
                strike = self.strike_source(o, c)
            except Exception:                                    # noqa: BLE001 -- a missing strike is None, never a crash
                strike = None
        iso = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat().replace("+00:00", "Z")
        return {"slug": slug, "status": status, "rebuilt": True, "feeCoefficient": str(POLYMARKET_TAKER),
                "outcomePrices": prices,
                "assetPriceTerms": {"windowStart": iso(o), "windowEnd": iso(c),
                                    "priceToBeat": None if strike is None else {"value": str(strike)}}}

    def book(self, slug: str) -> dict | None:
        try:
            return self._get(f"/v1/markets/{slug}/book").get("marketData")
        except httpx.HTTPStatusError:
            return None

    def market(self, slug: str) -> dict:
        meta = self.meta(slug)
        if meta is None:
            raise LookupError(slug)
        return normalize(meta, self.book(slug) if meta.get("status") == "MARKET_STATUS_OPEN" else None)

    def current(self, now: float) -> dict | None:
        meta = self.meta(slug_at(now, self.horizon))
        self.last_meta = meta
        if meta is None or meta.get("status") != "MARKET_STATUS_OPEN":
            return None
        m = normalize(meta, self.book(meta["slug"]))
        return m if (m["open_ts"] and m["close_ts"] and m["open_ts"] <= now < m["close_ts"]) else None

    def outcome(self, slug: str) -> dict:
        m = self.market(slug)
        return {"final": m["status"] == "finalized" and m["result"] in ("yes", "no"),
                "result": m["result"], "expiration_value": m["expiration_value"]}

    def fee_units(self, price_u: int, market: dict) -> int:
        coef = market.get("fee_coefficient")
        if coef in (None, ""):
            raise ValueError(f"{market.get('ticker')}: no feeCoefficient on the market")
        p = Decimal(price_u) / UNITS_PER_DOLLAR
        dollars = Decimal(str(coef)) * p * (1 - p)
        return int((dollars * 100).to_integral_value(rounding=ROUND_CEILING)) * 100
