"""The sub-second record of the BTC window in play: every venue book message, every print and
every exchange quote update, stamped on one clock at receipt -- one SQLite file, one writer thread.

Why a file of its own and not the ledger: the ledger is the money book (fills, settlements, the
$10 guard) and its once-a-second ``ticks`` and ``quotes`` tables are the settlement proxy and the
joint quote tape, whose meaning analyses already depend on. This file is the instrument that tape
cannot be. Measured on the tape itself, 2026-09-30: ``quotes`` was written every 3.6 s (05:08Z to
16:20Z) and every 1.85 s after the message-driven deploy, and 13-17 % of the composite's seconds
were skipped while the loop waited on a REST ticker. The arms act on the venue's messages; this
records what they saw at that resolution -- the book at every message, the prints (the only fill
evidence short of an order, and what a maker's fill model reads), and spot from the exchanges'
own sockets -- so that spot-vs-book lead-lag, quote staleness and adverse selection can be read
at the cadence the decisions are made at, not at the tape's.

Writers enqueue and never block; a full queue drops the row and counts it. A socket quote
whose bid and ask equal the exchange's previous stored quote is not stored again (Coinbase
prints a ticker on every trade; the mid moves far less often). Rows older than ``keep_days``
(3, MERIDIAN_BTC15_MICROTAPE_DAYS) are pruned once an hour so the file stays bounded on a disk
that was at 90 % when this shipped; the growth per day is measured in docs/math/btc15-microtape.md.
"""
from __future__ import annotations

import collections
import logging
import queue
import sqlite3
import threading
import time

log = logging.getLogger("btc15.microtape")

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
CREATE TABLE IF NOT EXISTS book_msgs(
  recv REAL NOT NULL, slug TEXT NOT NULL, bid REAL, ask REAL, bid_size REAL, ask_size REAL, tt TEXT, state TEXT);
CREATE INDEX IF NOT EXISTS book_msgs_slug ON book_msgs(slug, recv);
CREATE TABLE IF NOT EXISTS trades(
  recv REAL NOT NULL, slug TEXT NOT NULL, price REAL, quantity REAL, trade_time TEXT,
  taker_intent TEXT, maker_intent TEXT);
CREATE INDEX IF NOT EXISTS trades_slug ON trades(slug, recv);
CREATE TABLE IF NOT EXISTS spot(
  recv REAL NOT NULL, exchange TEXT NOT NULL, bid REAL, ask REAL, last REAL);
CREATE INDEX IF NOT EXISTS spot_recv ON spot(recv);
CREATE TABLE IF NOT EXISTS brti(
  recv REAL NOT NULL, source_ts_ms INTEGER, value REAL NOT NULL, avg_60s REAL, last_60s_15m REAL, seq INTEGER);
CREATE INDEX IF NOT EXISTS brti_recv ON brti(recv);
CREATE TABLE IF NOT EXISTS kalshi_book(
  recv REAL NOT NULL, ticker TEXT NOT NULL, side TEXT NOT NULL, level INTEGER NOT NULL, price REAL NOT NULL, size REAL NOT NULL);
CREATE INDEX IF NOT EXISTS kalshi_book_t ON kalshi_book(ticker, recv);
"""

_INSERT = {
    "book": "INSERT INTO book_msgs(recv,slug,bid,ask,bid_size,ask_size,tt,state) VALUES(?,?,?,?,?,?,?,?)",
    "trade": "INSERT INTO trades(recv,slug,price,quantity,trade_time,taker_intent,maker_intent) VALUES(?,?,?,?,?,?,?)",
    "spot": "INSERT INTO spot(recv,exchange,bid,ask,last) VALUES(?,?,?,?,?)",
    "brti": "INSERT INTO brti(recv,source_ts_ms,value,avg_60s,last_60s_15m,seq) VALUES(?,?,?,?,?,?)",
    "kalshi_book": "INSERT INTO kalshi_book(recv,ticker,side,level,price,size) VALUES(?,?,?,?,?,?)",
}


class Microtape:
    def __init__(self, path: str, *, keep_days: float = 3.0, clock=time.time, max_queue: int = 100_000,
                 flush_s: float = 0.5) -> None:
        self.path, self.keep_days, self._clock, self.flush_s = path, keep_days, clock, flush_s
        self._last_spot: dict[str, tuple] = {}
        self._q: queue.Queue = queue.Queue(maxsize=max_queue)
        self.dropped = 0
        self.written: collections.Counter = collections.Counter()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._local = threading.local()
        self._next_prune = 0.0
        conn = sqlite3.connect(path)                     # a bad path fails here, on the caller's thread
        try:
            conn.executescript(SCHEMA)
        finally:
            conn.close()

    # ------------------------------------------------------------------ writers (any thread, never block)
    def book(self, row: dict, at: float) -> None:
        self._put("book", (at, row.get("slug"), row.get("bid"), row.get("ask"), row.get("bid_size"),
                           row.get("ask_size"), row.get("tt"), row.get("state")))

    def trade(self, row: dict, at: float) -> None:
        self._put("trade", (at, row.get("slug"), row.get("price"), row.get("quantity"), row.get("tradeTime"),
                            row.get("taker_intent"), row.get("maker_intent")))

    def spot(self, exchange: str, bid: float, ask: float, last: float, at: float) -> None:
        if self._last_spot.get(exchange) == (bid, ask):
            return                                           # the touch did not move: nothing new to record
        self._last_spot[exchange] = (bid, ask)
        self._put("spot", (at, exchange, bid, ask, last))

    def brti(self, tick) -> None:
        """Kalshi's relay of the settlement index (core/btc15/brti_relay.py), every tick."""
        self._put("brti", (tick.recv, tick.source_ts_ms, tick.value, tick.avg_60s, tick.last_60s_15m, tick.seq))

    def kalshi_book(self, ticker: str, levels: dict | None, at: float) -> None:
        """Kalshi's depth at one read (core/btc15/kalshi.book_levels): one row per level per side.
        Taped so the size resting at the last tenths of a cent near the close can be read."""
        if not levels:
            return
        for side in ("yes", "no"):
            for i, (price, size) in enumerate(levels.get(side) or []):
                self._put("kalshi_book", (at, ticker, side, i, price, size))

    def _put(self, kind: str, values: tuple) -> None:
        try:
            self._q.put_nowait((kind, values))
        except queue.Full:
            self.dropped += 1

    # ------------------------------------------------------------------ the writer
    def start(self) -> "Microtape":
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="btc-microtape", daemon=True)
            self._thread.start()
        return self

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
        self.drain()

    def _conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = self._local.conn = sqlite3.connect(self.path, isolation_level=None)
            c.execute("PRAGMA synchronous=NORMAL")
        return c

    def drain(self) -> int:
        """Write everything queued, in one transaction per table. Returns rows written."""
        batches: dict[str, list] = collections.defaultdict(list)
        while True:
            try:
                kind, values = self._q.get_nowait()
            except queue.Empty:
                break
            batches[kind].append(values)
        if not batches:
            return 0
        c = self._conn()
        n = 0
        try:
            c.execute("BEGIN")
            for kind, rows in batches.items():
                c.executemany(_INSERT[kind], rows)
                self.written[kind] += len(rows)
                n += len(rows)
            c.execute("COMMIT")
        except sqlite3.Error:
            log.exception("microtape write")
            try:
                c.execute("ROLLBACK")
            except sqlite3.Error:
                pass
        return n

    def prune(self, now: float | None = None) -> None:
        now = self._clock() if now is None else now
        floor = now - self.keep_days * 86400
        c = self._conn()
        for t in ("book_msgs", "trades", "spot", "brti", "kalshi_book"):
            c.execute(f"DELETE FROM {t} WHERE recv < ?", (floor,))

    def _run(self) -> None:
        while not self._stop.is_set():
            self._stop.wait(self.flush_s)
            try:
                self.drain()
                now = self._clock()
                if now >= self._next_prune:
                    self._next_prune = now + 3600
                    self.prune(now)
            except Exception:                                # noqa: BLE001 -- the tape never stops the harness
                log.exception("microtape")

    def counters(self) -> dict:
        return {"written": dict(self.written), "dropped": self.dropped, "queued": self._q.qsize(),
                "alive": self._thread is not None and self._thread.is_alive()}
