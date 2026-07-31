"""Point-in-time feature tests.

The no-lookahead test is the most important test in the repository. A lookahead
bug does not crash — it produces an excellent, entirely fictional backtest.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import delete, select

from core.storage import TeamGameLog, get_engine, get_sessionmaker
from strategies.wnba_totals.config import WNBATotalsConfig
from strategies.wnba_totals.model.features import (
    _decayed_mean,
    _shrink,
    build_matchup_features,
    build_team_features,
    league_averages,
    pythagorean_win_pct,
)

UTC = dt.timezone.utc
T_HOME = "TEST_HOME"
T_AWAY = "TEST_AWAY"
SEASON = 1999  # fictional season, cannot collide with real data


def _game(session, *, gid, team, opp, date, scored, allowed, home=True, season_type=2):
    session.add(
        TeamGameLog(
            game_date=date, season=SEASON, espn_game_id=gid,
            team_id=team, team_abbrev=team[:5], opponent_id=opp, opponent_abbrev=opp[:5],
            is_home=home, points_scored=scored, points_allowed=allowed,
            is_completed=True, season_type=season_type,
        )
    )


@pytest.fixture
def session():
    Session = get_sessionmaker(get_engine())
    with Session() as s:
        s.execute(delete(TeamGameLog).where(TeamGameLog.season == SEASON))
        s.commit()
        yield s
        s.rollback()
        s.execute(delete(TeamGameLog).where(TeamGameLog.season == SEASON))
        s.commit()


def _seed(session, n=10, start_day=1, scored=85, allowed=80):
    for i in range(n):
        _game(
            session, gid=f"t{SEASON}-{i}", team=T_HOME, opp=T_AWAY,
            date=dt.datetime(SEASON, 6, start_day + i, tzinfo=UTC),
            scored=scored, allowed=allowed, home=(i % 2 == 0),
        )
        _game(
            session, gid=f"t{SEASON}-{i}", team=T_AWAY, opp=T_HOME,
            date=dt.datetime(SEASON, 6, start_day + i, tzinfo=UTC),
            scored=allowed, allowed=scored, home=(i % 2 == 1),
        )
    session.commit()


# ------------------------------------------------------------------ #
# 1. No lookahead — the critical one
# ------------------------------------------------------------------ #

def test_future_games_cannot_change_past_features(session):
    """Insert a game AFTER as_of; features as_of must be byte-identical."""
    _seed(session, n=8, start_day=1)
    as_of = dt.datetime(SEASON, 6, 15, tzinfo=UTC)

    before = build_team_features(team_id=T_HOME, as_of=as_of, session=session, season=SEASON)

    # A wildly different future game that would move every mean if it leaked.
    _game(session, gid=f"t{SEASON}-future", team=T_HOME, opp=T_AWAY,
          date=dt.datetime(SEASON, 8, 1, tzinfo=UTC), scored=200, allowed=10)
    session.commit()

    after = build_team_features(team_id=T_HOME, as_of=as_of, session=session, season=SEASON)
    assert before == after, "a future game changed a past feature vector"


def test_features_are_deterministic(session):
    _seed(session, n=8)
    as_of = dt.datetime(SEASON, 6, 15, tzinfo=UTC)
    a = build_team_features(team_id=T_HOME, as_of=as_of, session=session, season=SEASON)
    b = build_team_features(team_id=T_HOME, as_of=as_of, session=session, season=SEASON)
    assert a == b


def test_as_of_is_keyword_only_and_required():
    """There must be no way to ask for 'current' stats."""
    with pytest.raises(TypeError):
        build_team_features(T_HOME)  # type: ignore[call-arg]


def test_only_games_strictly_before_as_of_are_counted(session):
    _seed(session, n=5, start_day=1)  # games on Jun 1..5
    # as_of exactly at the Jun 3 game: that game must NOT count (strict <).
    as_of = dt.datetime(SEASON, 6, 3, tzinfo=UTC)
    f = build_team_features(team_id=T_HOME, as_of=as_of, session=session, season=SEASON)
    assert f.games_played == 2  # Jun 1 and Jun 2 only


# ------------------------------------------------------------------ #
# 2. Shrinkage
# ------------------------------------------------------------------ #

def test_shrink_pulls_small_samples_toward_league():
    #  1 game, k=5 -> mostly league
    assert _shrink(100.0, 80.0, n=1, k=5.0) == pytest.approx((100 + 5 * 80) / 6)
    # 30 games, k=5 -> mostly team
    near_team = _shrink(100.0, 80.0, n=30, k=5.0)
    assert near_team > 96.0


def test_shrink_with_zero_games_returns_league_mean():
    assert _shrink(999.0, 80.0, n=0, k=5.0) == 80.0


def test_team_with_one_game_is_not_absurd(session):
    """A single 130-point game must not project a 130-PPG team."""
    _seed(session, n=6, start_day=1, scored=80, allowed=80)   # league context
    _game(session, gid=f"t{SEASON}-solo", team="TEST_SOLO", opp=T_AWAY,
          date=dt.datetime(SEASON, 6, 2, tzinfo=UTC), scored=130, allowed=60)
    session.commit()

    f = build_team_features(
        team_id="TEST_SOLO", as_of=dt.datetime(SEASON, 6, 20, tzinfo=UTC),
        session=session, season=SEASON,
    )
    assert f.games_played == 1
    assert f.sufficient_data is False          # refuses to be trusted
    assert f.offense_ppg < 110                 # shrunk toward league


def test_no_prior_games_returns_league_average_and_flags(session):
    _seed(session, n=4)
    f = build_team_features(
        team_id="TEST_UNKNOWN", as_of=dt.datetime(SEASON, 6, 20, tzinfo=UTC),
        session=session, season=SEASON,
    )
    assert f.games_played == 0
    assert f.sufficient_data is False
    assert f.offense_ppg > 0          # league average, not a divide-by-zero
    assert "no prior games" in f.notes


# ------------------------------------------------------------------ #
# 3. Form decay and rest
# ------------------------------------------------------------------ #

def test_decayed_mean_weights_recent_games_more():
    # values[0] is most recent
    recent_hot = _decayed_mean([100.0, 80.0, 80.0, 80.0], half_life=5.0)
    plain = sum([100.0, 80.0, 80.0, 80.0]) / 4
    assert recent_hot > plain


def test_decayed_mean_of_constant_series_is_that_constant():
    assert _decayed_mean([80.0] * 6, half_life=5.0) == pytest.approx(80.0)


def test_rest_days(session):
    _game(session, gid=f"t{SEASON}-r", team=T_HOME, opp=T_AWAY,
          date=dt.datetime(SEASON, 6, 10, tzinfo=UTC), scored=80, allowed=75)
    session.commit()
    f = build_team_features(
        team_id=T_HOME, as_of=dt.datetime(SEASON, 6, 13, tzinfo=UTC),
        session=session, season=SEASON,
    )
    assert f.rest_days == pytest.approx(3.0)


# ------------------------------------------------------------------ #
# 4. Pythagorean and record
# ------------------------------------------------------------------ #

@pytest.mark.parametrize("k", [1.0, 5.0, 11.09, 13.91, 20.0])
def test_equal_points_gives_exactly_half_for_any_exponent(k):
    assert pythagorean_win_pct(1000.0, 1000.0, k) == 0.5


def test_pythagorean_monotonic():
    k = 11.09
    assert pythagorean_win_pct(1100.0, 1000.0, k) > 0.5
    assert pythagorean_win_pct(900.0, 1000.0, k) < 0.5


def test_record_excludes_postseason_and_only_counts_regular(session):
    """Regular-season record is the feature, even for a playoff game."""
    _seed(session, n=6, start_day=1, scored=90, allowed=80)  # 6 regular wins
    base = build_team_features(
        team_id=T_HOME, as_of=dt.datetime(SEASON, 7, 1, tzinfo=UTC),
        session=session, season=SEASON,
    )

    # Add a postseason LOSS — record must not move.
    _game(session, gid=f"t{SEASON}-post", team=T_HOME, opp=T_AWAY,
          date=dt.datetime(SEASON, 6, 20, tzinfo=UTC), scored=50, allowed=99,
          season_type=3)
    session.commit()

    after = build_team_features(
        team_id=T_HOME, as_of=dt.datetime(SEASON, 7, 1, tzinfo=UTC),
        session=session, season=SEASON,
    )
    assert after.wins == base.wins
    assert after.losses == base.losses
    assert after.win_pct == base.win_pct
    assert after.record_residual == pytest.approx(base.record_residual)


def test_residual_sign_tracks_over_and_under_performance(session):
    """A team winning more than its point differential implies -> positive."""
    # Big blowout win + two narrow losses => point diff strong, record poor.
    _game(session, gid=f"{SEASON}-a", team="TEST_UNLUCKY", opp=T_AWAY,
          date=dt.datetime(SEASON, 6, 1, tzinfo=UTC), scored=120, allowed=60)
    _game(session, gid=f"{SEASON}-b", team="TEST_UNLUCKY", opp=T_AWAY,
          date=dt.datetime(SEASON, 6, 2, tzinfo=UTC), scored=79, allowed=80)
    _game(session, gid=f"{SEASON}-c", team="TEST_UNLUCKY", opp=T_AWAY,
          date=dt.datetime(SEASON, 6, 3, tzinfo=UTC), scored=79, allowed=80)
    session.commit()

    f = build_team_features(
        team_id="TEST_UNLUCKY", as_of=dt.datetime(SEASON, 6, 10, tzinfo=UTC),
        session=session, season=SEASON,
    )
    # 1-2 record but a large positive point differential -> underperforming.
    assert f.win_pct == pytest.approx(1 / 3)
    assert f.pythagorean_win_pct > f.win_pct
    assert f.record_residual < 0


def test_residual_is_shrunk_toward_zero_on_small_samples(session):
    """A 1-0 team must not register a huge clutch residual."""
    _game(session, gid=f"{SEASON}-one", team="TEST_ONE", opp=T_AWAY,
          date=dt.datetime(SEASON, 6, 1, tzinfo=UTC), scored=81, allowed=80)
    session.commit()
    f = build_team_features(
        team_id="TEST_ONE", as_of=dt.datetime(SEASON, 6, 10, tzinfo=UTC),
        session=session, season=SEASON,
    )
    assert abs(f.record_residual) < 0.2


# ------------------------------------------------------------------ #
# 5. Matchup
# ------------------------------------------------------------------ #

def test_matchup_counts_head_to_head_and_flags_playoffs(session):
    _seed(session, n=4)
    m = build_matchup_features(
        home_team_id=T_HOME, away_team_id=T_AWAY,
        as_of=dt.datetime(SEASON, 7, 1, tzinfo=UTC),
        session=session, season=SEASON, is_playoff_game=True,
    )
    assert m.head_to_head_games == 4
    assert m.is_playoff_game is True
    assert m.home.team_id == T_HOME and m.away.team_id == T_AWAY


def test_league_averages_are_as_of_correct(session):
    _seed(session, n=3, start_day=1, scored=90, allowed=70)
    early = league_averages(
        as_of=dt.datetime(SEASON, 6, 2, tzinfo=UTC), session=session, season=SEASON
    )
    later = league_averages(
        as_of=dt.datetime(SEASON, 6, 30, tzinfo=UTC), session=session, season=SEASON
    )
    assert early.games < later.games


def test_min_games_required_is_configurable(session):
    _seed(session, n=3)
    cfg = WNBATotalsConfig(min_games_required=2)
    f = build_team_features(
        team_id=T_HOME, as_of=dt.datetime(SEASON, 7, 1, tzinfo=UTC),
        session=session, season=SEASON, config=cfg,
    )
    assert f.games_played == 3 and f.sufficient_data is True
