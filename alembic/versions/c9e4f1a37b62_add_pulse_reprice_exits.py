"""add pulse_reprice_exits — the dynamic-exit-repricing shadow arm

One row per filled entry recording what a profit-target exit repriced each
cycle at current fair value would have done (core/pulse/reprice.py), against
docs/math/dynamic-exit-repricing.md. Shadow only; no order exists behind it.
Paired to the static incumbent by entry_decision_id.

Revision ID: c9e4f1a37b62
Revises: b7d3e9f42a18
Create Date: 2026-09-02
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'c9e4f1a37b62'
down_revision: str | None = 'b7d3e9f42a18'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'pulse_reprice_exits',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('entry_decision_id', sa.BigInteger(), nullable=False),
        sa.Column('event_slug', sa.String(length=200), nullable=False),
        sa.Column('market_slug', sa.String(length=200), nullable=False),
        sa.Column('strategy', sa.String(length=16), nullable=False),
        sa.Column('side', sa.String(length=3), nullable=False),
        sa.Column('entry_price', sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column('contracts', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('profit_target', sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column('opened_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('dynamic_outcome', sa.String(length=16), nullable=False),
        sa.Column('dynamic_exit_price', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('dynamic_filled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('was_stop', sa.Boolean(), nullable=False),
        sa.Column('fv_open', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('reprice_cycles', sa.Integer(), nullable=False),
        sa.Column('target_diverged', sa.Boolean(), nullable=False),
        sa.Column('staleness_holds', sa.Integer(), nullable=False),
        sa.Column('staleness_fallbacks', sa.Integer(), nullable=False),
        sa.Column('estimates_version', sa.String(length=4), nullable=False),
        sa.CheckConstraint("dynamic_outcome in ('exit_fill','settlement')",
                           name='ck_pre_outcome'),
        sa.CheckConstraint("side in ('yes','no')", name='ck_pre_side'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('entry_decision_id', name='uq_pre_entry'),
    )
    op.create_index('ix_pre_event_slug', 'pulse_reprice_exits', ['event_slug'])
    op.create_index('ix_pre_entry_id', 'pulse_reprice_exits', ['entry_decision_id'])


def downgrade() -> None:
    op.drop_index('ix_pre_entry_id', table_name='pulse_reprice_exits')
    op.drop_index('ix_pre_event_slug', table_name='pulse_reprice_exits')
    op.drop_table('pulse_reprice_exits')
