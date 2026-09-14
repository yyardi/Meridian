"""Which row the ladder calibration calls a final score.

What is defended:

* a `post` row wins over a LATER in-game row, because ESPN drops `period` on
  the final (101 of 107 CFB post rows carry period NULL) and reverts states;
* the route is labelled, so a 'proxy' final — a pre-whistle score, biased
  toward UNDER on a totals market — cannot be read as a confirmed one;
* and a game with no `post` row still produces a final, labelled 'proxy',
  because whether to EXCLUDE those is a strategy decision taken elsewhere.

Against LIVE_FINALS_SQL rather than GAMES_SQL: the latter reads
`espn_cfb_backfill_games`, which has no migration and no model (it is created
by `archive/cfb/backfill_cfb.py`), so a migrated test schema does not have it.
The extracted CTE is the part this change touched.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text

from cfb.run_ladder_calibration import LIVE_FINALS_SQL
from core.storage import get_engine, get_sessionmaker

UTC = dt.timezone.utc
_Session = get_sessionmaker(get_engine())
EG = "test-ladder-espn-1"
EG2 = "test-ladder-espn-2"
VG = "test-ladder-venue-1"
NOW = dt.datetime.now(UTC)
NOW_PER_TEST = True


@pytest.fixture(autouse=True)
def clean():
    yield
    with _Session() as s:
        s.execute(text("delete from espn_cfb_game_state where game_id like :p"),
                  {"p": "test-ladder-%"})
        s.execute(text("delete from cfb_game_map where espn_game_id like :p"),
                  {"p": "test-ladder-%"})
        s.commit()


def _map(s, eg=EG, vg=VG):
    s.execute(text("""
        insert into cfb_game_map (first_seen_at, espn_game_id, venue_game_id,
                                  event_slug, match_method)
        values (now(), :eg, :vg, :slug, 'test')
    """), {"eg": eg, "vg": vg, "slug": f"slug-{eg}"})


def _state(s, *, eg=EG, at, state, period, h, a, league="cfb"):
    s.execute(text("""
        insert into espn_cfb_game_state
            (first_seen_at, league, game_id, state, period, display_clock,
             home, away, home_score, away_score)
        values (:at, :lg, :eg, :st, :p, '0:00', '1', '2', :h, :a)
    """), {"at": at, "lg": league, "eg": eg, "st": state, "p": period,
           "h": h, "a": a})


def _finals():
    with _Session() as s:
        return {r._mapping["eg"]: dict(r._mapping)
                for r in s.execute(text(LIVE_FINALS_SQL))
                if str(r._mapping["eg"]).startswith("test-ladder-")}


def test_the_post_row_wins_over_a_later_in_game_row():
    """★ THE DEFECT. `period >= 4` excluded the final, because ESPN drops
    `period` on the post row — 101 of 107 CFB post rows carry NULL. The old
    `DISTINCT ON ... ORDER BY first_seen_at DESC` then took the last IN-GAME
    row: a pre-whistle score for a game whose true final sat in the same
    table, on 28 CFB and 8 NFL of the games this query feeds.

    A pre-whistle total is too LOW, which settles a total UNDER when the real
    total may have cleared — and `cfb_total_under_all` is registered.
    """
    with _Session() as s:
        _map(s)
        _state(s, at=NOW - dt.timedelta(minutes=9), state="in", period=4,
               h=21, a=17)
        _state(s, at=NOW - dt.timedelta(minutes=6), state="post", period=None,
               h=24, a=17)
        # The revert: ESPN puts it back to `in` AFTER the final. Observed on
        # a real game 9.75 hours after its post.
        _state(s, at=NOW - dt.timedelta(minutes=3), state="in", period=4,
               h=21, a=17)
        s.commit()

    got = _finals()[EG]
    assert (got["h"], got["a"]) == (24, 17), (
        "took a pre-whistle row over the post row — the period>=4 defect")
    assert got["src"] == "post"


def test_a_game_that_never_posted_is_labelled_proxy():
    """Still produces a final — excluding it is a strategy decision made by
    the caller — but the label says the number is pre-whistle."""
    with _Session() as s:
        _map(s, eg=EG2, vg=VG + "-2")
        _state(s, eg=EG2, at=NOW - dt.timedelta(minutes=5), state="in",
               period=4, h=14, a=10)
        s.commit()

    got = _finals()[EG2]
    assert (got["h"], got["a"]) == (14, 10)
    assert got["src"] == "proxy", (
        "an unconfirmed final was not labelled; a reader cannot tell it from "
        "a confirmed one")


def test_the_last_post_row_wins_among_post_rows():
    """The score moves after the first post in 2 of the 37 games where that
    is observable, by up to 9 points. The LAST post row is the corrected one
    — the rule on CfbGameState's docstring."""
    with _Session() as s:
        _map(s)
        _state(s, at=NOW - dt.timedelta(minutes=8), state="post", period=None,
               h=31, a=17)
        _state(s, at=NOW - dt.timedelta(minutes=4), state="post", period=None,
               h=24, a=17)          # ESPN takes 7 points back
        s.commit()

    got = _finals()[EG]
    assert (got["h"], got["a"]) == (24, 17), "kept the pre-correction score"
    assert got["src"] == "post"
