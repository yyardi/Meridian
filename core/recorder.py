"""Polymarket US market snapshot recorder.

This is the most important process in Meridian, for one reason: **its output
cannot be reconstructed**. Team stats and sportsbook odds can be backfilled
from ESPN years after the fact. A market's bid/ask at 7:42pm on a Tuesday
exists only if something wrote it down at 7:42pm on that Tuesday.

Consequences that shape the code below:

* **Never crash the loop.** A recorder that dies unattended at 2am and is
  noticed a fortnight later has lost a fortnight. Every failure is caught at
  the narrowest scope that still allows progress: one bad market must not lose
  the other 149.
* **Idempotent by construction.** Snapshots are append-only and keyed
  `(market_slug, captured_at)`. A crash mid-cycle followed by a rerun re-inserts
  the same rows harmlessly rather than duplicating or half-writing.
* **Keep the raw payload.** Parsing can be fixed later; unrecorded data cannot.
"""

from __future__ import annotations

import datetime as dt
import signal
import time
from decimal import Decimal

import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from core.config import RECORDER, RecorderConfig
from core.heartbeat import SERVICE_PREGAME, Heartbeat
from core.polymarket.client import PolymarketGatewayClient
from core.polymarket.schemas import Event, Market
from core.storage import BookLevel, MarketSnapshot, get_engine, get_sessionmaker

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc


def _parse_ts(value: str | None) -> dt.datetime | None:
    """Parse an ISO-8601 timestamp, tolerating a trailing 'Z'."""
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class RecorderStats:
    """Per-cycle counters, for logging and for the health check."""

    def __init__(self) -> None:
        self.markets_seen = 0
        self.snapshots_written = 0
        self.books_written = 0
        self.market_errors = 0
        self.book_errors = 0


class Recorder:
    def __init__(
        self,
        config: RecorderConfig | None = None,
        client: PolymarketGatewayClient | None = None,
        sessionmaker=None,
    ) -> None:
        self.config = config or RECORDER
        self._client = client or PolymarketGatewayClient(self.config)
        self._Session = sessionmaker or get_sessionmaker(get_engine())
        self._heartbeat = Heartbeat(self._Session, SERVICE_PREGAME)

    # ------------------------------------------------------------------ #
    # One cycle
    # ------------------------------------------------------------------ #

    def run_once(self, captured_at: dt.datetime | None = None) -> RecorderStats:
        """Capture one full snapshot of the league board.

        All rows in a cycle share `captured_at`, so a snapshot is a coherent
        instant rather than a smear across the fetch duration.
        """
        captured_at = captured_at or dt.datetime.now(UTC)
        stats = RecorderStats()
        started = time.monotonic()

        try:
            parsed, raw = self._client.get_league_events()
        except Exception as exc:
            # The board call is the one failure we cannot work around — without
            # it there is nothing to record. Log and let the loop retry.
            log.error("board_fetch_failed", error=str(exc), exc_info=True)
            return stats

        raw_events = {str(e.get("slug")): e for e in raw.get("events", []) if isinstance(e, dict)}

        with self._Session() as session:
            for event in parsed.events:
                raw_event = raw_events.get(event.slug or "", {})
                raw_markets = {
                    str(m.get("slug")): m
                    for m in raw_event.get("markets", [])
                    if isinstance(m, dict)
                }
                for market in event.markets:
                    stats.markets_seen += 1
                    try:
                        self._record_market(
                            session=session,
                            event=event,
                            market=market,
                            captured_at=captured_at,
                            raw_market=raw_markets.get(market.slug),
                            stats=stats,
                        )
                    except Exception as exc:
                        # Narrow scope on purpose: one malformed market must not
                        # cost us the rest of the slate.
                        stats.market_errors += 1
                        session.rollback()
                        log.error(
                            "market_record_failed",
                            market_slug=market.slug,
                            error=str(exc),
                            exc_info=True,
                        )
            session.commit()

        log.info(
            "cycle_complete",
            captured_at=captured_at.isoformat(),
            markets_seen=stats.markets_seen,
            snapshots=stats.snapshots_written,
            books=stats.books_written,
            market_errors=stats.market_errors,
            book_errors=stats.book_errors,
            duration_s=round(time.monotonic() - started, 2),
        )
        return stats

    def _record_market(
        self,
        *,
        session: Session,
        event: Event,
        market: Market,
        captured_at: dt.datetime,
        raw_market: dict | None,
        stats: RecorderStats,
    ) -> None:
        state = event.event_state
        values = {
            "captured_at": captured_at,
            "market_slug": market.slug,
            "market_id": market.id,
            "event_slug": event.slug,
            "event_id": event.id,
            "game_id": event.game_id,
            "sports_market_type": market.sports_market_type,
            "line": market.line,
            "best_bid": market.best_bid,
            "best_ask": market.best_ask,
            "min_tick_size": market.order_price_min_tick_size,
            "min_trade_qty": market.minimum_trade_qty,
            "fee_coefficient": market.fee_coefficient,
            "game_start_time": _parse_ts(market.game_start_time or event.start_time),
            "is_live": event.is_live,
            "event_score": state.score if state else None,
            "event_period": state.period if state else None,
            "raw": raw_market,
        }

        # ON CONFLICT DO NOTHING makes a rerun after a crash a no-op rather
        # than a duplicate or a partial overwrite.
        stmt = (
            pg_insert(MarketSnapshot)
            .values(**values)
            .on_conflict_do_nothing(constraint="uq_snapshot_market_time")
            .returning(MarketSnapshot.id)
        )
        snapshot_id = session.execute(stmt).scalar()
        if snapshot_id is None:
            # Already recorded at this instant — nothing further to do.
            return
        stats.snapshots_written += 1

        if self.config.capture_depth:
            try:
                self._record_book(session, market.slug, snapshot_id)
                stats.books_written += 1
            except Exception as exc:
                # Depth is valuable but optional; never lose the top-of-book
                # snapshot because the book call failed.
                stats.book_errors += 1
                log.warning("book_fetch_failed", market_slug=market.slug, error=str(exc))

    def _record_book(self, session: Session, market_slug: str, snapshot_id: int) -> None:
        book, _raw = self._client.get_book(market_slug)
        data = book.market_data
        if data is None:
            return

        rows: list[dict] = []
        for side, entries in (("bid", data.bids), ("offer", data.offers)):
            for idx, entry in enumerate(entries[: self.config.max_book_levels]):
                price = entry.px.value if entry.px else None
                if price is None or entry.qty is None:
                    continue
                rows.append(
                    {
                        "snapshot_id": snapshot_id,
                        "side": side,
                        "price": price,
                        "quantity": entry.qty,
                        "level_index": idx,
                    }
                )
        if rows:
            session.execute(
                pg_insert(BookLevel).values(rows).on_conflict_do_nothing(
                    constraint="uq_book_level"
                )
            )

    # ------------------------------------------------------------------ #
    # Cadence
    # ------------------------------------------------------------------ #

    def next_interval_seconds(self, now: dt.datetime | None = None) -> int:
        """15 min when a tip-off is near or a game is live, else 60 min.

        Line movement concentrates in the hours before tip-off; polling hourly
        overnight wastes nothing of value.
        """
        now = now or dt.datetime.now(UTC)
        try:
            parsed, _ = self._client.get_league_events()
        except Exception:
            # If we cannot tell, poll at the faster rate. Over-sampling costs a
            # few requests; under-sampling loses data permanently.
            return self.config.interval_near_tipoff_seconds

        window = dt.timedelta(hours=self.config.near_tipoff_hours)
        for event in parsed.events:
            if event.is_live:
                return self.config.interval_near_tipoff_seconds
            start = _parse_ts(event.start_time)
            if start and now <= start <= now + window:
                return self.config.interval_near_tipoff_seconds
        return self.config.interval_idle_seconds

    def run_forever(self) -> None:
        """Poll on an adaptive cadence until signalled to stop."""
        stopping = {"flag": False}

        def _handle(signum, _frame):
            log.info("shutdown_signal", signal=signum)
            stopping["flag"] = True

        signal.signal(signal.SIGINT, _handle)
        signal.signal(signal.SIGTERM, _handle)

        log.info("recorder_started", league=self.config.league_slug)
        while not stopping["flag"]:
            started = time.monotonic()
            stats = RecorderStats()
            try:
                stats = self.run_once()
            except Exception as exc:
                # Absolute backstop. Nothing gets to kill this loop.
                log.error("cycle_failed", error=str(exc), exc_info=True)

            interval = self.next_interval_seconds()
            # Every cycle, whatever the cycle did (B11). A crashing cycle still
            # beats — the process IS alive — and the 0 in rows_written is what
            # says it produced nothing.
            self._heartbeat.beat(
                interval_seconds=interval,
                rows_written=stats.snapshots_written,
                cycle_seconds=time.monotonic() - started,
            )
            log.info("sleeping", seconds=interval)
            # Sleep in short slices so shutdown is prompt rather than waiting
            # out a full hour.
            waited = 0
            while waited < interval and not stopping["flag"]:
                time.sleep(min(5, interval - waited))
                waited += 5
        log.info("recorder_stopped")
