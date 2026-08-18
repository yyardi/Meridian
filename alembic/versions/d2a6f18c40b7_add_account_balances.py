"""add account_balances — the real bankroll, read from the venue

Every dollar the system computes is a fraction of a bankroll, and that
bankroll was a literal (`35.68`) typed into the scheduler on the day someone
last looked at the app. The account was at $23.82 by 2026-08-17, so every size
on the board was ~50% too large and the error grew silently with every fill.

Append-only, one row per poll: the history is the equity curve, and storing
the derived `bankroll` next to the raw venue fields is what makes a past
sizing decision reproducible. Tiny at any cadence — 20-minute polling is ~26k
rows a year.

Revision ID: d2a6f18c40b7
Revises: a7d94e02c5b1
Create Date: 2026-08-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'd2a6f18c40b7'
down_revision: Union[str, None] = 'a7d94e02c5b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MONEY = sa.Numeric(precision=18, scale=6)


def upgrade() -> None:
    op.create_table(
        'account_balances',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('observed_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('currency', sa.String(length=8), nullable=False),
        sa.Column('cash', _MONEY, nullable=False),
        sa.Column('buying_power', _MONEY, nullable=False),
        sa.Column('asset_notional', _MONEY, nullable=False),
        sa.Column('open_orders', _MONEY, nullable=False),
        sa.Column('unsettled_funds', _MONEY, nullable=False),
        sa.Column('pending_credit', _MONEY, nullable=False),
        sa.Column('margin_requirement', _MONEY, nullable=False),
        sa.Column('bankroll', _MONEY, nullable=False),
        sa.Column('raw', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_account_balances_observed_at', 'account_balances',
                    ['observed_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_account_balances_observed_at', table_name='account_balances')
    op.drop_table('account_balances')
