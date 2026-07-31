"""SQLAlchemy models for Meridian.

Two conventions run through every table here:

1. **Money and prices are exact NUMERIC, never binary approximations.**
   IEEE-754 types cannot represent 0.01 exactly; accumulated over thousands of
   fills, cents drift. Prices are NUMERIC(6,4), quantities NUMERIC(18,4).
   `tests/test_schema_roundtrip.py` introspects the live database and fails if
   any approximate column type ever appears.

2. **Timestamps are timestamptz, stored UTC.** WNBA games are US-scheduled and
   the recorder runs in the cloud; naive local times are a real source of
   off-by-hours bugs.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.storage.base import Base

# Reusable column types
Price = Numeric(6, 4)  # 0.0000 - 1.0000 contract prices
Qty = Numeric(18, 4)  # contract quantities
Points = Numeric(8, 2)  # basketball lines/scores


class MarketSnapshot(Base):
    """One row per market per poll — the time series of Polymarket US prices.

    This is the single unrecoverable dataset in the system. Stats and odds can
    be backfilled from ESPN at any time; a market price at a past instant
    cannot be reconstructed from anywhere once the moment has passed.
    """

    __tablename__ = "market_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    captured_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    market_slug: Mapped[str] = mapped_column(String(200), nullable=False)
    market_id: Mapped[str | None] = mapped_column(String(64))
    event_slug: Mapped[str | None] = mapped_column(String(200))
    event_id: Mapped[str | None] = mapped_column(String(64))
    game_id: Mapped[str | None] = mapped_column(String(64))

    # basketball_team_full_game_total / _spread / _winner
    sports_market_type: Mapped[str | None] = mapped_column(String(64))
    line: Mapped[Decimal | None] = mapped_column(Points)  # NULL for moneyline

    best_bid: Mapped[Decimal | None] = mapped_column(Price)
    best_ask: Mapped[Decimal | None] = mapped_column(Price)

    min_tick_size: Mapped[Decimal | None] = mapped_column(Price)
    min_trade_qty: Mapped[Decimal | None] = mapped_column(Qty)
    fee_coefficient: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))

    game_start_time: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    is_live: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    event_score: Mapped[str | None] = mapped_column(String(32))
    event_period: Mapped[str | None] = mapped_column(String(32))

    # Full payload. Schemas drift; reparsing stored JSON beats re-fetching data
    # that no longer exists.
    raw: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    levels: Mapped[list[BookLevel]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # Snapshots are append-only and keyed by (market, instant): this makes
        # a crashed-and-rerun recorder idempotent rather than duplicating rows.
        UniqueConstraint("market_slug", "captured_at", name="uq_snapshot_market_time"),
        Index("ix_market_snapshots_captured_at", "captured_at"),
        Index("ix_market_snapshots_market_slug", "market_slug"),
        Index("ix_market_snapshots_event_slug", "event_slug"),
        Index("ix_market_snapshots_game_id", "game_id"),
        # Backtest's hot path: one market's history in time order.
        Index("ix_market_snapshots_slug_time", "market_slug", "captured_at"),
    )


class BookLevel(Base):
    """Order book depth for a snapshot — many rows per snapshot."""

    __tablename__ = "book_levels"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("market_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    side: Mapped[str] = mapped_column(String(8), nullable=False)  # 'bid' | 'offer'
    price: Mapped[Decimal] = mapped_column(Price, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Qty, nullable=False)
    level_index: Mapped[int] = mapped_column(Integer, nullable=False)  # 0 = top of book

    snapshot: Mapped[MarketSnapshot] = relationship(back_populates="levels")

    __table_args__ = (
        UniqueConstraint("snapshot_id", "side", "level_index", name="uq_book_level"),
        Index("ix_book_levels_snapshot_id", "snapshot_id"),
    )


class TeamGameLog(Base):
    """Immutable one row per team per game.

    Two rows per game — one from each team's perspective, with points_scored /
    points_allowed oriented to that team.

    **No-lookahead, enforced structurally.** There is deliberately no
    `team_season_stats` table. If season aggregates were stored and overwritten
    nightly, a backtest of a July 15 game would silently read September's
    numbers and produce results that look fine but are worthless. Storing
    immutable per-game rows means every statistic must be derived `as_of` a
    date, which makes that bug unwritable rather than merely discouraged.
    """

    __tablename__ = "team_game_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    game_date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    espn_game_id: Mapped[str] = mapped_column(String(32), nullable=False)

    team_id: Mapped[str] = mapped_column(String(32), nullable=False)
    team_abbrev: Mapped[str | None] = mapped_column(String(16))
    opponent_id: Mapped[str | None] = mapped_column(String(32))
    opponent_abbrev: Mapped[str | None] = mapped_column(String(16))

    is_home: Mapped[bool] = mapped_column(Boolean, nullable=False)
    points_scored: Mapped[int | None] = mapped_column(Integer)
    points_allowed: Mapped[int | None] = mapped_column(Integer)
    is_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # ESPN event.seasonType.id: 1 = Preseason, 2 = Regular Season, 3 = Postseason.
    # Load-bearing twice over:
    #   - Preseason (1) must NEVER be written; it would pollute PPG and record.
    #   - Postseason (3) drives playoff down-weighting of the record feature.
    season_type: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("espn_game_id", "team_id", name="uq_team_game"),
        Index("ix_team_game_logs_game_date", "game_date"),
        Index("ix_team_game_logs_season_type", "season_type"),
        Index("ix_team_game_logs_team_id", "team_id"),
        Index("ix_team_game_logs_season", "season"),
        # The as_of query shape: one team's prior games, newest first.
        Index("ix_team_game_logs_team_date", "team_id", "game_date"),
    )


class SportsbookOdds(Base):
    """ESPN sportsbook lines, live and historical.

    `open_total` / `close_total` only exist for 2024+. Earlier seasons carry
    top-level consensus across 6-15 books but no open/close split, so
    `is_closing_line` must be set from an actual `close` object and never
    inferred — CLV is the backtest's primary metric and fabricating it would
    corrupt the headline result.
    """

    __tablename__ = "sportsbook_odds"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    espn_game_id: Mapped[str] = mapped_column(String(32), nullable=False)
    game_date: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False)
    captured_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    spread: Mapped[Decimal | None] = mapped_column(Points)
    over_under: Mapped[Decimal | None] = mapped_column(Points)
    over_odds: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    under_odds: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    home_moneyline: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    away_moneyline: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))

    open_total: Mapped[Decimal | None] = mapped_column(Points)
    close_total: Mapped[Decimal | None] = mapped_column(Points)
    is_closing_line: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    raw: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "espn_game_id", "provider_name", "captured_at", name="uq_odds_game_provider_time"
        ),
        Index("ix_sportsbook_odds_espn_game_id", "espn_game_id"),
        Index("ix_sportsbook_odds_game_date", "game_date"),
        Index("ix_sportsbook_odds_is_closing_line", "is_closing_line"),
    )


class Prediction(Base):
    """Every model output, forever — the long-run dataset.

    Append-only. A prediction's model price is never updated after the fact;
    doing so would destroy the record's integrity. Only the resolution fields
    are filled in later.

    Versioning: `model_version` alone is insufficient because it is a
    hand-bumped constant — changing shrinkage k or the record coefficient in
    config.py would alter the model without bumping it. `config_hash` is
    derived from the config actually used, so the backtest can group on
    (model_version, config_hash) and refuse to blend model generations.
    """

    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    predicted_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    strategy: Mapped[str] = mapped_column(String(64), nullable=False)

    market_slug: Mapped[str] = mapped_column(String(200), nullable=False)
    event_slug: Mapped[str | None] = mapped_column(String(200))
    game_id: Mapped[str | None] = mapped_column(String(64))
    sports_market_type: Mapped[str | None] = mapped_column(String(64))
    line: Mapped[Decimal | None] = mapped_column(Points)

    model_probability: Mapped[Decimal | None] = mapped_column(Price)
    model_fair_value: Mapped[Decimal | None] = mapped_column(Price)
    market_bid: Mapped[Decimal | None] = mapped_column(Price)
    market_ask: Mapped[Decimal | None] = mapped_column(Price)
    market_mid: Mapped[Decimal | None] = mapped_column(Price)
    edge: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))

    # Inputs to this prediction, for reproducibility.
    features: Mapped[dict | None] = mapped_column(JSONB)
    # Full config snapshot the model ran with, plus its deterministic hash.
    model_config_snapshot: Mapped[dict | None] = mapped_column("model_config", JSONB)
    config_hash: Mapped[str | None] = mapped_column(String(64))

    is_actionable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reduced_confidence: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confidence_notes: Mapped[str | None] = mapped_column(Text)

    resolved_outcome: Mapped[int | None] = mapped_column(SmallInteger)
    resolved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    was_correct: Mapped[bool | None] = mapped_column(Boolean)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_predictions_predicted_at", "predicted_at"),
        Index("ix_predictions_model_version", "model_version"),
        Index("ix_predictions_config_hash", "config_hash"),
        Index("ix_predictions_market_slug", "market_slug"),
        Index("ix_predictions_game_id", "game_id"),
        # The performance-query grouping key.
        Index("ix_predictions_version_config", "model_version", "config_hash"),
    )


class ResolvedOutcome(Base):
    """Ground truth from Polymarket settlement, cross-checked against ESPN."""

    __tablename__ = "resolved_outcomes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    market_slug: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    event_slug: Mapped[str | None] = mapped_column(String(200))
    game_id: Mapped[str | None] = mapped_column(String(64))

    settlement: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 0 = No, 1 = Yes
    resolved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    final_score_home: Mapped[int | None] = mapped_column(Integer)
    final_score_away: Mapped[int | None] = mapped_column(Integer)
    actual_total: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_resolved_outcomes_game_id", "game_id"),
        Index("ix_resolved_outcomes_event_slug", "event_slug"),
    )
