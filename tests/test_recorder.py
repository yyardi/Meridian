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


# --------------------------------------------------------------------- #
# game_id is a JOIN KEY and a CLUSTER KEY, so NULL is not "missing", it is
# a league that silently records nothing usable.
# --------------------------------------------------------------------- #
def _event(**kw):
    from core.polymarket.schemas import Event
    return Event(**kw)


def _stats():
    from core.recorder import RecorderStats
    return RecorderStats()


def test_a_us_team_sport_event_still_uses_the_venues_game_id():
    """Control first: the fallback must not take over the normal path."""
    from core.recorder import _event_key

    st = _stats()
    ev = _event(id="ev-1", slug="mlb-bal-tor-2026-09-13", gameId=10079518)
    assert _event_key(ev, st) == "10079518"
    assert st.game_id_from_fallback == 0


def test_a_cricket_shaped_event_gets_an_id_instead_of_null():
    """★ THE DEFECT. The venue sends `gameId` on US team sports and not on
    cricket or table tennis. Left NULL:

      * run_paper_book joins `g.game_id = s.game_id`, NULL never equals NULL,
        so every strategy in that league prints "no markets on tape" forever
        and it reads as a quiet league. Third league this has hit.
      * clustered() keys on game_id, so a join that ever succeeded with NULLs
        coerced would put every bet in ONE cluster — an interval that is
        arithmetic, not evidence. A number is worse than a blank.

    `event_id` and `event_slug` are already on the same row, so the fallback
    needs no new data and no slug parsing.
    """
    from core.recorder import _event_key

    st = _stats()
    ev = _event(id="ev-cplcr-1", slug="cplcr-bra-gaw-2026-09-13")
    assert _event_key(ev, st) == "ev-cplcr-1"
    assert st.game_id_from_fallback == 1, "the fallback must be COUNTED"
    assert st.game_id_missing == 0


def test_an_event_with_only_a_slug_falls_back_to_it():
    from core.recorder import _event_key

    st = _stats()
    assert _event_key(_event(slug="cplcr-bra-gaw-2026-09-13"), st) == \
        "cplcr-bra-gaw-2026-09-13"


def test_an_event_with_no_identifier_at_all_is_counted_not_guessed():
    """The fix must not silently do nothing either. No identifier means no
    key — counted and logged, never a manufactured one."""
    from core.recorder import _event_key

    st = _stats()
    assert _event_key(_event(title="something with no ids"), st) is None
    assert st.game_id_missing == 1
    assert st.game_id_from_fallback == 0


def test_the_snapshot_row_itself_carries_the_key_not_just_the_helper():
    """Asserted at the CALL SITE. A helper that returns the right value and a
    row that stores `event.game_id` anyway would pass every test above — that
    is the shape that has bitten me twice this week."""
    import inspect

    from core import recorder

    src = inspect.getsource(recorder.Recorder._record_market)
    assert '"game_id": _event_key(event, stats)' in src, (
        "the snapshot row does not use the fallback key")
    assert '"game_id": event.game_id,' not in src


# --------------------------------------------------------------------- #
# board_coverage. A verdict that is true on every long-game league for most
# of every day is the leak-guard failure arriving from the other direction.
# --------------------------------------------------------------------- #
class _Parsed:
    def __init__(self, n):
        self.events = [object()] * n


def _coverage(rows, listing, limit=500):
    """Run the check and return {venue_league: log kwargs}."""
    from core import recorder as R

    captured = {}

    class _Log:
        def info(self, event, **kw):
            if event == "board_coverage":
                captured[kw["venue_league"]] = kw

    class _Client:
        def get_sports_listing(self):
            return listing

    rec = object.__new__(R.Recorder)
    rec._client = _Client()
    rec.config = type("C", (), {"event_limit": limit})()
    old, R.log = R.log, _Log()
    try:
        R.Recorder._log_expected_vs_observed(
            rec, list(rows), [(vl, _Parsed(n)) for vl, n in rows.items()])
    finally:
        R.log = old
    return captured


def test_mlb_shaped_shortfall_is_reported_without_a_defect_verdict():
    """★ THE POINT. /v2/sports and the events endpoint count DIFFERENT
    POPULATIONS: measured on the saved listing, MLB lists 87 against 55 events
    returned over five days, untruncated, while table tennis agrees exactly on
    all four competitions. So `observed < expected` is a property of the
    league, not a gap — and a boolean that is true on every long-game league
    for most of every day is a check nobody reads.

    The numbers are still reported. A reader interprets 43 against 75; a
    permanently-true `missing` tells them nothing.
    """
    got = _coverage({"mlb": 43}, {"mlb": 75})["mlb"]
    assert got["expected"] == 75 and got["observed"] == 43
    assert got["shortfall"] == 32
    assert got["not_swept"] is False
    assert got["swept_nothing"] is False
    assert got["truncated"] is False
    assert "missing" not in got, (
        "the always-true verdict is back; obs < exp is not a defect")


def test_a_listed_competition_that_swept_nothing_is_still_loud():
    """The case the check was built for: an unknown or empty competition
    returns 200 with `events: []`, never a 404, so a wrong slug and a quiet
    board are the same response."""
    got = _coverage({"cplcr": 0}, {"cplcr": 15})["cplcr"]
    assert got["swept_nothing"] is True


def test_a_board_landing_exactly_on_the_limit_reads_as_truncated():
    """This is what caught the default limit of 50 recording a fifth of
    setkameua. Exactly-at-the-limit is the truncation signature: a real board
    can land there and rarely does; a truncated one always does."""
    assert _coverage({"setkameua": 50}, {"setkameua": 237}, limit=50)[
        "setkameua"]["truncated"] is True
    # ...and a board under the limit does not, or the flag would be constant.
    assert _coverage({"setkameua": 237}, {"setkameua": 237}, limit=500)[
        "setkameua"]["truncated"] is False


def test_a_competition_absent_from_the_sweep_is_reported():
    got = _coverage({}, {"ittf": 12})
    assert got == {} or got.get("ittf", {}).get("not_swept") is True


def test_the_exact_agreement_case_flags_nothing():
    """Control. Four flag tests are equally satisfied by a check that flags
    everything; table tennis matching exactly must be silent on all three."""
    got = _coverage({"setkamemd": 19}, {"setkamemd": 19})["setkamemd"]
    assert (got["not_swept"], got["swept_nothing"], got["truncated"]) == \
        (False, False, False)
    assert got["shortfall"] == 0
