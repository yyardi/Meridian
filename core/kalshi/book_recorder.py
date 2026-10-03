"""Kalshi's in-play books and prints for one slate, off its websocket, to files. Reads only.

Why: docs/math/cross-venue-status.md (2026-09-04) left the Polymarket-vs-Kalshi in-play gap
UNMEASURED because Kalshi was sampled every 120 s while Polymarket streamed; the five instants
that qualified were all one game at sub-second lag. This records Kalshi at message cadence for
the games the Polymarket slate recorder (cfb/run_stream_slate.py) is taping, so the two tapes
can be matched instant to instant (docs/math/cross-venue-inplay-football.md).

    python -m core.kalshi.book_recorder --series KXNFLGAME,KXNFLSPREAD --date 26OCT04 --minutes 740 --out /out

Discovers the open markets of those series whose ticker carries one of the date tags, writes
`tickers.json`, subscribes to `orderbook_delta` and `trade` for all of them on the one signed
socket (core/kalshi/lip_scorer.BookSocket: seq-tracked, a gap opens a fresh socket), and
writes, per ticker under --out: `books_<ticker>.jsonl` -- every snapshot RAW, then the TOUCH
(best yes bid and best no bid with their sizes) whenever it changed, coalesced to one line per
ticker per 250 ms carrying the receive stamp of the last change and how many changes it
stands for -- and `trades_<ticker>.jsonl`, every print raw. `--raw` keeps every delta as well.
Why: the first live minute (4 CFB games, 118 markets, 2026-10-03 01:25Z) carried 80,000
messages and 24 MB, deep-book churn at every cent level that no read of ours uses, and the
best level alone still flickered 5-15 times a second on the active markets. The read matches
instants at <= 1 s lag, so 250 ms loses nothing it measures. `_status.json` every minute.
Places nothing.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import re
import sys
import threading
import time

import httpx

from core.kalshi.lip_scorer import REST, Books, BookSocket

log = logging.getLogger("kalshi.recorder")
CHANNELS = ("orderbook_delta", "trade")


def _iso(t: float) -> str:
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def discover(series: list[str], date_tags: list[str], http: httpx.Client | None = None) -> list[dict]:
    """Open markets of ``series`` whose ticker's date segment is one of ``date_tags`` (e.g. 26OCT04).
    The ticker is SERIES-<yyMONdd><TEAMS>-<suffix>; the tag is matched at that position only."""
    http = http or httpx.Client(timeout=20, headers={"User-Agent": "meridian-kalshi-recorder/1"})
    out: list[dict] = []
    for s in series:
        cursor = None
        while True:
            r = http.get(REST + "/markets", params={"series_ticker": s, "status": "open", "limit": 1000,
                                                     **({"cursor": cursor} if cursor else {})})
            r.raise_for_status()
            d = r.json()
            for m in d.get("markets") or []:
                mm = re.match(r"^" + re.escape(s) + r"-(\d{2}[A-Z]{3}\d{2})([A-Z0-9]+)-", m.get("ticker", ""))
                if mm and mm.group(1) in date_tags:
                    out.append({"ticker": m["ticker"], "series": s, "date_tag": mm.group(1), "teams": mm.group(2),
                                "event_ticker": m.get("event_ticker"), "title": m.get("title"),
                                "yes_sub_title": m.get("yes_sub_title"), "open_time": m.get("open_time"),
                                "close_time": m.get("close_time"), "expected_expiration_time": m.get("expected_expiration_time")})
            cursor = d.get("cursor")
            if not cursor or not d.get("markets"):
                break
    return out


class Tape:
    """Append-only jsonl per ticker and channel; one open handle per file, flushed once a second."""

    def __init__(self, out_dir: str, clock=time.time) -> None:
        self.out_dir, self._clock = out_dir, clock
        os.makedirs(out_dir, exist_ok=True)
        self._fh: dict[str, object] = {}
        self._lock = threading.Lock()
        self.lines = self.bytes = 0
        self.per_channel = {"book": 0, "trade": 0, "other": 0}

    def path(self, channel: str, ticker: str) -> str:
        return os.path.join(self.out_dir, f"{'books' if channel == 'book' else 'trades'}_{ticker}.jsonl")

    def write(self, channel: str, ticker: str, row: dict) -> None:
        line = json.dumps(row, separators=(",", ":")) + "\n"
        with self._lock:
            fh = self._fh.get((channel, ticker))
            if fh is None:
                fh = self._fh[(channel, ticker)] = open(self.path(channel, ticker), "a", encoding="utf-8")
            fh.write(line)
            self.lines += 1; self.bytes += len(line); self.per_channel[channel] = self.per_channel.get(channel, 0) + 1

    def flush(self) -> None:
        with self._lock:
            for fh in self._fh.values():
                fh.flush()

    def close(self) -> None:
        with self._lock:
            for fh in self._fh.values():
                fh.close()
            self._fh.clear()


class RecordingBooks(Books):
    """Snapshots and prints raw; the best level on change, coalesced by ``drain``; deltas only under ``raw``."""

    def __init__(self, tape: Tape, raw: bool = False) -> None:
        super().__init__()
        self.tape, self.raw = tape, raw
        self.trades = self.other = self.touch_lines = self.touch_changes = 0
        self._last_touch: dict[str, tuple] = {}
        self._dirty: dict[str, dict] = {}
        self._dlock = threading.Lock()

    def touch(self, tk: str) -> tuple:
        yes = self.side(tk, "yes"); no = self.side(tk, "no")
        return (yes[0][0] if yes else None, yes[0][1] if yes else None, no[0][0] if no else None, no[0][1] if no else None)

    def handle(self, msg: dict, now: float) -> str | None:
        t = msg.get("type")
        m = msg.get("msg") or {}
        tk = m.get("market_ticker")
        row = {"recv": _iso(now), "type": t, "sid": msg.get("sid"), "seq": msg.get("seq")}
        if t in ("orderbook_snapshot", "orderbook_delta") and tk:
            if t == "orderbook_snapshot" or self.raw:
                self.tape.write("book", tk, {**row, "msg": m})
            out = super().handle(msg, now)
            if out == "gap":
                return out                                   # the gapped delta is not applied; a fresh socket follows
            tc = self.touch(tk)
            if tc != self._last_touch.get(tk):
                self._last_touch[tk] = tc
                self.touch_changes += 1
                with self._dlock:
                    d = self._dirty.get(tk)
                    self._dirty[tk] = {"recv": row["recv"], "type": "touch", "yes_bid": tc[0], "yes_bid_size": tc[1],
                                       "no_bid": tc[2], "no_bid_size": tc[3], "changes": (d["changes"] + 1) if d else 1}
            return out
        if t == "trade" and tk:
            self.trades += 1
            self.tape.write("trade", tk, {**row, "msg": m})
            return None
        if t not in ("subscribed", "ok", "unsubscribed"):
            self.other += 1
            self.tape.write("other", "_unrouted", {**row, "raw": msg})
        return None

    def drain(self) -> int:
        """Write every ticker whose touch changed since the last drain: one line each, the last
        state, stamped with its last change. Called from the main loop every 250 ms."""
        with self._dlock:
            dirty, self._dirty = self._dirty, {}
        for tk, line in dirty.items():
            self.tape.write("book", tk, line)
        self.touch_lines += len(dirty)
        return len(dirty)


def status(now: float, tickers: list[dict], sock: BookSocket, books: RecordingBooks, tape: Tape, started: float, minutes: float) -> dict:
    return {"at": _iso(now), "tickers": len(tickers), "series": sorted({t["series"] for t in tickers}),
            "elapsed_min": round((now - started) / 60, 1), "minutes": minutes,
            "socket": sock.counters(now), "trades": books.trades, "touch_lines": books.touch_lines, "touch_changes": books.touch_changes, "unrouted": books.other,
            "tape": {"lines": tape.lines, "bytes": tape.bytes, **tape.per_channel}}


def run(a) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    series = [s for s in a.series.split(",") if s]
    tags = [t.strip().upper() for t in a.date.split(",") if t.strip()]
    tickers = discover(series, tags)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "tickers.json"), "w", encoding="utf-8") as fh:
        json.dump({"discovered_at": _iso(time.time()), "series": series, "date_tags": tags, "markets": tickers}, fh, indent=1)
    log.info("kalshi recorder: %d markets in %s for %s; %d minutes; out %s", len(tickers), series, tags, a.minutes, a.out)
    if not tickers:
        log.warning("nothing to record")
        return 0
    tape = Tape(a.out)
    books = RecordingBooks(tape, raw=a.raw)
    sock = BookSocket(sorted(t["ticker"] for t in tickers), books, channels=CHANNELS).start()
    started = time.time(); next_status = 0.0; status_path = os.path.join(a.out, "_status.json")
    next_flush = 0.0
    try:
        while time.time() - started < a.minutes * 60:
            now = time.time()
            books.drain()
            if now >= next_flush:
                next_flush = now + 1.0
                tape.flush()
            if now >= next_status:
                next_status = now + 60
                st = status(now, tickers, sock, books, tape, started, a.minutes)
                with open(status_path, "w", encoding="utf-8") as fh:
                    json.dump(st, fh, indent=1)
                log.info("status %s", json.dumps({k: v for k, v in st.items() if k != "series"}))
            time.sleep(0.25)
    finally:
        sock.request_stop()
        books.drain(); tape.flush(); tape.close()
        log.info("done: %d lines, %d bytes, %d trades, gaps %d, reconnects %d", tape.lines, tape.bytes, books.trades, len(books.gaps), sock.reconnects)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--series", required=True, help="comma-separated series tickers, e.g. KXNFLGAME,KXNFLSPREAD")
    ap.add_argument("--date", required=True, help="comma-separated ticker date tags, e.g. 26OCT04,26OCT05")
    ap.add_argument("--minutes", type=float, default=600.0)
    ap.add_argument("--out", default="/out")
    ap.add_argument("--raw", action="store_true", help="also write every orderbook_delta raw (24 MB a minute for four CFB games)")
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
