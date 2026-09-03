"""add touch-at-fill to shadow_quote_fills (GRIDIRON A/B; gates FLATTEN)

best_bid_at_fill / best_ask_at_fill are the TOUCH of the SAME observation the
fill was judged against — recorded from that observation, never re-joined from
the tape. They are the phantom test: a bid fill is real iff best_ask_at_fill <=
quote_price, an ask fill iff best_bid_at_fill >= quote_price; the mid-cross rule
books the rest as phantoms. For FLATTEN this is a correctness precondition, not a
classification field: the inventory counter moves only on real fills, so a wrong
or absent touch makes the engine lean to flatten a position it does not hold.

Additive + nullable (rows written before touch-at-fill carry NULL; the recording
engines stamp both). Distinct from c3e8a1d6b4f2 (touch-at-FETCH on the
observation) — that is the book when observed; this is the book when the fill was
judged.

Revision ID: d7f4a2c9e5b1
Revises: e5c2f8a1b6d3
Create Date: 2026-09-03
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'd7f4a2c9e5b1'
down_revision: str | None = 'e5c2f8a1b6d3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('shadow_quote_fills',
                  sa.Column('best_bid_at_fill', sa.Numeric(6, 4), nullable=True))
    op.add_column('shadow_quote_fills',
                  sa.Column('best_ask_at_fill', sa.Numeric(6, 4), nullable=True))


def downgrade() -> None:
    op.drop_column('shadow_quote_fills', 'best_ask_at_fill')
    op.drop_column('shadow_quote_fills', 'best_bid_at_fill')
