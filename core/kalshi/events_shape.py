"""What a Kalshi non-sports payload MEANS: the venue facts, as pure functions.

No database, no network, no clock — everything here is a payload in and a row
or a Decimal out, which is what `tests/test_kalshi_events_recorder.py` drives.
The loop that calls it is `core.kalshi.events_recorder`.

THE POLL ANCHOR IS NOT close_time ALONE. close_time is on 107,599 of 107,599
open markets — that is what removes the Polymarket dependency this venue
otherwise inherits — but it is the LATEST possible close, and it differs from
`expected_expiration_time` on 79,605 of them (74.0%, survey 2026-09-14). On
KXITFWMATCH/KXATPCHALLENGERMATCH the gap is +330h and +333h: the two-week
postponement clause. A window of `[close_time - 24h, close_time]` would open
on the headline tennis series thirteen days AFTER the match. The anchor is
`min(close_time, expected_expiration_time)` (both present on 107,599/107,599):
the match on tennis, close_time on weather (-14h to -22h the other way) and
crypto (-5m).

THREE THINGS A CONSUMER OF THESE TABLES GETS WRONG (all measured 2026-09-14):

* **A tennis event is TWO markets, one per player** (2 legs on 95 of 95 open
  tennis events). YES on one is NO on the other, so four tradeable positions
  are ONE statistic. `(event_ticker, ticker_suffix)` recovers the pairing, and
  `leg_sum` is the source-free data-quality gate that falls out of it.
* **The fee regime is per-series and DATED.** KXWTAMATCH reads
  `quadratic_with_maker_fees` where the four other tennis series read
  `quadratic`; the venue lists 147 dated transitions, two of them tennis
  (KXATPMATCH, KXWTAMATCH, both 2025-11-15). Nothing here assumes a fee: it is
  re-read every cycle and stamped on every snapshot row.
* **Names are not identities.** 166 of 190 open tennis event-title name slots
  are a bare surname, and 'Liu' spans two series. The id is the ticker suffix
  plus `custom_strike` (a competitor UUID on every tennis leg).
"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from core.config import _env_bool, _env_float
from core.kalshi.recorder import _dec, _parse_ts

UTC = dt.timezone.utc

#: The pre-registered targets, used when KALSHI_SERIES is unset: an allowlist
#: defaulting to EMPTY would make a compose typo indistinguishable from a
#: quiet venue. NO FEE CLAIM IS ENCODED HERE.
DEFAULT_SERIES = (
    "KXITFWMATCH", "KXATPCHALLENGERMATCH",            # 833 settled/week, 1.0c
    "KXBTC15M", "KXBTCD",                             # continuous, forever
    "KXRAIN", "KXHIGHNY", "KXHIGHMIA", "KXHIGHLAX",   # no Polymarket twin
)

#: A change in any of these earns a snapshot row — the fee fields included,
#: because a fee transition on a still book is exactly the change a
#: price-only rule would drop.
_PRICE_KEYS = ("yes_bid", "yes_ask", "yes_bid_size", "yes_ask_size", "last_price",
               "volume", "open_interest", "status", "result", "fee_type", "fee_multiplier")
#: ...and of these, a terms row. Prices are deliberately absent.
_TERMS_KEYS = ("title", "event_title", "yes_sub_title", "strike_type", "floor_strike",
               "cap_strike", "custom_strike", "open_time", "close_time",
               "expected_expiration_time", "status", "market_type", "mutually_exclusive",
               "price_level_structure", "price_ranges", "min_tick", "rules_primary",
               "rules_secondary")


def series_allowlist(raw: str | None = None) -> tuple[str, ...]:
    """`'kxrain, KXBTCD ,,KXRAIN'` -> `('KXRAIN', 'KXBTCD')`. Order kept, dupes dropped."""
    raw = os.environ.get("KALSHI_SERIES") if raw is None else raw
    if raw is None:
        return DEFAULT_SERIES
    out: list[str] = []
    for part in raw.split(","):
        ticker = part.strip().upper()
        if ticker and ticker not in out:
            out.append(ticker)
    return tuple(out) or DEFAULT_SERIES


@dataclass(frozen=True)
class KalshiEventsConfig:
    series: tuple[str, ...] = field(default_factory=series_allowlist)
    #: W. A market is polled from anchor - W until anchor + grace.
    window_hours: float = field(
        default_factory=lambda: _env_float("KALSHI_EVENTS_WINDOW_HOURS", 24.0))
    #: Past its anchor a market is normally settled; the grace keeps a DELAYED
    #: one on tape instead of dropping it the moment the venue runs late.
    grace_hours: float = field(
        default_factory=lambda: _env_float("KALSHI_EVENTS_GRACE_HOURS", 2.0))
    interval_seconds: float = field(
        default_factory=lambda: _env_float("KALSHI_EVENTS_INTERVAL", 60.0))
    #: Full depth from /markets/orderbooks (100 books/request). OFF by default
    #: and not because it is expensive to FETCH: a KXBTCD book is ~100 levels,
    #: and a moving 550-market board at 60s is order GB/day of JSONB. The
    #: touch (bid/ask + both sizes) is already free in the events payload.
    depth: bool = field(default_factory=lambda: _env_bool("KALSHI_EVENTS_DEPTH", False))
    snapshot_raw: bool = field(
        default_factory=lambda: _env_bool("KALSHI_EVENTS_SNAPSHOT_RAW", False))
    #: The expected-vs-observed line. One extra request per series per cycle.
    coverage: bool = field(default_factory=lambda: _env_bool("KALSHI_EVENTS_COVERAGE", True))


def min_tick(market: dict[str, Any]) -> Decimal | None:
    """Smallest step in the market's price grid — NOT 1c everywhere.

    Four grids over the 107,599 open markets (2026-09-14): linear_cent 98,216
    at 0.0100, tapered_deci_cent 8,758 whose OUTER ranges step 0.0010,
    deci_cent 592 at 0.0010, center_half_edge_half_cent 33 at 0.0050. A float
    threshold against a grid it does not know has cost this project a whole
    tick level before, so the grid is stored and the floor derived here.
    """
    steps = [_dec(r.get("step")) for r in market.get("price_ranges") or []]
    steps = [s for s in steps if s is not None and s > 0]
    return min(steps) if steps else None


def poll_anchor(market: dict[str, Any]) -> dt.datetime | None:
    """min(close_time, expected_expiration_time) — see the module docstring."""
    stamps = [_parse_ts(market.get(f)) for f in ("close_time", "expected_expiration_time")]
    stamps = [s for s in stamps if s is not None]
    return min(stamps) if stamps else None


def in_window(anchor: dt.datetime | None, now: dt.datetime, cfg: KalshiEventsConfig) -> bool:
    if anchor is None:
        return False
    return (anchor - dt.timedelta(hours=cfg.window_hours) <= now
            <= anchor + dt.timedelta(hours=cfg.grace_hours))


def ticker_suffix(ticker: str | None, event_ticker: str | None) -> str | None:
    """The leg code: `KXITFWMATCH-26SEP13LEYSUN-LEY` -> `LEY`.

    The remainder after the event ticker, NOT "the last dash segment": KXBTCD
    legs are `...-T67099.99` and a strike can hold whatever the venue puts in
    it. With `(event_ticker, ticker_suffix)` a tennis event's two player legs
    are addressable without touching a name.

    None when the event ticker does not prefix the market ticker — including
    when they are equal. The dash fallback returns a DATE FRAGMENT there
    ('KXRAIN-26SEP13' -> '26SEP13'), which would be a confident, wrong leg
    code; refusing is the same rule the sports recorder applies to a game key
    it cannot split. The fallback survives only when we were given no event
    ticker at all.
    """
    ticker, event_ticker = str(ticker or ""), str(event_ticker or "")
    if event_ticker:
        return (ticker[len(event_ticker) + 1:] or None
                if ticker.startswith(event_ticker + "-") else None)
    return ticker.rsplit("-", 1)[-1] if "-" in ticker else None


def leg_bounds(markets: list[dict[str, Any]]) -> tuple[Decimal, Decimal, Decimal, Decimal] | None:
    """(sum of YES bids, sum of YES asks, sum of mids, tick) over one event's
    legs, or None if any leg is one-sided.

    The legs of a mutually exclusive event settle to exactly 1 between them,
    which is a consistency gate needing no external source. THE GATE IS NOT
    "the mids sum to 1": the mid sum floats anywhere inside the bid/ask band,
    whose width is the sum of the legs' spreads, and on the live ITF board
    that band reaches 1.66. Measured over the 71 two-sided mutually-exclusive
    events open on 2026-09-14, a mid-sum rule at `legs x tick` broke on 9 of
    them — every one a wide quote, not a venue error (the worst, VICLOP, is
    bid 0.80 / ask 1.05, perfectly consistent).

    What IS implied is no-arbitrage: buying every leg costs `ask_sum` and
    returns exactly 1, selling every leg receives `bid_sum` and pays exactly
    1, so `bid_sum <= 1 <= ask_sum`. That rule broke on 1 of the same 71
    (KXATPCHALLENGERMATCH-26SEP14CLAFOR, bid_sum 1.02) — a rate a reader will
    still be reading next week. The mid sum is returned anyway, as a NUMBER
    to log rather than a boolean to trip.

    None unless EVERY leg is two-sided: a quoted side with zero size is not a
    price (KXBTCD shows ask 1.0000 at size 0.00).
    """
    bids: list[Decimal] = []
    asks: list[Decimal] = []
    ticks: list[Decimal] = []
    for market in markets:
        bid, ask = _dec(market.get("yes_bid_dollars")), _dec(market.get("yes_ask_dollars"))
        bid_size, ask_size = (_dec(market.get("yes_bid_size_fp")),
                              _dec(market.get("yes_ask_size_fp")))
        tick = min_tick(market)
        if bid is None or ask is None or tick is None or not bid_size or not ask_size:
            return None
        bids.append(bid)
        asks.append(ask)
        ticks.append(tick)
    if not bids:
        return None
    return sum(bids), sum(asks), (sum(bids) + sum(asks)) / 2, max(ticks)


def terms_row(event: dict[str, Any], market: dict[str, Any], captured_at: dt.datetime) -> dict:
    """The carry list, verbatim from the venue's own field names."""
    ticker = str(market.get("ticker") or "")
    event_ticker = market.get("event_ticker") or event.get("event_ticker")
    return {
        "captured_at": captured_at, "series_ticker": event.get("series_ticker"),
        "event_ticker": event_ticker, "market_ticker": ticker,
        "ticker_suffix": ticker_suffix(ticker, event_ticker),
        "title": market.get("title"), "event_title": event.get("title"),
        "yes_sub_title": market.get("yes_sub_title"), "category": event.get("category"),
        "strike_type": market.get("strike_type"),
        "floor_strike": _dec(market.get("floor_strike")),
        "cap_strike": _dec(market.get("cap_strike")),
        "custom_strike": market.get("custom_strike"),
        "open_time": _parse_ts(market.get("open_time")),
        "close_time": _parse_ts(market.get("close_time")),
        "expected_expiration_time": _parse_ts(market.get("expected_expiration_time")),
        "poll_anchor": poll_anchor(market),
        "status": market.get("status"), "market_type": market.get("market_type"),
        "mutually_exclusive": event.get("mutually_exclusive"),
        "price_level_structure": market.get("price_level_structure"),
        "price_ranges": market.get("price_ranges"), "min_tick": min_tick(market),
        "rules_primary": market.get("rules_primary"),
        "rules_secondary": market.get("rules_secondary"),
        "settlement_sources": event.get("settlement_sources"),
        "raw": market,
    }


def price_row(event: dict[str, Any], market: dict[str, Any], captured_at: dt.datetime,
              *, raw: bool = False, fees: dict[str, Any] | None = None) -> dict:
    """Prices only; Kalshi serves them as decimal STRINGS ('0.8700'), kept exact.

    `fees` is the series' CURRENT fee regime, stamped on every row rather than
    resolved once — see the module docstring.
    """
    fees = fees or {}
    return {
        "captured_at": captured_at, "market_ticker": market.get("ticker"),
        "event_ticker": market.get("event_ticker") or event.get("event_ticker"),
        "series_ticker": event.get("series_ticker"),
        "yes_bid": _dec(market.get("yes_bid_dollars")),
        "yes_ask": _dec(market.get("yes_ask_dollars")),
        "yes_bid_size": _dec(market.get("yes_bid_size_fp")),
        "yes_ask_size": _dec(market.get("yes_ask_size_fp")),
        "last_price": _dec(market.get("last_price_dollars")),
        "volume": _dec(market.get("volume_fp")),
        "open_interest": _dec(market.get("open_interest_fp")),
        "status": market.get("status"), "result": market.get("result"),
        "fee_type": fees.get("fee_type"), "fee_multiplier": _dec(fees.get("fee_multiplier")),
        "book": None, "raw": market if raw else None,
    }


def changed(previous: dict | None, row: dict, keys: tuple[str, ...]) -> bool:
    """False iff every key equals the last row WE wrote for this ticker.

    Compared on the ROW, never on the payload: one parse, one representation,
    so there is no second implementation of the fingerprint to drift.
    """
    if previous is None:
        return True
    return any(previous.get(k) != row.get(k) for k in keys)


