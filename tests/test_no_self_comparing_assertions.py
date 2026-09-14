"""No test may assert a value against itself.

    pytest --noconftest tests/test_no_self_comparing_assertions.py

`assert f(x) == f(x)` passes no matter what `f` does. It is the cheapest way to
write a test that cannot fail, and on 2026-09-14 it had hidden a real claim:
`test_espn_live.py` asserted
`_count("espn_live_injury_observations") == _count("espn_live_injury_observations")`,
so the "injuries never duplicate" half of that test's own docstring was
untested. Removing the recorder's `on_conflict_do_nothing` left the suite green.

Controls that cannot fail were the most common defect in this project that
night -- six of them -- and this is the one shape a machine can find, so a
machine checks it on every run instead of a reviewer noticing.

Two forms are legitimate and are named below rather than pattern-matched,
because both look identical to the defect and only intent separates them.
"""
from __future__ import annotations

import ast

import pytest

from repo_tree import rel, repo_files

#: `file:line` -> why this one is not the defect. A self-comparison is allowed
#: ONLY when the two sides are not actually the same computation.
ALLOWED = {
    # `get_engine()` is memoised: comparing two calls with `is` is the only way
    # to assert the engine is SHARED. The next line asserts different arguments
    # give a different engine, so the pair cannot both pass by accident.
    "tests/test_api_status.py:get_engine": "identity of a memoised singleton",
    # `project(m) == project(m)` is a determinism check: it fails if `project`
    # ever consults a clock or an RNG. The repetition IS the test.
    "tests/test_fair_value.py:project": "determinism across repeated calls",
}


def _self_comparisons():
    """Every `assert X <op> X` in the tracked test tree, X byte-identical."""
    out = []
    for path in repo_files(".py"):
        r = rel(path)
        if "/test_" not in f"/{r}" and not r.startswith("tests/test_"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:                       # not ours to police
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assert):
                continue
            t = node.test
            if not (isinstance(t, ast.Compare) and len(t.ops) == 1
                    and isinstance(t.ops[0], (ast.Eq, ast.NotEq, ast.Is, ast.IsNot))):
                continue
            if ast.dump(t.left) == ast.dump(t.comparators[0]):
                out.append((r, node.lineno, ast.unparse(t)))
    return out


def _key(rel_path: str, expr: str) -> str | None:
    for k in ALLOWED:
        f, _, fn = k.partition(":")
        if rel_path == f and fn in expr:
            return k
    return None


def test_no_test_asserts_a_value_against_itself():
    unexplained = [(f, ln, e) for f, ln, e in _self_comparisons() if _key(f, e) is None]
    assert not unexplained, (
        "self-comparing assertion(s) -- these pass whatever the code does:\n  "
        + "\n  ".join(f"{f}:{ln}  {e}" for f, ln, e in unexplained)
        + "\n\nEither compare against an INDEPENDENT reference, or add the site to"
          " ALLOWED in this file with the reason it is not the defect.")


def test_every_allowance_is_still_needed():
    """An allowlist that outlives its entries teaches people to add to it.
    Each entry must still match something, or it comes out."""
    found = {_key(f, e) for f, _, e in _self_comparisons()}
    stale = set(ALLOWED) - found
    assert not stale, f"ALLOWED entries no longer match anything, delete them: {sorted(stale)}"


def test_the_guard_can_actually_fail(tmp_path, monkeypatch):
    """★ THE CONTROL ON A GUARD WHOSE WHOLE SUBJECT IS GUARDS THAT CANNOT FAIL.
    A planted tautology must be found; a real comparison beside it must not."""
    planted = tmp_path / "test_planted.py"
    planted.write_text(
        "def test_bad():\n"
        "    assert compute(1) == compute(1)\n"
        "def test_good():\n"
        "    assert compute(1) == 2\n",
        encoding="utf-8")
    monkeypatch.setattr("test_no_self_comparing_assertions.repo_files",
                        lambda *_s: [planted])
    monkeypatch.setattr("test_no_self_comparing_assertions.rel",
                        lambda p: f"tests/{p.name}")
    got = _self_comparisons()
    assert [(f, e) for f, _, e in got] == [("tests/test_planted.py",
                                            "compute(1) == compute(1)")], got


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
