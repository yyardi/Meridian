"""ESPN team game-log fetcher.

Writes **immutable one-row-per-team-per-game** records. Each game produces two
rows, one from each team's perspective, with points_scored/points_allowed
oriented to that team.

There is deliberately no season-aggregate table. If "team PPG" were stored and
overwritten nightly, a backtest of a July 15 game would silently read
September's numbers — plausible-looking, worthless results. Storing per-game
rows forces every statistic to be derived `as_of` a date, which makes that bug
unwritable rather than merely discouraged. See docs/math/point-in-time.md.

Preseason is never written: exhibition rotations would corrupt both PPG and
win-loss record.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys

import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.config import SEASON_TYPE_PRESEASON
from core.feeds.espn_client import ESPNClient
from core.feeds.espn_schemas import Event, ScheduleResponse, ScoreboardResponse
from core.storage import TeamGameLog, get_engine, get_sessionmaker

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc


class StatsStats:
    """Counters for one run."""

    def __init__(self) -> None:
        self.teams = 0
        self.events_seen = 0
        self.rows_written = 0
        self.skipped_preseason = 0
        self.skipped_incomplete = 0
        self.skipped_malformed = 0
        self.errors = 0


class ESPNStatsFetcher:
    def __init__(self, client: ESPNClient | None = None, sessionmaker=None) -> None:
        self._client = client or ESPNClient()
        self._Session = sessionmaker or get_sessionmaker(get_engine())

    # ---------------------------------------------------------------- #
    # Discovery
    # ---------------------------------------------------------------- #

    def get_team_ids(self) -> list[str]:
        """Discover team IDs rather than hardcoding them.

        Franchises relocate, fold, and get added (Toronto and Golden State are
        recent). A hardcoded list silently goes stale.
        """
        payload = self._client.get_teams()
        ids: list[str] = []
        for sport in payload.get("sports", []):
            for league in sport.get("leagues", []):
                for entry in league.get("teams", []):
                    team = entry.get("team") or {}
                    if team.get("id"):
                        ids.append(str(team["id"]))
        return ids

    # ---------------------------------------------------------------- #
    # Row construction
    # ---------------------------------------------------------------- #

    @staticmethod
    def _rows_for_event(event: Event, season: int) -> list[dict]:
        """Two rows per game — one per team's perspective.

        Returns [] for anything that should not be persisted.
        """
        comp = event.competition
        if comp is None or not comp.is_completed:
            return []

        season_type = event.season_type_id
        if season_type is None or season_type == SEASON_TYPE_PRESEASON:
            return []

        if len(comp.competitors) != 2:
            return []
        if any(c.score is None for c in comp.competitors):
            return []

        game_date = event.date
        if game_date is None:
            return []

        rows: list[dict] = []
        for i, me in enumerate(comp.competitors):
            opp = comp.competitors[1 - i]
            rows.append(
                {
                    "game_date": game_date,
                    "season": season,
                    "espn_game_id": event.id,
                    "team_id": me.team.id,
                    "team_abbrev": me.team.abbreviation,
                    "opponent_id": opp.team.id,
                    "opponent_abbrev": opp.team.abbreviation,
                    "is_home": me.is_home,
                    "points_scored": me.score,
                    "points_allowed": opp.score,
                    "is_completed": True,
                    "season_type": season_type,
                }
            )
        return rows

    def _persist(self, rows: list[dict]) -> int:
        """Upsert on (espn_game_id, team_id). Reruns must change nothing."""
        if not rows:
            return 0
        written = 0
        with self._Session() as session:
            for row in rows:
                stmt = (
                    pg_insert(TeamGameLog)
                    .values(**row)
                    .on_conflict_do_nothing(constraint="uq_team_game")
                    .returning(TeamGameLog.id)
                )
                if session.execute(stmt).scalar() is not None:
                    written += 1
            session.commit()
        return written

    # ---------------------------------------------------------------- #
    # Entry points
    # ---------------------------------------------------------------- #

    def fetch_season(self, season: int, stats: StatsStats | None = None) -> StatsStats:
        stats = stats or StatsStats()
        try:
            team_ids = self.get_team_ids()
        except Exception as exc:
            log.error("team_discovery_failed", error=str(exc), exc_info=True)
            stats.errors += 1
            return stats

        for team_id in team_ids:
            try:
                payload = self._client.get_team_schedule(team_id, season)
                schedule = ScheduleResponse.model_validate(payload)
            except Exception as exc:
                # One unreachable team must not abort the season.
                stats.errors += 1
                log.error(
                    "team_schedule_failed", team_id=team_id, season=season, error=str(exc)
                )
                continue

            stats.teams += 1
            batch: list[dict] = []
            for event in schedule.events:
                stats.events_seen += 1
                if event.season_type_id == SEASON_TYPE_PRESEASON:
                    stats.skipped_preseason += 1
                    continue
                comp = event.competition
                if comp is None or not comp.is_completed:
                    stats.skipped_incomplete += 1
                    continue
                rows = self._rows_for_event(event, season)
                if not rows:
                    stats.skipped_malformed += 1
                    continue
                batch.extend(rows)

            stats.rows_written += self._persist(batch)

        log.info(
            "season_complete",
            season=season,
            teams=stats.teams,
            events_seen=stats.events_seen,
            rows_written=stats.rows_written,
            skipped_preseason=stats.skipped_preseason,
            skipped_incomplete=stats.skipped_incomplete,
            errors=stats.errors,
        )
        return stats

    def fetch_backfill(self, start: int, end: int) -> StatsStats:
        """Backfill a range of seasons.

        Each season gets its own counters so the per-season log line reports
        that season, not a running total — a cumulative number reads as though
        later seasons fetched far more than they did.
        """
        total = StatsStats()
        for season in range(start, end + 1):
            log.info("backfill_season_start", season=season)
            season_stats = self.fetch_season(season)
            total.teams += season_stats.teams
            total.events_seen += season_stats.events_seen
            total.rows_written += season_stats.rows_written
            total.skipped_preseason += season_stats.skipped_preseason
            total.skipped_incomplete += season_stats.skipped_incomplete
            total.skipped_malformed += season_stats.skipped_malformed
            total.errors += season_stats.errors

        log.info(
            "backfill_complete",
            seasons=f"{start}-{end}",
            rows_written=total.rows_written,
            skipped_preseason=total.skipped_preseason,
            errors=total.errors,
        )
        return total

    def fetch_date(self, date_yyyymmdd: str, season: int) -> StatsStats:
        """Daily incremental update from the scoreboard."""
        stats = StatsStats()
        try:
            payload = self._client.get_scoreboard(date_yyyymmdd)
            board = ScoreboardResponse.model_validate(payload)
        except Exception as exc:
            log.error("scoreboard_failed", date=date_yyyymmdd, error=str(exc))
            stats.errors += 1
            return stats

        batch: list[dict] = []
        for event in board.events:
            stats.events_seen += 1
            if event.season_type_id == SEASON_TYPE_PRESEASON:
                stats.skipped_preseason += 1
                continue
            rows = self._rows_for_event(event, season)
            if not rows:
                stats.skipped_incomplete += 1
                continue
            batch.extend(rows)

        stats.rows_written = self._persist(batch)
        log.info(
            "date_complete",
            date=date_yyyymmdd,
            events=stats.events_seen,
            rows_written=stats.rows_written,
        )
        return stats


def _configure_logging() -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(prog="espn-stats")
    parser.add_argument("--season", type=int, help="fetch a single season, e.g. 2026")
    parser.add_argument("--backfill", type=str, help="season range, e.g. 2020-2026")
    parser.add_argument("--date", type=str, help="single date YYYYMMDD (incremental)")
    args = parser.parse_args()

    _configure_logging()
    fetcher = ESPNStatsFetcher()

    if args.backfill:
        start_s, _, end_s = args.backfill.partition("-")
        fetcher.fetch_backfill(int(start_s), int(end_s))
    elif args.season:
        fetcher.fetch_season(args.season)
    elif args.date:
        season = int(args.date[:4])
        fetcher.fetch_date(args.date, season)
    else:
        parser.error("one of --season, --backfill or --date is required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
