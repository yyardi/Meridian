"""The tipoff lookup's two failure modes, pinned.

/api/picks resolves each market's tipoff with a LIMIT-1 probe for any snapshot
row carrying a non-null game_start_time. Two things went wrong in production
(2026-08-24, ~4.75s per page load, measured in the api container):

* a market with rows but NO tipoff — futures/series markets by design, or a
  recording gap — forced a scan of every one of its rows in every partition
  before the planner could say "no row" (0.39s cold / 0.16s warm per slug,
  measured on a 50k-row synthetic all-NULL slug), repeated on every request
  because a miss caches nothing. The partial indexes in migration
  f3a8c1d92e47 contain only qualifying rows, making that probe a ~1ms B-tree
  miss.
* the same market was then dropped from the board silently — no tally, so a
  slate vanishing from picks was invisible. `no_tipoff_recorded` counts it.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, text

from core.api import app
from core.storage import MarketSnapshot, Prediction, get_engine, get_sessionmaker

UTC = dt.timezone.utc
_Session = get_sessionmaker(get_engine())

EVENT_NOTIP = "wnba-sea-tor-2099-03-01"
MARKET_NOTIP = f"aec-{EVENT_NOTIP}"
EVENT_TIPPED = "wnba-lv-ind-2099-03-01"
MARKET_TIPPED = f"tsc-{EVENT_TIPPED}-160pt5"


@pytest.fixture
def client():
    return TestClient(app)


def _clean(s):
    s.execute(delete(Prediction).where(Prediction.market_slug.in_(
        [MARKET_NOTIP, MARKET_TIPPED])))
    s.execute(text("DELETE FROM market_snapshots WHERE market_slug IN "
                   "(:a, :b)"), {"a": MARKET_NOTIP, "b": MARKET_TIPPED})


@pytest.fixture
def one_batch_two_markets():
    """A fresh prediction batch: one market whose snapshots never carry a
    tipoff, one whose snapshots do. predicted_at is far-future so this batch
    IS max(predicted_at) — the endpoint reads only it, isolating the test
    from every other row in the run's database."""
    predicted_at = dt.datetime(2099, 2, 28, 12, 0, tzinfo=UTC)
    tip = dt.datetime(2099, 3, 1, 23, 30, tzinfo=UTC)
    with _Session() as s:
        _clean(s)
        for slug, event, mtype, line in (
                (MARKET_NOTIP, EVENT_NOTIP,
                 "basketball_team_full_game_winner", None),
                (MARKET_TIPPED, EVENT_TIPPED,
                 "basketball_team_full_game_total", Decimal("160.5"))):
            s.add(Prediction(
                predicted_at=predicted_at, market_slug=slug, event_slug=event,
                sports_market_type=mtype, line=line, strategy="tipofftest",
                model_probability=Decimal("0.60"), market_bid=Decimal("0.49"),
                market_ask=Decimal("0.51"), market_mid=Decimal("0.50"),
                edge=Decimal("0.09"), model_version="tipofftest",
                is_actionable=True,
            ))
        s.add(MarketSnapshot(
            captured_at=predicted_at, market_slug=MARKET_NOTIP,
            event_slug=EVENT_NOTIP, is_live=False,
            game_start_time=None))
        s.add(MarketSnapshot(
            captured_at=predicted_at, market_slug=MARKET_TIPPED,
            event_slug=EVENT_TIPPED, is_live=False,
            game_start_time=tip))
        s.commit()
    yield
    with _Session() as s:
        _clean(s)
        s.commit()


def test_a_market_with_no_tipoff_is_counted_not_swallowed(
        client, one_batch_two_markets):
    """The silent skip is the bug: a slate vanishing from picks looked
    identical to a quiet evening. The market with no tipoff row is dropped
    AND counted; the market with one appears."""
    d = client.get("/api/picks?league=wnba&horizon_hours=999999").json()
    slugs = {p["market_slug"] for p in d["picks"]}
    assert MARKET_NOTIP not in slugs
    assert d["filtered"]["no_tipoff_recorded"] >= 1
    assert MARKET_TIPPED in slugs, "the hit path must still resolve a tipoff"


def test_the_tipoff_partial_indexes_exist():
    """Migration f3a8c1d92e47: partial indexes are what turn the all-NULL
    slug probe from a full scan of that slug's rows into a B-tree miss. The
    predicate is asserted, not just the name — a plain index under this name
    would silently reintroduce the scan."""
    eng = get_engine()
    with eng.connect() as c:
        rows = {r.indexname: r.indexdef for r in c.execute(text(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE tablename = 'market_snapshots'"))}
    for name, col in (("ix_snapshots_slug_has_start", "market_slug"),
                      ("ix_snapshots_event_has_start", "event_slug")):
        assert name in rows, f"{name} missing"
        assert "game_start_time IS NOT NULL" in rows[name]
        assert col in rows[name]
