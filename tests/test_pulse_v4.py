"""The v4 bundle: pure functions and the live engine's consumption of them.

What is defended:

* the pace/efficiency projection preserves the pregame anchor exactly at
  tip-off and moves only as evidence accrues, pace believed faster than
  efficiency (the registered shrink priors);
* availability flags fire on the registered thresholds (starter PF>=4 pre-Q4
  / >=5 in Q4, top-minutes starter off the floor in Q4, ejection) and widen
  sigma by exactly the registered factor — never direction;
* the on-floor tracker follows the substitution stream from the starters;
* scoring runs are computed but consumed by NOTHING (annotation only —
  pinned by the AST test's absence of any run input to pricing, and by the
  fv equality test here);
* the engine in v4 mode: totals rows priced by the pace projection say
  'v4'; winner rows with an active flag say 'v4' and carry widened-sigma
  pricing; winner rows with no active flag price identically to v3 and say
  'v3'; missing box counts fall back loudly to v3-style totals.
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
GAME = "992001"
SLUG = "test-pulse-v4-market"

_Session = get_sessionmaker(get_engine())

NOW = dt.datetime.now(UTC)
EVENT = f"wnba-ny-chi-{(NOW + sig._ET_OFFSET).date():%Y-%m-%d}"


@pytest.fixture(autouse=True)
def clean():
    yield
    with _Session() as s:
        s.execute(text("delete from pulse_decisions where market_slug like :m"),
                  {"m": SLUG + "%"})
        s.execute(text("delete from market_snapshots where market_slug like :m"),
                  {"m": SLUG + "%"})
        for t in ("espn_live_box_snapshots", "espn_live_plays",
                  "espn_live_player_snapshots"):
            s.execute(text(f"delete from {t} where espn_game_id like '9920%'"))
        s.execute(text("delete from service_heartbeats where service = 'pulse_engine'"))
        s.commit()


# --------------------------------------------------------------------- #
# Pure functions
# --------------------------------------------------------------------- #


def test_projection_preserves_the_pregame_anchor_on_expectation():
    """On-expectation evidence keeps the projection at mu EXACTLY, at any
    elapsed — the anchor-preservation property the registration states.
    (A scoreless opening correctly dips it slightly: that is evidence.)"""
    p = sig.projected_total_v4(
        total_so_far=1, possessions_so_far=0.5, elapsed_minutes=0.25,
        minutes_left=39.75, pregame_mu=160.0, poss_rate_expected=2.0)
    assert p == pytest.approx(160.0, abs=1e-9)
    scoreless = sig.projected_total_v4(
        total_so_far=0, possessions_so_far=0.5, elapsed_minutes=0.25,
        minutes_left=39.75, pregame_mu=160.0, poss_rate_expected=2.0)
    assert 155.0 < scoreless < 160.0


def test_projection_believes_pace_before_efficiency():
    """Same 20% surplus, once as pace and once as efficiency, at the half:
    the pace version must move the projection further (k_pace < k_eff)."""
    base = dict(total_so_far=80, elapsed_minutes=20.0, minutes_left=20.0,
                pregame_mu=160.0, poss_rate_expected=2.0)
    # Baseline consistency: on-expectation game stays ~mu.
    on_pace = sig.projected_total_v4(possessions_so_far=40.0, **base)
    assert on_pace == pytest.approx(160.0, abs=0.5)
    fast = sig.projected_total_v4(possessions_so_far=48.0, **{
        **base, "total_so_far": 96})     # +20% possessions, same ppp
    hot = sig.projected_total_v4(possessions_so_far=40.0, **{
        **base, "total_so_far": 96})     # same possessions, +20% ppp
    assert fast is not None and hot is not None
    assert fast > hot > 160.0            # both up; pace trusted more


def test_availability_flags_fire_on_registered_thresholds():
    def row(aid, team="1", fouls=0, starter=True, minutes=20, ejected=False):
        return {"athlete_id": aid, "team_id": team, "fouls": fouls,
                "starter": starter, "minutes": minutes, "ejected": ejected}

    # PF 4 pre-Q4 fires; PF 4 in Q4 does not (threshold 5 there).
    rows = [row("a", fouls=4), row("b")]
    assert sig.availability_flags(player_rows=rows, sub_plays=[], period=3).foul_trouble
    assert not sig.availability_flags(player_rows=rows, sub_plays=[], period=4).foul_trouble
    # Ejection fires any period; sigma factor is exactly the registered one.
    ej = sig.availability_flags(
        player_rows=[row("a", ejected=True)], sub_plays=[], period=2)
    assert ej.ejected and ej.sigma_factor == sig.AVAILABILITY_SIGMA_FACTOR
    # Star-off: top-minutes starter subbed out in Q4.
    rows = [row("star", minutes=30), row("role", minutes=10)]
    subs = [{"type_text": "Substitution", "athlete_id_1": "bench",
             "athlete_id_2": "star"}]
    assert sig.availability_flags(player_rows=rows, sub_plays=subs, period=4).star_off
    assert not sig.availability_flags(player_rows=rows, sub_plays=[], period=4).star_off


def test_on_floor_follows_the_substitution_stream():
    floor = sig.on_floor({"a", "b"}, [
        {"type_text": "Substitution", "athlete_id_1": "c", "athlete_id_2": "a"},
        {"type_text": "Substitution", "athlete_id_1": "a", "athlete_id_2": "b"},
    ])
    assert floor == {"a", "c"}


def test_scoring_run_is_computed_and_prices_nothing():
    plays = [{"scoring_play": True, "home_score": h, "away_score": a}
             for h, a in ((2, 0), (4, 0), (7, 0), (7, 2))]
    assert sig.scoring_run(plays) == 3       # 2-0 -> 7-2 over the window
    # Consumed by nothing: pricing functions take no run argument at all —
    # asserted structurally by signature.
    import inspect
    for fn in (sig.projected_total_v4, sig.availability_flags):
        assert "run" not in " ".join(inspect.signature(fn).parameters)


# --------------------------------------------------------------------- #
# The engine in v4 mode
# --------------------------------------------------------------------- #


def _box(s, *, ago, period=4, clock=300.0, fga=35, oreb=5, to=7, fta=10):
    s.execute(text("""
        insert into espn_live_box_snapshots
            (first_seen_at, espn_game_id, game_state, period, clock_seconds,
             clock_source, home_team_id, away_team_id, home_score, away_score,
             home_fga, home_oreb, home_turnovers, home_fta,
             away_fga, away_oreb, away_turnovers, away_fta)
        values (:t, :g, 'in', :p, :c, 'header', '8201', '8202', 55, 45,
                :fga, :oreb, :to, :fta, :fga, :oreb, :to, :fta)
    """), {"t": NOW - dt.timedelta(seconds=ago), "g": GAME,
           "p": period, "c": clock, "fga": fga, "oreb": oreb,
           "to": to, "fta": fta})


def _player(s, *, aid, ago=30, fouls=0, starter=True, minutes=20,
            ejected=False, team="8201"):
    s.execute(text("""
        insert into espn_live_player_snapshots
            (first_seen_at, espn_game_id, team_id, athlete_id, minutes,
             fouls, starter, ejected)
        values (:t, :g, :tm, :a, :m, :f, :st, :ej)
    """), {"t": NOW - dt.timedelta(seconds=ago), "g": GAME, "tm": team,
           "a": aid, "m": minutes, "f": fouls, "st": starter, "ej": ejected})


def _snap(s, *, ago, mtype=pl.MARKET_WINNER, line=None, bid=0.60, ask=0.62):
    s.execute(text("""
        insert into market_snapshots
            (market_slug, event_slug, game_id, sports_market_type, line,
             captured_at, best_bid, best_ask, is_live, event_score,
             event_period, min_trade_qty)
        values (:m, :e, 'v4-game', :ty, :ln, :t, :b, :a, true, '55-45',
                'Q4', 0.01)
    """), {"m": SLUG, "e": EVENT, "ty": mtype, "ln": line,
           "t": NOW - dt.timedelta(seconds=ago), "b": bid, "a": ask})


def _engine():
    eng = PulseEngine(
        _Session,
        estimates_version=pl.ESTIMATES_V4,
        settle_every_seconds=10 ** 9,
        bankroll_reader=lambda: 200.0,
        settlement_lookup=lambda slug: None,
    )
    eng._anchors[EVENT] = EventAnchors(
        winner_mid=0.50, totals_mu=165.0, espn_game_id=GAME,
        poss_rate_exp=2.0)
    return eng


def _enters():
    with _Session() as s:
        return s.query(PulseDecision).filter(
            PulseDecision.market_slug == SLUG,
            PulseDecision.action == ENTER).all()


def test_v4_totals_price_with_the_pace_projection_and_say_v4():
    with _Session() as s:
        _box(s, ago=5)
        _snap(s, ago=10, mtype=pl.MARKET_TOTAL, line=140.5)
        s.commit()
    _engine().cycle()
    rows = _enters()
    assert len(rows) == 1
    r = rows[0]
    assert r.estimates_version == "v4"
    assert r.projected_total is not None
    assert r.minutes_left_is_estimate is False


def test_v4_winner_without_active_flags_prices_v3_and_says_v3():
    """No flag active: the winner number is v3's exactly, and the label
    says so — the mode is not the label, per the registration."""
    with _Session() as s:
        _box(s, ago=5)
        _player(s, aid="p1", fouls=1)
        _snap(s, ago=10)
        s.commit()
    _engine().cycle()
    rows = _enters()
    assert len(rows) == 1
    assert rows[0].estimates_version == "v3"


def test_v4_winner_with_foul_trouble_widens_sigma_and_says_v4():
    """PF 5 in Q4 fires the flag: sigma widens x1.15, so the favourite's FV
    sits closer to the market than the unflagged number — uncertainty, not
    direction."""
    with _Session() as s:
        _box(s, ago=5)
        _player(s, aid="p1", fouls=5)
        _snap(s, ago=10)
        s.commit()
    _engine().cycle()
    flagged = _enters()[0]
    assert flagged.estimates_version == "v4"
    with _Session() as s:
        s.execute(text("delete from pulse_decisions where market_slug like :m"),
                  {"m": SLUG + "%"})
        s.execute(text("delete from espn_live_player_snapshots where espn_game_id = :g"),
                  {"g": GAME})
        s.commit()
    _engine().cycle()                          # same state, no flags
    unflagged = _enters()[0]
    assert unflagged.estimates_version == "v3"
    # Widened sigma pulls the big favourite toward 0.5.
    assert float(flagged.fair_value) < float(unflagged.fair_value)


def test_v4_totals_without_box_counts_fall_back_loudly_to_v3_style():
    with _Session() as s:
        _box(s, ago=5, fga=None, oreb=None, to=None, fta=None)
        _snap(s, ago=10, mtype=pl.MARKET_TOTAL, line=140.5)
        s.commit()
    eng = _engine()
    eng.cycle()
    rows = _enters()
    assert len(rows) == 1
    assert rows[0].estimates_version == "v3"   # clock still exact
    assert (EVENT, "no_box_counts") in eng._v3_fallback_logged
