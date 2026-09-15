"""The CFB backfill tables, which existed only where an archived script had run

`espn_cfb_backfill_games` and `espn_cfb_backfill_plays` were created by
`archive/cfb/backfill_cfb.py` and had no migration and no model. A migrated
schema did not have them, which is why `cfb/run_ladder_calibration.py`'s
GAMES_SQL cannot run against a fresh database and why the post-beats-backfill
precedence could be verified on prod but not TESTED.

What was at risk, measured 2026-09-15: 55 games and 9,537 plays, of which **44
of the 55 games have no `post` row in the live tape at all** — they finished
before the ESPN recorder existed, so nothing in the live tree can reacquire
them. All 55 also carry a DraftKings closing `spread` that
`cfb/run_making_touch.py` reads.

CREATE IF NOT EXISTS, and the downgrade does NOT drop. The tables already hold
irreplaceable rows on the box where the script ran; a migration that can delete
them is a worse outcome than one that leaves a table behind. `down_revision`
reversal therefore un-registers the schema without touching the data, and says
so.

Revision ID: b4e9f1c73d85
Revises: a1c7e35b9d20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b4e9f1c73d85"
down_revision = "a1c7e35b9d20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # checkfirst via IF NOT EXISTS: on the box that already has these tables
    # (with data) this migration must be a no-op rather than an error.
    op.execute("""
    CREATE TABLE IF NOT EXISTS espn_cfb_backfill_games (
      game_id       varchar(32) PRIMARY KEY,
      backfilled_at timestamptz NOT NULL DEFAULT now(),
      home          varchar(32),
      away          varchar(32),
      home_score    smallint,
      away_score    smallint,
      spread        numeric(6,2),
      provider      varchar(48)
    )""")
    op.execute("""
    CREATE TABLE IF NOT EXISTS espn_cfb_backfill_plays (
      id                    bigserial PRIMARY KEY,
      backfilled_at         timestamptz NOT NULL DEFAULT now(),
      game_id               varchar(32) NOT NULL,
      play_id               varchar(48) NOT NULL,
      wall_clock            timestamptz,
      period                smallint,
      clock_minutes         smallint,
      clock_seconds         smallint,
      is_overtime           boolean NOT NULL DEFAULT false,
      down                  smallint,
      distance              smallint,
      yards_to_goal         smallint,
      pos_team              varchar(32),
      home                  varchar(32),
      away                  varchar(32),
      drive_is_home_offense boolean,
      pos_team_score        smallint,
      def_pos_team_score    smallint,
      home_score            smallint,
      away_score            smallint,
      CONSTRAINT espn_cfb_backfill_plays_game_id_play_id_key
        UNIQUE (game_id, play_id)
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_cfb_bf_game_wall "
               "ON espn_cfb_backfill_plays (game_id, wall_clock)")


def downgrade() -> None:
    """DELIBERATELY DOES NOT DROP.

    44 of the 55 games in this table exist nowhere else and cannot be
    reacquired: they finished before the live recorder existed. A downgrade
    that drops them trades a schema inconvenience for permanent data loss, so
    it un-registers the revision and leaves the tables standing. Dropping them
    is a manual decision with the row counts in front of you.
    """
    pass
