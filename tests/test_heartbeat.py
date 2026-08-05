"""The per-cycle heartbeat, and the one rule that reads it (B11's fix).

What is under test, in the order it failed in production:

1. A stopped writer is DEAD within one check, **regardless of game state** —
   the 200ms recorder was dead for 23 hours while every reader said "idle
   between games, expected".
2. Between games, a fresh beat with zero rows is IDLE, not DEAD — otherwise
   the check cries wolf every night and trains the reader to ignore it.
3. A live game, a fresh beat, and zero rows is DEGRADED — alive and producing
   nothing is the B1 lesson (assert on outputs, not exit codes).
4. The beat is one upserted row per service: the table cannot grow, so the
   egress cost of honesty stays at one tiny statement per cycle.

Fixtures snapshot and restore `service_heartbeats` rather than deleting by
pattern — the table is keyed by real service names, and a running recorder may
own a row in it (the B6 lesson: fixture teardown must not eat real data).
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import delete, select

from core.heartbeat import (
    DEAD,
    DEGRADED,
    IDLE,
    MIN_STALE_SECONDS,
    OK,
    SERVICE_LIVE,
    Heartbeat,
    stale_after_seconds,
    verdict,
)
from core.storage import ServiceHeartbeat, get_engine, get_sessionmaker

UTC = dt.timezone.utc

TEST_SERVICE = "test_heartbeat_service"

_Session = get_sessionmaker(get_engine())


@pytest.fixture
def clean_table():
    """Snapshot every heartbeat row, hand the test a clean slate, restore after."""
    with _Session() as s:
        saved = [
            {c.name: getattr(row, c.name) for c in ServiceHeartbeat.__table__.columns}
            for row in s.execute(select(ServiceHeartbeat)).scalars()
        ]
        s.execute(delete(ServiceHeartbeat))
        s.commit()
    yield
    with _Session() as s:
        s.execute(delete(ServiceHeartbeat))
        for row in saved:
            s.add(ServiceHeartbeat(**row))
        s.commit()


def _row(session, service=TEST_SERVICE) -> ServiceHeartbeat | None:
    return session.get(ServiceHeartbeat, service)


# ------------------------------------------------------------------ #
# The rule
# ------------------------------------------------------------------ #


def test_a_stopped_writer_is_dead_regardless_of_game_state():
    """The B11 case. 23 hours of silence read as 'idle between games'."""
    day_old = 23 * 3600
    assert verdict(day_old, 15, game_live=False) == DEAD
    assert verdict(day_old, 15, game_live=True) == DEAD
    # Even at the writer's own idle cadence, 3x is the line.
    assert verdict(361, 120) == DEAD
    assert verdict(359, 120) != DEAD


def test_never_beaten_is_dead_not_unknown():
    """Ambiguity rounds toward DEAD: a missed outage loses games permanently,
    a false alarm costs a glance."""
    assert verdict(None, None) == DEAD
    assert verdict(None, 15) == DEAD


def test_idle_is_only_claimable_with_a_fresh_beat():
    """Fresh beat + no rows expected -> IDLE, not DEAD. This is what stops the
    check from crying wolf every night."""
    assert verdict(10, 120, game_live=False, rows_recent=0) == IDLE
    assert verdict(10, 120, game_live=False, rows_recent=None) == IDLE


def test_live_game_fresh_beat_zero_rows_is_degraded():
    """Alive and writing nothing — the state the old check called healthy."""
    assert verdict(0.5, 0.2, game_live=True, rows_recent=0) == DEGRADED
    assert verdict(0.5, 0.2, game_live=True, rows_recent=1500) == OK
    # rows None means "not measured" and must not fake a degradation.
    assert verdict(0.5, 0.2, game_live=True, rows_recent=None) == OK


def test_the_3x_rule_has_a_floor_for_subsecond_writers():
    """3 x 200ms = 600ms would flap on any GC pause; the floor absorbs that
    without hiding a real outage."""
    assert stale_after_seconds(0.2) == MIN_STALE_SECONDS
    assert verdict(MIN_STALE_SECONDS - 1, 0.2) != DEAD
    assert verdict(MIN_STALE_SECONDS + 1, 0.2) == DEAD
    # For slow writers the floor is irrelevant: 3x their interval dominates.
    assert stale_after_seconds(3600) == 3 * 3600


# ------------------------------------------------------------------ #
# The writer
# ------------------------------------------------------------------ #


def test_beat_upserts_one_row_that_never_grows(clean_table):
    hb = Heartbeat(_Session, TEST_SERVICE)
    assert hb.beat(interval_seconds=15, rows_written=3, cycle_seconds=0.4)
    assert hb.beat(interval_seconds=300, rows_written=2, cycle_seconds=0.1,
                   game_live=False)

    with _Session() as s:
        rows = s.execute(select(ServiceHeartbeat)).scalars().all()
        assert len(rows) == 1, "one row per service, updated in place"
        row = rows[0]
        assert row.service == TEST_SERVICE
        assert float(row.interval_seconds) == 300, "latest cadence wins"
        assert row.rows_written == 2
        assert row.rows_total == 5, "cumulative across beats"
        assert row.game_live is False


def test_beat_defaults_to_the_database_clock(clean_table):
    """A container with a skewed clock must not report itself alive into the
    future — beat_at comes from the database unless a test injects one."""
    Heartbeat(_Session, TEST_SERVICE).beat(interval_seconds=15)
    with _Session() as s:
        age = (dt.datetime.now(UTC) - _row(s).beat_at).total_seconds()
    assert abs(age) < 30


def test_beat_never_raises_when_the_database_is_gone():
    """A heartbeat that can kill its service is worse than no heartbeat."""
    from sqlalchemy import create_engine

    dead_db = get_sessionmaker(
        create_engine("postgresql+psycopg://nobody:nothing@127.0.0.1:1/void",
                      pool_pre_ping=False)
    )
    assert Heartbeat(dead_db, TEST_SERVICE).beat(interval_seconds=15) is False


# ------------------------------------------------------------------ #
# The live recorder beats with no game on
# ------------------------------------------------------------------ #


def test_live_recorder_beats_between_games(clean_table):
    """The whole point: the beat is unconditional. A cycle that saw no live
    markets still writes rows_written=0 / game_live=False — which is exactly
    the evidence 'idle' needs to be claimable."""
    from core.live_recorder import IDLE_POLL_SECONDS, LiveCycleStats, LiveRecorder

    rec = LiveRecorder(client=object(), sessionmaker=_Session, capture_depth=False)
    rec._heartbeat.service = TEST_SERVICE  # keep off any real recorder's row

    rec._beat_cycle(LiveCycleStats(), IDLE_POLL_SECONDS, cycle_seconds=0.05)

    with _Session() as s:
        row = _row(s)
    assert row is not None, "no game is not an excuse for no beat"
    assert row.rows_written == 0
    assert row.game_live is False
    assert float(row.interval_seconds) == IDLE_POLL_SECONDS
