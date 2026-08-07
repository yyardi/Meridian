"""pre-authorized exits, fill state, and the amended safety constraint

Safety amendment (user-approved 2026-08-05)
-------------------------------------------
HUMAN_CONFIRM gains a **pre-authorized** variant: an order whose market, side,
price and quantity were ALL fixed by a human click, which the system may submit
later on a defined trigger (the entry's fill) and may do nothing else with. The
first and only use is the attached exit.

`orders_autonomous` keeps its meaning — "an order whose terms no human
specified" — and must remain 0. A pre-authorized exit does not count against
it: every one of its terms was typed or accepted by a human on the ticket; only
the *timing* is the machine's.

Two constraints now carry the invariant:

* `ck_orders_accepted_requires_human` — unchanged. An accepted order in any
  mode other than HUMAN_CONFIRM stays unrepresentable.
* `ck_orders_pre_authorized_requires_human` — new. A pre-authorized order in
  any mode other than HUMAN_CONFIRM is unrepresentable too, so the flag can
  never be used to smuggle a machine-termed order into some future mode.

`pending_exits` is the stored trigger: one row per attached exit, linked to its
entry by **our** order id (explicit, one-to-one, never matched by
market/price/size similarity). The exit's market slug and price are copied at
click time and never re-derived at submit.

Revision ID: f4b8d21c9e07
Revises: d9c4e7a15b62
Create Date: 2026-08-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f4b8d21c9e07'
down_revision: Union[str, None] = 'd9c4e7a15b62'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- orders: the pre-authorized flag and venue-truth fill state --------- #
    op.add_column('orders', sa.Column(
        'pre_authorized', sa.Boolean(), nullable=False,
        server_default=sa.text('false'),
    ))
    # Venue truth, written only by the fill watcher: OPEN / PARTIAL / FILLED /
    # CANCELLED / EXPIRED. NULL means "never reconciled" — distinct from OPEN,
    # which means "reconciled and confirmed still resting".
    op.add_column('orders', sa.Column('fill_status', sa.String(length=16), nullable=True))
    op.add_column('orders', sa.Column(
        'filled_quantity', sa.Numeric(precision=18, scale=4), nullable=True))
    op.add_column('orders', sa.Column(
        'fill_checked_at', sa.DateTime(timezone=True), nullable=True))

    op.create_check_constraint(
        'ck_orders_pre_authorized_requires_human',
        'orders',
        "pre_authorized = false OR mode = 'HUMAN_CONFIRM'",
    )

    # --- pending_exits: the stored trigger ---------------------------------- #
    op.create_table(
        'pending_exits',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        # The one and only link to the entry. Explicit, by our order id.
        sa.Column('entry_order_id', sa.BigInteger(), nullable=False),
        # Copied from the entry row at click time, never re-looked-up.
        sa.Column('market_slug', sa.String(length=200), nullable=False),
        sa.Column('outcome', sa.String(length=8), nullable=False),
        # YES-frame price.value, immutable — sent exactly as stored.
        sa.Column('limit_price', sa.Numeric(precision=6, scale=4), nullable=False),
        # What the human actually typed, in the cost frame they saw.
        sa.Column('typed_price', sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column('state', sa.String(length=16), nullable=False,
                  server_default=sa.text("'PENDING'")),
        sa.Column('submitted_order_id', sa.BigInteger(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['entry_order_id'], ['orders.id']),
        sa.ForeignKeyConstraint(['submitted_order_id'], ['orders.id']),
        # One exit per entry — the one-to-one is structural, not a convention.
        sa.UniqueConstraint('entry_order_id', name='uq_pending_exit_entry'),
        sa.CheckConstraint(
            "state in ('PENDING','SUBMITTED','FAILED','DELETED')",
            name='ck_pending_exit_state',
        ),
        sa.CheckConstraint(
            "outcome in ('YES','NO')",
            name='ck_pending_exit_outcome',
        ),
    )
    op.create_index('ix_pending_exits_state', 'pending_exits', ['state'])


def downgrade() -> None:
    op.drop_index('ix_pending_exits_state', table_name='pending_exits')
    op.drop_table('pending_exits')
    op.drop_constraint('ck_orders_pre_authorized_requires_human', 'orders', type_='check')
    op.drop_column('orders', 'fill_checked_at')
    op.drop_column('orders', 'filled_quantity')
    op.drop_column('orders', 'fill_status')
    op.drop_column('orders', 'pre_authorized')
