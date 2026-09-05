"""add cfb_game_map: the bridge from ESPN game state to venue prices

Recording football game state was not enough. `espn_cfb_live_plays.game_id`
is an ESPN event id ('401856635'); `market_snapshots.game_id` is a venue id
('16450'); overlap is ZERO. And the obvious fallback fails too — `home`/`away`
in the plays table are ESPN NUMERIC TEAM IDS ('8', '2453'), while our slugs
carry team codes ('cfb-ntx-ind-2026-09-05'). So a model has inputs and prices
and no way to attach one to the other.

WHY THIS IS A TABLE AND NOT A DERIVED VIEW
-------------------------------------------
The standing rule is "store raw, derive in shared code", and features like
`spread_time` stay derived. But the correct line is narrower: **derive what is
a pure function of stored columns; MATERIALISE what required an external call
or a fuzzy match.** Game identity and division are the second kind — they need
ESPN's scoreboard and a date tolerance, they are not recomputable from our own
data, and if every consumer re-derives the fuzzy join then every consumer gets
a slightly different answer. Stored once, with the method recorded.

`match_method` and `match_confidence` are load-bearing, not provenance
decoration: **a mispaired game is silent and unrecoverable downstream** — the
model would train one game's state against another game's prices and every
validation would pass, because both halves are internally consistent.

Shape follows `kalshi_games`, which already solved exactly this for WNBA
(espn_game_id + first_espn/second_espn + polymarket_event_slug).

TWO JOIN TRAPS MEASURED WHILE BUILDING THIS, both encoded in the builder:
  * ESPN's scoreboard DEFAULTS to groups=80 (FBS). Fetching "all games" and
    "FBS games" returns the identical list, which reads as "no FCS games
    exist" — a confident, wrong zero. FCS is groups=81, with disjoint ids.
  * Our slug/event dates are VENUE-LOCAL; ESPN's event date is UTC. Exact-date
    matching left 45.3% of fills unclassified, including games known to exist.
    A +/-1 day tolerance took that to 1.7%.

Revision ID: d4a71e6c93b8
Revises: c9f1e4b73a20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "d4a71e6c93b8"
down_revision: str | None = "c9f1e4b73a20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cfb_game_map",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),

        # --- the two identities this table exists to bridge ---------------- #
        sa.Column("espn_game_id", sa.String(length=32), nullable=False),
        sa.Column("venue_game_id", sa.String(length=64), nullable=True),
        sa.Column("event_slug", sa.String(length=160), nullable=True),

        # --- what CFBD cannot tell us retroactively about our own board ---- #
        sa.Column("division", sa.String(length=8), nullable=True),   # FBS / FCS
        sa.Column("home_espn_team_id", sa.String(length=32), nullable=True),
        sa.Column("away_espn_team_id", sa.String(length=32), nullable=True),
        sa.Column("home_espn_name", sa.String(length=96), nullable=True),
        sa.Column("away_espn_name", sa.String(length=96), nullable=True),
        sa.Column("espn_date", sa.Date(), nullable=True),
        sa.Column("venue_date", sa.Date(), nullable=True),

        # --- provenance. A wrong pairing is silent; this is how it is caught #
        sa.Column("match_method", sa.String(length=48), nullable=False),
        sa.Column("match_confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("date_offset_days", sa.SmallInteger(), nullable=True),

        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("espn_game_id", name="uq_cfb_map_espn"),
    )
    op.create_index("ix_cfb_map_venue_game", "cfb_game_map", ["venue_game_id"])
    op.create_index("ix_cfb_map_event_slug", "cfb_game_map", ["event_slug"])
    op.create_index("ix_cfb_map_division", "cfb_game_map", ["division"])


def downgrade() -> None:
    op.drop_table("cfb_game_map")
