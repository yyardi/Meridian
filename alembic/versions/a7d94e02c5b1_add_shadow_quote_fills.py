"""add shadow_quote_fills — the QUOTE shadow run's raw material

One row per simulated fill of a resting shadow quote. No order exists behind
any row here and none ever can: the engine that writes this table
(core/quote/engine.py) has no import path to the executor or the order
client, pinned by test — the same structural guarantee the live-FV strip and
the EV guard carry.

Chains the (uncommitted-at-authoring) retention migration c8f1a4d27e93 so the
history stays linear; if that revision id changes before it lands, this
down_revision is the one-line fix.

Revision ID: a7d94e02c5b1
Revises: c8f1a4d27e93
Create Date: 2026-08-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a7d94e02c5b1'
down_revision: Union[str, None] = 'c8f1a4d27e93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'shadow_quote_fills',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('market_slug', sa.String(length=200), nullable=False),
        sa.Column('game_id', sa.String(length=64), nullable=False),
        sa.Column('regime', sa.String(length=8), nullable=False),
        sa.Column('side', sa.String(length=4), nullable=False),
        sa.Column('quote_price', sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column('mid_at_quote', sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column('spread_at_quote', sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column('mid_at_fill', sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column('quoted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('filled_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('settlement', sa.SmallInteger(), nullable=True),
        sa.Column('settled_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("regime in ('pregame','ingame')", name='ck_sqf_regime'),
        sa.CheckConstraint("side in ('bid','ask')", name='ck_sqf_side'),
        sa.CheckConstraint('settlement is null or settlement in (0,1)',
                           name='ck_sqf_settlement'),
    )
    op.create_index('ix_sqf_market_slug', 'shadow_quote_fills', ['market_slug'])
    op.create_index('ix_sqf_game_id', 'shadow_quote_fills', ['game_id'])
    op.create_index('ix_sqf_settlement', 'shadow_quote_fills', ['settlement'])
    op.create_index('ix_sqf_filled_at', 'shadow_quote_fills', ['filled_at'])


def downgrade() -> None:
    op.drop_index('ix_sqf_filled_at', table_name='shadow_quote_fills')
    op.drop_index('ix_sqf_settlement', table_name='shadow_quote_fills')
    op.drop_index('ix_sqf_game_id', table_name='shadow_quote_fills')
    op.drop_index('ix_sqf_market_slug', table_name='shadow_quote_fills')
    op.drop_table('shadow_quote_fills')
