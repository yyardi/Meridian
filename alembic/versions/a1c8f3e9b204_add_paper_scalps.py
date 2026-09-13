"""add paper_scalps

The PAPER in-game scalp engine's output (core/gridiron/scalp.py). One row per
CLOSED position; an open one lives only in the engine's memory, so a restart
drops it rather than resuming a position priced off a tape nobody watched.

Revision ID: a1c8f3e9b204
Revises: e7b2c48f91d3
Create Date: 2026-09-13
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "a1c8f3e9b204"
down_revision: str = "e7b2c48f91d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "paper_scalps",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("league", sa.String(length=16), nullable=False),
        sa.Column("game_id", sa.String(length=64), nullable=False),
        sa.Column("market_slug", sa.String(length=200), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("entered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entry_px", sa.Numeric(6, 4), nullable=False),
        sa.Column("exit_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exit_px", sa.Numeric(6, 4), nullable=False),
        sa.Column("exit_reason", sa.String(length=16), nullable=False),
        sa.Column("pnl", sa.Numeric(12, 6), nullable=False),
        sa.Column("fee", sa.Numeric(12, 6), nullable=False),
        sa.Column("params", JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        # the five reasons the engine can emit; a sixth is a code change, and
        # this is where it should fail rather than in a dashboard aggregate
        sa.CheckConstraint(
            "exit_reason IN ('tp','stop','drive_end','final','stale')",
            name="ck_paper_scalps_exit_reason"),
        sa.CheckConstraint("side IN ('yes','no')", name="ck_paper_scalps_side"),
    )
    op.create_index("ix_paper_scalps_exit_at", "paper_scalps", ["exit_at"])
    op.create_index("ix_paper_scalps_league_exit_at", "paper_scalps", ["league", "exit_at"])


def downgrade() -> None:
    op.drop_index("ix_paper_scalps_league_exit_at", table_name="paper_scalps")
    op.drop_index("ix_paper_scalps_exit_at", table_name="paper_scalps")
    op.drop_table("paper_scalps")
