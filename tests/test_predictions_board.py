"""The prediction job must see pregame markets while a game is in flight.

The failure this pins
---------------------
`PredictionLogger.run()` took `max(captured_at)` and then filtered out live
markets. During a game the newest snapshot comes from the 200ms live recorder
and contains **only** live markets, so that filter emptied the list. The job
logged `no_pregame_markets`, wrote zero predictions, and returned successfully.

Measured: zero predictions between 19:30 and 21:56 — the whole duration of one
game — with the scheduler reporting `job_ok` on every cycle. No predictions
means no shadow orders, so nothing accrued toward v4's 50-resolved-bet gate,
and it would have recurred at every single tip-off.

Two things are tested here, and the second matters as much as the first: the
query must be right, *and* a run that does nothing must say so.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import delete, select

from core.board import is_pregame, latest_snapshot_per_market, snapshot_age_seconds
from core.predictions import PredictionStats
from core.storage import MarketSnapshot, get_engine, get_sessionmaker

UTC = dt.timezone.utc

LIVE = "tsc-wnba-predtest-live-100pt5"
PREGAME = "tsc-wnba-predtest-pre-200pt5"


@pytest.fixture
def board():
    """The exact shape that broke: a 200ms live row, a 15-minute-old pregame row."""
    Session = get_sessionmaker(get_engine())
    now = dt.datetime.now(UTC)

    def _wipe(s):
        s.execute(
            delete(MarketSnapshot).where(MarketSnapshot.market_slug.like("%predtest%"))
        )
        s.commit()

    rows = [
        # Live recorder, 0.2s ago, in-flight game.
        dict(
            captured_at=now - dt.timedelta(seconds=0.2),
            market_slug=LIVE, event_slug="wnba-predtest-live",
            sports_market_type="basketball_team_full_game_total",
            line=Decimal("100.5"), best_bid=Decimal("0.50"), best_ask=Decimal("0.52"),
            game_start_time=now - dt.timedelta(hours=1), is_live=True,
        ),
        # Pregame recorder, 15 minutes ago. The row the old query dropped.
        dict(
            captured_at=now - dt.timedelta(minutes=15),
            market_slug=PREGAME, event_slug="wnba-predtest-pre",
            sports_market_type="basketball_team_full_game_total",
            line=Decimal("200.5"), best_bid=Decimal("0.48"), best_ask=Decimal("0.51"),
            game_start_time=now + dt.timedelta(hours=3), is_live=False,
        ),
    ]
    with Session() as s:
        _wipe(s)
        for row in rows:
            s.add(MarketSnapshot(**row))
        s.commit()
    yield Session, now
    with Session() as s:
        _wipe(s)


def _slugs(snaps):
    return {s.market_slug for s in snaps if "predtest" in s.market_slug}


# ------------------------------------------------------------------ #
# The regression
# ------------------------------------------------------------------ #


def test_pregame_market_survives_a_live_game(board):
    """With a live-only newest cycle, the pregame market must still be found."""
    Session, now = board
    with Session() as s:
        snaps = latest_snapshot_per_market(s, as_of=now)
        pregame = _slugs([x for x in snaps if is_pregame(x, as_of=now)])

    assert PREGAME in pregame, (
        "the pregame market was written 15 min ago and the newest cycle holds "
        "only the live game — this is the bug that stopped ANCHOR"
    )
    assert LIVE not in pregame, "an in-flight game must never be priced"


def test_the_old_query_shape_would_have_found_nothing(board):
    """Demonstrates the defect, so the fix is not merely asserted."""
    from sqlalchemy import func

    Session, now = board
    with Session() as s:
        newest = s.scalar(select(func.max(MarketSnapshot.captured_at)))
        old_shape = s.scalars(
            select(MarketSnapshot).where(MarketSnapshot.captured_at == newest)
        ).all()
        pregame_under_old = [
            m for m in old_shape if "predtest" in m.market_slug and not m.is_live
        ]
    assert pregame_under_old == [], (
        "the old query really did yield zero pregame markets during a game"
    )


def test_a_just_tipped_game_is_not_priced_from_a_stale_flag(board):
    """`is_live` is only as fresh as the row carrying it.

    Right after tip-off the pregame recorder's last sweep still says
    `is_live=False` for a game that is already running. Checking the start time
    as well is what stops a game in flight being priced.
    """
    Session, now = board
    with Session() as s:
        s.add(MarketSnapshot(
            captured_at=now - dt.timedelta(minutes=14),
            market_slug="tsc-wnba-predtest-justtipped-1pt5",
            event_slug="wnba-predtest-justtipped",
            sports_market_type="basketball_team_full_game_total",
            line=Decimal("1.5"), best_bid=Decimal("0.5"), best_ask=Decimal("0.52"),
            game_start_time=now - dt.timedelta(minutes=5),   # already started
            is_live=False,                                   # but the flag is stale
        ))
        s.commit()
        snaps = latest_snapshot_per_market(s, as_of=now)
        pregame = _slugs([x for x in snaps if is_pregame(x, as_of=now)])

    assert "tsc-wnba-predtest-justtipped-1pt5" not in pregame


def test_snapshot_age_is_measured_against_the_run_not_the_row(board):
    Session, now = board
    with Session() as s:
        snaps = {m.market_slug: m for m in latest_snapshot_per_market(s, as_of=now)}

    assert snapshot_age_seconds(snaps[LIVE], as_of=now) < 5
    assert snapshot_age_seconds(snaps[PREGAME], as_of=now) > 600


# ------------------------------------------------------------------ #
# Silent success — the more dangerous half
# ------------------------------------------------------------------ #


def test_run_that_had_work_and_wrote_nothing_is_not_ok():
    """The exact condition that reported job_ok for two and a half hours."""
    stats = PredictionStats()
    stats.markets_on_board = 131
    stats.pregame_markets = 40
    stats.quotable_markets = 40
    stats.predictions_written = 0
    assert stats.ok is False


def test_a_board_of_only_live_games_is_legitimately_quiet():
    """During a full slate there is genuinely nothing to price — not a fault."""
    stats = PredictionStats()
    stats.markets_on_board = 18
    stats.pregame_markets = 0
    stats.quotable_markets = 0
    stats.predictions_written = 0
    assert stats.ok is True


def test_a_run_that_wrote_something_is_ok():
    stats = PredictionStats()
    stats.quotable_markets = 40
    stats.predictions_written = 40
    assert stats.ok is True


def test_summary_reports_the_counts_needed_to_diagnose():
    stats = PredictionStats()
    stats.markets_on_board = 131
    stats.quotable_markets = 40
    stats.predictions_written = 0
    keys = stats.summary
    for field in ("markets_on_board", "pregame", "quotable", "written", "stale"):
        assert field in keys


def test_scheduler_logs_degraded_rather_than_ok(monkeypatch):
    """A job that returns without error but did nothing must not read as healthy."""
    from core import scheduler

    events = []
    monkeypatch.setattr(
        scheduler.log, "info", lambda ev, **kw: events.append(("info", ev))
    )
    monkeypatch.setattr(
        scheduler.log, "warning", lambda ev, **kw: events.append(("warning", ev))
    )
    monkeypatch.setattr(
        scheduler.log, "error", lambda ev, **kw: events.append(("error", ev))
    )

    idle = PredictionStats()
    idle.quotable_markets = 40
    idle.predictions_written = 0
    scheduler._safe("predictions", lambda: idle)
    assert ("warning", "job_degraded") in events

    events.clear()
    healthy = PredictionStats()
    healthy.quotable_markets = 40
    healthy.predictions_written = 40
    scheduler._safe("predictions", lambda: healthy)
    assert ("info", "job_ok") in events


def test_scheduler_still_reports_ok_for_jobs_that_return_nothing(monkeypatch):
    """Opt-in: jobs with no health signal are unchanged."""
    from core import scheduler

    events = []
    monkeypatch.setattr(
        scheduler.log, "info", lambda ev, **kw: events.append(("info", ev))
    )
    scheduler._safe("stats", lambda: None)
    assert ("info", "job_ok") in events
