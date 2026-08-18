"""add pulse_decisions — the PULSE live run's tape

One row per in-game shadow decision (enter / exit / hold) from the PULSE live
loop (core/pulse/live.py). No order exists behind any row and none can: the
engine has no import path to the executor or the order client, pinned by an
AST-level test — the same structural guarantee shadow_quote_fills carries.

Carries the game tape's join keys (event_slug, market_slug, decided_at) and
the tape's own context columns denormalised at decision time, plus the
'phase' marker the tape view's PREGAME/IN-PLAY seam labels.

Revision ID: e6f2a8b93c51
Revises: d2a6f18c40b7
Create Date: 2026-08-18
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'e6f2a8b93c51'
down_revision: str | None = 'd2a6f18c40b7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'pulse_decisions',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('event_slug', sa.String(length=200), nullable=False),
        sa.Column('market_slug', sa.String(length=200), nullable=False),
        sa.Column('game_id', sa.String(length=64), nullable=True),
        sa.Column('sports_market_type', sa.String(length=64), nullable=False),
        sa.Column('line', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('strategy', sa.String(length=16), nullable=False),
        sa.Column('phase', sa.String(length=8), nullable=False),
        sa.Column('action', sa.String(length=8), nullable=False),
        sa.Column('side', sa.String(length=3), nullable=False),
        sa.Column('limit_price', sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column('contracts', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('stake_usd', sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column('bankroll_usd', sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column('binding_constraint', sa.String(length=40), nullable=True),
        sa.Column('reason', sa.String(length=200), nullable=True),
        sa.Column('entry_id', sa.BigInteger(), nullable=True),
        sa.Column('score', sa.String(length=32), nullable=True),
        sa.Column('margin', sa.Integer(), nullable=True),
        sa.Column('period', sa.String(length=32), nullable=True),
        sa.Column('minutes_left', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('minutes_left_is_estimate', sa.Boolean(), nullable=False),
        sa.Column('total_so_far', sa.Integer(), nullable=True),
        sa.Column('projected_total', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('total_sigma', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('market_bid', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('market_ask', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('fair_value', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('edge_net', sa.Numeric(precision=7, scale=4), nullable=True),
        sa.Column('filled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('mid_at_fill', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('withdrawn_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('settlement', sa.SmallInteger(), nullable=True),
        sa.Column('settled_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("phase in ('pregame','in_play')", name='ck_pd_phase'),
        sa.CheckConstraint("action in ('enter','exit','hold')", name='ck_pd_action'),
        sa.CheckConstraint("side in ('yes','no')", name='ck_pd_side'),
        sa.CheckConstraint("strategy in ('winner','total','spread')",
                           name='ck_pd_strategy'),
        sa.CheckConstraint('settlement is null or settlement in (0,1)',
                           name='ck_pd_settlement'),
    )
    op.create_index('ix_pd_event_slug', 'pulse_decisions', ['event_slug'])
    op.create_index('ix_pd_market_slug', 'pulse_decisions', ['market_slug'])
    op.create_index('ix_pd_decided_at', 'pulse_decisions', ['decided_at'])
    op.create_index('ix_pd_entry_id', 'pulse_decisions', ['entry_id'])
    op.create_index('ix_pd_settlement', 'pulse_decisions', ['settlement'])


def downgrade() -> None:
    op.drop_index('ix_pd_settlement', table_name='pulse_decisions')
    op.drop_index('ix_pd_entry_id', table_name='pulse_decisions')
    op.drop_index('ix_pd_decided_at', table_name='pulse_decisions')
    op.drop_index('ix_pd_market_slug', table_name='pulse_decisions')
    op.drop_index('ix_pd_event_slug', table_name='pulse_decisions')
    op.drop_table('pulse_decisions')
