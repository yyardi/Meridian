"""Backfill player-level participation onto `player_game_logs`.

Same ESPN summary call that already supplies team box scores also carries
`boxscore.players[]` — every dressed player, her minutes, points, plus/minus,
and whether she was a starter or a DNP. That is the raw material for asking
"who actually played?", which is the retrospective half of the availability
work.

**What this data can and cannot be used for.** It is knowable only after
tip-off, so it may never feed a tradable model. Its job is to *screen* the
hypothesis: if a model that knows the true lineup with hindsight cannot beat
the incumbent, one that guesses the lineup from an injury report certainly
cannot, and the whole line of work dies for the cost of one backfill rather
than a season of waiting. See docs/math/availability.md.

Idempotent: games that already have player rows are skipped.

    python -m core.feeds.espn_player_boxscores --start 2024 --end 2026
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys

import structlog
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from core.feeds.espn_client import ESPNClient, ESPNNotFound
from core.storage import PlayerGameLog, TeamGameLog, get_engine, get_sessionmaker

log = structlog.get_logger(__name__)

SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/summary"


def _int(value) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _plus_minus(value) -> int | None:
    """'+12' / '-2' -> 12 / -2."""
    if value is None:
        return None
    return _int(str(value).lstrip("+"))


def parse_players(payload: dict) -> list[dict]:
    """ESPN summary -> one dict per dressed player.

    Column order is read from `statistics[].names` rather than assumed: ESPN
    has changed it before, and silently reading minutes out of the points
    column would poison every downstream rating.
    """
    out: list[dict] = []

    for group in payload.get("boxscore", {}).get("players", []):
        team_id = str(group.get("team", {}).get("id", ""))
        if not team_id:
            continue
        for block in group.get("statistics", []):
            names = [str(n).upper() for n in block.get("names", [])]
            idx = {name: i for i, name in enumerate(names)}
            for entry in block.get("athletes", []):
                athlete = entry.get("athlete") or {}
                athlete_id = str(athlete.get("id") or "")
                if not athlete_id:
                    continue

                stats = entry.get("stats") or []

                # idx/stats bound as defaults: the closure is consumed inside
                # this iteration, but binding them makes that independent of
                # where it is called from.
                def stat(key: str, idx=idx, stats=stats):
                    i = idx.get(key)
                    if i is None or i >= len(stats):
                        return None
                    return stats[i]

                dnp = bool(entry.get("didNotPlay")) or not stats
                out.append(
                    {
                        "team_id": team_id,
                        "athlete_id": athlete_id,
                        "athlete_name": athlete.get("displayName"),
                        "position": (athlete.get("position") or {}).get("abbreviation"),
                        "starter": bool(entry.get("starter")),
                        "did_not_play": dnp,
                        # ESPN sends a `reason` even for players who played;
                        # it only means anything alongside didNotPlay.
                        "dnp_reason": (entry.get("reason") or None) if dnp else None,
                        "minutes": None if dnp else _int(stat("MIN")),
                        "points": None if dnp else _int(stat("PTS")),
                        "plus_minus": None if dnp else _plus_minus(stat("+/-")),
                    }
                )
    return out


def _games_needing_backfill(
    session: Session, start_season: int, end_season: int, limit: int | None
) -> list[tuple[str, dt.datetime, int, int]]:
    """Completed games with no player rows yet, oldest first."""
    have = select(PlayerGameLog.espn_game_id).distinct().scalar_subquery()
    return list(
        session.execute(
            select(
                TeamGameLog.espn_game_id,
                func.min(TeamGameLog.game_date),
                func.min(TeamGameLog.season),
                func.min(TeamGameLog.season_type),
            )
            .where(TeamGameLog.season >= start_season)
            .where(TeamGameLog.season <= end_season)
            .where(TeamGameLog.is_completed.is_(True))
            .where(TeamGameLog.espn_game_id.notin_(have))
            .group_by(TeamGameLog.espn_game_id)
            .order_by(func.min(TeamGameLog.game_date))
            .limit(limit)
        ).all()
    )


def backfill(start_season: int, end_season: int, limit: int | None = None) -> tuple[int, int]:
    """Fetch player box scores for games missing them. Returns (games, rows)."""
    Session_ = get_sessionmaker(get_engine())
    client = ESPNClient()

    with Session_() as session:
        targets = _games_needing_backfill(session, start_season, end_season, limit)

    games = rows = 0
    with Session_() as session:
        for i, (gid, game_date, season, season_type) in enumerate(targets, 1):
            try:
                payload = client.get(SUMMARY_URL, params={"event": gid})
                players = parse_players(payload)
            except ESPNNotFound:
                log.warning("summary_missing", game=gid)
                continue
            except Exception as exc:
                log.warning("summary_failed", game=gid, error=str(exc))
                continue
            if not players:
                log.warning("no_players_in_summary", game=gid)
                continue

            values = [
                {
                    "espn_game_id": gid,
                    "game_date": game_date,
                    "season": season,
                    "season_type": season_type,
                    **p,
                }
                for p in players
            ]
            stmt = pg_insert(PlayerGameLog).values(values)
            # Re-running must be a no-op, not a duplicate-key crash.
            result = session.execute(
                stmt.on_conflict_do_nothing(constraint="uq_player_game")
            )
            # psycopg reports -1 for a multi-VALUES insert; fall back to the
            # attempted count rather than logging a negative total.
            rows += result.rowcount if (result.rowcount or 0) >= 0 else len(values)
            games += 1
            if i % 100 == 0:
                session.commit()
                log.info("player_boxscore_progress", done=i, total=len(targets), rows=rows)
        session.commit()

    log.info("player_boxscore_backfill_complete", games=games, rows=rows)
    return games, rows


def main() -> int:
    parser = argparse.ArgumentParser(prog="espn-player-boxscores")
    parser.add_argument("--start", type=int, default=2024)
    parser.add_argument("--end", type=int, default=2026)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )
    backfill(args.start, args.end, args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
