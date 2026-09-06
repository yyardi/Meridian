"""add commit to service_heartbeats (the deployed-code audit)

Every heartbeat-writing service reports the git commit it is running
(MERIDIAN_ENGINE_COMMIT, baked by the Dockerfile ARG GIT_COMMIT). The audit
compares it against a reference to catch a container silently running code older
than main — the failure class behind three of the night's bugs, the dangerous
one being a stale image that reports a false zero (indistinguishable from a quiet
venue). NULL = UNKNOWN PROVENANCE (built without the arg), never "fine".

Additive + nullable; every service upserts it on its next beat.

Revision ID: d4f1a2b7c9e8
Revises: c3e8a1d6b4f2
Create Date: 2026-09-03
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'd4f1a2b7c9e8'
down_revision: str | None = 'c3e8a1d6b4f2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('service_heartbeats',
                  sa.Column('commit', sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column('service_heartbeats', 'commit')
