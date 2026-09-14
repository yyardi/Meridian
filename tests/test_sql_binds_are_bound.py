r"""Every :name written into a text() SQL literal must actually bind.

SQLAlchemy's bind-param regex ends in a negative lookahead for a colon --
`(?<![:\w\x5c]):(\w+)(?!:)` -- so it does not mistake the `::` cast operator for
a parameter. The cost is that `:t::regclass` matches NOTHING. The colon reaches
postgres verbatim and it answers `syntax error at or near ":"`.

The 09:52Z scan of 2026-09-14 died on exactly that, inside `check_since`, the
function whose entire job is to validate a parameter. It had never executed: the
value it guards had only ever been passed on runs that returned before it, so a
validator that could not run looked identical to a validator that passed.

This test cannot import the scripts -- they run their whole analysis at import,
which is why they are piped to `python -`. It parses them instead and compiles
each text() literal through SQLAlchemy, so the thing under test is SQLAlchemy's
real binding behaviour and not a regex of mine that agrees with my own mistake.
"""
from __future__ import annotations

import ast
import pathlib
import re

import pytest
from sqlalchemy import text

ROOT = pathlib.Path(__file__).resolve().parents[1]
FILES = sorted(p for d in ("cfb", "core", "strategies", "analysis")
               for p in (ROOT / d).rglob("*.py") if (ROOT / d).is_dir())

# a colon-name NOT preceded by a colon or word char -- deliberately WITHOUT the
# trailing lookahead, so it sees what the author meant and SQLAlchemy sees what
# SQLAlchemy binds. The gap between the two sets is the defect.
AUTHOR = re.compile(r"(?<![:\w]):(\w+)")
QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")     # '12:00' is not a bind param


def _sql_literals():
    for path in FILES:
        # NOT wrapped in try/except SyntaxError. The first version was, and it
        # turned a file I had just broken into a silent skip: 175 tests green over
        # a module that would not import. A collector that swallows the failure it
        # exists to find is the defect this whole file documents.
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "text"):
                continue
            if not node.args:
                continue
            try:
                sql = ast.literal_eval(node.args[0])
            except (ValueError, TypeError):
                continue        # an f-string or a name; not checkable here
            if isinstance(sql, str):
                yield path.relative_to(ROOT), node.lineno, sql


LITERALS = list(_sql_literals())


def test_the_scan_reads_more_than_one_sql_literal():
    """Guards the guard: an AST walk that silently matched nothing would make
    every assertion below vacuous, which is the failure this whole file is about."""
    assert len(LITERALS) >= 5, f"only found {len(LITERALS)} text() literals"


@pytest.mark.parametrize("rel,lineno,sql", LITERALS,
                         ids=[f"{r}:{n}" for r, n, _ in LITERALS])
def test_every_colon_name_actually_binds(rel, lineno, sql):
    intended = set(AUTHOR.findall(QUOTED.sub("''", sql)))
    bound = set(text(sql)._bindparams)
    missed = intended - bound
    assert not missed, (
        f"{rel}:{lineno} writes {sorted(missed)} as a parameter but SQLAlchemy binds "
        f"{sorted(bound)}. A `:name` immediately followed by `::` never binds -- "
        f"write CAST(:name AS type) instead.\n  {sql[:200]}")


def test_the_check_can_fail():
    """The shape that shipped, asserted directly: without this the test above
    passes on a file that happens to contain no casts at all."""
    broken = "SELECT 1 FROM pg_inherits WHERE inhparent = :t::regclass"
    assert set(text(broken)._bindparams) == set()
    assert AUTHOR.findall(broken) == ["t"]
    fixed = "SELECT 1 FROM pg_inherits WHERE inhparent = CAST(:t AS regclass)"
    assert set(text(fixed)._bindparams) == {"t"}


# --------------------------------------------------------------------------- #
# The sweep above compiles only text() calls whose argument is a STRING LITERAL,
# and it is blind to the other 70 of 238, which are f-strings and concatenations.
# That blind spot is not incidental: the defect of 2026-09-14 lived in `_FLOOR`,
# a module-level format string interpolated into a larger query, so the compiled
# sweep would have passed over the very thing that broke the nightly run.
#
# This second sweep has no blind spot, because it does not care where the string
# is used. Any string constant anywhere that writes `:name::` is the defect, since
# SQLAlchemy cannot bind that spelling under any circumstances. A grep would do the
# same job, but a grep is not run by anything, and this one fails the suite.
# --------------------------------------------------------------------------- #
COLON_CAST = re.compile(r":\w+::")


def _string_constants():
    for path in FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                yield path.relative_to(ROOT), node.lineno, node.value


def test_no_string_anywhere_writes_a_bind_param_before_a_cast():
    bad = [(p, n, v[:120]) for p, n, v in _string_constants() if COLON_CAST.search(v)]
    assert not bad, (
        "these strings spell a parameter SQLAlchemy cannot bind; use CAST(:name AS type):\n"
        + "\n".join(f"  {p}:{n}  {v}" for p, n, v in bad))


def test_the_second_sweep_reads_the_files_it_claims_to():
    """Same guard as above. An empty generator would make the assertion vacuous,
    and 'found nothing, passed' is the exact shape of the bug being tested."""
    seen = list(_string_constants())
    assert len(seen) > 500, f"only walked {len(seen)} string constants"
    assert COLON_CAST.search("WHERE captured_at >= :since::timestamptz")
    assert not COLON_CAST.search("WHERE captured_at >= CAST(:since AS timestamptz)")
