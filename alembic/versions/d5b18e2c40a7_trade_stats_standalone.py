"""market_trade_stats: allow standalone (sweeper) rows

Revision ID: d5b18e2c40a7
Revises: c3f7a91b28d4
Create Date: 2026-09-03

The pregame stats sweeper records the VOLUME TRAJECTORY of a board — the only
thing that separates "this market is dead" from "this market fills up late",
and unreconstructable after the fact because the venue exposes a cumulative
counter with no history. Those rows have no snapshot of their own, so
snapshot_id becomes nullable and market_slug carries the identity.
"""
from alembic import op
import sqlalchemy as sa

revision = "d5b18e2c40a7"
down_revision = "c3f7a91b28d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("market_trade_stats", "snapshot_id",
                    existing_type=sa.BigInteger(), nullable=True)
    op.add_column("market_trade_stats",
                  sa.Column("market_slug", sa.String(160), nullable=True))
    op.create_index("ix_market_trade_stats_slug_time", "market_trade_stats",
                    ["market_slug", "captured_at"])


def downgrade() -> None:
    op.drop_index("ix_market_trade_stats_slug_time",
                  table_name="market_trade_stats")
    op.drop_column("market_trade_stats", "market_slug")
    op.alter_column("market_trade_stats", "snapshot_id",
                    existing_type=sa.BigInteger(), nullable=False)
