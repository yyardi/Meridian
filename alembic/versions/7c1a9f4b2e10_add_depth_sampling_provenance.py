"""add depth sampling provenance

Two columns that exist so the live recorder's sparsity is auditable rather
than implicit:

* `market_snapshots.book_tier` — which depth tier the row was sampled under
  ('near' | 'deep' | NULL). Distinguishes "no resting size" from "we did not
  look", which are otherwise the same absence.
* `book_levels.captured_at` — when the book call returned. Once depth is
  sampled on a slower loop than price, the parent snapshot's timestamp is no
  longer the depth's timestamp, and the depth-signal question is about
  ordering.

Both nullable, so the backfill is a no-op and existing rows stay honest: NULL
means "written before the tiered sampler existed", not "not sampled".

Revision ID: 7c1a9f4b2e10
Revises: 50bde990beba
Create Date: 2026-08-02 19:20:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7c1a9f4b2e10'
down_revision: Union[str, None] = '50bde990beba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'market_snapshots',
        sa.Column('book_tier', sa.String(length=8), nullable=True),
    )
    op.add_column(
        'book_levels',
        sa.Column('captured_at', sa.DateTime(timezone=True), nullable=True),
    )
    # The depth-signal query shape: one market's resting size in time order.
    op.create_index(
        'ix_book_levels_captured_at', 'book_levels', ['captured_at'], unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_book_levels_captured_at', table_name='book_levels')
    op.drop_column('book_levels', 'captured_at')
    op.drop_column('market_snapshots', 'book_tier')
