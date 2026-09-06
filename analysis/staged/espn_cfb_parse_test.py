"""The CFB recorder's parse had NO test, and its failure mode is silent.

STAGED, NOT INSTALLED. This branch does not carry
`core/feeds/espn_cfb_recorder.py` (it lives on main), so the file is parked
here without a `test_` prefix to keep it out of collection. To install:

    cp analysis/staged/espn_cfb_parse_test.py       tests/test_espn_cfb_recorder.py
    cp analysis/staged/espn_cfb_summary_slim.json   tests/fixtures/

on a branch containing the recorder, and fix FIXTURE to `fixtures/`.
Verified there on 2026-09-06: 6 passed, and mutation-checked -- moving the
plays to `summary.plays` gives 0 parsed, and removing `yardsToEndzone` nulls
17/17. Both kill the suite, so these assertions can fail.

`docker-compose.cfb-live.yml` states the hazard in its own header: for football
``summary.plays`` is EMPTY -- the plays live under ``drives`` -- so a
basketball-shaped parser here "writes nothing while every heartbeat stays
green." Nothing asserted that our parser reads the right branch, and nothing
asserted that the four situational features survive the parse.

Those four -- down, distance, yards-to-goal, possession -- are the core of
every public football win-probability model. If they silently stop parsing the
model degrades to clock/score/margin and no alarm fires, because state rows
keep landing from the same poll.

Fixture is a real ESPN college-football summary, trimmed: 3 drives, 17 plays.
``plays`` is deliberately left EMPTY in it, exactly as ESPN serves football, so
a regression to the basketball branch fails here instead of in production.

Play and drive ``id`` values are SYNTHETIC (``d1p1`` …). ESPN's real ones are
twelve-digit strings and the staged-secret detector reads a bare twelve-digit
run as an AWS account id — correctly, since it cannot know the difference. The
football payload is untouched: every down, distance, yardsToEndzone, team and
clock value is exactly as served. Only opaque identifiers were shortened, and
nothing asserts on their format.
"""
from __future__ import annotations

import json
import pathlib

from core.feeds.espn_cfb_recorder import (
    parse_game_state,
    parse_plays,
    parse_win_probability,
)

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "espn_cfb_summary_slim.json"
GAME = "401867866"
SITUATIONAL = ("down", "distance", "yards_to_goal", "pos_team")


def _payload() -> dict:
    return json.loads(FIXTURE.read_text())


def _plays() -> list[dict]:
    p = _payload()
    st = parse_game_state(p, GAME)
    return parse_plays(p, GAME, st.get("home"), st.get("away"))


def test_football_plays_come_from_drives_not_summary_plays():
    """The documented silent failure: reading `summary.plays` yields nothing."""
    payload = _payload()
    assert payload["plays"] == [], "fixture must keep football's empty plays[]"
    assert len(_plays()) == 17, "plays must be read from drives[].plays"


def test_every_play_carries_the_four_situational_features():
    """Asserted PER PLAY, not in aggregate: a totals check passes while a
    subset silently parses to None, which is the shape this guards."""
    plays = _plays()
    assert plays, "no plays parsed at all"
    for p in plays:
        for field in SITUATIONAL:
            assert p[field] is not None, f"{field} is None on play {p['play_id']}"


def test_situational_values_are_in_range_not_merely_present():
    """A present-but-wrong parse is what a not-None check cannot see."""
    for p in _plays():
        assert 1 <= p["down"] <= 4, f"down out of range: {p['down']}"
        assert 0 <= p["distance"] <= 99, f"distance out of range: {p['distance']}"
        assert 1 <= p["yards_to_goal"] <= 99, (
            f"yards_to_goal out of range: {p['yards_to_goal']}")


def test_possession_is_a_real_team_and_defence_is_the_other_one():
    st = parse_game_state(_payload(), GAME)
    teams = {st.get("home"), st.get("away")} - {None}
    assert len(teams) == 2, f"expected two teams, got {teams}"
    for p in _plays():
        assert p["pos_team"] in teams, f"pos_team {p['pos_team']} not a competitor"
        assert p["def_pos_team"] in teams
        assert p["pos_team"] != p["def_pos_team"], "possession on both sides"


def test_yards_to_goal_is_yardline_100_not_the_raw_yard_line():
    """`yardsToEndzone`, not `yardLine`. They coincide on one half of the field
    and diverge on the other, so a wrong pick is invisible in half the data --
    which is why this asserts the mapping, not the value's presence."""
    payload = _payload()
    raw = [pl for d in payload["drives"]["previous"] for pl in d["plays"]]
    parsed = _plays()
    assert len(raw) == len(parsed)
    for r, p in zip(raw, parsed):
        assert p["yards_to_goal"] == r["start"]["yardsToEndzone"]


def test_state_and_win_probability_still_parse():
    """Sibling rows written by the same poll, so a shared regression shows."""
    payload = _payload()
    st = parse_game_state(payload, GAME)
    assert st["home_score"] is not None and st["away_score"] is not None
    assert parse_win_probability(payload, GAME)
