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
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    text,
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
    #: move?") is precisely a question about ordering. Stamped by EVERY writer
    #: since 2026-08-07 (the pregame path uses its cycle instant, which is
    #: exact there): the partitioned local table routes on this column and its
    #: PK forbids NULL. Still nullable in the model because Supabase keeps
    #: historical fetched-together rows where it genuinely was NULL.
    captured_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    snapshot: Mapped[MarketSnapshot] = relationship(back_populates="levels")

    __table_args__ = (
        UniqueConstraint("snapshot_id", "side", "level_index", name="uq_book_level"),
        Index("ix_book_levels_snapshot_id", "snapshot_id"),
        Index("ix_book_levels_captured_at", "captured_at"),
    )


class KalshiGame(Base):
    """One row per Kalshi WNBA game — the mapping table between venues.

    There is no shared identifier between Kalshi, Polymarket, and ESPN, so the
    join key is the same one `core.team_mapping` uses for Polymarket: the
    **unordered ESPN team pair plus a local date**. `first_code`/`second_code`
    preserve Kalshi's own ticker order verbatim, but nothing may read them as
    away/home — Polymarket's slug order flipped convention mid-season
    (team_mapping module docstring), and Kalshi's order gets the same
    presumption of unreliability until measured otherwise.

    `game_start_time` is copied from our own Polymarket snapshots, because
    Kalshi's event payload carries no start time (strike_date is null on WNBA
    games; verified against the venue 2026-08-05). A row with a start time is
    therefore *by construction* a game we also record on Polymarket — the
    "matched games only" scope rule is structural, not a filter someone can
    forget.
    """

    __tablename__ = "kalshi_games"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    #: The shared suffix of the game's event tickers across all three series,
    #: e.g. '26AUG05PHXATL' from KXWNBAGAME-26AUG05PHXATL.
    game_key: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    #: Date encoded in the ticker (US-local, like Polymarket slug dates).
    local_date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    first_code: Mapped[str] = mapped_column(String(8), nullable=False)   # Kalshi's, verbatim
    second_code: Mapped[str] = mapped_column(String(8), nullable=False)  # positional only
    first_espn: Mapped[str | None] = mapped_column(String(16))   # NULL = unmapped (all-star)
    second_espn: Mapped[str | None] = mapped_column(String(16))

    title: Mapped[str | None] = mapped_column(String(200))  # Kalshi's, verbatim

    polymarket_event_slug: Mapped[str | None] = mapped_column(String(200))
    game_start_time: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    espn_game_id: Mapped[str | None] = mapped_column(String(32))

    first_seen_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_kalshi_games_local_date", "local_date"),
        Index("ix_kalshi_games_polymarket_event_slug", "polymarket_event_slug"),
    )


class KalshiContract(Base):
    """Point-in-time change log of each Kalshi contract's terms, verbatim.

    A cross-venue price comparison is only as honest as its strike matching:
    Kalshi settles "Atlanta wins by more than 3.5" while Polymarket quotes
    "Seattle covers +19.5", and a half-point or settlement-rule mismatch is
    basis risk that must be auditable, not assumed away. This table keeps the
    line (`floor_strike`/`cap_strike`/`strike_type`) and the settlement rules
    (`rules_primary`/`rules_secondary`) exactly as the venue served them, plus
    the full raw payload.

    Written like `InjuryReport`: a row when terms *change*, not per poll — the
    rules text is ~1 KB and repeating it every 60s per contract is pure quota
    burn (docs/infra/supabase-quota.md). Reading terms as of an instant is
    "latest row for the ticker with captured_at <= as_of".
    """

    __tablename__ = "kalshi_contracts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    #: When WE observed these terms — the only timestamp analysis may filter on.
    captured_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    ticker: Mapped[str] = mapped_column(String(64), nullable=False)
    event_ticker: Mapped[str] = mapped_column(String(64), nullable=False)
    series_ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    game_key: Mapped[str] = mapped_column(String(32), nullable=False)
    #: 'winner' | 'spread' | 'total' — derived from series_ticker.
    market_type: Mapped[str] = mapped_column(String(16), nullable=False)

    yes_sub_title: Mapped[str | None] = mapped_column(String(200))
    floor_strike: Mapped[Decimal | None] = mapped_column(Points)
    cap_strike: Mapped[Decimal | None] = mapped_column(Points)
    strike_type: Mapped[str | None] = mapped_column(String(32))

    rules_primary: Mapped[str | None] = mapped_column(Text)
    rules_secondary: Mapped[str | None] = mapped_column(Text)

    open_time: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    close_time: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    expected_expiration_time: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    #: The full market payload as served. Schemas drift; reparsing stored JSON
    #: beats re-fetching data that no longer exists.
    raw: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("ticker", "captured_at", name="uq_kalshi_contract_ticker_time"),
        Index("ix_kalshi_contracts_ticker_time", "ticker", "captured_at"),
        Index("ix_kalshi_contracts_game_key", "game_key"),
    )


class KalshiSnapshot(Base):
    """One row per Kalshi contract per poll — `market_snapshots` for Kalshi.

    Same reason to exist: a price at a past instant cannot be reconstructed
    once the moment has passed. Same point-in-time contract: `captured_at` is
    mandatory and shared across a cycle, so a cycle is a coherent instant.

    Slimmer than its Polymarket sibling on purpose: the static terms live in
    `kalshi_contracts`, and `no_bid`/`no_ask` are not stored because Kalshi's
    no side is the yes side's complement (no_bid = 1 - yes_ask; verified
    against live payloads 2026-08-05) — storing both would just be a place for
    them to disagree.
    """

    __tablename__ = "kalshi_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    captured_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    ticker: Mapped[str] = mapped_column(String(64), nullable=False)
    event_ticker: Mapped[str] = mapped_column(String(64), nullable=False)
    series_ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    game_key: Mapped[str] = mapped_column(String(32), nullable=False)
    market_type: Mapped[str] = mapped_column(String(16), nullable=False)
    #: Denormalized from the contract for query convenience, exactly as
    #: market_snapshots carries `line`.
    floor_strike: Mapped[Decimal | None] = mapped_column(Points)

    yes_bid: Mapped[Decimal | None] = mapped_column(Price)
    yes_ask: Mapped[Decimal | None] = mapped_column(Price)
    last_price: Mapped[Decimal | None] = mapped_column(Price)
    yes_bid_size: Mapped[Decimal | None] = mapped_column(Qty)
    yes_ask_size: Mapped[Decimal | None] = mapped_column(Qty)

    volume: Mapped[Decimal | None] = mapped_column(Qty)
    open_interest: Mapped[Decimal | None] = mapped_column(Qty)
    status: Mapped[str | None] = mapped_column(String(32))
    result: Mapped[str | None] = mapped_column(String(16))

    #: NULL unless KALSHI_SNAPSHOT_RAW is set — the verbatim payload is kept
    #: point-in-time in kalshi_contracts instead.
    raw: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # Append-only, keyed (ticker, instant): a crashed-and-rerun recorder
        # is idempotent rather than duplicating rows.
        UniqueConstraint("ticker", "captured_at", name="uq_kalshi_snapshot_ticker_time"),
        Index("ix_kalshi_snapshots_captured_at", "captured_at"),
        Index("ix_kalshi_snapshots_ticker_time", "ticker", "captured_at"),
        Index("ix_kalshi_snapshots_game_key", "game_key"),
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


class RetentionLog(Base):
    """One row per archived tick partition — the receipt the invariant rests on.

    The retention job (core/retention.py) may only DETACH a partition after a
    row exists here with `verified_at` set: dump written, restored into a
    scratch database, row count and id range matched exactly. The health check
    and the alerter read this table; a missing or stale tail is loud.
    """

    __tablename__ = "retention_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    table_name: Mapped[str] = mapped_column(String(64), nullable=False)
    partition_name: Mapped[str] = mapped_column(String(80), nullable=False)
    month_start: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rows_archived: Mapped[int] = mapped_column(BigInteger, nullable=False)
    dump_path: Mapped[str] = mapped_column(Text, nullable=False)
    dump_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    dump_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    verified_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    detached_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    dropped_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("partition_name", name="uq_retention_partition"),
    )


class ServiceHeartbeat(Base):
    """One row per long-running writer, upserted every cycle — game or no game.

    `InjuryPoll` generalised. Every writer's silence is ambiguous from its data
    alone: the live recorder is legitimately quiet between games, the pregame
    recorder sleeps an hour overnight, the scheduler naps twenty minutes. That
    ambiguity is what let the 200ms recorder stay dead for 23 hours (B11) —
    "no rows" read as "no game". A beat written unconditionally, to the same
    database the service writes its data to, removes it: no beat for 3x the
    service's own reported interval means dead, whatever the schedule says.

    One row per service, updated in place, so the table never grows and the
    egress cost of honesty is one tiny upsert per cycle.
    """

    __tablename__ = "service_heartbeats"

    #: 'pregame_recorder' | 'live_recorder' | 'live_odds_recorder' | 'scheduler'.
    service: Mapped[str] = mapped_column(String(64), primary_key=True)
    #: Set from the database's own clock, so a container with a skewed clock
    #: cannot report itself alive into the future.
    beat_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    #: The cadence the writer is currently on, self-reported. Idle and active
    #: cadences differ (200ms vs 120s for the live recorder), and the staleness
    #: rule is relative to this, so a sleeping writer is judged by its sleep.
    interval_seconds: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    #: How long the last cycle's work took.
    cycle_seconds: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    #: Rows the last cycle actually landed in the database — an output, not an
    #: exit code. NULL means "not measured" (the scheduler), which is different
    #: from 0 ("measured, nothing written").
    rows_written: Mapped[int | None] = mapped_column(Integer)
    #: Cumulative rows since process start, for eyeballing a delta.
    rows_total: Mapped[int | None] = mapped_column(BigInteger)
    #: What the writer itself believed about game state this cycle. Readers
    #: with an independent game signal (ESPN) should prefer their own.
    game_live: Mapped[bool | None] = mapped_column(Boolean)


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
    #: DIAGNOSTIC, not performance: "was the model probability on the right
    #: side of 0.50", which is not "did the bet win" (findings C5). Never
    #: aggregate this into anything presented as a win rate.
    direction_correct: Mapped[bool | None] = mapped_column(Boolean)

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


#: The only mode under which a real order may be accepted by the venue.
#: Duplicated as a literal here rather than imported from `core.executor`
#: because it is baked into a database CHECK constraint — the constraint is the
#: authority, and a Python import could drift from what Postgres enforces.
HUMAN_CONFIRM_MODE = "HUMAN_CONFIRM"


class PlacedOrder(Base):
    """An order actually sent to the venue. One row per submission attempt.

    Rejected and errored attempts are rows too. That is deliberate: a table
    that only records successes cannot answer "did we ever try?", which is the
    question an audit actually asks.

    The safety invariant is enforced by Postgres, not by Python
    -----------------------------------------------------------
    ``ck_orders_accepted_requires_human`` makes **an accepted order in any mode
    other than HUMAN_CONFIRM unrepresentable**. Not discouraged, not caught by a
    guard someone can forget to call — rejected by the database.

    This is the replacement for "there is no mutating endpoint". The old
    invariant was structural: the client had no verb but GET, so no code path
    could place an order. Adding a POST path spends that guarantee, and it has
    to be bought back somewhere. A CHECK constraint is the cheapest equivalent:
    every write, from every process, migration and psql session, passes through
    it. `orders_autonomous` on /api/status reads 0 forever *because this
    constraint exists*, and the counter is a tripwire for the constraint having
    been removed rather than the primary defence.

    Same reasoning as the hardcoded order type in `core.executor`: the safest
    guard is the one that makes the bad state impossible to express.
    """

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    submitted_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    #: Deterministic, from `core.executor.make_idempotency_key`. UNIQUE, so a
    #: double-click or a retry cannot produce a second submission.
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)

    #: Execution mode. The CHECK constraint below reads this column.
    mode: Mapped[str] = mapped_column(String(20), nullable=False)

    market_slug: Mapped[str] = mapped_column(String(200), nullable=False)
    event_slug: Mapped[str | None] = mapped_column(String(200))
    sports_market_type: Mapped[str | None] = mapped_column(String(64))

    side: Mapped[str] = mapped_column(String(8), nullable=False)       # 'buy' | 'sell'
    #: Always ORDER_TYPE_LIMIT. Stored so a market order would be visible in the
    #: data if one ever appeared, rather than being silently indistinguishable.
    order_type: Mapped[str] = mapped_column(String(32), nullable=False)
    limit_price: Mapped[Decimal] = mapped_column(Price, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Qty, nullable=False)

    #: True only when the venue confirmed acceptance. Drives both counters.
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    #: The 2026-08-05 amendment (user-approved): True for an order whose
    #: market, side, price and quantity were ALL fixed by a human click and
    #: which the system submitted later on a defined trigger — today, only the
    #: attached exit, submitted when its entry fills. Every term is the
    #: human's; only the timing is the machine's, which is why it does not
    #: count toward `orders_autonomous`. The CHECK constraint below pins it to
    #: HUMAN_CONFIRM so the flag can never launder a machine-termed order.
    pre_authorized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    #: Venue truth, written only by the fill watcher and attributed by venue
    #: order id alone: OPEN / PARTIAL / FILLED / CANCELLED / EXPIRED. NULL
    #: means "never reconciled", which is not the same claim as OPEN
    #: ("reconciled, confirmed still resting") — orders #1–3 sat at
    #: `accepted=True` while a human cancelled two of them in the app, and
    #: nothing in this table could tell.
    fill_status: Mapped[str | None] = mapped_column(String(16))
    #: Contracts the venue reports filled. The attached exit's quantity is
    #: THIS number, never `quantity` — a partial fill exited at the ordered
    #: size would be selling contracts we do not hold.
    filled_quantity: Mapped[Decimal | None] = mapped_column(Qty)
    fill_checked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    #: The human cancel path (V21). `cancel_requested_at` is written BEFORE
    #: the venue call — an attempt that never came back must still read as an
    #: attempt — and the rest record the venue's answer verbatim: the ack
    #: status, the round-trip and venue-side latency (the last unmeasured
    #: number in docs/math/write-latency.md), and the response body the V21
    #: findings entry gets transcribed from. Only the /api/orders/{id}/cancel
    #: endpoint writes these; no machine path may initiate a cancel.
    cancel_requested_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_http_status: Mapped[int | None] = mapped_column(Integer)
    cancel_latency_ms: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    cancel_venue_latency_ms: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    cancel_response: Mapped[str | None] = mapped_column(Text)
    venue_order_id: Mapped[str | None] = mapped_column(String(120))
    venue_status: Mapped[str | None] = mapped_column(String(64))
    http_status: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)

    #: Write latency — the number `docs/math/write-latency.md` gates QUOTE on.
    #: `submit_latency_ms` is our full round trip; `venue_latency_ms` is the
    #: venue's self-reported processing time from `x-pm-server-latency`.
    submit_latency_ms: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    venue_latency_ms: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))

    #: Book state at submission, so a fill can later be judged against what was
    #: actually showing rather than against a reconstruction.
    market_bid: Mapped[Decimal | None] = mapped_column(Price)
    market_ask: Mapped[Decimal | None] = mapped_column(Price)
    would_rest: Mapped[bool | None] = mapped_column(Boolean)

    shadow_order_id: Mapped[int | None] = mapped_column(BigInteger)
    prediction_id: Mapped[int | None] = mapped_column(BigInteger)
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        # The invariant. An accepted order must be HUMAN_CONFIRM.
        CheckConstraint(
            f"accepted = false OR mode = '{HUMAN_CONFIRM_MODE}'",
            name="ck_orders_accepted_requires_human",
        ),
        # The amendment's own constraint: pre-authorization exists only inside
        # HUMAN_CONFIRM. A future mode cannot inherit the flag.
        CheckConstraint(
            f"pre_authorized = false OR mode = '{HUMAN_CONFIRM_MODE}'",
            name="ck_orders_pre_authorized_requires_human",
        ),
        # Market orders are unrepresentable in core.executor; keep them
        # unrepresentable in the data too, so the two cannot drift.
        CheckConstraint(
            "order_type = 'ORDER_TYPE_LIMIT'",
            name="ck_orders_limit_only",
        ),
        Index("ix_orders_submitted_at", "submitted_at"),
        Index("ix_orders_market_slug", "market_slug"),
        Index("ix_orders_mode_accepted", "mode", "accepted"),
    )


class PendingExit(Base):
    """A pre-authorized exit, stored at click time and submitted on fill.

    Every term here was fixed by the human on the ticket — market, outcome,
    price — except the quantity, which by rule is **the entry's filled
    quantity**, knowable only when the fill watcher confirms it. The rules,
    each load-bearing (see docs/infra/fill-watcher.md):

    * `market_slug` is copied from the entry row at click time, never
      re-looked-up at submit.
    * `limit_price` is immutable — sent exactly as stored even if the market
      has moved 30¢. No chasing, ever. A stale exit is the human's to cancel.
    * The link to the entry is `entry_order_id`, our own order id: explicit,
      one-to-one (UNIQUE), never matched by market/price/size similarity —
      the account also holds hand trades in the same markets.
    * Entry cancelled or expired unfilled → state DELETED, with a log line.
    * One retry on submit failure, then FAILED loudly on the dashboard.
    """

    __tablename__ = "pending_exits"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    entry_order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("orders.id"), nullable=False, unique=True
    )

    market_slug: Mapped[str] = mapped_column(String(200), nullable=False)
    outcome: Mapped[str] = mapped_column(String(8), nullable=False)  # 'YES' | 'NO'
    #: YES-frame price.value — what the venue receives, per V14.
    limit_price: Mapped[Decimal] = mapped_column(Price, nullable=False)
    #: The number the human typed, in the cost frame they saw. On a NO exit
    #: these differ by 1 − p, and keeping both is what makes the row auditable.
    typed_price: Mapped[Decimal] = mapped_column(Price, nullable=False)

    #: PENDING → SUBMITTED | FAILED | DELETED. Enforced by CHECK.
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    submitted_order_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("orders.id")
    )
    error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "state in ('PENDING','SUBMITTED','FAILED','DELETED')",
            name="ck_pending_exit_state",
        ),
        CheckConstraint("outcome in ('YES','NO')", name="ck_pending_exit_outcome"),
        Index("ix_pending_exits_state", "state"),
    )


class AccountBalance(Base):
    """The venue's own answer to "how much money is in the account", per poll.

    Every dollar figure this system computes — Kelly stake, ticket size, the
    per-order cap — is a fraction of a bankroll, and until 2026-08-17 that
    bankroll was the literal ``35.68`` typed into ``core/scheduler.py`` on the
    day someone last looked at the app. The account was at $23.82 by then, so
    every size on the board was ~50% too large and the error grew silently
    with every fill. A number that decays without anybody noticing is not a
    parameter, it is a bug with a decimal point.

    Append-only, one row per poll. The history is the equity curve, and it is
    also what makes a past sizing decision reproducible: ``bankroll`` stores
    the derived number that was actually used, next to the raw fields it came
    from, so "why was this staked at $0.58" is answerable months later.
    Cheap at any cadence — 20-minute polling is ~26k rows a year.
    """

    __tablename__ = "account_balances"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    #: When we asked. Our clock, not the venue's: the venue's ``lastUpdated``
    #: has been null on every observation so far, so it cannot be the key.
    observed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False)

    #: ``currentBalance`` — settled cash.
    cash: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    #: ``buyingPower`` — what the venue says is deployable right now.
    buying_power: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    #: ``assetNotional`` — open positions marked to market.
    asset_notional: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    #: ``openOrders`` — cash committed to resting orders.
    open_orders: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unsettled_funds: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    pending_credit: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    margin_requirement: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    #: The number sizing actually used — see `core.bankroll.AccountSnapshot`.
    bankroll: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    #: The venue's payload verbatim. Reparsing a stored body beats re-fetching
    #: a balance that has since moved.
    raw: Mapped[dict | None] = mapped_column(JSONB)

    #: Open positions at this reading, and whether they were actually read.
    #:
    #: These exist because the round trip was lossy without them, and lossy in
    #: the worst direction. `AccountSnapshot` grew `positions`/`positions_read_ok`
    #: when equity display was added, but `record()` did not persist them and
    #: `latest()` did not reconstruct them — so a stored snapshot came back with
    #: `positions=()` and `positions_read_ok=False`, which does not mean "no
    #: positions", it means **"the read failed"**. The poller logged a real
    #: $3.60 position while the page rendered "positions unread" in red, in the
    #: same minute, because `current()` prefers the fresh stored row.
    #:
    #: `positions_read_ok` is stored rather than derived from `positions` being
    #: empty, because an empty book and an unread book are different facts and
    #: the whole display turns on telling them apart.
    positions: Mapped[list | None] = mapped_column(JSONB)
    positions_read_ok: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    __table_args__ = (
        Index("ix_account_balances_observed_at", "observed_at"),
    )
