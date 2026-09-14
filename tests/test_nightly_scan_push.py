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

import pytest

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


# --------------------------------------------------------------------------- #
# Attacked with six artifact shapes. Three of them broke it.
# --------------------------------------------------------------------------- #
#: Every guard in `cfb/run_scan.py` exits via `raise SystemExit("message")`, and
#: Python prints the bare message with NO exception name. So the six most likely
#: failures all looked identical to the push.
SYSTEMEXIT_ARTIFACTS = {
    "no_data": "NO DATA: no cell collected -- check the league patterns\nexit 1\n",
    "bad_floor": ("SCAN_SINCE=2026-08-25 is not a market_snapshots partition "
                  "boundary.\nexit 1\n"),
    "ambiguous_slug": ("slug 'x-cfb-y-nfl-z' matched 2 patterns -- attribution is "
                       "ambiguous\nexit 1\n"),
    "expect_mismatch": ("SCAN_EXPECT was taken with since=NONE and this run uses "
                        "since=2026-09-01.\nexit 1\n"),
}


@pytest.mark.parametrize("name", sorted(SYSTEMEXIT_ARTIFACTS))
def test_a_systemexit_guard_keeps_its_reason(tmp_path, name):
    """★ `raise SystemExit("msg")` PRINTS NO EXCEPTION NAME, so
    `^[A-Za-z_.]*(Error|Exception):` never matched and the push said "no
    exception line in the artifact" while the artifact's last line stated the
    reason in plain English. These guards were written to kill the run rather
    than warn; throwing away what they said undoes that."""
    art = SYSTEMEXIT_ARTIFACTS[name]
    body = _push_body(tmp_path, art, 1)
    assert "SCAN FAILED" in body
    assert "no exception line in the artifact" not in body, (
        "the reason was discarded even though it is the artifact's last line")
    head = art.splitlines()[0][:60]
    assert head in body, f"expected {head!r} in the push"


def test_exit_zero_having_written_nothing_is_not_a_quiet_night(tmp_path):
    """★ THE SHAPE THAT STILL READ AS SUCCESS. Blank coverage, blank
    distribution, then "0 cells cleared the nomination bar" and the null caveat
    -- the exact sentence this block exists to stop printing, on a run that
    produced nothing.

    Reachable: `python - < cfb/run_scan.py` on an EMPTY or truncated file reads
    nothing, runs nothing and exits 0. A count over a table that was never
    written is not zero whether the exit code is 1 or 0, so the nomination line
    is earned by the CELL TABLE being present, not by the exit code."""
    for artifact in ("exit 0\n", "\n\nexit 0\n"):
        body = _push_body(tmp_path, artifact, 0)
        assert "cleared the nomination bar" not in body, (
            "a run that wrote nothing reported a nomination count")
        assert "INCOMPLETE" in body
        assert "no cell table" in body


def test_the_healthy_body_has_no_stray_zero_line(tmp_path):
    """★ A PRE-EXISTING DEFECT IN THE NOMINATION COUNT ITSELF. `grep -c` prints
    "0" AND returns 1 when nothing matches, so `|| echo 0` appended a SECOND
    zero and `$NOM` expanded to "0\\n0". Every healthy null night pushed

        0
        0 cells cleared the nomination bar

    Two failures from one shape: the stray line here, and the `DONE` guard above
    failing its integer test and falling through to the success branch, which is
    why the fix for the previous test did not work the first time."""
    body = _push_body(tmp_path, GOOD, 0)
    assert "\n0\n0 cells" not in body
    assert body.count("cleared the nomination bar") == 1
    lines = [ln for ln in body.splitlines() if ln.strip()]
    assert not any(ln.strip() == "0" for ln in lines), (
        f"stray bare-zero line in the push:\n{body}")


def test_a_crash_before_the_coverage_line_still_says_failed(tmp_path):
    """The other shape asked about: died so early that COV is empty too. This
    one already held -- recorded so a future change cannot quietly lose it. The
    artifact is the real 09:52Z crash."""
    body = _push_body(
        tmp_path,
        'Traceback (most recent call last):\n'
        '  File "<stdin>", line 204, in <module>\n'
        'sqlalchemy.exc.ProgrammingError: (psycopg.errors.SyntaxError) syntax '
        'error at or near ":"\nexit 1\n', 1)
    assert "SCAN FAILED exit 1" in body
    assert "cleared the nomination bar" not in body
    assert "ProgrammingError" in body
