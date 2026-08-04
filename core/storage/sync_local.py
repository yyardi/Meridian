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
    python -m core.storage.sync_local                 # durable tables only
                                                      # (--stream now REFUSES; see below)
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
    BookLevel,
    InjuryPoll,
    InjuryReport,
    MarketSnapshot,
    PlayerGameLog,
    Prediction,
    ResolvedOutcome,
    SportsbookOdds,
    TeamGameLog,
)

log = structlog.get_logger(__name__)

#: Local Docker Postgres from docker-compose.yml — same target the tests use.
LOCAL_URL = "postgresql+psycopg://meridian:meridian@localhost:5433/meridian"

#: Everything a historical backtest reads. Synced by default.
DEFAULT_TABLES = {
    "team_game_logs": TeamGameLog,
    "sportsbook_odds": SportsbookOdds,
    "player_game_logs": PlayerGameLog,
    "injury_reports": InjuryReport,
    "injury_polls": InjuryPoll,
    "resolved_outcomes": ResolvedOutcome,
    "predictions": Prediction,
}

#: The market stream. **Not** synced by default: it is the largest and
#: fastest-growing pair of tables in the system, and now that the live recorder
#: samples at 1s rather than 30s it grows ~30x faster than it used to. No
#: historical backtest touches it.
#:
#: The microstructure experiments (adverse selection, run overreaction, depth
#: signal) do read it, and the project rule is that experiments run against
#: local Postgres — 11m28s against Supabase versus 13s locally is the
#: difference between a result that gets re-run under different settings and
#: one that stands unchallenged because re-running it is too expensive. So
#: these are opt-in rather than unavailable:
#:
#:     python -m core.storage.sync_local --stream
#:
#: Order matters: book_levels carries a foreign key into market_snapshots, so
#: the parent must land first.
STREAM_TABLES = {
    "market_snapshots": MarketSnapshot,
    "book_levels": BookLevel,
}

#: **The stream is no longer safe to sync, and this is not a preference.**
#:
#: As of 2026-08-03 the live recorder writes `market_snapshots` and
#: `book_levels` directly to LOCAL Postgres, not Supabase — it was 99.1% of the
#: write load (657,000 rows/day against 5,900 for everything else) and had
#: pinned a shared-CPU instance at 99%.
#:
#: The two databases now have *independent* id sequences for these tables. This
#: module upserts on primary key, so pulling Supabase's copy down would match a
#: remote row against a completely unrelated local row with the same id and
#: overwrite it. That silently destroys ticks which cannot be refetched from
#: anywhere: Polymarket publishes no price history.
#:
#: Passing `--stream` therefore refuses rather than warning. A flag that
#: corrupts the one irreplaceable dataset should not be one keystroke away.
STREAM_IS_LOCALLY_AUTHORED = True


class StreamSyncRefused(SystemExit):
    """Raised when someone asks to sync a locally-authored stream table."""


SYNCED_TABLES = {**DEFAULT_TABLES, **STREAM_TABLES}

#: Postgres caps a statement at 65535 bound parameters, and a multi-VALUES
#: insert uses one per column per row. Chunk size is therefore derived from the
#: table's width, not fixed — a 23-column table and a 5-column one have very
#: different safe batch sizes.
MAX_BIND_PARAMS = 60000

#: Columns dropped from the local copy by default, per table.
#:
#: `market_snapshots.raw` is 62% of the table's bytes ([infra/live-cadence.md])
#: and **24x its transfer time**: measured 2026-08-02 over the Supabase pooler,
#: one 2,857-row page took **35.7s with `raw` and 1.5s without**. At 837k rows
#: that is the difference between a 4.7-hour sync and a 7-minute one.
#:
#: Nothing reads it. It is a schema-drift archive — kept on the primary so a
#: parsing bug can be fixed retroactively — and the primary keeps it. This
#: module's whole premise is that a local copy exists so experiments are cheap
#: enough to re-run; a 4.7-hour setup is exactly the cost that makes a result
#: stand unchallenged.
OMITTED_BY_DEFAULT: dict[str, frozenset[str]] = {
    "market_snapshots": frozenset({"raw"}),
}

#: What an omitted column holds locally. **Not NULL** — deliberately.
#:
#: NULL already means "the recorder captured no payload", and a local copy that
#: silently reuses that value would let someone conclude the recorder was
#: broken. A row that says why it is empty cannot be misread. Same reasoning as
#: `book_tier` being nullable: the absence has to name its own cause.
OMITTED_SENTINEL = {"_omitted_by": "sync_local", "_see": "primary has the payload"}


def _guard(source_url: str, target_url: str) -> None:
    """Refuse to run in any direction but primary -> local."""
    if "localhost" not in target_url and "127.0.0.1" not in target_url:
        raise SystemExit(f"Refusing to write to a non-local target: {target_url.split('@')[-1]}")
    if "localhost" in source_url or "127.0.0.1" in source_url:
        raise SystemExit("Source looks local — nothing to sync from. Set DATABASE_URL to the primary.")


def sync_table(
    name: str,
    model,
    *,
    source_session,
    target_session,
    resume: bool = False,
    omit: frozenset[str] = frozenset(),
) -> tuple[int, int]:
    """Copy one table by keyset, oldest id first. Returns (source_rows, written).

    **Keyset, not OFFSET.** `OFFSET n` makes Postgres walk and discard the
    first n rows on every page, so a full copy is quadratic in the table
    length. That was survivable at 30s cadence; at 200ms it is not. Measured
    2026-08-02: the OFFSET version died on `market_snapshots` at offset 31,427
    of 837,220 with `canceling statement due to statement timeout` — the page
    query itself had grown past Supabase's limit, so the copy could not finish
    at any speed. `WHERE id > last` rides the primary key and each page costs
    the same as the first.

    **`resume` skips ids already present locally**, and is therefore only
    correct for **append-only** tables — one whose rows are never updated after
    insert. `market_snapshots` and `book_levels` are appended by the recorders
    and never rewritten. Everything else (`predictions`, `resolved_outcomes`,
    `team_game_logs`, ...) is upserted in place, so a resumed copy would keep a
    stale local row forever. The caller decides; the default is off, because
    the failure mode of a wrong resume is silent staleness rather than an
    error.

    **`omit` drops columns from the wire**, writing `OMITTED_SENTINEL` locally
    instead. See `OMITTED_BY_DEFAULT` for why, and why the placeholder is not
    NULL.
    """
    table = model.__table__
    columns = [c.name for c in table.columns]
    fetched = [c for c in table.columns if c.name not in omit]
    if omit:
        log.warning("sync_omitting_columns", table=name, columns=sorted(omit),
                    stored_as="OMITTED_SENTINEL, not NULL")

    total = source_session.scalar(select(func.count()).select_from(table)) or 0
    chunk = max(1, MAX_BIND_PARAMS // len(columns))

    last_id = 0
    if resume:
        last_id = target_session.scalar(select(func.max(table.c.id))) or 0
        if last_id:
            log.info("sync_resume", table=name, after_id=last_id)

    written = 0
    while True:
        rows = source_session.execute(
            select(*fetched)
            .where(table.c.id > last_id)
            .order_by(table.c.id)
            .limit(chunk)
        ).all()
        if not rows:
            break
        names = [c.name for c in fetched]
        values = [dict(zip(names, row)) for row in rows]
        for v in values:
            for column in omit:
                v[column] = OMITTED_SENTINEL
        # Upsert on primary key: re-running is a refresh, not a duplicate.
        stmt = pg_insert(table).values(values)
        target_session.execute(
            stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={c: stmt.excluded[c] for c in columns if c != "id"},
            )
        )
        # Keep the sequence ahead of the copied ids, or the next local insert
        # collides with a row that was synced in.
        #
        # **Per chunk, not once at the end.** A copy of 837k rows takes minutes,
        # and any interruption inside it — Ctrl-C, a dropped connection, the
        # statement timeout that killed the OFFSET version — used to leave the
        # sequence behind the ids already committed. The next local INSERT then
        # failed with a duplicate-key violation on a table that looked fine,
        # which is how the test suite started failing against a half-synced
        # database. One extra statement per 2,857 rows is not a measurable cost.
        _advance_sequence(name, target_session)
        target_session.commit()
        written += len(values)
        last_id = values[-1]["id"]
        log.info("sync_progress", table=name, done=written, total=total,
                 last_id=last_id)

    _advance_sequence(name, target_session)
    target_session.commit()
    return total, written


def _advance_sequence(name: str, target_session) -> None:
    """Push the local id sequence past the highest copied id."""
    target_session.execute(
        text(
            f"SELECT setval(pg_get_serial_sequence('{name}', 'id'), "
            f"COALESCE((SELECT MAX(id) FROM {name}), 1))"
        )
    )


def sync(
    tables: list[str] | None = None,
    *,
    stream: bool = False,
    full: bool = False,
    with_raw: bool = False,
) -> dict[str, tuple[int, int]]:
    source_url = os.environ.get("DATABASE_URL", "")
    target_url = os.environ.get("MERIDIAN_LOCAL_URL", LOCAL_URL)
    _guard(source_url, target_url)

    source = create_engine(source_url, pool_pre_ping=True)
    target = create_engine(target_url, pool_pre_ping=True)
    Base.metadata.create_all(target)

    SourceSession = sessionmaker(bind=source)
    TargetSession = sessionmaker(bind=target)

    names = tables or list(DEFAULT_TABLES)
    if stream and not tables:
        if STREAM_IS_LOCALLY_AUTHORED:
            raise StreamSyncRefused(
                "Refusing --stream: market_snapshots and book_levels are now "
                "written directly to LOCAL Postgres by the live recorder, so "
                "the two databases have independent id sequences. Upserting "
                "Supabase's copy by id would overwrite unrelated local rows and "
                "destroy ticks that cannot be refetched (Polymarket publishes no "
                "price history). The stream is already local — there is nothing "
                "to sync."
            )
        names = names + list(STREAM_TABLES)
    out: dict[str, tuple[int, int]] = {}
    with SourceSession() as s, TargetSession() as t:
        for name in names:
            model = SYNCED_TABLES.get(name)
            if model is None:
                raise SystemExit(f"Unknown table {name!r}. Known: {', '.join(SYNCED_TABLES)}")
            # Resume only where it is sound: STREAM_TABLES are append-only.
            resume = (name in STREAM_TABLES) and not full
            omit = frozenset() if with_raw else OMITTED_BY_DEFAULT.get(name, frozenset())
            out[name] = sync_table(
                name, model, source_session=s, target_session=t,
                resume=resume, omit=omit,
            )
            log.info("sync_table_done", table=name, source=out[name][0],
                     written=out[name][1], resumed=resume, omitted=sorted(omit))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(prog="meridian-sync-local")
    parser.add_argument("--table", action="append", dest="tables", default=None)
    parser.add_argument(
        "--stream",
        action="store_true",
        help="also sync market_snapshots and book_levels (large; needed by the "
             "microstructure experiments, not by any historical backtest)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="re-copy the stream tables from id 0 instead of resuming after "
             "the newest local id (they are append-only, so resuming is the "
             "default; use this if you suspect the local copy is corrupt)",
    )
    parser.add_argument(
        "--with-raw",
        action="store_true",
        help="also copy market_snapshots.raw. It is 62%% of the bytes and 24x "
             "the transfer time (35.7s vs 1.5s per page, measured), and no "
             "experiment reads it, so it is omitted by default and stored "
             "locally as a self-describing sentinel rather than NULL",
    )
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
    results = sync(args.tables, stream=args.stream, full=args.full,
                   with_raw=args.with_raw)
    for name, (total, written) in results.items():
        print(f"{name:<22s} {written:>7,} / {total:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
