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

    #: Which depth tier this row was sampled under, or NULL for none.
    #:
    #: The live recorder cannot afford full depth on every market every second,
    #: so it samples the rungs nearest the money often ('near') and the deep
    #: rungs rarely ('deep'). Recording the tier makes that sparsity a query
    #: rather than a thing you have to know: a later analysis can ask "was this
    #: market eligible for depth at this instant?" and distinguish *no resting
    #: size* from *we did not look*. Without it the two are indistinguishable,
    #: and an absent book reads as an empty one.
    book_tier: Mapped[str | None] = mapped_column(String(8))

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

    #: When the book call actually returned, which is NOT the parent snapshot's
    #: `captured_at` once depth is sampled on a slower loop than price.
    #:
    #: The live recorder polls top-of-book every second but depth every few
    #: seconds, so a depth row can be several seconds younger than the snapshot
    #: it hangs from. Inheriting the parent's timestamp would silently backdate
    #: it, and the whole depth-signal question ("did size appear *before* the
    #: move?") is precisely a question about ordering. NULL for rows written
    #: before this column existed, where depth and price were fetched together.
    captured_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    snapshot: Mapped[MarketSnapshot] = relationship(back_populates="levels")

    __table_args__ = (
        UniqueConstraint("snapshot_id", "side", "level_index", name="uq_book_level"),
        Index("ix_book_levels_snapshot_id", "snapshot_id"),
        Index("ix_book_levels_captured_at", "captured_at"),
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

    # Box-score stats (nullable — backfilled by core/feeds/espn_boxscores.py).
    # Enough for the Kubatko possessions estimate FGA − OREB + TOV + 0.44·FTA,
    # which unlocks pace-based projections (Dean Oliver's structure).
    fga: Mapped[int | None] = mapped_column(Integer)
    fta: Mapped[int | None] = mapped_column(Integer)
    oreb: Mapped[int | None] = mapped_column(Integer)
    turnovers: Mapped[int | None] = mapped_column(Integer)
    # Quarter linescores, stored now for future garbage-time filtering.
    q1: Mapped[int | None] = mapped_column(Integer)
    q2: Mapped[int | None] = mapped_column(Integer)
    q3: Mapped[int | None] = mapped_column(Integer)
    q4: Mapped[int | None] = mapped_column(Integer)
    ot_points: Mapped[int | None] = mapped_column(Integer)

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


class PlayerGameLog(Base):
    """One row per player per game — who actually played, and how much.

    **Retrospective, not point-in-time.** A row here is only knowable after the
    game: it is the box score. It answers "was she available?" with hindsight,
    which is exactly what a *screening* experiment needs (an upper bound on
    what roster awareness could be worth) and exactly what a tradable model may
    not use. The point-in-time counterpart is `InjuryReport`, which only
    accrues forward. Nothing in the feature layer may join these two as if they
    were the same thing; see docs/math/availability.md.

    `did_not_play` is ESPN's own flag. A player who is injured usually does not
    appear in the payload at all, so absence from this table for a game she
    could otherwise have played is itself the signal.
    """

    __tablename__ = "player_game_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    espn_game_id: Mapped[str] = mapped_column(String(32), nullable=False)
    game_date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    season_type: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    team_id: Mapped[str] = mapped_column(String(32), nullable=False)
    athlete_id: Mapped[str] = mapped_column(String(32), nullable=False)
    athlete_name: Mapped[str | None] = mapped_column(String(120))
    position: Mapped[str | None] = mapped_column(String(16))

    starter: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    did_not_play: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dnp_reason: Mapped[str | None] = mapped_column(String(64))

    minutes: Mapped[int | None] = mapped_column(Integer)
    points: Mapped[int | None] = mapped_column(Integer)
    plus_minus: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("espn_game_id", "athlete_id", name="uq_player_game"),
        Index("ix_player_game_logs_game_date", "game_date"),
        Index("ix_player_game_logs_espn_game_id", "espn_game_id"),
        # The as_of query shape: one team's players' prior games, newest first.
        Index("ix_player_game_logs_team_date", "team_id", "game_date"),
        Index("ix_player_game_logs_athlete_date", "athlete_id", "game_date"),
    )


class InjuryReport(Base):
    """Point-in-time injury status — a **change log**, not a per-poll dump.

    ESPN's injuries feed reports *current* state only. The same is true of the
    `injuries` block inside a game summary: fetching the summary of a 2025 game
    today returns injuries dated 2026, so historical status cannot be
    reconstructed from it. This table is therefore only ever correct going
    forward, from the moment the recorder starts.

    A row is written when a player's status *changes* (including to `Cleared`,
    synthesised when she drops out of the feed). Reading the status as of an
    instant is "latest row for that athlete with `captured_at` <= as_of", which
    is correct precisely because unchanged states are not re-written. Gaps in
    coverage are not silently invisible: `InjuryPoll` records every poll, so a
    recorder outage is detectable rather than being mistaken for "no changes".
    """

    __tablename__ = "injury_reports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    #: When WE observed this state. The only timestamp a backtest may filter on.
    captured_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: ESPN's own "last updated" for the designation. Informational only — it is
    #: not evidence we knew it then.
    reported_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    source: Mapped[str] = mapped_column(String(32), nullable=False, default="espn_injuries")
    team_id: Mapped[str | None] = mapped_column(String(32))
    team_name: Mapped[str | None] = mapped_column(String(64))

    athlete_id: Mapped[str] = mapped_column(String(32), nullable=False)
    athlete_name: Mapped[str | None] = mapped_column(String(120))
    position: Mapped[str | None] = mapped_column(String(16))

    #: 'Out' | 'Day-To-Day' | 'Cleared' (synthesised) | whatever ESPN sends.
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    status_type: Mapped[str | None] = mapped_column(String(48))  # INJURY_STATUS_OUT etc.
    detail_type: Mapped[str | None] = mapped_column(String(64))  # 'Knee', "Coach's Decision"
    return_date: Mapped[str | None] = mapped_column(String(16))

    raw: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # Re-running a poll must not duplicate a change.
        UniqueConstraint("athlete_id", "captured_at", name="uq_injury_athlete_time"),
        Index("ix_injury_reports_captured_at", "captured_at"),
        # The as_of query shape: one athlete's status history, newest first.
        Index("ix_injury_reports_athlete_time", "athlete_id", "captured_at"),
        Index("ix_injury_reports_team_id", "team_id"),
    )


class InjuryPoll(Base):
    """One row per injury-feed poll, whether or not anything changed.

    Without this, a change log is ambiguous: no rows for a week could mean a
    quiet week or a dead recorder. With it, coverage is a query.
    """

    __tablename__ = "injury_polls"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    captured_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, unique=True
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="espn_injuries")
    n_teams: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    n_designations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    n_changes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_injury_polls_captured_at", "captured_at"),)


class ModelCalibration(Base):
    """Slow-moving fitted constants, computed once and reused.

    The winner's-curse slope is estimated by walking every completed game and
    re-deriving its point-in-time features — seconds locally, minutes against a
    remote database. The prediction job runs every 20 minutes and cannot pay
    that each time, but the slope only changes when games complete, so it is
    computed daily and read from here.

    `as_of` is stored because the value is a point-in-time estimate: a slope
    fitted on games through August must never be applied to a July prediction.
    Readers take the freshest row at or before their own `as_of`.
    """

    __tablename__ = "model_calibration"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    #: The instant the estimate is valid from — games strictly before it.
    as_of: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: e.g. 'totals_market_slope'.
    metric: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    #: Games the estimate was fitted on — an estimate from 12 games is not the
    #: same object as one from 700, and the reader should be able to tell.
    n_observations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    computed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("metric", "as_of", name="uq_calibration_metric_asof"),
        Index("ix_model_calibration_metric_asof", "metric", "as_of"),
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
        # A prediction is a function of (market, model, instant). Re-running
        # against the same snapshot must be a no-op, not a duplicate row that
        # double-counts in every performance statistic.
        UniqueConstraint(
            "market_slug", "predicted_at", "model_version", "config_hash",
            name="uq_prediction_market_time_model",
        ),
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


class ShadowOrder(Base):
    """An order the executor WOULD have placed. Nothing is sent to the venue.

    Kept faithful enough to be comparable against reality later: tick-rounded
    limit price, venue minimum respected, book state at decision time, and
    whether the order would have rested (maker, earns a rebate) or crossed
    (taker, pays a fee).
    """

    __tablename__ = "shadow_orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    decided_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    #: Deterministic key so a retry cannot double-place in later modes.
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)

    prediction_id: Mapped[int | None] = mapped_column(BigInteger)
    market_slug: Mapped[str] = mapped_column(String(200), nullable=False)
    event_slug: Mapped[str | None] = mapped_column(String(200))
    sports_market_type: Mapped[str | None] = mapped_column(String(64))
    line: Mapped[Decimal | None] = mapped_column(Points)

    side: Mapped[str] = mapped_column(String(8), nullable=False)      # 'buy' | 'sell'
    limit_price: Mapped[Decimal] = mapped_column(Price, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Qty, nullable=False)

    model_probability: Mapped[Decimal | None] = mapped_column(Price)
    market_bid: Mapped[Decimal | None] = mapped_column(Price)
    market_ask: Mapped[Decimal | None] = mapped_column(Price)
    edge_net: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))

    #: True when the limit would rest on the book (earns the maker rebate).
    would_rest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    expected_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))

    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="SHADOW")
    binding_constraint: Mapped[str | None] = mapped_column(String(40))
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_shadow_orders_decided_at", "decided_at"),
        Index("ix_shadow_orders_market_slug", "market_slug"),
    )
