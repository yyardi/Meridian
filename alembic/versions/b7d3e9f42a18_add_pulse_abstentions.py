"""add pulse_abstentions — recorded refusals to price

One row per throttled guard refusal from the PULSE live loop: a
jointly-impossible clock/score state, or an emitted certainty the Gaussian
tail cannot represent (core/pulse/guards.py). The `binding_constraint`
principle applied to pricing: a state we refused to price is data; a state
that silently vanishes is not.

Revision ID: b7d3e9f42a18
Revises: c4e7f2a81d59
Create Date: 2026-09-01
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'b7d3e9f42a18'
down_revision: str | None = 'c4e7f2a81d59'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'pulse_abstentions',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('event_slug', sa.String(length=200), nullable=False),
        sa.Column('market_slug', sa.String(length=200), nullable=False),
        sa.Column('strategy', sa.String(length=16), nullable=False),
        sa.Column('guard', sa.String(length=32), nullable=False),
        sa.Column('reason', sa.String(length=200), nullable=False),
        sa.Column('period', sa.String(length=32), nullable=True),
        sa.Column('minutes_left', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('total_so_far', sa.Integer(), nullable=True),
        sa.Column('margin', sa.Integer(), nullable=True),
        sa.Column('line', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('fair_value_raw', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('estimates_version', sa.String(length=4), nullable=False),
        sa.CheckConstraint(
            "guard in ('implausible_state','unrepresentable_confidence')",
            name='ck_pa_guard'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_pa_event_slug', 'pulse_abstentions', ['event_slug'])
    op.create_index('ix_pa_decided_at', 'pulse_abstentions', ['decided_at'])


def downgrade() -> None:
    op.drop_index('ix_pa_decided_at', table_name='pulse_abstentions')
    op.drop_index('ix_pa_event_slug', table_name='pulse_abstentions')
    op.drop_table('pulse_abstentions')
