"""add retention_log — the archive receipts the no-data-loss invariant rests on

Only this small table travels through Alembic. The partitioning conversion
itself is deliberately NOT a migration: `alembic upgrade head` runs on every
container start against both databases, and rewriting a 2+ GB table implicitly
— against Supabase at 395 of 500 MB — is not a thing a container start should
be able to do. See core/retention.py.

Revision ID: c8f1a4d27e93
Revises: b3e7a90c4d12
Create Date: 2026-08-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c8f1a4d27e93'
down_revision: Union[str, None] = 'b3e7a90c4d12'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'retention_log',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('table_name', sa.String(length=64), nullable=False),
        sa.Column('partition_name', sa.String(length=80), nullable=False),
        sa.Column('month_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('rows_archived', sa.BigInteger(), nullable=False),
        sa.Column('dump_path', sa.Text(), nullable=False),
        sa.Column('dump_bytes', sa.BigInteger(), nullable=False),
        sa.Column('dump_sha256', sa.String(length=64), nullable=False),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('detached_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('dropped_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('partition_name', name='uq_retention_partition'),
    )


def downgrade() -> None:
    op.drop_table('retention_log')
