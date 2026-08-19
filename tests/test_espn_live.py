"""The signal-side recorder, its point-in-time tables, and signals 1-3.

What is defended:

* parsers transcribe a REAL recorded payload (the fixture is a slimmed copy
  of game 401857152's actual summary) — clock formats, made-attempted
  splits, the nested season-type spelling (#25), the play fields;
* every stored row's `first_seen_at` is OUR observation instant, not ESPN's;
* plays, win-probability and injury rows are idempotent across re-polls
  (append-only / on-change-only, structurally); box snapshots are one per
  poll because the cadence is the data;
* a game leaving the live set gets exactly one final sweep;
* the exact clock converts venue time to regulation minutes and refuses to
  pretend OT minutes are regulation minutes;
* pace decomposition and shooting splits do their arithmetic (free throws
  NEVER count as field goals);
* the point-in-time bound lives in the signal loaders' queries;
* and the structural claim: no path from any of it to an order.
"""

from __future__ import annotations

import datetime as dt
import json
import os

import pytest
from sqlalchemy import text

from core.feeds import espn_live_recorder as rec
from core.feeds import espn_live_storage as st
from core.pulse import signals as sig
from core.storage import get_engine, get_sessionmaker

UTC = dt.timezone.utc
GAME = "401857152"

_Session = get_sessionmaker(get_engine())

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "fixtures", "espn_summary_slim.json")


def _payload() -> dict:
    with open(FIXTURE) as f:
        return json.load(f)


@pytest.fixture(autouse=True)
def clean():
    yield
    with _Session() as s:
        for table in ("espn_live_plays", "espn_live_box_snapshots",
                      "espn_live_player_snapshots", "espn_live_win_probability",
                      "espn_live_injury_observations"):
            s.execute(text(f"delete from {table} where espn_game_id = :g"),
                      {"g": GAME})
        s.execute(text(
            "delete from service_heartbeats where service = 'espn_live_recorder'"))
        s.commit()


NOW = dt.datetime.now(UTC)


# --------------------------------------------------------------------- #
# Parsers, against the real payload
# --------------------------------------------------------------------- #


def test_parse_clock_handles_both_observed_formats():
    assert rec.parse_clock("3:36") == pytest.approx(216.0)
    assert rec.parse_clock("10:00") == pytest.approx(600.0)
    assert rec.parse_clock("36.0") == pytest.approx(36.0)
    assert rec.parse_clock("0.4") == pytest.approx(0.4)
    assert rec.parse_clock(None) is None
    assert rec.parse_clock("garbage") is None


def test_parse_plays_transcribes_the_recorded_game():
    plays = rec.parse_plays(_payload(), espn_game_id=GAME, first_seen_at=NOW)
    assert len(plays) == 40
    by_type = {}
    for p in plays:
        assert p["play_id"].startswith(GAME)
        assert p["first_seen_at"] == NOW
        by_type.setdefault(p["type_text"], p)
    # A free throw is a shooting play with ONE point attempted — the case the
    # shooting-splits signal must exclude from FG counts.
    ft = next(p for t, p in by_type.items() if t and "Free Throw" in t)
    assert ft["shooting_play"] is True and ft["points_attempted"] == 1
    sub = by_type.get("Substitution")
    assert sub is not None and sub["athlete_id_1"] and sub["athlete_id_2"]
    # ESPN's wallclock is data BESIDE our stamp, parsed tz-aware.
    stamped = [p for p in plays if p["wallclock"] is not None]
    assert stamped and all(p["wallclock"].tzinfo is not None for p in stamped)


def test_parse_box_carries_state_season_and_the_play_clock_fallback():
    box = rec.parse_box(_payload(), espn_game_id=GAME, first_seen_at=NOW)
    assert box is not None
    assert box["game_state"] == "post"
    assert box["season_type"] == 2            # the NESTED spelling (#25)
    assert box["home_team_id"] == "18" and box["away_team_id"] == "6"
    assert box["home_score"] == 85 and box["away_score"] == 77
    # LA (away) shot 29-64 in the recorded game.
    assert box["away_fgm"] == 29 and box["away_fga"] == 64
    assert box["away_tpm"] == 2 and box["away_tpa"] == 16
    # A finished game's header has no clock — the newest play supplies it,
    # and the source column says so (the live checklist's question 2).
    assert box["clock_source"] == "play"
    assert box["period"] is not None


def test_parse_players_and_injuries():
    players = rec.parse_players(_payload(), espn_game_id=GAME, first_seen_at=NOW)
    assert len(players) == 12                  # 6 per team in the slim fixture
    starter = next(p for p in players if p["starter"])
    assert starter["athlete_id"] and starter["minutes"] is not None
    assert starter["fga"] is not None and starter["fgm"] <= starter["fga"]

    injuries = rec.parse_injuries(_payload(), espn_game_id=GAME, first_seen_at=NOW)
    assert len(injuries) >= 5
    assert all(i["status"] for i in injuries)


# --------------------------------------------------------------------- #
# The recorder against the database
# --------------------------------------------------------------------- #


class FakeESPN:
    """Scoreboard + summary from the fixture; state is mutable per test."""

    def __init__(self, state="in"):
        self.state = state
        self.summary_calls = 0

    def get_scoreboard(self, date_str):
        return {"events": [{
            "id": GAME,
            "competitions": [{"status": {"type": {"state": self.state}}}],
        }]}

    def get(self, url, params=None):
        self.summary_calls += 1
        return _payload()


def _recorder(client, **kw):
    kw.setdefault("scoreboard_interval", 0.0)   # re-poll every cycle in tests
    return rec.EspnLiveRecorder(_Session, client=client, **kw)


def _count(table):
    with _Session() as s:
        return s.execute(text(
            f"select count(*) from {table} where espn_game_id = :g"),
            {"g": GAME}).scalar()


def test_one_cycle_writes_all_five_tables():
    r = _recorder(FakeESPN())
    polled, rows = r.cycle()
    assert polled == 1 and rows > 0
    assert _count("espn_live_plays") == 40
    assert _count("espn_live_box_snapshots") == 1
    assert _count("espn_live_player_snapshots") == 12
    assert _count("espn_live_win_probability") == 10
    assert _count("espn_live_injury_observations") >= 5
    with _Session() as s:
        seen = s.execute(text("""
            select min(first_seen_at) from espn_live_plays
            where espn_game_id = :g"""), {"g": GAME}).scalar()
    assert seen is not None and seen >= NOW - dt.timedelta(minutes=5)


def test_repolling_is_idempotent_where_it_must_be():
    """Plays, win probability and injuries never duplicate; box snapshots
    grow one per poll BECAUSE the cadence is the data; players respect the
    slow cadence."""
    r = _recorder(FakeESPN())
    r.cycle()
    r.cycle()
    assert _count("espn_live_plays") == 40                 # append-only
    assert _count("espn_live_win_probability") == 10
    assert _count("espn_live_injury_observations") == _count(
        "espn_live_injury_observations")
    assert _count("espn_live_box_snapshots") == 2          # one per poll
    assert _count("espn_live_player_snapshots") == 12      # 60s cadence held


def test_a_game_leaving_the_live_set_gets_one_final_sweep():
    client = FakeESPN()
    r = _recorder(client)
    r.cycle()
    client.state = "post"
    r.cycle()                                  # detects departure + final sweep
    calls_after_final = client.summary_calls
    r.cycle()                                  # game gone: no more polls
    assert client.summary_calls == calls_after_final
    assert GAME not in r._live and GAME not in r._pending_final


# --------------------------------------------------------------------- #
# Signals
# --------------------------------------------------------------------- #


def test_exact_clock_regulation_arithmetic():
    assert sig.exact_clock(4, 216.0).minutes_left == pytest.approx(3.6)
    assert sig.exact_clock(1, 600.0).minutes_left == pytest.approx(40.0)
    assert sig.exact_clock(2, 0.0).minutes_left == pytest.approx(20.0)
    assert sig.exact_clock(3, 45.0).minutes_left == pytest.approx((600 + 45) / 60)


def test_exact_clock_refuses_to_call_ot_minutes_regulation():
    ot = sig.exact_clock(5, 120.0)
    assert ot.is_overtime
    assert ot.minutes_left == 0.0
    assert ot.ot_minutes_left == pytest.approx(2.0)


def test_pace_decomposition_separates_fast_from_hot():
    row = {"home_fga": 40, "home_oreb": 5, "home_turnovers": 7, "home_fta": 10,
           "home_score": 50,
           "away_fga": 38, "away_oreb": 4, "away_turnovers": 6, "away_fta": 8,
           "away_score": 44}
    d = sig.pace_decomposition(row, elapsed_minutes=20.0)
    assert d is not None
    assert d.home.possessions == pytest.approx(40 - 5 + 7 + 4.4)
    assert d.home.points_per_possession == pytest.approx(50 / 46.4)
    assert d.pace_per_40 == pytest.approx(d.possessions_per_side * 2)
    assert sig.pace_decomposition({"home_fga": None}, elapsed_minutes=20.0) is None


def test_shooting_splits_never_count_free_throws_as_field_goals():
    plays = [
        {"team_id": "6", "period": 1, "shooting_play": True,
         "scoring_play": True, "points_attempted": 2},
        {"team_id": "6", "period": 1, "shooting_play": True,
         "scoring_play": False, "points_attempted": 3},
        {"team_id": "6", "period": 1, "shooting_play": True,
         "scoring_play": True, "points_attempted": 1},   # FT — not a FG
        {"team_id": "6", "period": 2, "shooting_play": True,
         "scoring_play": True, "points_attempted": 3},
        {"team_id": "6", "period": 1, "shooting_play": False,
         "scoring_play": False, "points_attempted": None},  # rebound etc.
    ]
    splits = sig.shooting_splits(plays)
    q1 = splits[("6", 1)]
    assert (q1.fgm, q1.fga) == (1, 2)
    assert (q1.tpm, q1.tpa) == (0, 1)
    assert (q1.ftm, q1.fta) == (1, 1)
    q2 = splits[("6", 2)]
    assert (q2.tpm, q2.tpa) == (1, 1) and q2.fgm == 1


def test_splits_from_the_recorded_game_agree_with_its_own_plays():
    plays = rec.parse_plays(_payload(), espn_game_id=GAME, first_seen_at=NOW)
    splits = sig.shooting_splits(plays)
    n_fg_plays = sum(1 for p in plays
                     if p["shooting_play"] and (p["points_attempted"] or 0) >= 2)
    assert sum(s.fga for s in splits.values()) == n_fg_plays


def test_signal_loaders_enforce_the_point_in_time_bound():
    with _Session() as s:
        for period, clock, ago in ((2, 300.0, 60), (4, 100.0, 5)):
            s.add(st.EspnLiveBoxSnapshot(
                espn_game_id=GAME, game_state="in", period=period,
                clock_seconds=clock, clock_source="header",
                first_seen_at=NOW - dt.timedelta(seconds=ago)))
        s.commit()
    with _Session() as s:
        # As of 30s ago, only the period-2 reading was knowable.
        old = sig.latest_exact_clock(s, GAME, at=NOW - dt.timedelta(seconds=30))
        newest = sig.latest_exact_clock(s, GAME)
    assert old is not None and old.period == 2
    assert old.minutes_left == pytest.approx(25.0)
    assert newest is not None and newest.period == 4


# --------------------------------------------------------------------- #
# The structural claim extends to the signal side
# --------------------------------------------------------------------- #


def test_the_signal_side_cannot_place_modify_or_cancel_anything():
    import ast
    import inspect

    for module in (rec, st, sig):
        tree = ast.parse(inspect.getsource(module))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
                imported.update(f"{node.module}.{a.name}" for a in node.names)
            elif isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
        for forbidden in ("core.executor",
                          "core.fill_watcher",
                          "core.polymarket.client",
                          "core.polymarket.client.PolymarketOrderClient",
                          "core.polymarket.client.PolymarketAuthedClient",
                          "core.polymarket.client.USCredentials"):
            assert not any(i == forbidden for i in imported), (
                f"{module.__name__} imports {forbidden}")
        calls = {
            n.func.attr for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        }
        assert not {"submit_limit_order", "cancel_order"} & calls
