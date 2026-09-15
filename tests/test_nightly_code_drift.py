"""The drift wrapper speaks only on a transition, so its silence is load-bearing.

A job that pushes only when the answer CHANGES has one catastrophic failure mode:
being permanently broken looks exactly like "nothing changed". These pin the
three things that separate those, and the first-run rule that stops night one
from pushing the whole fleet.
"""
from __future__ import annotations

import pathlib
import subprocess

SH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "nightly_code_drift.sh"
TEXT = SH.read_text(encoding="utf-8")


def test_valid_bash_and_executable():
    assert subprocess.run(["bash", "-n", str(SH)]).returncode == 0
    assert SH.stat().st_mode & 0o111, "cron needs the execute bit"


def test_a_missing_state_file_is_a_first_run_not_a_full_fleet_push():
    """Otherwise night one pushes every inert file and the channel is learned
    as noise before it carries the one message that matters."""
    assert 'if [ ! -f "$STATE" ]; then' in TEXT
    first = TEXT[TEXT.index('if [ ! -f "$STATE" ]; then'):]
    assert "no transition by definition" in first[:400]
    assert "exit 0" in first[:400]


def test_the_instruments_health_is_not_conflated_with_its_answer():
    """code_drift.sh exits 0 whether or not anything drifted -- DIFFERS is a
    finding. Non-zero means it could NOT answer (exit 2 = bad reference). A
    wrapper that read DIFFERS off the exit code would report a clean fleet
    every night forever."""
    assert 'if [ "$RC" -ne 0 ]; then' in TEXT
    assert "CODE DRIFT CHECK FAILED exit" in TEXT
    assert "RC=$?" in TEXT


def test_the_state_write_is_atomic():
    """A kill mid-write must leave the OLD state, not a truncated file the next
    run misreads as a different set and pushes about."""
    assert TEXT.count('mv "$STATE.tmp" "$STATE"') == 2, "both write sites must be atomic"
    assert '> "$STATE"' not in TEXT.replace('> "$STATE.tmp"', ""), "no direct write to the state file"


def test_both_directions_of_the_transition_are_reported():
    """A file becoming inert and a file becoming deployed are both news. A
    detector that only announces new drift never tells you a rebuild worked."""
    assert "now inert:" in TEXT
    assert "now deployed:" in TEXT


def test_it_compares_the_file_set_not_the_container_list():
    """28 containers share one drifting set; keying on containers would push on
    any container restart and drown the real signal."""
    assert "sort -u" in TEXT
