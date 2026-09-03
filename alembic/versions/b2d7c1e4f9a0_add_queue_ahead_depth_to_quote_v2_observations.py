"""add queue-ahead depth at our quote price to quote_v2_observations

The fill-probability surface P(fill within h | distance-from-touch, queue-ahead)
needs BOTH axes on the same row: leaning inside the touch moves them together
(shortens the queue, lowers reach), and a fill rate without queue depth cannot
tell "the market never reached us" from "we stood behind fifteen thousand
contracts". The observation row carried only prices (Quote = value+currency, no
size), so this adds the queue-ahead size AT our own quote price on each side,
plus the fetch instant so the sample's staleness is visible on every row.

Option 1 (manager 2026-09-03): the exact qty at our quote price, not a
top-of-book proxy — same cost once the book is fetched, and the honest object.
Sampled for QUOTED markets only, on a bounded cadence, off the decision path
(record_cycle reads _standing, never writes it; proof 3). NOT a book_levels
cross-join (D's point-in-time hazard) — the observation's own fresh fetch.

Additive and nullable per amendment 12 (ADD only; nothing the frozen binary's
quoting touches is altered). The staleness bound / refresh interval are D's
convention, carried as named constants in engine_v2 so their answer is a
one-line change, not a migration.

Revision ID: b2d7c1e4f9a0
Revises: a1c9e5f70b23
Create Date: 2026-09-03
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'b2d7c1e4f9a0'
down_revision: str | None = 'a1c9e5f70b23'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('quote_v2_observations',
                  sa.Column('our_bid_qty', sa.Numeric(precision=18, scale=4),
                            nullable=True))
    op.add_column('quote_v2_observations',
                  sa.Column('our_ask_qty', sa.Numeric(precision=18, scale=4),
                            nullable=True))
    op.add_column('quote_v2_observations',
                  sa.Column('depth_fetched_at', sa.DateTime(timezone=True),
                            nullable=True))


def downgrade() -> None:
    op.drop_column('quote_v2_observations', 'depth_fetched_at')
    op.drop_column('quote_v2_observations', 'our_ask_qty')
    op.drop_column('quote_v2_observations', 'our_bid_qty')
