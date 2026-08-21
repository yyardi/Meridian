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
    # The table markup moved from renderBoard into gameTable when live games
    # got the trading view (live-view restructure) — same columns, new home.
    board = _fn(html, "function gameTable(g, hrs, picksBySlug){")
    for column in ("BUY at", "SELL at", "Return", "Line", "Model FV", "Edge"):
        assert f">{column}</th>" in board, f"the {column} column is missing"
    assert "sendCell(p)" in _fn(html, "function pickRow(p, br){")


def test_picks_are_grouped_by_game_with_a_tip_time(html):
    board = _fn(html, "function renderBoard(b, picksBySlug){")
    assert "games.find" in board, "rows must be grouped by event, not listed flat"
    assert "tips in" in board


def test_the_picks_table_has_no_shadow_column(html):
    """The old board's REST/CROSS column deliberately did not come across.

    The confirm ticket computes rests-or-crosses live off the price actually
    in the box; a column showed the verdict for a limit price nobody was going
    to send. Two numbers for one decision, and the stale one was larger.
    """
    picks = _fn(html, "function gameTable(g, hrs, picksBySlug){")
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


def test_the_shadow_picks_banner_is_gone_and_the_row_honesty_is_not(html):
    """The banner was removed at the operator's request (2026-08-17): they
    read this page all day and the caveat had become wallpaper. What must NOT
    go with it is the honesty that is load-bearing per row — the ? marker on
    wide disagreements — and the model-quality story on /analytics, which is
    where trust decisions belong.
    """
    assert "These are shadow picks, not advice." not in html
    assert "disagreement over 15%" in html          # the ? marker's tooltip
    analytics = Path("static/analytics.html").read_text()
    assert "never been backtested" in analytics     # the scope banner survives


def test_the_suspect_marker_still_marks_wide_disagreements(html):
    picks = _fn(html, "function pickRow(p, br){")
    assert "p.suspect" in picks
    assert "usually model error, not free money" in picks


def test_the_display_only_captions_survive(html):
    """Shorter now, but the claim itself may not be lost: both formula-FV
    strips and the EV guard must still say nothing on them is orderable."""
    assert html.count("nothing here is orderable") >= 3
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
    """The NOW button carries the label now. It sits next to a retrospective
    game tape; saying which is which is what keeps the pair legible."""
    assert "striplbl" in html
    btn = _block(html, 'class="striplbl', "</button>")
    assert ">now" in btn.lower()
    assert "Current state" in btn


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
# The board shows MARKETS, not only picks
# --------------------------------------------------------------------- #


def test_the_table_renders_every_market_not_only_actionable_ones(html):
    """The regression this fixes.

    The picks-only table printed "No tradeable pregame markets right now" on a
    night with 95 quoted markets on the board — true, and useless. The operator
    reads this page to see lines; a page that hides every line whenever nothing
    is orderable answers a question nobody asked.
    """
    load = _fn(html, "async function loadPicks(league){")
    assert "/api/board?league=" in load, "the table must be driven by the board"
    assert "/api/picks?league=" in load, "picks supply the actionable subset"
    board = _fn(html, "function renderBoard(b, picksBySlug){")
    assert "b.markets" in board
    assert "picksBySlug[r.market_slug]" in board, "picks merge onto board rows"


def test_a_non_actionable_row_still_shows_its_prices_and_says_why(html):
    row = _fn(html, "function boardRow(r, hrs){")
    for cell in ("r.line", "v.bid", "v.ask", "r.spread", "v.model", "v.edge"):
        assert cell in row, f"{cell} missing from a non-actionable row"
    assert "whynot" in row, "the reason must sit where the SEND button would be"
    assert "sendCell" not in row, "a non-actionable row must never be orderable"
    assert "openTicket" not in row


def test_the_reasons_cover_every_filter_the_server_applies(html):
    """Each branch mirrors one /api/picks filter. Verified against the live
    board: these reproduce `filtered` exactly (77 far-dated, 1 moneyline,
    17 unanchored, 0 wide)."""
    why = _fn(html, "function whyNotActionable(r, hrs){")
    for reason in ("in-play", "final", "no quotes", "beyond", "spread",
                   "moneyline", "no fresh line"):
        assert reason in why, f"no branch explains {reason!r}"


def test_a_pick_row_never_recomputes_the_servers_numbers(html):
    """Two renderings of one tradable decision is the drift this page exists
    to remove. Only rows with no order path get a client-side derivation."""
    pick = _fn(html, "function pickRow(p, br){")
    assert "positionView" not in pick, "a pick row must use the server's numbers"
    for field in ("p.ticket.buy_at", "p.ticket.sell_at", "p.ticket.return_pct"):
        assert field in pick


def test_the_row_says_when_the_book_has_moved_off_the_priced_at(html):
    """/api/picks prices are frozen at `predicted_at`; /api/board is live, and
    predictions run every 20 minutes. Measured here: a 174.5 total priced
    against ask 0.44 while the book had moved to 0.48. Two instants in one
    table without saying so is how every number reads right and the row reads
    wrong."""
    moved = _fn(html, "function movedChip(p, br){")
    assert "p.ask" in moved and "live.ask" in moved
    assert "livePrice" in moved
    live = _fn(html, "function livePrice(br, p){")
    assert 'p.side === "NO" || p.side === "UNDER"' in live, (
        "the flip must use the side the SERVER chose, not a re-derived one")


def test_freshness_is_per_row(html):
    """200ms live and 15-minute pregame writers land in the same table."""
    assert ">Age</th>" in html
    assert "age_seconds" in _fn(html, "function ageCls(br){")


# --------------------------------------------------------------------- #
# View modes — NOW is the default, the wall of tables is opt-in
# --------------------------------------------------------------------- #


def test_now_is_the_default_view(html):
    """The operator's complaint: every future game's ladder stacked under the
    strip. The page opens on what is live; everything else is one click."""
    assert 'let VIEW = {mode: "now"};' in html
    vg = _fn(html, "function viewGames(games){")
    assert "is_live" in vg, "NOW must be decided by live markets"
    assert "upcoming" in vg, "with nothing live, NOW falls through to next tip"


def test_a_strip_card_filters_to_one_game_and_can_open_a_tab(html):
    strip = _fn(html, "function renderStrip(){")
    assert 'data-ev="${e.event_slug}"' in strip
    assert 'setView' in strip
    assert 'class="newtab"' in strip and 'target="_blank"' in strip
    assert '/?game=' in strip


def test_the_game_url_param_selects_the_game_and_its_league(html):
    assert 'new URLSearchParams(location.search).get("game")' in html
    assert 'VIEW = {mode: "game", ev: QGAME}' in html
    # the link's league must beat the stored tab, or a shared NBA link opens
    # an empty WNBA page — but it must not persist
    assert "LEAGUE = QGAME.split" in html


def test_the_strip_still_cannot_reach_the_order_path(html):
    """Cards navigate now (operator request) — that is a change of role, not
    of privilege. Nothing on the strip may open a ticket."""
    strip = _fn(html, "function renderStrip(){")
    for forbidden in ("openTicket", "sendCell", "PICKS[", "confirmBtn"):
        assert forbidden not in strip


# --------------------------------------------------------------------- #
# Declutter: what left the page and what it must not take with it
# --------------------------------------------------------------------- #


def test_the_header_pill_is_gone_but_the_autonomous_tripwire_is_not(html):
    """The pill announced HUMAN_CONFIRM on every load; its one load-bearing
    job — the autonomous counter that must read 0 forever — survives as a
    banner that only exists when it fires."""
    assert "modepill" not in html
    assert 'id="autoalert"' in html
    status = _fn(html, "async function loadStatus(){")
    assert "orders_autonomous" in status
    assert "autoalert" in status


def test_real_orders_live_inside_the_game_they_belong_to(html):
    """The page-level panel is gone; the game tape answers "what did I do in
    THIS game". Slug containment does the join, and the cancel flow keeps its
    two-click arming."""
    assert 'id="orders"' not in html
    fn = _fn(html, "async function loadGameOrders(ev){")
    assert '.includes(ev)' in fn
    assert "cxbtn" in fn and "SURE?" in fn
    assert "X-Meridian-Order-Token" in fn
    # wired from the tape, and refreshed after a send
    assert "loadGameOrders(d.event_slug)" in html
    send = _fn(html, "async function sendOrder(){")
    assert "loadGameOrders(OPEN_GAME)" in send


def test_a_failed_exit_is_still_the_loudest_thing_in_the_orders_table(html):
    fn = _fn(html, "async function loadGameOrders(ev){")
    assert "FAILED — position is NOT protected" in fn


# --------------------------------------------------------------------- #
# Bankroll is live
# --------------------------------------------------------------------- #


def test_the_bankroll_is_polled_from_the_venue_not_the_stored_reading(html):
    """The operator was in a trade and the page showed the scheduler's
    20-minute-old snapshot. refresh=true is the on-demand half of the poller —
    read-only by construction — and it exists for exactly this moment."""
    assert '/api/bankroll?refresh=true' in html
    assert "setInterval(refreshBankroll, 60000)" in html
    fn = _fn(html, "async function refreshBankroll(){")
    assert "renderBankroll" in fn


def test_one_writer_for_both_bankroll_displays(html):
    """loadStatus writing the header while the poll wrote the note made the
    number flap between a fresh read and a 20-minute-old one."""
    fn = _fn(html, "function renderBankroll(b){")
    assert "s-bankroll" in fn, "renderBankroll owns the header stat"
    status = _fn(html, "async function loadStatus(){")
    assert "s-bankroll" not in status, "loadStatus must not also write it"


def test_an_unknown_bankroll_is_said_not_guessed(html):
    fn = _fn(html, "function renderBankroll(b){")
    assert "Bankroll unknown" in fn


# --------------------------------------------------------------------- #
# The game chart is an instrument now
# --------------------------------------------------------------------- #


def test_the_chart_has_a_real_time_axis_and_labelled_scales(html):
    chart = _fn(html, "function gamePath(d){")
    assert "new Date(p.at).getTime()" in chart, "x must be time, not index"
    assert "clock(t)" in chart, "time ticks labelled in wall time"
    for scale in ('text-anchor="end"', "#ffb020", "#4c8dff"):
        assert scale in chart, "both y scales must be labelled"


def test_decisions_are_dots_clustered_when_they_overlap(html):
    """The model trades pregame, so hundreds of decisions land at the start.
    One dot per overlap cluster, sized by count; the hover lists a few rounds
    and says how many more."""
    chart = _fn(html, "function gamePath(d){")
    assert "clusters" in chart
    assert "Math.abs(c.x - m.x) < 10" in chart
    wire = _fn(html, "function wireGamePath(){")
    assert "more rounds" in wire
    assert "click to jump" in wire


def test_the_chart_hover_reads_score_margin_and_mid(html):
    wire = _fn(html, "function wireGamePath(){")
    for field in ("score", "margin", "mid"):
        assert field in wire


def test_chart_clicks_jump_to_the_round_table(html):
    wire = _fn(html, "function wireGamePath(){")
    assert 'getElementById("round-"' in wire
    assert 'id="round-' in html, "rounds must carry the anchors the chart jumps to"


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
    assert "openTicket" in _fn(html, "function renderBoard(b, picksBySlug){")


def test_only_human_confirm_is_ever_posted(html):
    """The page has one mode and cannot express another."""
    body = _fn(html, "async function sendOrder(){")
    assert 'mode: "HUMAN_CONFIRM"' in body
    assert "AUTONOMOUS" not in body
