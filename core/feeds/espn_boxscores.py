"""Backfill box-score stats onto team_game_logs.

One ESPN summary call per game supplies both teams' FGA/FTA/OREB/turnovers —
the inputs to the Kubatko possessions estimate — plus quarter linescores,
stored now so future garbage-time work needs no refetch.

Idempotent: games whose rows already carry `fga` are skipped, so reruns only
fetch what is missing.

    python -m core.feeds.espn_boxscores --start 2024 --end 2026
"""

from __future__ import annotations

import argparse
import logging
import sys

import structlog
from sqlalchemy import select, update

from core.feeds.espn_client import ESPNClient
from core.storage import TeamGameLog, get_engine, get_sessionmaker

log = structlog.get_logger(__name__)

SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/summary"


def _split_attempts(display: str | None) -> int | None:
    """'30-68' -> 68 (attempts half of a made-attempted pair)."""
    if not display or "-" not in display:
        return None
    try:
        return int(display.split("-")[1])
    except (ValueError, IndexError):
        return None


def _int(value) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def parse_summary(payload: dict) -> dict[str, dict]:
    """ESPN summary -> {team_id: {fga, fta, oreb, turnovers, q1..q4, ot_points}}."""
    out: dict[str, dict] = {}

    for team in payload.get("boxscore", {}).get("teams", []):
        tid = str(team.get("team", {}).get("id", ""))
        if not tid:
            continue
        stats = {s.get("name"): s.get("displayValue") for s in team.get("statistics", [])}
        out[tid] = {
            "fga": _split_attempts(stats.get("fieldGoalsMade-fieldGoalsAttempted")),
            "fta": _split_attempts(stats.get("freeThrowsMade-freeThrowsAttempted")),
            "oreb": _int(stats.get("offensiveRebounds")),
            # totalTurnovers includes team turnovers, which is what the
            # possessions formula wants.
            "turnovers": _int(stats.get("totalTurnovers")) or _int(stats.get("turnovers")),
        }

    comps = payload.get("header", {}).get("competitions", [])
    if comps:
        for comp in comps[0].get("competitors", []):
            tid = str(comp.get("team", {}).get("id", ""))
            ls = [_int(x.get("displayValue")) for x in comp.get("linescores", [])]
            if tid in out and ls:
                quarters = ls[:4] + [None] * (4 - len(ls))
                out[tid].update({
                    "q1": quarters[0], "q2": quarters[1],
                    "q3": quarters[2], "q4": quarters[3],
                    "ot_points": sum(v for v in ls[4:] if v is not None) if len(ls) > 4 else None,
                })
    return out


def backfill(start_season: int, end_season: int, limit: int | None = None) -> tuple[int, int]:
    """Fetch stats for completed games missing them. Returns (games, updated_rows)."""
    Session = get_sessionmaker(get_engine())
    client = ESPNClient()

    with Session() as session:
        game_ids = session.scalars(
            select(TeamGameLog.espn_game_id)
            .where(TeamGameLog.season >= start_season)
            .where(TeamGameLog.season <= end_season)
            .where(TeamGameLog.is_completed.is_(True))
            .where(TeamGameLog.fga.is_(None))
            .distinct()
            .limit(limit)
        ).all()

    games = rows = 0
    with Session() as session:
        for i, gid in enumerate(game_ids, 1):
            try:
                payload = client.get(SUMMARY_URL, params={"event": gid})
                parsed = parse_summary(payload)
            except Exception as exc:
                log.warning("summary_failed", game=gid, error=str(exc))
                continue
            if not parsed:
                continue
            for tid, vals in parsed.items():
                result = session.execute(
                    update(TeamGameLog)
                    .where(TeamGameLog.espn_game_id == gid, TeamGameLog.team_id == tid)
                    .values(**vals)
                )
                rows += result.rowcount or 0
            games += 1
            if i % 100 == 0:
                session.commit()
                log.info("boxscore_progress", done=i, total=len(game_ids))
        session.commit()

    log.info("boxscore_backfill_complete", games=games, rows_updated=rows)
    return games, rows


def main() -> int:
    parser = argparse.ArgumentParser(prog="espn-boxscores")
    parser.add_argument("--start", type=int, default=2024)
    parser.add_argument("--end", type=int, default=2026)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    structlog.configure(
        processors=[structlog.processors.add_log_level,
                    structlog.processors.TimeStamper(fmt="iso"),
                    structlog.dev.ConsoleRenderer()],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )
    backfill(args.start, args.end, args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
