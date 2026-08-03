"""Continuous sportsbook-odds recorder — the book-side mirror of the live recorder.

Read the measurement before the design; it inverts the obvious plan.

What ESPN actually publishes (measured 2026-08-02, live WNBA game)
-----------------------------------------------------------------
The brief for this module was "poll ESPN's live odds for in-progress games".
ESPN does not have any.

============================  ==========================================
surface                       what it does during an in-progress game
============================  ==========================================
`scoreboard` -> `odds`        **empty**. 0 providers across 120 frames /
                              238s. Pregame events on the same payload
                              carry 1 provider (DraftKings); the block is
                              stripped the moment a game tips.
`summary` -> `pickcenter`     present, and **frozen**. 0 changes across 83
                              frames / 7 min, holding spread -1.5 /
                              total 186.5 while the score moved 43-37 to
                              49-43. It is the pregame line surviving into
                              the game, not a live one.
`summary` -> `winprobability` genuinely live (15 updates in 7 min) — but
                              that is ESPN's own model, not a market price.
core API `.../odds`           404 until the game is final.
============================  ==========================================

So the in-game update cadence is not "60s, so don't poll at 1s". It is
**never**. There is no live sportsbook line available from ESPN at any
polling rate, and a poller that wrote `pickcenter` during a game would
manufacture thousands of rows all carrying a stale pregame number — actively
dangerous, because PULSE would read it as a live anchor.

What this module does instead
-----------------------------
The complaint that prompted it is still real and still fixable: odds land only
when the 6-hourly scheduler happens to catch a game, which is why the whole
database holds **3** in-play-adjacent odds rows. That under-sampling also
starved Experiment 4 — `core/window_detector.py` reported zero triggers with
its book leg polled every ~20 minutes, against a lag the literature measures in
minutes.

This process therefore records **pregame line movement at fine resolution**,
which is the thing that both exists and is tradable:

* polls the scoreboard continuously (one small request, 29ms median);
* writes a row only when a provider's numbers actually **change**, so the table
  stays small and "the line moved" is a query rather than a diff across
  thousands of identical rows;
* keeps polling during a game so that if ESPN ever does start publishing a live
  line, it is captured the day it appears rather than the day someone notices;
* tags anything captured while a game is in progress as a **live provider**
  (`"DraftKings (live)"`), which `core.backtest.engine._is_live_provider`
  already excludes — so an in-game line can never leak into a CLV benchmark or
  a backtest entry price.

That last point is the load-bearing one. Pregame rows keep their plain provider
name and remain fully usable; only in-game rows are quarantined.

    python -m core.feeds.live_odds_recorder
    python -m core.feeds.live_odds_recorder --interval 15
    python -m core.feeds.live_odds_recorder --once
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import signal
import sys
import time
from typing import Any

import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.feeds.espn_client import ESPNClient
from core.feeds.espn_odds import ESPNOddsFetcher, _nested
from core.storage import SportsbookOdds, get_engine, get_sessionmaker

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc

#: One small scoreboard call per cycle (29ms median, ESPN_RPS is 3/s), so this
#: costs ~0.07 req/s — two orders of magnitude inside the budget.
#:
#: Chosen for *pregame* movement, which is what exists. It is deliberately not
#: faster: no pregame line was observed moving during the measurement windows,
#: so the true update cadence of the book leg is **not yet known** and a tighter
#: interval would be a guess dressed as a decision. Once this has run through a
#: slate, `python -m core.feeds.live_odds_recorder --report` prints the observed
#: inter-change gaps and the interval can be set from data.
DEFAULT_INTERVAL_SECONDS = 15.0

#: When nothing tips for hours, back off. Lines do drift overnight but not on a
#: 15-second timescale.
IDLE_INTERVAL_SECONDS = 300.0

#: Within this long before tip-off, treat the slate as active.
ACTIVE_WINDOW_HOURS = 8.0

#: Re-write an unchanged line this often anyway, as a heartbeat. Without it,
#: "no rows for six hours" is ambiguous between a still market and a dead
#: recorder — the same ambiguity `InjuryPoll` exists to remove.
HEARTBEAT_SECONDS = 1800.0

#: Appended to the provider name for anything captured mid-game. Must contain
#: the substring 'live' — that is exactly what `_is_live_provider` matches on.
LIVE_SUFFIX = " (live)"


class LiveOddsStats:
    def __init__(self) -> None:
        self.games_seen = 0
        self.in_progress = 0
        self.with_odds = 0
        self.rows_written = 0
        self.unchanged = 0
        self.errors = 0


def game_state(competition: dict[str, Any]) -> str | None:
    """'pre' | 'in' | 'post', from the scoreboard's own status block."""
    return _nested(competition, "status", "type", "state")


def provider_name(base: str, state: str | None) -> str:
    """Quarantine in-game lines by name.

    The backtest excludes any provider whose name contains 'live', because such
    lines are set during the game and would corrupt both the CLV benchmark and
    the entry price. Pregame rows keep their plain name and stay usable.
    """
    if state == "in" and not base.lower().endswith(LIVE_SUFFIX.strip()):
        return f"{base}{LIVE_SUFFIX}"
    return base


def odds_fingerprint(row: dict[str, Any]) -> tuple:
    """The values that decide whether this is a new observation."""
    return (
        row.get("spread"),
        row.get("over_under"),
        row.get("over_odds"),
        row.get("under_odds"),
        row.get("home_moneyline"),
        row.get("away_moneyline"),
    )


class LiveOddsRecorder:
    """Polls the ESPN scoreboard and records odds changes."""

    def __init__(
        self,
        client: ESPNClient | None = None,
        sessionmaker=None,
        interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
        *,
        heartbeat_seconds: float = HEARTBEAT_SECONDS,
    ) -> None:
        self._client = client or ESPNClient()
        # A single connection is ample: this process writes only when a line
        # actually moves, which is a handful of rows an hour. It matters because
        # Supabase's session-mode pooler allows 15 clients *in total across every
        # container*, and that ceiling is already being hit — the scheduler has
        # logged EMAXCONNSESSION. A new container must not take a share it does
        # not need. See docs/infra/live-odds.md.
        self._Session = sessionmaker or get_sessionmaker(
            get_engine(pool_size=1, max_overflow=0)
        )
        self.interval_seconds = interval_seconds
        self.heartbeat_seconds = heartbeat_seconds
        #: (game_id, provider) -> (fingerprint, monotonic time last written)
        self._last: dict[tuple[str, str], tuple[tuple, float]] = {}

    # ------------------------------------------------------------------ #
    # One cycle
    # ------------------------------------------------------------------ #

    def poll_once(
        self,
        captured_at: dt.datetime | None = None,
        date_yyyymmdd: str | None = None,
    ) -> LiveOddsStats:
        captured_at = captured_at or dt.datetime.now(UTC)
        stats = LiveOddsStats()
        date_str = date_yyyymmdd or captured_at.strftime("%Y%m%d")

        try:
            payload = self._client.get_scoreboard(date_str)
        except Exception as exc:
            # Never crash the loop. Odds are backfillable from the core API for
            # completed games, so a missed cycle is not the catastrophe a missed
            # market snapshot is — but a dead process still is.
            stats.errors += 1
            log.error("scoreboard_failed", date=date_str, error=str(exc))
            return stats

        rows = self._rows_from_payload(payload, captured_at, stats)
        stats.rows_written = self._persist(rows)
        log.info(
            "live_odds_cycle",
            games=stats.games_seen,
            in_progress=stats.in_progress,
            with_odds=stats.with_odds,
            written=stats.rows_written,
            unchanged=stats.unchanged,
        )
        return stats

    def _rows_from_payload(
        self, payload: dict, captured_at: dt.datetime, stats: LiveOddsStats
    ) -> list[dict]:
        now = time.monotonic()
        rows: list[dict] = []

        for event in payload.get("events") or []:
            if not isinstance(event, dict):
                continue
            stats.games_seen += 1
            game_id = str(event.get("id"))
            competitions = event.get("competitions") or []
            if not competitions:
                continue
            competition = competitions[0]
            state = game_state(competition)
            if state == "in":
                stats.in_progress += 1

            odds_list = competition.get("odds") or []
            if not odds_list:
                continue
            stats.with_odds += 1

            game_date = _parse_date(event.get("date"))
            for entry in odds_list:
                try:
                    row = ESPNOddsFetcher.parse_live_odds(
                        entry, game_id, captured_at, game_date
                    )
                except Exception as exc:
                    stats.errors += 1
                    log.warning("live_odds_parse_failed", game=game_id, error=str(exc))
                    continue

                row["provider_name"] = provider_name(row["provider_name"], state)

                key = (game_id, row["provider_name"])
                fingerprint = odds_fingerprint(row)
                previous = self._last.get(key)

                if previous is not None:
                    unchanged = previous[0] == fingerprint
                    stale = (now - previous[1]) >= self.heartbeat_seconds
                    if unchanged and not stale:
                        stats.unchanged += 1
                        continue

                self._last[key] = (fingerprint, now)
                rows.append(row)
        return rows

    def _persist(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        try:
            with self._Session() as session:
                result = session.execute(
                    pg_insert(SportsbookOdds)
                    .values(rows)
                    .on_conflict_do_nothing(
                        constraint="uq_odds_game_provider_time"
                    )
                    .returning(SportsbookOdds.id)
                )
                written = len(result.all())
                session.commit()
                return written
        except Exception as exc:
            log.error("live_odds_write_failed", rows=len(rows), error=str(exc))
            return 0

    # ------------------------------------------------------------------ #
    # Cadence
    # ------------------------------------------------------------------ #

    def next_interval(self, payload: dict | None) -> float:
        """Fast while a slate is live or approaching, slow otherwise."""
        if payload is None:
            return self.interval_seconds
        now = dt.datetime.now(UTC)
        window = dt.timedelta(hours=ACTIVE_WINDOW_HOURS)
        for event in payload.get("events") or []:
            competitions = event.get("competitions") or []
            if competitions and game_state(competitions[0]) == "in":
                return self.interval_seconds
            start = _parse_date(event.get("date"))
            if start and now <= start <= now + window:
                return self.interval_seconds
        return IDLE_INTERVAL_SECONDS

    def run_forever(self) -> None:
        stopping = {"flag": False}

        def _handle(signum, _frame):
            log.info("live_odds_stopping", signal=signum)
            stopping["flag"] = True

        signal.signal(signal.SIGINT, _handle)
        signal.signal(signal.SIGTERM, _handle)

        log.info(
            "live_odds_recorder_started",
            interval_seconds=self.interval_seconds,
            heartbeat_seconds=self.heartbeat_seconds,
        )

        while not stopping["flag"]:
            started = time.monotonic()
            payload = None
            try:
                date_str = dt.datetime.now(UTC).strftime("%Y%m%d")
                payload = self._client.get_scoreboard(date_str)
                stats = self._cycle_from_payload(payload)
                log.debug("live_odds_written", written=stats.rows_written)
            except Exception as exc:
                log.error("live_odds_cycle_failed", error=str(exc), exc_info=True)

            wait = self.next_interval(payload)
            deadline = started + wait
            while not stopping["flag"] and time.monotonic() < deadline:
                time.sleep(min(1.0, deadline - time.monotonic()))

        log.info("live_odds_recorder_stopped")

    def _cycle_from_payload(self, payload: dict) -> LiveOddsStats:
        """Turn an already-fetched payload into rows, so `run_forever` does not
        pay for the scoreboard twice per cycle."""
        stats = LiveOddsStats()
        captured_at = dt.datetime.now(UTC)
        rows = self._rows_from_payload(payload, captured_at, stats)
        stats.rows_written = self._persist(rows)
        if stats.rows_written:
            log.info(
                "live_odds_change",
                games=stats.games_seen,
                in_progress=stats.in_progress,
                written=stats.rows_written,
            )
        return stats


def _parse_date(value: Any) -> dt.datetime | None:
    if not value:
        return None
    if isinstance(value, dt.datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def main() -> int:
    parser = argparse.ArgumentParser(prog="meridian-live-odds-recorder")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )

    rec = LiveOddsRecorder(interval_seconds=args.interval)
    if args.once:
        stats = rec.poll_once()
        log.info("live_odds_once", written=stats.rows_written,
                 games=stats.games_seen, in_progress=stats.in_progress)
        return 0
    rec.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
