"""add orders table for human-confirmed real orders

The CHECK constraint is the point of this migration, not the table.

`ck_orders_accepted_requires_human` makes an accepted order in any mode other
than HUMAN_CONFIRM unrepresentable in the database. It is what buys back the
safety guarantee spent by giving the system a POST path to the venue at all:
before this, no order could be placed because no code path existed. Now one
does, and the guarantee has to live somewhere that a forgotten `if` cannot
bypass.

Revision ID: a1f3c7d92b40
Revises: 7c1a9f4b2e10
Create Date: 2026-08-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a1f3c7d92b40'
down_revision: Union[str, None] = '7c1a9f4b2e10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'orders',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('idempotency_key', sa.String(length=120), nullable=False),
        sa.Column('mode', sa.String(length=20), nullable=False),
        sa.Column('market_slug', sa.String(length=200), nullable=False),
        sa.Column('event_slug', sa.String(length=200), nullable=True),
        sa.Column('sports_market_type', sa.String(length=64), nullable=True),
        sa.Column('side', sa.String(length=8), nullable=False),
        sa.Column('order_type', sa.String(length=32), nullable=False),
        sa.Column('limit_price', sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column('quantity', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('accepted', sa.Boolean(), nullable=False,
                  server_default=sa.text('false')),
        sa.Column('venue_order_id', sa.String(length=120), nullable=True),
        sa.Column('venue_status', sa.String(length=64), nullable=True),
        sa.Column('http_status', sa.Integer(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('submit_latency_ms', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('venue_latency_ms', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('market_bid', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('market_ask', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('would_rest', sa.Boolean(), nullable=True),
        sa.Column('shadow_order_id', sa.BigInteger(), nullable=True),
        sa.Column('prediction_id', sa.BigInteger(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key'),
        # The invariant. Enforced by Postgres on every write from every process.
        sa.CheckConstraint(
            "accepted = false OR mode = 'HUMAN_CONFIRM'",
            name='ck_orders_accepted_requires_human',
        ),
        # Market orders are unrepresentable in core/executor.py. Keep them
        # unrepresentable in the data, so code and storage cannot drift.
        sa.CheckConstraint(
            "order_type = 'ORDER_TYPE_LIMIT'",
            name='ck_orders_limit_only',
        ),
    )
    op.create_index('ix_orders_submitted_at', 'orders', ['submitted_at'])
    op.create_index('ix_orders_market_slug', 'orders', ['market_slug'])
    op.create_index('ix_orders_mode_accepted', 'orders', ['mode', 'accepted'])


def downgrade() -> None:
    op.drop_index('ix_orders_mode_accepted', table_name='orders')
    op.drop_index('ix_orders_market_slug', table_name='orders')
    op.drop_index('ix_orders_submitted_at', table_name='orders')
    op.drop_table('orders')
