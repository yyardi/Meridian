"""The population a repo-scanning guard means by "the repository".

Guards like `test_no_infra_identifiers` and the order-client scan in
`test_human_confirm_orders` answer questions about *this codebase*: what
ships, what is public, what can reach the venue. They used to answer them by
walking the directory with `rglob`, which is a different question — it scans
whatever happens to sit on disk under the repo path.

The two drift apart, and on 2026-09-05 they did: a sibling agent's git
worktree was checked out at `.claude/worktrees/`, INSIDE the repo, and its
stale copy of `core/api.py` made the "only the API endpoint may place orders"
guard report six modules that do not exist on this branch. A safety guard
that cries wolf is a safety guard someone mutes.

`git ls-files` is the question actually being asked, and it needs no skip
list: build output, virtualenvs, caches, untracked scratch files and nested
checkouts are all excluded because none of them are tracked here. Nothing to
maintain as new kinds of junk land on disk.

Not importable from `conftest` on purpose — `tests/` is not a package and
importing conftest re-executes it (which once created the test database
twice). This module has no import side effects.
"""

from __future__ import annotations

import subprocess
from functools import cache
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: Below this, assume the listing failed rather than that the repo shrank.
#: A scanner handed zero files passes every assertion in it — the silent
#: false negative is the failure mode worth an explicit floor.
_MIN_TRACKED = 100


@cache
def _tracked() -> tuple[Path, ...]:
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z"],
        capture_output=True, text=True, check=True,
    ).stdout
    paths = sorted(REPO / p for p in out.split("\0") if p)
    assert len(paths) >= _MIN_TRACKED, (
        f"git ls-files returned {len(paths)} paths under {REPO} — too few to "
        "be this repository. Every scanner built on it would pass vacuously."
    )
    # Tracked-but-deleted paths are listed; only what is on disk is readable.
    return tuple(p for p in paths if p.is_file())


def repo_files(*suffixes: str) -> list[Path]:
    """Tracked files in this checkout, optionally filtered by suffix.

    Suffixes include the dot: ``repo_files(".py")``.
    """
    files = _tracked()
    if suffixes:
        files = tuple(p for p in files if p.suffix in suffixes)
    return list(files)


def rel(path: Path) -> str:
    """Repo-relative POSIX path, the form every guard reports offenders in."""
    return path.relative_to(REPO).as_posix()
