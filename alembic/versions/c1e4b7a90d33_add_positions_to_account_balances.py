"""add positions + positions_read_ok to account_balances

The round trip was lossy, and lossy in the worst direction. `AccountSnapshot`
grew `positions` and `positions_read_ok` when equity display was added, but
`record()` never persisted them and `latest()` never reconstructed them — so a
stored snapshot came back with `positions=()` and `positions_read_ok=False`.

That is not "no positions". It is **"the positions read failed"**. So the
poller logged `equity=23.2204 n_positions=1` while the page served
`positions_read_ok: false, positions: [], equity == bankroll` in the same
minute, because `current()` prefers a fresh stored row over a live fetch.

`positions_read_ok` is a stored column rather than `len(positions) > 0`
because an empty book and an unread book are different facts, and the entire
display turns on telling them apart.

Revision ID: c1e4b7a90d33
Revises: f7c3d9e04a62
Create Date: 2026-08-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'c1e4b7a90d33'
down_revision: Union[str, None] = 'f7c3d9e04a62'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('account_balances',
                  sa.Column('positions', postgresql.JSONB(astext_type=sa.Text()),
                            nullable=True))
    # Existing rows predate positions entirely: false is the truthful value for
    # them, because nothing read a position book at the time they were written.
    op.add_column('account_balances',
                  sa.Column('positions_read_ok', sa.Boolean(), nullable=False,
                            server_default=sa.text('false')))


def downgrade() -> None:
    op.drop_column('account_balances', 'positions_read_ok')
    op.drop_column('account_balances', 'positions')
