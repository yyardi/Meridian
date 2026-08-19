"""Storage for the signal side: point-in-time ESPN live game observations.

Models live beside their only writer (`core/feeds/espn_live_recorder.py`),
the quote/pulse precedent. Design: docs/infra/signal-side.md.

The one non-negotiable, stated once and enforced everywhere
-----------------------------------------------------------
**`first_seen_at` is the instant OUR poller observed the row, and it is the
only knowability stamp.** ESPN's own per-play ``wallclock`` is stored beside
it as data — the (wallclock, first_seen_at) pair makes feed lag a measurable
distribution — but a replay may use a row iff ``first_seen_at <= t``, full
stop. Trusting ESPN's stamp for knowability would smuggle lookahead into
every future replay through whatever batching lag the feed had that night.

Write shapes
------------
* Plays and win-probability rows are append-only: a play never updates, so
  re-observing one is ``ON CONFLICT DO NOTHING`` — idempotent across poller
  restarts and overlapping polls.
* Box snapshots are one row per poll per game (that cadence IS the data).
* Player snapshots are the same at a slower cadence.
* Injury observations are unique per (game, athlete, status): "on change
  only" achieved structurally rather than by remembered state.

Nothing here is derived: parsed columns are transcriptions of the payload,
and every signal is a pure function computed at read time
(`core/pulse/signals.py`) so a signal bug can never corrupt the archive.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.storage.base import Base


class EspnLivePlay(Base):
    """One play, append-only, keyed by ESPN's own play id."""

    __tablename__ = "espn_live_plays"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    #: When OUR poller first observed this play — the knowability stamp.
    first_seen_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)

    espn_game_id: Mapped[str] = mapped_column(String(32), nullable=False)
    play_id: Mapped[str] = mapped_column(String(32), nullable=False)
    sequence: Mapped[int | None] = mapped_column(Integer)
    period: Mapped[int | None] = mapped_column(SmallInteger)
    #: Game clock at the play, in seconds remaining in the period.
    clock_seconds: Mapped[Decimal | None] = mapped_column(Numeric(6, 1))
    #: ESPN's own UTC stamp for the play. DATA, never the knowability stamp.
    wallclock: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    type_id: Mapped[str | None] = mapped_column(String(16))
    type_text: Mapped[str | None] = mapped_column(String(80))
    team_id: Mapped[str | None] = mapped_column(String(16))
    #: Up to two participants observed (shooter/assister, sub in/out).
    athlete_id_1: Mapped[str | None] = mapped_column(String(16))
    athlete_id_2: Mapped[str | None] = mapped_column(String(16))
    shooting_play: Mapped[bool | None] = mapped_column(Boolean)
    scoring_play: Mapped[bool | None] = mapped_column(Boolean)
    points_attempted: Mapped[int | None] = mapped_column(SmallInteger)
    score_value: Mapped[int | None] = mapped_column(SmallInteger)
    home_score: Mapped[int | None] = mapped_column(SmallInteger)
    away_score: Mapped[int | None] = mapped_column(SmallInteger)
    text: Mapped[str | None] = mapped_column(String(300))
    raw: Mapped[dict | None] = mapped_column(JSONB)

    __table_args__ = (
        UniqueConstraint("play_id", name="uq_elp_play_id"),
        Index("ix_elp_game", "espn_game_id"),
        Index("ix_elp_game_seq", "espn_game_id", "sequence"),
        Index("ix_elp_first_seen", "first_seen_at"),
    )


class EspnLiveBoxSnapshot(Base):
    """One poll's team-level box + the game state. One row per poll per game.

    Team stats are transcribed into one JSONB dict per side (the payload's
    own stat names, values as strings exactly as served) plus first-class
    columns for the pace/efficiency-critical counts, parsed from the
    made-attempted pairs.
    """

    __tablename__ = "espn_live_box_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    first_seen_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)

    espn_game_id: Mapped[str] = mapped_column(String(32), nullable=False)
    #: STATUS_IN_PROGRESS etc. — state 'pre' | 'in' | 'post'.
    game_state: Mapped[str | None] = mapped_column(String(8))
    #: From the summary header's NESTED spelling (`season: {"type": 2}`) —
    #: the scoreboard uses the same nesting and the flat `seasonType` does
    #: not exist there, which is exactly how PR #25's 18-day outage started.
    #: Recorded so consumers can exclude preseason without re-fetching.
    season_type: Mapped[int | None] = mapped_column(SmallInteger)
    period: Mapped[int | None] = mapped_column(SmallInteger)
    #: Seconds remaining in the period, from the header status when the venue
    #: serves one live, else from the newest play. NULL = neither available.
    clock_seconds: Mapped[Decimal | None] = mapped_column(Numeric(6, 1))
    #: Where the clock came from: 'header' | 'play' — the live checklist's
    #: question 2 made queryable.
    clock_source: Mapped[str | None] = mapped_column(String(8))

    home_team_id: Mapped[str | None] = mapped_column(String(16))
    away_team_id: Mapped[str | None] = mapped_column(String(16))
    home_score: Mapped[int | None] = mapped_column(SmallInteger)
    away_score: Mapped[int | None] = mapped_column(SmallInteger)

    # Pace/efficiency-critical counts, parsed per side.
    home_fgm: Mapped[int | None] = mapped_column(SmallInteger)
    home_fga: Mapped[int | None] = mapped_column(SmallInteger)
    home_tpm: Mapped[int | None] = mapped_column(SmallInteger)
    home_tpa: Mapped[int | None] = mapped_column(SmallInteger)
    home_ftm: Mapped[int | None] = mapped_column(SmallInteger)
    home_fta: Mapped[int | None] = mapped_column(SmallInteger)
    home_oreb: Mapped[int | None] = mapped_column(SmallInteger)
    home_turnovers: Mapped[int | None] = mapped_column(SmallInteger)
    away_fgm: Mapped[int | None] = mapped_column(SmallInteger)
    away_fga: Mapped[int | None] = mapped_column(SmallInteger)
    away_tpm: Mapped[int | None] = mapped_column(SmallInteger)
    away_tpa: Mapped[int | None] = mapped_column(SmallInteger)
    away_ftm: Mapped[int | None] = mapped_column(SmallInteger)
    away_fta: Mapped[int | None] = mapped_column(SmallInteger)
    away_oreb: Mapped[int | None] = mapped_column(SmallInteger)
    away_turnovers: Mapped[int | None] = mapped_column(SmallInteger)

    home_stats: Mapped[dict | None] = mapped_column(JSONB)
    away_stats: Mapped[dict | None] = mapped_column(JSONB)

    __table_args__ = (
        Index("ix_elbs_game_seen", "espn_game_id", "first_seen_at"),
    )


class EspnLivePlayerSnapshot(Base):
    """One player's box line at one poll (slow cadence)."""

    __tablename__ = "espn_live_player_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    first_seen_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)

    espn_game_id: Mapped[str] = mapped_column(String(32), nullable=False)
    team_id: Mapped[str | None] = mapped_column(String(16))
    athlete_id: Mapped[str] = mapped_column(String(16), nullable=False)
    athlete_name: Mapped[str | None] = mapped_column(String(80))

    minutes: Mapped[int | None] = mapped_column(SmallInteger)
    points: Mapped[int | None] = mapped_column(SmallInteger)
    fgm: Mapped[int | None] = mapped_column(SmallInteger)
    fga: Mapped[int | None] = mapped_column(SmallInteger)
    tpm: Mapped[int | None] = mapped_column(SmallInteger)
    tpa: Mapped[int | None] = mapped_column(SmallInteger)
    ftm: Mapped[int | None] = mapped_column(SmallInteger)
    fta: Mapped[int | None] = mapped_column(SmallInteger)
    rebounds: Mapped[int | None] = mapped_column(SmallInteger)
    assists: Mapped[int | None] = mapped_column(SmallInteger)
    turnovers: Mapped[int | None] = mapped_column(SmallInteger)
    fouls: Mapped[int | None] = mapped_column(SmallInteger)
    plus_minus: Mapped[int | None] = mapped_column(SmallInteger)

    starter: Mapped[bool | None] = mapped_column(Boolean)
    #: Semantics unverified pregame — the live checklist's question 3. Stored
    #: exactly as served; interpreted only after a live game confirms it.
    active: Mapped[bool | None] = mapped_column(Boolean)
    ejected: Mapped[bool | None] = mapped_column(Boolean)
    did_not_play: Mapped[bool | None] = mapped_column(Boolean)
    reason: Mapped[str | None] = mapped_column(String(120))

    __table_args__ = (
        Index("ix_elps_game_seen", "espn_game_id", "first_seen_at"),
        Index("ix_elps_athlete", "athlete_id"),
    )


class EspnLiveWinProbability(Base):
    """ESPN's own per-play win probability — the free external benchmark."""

    __tablename__ = "espn_live_win_probability"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    first_seen_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False)

    espn_game_id: Mapped[str] = mapped_column(String(32), nullable=False)
    play_id: Mapped[str] = mapped_column(String(32), nullable=False)
    home_win_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))

    __table_args__ = (
        UniqueConstraint("play_id", name="uq_elwp_play_id"),
        Index("ix_elwp_game", "espn_game_id"),
    )


class EspnLiveInjuryObservation(Base):
    """One (game, athlete, status) sighting from the summary injuries block.

    RECORD-ONLY raw material for the availability delta — consumption is
    blocked by B's oracle-arm verdict (docs/math/injury-delta.md) until that
    measurement separates from zero. The unique constraint makes "on change
    only" structural: re-observing the same status is a no-op; a status
    CHANGE (Out -> Available, an in-game exit) lands a new row with its own
    `first_seen_at`.
    """

    __tablename__ = "espn_live_injury_observations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    first_seen_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False)

    espn_game_id: Mapped[str] = mapped_column(String(32), nullable=False)
    team_id: Mapped[str | None] = mapped_column(String(16))
    athlete_id: Mapped[str] = mapped_column(String(16), nullable=False)
    athlete_name: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    details: Mapped[dict | None] = mapped_column(JSONB)

    __table_args__ = (
        UniqueConstraint("espn_game_id", "athlete_id", "status",
                         name="uq_elio_game_athlete_status"),
        Index("ix_elio_game", "espn_game_id"),
    )
