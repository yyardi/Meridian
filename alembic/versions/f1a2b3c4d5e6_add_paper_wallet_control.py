"""add paper_wallet_control — the paper wallet's append-only control ledger

The ONLY mutations to the paper wallet (docs/math/paper-wallet-scoreboard.md
term 6): the $500+$500 birth seeds and any operator reset/resplit, each a dated
line, never edited or deleted. Per-fill P&L is folded live from
shadow_quote_fills (not materialised here); the fold's bankruptcy halt is
computed at read time. Shadow-only, no order path.

Revision ID: f1a2b3c4d5e6
Revises: a9d4e17c62b8
Create Date: 2026-09-03
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'f1a2b3c4d5e6'
down_revision: str | None = 'a9d4e17c62b8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'paper_wallet_control',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('effective_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('league', sa.String(length=8), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('amount', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('note', sa.String(length=500), nullable=False),
        sa.CheckConstraint("kind in ('seed','reset','resplit')",
                           name='ck_pwc_kind'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_pwc_league', 'paper_wallet_control', ['league'])
    op.create_index('ix_pwc_effective_at', 'paper_wallet_control',
                    ['effective_at'])


def downgrade() -> None:
    op.drop_index('ix_pwc_effective_at', table_name='paper_wallet_control')
    op.drop_index('ix_pwc_league', table_name='paper_wallet_control')
    op.drop_table('paper_wallet_control')
