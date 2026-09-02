"""add source_captured_at to quote_v2_observations

Raw provenance: the upstream recorder snapshot's stamp
(`market_snapshots.captured_at`) carried through alongside the quoter's own
`observed_at`. NOT venue truth and NOT a detector clock — the detector and every
gate read `observed_at` only (docs/math/quote-v2-observation-schema.md). It
exists so the wrong-clock regression (`observed_at == source_captured_at`
everywhere) has an assertable signature the integrity replay alone cannot see,
for quoter-vs-upstream latency decomposition, and as the amendment-9
proxy-validation join key. Nullable and additive; the table holds no forward
rows yet (recording binary not deployed), so this is a pure add-column.

Revision ID: e1a7c3f60d94
Revises: d4e8b1c60f39
Create Date: 2026-09-02
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'e1a7c3f60d94'
down_revision: str | None = 'd4e8b1c60f39'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'quote_v2_observations',
        sa.Column('source_captured_at', sa.DateTime(timezone=True),
                  nullable=True))


def downgrade() -> None:
    op.drop_column('quote_v2_observations', 'source_captured_at')
