"""A book anchor must be fresh, not merely present.

The failure this pins
---------------------
`anchored` was computed from the *existence* of a non-live book row, with no
age check. On 2026-08-04 the ESPN odds feed died for six hours; had games been
on, predictions would have kept flowing, shrunk toward a line hours old, and
been marked actionable. The outage fell between games — free, like every bug
so far — so the guard is built before the one that isn't.

The threshold is pre-registered: 60 minutes, chosen 2026-08-05 before any
measurement against it. The fast leg polls book lines every 20 minutes, so
60 minutes is three consecutive missed polls — a feed that is down, not one
between cycles.

Same policy as unanchored predictions: logged, flagged, never actionable, and
never silenced.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import delete

from core.predictions import (
    MAX_ANCHOR_AGE_SECONDS,
    PredictionStats,
    _anchor_staleness_note,
    _apply_anchor_guard,
    _book_consensus,
)
from core.storage import SportsbookOdds, get_engine, get_sessionmaker

UTC = dt.timezone.utc

#: Fake game key, wiped before and after each test.
GAME = "anchortest-9001"


@pytest.fixture
def session():
    Session = get_sessionmaker(get_engine())

    def _wipe(s):
        s.execute(delete(SportsbookOdds).where(SportsbookOdds.espn_game_id == GAME))
        s.commit()

    with Session() as s:
        _wipe(s)
        yield s
        _wipe(s)


def _odds_row(minutes_old: float, now: dt.datetime, provider: str = "consensus"):
    return SportsbookOdds(
        espn_game_id=GAME,
        provider_name=provider,
        captured_at=now - dt.timedelta(minutes=minutes_old),
        over_under=Decimal("162.5"),
        spread=Decimal("-3.5"),
    )


# ------------------------------------------------------------------ #
# The gate itself — the exact code path _predict_one runs
# ------------------------------------------------------------------ #


def test_fresh_anchor_leaves_actionable_unchanged():
    """A 20-minute-old line is one poll cycle — normal operation."""
    stats = PredictionStats()
    actionable, notes, stale = _apply_anchor_guard(
        actionable=True, notes=None, anchored=True,
        anchor_age_seconds=20 * 60, stats=stats,
    )
    assert (actionable, notes, stale) == (True, None, False)
    assert stats.stale_anchors == 0


def test_anchor_61_minutes_old_is_not_actionable_and_says_how_old():
    stats = PredictionStats()
    actionable, notes, stale = _apply_anchor_guard(
        actionable=True, notes=None, anchored=True,
        anchor_age_seconds=61 * 60, stats=stats,
    )
    assert actionable is False
    assert stale is True
    assert notes == "anchor stale: 61m"
    assert stats.stale_anchors == 1
    assert stats.suppressed_by_stale_anchor == 1


def test_the_registered_boundary_is_strict():
    """"Less than 60 minutes old" — exactly 60 is already three misses."""
    assert _anchor_staleness_note(MAX_ANCHOR_AGE_SECONDS, anchored=True) is not None
    assert _anchor_staleness_note(MAX_ANCHOR_AGE_SECONDS - 1, anchored=True) is None


def test_unanchored_predictions_take_the_existing_path_unchanged():
    """No book line at all is the unanchored gate's business, not this one's.

    The caller has already flipped actionable and written the unshrunk-model
    note; the guard must not double-flag or double-count it.
    """
    stats = PredictionStats()
    prior_note = "no book line yet: price is unshrunk model opinion"
    actionable, notes, stale = _apply_anchor_guard(
        actionable=False, notes=prior_note, anchored=False,
        anchor_age_seconds=None, stats=stats,
    )
    assert (actionable, notes, stale) == (False, prior_note, False)
    assert stats.stale_anchors == 0
    assert stats.suppressed_by_stale_anchor == 0


def test_an_anchored_prediction_with_unknown_age_is_stale():
    """A timestamp we cannot produce is not evidence of freshness."""
    assert _anchor_staleness_note(None, anchored=True) == "anchor stale: ?m"


def test_a_stale_anchor_appends_to_existing_notes_rather_than_replacing():
    stats = PredictionStats()
    _, notes, _ = _apply_anchor_guard(
        actionable=True, notes="edge above cap", anchored=True,
        anchor_age_seconds=120 * 60, stats=stats,
    )
    assert notes == "edge above cap; anchor stale: 120m"


def test_a_prediction_already_unactionable_is_not_counted_as_suppressed():
    """Suppression means the anchor *alone* flipped it — "solely due to
    staleness" is what distinguishes a dead feed from a quiet board."""
    stats = PredictionStats()
    actionable, _, _ = _apply_anchor_guard(
        actionable=False, notes=None, anchored=True,
        anchor_age_seconds=61 * 60, stats=stats,
    )
    assert actionable is False
    assert stats.stale_anchors == 1
    assert stats.suppressed_by_stale_anchor == 0


# ------------------------------------------------------------------ #
# The age comes from the freshest row that could actually anchor
# ------------------------------------------------------------------ #


def test_consensus_reports_the_freshest_contributing_row(session):
    now = dt.datetime.now(UTC)
    session.add(_odds_row(180, now))
    session.add(_odds_row(25, now))
    session.commit()

    total, margin, captured_at = _book_consensus(session, GAME)
    assert total is not None and margin is not None
    age_minutes = (now - captured_at).total_seconds() / 60
    assert 24 < age_minutes < 26, "freshest row wins, not the median or oldest"


def test_a_live_provider_cannot_vouch_for_freshness(session):
    """Live rows are excluded from the anchor, so they must not renew it either.

    Otherwise an in-game live feed would keep a dead pregame feed looking
    fresh — precisely the confusion the exclusion exists to prevent.
    """
    now = dt.datetime.now(UTC)
    session.add(_odds_row(90, now))
    session.add(_odds_row(1, now, provider="ESPN BET - Live Odds"))
    session.commit()

    _, _, captured_at = _book_consensus(session, GAME)
    age_minutes = (now - captured_at).total_seconds() / 60
    assert age_minutes > 60, "the 1-minute-old live row must not count"


def test_no_rows_means_no_anchor_and_no_timestamp(session):
    total, margin, captured_at = _book_consensus(session, GAME)
    assert (total, margin, captured_at) == (None, None, None)


# ------------------------------------------------------------------ #
# Zero actionable solely from staleness must degrade the job
# ------------------------------------------------------------------ #


def _outage_shaped_stats() -> PredictionStats:
    """Predictions flowed; every would-be-actionable one hit a stale anchor."""
    stats = PredictionStats()
    stats.quotable_markets = 40
    stats.predictions_written = 40
    stats.stale_anchors = 40
    stats.suppressed_by_stale_anchor = 12
    stats.actionable_predictions = 0
    return stats


def test_all_actionable_suppressed_by_staleness_is_not_ok():
    assert _outage_shaped_stats().ok is False


def test_a_board_with_no_edge_is_ok_even_with_zero_actionable():
    """Zero actionable with zero suppressions is a fine outcome, not a fault."""
    stats = PredictionStats()
    stats.quotable_markets = 40
    stats.predictions_written = 40
    stats.actionable_predictions = 0
    stats.suppressed_by_stale_anchor = 0
    assert stats.ok is True


def test_surviving_actionable_predictions_keep_the_job_ok():
    stats = _outage_shaped_stats()
    stats.actionable_predictions = 3
    assert stats.ok is True


def test_scheduler_emits_job_degraded_for_the_outage_shape(monkeypatch):
    """The existing `_safe` mechanism, fed the stale-anchor shape."""
    from core import scheduler

    events = []
    monkeypatch.setattr(
        scheduler.log, "info", lambda ev, **kw: events.append(("info", ev))
    )
    monkeypatch.setattr(
        scheduler.log, "warning", lambda ev, **kw: events.append(("warning", ev))
    )

    scheduler._safe("predictions", _outage_shaped_stats)
    assert ("warning", "job_degraded") in events


def test_staleness_counts_are_in_the_summary():
    """job_degraded is only useful if the log line says *why*."""
    summary = _outage_shaped_stats().summary
    assert summary["stale_anchors"] == 40
    assert summary["suppressed_by_stale_anchor"] == 12
    assert summary["actionable"] == 0
