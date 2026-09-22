"""The stream recorder keeps game totals, per game, without the spread
scanner ever seeing them.

    pytest --noconftest tests/test_recorder_totals.py

On 2026-09-21 a discovery agent found the game-total ladder carrying the
spread ladder's defect in play, with market-maker size on both legs for
minutes, and no update-resolution tape existed to measure it on: the
recorder subscribed only winners and spreads, and any slug the spread
parser refused was filed under one unmapped name. Three things must hold:

  1. a totals slug is filed beside its own game's spreads;
  2. it carries line null there, and every spread scanner skips it,
     because a totals ladder runs the other way and feeding it to the
     spread scanner reports the correct board as broken;
  3. the scheduler still counts rungs off the ladder families only, so a
     game's 42 total rungs cannot pass it as a 30-rung spread ladder.
"""
from __future__ import annotations

import importlib
import inspect
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core.ladder import live, stream, stream_episodes  # noqa: E402

GAME = "nfl-phi-ten-2026-09-20"
TOTAL = f"tsc-{GAME}-total-21pt5"
TEAM_TOTAL = f"tsc-{GAME}-tt-phi-10pt5"
SPREAD = f"asc-{GAME}-neg-2pt5"
WINNER = f"aec-{GAME}"


def test_the_game_is_read_off_any_family_s_slug():
    for slug in (TOTAL, TEAM_TOTAL, SPREAD, WINNER):
        assert live.game_of_slug(slug) == GAME, slug
    assert live.game_of_slug("nonsense") is None
    assert live.game_of_slug("asc-cfb-portst-ore-2026-09-18-pos-58pt5") == "cfb-portst-ore-2026-09-18"


def test_a_totals_slug_has_a_game_but_no_line_for_the_spread_scanners():
    """`game_and_line` refusing it is what keeps the orientation trap shut."""
    assert live.game_and_line(TOTAL) is None
    assert live.game_and_line(TEAM_TOTAL) is None
    assert live.game_and_line(SPREAD) == (GAME, -2.5)
    assert live.game_and_line(WINNER) == (GAME, 0.0)
    assert stream_episodes.line_of(TOTAL) is None, "the episode scanner skips it too"
    assert live.line_of(TOTAL, WINNER) is None


def test_the_recorder_routes_by_game_and_records_the_line_as_null():
    row = stream.book_row({"marketSlug": TOTAL, "bids": [{"px": {"value": "0.4"}, "qty": "10"}],
                           "offers": [{"px": {"value": "0.42"}, "qty": "10"}]}, "2026-09-20T18:00:00Z")
    assert row is not None and row["slug"] == TOTAL and row["line"] is None
    src = inspect.getsource(stream.StreamConnection._record)
    assert 'game_of_slug(row["slug"]) or UNMAPPED_GAME' in src, \
        "route by the game alone; the unmapped file is for slugs with no game at all"


def test_the_recorder_subscribes_totals_and_the_scheduler_does_not_count_them():
    assert set(live.LADDER_MARKET_TYPES) < set(live.RECORDED_MARKET_TYPES)
    for fam in ("football_team_full_game_total", "basketball_team_full_game_total",
                "baseball_team_full_game_total"):
        assert fam in live.RECORDED_MARKET_TYPES and fam not in live.LADDER_MARKET_TYPES
    assert "RECORDED_MARKET_TYPES" in inspect.getsource(live.slate_slugs)
    gs = importlib.import_module("scripts.game_schedule")
    src = inspect.getsource(gs)
    assert "LADDER_MARKET_TYPES" in src and "RECORDED_MARKET_TYPES" not in src, \
        "the board's rung counts, and so the REST cap, stay spread-only"


def test_the_cricket_winner_is_recorded_and_is_not_a_ladder_family():
    """One market per match, no line: on the stream for the in-play read
    (docs/math/cricket-inplay-dip.md), never counted as a ladder rung."""
    assert live.MATCH_WINNER_TYPES == ("cricket_match_winner",)
    for fam in live.MATCH_WINNER_TYPES:
        assert fam in live.RECORDED_MARKET_TYPES and fam not in live.LADDER_MARKET_TYPES
    assert live.game_and_line("aec-t20icr-japan-india-2026-09-22") == ("t20icr-japan-india-2026-09-22", 0.0)
    assert "county" in live.EXCLUDED_LEAGUES and "county" not in live.CRICKET_STREAM_LEAGUES
