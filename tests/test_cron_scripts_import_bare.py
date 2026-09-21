"""A script cron runs must resolve its imports with no PYTHONPATH.

I moved one constant's import from below `scripts/schedule_slate.py`'s
`sys.path.insert` bootstrap up into the tidy import block at the top of the
file. The whole suite stayed green -- 2,758 passed -- while

    python scripts/schedule_slate.py

raised `ModuleNotFoundError` on line 50, because the repo root is not on
`sys.path` until that insert runs. pytest puts the root there for every test in
this suite; cron does not. The mid-file import with its `# noqa: E402` was not
untidiness, it was the bootstrap, and tidying it broke the only invocation that
matters for a planner whose whole job is to run unattended at 09:00Z.

So the probe is a SUBPROCESS with a stripped environment, which is the
production predicate. It asserts only that the import chain resolves: a usage
error is a legitimate answer from a script with no argparse
(`scripts/ntfy_allowed.py` prints usage and exits 2), while a
ModuleNotFoundError never is.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: The scripts that bootstrap sys.path are the ones meant to be RUN, not
#: imported, so they are exactly the population that can have this defect.
BOOTSTRAPPING = sorted(
    p for p in (ROOT / "scripts").glob("*.py")
    if "sys.path.insert" in p.read_text(encoding="utf-8"))

IMPORT_FAILURES = ("ModuleNotFoundError", "ImportError")


def test_the_population_is_not_empty():
    """If the glob or the marker changes, every case below vacuously passes."""
    names = {p.name for p in BOOTSTRAPPING}
    assert "schedule_slate.py" in names
    assert len(BOOTSTRAPPING) >= 5


@pytest.mark.parametrize("script", BOOTSTRAPPING, ids=lambda p: p.name)
def test_imports_resolve_with_no_pythonpath(script: pathlib.Path):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}   # no PYTHONPATH
    proc = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    bad = [m for m in IMPORT_FAILURES if m in proc.stderr]
    assert not bad, (
        f"{script.name} cannot resolve its imports the way cron runs it "
        f"({bad[0]}):\n{proc.stderr[-400:]}")
