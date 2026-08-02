"""Roster availability: what a team's projected scoring loses when a player sits.

The gap this closes
-------------------
The team model prices season-and-recent-form averages, which describe a roster
that may not be on the floor tonight. The published effect sizes are large
enough to matter — a star ruled out moves a spread 2-5 points and a total 2-4 —
and they land on exactly the games where the line moves most.

The adjustment, and why it is a *delta*
---------------------------------------
Nothing here re-projects a team from scratch: a player-sum projection at WNBA
sample sizes is noisier than the team means it would replace. Instead the team
projection stands and only the change is priced.

    projected minutes m_i  — exponentially decayed over the team's recent
                             games, counting **zero for games she missed**
    per-minute points p_i  — her decayed points divided by her decayed minutes

    baseline = Σ m_i · p_i
    adjusted = Σ_available (m_i · 200/Σ_available m) · p_i
    delta    = adjusted − baseline          (negative when a scorer is out)

Two properties are load-bearing:

1. **Zero-filling missed games prevents double counting.** A player who has
   been out three weeks already has near-zero projected minutes, so the model
   does not deduct her twice — once through the team's depressed recent form
   and again here. A player who played last night and is ruled out tonight
   carries her full minutes and gets the full deduction. That is the whole
   distinction the feature exists to make.

2. **Minutes are conserved, not replaced.** Her minutes are redistributed
   across available players in proportion to their existing share, so no
   replacement-level constant has to be invented. Two biases follow, and they
   point in opposite directions: real bench units are worse than a
   proportional reshuffle of the rotation (understates the drop), while usage
   actually concentrates on the next-best scorers rather than spreading evenly
   (overstates it, most for the biggest stars — A'ja Wilson out prices at ~9
   points here, above the 2-4 the literature puts on a star's effect on a
   total). Which dominates is not known, so `availability_beta` exists to let
   the data scale the whole term rather than a guess.

Point-in-time
-------------
`as_of` is keyword-only with no default, as everywhere else in the feature
layer. The two absence sources are NOT interchangeable and are deliberately
separate functions:

* `absent_from_injury_reports` — point-in-time, tradable, only exists forward
  of the recorder's first run (2026-08-01).
* `absent_from_boxscore` — hindsight, **not tradable**, for screening the
  hypothesis on history.

See docs/math/availability.md.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from core.storage import InjuryReport, PlayerGameLog

#: Team minutes in a regulation WNBA game: 5 players × 40 minutes.
TEAM_MINUTES = 200.0

#: Statuses that mean "will not play". `Day-To-Day` is deliberately excluded —
#: it resolves to active more often than not, and treating it as an absence
#: would fire the adjustment on most of the league most of the time.
OUT_STATUSES = frozenset({"Out", "Suspension", "Injured Reserve"})

#: Below this many projected minutes a player is not a rotation piece and her
#: absence is not news. Roughly the 9th player in a WNBA rotation.
ROTATION_MINUTES = 12.0

#: Team games needed before minute shares mean anything.
MIN_TEAM_GAMES = 3


@dataclass(frozen=True)
class PlayerProjection:
    """One player's expected contribution to tonight, as_of."""

    athlete_id: str
    athlete_name: str | None
    projected_minutes: float
    points_per_minute: float

    @property
    def projected_points(self) -> float:
        return self.projected_minutes * self.points_per_minute

    @property
    def is_rotation(self) -> bool:
        return self.projected_minutes >= ROTATION_MINUTES


@dataclass(frozen=True)
class AvailabilityAdjustment:
    """The scoring delta for one team, plus enough to audit it."""

    team_id: str
    as_of: dt.datetime
    delta_points: float = 0.0
    absent_rotation_players: tuple[str, ...] = field(default_factory=tuple)
    absent_projected_minutes: float = 0.0
    n_team_games: int = 0
    sufficient_data: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_absence(self) -> bool:
        return bool(self.absent_rotation_players)


def _decay_weights(n: int, half_life: float) -> list[float]:
    """Newest first; a game `half_life` games ago counts half."""
    if half_life <= 0:
        return [1.0] + [0.0] * (n - 1)
    return [2.0 ** (-i / half_life) for i in range(n)]


@dataclass(frozen=True)
class PlayerGameRow:
    """One player-game, decoupled from SQLAlchemy so the maths is testable."""

    athlete_id: str
    athlete_name: str | None
    espn_game_id: str
    game_date: dt.datetime
    minutes: int | None
    points: int | None
    did_not_play: bool = False


def projections_from_rows(
    rows: list[PlayerGameRow], *, half_life: float = 5.0, lookback_games: int = 15
) -> tuple[list[PlayerProjection], int]:
    """The actual computation, over one team's rows from games before `as_of`.

    Pure: no database, no clock. Both the query path and the in-memory index
    call this, so a backtest and a live prediction cannot drift apart.
    """
    if not rows:
        return [], 0

    # The team's recent games, newest first — the frame every player is scored
    # against, present or not.
    by_game: dict[str, dt.datetime] = {}
    for r in rows:
        prev = by_game.get(r.espn_game_id)
        if prev is None or r.game_date > prev:
            by_game[r.espn_game_id] = r.game_date
    game_ids = [
        gid for gid, _ in sorted(by_game.items(), key=lambda kv: kv[1], reverse=True)
    ][:lookback_games]
    if not game_ids:
        return [], 0

    rank = {gid: i for i, gid in enumerate(game_ids)}  # 0 = most recent
    weights = _decay_weights(len(game_ids), half_life)

    names: dict[str, str | None] = {}
    # Weighted minutes over ALL team games (missing = 0) vs weighted minutes
    # and points over games she actually played (the per-minute rate).
    wt_minutes: dict[str, float] = {}
    played_minutes: dict[str, float] = {}
    played_points: dict[str, float] = {}

    for r in rows:
        if r.espn_game_id not in rank:
            continue  # older than the lookback window
        w = weights[rank[r.espn_game_id]]
        names.setdefault(r.athlete_id, r.athlete_name)
        minutes = float(r.minutes or 0)
        wt_minutes[r.athlete_id] = wt_minutes.get(r.athlete_id, 0.0) + w * minutes
        if minutes > 0:
            played_minutes[r.athlete_id] = played_minutes.get(r.athlete_id, 0.0) + w * minutes
            played_points[r.athlete_id] = (
                played_points.get(r.athlete_id, 0.0) + w * float(r.points or 0)
            )

    total_w = sum(weights)
    projections: list[PlayerProjection] = []
    for athlete_id, weighted in wt_minutes.items():
        proj_min = weighted / total_w  # zero-filled: absences drag this down
        pm = played_minutes.get(athlete_id, 0.0)
        ppm = (played_points.get(athlete_id, 0.0) / pm) if pm > 0 else 0.0
        projections.append(
            PlayerProjection(
                athlete_id=athlete_id,
                athlete_name=names.get(athlete_id),
                projected_minutes=proj_min,
                points_per_minute=ppm,
            )
        )

    projections.sort(key=lambda p: p.projected_minutes, reverse=True)
    return projections, len(game_ids)


def team_player_projections(
    *,
    team_id: str,
    as_of: dt.datetime,
    session: Session,
    season: int | None = None,
    half_life: float = 5.0,
    lookback_games: int = 15,
) -> tuple[list[PlayerProjection], int]:
    """Projected minutes and per-minute scoring for a team, as_of.

    Returns (projections, n_team_games). Minutes are decayed over the team's
    recent games with **zero filled in for games a player missed**, which is
    what keeps a long-term absentee from being deducted twice.
    """
    conditions = [
        PlayerGameLog.team_id == team_id,
        PlayerGameLog.game_date < as_of,  # <- the no-lookahead guarantee
    ]
    if season is not None:
        conditions.append(PlayerGameLog.season == season)

    rows = [
        PlayerGameRow(
            athlete_id=r.athlete_id,
            athlete_name=r.athlete_name,
            espn_game_id=r.espn_game_id,
            game_date=r.game_date,
            minutes=r.minutes,
            points=r.points,
            did_not_play=r.did_not_play,
        )
        for r in session.execute(
            select(
                PlayerGameLog.athlete_id,
                PlayerGameLog.athlete_name,
                PlayerGameLog.espn_game_id,
                PlayerGameLog.game_date,
                PlayerGameLog.minutes,
                PlayerGameLog.points,
                PlayerGameLog.did_not_play,
            )
            .where(and_(*conditions))
            .order_by(PlayerGameLog.game_date.desc())
            # Enough rows to cover `lookback_games` for a 12-15 player roster.
            .limit(lookback_games * 30)
        ).all()
    ]
    return projections_from_rows(
        rows, half_life=half_life, lookback_games=lookback_games
    )


class PlayerAvailabilityIndex:
    """Every player-game for a season range, held in memory.

    Purely a performance shim, and it exists because the alternative was
    dangerous rather than merely slow: per-game round trips to a remote
    Postgres made the walk-forward loop take hours, and an experiment nobody
    can afford to re-run is an experiment that quietly stops being re-run.

    Point-in-time safety survives the move because the index never answers a
    question without an `as_of` and filters on it in exactly the same
    `game_date < as_of` form the SQL used.
    """

    def __init__(
        self,
        *,
        session: Session,
        start_season: int,
        end_season: int,
        half_life: float = 5.0,
        lookback_games: int = 15,
    ) -> None:
        self.half_life = half_life
        self.lookback_games = lookback_games
        self._by_team: dict[str, list[PlayerGameRow]] = {}
        self._played: dict[tuple[str, str], set[str]] = {}
        self._cache: dict[tuple[str, dt.datetime], tuple[list[PlayerProjection], int]] = {}
        #: team_id -> [(captured_at, athlete_id, status)], oldest first.
        #: Empty unless `load_injury_log` is called, which is the honest state
        #: for any backtest of history: ESPN keeps no injury past.
        self._injuries: dict[str, list[tuple[dt.datetime, str, str]]] = {}

        rows = session.execute(
            select(
                PlayerGameLog.team_id,
                PlayerGameLog.athlete_id,
                PlayerGameLog.athlete_name,
                PlayerGameLog.espn_game_id,
                PlayerGameLog.game_date,
                PlayerGameLog.minutes,
                PlayerGameLog.points,
                PlayerGameLog.did_not_play,
            )
            .where(PlayerGameLog.season >= start_season)
            .where(PlayerGameLog.season <= end_season)
            .order_by(PlayerGameLog.game_date.desc())
        ).all()

        for r in rows:
            row = PlayerGameRow(
                athlete_id=r.athlete_id,
                athlete_name=r.athlete_name,
                espn_game_id=r.espn_game_id,
                game_date=r.game_date,
                minutes=r.minutes,
                points=r.points,
                did_not_play=r.did_not_play,
            )
            self._by_team.setdefault(r.team_id, []).append(row)
            if not row.did_not_play and (row.minutes or 0) > 0:
                self._played.setdefault((r.espn_game_id, r.team_id), set()).add(
                    r.athlete_id
                )

    def load_injury_log(self, *, session: Session) -> None:
        """Pull the injury change log into memory for the `report` arm.

        Small by construction — one row per status *change*, not per poll — so
        the whole history fits comfortably. On history it loads nothing, which
        is the honest answer: ESPN keeps no injury past.
        """
        self._injuries = {}
        rows = session.execute(
            select(
                InjuryReport.team_id,
                InjuryReport.athlete_id,
                InjuryReport.captured_at,
                InjuryReport.status,
            ).order_by(InjuryReport.captured_at)
        ).all()
        for r in rows:
            if r.team_id is None:
                continue
            self._injuries.setdefault(r.team_id, []).append(
                (r.captured_at, r.athlete_id, r.status)
            )

    def absent_from_reports(self, *, team_id: str, as_of: dt.datetime) -> set[str]:
        """Players designated out as of `as_of` — point-in-time, tradable."""
        latest: dict[str, str] = {}
        for captured_at, athlete_id, status in self._injuries.get(team_id, []):
            if captured_at > as_of:
                break  # rows are oldest-first, so nothing later can qualify
            latest[athlete_id] = status
        return {a for a, s in latest.items() if s in OUT_STATUSES}

    def projections(
        self, *, team_id: str, as_of: dt.datetime
    ) -> tuple[list[PlayerProjection], int]:
        key = (team_id, as_of)
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        rows = [r for r in self._by_team.get(team_id, []) if r.game_date < as_of]
        out = projections_from_rows(
            rows, half_life=self.half_life, lookback_games=self.lookback_games
        )
        self._cache[key] = out
        return out

    def played(self, *, espn_game_id: str, team_id: str) -> set[str]:
        return self._played.get((espn_game_id, team_id), set())

    def oracle_absent_ids(
        self, *, espn_game_id: str, team_id: str, as_of: dt.datetime
    ) -> set[str]:
        projections, n_games = self.projections(team_id=team_id, as_of=as_of)
        if n_games < MIN_TEAM_GAMES:
            return set()
        played = self.played(espn_game_id=espn_game_id, team_id=team_id)
        if not played:
            return set()
        return {
            p.athlete_id
            for p in projections
            if p.is_rotation and p.athlete_id not in played
        }


def adjustment_from_projections(
    *,
    team_id: str,
    as_of: dt.datetime,
    projections: list[PlayerProjection],
    n_games: int,
    absent_ids: set[str],
) -> AvailabilityAdjustment:
    """Points the team is expected to gain (+) or lose (−) from tonight's absences.

    Pure. See the module docstring for the arithmetic and its known bias.
    """
    if n_games < MIN_TEAM_GAMES or not projections:
        return AvailabilityAdjustment(
            team_id=team_id,
            as_of=as_of,
            n_team_games=n_games,
            sufficient_data=False,
            notes=(f"only {n_games} prior games with player logs",),
        )

    baseline = sum(p.projected_points for p in projections)
    available = [p for p in projections if p.athlete_id not in absent_ids]
    available_minutes = sum(p.projected_minutes for p in available)

    absent_rotation = tuple(
        p.athlete_name or p.athlete_id
        for p in projections
        if p.athlete_id in absent_ids and p.is_rotation
    )
    absent_minutes = sum(
        p.projected_minutes for p in projections if p.athlete_id in absent_ids
    )

    if not absent_ids or absent_minutes <= 0:
        return AvailabilityAdjustment(
            team_id=team_id, as_of=as_of, delta_points=0.0,
            n_team_games=n_games, sufficient_data=True,
        )

    if available_minutes <= 0:
        # Everyone with minutes is out — not a real lineup, refuse to price it.
        return AvailabilityAdjustment(
            team_id=team_id, as_of=as_of, n_team_games=n_games,
            sufficient_data=False, notes=("no available players with minutes",),
        )

    # Redistribute the vacated minutes proportionally across whoever is left.
    scale = TEAM_MINUTES / available_minutes
    adjusted = sum(p.projected_minutes * scale * p.points_per_minute for p in available)
    # Baseline is rescaled the same way so the delta measures the lineup change,
    # not the fact that projected minutes rarely sum to exactly 200.
    baseline_scaled = baseline * (TEAM_MINUTES / sum(p.projected_minutes for p in projections))

    return AvailabilityAdjustment(
        team_id=team_id,
        as_of=as_of,
        delta_points=adjusted - baseline_scaled,
        absent_rotation_players=absent_rotation,
        absent_projected_minutes=absent_minutes,
        n_team_games=n_games,
        sufficient_data=True,
    )


def availability_adjustment(
    *,
    team_id: str,
    as_of: dt.datetime,
    absent_ids: set[str],
    session: Session,
    season: int | None = None,
    half_life: float = 5.0,
) -> AvailabilityAdjustment:
    """Query-backed convenience wrapper around `adjustment_from_projections`."""
    projections, n_games = team_player_projections(
        team_id=team_id, as_of=as_of, session=session, season=season, half_life=half_life
    )
    return adjustment_from_projections(
        team_id=team_id, as_of=as_of, projections=projections,
        n_games=n_games, absent_ids=absent_ids,
    )


# --------------------------------------------------------------------- #
# The two absence sources. Kept apart on purpose.
# --------------------------------------------------------------------- #


def absent_from_injury_reports(
    *, team_id: str, as_of: dt.datetime, session: Session
) -> set[str]:
    """Players designated out as of `as_of` — **point-in-time, tradable**.

    Reads the change log: the newest row per athlete at or before `as_of`. Only
    correct forward of the recorder's first run, because ESPN publishes no
    injury history.
    """
    rows = session.execute(
        select(InjuryReport.athlete_id, InjuryReport.status)
        .where(InjuryReport.team_id == team_id)
        .where(InjuryReport.captured_at <= as_of)
        .distinct(InjuryReport.athlete_id)
        .order_by(InjuryReport.athlete_id, InjuryReport.captured_at.desc())
    ).all()
    return {r.athlete_id for r in rows if r.status in OUT_STATUSES}


def absent_from_boxscore(
    *, espn_game_id: str, team_id: str, session: Session
) -> set[str]:
    """Players who did not play in this game — **hindsight, NOT tradable**.

    Absence is inferred from the box score two ways: an explicit `didNotPlay`,
    or not being listed at all. The second case is the important one, since
    ESPN usually omits an injured player entirely, and it is why this returns
    the *complement* of who appeared rather than reading a flag.

    Callers get the played set; deciding who "should" have played is the
    caller's job, because it depends on the as_of minute shares.
    """
    rows = session.execute(
        select(PlayerGameLog.athlete_id, PlayerGameLog.minutes, PlayerGameLog.did_not_play)
        .where(PlayerGameLog.espn_game_id == espn_game_id)
        .where(PlayerGameLog.team_id == team_id)
    ).all()
    played = {r.athlete_id for r in rows if not r.did_not_play and (r.minutes or 0) > 0}
    return played


def oracle_absent_ids(
    *,
    espn_game_id: str,
    team_id: str,
    as_of: dt.datetime,
    session: Session,
    season: int | None = None,
    half_life: float = 5.0,
) -> set[str]:
    """Rotation players who were expected to play and did not — hindsight.

    The screening arm's absence source. Anyone with a rotation-sized as_of
    minute share who does not appear in the box score is treated as out.
    """
    projections, n_games = team_player_projections(
        team_id=team_id, as_of=as_of, session=session, season=season, half_life=half_life
    )
    if n_games < MIN_TEAM_GAMES:
        return set()
    played = absent_from_boxscore(
        espn_game_id=espn_game_id, team_id=team_id, session=session
    )
    if not played:
        # No player rows for this game — absence is unknowable, not total.
        return set()
    return {
        p.athlete_id
        for p in projections
        if p.is_rotation and p.athlete_id not in played
    }
