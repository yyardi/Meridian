"""add policy to shadow_quote_fills and quote_v2_observations (GRIDIRON A/B)

The parallel policy A/B (docs/gridiron/policy-variants.md) runs five arms as five
engines sharing the same image on the same board. They share engine_commit, so
engine_commit cannot distinguish them — the `policy` stamp is what makes a fill or
observation name its arm. Additive + nullable (pre-A/B rows carry NULL; the
variant engines always stamp it).

Revision ID: e5c2f8a1b6d3
Revises: c3e8a1d6b4f2
Create Date: 2026-09-03
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'e5c2f8a1b6d3'
down_revision: str | None = 'c3e8a1d6b4f2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('shadow_quote_fills',
                  sa.Column('policy', sa.String(length=16), nullable=True))
    op.add_column('quote_v2_observations',
                  sa.Column('policy', sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column('quote_v2_observations', 'policy')
    op.drop_column('shadow_quote_fills', 'policy')
