"""PULSE's estimates on the board's in-play rows — alive, labelled, unorderable.

During a live game the pregame model is correctly silent, so the board showed
dashes while PULSE decided one table away. In-play rows now wear PULSE's
latest estimate — from the same rows the deep-dive tape reads — clearly
labelled as PULSE, and structurally unable to become an order.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from core.api import PULSE_LATEST_MAX_AGE_SECONDS, app
from core.storage import get_engine, get_sessionmaker

UTC = dt.timezone.utc
PAGE = Path("static/index.html")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def Session():
    return get_sessionmaker(get_engine())


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


@pytest.fixture()
def pulse_rows(Session):
    now = dt.datetime.now(UTC)
    with Session() as s:
        s.execute(text("DELETE FROM pulse_decisions WHERE market_slug LIKE '%pobtest%'"))
        for at, slug, action, fv in (
            (now - dt.timedelta(seconds=30), "tsc-wnba-pobtest-1", "hold", 0.61),
            (now - dt.timedelta(seconds=5), "tsc-wnba-pobtest-1", "enter", 0.63),
            # stale: outside the window, must not be served
            (now - dt.timedelta(seconds=PULSE_LATEST_MAX_AGE_SECONDS + 60),
             "tsc-wnba-pobtest-2", "enter", 0.40),
        ):
            s.execute(text("""
                INSERT INTO pulse_decisions
                    (decided_at, event_slug, market_slug, sports_market_type,
                     strategy, phase, action, side, limit_price, contracts,
                     stake_usd, minutes_left_is_estimate, fair_value, edge_net,
                     market_bid, market_ask, score, period)
                VALUES (:at, 'wnba-pobtest-9999-01-01', :slug, 'total', 'total',
                        'in_play', :action, 'yes', 0.55, 1, 0.55, false,
                        :fv, 0.021, 0.54, 0.58, '40-38', 'Q3')
            """), {"at": at, "slug": slug, "action": action, "fv": fv})
        s.commit()
    yield
    with Session() as s:
        s.execute(text("DELETE FROM pulse_decisions WHERE market_slug LIKE '%pobtest%'"))
        s.commit()


# ------------------------------------------------------------------ #
# The endpoint
# ------------------------------------------------------------------ #


def test_latest_decision_per_market_and_only_fresh_ones(client, pulse_rows):
    d = client.get("/api/pulse/latest?league=wnba").json()
    m = d["markets"]
    assert "tsc-wnba-pobtest-1" in m
    row = m["tsc-wnba-pobtest-1"]
    assert row["action"] == "enter", "must be the NEWEST decision, not the first"
    assert row["fair_value"] == 0.63
    assert row["edge_net"] == 0.021
    assert "tsc-wnba-pobtest-2" not in m, (
        "a decision older than the freshness window must not paint the board")


def test_the_endpoint_is_league_scoped_and_get_only(client, pulse_rows):
    d = client.get("/api/pulse/latest?league=nba").json()
    assert "tsc-wnba-pobtest-1" not in d["markets"]
    routes = {r.path: r.methods for r in app.routes if hasattr(r, "methods")}
    assert routes.get("/api/pulse/latest") == {"GET"}


# ------------------------------------------------------------------ #
# The page
# ------------------------------------------------------------------ #


@pytest.fixture(scope="module")
def html() -> str:
    return PAGE.read_text()


def test_a_pulse_row_is_labelled_and_phase_distinct(html):
    row = _fn(html, "function boardRow(r, hrs){")
    assert "PULSE_LATEST[r.market_slug]" in row
    assert "r.is_live" in row, "PULSE decorates IN-PLAY rows only"
    assert "pubadge" in row and ">PULSE</span>" in row
    assert "pulserow" in row, "phase must be visually distinct from ANCHOR rows"


def test_a_pulse_row_can_never_become_an_order(html):
    """PULSE is shadow structurally; its board presence is display only.

    Comments are stripped before scanning: the first version of this test
    tripped on a comment that NAMED the forbidden functions while promising
    their absence — the word-ban-on-prose mistake, third instance, one day
    after findings.md recorded it. Code is what can call a function; prose
    is not."""
    import re

    row = _fn(html, "function boardRow(r, hrs){")
    code = re.sub(r"/\*.*?\*/", "", row, flags=re.S)
    code = re.sub(r"^\s*//.*$", "", code, flags=re.M)
    for forbidden in ("sendCell", "openTicket", "PICKS[", "sendbtn"):
        assert forbidden not in code, f"{forbidden} reachable from a PULSE row"


def test_the_two_edges_are_never_conflated(html):
    """The rendered edge is PULSE FV against the CURRENT touch, gross. PULSE's
    own edge_net was net of fees at ITS limit at decision time. Different
    quantities; the tooltip names both rather than letting one wear the
    other's number."""
    row = _fn(html, "function boardRow(r, hrs){")
    assert "gross" in row and "edge_net" in row
    assert "positionView({...r, model: pu.fair_value})" in row, (
        "one derivation on the page: the ANCHOR rows' own positionView")


def test_the_action_chip_carries_action_side_price_and_age(html):
    row = _fn(html, "function boardRow(r, hrs){")
    assert "puchip" in row
    for piece in ("pu.action.toUpperCase()", "pu.side", "num(pu.limit_price)",
                  "agef(pu.age_seconds)"):
        assert piece in row


def test_estimates_refresh_without_refetching_the_board(html):
    fn = _fn(html, "async function loadPulseLatest(league){")
    assert "stale(league)" in fn, "the league guard covers this loader too"
    assert "renderBoard(LAST_BOARD" in fn, "re-render from cache, not refetch"
    assert "setInterval(() => loadPulseLatest(LEAGUE), 10000)" in html
