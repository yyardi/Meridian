"""The instructions page: the one document the operator obeys under time
pressure.

    pytest --noconftest tests/test_instructions_page.py

Two failures this pins. The first is the one that happened: the page lived
in cfb/, only the temporary desk served it, that desk was killed, and
/instructions 404'd for a day -- on the dashboard an operator opens WITH a
live ticket in front of them.

The second is worse and has never happened: the page tells a person which
button to tap, and the venue frames a spread row from the side LAYING the
points while pricing the underdog's contract. If the page and `ui_wording`
ever disagree about that, the page wins (a person obeys the page, not the
function) and every ticket goes in backwards. So the rows and buttons on it
are not compared against remembered strings here -- they are recomputed
from the production function and required to match.
"""
from __future__ import annotations

import pathlib
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core import api as api_module          # noqa: E402
from core.ladder import instructions        # noqa: E402
from core.ladder.ui import ui_wording       # noqa: E402

#: The page's worked example, in the slug frame the scanner works in.
GAME = "nfl-det-buf-2026-09-14"
PAGE = instructions.HTML


@pytest.fixture
def client():
    return TestClient(api_module.app)


def test_the_route_answers_and_is_not_a_file_read(client):
    """It 404'd because it was served from a module the api image does not
    carry; a constant in core/ cannot go missing without the import failing
    at start-up, which is loud."""
    r = client.get("/instructions")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "ladder ticket" in r.text
    assert pathlib.Path(instructions.__file__).parts[-3:-1] == ("core", "ladder")


def test_the_buy_leg_row_and_button_come_out_of_the_production_function():
    """The easier line is the one you BUY, and on the screen that is the
    OTHER team's row with No tapped. Recomputed, not remembered."""
    row, button = ui_wording(GAME, 13.5, "BUY YES")
    assert (row, button) == ("BUF to win by over 13.5 points", "No")
    assert row in PAGE, f"the page must name the row {row!r} the operator taps"
    assert f"{row} -&gt; tap {button}" in PAGE or f'{row}" &rarr; tap <b>{button}</b>' in PAGE


def test_the_sell_leg_is_the_same_row_family_with_the_other_button():
    row, button = ui_wording(GAME, 10.5, "BUY NO")
    assert (row, button) == ("BUF to win by over 10.5 points", "Yes")
    assert row in PAGE and button in PAGE


def test_the_two_legs_never_carry_the_same_button():
    """If they did, the pair would be two bets on the same side of the same
    question and the no-lose argument in section 6 would be false."""
    _, buy = ui_wording(GAME, 13.5, "BUY YES")
    _, sell = ui_wording(GAME, 10.5, "BUY NO")
    assert buy != sell


def test_the_winner_market_is_refused_by_the_function_the_page_describes():
    """Section 5 says spread-vs-spread only; the function enforces it."""
    with pytest.raises(ValueError):
        ui_wording(GAME, 0.0, "BUY YES")
    assert "Never the winner market" in PAGE


def test_the_page_does_not_send_the_operator_to_the_desk_that_was_killed():
    """Its links are the routes on :8008, not the root of a dead app."""
    assert "href='/'" not in PAGE and 'href="/"' not in PAGE
    for route in ("/arb", "/log", "/pnl"):
        assert f"href='{route}'" in PAGE, route


def test_it_does_not_quote_a_budget_cap_that_no_longer_exists():
    """The executor's cap and cooldown were removed: the capital decision is
    the SEND click. A page promising a $5 ceiling would be describing a
    guard that is not there."""
    assert "$5 budget" not in PAGE
    assert "no budget cap" in PAGE.lower()


def test_it_says_plainly_that_nothing_has_been_placed():
    """Every dollar figure the operator sees anywhere in this system is
    what the tape OFFERED. The page that teaches them to read those figures
    is where that has to be said, not a footnote elsewhere."""
    assert "Nothing has been placed yet" in PAGE


def test_the_dashboard_links_to_both_pages_so_they_can_be_found():
    """A page nobody can reach is the same as a 404. /instructions was
    unreachable for a day, and /log shipped with no link at all: the
    operator was told it existed and had to type the path."""
    nav = pathlib.Path(__file__).resolve().parents[1] / "static" / "arb.html"
    html = nav.read_text(encoding="utf-8")
    for route in ('href="/log"', 'href="/instructions"', 'href="/pnl"'):
        assert route in html, route


def test_the_log_page_links_to_the_instructions():
    """The log is where an operator sees a crossing they did not take; the
    next question is how to take one."""
    from core.ladder import gamelog_page
    page = gamelog_page.render(None, {"games": []}, [], "/nonexistent")
    assert "/instructions" in page
