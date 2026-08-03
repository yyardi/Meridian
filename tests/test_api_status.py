"""The health endpoint must be cheap, honest, and able to detect a dead writer.

Three things went wrong at once when the recorder moved to 200ms, and all
three are pinned here:

* `count(*)` on market_snapshots went from 3.2s to **exceeding the two-minute
  statement timeout**, on a path the dashboard polls continuously.
* `age_minutes` became meaningless: the live recorder writes five times a
  second, so the newest row is always ~0s old and the page read healthy with
  the pregame recorder dead for hours.
* `gaps_recent` became structurally incapable of firing — it looked for holes
  over 90 minutes among the 200 most recent distinct instants, which at 200ms
  span forty seconds. It returned 0 unconditionally.
"""

from __future__ import annotations

import datetime as dt
import time
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

import core.api as api
from core.api import PREGAME_STALE_SECONDS, app
from core.storage import MarketSnapshot, get_engine, get_sessionmaker

UTC = dt.timezone.utc


def _snap(slug, captured_at, tier, start):
    return MarketSnapshot(
        captured_at=captured_at, market_slug=slug, event_slug="wnba-statustest",
        sports_market_type="basketball_team_full_game_total",
        line=Decimal("100.5"), best_bid=Decimal("0.50"), best_ask=Decimal("0.52"),
        game_start_time=start, is_live=(tier is not None), book_tier=tier,
    )


@pytest.fixture
def client():
    api._status_cache["at"] = 0.0
    api._status_cache["value"] = None
    yield TestClient(app)
    api._status_cache["at"] = 0.0
    api._status_cache["value"] = None


@pytest.fixture
def writers():
    """A fresh pregame write and an older live write."""
    Session = get_sessionmaker(get_engine())
    now = dt.datetime.now(UTC)

    def _wipe(s):
        s.execute(
            delete(MarketSnapshot).where(MarketSnapshot.market_slug.like("%statustest%"))
        )
        s.commit()

    with Session() as s:
        _wipe(s)
        s.add(_snap("tsc-statustest-pre", now - dt.timedelta(seconds=30), None,
                    now + dt.timedelta(hours=2)))
        s.add(_snap("tsc-statustest-live", now - dt.timedelta(minutes=40), "near",
                    now - dt.timedelta(hours=1)))
        s.commit()
    yield Session
    with Session() as s:
        _wipe(s)


# ------------------------------------------------------------------ #
# Cost
# ------------------------------------------------------------------ #


def test_status_does_not_count_rows():
    """count(*) is what broke this endpoint; it must not come back.

    On 857k snapshots it exceeded the two-minute statement timeout. The
    estimate reads in ~1ms.
    """
    sql = str(api._HEALTH_SQL).lower()
    assert "count(" not in sql, "an exact count on the health path is what broke it"
    assert "reltuples" in sql, "counts must come from planner statistics"


def test_status_is_one_round_trip():
    """One statement, because the round trip to Supabase is ~60ms and this is
    polled continuously. Four sequential queries would blow the 300ms budget on
    latency alone."""
    assert str(api._HEALTH_SQL).lower().count("select") >= 4, "sub-selects expected"
    assert str(api._HEALTH_SQL).strip().lower().startswith("select")


def test_repeat_polls_are_served_from_cache(client, writers):
    first = client.get("/api/status").json()
    t0 = time.monotonic()
    for _ in range(25):
        client.get("/api/status")
    elapsed = (time.monotonic() - t0) / 25
    assert elapsed < 0.02, f"cached poll took {elapsed*1000:.1f}ms"
    assert client.get("/api/status").json() == first


def test_cache_expires(client, writers, monkeypatch):
    client.get("/api/status")
    monkeypatch.setattr(api, "STATUS_CACHE_SECONDS", 0.0)
    api._status_cache["at"] = time.monotonic() - 1.0
    assert client.get("/api/status").status_code == 200


# ------------------------------------------------------------------ #
# Honesty
# ------------------------------------------------------------------ #


def test_counts_are_labelled_as_estimates(client, writers):
    body = client.get("/api/status").json()
    assert body["counts_estimated"] is True, (
        "an approximate number presented as exact is worse than either"
    )
    assert set(body["counts"]) == {
        "snapshots", "book_levels", "predictions", "shadow_orders"
    }


def test_the_broken_gap_counter_is_gone(client, writers):
    """It could not detect a 90-minute gap in a 40-second window, and reported
    0 unconditionally. Reporting nothing beats reporting a comforting zero."""
    assert "gaps_recent" not in client.get("/api/status").json()


# ------------------------------------------------------------------ #
# Detecting a dead writer — the thing health is actually for
# ------------------------------------------------------------------ #


def test_freshness_is_reported_per_writer(client, writers):
    """A global max is always ~0s old while a game is live."""
    body = client.get("/api/status").json()
    assert body["pregame_age_seconds"] < 120
    assert body["live_age_seconds"] > 1800
    assert body["live_age_seconds"] > body["pregame_age_seconds"]


def test_a_silent_live_recorder_does_not_fail_the_health_check(client, writers):
    """It is legitimately quiet between games; failing on that would show STALE
    every night and train the reader to ignore the light."""
    body = client.get("/api/status").json()
    assert body["live_age_seconds"] > 1800
    assert body["healthy"] is True


def test_a_dead_pregame_recorder_is_unhealthy(client):
    """The case the old endpoint could not see."""
    Session = get_sessionmaker(get_engine())
    now = dt.datetime.now(UTC)
    with Session() as s:
        s.execute(delete(MarketSnapshot).where(
            MarketSnapshot.market_slug.like("%statustest%")))
        # Pregame recorder silent for three hours; live recorder writing now.
        s.add(_snap("tsc-statustest-pre", now - dt.timedelta(hours=3), None,
                    now + dt.timedelta(hours=2)))
        s.add(_snap("tsc-statustest-live", now - dt.timedelta(seconds=1), "near",
                    now - dt.timedelta(hours=1)))
        s.commit()
    try:
        body = client.get("/api/status").json()
        assert body["pregame_age_seconds"] > PREGAME_STALE_SECONDS
        assert body["healthy"] is False, (
            "a stopped pregame recorder must fail the check even while the "
            "live recorder is writing five times a second"
        )
    finally:
        with Session() as s:
            s.execute(delete(MarketSnapshot).where(
                MarketSnapshot.market_slug.like("%statustest%")))
            s.commit()


# ------------------------------------------------------------------ #
# Connection hygiene
# ------------------------------------------------------------------ #


def test_engines_are_shared_not_created_per_caller():
    """The scheduler builds PredictionLogger()/ESPNOddsFetcher()/ResolutionJob()
    fresh every cycle. Without a shared engine that is a new connection pool
    several times an hour, disposed only when GC happens to notice — which is
    how the session-mode pooler was exhausted."""
    assert get_engine() is get_engine()
    assert get_engine() is not get_engine(pool_size=1, max_overflow=0)


def test_pool_is_capped_small():
    from core.storage.base import DEFAULT_MAX_OVERFLOW, DEFAULT_POOL_SIZE

    assert DEFAULT_POOL_SIZE + DEFAULT_MAX_OVERFLOW <= 3


def test_migrations_use_session_mode_not_the_transaction_pooler(monkeypatch):
    """Alembic's advisory locks do not work in transaction mode, so migrations
    must keep port 5432 even when every app process moves to 6543."""
    from core.storage.base import app_database_url, get_database_url

    url = "postgresql+psycopg://u:p@aws-1.pooler.supabase.com:5432/postgres"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("MERIDIAN_TX_POOLER", "1")

    assert ":5432/" in get_database_url(), "alembic reads this one"
    assert ":6543/" in app_database_url(), "app processes read this one"
