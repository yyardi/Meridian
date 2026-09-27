"""The resolution job's snapshot subquery is bounded, because unbounded it killed postgres.

    pytest --noconftest tests/test_resolution_floor.py

2026-09-26 22:35Z and 2026-09-27 15:58Z: `SELECT predictions.market_slug,
max(line) ...` was the statement postgres was running when the kernel killed a
4 GB backend. Its `IN (SELECT market_slug FROM market_snapshots WHERE
game_start_time < now - 3h)` hashed every slug of an 87-million-row table.
"""
from __future__ import annotations

import datetime as dt
import inspect
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core import resolution  # noqa: E402

UTC = dt.timezone.utc


def test_the_floor_is_a_month_boundary_at_least_the_lookback_back():
    now = dt.datetime(2026, 9, 27, 16, 0, tzinfo=UTC)
    f = resolution.snapshot_floor(now)
    assert f == dt.datetime(2026, 8, 1, tzinfo=UTC)
    assert (now - f).days >= resolution.SNAPSHOT_LOOKBACK_DAYS
    assert f.day == 1 and f.hour == 0, "a mid-month floor filters rows and costs MORE"


def test_the_snapshot_subquery_carries_the_floor():
    src = inspect.getsource(resolution.ResolutionJob.run)
    sub = src[src.index("select(MarketSnapshot.market_slug)"):]
    assert "MarketSnapshot.captured_at >= snapshot_floor()" in sub[:300], \
        "the subquery over market_snapshots must be floored before game_start_time is tested"
