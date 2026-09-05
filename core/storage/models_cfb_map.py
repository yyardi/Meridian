"""The ESPN <-> venue game map for college football.

Written by `scripts/build_cfb_game_map.py`, read by anything that needs to
attach game state to a price. See the migration (d4a71e6c93b8) for why this is
materialised rather than derived: game identity and division require an
external call and a fuzzy match, so they are facts to store once with their
method recorded — not pure functions of our own columns.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Date, DateTime, Numeric, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from core.storage.base import Base


class CfbGameMap(Base):
    __tablename__ = "cfb_game_map"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    first_seen_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())

    espn_game_id: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    venue_game_id: Mapped[str | None] = mapped_column(String(64), index=True)
    event_slug: Mapped[str | None] = mapped_column(String(160), index=True)

    division: Mapped[str | None] = mapped_column(String(8), index=True)
    home_espn_team_id: Mapped[str | None] = mapped_column(String(32))
    away_espn_team_id: Mapped[str | None] = mapped_column(String(32))
    home_espn_name: Mapped[str | None] = mapped_column(String(96))
    away_espn_name: Mapped[str | None] = mapped_column(String(96))
    espn_date: Mapped[dt.date | None] = mapped_column(Date)
    venue_date: Mapped[dt.date | None] = mapped_column(Date)

    #: provenance — a mispaired game is silent and unrecoverable downstream.
    match_method: Mapped[str] = mapped_column(String(48), nullable=False)
    match_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    date_offset_days: Mapped[int | None] = mapped_column(SmallInteger)
