"""Recorder guarantees: idempotency, failure isolation, rate limiting, cadence.

These use a fake client rather than the live gateway, so they are fast,
deterministic, and runnable offline.
"""

from __future__ import annotations

import datetime as dt
import time
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select

from core.config import RecorderConfig
from core.polymarket.schemas import BookResponse, EventsResponse
from core.ratelimit import TokenBucket
from core.recorder import Recorder
from core.storage import BookLevel, MarketSnapshot, get_engine, get_sessionmaker

UTC = dt.timezone.utc

BOARD = {
    "events": [
        {
            "id": "62459",
            "slug": "wnba-test-evt",
            "title": "Test A vs. Test B",
            "startTime": "2026-08-01T02:00:00Z",
            "gameId": 13002436,
            "eventState": {"score": "46-34", "period": "Q3", "live": True},
            "markets": [
                {
                    "id": "298081",
                    "slug": "tsc-wnba-test-evt-144pt5",
                    "sportsMarketType": "basketball_team_full_game_total",
                    "line": 144.5,
                    "bestBidQuote": {"value": "0.9100", "currency": "USD"},
                    "bestAskQuote": {"value": "0.9600", "currency": "USD"},
                    "orderPriceMinTickSize": 0.01,
                    "minimumTradeQty": 0.01,
                    "feeCoefficient": 0.06,
                },
                {
                    "id": "298082",
                    "slug": "aec-wnba-test-evt",
                    "sportsMarketType": "basketball_team_full_game_winner",
                    "bestBidQuote": {"value": "0.8500", "currency": "USD"},
                    "bestAskQuote": {"value": "0.8600", "currency": "USD"},
                },
            ],
        }
    ]
}

BOOK = {
    "marketData": {
        "marketSlug": "x",
        "bids": [{"px": {"value": "0.5100", "currency": "USD"}, "qty": "1559.0000"}],
        "offers": [{"px": {"value": "0.5300", "currency": "USD"}, "qty": "1505.7800"}],
    }
}


class FakeClient:
    """Stands in for PolymarketGatewayClient."""

    def __init__(self, fail_on_book: set[str] | None = None) -> None:
        self.fail_on_book = fail_on_book or set()
        self.book_calls = 0

    def get_league_events(self, league=None, limit=None):
        return EventsResponse.model_validate(BOARD), BOARD

    def get_book(self, market_slug: str):
        self.book_calls += 1
        if market_slug in self.fail_on_book:
            raise RuntimeError(f"simulated book failure for {market_slug}")
        return BookResponse.model_validate(BOOK), BOOK


@pytest.fixture
def clean_db():
    Session = get_sessionmaker(get_engine())

    def _wipe(s):
        # Explicit two-step delete: since the tables went partitioned there is
        # no FK cascade from snapshots to levels (a plain FK cannot reference
        # a partitioned table), so relying on it would strand orphan rows.
        s.execute(delete(BookLevel).where(BookLevel.snapshot_id.in_(
            select(MarketSnapshot.id).where(MarketSnapshot.market_slug.like("%test%"))
        )))
        s.execute(delete(MarketSnapshot).where(MarketSnapshot.market_slug.like("%test%")))
        s.commit()

    with Session() as s:
        _wipe(s)
    yield Session
    with Session() as s:
        _wipe(s)


def _recorder(client, sessionmaker, **overrides):
    cfg = RecorderConfig(**overrides) if overrides else RecorderConfig()
    return Recorder(config=cfg, client=client, sessionmaker=sessionmaker)


def test_records_snapshots_and_depth(clean_db):
    Session = clean_db
    rec = _recorder(FakeClient(), Session)
    stats = rec.run_once(captured_at=dt.datetime.now(UTC))

    assert stats.markets_seen == 2
    assert stats.snapshots_written == 2
    assert stats.market_errors == 0

    with Session() as s:
        snap = s.scalar(
            select(MarketSnapshot).where(
                MarketSnapshot.market_slug == "tsc-wnba-test-evt-144pt5"
            )
        )
        assert snap is not None
        # Prices must survive as exact Decimals, not binary approximations.
        assert isinstance(snap.best_bid, Decimal) and snap.best_bid == Decimal("0.9100")
        assert snap.line == Decimal("144.50")
        assert snap.is_live is True  # eventState.live propagated
        assert snap.game_id == "13002436"  # int coerced to text
        assert snap.raw is not None  # full payload retained

        levels = s.scalars(
            select(BookLevel).where(BookLevel.snapshot_id == snap.id)
        ).all()
        assert len(levels) == 2
        assert {lv.side for lv in levels} == {"bid", "offer"}


def test_rerun_at_same_instant_is_idempotent(clean_db):
    """A crash mid-cycle then a rerun must not duplicate or corrupt."""
    Session = clean_db
    at = dt.datetime.now(UTC)
    rec = _recorder(FakeClient(), Session)

    first = rec.run_once(captured_at=at)
    second = rec.run_once(captured_at=at)

    assert first.snapshots_written == 2
    assert second.snapshots_written == 0, "second run should insert nothing"

    with Session() as s:
        count = s.scalar(
            select(func.count(MarketSnapshot.id)).where(
                MarketSnapshot.market_slug.like("%test%")
            )
        )
        assert count == 2, f"expected 2 rows, got {count}"


def test_book_failure_does_not_lose_the_snapshot(clean_db):
    """A failed depth call must still leave top-of-book recorded."""
    Session = clean_db
    client = FakeClient(fail_on_book={"tsc-wnba-test-evt-144pt5"})
    rec = _recorder(client, Session)
    stats = rec.run_once(captured_at=dt.datetime.now(UTC))

    assert stats.book_errors == 1
    assert stats.snapshots_written == 2, "snapshot must survive a book failure"

    with Session() as s:
        snap = s.scalar(
            select(MarketSnapshot).where(
                MarketSnapshot.market_slug == "tsc-wnba-test-evt-144pt5"
            )
        )
        assert snap is not None
        assert s.scalars(select(BookLevel).where(BookLevel.snapshot_id == snap.id)).all() == []


def test_board_failure_returns_cleanly_without_raising(clean_db):
    """The loop must never die — a board fetch failure returns empty stats."""
    Session = clean_db

    class DeadClient(FakeClient):
        def get_league_events(self, league=None, limit=None):
            raise RuntimeError("network down")

    stats = _recorder(DeadClient(), Session).run_once()
    assert stats.snapshots_written == 0  # and crucially: no exception escaped


def test_token_bucket_holds_average_rate():
    """Rate limiter must hold the long-run average under the configured rate."""
    bucket = TokenBucket(rate=20.0, capacity=1)
    start = time.monotonic()
    for _ in range(10):
        bucket.acquire()
    elapsed = time.monotonic() - start
    # 10 tokens at 20/s with capacity 1 => >= ~0.45s. Generous lower bound to
    # avoid flakiness on a loaded machine.
    assert elapsed >= 0.4, f"drained too fast: {elapsed:.3f}s"


def test_cadence_tightens_for_live_games(clean_db):
    """A live game must force the fast poll interval."""
    rec = _recorder(FakeClient(), clean_db)
    assert rec.next_interval_seconds() == rec.config.interval_near_tipoff_seconds


def test_cadence_falls_back_to_fast_poll_when_board_unavailable(clean_db):
    """If we can't tell, over-sample: under-sampling loses data permanently."""

    class DeadClient(FakeClient):
        def get_league_events(self, league=None, limit=None):
            raise RuntimeError("network down")

    rec = _recorder(DeadClient(), clean_db)
    assert rec.next_interval_seconds() == rec.config.interval_near_tipoff_seconds
