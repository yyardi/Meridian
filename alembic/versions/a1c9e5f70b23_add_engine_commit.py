"""add engine_commit to shadow_quote_fills and quote_v2_observations

Amendment 12 engine-identity: every fill and observation row stamps the writing
binary's git commit (the GIT_COMMIT build-arg baked into the image; the engine
fails to start if it is absent). Makes "one binary per cohort" verifiable in the
data rather than a deployment-history narrative — a cohort gate asserts a single
engine_commit across its rows, and a stray row becomes detectable. Additive and
nullable (old rows carry NULL; the writer never writes NULL). Schema-additive
per amendment 12 (ADD only; nothing the frozen binary touches is altered).

Revision ID: a1c9e5f70b23
Revises: d5b18e2c40a7
Create Date: 2026-09-03
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'a1c9e5f70b23'
down_revision: str | None = 'd5b18e2c40a7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('shadow_quote_fills',
                  sa.Column('engine_commit', sa.String(length=40), nullable=True))
    op.add_column('quote_v2_observations',
                  sa.Column('engine_commit', sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column('quote_v2_observations', 'engine_commit')
    op.drop_column('shadow_quote_fills', 'engine_commit')
