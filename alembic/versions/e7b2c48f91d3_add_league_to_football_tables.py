"""add league column to the football game-state tables

NFL week 1 opens 2026-09-10 and PULSE has never made a football prediction.
There was no NFL game-state recorder and no NFL game-state table: espn_cfb_*
is CFB, espn_live_* is WNBA and basketball-shaped. NFL would have arrived with
venue price tape and zero game state — exactly where CFB was on 2026-09-05.

The espn_cfb_* tables are FOOTBALL-shaped, not CFB-shaped: down, distance,
yards_to_goal and possession mean the same thing in the NFL. Only the table
NAMES say cfb, which is an artefact of being built for CFB first. So NFL rows
go here with a `league` discriminator rather than into a duplicate schema —
one training frame, one parser, one set of traps already found.

Defaults to 'cfb' so every existing row is correctly labelled without a
backfill pass.

Revision ID: e7b2c48f91d3
Revises: d4a71e6c93b8
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "e7b2c48f91d3"
down_revision: str | None = "d4a71e6c93b8"
branch_labels = None
depends_on = None

_TABLES = (
    "espn_cfb_live_plays",
    "espn_cfb_game_state",
    "espn_cfb_win_probability",
)


def upgrade() -> None:
    for t in _TABLES:
        op.add_column(t, sa.Column("league", sa.String(length=8),
                                   server_default="cfb", nullable=False))
        op.create_index(f"ix_{t}_league", t, ["league"])


def downgrade() -> None:
    for t in _TABLES:
        op.drop_index(f"ix_{t}_league", table_name=t)
        op.drop_column(t, "league")
