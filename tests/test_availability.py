"""Roster-availability tests.

The two that matter most:

* **Double-count guard.** A player who has been out for weeks must produce
  almost no adjustment, because the team's recent form already prices her
  absence. Deducting her again is the obvious way for this feature to lose
  money while looking sophisticated.
* **Point-in-time.** An injury designation recorded after `as_of` must be
  invisible, for the same reason every other feature filters on `as_of`.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import delete

from core.storage import InjuryReport, PlayerGameLog, get_engine, get_sessionmaker
from strategies.wnba_totals.model.availability import (
    MIN_TEAM_GAMES,
    TEAM_MINUTES,
    PlayerAvailabilityIndex,
    PlayerGameRow,
    absent_from_injury_reports,
    adjustment_from_projections,
    projections_from_rows,
)

UTC = dt.timezone.utc
SEASON = 1999  # fictional season, cannot collide with real data
TEAM = "TEST_AVAIL_TEAM"


def _rows(
    *,
    n_games: int = 10,
    minutes_by_player: dict[str, list[int]] | None = None,
    points_by_player: dict[str, list[int]] | None = None,
    start_day: int = 1,
) -> list[PlayerGameRow]:
    """Build player-game rows; index 0 of each list is the OLDEST game."""
    minutes_by_player = minutes_by_player or {}
    points_by_player = points_by_player or {}
    out: list[PlayerGameRow] = []
    for i in range(n_games):
        date = dt.datetime(SEASON, 6, start_day + i, tzinfo=UTC)
        for athlete_id, mins in minutes_by_player.items():
            m = mins[i]
            pts = points_by_player.get(athlete_id, [0] * n_games)[i]
            out.append(
                PlayerGameRow(
                    athlete_id=athlete_id,
                    athlete_name=f"P{athlete_id}",
                    espn_game_id=f"g{SEASON}-{i}",
                    game_date=date,
                    minutes=m,
                    points=pts,
                    did_not_play=(m == 0),
                )
            )
    return out


def _even_team(n_games: int = 10) -> list[PlayerGameRow]:
    """Five players, 40 minutes each, 10 points each — a flat 200-minute team."""
    return _rows(
        n_games=n_games,
        minutes_by_player={str(i): [40] * n_games for i in range(1, 6)},
        points_by_player={str(i): [10] * n_games for i in range(1, 6)},
    )


# ------------------------------------------------------------------ #
# 1. Minute shares
# ------------------------------------------------------------------ #


def test_minutes_sum_to_a_full_team_game():
    projections, n = projections_from_rows(_even_team())
    assert n == 10
    assert sum(p.projected_minutes for p in projections) == pytest.approx(TEAM_MINUTES)


def test_per_minute_rate_uses_played_games_only():
    """A player who sat out three games still scores at her own rate."""
    rows = _rows(
        n_games=6,
        minutes_by_player={"1": [30, 30, 30, 0, 0, 0]},
        points_by_player={"1": [15, 15, 15, 0, 0, 0]},
    )
    projections, _ = projections_from_rows(rows)
    (player,) = projections
    assert player.points_per_minute == pytest.approx(0.5)
    # But her projected minutes are dragged down by the games she missed.
    assert player.projected_minutes < 30


def test_recent_games_weigh_more():
    """Same total minutes, different order — recency must change the answer."""
    rising = _rows(n_games=6, minutes_by_player={"1": [10, 10, 10, 30, 30, 30]})
    falling = _rows(n_games=6, minutes_by_player={"1": [30, 30, 30, 10, 10, 10]})
    (up,), _ = projections_from_rows(rising)
    (down,), _ = projections_from_rows(falling)
    assert up.projected_minutes > down.projected_minutes


# ------------------------------------------------------------------ #
# 2. The adjustment
# ------------------------------------------------------------------ #


def test_no_absences_is_exactly_zero():
    projections, n = projections_from_rows(_even_team())
    adj = adjustment_from_projections(
        team_id=TEAM, as_of=dt.datetime(SEASON, 7, 1, tzinfo=UTC),
        projections=projections, n_games=n, absent_ids=set(),
    )
    assert adj.delta_points == 0.0
    assert adj.sufficient_data
    assert not adj.has_absence


def test_losing_an_above_average_scorer_lowers_the_projection():
    rows = _rows(
        n_games=8,
        minutes_by_player={"star": [30] * 8, "a": [30] * 8, "b": [30] * 8},
        # The star scores at 0.6/min, the others at 0.2/min.
        points_by_player={"star": [18] * 8, "a": [6] * 8, "b": [6] * 8},
    )
    projections, n = projections_from_rows(rows)
    adj = adjustment_from_projections(
        team_id=TEAM, as_of=dt.datetime(SEASON, 7, 1, tzinfo=UTC),
        projections=projections, n_games=n, absent_ids={"star"},
    )
    assert adj.delta_points < 0
    assert adj.has_absence
    assert "Pstar" in adj.absent_rotation_players


def test_losing_an_interchangeable_player_barely_moves_it():
    """Everyone identical: who sits cannot matter."""
    projections, n = projections_from_rows(_even_team())
    adj = adjustment_from_projections(
        team_id=TEAM, as_of=dt.datetime(SEASON, 7, 1, tzinfo=UTC),
        projections=projections, n_games=n, absent_ids={"1"},
    )
    assert adj.delta_points == pytest.approx(0.0, abs=1e-9)


def test_long_term_absentee_is_not_deducted_twice():
    """The double-count guard.

    A star who has already missed the recent stretch is priced into the team's
    recent form. Her projected minutes have decayed toward zero, so ruling her
    out again must shrink toward a no-op — otherwise the model deducts her
    twice and systematically under-projects.

    The decay is graded, not a cliff, which is the intended behaviour: a player
    out one game is still mostly "expected to play", one out for a month is
    not. So the assertion is monotone shrinkage that keeps going with the
    length of the absence.
    """
    n_games = 15
    as_of = dt.datetime(SEASON, 7, 1, tzinfo=UTC)

    def deduction(games_missed: int) -> float:
        played = n_games - games_missed
        rows = _rows(
            n_games=n_games,
            minutes_by_player={
                "star": [34] * played + [0] * games_missed,
                "a": [33] * n_games,
                "b": [33] * n_games,
            },
            points_by_player={
                "star": [20] * played + [0] * games_missed,
                "a": [8] * n_games,
                "b": [8] * n_games,
            },
        )
        projections, n = projections_from_rows(rows)
        return adjustment_from_projections(
            team_id=TEAM, as_of=as_of, projections=projections, n_games=n,
            absent_ids={"star"},
        ).delta_points

    fresh, short, long = deduction(0), deduction(5), deduction(12)

    assert fresh < 0
    # Strictly shrinking toward zero as the absence lengthens.
    assert fresh < short < long <= 0
    # Twelve games out leaves only the tail of the decay window, so the
    # remaining deduction is a small fraction of the full one.
    assert abs(long) < 0.15 * abs(fresh)
    # And a player absent for the whole window is priced entirely by the
    # team's own form: no second deduction at all.
    assert deduction(n_games) == 0.0


def test_too_few_games_refuses_to_price():
    rows = _even_team(n_games=MIN_TEAM_GAMES - 1)
    projections, n = projections_from_rows(rows)
    adj = adjustment_from_projections(
        team_id=TEAM, as_of=dt.datetime(SEASON, 7, 1, tzinfo=UTC),
        projections=projections, n_games=n, absent_ids={"1"},
    )
    assert not adj.sufficient_data
    assert adj.delta_points == 0.0


# ------------------------------------------------------------------ #
# 3. Point-in-time (database)
# ------------------------------------------------------------------ #


@pytest.fixture
def session():
    Session = get_sessionmaker(get_engine())
    with Session() as s:
        s.execute(delete(PlayerGameLog).where(PlayerGameLog.season == SEASON))
        s.execute(delete(InjuryReport).where(InjuryReport.team_id == TEAM))
        s.commit()
        yield s
        s.rollback()
        s.execute(delete(PlayerGameLog).where(PlayerGameLog.season == SEASON))
        s.execute(delete(InjuryReport).where(InjuryReport.team_id == TEAM))
        s.commit()


def _injury(session, *, athlete_id, status, captured_at):
    session.add(
        InjuryReport(
            captured_at=captured_at, source="test", team_id=TEAM,
            athlete_id=athlete_id, athlete_name=f"P{athlete_id}", status=status,
        )
    )


def test_injury_status_recorded_later_is_invisible(session):
    """The no-lookahead rule, applied to injuries."""
    early = dt.datetime(SEASON, 6, 1, tzinfo=UTC)
    late = dt.datetime(SEASON, 6, 10, tzinfo=UTC)
    _injury(session, athlete_id="1", status="Out", captured_at=late)
    session.commit()

    assert absent_from_injury_reports(team_id=TEAM, as_of=early, session=session) == set()
    assert absent_from_injury_reports(team_id=TEAM, as_of=late, session=session) == {"1"}


def test_latest_status_wins_and_cleared_removes(session):
    t1 = dt.datetime(SEASON, 6, 1, tzinfo=UTC)
    t2 = dt.datetime(SEASON, 6, 5, tzinfo=UTC)
    _injury(session, athlete_id="1", status="Out", captured_at=t1)
    _injury(session, athlete_id="1", status="Cleared", captured_at=t2)
    session.commit()

    mid = dt.datetime(SEASON, 6, 3, tzinfo=UTC)
    after = dt.datetime(SEASON, 6, 7, tzinfo=UTC)
    assert absent_from_injury_reports(team_id=TEAM, as_of=mid, session=session) == {"1"}
    assert absent_from_injury_reports(team_id=TEAM, as_of=after, session=session) == set()


def test_day_to_day_is_not_treated_as_out(session):
    t = dt.datetime(SEASON, 6, 1, tzinfo=UTC)
    _injury(session, athlete_id="1", status="Day-To-Day", captured_at=t)
    session.commit()
    after = dt.datetime(SEASON, 6, 2, tzinfo=UTC)
    assert absent_from_injury_reports(team_id=TEAM, as_of=after, session=session) == set()


def test_index_matches_the_query_path(session):
    """The in-memory index is a speed shim; it must not change any answer."""
    for i in range(6):
        for athlete_id, mins, pts in (("1", 34, 20), ("2", 33, 8), ("3", 33, 8)):
            session.add(
                PlayerGameLog(
                    espn_game_id=f"gi{SEASON}-{i}",
                    game_date=dt.datetime(SEASON, 6, 1 + i, tzinfo=UTC),
                    season=SEASON, season_type=2, team_id=TEAM,
                    athlete_id=athlete_id, athlete_name=f"P{athlete_id}",
                    starter=True, did_not_play=False, minutes=mins, points=pts,
                )
            )
    session.commit()

    as_of = dt.datetime(SEASON, 7, 1, tzinfo=UTC)
    index = PlayerAvailabilityIndex(
        session=session, start_season=SEASON, end_season=SEASON
    )
    from strategies.wnba_totals.model.availability import team_player_projections

    queried, n_q = team_player_projections(
        team_id=TEAM, as_of=as_of, session=session, season=SEASON
    )
    indexed, n_i = index.projections(team_id=TEAM, as_of=as_of)

    assert n_q == n_i == 6
    assert [(p.athlete_id, round(p.projected_minutes, 6)) for p in queried] == [
        (p.athlete_id, round(p.projected_minutes, 6)) for p in indexed
    ]


def test_index_injury_lookup_matches_the_query_path(session):
    """The index's point-in-time injury read must agree with the SQL one."""
    t1 = dt.datetime(SEASON, 6, 1, tzinfo=UTC)
    t2 = dt.datetime(SEASON, 6, 5, tzinfo=UTC)
    _injury(session, athlete_id="1", status="Out", captured_at=t1)
    _injury(session, athlete_id="2", status="Out", captured_at=t1)
    _injury(session, athlete_id="1", status="Cleared", captured_at=t2)
    session.commit()

    index = PlayerAvailabilityIndex(
        session=session, start_season=SEASON, end_season=SEASON
    )
    # Without the log loaded the index reports nobody out — the honest state
    # for a backtest of history, where no injury data exists.
    assert index.absent_from_reports(team_id=TEAM, as_of=t2) == set()

    index.load_injury_log(session=session)
    for as_of in (
        dt.datetime(SEASON, 6, 3, tzinfo=UTC),
        dt.datetime(SEASON, 6, 7, tzinfo=UTC),
    ):
        assert index.absent_from_reports(
            team_id=TEAM, as_of=as_of
        ) == absent_from_injury_reports(team_id=TEAM, as_of=as_of, session=session)


def test_index_respects_as_of(session):
    for i in range(6):
        session.add(
            PlayerGameLog(
                espn_game_id=f"ga{SEASON}-{i}",
                game_date=dt.datetime(SEASON, 6, 1 + i, tzinfo=UTC),
                season=SEASON, season_type=2, team_id=TEAM,
                athlete_id="1", athlete_name="P1",
                starter=True, did_not_play=False, minutes=30, points=15,
            )
        )
    session.commit()

    index = PlayerAvailabilityIndex(
        session=session, start_season=SEASON, end_season=SEASON
    )
    _, n_early = index.projections(
        team_id=TEAM, as_of=dt.datetime(SEASON, 6, 4, tzinfo=UTC)
    )
    _, n_late = index.projections(
        team_id=TEAM, as_of=dt.datetime(SEASON, 7, 1, tzinfo=UTC)
    )
    assert n_early == 3
    assert n_late == 6
