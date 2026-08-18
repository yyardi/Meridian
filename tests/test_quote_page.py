"""The QUOTE page: an accruing measurement rendered without inventing a verdict.

The page's honesty contract is the pre-registered one
(docs/math/quote-shadow.md): floors are 500 settled fills AND 10 games per
regime, and until both are met the only honest render is "accruing — no
verdict yet". The endpoint serializes core.quote.report.build_report verbatim
and the page displays the server's verdict string — it never computes one.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.api import app

PAGE = Path("static/quote.html")


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


# ------------------------------------------------------------------ #
# Routes and payload
# ------------------------------------------------------------------ #


def test_the_page_is_served(client):
    r = client.get("/quote")
    assert r.status_code == 200
    assert "QUOTE" in r.text


def test_the_endpoint_carries_the_registered_floors(client):
    from core.quote.report import FLOOR_FILLS, FLOOR_GAMES

    d = client.get("/api/quote").json()
    assert d["floors"] == {"fills": FLOOR_FILLS, "games": FLOOR_GAMES}, (
        "the floors on the page must BE the pre-registered constants, "
        "never a copy that can drift")
    assert "regimes" in d and "quoting" in d and "recent_fills" in d


def test_the_endpoint_is_get_only():
    """Display only. A POST to it must not exist."""
    routes = {r.path: r.methods for r in app.routes if hasattr(r, "methods")}
    assert routes.get("/api/quote") == {"GET"}


# ------------------------------------------------------------------ #
# The page never invents a verdict
# ------------------------------------------------------------------ #


def test_below_the_floor_renders_accruing_never_a_verdict(html):
    card = _fn(html, "function regimeCard(name, r, floors){")
    assert "accruing — no verdict yet" in card
    assert "r.at_floor" in card, "the branch must be the server's at_floor"
    assert "r.verdict" in card, "above the floor, the SERVER's verdict verbatim"


def test_the_page_does_not_recompute_the_measurement(html):
    """Serialized verbatim; rendered verbatim. The page may derive a per-fill
    capture mark for the recent-fills table, but never a regime verdict, an
    ROI, or a confidence interval.

    Asserted on the property, not on vocabulary: the card must READ the
    server's numbers (r.roi.mean, r.capture.mean, the CI bounds) and must
    contain no aggregation machinery of its own. A first draft banned the
    word "clustered" and tripped on a tooltip describing the CI — the
    findings.md proxy-check mistake, in a test written the same day the doc
    merged."""
    card = _fn(html, "function regimeCard(name, r, floors){")
    for read in ("cap.mean", "roi.mean", "cap.lo", "roi.lo"):
        assert read in card, f"the card must render the server's {read}"
    for machinery in ("Math.sqrt", ".reduce(", "stddev", "n_clusters -"):
        assert machinery not in card, f"{machinery} is aggregation, not rendering"


def test_the_explainer_says_what_quote_is_and_that_nothing_is_sent(html):
    for phrase in ("posts both sides", "adverse selection", "−2.74¢",
                   "requoting", "Nothing is sent"):
        assert phrase in html, f"the explainer lost {phrase!r}"


def test_the_reconstruction_is_labelled_as_one(html):
    """Current quotes are rebuilt from the same observations via the engine's
    own imported code — the page must say the engine's memory is not read."""
    assert "engine's own code" in html
    assert "memory is not readable" in html


def test_league_tabs_filter_live_tables_but_never_the_measurement(html):
    assert 'id="lgtabs"' in html
    assert "inLeague" in html
    assert "registered regime-split, not league-split" in html


# ------------------------------------------------------------------ #
# The endpoint reuses the engine's code rather than restating it
# ------------------------------------------------------------------ #


def test_the_endpoint_uses_the_engines_observation_class():
    import inspect

    from core import api

    src = inspect.getsource(api.quote_status)
    assert "ShadowQuoter._observations" in src, (
        "the quotable band must come from the engine's own class — two "
        "renderings of one rule is the drift this repo keeps re-learning")
    assert "build_report" in src
