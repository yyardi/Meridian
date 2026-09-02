"""Kalshi WNBA snapshot recorder — the second venue, pregame only.

Purpose, pre-registered before any data was seen: the venue-gap thesis
(findings Q1) is measured against the ESPN sportsbook opening line, which
cannot be transacted. Kalshi is a second CFTC-regulated venue quoting the same
games; recording it alongside Polymarket turns "is Polymarket mispriced?" into
a same-minute comparison of two transactable prices. The conclusion gate lives
in :mod:`core.kalshi.analysis` — this module only writes rows.

Inherits the Polymarket recorder's discipline, for the same reasons:

* **Never crash the loop.** Failures are caught at the narrowest scope that
  still allows progress: one bad game must not lose the slate.
* **Idempotent by construction.** Snapshots are append-only, keyed
  ``(ticker, captured_at)``, inserted ON CONFLICT DO NOTHING.
* **Terms verbatim, prices slim.** Each contract's line and settlement rules
  are kept point-in-time in ``kalshi_contracts`` (written on change); the
  per-minute snapshot rows carry prices only. See docs/infra/supabase-quota.md
  for why the split matters.

Three cycles kinds, cheapest first:

1. **Idle** — no game inside the pregame window. Database-only; zero requests
   to Kalshi.
2. **Discovery** (every ``discovery_interval_seconds``) — page the three
   full-game series' open events, upsert ``kalshi_games`` rows, then link them
   to Polymarket games recorded in ``market_snapshots``. A game only gets a
   ``game_start_time`` from that link, and only games with a start time are
   ever polled — so "games we also record on Polymarket" is structural.
3. **Polling** (60s, from ``pregame_window_hours`` before tip until tip) —
   one ``/markets?event_ticker=`` request per series per game (3 per game per
   cycle) captures top-of-book, last price, sizes, and rules for every
   contract in the event.
"""

from __future__ import annotations

import datetime as dt
import signal
import time
from decimal import Decimal, InvalidOperation
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from core.config import KALSHI, KalshiConfig
from core.heartbeat import SERVICE_KALSHI, Heartbeat
from core.kalshi.client import KalshiPublicClient
from core.kalshi.mapping import (
    LEAGUE_SERIES,
    SERIES_MONEYLINE,
    SERIES_SPREAD,
    SERIES_TO_LEAGUE,
    SERIES_TO_MARKET_TYPE,
    SERIES_TOTAL,
    ParsedGameKey,
    game_key_from_event_ticker,
    parse_game_key,
)
from core.storage import (
    KalshiContract,
    KalshiGame,
    KalshiSnapshot,
    MarketSnapshot,
    get_engine,
    get_sessionmaker,
)
from core.team_mapping import UnknownTeamError, parse_event_slug

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc

#: Every series the recorder discovers and polls, both leagues. Per-game
#: polling uses the game's OWN league's three series (a game key is only
#: meaningful inside its league). Sunday worst case, stated arithmetic:
#: ~13 NFL games + ~4 WNBA games in the 6h pregame window x 3 series
#: = ~51 requests per 60s cycle = 0.85 req/s sustained against the 5/s
#: bucket (burst drains in ~10s); discovery adds 6 requests per 6h.
POLLED_SERIES = LEAGUE_SERIES["wnba"] + LEAGUE_SERIES["nfl"]

#: Fields whose change means "the contract's terms changed" and earns a new
#: kalshi_contracts row. Prices are deliberately absent.
_TERMS_FIELDS = (
    "yes_sub_title",
    "floor_strike",
    "cap_strike",
    "strike_type",
    "rules_primary",
    "rules_secondary",
    "close_time",
    "expected_expiration_time",
)


def _parse_ts(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _dec(value: Any) -> Decimal | None:
    """Kalshi serves prices/sizes as decimal strings ('0.3300'); keep them exact."""
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _terms_fingerprint(market: dict[str, Any]) -> tuple:
    return tuple(str(market.get(f)) for f in (
        "yes_sub_title", "floor_strike", "cap_strike", "strike_type",
        "rules_primary", "rules_secondary", "close_time", "expected_expiration_time",
    ))


def _stored_fingerprint(row: KalshiContract) -> tuple:
    def _fmt(v: Any) -> str:
        if isinstance(v, dt.datetime):
            return v.astimezone(UTC).isoformat().replace("+00:00", "Z")
        if isinstance(v, Decimal):
            # Kalshi serves strikes as JSON numbers (15.5); Decimal('15.50')
            # must fingerprint back to '15.5'.
            return str(v.normalize())
        return str(v)
    return tuple(_fmt(getattr(row, f)) for f in _TERMS_FIELDS)


class KalshiStats:
    """Per-cycle counters, for logging and the health check."""

    def __init__(self) -> None:
        self.games_polled = 0
        self.snapshots_written = 0
        self.contracts_written = 0
        self.games_discovered = 0
        self.games_matched = 0
        self.errors = 0


class KalshiRecorder:
    def __init__(
        self,
        config: KalshiConfig | None = None,
        client: KalshiPublicClient | None = None,
        sessionmaker=None,
    ) -> None:
        self.config = config or KALSHI
        self._client = client or KalshiPublicClient(self.config)
        self._Session = sessionmaker or get_sessionmaker(get_engine())
        self._heartbeat = Heartbeat(self._Session, SERVICE_KALSHI)
        self._last_discovery: float | None = None
        #: ticker -> terms fingerprint of the latest kalshi_contracts row.
        self._terms_cache: dict[str, tuple] = {}

    # ------------------------------------------------------------------ #
    # One cycle
    # ------------------------------------------------------------------ #

    def run_once(self, captured_at: dt.datetime | None = None) -> KalshiStats:
        """Discovery if due, then poll every game inside the pregame window.

        All rows in a cycle share `captured_at` — a snapshot is a coherent
        instant, not a smear across the fetch duration.
        """
        captured_at = captured_at or dt.datetime.now(UTC)
        stats = KalshiStats()
        started = time.monotonic()

        if self._discovery_due():
            try:
                self._discover(captured_at, stats)
                self._last_discovery = time.monotonic()
            except Exception as exc:
                # Discovery failing must not stop polling of already-known
                # games; retry next cycle.
                stats.errors += 1
                log.error("kalshi_discovery_failed", error=str(exc), exc_info=True)

        with self._Session() as session:
            for game in self._pollable_games(session, captured_at):
                stats.games_polled += 1
                for series in LEAGUE_SERIES[game.league]:
                    event_ticker = f"{series}-{game.game_key}"
                    try:
                        self._record_event(
                            session=session,
                            series=series,
                            event_ticker=event_ticker,
                            game_key=game.game_key,
                            captured_at=captured_at,
                            stats=stats,
                        )
                    except Exception as exc:
                        # Narrow scope: one series of one game, not the slate.
                        stats.errors += 1
                        session.rollback()
                        log.error(
                            "kalshi_event_record_failed",
                            event_ticker=event_ticker,
                            error=str(exc),
                            exc_info=True,
                        )
            session.commit()

        log.info(
            "kalshi_cycle_complete",
            captured_at=captured_at.isoformat(),
            games_polled=stats.games_polled,
            snapshots=stats.snapshots_written,
            contracts=stats.contracts_written,
            discovered=stats.games_discovered,
            matched=stats.games_matched,
            errors=stats.errors,
            duration_s=round(time.monotonic() - started, 2),
        )
        return stats

    def _discovery_due(self) -> bool:
        if self._last_discovery is None:
            return True
        return time.monotonic() - self._last_discovery >= self.config.discovery_interval_seconds

    # ------------------------------------------------------------------ #
    # Discovery: series events -> kalshi_games -> Polymarket link
    # ------------------------------------------------------------------ #

    def _discover(self, captured_at: dt.datetime, stats: KalshiStats) -> None:
        """Upsert one kalshi_games row per open game, then link to Polymarket."""
        seen: dict[tuple[str, str], dict[str, Any]] = {}
        # The moneyline series alone names every game, but spread/total events
        # can in principle open on a different schedule; union all three.
        # Keyed by (league, game_key): shared team codes make the key alone
        # league-ambiguous (the SEA/ATL Sunday collision).
        for series in POLLED_SERIES:
            league = SERIES_TO_LEAGUE[series]
            for event in self._client.iter_events(series, status="open"):
                key = game_key_from_event_ticker(str(event.get("event_ticker") or ""))
                if key and (league, key) not in seen:
                    seen[(league, key)] = event

        with self._Session() as session:
            for (league, key), event in seen.items():
                parsed = parse_game_key(key, league)
                if parsed is None:
                    # All-star exhibitions ('26JUL25SPNCOO') and anything else
                    # that is not a franchise game. Not an error.
                    log.debug("kalshi_game_key_unparsed", game_key=key)
                    continue
                values = {
                    "game_key": parsed.game_key,
                    "league": parsed.league,
                    "local_date": dt.datetime.combine(
                        parsed.local_date, dt.time.min, tzinfo=UTC
                    ),
                    "first_code": parsed.first_code,
                    "second_code": parsed.second_code,
                    "first_espn": self._espn_or_none(parsed, "first"),
                    "second_espn": self._espn_or_none(parsed, "second"),
                    "title": event.get("title"),
                    "first_seen_at": captured_at,
                }
                inserted = session.execute(
                    pg_insert(KalshiGame)
                    .values(**values)
                    .on_conflict_do_nothing(
                        index_elements=["league", "game_key"])
                    .returning(KalshiGame.id)
                ).scalar()
                if inserted is not None:
                    stats.games_discovered += 1
            session.commit()
            self._link_polymarket(session, stats)
            session.commit()

    @staticmethod
    def _espn_or_none(parsed: ParsedGameKey, which: str) -> str | None:
        try:
            return parsed.first_espn if which == "first" else parsed.second_espn
        except UnknownTeamError:
            return None

    def _link_polymarket(self, session: Session, stats: KalshiStats) -> None:
        """Attach polymarket_event_slug + game_start_time to unmatched games.

        The index is built from our own market_snapshots — the same database
        this recorder writes to — keyed by (unordered ESPN pair, slug local
        date). Kalshi ticker dates and Polymarket slug dates are both US-local
        game dates, so they agree directly; ±1 day is tried anyway because a
        postponement can move one venue's label before the other's.
        """
        rows = session.execute(
            select(
                MarketSnapshot.event_slug,
                func.max(MarketSnapshot.game_start_time),
            )
            .where(MarketSnapshot.event_slug.is_not(None))
            .where(MarketSnapshot.game_start_time.is_not(None))
            .where(
                MarketSnapshot.game_start_time
                >= dt.datetime.now(UTC) - dt.timedelta(hours=36)
            )
            .group_by(MarketSnapshot.event_slug)
        ).all()

        index: dict[tuple[frozenset[str], dt.date], tuple[str, dt.datetime]] = {}
        for slug, start in rows:
            parsed = parse_event_slug(slug)
            if parsed is None:
                continue
            try:
                pair = parsed.espn_pair
            except UnknownTeamError:
                continue
            index[(pair, parsed.local_date)] = (slug, start)

        unmatched = session.scalars(
            select(KalshiGame).where(
                KalshiGame.polymarket_event_slug.is_(None),
                KalshiGame.first_espn.is_not(None),
                KalshiGame.second_espn.is_not(None),
            )
        ).all()
        for game in unmatched:
            pair = frozenset({game.first_espn, game.second_espn})
            local_date = game.local_date.date()
            for offset in (0, 1, -1):
                hit = index.get((pair, local_date + dt.timedelta(days=offset)))
                if hit is not None:
                    game.polymarket_event_slug, game.game_start_time = hit
                    stats.games_matched += 1
                    break

    # ------------------------------------------------------------------ #
    # Polling
    # ------------------------------------------------------------------ #

    def _pollable_games(
        self, session: Session, now: dt.datetime
    ) -> list[KalshiGame]:
        """Games inside [tip - pregame_window, tip). Pregame only, by scope:
        the comparison is pre-registered on pregame prices, and in-game 60s
        sampling would be quota spend with no registered question attached."""
        window = dt.timedelta(hours=self.config.pregame_window_hours)
        return list(
            session.scalars(
                select(KalshiGame).where(
                    KalshiGame.game_start_time.is_not(None),
                    KalshiGame.game_start_time > now,
                    KalshiGame.game_start_time <= now + window,
                )
            )
        )

    def _record_event(
        self,
        *,
        session: Session,
        series: str,
        event_ticker: str,
        game_key: str,
        captured_at: dt.datetime,
        stats: KalshiStats,
    ) -> None:
        markets = self._client.get_markets(event_ticker)
        market_type = SERIES_TO_MARKET_TYPE[series]
        for market in markets:
            ticker = str(market.get("ticker") or "")
            if not ticker:
                continue
            self._record_contract_terms(
                session=session,
                market=market,
                ticker=ticker,
                event_ticker=event_ticker,
                series=series,
                game_key=game_key,
                market_type=market_type,
                captured_at=captured_at,
                stats=stats,
            )
            values = {
                "captured_at": captured_at,
                "ticker": ticker,
                "event_ticker": event_ticker,
                "series_ticker": series,
                "game_key": game_key,
                "market_type": market_type,
                "floor_strike": _dec(market.get("floor_strike")),
                "yes_bid": _dec(market.get("yes_bid_dollars")),
                "yes_ask": _dec(market.get("yes_ask_dollars")),
                "last_price": _dec(market.get("last_price_dollars")),
                "yes_bid_size": _dec(market.get("yes_bid_size_fp")),
                "yes_ask_size": _dec(market.get("yes_ask_size_fp")),
                "volume": _dec(market.get("volume_fp")),
                "open_interest": _dec(market.get("open_interest_fp")),
                "status": market.get("status"),
                "result": market.get("result"),
                "raw": market if self.config.snapshot_raw else None,
            }
            written = session.execute(
                pg_insert(KalshiSnapshot)
                .values(**values)
                .on_conflict_do_nothing(constraint="uq_kalshi_snapshot_ticker_time")
                .returning(KalshiSnapshot.id)
            ).scalar()
            if written is not None:
                stats.snapshots_written += 1

    def _record_contract_terms(
        self,
        *,
        session: Session,
        market: dict[str, Any],
        ticker: str,
        event_ticker: str,
        series: str,
        game_key: str,
        market_type: str,
        captured_at: dt.datetime,
        stats: KalshiStats,
    ) -> None:
        """Write a kalshi_contracts row iff the terms changed (or are new).

        The cache is warmed from the database on first sight of a ticker, so a
        process restart does not re-write an unchanged contract.
        """
        fp = _terms_fingerprint(market)
        if ticker not in self._terms_cache:
            latest = session.scalars(
                select(KalshiContract)
                .where(KalshiContract.ticker == ticker)
                .order_by(KalshiContract.captured_at.desc())
                .limit(1)
            ).first()
            if latest is not None:
                self._terms_cache[ticker] = _stored_fingerprint(latest)
        if self._terms_cache.get(ticker) == fp:
            return

        session.execute(
            pg_insert(KalshiContract)
            .values(
                captured_at=captured_at,
                ticker=ticker,
                event_ticker=event_ticker,
                series_ticker=series,
                game_key=game_key,
                market_type=market_type,
                yes_sub_title=market.get("yes_sub_title"),
                floor_strike=_dec(market.get("floor_strike")),
                cap_strike=_dec(market.get("cap_strike")),
                strike_type=market.get("strike_type"),
                rules_primary=market.get("rules_primary"),
                rules_secondary=market.get("rules_secondary"),
                open_time=_parse_ts(market.get("open_time")),
                close_time=_parse_ts(market.get("close_time")),
                expected_expiration_time=_parse_ts(market.get("expected_expiration_time")),
                raw=market,
            )
            .on_conflict_do_nothing(constraint="uq_kalshi_contract_ticker_time")
        )
        self._terms_cache[ticker] = fp
        stats.contracts_written += 1

    # ------------------------------------------------------------------ #
    # Cadence
    # ------------------------------------------------------------------ #

    def next_interval_seconds(self, now: dt.datetime | None = None) -> int:
        """60s while any game sits in the pregame window, else the idle check.

        Decided from the local database only — an idle recorder costs Kalshi
        nothing.
        """
        now = now or dt.datetime.now(UTC)
        with self._Session() as session:
            if self._pollable_games(session, now):
                return self.config.poll_interval_seconds
        return self.config.idle_interval_seconds

    def run_forever(self) -> None:
        """Poll on the adaptive cadence until signalled to stop."""
        stopping = {"flag": False}

        def _handle(signum, _frame):
            log.info("shutdown_signal", signal=signum)
            stopping["flag"] = True

        signal.signal(signal.SIGINT, _handle)
        signal.signal(signal.SIGTERM, _handle)

        log.info("kalshi_recorder_started", base_url=self.config.base_url)
        while not stopping["flag"]:
            started = time.monotonic()
            stats = KalshiStats()
            try:
                stats = self.run_once()
            except Exception as exc:
                # Absolute backstop. Nothing gets to kill this loop.
                log.error("kalshi_cycle_failed", error=str(exc), exc_info=True)

            interval = self.next_interval_seconds()
            # Every cycle, whatever the cycle did (B11).
            self._heartbeat.beat(
                interval_seconds=interval,
                rows_written=stats.snapshots_written,
                cycle_seconds=time.monotonic() - started,
            )
            log.info("sleeping", seconds=interval)
            waited = 0
            while waited < interval and not stopping["flag"]:
                time.sleep(min(5, interval - waited))
                waited += 5
        log.info("kalshi_recorder_stopped")
