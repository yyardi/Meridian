"""Paths handed INTO a container must be container paths.

The first real run of nightly_tt_elo.sh died on FileNotFoundError for
/opt/meridian/artifacts/reads/settlements.json with the file sitting on the box:
the mount is `-v /opt/meridian:/app`, so a host path resolves to nothing inside.
The failure was loud -- the script pushed TT ELO FAILED, which is why it was
caught on the first manual run -- but nothing in the suite could have caught it,
because a host path and a container path are both just strings.
"""
from __future__ import annotations

import pathlib
import re
import subprocess

SH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "nightly_tt_elo.sh"
TEXT = SH.read_text(encoding="utf-8")
RUN = TEXT[TEXT.index("docker run"):TEXT.index("RC=$?")]


def test_the_script_is_valid_bash():
    assert subprocess.run(["bash", "-n", str(SH)]).returncode == 0


def test_the_mount_is_the_one_the_container_paths_assume():
    assert "-v /opt/meridian:/app" in RUN, "the /app container paths below depend on this mount"


#: Shell variables that hold HOST paths. The defect was `$OUT` reaching the
#: container, not the literal string, so a test that greps for /opt/meridian
#: cannot see it -- the first version of this test passed on the real bug.
HOST_VARS = ("OUT", "STATE", "F")


def test_no_host_path_is_passed_into_the_container():
    """The exact defect, in the spelling it actually had: a host-path VARIABLE
    as an argument to the containerised command. Literal /opt/meridian is
    checked too, but the variable is the case that occurred."""
    # Redirections are evaluated by the SHELL, on the host, so `> "$F"` is
    # correct and must not be flagged -- dropping them was the difference
    # between this test failing on the fix and failing on the bug.
    args = re.sub(r"[12]?>{1,2}\s*\S+", "", RUN)
    args = re.sub(r"-v\s+\S+", "", args)
    args = re.sub(r"--env-file\s+\S+", "", args)
    leaked = re.findall(r"(?<![\w/])/opt/meridian/\S*", args)
    for v in HOST_VARS:
        if re.search(r"\$\{?" + v + r"\b", args):
            leaked.append("$" + v)
    assert not leaked, f"host paths handed to the container: {leaked}"


def test_the_settlement_cache_and_state_are_read_from_app():
    assert "--settlements \"$COUT/settlements.json\"" in RUN
    assert 'COUT=/app/artifacts/reads' in TEXT
    assert "--state \"$CSTATE\"" in RUN


def test_the_host_side_still_writes_where_cron_and_the_api_can_read_it():
    """The artifact and the state file are read by humans and by the next run
    from the HOST, so those must stay host paths -- the two spellings coexist
    and the test pins that they are not collapsed into one."""
    assert 'OUT=/opt/meridian/artifacts/reads' in TEXT
    assert 'F="$OUT/tt_elo_$TS.txt"' in TEXT
    assert 'STATE="$OUT/tt_elo_state.json"' in TEXT


def test_a_failed_run_is_pushed_rather_than_read_as_quiet():
    """This job pushes only on a verdict TRANSITION, so a permanently broken run
    would otherwise be indistinguishable from 'nothing changed' forever."""
    assert 'if [ "$RC" -ne 0 ]; then' in TEXT
    assert "TT ELO FAILED exit" in TEXT
