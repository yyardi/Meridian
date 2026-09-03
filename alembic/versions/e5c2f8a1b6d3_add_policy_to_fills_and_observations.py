"""add policy to shadow_quote_fills and quote_v2_observations (GRIDIRON A/B)

The parallel policy A/B (docs/gridiron/policy-variants.md) runs five arms as five
engines sharing the same image on the same board. They share engine_commit, so
engine_commit cannot distinguish them — the `policy` stamp is what makes a fill or
observation name its arm. Additive + nullable (pre-A/B rows carry NULL; the
variant engines always stamp it).

Revision ID: e5c2f8a1b6d3
Revises: b7e2f91a4c33
Create Date: 2026-09-03

Re-parented from c3e8a1d6b4f2 onto b7e2f91a4c33 (kalshi_start_time_source) after
rebasing onto main: main's kalshi migration and this one both branched off
c3e8a1d6b4f2, which would leave two alembic heads. This column-add is independent
of the kalshi change, so a linear re-chain (not a merge migration) is the right
fix; the policy column lands after the kalshi column.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'e5c2f8a1b6d3'
down_revision: str | None = 'b7e2f91a4c33'
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
