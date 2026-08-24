"""The two-table redesign: one lines table, one trades table, nothing else.

Operator: "simplify the infra honestly theres 3 or 4 tables. we just need 2."
The three fragments (live-FV strip, live-totals strip, EV-guard panel) are
deleted from the page; their content lives in the two tables. Performance was
measured before and after — the numbers are in the PR.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.api import app

PAGE = Path("static/index.html")


@pytest.fixture(scope="module")
def html() -> str:
    return PAGE.read_text()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _fn(html: str, signature: str) -> str:
    i = html.index(signature)
    depth, j = 0, html.index("{", i)
    for k in range(j, len(html)):
        if html[k] == "{":
            depth += 1
        elif html[k] == "}":
            depth -= 1
            if depth == 0:
                return html[i:k + 1]
    raise AssertionError(f"unbalanced braces after {signature!r}")


def test_the_three_fragments_are_gone(html):
    for gone in ("loadLiveFV", "loadLiveTotals", "loadEVGuard",
                 'id="livefv"', 'id="livetot"', 'id="evguard"'):
        assert gone not in html, f"{gone} crept back — a third view of one model"


def test_the_strip_scores_resource_from_pulse(html):
    """The deleted FV loader used to populate LIVE_CTX as a side effect; the
    strip's scores now come from PULSE's own estimates."""
    fn = _fn(html, "function rebuildLiveCtx(){")
    assert "PULSE_LATEST" in fn
    assert "rebuildLiveCtx();" in _fn(html, "async function loadPulseLatest(league){")


def test_the_ribbon_shows_deltas_vs_the_market(html):
    """A judgment surface: agreement is only checkable against the market's
    own number. WP carries its delta vs the ML mid; the projection carries
    its delta vs the closest-to-the-money line."""
    fn = _fn(html, "function renderPulseFeed(){")
    assert "vs mkt" in fn
    assert "projection minus the closest-to-the-money line" in fn


def test_the_margin_gap_is_named_not_papered(html):
    """No margin projection exists (verified against the production export's
    39 columns, and C2's engine at v3 head). The ribbon says so instead of
    inventing an estimator."""
    fn = _fn(html, "function renderPulseFeed(){")
    assert "No margin projection exists" in fn
    assert "direction, not distance" in fn


def test_the_trades_table_shows_reason_in_a_column(html):
    sec = _fn(html, "function liveTradingSection(g){")
    assert ">Reason</th>" in sec
    assert "f.reason" in sec


def test_results_ships_no_rows_by_default(client):
    d = client.get("/api/results").json()
    assert d["results"] == []
    assert "n_rows_computed" in d
    assert "summary" in d, "the KPIs still compute over the full window"
    d2 = client.get("/api/results?include_rows=true").json()
    assert isinstance(d2["results"], list)
