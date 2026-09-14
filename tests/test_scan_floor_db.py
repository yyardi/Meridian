"""The floor guard's queries must EXECUTE, not merely parse.

Needs the suite's database — so no `--noconftest` here, unlike
`tests/test_scan_floor.py`, which tests the pure logic with a fake connection
and is standalone.

★ THIS FILE EXISTS BECAUSE THAT FAKE CONNECTION STUBBED OUT THE ONLY BROKEN
PART. Its `execute(self, _q, _p=None): return self` ignored the SQL, so ten
tests covered `partition_floors`/`check_since` and none of them ever sent the
query to a database. The query was unrunnable:

    WHERE i.inhparent = :t::regclass

SQLAlchemy's bind-param regex is `(?<![:\\w\\\\]):(\\w+)(?!:)`. The trailing
`(?!:)` means a parameter FOLLOWED BY A COLON is not recognised, because `::`
is assumed to be a cast — so `:t::regclass` bound **zero** parameters and
postgres received the literal `:t`:

    psycopg.errors.SyntaxError: syntax error at or near ":"

The 09:52Z run of 2026-09-14, the first scan ever launched with `SCAN_SINCE`
set, died there in under two minutes without reading a row. Every EXPLAIN and
every unit test said the floor was sound; the first real unattended run said
otherwise, which is exactly the gap I had flagged and then failed to close.
"""
from __future__ import annotations

import ast
import pathlib
import re

import pytest
from sqlalchemy import text

from core.storage import get_engine

SRC = (pathlib.Path(__file__).resolve().parents[1] / "cfb" / "run_scan.py").read_text()


def _lift(*names: str):
    tree = ast.parse(SRC)
    fns = [n for n in tree.body
           if isinstance(n, ast.FunctionDef) and n.name in set(names)]
    assert len(fns) == len(names), f"missing {set(names) - {f.name for f in fns}}"
    ns: dict = {"re": re, "text": text}
    exec(compile(ast.Module(body=fns, type_ignores=[]), "<scan>", "exec"), ns)  # noqa: S102
    return ns


@pytest.fixture
def parted():
    """A real range-partitioned table with a DEFAULT, built here.

    The suite's database is a fresh `alembic upgrade head`, where
    `market_snapshots` is NOT partitioned — the conversion is a separate
    retention step. Asserting against it would have made this test pass on an
    empty set, which is the same "returned nothing, looked fine" shape as the
    defect it guards. WEEKLY bounds on purpose, so a monthly assumption cannot
    reproduce them (see tests/test_scan_floor.py for why).
    """
    with get_engine().begin() as c:
        c.execute(text("DROP TABLE IF EXISTS dbg_parted"))
        c.execute(text("CREATE TABLE dbg_parted (captured_at timestamptz) "
                       "PARTITION BY RANGE (captured_at)"))
        for lo, hi in (("2026-09-07", "2026-09-14"), ("2026-09-14", "2026-09-21")):
            c.execute(text(f"CREATE TABLE dbg_parted_{lo.replace('-','')} "
                           f"PARTITION OF dbg_parted FOR VALUES "
                           f"FROM ('{lo}') TO ('{hi}')"))
        c.execute(text("CREATE TABLE dbg_parted_def PARTITION OF dbg_parted DEFAULT"))
    yield "dbg_parted"
    with get_engine().begin() as c:
        c.execute(text("DROP TABLE IF EXISTS dbg_parted"))


def test_partition_floors_actually_runs_against_postgres(parted):
    """The regression test for the defect above. It must EXECUTE and return the
    real boundaries, not merely be well-formed Python."""
    ns = _lift("partition_floors")
    with get_engine().connect() as c:
        got = ns["partition_floors"](c, table=parted)
    assert got == {"2026-09-07", "2026-09-14"}, got   # DEFAULT has no FROM
    assert all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) for d in got), got


def test_the_parameter_is_actually_bound():
    """★ The narrow assertion, because the failure was silent at the Python
    level: the statement compiled, `text()` accepted it, and only postgres
    objected. A `:t` that binds nothing is indistinguishable from one that
    binds, until it reaches a server."""
    ns = _lift("partition_floors")

    seen: dict = {}

    class _Spy:
        """Passes the statement to a REAL connection but records what bound."""

        def __init__(self, conn): self._c = conn

        def execute(self, stmt, params=None):
            seen["bound"] = sorted(getattr(stmt, "_bindparams", {}))
            seen["params"] = params
            return self._c.execute(stmt, params)

    with get_engine().connect() as c:
        ns["partition_floors"](_Spy(c), table="market_snapshots")
    assert seen["bound"] == ["t"], (
        f"the statement bound {seen['bound']} — a parameter followed by `::` is "
        "not recognised by SQLAlchemy, so the literal reaches postgres")
    assert seen["params"] == {"t": "market_snapshots"}


def test_check_since_accepts_a_real_boundary_and_refuses_a_real_non_boundary(parted):
    """End to end against postgres, both directions. The accept half is the
    control: a `check_since` that raised unconditionally would satisfy the
    refuse half on its own."""
    ns = _lift("partition_floors", "check_since")
    # `check_since` hardcodes the table, so point `partition_floors` at the
    # fixture by patching the lifted default rather than faking the connection.
    import functools
    ns["partition_floors"] = functools.partial(ns["partition_floors"], table=parted)
    with get_engine().connect() as c:
        floors = sorted(ns["partition_floors"](c))
        assert floors, "no boundaries to test against"
        ns["check_since"](c, floors[-1])                    # accepted, no raise
        with pytest.raises(SystemExit) as e:
            ns["check_since"](c, floors[-1][:-2] + "18")    # mid-week
    assert "not a market_snapshots partition boundary" in str(e.value)


def test_the_close_query_runs_with_the_floor_bound():
    """The other half of the floor: the scan's own CLOSE query, with
    `SCAN_SINCE` set, executed for real. A bind error there would have shown up
    the same way — after the guard passed, two minutes into an unattended run."""
    blk = SRC[SRC.index('_FLOOR = "'):SRC.index("def partition_floors")]
    ns: dict = {"SINCE": "2026-09-01"}
    exec(blk, ns)                                            # noqa: S102
    with get_engine().connect() as c:
        c.execute(text(ns["CLOSE"]),
                  {"pats": ["%-cfb-%"], "since": "2026-09-01"}).fetchmany(1)
