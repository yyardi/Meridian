"""Kalshi's touch on the same games, taped beside the venue's stream for the thin leagues.

For the international basketball leagues the anchor in
docs/math/intl-basketball-ls-research.md is Kalshi's price on the same game:
its books are 1-6c wide and trade six figures a market where the venue's are
7c wide and mostly empty. The events recorder that would carry it writes to the
shared Postgres (OOM-killed three times on 2026-09-26/27) and is not running,
so the stream slate tapes Kalshi itself, into the same directory as the venue's
books, for exactly the window the venue is recorded:

    <out>/kalshi_<league>.jsonl   one line per market whose touch CHANGED:
    {"recv", "prev_recv", "ticker", "event_ticker", "team", "yes_bid", "yes_ask",
     "yes_bid_size", "yes_ask_size", "last", "volume", "open_interest", "status",
     "result", "updated_time"}

Prices and sizes are Kalshi's own decimal strings, kept as strings (the
``*_dollars`` / ``*_fp`` fields); ``updated_time`` is Kalshi's stamp. Public,
unauthenticated GETs: one per series per ``interval_s``.

Series verified against Kalshi's /series listing on 2026-09-28. The venue's
``denbl`` and ``hunbl`` have no Kalshi series (its "Danish Superliga" series are
football); ``slnbl`` maps to both Slovenian series Kalshi lists.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import threading
import time

import httpx

KALSHI = os.environ.get("KALSHI_API_URL", "https://api.elections.kalshi.com/trade-api/v2")

KALSHI_SERIES_BY_LEAGUE: dict[str, tuple[str, ...]] = {
    "eurolg": ("KXEUROLEAGUEGAME",),
    "lnbp": ("KXLNBPGAME",),
    "bbl": ("KXBBLGAME",),
    "vtb": ("KXVTBGAME",),
    "bsl": ("KXBSLGAME",),
    "slnbl": ("KXSKLGAME", "KXSVNPLGAME"),
}

_MAP = (("yes_bid", "yes_bid_dollars"), ("yes_ask", "yes_ask_dollars"),
        ("yes_bid_size", "yes_bid_size_fp"), ("yes_ask_size", "yes_ask_size_fp"),
        ("last", "last_price_dollars"), ("volume", "volume_fp"), ("open_interest", "open_interest_fp"),
        ("status", "status"), ("result", "result"))


def _iso(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat(timespec="milliseconds")


def touch_of(m: dict) -> dict:
    return {k: m.get(src) for k, src in _MAP}


class KalshiTape:
    def __init__(self, league: str, out_dir: str, *, interval_s: float = 10.0,
                 client: httpx.Client | None = None, clock=time.time, sleep=time.sleep) -> None:
        self.series = KALSHI_SERIES_BY_LEAGUE[league]
        self.path = os.path.join(out_dir, f"kalshi_{league}.jsonl")
        self.interval_s = interval_s
        self._http = client or httpx.Client(timeout=10.0, headers={"User-Agent": "meridian-kalshi-tape/1"})
        self._clock, self._sleep = clock, sleep
        self._last: dict[str, dict] = {}
        self._prev_poll: float | None = None
        self.polls = self.changes = self.errors = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def poll_once(self) -> int:
        """One request per series; append a line per market whose touch changed. Returns lines written."""
        lines = []
        now = None
        for s in self.series:
            try:
                r = self._http.get(f"{KALSHI}/markets", params={"series_ticker": s, "status": "open", "limit": 1000})
                r.raise_for_status()
                markets = r.json().get("markets") or []
            except (httpx.HTTPError, ValueError):
                self.errors += 1
                continue
            now = self._clock()
            for m in markets:
                t = touch_of(m)
                if self._last.get(m["ticker"]) == t:
                    continue
                self._last[m["ticker"]] = t
                lines.append({"recv": _iso(now), "prev_recv": None if self._prev_poll is None else _iso(self._prev_poll),
                              "ticker": m["ticker"], "event_ticker": m.get("event_ticker"),
                              "team": m.get("yes_sub_title"), **t, "updated_time": m.get("updated_time")})
        if now is not None:
            self._prev_poll = now
            self.polls += 1
        if lines:
            with open(self.path, "a") as fh:
                fh.write("".join(json.dumps(x) + "\n" for x in lines))
            self.changes += len(lines)
        return len(lines)

    def run(self) -> None:
        while not self._stop.is_set():
            t0 = self._clock()
            self.poll_once()
            self._stop.wait(max(0.5, self.interval_s - (self._clock() - t0)))

    def start(self) -> None:
        self._thread = threading.Thread(target=self.run, name="kalshi-tape", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def status(self) -> str:
        return (f"kalshi  series {','.join(self.series)}  polls {self.polls}  "
                f"markets {len(self._last)}  changes {self.changes}  errors {self.errors}")
