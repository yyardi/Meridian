"""kalshi_games.venue_occurrence_time — the only clock we get for unquoted leagues

College coverage (NCAAF) records leagues we do not quote, so no Polymarket
slug exists and `game_start_time` stays NULL — which would leave every
college game unpollable forever while the log reported a cheerful zero.
Kalshi's `occurrence_datetime` is the only clock the venue offers, but it is
NOT a tip time: measured 2026-09-03 it runs **kickoff + 3h** in both college
(MASS/RUTG: ESPN 22:00Z vs venue 01:00Z) and the NFL (NE/SEA: ESPN 00:20Z vs
venue 03:20Z). Storing it in `game_start_time` would put an end-stamp in a
start column, so it gets its own honestly-named column and the poll window
does the offset arithmetic explicitly.

Revision ID: b7e2f91a4c33
Revises: c3e8a1d6b4f2
Create Date: 2026-09-03
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'b7e2f91a4c33'
down_revision: str | None = 'c3e8a1d6b4f2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('kalshi_games', sa.Column(
        'venue_occurrence_time', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('kalshi_games', 'venue_occurrence_time')
