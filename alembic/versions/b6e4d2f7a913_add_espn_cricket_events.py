"""add espn_cricket_events

The cricket signal recorder's one table (core/feeds/espn_cricket_recorder.py):
one row per observed CHANGE of a match's state/period/toss/innings/
commentary count/winner, stamped with our observation instant. `raw` is
filled only on state/period/toss/winner changes (a ball changes innings and
commentary_count, and 300 balls x 60 KB would be 20 MB per match).

Revision ID: b6e4d2f7a913
Revises: a1c8f3e9b204
Create Date: 2026-09-13
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "b6e4d2f7a913"
down_revision: str = "a1c8f3e9b204"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "espn_cricket_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("series_id", sa.String(length=16), nullable=False),
        sa.Column("event_id", sa.String(length=16), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("home_team", sa.Text(), nullable=True),
        sa.Column("away_team", sa.Text(), nullable=True),
        sa.Column("scheduled_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("state", sa.String(length=8), nullable=True),
        sa.Column("status_detail", sa.Text(), nullable=True),
        sa.Column("period", sa.SmallInteger(), nullable=True),
        sa.Column("toss_text", sa.Text(), nullable=True),
        sa.Column("toss_first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("innings", JSONB(), nullable=True),
        sa.Column("winner_team", sa.Text(), nullable=True),
        sa.Column("result_text", sa.Text(), nullable=True),
        sa.Column("commentary_count", sa.Integer(), nullable=True),
        sa.Column("commentary_latest", sa.Text(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw", JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "captured_at"),
    )
    op.create_index("ix_espn_cricket_events_event_id", "espn_cricket_events", ["event_id"])
    op.create_index("ix_espn_cricket_events_captured_at", "espn_cricket_events", ["captured_at"])


def downgrade() -> None:
    op.drop_index("ix_espn_cricket_events_captured_at", table_name="espn_cricket_events")
    op.drop_index("ix_espn_cricket_events_event_id", table_name="espn_cricket_events")
    op.drop_table("espn_cricket_events")
