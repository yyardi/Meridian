"""add cancel columns to orders — the human cancel path's evidence trail

A cancel is the one order action this system has never performed, and its
venue response shape is UNVERIFIED (findings V21): there is no documented
cancel endpoint we trust, `/v1/orders` reads are 501/404 (V19), and the only
cancels ever done went through the venue's app. These columns exist so the
FIRST live cancel records everything — the ack, its latency (the last
unmeasured number in docs/math/write-latency.md), and the verbatim response
body that V21 will be written from.

Revision ID: b3e7a90c4d12
Revises: f4b8d21c9e07
Create Date: 2026-08-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b3e7a90c4d12'
down_revision: Union[str, None] = 'f4b8d21c9e07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # When the human clicked cancel. Set before the venue call, so an attempt
    # that never came back is still visible as an attempt.
    op.add_column('orders', sa.Column(
        'cancel_requested_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('orders', sa.Column(
        'cancel_http_status', sa.Integer(), nullable=True))
    # Submit-to-venue-ack round trip, and the venue's own processing time.
    op.add_column('orders', sa.Column(
        'cancel_latency_ms', sa.Numeric(precision=10, scale=2), nullable=True))
    op.add_column('orders', sa.Column(
        'cancel_venue_latency_ms', sa.Numeric(precision=10, scale=2), nullable=True))
    # The verbatim (truncated) response — the V21 evidence.
    op.add_column('orders', sa.Column('cancel_response', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('orders', 'cancel_response')
    op.drop_column('orders', 'cancel_venue_latency_ms')
    op.drop_column('orders', 'cancel_latency_ms')
    op.drop_column('orders', 'cancel_http_status')
    op.drop_column('orders', 'cancel_requested_at')
