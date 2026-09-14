"""`scripts/wait_for_container.sh`: does it refuse to guess?

Run with a stub `docker` on PATH, so every branch is exercised without a
daemon. The script exists because two wall-time errors in one day shared a
shape -- inferring completion from the newest thing visible rather than from a
signal that only exists after completion -- and the point of a standing tool is
that nobody re-derives that at two in the morning.
"""
from __future__ import annotations

import os
import pathlib
import subprocess

import pytest

SH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "wait_for_container.sh"


def _stub(tmp_path, script: str):
    """A fake `docker` earlier on PATH than the real one."""
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    f = d / "docker"
    f.write_text("#!/usr/bin/env bash\n" + script, encoding="utf-8")
    f.chmod(0o755)
    env = dict(os.environ, PATH=f"{d}:{os.environ['PATH']}")
    return env


def _run(env, *args, timeout=60):
    return subprocess.run([str(SH), "--no-sudo", "--poll", "1", *args],
                          capture_output=True, text=True, env=env, timeout=timeout)


def test_it_is_valid_bash():
    assert subprocess.run(["bash", "-n", str(SH)]).returncode == 0


def test_a_container_never_seen_is_NOT_reported_as_finished(tmp_path):
    """★ THE CASE A NAIVE LOOP CALLS DONE. Absent on the first poll means it
    never started -- a job that failed to launch, a wrong name, a typo in a
    filter. Reporting that as finished is how a two-hour run gets a wall time of
    four seconds."""
    env = _stub(tmp_path, 'if [ "$1" = ps ]; then exit 0; fi\n')   # prints nothing
    r = _run(env, "--name", "ghost")
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert "NEVER STARTED" in r.stderr
    assert "FINISHED" not in r.stdout


def test_it_waits_then_reports_finished_with_the_logs_mtime(tmp_path):
    """Seen running, then gone: finished. The finish time comes from the LOG's
    mtime, not from the poll clock -- reading a log still being written and
    calling its last line the end is what dropped 3m44s and turned a 34%
    improvement into 10%."""
    flag = tmp_path / "gone"
    log = tmp_path / "run.txt"
    log.write_text("head\nmiddle\nexit 0\n", encoding="utf-8")
    env = _stub(tmp_path, f'''
if [ "$1" = ps ]; then
  if [ -e "{flag}" ]; then exit 0; fi
  echo abc123; exit 0
fi
if [ "$1" = stat ]; then shift; fi
exit 0
''')
    # disappear after the first poll
    (tmp_path / "arm").write_text("x")
    import threading
    threading.Timer(1.5, lambda: flag.write_text("x")).start()
    # ★ THE LOG'S mtime IS SET TO A DISTINCT PAST VALUE, so the reported finish
    # cannot be the poll clock. Without this, deleting the mtime lookup entirely
    # still passed -- and on darwin it HAD silently fallen through to the poll
    # clock, because `stat -c` is GNU-only, so the exact path was never
    # exercised locally at all.
    os.utime(log, (1767368400, 1767368400))          # 2026-01-02 13:00:00 UTC
    r = _run(env, "--name", "real", "--log", str(log))
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "seen running at" in r.stdout
    assert "FINISHED. log last written: 2026-01-02" in r.stdout, (
        f"the finish time is not the log's mtime:\n{r.stdout}")
    assert "exit 0" in r.stdout, "the log's tail is not shown"
    assert "POLL" not in r.stdout, "it fell back to the poll clock silently"


def test_a_failing_docker_probe_is_not_a_finish(tmp_path):
    """★ AN SSH OR DAEMON FAILURE MUST NOT READ AS DONE. My first waiter today
    used an unquoted variable that never executed, got empty output, and called
    it finished. Empty is not zero."""
    env = _stub(tmp_path, 'echo "Cannot connect to the Docker daemon" >&2; exit 1\n')
    r = _run(env, "--name", "x")
    assert r.returncode == 5, (r.returncode, r.stdout, r.stderr)
    assert "not reporting this as finished" in r.stderr


def test_it_times_out_rather_than_waiting_forever(tmp_path):
    """A container that never exits must end the wait with a distinct code, not
    hang a session."""
    env = _stub(tmp_path, 'if [ "$1" = ps ]; then echo abc123; fi\nexit 0\n')
    r = _run(env, "--name", "forever", "--timeout", "2")
    assert r.returncode == 3
    assert "TIMED OUT" in r.stderr


def test_it_does_not_use_pgrep(tmp_path):
    """★ `pgrep -f <pattern>` MATCHES ITS OWN COMMAND LINE, which is how a
    waiter reports RUNNING forever. Asserted at the source, because the
    behavioural tests above would all pass against a pgrep implementation that
    happened to be given a pattern not in its own argv."""
    src = SH.read_text()
    body = src[src.index("probe() {"):]
    assert "pgrep" not in body, "the probe uses pgrep and can match itself"
    assert "docker ps" in body


def test_usage_errors_are_distinct_from_outcomes(tmp_path):
    """Calling it wrong must not look like any job state."""
    env = _stub(tmp_path, "exit 0\n")
    assert _run(env).returncode == 4                       # no selector
    assert _run(env, "--bogus", "x").returncode == 4




def test_a_failing_inspect_is_not_a_missing_container(tmp_path):
    """★ ONE LINE BELOW THE `docker ps` FIX, AND IT HAD THE SAME BUG.
    `docker inspect | grep -q` reads a FAILED inspect as "no match", so a
    transient failure undercounts -- and if it hit every container, the job
    would be reported finished. Found by a deliberate sweep for the
    pipeline-status shape, not by re-reading my own diff, which is the argument
    for the sweep."""
    env = _stub(tmp_path, '''
if [ "$1" = ps ]; then echo abc123; exit 0; fi
if [ "$1" = inspect ]; then echo "no such object" >&2; exit 1; fi
exit 0
''')
    r = _run(env, "--env-contains", "isolate_rows")
    assert r.returncode == 5, (r.returncode, r.stdout, r.stderr)
    assert "not reporting this as finished" in r.stderr


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
