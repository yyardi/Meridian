"""Copy tables from the primary (Supabase) into the local warm standby.

Why this exists
---------------
Every query in a walk-forward backtest is a network round trip. Against
Supabase a paired experiment takes ~11 minutes; against local Postgres the same
work is seconds. That is not a comfort issue — an experiment that costs 11
minutes gets run once and its result stands unchallenged, while one that costs
seconds gets re-run under different settings, which is how a result earns
trust. The same lesson is already recorded in `tests/conftest.py`, which pins
the suite to the local database for exactly this reason.

Direction is one-way and enforced: primary -> local, never the reverse. The
local copy is disposable; the primary is the record.

    python -m core.storage.sync_local                 # every backtest table
    python -m core.storage.sync_local --table player_game_logs
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

import structlog
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import sessionmaker

from core.storage.base import Base
from core.storage.models import (
    InjuryPoll,
    InjuryReport,
    PlayerGameLog,
    Prediction,
    ResolvedOutcome,
    SportsbookOdds,
    TeamGameLog,
)

log = structlog.get_logger(__name__)

#: Local Docker Postgres from docker-compose.yml — same target the tests use.
LOCAL_URL = "postgresql+psycopg://meridian:meridian@localhost:5433/meridian"

#: Everything a backtest or experiment reads. `market_snapshots` and
#: `book_levels` are deliberately excluded: they are large, they are the
#: unrecoverable stream, and no historical backtest touches them.
SYNCED_TABLES = {
    "team_game_logs": TeamGameLog,
    "sportsbook_odds": SportsbookOdds,
    "player_game_logs": PlayerGameLog,
    "injury_reports": InjuryReport,
    "injury_polls": InjuryPoll,
    "resolved_outcomes": ResolvedOutcome,
    "predictions": Prediction,
}

#: Postgres caps a statement at 65535 bound parameters, and a multi-VALUES
#: insert uses one per column per row. Chunk size is therefore derived from the
#: table's width, not fixed — a 23-column table and a 5-column one have very
#: different safe batch sizes.
MAX_BIND_PARAMS = 60000


def _guard(source_url: str, target_url: str) -> None:
    """Refuse to run in any direction but primary -> local."""
    if "localhost" not in target_url and "127.0.0.1" not in target_url:
        raise SystemExit(f"Refusing to write to a non-local target: {target_url.split('@')[-1]}")
    if "localhost" in source_url or "127.0.0.1" in source_url:
        raise SystemExit("Source looks local — nothing to sync from. Set DATABASE_URL to the primary.")


def sync_table(name: str, model, *, source_session, target_session) -> tuple[int, int]:
    """Copy one table. Returns (source_rows, rows_written)."""
    columns = [c.name for c in model.__table__.columns]
    total = source_session.scalar(select(func.count()).select_from(model.__table__)) or 0
    chunk = max(1, MAX_BIND_PARAMS // len(columns))

    written = 0
    offset = 0
    while True:
        rows = source_session.execute(
            select(model.__table__)
            .order_by(model.__table__.c.id)
            .offset(offset)
            .limit(chunk)
        ).all()
        if not rows:
            break
        values = [dict(zip(columns, row)) for row in rows]
        # Upsert on primary key: re-running is a refresh, not a duplicate.
        stmt = pg_insert(model.__table__).values(values)
        target_session.execute(
            stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={c: stmt.excluded[c] for c in columns if c != "id"},
            )
        )
        target_session.commit()
        written += len(values)
        offset += chunk
        log.info("sync_progress", table=name, done=written, total=total)

    # Keep the sequence ahead of the copied ids, or the next local insert
    # collides with a row that was synced in.
    target_session.execute(
        text(
            f"SELECT setval(pg_get_serial_sequence('{name}', 'id'), "
            f"COALESCE((SELECT MAX(id) FROM {name}), 1))"
        )
    )
    target_session.commit()
    return total, written


def sync(tables: list[str] | None = None) -> dict[str, tuple[int, int]]:
    source_url = os.environ.get("DATABASE_URL", "")
    target_url = os.environ.get("MERIDIAN_LOCAL_URL", LOCAL_URL)
    _guard(source_url, target_url)

    source = create_engine(source_url, pool_pre_ping=True)
    target = create_engine(target_url, pool_pre_ping=True)
    Base.metadata.create_all(target)

    SourceSession = sessionmaker(bind=source)
    TargetSession = sessionmaker(bind=target)

    names = tables or list(SYNCED_TABLES)
    out: dict[str, tuple[int, int]] = {}
    with SourceSession() as s, TargetSession() as t:
        for name in names:
            model = SYNCED_TABLES.get(name)
            if model is None:
                raise SystemExit(f"Unknown table {name!r}. Known: {', '.join(SYNCED_TABLES)}")
            out[name] = sync_table(name, model, source_session=s, target_session=t)
            log.info("sync_table_done", table=name, source=out[name][0], written=out[name][1])
    return out


def main() -> int:
    parser = argparse.ArgumentParser(prog="meridian-sync-local")
    parser.add_argument("--table", action="append", dest="tables", default=None)
    args = parser.parse_args()

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )
    results = sync(args.tables)
    for name, (total, written) in results.items():
        print(f"{name:<22s} {written:>7,} / {total:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
