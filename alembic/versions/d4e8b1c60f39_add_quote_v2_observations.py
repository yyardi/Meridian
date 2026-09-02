"""add quote_v2_observations — the QUOTE v2 forward observation stream

One row per v2-quoter observation on the quoter's OWN clock (<=1s cadence).
The compliant substrate the congestion gate, the guard arm, and PATIENCE all
converge on (docs/math/quote-v2-observation-schema.md, field set signed off by
B 2026-09-02). Records only; the quoted policy stays the frozen v1 commit, so
the table is freeze-safe. No order path — shadow-only.

Revision ID: d4e8b1c60f39
Revises: c9e4f1a37b62
Create Date: 2026-09-02
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'd4e8b1c60f39'
down_revision: str | None = 'c9e4f1a37b62'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'quote_v2_observations',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('market_slug', sa.String(length=200), nullable=False),
        sa.Column('game_id', sa.String(length=64), nullable=False),
        sa.Column('event_slug', sa.String(length=200), nullable=False),
        sa.Column('sports_market_type', sa.String(length=64), nullable=False),
        sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('best_bid', sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column('best_ask', sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column('is_live', sa.Boolean(), nullable=False),
        sa.Column('event_period', sa.String(length=32), nullable=True),
        sa.Column('event_score', sa.String(length=32), nullable=True),
        sa.Column('margin', sa.Integer(), nullable=True),
        sa.Column('total_so_far', sa.Integer(), nullable=True),
        sa.Column('minutes_left', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('minutes_left_is_estimate', sa.Boolean(), nullable=True),
        sa.Column('fair_value', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('game_start_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('quote_bid', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('quote_ask', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('quote_event', sa.String(length=16), nullable=False),
        sa.Column('det_version', sa.String(length=40), nullable=True),
        sa.Column('det_in_window', sa.Boolean(), nullable=True),
        sa.Column('det_confirm_t0', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "quote_event in ('rested','requoted','withdrawn','held',"
            "'filled_bid','filled_ask','none')", name='ck_qv2_quote_event'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_qv2_market_slug', 'quote_v2_observations', ['market_slug'])
    op.create_index('ix_qv2_game_id', 'quote_v2_observations', ['game_id'])
    op.create_index('ix_qv2_event_slug', 'quote_v2_observations', ['event_slug'])
    op.create_index('ix_qv2_observed_at', 'quote_v2_observations', ['observed_at'])


def downgrade() -> None:
    op.drop_index('ix_qv2_observed_at', table_name='quote_v2_observations')
    op.drop_index('ix_qv2_event_slug', table_name='quote_v2_observations')
    op.drop_index('ix_qv2_game_id', table_name='quote_v2_observations')
    op.drop_index('ix_qv2_market_slug', table_name='quote_v2_observations')
    op.drop_table('quote_v2_observations')
