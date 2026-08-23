"""The v3 regime in the LIVE engine: the venue clock, and only the clock.

What is defended:

* a fresh venue clock replaces the estimator — the row says 'v3',
  minutes_left is exact, and minutes_left_is_estimate is False on the
  EXISTING field (the seam contract);
* a stale or missing clock falls back to the estimator and the row says
  'v1' — the engine mode is not the row label;
* overtime abstains (no registered OT model; the venue clock does not
  change that);
* an unresolvable event join prices v1;
* v1 mode never consumes the venue clock even when readings exist;
* the live join and the one-query clock reader behave (fresh in, stale
  out).
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text

from core.pulse import live as pl
from core.pulse import signals as sig
from core.pulse.live import EventAnchors, PulseEngine
from core.pulse.storage import ENTER, PulseDecision
from core.storage import get_engine, get_sessionmaker

UTC = dt.timezone.utc
GAME = "991001"
SLUG = "test-pulse-v3live-market"

_Session = get_sessionmaker(get_engine())

NOW = dt.datetime.now(UTC)
#: Slug date derived from the seeded clock (the join's ±1-ET-day window) —
#: the lesson from the eval fixtures, applied from birth this time.
EVENT = f"wnba-ny-chi-{(NOW + sig._ET_OFFSET).date():%Y-%m-%d}"


@pytest.fixture(autouse=True)
def clean():
    yield
    with _Session() as s:
        s.execute(text("delete from pulse_decisions where market_slug like :m"),
                  {"m": SLUG + "%"})
        s.execute(text("delete from market_snapshots where market_slug like :m"),
                  {"m": SLUG + "%"})
        s.execute(text("delete from espn_live_box_snapshots where espn_game_id like '9910%'"))
        s.execute(text("delete from team_game_logs where espn_game_id like 'tpv3l-%'"))
        s.execute(text("delete from service_heartbeats where service = 'pulse_engine'"))
        s.commit()


def _team_map(s):
    for tid, ab, oid, oab in (("8101", "NY", "8102", "CHI"),
                              ("8102", "CHI", "8101", "NY")):
        s.execute(text("""
            insert into team_game_logs
                (game_date, season, espn_game_id, team_id, team_abbrev,
                 opponent_id, opponent_abbrev, is_home, points_scored,
                 points_allowed, is_completed, season_type)
            values (:d, 2026, :g, :t, :a, :o, :oa, true, 80, 70, true, 2)
        """), {"d": NOW - dt.timedelta(days=20), "g": f"tpv3l-{tid}",
               "t": tid, "a": ab, "o": oid, "oa": oab})


def _box(s, *, ago, period=4, clock=300.0, game=GAME):
    s.execute(text("""
        insert into espn_live_box_snapshots
            (first_seen_at, espn_game_id, game_state, period, clock_seconds,
             clock_source, home_team_id, away_team_id)
        values (:t, :g, 'in', :p, :c, 'header', '8101', '8102')
    """), {"t": NOW - dt.timedelta(seconds=ago), "g": game,
           "p": period, "c": clock})


def _snap(s, *, ago, bid=0.60, ask=0.62, score="55-45", period="Q4"):
    s.execute(text("""
        insert into market_snapshots
            (market_slug, event_slug, game_id, sports_market_type,
             captured_at, best_bid, best_ask, is_live, event_score,
             event_period, min_trade_qty)
        values (:m, :e, 'v3l-game', :ty, :t, :b, :a, true, :sc, :p, 0.01)
    """), {"m": SLUG, "e": EVENT, "ty": pl.MARKET_WINNER,
           "t": NOW - dt.timedelta(seconds=ago), "b": bid, "a": ask,
           "sc": score, "p": period})


def _engine(version=pl.ESTIMATES_V3, espn_game_id=GAME):
    eng = PulseEngine(
        _Session,
        estimates_version=version,
        settle_every_seconds=10 ** 9,
        bankroll_reader=lambda: 200.0,
        settlement_lookup=lambda slug: None,
    )
    eng._anchors[EVENT] = EventAnchors(
        winner_mid=0.50, totals_mu=165.0, espn_game_id=espn_game_id)
    return eng


def _enters():
    with _Session() as s:
        return s.query(PulseDecision).filter(
            PulseDecision.market_slug == SLUG,
            PulseDecision.action == ENTER).all()


def test_fresh_venue_clock_prices_v3_with_exact_minutes():
    with _Session() as s:
        _box(s, ago=5, period=4, clock=300.0)      # 5:00 left in Q4 = 5.0 min
        _snap(s, ago=10)
        s.commit()
    _engine().cycle()
    rows = _enters()
    assert len(rows) == 1
    r = rows[0]
    assert r.estimates_version == "v3"
    assert float(r.minutes_left) == pytest.approx(5.0)
    assert r.minutes_left_is_estimate is False     # the seam contract
    # And the FV reflects the exact 5 minutes: Phi(10/(2.628*sqrt(5))) ~ 0.955
    assert float(r.fair_value) > 0.93


def test_stale_venue_clock_falls_back_to_v1_and_says_so():
    with _Session() as s:
        _box(s, ago=120, period=4, clock=300.0)    # 2 min stale > 60s bound
        _snap(s, ago=200)                          # Q4 first seen 200s ago...
        _snap(s, ago=10)                           # ...so this tick is mid-period
        s.commit()
    _engine().cycle()
    rows = _enters()
    assert len(rows) == 1
    r = rows[0]
    assert r.estimates_version == "v1"             # the mode is not the label
    assert r.minutes_left_is_estimate is True


def test_overtime_venue_clock_abstains():
    with _Session() as s:
        _box(s, ago=5, period=5, clock=120.0)      # OT, 2:00 left
        _snap(s, ago=10, period="OT")
        s.commit()
    _engine().cycle()
    assert _enters() == []                          # no registered OT model


def test_unresolvable_join_prices_v1():
    with _Session() as s:
        _box(s, ago=5)
        _snap(s, ago=10)
        s.commit()
    _engine(espn_game_id=None).cycle()             # join failed at anchor time
    rows = _enters()
    assert len(rows) == 1
    assert rows[0].estimates_version == "v1"


def test_v1_mode_never_consumes_the_venue_clock():
    with _Session() as s:
        _box(s, ago=5)
        _snap(s, ago=200)
        _snap(s, ago=10)
        s.commit()
    _engine(version=pl.ESTIMATES_V1).cycle()
    rows = _enters()
    assert len(rows) == 1
    assert rows[0].estimates_version == "v1"
    assert rows[0].minutes_left_is_estimate is True


def test_live_join_and_clock_reader():
    with _Session() as s:
        _team_map(s)
        _box(s, ago=3600)                          # game seen an hour ago
        _box(s, ago=5, clock=250.0)                # freshest reading
        _box(s, ago=30, clock=400.0)
        s.commit()
    with _Session() as s:
        assert sig.resolve_espn_game(s, EVENT) == GAME
        clocks = sig.latest_venue_clocks(s, [GAME])
        assert GAME in clocks
        assert clocks[GAME].period_seconds_left == pytest.approx(250.0)
        # Staleness bound: nothing fresh enough -> absent, caller falls back.
        none = sig.latest_venue_clocks(s, [GAME], max_staleness_seconds=1.0)
    assert none == {}
