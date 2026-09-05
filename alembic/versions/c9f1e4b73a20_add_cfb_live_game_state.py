"""add college-football live game state tables

We held 56,948 CFB shadow fills across 48 games and zero rows of CFB game
state: the market was recorded and the game was not. The existing
espn_live_* tables are basketball-shaped (home_fgm, home_tpa, home_oreb,
home_turnovers) and cannot hold down/distance/yards-to-goal/possession, so
football gets its own tables rather than widened ones.

Column names match CFBD/cfbfastR so historical backfill (load_cfb_pbp, FBS
from 2014) and our own live recording land in one training frame. Nothing
derived is stored — game_seconds_remaining, diff_time_ratio and spread_time
are computed in shared code imported by both trainer and server, so the two
cannot drift into train/serve skew.

Revision ID: c9f1e4b73a20
Revises: b7e2f91a4c33
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "c9f1e4b73a20"
down_revision: str | None = "b7e2f91a4c33"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "espn_cfb_live_plays",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("game_id", sa.String(length=32), nullable=False),
        sa.Column("play_id", sa.String(length=48), nullable=False),
        sa.Column("drive_id", sa.String(length=48), nullable=True),
        sa.Column("sequence_number", sa.String(length=32), nullable=True),
        # ESPN's own per-play stamp: the ONLY join key to market_snapshots.
        sa.Column("wall_clock", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period", sa.SmallInteger(), nullable=True),
        sa.Column("half", sa.SmallInteger(), nullable=True),
        sa.Column("clock_minutes", sa.SmallInteger(), nullable=True),
        sa.Column("clock_seconds", sa.SmallInteger(), nullable=True),
        # College OT has no clock, so every time-decayed feature is undefined
        # there; the model routes on these rather than being fed NULLs.
        sa.Column("is_overtime", sa.Boolean(), server_default=sa.text("false"),
                  nullable=False),
        sa.Column("ot_possession_number", sa.SmallInteger(), nullable=True),
        sa.Column("down", sa.SmallInteger(), nullable=True),
        sa.Column("distance", sa.SmallInteger(), nullable=True),
        sa.Column("yards_to_goal", sa.SmallInteger(), nullable=True),
        sa.Column("pos_team", sa.String(length=32), nullable=True),
        sa.Column("def_pos_team", sa.String(length=32), nullable=True),
        sa.Column("home", sa.String(length=32), nullable=True),
        sa.Column("away", sa.String(length=32), nullable=True),
        sa.Column("drive_is_home_offense", sa.Boolean(), nullable=True),
        sa.Column("pos_team_score", sa.SmallInteger(), nullable=True),
        sa.Column("def_pos_team_score", sa.SmallInteger(), nullable=True),
        sa.Column("home_score", sa.SmallInteger(), nullable=True),
        sa.Column("away_score", sa.SmallInteger(), nullable=True),
        sa.Column("play_type", sa.String(length=96), nullable=True),
        # needed for the documented CFBD/ESPN possession-mislabel cleaning
        sa.Column("play_text", sa.Text(), nullable=True),
        sa.Column("scoring_play", sa.Boolean(), nullable=True),
        sa.Column("score_value", sa.SmallInteger(), nullable=True),
        sa.Column("is_turnover", sa.Boolean(), nullable=True),
        sa.Column("is_penalty", sa.Boolean(), nullable=True),
        sa.Column("raw", JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "play_id", name="uq_cfb_play"),
    )
    op.create_index("ix_espn_cfb_live_plays_first_seen_at",
                    "espn_cfb_live_plays", ["first_seen_at"])
    op.create_index("ix_espn_cfb_live_plays_game_id",
                    "espn_cfb_live_plays", ["game_id"])
    op.create_index("ix_espn_cfb_live_plays_wall_clock",
                    "espn_cfb_live_plays", ["wall_clock"])
    op.create_index("ix_cfb_plays_game_wall",
                    "espn_cfb_live_plays", ["game_id", "wall_clock"])

    op.create_table(
        "espn_cfb_game_state",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("game_id", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=True),
        sa.Column("period", sa.SmallInteger(), nullable=True),
        sa.Column("display_clock", sa.String(length=16), nullable=True),
        sa.Column("home", sa.String(length=32), nullable=True),
        sa.Column("away", sa.String(length=32), nullable=True),
        sa.Column("home_score", sa.SmallInteger(), nullable=True),
        sa.Column("away_score", sa.SmallInteger(), nullable=True),
        # game-level as of THIS poll: ESPN exposes no per-play timeouts, so
        # these are joined to plays by time rather than stamped onto them.
        sa.Column("home_timeouts_used", sa.SmallInteger(), nullable=True),
        sa.Column("away_timeouts_used", sa.SmallInteger(), nullable=True),
        sa.Column("live_spread", sa.Numeric(6, 2), nullable=True),
        sa.Column("live_over_under", sa.Numeric(6, 2), nullable=True),
        sa.Column("line_provider", sa.String(length=48), nullable=True),
        # ESPN's own model: a benchmark to beat, never a feature.
        sa.Column("espn_home_win_pct", sa.Numeric(6, 5), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_espn_cfb_game_state_first_seen_at",
                    "espn_cfb_game_state", ["first_seen_at"])
    op.create_index("ix_espn_cfb_game_state_game_id",
                    "espn_cfb_game_state", ["game_id"])
    op.create_index("ix_cfb_state_game_seen",
                    "espn_cfb_game_state", ["game_id", "first_seen_at"])

    op.create_table(
        "espn_cfb_win_probability",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("game_id", sa.String(length=32), nullable=False),
        sa.Column("play_id", sa.String(length=48), nullable=False),
        sa.Column("home_win_pct", sa.Numeric(6, 5), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "play_id", name="uq_cfb_wp"),
    )
    op.create_index("ix_espn_cfb_win_probability_game_id",
                    "espn_cfb_win_probability", ["game_id"])


def downgrade() -> None:
    op.drop_table("espn_cfb_win_probability")
    op.drop_table("espn_cfb_game_state")
    op.drop_table("espn_cfb_live_plays")
