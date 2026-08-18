"""add pulse_decisions.estimates_version — which estimate set priced the row

'v1' (pregame price + score/clock + league sigma) or 'v2' (per-matchup fitted
volatility and the blended totals anchor, core/pulse/team_form.py). Recorded
per ROW, not per engine mode: a v2-mode engine whose form data was stale
prices with the v1 values and its rows say so, which is what keeps two model
generations from blending in a performance query (the era-separation lesson,
PR #23's whole point).

Revision ID: f7c3d9e04a62
Revises: e6f2a8b93c51
Create Date: 2026-08-18
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'f7c3d9e04a62'
down_revision: str | None = 'e6f2a8b93c51'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('pulse_decisions', sa.Column(
        'estimates_version', sa.String(length=4),
        nullable=False, server_default='v1'))


def downgrade() -> None:
    op.drop_column('pulse_decisions', 'estimates_version')
