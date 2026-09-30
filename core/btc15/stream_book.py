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
"""
from __future__ import annotations

import logging
import threading
import time

from core.ladder.stream import StreamConnection

log = logging.getLogger("btc15.stream")


class _Sink:
    """What StreamConnection writes to: here, the last touch per slug, in memory."""

    def __init__(self, clock=time.time, on_update=None) -> None:
        self._lock = threading.Lock()
        self._clock = clock
        self._on_update = on_update
        self.rows: dict[str, tuple[float, dict]] = {}

    def book(self, game: str, row: dict) -> None:
        with self._lock:
            self.rows[row["slug"]] = (self._clock(), row)
        if self._on_update is not None:                     # on the socket's thread: the harness acts now
            try:
                self._on_update(row["slug"])
            except Exception:                                # noqa: BLE001 -- a handler error never drops the socket
                log.exception("stream update handler")

    def trade(self, game: str, row: dict) -> None:
        pass

    def get(self, slug: str) -> tuple[float, dict] | None:
        with self._lock:
            return self.rows.get(slug)

    def forget_except(self, slug: str) -> None:
        with self._lock:
            self.rows = {k: v for k, v in self.rows.items() if k == slug}


class StreamBook:
    #: A socket whose thread died (it should not: StreamConnection reconnects on its own) is
    #: restarted at most this often, so a persistent failure cannot become a thread a second.
    RESTART_S = 30.0

    def __init__(self, *, open_socket=None, live_s: float = 30.0, clock=time.time, enabled: bool = True,
                 on_update=None) -> None:
        self._open_socket = open_socket
        self.enabled = enabled          # False: no credentials -- never subscribes, never live
        self.live_s = live_s
        self._started_at = float("-inf")
        self._clock = clock
        #: Called with the slug on every MARKET_DATA update, on the socket's thread.
        self.on_update = on_update
        self.sink = _Sink(clock, lambda slug: self.on_update(slug) if self.on_update is not None else None)
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

    def status(self, now: float | None = None) -> dict:
        c = self.conn
        return {"slug": self.slug, "live": self.live(now),
                "books": None if c is None else c.books, "reconnects": None if c is None else c.reconnects,
                "last_error": None if c is None else c.last_error}
