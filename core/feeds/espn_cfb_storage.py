"""Storage for COLLEGE FOOTBALL live game state. Football-shaped, deliberately.

Models live beside their only writer (`core/feeds/espn_cfb_recorder.py`).
Sibling of `core/feeds/espn_live_storage.py`, which is BASKETBALL-shaped and
cannot be widened to hold this: its columns are `home_fgm`, `home_tpa`,
`home_oreb`, `home_turnovers`. A football play has none of those and needs
down, distance, yards-to-goal and possession, which basketball has none of.
The sport is in the schema; that is why this is a second table and not a
column added to the first.

WHY THESE COLUMN NAMES
----------------------
They match **CFBD/cfbfastR** (`cfbd_pbp_data`), so historical backfill
(`load_cfb_pbp()`, FBS from 2014) and our own live recording are
interchangeable in one training frame. Deviating would force a mapping layer
that silently diverges.

THE GOVERNING RULE: STORE RAW, DERIVE IN SHARED CODE
----------------------------------------------------
Nothing derived is stored. `game_seconds_remaining`, `score_differential`,
`receives_2h_kickoff`, `diff_time_ratio` and `spread_time` are all pure
transforms of the columns below and are computed in ONE function imported by
both the trainer and the live server. Storing them here would let the live
path drift from the training path — train/serve skew that offline validation
cannot catch, because offline validation only ever sees one of the two.

``wall_clock`` IS LOAD-BEARING, NOT METADATA
--------------------------------------------
It is the only join key between game state and ``market_snapshots.captured_at``.
Without it a model can describe a game but cannot be aligned to a quote, and
the entire exercise is descriptive rather than tradeable. Recorded at full
precision, straight from ESPN's own per-play stamp — and stored BESIDE
``first_seen_at``, which is the instant OUR poller saw the row. Only
``first_seen_at`` establishes knowability for a replay; ``wall_clock`` is
data. (The signal-side rule, unchanged from the basketball recorder.)

OVERTIME IS A DIFFERENT REGIME AND THE SCHEMA SAYS SO
------------------------------------------------------
College overtime has **no clock**. ``game_seconds_remaining`` is therefore
undefined, and so is every time-decayed feature — including ``spread_time``,
which the published recipe says is the decisive one. A model that imputes
zero there will emit confident nonsense in the highest-leverage state in the
sport. ``is_overtime`` and ``ot_possession_number`` exist so the model can
route OT to its own head instead of being fed NULLs.

TIMEOUTS: A DOCUMENTED SUBSTITUTION
------------------------------------
CFBD carries ``pos_team_timeouts_rem_before`` **per play**. ESPN's live
summary does NOT — it exposes ``competitors[N].timeoutsUsed``, which is the
**game-level count at poll time**. Stamping that onto older plays in the same
payload would attribute the current count to a play that happened minutes
earlier. So timeouts live in ``espn_cfb_game_state`` (one row per poll, with
its own ``first_seen_at``) and are joined to plays by time at read time. The
live feature is therefore an as-of-poll approximation where the backfill is
exact; any model using timeouts must be told which source it is reading.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import BIGINT, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.storage.base import Base


class CfbLivePlay(Base):
    """One football play, as observed. Append-only: a play never updates, so
    re-observing one is ON CONFLICT DO NOTHING — idempotent across restarts
    and overlapping polls."""

    __tablename__ = "espn_cfb_live_plays"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)

    #: the instant THIS process observed the row — the only knowability stamp.
    first_seen_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    game_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    play_id: Mapped[str] = mapped_column(String(48), nullable=False)
    drive_id: Mapped[str | None] = mapped_column(String(48))
    sequence_number: Mapped[str | None] = mapped_column(String(32))

    #: ESPN's own stamp for the play. The join key to market_snapshots.
    wall_clock: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), index=True)

    # --- clock/period, raw. 1-4 regulation; 5+ is overtime. --------------- #
    period: Mapped[int | None] = mapped_column(SmallInteger)
    half: Mapped[int | None] = mapped_column(SmallInteger)
    clock_minutes: Mapped[int | None] = mapped_column(SmallInteger)
    clock_seconds: Mapped[int | None] = mapped_column(SmallInteger)
    is_overtime: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ot_possession_number: Mapped[int | None] = mapped_column(SmallInteger)

    # --- game state at the START of the play (nflfastR's convention) ------ #
    down: Mapped[int | None] = mapped_column(SmallInteger)
    distance: Mapped[int | None] = mapped_column(SmallInteger)
    yards_to_goal: Mapped[int | None] = mapped_column(SmallInteger)

    pos_team: Mapped[str | None] = mapped_column(String(32))
    def_pos_team: Mapped[str | None] = mapped_column(String(32))
    home: Mapped[str | None] = mapped_column(String(32))
    away: Mapped[str | None] = mapped_column(String(32))
    #: the posteam-is-home indicator the recipe needs.
    drive_is_home_offense: Mapped[bool | None] = mapped_column(Boolean)

    pos_team_score: Mapped[int | None] = mapped_column(SmallInteger)
    def_pos_team_score: Mapped[int | None] = mapped_column(SmallInteger)
    home_score: Mapped[int | None] = mapped_column(SmallInteger)
    away_score: Mapped[int | None] = mapped_column(SmallInteger)

    # --- play identity. play_text is needed for the documented CFBD/ESPN -- #
    # --- possession-mislabel cleaning; do not drop it as cosmetic. -------- #
    play_type: Mapped[str | None] = mapped_column(String(96))
    play_text: Mapped[str | None] = mapped_column(Text)
    scoring_play: Mapped[bool | None] = mapped_column(Boolean)
    score_value: Mapped[int | None] = mapped_column(SmallInteger)
    is_turnover: Mapped[bool | None] = mapped_column(Boolean)
    is_penalty: Mapped[bool | None] = mapped_column(Boolean)

    #: the whole play object, so a parsing bug is recoverable from the archive.
    raw: Mapped[dict | None] = mapped_column(JSONB)

    __table_args__ = (
        UniqueConstraint("game_id", "play_id", name="uq_cfb_play"),
        Index("ix_cfb_plays_game_wall", "game_id", "wall_clock"),
    )


class CfbGameState(Base):
    """One row per poll per game. That cadence IS the data.

    Carries what is game-level rather than play-level: timeouts, the live
    betting line, and ESPN's own win probability — the external benchmark.
    """

    __tablename__ = "espn_cfb_game_state"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    first_seen_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    game_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    state: Mapped[str | None] = mapped_column(String(16))       # pre / in / post
    period: Mapped[int | None] = mapped_column(SmallInteger)
    display_clock: Mapped[str | None] = mapped_column(String(16))

    home: Mapped[str | None] = mapped_column(String(32))
    away: Mapped[str | None] = mapped_column(String(32))
    home_score: Mapped[int | None] = mapped_column(SmallInteger)
    away_score: Mapped[int | None] = mapped_column(SmallInteger)

    #: game-level, as of THIS poll. See the timeout note in the module docstring.
    home_timeouts_used: Mapped[int | None] = mapped_column(SmallInteger)
    away_timeouts_used: Mapped[int | None] = mapped_column(SmallInteger)

    #: the live line, from the same call. NOT the closing line — the closing
    #: spread comes from `sportsbook_odds` and is the benchmark, not a feature.
    live_spread: Mapped[float | None] = mapped_column(Numeric(6, 2))
    live_over_under: Mapped[float | None] = mapped_column(Numeric(6, 2))
    line_provider: Mapped[str | None] = mapped_column(String(48))

    #: ESPN's own model output — a second external benchmark alongside the line.
    espn_home_win_pct: Mapped[float | None] = mapped_column(Numeric(6, 5))

    __table_args__ = (
        Index("ix_cfb_state_game_seen", "game_id", "first_seen_at"),
    )


class CfbWinProbability(Base):
    """ESPN's per-play win probability. Append-only, one row per (game, play).

    A benchmark to beat, never a feature — letting a competitor's model into
    our own feature set would make beating it trivial and meaningless.
    """

    __tablename__ = "espn_cfb_win_probability"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    first_seen_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    game_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    play_id: Mapped[str] = mapped_column(String(48), nullable=False)
    home_win_pct: Mapped[float | None] = mapped_column(Numeric(6, 5))

    __table_args__ = (
        UniqueConstraint("game_id", "play_id", name="uq_cfb_wp"),
    )
