"""No module may define anything after its `if __name__ == "__main__"` guard.

    pytest --noconftest tests/test_no_defs_after_main_guard.py

A def below the guard is UNREACHABLE WHEN THE FILE RUNS AS A SCRIPT, and
perfectly visible when it is imported. So the tests pass and the program dies.

On 2026-09-14 the whole binomial branch of `cfb/run_scan_null.py` --
`poisson_binomial_pmf`, `poisson_binomial_p`, `break_even`, `cell_price_table`,
`binomial_cells`, `min_p`, six functions -- had been appended after the guard.
Thirty-seven tests covered them and all thirty-seven passed, because pytest
imports a module rather than executing it; the first real run died with
`NameError: name 'cell_price_table' is not defined`. Nothing in a test suite
can see this, which is why it is checked structurally.
"""
from __future__ import annotations

import ast

import pytest

from repo_tree import rel, repo_files


def _offenders():
    out = []
    for path in repo_files(".py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        guards = [n.lineno for n in tree.body
                  if isinstance(n, ast.If) and "__main__" in ast.unparse(n.test)]
        if not guards:
            continue
        first = min(guards)
        late = [n.name for n in tree.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and n.lineno > first]
        if late:
            out.append((rel(path), first, late))
    return out


def test_nothing_is_defined_below_the_main_guard():
    bad = _offenders()
    assert not bad, (
        "definitions below `if __name__ == \"__main__\"` are unreachable when the "
        "file runs as a script, and invisible to any test that imports it:\n  "
        + "\n  ".join(f"{f} (guard at line {ln}): {', '.join(names)}"
                      for f, ln, names in bad))


def test_the_guard_can_actually_fail(tmp_path, monkeypatch):
    """★ A control, because this file's whole subject is checks that cannot
    fail. A planted late def must be caught and a normal layout must not."""
    bad = tmp_path / "late.py"
    bad.write_text('if __name__ == "__main__":\n    main()\n\n\ndef helper():\n    pass\n',
                   encoding="utf-8")
    good = tmp_path / "fine.py"
    good.write_text('def helper():\n    pass\n\n\nif __name__ == "__main__":\n    helper()\n',
                    encoding="utf-8")
    monkeypatch.setattr("test_no_defs_after_main_guard.repo_files", lambda *_s: [bad, good])
    monkeypatch.setattr("test_no_defs_after_main_guard.rel", lambda p: p.name)
    got = _offenders()
    assert [(f, names) for f, _, names in got] == [("late.py", ["helper"])], got


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
