"""The scan's opt-in `captured_at` floor: prunes partitions, refuses to be wrong.

    pytest --noconftest tests/test_scan_floor.py

`cfb/run_scan.py` is a SCRIPT -- it builds an engine and runs the whole scan at
module level -- so it cannot be imported. These tests exec the shipped top-level
blocks and parse the shipped source. They therefore test the real file, not a
copy of it, which is the only version worth testing.
"""
from __future__ import annotations

import ast
import pathlib
import re

import pytest

SRC = (pathlib.Path(__file__).resolve().parents[1] / "cfb" / "run_scan.py").read_text()


def _exec_block(start: str, end: str, **names):
    blk = SRC[SRC.index(start):SRC.index(end)]
    ns = dict(names)
    exec(blk, ns)                                     # noqa: S102 - the shipped source
    return ns


def _func(name: str):
    """The shipped function, lifted out by AST so no module-level work runs.

    Every top-level def is lifted into ONE namespace, because `check_since`
    calls `partition_floors`; lifting them singly gave a NameError that looked
    like a bug in the source rather than in this harness.
    """
    tree = ast.parse(SRC)
    # Exactly the two under test, into one namespace. Lifting every def drags
    # in `_np`'s @event.listens_for and `fee(p, k=FEE_PM)`'s def-time default,
    # so the harness failed with NameErrors that read like source bugs.
    want = {"partition_floors", "check_since"}
    fns = [n for n in tree.body
           if isinstance(n, ast.FunctionDef) and n.name in want]
    ns: dict = {"re": re, "text": lambda q: q}
    exec(compile(ast.Module(body=fns, type_ignores=[]), "<scan>", "exec"), ns)  # noqa: S102
    return ns[name]


class _Conn:
    """Minimal stand-in: `execute(...).all()` returning one-tuples."""

    def __init__(self, bounds): self._b = bounds
    def execute(self, _q, _p=None): return self
    def all(self): return [(b,) for b in self._b]


# --------------------------------------------------------------------------- #
# The floor has to be OPT-IN. A default would be a silent population change.
# --------------------------------------------------------------------------- #
def test_absent_floor_means_the_clause_is_not_in_the_sql_at_all():
    """★ NOT a neutralised clause -- an ABSENT one. `(:since IS NULL OR ...)` does
    prune on postgres 16, but only while the planner builds a custom plan; after
    five executions a generic plan cannot fold `$1 IS NULL` and the pruning
    disappears with nothing to show it did. Two literal strings depend on
    nothing."""
    assert _exec_block('_FLOOR = "', "def partition_floors",
                       SINCE=None)["CLOSE"].count("captured_at >= :since") == 0


def test_a_floor_is_applied_to_BOTH_scans_not_just_one():
    """The query reads the table twice -- the kickoff CTE and the close -- so a
    floor on one of them prunes half the work and, worse, makes the two halves
    disagree about which games exist."""
    sql = _exec_block('_FLOOR = "', "def partition_floors", SINCE="2026-09-01")["CLOSE"]
    assert sql.count("captured_at >= :since") == 2
    # the CTE's copy is unqualified, the close's is qualified to the alias
    assert "AND captured_at >= :since" in sql
    assert "AND s.captured_at >= :since" in sql


def test_there_is_no_default_floor_in_the_source():
    """A default is the whole risk. Asserted against the source, because a
    default that appears later would pass every behavioural test above."""
    line = next(l for l in SRC.splitlines() if l.startswith("SINCE ="))
    assert 'os.environ.get("SCAN_SINCE")' in line
    assert not re.search(r'SCAN_SINCE"\s*,\s*["\']', line), f"default floor: {line}"


# --------------------------------------------------------------------------- #
# A floor that is not on a boundary is BOTH slower and narrower. Refuse it.
# --------------------------------------------------------------------------- #
_BOUNDS = [
    "FOR VALUES FROM ('2026-07-01 00:00:00+00') TO ('2026-08-01 00:00:00+00')",
    "FOR VALUES FROM ('2026-08-01 00:00:00+00') TO ('2026-09-01 00:00:00+00')",
    "FOR VALUES FROM ('2026-09-01 00:00:00+00') TO ('2026-10-01 00:00:00+00')",
    "DEFAULT",
]


def test_the_boundaries_are_read_from_the_catalogue_not_assumed_monthly():
    """★ THIS TEST FAILED TO FAIL AND HAD TO BE REWRITTEN. The first version fed
    it monthly bounds and asserted the monthly answer, so a `partition_floors`
    that IGNORED the catalogue and returned a hardcoded month list passed it --
    the mutant agreed with the fixture because the fixture agreed with the
    assumption.

    The population here is therefore WEEKLY, which no monthly assumption can
    produce. If retention ever moves off months, this is the test that notices;
    the monthly version would have gone on passing while pruning silently
    stopped."""
    weekly = [
        "FOR VALUES FROM ('2026-09-07 00:00:00+00') TO ('2026-09-14 00:00:00+00')",
        "FOR VALUES FROM ('2026-09-14 00:00:00+00') TO ('2026-09-21 00:00:00+00')",
        "DEFAULT",
    ]
    got = _func("partition_floors")(_Conn(weekly))
    assert got == {"2026-09-07", "2026-09-14"}, got
    assert not any(g.endswith("-01") for g in got), \
        "a month-shaped answer from weekly bounds means the catalogue was not read"
    # and DEFAULT, which has no FROM clause, is skipped rather than crashing
    assert _func("partition_floors")(_Conn(["DEFAULT"])) == set()


def test_a_mid_partition_floor_is_refused():
    """★ THE POINT OF THE GUARD. `2026-08-25` sits INSIDE the August partition,
    so postgres still reads the whole partition to filter rows: measured cost
    6.35M against 7.02M for no floor at all -- barely faster, and narrower.
    A parameter whose wrong values cost you both must reject them."""
    with pytest.raises(SystemExit) as e:
        _func("check_since")(_Conn(_BOUNDS), "2026-08-25")
    assert "not a market_snapshots partition boundary" in str(e.value)
    assert "2026-09-01" in str(e.value), "the error must name the valid choices"


def test_a_boundary_floor_is_accepted():
    """The control: the guard must be capable of passing, or it is just a
    refusal."""
    _func("check_since")(_Conn(_BOUNDS), "2026-09-01")          # no raise


def test_a_floor_with_a_time_component_is_judged_on_its_date():
    """`2026-09-01T00:00:00Z` is the same instant as the boundary and must not be
    refused for its formatting."""
    _func("check_since")(_Conn(_BOUNDS), "2026-09-01T00:00:00+00:00")


def test_a_floor_that_is_not_a_date_at_all_is_refused():
    """It is refused by the boundary check rather than by a date parser -- there
    is deliberately no parsing step, because the boundary set IS the whitelist
    and postgres's own cast catches anything that slips past the prefix."""
    with pytest.raises(SystemExit):
        _func("check_since")(_Conn(_BOUNDS), "last-tuesday")


# --------------------------------------------------------------------------- #
# The exclusion must be visible next to the count it produced.
# --------------------------------------------------------------------------- #
def test_the_floor_is_printed_on_the_same_line_as_the_closes_count():
    """★ A reader must not be able to see "22,870 closes" without seeing what
    was excluded to get it. In a footer it is a caveat nobody reads; on the
    same line it is part of the number."""
    line = next(l for l in SRC.splitlines() if "closes," in l and "settlement calls" in l)
    nxt = SRC.splitlines()[SRC.splitlines().index(line) + 1]
    assert "since=" in line or "since=" in nxt, f"floor not on the coverage line: {line}"
    assert "ALL (no floor)" in SRC, "an absent floor must say so, not print blank"


def test_the_guard_runs_before_the_first_scan_not_after_it():
    """Fail fast: validating inside the per-pattern loop would pay a 62M-row
    scan before telling the caller the floor was wrong -- and would re-query the
    catalogue once per pattern."""
    tree = ast.parse(SRC)
    calls, loops = [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "check_since":
            calls.append(node.lineno)
        if isinstance(node, ast.For):
            loops.append((node.lineno, max(getattr(n, "lineno", 0) for n in ast.walk(node))))
    assert calls, "check_since is never called -- the guard is dead"
    for c in calls:
        assert not any(lo < c <= hi for lo, hi in loops), \
            f"check_since at line {c} is inside a loop"


# --------------------------------------------------------------------------- #
# One query for thirteen patterns, and the attribution that makes it safe.
# --------------------------------------------------------------------------- #
def _attrib(needles):
    """`attribute` lifted with a chosen NEEDLES table."""
    tree = ast.parse(SRC)
    fns = [n for n in tree.body
           if isinstance(n, ast.FunctionDef) and n.name in {"attribute", "like_to_needle"}]
    ns: dict = {"re": re, "NEEDLES": needles, "SystemExit": SystemExit}
    exec(compile(ast.Module(body=fns, type_ignores=[]), "<scan>", "exec"), ns)  # noqa: S102
    return ns


def test_one_query_reads_the_table_twice_not_twenty_six_times():
    """★ THE WHOLE POINT. The table is read once per query for the kickoff CTE
    and once for the close, so one query per pattern was 26 passes over 57 GB --
    ~1.1 TB per run on a box with 7 GB of RAM, where nothing can be cached, and
    nine of thirteen patterns returned fifteen rows or fewer while still paying
    two full scans. Asserted on the SQL and on the absence of the old loop,
    because a rewrite that left one `LIKE :pat` behind would still work and
    still be slow."""
    assert SRC.count("LIKE ANY(:pats)") == 2
    assert "LIKE :pat " not in SRC and "LIKE :pat\n" not in SRC
    # exactly one execute of the close query, not one per pattern
    tree = ast.parse(SRC)
    execs = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and ast.unparse(n.func).endswith("execute")
             and "CLOSE" in ast.unparse(n)]
    assert len(execs) == 1, f"{len(execs)} executions of the close query"


def test_attribution_uses_the_query_patterns_not_league_of_slug():
    """Two attribution routes that can disagree would silently move rows between
    cells -- a population change to a registered result, wearing the costume of
    a faster scan. Asserted at the source: `league_of_slug` must not appear in
    the attribution path."""
    fn = SRC[SRC.index("def attribute("):SRC.index("#: Opt-in equivalence")]
    assert "league_of_slug" not in fn
    assert "NEEDLES" in fn


def test_a_slug_matching_two_patterns_kills_the_run():
    """★ AND THE OVERLAP IS NOT HYPOTHETICAL. `nfl-cfb-osu-mich-...` is a slug
    shape I produced by accident writing a board test an hour earlier; it
    contains `-cfb-` and would be counted under cfb while looking like an NFL
    slug to a human. If a slug ever matched two patterns its cell assignment
    would be whichever the loop saw first."""
    ns = _attrib([("cfb", "%-cfb-%", "-cfb-"), ("nfl", "%-nfl-%", "-nfl-")])
    assert ns["attribute"]("asc-cfb-osu-mich-2026-09-13") == ("cfb", "%-cfb-%")
    with pytest.raises(SystemExit) as e:
        ns["attribute"]("x-cfb-y-nfl-z")
    assert "matched 2 patterns" in str(e.value)


def test_a_slug_matching_no_pattern_kills_the_run():
    """Zero means the query returned something no pattern asked for -- either the
    SQL and the needles have drifted apart, or the LIKE conversion is wrong.
    Silently dropping it would shrink the population invisibly."""
    ns = _attrib([("cfb", "%-cfb-%", "-cfb-")])
    with pytest.raises(SystemExit) as e:
        ns["attribute"]("aec-wnba-conn-dal-2026-08-02")
    assert "matched 0 patterns" in str(e.value)


def test_the_like_conversion_refuses_a_pattern_it_cannot_reproduce():
    """A substring test is only equivalent to `%needle%` when the needle has no
    wildcards and the pattern is anchored at neither end. Anything else is
    refused rather than silently mis-matched -- the conversion is the join
    between the SQL population and the Python one."""
    ns = _attrib([])
    assert ns["like_to_needle"]("%-cfb-%") == "-cfb-"
    for bad in ("-cfb-%", "%-cfb-", "-cfb-", "%%", "%a%b%", "%a_b%"):
        with pytest.raises(SystemExit):
            ns["like_to_needle"](bad)


def test_the_real_patterns_all_convert():
    """The control: the refusal above must not reject the thirteen patterns the
    scan actually uses, or the program cannot start."""
    from core.leagues import LEAGUES, venue_patterns

    ns = _attrib([])
    pats = [p for lg in ("cfb", "nfl", "wnba", "mlb", "cricket", "tabletennis")
            if lg in LEAGUES for p in venue_patterns(lg)]
    assert len(pats) == 13, f"{len(pats)} patterns, expected 13"
    assert all(ns["like_to_needle"](p) for p in pats)
    # and no two of the real patterns can both match one slug
    needles = [ns["like_to_needle"](p) for p in pats]
    assert len(set(needles)) == len(needles)


def test_the_equivalence_check_is_opt_in_and_not_hardcoded():
    """Per-pattern counts are a fact about ONE tape window, not an invariant --
    the tape grows every minute. So the reference is passed in and compared
    exactly, never baked into the source where it would rot into a false
    failure."""
    assert 'os.environ.get("SCAN_EXPECT")' in SRC
    assert "SCAN_EXPECT mismatch" in SRC
    # no hardcoded reference counts anywhere in the file
    assert "15818" not in SRC and "15,818" not in SRC
