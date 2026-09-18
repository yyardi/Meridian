"""orders.avg_fill_price — the price the venue says a fill cost

The fill test protocol (docs/math/ladder-fill-test.md) records, per leg, "at
what price?". The `orders` table could answer "what limit did we send" and
"how many filled", but not what the venue reports we paid: the activities
feed and the synchronous create-order reply both carry `avgPx.value`, and
nothing stored it. The ARB tab's send (2026-09-18) reads it off the reply;
the fill watcher reads it off the feed. One nullable column, YES frame like
`limit_price`, NULL meaning "not reported" and never "zero".

Additive and IF NOT EXISTS: a container that already ran this must skip it,
not die (the 2026-09-13 DuplicateTable crash-loop), and nothing downstream
depends on the column being absent.

Revision ID: c7d2e9f14b60
Revises: b4e9f1c73d85
Create Date: 2026-09-18
"""
from collections.abc import Sequence

from alembic import op

revision: str = 'c7d2e9f14b60'
down_revision: str | None = 'b4e9f1c73d85'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS avg_fill_price numeric(6, 4)")


def downgrade() -> None:
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS avg_fill_price")
