"""partial indexes so a market with no tipoff answers in ~1ms, not ~400ms

The picks and games tipoff lookups probe `LIMIT 1` for any snapshot row with a
non-null game_start_time. A market that HAS such a row answers off the slug
index in ~2ms. A market that has NONE — futures/series markets, or any market
whose snapshots never carry a tipoff — forces a scan of every one of its rows
in every partition before the planner can say "no row": measured 0.39s cold /
0.16s warm per slug on a 50k-row synthetic all-NULL slug, repeated on every
page load because a miss caches nothing. A handful of such slugs in the
prediction batch is the difference between the 0.46s /api/picks measured on
the mirror and the ~4.75s measured in production (2026-08-24).

A partial index contains only qualifying rows, so for an all-NULL slug the
probe is a pure B-tree miss regardless of how many NULL rows the table holds:
~1ms measured against the same synthetic slug. Two indexes because the picks
path keys on market_slug and the games path on event_slug.

NOTE for the deploy: plain CREATE INDEX takes a write-blocking lock per
partition while it builds (~tens of seconds on the big current-month
partition). Run it off-slate — the 200ms recorder's inserts stall for the
build, they are not lost.

Revision ID: f3a8c1d92e47
Revises: b8d2f5a91c37
Create Date: 2026-08-24
"""
from collections.abc import Sequence

from alembic import op

revision: str = 'f3a8c1d92e47'
down_revision: str | None = 'b8d2f5a91c37'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        'ix_snapshots_slug_has_start', 'market_snapshots', ['market_slug'],
        postgresql_where='game_start_time IS NOT NULL')
    op.create_index(
        'ix_snapshots_event_has_start', 'market_snapshots', ['event_slug'],
        postgresql_where='game_start_time IS NOT NULL')


def downgrade() -> None:
    op.drop_index('ix_snapshots_event_has_start', table_name='market_snapshots')
    op.drop_index('ix_snapshots_slug_has_start', table_name='market_snapshots')
