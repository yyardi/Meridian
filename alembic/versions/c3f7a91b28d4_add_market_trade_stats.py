"""add market_trade_stats — the venue's trade tape, previously discarded

Revision ID: c3f7a91b28d4
Revises: f1a2b3c4d5e6
Create Date: 2026-09-03

The book response the depth loop already fetches carries the ONLY flow
observable this venue offers (findings V31/V32): no gateway or authenticated
endpoint exposes market volume. These fields were parsed and thrown away on
every poll from the recorder's first day. Additive table; nothing existing
changes.
"""
from alembic import op
import sqlalchemy as sa

revision = "c3f7a91b28d4"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_trade_stats",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_trade_px", sa.Numeric(6, 4), nullable=True),
        sa.Column("last_trade_qty", sa.Numeric(18, 4), nullable=True),
        sa.Column("last_trade_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shares_traded", sa.Numeric(18, 4), nullable=True),
        sa.Column("notional_traded", sa.Numeric(20, 4), nullable=True),
        sa.Column("open_interest", sa.Numeric(18, 4), nullable=True),
        sa.Column("high_px", sa.Numeric(6, 4), nullable=True),
        sa.Column("low_px", sa.Numeric(6, 4), nullable=True),
        sa.ForeignKeyConstraint(["snapshot_id"], ["market_snapshots.id"],
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("snapshot_id", name="uq_market_trade_stat_snapshot"),
    )
    op.create_index("ix_market_trade_stats_captured_at", "market_trade_stats",
                    ["captured_at"])


def downgrade() -> None:
    op.drop_index("ix_market_trade_stats_captured_at",
                  table_name="market_trade_stats")
    op.drop_table("market_trade_stats")
