"""rows_written=0 has two causes; only markets_seen separates them.

On 2026-09-14 the venue's entire board emptied at 09:35Z. Every container stayed
up, every log stayed clean, every heartbeat kept beating, and no quantity in this
database could distinguish "the board is empty" from "the board is full and no
price moved". Both write zero rows.

The tests that matter here are the two zero cases. A test that only checks a
non-zero value passes on a column that is never read and never distinguishes
anything, which is the defect this column exists to fix.
"""
from __future__ import annotations

import sqlalchemy as sa

from core.heartbeat import Heartbeat
from core.storage import get_engine
from core.storage.models import ServiceHeartbeat


def _mk(session_factory, service):
    return Heartbeat(session_factory, service)


def _read(service):
    with get_engine().connect() as c:
        return c.execute(sa.text(
            "SELECT rows_written, markets_seen FROM service_heartbeats WHERE service=:s"),
            {"s": service}).first()


def _sessionmaker():
    from sqlalchemy.orm import sessionmaker
    return sessionmaker(bind=get_engine())


def _clean(service):
    with get_engine().begin() as c:
        c.execute(sa.text("DELETE FROM service_heartbeats WHERE service=:s"), {"s": service})


def test_an_empty_board_and_a_quiet_board_are_now_different_rows():
    """The property under test, stated as the thing that failed today."""
    sm = _sessionmaker()
    for svc, seen in (("utest_empty_board", 0), ("utest_quiet_board", 450)):
        _clean(svc)
        assert _mk(sm, svc).beat(interval_seconds=600, rows_written=0, markets_seen=seen)
    empty, quiet = _read("utest_empty_board"), _read("utest_quiet_board")
    assert empty[0] == quiet[0] == 0, "both wrote nothing -- that is the whole problem"
    assert empty[1] == 0 and quiet[1] == 450, "and now they are distinguishable"
    for svc in ("utest_empty_board", "utest_quiet_board"):
        _clean(svc)


def test_not_measured_stays_null_and_is_not_zero():
    """A writer with no board (the scheduler) must not claim it saw zero markets.
    NULL means not measured; 0 means measured and empty. Collapsing them would
    make every scheduler beat look like a venue outage."""
    svc = "utest_no_board"
    _clean(svc)
    assert _mk(_sessionmaker(), svc).beat(interval_seconds=1200, rows_written=None)
    row = _read(svc)
    assert row[1] is None
    _clean(svc)


def test_the_column_exists_on_the_model_and_in_the_database():
    """Guards the guard: if the migration had not run, the writes above would
    have failed loudly, but a future refactor that drops the model attribute
    while leaving the column would not."""
    assert "markets_seen" in ServiceHeartbeat.__table__.columns
    with get_engine().connect() as c:
        cols = {r[0] for r in c.execute(sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='service_heartbeats'"))}
    assert "markets_seen" in cols
