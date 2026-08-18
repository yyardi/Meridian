"""The analytics job's memory bound and its one-pass contract.

These tests take no database. That is deliberate: the bug they pin took the
operator's machine to ~9GB RSS and forced a restart, and a regression test that
needs a live 13.7M-row archive to run is a test nobody runs.

What is actually asserted:

* **the producer issues ONE query, not two.** The original ran the
  market_snapshots aggregate twice — once for counts, once to ship ~96k rows to
  Python for squaring. Counting the queries is the only way to catch that
  reappearing, because the OUTPUT is identical either way.
* **aggregation happens in SQL.** The query text must contain the Brier means
  and must not select raw per-prediction probabilities.
* **no ORM entities are loaded in the backtest odds path**, which is what the
  session's identity map was retaining across all three fill models.
* **the emitted shape is unchanged**, so the memory fix cannot quietly break
  the renderer contract agreed with Builder A.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from core import analytics


class _StubResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _StubSession:
    """Records every statement it is asked to execute."""

    def __init__(self, rows):
        self.rows = rows
        self.statements: list[str] = []

    def execute(self, statement, *args, **kwargs):
        self.statements.append(str(statement))
        return _StubResult(self.rows)


# One row per (type, phase) as the aggregate now returns them:
# type, phase, n_preds, n_resolved, n_games, brier_model, brier_market
_AGG_ROWS = [
    ("basketball_team_full_game_total", "pregame", 50535, 45841, 54, 0.2181, 0.2063),
    ("basketball_team_full_game_total", "ingame", 94, 94, 5, 0.1900, 0.1800),
    ("basketball_team_full_game_winner", "pregame", 11636, 10000, 60, 0.2400, 0.2300),
    ("basketball_team_full_game_spread", "pregame", 44797, 40636, 54, 0.2500, 0.2400),
]


@dataclass
class _Metrics:
    n_bets: int = 0
    n_filled: int = 0
    n_wins: int = 0
    n_resolved: int = 0
    total_pnl: float = 0.0
    total_staked: float = 0.0
    total_fees: float = 0.0
    clv_points: list[float] = field(default_factory=list)
    n_with_closing_line: int = 0
    hit_rate = roi = mean_clv = clv_stderr = None


@dataclass
class _Result:
    metrics: _Metrics = field(default_factory=_Metrics)
    bets: list = field(default_factory=list)


# ------------------------------------------------------------------ #
# The one-pass contract
# ------------------------------------------------------------------ #


def test_the_producer_issues_exactly_one_query():
    """Two queries is the bug. The output is the same either way, so the query
    count is the only thing that can catch a regression here."""
    session = _StubSession(_AGG_ROWS)
    analytics._prediction_rows(session)
    assert len(session.statements) == 1, (
        f"expected one aggregate, got {len(session.statements)}")


def test_the_query_aggregates_in_sql_rather_than_in_python():
    session = _StubSession(_AGG_ROWS)
    analytics._prediction_rows(session)
    sql = session.statements[0].lower()
    # The means are computed by the database.
    assert "avg(power(" in sql and sql.count("avg(power(") == 2
    assert "count(distinct p.game_id)" in sql
    # And no raw per-prediction probability is selected for Python to square.
    assert not re.search(r"select\s+p\.model_probability", sql)


def test_the_snapshot_aggregate_is_pruned_to_markets_that_have_predictions():
    """13.7M rows aggregated for six output values is the cost being avoided.
    Pruning cannot change the result — a snapshot with no prediction has
    nothing to join to."""
    session = _StubSession(_AGG_ROWS)
    analytics._prediction_rows(session)
    sql = session.statements[0].lower()
    assert "market_slug in (select distinct market_slug from predictions)" in sql


def test_rows_are_folded_by_type_and_phase_with_briers_preserved():
    session = _StubSession(_AGG_ROWS)
    out = analytics._prediction_rows(session)
    assert out[("total", "pregame")]["n_preds"] == 50535
    assert out[("total", "pregame")]["brier_model"] == 0.2181
    assert out[("total", "pregame")]["brier_market"] == 0.2063
    assert out[("winner", "pregame")]["n_games"] == 60
    assert ("spread", "ingame") not in out          # absent, not fabricated


def test_a_null_brier_stays_null_and_never_becomes_zero():
    """A slice with nothing resolved has no Brier. Zero would read as a perfect
    score — the same null-never-zero rule the renderer contract depends on."""
    session = _StubSession([
        ("basketball_team_full_game_spread", "ingame", 84, 0, 5, None, None),
    ])
    out = analytics._prediction_rows(session)
    assert out[("spread", "ingame")]["brier_model"] is None
    assert out[("spread", "ingame")]["brier_market"] is None


# ------------------------------------------------------------------ #
# The emitted shape must survive the memory fix
# ------------------------------------------------------------------ #


def test_by_market_type_still_emits_the_agreed_shape():
    """The renderer is already merged against this shape. A memory fix that
    changes it would break a page that is live."""
    session = _StubSession(_AGG_ROWS)
    block = analytics.by_market_type(session, _Result())

    assert set(block) == {"rows", "caption"}
    assert len(block["rows"]) == 6              # 3 types x 2 phases, always
    row = block["rows"][0]
    assert set(row) == {
        "type", "phase", "n_preds", "n_resolved", "n_games",
        "brier_model", "brier_market", "clv", "money", "backtested", "note",
    }
    # Exactly one row is the backtested slice, and it is totals/pregame.
    backtested = [r for r in block["rows"] if r["backtested"]]
    assert len(backtested) == 1
    assert (backtested[0]["type"], backtested[0]["phase"]) == ("total", "pregame")


# ------------------------------------------------------------------ #
# The identity-map bound, asserted against the source
# ------------------------------------------------------------------ #


def test_the_odds_path_loads_columns_not_orm_entities():
    """`session.scalars(select(SportsbookOdds))` returns ORM instances, and the
    identity map keeps a strong reference to each for the session's life.
    build() shares ONE session across three fill models, so that retained a
    full traversal of sportsbook_odds for the entire run. Selecting columns
    instead keeps peak memory at one game's odds.
    """
    src = (Path(analytics.__file__).parent / "backtest" / "engine.py").read_text()

    # AST, not a substring search: this file's own comments explain the bug and
    # necessarily contain the offending call text. A grep matches the
    # explanation and reports a bug that is not there — which is exactly the
    # kind of false signal a regression test must not produce.
    calls = [
        node for node in ast.walk(ast.parse(src))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "scalars"
    ]
    assert not calls, (
        f"{len(calls)} ORM-entity load(s) in the backtest path (line(s) "
        f"{[c.lineno for c in calls]}); the shared session retains them for "
        "the whole analytics run")
    assert "SportsbookOdds.provider_name," in src


def test_build_clears_orm_state_between_fill_models():
    src = Path(analytics.__file__).read_text()
    assert "s.expunge_all()" in src, (
        "three backtests share one session; without a clear between them the "
        "identity map grows for the whole run")


def test_progress_reports_stages_and_peak_memory():
    """A run that cannot finish must at least say what it is doing and that
    memory is climbing. Silence is what made the OOM a restart."""
    src = Path(analytics.__file__).read_text()
    assert "_peak_rss_mb" in src and "TOTAL" in src
    assert analytics._peak_rss_mb() > 0
