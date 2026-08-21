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

_Session = get_sessionmaker(get_engine())


@pytest.fixture(scope="module", autouse=True)
def partitioned_db():
    """Run the REAL conversion on the suite's per-run database.

    The conftest gives every run a fresh alembic-created database, which is
    unpartitioned — so this fixture exercises `migrate()` itself (rename-away,
    copy, swap, count-verify) on a disposable target, and the routing tests
    below then run against genuinely partitioned tables. On the operator's
    converted mirror it is a no-op.
    """
    from core.retention import migrate

    with get_engine().connect() as c:
        already = is_partitioned(c, "market_snapshots")
    if not already:
        migrate(get_engine())
    yield


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


def _snap(captured_at):
    return MarketSnapshot(
        captured_at=captured_at, market_slug=SLUG,
        sports_market_type="basketball_team_full_game_total",
        best_bid=Decimal("0.5"), best_ask=Decimal("0.52"), is_live=True,
    )


@needs_partitions
def test_rows_route_to_their_month_partition(clean_rows):
    aug = dt.datetime(2026, 8, 3, 1, 0, tzinfo=UTC)
    with _Session() as s:
        s.add(_snap(aug))
        s.commit()
        part = s.execute(text(
            "select tableoid::regclass::text from market_snapshots "
            "where market_slug = :m"), {"m": SLUG}).scalar()
    assert part == "market_snapshots_y2026m08"


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

    at = dt.datetime(2026, 8, 3, 2, 0, tzinfo=UTC)
    values = dict(captured_at=at, market_slug=SLUG, is_live=True)
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

    at = dt.datetime(2026, 8, 3, 3, 0, tzinfo=UTC)
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
    assert part == "book_levels_y2026m08"
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
