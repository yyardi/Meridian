"""add predictions.damped_probability — the ladder-sigma damping shadow arm

The damped rung probability (ladder re-priced at the published
finals-residual sigma 19.00, implied mean preserved) lands BESIDE the
undamped, replacing nothing. NULL before activation and wherever no ladder
could be fitted. docs/math/ladder-sigma-damping.md, activation ruling
2026-08-25.

Revision ID: c4e7f2a81d59
Revises: f3a8c1d92e47
Create Date: 2026-08-25
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'c4e7f2a81d59'
down_revision: str | None = 'f3a8c1d92e47'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('predictions', sa.Column(
        'damped_probability', sa.Numeric(precision=6, scale=4), nullable=True))


def downgrade() -> None:
    op.drop_column('predictions', 'damped_probability')
