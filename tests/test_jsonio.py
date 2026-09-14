"""The guarded writer, tested on the three types that actually broke it today."""
from __future__ import annotations

import datetime as dt
import json

import pytest

from core.jsonio import _plain, write_json


def test_datetime_round_trips_as_iso():
    """cfb/run_paper_book.py died on this at 10:16Z and the day had no book."""
    t = dt.datetime(2026, 9, 14, 10, 16, tzinfo=dt.timezone.utc)
    out = json.loads(json.dumps({"g": t}, default=_plain))
    assert out["g"] == t.isoformat()


def test_a_numpy_style_scalar_is_unwrapped():
    """cfb/run_scan.py died on a numpy int64 at 05:28Z. No numpy dependency in
    the test: the writer's contract is `.item()`, not the numpy package."""
    class Int64:
        def item(self): return 7
    assert json.loads(json.dumps({"n": Int64()}, default=_plain))["n"] == 7


def test_an_unknown_type_still_raises():
    """Deliberately not `default=str`. A silent stringify would have let the
    paper book write a document whose fields had the wrong types and call it a
    success, which is worse than the exit 1 we got."""
    with pytest.raises(TypeError, match="not JSON serializable"):
        json.dumps({"x": object()}, default=_plain)


def test_a_failed_write_leaves_the_previous_file_and_no_temp(tmp_path):
    """The property the atomic write exists for. The scan's truncated artifact
    had a plausible size and a fresh mtime, and the settle cache read that shape
    as an empty cache and would have overwritten 20,000 settlements."""
    p = tmp_path / "a.json"
    write_json(str(p), {"v": 1})
    with pytest.raises(TypeError):
        write_json(str(p), {"v": object()})
    assert json.loads(p.read_text()) == {"v": 1}, "the old file must survive"
    assert not list(tmp_path.glob("*.tmp")), "a stray .tmp is the same trap again"


def test_a_successful_write_replaces_the_file(tmp_path):
    """Guards the guard above: if write_json never wrote anything, the survival
    test would pass for the wrong reason."""
    p = tmp_path / "a.json"
    write_json(str(p), {"v": 1})
    write_json(str(p), {"v": 2})
    assert json.loads(p.read_text()) == {"v": 2}
