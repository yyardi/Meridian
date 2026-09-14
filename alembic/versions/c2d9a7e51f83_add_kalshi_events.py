"""add kalshi_events + kalshi_event_snapshots

The non-sports Kalshi board (core/kalshi/events_recorder.py). A SIBLING of
kalshi_games, not a widening of it: kalshi_games is keyed on an ESPN team pair
plus a local date with first_code/second_code NOT NULL, and its game_start_time
is copied from our own Polymarket snapshots — so a weather, crypto or
challenger-tennis event, which has neither a team pair nor a Polymarket twin,
cannot be represented there at all. Identity here is the venue's own
(market_ticker, captured_at), grouped by event_ticker.

Both tables are append-only ON CHANGE. price_ranges/price_level_structure/
min_tick are carried because the tick grid is not 1c everywhere (four grids
over the 107,599 open markets on 2026-09-14, finest step $0.0010), and
mutually_exclusive because 4,377 of 11,696 open events are ladders whose legs
sum to 1. ticker_suffix is the leg code (a tennis event is two markets, one
per player) and fee_type/fee_multiplier are stamped on every snapshot because
the venue publishes DATED per-series fee transitions.

Revision ID: c2d9a7e51f83
Revises: b6e4d2f7a913
Create Date: 2026-09-14
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "c2d9a7e51f83"
down_revision: str = "b6e4d2f7a913"
branch_labels = None
depends_on = None

PRICE = sa.Numeric(6, 4)
QTY = sa.Numeric(18, 4)
#: NOT Numeric(8,2) like `Points`: KXBTCD strikes at 67099.99 today.
STRIKE = sa.Numeric(18, 6)
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "kalshi_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("captured_at", TS, nullable=False),
        sa.Column("series_ticker", sa.String(length=64), nullable=False),
        sa.Column("event_ticker", sa.String(length=128), nullable=False),
        sa.Column("market_ticker", sa.String(length=128), nullable=False),
        sa.Column("ticker_suffix", sa.String(length=64), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("event_title", sa.Text(), nullable=True),
        sa.Column("yes_sub_title", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("strike_type", sa.String(length=32), nullable=True),
        sa.Column("floor_strike", STRIKE, nullable=True),
        sa.Column("cap_strike", STRIKE, nullable=True),
        sa.Column("custom_strike", JSONB(), nullable=True),
        sa.Column("open_time", TS, nullable=True),
        sa.Column("close_time", TS, nullable=True),
        sa.Column("expected_expiration_time", TS, nullable=True),
        sa.Column("poll_anchor", TS, nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("market_type", sa.String(length=32), nullable=True),
        sa.Column("mutually_exclusive", sa.Boolean(), nullable=True),
        sa.Column("price_level_structure", sa.String(length=48), nullable=True),
        sa.Column("price_ranges", JSONB(), nullable=True),
        sa.Column("min_tick", PRICE, nullable=True),
        sa.Column("rules_primary", sa.Text(), nullable=True),
        sa.Column("rules_secondary", sa.Text(), nullable=True),
        sa.Column("settlement_sources", JSONB(), nullable=True),
        sa.Column("raw", JSONB(), nullable=True),
        sa.Column("created_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("market_ticker", "captured_at", name="uq_kalshi_event_market_time"),
    )
    op.create_index("ix_kalshi_events_event_ticker", "kalshi_events", ["event_ticker"])
    op.create_index(
        "ix_kalshi_events_series_anchor", "kalshi_events", ["series_ticker", "poll_anchor"]
    )

    op.create_table(
        "kalshi_event_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("captured_at", TS, nullable=False),
        sa.Column("market_ticker", sa.String(length=128), nullable=False),
        sa.Column("event_ticker", sa.String(length=128), nullable=False),
        sa.Column("series_ticker", sa.String(length=64), nullable=False),
        sa.Column("yes_bid", PRICE, nullable=True),
        sa.Column("yes_ask", PRICE, nullable=True),
        sa.Column("yes_bid_size", QTY, nullable=True),
        sa.Column("yes_ask_size", QTY, nullable=True),
        sa.Column("last_price", PRICE, nullable=True),
        sa.Column("volume", QTY, nullable=True),
        sa.Column("open_interest", QTY, nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("result", sa.String(length=16), nullable=True),
        sa.Column("fee_type", sa.String(length=48), nullable=True),
        sa.Column("fee_multiplier", sa.Numeric(10, 4), nullable=True),
        sa.Column("book", JSONB(), nullable=True),
        sa.Column("raw", JSONB(), nullable=True),
        sa.Column("created_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "market_ticker", "captured_at", name="uq_kalshi_event_snapshot_market_time"
        ),
    )
    op.create_index(
        "ix_kalshi_event_snapshots_captured_at", "kalshi_event_snapshots", ["captured_at"]
    )
    op.create_index(
        "ix_kalshi_event_snapshots_event_ticker", "kalshi_event_snapshots", ["event_ticker"]
    )
    op.create_index(
        "ix_kalshi_event_snapshots_series_time",
        "kalshi_event_snapshots",
        ["series_ticker", "captured_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_kalshi_event_snapshots_series_time", table_name="kalshi_event_snapshots")
    op.drop_index("ix_kalshi_event_snapshots_event_ticker", table_name="kalshi_event_snapshots")
    op.drop_index("ix_kalshi_event_snapshots_captured_at", table_name="kalshi_event_snapshots")
    op.drop_table("kalshi_event_snapshots")
    op.drop_index("ix_kalshi_events_series_anchor", table_name="kalshi_events")
    op.drop_index("ix_kalshi_events_event_ticker", table_name="kalshi_events")
    op.drop_table("kalshi_events")
