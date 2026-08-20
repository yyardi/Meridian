"""The replay loader's memory bounds.

No database. The bug these pin took the operator's laptop to 23GB of swap and
killed the Docker daemon with it, and a regression test that needs a live
16.75M-row archive is a test nobody runs — the same reasoning as
tests/test_analytics_memory.py.

What went wrong, so the shape is recognisable next time: `available_games()`
selected every live row in the archive and tallied them in a Python
defaultdict, to produce one count per game. 16.75M rows materialised for 56
numbers, once per replay process, and three replays were running at once.

The tests assert the SHAPE OF THE QUERY and the TYPE OF THE RETURN, because
both wrong versions produce identical output — a correct list of counts, a
correct list of ticks — and only the memory profile differs. Output-based tests
cannot see this class of bug at all.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from core.pulse import replay


class _StubResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def __iter__(self):
        return iter(self._rows)


class _StubSession:
    """Records statements and any execution options they were given."""

    def __init__(self, rows):
        self.rows = rows
        self.statements: list[str] = []
        self.options: list[dict] = []

    def execute(self, statement, *args, **kwargs):
        self.statements.append(str(statement))
        self.options.append(kwargs.get("execution_options") or {})
        return _StubResult(self.rows)


# ------------------------------------------------------------------ #
# available_games counts in the database
# ------------------------------------------------------------------ #


def test_available_games_groups_in_sql_rather_than_tallying_rows():
    session = _StubSession([("wnba-a-b-2026-08-01", 42)])
    replay.available_games(session)
    sql = session.statements[0].lower()
    assert "group by" in sql, "the count must happen in the database"
    assert "count(" in sql
    # One row per game comes back, so there is nothing to tally in Python.
    assert "having" in sql


def test_available_games_returns_counts_from_the_query_not_a_python_tally():
    session = _StubSession([("game-a", 900), ("game-b", 100)])
    assert replay.available_games(session) == [("game-a", 900), ("game-b", 100)]


def test_available_games_does_not_iterate_rows_to_count_them():
    """The defeated version looped over every returned row. Any per-row loop
    here is the bug returning, whatever the output looks like."""
    tree = ast.parse(inspect.getsource(replay.available_games).strip())
    loops = [n for n in ast.walk(tree) if isinstance(n, (ast.For, ast.AsyncFor))]
    assert not loops, (
        "available_games loops over rows again; it must let SQL aggregate")

    # AST for the accumulator too, NOT a substring search. The docstring above
    # necessarily names `defaultdict` to explain the bug, so `"defaultdict" not
    # in source` fails on the explanation — I wrote exactly that bug here, two
    # hours after fixing the identical one in tests/test_analytics_memory.py.
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert "defaultdict" not in names | attrs


def test_min_ticks_filters_in_sql():
    """Filtering after materialising would defeat the point of the HAVING."""
    session = _StubSession([])
    replay.available_games(session, min_ticks=500)
    assert "having" in session.statements[0].lower()


# ------------------------------------------------------------------ #
# Ticks stream rather than buffer
# ------------------------------------------------------------------ #


def test_stream_ticks_returns_an_iterator_not_a_list():
    """A list here is a whole game in memory. The type IS the guarantee."""
    session = _StubSession([])
    out = replay.stream_ticks(session, event_slug="g")
    assert not isinstance(out, list)
    assert hasattr(out, "__next__")


def test_streaming_asks_the_driver_for_batches():
    session = _StubSession([])
    list(replay.stream_ticks(session, event_slug="g"))
    assert any(o.get("yield_per") for o in session.options), (
        "without yield_per the driver buffers the entire result set")
    assert replay.TICK_BATCH >= 1000


def test_load_ticks_still_returns_a_list_for_callers_that_reiterate():
    """Some callers walk the ticks twice — a second strategy arm, or a span
    computed up front. A generator consumed twice yields nothing the second
    time, SILENTLY, which is why both readers exist."""
    session = _StubSession([])
    assert isinstance(replay.load_ticks(session, event_slug="g"), list)


def test_replay_all_uses_the_streaming_reader():
    src = inspect.getsource(replay.replay_all)
    assert "stream_ticks(" in src, (
        "replay_all consumes each game once; listing it holds a whole game "
        "in memory for no reason")
    assert "load_ticks(" not in src


def test_replay_game_accepts_any_iterable():
    """It must not re-annotate to list[Tick] — that invites a caller to
    materialise what it only iterates once."""
    sig = inspect.signature(replay.replay_game)
    annotation = sig.parameters["ticks"].annotation
    assert annotation in (inspect.Parameter.empty, "ticks"), (
        f"replay_game pins its input to {annotation!r}; keep it iterable")


def test_the_module_carries_no_other_whole_archive_scan():
    """Any `.all()` on a statement without a LIMIT, GROUP BY or per-game WHERE
    is the same bug wearing a different name."""
    src = Path(replay.__file__).read_text()
    tree = ast.parse(src)
    bad = [
        node.lineno for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "all"
    ]
    # Exactly one survives: available_games, whose statement is grouped.
    assert len(bad) <= 1, f"unbounded .all() calls at lines {bad}"
