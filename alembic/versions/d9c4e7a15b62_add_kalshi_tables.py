"""add kalshi_games, kalshi_contracts, kalshi_snapshots — the second venue

The venue-gap thesis (findings Q1) is currently measured against the ESPN
sportsbook opening line, which cannot be transacted. Kalshi is a second
CFTC-regulated venue with WNBA markets and public unauthenticated market-data
endpoints; recording it alongside Polymarket turns "is Polymarket mispriced?"
into a same-minute comparison of two transactable prices.

Three tables:

* `kalshi_games` — mapping between venues. No shared identifier exists, so the
  join key is the unordered ESPN team pair + local date, same as Polymarket.
* `kalshi_contracts` — change log of each contract's line and settlement terms
  verbatim (strike/settlement mismatches are basis risk and must be auditable).
* `kalshi_snapshots` — market_snapshots for Kalshi: mandatory captured_at,
  append-only, unique (ticker, captured_at) for a crash-idempotent recorder.

Revision ID: d9c4e7a15b62
Revises: e5c9f2a71d30
Create Date: 2026-08-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = 'd9c4e7a15b62'
down_revision: Union[str, None] = 'e5c9f2a71d30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'kalshi_games',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('game_key', sa.String(length=32), nullable=False),
        sa.Column('local_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('first_code', sa.String(length=8), nullable=False),
        sa.Column('second_code', sa.String(length=8), nullable=False),
        sa.Column('first_espn', sa.String(length=16), nullable=True),
        sa.Column('second_espn', sa.String(length=16), nullable=True),
        sa.Column('title', sa.String(length=200), nullable=True),
        sa.Column('polymarket_event_slug', sa.String(length=200), nullable=True),
        sa.Column('game_start_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('espn_game_id', sa.String(length=32), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('game_key'),
    )
    op.create_index('ix_kalshi_games_local_date', 'kalshi_games', ['local_date'])
    op.create_index(
        'ix_kalshi_games_polymarket_event_slug', 'kalshi_games', ['polymarket_event_slug']
    )

    op.create_table(
        'kalshi_contracts',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('captured_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ticker', sa.String(length=64), nullable=False),
        sa.Column('event_ticker', sa.String(length=64), nullable=False),
        sa.Column('series_ticker', sa.String(length=32), nullable=False),
        sa.Column('game_key', sa.String(length=32), nullable=False),
        sa.Column('market_type', sa.String(length=16), nullable=False),
        sa.Column('yes_sub_title', sa.String(length=200), nullable=True),
        sa.Column('floor_strike', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('cap_strike', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('strike_type', sa.String(length=32), nullable=True),
        sa.Column('rules_primary', sa.Text(), nullable=True),
        sa.Column('rules_secondary', sa.Text(), nullable=True),
        sa.Column('open_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('close_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expected_expiration_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('raw', JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ticker', 'captured_at', name='uq_kalshi_contract_ticker_time'),
    )
    op.create_index(
        'ix_kalshi_contracts_ticker_time', 'kalshi_contracts', ['ticker', 'captured_at']
    )
    op.create_index('ix_kalshi_contracts_game_key', 'kalshi_contracts', ['game_key'])

    op.create_table(
        'kalshi_snapshots',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('captured_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ticker', sa.String(length=64), nullable=False),
        sa.Column('event_ticker', sa.String(length=64), nullable=False),
        sa.Column('series_ticker', sa.String(length=32), nullable=False),
        sa.Column('game_key', sa.String(length=32), nullable=False),
        sa.Column('market_type', sa.String(length=16), nullable=False),
        sa.Column('floor_strike', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('yes_bid', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('yes_ask', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('last_price', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('yes_bid_size', sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column('yes_ask_size', sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column('volume', sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column('open_interest', sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=True),
        sa.Column('result', sa.String(length=16), nullable=True),
        sa.Column('raw', JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ticker', 'captured_at', name='uq_kalshi_snapshot_ticker_time'),
    )
    op.create_index('ix_kalshi_snapshots_captured_at', 'kalshi_snapshots', ['captured_at'])
    op.create_index(
        'ix_kalshi_snapshots_ticker_time', 'kalshi_snapshots', ['ticker', 'captured_at']
    )
    op.create_index('ix_kalshi_snapshots_game_key', 'kalshi_snapshots', ['game_key'])


def downgrade() -> None:
    op.drop_table('kalshi_snapshots')
    op.drop_table('kalshi_contracts')
    op.drop_table('kalshi_games')
