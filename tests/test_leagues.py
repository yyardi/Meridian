"""League is a parameter, not a string repeated in three page headers.

The dashboard said "MERIDIAN · WNBA" in every header while `core/config.py`
carried a `MERIDIAN_LEAGUE` env var nothing on the page read. This pins the
properties that make a second league a table entry rather than a search and
replace.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core import leagues
from core.api import app

REPO = Path(leagues.__file__).resolve().parent.parent


@pytest.fixture
def client():
    return TestClient(app)


def test_an_unknown_league_raises_rather_than_guessing():
    """The `UnknownTeamError` pattern: an explicit table fails loudly where a
    derivation fails silently, and a silently unknown league renders an empty
    board that looks like a quiet evening."""
    with pytest.raises(leagues.UnknownLeagueError):
        leagues.get_league("mlb")


def test_slug_lookup_covers_event_and_market_shapes():
    assert leagues.league_of_slug("wnba-ny-chi-2026-08-18").slug == "wnba"
    assert leagues.league_of_slug("tsc-wnba-ny-chi-2026-08-18-191pt5").slug == "wnba"
    assert leagues.league_of_slug("nba-bos-lal-2026-10-21").slug == "nba"
    assert leagues.league_of_slug("mlb-nyy-bos-2026-05-01") is None
    assert leagues.league_of_slug(None) is None


def test_a_bad_env_default_does_not_take_the_board_down(monkeypatch):
    monkeypatch.setattr(leagues, "DEFAULT_LEAGUE", "kabaddi")
    assert leagues.default_league().slug == "wnba"


def test_the_api_rejects_an_unknown_league(client):
    assert client.get("/api/games?league=mlb").status_code == 400
    assert client.get("/api/board?league=mlb").status_code == 400
    assert client.get("/api/picks?league=mlb").status_code == 400


def test_every_league_endpoint_carries_the_tab_context(client):
    """Each league-scoped endpoint reports which league answered. Without it
    the page cannot tell "no games in the NBA" from "the NBA tab did nothing"."""
    for url in ("/api/board", "/api/picks", "/api/events", "/api/games"):
        body = client.get(f"{url}?league=nba").json()
        assert body["league"] == "nba", url


def test_an_empty_league_explains_itself(client):
    """An empty board and a broken board look identical on screen, and only
    one of them is fine. Every unrecorded league carries its own reason."""
    body = client.get("/api/games?league=nba").json()
    assert body["recorded"] is False
    assert body["games"] == []
    assert "October" in body["empty_state"]

    for lg in leagues.LEAGUES.values():
        assert lg.empty_state.strip(), f"{lg.slug} has no empty state"


def test_picks_counts_slugs_it_cannot_place(client):
    """A row dropped for having no recognisable league is reported, not
    swallowed — a rising count here means the venue changed its slug format."""
    body = client.get("/api/picks?league=wnba").json()
    if body.get("predicted_at") is not None:
        assert "unknown_league" in body["filtered"]


def test_no_page_hardcodes_the_league_in_its_header():
    """The literal this whole change exists to delete."""
    for page in (REPO / "static").glob("*.html"):
        head = page.read_text().split("</header>")[0]
        assert "MERIDIAN<span>·</span>WNBA" not in head, page.name
        assert 'id="lgtabs"' in head, f"{page.name} has no league tabs"


def test_no_page_strips_a_hardcoded_league_slug():
    """`replace("wnba-","")` silently stopped shortening labels the moment a
    second league appeared, leaving raw slugs on screen with no error."""
    for page in (REPO / "static").glob("*.html"):
        body = page.read_text()
        assert '"wnba-"' not in body, page.name
        assert "-wnba-/" not in body, page.name
