"""add pulse_decisions capped-size annotation — shadow caps annotate, never bind

Operator decision 2026-08-21: in shadow mode the engine records the model's
FULL desired size on every entry; when an exposure cap would have bound in
live mode, these columns carry the live-faithful capped size (0 = the cap
would have blocked entirely — the 2026-08-20 starvation shape). NULL = no
cap would have bound. Sizing semantics changed mid-accrual; the dated note
in docs/math/pulse-live.md carries the pre/post split marker.

Revision ID: b8d2f5a91c37
Revises: 7fe2c9d40b18
Create Date: 2026-08-21
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'b8d2f5a91c37'
down_revision: str | None = '7fe2c9d40b18'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('pulse_decisions', sa.Column(
        'capped_stake_usd', sa.Numeric(precision=12, scale=4), nullable=True))
    op.add_column('pulse_decisions', sa.Column(
        'capped_contracts', sa.Numeric(precision=18, scale=4), nullable=True))


def downgrade() -> None:
    op.drop_column('pulse_decisions', 'capped_contracts')
    op.drop_column('pulse_decisions', 'capped_stake_usd')
