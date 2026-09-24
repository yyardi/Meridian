"""A tape is verdicted once, dated by its tag, however late the verdict runs.

    pytest --noconftest tests/test_verdict_tapes.py

2026-09-24: the planner waited for an ODI, the verdict rolled a day, and the
previous night's WNBA and MLB tapes aged out of the verdict's twenty-hour
clock window unread. These pin the replacement: a marker per directory.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import os
import pathlib
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("verdict_tapes", ROOT / "scripts" / "launchers" / "verdict_tapes.py")
VT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VT)

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 9, 25, 6, 0, tzinfo=UTC)


def _tape(root, name, age_hours):
    d = root / name
    d.mkdir()
    (d / "slate_books_x.jsonl").write_text("{}\n")
    t = (NOW - dt.timedelta(hours=age_hours)).timestamp()
    os.utime(d, (t, t))
    return d


def test_a_tape_is_dated_by_its_tag_not_by_the_run():
    m = dt.datetime(2026, 9, 24, 3, 0, tzinfo=UTC)
    assert VT.tag_date("wnba-09232350", m) == "2026-09-23"
    assert VT.tag_date("mlb-09241625", m) == "2026-09-24"
    assert VT.tag_date("county-09240920", m) == "2026-09-24"


def test_a_december_tape_read_in_january_belongs_to_the_earlier_year():
    assert VT.tag_date("nfl-12282000", dt.datetime(2027, 1, 2, tzinfo=UTC)) == "2026-12-28"


def test_hand_named_and_fixture_tapes_carry_no_date_and_are_never_candidates(tmp_path):
    for n in ("nfl-a", "nfl-b", "smoke-1", "_scratch", "cfb_fixture"):
        _tape(tmp_path, n, 2)
    assert VT.unverdicted(str(tmp_path), NOW) == []


def test_an_unmarked_tape_older_than_the_old_clock_window_is_still_read(tmp_path):
    """The 2026-09-24 case: 27 hours old, no marker, previous night's slate."""
    d = _tape(tmp_path, "wnba-09232350", 27)
    assert VT.unverdicted(str(tmp_path), NOW) == [("2026-09-23", str(d))]


def test_a_marked_tape_is_never_read_twice(tmp_path):
    d = _tape(tmp_path, "mlb-09232225", 27)
    VT.mark([str(d)], NOW)
    assert (d / VT.MARKER).read_text().startswith("2026-09-25T06:00:00Z")
    assert VT.unverdicted(str(tmp_path), NOW) == []


def test_a_tape_whose_recorder_is_still_up_waits_for_the_next_run(tmp_path):
    _tape(tmp_path, "county-09240920", 1)
    _tape(tmp_path, "mlb-09242155", 1)
    got = VT.unverdicted(str(tmp_path), NOW, running={"county-09240920"})
    assert [os.path.basename(d) for _, d in got] == ["mlb-09242155"]


def test_archaeology_is_not_a_candidate(tmp_path):
    _tape(tmp_path, "cfb-09121800", 24 * 12)
    assert VT.unverdicted(str(tmp_path), NOW) == []


def test_candidates_come_oldest_first_so_the_ledger_appends_in_date_order(tmp_path):
    a = _tape(tmp_path, "mlb-09241625", 10)
    b = _tape(tmp_path, "wnba-09232350", 27)
    c = _tape(tmp_path, "mlb-09231700", 36)
    assert [os.path.basename(d) for _, d in VT.unverdicted(str(tmp_path), NOW)] == \
        [c.name, b.name, a.name]


def test_the_verdict_script_uses_the_marker_and_not_a_clock():
    src = (ROOT / "scripts" / "launchers" / "slate_verdict.sh").read_text()
    assert "verdict_tapes.py" in src and "--mark" in src
    assert "-mmin" not in src, "the twenty-hour clock window is the defect this replaces"
