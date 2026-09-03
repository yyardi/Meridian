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
    LEAGUE_CFB,
    LEAGUE_SERIES,
    SERIES_MONEYLINE_NCAAF,
    SERIES_MONEYLINE,
    SERIES_SPREAD,
    SERIES_TO_LEAGUE,
    SERIES_TO_MARKET_TYPE,
    SERIES_TOTAL,
    ParsedGameKey,
    codes_from_sub_title,
    game_key_from_event_ticker,
    local_date_from_game_key,
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
POLLED_SERIES = (LEAGUE_SERIES["wnba"] + LEAGUE_SERIES["nfl"]
                 + LEAGUE_SERIES[LEAGUE_CFB])

#: How far ahead a game may be and still get its venue occurrence stamp
#: fetched. Leagues we do not quote have no Polymarket link, so their poll
#: window depends on this; 3 days covers a Thu-through-Sat slate discovered
#: on any weekday.
VENUE_OCCURRENCE_HORIZON_DAYS = 3

#: Kalshi's `occurrence_datetime` minus the real kickoff, MEASURED
#: 2026-09-03 on both boards: college MASS/RUTG (ESPN 22:00Z, venue
#: 01:00Z) and NFL NE/SEA (ESPN 00:20Z, venue 03:20Z) — +3h in both. The
#: venue publishes no tip time, so a league without a Polymarket link has
#: its window derived from this stamp with the offset applied EXPLICITLY
#: rather than by pretending the stamp is a kickoff.
VENUE_OCCURRENCE_AFTER_TIP = dt.timedelta(hours=3)

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


class KalshiStats:  # noqa: D101 — counters, named at their use sites
    """Per-cycle counters, for logging and the health check."""

    def __init__(self) -> None:
        self.games_polled = 0
        self.snapshots_written = 0
        self.contracts_written = 0
        self.games_discovered = 0
        self.games_matched = 0
        self.errors = 0
        #: Pairing provenance. sub_title is the venue's own statement of
        #: which two teams a game key means; the split is our inference.
        self.pairs_from_sub_title = 0
        self.pairs_from_split = 0
        #: LOUD failures. A mismatch means the venue contradicted itself or
        #: our split disagreed with the venue — never silently resolved.
        self.pair_mismatches = 0
        self.games_unparsed = 0
        #: Requested-vs-returned, so a throttled cycle reads as a SHORTFALL
        #: rather than as a quiet venue (rule 22).
        self.events_requested = 0
        self.events_returned = 0
        self.markets_returned = 0
        self.start_times_set = 0


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
        #: Cycles whose own duration exceeded their interval. Counted for
        #: the life of the process because a single overrun is noise and a
        #: rising count is the slate outgrowing the cadence.
        self._cycle_overruns = 0

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
            # Provenance and shortfall counters, printed every cycle so a
            # zero is never bare: pairs_* say HOW each game key was read,
            # events_requested vs events_returned exposes throttling, and
            # any mismatch/unparsed is a loud number rather than silence.
            pairs_sub_title=stats.pairs_from_sub_title,
            pairs_split=stats.pairs_from_split,
            pair_mismatches=stats.pair_mismatches,
            games_unparsed=stats.games_unparsed,
            events_requested=stats.events_requested,
            events_returned=stats.events_returned,
            markets_returned=stats.markets_returned,
            start_times_set=stats.start_times_set,
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
                parsed = self._resolve_pair(league, key, event, stats)
                if parsed is None:
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
            self._fill_venue_occurrence(session, stats, captured_at)
            session.commit()

    def _resolve_pair(
        self, league: str, key: str, event: dict[str, Any], stats: KalshiStats
    ) -> ParsedGameKey | None:
        """Which two teams a game key means — venue first, inference second.

        College tickers concatenate 130+ variable-length codes with no
        delimiter, so a SPLIT IS A GUESS and a wrong guess yields a
        confident row for a game that never existed — the failure no
        drop-counter can see. The event payload states both codes in its
        `sub_title` ("KCU vs MORE (Sep 3)"), so that is the authority and
        the split is only a cross-check. Every disagreement is counted and
        logged at error level; none is silently resolved.
        """
        split = parse_game_key(key, league)
        truth = codes_from_sub_title(event.get("sub_title"))
        if truth is not None:
            first, second = truth
            teams = key[7:]
            if first + second != teams:
                # The venue contradicting itself: refuse rather than pick.
                stats.pair_mismatches += 1
                log.error(
                    "kalshi_sub_title_disagrees_with_ticker",
                    game_key=key, league=league,
                    sub_title=event.get("sub_title"),
                    codes=f"{first}+{second}", ticker_teams=teams,
                )
                return None
            local_date = local_date_from_game_key(key)
            if local_date is None:
                stats.games_unparsed += 1
                log.warning("kalshi_game_key_bad_date", game_key=key,
                            league=league)
                return None
            if split is not None and (
                split.first_code, split.second_code
            ) != (first, second):
                # Ground truth wins, but a split that would have been wrong
                # is exactly the silent mis-pairing we are guarding against.
                stats.pair_mismatches += 1
                log.error(
                    "kalshi_split_disagrees_with_sub_title",
                    game_key=key, league=league,
                    venue=f"{first}+{second}",
                    split=f"{split.first_code}+{split.second_code}",
                )
            stats.pairs_from_sub_title += 1
            return ParsedGameKey(
                game_key=key, local_date=local_date, first_code=first,
                second_code=second, league=league,
            )
        if split is not None:
            stats.pairs_from_split += 1
            return split
        # All-star exhibitions ('26JUL25SPNCOO') and anything else that is
        # not a franchise game. Counted and named, never silently skipped.
        stats.games_unparsed += 1
        log.warning("kalshi_game_key_unparsed", game_key=key, league=league,
                    sub_title=event.get("sub_title"))
        return None

    def _fill_venue_occurrence(
        self, session: Session, stats: KalshiStats, now: dt.datetime
    ) -> None:
        """Record the venue's own clock for leagues we do not quote.

        `game_start_time` is populated only by the Polymarket link, and a
        college game has no Polymarket slug — so without this every college
        game would sit unpollable forever while the log said a cheerful
        zero (rule 22's exact shape). What the venue gives is
        `occurrence_datetime`, which is NOT a kickoff: measured at
        kickoff + 3h on both boards. It is stored under its own name and
        the window arithmetic applies the offset in the open.
        """
        horizon = now + dt.timedelta(days=VENUE_OCCURRENCE_HORIZON_DAYS)
        games = session.scalars(
            select(KalshiGame).where(
                KalshiGame.league == LEAGUE_CFB,
                KalshiGame.venue_occurrence_time.is_(None),
                KalshiGame.local_date >= now - dt.timedelta(days=1),
                KalshiGame.local_date <= horizon,
            )
        ).all()
        for game in games:
            event_ticker = f"{SERIES_MONEYLINE_NCAAF}-{game.game_key}"
            try:
                markets = self._client.get_markets(event_ticker)
            except Exception as exc:
                stats.errors += 1
                log.error("kalshi_start_time_fetch_failed",
                          event_ticker=event_ticker, error=str(exc))
                continue
            stamps = [
                _parse_ts(m.get("occurrence_datetime")) for m in markets
            ]
            stamps = [s for s in stamps if s is not None]
            if not stamps:
                continue
            game.venue_occurrence_time = min(stamps)
            stats.start_times_set += 1

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
        by_tip = select(KalshiGame).where(
            KalshiGame.game_start_time.is_not(None),
            KalshiGame.game_start_time > now,
            KalshiGame.game_start_time <= now + window,
        )
        # Leagues we do not quote have no tip time at all; their window is
        # derived from the venue's occurrence stamp with the measured +3h
        # offset applied explicitly. Equivalent to [tip - window, tip + 3h),
        # so it also spans the game itself — a consequence of the only clock
        # the venue publishes, stated rather than hidden.
        by_occurrence = select(KalshiGame).where(
            KalshiGame.game_start_time.is_(None),
            KalshiGame.venue_occurrence_time.is_not(None),
            KalshiGame.venue_occurrence_time > now,
            KalshiGame.venue_occurrence_time
            <= now + window + VENUE_OCCURRENCE_AFTER_TIP,
        )
        return list(session.scalars(by_tip)) + list(
            session.scalars(by_occurrence))

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
        # Requested-vs-returned accounting (rule 22): a throttled or
        # empty fetch must read as a SHORTFALL, not as a quiet venue.
        stats.events_requested += 1
        markets = self._client.get_markets(event_ticker)
        stats.events_returned += 1
        stats.markets_returned += len(markets)
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
            cycle_seconds = time.monotonic() - started
            # Every cycle, whatever the cycle did (B11).
            self._heartbeat.beat(
                interval_seconds=interval,
                rows_written=stats.snapshots_written,
                cycle_seconds=cycle_seconds,
            )
            # The interval is a SLEEP, not a period: nothing stacks and
            # nothing is skipped, but the real sampling cadence is
            # (cycle + interval) and it stretches silently as the slate
            # grows. Print it every cycle, and count the case where the
            # cycle alone outran its own interval — otherwise a recorder
            # sampling every 3 minutes looks exactly like one sampling
            # every 2 (rule 22: the degradation must be visible AS
            # degradation).
            effective_period = cycle_seconds + interval
            if cycle_seconds > interval:
                self._cycle_overruns += 1
                log.warning(
                    "kalshi_cycle_overran_interval",
                    cycle_seconds=round(cycle_seconds, 1),
                    interval_seconds=interval,
                    effective_period_seconds=round(effective_period, 1),
                    overruns_total=self._cycle_overruns,
                    games_polled=stats.games_polled,
                    events_requested=stats.events_requested,
                )
            log.info("sleeping", seconds=interval,
                     cycle_seconds=round(cycle_seconds, 1),
                     effective_period_seconds=round(effective_period, 1),
                     cycle_overruns_total=self._cycle_overruns)
            waited = 0
            while waited < interval and not stopping["flag"]:
                time.sleep(min(5, interval - waited))
                waited += 5
        log.info("kalshi_recorder_stopped")
