"""A module nothing calls is inert, and the suite cannot see it.

`core/tt/money.py` shipped with 20 passing tests, a registered criterion in a
pre-registration doc, and a commit message describing it working. Nothing
imported it outside its own test file, `PRICE_SQL` selected only the mid, and
the runner imported `elo, rule`. It could never have executed, and the suite
was green at 2,326 throughout -- because the tests exercise the module
directly. Nothing in a test suite separates "runs and is correct" from "is
correct and never runs". Only asking WHAT CALLS IT does, and no test asks that
by default.

Scoped to `core/tt/` on purpose. The same sweep across `core/` reports 22 of
111 modules with no caller in code, compose, shell or cron, and most of those
are legitimately run by hand -- a repo-wide version would be 22 lines of noise
that trains its reader to skip it. `core/tt/` is the package that has to fire
unattended at 09:00Z with nobody watching, which is exactly where inertness is
invisible and costly.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from core.tt import money

REPO = pathlib.Path(__file__).resolve().parent.parent
SKIP_DIRS = {".venv", "node_modules", "alembic", ".git", ".pytest_cache",
             "__pycache__"}


def _imports(path: pathlib.Path) -> set[str]:
    """Every dotted name this file imports, including `from pkg import name`.

    The comma form matters: a regex for "tt import money" misses
    `from core.tt import elo, money, rule`, which is how the real caller is
    spelled. My first sweep used exactly that regex and reported the module
    still unwired after it had been wired -- the matcher was narrower than the
    measurement.
    """
    out: set[str] = set()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
            out.update(f"{node.module}.{a.name}" for a in node.names)
    return out


def _non_test_importers(dotted: str) -> list[str]:
    hits = []
    for p in REPO.glob("**/*.py"):
        if SKIP_DIRS & set(p.parts):
            continue
        if p.name.startswith("test_") or "tests" in p.parts:
            continue
        if dotted in _imports(p):
            hits.append(str(p.relative_to(REPO)))
    return hits


TT_MODULES = sorted(p.stem for p in (REPO / "core" / "tt").glob("*.py")
                    if p.name != "__init__.py")


def test_the_package_is_not_empty():
    """If the glob breaks, every parametrised case below vacuously passes."""
    assert set(TT_MODULES) >= {"elo", "fit", "money", "rule"}


@pytest.mark.parametrize("mod", TT_MODULES)
def test_every_tt_module_has_a_non_test_caller(mod):
    callers = _non_test_importers(f"core.tt.{mod}")
    assert callers, (
        f"core/tt/{mod}.py is imported by nothing outside tests. It cannot "
        f"run, and no other test in this suite can tell."
    )


def test_the_money_line_reads_the_registered_rule_not_an_expression():
    """Behaviour, not a source grep (a grep is a contract on text).

    The expression this replaced returned PASS on `hi < 0` -- an interval
    entirely BELOW zero, a strategy that reliably loses, printed as a pass.
    """
    import cfb.run_tt_elo as runner

    class _P:
        def __init__(self, slug, p, y, a, b):
            self.slug, self.elo_p, self.y, self.p1, self.p2 = slug, p, y, a, b

    before = runner.BOOKS
    try:
        # 40 bets that all lose: the interval sits entirely below zero
        runner.BOOKS = {f"s{i}": (0.49, 0.50) for i in range(40)}
        preds = [_P(f"s{i}", 0.99, 0, f"a{i}", f"b{i}") for i in range(40)]
        line = runner._money_line(preds)
    finally:
        runner.BOOKS = before
    assert not line.startswith("PASS"), line
    assert "-51.50c" in line            # and it does report the loss

def test_the_money_line_prints_in_every_state():
    """Silence at zero is how the uncalled arm survived a merge and a review."""
    import cfb.run_tt_elo as runner

    before = runner.BOOKS
    try:
        runner.BOOKS = {}
        assert runner._money_line([]).startswith("NOT YET")
        runner.BOOKS = {"s0": (0.49, 0.50)}
        assert runner._money_line([]).startswith("NOT YET")
    finally:
        runner.BOOKS = before


def test_both_ends_of_the_bar_are_reachable_targets():
    """The gate's X is a choice, so neither end may be the only one quoted."""
    strict = money.required_n(resolution=money.BAR_MEDIAN)
    loose = money.required_n(resolution=money.BAR_MEAN)
    assert strict > loose                      # median bar is the STRICTER gate
