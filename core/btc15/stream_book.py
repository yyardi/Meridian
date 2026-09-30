"""The venue's book for the window in play, off its market-data stream.

The venue's REST book (``/v1/markets/<slug>/book``) is served through Cloudflare with
``cache-control: public, max-age=30`` (``cf-cache-status: HIT``, read 2026-09-30). Measured
the same night, it held unchanged -- sizes to the cent -- for a mean of 24 s while Kalshi's
order book changed every second (analysis/btc15/quote_freshness_probe.py). Every arm had
entered and paper-filled on it, so a fill could land at a price the book had already left.

This keeps one socket -- the recorder's own ``core.ladder.stream.StreamConnection``, which
has run live on the sports slates -- subscribed to the window in play, and holds the last
MARKET_DATA touch it delivered. ``touch`` answers only while the socket is live (a message,
update or heartbeat, within ``live_s``) and only for the window it is subscribed to; any
other state is None, and the harness does not trade on None.

It also keeps the window's PRINTS (the socket's TRADE messages: price, quantity, which side
took) in memory, stamped at receipt on the same clock as the books. A print is the only fill
evidence short of an order: a maker arm reads ``prints`` to decide whether a resting quote
would have been filled. Every book message and every print is also handed to the optional
``on_book`` / ``on_trade`` hooks (the microtape) on the socket's thread, before the arms act.
"""
from __future__ import annotations

import collections
import logging
import threading
import time

from core.ladder.stream import StreamConnection

log = logging.getLogger("btc15.stream")


class _Sink:
    """What StreamConnection writes to: here, the last touch per slug, in memory."""

    #: Prints kept per window, newest last; a 15-minute window prints far fewer than this.
    PRINTS_KEPT = 20_000

    def __init__(self, clock=time.time, on_update=None, on_book=None, on_trade=None) -> None:
        self._lock = threading.Lock()
        self._clock = clock
        self._on_update, self._on_book, self._on_trade = on_update, on_book, on_trade
        self.rows: dict[str, tuple[float, dict]] = {}
        #: slug -> deque of (at, price, quantity, taker_intent, maker_intent)
        self.prints: dict[str, collections.deque] = {}

    def book(self, game: str, row: dict) -> None:
        at = self._clock()
        with self._lock:
            self.rows[row["slug"]] = (at, row)
        self._call(self._on_book, row, at)
        if self._on_update is not None:                     # on the socket's thread: the harness acts now
            try:
                self._on_update(row["slug"])
            except Exception:                                # noqa: BLE001 -- a handler error never drops the socket
                log.exception("stream update handler")

    def trade(self, game: str, row: dict) -> None:
        at = self._clock()
        with self._lock:
            d = self.prints.get(row["slug"])
            if d is None:
                d = self.prints[row["slug"]] = collections.deque(maxlen=self.PRINTS_KEPT)
            d.append((at, row.get("price"), row.get("quantity"), row.get("taker_intent"), row.get("maker_intent")))
        self._call(self._on_trade, row, at)

    @staticmethod
    def _call(hook, row: dict, at: float) -> None:
        if hook is None:
            return
        try:
            hook(row, at)
        except Exception:                                    # noqa: BLE001 -- a tape error never drops the socket
            log.exception("stream tape hook")

    def get(self, slug: str) -> tuple[float, dict] | None:
        with self._lock:
            return self.rows.get(slug)

    def prints_since(self, slug: str, since: float) -> list[tuple]:
        """The window's prints received after ``since``, oldest first."""
        with self._lock:
            d = self.prints.get(slug)
            return [p for p in d if p[0] > since] if d else []

    def forget_except(self, slug: str) -> None:
        with self._lock:
            self.rows = {k: v for k, v in self.rows.items() if k == slug}
            self.prints = {k: v for k, v in self.prints.items() if k == slug}


class StreamBook:
    #: A socket whose thread died (it should not: StreamConnection reconnects on its own) is
    #: restarted at most this often, so a persistent failure cannot become a thread a second.
    RESTART_S = 30.0

    def __init__(self, *, open_socket=None, live_s: float = 30.0, clock=time.time, enabled: bool = True,
                 on_update=None, on_book=None, on_trade=None) -> None:
        self._open_socket = open_socket
        self.enabled = enabled          # False: no credentials -- never subscribes, never live
        self.live_s = live_s
        self._started_at = float("-inf")
        self._clock = clock
        #: Called with the slug on every MARKET_DATA update, on the socket's thread.
        self.on_update = on_update
        #: Called with (row, at) for every book message / every print, on the socket's thread, before
        #: on_update. The microtape hangs here; a hook that raises is logged and never drops the socket.
        self.on_book, self.on_trade = on_book, on_trade
        self.sink = _Sink(clock, lambda slug: self.on_update(slug) if self.on_update is not None else None,
                          lambda row, at: self.on_book(row, at) if self.on_book is not None else None,
                          lambda row, at: self.on_trade(row, at) if self.on_trade is not None else None)
        self.slug: str | None = None
        self.conn: StreamConnection | None = None
        self._thread: threading.Thread | None = None

    def ensure(self, slug: str) -> None:
        """Be subscribed to ``slug``: a new window replaces the previous window's socket."""
        if not self.enabled:
            return
        if slug == self.slug and self._thread is not None and self._thread.is_alive():
            return
        if slug == self.slug and self._clock() - self._started_at < self.RESTART_S:
            return
        self.stop()
        self._started_at = self._clock()
        self.slug = slug
        self.sink.forget_except(slug)
        self.conn = StreamConnection("btc", [[slug]], self.sink, open_socket=self._open_socket)
        self._thread = threading.Thread(target=self.conn.run, name=f"btc-stream-{slug[-6:]}", daemon=True)
        self._thread.start()
        log.info("stream: subscribing %s", slug)

    def stop(self) -> None:
        if self.conn is not None:
            self.conn.request_stop()
        self.conn, self._thread = None, None

    def live(self, now: float | None = None) -> bool:
        c = self.conn
        if c is None or not c.connected or c.last_msg_at is None:
            return False
        now = self._clock() if now is None else now
        return now - c.last_msg_at <= self.live_s

    def touch(self, slug: str, now: float | None = None) -> dict | None:
        """The last streamed touch for ``slug``, or None unless the socket is live on it."""
        if slug != self.slug or not self.live(now):
            return None
        hit = self.sink.get(slug)
        if hit is None:
            return None
        at, row = hit
        now = self._clock() if now is None else now
        return {**row, "age_s": round(now - at, 3)}

    def prints(self, slug: str, since: float) -> list[tuple]:
        """The window's prints received after ``since`` -- (at, price, quantity, taker_intent,
        maker_intent), oldest first -- while the socket is live on it; otherwise none (a dead
        socket has not seen the prints, and "none seen" must not read as "none happened")."""
        if slug != self.slug or not self.live():
            return []
        return self.sink.prints_since(slug, since)

    def status(self, now: float | None = None) -> dict:
        c = self.conn
        return {"slug": self.slug, "live": self.live(now),
                "books": None if c is None else c.books, "trades": None if c is None else c.trades,
                "reconnects": None if c is None else c.reconnects,
                "last_error": None if c is None else c.last_error}
