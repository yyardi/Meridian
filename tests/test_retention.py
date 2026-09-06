"""Retention: month arithmetic, partition routing, and the writers' idempotency
guarantees surviving the conversion.

The pure functions are tested unconditionally. The routing tests run only when
the local database has actually been converted (`migrate --yes` is an explicit
operator step, not something a test may trigger) — on an unconverted database
they skip rather than fail, and say why.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import delete, select, text

from core.retention import (
    KEEP_DAYS,
    detachable_months,
    is_partitioned,
    month_label,
    month_start,
    months_covering,
    next_month,
    partition_name,
)
from core.storage import BookLevel, MarketSnapshot, get_engine, get_sessionmaker

UTC = dt.timezone.utc
REPO = Path(__file__).resolve().parent.parent


# ------------------------------------------------------------------ #
# Month arithmetic
# ------------------------------------------------------------------ #


def test_month_boundaries():
    assert month_start(dt.datetime(2026, 8, 7, 23, 59, tzinfo=UTC)) == \
        dt.datetime(2026, 8, 1, tzinfo=UTC)
    assert next_month(dt.datetime(2026, 12, 1, tzinfo=UTC)) == \
        dt.datetime(2027, 1, 1, tzinfo=UTC)
    assert month_label(dt.datetime(2026, 8, 1, tzinfo=UTC)) == "y2026m08"
    assert partition_name("market_snapshots", dt.datetime(2026, 8, 1, tzinfo=UTC)) \
        == "market_snapshots_y2026m08"


def test_months_covering_spans_inclusive():
    months = months_covering(
        dt.datetime(2026, 7, 31, tzinfo=UTC), dt.datetime(2026, 10, 2, tzinfo=UTC)
    )
    assert [m.month for m in months] == [7, 8, 9, 10]


def test_detachable_requires_the_whole_month_outside_the_keep_window():
    """A month qualifies only when its END is past the cutoff — one row
    younger than KEEP_DAYS keeps the whole partition attached."""
    now = dt.datetime(2026, 8, 15, tzinfo=UTC)
    july = dt.datetime(2026, 7, 1, tzinfo=UTC)
    june = dt.datetime(2026, 6, 1, tzinfo=UTC)
    # cutoff = July 16: July's end (Aug 1) is after it -> July stays.
    assert detachable_months([june, july], now, keep_days=KEEP_DAYS) == [june]
    # Sept 1: July's end (Aug 1) <= Aug 2 cutoff -> July becomes eligible.
    later = dt.datetime(2026, 9, 1, tzinfo=UTC)
    assert detachable_months([june, july], later, keep_days=KEEP_DAYS) == [june, july]


def test_nothing_recent_is_ever_detachable():
    now = dt.datetime(2026, 8, 15, tzinfo=UTC)
    this_month = month_start(now)
    assert detachable_months([this_month], now) == []


# ------------------------------------------------------------------ #
# Routing on the real (converted) database
# ------------------------------------------------------------------ #

#: Set by `partitioned_db` — the CONVERTED database's engine/sessionmaker.
#: Not the suite's: see that fixture for why the conversion cannot share one.
_conv: dict = {}


def _engine():
    return _conv["engine"]


def _Session():
    return _conv["Session"]()


def _indexes(conn, table: str) -> dict[str, str]:
    """{name: shape} for every PLAIN index on `table`.

    Constraint-backed indexes are excluded: the primary key deliberately
    CHANGES shape in the conversion (a partitioned table's PK must contain the
    partition key) and the unique constraints are declared explicitly by
    `migrate()`, with their own test below. What is left is exactly the set
    that used to be hand-copied into `_SNAPSHOT_INDEXES`.

    `shape` is the definition from `USING` onward, so it carries the access
    method, the columns AND the partial predicate — a plain index under a
    partial index's name is a different index, not the same one.
    """
    rows = conn.execute(text("""
        SELECT c.relname, pg_get_indexdef(c.oid)
        FROM pg_index x
        JOIN pg_class c ON c.oid = x.indexrelid
        JOIN pg_class t ON t.oid = x.indrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname = 'public' AND t.relname = :t
          AND NOT x.indisprimary
          AND NOT EXISTS (SELECT 1 FROM pg_constraint k
                          WHERE k.conindid = x.indexrelid)
    """), {"t": table}).all()
    return {name: d[d.index(" USING "):] for name, d in rows}


@pytest.fixture(scope="module", autouse=True)
def partitioned_db():
    """Run the REAL conversion — on a database of THIS MODULE'S OWN.

    `migrate()` is one-way and destructive: it rebuilds market_snapshots and
    book_levels as partitioned tables, and Postgres marks a range-partition
    key NOT NULL. Run against the suite's shared per-run database, that
    leaked into every test that collected after it. `test_wallet_depth_join`
    deliberately writes a NULL `captured_at` to model the legacy
    fetched-together rows, and became 7 collection ERRORS the moment
    retention converted the database first (r < w alphabetically). Those
    seven tests pass in isolation and had stopped running in every full run.

    The same leak is why nothing caught `_SNAPSHOT_INDEXES` dropping the
    tipoff partial indexes: the only test that asserts them
    (test_picks_tipoff) ran BEFORE the conversion and never saw a converted
    table.

    So the conversion gets its own database, created next to the suite's on
    the same server and dropped afterwards. Nothing outside this module can
    observe it. On the operator's already-converted mirror the fixture is a
    no-op and yields {}.

    Yields the pre-conversion index sets, or {} when there was nothing to
    convert.
    """
    import os

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    from core.retention import migrate
    from core.storage import get_database_url

    suite_url = get_database_url()
    with get_engine().connect() as c:
        if is_partitioned(c, "market_snapshots"):
            _conv["engine"] = get_engine()
            _conv["Session"] = get_sessionmaker(get_engine())
            yield {}
            return

    base, _ = suite_url.rsplit("/", 1)
    name = f"meridian_retention_{os.getpid()}"
    url = f"{base}/{name}"
    admin = create_engine(suite_url, isolation_level="AUTOCOMMIT",
                          pool_size=1, max_overflow=0)
    with admin.connect() as c:
        c.execute(text(f'drop database if exists "{name}" with (force)'))
        c.execute(text(f'create database "{name}"'))

    # alembic/env.py reads DATABASE_URL, so point it at the new database for
    # the upgrade and put it back immediately.
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        cfg = Config(str(REPO / "alembic.ini"))
        command.upgrade(cfg, "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous

    engine = create_engine(url)
    _conv["engine"] = engine
    _conv["Session"] = get_sessionmaker(engine)
    with engine.connect() as c:
        before = {t: _indexes(c, t)
                  for t in ("market_snapshots", "book_levels")}
    migrate(engine)
    try:
        yield before
    finally:
        engine.dispose()
        with admin.connect() as c:
            c.execute(text(f'drop database if exists "{name}" with (force)'))
        admin.dispose()


needs_partitions = pytest.mark.usefixtures("partitioned_db")

SLUG = "tsc-retention-test-144pt5"


@pytest.fixture
def clean_rows():
    def _wipe(s):
        s.execute(delete(BookLevel).where(BookLevel.snapshot_id.in_(
            select(MarketSnapshot.id).where(MarketSnapshot.market_slug == SLUG))))
        s.execute(delete(MarketSnapshot).where(MarketSnapshot.market_slug == SLUG))
        s.commit()

    with _Session() as s:
        _wipe(s)
    yield
    with _Session() as s:
        _wipe(s)


#: A timestamp inside a month the conversion actually creates. `migrate()`
#: covers [min(captured_at) … now] plus MONTHS_AHEAD, so on the suite's EMPTY
#: per-run database that set STARTS at the current month — anything earlier
#: routes to `_default`. These tests were written in August 2026 with the
#: month hardcoded, and began failing on 2026-09-01 for that reason alone.
#: Deriving the month from the clock is what they always meant.
_MONTH = month_start(dt.datetime.now(UTC))
_SNAPS_PARTITION = partition_name("market_snapshots", _MONTH)
_BOOK_PARTITION = partition_name("book_levels", _MONTH)


def _in_month(hour: int) -> dt.datetime:
    """Day 3 of the current month — every month has one."""
    return _MONTH + dt.timedelta(days=2, hours=hour)


def _snap(captured_at):
    return MarketSnapshot(
        captured_at=captured_at, market_slug=SLUG,
        sports_market_type="basketball_team_full_game_total",
        best_bid=Decimal("0.5"), best_ask=Decimal("0.52"), is_live=True,
    )


def test_every_index_survives_the_conversion(partitioned_db):
    """The conversion rebuilds the table; whatever it does not rebuild is
    GONE, silently, on the operator's mirror.

    2026-09-05: `_SNAPSHOT_INDEXES` was a hand-kept copy of the table's index
    set, and migration f3a8c1d92e47's two partial indexes — the ones that took
    /api/picks from 4.75s to 0.42s in production — were never added to it. A
    conversion would have dropped them and nothing would have said so; the
    only symptom is the page getting slow again.

    Compared by SHAPE, not just by name: a plain index under a partial
    index's name reintroduces the full scan the partial one exists to
    prevent."""
    if not partitioned_db:
        pytest.skip("database was already partitioned — no before-state to "
                    "compare against")
    with _engine().connect() as c:
        for table, before in partitioned_db.items():
            after = _indexes(c, table)
            # A partitioned parent's indexes read as ON ONLY the parent.
            norm = {n: d.replace(" ONLY ", " ") for n, d in after.items()}
            for name, shape in before.items():
                assert name in norm, (
                    f"{table}.{name} did not survive the partition conversion")
                assert norm[name] == shape.replace(" ONLY ", " "), (
                    f"{table}.{name} came back a different index:\n"
                    f"  before: {shape}\n  after:  {norm[name]}")


@needs_partitions
def test_rows_route_to_their_month_partition(clean_rows):
    with _Session() as s:
        s.add(_snap(_in_month(1)))
        s.commit()
        part = s.execute(text(
            "select tableoid::regclass::text from market_snapshots "
            "where market_slug = :m"), {"m": SLUG}).scalar()
    assert part == _SNAPS_PARTITION


@needs_partitions
def test_a_month_with_no_partition_lands_in_default_not_an_error(clean_rows):
    """The safety net: a missed maintenance run must never cost a row."""
    far = dt.datetime(2031, 1, 5, tzinfo=UTC)
    with _Session() as s:
        s.add(_snap(far))
        s.commit()
        part = s.execute(text(
            "select tableoid::regclass::text from market_snapshots "
            "where market_slug = :m"), {"m": SLUG}).scalar()
    assert part == "market_snapshots_default"


@needs_partitions
def test_on_conflict_idempotency_survives_partitioning(clean_rows):
    """The recorders' rerun guarantee rides `uq_snapshot_market_time` by name;
    the conversion must keep both the name and the semantics."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    values = dict(captured_at=_in_month(2), market_slug=SLUG, is_live=True)
    with _Session() as s:
        for _ in range(2):
            s.execute(pg_insert(MarketSnapshot).values(**values)
                      .on_conflict_do_nothing(constraint="uq_snapshot_market_time"))
        s.commit()
        n = s.execute(text(
            "select count(*) from market_snapshots where market_slug = :m"),
            {"m": SLUG}).scalar()
    assert n == 1


@needs_partitions
def test_book_levels_partitioned_and_unique_constraint_survives(clean_rows):
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    at = _in_month(3)
    with _Session() as s:
        s.add(_snap(at))
        s.commit()
        sid = s.execute(select(MarketSnapshot.id).where(
            MarketSnapshot.market_slug == SLUG)).scalar()
        row = dict(snapshot_id=sid, side="bid", price=Decimal("0.5"),
                   quantity=Decimal("10"), level_index=0, captured_at=at)
        for _ in range(2):
            s.execute(pg_insert(BookLevel).values(**row)
                      .on_conflict_do_nothing(constraint="uq_book_level"))
        s.commit()
        part, n = s.execute(text(
            "select tableoid::regclass::text, count(*) from book_levels "
            "where snapshot_id = :s group by 1"), {"s": sid}).one()
    assert part == _BOOK_PARTITION
    assert n == 1


# ------------------------------------------------------------------ #
# Swap verification (live-table semantics)
# ------------------------------------------------------------------ #


def _swap_fixture(conn, preswap_ids, parent_ids):
    """Two throwaway tables shaped like a parent and its *_preswap sibling."""
    conn.execute(text("drop table if exists vs_parent, vs_parent_preswap"))
    conn.execute(text("create table vs_parent (id bigint primary key)"))
    conn.execute(text("create table vs_parent_preswap (id bigint primary key)"))
    for tbl, ids in (("vs_parent_preswap", preswap_ids), ("vs_parent", parent_ids)):
        if ids:
            vals = ",".join(f"({i})" for i in ids)
            conn.execute(text(f"insert into {tbl} (id) values {vals}"))


@pytest.mark.parametrize(
    "post_swap_writes", [0, 5], ids=["quiesced", "live_writer"]
)
def test_verify_swap_ignores_rows_written_after_the_swap(post_swap_writes):
    """The regression this replaces: on a live server the recorder keeps
    writing, so the parent is legitimately LARGER than *_preswap. The old
    `count == count` check called that corruption and refused to clean up."""
    from core.retention import verify_swap

    engine = get_engine()
    preswap = list(range(1, 101))
    parent = preswap + [100 + i for i in range(1, post_swap_writes + 1)]
    with engine.begin() as conn:
        _swap_fixture(conn, preswap, parent)
        rows, written_after = verify_swap(conn, "vs_parent")
        conn.execute(text("drop table vs_parent, vs_parent_preswap"))

    assert rows == 100
    assert written_after == post_swap_writes


def test_verify_swap_still_catches_a_row_that_did_not_survive():
    """The check must not have been loosened into uselessness: a row missing
    from BELOW the boundary is real data loss and must still raise."""
    from core.retention import verify_swap

    engine = get_engine()
    preswap = list(range(1, 101))
    parent = [i for i in preswap if i != 42] + [101, 102]  # 42 lost, 2 new
    with engine.begin() as conn:
        _swap_fixture(conn, preswap, parent)
        with pytest.raises(RuntimeError, match="BOTH TABLES KEPT"):
            verify_swap(conn, "vs_parent")
    with engine.begin() as conn:
        conn.execute(text("drop table vs_parent, vs_parent_preswap"))
