"""Live recorder guarantees: rung selection, request cost, tiering, idempotency.

The point of the live recorder is a ~1s cadence, and the thing that makes 1s
possible is spending **one request per cycle** instead of 132. So the load-
bearing test here is `test_price_cycle_costs_one_request`: if that ever fails,
the cadence claim in the module docstring is false regardless of what the other
tests say.

Fake client throughout — fast, deterministic, offline.
"""

from __future__ import annotations

import datetime as dt
import sys
import time
from decimal import Decimal
from unittest import mock

import pytest
from sqlalchemy import delete, func, select

from core.config import RecorderConfig
from core.live_recorder import (
    DEFAULT_INTERVAL_SECONDS,
    DEPTH_DEEP_SECONDS,
    DEPTH_NEAR_SECONDS,
    TIER_DEEP,
    TIER_NEAR,
    DepthSampler,
    LiveRecorder,
    SnapshotWriter,
    build_plan,
    live_events,
    main,
    moneyness,
    select_near_money,
)
from core.polymarket.schemas import BookResponse, EventsResponse
from core.storage import BookLevel, MarketSnapshot, get_engine, get_sessionmaker

UTC = dt.timezone.utc


def _market(slug: str, mtype: str, line: float | None, bid: str, ask: str) -> dict:
    m = {
        "id": slug,
        "slug": slug,
        "sportsMarketType": mtype,
        "bestBidQuote": {"value": bid, "currency": "USD"},
        "bestAskQuote": {"value": ask, "currency": "USD"},
        "orderPriceMinTickSize": 0.01,
        "minimumTradeQty": 0.01,
        "feeCoefficient": 0.06,
    }
    if line is not None:
        m["line"] = line
    return m


TOTAL = "basketball_team_full_game_total"
SPREAD = "basketball_team_full_game_spread"
WINNER = "basketball_team_full_game_winner"

#: A live event with a 7-rung totals ladder spanning deep-in to deep-out of the
#: money, a 3-rung spread ladder, and a moneyline. Mids are, in ladder order:
#: 0.97, 0.90, 0.66, 0.52, 0.30, 0.08, 0.03 — so the four nearest the money are
#: the 205pt5 (0.52), 202pt5 (0.66), 208pt5 (0.30) and 199pt5 (0.90) rungs.
LIVE_MARKETS = [
    _market("tsc-test-193pt5", TOTAL, 193.5, "0.9600", "0.9800"),   # |mid-.5| = .47
    _market("tsc-test-199pt5", TOTAL, 199.5, "0.8800", "0.9200"),   # .40
    _market("tsc-test-202pt5", TOTAL, 202.5, "0.6400", "0.6800"),   # .16
    _market("tsc-test-205pt5", TOTAL, 205.5, "0.5000", "0.5400"),   # .02
    _market("tsc-test-208pt5", TOTAL, 208.5, "0.2800", "0.3200"),   # .20
    _market("tsc-test-211pt5", TOTAL, 211.5, "0.0600", "0.1000"),   # .42
    _market("tsc-test-214pt5", TOTAL, 214.5, "0.0200", "0.0400"),   # .47
    _market("asc-test-pos-3pt5", SPREAD, 3.5, "0.5500", "0.5900"),
    _market("asc-test-pos-6pt5", SPREAD, 6.5, "0.7500", "0.7900"),
    _market("asc-test-neg-9pt5", SPREAD, -9.5, "0.1500", "0.1900"),
    _market("aec-test", WINNER, None, "0.8500", "0.8600"),
]

BOARD = {
    "events": [
        {
            "id": "62459",
            "slug": "wnba-test-live",
            "title": "Test A vs. Test B",
            "startTime": "2026-08-02T02:00:00Z",
            "gameId": 13002436,
            "eventState": {"score": "46-34", "period": "Q3", "live": True},
            "markets": LIVE_MARKETS,
        },
        {
            # Tomorrow — must not be sampled at all.
            "id": "62460",
            "slug": "wnba-test-future",
            "title": "Test C vs. Test D",
            "startTime": "2026-08-09T02:00:00Z",
            "gameId": 13002437,
            "eventState": None,
            "markets": [_market("tsc-test-future-180pt5", TOTAL, 180.5, "0.4900", "0.5100")],
        },
    ]
}

BOOK = {
    "marketData": {
        "marketSlug": "x",
        "bids": [
            {"px": {"value": "0.5100", "currency": "USD"}, "qty": "1559.0000"},
            {"px": {"value": "0.5000", "currency": "USD"}, "qty": "220.0000"},
        ],
        "offers": [{"px": {"value": "0.5300", "currency": "USD"}, "qty": "1505.7800"}],
    }
}


class FakeClient:
    """Stands in for PolymarketGatewayClient, and counts every request."""

    def __init__(self, board: dict | None = None) -> None:
        self.board = board if board is not None else BOARD
        self.board_calls = 0
        self.book_calls: list[str] = []

    def get_league_events(self, league=None, limit=None):
        self.board_calls += 1
        return EventsResponse.model_validate(self.board), self.board

    def get_book(self, market_slug: str):
        self.book_calls.append(market_slug)
        return BookResponse.model_validate(BOOK), BOOK


@pytest.fixture
def clean_db():
    Session = get_sessionmaker(get_engine())

    def _wipe(s):
        ids = select(MarketSnapshot.id).where(MarketSnapshot.market_slug.like("%test%"))
        s.execute(delete(BookLevel).where(BookLevel.snapshot_id.in_(ids)))
        s.execute(delete(MarketSnapshot).where(MarketSnapshot.market_slug.like("%test%")))
        s.commit()

    with Session() as s:
        _wipe(s)
    yield Session
    with Session() as s:
        _wipe(s)


def _recorder(client, sessionmaker, **kwargs):
    return LiveRecorder(
        config=RecorderConfig(), client=client, sessionmaker=sessionmaker, **kwargs
    )


def main_with_args(argv: list[str]) -> int:
    with mock.patch.object(sys, "argv", ["meridian-live-recorder", *argv]):
        return main()


# ------------------------------------------------------------------ #
# Rung selection — pure, no database
# ------------------------------------------------------------------ #


def test_moneyness_ranks_at_the_money_first():
    board = EventsResponse.model_validate(BOARD)
    totals = [m for m in board.events[0].markets if m.sports_market_type == TOTAL]
    ranked = sorted(totals, key=moneyness)
    assert ranked[0].slug == "tsc-test-205pt5", "mid 0.52 is the at-the-money rung"
    assert ranked[-1].slug in {"tsc-test-193pt5", "tsc-test-214pt5"}


def test_select_near_money_keeps_four_per_ladder_and_all_of_the_moneyline():
    board = EventsResponse.model_validate(BOARD)
    chosen = select_near_money(board.events[0].markets, per_type=4)

    totals = {s for s in chosen if s.startswith("tsc-")}
    assert totals == {
        "tsc-test-205pt5",  # .02
        "tsc-test-202pt5",  # .16
        "tsc-test-208pt5",  # .20
        "tsc-test-199pt5",  # .40
    }
    # The 22-26c-spread rungs at the ends of the ladder are excluded: they do
    # not trade, so they do not get the request budget.
    assert "tsc-test-214pt5" not in chosen
    assert "tsc-test-193pt5" not in chosen

    # Spread ladder is shorter than the cap, so all of it survives; moneyline
    # is a single market and is always in.
    assert {"asc-test-pos-3pt5", "asc-test-pos-6pt5", "asc-test-neg-9pt5"} <= chosen
    assert "aec-test" in chosen


def test_ladders_are_ranked_independently():
    """A tight spread ladder must not crowd out every totals rung."""
    board = EventsResponse.model_validate(BOARD)
    chosen = select_near_money(board.events[0].markets, per_type=2)
    # Each ladder yields its own two, rather than one ladder taking all four.
    assert len([s for s in chosen if s.startswith("tsc-")]) == 2
    assert len([s for s in chosen if s.startswith("asc-")]) == 2
    assert "aec-test" in chosen  # moneyline is a single market, never ranked out


def test_market_with_no_quote_sorts_last_rather_than_crashing():
    board = EventsResponse.model_validate(
        {"events": [{"slug": "e", "markets": [
            _market("tsc-test-a", TOTAL, 1.5, "0.5000", "0.5000"),
            {"slug": "tsc-test-noquote", "sportsMarketType": TOTAL, "line": 2.5},
        ]}]}
    )
    markets = board.events[0].markets
    assert moneyness(markets[1]) == float("inf")
    assert sorted(markets, key=moneyness)[0].slug == "tsc-test-a"


def test_plan_excludes_events_that_are_not_live_or_imminent():
    board = EventsResponse.model_validate(BOARD)
    now = dt.datetime(2026, 8, 2, 3, 0, tzinfo=UTC)
    plan = build_plan(board, now=now)

    assert "tsc-test-future-180pt5" not in plan.all_live
    assert len(plan.all_live) == len(LIVE_MARKETS)
    assert plan.near < plan.all_live
    assert plan.deep == plan.all_live - plan.near


def test_plan_tiers_every_live_market():
    plan = build_plan(EventsResponse.model_validate(BOARD),
                      now=dt.datetime(2026, 8, 2, 3, 0, tzinfo=UTC))
    assert plan.tier("tsc-test-205pt5") == TIER_NEAR
    assert plan.tier("tsc-test-214pt5") == TIER_DEEP
    assert plan.tier("tsc-test-future-180pt5") is None


def test_imminent_game_is_recorded_before_tipoff():
    """The pregame-to-live handover is itself worth having."""
    board = EventsResponse.model_validate({"events": [{
        "slug": "wnba-test-soon", "startTime": "2026-08-02T03:05:00Z",
        "eventState": None, "markets": [_market("tsc-test-soon", TOTAL, 1.5, "0.5", "0.51")],
    }]})
    now = dt.datetime(2026, 8, 2, 3, 0, tzinfo=UTC)
    assert len(live_events(board, now=now, pre_tipoff_minutes=10.0)) == 1
    assert len(live_events(board, now=now, pre_tipoff_minutes=2.0)) == 0


def test_naive_start_time_does_not_raise():
    """A timestamp without an offset must not take the process down."""
    board = EventsResponse.model_validate({"events": [{
        "slug": "wnba-test-naive", "startTime": "2026-08-02T03:05:00",
        "eventState": None, "markets": [],
    }]})
    assert live_events(board, now=dt.datetime(2026, 8, 2, 3, 0, tzinfo=UTC)) != []


# ------------------------------------------------------------------ #
# The cadence claim
# ------------------------------------------------------------------ #


def test_price_cycle_costs_one_request(clean_db):
    """The whole basis of the 1s cadence: top-of-book is one board call.

    The board payload embeds bestBidQuote/bestAskQuote for every market, so a
    price cycle issues no order-book calls at all. If this regresses to
    per-market book calls, 1s becomes arithmetically impossible at the
    documented 20 req/s ceiling.
    """
    client = FakeClient()
    rec = _recorder(client, clean_db, capture_depth=False)
    rec.run_cycle(captured_at=dt.datetime.now(UTC))

    assert client.board_calls == 1
    assert client.book_calls == [], "a price cycle must issue zero book calls"


def test_cycle_records_only_live_markets(clean_db):
    Session = clean_db
    rec = _recorder(FakeClient(), Session, capture_depth=False)
    stats = rec.run_cycle(captured_at=dt.datetime.now(UTC))

    assert stats.markets_seen == len(LIVE_MARKETS)
    assert stats.snapshots_written == len(LIVE_MARKETS)

    with Session() as s:
        slugs = set(s.scalars(
            select(MarketSnapshot.market_slug).where(MarketSnapshot.market_slug.like("%test%"))
        ).all())
    assert "tsc-test-future-180pt5" not in slugs, "tomorrow's board must not be polled"


def test_snapshot_row_shape_matches_the_pregame_recorder(clean_db):
    """A live row and a pregame row must remain the same object."""
    Session = clean_db
    rec = _recorder(FakeClient(), Session, capture_depth=False)
    rec.run_cycle(captured_at=dt.datetime.now(UTC))

    with Session() as s:
        snap = s.scalar(
            select(MarketSnapshot).where(MarketSnapshot.market_slug == "tsc-test-205pt5")
        )
    assert snap is not None
    # Exact Decimals, never binary approximations.
    assert isinstance(snap.best_bid, Decimal) and snap.best_bid == Decimal("0.5000")
    assert snap.line == Decimal("205.50")
    assert snap.is_live is True
    assert snap.game_id == "13002436"      # int coerced to text
    assert snap.event_score == "46-34"
    assert snap.raw is not None            # full payload retained
    assert snap.book_tier == TIER_NEAR


def test_raw_payload_is_retained_periodically_not_every_cycle(clean_db):
    """`raw` is 62% of a row and 5 near-identical copies/second is a disk bill.

    Prices are untouched — they live in typed columns at full resolution. What
    is sampled is the schema-drift safety net, which a 30s copy serves as well
    as a 200ms one.
    """
    Session = clean_db
    rec = _recorder(FakeClient(), Session, capture_depth=False,
                    raw_snapshot_seconds=3600.0)

    at = dt.datetime.now(UTC)
    rec.run_cycle(captured_at=at)
    rec.run_cycle(captured_at=at + dt.timedelta(milliseconds=200))

    with Session() as s:
        rows = s.scalars(
            select(MarketSnapshot)
            .where(MarketSnapshot.market_slug == "tsc-test-205pt5")
            .order_by(MarketSnapshot.captured_at)
        ).all()

    assert len(rows) == 2
    assert rows[0].raw is not None, "first sighting keeps the payload"
    assert rows[1].raw is None, "200ms later it is redundant"
    # The price is still recorded at full resolution on both rows.
    assert rows[1].best_bid == Decimal("0.5000")
    assert rows[1].best_ask == Decimal("0.5400")


def test_deep_rungs_are_throttled_but_near_rungs_are_not(clean_db):
    """Deep rungs get the old 30s cadence; near rungs get every cycle."""
    Session = clean_db
    client = FakeClient()
    rec = _recorder(client, Session, capture_depth=False, deep_snapshot_seconds=3600.0)

    at = dt.datetime.now(UTC)
    first = rec.run_cycle(captured_at=at)
    second = rec.run_cycle(captured_at=at + dt.timedelta(seconds=1))

    assert first.near > 0 and first.deep > 0
    # Second cycle, one second later: near rungs resample, deep ones do not.
    assert second.near == first.near
    assert second.deep == 0
    assert second.snapshots_written == second.near


def test_rerun_at_same_instant_is_idempotent(clean_db):
    """A crash mid-cycle then a rerun must not duplicate or corrupt."""
    Session = clean_db
    at = dt.datetime.now(UTC)
    rec = _recorder(FakeClient(), Session, capture_depth=False)

    first = rec.run_cycle(captured_at=at)
    second = rec.run_cycle(captured_at=at)

    assert first.snapshots_written == len(LIVE_MARKETS)
    assert second.snapshots_written == 0, "second run should insert nothing"

    with Session() as s:
        count = s.scalar(
            select(func.count(MarketSnapshot.id)).where(
                MarketSnapshot.market_slug.like("%test%")
            )
        )
    assert count == len(LIVE_MARKETS)


def test_board_failure_returns_cleanly_without_raising(clean_db):
    """The loop must never die — a board fetch failure returns empty stats."""

    class DeadClient(FakeClient):
        def get_league_events(self, league=None, limit=None):
            raise RuntimeError("network down")

    stats = _recorder(DeadClient(), clean_db, capture_depth=False).run_cycle()
    assert stats.snapshots_written == 0  # and crucially: no exception escaped


def test_no_live_game_writes_nothing(clean_db):
    """Idle boards must not be recorded — that is the pregame recorder's job."""
    quiet = {"events": [dict(BOARD["events"][1])]}  # tomorrow only
    stats = _recorder(FakeClient(quiet), clean_db, capture_depth=False).run_cycle()
    assert stats.markets_seen == 0
    assert stats.snapshots_written == 0


# ------------------------------------------------------------------ #
# Depth sampling
# ------------------------------------------------------------------ #


def test_depth_samples_only_the_requested_tier(clean_db):
    Session = clean_db
    client = FakeClient()
    rec = _recorder(client, Session, capture_depth=False)
    rec.run_cycle(captured_at=dt.datetime.now(UTC))

    with Session() as s:
        ids = {
            slug: sid
            for sid, slug in s.execute(
                select(MarketSnapshot.id, MarketSnapshot.market_slug).where(
                    MarketSnapshot.market_slug.like("%test%")
                )
            ).all()
        }

    plan = build_plan(EventsResponse.model_validate(BOARD),
                      now=dt.datetime(2026, 8, 2, 3, 0, tzinfo=UTC))
    sampler = DepthSampler(
        client=client, sessionmaker=Session, max_book_levels=50, concurrency=4
    )
    written = sampler.sample(sorted(plan.near), ids, tier=TIER_NEAR)

    assert set(client.book_calls) == plan.near, "only near-money rungs were fetched"
    assert written == 3 * len(plan.near)  # 2 bids + 1 offer per market


def test_depth_rows_carry_their_own_timestamp(clean_db):
    """Depth runs on a slower loop than price, so it must not inherit the
    snapshot's `captured_at` — the depth-signal question is about ordering."""
    Session = clean_db
    client = FakeClient()
    rec = _recorder(client, Session, capture_depth=False)

    snapshot_at = dt.datetime.now(UTC) - dt.timedelta(seconds=30)
    rec.run_cycle(captured_at=snapshot_at)

    with Session() as s:
        snap = s.scalar(
            select(MarketSnapshot).where(MarketSnapshot.market_slug == "tsc-test-205pt5")
        )
        ids = {snap.market_slug: snap.id}

    sampler = DepthSampler(client=client, sessionmaker=Session, max_book_levels=50)
    sampler.sample(["tsc-test-205pt5"], ids, tier=TIER_NEAR)

    with Session() as s:
        level = s.scalar(select(BookLevel).where(BookLevel.snapshot_id == ids["tsc-test-205pt5"]))
    assert level.captured_at is not None
    assert level.captured_at > snapshot_at, "depth is younger than its parent snapshot"


def test_depth_respects_max_book_levels(clean_db):
    Session = clean_db
    client = FakeClient()
    rec = _recorder(client, Session, capture_depth=False)
    rec.run_cycle(captured_at=dt.datetime.now(UTC))

    with Session() as s:
        snap = s.scalar(
            select(MarketSnapshot).where(MarketSnapshot.market_slug == "tsc-test-205pt5")
        )
        ids = {snap.market_slug: snap.id}

    sampler = DepthSampler(client=client, sessionmaker=Session, max_book_levels=1)
    sampler.sample(["tsc-test-205pt5"], ids, tier=TIER_NEAR)

    with Session() as s:
        levels = s.scalars(
            select(BookLevel).where(BookLevel.snapshot_id == ids["tsc-test-205pt5"])
        ).all()
    assert len(levels) == 2, "one bid + one offer when capped at 1 level a side"


def test_book_failure_does_not_lose_the_snapshot(clean_db):
    """A failed depth call must still leave top-of-book recorded."""
    Session = clean_db

    class BadBooks(FakeClient):
        def get_book(self, market_slug: str):
            self.book_calls.append(market_slug)
            raise RuntimeError("simulated book failure")

    client = BadBooks()
    rec = _recorder(client, Session, capture_depth=False)
    rec.run_cycle(captured_at=dt.datetime.now(UTC))

    with Session() as s:
        snap = s.scalar(
            select(MarketSnapshot).where(MarketSnapshot.market_slug == "tsc-test-205pt5")
        )
        ids = {snap.market_slug: snap.id}

    sampler = DepthSampler(client=client, sessionmaker=Session, max_book_levels=50)
    written = sampler.sample(["tsc-test-205pt5"], ids, tier=TIER_NEAR)

    assert written == 0
    assert sampler.book_errors == 1
    with Session() as s:
        assert s.scalar(
            select(MarketSnapshot).where(MarketSnapshot.market_slug == "tsc-test-205pt5")
        ) is not None


def test_depth_skips_markets_with_no_snapshot_yet(clean_db):
    """Publishing a plan before the first write must not fabricate a foreign key."""
    sampler = DepthSampler(
        client=FakeClient(), sessionmaker=clean_db, max_book_levels=50
    )
    assert sampler.sample(["tsc-test-205pt5"], {}, tier=TIER_NEAR) == 0


def test_sampler_publish_retains_ids_for_throttled_deep_rungs():
    """A deep rung is snapshotted every 30s; its depth must still find a row."""
    sampler = DepthSampler(client=FakeClient(), sessionmaker=None, max_book_levels=50)
    plan = build_plan(EventsResponse.model_validate(BOARD),
                      now=dt.datetime(2026, 8, 2, 3, 0, tzinfo=UTC))

    sampler.publish(plan, {"tsc-test-214pt5": 1, "tsc-test-205pt5": 2})
    sampler.publish(plan, {"tsc-test-205pt5": 3})  # next cycle: near rungs only

    _, ids = sampler._current()
    assert ids["tsc-test-214pt5"] == 1, "deep rung id survives cycles that skip it"
    assert ids["tsc-test-205pt5"] == 3, "near rung id is refreshed"


# ------------------------------------------------------------------ #
# Request budget
# ------------------------------------------------------------------ #


# ------------------------------------------------------------------ #
# The async writer — polling and persisting are different problems
# ------------------------------------------------------------------ #


def test_writer_is_synchronous_until_started(clean_db):
    """Tests and `--once` must be able to write without any concurrency."""
    writer = SnapshotWriter(clean_db)
    assert writer.is_async is False

    rows = [{
        "captured_at": dt.datetime.now(UTC), "market_slug": "tsc-test-sync",
        "is_live": True, "best_bid": Decimal("0.5"), "best_ask": Decimal("0.52"),
    }]
    ids = writer.submit(rows)
    assert set(ids) == {"tsc-test-sync"}, "sync mode returns ids immediately"


def test_writer_drains_everything_on_stop(clean_db):
    """An ordinary shutdown or redeploy must lose nothing.

    The buffer is the price paid for decoupling the poll loop from a ~330ms
    Supabase round trip. It is only acceptable because a clean exit flushes.
    """
    Session = clean_db
    writer = SnapshotWriter(Session)
    writer.start()
    assert writer.is_async

    at = dt.datetime.now(UTC)
    for i in range(20):
        writer.submit([{
            "captured_at": at + dt.timedelta(milliseconds=200 * i),
            "market_slug": f"tsc-test-drain-{i}", "is_live": True,
            "best_bid": Decimal("0.5"), "best_ask": Decimal("0.52"),
        }])
    writer.stop()

    with Session() as s:
        n = s.scalar(
            select(func.count(MarketSnapshot.id)).where(
                MarketSnapshot.market_slug.like("tsc-test-drain-%")
            )
        )
    assert n == 20, f"stop() must flush the queue; wrote {n}/20"


def test_writer_batches_multiple_cycles_into_one_statement(clean_db):
    """DB latency should change the batch size, not the sampling rate."""
    Session = clean_db
    writer = SnapshotWriter(Session)

    at = dt.datetime.now(UTC)
    for i in range(12):
        writer._queue.put([{
            "captured_at": at + dt.timedelta(milliseconds=200 * i),
            "market_slug": f"tsc-test-batch-{i}", "is_live": True,
            "best_bid": Decimal("0.5"), "best_ask": Decimal("0.52"),
        }])

    writer._drain_once(block=False)
    assert writer.batches == 1, "12 queued cycles must collapse to one statement"
    assert writer.rows_written == 12


def test_writer_never_blocks_the_poll_loop_when_the_queue_fills(clean_db):
    """A dead database must not jam the recorder into losing every future cycle."""
    writer = SnapshotWriter(clean_db)
    writer._thread = object()  # pretend async without starting the drain
    assert writer.is_async

    row = [{"captured_at": dt.datetime.now(UTC), "market_slug": "x", "is_live": True}]
    for _ in range(SnapshotWriter.MAX_PENDING + 25):
        writer.submit(row)

    assert writer.dropped > 0, "overflow must be counted, not silently swallowed"
    assert writer._queue.qsize() == SnapshotWriter.MAX_PENDING


def test_writer_publishes_ids_for_the_depth_sampler(clean_db):
    """Depth hangs off snapshot ids, which now arrive from the writer thread."""
    seen: list[dict] = []
    writer = SnapshotWriter(clean_db, on_ids=seen.append)

    writer._queue.put([{
        "captured_at": dt.datetime.now(UTC), "market_slug": "tsc-test-ids",
        "is_live": True, "best_bid": Decimal("0.5"), "best_ask": Decimal("0.52"),
    }])
    writer._drain_once(block=False)

    assert seen and "tsc-test-ids" in seen[0]


def test_writer_survives_a_database_failure(clean_db):
    """The loop must never die — a failed write is logged, not raised."""

    class Boom:
        def __call__(self):
            raise RuntimeError("database gone")

    writer = SnapshotWriter(Boom())
    assert writer.submit([{"market_slug": "x"}]) == {}  # and no exception escaped


def test_steady_state_request_rate_fits_the_budget():
    """Arithmetic check on the documented ceiling, with four games live.

    The gateway allows 20 req/s per IP and the pregame recorder holds 5, so the
    live recorder's budget is 12 (MERIDIAN_RPS in docker-compose.yml). This
    test is the thing that fails if someone tightens the price loop, widens the
    near-money set, or speeds up depth past what the budget allows — all three
    of which are one-character changes.
    """
    board = EventsResponse.model_validate(BOARD)
    plan = build_plan(board, now=dt.datetime(2026, 8, 2, 3, 0, tzinfo=UTC))

    games = 4  # a full WNBA slate running concurrently
    # One board call serves every game at once, so price does not scale.
    price_rps = 1.0 / DEFAULT_INTERVAL_SECONDS
    near_rps = games * len(plan.near) / DEPTH_NEAR_SECONDS
    deep_rps = games * len(plan.deep) / DEPTH_DEEP_SECONDS
    total = price_rps + near_rps + deep_rps

    assert total <= 12.0, f"steady-state {total:.1f} req/s exceeds the 12 req/s budget"


def test_price_loop_is_the_measured_200ms():
    """The interval is a measured quantity, not a preference.

    Detected changes/second peaks at 200-300ms and halves by 1s. If someone
    relaxes this back toward 1s, ~40% of observable quote changes go
    unrecorded — and unlike a bug, that loss is silent and unrecoverable.
    """
    assert DEFAULT_INTERVAL_SECONDS == 0.2


def test_interval_cannot_be_set_below_the_floor():
    """A typo must not become a hot loop against the gateway."""
    with pytest.raises(SystemExit):
        main_with_args(["--interval", "0.001"])


def test_sleep_returns_immediately_when_the_cycle_overran():
    """The interval is a floor, not a promise.

    p90 board latency (226ms) exceeds the 200ms target, so cycles do overrun.
    When they do the loop must run back-to-back at the speed the gateway
    allows, never queue a request on top of one still in flight.
    """
    rec = _recorder(FakeClient(), None, capture_depth=False)
    stopping = {"flag": False}

    started = time.monotonic() - 5.0  # a cycle that already took 5 seconds
    t0 = time.monotonic()
    rec._sleep_remaining(started, 0.2, stopping)
    assert time.monotonic() - t0 < 0.05, "must not sleep after an overrun"


def test_sleep_honours_the_interval_when_the_cycle_was_fast():
    rec = _recorder(FakeClient(), None, capture_depth=False)
    stopping = {"flag": False}

    started = time.monotonic()
    rec._sleep_remaining(started, 0.3, stopping)
    assert time.monotonic() - started >= 0.29
