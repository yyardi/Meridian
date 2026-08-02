"""Point-in-time recorder for WNBA injury designations.

This is the tradable half of the availability work, and like the Polymarket
snapshot stream it is **unrecoverable**: ESPN publishes current status only.
Measured, not assumed — the `injuries` block inside the summary of a 2025 game
returns designations dated 2026, so no historical status can be reconstructed
from ESPN at all. Every point-in-time injury row this project will ever own
starts at the moment this recorder first runs.

Change-log, not per-poll dump
-----------------------------
Writing all ~35 open designations every poll would add ~2.5k rows a day to say
nothing new. Instead a row is written only when a player's designation changes,
and a synthetic `Cleared` row is written when she drops out of the feed — which
is how ESPN signals "available again". Status as of an instant is then

    latest InjuryReport for that athlete with captured_at <= as_of

which is correct *because* unchanged states are not rewritten. The cost of that
compression is that silence is ambiguous, so every poll also writes an
`InjuryPoll` row: a recorder outage shows up as a gap in polls rather than
masquerading as a quiet week.

    python -m core.feeds.espn_injuries --once
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import re
import sys
from dataclasses import dataclass

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from core.feeds.espn_client import ESPNClient
from core.storage import InjuryPoll, InjuryReport, get_engine, get_sessionmaker

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc

INJURIES_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/injuries"

#: Feed identity. The change log is a state machine per source, so this is the
#: key that keeps one feed's silence from clearing another's designations.
SOURCE = "espn_injuries"

#: Synthesised when a player leaves the feed. ESPN never sends this itself.
STATUS_CLEARED = "Cleared"

#: ESPN omits `athlete.id` from this feed but leaks it in every player URL.
_ATHLETE_ID_RE = re.compile(r"/(?:id|players/full)/(\d+)")


@dataclass(frozen=True)
class Designation:
    """One player's injury state at one instant."""

    athlete_id: str
    athlete_name: str | None
    position: str | None
    team_id: str | None
    team_name: str | None
    status: str
    status_type: str | None
    detail_type: str | None
    return_date: str | None
    reported_at: dt.datetime | None
    raw: dict | None = None

    @property
    def state_key(self) -> tuple:
        """What counts as a change.

        Deliberately excludes `reported_at`: ESPN bumps it whenever a beat
        writer's comment is edited, which is not new information about whether
        she plays, and churning a row for it would make the log lie about how
        often status actually moves.
        """
        return (self.status, self.status_type, self.detail_type, self.return_date)


def _athlete_id(athlete: dict) -> str | None:
    direct = athlete.get("id")
    if direct:
        return str(direct)
    candidates = [link.get("href", "") for link in athlete.get("links", []) or []]
    candidates.append((athlete.get("headshot") or {}).get("href", ""))
    for href in candidates:
        match = _ATHLETE_ID_RE.search(href or "")
        if match:
            return match.group(1)
    return None


def _parse_ts(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        # ESPN sends '2026-07-31T22:37Z'.
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_injuries(payload: dict) -> tuple[list[Designation], int]:
    """ESPN injuries feed -> (designations, n_teams)."""
    teams = payload.get("injuries", []) or []
    out: list[Designation] = []

    for team in teams:
        team_id = str(team.get("id")) if team.get("id") is not None else None
        team_name = team.get("displayName")
        for item in team.get("injuries", []) or []:
            athlete = item.get("athlete") or {}
            athlete_id = _athlete_id(athlete)
            if not athlete_id:
                # Without a stable key the change log cannot track her; drop
                # rather than invent an identifier that will collide later.
                log.warning("injury_without_athlete_id", name=athlete.get("displayName"))
                continue
            details = item.get("details") or {}
            out.append(
                Designation(
                    athlete_id=athlete_id,
                    athlete_name=athlete.get("displayName"),
                    position=(athlete.get("position") or {}).get("abbreviation"),
                    team_id=team_id,
                    team_name=team_name,
                    status=str(item.get("status") or "Unknown"),
                    status_type=(item.get("type") or {}).get("name"),
                    detail_type=details.get("type"),
                    return_date=details.get("returnDate"),
                    reported_at=_parse_ts(item.get("date")),
                    raw=item,
                )
            )
    return out, len(teams)


def _current_states(
    session: Session, source: str = SOURCE
) -> tuple[dict[str, tuple], dict[str, tuple[str | None, str | None]]]:
    """Latest known state per athlete, and her last known (team_id, name).

    Returns (states, identities). `states` excludes athletes already cleared —
    those need no further action. `identities` covers everyone, because a
    synthesised `Cleared` row must carry the team forward: status is read back
    with a `team_id` filter, so a cleared row without one would never be found
    and the player would stay "Out" forever.

    Scoped to one `source`. The change log is a state machine over whatever
    feed wrote it, so mixing feeds would have one source's silence clear the
    other's designations.

    DISTINCT ON is the cheap way to get "newest row per athlete" in Postgres
    and rides the (athlete_id, captured_at) index.
    """
    rows = session.execute(
        select(
            InjuryReport.athlete_id,
            InjuryReport.status,
            InjuryReport.status_type,
            InjuryReport.detail_type,
            InjuryReport.return_date,
            InjuryReport.team_id,
            InjuryReport.athlete_name,
        )
        .where(InjuryReport.source == source)
        .distinct(InjuryReport.athlete_id)
        .order_by(InjuryReport.athlete_id, InjuryReport.captured_at.desc())
    ).all()
    states = {
        r.athlete_id: (r.status, r.status_type, r.detail_type, r.return_date)
        for r in rows
        if r.status != STATUS_CLEARED
    }
    identities = {r.athlete_id: (r.team_id, r.athlete_name) for r in rows}
    return states, identities


def record_once(*, session: Session, client: ESPNClient | None = None,
                captured_at: dt.datetime | None = None, source: str = SOURCE) -> int:
    """One poll. Returns the number of state changes written."""
    client = client or ESPNClient()
    captured_at = captured_at or dt.datetime.now(UTC)

    payload = client.get(INJURIES_URL)
    designations, n_teams = parse_injuries(payload)

    known, last_seen = _current_states(session, source)
    seen: set[str] = set()
    changes: list[dict] = []

    def _row(**fields) -> dict:
        """Every change row carries the same keys.

        A multi-VALUES insert compiles one statement for the whole batch, so
        rows with differing key sets fail outright — and the batch that mixes
        them (a status change alongside a synthesised `Cleared`) is exactly the
        common case in production, where it broke on the first live poll.
        """
        base = {
            "captured_at": captured_at,
            "reported_at": None,
            "source": source,
            "team_id": None,
            "team_name": None,
            "athlete_id": None,
            "athlete_name": None,
            "position": None,
            "status": None,
            "status_type": None,
            "detail_type": None,
            "return_date": None,
            "raw": None,
        }
        base.update(fields)
        return base

    for d in designations:
        seen.add(d.athlete_id)
        if known.get(d.athlete_id) == d.state_key:
            continue
        changes.append(
            _row(
                reported_at=d.reported_at,
                team_id=d.team_id,
                team_name=d.team_name,
                athlete_id=d.athlete_id,
                athlete_name=d.athlete_name,
                position=d.position,
                status=d.status,
                status_type=d.status_type,
                detail_type=d.detail_type,
                return_date=d.return_date,
                raw=d.raw,
            )
        )

    # Gone from the feed = available again. Without this the log would leave
    # every recovered player permanently "Out". Team and name are carried over
    # from the last known row so a cleared player stays queryable by team.
    for athlete_id in known.keys() - seen:
        last = last_seen.get(athlete_id, (None, None))
        changes.append(
            _row(
                athlete_id=athlete_id,
                team_id=last[0],
                athlete_name=last[1],
                status=STATUS_CLEARED,
            )
        )

    if changes:
        session.execute(
            pg_insert(InjuryReport)
            .values(changes)
            .on_conflict_do_nothing(constraint="uq_injury_athlete_time")
        )

    session.execute(
        pg_insert(InjuryPoll)
        .values(
            captured_at=captured_at,
            source=source,
            n_teams=n_teams,
            n_designations=len(designations),
            n_changes=len(changes),
        )
        .on_conflict_do_nothing(index_elements=["captured_at"])
    )
    session.commit()

    log.info(
        "injury_poll",
        teams=n_teams,
        designations=len(designations),
        changes=len(changes),
    )
    return len(changes)


def run(captured_at: dt.datetime | None = None) -> int:
    """Entry point for the scheduler."""
    Session_ = get_sessionmaker(get_engine())
    client = ESPNClient()
    with Session_() as session:
        return record_once(session=session, client=client, captured_at=captured_at)


def main() -> int:
    parser = argparse.ArgumentParser(prog="espn-injuries")
    parser.add_argument("--once", action="store_true", default=True)
    parser.parse_args()

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
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
