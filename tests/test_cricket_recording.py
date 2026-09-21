"""Cricket and table tennis: the venue facts this recording depends on.

    pytest --noconftest tests/test_cricket_recording.py

No database and no network. The event fixture below is a verbatim trim of a
real 2026-09-13 cplcr payload, so the shape is the venue's, not mine.
"""
from __future__ import annotations

import json

import pytest

from core.fees import POLYMARKET_TAKER as FEE  # the venue's coefficient; these read 0.06 until 2026-09-21

from cfb.run_paper_book import STRATEGIES, bet_pnl, venue_patterns
from core.leagues import LEAGUES
from core.polymarket.schemas import Event
from core.settlements import LABELS, label, load, save

# a real cplcr market, trimmed: one market, two sides, ordering on the side's team
EVENT = {
    "slug": "cplcr-bra-gaw-2026-09-13",
    "markets": [{
        "slug": "aec-cplcr-bra-gaw-2026-09-13",
        "sportsMarketType": "cricket_match_winner",
        "bestBid": None, "bestAsk": None,
        "bestBidQuote": {"value": "0.4000", "currency": "USD"},
        "bestAskQuote": {"value": "0.4100", "currency": "USD"},
        "marketSides": [
            {"long": True, "price": "0.4000", "quote": {"value": "0.4100"},
             "team": {"name": "Barbados Royals", "ordering": "home"}},
            {"long": False, "price": "0.4100", "quote": {"value": "0.6"},
             "team": {"name": "Guyana Amazon Warriors", "ordering": "away"}},
        ],
    }],
    "teams": [{"name": "Barbados Royals", "isHome": None},
              {"name": "Guyana Amazon Warriors", "isHome": None}],
}


# ------------------------------------------------------------------- parsing
def test_the_existing_schema_parses_a_cricket_event_unchanged():
    e = Event.model_validate(EVENT)
    m = e.markets[0]
    assert m.sports_market_type == "cricket_match_winner"
    assert m.slug == "aec-" + EVENT["slug"]
    assert m.line is None


def test_prices_come_from_bestBidQuote_because_bestBid_is_always_null():
    """Measured across the whole 2026-09-13 sweep: `bestBid` was null on every
    market in every league — ~31,000 of them. `bestBidQuote` is the field."""
    m = Event.model_validate(EVENT).markets[0]
    assert EVENT["markets"][0]["bestBid"] is None
    assert float(m.best_bid) == 0.40 and float(m.best_ask) == 0.41


def test_yes_is_the_home_team_here_not_the_away_team():
    """The opposite of football and MLB. nfl/cfb/mlb carry (long=True,
    ordering='away'); cricket, table tennis, tennis, soccer, esports, ufc and
    darts all carry (long=True, ordering='home'). The three US leagues are the
    exception, so anything that hardcoded 'YES is away' is wrong here."""
    sides = Event.model_validate(EVENT).markets[0].market_sides
    yes = next(s for s in sides if s.long)
    assert (yes.model_extra or {})["team"]["ordering"] == "home"
    assert yes.model_extra["team"]["name"] == "Barbados Royals"   # first team of the slug


def test_the_team_ordering_survives_into_the_raw_json_we_persist():
    """No migration tonight: the recorder stores the raw market dict verbatim
    into `market_snapshots.raw`, and the ordering is inside it."""
    raw = EVENT["markets"][0]
    assert raw["marketSides"][0]["team"]["ordering"] == "home"
    assert json.loads(json.dumps(raw))["marketSides"][0]["team"]["ordering"] == "home"


def test_the_event_level_teams_do_not_carry_the_side():
    """`isHome` is null on these, which is why the ordering is read off the
    market side rather than the event's team list."""
    assert all(t["isHome"] is None for t in EVENT["teams"])


# ------------------------------------------------------------------- leagues
@pytest.mark.parametrize("lg, want", [
    ("cricket", ("cplcr", "t20icr", "t20iwcr", "odicr", "county")),
    ("tabletennis", ("setkameua", "setkamemd", "setkamecz", "setkawoua")),
])
def test_a_league_fans_out_to_its_venue_competitions(lg, want):
    assert LEAGUES[lg].venue_leagues == want


@pytest.mark.parametrize("lg", ["wnba", "nfl", "cfb", "mlb"])
def test_an_ordinary_league_is_its_own_single_venue_slug(lg):
    assert LEAGUES[lg].venue_leagues == (lg,)


def test_the_book_matches_every_competition_not_the_league_word():
    """`%-cricket-%` matches nothing at all on this venue — an empty table that
    reads as a quiet night rather than a wrong pattern."""
    assert venue_patterns("cricket") == tuple(
        f"%-{v}-%" for v in LEAGUES["cricket"].venue_leagues)
    assert venue_patterns("wnba") == ("%-wnba-%",)
    assert venue_patterns("not-a-league") == ("%-not-a-league-%",)


# --------------------------------------------------------------- settlements
@pytest.mark.parametrize("v, want", [
    (0, 0), (1, 1), (0.5, 0.5), ("0", 0), ("1", 1), ("0.5", 0.5), (0.0, 0), (1.0, 1)])
def test_a_draw_settles_at_a_half_and_that_is_a_real_settlement(v, want):
    """First-class cricket can be drawn. Every consumer that wrote
    `v in (0, 1)` would have discarded these as unsettled — silently, and
    forever, since an unsettled market is re-asked but never stored."""
    assert label(v) == want


@pytest.mark.parametrize("v", [None, "", "pending", 2, -1, 0.4, 0.51, [1], {}])
def test_anything_else_is_not_a_settlement(v):
    assert label(v) is None


@pytest.mark.parametrize("v", [True, False])
def test_a_bool_is_refused_even_though_python_says_it_equals_one(v):
    """`True == 1` in Python; a client returning a boolean has told us
    something other than a settlement of 1."""
    assert label(v) is None


def test_a_half_survives_the_round_trip_to_disk(tmp_path):
    p = tmp_path / "s.json"
    save({"draw": 0.5, "home": 1, "away": 0, "pending": None}, p)
    back = load(p)
    assert back == {"draw": 0.5, "home": 1, "away": 0}
    assert isinstance(back["home"], int) and back["draw"] == 0.5


def test_LABELS_names_exactly_what_label_accepts():
    assert sorted(LABELS) == [0, 0.5, 1]
    assert all(label(v) == v for v in LABELS)


# ------------------------------------------------------------------- the book
def test_a_half_settlement_pays_half_the_ticket_and_still_charges_the_fee():
    """bet_pnl handles y=0.5 arithmetically; this pins what that means."""
    yes = bet_pnl("yes", 0.5, 0.49, 0.50, FEE)
    assert yes == pytest.approx(0.5 - 0.50 - FEE * 0.50 * 0.50)
    no = bet_pnl("no", 0.5, 0.49, 0.50, FEE)
    assert no == pytest.approx((1 - 0.5) - (1 - 0.49) - FEE * 0.49 * 0.51)
    assert yes < 0 and no < 0, "a draw loses the spread and the fee on both sides"


def test_a_draw_is_worse_than_a_win_and_better_than_a_loss():
    args = (0.49, 0.50)
    assert bet_pnl("yes", 0, *args, FEE) < bet_pnl("yes", 0.5, *args, FEE) < bet_pnl("yes", 1, *args, FEE)


@pytest.mark.parametrize("name", [
    "cricket_home_yes_all", "cricket_away_no_all", "cricket_home_fav_yes_60",
    "cricket_home_dog_yes_40", "tt_home_fav_yes_60", "tt_home_dog_yes_40"])
def test_the_six_strategies_are_registered_before_any_tape(name):
    st = STRATEGIES[name]
    assert st["league"] in ("cricket", "tabletennis")
    assert st["types"] == ("match_winner",)
    assert st["side"] in ("yes", "no")


def test_the_all_market_pair_are_mirrors_of_each_other():
    a, b = STRATEGIES["cricket_home_yes_all"], STRATEGIES["cricket_away_no_all"]
    assert a["side"] != b["side"] and a["league"] == b["league"]
    assert a["rule"]({}) is b["rule"]({}) is True


@pytest.mark.parametrize("m, fav, dog", [(0.60, True, False), (0.40, False, True),
                                         (0.50, False, False), (0.99, True, False)])
def test_the_fav_and_dog_cuts_are_inclusive_and_do_not_overlap(m, fav, dog):
    r = {"bid": m - 0.005, "ask": m + 0.005}
    assert STRATEGIES["cricket_home_fav_yes_60"]["rule"](r) is fav
    assert STRATEGIES["cricket_home_dog_yes_40"]["rule"](r) is dog


def test_the_market_type_suffix_matches_both_sports():
    """The book matches with `mtype.endswith(t)`, and the venue's two types are
    cricket_match_winner and table_tennis_match_winner."""
    for t in ("cricket_match_winner", "table_tennis_match_winner"):
        assert t.endswith(STRATEGIES["cricket_home_yes_all"]["types"][0])
