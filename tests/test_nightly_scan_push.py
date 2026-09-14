"""The nightly push must not read the same on a crash as on a quiet night.

The 05:28Z run of 2026-09-14 exited 1 on a json.dump TypeError, wrote no cell
table, and pushed "0 cells cleared the nomination bar" -- the sentence a healthy
null night prints. Nothing in the notification distinguished the two, and the
operator's only view of the scan is that notification.

These tests run the script's ACTUAL message block (extracted between its own two
markers and evaluated by bash), not a grep over its source: a comment can say the
right thing while the code does not.
"""
from __future__ import annotations

import pathlib
import re
import subprocess

SH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "nightly_scan.sh"
TEXT = SH.read_text(encoding="utf-8")

# a completed run's artifact: a coverage line, a distribution block, no nominations
GOOD = """markets with a pregame close 20,019  since=2026-09-01
=== DISTRIBUTION ===
  cells excluding zero 12 of 326
  Var(t) 1.84   max|t| 3.61
exit 0
"""
# the real crash, trimmed
BAD = """markets with a pregame close 20,019  since=2026-09-01
  wrote ROWS_JSON /opt/meridian/artifacts/reads/scan_rows.json (20,019 bet inputs)
Traceback (most recent call last):
  File "<stdin>", line 193, in <module>
TypeError: Object of type int64 is not JSON serializable
exit 1
"""


def _push_body(tmp_path, artifact: str, rc: int) -> str:
    block = TEXT[TEXT.index("# --- the push:"):TEXT.index("TOPIC=")]
    f = tmp_path / "scan.txt"
    f.write_text(artifact, encoding="utf-8")
    script = f'set -u\nF={f}\nTS=2026-09-14T0528Z\nRC={rc}\n{block}\nprintf "%s" "$MSG"\n'
    out = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_the_script_is_valid_bash():
    assert subprocess.run(["bash", "-n", str(SH)]).returncode == 0


def test_a_crash_says_so_and_carries_the_exception(tmp_path):
    msg = _push_body(tmp_path, BAD, 1)
    assert "FAILED exit 1" in msg
    assert "TypeError: Object of type int64" in msg


def test_a_crash_does_not_report_a_nomination_count(tmp_path):
    """Zero nominations over a table that was never written is not zero, it is
    absent. The failure body may SAY there is no count; what it must never do is
    attach a number to one. This is the assertion the old script failed -- it
    pushed "0 cells cleared the nomination bar" off a run that scored no cells."""
    msg = _push_body(tmp_path, BAD, 1)
    assert not re.search(r"\d+ cells cleared", msg), msg
    assert "no nomination count" in msg


def test_a_completed_run_still_reports_the_count_and_the_distribution(tmp_path):
    """The guard above is only worth anything if the good path is unchanged --
    otherwise every night reads as a failure and the signal is gone again."""
    msg = _push_body(tmp_path, GOOD, 0)
    assert "0 cells cleared the nomination bar" in msg
    assert "Var(t) 1.84" in msg
    assert "FAILED" not in msg


def test_the_two_bodies_actually_differ(tmp_path):
    """The property under test, stated directly: same artifact shape, different
    exit code, different push. If this ever passes trivially the tests above are
    checking a constant."""
    assert _push_body(tmp_path, BAD, 1) != _push_body(tmp_path, BAD, 0)


def test_the_push_stays_inside_the_ntfy_cap(tmp_path):
    for artifact, rc in ((GOOD, 0), (BAD, 1)):
        assert len(_push_body(tmp_path, artifact, rc)) <= 500
