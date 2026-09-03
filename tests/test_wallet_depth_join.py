"""The depth-join's stamp handling — the fix for the ~200x n_zero gap.

`_load_fills_with_depth` matches each fill to the recorded book depth at its
quoted level. The historical Supabase tape stores pre-08-07 `book_levels` that
were fetched TOGETHER with their snapshot, so their own `captured_at` is
genuinely NULL and the parent snapshot's stamp is their exact time. A bare
`bl.captured_at IS NOT NULL` dropped every one of them — the wallet found depth
for 0.3% of August fills where a window search finds 68%.

These tests pin the amended convention (COALESCE own->parent):
  1. fetched-together (NULL own-stamp, parent in window)  -> RECOVERED, flagged
  2. the staleness bound still bites (parent stamp too old) -> clips (rule-18)
  3. own stamp wins and is never backdated by the parent    -> own-stamp match
  4. exact-price discipline is untouched                    -> wrong price clips
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text

from core.quote.wallet import (
    DEPTH_STALENESS_S,
    _absent_meta,
    _load_fills_with_depth,
)
from core.storage import get_sessionmaker
from core.storage.base import get_engine

UTC = dt.timezone.utc
# Pre-epoch era (< DEPTH_OWNSTAMP_EPOCH = 2026-08-07): depth was fetched together
# with the snapshot, so a NULL own-stamp legitimately means "parent is exact".
T0 = dt.datetime(2026, 8, 3, 18, 0, 0, tzinfo=UTC)
# Post-epoch: a NULL own-stamp here is a broken-invariant ANOMALY, gated out.
T_POST = dt.datetime(2026, 8, 20, 18, 0, 0, tzinfo=UTC)
TAG = "test-depthjoin"


def _mk(s, slug, snap_at, level_price, level_stamp, fill_price, fill_at):
    """One market: a snapshot, one offer level, and one ask fill at fill_price."""
    sid = s.execute(text("""
        INSERT INTO market_snapshots (market_slug, game_id, captured_at, is_live)
        VALUES (:slug, :gid, :cap, true) RETURNING id
    """), {"slug": slug, "gid": f"g-{slug}", "cap": snap_at}).scalar()
    s.execute(text("""
        INSERT INTO book_levels (snapshot_id, side, price, quantity, level_index, captured_at)
        VALUES (:sid, 'offer', :px, 40, 0, :cap)
    """), {"sid": sid, "px": level_price, "cap": level_stamp})
    s.execute(text("""
        INSERT INTO shadow_quote_fills
          (market_slug, game_id, regime, side, quote_price, mid_at_quote,
           spread_at_quote, mid_at_fill, quoted_at, filled_at)
        VALUES (:slug, :gid, 'ingame', 'ask', :px, :px, 0.02, :px, :q, :f)
    """), {"slug": slug, "gid": f"g-{slug}", "px": fill_price,
           "q": fill_at, "f": fill_at})


@pytest.fixture(scope="module")
def session():
    engine = get_engine()
    Session = get_sessionmaker(engine)
    with Session() as s:
        # Four markets, one scenario each. Distinct slugs -> no uq collisions.
        _mk(s, f"{TAG}-together", T0, "0.5000", None,
            "0.5000", T0 + dt.timedelta(seconds=5))          # NULL own, in window
        _mk(s, f"{TAG}-stale", T0, "0.5000", None,
            "0.5000", T0 + dt.timedelta(seconds=600))        # NULL own, 600s > bound
        _mk(s, f"{TAG}-ownstamp", T0, "0.6000",
            T0 + dt.timedelta(seconds=3),                    # own stamp, younger
            "0.6000", T0 + dt.timedelta(seconds=8))
        _mk(s, f"{TAG}-wrongpx", T0, "0.7000", None,
            "0.5500", T0 + dt.timedelta(seconds=5))          # level price != quote
        _mk(s, f"{TAG}-postepoch", T_POST, "0.5000", None,   # NULL own AT/AFTER epoch
            "0.5000", T_POST + dt.timedelta(seconds=5))      # -> anomaly, gated out
        s.commit()
        yield s
        s.rollback()
        s.execute(text("""
            DELETE FROM book_levels WHERE snapshot_id IN (
                SELECT id FROM market_snapshots WHERE market_slug LIKE :like)
        """), {"like": f"{TAG}-%"})
        s.execute(text("DELETE FROM shadow_quote_fills WHERE market_slug LIKE :like"),
                  {"like": f"{TAG}-%"})
        s.execute(text("DELETE FROM market_snapshots WHERE market_slug LIKE :like"),
                  {"like": f"{TAG}-%"})
        s.commit()


@pytest.fixture(scope="module")
def by_slug(session):
    fills, _, _, _ = _load_fills_with_depth(session, staleness_s=DEPTH_STALENESS_S)
    return {f.market_slug: f for f in fills if f.market_slug.startswith(TAG)}


def test_fetched_together_is_recovered(by_slug):
    """A NULL-own-stamp level (parent exact, in window) is FOUND, not dropped."""
    f = by_slug[f"{TAG}-together"]
    assert f.depth == 40.0                     # recovered (was 0 under IS NOT NULL)
    assert f.depth_parent_stamped is True      # matched via the parent stamp
    assert f.depth_staleness_s == pytest.approx(5.0)


def test_staleness_bound_still_bites(by_slug):
    """The relaxation is bounded: a parent stamp older than the bound clips."""
    f = by_slug[f"{TAG}-stale"]
    assert f.depth == 0.0                       # 600s > 120s -> conservative zero
    assert f.depth_parent_stamped is False


def test_own_stamp_wins_and_is_not_backdated(by_slug):
    """When the level has its OWN stamp, that stamp is the authority (D's rule)."""
    f = by_slug[f"{TAG}-ownstamp"]
    assert f.depth == 40.0
    assert f.depth_parent_stamped is False      # own stamp used, parent ignored
    # Staleness measured from the OWN stamp (fill T0+8s, own T0+3s) = 5s, NOT
    # from the parent (T0) which would read 8s. Proves no backdating.
    assert f.depth_staleness_s == pytest.approx(5.0)


def test_exact_price_discipline_untouched(by_slug):
    """A level at a different price never matches — exact-4dp still holds."""
    f = by_slug[f"{TAG}-wrongpx"]
    assert f.depth == 0.0


def test_post_epoch_null_is_gated_out_not_inherited(by_slug):
    """A NULL own-stamp AT/AFTER the epoch is an anomaly: counted out, not
    inherited (D's ruling — inheriting would backdate a row that isn't
    fetched-together, and the staleness counter is blind to that)."""
    f = by_slug[f"{TAG}-postepoch"]
    assert f.depth == 0.0                        # gated out, NOT recovered
    assert f.depth_parent_stamped is False


def test_post_epoch_null_is_counted_as_anomaly(session):
    """The gated-out post-epoch NULL is tallied loudly, not silently dropped."""
    _, _, _, n_post_epoch_null = _load_fills_with_depth(
        session, staleness_s=DEPTH_STALENESS_S)
    assert n_post_epoch_null >= 1               # the -postepoch level


def test_absent_meta_measures_the_relaxation(session):
    """The parent-stamp relaxation is counted and its staleness surfaced."""
    fills, _, _, _ = _load_fills_with_depth(session, staleness_s=DEPTH_STALENESS_S)
    mine = [f for f in fills if f.market_slug.startswith(TAG)]
    meta = _absent_meta(mine)
    # Two sized (together + ownstamp); exactly one via a parent stamp. The
    # post-epoch NULL is gated out (depth 0), so it is not among the sized.
    assert meta["n_depth_sized"] == 2
    assert meta["n_depth_parent_stamped"] == 1
    assert meta["depth_parent_stamped_rate"] == pytest.approx(0.5)
    assert meta["parent_stamped_staleness_max_s"] == pytest.approx(5.0)
