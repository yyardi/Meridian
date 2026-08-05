"""add service_heartbeats — one upserted row per writer, beaten every cycle

B11's fix. "Dead for 23 hours" and "idle between games" were indistinguishable
because every writer has a schedule on which silence is legitimate. A row that
is upserted unconditionally every cycle — game or no game — makes staleness
mean exactly one thing: the process is not running.

One row per service, updated in place: the table never grows, so the egress
cost is one tiny upsert per cycle. `beat_at` defaults to the database clock so
a container with a skewed clock cannot report itself alive into the future.

Revision ID: b7e2c9d41f80
Revises: a1f3c7d92b40
Create Date: 2026-08-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b7e2c9d41f80'
down_revision: Union[str, None] = 'a1f3c7d92b40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'service_heartbeats',
        sa.Column('service', sa.String(length=64), nullable=False),
        sa.Column('beat_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('interval_seconds', sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column('cycle_seconds', sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column('rows_written', sa.Integer(), nullable=True),
        sa.Column('rows_total', sa.BigInteger(), nullable=True),
        sa.Column('game_live', sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint('service'),
    )


def downgrade() -> None:
    op.drop_table('service_heartbeats')
