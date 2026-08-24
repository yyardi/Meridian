"""Signal set 1-3 over the signal-side archive: clock, pace, shooting.

Pure functions over recorded rows — nothing here reads ESPN, writes a table,
or caches. A signal computed at replay time from rows with
``first_seen_at <= t`` is knowable at ``t`` by construction; materializing
these would freeze today's definitions (and today's bugs) into the archive,
which is the analytics-path lesson inverted: never let two resolutions of
one quantity exist (docs/infra/analytics-path.md, docs/infra/signal-side.md).

The three signals, and what each is for:

* **The exact game clock** — the highest-value signal in the set. PULSE's
  minutes-left today is wall-clock interpolation that saturates late in
  quarters (forcing FV suppression exactly when in-game prices move most)
  and cannot see OT. The box snapshots carry the venue's own clock at ≤10s
  staleness. Integration contract (agreed with the tape's author): when this
  reaches the FV path it sets ``minutes_left_is_estimate=False`` on the
  EXISTING field — never a parallel exact-clock field.
* **Pace decomposition** — possessions (FGA − OREB + TO + 0.44·FTA) and
  points-per-possession per side, so a high-scoring first half can be read
  as "fast" (pace persists) or "hot" (shooting mean-reverts) instead of one
  undifferentiated surprise.
* **Shooting splits** — per team per period from the play stream, the
  efficiency half of the same decomposition plus the 3PT-volume context the
  volatility input wants.

Consumption is PULSE v3 and it is replay-gated (design §d); these functions
existing changes no live behaviour.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

QUARTER_SECONDS = 600.0
OT_SECONDS = 300.0
REGULATION_PERIODS = 4


def _get(row, name):
    if isinstance(row, dict):
        return row.get(name)
    return getattr(row, name, None)


# --------------------------------------------------------------------- #
# Signal 1: the exact clock
# --------------------------------------------------------------------- #


@dataclass(frozen=True)
class ExactClock:
    """The venue's own clock, not an interpolation."""

    period: int
    #: Seconds remaining in the CURRENT period.
    period_seconds_left: float
    #: Minutes left in REGULATION. 0.0 throughout overtime.
    minutes_left: float
    is_overtime: bool
    #: Minutes left in the current OT period (0.0 in regulation).
    ot_minutes_left: float
    #: How stale the reading was when observed (now − first_seen_at), set by
    #: the session loader; 0 for the pure constructor.
    staleness_seconds: float = 0.0


def exact_clock(period: int, clock_seconds: float, *,
                staleness_seconds: float = 0.0) -> ExactClock:
    """Period + venue clock -> minutes remaining, exactly.

    Regulation: full quarters remaining plus the running one. Overtime:
    regulation is over by definition (the game reached 40:00 level), so
    regulation-minutes-left is 0 and the OT clock is reported separately —
    the consumer decides what its model does with OT, this function only
    refuses to pretend OT minutes are regulation minutes.
    """
    clock_seconds = max(float(clock_seconds), 0.0)
    if period <= REGULATION_PERIODS:
        remaining_quarters = REGULATION_PERIODS - period
        seconds = remaining_quarters * QUARTER_SECONDS + min(clock_seconds,
                                                            QUARTER_SECONDS)
        return ExactClock(
            period=period, period_seconds_left=clock_seconds,
            minutes_left=seconds / 60.0, is_overtime=False,
            ot_minutes_left=0.0, staleness_seconds=staleness_seconds,
        )
    return ExactClock(
        period=period, period_seconds_left=clock_seconds,
        minutes_left=0.0, is_overtime=True,
        ot_minutes_left=min(clock_seconds, OT_SECONDS) / 60.0,
        staleness_seconds=staleness_seconds,
    )


def latest_exact_clock(
    session, espn_game_id: str, *, at: dt.datetime | None = None,
) -> ExactClock | None:
    """The newest recorded clock knowable at ``at`` (default: now).

    The point-in-time bound is in the query, not the caller's discipline.
    """
    from sqlalchemy import text

    row = session.execute(text("""
        SELECT period, clock_seconds, first_seen_at
        FROM espn_live_box_snapshots
        WHERE espn_game_id = :g
          AND period IS NOT NULL AND clock_seconds IS NOT NULL
          AND first_seen_at <= coalesce(:at, now())
        ORDER BY first_seen_at DESC LIMIT 1
    """), {"g": espn_game_id, "at": at}).first()
    if row is None:
        return None
    ref = at or dt.datetime.now(dt.timezone.utc)
    return exact_clock(
        int(row.period), float(row.clock_seconds),
        staleness_seconds=max((ref - row.first_seen_at).total_seconds(), 0.0),
    )


# --------------------------------------------------------------------- #
# Signal 2: pace decomposition
# --------------------------------------------------------------------- #


@dataclass(frozen=True)
class TeamPace:
    possessions: float
    points: int
    points_per_possession: float | None


@dataclass(frozen=True)
class PaceDecomposition:
    """Fast vs hot, separated. Rates are per 40 minutes of game clock."""

    elapsed_minutes: float
    home: TeamPace
    away: TeamPace
    #: Mean of the two sides' possessions — the game's pace so far.
    possessions_per_side: float
    pace_per_40: float | None


def possessions(*, fga: int, oreb: int, turnovers: int, fta: int) -> float:
    """The standard estimate: FGA − OREB + TO + 0.44·FTA."""
    return float(fga) - float(oreb) + float(turnovers) + 0.44 * float(fta)


def pace_decomposition(box_row, *, elapsed_minutes: float) -> PaceDecomposition | None:
    """One box snapshot -> the fast/hot split. None when counts are missing.

    ``elapsed_minutes`` comes from the exact clock (signal 1) — game minutes,
    not wall minutes.
    """
    vals = {}
    for side in ("home", "away"):
        for f in ("fga", "oreb", "turnovers", "fta", "score"):
            v = _get(box_row, f"{side}_{f}")
            if v is None:
                return None
            vals[f"{side}_{f}"] = int(v)

    def team(side: str) -> TeamPace:
        poss = possessions(
            fga=vals[f"{side}_fga"], oreb=vals[f"{side}_oreb"],
            turnovers=vals[f"{side}_turnovers"], fta=vals[f"{side}_fta"])
        pts = vals[f"{side}_score"]
        return TeamPace(
            possessions=poss, points=pts,
            points_per_possession=pts / poss if poss > 0 else None,
        )

    home, away = team("home"), team("away")
    per_side = (home.possessions + away.possessions) / 2.0
    return PaceDecomposition(
        elapsed_minutes=elapsed_minutes, home=home, away=away,
        possessions_per_side=per_side,
        pace_per_40=(per_side * 40.0 / elapsed_minutes
                     if elapsed_minutes > 0 else None),
    )


# --------------------------------------------------------------------- #
# Signal 3: shooting splits by period
# --------------------------------------------------------------------- #


@dataclass
class ShootingSplit:
    fgm: int = 0
    fga: int = 0
    tpm: int = 0
    tpa: int = 0
    ftm: int = 0
    fta: int = 0

    @property
    def fg_pct(self) -> float | None:
        return self.fgm / self.fga if self.fga else None

    @property
    def tp_pct(self) -> float | None:
        return self.tpm / self.tpa if self.tpa else None


def shooting_splits(plays) -> dict[tuple[str, int], ShootingSplit]:
    """Play rows -> {(team_id, period): split}.

    Free throws (``points_attempted == 1``) are ALWAYS excluded from FG
    counts — the payload marks them ``shootingPlay=True``, and folding them
    in silently inflates FG% (measured on the probe game: 28 FT plays).
    A make is ``scoring_play``; a three is ``points_attempted == 3``.
    """
    out: dict[tuple[str, int], ShootingSplit] = defaultdict(ShootingSplit)
    for p in plays:
        if not _get(p, "shooting_play"):
            continue
        team = _get(p, "team_id")
        period = _get(p, "period")
        attempted = _get(p, "points_attempted")
        if team is None or period is None or attempted is None:
            continue
        split = out[(str(team), int(period))]
        made = bool(_get(p, "scoring_play"))
        if attempted == 1:
            split.fta += 1
            split.ftm += int(made)
            continue
        split.fga += 1
        split.fgm += int(made)
        if attempted == 3:
            split.tpa += 1
            split.tpm += int(made)
    return dict(out)


def plays_before(session, espn_game_id: str, *, at: dt.datetime | None = None):
    """Play rows knowable at ``at`` — the point-in-time bound in the query."""
    from sqlalchemy import text

    return session.execute(text("""
        SELECT play_id, sequence, period, clock_seconds, team_id,
               shooting_play, scoring_play, points_attempted, score_value,
               home_score, away_score, type_text,
               athlete_id_1, athlete_id_2, first_seen_at, wallclock
        FROM espn_live_plays
        WHERE espn_game_id = :g
          AND first_seen_at <= coalesce(:at, now())
        ORDER BY sequence
    """), {"g": espn_game_id, "at": at}).all()


# --------------------------------------------------------------------- #
# Live consumption (the v3 regime): the venue clock, and only the clock
# --------------------------------------------------------------------- #

#: ET offset for the join's date check (in-season EDT). Restated from the
#: recorder rather than imported — importing the recorder module would drag
#: its HTTP client into the engine's import graph for one constant.
_ET_OFFSET = dt.timedelta(hours=-4)


def resolve_espn_game(session, event_slug: str) -> str | None:
    """Unambiguous espn_game_id for an event, or None — the replay eval's
    registered join (team abbrevs via team_mapping + date within a day),
    applied live. Ambiguity refuses; the engine then prices v1.
    """
    from sqlalchemy import text as _text

    from core.pulse.team_form import event_team_abbrevs
    from core.team_mapping import parse_event_slug

    abbrevs = event_team_abbrevs(event_slug)
    parsed = parse_event_slug(event_slug)
    if abbrevs is None or parsed is None:
        return None
    abbrev_of = dict(session.execute(_text(
        "SELECT DISTINCT team_id, team_abbrev FROM team_game_logs")).all())
    games = session.execute(_text("""
        SELECT DISTINCT ON (espn_game_id)
               espn_game_id, home_team_id, away_team_id,
               min(first_seen_at) OVER (PARTITION BY espn_game_id) AS first_seen
        FROM espn_live_box_snapshots
        WHERE first_seen_at > now() - interval '24 hours'
          AND home_team_id IS NOT NULL AND away_team_id IS NOT NULL
        ORDER BY espn_game_id, first_seen_at DESC
    """)).all()
    matches = [
        g.espn_game_id for g in games
        if {abbrev_of.get(g.home_team_id), abbrev_of.get(g.away_team_id)}
        == {abbrevs[0], abbrevs[1]}
        and abs(((g.first_seen + _ET_OFFSET).date()
                 - parsed.local_date).days) <= 1
    ]
    return matches[0] if len(matches) == 1 else None


def latest_venue_clocks(
    session, espn_game_ids: list[str], *, max_staleness_seconds: float = 60.0,
) -> dict[str, ExactClock]:
    """Freshest venue clock per game, one query — the engine's per-cycle
    read. A game with no reading fresher than the staleness bound is simply
    absent, and the caller falls back to the estimator (row labelled v1)."""
    from sqlalchemy import text as _text

    if not espn_game_ids:
        return {}
    rows = session.execute(_text("""
        SELECT DISTINCT ON (espn_game_id)
               espn_game_id, period, clock_seconds, first_seen_at
        FROM espn_live_box_snapshots
        WHERE espn_game_id = ANY(:ids)
          AND period IS NOT NULL AND clock_seconds IS NOT NULL
          AND first_seen_at > now() - make_interval(secs => :age)
        ORDER BY espn_game_id, first_seen_at DESC
    """), {"ids": espn_game_ids, "age": max_staleness_seconds}).all()
    now = dt.datetime.now(dt.timezone.utc)
    return {
        r.espn_game_id: exact_clock(
            int(r.period), float(r.clock_seconds),
            staleness_seconds=max((now - r.first_seen_at).total_seconds(), 0.0))
        for r in rows
    }


# --------------------------------------------------------------------- #
# The v4 bundle (docs/math/pulse-v4-bundle.md) — pure functions
# --------------------------------------------------------------------- #

#: Shrink priors, REGISTERED a priori (not fits): pace is believed after
#: about a quarter of evidence; efficiency is distrusted for about three.
K_PACE_MINUTES = 10.0
K_EFF_MINUTES = 30.0
#: Availability flags widen the margin sigma by this factor while active.
#: One a priori constant for all flags; direction deliberately unmodelled.
AVAILABILITY_SIGMA_FACTOR = 1.15
#: Foul-trouble thresholds: any starter at PF >= 4 before Q4, >= 5 in Q4.
FOUL_TROUBLE_PRE_Q4 = 4
FOUL_TROUBLE_Q4 = 5


def shrink(observed: float, prior: float, *, elapsed_minutes: float,
           k_minutes: float) -> float:
    """Evidence-weighted blend: (elapsed·obs + k·prior) / (elapsed + k)."""
    denom = elapsed_minutes + k_minutes
    if denom <= 0:
        return prior
    return (elapsed_minutes * observed + k_minutes * prior) / denom


def projected_total_v4(
    *,
    total_so_far: int,
    possessions_so_far: float,        # per SIDE (the pace_decomposition mean)
    elapsed_minutes: float,
    minutes_left: float,
    pregame_mu: float,
    poss_rate_expected: float,        # possessions per side per minute
) -> float | None:
    """The registered pace/efficiency-decomposed projection.

    ppp_exp is derived from the pregame anchor so that at elapsed 0 the
    projection equals mu exactly — the anchor is preserved at tip-off and
    evidence moves it only as evidence accrues.
    """
    if elapsed_minutes <= 0 or possessions_so_far <= 0 or poss_rate_expected <= 0:
        return None
    ppp_expected = pregame_mu / (2.0 * poss_rate_expected * 40.0)
    poss_rate_obs = possessions_so_far / elapsed_minutes
    ppp_obs = total_so_far / (2.0 * possessions_so_far)
    pace_blend = shrink(poss_rate_obs, poss_rate_expected,
                        elapsed_minutes=elapsed_minutes, k_minutes=K_PACE_MINUTES)
    ppp_blend = shrink(ppp_obs, ppp_expected,
                       elapsed_minutes=elapsed_minutes, k_minutes=K_EFF_MINUTES)
    return total_so_far + minutes_left * 2.0 * pace_blend * ppp_blend


@dataclass(frozen=True)
class AvailabilityFlags:
    """Uncertainty flags from the player box + substitution stream."""

    foul_trouble: bool
    star_off: bool
    ejected: bool

    @property
    def any_active(self) -> bool:
        return self.foul_trouble or self.star_off or self.ejected

    @property
    def sigma_factor(self) -> float:
        return AVAILABILITY_SIGMA_FACTOR if self.any_active else 1.0


def on_floor(starters: set[str], sub_plays) -> set[str]:
    """Current on-floor athlete ids from the substitution stream.

    Substitution plays carry athlete_id_1 = entering, athlete_id_2 =
    leaving (the recorded payload's own order: 'X enters the game for Y').
    Plays must be time-ordered; unknown ids are handled gracefully because
    ESPN occasionally reports garbage substitutions.
    """
    floor = set(starters)
    for p in sub_plays:
        if _get(p, "type_text") != "Substitution":
            continue
        entering = _get(p, "athlete_id_1")
        leaving = _get(p, "athlete_id_2")
        if leaving is not None:
            floor.discard(str(leaving))
        if entering is not None:
            floor.add(str(entering))
    return floor


def availability_flags(
    *,
    player_rows,                      # latest player snapshot per athlete
    sub_plays,                        # time-ordered Substitution plays
    period: int,
    team_id: str | None = None,       # restrict to one team, or both when None
) -> AvailabilityFlags:
    """The registered flags: foul trouble, star-off (top-minutes starter not
    on the floor in Q4+), and ejection. Pure over recorded rows."""
    rows = [r for r in player_rows
            if team_id is None or str(_get(r, "team_id")) == str(team_id)]
    threshold = FOUL_TROUBLE_Q4 if period >= 4 else FOUL_TROUBLE_PRE_Q4
    foul_trouble = any(
        bool(_get(r, "starter")) and (_get(r, "fouls") or 0) >= threshold
        for r in rows)
    ejected = any(bool(_get(r, "ejected")) for r in rows)

    star_off = False
    if period >= 4:
        starters = [r for r in rows if bool(_get(r, "starter"))]
        if starters:
            star = max(starters, key=lambda r: (_get(r, "minutes") or 0))
            star_id = str(_get(star, "athlete_id"))
            all_starter_ids = {
                str(_get(r, "athlete_id")) for r in player_rows
                if bool(_get(r, "starter"))}
            floor = on_floor(all_starter_ids, sub_plays)
            star_off = star_id not in floor
    return AvailabilityFlags(foul_trouble=foul_trouble, star_off=star_off,
                             ejected=ejected)


def scoring_run(plays, *, window: int = 12) -> int:
    """Annotation only (the fade family is closed): the current run — net
    points over the last `window` scoring plays, positive = home."""
    scoring = [p for p in plays if _get(p, "scoring_play")]
    if len(scoring) < 2:
        return 0
    recent = scoring[-window:]
    first, last = recent[0], recent[-1]
    dh = (_get(last, "home_score") or 0) - (_get(first, "home_score") or 0)
    da = (_get(last, "away_score") or 0) - (_get(first, "away_score") or 0)
    return int(dh - da)


def latest_box_states(
    session, espn_game_ids: list[str], *, max_staleness_seconds: float = 60.0,
) -> dict[str, dict]:
    """Freshest box row per game WITH possession counts — the v4 engine's
    per-cycle read (a superset of the clock read; same table, same row)."""
    from sqlalchemy import text as _text

    if not espn_game_ids:
        return {}
    rows = session.execute(_text("""
        SELECT DISTINCT ON (espn_game_id)
               espn_game_id, period, clock_seconds, first_seen_at,
               home_score, away_score,
               home_fga, home_oreb, home_turnovers, home_fta,
               away_fga, away_oreb, away_turnovers, away_fta
        FROM espn_live_box_snapshots
        WHERE espn_game_id = ANY(:ids)
          AND period IS NOT NULL AND clock_seconds IS NOT NULL
          AND first_seen_at > now() - make_interval(secs => :age)
        ORDER BY espn_game_id, first_seen_at DESC
    """), {"ids": espn_game_ids, "age": max_staleness_seconds}).all()
    now = dt.datetime.now(dt.timezone.utc)
    out: dict[str, dict] = {}
    for r in rows:
        clock = exact_clock(
            int(r.period), float(r.clock_seconds),
            staleness_seconds=max((now - r.first_seen_at).total_seconds(), 0.0))
        counts_ok = None not in (r.home_fga, r.home_oreb, r.home_turnovers,
                                 r.home_fta, r.away_fga, r.away_oreb,
                                 r.away_turnovers, r.away_fta)
        poss = None
        if counts_ok:
            poss = (possessions(fga=r.home_fga, oreb=r.home_oreb,
                                turnovers=r.home_turnovers, fta=r.home_fta)
                    + possessions(fga=r.away_fga, oreb=r.away_oreb,
                                  turnovers=r.away_turnovers, fta=r.away_fta)
                    ) / 2.0
        out[r.espn_game_id] = {
            "clock": clock,
            "possessions_per_side": poss,
        }
    return out


def latest_player_rows(
    session, espn_game_ids: list[str], *, max_staleness_seconds: float = 180.0,
) -> dict[str, list]:
    """Latest player-box line per athlete per game. 180s bound: the recorder
    writes players on a 60s cadence, so 3 missed writes = stale."""
    from sqlalchemy import text as _text

    if not espn_game_ids:
        return {}
    rows = session.execute(_text("""
        SELECT DISTINCT ON (espn_game_id, athlete_id)
               espn_game_id, athlete_id, team_id, minutes, fouls, starter,
               ejected, first_seen_at
        FROM espn_live_player_snapshots
        WHERE espn_game_id = ANY(:ids)
          AND first_seen_at > now() - make_interval(secs => :age)
        ORDER BY espn_game_id, athlete_id, first_seen_at DESC
    """), {"ids": espn_game_ids, "age": max_staleness_seconds}).all()
    out: dict[str, list] = {}
    for r in rows:
        out.setdefault(r.espn_game_id, []).append(r)
    return out


def substitution_plays(session, espn_game_id: str) -> list:
    """The game's Substitution plays, time-ordered — on-floor ground truth."""
    from sqlalchemy import text as _text

    return session.execute(_text("""
        SELECT sequence, type_text, athlete_id_1, athlete_id_2
        FROM espn_live_plays
        WHERE espn_game_id = :g AND type_text = 'Substitution'
        ORDER BY sequence
    """), {"g": espn_game_id}).all()
