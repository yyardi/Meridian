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
                       SINCE=None)["CLOSE"].count(":since") == 0


def test_a_floor_is_applied_to_BOTH_scans_not_just_one():
    """The query reads the table twice -- the kickoff CTE and the close -- so a
    floor on one of them prunes half the work and, worse, makes the two halves
    disagree about which games exist."""
    sql = _exec_block('_FLOOR = "', "def partition_floors", SINCE="2026-09-01")["CLOSE"]
    # Matched on the BOUND NAME, not on a spelling of the cast. The first
    # version asserted `captured_at >= :since`, which pinned the exact defect
    # that killed the 09:52Z run: `:since::timestamptz` binds NOTHING, because
    # SQLAlchemy will not recognise a parameter followed by a colon. A test that
    # pins a broken spelling defends it.
    assert sql.count(":since") == 2
    assert "AND captured_at >= CAST(:since" in sql        # the CTE's copy
    assert "AND s.captured_at >= CAST(:since" in sql      # the close's copy
    # and the cast must be the form that actually binds
    assert "::timestamptz" not in sql, (
        "a parameter immediately followed by `::` is not bound by SQLAlchemy")


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
    # SCOPED TO THE CLOSE QUERY, which is this test's subject. It used to count
    # over the whole file, and it caught a real defect doing so: my first
    # START_LAG used `LIKE :pat`, which would have been 13 more full scans of a
    # 57 GB table -- exactly what this rewrite removed. But the assertion cannot
    # stay file-wide, or no second query may ever exist. The close query reads
    # the table twice, once for the kickoff CTE and once for the close, and that
    # is what is pinned here.
    close = SRC[SRC.index("CLOSE_SQL = "):SRC.index("CLOSE = CLOSE_SQL.format")]
    assert close.count("LIKE ANY(:pats)") == 2
    assert ":pat " not in close and ":pat\n" not in close, (
        "the close query is per-pattern again -- that is 26 full passes over a "
        "57 GB table")
    # and no OTHER query may be per-pattern either, which is the file-wide half
    assert "LIKE :pat" not in SRC, (
        "a per-pattern LIKE remains somewhere: every one is a full scan")
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


# --------------------------------------------------------------------------- #
# The artifact writers, and the floor the equivalence check is pinned to.
# --------------------------------------------------------------------------- #
def test_a_numpy_scalar_no_longer_kills_the_artifact_write(tmp_path):
    """★ THE 05:28Z RUN OF 2026-09-14 DIED HERE. `p_lt_01` is
    `sum(p < 0.01 for p in ps)` over scipy p-values -- a numpy int64 -- and
    `json.dump` raised after writing 225 bytes, leaving CELLS_JSON as truncated,
    unparseable JSON with a plausible size and a fresh mtime. The scan exited 1
    as its contract promises; the artifact it left behind was worse than none."""
    import json as _json

    # ONE namespace, used as globals: `_write_json` looks `_plain` up in its
    # own globals, so exec'ing with separate globals/locals hid it and the
    # NameError read like a bug in the source.
    ns = {"os": __import__("os"), "json": _json}
    exec(SRC[SRC.index("def _plain("):
             SRC.index('if os.environ.get("ROWS_JSON")')], ns)  # noqa: S102

    class _Int64:                      # what numpy hands json.dump
        def item(self): return 34

    # ★ THROUGH `_write_json`, NOT `_plain` ALONE. My first version called
    # `json.dumps(..., default=_plain)` itself, so deleting the `default=_plain`
    # wiring inside `_write_json` broke nothing -- I was testing the helper and
    # not the thing that uses it, the same gap a mutation found in the live_fv
    # `usable` propagation an hour earlier.
    out = tmp_path / "cells.json"
    ns["_write_json"](str(out), {"p_lt_01": _Int64()})
    assert _json.loads(out.read_text()) == {"p_lt_01": 34}

    # and it stays NARROW -- a genuinely unserialisable object must still raise
    with pytest.raises(TypeError):
        ns["_write_json"](str(tmp_path / "x.json"), {"x": object()})


def test_a_crash_mid_write_leaves_the_old_artifact_not_half_a_new_one(tmp_path):
    """The idiom is lifted from `core/settlements.py`, which has had it for
    weeks. A partial artifact that looks complete is the failure both guard
    against, and only one of them was doing it."""
    import json as _json

    # ONE namespace, used as globals: `_write_json` looks `_plain` up in its
    # own globals, so exec'ing with separate globals/locals hid it and the
    # NameError read like a bug in the source.
    ns = {"os": __import__("os"), "json": _json}
    exec(SRC[SRC.index("def _plain("):
             SRC.index('if os.environ.get("ROWS_JSON")')], ns)  # noqa: S102

    target = tmp_path / "cells.json"
    target.write_text('{"run": "previous"}', encoding="utf-8")
    with pytest.raises(TypeError):
        ns["_write_json"](str(target), {"ok": 1, "bad": object()})
    # the OLD file survives, intact and parseable
    assert _json.loads(target.read_text())["run"] == "previous"
    assert not list(tmp_path.glob("*.tmp")), "temp file left behind"
    # and a good write replaces it
    ns["_write_json"](str(target), {"run": "new"})
    assert _json.loads(target.read_text())["run"] == "new"


def test_the_equivalence_reference_must_declare_its_floor():
    """★ A GUARD THAT FIRES ON A CORRECT CHANGE TRAINS PEOPLE TO IGNORE IT.
    Row counts depend on the floor as well as the window: the 05:28Z reference
    was taken with NO floor, and cfb, nfl and wnba all have pre-September tape,
    so a floored run legitimately returns fewer rows for them. A floor mismatch
    is a refusal to compare, not a count mismatch. Asserted at the source
    because the check runs at import, before anything is testable."""
    # ★ RUN IT, DO NOT GREP FOR IT. My first version asserted the error strings
    # were present in the source -- and a mutation that replaced the condition
    # with `if False:` left every string in place and passed. A disabled branch
    # is invisible to a source-text assertion.
    blk = SRC[SRC.index("_EXP = dict("):SRC.index("\n\n", SRC.index("_ref != SINCE"))]

    def _run(scan_expect, since):
        ns = {"os": type("O", (), {"environ": {"SCAN_EXPECT": scan_expect}})(),
              "SINCE": since, "SystemExit": SystemExit}
        exec(blk, ns)                                        # noqa: S102
        return ns

    # a reference with no floor term cannot be compared at all
    with pytest.raises(SystemExit) as e:
        _run("%-cfb-%=10", None)
    assert "missing its `since=` term" in str(e.value)

    # floored run against an unfloored reference: REFUSED, not a count mismatch
    with pytest.raises(SystemExit) as e:
        _run("since=NONE,%-cfb-%=10", "2026-09-01")
    assert "not comparable across floors" in str(e.value)

    # and the matching cases pass through to the count comparison
    assert _run("since=NONE,%-cfb-%=10", None)["EXPECT"] == {"%-cfb-%": 10}
    assert _run("since=2026-09-01,%-cfb-%=10", "2026-09-01")["EXPECT"] == {"%-cfb-%": 10}
    # no reference at all is not an error
    assert _run("", None)["EXPECT"] == {}


# --------------------------------------------------------------------------- #
# The close COUNT is a label; the close AGE is the thing that varies.
# --------------------------------------------------------------------------- #
def _age_summary():
    tree = ast.parse(SRC)
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "age_summary")
    ns: dict = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "<scan>", "exec"), ns)  # noqa: S102
    return ns["age_summary"]


def test_the_coverage_line_carries_the_close_age_not_just_the_count():
    """★ A COUNT OF CLOSES WITHOUT THEIR AGE MISDESCRIBES ITS POPULATION.
    Football closes at the whistle; table tennis does not. Measured 2026-09-01
    onward on the scan's own population, close age / event duration: cfb median
    0.000 p90 0.001, nfl 0.000/0.000, tabletennis **0.405 / 5.852** -- a median
    table-tennis close is 40% of a ~14-minute match before it starts and the p90
    is nearly six matches. No artifact reported it, so every table-tennis number
    the programme produced described a population nobody had measured."""
    assert "close_age_min" in SRC
    line = next(ln for ln in SRC.splitlines() if "closes," in ln and "settlement calls" in ln)
    assert "age_summary(ages)" in line, f"age not on the coverage line: {line}"


def test_age_summary_separates_football_from_table_tennis():
    """The discriminating property, on the two real shapes. If these collapsed to
    the same string the statistic would not be worth printing."""
    A = _age_summary()
    football = A([0.0] * 50)
    tt = A([2, 5, 8, 8, 12, 20, 34, 44, 90, 141])
    assert football == "age med 0m p90 0m >1h 0%"
    assert football != tt
    assert ">1h 20%" in tt and "p90 90m" in tt
    # and an empty pattern says so rather than printing a zero that reads as fresh
    assert A([]) == "age n/a", "no closes must not render as a 0-minute age"


def test_the_circularity_is_printed_not_implied():
    """★ THE AGE IS COMPUTED FROM `game_start_time`, THE SAME COLUMN THE CLOSE
    SELECTION USES, so it agrees with itself by construction and cannot detect a
    wrong schedule. The only independent handle is `event_period` leaving its
    pregame state -- an observation, not a schedule -- and it covers a minority
    of games: table tennis has 249 in-play rows across 386 games since
    2026-09-01, 82 games with any observed play. So it validates rather than
    replaces, and both facts are printed. Measured: scheduled start LEADS
    observed play by a median 2.5 min in cfb (159 games) and 6.6 in table tennis
    (82), so the circular age UNDERSTATES the true one."""
    assert "START_LAG" in SRC
    assert "cannot detect a wrong schedule" in SRC
    assert "NO independent check possible" in SRC, (
        "a league with no observed play must say the age is circular, not go quiet")
    # the independent query must not read game_start_time as its start signal
    lag = SRC[SRC.index('START_LAG = """'):]
    lag = lag[:lag.index('"""', 15)]
    assert "event_period" in lag, "the independent check is not independent"
    # and it must survive its own failure rather than killing the scan
    assert "start-lag unavailable" in SRC
