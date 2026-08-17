"""Tick-archive retention: monthly partitions, archive-then-detach, never lose a row.

The invariant, stated once and enforced everywhere below: **no tick is ever
deleted without a verified copy existing first.** The local tick archive is
the one unrecoverable dataset in this project — every future in-game
hypothesis replays it — so "retention" here means moving months out of the
live database into compressed dumps, not discarding them.

The design
----------
`market_snapshots` and `book_levels` become **natively partitioned** by
`captured_at`, one partition per calendar month, plus a DEFAULT partition as a
safety net: a row whose month has no partition lands in DEFAULT rather than
erroring, so a missed maintenance run can never cost data (the health check
reports a non-empty DEFAULT loudly instead).

Archival of a month, in this exact order:

1. ``pg_dump -Fc`` the month's partition to ``backups/ticks/`` (host-mounted).
2. **Verify the dump restores**: a scratch database gets the parent's schema,
   the dump is ``pg_restore``-ed into it, and row count + min/max id must
   match the live partition exactly.
3. Only then ``DETACH PARTITION`` and drop the detached table, recording
   every step — rows, bytes, sha256, verified/detached/dropped timestamps —
   in ``retention_log``, which is what the health check and the alerter read.

A failure at any step aborts *before* the detach: the worst possible outcome
is a stale dump file, never a missing month.

Why the conversion is NOT an Alembic migration
----------------------------------------------
``alembic upgrade head`` runs on every container start against **both**
databases. Partitioning rewrites the whole table (2+ GB locally); running
that implicitly against Supabase would double its storage mid-flight — the
free tier is at 395 of 500 MB — and take an exclusive lock on the primary at
whatever moment a container happened to restart. The conversion is therefore
an explicit, local-only, operator-run command with its own preconditions
(no live game, exact row-count verification, old tables kept until counts
match). Only the small ``retention_log`` table travels through Alembic.

Schema changes the conversion makes (documented, deliberate):

* Primary keys become ``(id, captured_at)`` — Postgres requires the
  partition key inside every unique constraint. ``id`` keeps its sequence.
* ``uq_snapshot_market_time`` (market_slug, captured_at) is unchanged.
* ``uq_book_level`` gains ``captured_at``. Every writer stamps one
  ``captured_at`` per batch, so rerun-idempotency is preserved; legacy NULL
  ``captured_at`` book rows are first backfilled from their parent snapshot —
  exact for those rows, which predate the split depth loop.
* The ``book_levels -> market_snapshots`` FK is dropped: a plain FK cannot
  reference a partitioned table without carrying the partition key, and the
  join column (``snapshot_id``) is unchanged for every reader.

    python -m core.retention status
    python -m core.retention migrate --yes     # the one-time conversion
    python -m core.retention ensure            # create current+future partitions
    python -m core.retention archive --yes     # dump/verify/detach eligible months
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import structlog
from sqlalchemy import create_engine, text

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc

PARENTS = ("market_snapshots", "book_levels")

#: A month may be archived once it is entirely older than this.
KEEP_DAYS = 30
#: The health check calls the job overdue this long after eligibility.
GRACE_DAYS = 15
#: Extra months of future partitions kept ready ahead of now.
MONTHS_AHEAD = 2

# Paths route through core.paths (MERIDIAN_DATA_DIR override, default
# <repo>/backups). BACKUP_DIR_CONTAINER is the container side of the
# compose mount and moves only together with docker-compose.yml.
from core.paths import BACKUP_DIR_CONTAINER, supabase_dir, ticks_dir

COMPOSE = ["docker", "compose", "exec", "-T", "postgres"]
PG_ENV = ["env", "PGUSER=meridian", "PGPASSWORD=meridian", "PGDATABASE=meridian"]


def _local_url() -> str:
    from core.healthchecks import local_url

    return local_url()


# --------------------------------------------------------------------------- #
# Month arithmetic — pure, unit-tested
# --------------------------------------------------------------------------- #


def month_start(ts: dt.datetime) -> dt.datetime:
    return dt.datetime(ts.year, ts.month, 1, tzinfo=UTC)


def next_month(ms: dt.datetime) -> dt.datetime:
    return dt.datetime(ms.year + (ms.month == 12), ms.month % 12 + 1, 1, tzinfo=UTC)


def month_label(ms: dt.datetime) -> str:
    return f"y{ms.year}m{ms.month:02d}"


def partition_name(parent: str, ms: dt.datetime) -> str:
    return f"{parent}_{month_label(ms)}"


def months_covering(lo: dt.datetime, hi: dt.datetime) -> list[dt.datetime]:
    """Every month start from lo's month through hi's month, inclusive."""
    out, cur = [], month_start(lo)
    while cur <= hi:
        out.append(cur)
        cur = next_month(cur)
    return out


def detachable_months(
    attached: list[dt.datetime], now: dt.datetime, keep_days: int = KEEP_DAYS
) -> list[dt.datetime]:
    """Months whose entire range is older than the keep window.

    A month qualifies only when its *end* — not its start — is past the
    cutoff: a partition with even one row younger than ``keep_days`` stays.
    """
    cutoff = now - dt.timedelta(days=keep_days)
    return sorted(ms for ms in attached if next_month(ms) <= cutoff)


# --------------------------------------------------------------------------- #
# Introspection
# --------------------------------------------------------------------------- #


def is_partitioned(conn, parent: str) -> bool:
    kind = conn.execute(text(
        "select relkind from pg_class c join pg_namespace n on n.oid = c.relnamespace "
        "where n.nspname = 'public' and c.relname = :t"
    ), {"t": parent}).scalar()
    return kind == "p"


@dataclass(frozen=True)
class Partition:
    name: str
    is_default: bool
    month: dt.datetime | None       # None for DEFAULT


def attached_partitions(conn, parent: str) -> list[Partition]:
    rows = conn.execute(text("""
        select c.relname, pg_get_expr(c.relpartbound, c.oid)
        from pg_inherits i
        join pg_class c on c.oid = i.inhrelid
        join pg_class p on p.oid = i.inhparent
        where p.relname = :t
    """), {"t": parent}).all()
    out: list[Partition] = []
    for name, bound in rows:
        if bound == "DEFAULT":
            out.append(Partition(name, True, None))
            continue
        # FOR VALUES FROM ('2026-07-01 ...') TO ('2026-08-01 ...')
        try:
            lo = bound.split("FROM ('")[1].split("'")[0]
            ms = month_start(dt.datetime.fromisoformat(lo).replace(tzinfo=UTC))
        except (IndexError, ValueError):
            ms = None
        out.append(Partition(name, False, ms))
    return out


# --------------------------------------------------------------------------- #
# Partition maintenance
# --------------------------------------------------------------------------- #


def ensure_partitions(conn, parent: str, months: list[dt.datetime]) -> list[str]:
    """Create any missing monthly partitions. Returns names created.

    If DEFAULT already holds rows for a requested month, Postgres refuses the
    creation — that error is surfaced loudly rather than worked around,
    because silently leaving rows in DEFAULT is safe and moving them is an
    operator decision.
    """
    have = {p.month for p in attached_partitions(conn, parent) if p.month}
    created = []
    for ms in months:
        if ms in have:
            continue
        name = partition_name(parent, ms)
        conn.execute(text(
            f"create table {name} partition of {parent} "
            f"for values from ('{ms:%Y-%m-%d}') to ('{next_month(ms):%Y-%m-%d}')"
        ))
        created.append(name)
        log.info("partition_created", partition=name)
    return created


# --------------------------------------------------------------------------- #
# The one-time conversion
# --------------------------------------------------------------------------- #

#: Parent-level index definitions, mirroring core/storage/models.py. Unique
#: constraints are declared inline in the CREATE so their names — which
#: ON CONFLICT clauses reference — are identical to the originals.
_SNAPSHOT_INDEXES = [
    ("ix_market_snapshots_captured_at", "(captured_at)"),
    ("ix_market_snapshots_market_slug", "(market_slug)"),
    ("ix_market_snapshots_event_slug", "(event_slug)"),
    ("ix_market_snapshots_game_id", "(game_id)"),
    ("ix_market_snapshots_slug_time", "(market_slug, captured_at)"),
]
_BOOK_INDEXES = [
    ("ix_book_levels_snapshot_id", "(snapshot_id)"),
    ("ix_book_levels_captured_at", "(captured_at)"),
]


def migrate(engine, *, now: dt.datetime | None = None) -> dict:
    """Convert both tables to monthly partitioning, in one transaction.

    The old tables survive (renamed ``*_preswap``) until row counts match
    exactly; only then are they dropped. Any mismatch keeps them and raises.
    """
    now = now or dt.datetime.now(UTC)
    with engine.begin() as conn:
        for parent in PARENTS:
            if is_partitioned(conn, parent):
                raise RuntimeError(f"{parent} is already partitioned")
        conn.execute(text("set lock_timeout = '30s'"))
        conn.execute(text(
            "lock table market_snapshots, book_levels in access exclusive mode"
        ))

        # Legacy depth rows predate the split depth loop, when book calls and
        # snapshots happened together — the parent's captured_at is exact.
        backfilled = conn.execute(text("""
            update book_levels b set captured_at = s.captured_at
            from market_snapshots s
            where b.captured_at is null and s.id = b.snapshot_id
        """)).rowcount
        log.info("book_levels_captured_at_backfilled", rows=backfilled)

        lo, hi = conn.execute(text(
            "select min(captured_at), max(captured_at) from market_snapshots"
        )).one()
        months = months_covering(lo or now, max(hi or now, now))
        months += [m for i in range(1, MONTHS_AHEAD + 1)
                   for m in [_add_months(month_start(now), i)] if m not in months]

        # Free the canonical constraint/index names before recreating them on
        # the new parents — index and constraint names are schema-global.
        conn.execute(text(
            "alter table book_levels drop constraint if exists "
            "book_levels_snapshot_id_fkey"
        ))
        _rename_away(conn, "market_snapshots",
                     ["uq_snapshot_market_time"], [n for n, _ in _SNAPSHOT_INDEXES],
                     pkey="market_snapshots_pkey")
        _rename_away(conn, "book_levels",
                     ["uq_book_level"], [n for n, _ in _BOOK_INDEXES],
                     pkey="book_levels_pkey")

        _create_partitioned(conn, "market_snapshots", months,
                            unique="constraint uq_snapshot_market_time "
                                   "unique (market_slug, captured_at)",
                            indexes=_SNAPSHOT_INDEXES)
        _create_partitioned(conn, "book_levels", months,
                            unique="constraint uq_book_level unique "
                                   "(snapshot_id, side, level_index, captured_at)",
                            indexes=_BOOK_INDEXES)

        copied = {}
        for parent in PARENTS:
            copied[parent] = conn.execute(text(
                f"insert into {parent}_new select * from {parent}"
            )).rowcount
            conn.execute(text(f"alter table {parent} rename to {parent}_preswap"))
            conn.execute(text(f"alter table {parent}_new rename to {parent}"))
            # The id default points at the original sequence; re-own it so
            # dropping the preswap table cannot take the sequence with it.
            conn.execute(text(
                f"alter sequence {parent}_id_seq owned by {parent}.id"
            ))
        log.info("partition_swap_committed", **copied)

    # Verification and cleanup OUTSIDE the swap transaction, so a mismatch
    # leaves both tables inspectable side by side.
    with engine.begin() as conn:
        for parent in PARENTS:
            new_n, old_n = conn.execute(text(
                f"select (select count(*) from {parent}), "
                f"(select count(*) from {parent}_preswap)"
            )).one()
            if new_n != old_n:
                raise RuntimeError(
                    f"{parent}: partitioned copy has {new_n} rows vs "
                    f"{old_n} original — BOTH TABLES KEPT ({parent} and "
                    f"{parent}_preswap); do not drop anything by hand"
                )
        for parent in PARENTS:
            conn.execute(text(f"drop table {parent}_preswap"))
        log.info("preswap_tables_dropped_after_exact_count_match")
    return copied


def _add_months(ms: dt.datetime, n: int) -> dt.datetime:
    for _ in range(n):
        ms = next_month(ms)
    return ms


def _rename_away(conn, table: str, constraints: list[str], indexes: list[str],
                 *, pkey: str) -> None:
    for c in constraints + [pkey]:
        conn.execute(text(
            f"alter table {table} rename constraint {c} to {c}_preswap"
        ))
    for i in indexes:
        conn.execute(text(f"alter index if exists {i} rename to {i}_preswap"))


def _create_partitioned(conn, parent: str, months: list[dt.datetime],
                        *, unique: str, indexes: list[tuple[str, str]]) -> None:
    conn.execute(text(
        f"create table {parent}_new (like {parent} including defaults) "
        f"partition by range (captured_at)"
    ))
    conn.execute(text(
        f"alter table {parent}_new add primary key (id, captured_at), "
        f"add {unique}"
    ))
    for name, cols in indexes:
        conn.execute(text(f"create index {name} on {parent}_new {cols}"))
    for ms in months:
        conn.execute(text(
            f"create table {partition_name(parent, ms)} partition of {parent}_new "
            f"for values from ('{ms:%Y-%m-%d}') to ('{next_month(ms):%Y-%m-%d}')"
        ))
    conn.execute(text(
        f"create table {parent}_default partition of {parent}_new default"
    ))
    # book_levels keeps accepting NULL captured_at (the column is nullable in
    # the model); NULL routes to DEFAULT, which the health check watches.


# --------------------------------------------------------------------------- #
# Archival — dump, VERIFY, then detach. Never the other order.
# --------------------------------------------------------------------------- #


def _pg(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    """Run a postgres-client command inside the compose postgres container."""
    return subprocess.run(COMPOSE + PG_ENV + cmd, capture_output=True,
                          text=True, timeout=1800, **kw)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def archive_month(engine, ms: dt.datetime, *, now: dt.datetime | None = None) -> list[dict]:
    """Archive one month across both tables. Returns per-table receipts.

    Order per table: pg_dump → restore into a scratch database → row count and
    id-range must match the live partition exactly → record in retention_log →
    DETACH → drop the detached table. Abort before detach on any failure.
    """
    now = now or dt.datetime.now(UTC)
    if next_month(ms) > now - dt.timedelta(days=KEEP_DAYS):
        raise RuntimeError(f"{month_label(ms)} is inside the {KEEP_DAYS}-day keep window")
    ticks_dir().mkdir(parents=True, exist_ok=True)

    receipts = []
    for parent in PARENTS:
        part = partition_name(parent, ms)
        with engine.connect() as conn:
            if part not in {p.name for p in attached_partitions(conn, parent)}:
                log.info("archive_skip_no_partition", partition=part)
                continue
            n_live, id_lo, id_hi = conn.execute(text(
                f"select count(*), min(id), max(id) from {part}"
            )).one()

        dump_host = ticks_dir() / f"{part}.dump"
        dump_ctr = f"{BACKUP_DIR_CONTAINER}/{part}.dump"
        r = _pg(["pg_dump", "-Fc", "-t", f"public.{part}", "-f", dump_ctr])
        if r.returncode != 0:
            raise RuntimeError(f"pg_dump {part} failed: {r.stderr[:300]}")
        if not dump_host.exists() or dump_host.stat().st_size == 0:
            raise RuntimeError(
                f"dump for {part} not visible at {dump_host} — is the "
                "./backups/ticks:/backups mount on the postgres service?"
            )

        _verify_dump(parent, part, dump_ctr, n_live, id_lo, id_hi)

        digest = _sha256(dump_host)
        with engine.begin() as conn:
            conn.execute(text("""
                insert into retention_log
                  (table_name, partition_name, month_start, rows_archived,
                   dump_path, dump_bytes, dump_sha256, verified_at)
                values (:t, :p, :m, :n, :path, :bytes, :sha, now())
            """), {"t": parent, "p": part, "m": ms, "n": n_live,
                   "path": str(dump_host), "bytes": dump_host.stat().st_size,
                   "sha": digest})
            # The verified copy exists and is recorded; ONLY NOW may the live
            # partition go.
            conn.execute(text(f"alter table {parent} detach partition {part}"))
            conn.execute(text(f"drop table {part}"))
            conn.execute(text("""
                update retention_log set detached_at = now(), dropped_at = now()
                where partition_name = :p and dropped_at is null
            """), {"p": part})
        receipts.append({"partition": part, "rows": int(n_live),
                         "dump": str(dump_host), "sha256": digest})
        log.info("partition_archived", partition=part, rows=int(n_live),
                 bytes=dump_host.stat().st_size)
    return receipts


def _verify_dump(parent: str, part: str, dump_ctr: str,
                 n_live: int, id_lo, id_hi) -> None:
    """Restore the dump into a scratch database and compare it to the live
    partition. Raises on the first discrepancy — nothing detaches after that."""
    scratch = "meridian_retention_verify"
    _pg(["dropdb", "--if-exists", scratch])
    r = _pg(["createdb", scratch])
    if r.returncode != 0:
        raise RuntimeError(f"createdb {scratch} failed: {r.stderr[:200]}")
    try:
        # The parent's schema first — a partition's dump attaches to it.
        schema = _pg(["pg_dump", "-s", "-t", f"public.{parent}"])
        if schema.returncode != 0:
            raise RuntimeError(f"schema dump failed: {schema.stderr[:200]}")
        r = _pg(["psql", "-d", scratch, "-v", "ON_ERROR_STOP=1"], input=schema.stdout)
        if r.returncode != 0:
            raise RuntimeError(f"schema restore failed: {r.stderr[:300]}")
        # pre-data + data only: the check is row fidelity (count, id range).
        # Replaying post-data against a parent that already cascaded its
        # constraint onto the attached child duplicates the constraint and
        # aborts the restore — measured 2026-08-07, and exactly why a real
        # re-attach restore is documented as data sections + explicit ATTACH.
        r = _pg(["pg_restore", "-d", scratch, "--section=pre-data",
                 "--section=data", dump_ctr])
        if r.returncode != 0:
            raise RuntimeError(f"pg_restore failed: {r.stderr[:300]}")
        r = _pg(["psql", "-d", scratch, "-tA", "-c",
                 f"select count(*), coalesce(min(id),0), coalesce(max(id),0) from {part}"])
        if r.returncode != 0:
            raise RuntimeError(f"verify query failed: {r.stderr[:200]}")
        n, lo, hi = r.stdout.strip().split("|")
        if int(n) != int(n_live) or int(lo) != int(id_lo or 0) or int(hi) != int(id_hi or 0):
            raise RuntimeError(
                f"VERIFY FAILED for {part}: restored ({n}, {lo}, {hi}) vs live "
                f"({n_live}, {id_lo}, {id_hi}) — partition NOT detached"
            )
        log.info("dump_verified", partition=part, rows=int(n))
    finally:
        _pg(["dropdb", "--if-exists", scratch])


# --------------------------------------------------------------------------- #
# Supabase rolling window — approved 2026-08-07 (manager), flow emergency
# --------------------------------------------------------------------------- #
#
# The primary database grows ~59 MB/day against a 500 MB cap with no cold
# stock to shed (measured 2026-08-07: nothing older than 14 days exists).
# So the mitigation is a rolling window: every ~3 days, archive-then-delete
# rows older than 72 hours from the three big tables, then VACUUM FULL
# (the enforced number is the *reported* size, which DELETE alone never
# shrinks). The same invariant as the monthly local job: a verified dump
# exists before any row is deleted, receipts in retention_log, and any
# verification failure aborts untouched AND pushes to the phone.
#
# `kalshi_snapshots` is deliberately NOT in this list: the pre-registered
# venue-gap gate counts matched games by joining kalshi_snapshots, and
# deleting old rows would silently un-count games already banked toward the
# 10-game gate. Its ~10 MB/day is budgeted instead.
#
# "Log every prediction, forever" (design rule 3) is preserved in letter and
# spirit: every prediction row lives on in the verified archive; the live
# table holds the working set the dashboard and resolution job actually read.

ROLLING_TABLES = ("book_levels", "predictions", "market_snapshots")
ROLLING_KEEP_HOURS = 72
ROLLING_EVERY_DAYS = 3


#: How rows are aged per table. book_levels has no reliable own timestamp on
#: the pregame path (captured_at NULL), so it ages through its parent snapshot.
_ROLLING_AGE = {
    "predictions": "created_at < :cutoff",
    "market_snapshots": "captured_at < :cutoff",
    "book_levels": ("snapshot_id in (select id from market_snapshots "
                    "where captured_at < :cutoff)"),
}


def _remote_conn_args() -> list[str]:
    """psql/pg_dump args for the PRIMARY database, parsed from DATABASE_URL."""
    from urllib.parse import urlparse

    from core.storage.base import get_database_url

    url = get_database_url()
    if "localhost" in url or "127.0.0.1" in url or "@postgres:" in url:
        raise RuntimeError(
            "DATABASE_URL points at local Postgres — the rolling job is for "
            "the primary; the local tick archive has its own monthly job"
        )
    p = urlparse(url.split("+psycopg", 1)[0].replace("postgresql", "postgresql", 1)
                 if "+psycopg" in url else url)
    if "+psycopg" in url:
        p = urlparse(url.replace("+psycopg", "", 1))
    return (["env", f"PGPASSWORD={p.password}"],
            ["-h", p.hostname, "-p", str(p.port or 5432), "-U", p.username,
             "-d", p.path.lstrip("/")])


def _pg_remote(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    """A pg client command inside the compose container, against the PRIMARY."""
    env, conn = _remote_conn_args()
    return subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres"] + env
        + [cmd[0]] + conn + cmd[1:],
        capture_output=True, text=True, timeout=3600, **kw)


def _push_alert(title: str, body: str) -> None:
    """Immediate phone push on verification failure — approval condition #2."""
    import os

    topic = (os.environ.get("MERIDIAN_NTFY_TOPIC") or "").strip()
    if not topic:
        log.error("rolling_alert_no_topic", title=title)
        return
    try:
        from core.alerter import Notifier

        Notifier(topic).push(title, body, priority="urgent", tags="rotating_light")
    except Exception as exc:
        log.error("rolling_alert_push_failed", error=str(exc)[:200])


def rolling_due(engine, now: dt.datetime | None = None) -> bool:
    """True when the last rolling run is older than ROLLING_EVERY_DAYS.

    Stateless on purpose: the receipts ARE the state, so a rebuilt container
    or a second host cannot double-schedule or lose the cadence.
    """
    now = now or dt.datetime.now(UTC)
    with engine.connect() as c:
        last = c.execute(text(
            "select max(created_at) from retention_log "
            "where partition_name like '%-rolling-%'"
        )).scalar()
    return last is None or last < now - dt.timedelta(days=ROLLING_EVERY_DAYS)


def rolling_run(engine, *, now: dt.datetime | None = None) -> list[dict]:
    """One rolling pass: dump all three, verify all three, only then delete.

    Two phases on purpose — every table's archive is verified before ANY
    table loses a row, so a failure in the third dump cannot strand the first
    table already-deleted.
    """
    now = now or dt.datetime.now(UTC)
    cutoff = now - dt.timedelta(hours=ROLLING_KEEP_HOURS)
    stamp = now.strftime("%Y%m%dT%H%M")
    supabase_dir().mkdir(parents=True, exist_ok=True)

    # ---- phase 1: measure, dump, verify (read-only against the primary) --- #
    plans: list[dict] = []
    scratch = "meridian_rolling_verify"
    _pg(["dropdb", "--if-exists", scratch])
    r = _pg(["createdb", scratch])
    if r.returncode != 0:
        raise RuntimeError(f"createdb failed: {r.stderr[:200]}")
    try:
        with engine.connect() as c:
            c.execute(text("set statement_timeout = '300s'"))
            for tbl in ROLLING_TABLES:
                n_old = c.execute(
                    text(f"select count(*) from {tbl} where {_ROLLING_AGE[tbl]}"),
                    {"cutoff": cutoff},
                ).scalar() or 0
                size = c.execute(text(
                    f"select pg_total_relation_size('{tbl}')")).scalar() or 0
                plans.append({"table": tbl, "rows_to_archive": int(n_old),
                              "size_before": int(size)})

        # CSV COPY, not pg_dump: the primary runs PG 17 and the container's
        # client is 16 — pg_dump refuses a newer server outright (hit live
        # 2026-08-07, verification aborted untouched, exactly as designed).
        # psql's \copy is version-agnostic, CSV is readable forever (a virtue
        # in an archive format), and only the >cutoff slice is exported, which
        # also halves the Supabase egress the dumps cost.
        cutoff_lit = f"'{cutoff:%Y-%m-%d %H:%M:%S%z}'"
        for tbl in ROLLING_TABLES:
            # Scratch gets the LOCAL table's schema — same columns; the local
            # stream tables are partitioned parents, so give each a DEFAULT
            # partition to receive whatever the CSV holds.
            schema = _pg(["pg_dump", "-s", "-t", f"public.{tbl}"])
            if schema.returncode != 0:
                raise RuntimeError(f"schema dump {tbl} failed: {schema.stderr[:200]}")
            r = _pg(["psql", "-d", scratch, "-v", "ON_ERROR_STOP=1"],
                    input=schema.stdout)
            if r.returncode != 0:
                raise RuntimeError(f"schema restore {tbl} failed: {r.stderr[:300]}")
            _pg(["psql", "-d", scratch, "-c",
                 f"create table {tbl}_vdefault partition of {tbl} default"])
            # (fails harmlessly for unpartitioned tables like predictions)
            #
            # The scratch is a counting vessel, not a database: the LOCAL
            # schema's (id, captured_at) PK forbids the NULL captured_at that
            # the REMOTE's pregame book rows legitimately carry, so relax it.
            for ddl in (f"alter table {tbl} drop constraint if exists {tbl}_pkey",
                        f"alter table {tbl} drop constraint if exists {tbl}_new_pkey",
                        f"alter table {tbl} alter column captured_at drop not null"):
                _pg(["psql", "-d", scratch, "-c", ddl])

        for plan in plans:
            tbl = plan["table"]
            # Staged inside the ticks mount (the only path the container can
            # write that the host can see), moved to backups/supabase/ after
            # the whole verification phase passes.
            dump_name = f"{tbl}-rolling-{stamp}.csv"
            dump_ctr = f"{BACKUP_DIR_CONTAINER}/{dump_name}"
            staging = ticks_dir() / dump_name
            pred = _ROLLING_AGE[tbl].replace(":cutoff", cutoff_lit)
            r = _pg_remote(["psql", "-v", "ON_ERROR_STOP=1", "-c",
                            f"\\copy (select * from {tbl} where {pred}) "
                            f"to '{dump_ctr}' with (format csv)"])
            if r.returncode != 0:
                raise RuntimeError(f"export {tbl} failed: {r.stderr[:300]}")
            if not staging.exists():
                raise RuntimeError(f"export for {tbl} not visible at {staging}")
            # Load into local scratch. The verification set is CLOSED: rows
            # older than the cutoff can neither appear nor vanish (timestamps
            # are set at insert, nothing else deletes), so an exact count match
            # is meaningful even while the live table keeps taking writes.
            r = _pg(["psql", "-d", scratch, "-v", "ON_ERROR_STOP=1", "-c",
                     f"\\copy {tbl} from '{dump_ctr}' with (format csv)"])
            if r.returncode != 0:
                raise RuntimeError(f"verify load {tbl} failed: {r.stderr[:300]}")
            plan["staging"] = staging
            plan["dump_name"] = dump_name

        # book_levels verification joins market_snapshots, so counts run after
        # every table is restored.
        for plan in plans:
            tbl = plan["table"]
            r = _pg(["psql", "-d", scratch, "-tA", "-c",
                     f"select count(*) from {tbl} where "
                     + _ROLLING_AGE[tbl].replace(
                         ":cutoff", f"'{cutoff:%Y-%m-%d %H:%M:%S%z}'")])
            if r.returncode != 0:
                raise RuntimeError(f"verify count {tbl} failed: {r.stderr[:200]}")
            restored = int(r.stdout.strip() or 0)
            if restored != plan["rows_to_archive"]:
                raise RuntimeError(
                    f"VERIFY FAILED for {tbl}: restored {restored} old rows vs "
                    f"{plan['rows_to_archive']} live — NOTHING deleted"
                )
            log.info("rolling_dump_verified", table=tbl, rows=restored)

        # All three verified: move the dumps to their permanent home and seal
        # them (path + sha recorded in the receipt below).
        for plan in plans:
            final = supabase_dir() / plan["dump_name"]
            plan["staging"].replace(final)
            plan["dump_path"] = str(final)
            plan["dump_bytes"] = final.stat().st_size
            plan["sha256"] = _sha256(final)
            del plan["staging"], plan["dump_name"]
    except Exception as exc:
        _push_alert("Supabase rolling archive FAILED (nothing deleted)",
                    str(exc)[:400])
        raise
    finally:
        _pg(["dropdb", "--if-exists", scratch])

    # ---- phase 2: receipts, deletes, VACUUM FULL smallest-first ----------- #
    receipts = []
    for plan in plans:
        tbl = plan["table"]
        with engine.begin() as c:
            c.execute(text("""
                insert into retention_log
                  (table_name, partition_name, month_start, rows_archived,
                   dump_path, dump_bytes, dump_sha256, verified_at)
                values (:t, :p, :m, :n, :path, :bytes, :sha, now())
            """), {"t": tbl, "p": f"{tbl}-rolling-{stamp}", "m": cutoff,
                   "n": plan["rows_to_archive"], "path": plan["dump_path"],
                   "bytes": plan["dump_bytes"], "sha": plan["sha256"]})
        if plan["rows_to_archive"]:
            with engine.begin() as c:
                c.execute(text("set statement_timeout = '600s'"))
                deleted = c.execute(
                    text(f"delete from {tbl} where {_ROLLING_AGE[tbl]}"),
                    {"cutoff": cutoff},
                ).rowcount
            with engine.begin() as c:
                c.execute(text("""
                    update retention_log set detached_at = now(), dropped_at = now()
                    where partition_name = :p
                """), {"p": f"{tbl}-rolling-{stamp}"})
            log.info("rolling_deleted", table=tbl, rows=deleted)
        receipts.append(plan)

    # VACUUM FULL returns the space the cap actually enforces. Smallest
    # post-delete table first, so peak temp usage stays minimal.
    order = sorted(ROLLING_TABLES, key=lambda t: next(
        p["size_before"] for p in plans if p["table"] == t))
    vac_engine = engine.execution_options(isolation_level="AUTOCOMMIT")
    for tbl in order:
        try:
            with vac_engine.connect() as c:
                # A full rewrite of an 87 MB table can exceed the platform's
                # default statement timeout; lift it for this session only.
                c.execute(text("set statement_timeout = 0"))
                c.execute(text(f"vacuum full {tbl}"))
            log.info("rolling_vacuumed", table=tbl)
        except Exception as exc:
            _push_alert(f"VACUUM FULL {tbl} failed",
                        f"rows already archived+deleted safely; size not yet "
                        f"reclaimed: {str(exc)[:200]}")
    with engine.connect() as c:
        after = c.execute(text(
            "select pg_database_size(current_database())")).scalar()
    log.info("rolling_complete", db_mb_after=round((after or 0) / 1e6))
    return receipts


def rolling_if_due(now: dt.datetime | None = None) -> list[dict] | None:
    """The scheduler's entry point: run when due AND no game is live."""
    from core.storage import get_engine

    engine = get_engine()
    if not rolling_due(engine, now):
        return None
    if _game_live():
        log.info("rolling_deferred_game_live")
        return None
    return rolling_run(engine, now=now)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _game_live() -> bool:
    from core.healthchecks import todays_games

    return todays_games()[1]


def status(engine) -> dict:
    now = dt.datetime.now(UTC)
    out: dict = {"as_of": now.isoformat()}
    with engine.connect() as conn:
        for parent in PARENTS:
            if not is_partitioned(conn, parent):
                out[parent] = {"partitioned": False}
                continue
            parts = attached_partitions(conn, parent)
            default_rows = 0
            for p in parts:
                if p.is_default:
                    default_rows = conn.execute(
                        text(f"select count(*) from {p.name}")).scalar()
            months = [p.month for p in parts if p.month]
            out[parent] = {
                "partitioned": True,
                "partitions": sorted(p.name for p in parts),
                "default_rows": int(default_rows or 0),
                "archivable_now": [month_label(m) for m in
                                   detachable_months(months, now)],
            }
        try:
            rows = conn.execute(text(
                "select partition_name, rows_archived, verified_at, dropped_at "
                "from retention_log order by id desc limit 10"
            )).all()
            out["retention_log_tail"] = [
                {"partition": r[0], "rows": int(r[1]),
                 "verified_at": str(r[2]), "dropped_at": str(r[3])}
                for r in rows
            ]
        except Exception:
            out["retention_log_tail"] = "table missing — run alembic upgrade head"
    return out


def main() -> int:
    parser = argparse.ArgumentParser(prog="meridian-retention")
    parser.add_argument("command", choices=[
        "status", "migrate", "ensure", "archive", "supabase-rolling"])
    parser.add_argument("--yes", action="store_true",
                        help="required for migrate/archive — they change the database")
    parser.add_argument("--force-during-game", action="store_true")
    args = parser.parse_args()

    import json as _json
    import logging

    logging.basicConfig(format="%(message)s", stream=sys.stderr, level=logging.INFO)
    engine = create_engine(_local_url())

    if args.command == "status":
        print(_json.dumps(status(engine), indent=2))
        return 0

    if args.command == "supabase-rolling":
        if not args.yes:
            print("supabase-rolling deletes archived rows from the PRIMARY; "
                  "re-run with --yes", file=sys.stderr)
            return 2
        if _game_live() and not args.force_during_game:
            print("A GAME IS LIVE — VACUUM FULL locks tables the prediction "
                  "leg writes. Refusing.", file=sys.stderr)
            return 3
        from core.storage import get_engine as _ge

        receipts = rolling_run(_ge())
        print(_json.dumps({"rolling": receipts}, indent=2, default=str))
        return 0

    if args.command in ("migrate", "archive"):
        if not args.yes:
            print(f"{args.command} rewrites the tick archive; re-run with --yes",
                  file=sys.stderr)
            return 2
        if _game_live() and not args.force_during_game:
            print("A GAME IS LIVE — the conversion takes an exclusive lock and "
                  "the 200ms writer would drop ticks. Refusing. (Between slates "
                  "only; --force-during-game exists but should not be used.)",
                  file=sys.stderr)
            return 3

    if args.command == "migrate":
        copied = migrate(engine)
        print(_json.dumps({"copied": copied}, indent=2))
        return 0

    if args.command == "ensure":
        now = dt.datetime.now(UTC)
        months = [month_start(now), _add_months(month_start(now), 1),
                  _add_months(month_start(now), 2)]
        with engine.begin() as conn:
            created = {p: ensure_partitions(conn, p, months) for p in PARENTS}
        print(_json.dumps(created, indent=2))
        return 0

    if args.command == "archive":
        now = dt.datetime.now(UTC)
        receipts = []
        with engine.connect() as conn:
            months = [p.month for p in attached_partitions(conn, "market_snapshots")
                      if p.month]
        for ms in detachable_months(months, now):
            receipts += archive_month(engine, ms, now=now)
        print(_json.dumps({"archived": receipts}, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
