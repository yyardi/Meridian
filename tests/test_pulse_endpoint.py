"""`/api/pulse`: the PULSE record on the Model-performance page.

The contract is `/api/quote`'s: serialize `core.pulse.live_report` verbatim,
carry the module's own floors, and let the page render the server's verdict
rather than compute one.

History worth keeping, because it is why this file exists at all. The
endpoint was written 2026-08-18 against a `build_report` that returned ONE
report; 1f69c30 (2026-08-22) made it return `dict[version -> LiveReport]` —
era separation, v1 and v2 are different models and are never blended — and
did not update the endpoint. `r.n_decisions` on a dict is an AttributeError,
so it was a 500 on every request, empty database or not, for two weeks.

Nothing failed. No test called the endpoint, and the page's `catch(e)`
rendered a tidy "unavailable" that reads exactly like "no data yet".

`mgr/pulse-direction` fixed the endpoint by reporting the NEWEST version.
These tests pin that behaviour, and the thing it was still missing: the
payload now says WHICH version, because unlabelled counts read as PULSE's
whole record when an earlier model's record is being deliberately excluded.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from core.api import app
from core.storage import get_engine, get_sessionmaker

PAGE = Path("static/analytics.html")
UTC = dt.timezone.utc
SLUG = "wnba-endpointtest-aaa-bbb-2099-01-01"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def two_versions():
    """One filled entry under v1, one under v2 — the shape that broke it."""
    Session = get_sessionmaker(get_engine())
    at = dt.datetime(2099, 1, 1, tzinfo=UTC)

    def _wipe(s):
        s.execute(text("DELETE FROM pulse_decisions WHERE event_slug = :e"),
                  {"e": SLUG})
        s.commit()

    with Session() as s:
        _wipe(s)
        for i, version in enumerate(("v1", "v2")):
            s.execute(text("""
                INSERT INTO pulse_decisions
                    (decided_at, event_slug, market_slug, sports_market_type,
                     strategy, phase, action, side, limit_price, contracts,
                     stake_usd, minutes_left_is_estimate, filled_at,
                     estimates_version)
                VALUES (:at, :e, :m, 'total', 'total', 'in_play', 'enter',
                        'yes', 0.5, 10, 5.0, false, :at, :v)
            """), {"at": at, "e": SLUG, "m": f"tsc-endpointtest-{i}",
                   "v": version})
        s.commit()
    yield
    with Session() as s:
        _wipe(s)


# ------------------------------------------------------------------ #
# It answers at all — the regression, in two lines
# ------------------------------------------------------------------ #


def test_the_endpoint_answers_on_an_empty_record(client):
    """Empty is a real state — the engine has not run — and must render as
    counts, not as a 500."""
    r = client.get("/api/pulse")
    assert r.status_code == 200, r.text[:400]


def test_the_endpoint_answers_with_decisions_recorded(client, two_versions):
    r = client.get("/api/pulse")
    assert r.status_code == 200, r.text[:400]


def test_the_endpoint_carries_the_registered_floors(client):
    from core.pulse.live_report import FLOOR_ENTRY_FILLS, FLOOR_GAMES

    d = client.get("/api/pulse").json()
    assert d["floors"] == {"entry_fills": FLOOR_ENTRY_FILLS,
                           "games": FLOOR_GAMES}, (
        "the floors on the page must BE the module's constants, never a copy "
        "that can drift")


def test_the_endpoint_is_get_only():
    routes = {r.path: r.methods for r in app.routes if hasattr(r, "methods")}
    assert routes.get("/api/pulse") == {"GET"}


def test_an_empty_record_says_so_rather_than_looking_like_a_zero(client):
    d = client.get("/api/pulse").json()
    if not d.get("available", True):
        assert "floors" in d, "the empty payload still drives the floors text"
        assert "n_decisions" not in d, (
            "a zero count is a measurement; 'no decisions recorded' is not")


# ------------------------------------------------------------------ #
# One version, and it says which
# ------------------------------------------------------------------ #


def test_the_payload_is_one_version_and_names_it(client, two_versions):
    """v1 and v2 are different models. The endpoint reports the newest rather
    than a blend — and the reader has to be told which, or the counts read as
    PULSE's whole record."""
    d = client.get("/api/pulse").json()
    assert d["version"] == "v2", d.get("version")
    assert d["n_versions"] >= 2, d.get("n_versions")
    assert d["n_entry_fills"] == 1, (
        "one fill under v2 — a blend of both versions would read 2, which is "
        "the era-separation bug PR #23 deleted")


def test_the_verdict_is_the_reports_own(client, two_versions):
    d = client.get("/api/pulse").json()
    assert d["at_floor"] is False, "one fill is far below the floors"
    assert d["verdict"] == "NO DATA", (
        "below a floor the verdict is the report's own NO DATA — the page "
        "must never be handed a performance number it could render")


# ------------------------------------------------------------------ #
# The page renders what the endpoint sends
# ------------------------------------------------------------------ #


@pytest.fixture(scope="module")
def html() -> str:
    return PAGE.read_text()


def _fn(html: str, signature: str) -> str:
    """One function's source, brace-matched, so an assertion about the fetcher
    cannot be satisfied by a helper below it."""
    i = html.index(signature)
    depth, j = 0, html.index("{", i)
    for k in range(j, len(html)):
        depth += 1 if html[k] == "{" else -1 if html[k] == "}" else 0
        if depth == 0:
            return html[i:k + 1]
    raise AssertionError(f"unbalanced braces after {signature!r}")


def test_the_panel_names_the_estimates_version(html):
    body = _fn(html, "async function loadPulse()")
    assert "d.version" in body and "ESTIMATES" in body, (
        "unlabelled, the newest version's counts read as PULSE's whole record")
    assert "n_versions" in body, (
        "and the reader must be told an earlier version exists and is excluded")


def test_the_page_says_when_the_endpoint_is_broken(html):
    """A tidy "unavailable" reads as "no data yet" and hid a 500 for two
    weeks. The failure branch must name it as a failure, and must be REACHED
    on a 500 — `fetch` does not throw on one."""
    body = _fn(html, "async function loadPulse()")
    assert "failed" in body or "error" in body.lower(), (
        "the catch branch must distinguish a broken endpoint from an empty "
        "record")
    assert ".ok" in body, (
        "fetch resolves on a 500 — without an r.ok check the failure lands in "
        "the JSON parse, or worse, renders as empty")
