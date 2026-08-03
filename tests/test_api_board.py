"""The board must not disappear when writers run at different cadences.

The bug this pins
-----------------
`/api/board` and `/api/events` selected `captured_at == max(captured_at)`. That
was correct while a single recorder wrote the whole board every cycle: the
newest instant *was* a complete picture.

It stopped being true the moment two writers existed on different cadences. The
live recorder samples only in-progress games every 200ms; the pregame recorder
sweeps the whole board every 15 minutes. So the global maximum timestamp belongs
to one live game and contains nothing else, and an equality test that looks
entirely reasonable silently drops every pregame market. Observed live: a
12-game board rendered as one game with 9 markets.

The failure mode is what makes it worth a test — nothing errors, nothing logs,
the page just quietly shows less than it should.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from core.api import app
from core.storage import MarketSnapshot, get_engine, get_sessionmaker

UTC = dt.timezone.utc

LIVE = "tsc-apitest-live-100pt5"
PREGAME = "tsc-apitest-pregame-200pt5"
OLD = "tsc-apitest-finished-150pt5"


@pytest.fixture
def seeded():
    """One market written now, another 15 minutes ago — the exact shape."""
    Session = get_sessionmaker(get_engine())
    now = dt.datetime.now(UTC)

    def _wipe(s):
        s.execute(
            delete(MarketSnapshot).where(MarketSnapshot.market_slug.like("%apitest%"))
        )
        s.commit()

    rows = [
        # Live game: written 0.2s ago by the fast recorder.
        dict(
            captured_at=now - dt.timedelta(seconds=0.2),
            market_slug=LIVE, event_slug="wnba-apitest-live",
            sports_market_type="basketball_team_full_game_total",
            line=Decimal("100.5"), best_bid=Decimal("0.50"), best_ask=Decimal("0.52"),
            game_start_time=now - dt.timedelta(hours=1), is_live=True,
        ),
        # Pregame game: written 15 minutes ago by the slow recorder. This is
        # the row the old query dropped.
        dict(
            captured_at=now - dt.timedelta(minutes=15),
            market_slug=PREGAME, event_slug="wnba-apitest-pregame",
            sports_market_type="basketball_team_full_game_total",
            line=Decimal("200.5"), best_bid=Decimal("0.48"), best_ask=Decimal("0.51"),
            game_start_time=now + dt.timedelta(hours=3), is_live=False,
        ),
        # An older snapshot of the SAME pregame market — must not win.
        dict(
            captured_at=now - dt.timedelta(hours=2),
            market_slug=PREGAME, event_slug="wnba-apitest-pregame",
            sports_market_type="basketball_team_full_game_total",
            line=Decimal("200.5"), best_bid=Decimal("0.10"), best_ask=Decimal("0.90"),
            game_start_time=now + dt.timedelta(hours=3), is_live=False,
        ),
        # A game that finished days ago — off the board entirely.
        dict(
            captured_at=now - dt.timedelta(days=2),
            market_slug=OLD, event_slug="wnba-apitest-finished",
            sports_market_type="basketball_team_full_game_total",
            line=Decimal("150.5"), best_bid=Decimal("0.60"), best_ask=Decimal("0.62"),
            game_start_time=now - dt.timedelta(days=2), is_live=False,
        ),
    ]

    with Session() as s:
        _wipe(s)
        for row in rows:
            s.add(MarketSnapshot(**row))
        s.commit()
    yield TestClient(app)
    with Session() as s:
        _wipe(s)


def _markets(client):
    return {
        m["market_slug"]: m
        for m in client.get("/api/board").json()["markets"]
        if "apitest" in m["market_slug"]
    }


# ------------------------------------------------------------------ #
# The regression
# ------------------------------------------------------------------ #


def test_board_returns_markets_written_at_different_times(seeded):
    """One market at T and another at T-15min: the board must return BOTH."""
    found = _markets(seeded)
    assert LIVE in found, "the live market should be present"
    assert PREGAME in found, (
        "the pregame market was written 15 minutes ago and was dropped by the "
        "global-max-timestamp query — this is the bug"
    )


def test_board_picks_the_newest_row_per_market(seeded):
    """Per-market latest, not merely 'some row within a window'."""
    found = _markets(seeded)
    assert found[PREGAME]["bid"] == pytest.approx(0.48), (
        "should be the 15-minute-old row, not the 2-hour-old one"
    )
    assert found[PREGAME]["ask"] == pytest.approx(0.51)


def test_finished_games_fall_off_the_board(seeded):
    """The bound is on game time, so a two-day-old game is gone.

    Deliberately not a bound on `captured_at`: that would make a market vanish
    because its writer is slow rather than because its game is over, which is
    the original bug wearing a different hat.
    """
    assert OLD not in _markets(seeded)


def test_events_lists_every_game_not_just_the_live_one(seeded):
    """The sidebar had the identical defect — a full slate rendered as one game."""
    slugs = {
        e["event_slug"]
        for e in seeded.get("/api/events").json()["events"]
        if "apitest" in e["event_slug"]
    }
    assert "wnba-apitest-live" in slugs
    assert "wnba-apitest-pregame" in slugs
    assert "wnba-apitest-finished" not in slugs


# ------------------------------------------------------------------ #
# Staleness must be visible
# ------------------------------------------------------------------ #


def test_each_row_reports_its_own_age(seeded):
    """A 15-minute-old quote must not be presented as 200ms-fresh."""
    found = _markets(seeded)
    assert found[LIVE]["age_seconds"] < 30
    assert found[PREGAME]["age_seconds"] > 600
    assert found[PREGAME]["age_seconds"] > found[LIVE]["age_seconds"] * 10


def test_events_report_the_staleness_of_their_oldest_market(seeded):
    events = {
        e["event_slug"]: e
        for e in seeded.get("/api/events").json()["events"]
        if "apitest" in e["event_slug"]
    }
    assert events["wnba-apitest-pregame"]["age_seconds"] > 600
    assert events["wnba-apitest-live"]["age_seconds"] < 30


# ------------------------------------------------------------------ #
# "No edge" must say why
# ------------------------------------------------------------------ #


def test_in_play_market_is_labelled_not_left_blank(seeded):
    """The model is pregame-only and correctly refuses to price a live game.

    That is right, but on screen it is indistinguishable from a malfunction, so
    the state is named rather than left as an empty cell.
    """
    found = _markets(seeded)
    assert found[LIVE]["pricing_state"] == "in_play"
    assert found[LIVE]["is_live"] is True


def test_pregame_market_without_a_prediction_is_unpriced_not_in_play(seeded):
    """Two different reasons for a blank edge must not look the same."""
    found = _markets(seeded)
    assert found[PREGAME]["pricing_state"] == "unpriced"


def test_board_is_empty_rather_than_erroring_with_no_data():
    """No snapshots at all must not 500."""
    Session = get_sessionmaker(get_engine())
    with Session() as s:
        s.execute(
            delete(MarketSnapshot).where(MarketSnapshot.market_slug.like("%apitest%"))
        )
        s.commit()
    body = TestClient(app).get("/api/board").json()
    assert "markets" in body
