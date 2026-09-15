"""The CFB backfill tables, modelled so a migrated schema can create them.

WHY THIS EXISTS. Both tables were created by `archive/cfb/backfill_cfb.py` — a
script in `archive/` — and had **no Alembic migration and no model**. They
therefore existed only on the one box where that script was once run, a
migrated schema did not have them at all, and nothing in the live tree could
recreate them.

WHAT WOULD HAVE BEEN LOST. Measured 2026-09-15: 55 games and 9,537 plays.
**44 of the 55 games have no `post` row in the live tape** — they finished
before the ESPN recorder existed, so the live table can never acquire them
retrospectively. Every one of the 55 also carries a DraftKings closing
`spread`, which `cfb/run_making_touch.py` reads. So this is not a tidy-up: a
correct post-row filter does not supersede the table, it loses 80% of what it
supplies, and the spread column has a second consumer.

WHAT THIS IS NOT. No behaviour change, no data movement, no re-import. The
columns, types, nullability, defaults and indexes are copied from the LIVE
table rather than from the archive script's DDL — the live table is the
artifact and the DDL is a hypothesis about it (they agree, and that was
checked, but the direction of trust matters). Every consumer keeps reading exactly
what it read before.

WHO ACTUALLY READS THEM, counted rather than assumed: **13 scripts under
`cfb/`** — run_making_touch, run_ladder_calibration, run_slowside,
run_trigger_replay, run_total_fit, run_overshoot, run_drift, run_kalshi_dk_lag,
run_kalshi_early_vs_close, run_cross_venue, run_ladder_rv, run_longshot_shadow,
run_cover_fit — plus two in `archive/`. I had said "a second consumer" and it is
thirteen.

AND NO LIVE SERVICE READS THEM. The only reference anywhere under `core/` is a
COMMENT I wrote in `espn_cfb_recorder.py`, which a grep for the table name
returns and which reads like a code path. So the exposure is analytical, not an
availability one: a schema rebuilt from migrations loses 44 finals and 55
closing spreads and breaks 13 analysis runners, but no running recorder.

The tables are APPEND-ONLY history. Nothing writes them any more.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.storage.base import Base


class CfbBackfillGame(Base):
    """One historical game's final score and its closing DraftKings spread.

    `game_id` is the primary key, so a re-import is an upsert rather than a
    duplicate. 44 of these 55 rows exist nowhere else.
    """

    __tablename__ = "espn_cfb_backfill_games"

    game_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    backfilled_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())

    #: ESPN numeric team ids, as strings — NOT names. A consumer that expects
    #: names gets ids, which is the join trap that cost an afternoon.
    home: Mapped[str | None] = mapped_column(String(32))
    away: Mapped[str | None] = mapped_column(String(32))
    home_score: Mapped[int | None] = mapped_column(SmallInteger)
    away_score: Mapped[int | None] = mapped_column(SmallInteger)

    #: The closing line, and the reason retiring this table would cost a second
    #: consumer: `cfb/run_making_touch.py` reads it.
    spread: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    provider: Mapped[str | None] = mapped_column(String(48))


class CfbBackfillPlay(Base):
    """One historical play. 9,537 rows, the substrate for the making-touch read.

    Keyed `(game_id, play_id)` as well as by `id`: the archive script could be
    re-run over the same games without duplicating them.
    """

    __tablename__ = "espn_cfb_backfill_plays"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True,
                                    autoincrement=True)
    backfilled_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    game_id: Mapped[str] = mapped_column(String(32), nullable=False)
    play_id: Mapped[str] = mapped_column(String(48), nullable=False)

    #: The play's own instant. `cfb/run_making_touch.py` bisects prices against
    #: it, and `ix_cfb_bf_game_wall` is what makes that bounded.
    wall_clock: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True))
    period: Mapped[int | None] = mapped_column(SmallInteger)
    clock_minutes: Mapped[int | None] = mapped_column(SmallInteger)
    clock_seconds: Mapped[int | None] = mapped_column(SmallInteger)
    is_overtime: Mapped[bool] = mapped_column(Boolean, nullable=False,
                                              server_default="false")
    down: Mapped[int | None] = mapped_column(SmallInteger)
    distance: Mapped[int | None] = mapped_column(SmallInteger)
    yards_to_goal: Mapped[int | None] = mapped_column(SmallInteger)
    pos_team: Mapped[str | None] = mapped_column(String(32))
    home: Mapped[str | None] = mapped_column(String(32))
    away: Mapped[str | None] = mapped_column(String(32))
    drive_is_home_offense: Mapped[bool | None] = mapped_column(Boolean)
    pos_team_score: Mapped[int | None] = mapped_column(SmallInteger)
    def_pos_team_score: Mapped[int | None] = mapped_column(SmallInteger)
    home_score: Mapped[int | None] = mapped_column(SmallInteger)
    away_score: Mapped[int | None] = mapped_column(SmallInteger)

    __table_args__ = (
        UniqueConstraint("game_id", "play_id",
                         name="espn_cfb_backfill_plays_game_id_play_id_key"),
        Index("ix_cfb_bf_game_wall", "game_id", "wall_clock"),
    )
