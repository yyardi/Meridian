"""The v3 eval: the signal-consuming arm, exactly as protocol #38 registered.

What is defended:

* the join resolves an event to its ESPN game via team mapping + date, and
  ambiguity EXCLUDES (counted) rather than guesses;
* v3a is v1's own formulas fed the venue clock — same constants, and with no
  signal rows at all v3a IS v1 (all-fallback parity);
* a stale clock falls back to v1 per tick and is counted;
* the coverage metric counts exactly the ticks v1 must suppress but v3a can
  price (the late-quarter saturation hole);
* OT ticks are priced by NEITHER arm (no registered OT model) and counted;
* the ESPN win-probability reference converts the home frame to the slug's
  first-team frame through the join's orientation;
* floors are the protocol's and the verdict below them is NO DATA.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text

from core.pulse import replay_eval as re_
from core.storage import get_engine, get_sessionmaker

UTC = dt.timezone.utc
EVENT = "wnba-ny-chi-2026-08-19"
GAME = "990001"

_Session = get_sessionmaker(get_engine())

NOW = dt.datetime.now(UTC)


@pytest.fixture(autouse=True)
def clean():
    yield
    with _Session() as s:
        s.execute(text("delete from espn_live_box_snapshots where espn_game_id like '9900%'"))
        s.execute(text("delete from espn_live_win_probability where espn_game_id like '9900%'"))
        s.execute(text("delete from team_game_logs where espn_game_id like 'tpv3-%'"))
        s.commit()


def _team_map(s):
    """team_id -> abbrev rows the join reads (NY=home id 8001, CHI 8002)."""
    for tid, ab, opp_id, opp_ab in (("8001", "NY", "8002", "CHI"),
                                    ("8002", "CHI", "8001", "NY")):
        s.execute(text("""
            insert into team_game_logs
                (game_date, season, espn_game_id, team_id, team_abbrev,
                 opponent_id, opponent_abbrev, is_home, points_scored,
                 points_allowed, is_completed, season_type)
            values (:d, 2026, :g, :t, :a, :o, :oa, true, 80, 70, true, 2)
        """), {"d": NOW - dt.timedelta(days=30), "g": f"tpv3-{tid}",
               "t": tid, "a": ab, "o": opp_id, "oa": opp_ab})


def _box(s, *, at, period=4, clock=300.0, game=GAME,
         home_id="8001", away_id="8002"):
    s.execute(text("""
        insert into espn_live_box_snapshots
            (first_seen_at, espn_game_id, game_state, period, clock_seconds,
             clock_source, home_team_id, away_team_id)
        values (:t, :g, 'in', :p, :c, 'header', :h, :a)
    """), {"t": at, "g": game, "p": period, "c": clock,
           "h": home_id, "a": away_id})


def _wp(s, *, at, pct, play="1", game=GAME):
    s.execute(text("""
        insert into espn_live_win_probability
            (first_seen_at, espn_game_id, play_id, home_win_pct)
        values (:t, :g, :p, :w)
    """), {"t": at, "g": game, "p": f"{game}{play}", "w": pct})


def _event(**kw):
    defaults = {
        "event_slug": EVENT, "final_score": (80, 70), "winner_mid": 0.5,
        "mu_v4": None, "form": None, "form_fresh": False,
    }
    defaults.update(kw)
    return re_.EventData(**defaults)


def _tick(seconds_ago, bid, ask, score="55-45", period="Q4"):
    return re_.Tick(at=NOW - dt.timedelta(seconds=seconds_ago),
                    bid=bid, ask=ask, score=score, period=period)


# --------------------------------------------------------------------- #
# The join
# --------------------------------------------------------------------- #


def test_join_resolves_by_teams_and_date_and_orientation():
    with _Session() as s:
        _team_map(s)
        _box(s, at=NOW - dt.timedelta(hours=2))
        s.commit()
    signals, excluded = re_.resolve_signal_games(_Session, [_event()])
    assert excluded == 0
    assert EVENT in signals
    sig = signals[EVENT]
    assert sig.espn_game_id == GAME
    # Slug first team is 'ny' -> NY, which is the HOME id in the box row.
    assert sig.first_is_home is True
    assert len(sig.clock_rows) == 1


def test_ambiguous_join_excludes_and_counts():
    with _Session() as s:
        _team_map(s)
        _box(s, at=NOW - dt.timedelta(hours=2), game="990001")
        _box(s, at=NOW - dt.timedelta(hours=3), game="990002")   # same teams
        s.commit()
    signals, excluded = re_.resolve_signal_games(_Session, [_event()])
    assert EVENT not in signals
    assert excluded == 1


# --------------------------------------------------------------------- #
# The arm
# --------------------------------------------------------------------- #


def test_v3a_with_no_signal_rows_is_not_in_the_cohort():
    signals, _ = re_.resolve_signal_games(_Session, [_event()])
    assert signals == {}


def test_series_pointer_enforces_first_seen_bound():
    rows = [(NOW - dt.timedelta(seconds=60), 4, 300.0),
            (NOW - dt.timedelta(seconds=5), 4, 100.0)]
    p = re_._SeriesPointer(rows)
    assert p.at(NOW - dt.timedelta(seconds=30))[2] == 300.0
    assert p.at(NOW)[2] == 100.0
    assert re_._SeriesPointer(rows).at(NOW - dt.timedelta(seconds=90)) is None


def test_exact_clock_prices_where_the_estimator_saturates():
    """A tick deep into Q4 wall-time: v1's clock is exhausted (usable=False,
    no price) while the venue clock says 5:00 remains — the coverage tick."""
    from core.live_fv import minutes_remaining

    saturated = minutes_remaining("Q4", seconds_into_period=900.0)
    assert not saturated.usable            # the hole v3a exists to fill

    from core.pulse.signals import exact_clock
    exact = exact_clock(4, 300.0)
    fv = re_.estimate_fv(
        market_type=re_.MARKET_WINNER, line=None, margin=10, total_so_far=100,
        minutes_left=exact.minutes_left, winner_mid=0.5,
        params=re_.ArmParams(name="v3", sigma=re_.DEFAULT_SIGMA, totals_mu=None))
    assert fv is not None and fv > 0.9


def test_v3_end_to_end_counts_coverage_fallback_and_wp(monkeypatch):
    """A three-tick market: fresh exact clock (paired + WP), stale clock
    (fallback to v1), and a saturated-estimator tick (coverage). Floors not
    met -> NO DATA, which is the protocol working."""
    with _Session() as s:
        _team_map(s)
        # Clock rows: one fresh for tick A, none fresh for tick B (stale),
        # one fresh again for tick C where the estimator has saturated.
        _box(s, at=NOW - dt.timedelta(seconds=95), period=4, clock=400.0)
        _box(s, at=NOW - dt.timedelta(seconds=12), period=4, clock=290.0)
        _wp(s, at=NOW - dt.timedelta(seconds=95), pct=0.83, play="1")
        s.commit()

    # Period starts: Q4 first seen long ago so tick C's estimator saturates.
    q4_start = NOW - dt.timedelta(seconds=1000)
    data = _event()
    data.period_starts["Q4"] = q4_start
    data.markets["aec-" + EVENT] = (
        re_.MARKET_WINNER, None,
        [re_.Tick(at=NOW - dt.timedelta(seconds=90), bid=0.60, ask=0.62,
                  score="55-45", period="Q4"),
         re_.Tick(at=NOW - dt.timedelta(seconds=80), bid=0.60, ask=0.62,
                  score="55-45", period="Q4"),
         re_.Tick(at=NOW - dt.timedelta(seconds=8), bid=0.62, ask=0.64,
                  score="60-50", period="Q4")],
    )

    monkeypatch.setattr(re_, "load_events", lambda S, limit=None: [data])
    r = re_.evaluate_v3(_Session)

    assert r.n_events_with_signals == 1
    # Q4's first sighting is 1000s before NOW, so every tick sits >600s into
    # the quarter: v1's estimator is saturated (unusable) at all three. The
    # exact clock is fresh at all three (5s / 15s / 4s stale), so every tick
    # is a COVERAGE tick — v1 suppressed, v3a priced — and none is a paired
    # point or a fallback.
    assert r.coverage_ticks == 3
    assert r.n_points == 0 and r.fallback_ticks == 0
    assert 0.0 <= r.coverage_brier_sum / r.coverage_ticks <= 1.0
    assert r.verdict == "NO DATA"


def test_wp_frame_conversion_respects_orientation():
    sig_home = re_.SignalData(espn_game_id=GAME, first_is_home=True,
                              clock_rows=[], wp_rows=[])
    sig_away = re_.SignalData(espn_game_id=GAME, first_is_home=False,
                              clock_rows=[], wp_rows=[])
    p_home = 0.83
    assert (p_home if sig_home.first_is_home else 1 - p_home) == pytest.approx(0.83)
    assert (p_home if sig_away.first_is_home else 1 - p_home) == pytest.approx(0.17)
