"""One landing page, and it is the picks page.

The bug this pins
-----------------
The dashboard opened on a live board: every rung of every ladder, with a
model price and an edge beside it. It was the wrong first screen. The
operator's first action every session was to click past it to `/picks`,
because the board answers "what is quoted" and the only question worth
opening the page for is "what do I send". Two documents rendered overlapping
views of the same data, which is how the send button and the numbers beside
it drift apart.

So the board's table is gone and `/` serves the picks page. What survives of
the board is the part the picks page never had: which games are on, the score
if one is running, and how long until the next tip.

These tests pin the merge itself — the routes, the columns that came across,
the ones that deliberately did not, and the honesty text that is not allowed
to be lost in a redesign.
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


def _block(html: str, start: str, end: str) -> str:
    """The text between two markers, for guards that span more than a function."""
    i = html.index(start)
    return html[i:html.index(end, i)]


def _fn(html: str, signature: str) -> str:
    """The body of exactly one function, found by matching its braces.

    The obvious version — slice from this function to the next known one —
    silently grows whenever somebody inserts a function between the two, and
    then a guard scoped to *this* function starts scanning *theirs*. Three
    branches are landing on this page in sequence (bankroll, league tabs, game
    tape); every one of them inserts. A brace match cannot be widened by a
    neighbour.
    """
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


# --------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------- #


def test_the_landing_page_is_the_picks_page(client):
    r = client.get("/")
    assert r.status_code == 200
    body = r.text
    # The three things the operator came for.
    assert "Tonight's pregame picks" in body
    assert ">SEND</button>" in body or "sendbtn" in body
    assert "BUY at" in body and "SELL at" in body


def test_the_old_picks_url_redirects_rather_than_serving_a_second_copy(client):
    """Two documents rendering the same picks is the drift this merge removes."""
    r = client.get("/picks", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/"


def test_the_redirect_lands_on_the_picks_page(client):
    r = client.get("/picks")
    assert r.status_code == 200
    assert "Tonight's pregame picks" in r.text


def test_there_is_only_one_page_file():
    """`static/picks.html` is gone. A leftover copy is a page nobody updates."""
    assert not Path("static/picks.html").exists()


def test_the_board_table_did_not_come_across(html):
    """The live board's own market table is what the merge deleted."""
    for gone in ("<th>Spr</th>", 'id="rows"', 'data-f="all"', "sparkline("):
        assert gone not in html, f"{gone} is live-board markup that should be gone"


# --------------------------------------------------------------------- #
# The picks table
# --------------------------------------------------------------------- #


def test_every_pick_row_carries_return_buy_at_sell_at_and_a_send_cell(html):
    picks = _fn(html, "function renderPicks(d){")
    for column in ("BUY at", "SELL at", "Return"):
        assert f">{column}</th>" in picks, f"the {column} column is missing"
    assert "sendCell(p)" in picks


def test_picks_are_grouped_by_game_with_a_tip_time(html):
    picks = _fn(html, "function renderPicks(d){")
    assert "games.find" in picks, "picks must be grouped by event, not listed flat"
    assert "tips in" in picks
    assert "hours_to_tipoff" in picks or "g.hrs" in picks


def test_the_picks_table_has_no_shadow_column(html):
    """The old board's REST/CROSS column deliberately did not come across.

    The confirm ticket computes rests-or-crosses live off the price actually
    in the box; a column showed the verdict for a limit price nobody was going
    to send. Two numbers for one decision, and the stale one was larger.
    """
    picks = _fn(html, "function renderPicks(d){")
    header = _block(picks, "<thead>", "</thead>")
    assert "shadow" not in header.lower(), "no shadow column header"
    # And no row cell reads the shadow order either — a column can be
    # reintroduced by rendering the field without renaming the header.
    assert "p.shadow" not in picks
    assert "would_rest" not in picks
    # The ticket keeps the live version of that label.
    assert "rests — may not fill" in html
    assert "crosses — fills now" in html


# --------------------------------------------------------------------- #
# Honesty infrastructure
# --------------------------------------------------------------------- #


def test_the_banner_disclaimers_survive_the_merge(html):
    """Ratified text. A redesign is not a reason to lose any of it."""
    assert "These are shadow picks, not advice." in html
    assert "CLV gate" in html
    assert "60-day shadow window" in html
    assert "disagreement over 15%" in html


def test_the_suspect_marker_still_marks_wide_disagreements(html):
    picks = _fn(html, "function renderPicks(d){")
    assert "p.suspect" in picks
    assert "usually model error, not free money" in picks


def test_the_display_only_captions_survive(html):
    """Neither formula-FV strip may lose its caption in a layout change."""
    assert html.count("Nothing here is orderable") >= 2
    assert "display only, nothing here is orderable" in html


# --------------------------------------------------------------------- #
# Game context strip — the surviving half of the live board
# --------------------------------------------------------------------- #


def test_the_page_has_a_game_context_strip(html):
    assert 'id="strip"' in html
    strip = _fn(html, "function renderStrip(){")
    assert "is_live" in strip
    assert "tips in" in strip
    assert "ctx.score" in strip, "a running game must show its score"


def test_the_strip_is_display_only(html):
    """It frames the picks. It is not a market table and cannot become one."""
    strip = _fn(html, "function renderStrip(){")
    for forbidden in ("openTicket", "sendCell", "PICKS[", "confirmBtn", "onclick"):
        assert forbidden not in strip, f"{forbidden} must not appear in the strip"


def test_the_strip_says_it_is_current_state(html):
    """It sits next to a retrospective game tape (PR #7). Saying which is which
    is what makes the pair legible rather than merely non-contradictory — and
    the two must never be merged into one component that can render both."""
    assert '"striplbl"' in html or "striplbl" in html
    strip_label = _block(html, 'class="striplbl"', "</div>")
    assert ">now" in strip_label.lower() or "now<" in strip_label.lower()


def test_the_strip_reports_per_game_staleness(html):
    """A 15-minute-old pregame quote must not look as fresh as a 200ms one."""
    strip = _fn(html, "function renderStrip(){")
    assert "age_seconds" in strip
    assert "agef(" in strip


def test_recorder_health_came_across_from_the_board(html):
    """A pick priced off a dead writer still renders; only this says so."""
    for stat in ('id="s-health"', 'id="s-pregame"', 'id="s-live"'):
        assert stat in html


# --------------------------------------------------------------------- #
# League switching
# --------------------------------------------------------------------- #


def test_every_league_loader_drops_a_stale_response(html):
    """A response for a league you switched away from must not be rendered.

    Measured on the live page: `/api/picks?league=wnba` took over three
    seconds while NBA answered immediately, so switching WNBA -> NBA let the
    late WNBA response overwrite the NBA view — sixteen WNBA picks under an
    NBA tab, each with a live SEND button. Everywhere else on this page a
    stale table is a nuisance; on the picks table it is an order for a game
    the operator is not looking at.
    """
    assert "function stale(league){ return league !== LEAGUE; }" in html
    for loader in ("function loadPicks(league){",
                   "function loadGames(league){",
                   "async function loadEvents(league){"):
        body = _fn(html, loader)
        assert "stale(league)" in body, f"{loader} renders stale responses"


def test_the_league_has_one_source_of_truth(html):
    """A copy of the current league is one more thing that can disagree with
    the tab the operator is looking at."""
    assert "LEAGUE_NOW" not in html
    assert "setInterval(() => loadEvents(LEAGUE), 30000)" in html


def test_the_strip_does_not_share_a_class_with_the_game_tape(html):
    """The tape binds clicks with a document-wide querySelectorAll('.gcard').

    Sharing the name would have hung openGame() off every strip card, making
    a display-only surface clickable — the one thing it must not be — and the
    CSS (:hover, .on) would have collided too.
    """
    strip = _fn(html, "function renderStrip(){")
    assert "gcard" not in strip, "the strip must not use the tape's class"
    assert "scard" in strip





def test_the_send_flow_still_needs_the_token_header(html):
    """Token gating is not part of this change and must read exactly as before."""
    assert '"X-Meridian-Order-Token": $("#tok").value.trim()' in html
    assert 'sessionStorage.setItem("meridian_order_token"' in html
    # sessionStorage, not localStorage: the token dies with the tab rather
    # than sitting on disk between sessions.
    #
    # Scoped to the token, not to localStorage page-wide. The broad version
    # was wrong in a way that would only have shown up later: a durable UI
    # preference (a league tab, a column choice) is a perfectly good reason to
    # touch localStorage, and a test that bans the API outright fails on the
    # first one and teaches whoever hits it that the rule is noise. The rule
    # is about the token.
    # Every access to the token goes through sessionStorage — checked by
    # looking at what precedes each mention rather than by banning the API.
    import re

    for m in re.finditer(r'(\w+Storage)\.\w+\(\s*"meridian_order_token"', html):
        assert m.group(1) == "sessionStorage", (
            f"the order token must not touch {m.group(1)}")
    assert 'sessionStorage.getItem("meridian_order_token")' in html


def test_the_row_button_only_opens_the_ticket(html):
    """Two clicks, two different elements. The row button sends nothing."""
    send = _fn(html, "function sendCell(p){")
    assert "fetch(" not in send
    assert "openTicket" in _fn(html, "function renderPicks(d){")


def test_only_human_confirm_is_ever_posted(html):
    """The page has one mode and cannot express another."""
    body = _fn(html, "async function sendOrder(){")
    assert 'mode: "HUMAN_CONFIRM"' in body
    assert "AUTONOMOUS" not in body
