"""The board itself is live: cadence, source truth, and the hint that lied.

Verified mechanism (production, 2026-08-21 00:24Z, read-only): the live game
had 2,691 snapshot rows in the trailing 60s with is_live=t — the data layer
was seconds-fresh the whole time. "nothing live — showing next to tip"
printed because loadPicks ran once at page load and never again; the table
was a photograph. Both recorders write ONE table and the newest row already
wins, so the fix is cadence, not a data merge.
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


def test_the_board_refetches_on_a_heartbeat(html):
    """10s while anything is live; every 6th beat (60s) when idle — a quiet
    minute of pregame staleness is honest, a live minute is not."""
    fn = _fn(html, "async function boardHeartbeat(){")
    assert "loadPicks(LEAGUE)" in fn, "the full board+picks refetch is the fix"
    assert "anyLive" in fn and "IDLE_BEATS >= 6" in fn
    assert "BOARD_INFLIGHT" in fn, "slow fetches must not stack"
    assert "setInterval(boardHeartbeat, 10000)" in html
    assert "setInterval(() => loadPulseLatest(LEAGUE), 10000)" not in html, (
        "one heartbeat, not two competing intervals")


def test_the_hint_shows_cadence_and_a_timestamp(html):
    """The operator's complaint was epistemic — they could not tell the page
    was alive. The hint now says which cadence is running and when the render
    happened, so a frozen page is visibly frozen."""
    board = _fn(html, "function renderBoard(b, picksBySlug){")
    assert "refreshing 10s" in board and "refreshing 60s" in board
    assert "as of" in board


def test_every_age_cell_names_its_writer(html):
    """8s and 12m are different KINDS of fresh — pregame sweeps 15m, live
    tiers run 200ms-10s. Never silently the same."""
    assert html.count("writer") >= 3, "board row, pulse row, and pick row ages"
    assert "pregame sweeps every 15m" in html


def test_the_board_payload_carries_the_source(client):
    """`source` = book_tier or 'pregame' on every row. Field-presence only —
    a live-tier row needs a live game, which the fixture cannot conjure."""
    d = client.get("/api/board?league=wnba").json()
    for r in d.get("markets", []):
        assert "source" in r
        assert r["source"] is not None


def test_the_nothing_live_hint_is_computed_at_render_not_at_load(html):
    """The bug in one line: the hint text must live inside a function the
    heartbeat re-runs, not in one-shot boot code."""
    board = _fn(html, "function renderBoard(b, picksBySlug){")
    assert "nothing live — showing next to tip" in board, (
        "the fallback note is part of the re-rendered board, so it "
        "re-evaluates every refetch")
