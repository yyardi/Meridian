"""The resolution job looks finished games up by slug, because the subquery form killed postgres.

    pytest --noconftest tests/test_resolution_floor.py

2026-09-26 22:35Z, 2026-09-27 15:58Z and 20:10Z: `SELECT predictions.market_slug,
max(line) ...` was the statement postgres was running when the kernel killed a
1.2-4 GB backend. Its `IN (SELECT market_slug FROM market_snapshots WHERE
game_start_time < now - 3h)` hashed every slug of an 87-million-row table; a
month floor removed a few thousand rows of it and the third kill followed.
"""
from __future__ import annotations

import datetime as dt
import inspect
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core import resolution  # noqa: E402

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 9, 27, 20, 0, tzinfo=UTC)


class _Session:
    """Records every statement and its parameters; answers with the slugs asked for
    that end in 'done', so the test can see filtering happen."""

    def __init__(self):
        self.calls = []

    def execute(self, stmt, params=None):
        self.calls.append((str(stmt), params))
        slugs = params["slugs"]

        class _R:
            def all(_):
                return [(s,) for s in slugs if s.endswith("done")]
        return _R()


def test_the_floor_is_a_month_boundary_at_least_the_lookback_back():
    f = resolution.snapshot_floor(NOW)
    assert f == dt.datetime(2026, 8, 1, tzinfo=UTC)
    assert (NOW - f).days >= resolution.SNAPSHOT_LOOKBACK_DAYS
    assert f.day == 1 and f.hour == 0, "a mid-month floor filters rows and costs MORE"


def test_finished_games_are_looked_up_by_slug_in_chunks_with_the_floor_and_the_cut():
    s = _Session()
    slugs = [f"m{i}-{'done' if i % 3 == 0 else 'live'}" for i in range(1201)]
    got = resolution.finished_slugs(s, slugs, now=NOW, chunk=500)
    assert len(s.calls) == 3, "1,201 slugs in chunks of 500 is three index lookups, never one hash of the table"
    for stmt, params in s.calls:
        assert "market_slug = ANY(:slugs)" in stmt and "captured_at >= :floor" in stmt and "game_start_time < :cut" in stmt
        assert params["floor"] == dt.datetime(2026, 8, 1, tzinfo=UTC)
        assert params["cut"] == NOW - dt.timedelta(hours=3)
        assert len(params["slugs"]) <= 500
    assert got == {x for x in slugs if x.endswith("done")}
    assert resolution.finished_slugs(s, [], now=NOW) == set() and len(s.calls) == 3, "no slugs, no statement"


def test_run_no_longer_hashes_the_snapshot_table():
    src = inspect.getsource(resolution.ResolutionJob.run)
    assert "select(MarketSnapshot.market_slug)" not in src, "the IN (SELECT ... FROM market_snapshots) form is the defect"
    assert "finished_slugs(" in src
