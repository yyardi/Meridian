"""The ladder job speaks only for a large opportunity, so its silence matters.

Same failure mode as the TT Elo and drift jobs: a job that pushes conditionally
is indistinguishable from a broken one when it is quiet. These pin the four
things that separate those, plus the floor that stops it reporting pennies.
"""
from __future__ import annotations

import pathlib
import subprocess

SH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "nightly_ladder.sh"
TEXT = SH.read_text(encoding="utf-8")


def test_valid_bash_and_executable():
    assert subprocess.run(["bash", "-n", str(SH)]).returncode == 0
    assert SH.stat().st_mode & 0o111


def test_a_failed_run_is_pushed_rather_than_read_as_quiet():
    assert 'if [ "$RC" -ne 0 ]; then' in TEXT
    assert "LADDER SCAN FAILED exit" in TEXT


def test_it_does_not_push_pennies():
    """Median opportunity is $0.01 and these quotes are never consumed. A
    nightly 'found 350 things worth a penny' teaches the reader to skip it."""
    assert "FLOOR=50" in TEXT
    assert '[ "$BEST" -lt "$FLOOR" ]' in TEXT


def test_it_does_not_repush_the_same_opportunity_nightly():
    """These persist for hours; the same standing quote must not page twice."""
    assert '[ "$(cat "$STATE")" = "$BEST" ]' in TEXT
    assert 'mv "$STATE.tmp" "$STATE"' in TEXT


def test_the_artifact_is_written_even_when_nothing_is_found():
    """The record is the point: whether $413.90 recurs weekly is unknown and
    only accrual answers it."""
    assert TEXT.count('echo "wrote $F"') >= 3


def test_it_runs_off_the_api_image_with_the_checkout_mounted():
    """A long-lived container carries whatever code it was built with; on
    2026-09-13 that was eight days stale."""
    assert 'docker inspect meridian-api' in TEXT
    assert "-v /opt/meridian/core:/app/core" in TEXT
    assert "docker exec" not in TEXT


def test_it_places_nothing_and_says_so_in_the_push():
    for bad in ("place_order", "MERIDIAN_ORDER_TOKEN", "run_longshot_shadow"):
        assert bad not in TEXT
    assert "QUOTED NOT FILLED" in TEXT


def test_the_schedule_avoids_every_other_job():
    """04:40 scan (seen finishing as late as 10:16), 09:00 Elo, 09:30 drift,
    10:40 mlb read."""
    assert "30 11 * * *" in TEXT
