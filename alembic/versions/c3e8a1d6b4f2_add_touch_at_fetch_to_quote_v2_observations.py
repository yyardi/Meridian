"""add touch-at-fetch (depth_best_bid/ask) to quote_v2_observations

The queue-ahead validity gate is PRICE IDENTITY, not elapsed time (D, 2026-09-03):
WNBA in-play touch survival is median 2s / p90 17s, so no time bound separates a
fresh queue-ahead sample from a dead one. The exact test is whether the touch has
moved since the sample: these two columns carry the touch AT the sample's fetch
(best bid / best ask in the fetched book), and the consumer compares them to
best_bid/best_ask (the touch at observation) — same -> the queue-ahead is exactly
valid at any age; different -> unusable at any age. depth_fetched_at +
DEPTH_QUEUE_STALENESS_MAX_SECONDS remain only as the secondary backstop.

Follows the original queue-ahead columns (b2d7c1e4f9a0); additive + nullable per
amendment 12.

Revision ID: c3e8a1d6b4f2
Revises: b2d7c1e4f9a0
Create Date: 2026-09-03
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'c3e8a1d6b4f2'
down_revision: str | None = 'b2d7c1e4f9a0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('quote_v2_observations',
                  sa.Column('depth_best_bid', sa.Numeric(precision=6, scale=4),
                            nullable=True))
    op.add_column('quote_v2_observations',
                  sa.Column('depth_best_ask', sa.Numeric(precision=6, scale=4),
                            nullable=True))


def downgrade() -> None:
    op.drop_column('quote_v2_observations', 'depth_best_ask')
    op.drop_column('quote_v2_observations', 'depth_best_bid')
