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
        #: Events whose `gameId` was absent and whose id came from the
        #: fallback, and events with NO usable identifier at all. Counted so
        #: the fallback cannot silently become the normal path, and so a
        #: league arriving with neither is LOUD rather than NULL.
        self.game_id_from_fallback = 0
        self.game_id_missing = 0


def _event_key(event: Event, stats: RecorderStats) -> str | None:
    """A stable per-event id for `game_id`, which is a JOIN KEY and a CLUSTER KEY.

    The venue sends `gameId` on US team sports and NOT on cricket or table
    tennis, whose events are shaped differently. Left NULL, the consequences
    are both silent:

    * `run_paper_book`'s CLOSE_SQL does `JOIN g ON g.game_id = s.game_id`, and
      NULL never equals NULL — so every strategy in that league finds zero
      markets forever and prints "no markets on tape", which reads as a quiet
      league rather than a broken join. Third league this has happened to.
    * `clustered(vals, keys)` keys on game_id, so had the join ever succeeded
      with NULLs coerced, every bet would land in ONE cluster and the interval
      would be arithmetic rather than evidence — a number, not a blank, which
      is the worse failure.

    `event_id` and `event_slug` are already recorded on the same row and are
    per-event, so the fallback needs no new data and no slug parsing. Both are
    counted: a fallback that quietly became the normal path would hide the
    venue changing shape under us, and an event with NO identifier writes
    nothing rather than a NULL that reads as a row.
    """
    key = event.game_id or event.id or event.slug
    if key is None:
        stats.game_id_missing += 1
        log.error("event_without_any_id", event_slug=event.slug,
                  event_title=event.title)
        return None
    if event.game_id is None:
        stats.game_id_from_fallback += 1
    return key


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
        # One heartbeat ROW per recorder process (2026-09-02, multi-league
        # expansion): two recorders sharing one service key would mask each
        # other's death — the B11 shape. wnba keeps the bare name so every
        # existing health surface stays true.
        _svc = (SERVICE_PREGAME if self.config.league_slug == "wnba"
                else f"{SERVICE_PREGAME}_{self.config.league_slug}")
        self._heartbeat = Heartbeat(self._Session, _svc)

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

        # A league can be ONE venue slug (wnba, nfl) or several (cricket ->
        # cplcr/t20icr/.../county). Sweeping them in one cycle keeps one
        # heartbeat row per process, which is what the health check counts.
        try:
            from core.leagues import LEAGUES
            venue_leagues = LEAGUES[self.config.league_slug].venue_leagues
        except Exception:
            venue_leagues = (self.config.league_slug,)

        boards, raw_events = [], {}
        for vl in venue_leagues:
            try:
                parsed_vl, raw_vl = self._client.get_league_events(league=vl)
            except Exception as exc:
                # One competition failing must not cost the others; the whole
                # cycle is lost only when every one of them fails.
                log.error("board_fetch_failed", venue_league=vl, error=str(exc), exc_info=True)
                continue
            boards.append((vl, parsed_vl))
            for e in raw_vl.get("events", []):
                if isinstance(e, dict):
                    raw_events[str(e.get("slug"))] = e
        if not boards:
            return stats
        self._log_expected_vs_observed(venue_leagues, boards)

        events = [e for _vl, parsed in boards for e in parsed.events]
        with self._Session() as session:
            for event in events:
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
            # On the cycle line, not just on the counter: a fallback nobody
            # can see becoming the normal path is how the venue changes shape
            # without anyone noticing.
            game_id_from_fallback=stats.game_id_from_fallback,
            game_id_missing=stats.game_id_missing,
            duration_s=round(time.monotonic() - started, 2),
        )
        return stats

    def _log_expected_vs_observed(self, venue_leagues, boards) -> None:
        """What the venue's own listing SAYS, against what the sweep returned.

        An unknown or empty competition returns **200 with `events: []`**, never
        a 404, so a quiet board and a wrong slug are the same response. This is
        the only thing that tells them apart.

        `missing=(obs < exp)` USED TO BE THE VERDICT AND IT WAS NOT ONE.
        Measured on the saved listing 2026-09-14: `/v2/sports`'s
        `activeEventCount` and the events endpoint count DIFFERENT POPULATIONS
        for at least one league. MLB lists 87 and the events endpoint returns
        55, spanning only five days and not truncated — no pagination field, no
        round-number cap. Table tennis agrees exactly on every competition
        (8=8, 19=19, 69=69, 1=1). So `obs < exp` is a property of the league,
        not evidence of a gap, and a check that is red on every long-game
        league for most of every day is a check nobody reads.

        IT IS ALSO NOT ABOUT LIVE GAMES, which was the natural guess.
        `setkawoua` lists activeEventCount=1, the events endpoint returns that
        1 event, and that event is LIVE. Live events appear on BOTH sides and
        cancel; subtracting an in-progress count would subtract from one side a
        quantity present in both.

        So the pair is reported as numbers, and the only booleans left are the
        three that cannot be anything but a defect.
        """
        observed = {vl: len(parsed.events) for vl, parsed in boards}
        limit = self.config.event_limit
        try:
            listing = self._client.get_sports_listing()
        except Exception as exc:
            log.info("listing_unavailable", error=str(exc),
                     observed=observed, swept=len(venue_leagues))
            return
        for vl in venue_leagues:
            exp = listing.get(vl)
            obs = observed.get(vl)
            log.info(
                "board_coverage", venue_league=vl, expected=exp, observed=obs,
                shortfall=(exp - obs if exp is not None and obs is not None
                           else None),
                # The competition was not in the sweep at all.
                not_swept=(obs is None),
                # The listing says there are events and we got none: the
                # wrong-slug case this check was built for, and unambiguous.
                swept_nothing=(exp is not None and exp > 0 and obs == 0),
                # Exactly at the limit is the truncation signature — this is
                # what caught the default 50 recording a fifth of setkameua.
                # A real board landing exactly on the limit is possible and
                # rare; a truncated one always does.
                truncated=(obs is not None and obs == limit),
                # `truncated` compares a POST-filter count to a PRE-fetch limit,
                # so it reads False whenever the sweep fetched `limit` events and
                # dropped even one. On 2026-09-14 MLB logged observed=49 against
                # limit=50 and truncated=false, 32 events short of the listing:
                # the flag built to catch the default-50 truncation was silent in
                # exactly the case it exists for. Fixing the comparison needs the
                # pre-filter count, which this method does not have. Logging the
                # limit costs nothing and lets a reader see 49 against 50, which
                # is the fact the boolean was hiding.
                limit=limit,
            )

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
            "game_id": _event_key(event, stats),
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
                self._record_book(session, market.slug, snapshot_id, captured_at)
                stats.books_written += 1
            except Exception as exc:
                # Depth is valuable but optional; never lose the top-of-book
                # snapshot because the book call failed.
                stats.book_errors += 1
                log.warning("book_fetch_failed", market_slug=market.slug, error=str(exc))

    def _record_book(
        self, session: Session, market_slug: str, snapshot_id: int,
        captured_at: dt.datetime,
    ) -> None:
        """Depth for one snapshot, stamped with the cycle's own instant.

        On this path price and depth are fetched in the same cycle, so the
        snapshot's `captured_at` is the honest timestamp (the live recorder's
        split depth loop stamps its own). Stamped always since 2026-08-07: the
        partitioned local table routes on it and its PK forbids NULL.
        """
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
                        "captured_at": captured_at,
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
                markets_seen=stats.markets_seen,
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
