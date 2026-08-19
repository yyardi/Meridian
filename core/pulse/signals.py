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
