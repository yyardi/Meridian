"""The scanners' population is git's, not the filesystem's.

Regression for 2026-09-05: a sibling agent's git worktree checked out at
`.claude/worktrees/` — inside the repo — put a stale second copy of every
module on disk, and `test_only_the_api_endpoint_imports_the_order_client`
reported six modules that do not exist on this branch. See `repo_tree.py`.
"""

from __future__ import annotations

import subprocess

import pytest

from repo_tree import REPO, _tracked, repo_files, rel


def test_population_is_exactly_what_git_tracks():
    listed = {
        p for p in subprocess.run(
            ["git", "-C", str(REPO), "ls-files"],
            capture_output=True, text=True, check=True,
        ).stdout.splitlines() if (REPO / p).is_file()
    }
    assert {rel(p) for p in repo_files()} == listed


def test_an_untracked_file_in_the_repo_is_not_scanned():
    """The bug in one line: a file on disk that git does not track — a nested
    checkout, build output, a scratch script — must not reach a scanner."""
    scratch = REPO / "zz_untracked_scratch_for_repo_tree_test.py"
    scratch.write_text("PolymarketOrderClient  # not tracked, not ours\n")
    try:
        _tracked.cache_clear()
        assert scratch.name not in {p.name for p in repo_files(".py")}
    finally:
        scratch.unlink()
        _tracked.cache_clear()


def test_suffix_filter_narrows_without_widening():
    py = repo_files(".py")
    assert py and set(py) <= set(repo_files())
    assert {p.suffix for p in py} == {".py"}


def test_a_short_listing_fails_loudly_instead_of_passing_vacuously():
    """A scanner handed zero files reports zero offenders — green, and blind.
    Break the floor on purpose so we know it is load-bearing."""
    import repo_tree

    class _Stub:
        stdout = "core/api.py\0README.md\0"

    _tracked.cache_clear()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(repo_tree.subprocess, "run", lambda *a, **k: _Stub())
        with pytest.raises(AssertionError, match="too few to be this repos"):
            repo_tree._tracked()
    _tracked.cache_clear()
