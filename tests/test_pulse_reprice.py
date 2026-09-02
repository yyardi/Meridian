"""The dynamic-exit-repricing shadow arm (core/pulse/reprice.py + its wiring).

Mutation tests the manager required (docs/math/dynamic-exit-repricing.md):

* FV that MOVES produces a diverging exit; FV that is FLAT produces zero
  divergence — the pinned rule is a shift of the static target, so flat FV
  reproduces the incumbent exactly.
* the staleness bound provably fires: a held FV within the bound reprices off
  the last-good value; beyond the bound the target falls back to static.

The pure-arm tests own the exact numerics (full control of FV); the DB tests
prove the engine persists both arms, paired by entry_decision_id, changing
nothing the engine actually rests.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text

from core.pulse import live as pl
from core.pulse.live import EventAnchors, PulseEngine
from core.pulse.reprice import (
    REPRICE_STALENESS_SECONDS,
    NO,
    YES,
    RepriceArm,
    dynamic_target,
    static_target,
)
from core.pulse.storage import ENTER, PulseDecision, PulseRepriceExit
from core.storage import get_engine, get_sessionmaker

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 9, 2, 1, 0, 0, tzinfo=UTC)


def _arm(side=YES, entry=0.30, pt=0.05, **kw) -> RepriceArm:
    return RepriceArm(
        entry_decision_id=kw.pop("eid", 1), event_slug="e", market_slug="m",
        side=side, strategy="winner", entry_price=entry, contracts=2.0,
        profit_target=pt, opened_at=T0, **kw)


def _at(sec: int) -> dt.datetime:
    return T0 + dt.timedelta(seconds=sec)


# --------------------------------------------------------------------------- #
# The pinned rule
# --------------------------------------------------------------------------- #

def test_static_and_dynamic_frames():
    assert static_target(YES, 0.30, 0.05) == pytest.approx(0.35)
    assert static_target(NO, 0.60, 0.05) == pytest.approx(0.55)
    # flat FV (fv_now == fv_open) reproduces the static target exactly
    assert dynamic_target(YES, 0.30, 0.05, 0.40, 0.40) == pytest.approx(0.35)
    # a rise shifts the YES target up by the FV move; a fall shifts it down
    assert dynamic_target(YES, 0.30, 0.05, 0.55, 0.40) == pytest.approx(0.50)
    assert dynamic_target(YES, 0.30, 0.05, 0.30, 0.40) == pytest.approx(0.25)
    # missing FV falls back to static
    assert dynamic_target(YES, 0.30, 0.05, None, 0.40) == pytest.approx(0.35)


# --------------------------------------------------------------------------- #
# Divergence: FV moves -> diverge; FV flat -> zero (the mutation invariant)
# --------------------------------------------------------------------------- #

def test_flat_fv_never_diverges_and_fills_like_the_static_exit():
    arm = _arm(side=YES, entry=0.30, pt=0.05)          # static target 0.35
    # FV pinned at 0.40 every cycle; the target must stay 0.35 throughout.
    for i in range(1, 6):
        out = arm.observe(mid=0.31, ask=0.32, bid=0.30, at=_at(i),
                          fv=0.40, clock_usable=True)
        assert out.staleness == "fresh"
        assert arm.limit == pytest.approx(0.35)
    assert arm.target_diverged is False
    # and when the mid finally reaches 0.35, it fills exactly where the
    # incumbent's fixed target would have — no divergence.
    out = arm.observe(mid=0.35, ask=0.36, bid=0.34, at=_at(10),
                      fv=0.40, clock_usable=True)
    assert out.filled and arm.fill_price == pytest.approx(0.35)


def test_rising_fv_diverges_and_holds_out_for_a_better_yes_exit():
    arm = _arm(side=YES, entry=0.30, pt=0.05)          # static target 0.35
    # Mid stays below the target while FV climbs, so the target reprices up
    # BEFORE the mid arrives (fill is checked first, against the resting limit).
    arm.observe(mid=0.10, ask=0.12, bid=0.09, at=_at(1), fv=0.40,
                clock_usable=True)                      # fv_open = 0.40
    assert arm.fv_open == pytest.approx(0.40)
    arm.observe(mid=0.10, ask=0.12, bid=0.09, at=_at(2), fv=0.55,
                clock_usable=True)                      # target -> 0.50, DIVERGES
    assert arm.target_diverged is True
    assert arm.limit == pytest.approx(0.50)
    # a mid of 0.36 would have filled the STATIC exit (0.35) — the dynamic
    # exit, now resting at 0.50, holds out instead.
    out = arm.observe(mid=0.36, ask=0.38, bid=0.35, at=_at(3), fv=0.55,
                      clock_usable=True)
    assert not out.filled and not arm.done
    # only when the mid reaches the repriced target does it fill, higher.
    out = arm.observe(mid=0.51, ask=0.53, bid=0.50, at=_at(4), fv=0.55,
                      clock_usable=True)
    assert out.filled and arm.fill_price == pytest.approx(0.50)
    assert arm.fill_price > static_target(YES, 0.30, 0.05)   # a better exit


def test_falling_fv_lowers_the_target_without_tripping_the_stop():
    # FV falls but stays above entry, so the ev stop does NOT fire and we see
    # pure downward repricing (target below static, fills sooner/cheaper).
    arm = _arm(side=YES, entry=0.60, pt=0.05)          # static target 0.65
    arm.observe(mid=0.61, ask=0.63, bid=0.60, at=_at(1), fv=0.72,
                clock_usable=True)                      # fv_open 0.72; mid<0.65
    arm.observe(mid=0.61, ask=0.63, bid=0.60, at=_at(2), fv=0.64,
                clock_usable=True)                      # fv 0.64 > entry 0.60
    assert not arm.is_stop                              # no stop: still edge
    assert arm.target_diverged is True
    assert arm.limit == pytest.approx(0.57)            # 0.65 + (0.64 - 0.72)


def test_no_side_symmetry():
    arm = _arm(side=NO, entry=0.60, pt=0.05)           # static target 0.55
    # A NO buys YES back (fills when mid <= limit); keep mid above 0.55 so it
    # doesn't fill before the target reprices down.
    arm.observe(mid=0.57, ask=0.59, bid=0.56, at=_at(1), fv=0.55,
                clock_usable=True)                      # fv_open = 0.55
    # FV (P(YES)) falls to 0.45 — good for a NO; target drops to 0.45.
    arm.observe(mid=0.57, ask=0.59, bid=0.56, at=_at(2), fv=0.45,
                clock_usable=True)
    assert arm.target_diverged is True
    assert arm.limit == pytest.approx(0.45)
    out = arm.observe(mid=0.44, ask=0.46, bid=0.43, at=_at(3), fv=0.45,
                      clock_usable=True)
    assert out.filled and arm.fill_price == pytest.approx(0.45)


# --------------------------------------------------------------------------- #
# The staleness bound — provably fires
# --------------------------------------------------------------------------- #

def test_staleness_holds_within_bound_then_falls_back_to_static():
    arm = _arm(side=YES, entry=0.30, pt=0.05)          # static target 0.35
    arm.observe(mid=0.31, ask=0.33, bid=0.30, at=_at(0), fv=0.40,
                clock_usable=True)                      # fv_open 0.40
    out = arm.observe(mid=0.31, ask=0.33, bid=0.30, at=_at(5), fv=0.55,
                      clock_usable=True)                # fresh; target 0.50
    assert out.staleness == "fresh" and arm.limit == pytest.approx(0.50)
    # clock goes unusable 30s after the last good FV: HELD at 0.55 -> 0.50.
    out = arm.observe(mid=0.31, ask=0.33, bid=0.30,
                      at=_at(5 + 30), fv=None, clock_usable=False)
    assert out.staleness == "held"
    assert arm.staleness_holds == 1
    assert arm.limit == pytest.approx(0.50)            # still the last-good FV
    # beyond the bound (> REPRICE_STALENESS_SECONDS since the last good FV):
    # FALL BACK to the static target.
    out = arm.observe(mid=0.31, ask=0.33, bid=0.30,
                      at=_at(5 + int(REPRICE_STALENESS_SECONDS) + 1),
                      fv=None, clock_usable=False)
    assert out.staleness == "fallback"
    assert arm.staleness_fallbacks == 1
    assert arm.limit == pytest.approx(0.35)            # reverted to static


def test_fallback_when_no_good_fv_has_ever_arrived():
    arm = _arm(side=YES, entry=0.30, pt=0.05)
    out = arm.observe(mid=0.31, ask=0.33, bid=0.30, at=_at(1), fv=None,
                      clock_usable=False)
    assert out.staleness == "fallback"
    assert arm.fv_open is None and arm.limit == pytest.approx(0.35)


# --------------------------------------------------------------------------- #
# Stop mirror and birth-tick guard
# --------------------------------------------------------------------------- #

def test_ev_stop_mirrors_the_incumbent_and_cuts_to_the_touch():
    arm = _arm(side=YES, entry=0.60, pt=0.05)
    arm.observe(mid=0.61, ask=0.68, bid=0.60, at=_at(1), fv=0.72,
                clock_usable=True)                      # mid<0.65: no fill
    # FV falls to the entry price: the ev stop fires (adverse >= 0).
    out = arm.observe(mid=0.61, ask=0.63, bid=0.60, at=_at(2), fv=0.60,
                      clock_usable=True)
    assert arm.is_stop is True
    assert arm.limit == pytest.approx(0.63)            # cut at the ask (touch)
    assert out.staleness == "n/a"
    # once stopped it no longer reprices, only waits to fill.
    arm.observe(mid=0.50, ask=0.52, bid=0.49, at=_at(3), fv=0.30,
                clock_usable=True)
    assert arm.limit == pytest.approx(0.63)


def test_never_filled_by_the_tick_it_was_born_from():
    arm = _arm(side=YES, entry=0.30, pt=0.05)
    # mid already through the static target, but at == opened_at: no fill.
    out = arm.observe(mid=0.40, ask=0.42, bid=0.39, at=T0, fv=0.40,
                      clock_usable=True)
    assert not out.filled and not arm.done


def test_a_moving_game_diverges_a_flat_one_does_not_count():
    # The mutation spec in one place: run the two synthetic games and count
    # diverging exits. Moving FV -> 1; flat FV -> 0.
    def run(fvs):
        arm = _arm(side=YES, entry=0.30, pt=0.05)
        for i, fv in enumerate(fvs, start=1):
            arm.observe(mid=0.10, ask=0.12, bid=0.09, at=_at(i), fv=fv,
                        clock_usable=True)             # mid too low to fill
        return arm.target_diverged
    assert run([0.40, 0.50, 0.60, 0.70]) is True       # FV moves -> diverges
    assert run([0.40, 0.40, 0.40, 0.40]) is False      # FV flat -> zero


# --------------------------------------------------------------------------- #
# Wiring — the engine persists both arms, paired by entry_decision_id
# --------------------------------------------------------------------------- #

_Session = get_sessionmaker(get_engine())
SLUG = "test-reprice-market"
EVENT = "test-reprice-event"
NOW = dt.datetime.now(UTC)


@pytest.fixture(autouse=True)
def clean():
    yield
    with _Session() as s:
        s.execute(text("delete from pulse_reprice_exits where market_slug like :m"),
                  {"m": SLUG + "%"})
        s.execute(text("delete from pulse_decisions where market_slug like :m"),
                  {"m": SLUG + "%"})
        s.execute(text("delete from market_snapshots where market_slug like :m"),
                  {"m": SLUG + "%"})
        s.execute(text("delete from service_heartbeats where service = 'pulse_engine'"))
        s.commit()


def _snap(s, *, bid, ask, at, score="55-45", period="Q4"):
    s.execute(text("""
        insert into market_snapshots
            (market_slug, event_slug, game_id, sports_market_type, line,
             captured_at, best_bid, best_ask, is_live, event_score,
             event_period, min_trade_qty)
        values (:m, :e, 'g1', :ty, NULL, :t, :b, :a, true, :sc, :p, 0.01)
    """), {"m": SLUG, "e": EVENT, "ty": pl.MARKET_WINNER, "t": at,
           "b": bid, "a": ask, "sc": score, "p": period})
    s.commit()


def _engine():
    eng = PulseEngine(_Session, settle_every_seconds=10 ** 9,
                      bankroll_reader=lambda: 200.0,
                      settlement_lookup=lambda slug: None)
    eng._anchors[EVENT] = EventAnchors(winner_mid=0.50, totals_mu=165.0)
    return eng


def _reprice_rows():
    with _Session() as s:
        return s.query(PulseRepriceExit).filter(
            PulseRepriceExit.market_slug == SLUG
        ).order_by(PulseRepriceExit.id).all()


def test_entry_fill_creates_an_arm_that_rides_to_settlement():
    with _Session() as s:
        _snap(s, bid=0.60, ask=0.62, at=NOW - dt.timedelta(seconds=12))
    eng = _engine()
    eng.cycle()                                         # entry rests
    with _Session() as s:
        _snap(s, bid=0.55, ask=0.59, at=NOW - dt.timedelta(seconds=8))
    eng.cycle()                                         # entry fills -> arm born
    arms = eng._markets[SLUG].reprice_arms
    assert len(arms) == 1
    entry_id = next(iter(arms))
    # Nothing rests behind it: the incumbent exit is the only decision row.
    assert eng._markets[SLUG].position is not None
    # The market goes quiet; force the ride grace and sweep.
    with _Session() as s:
        s.execute(text("delete from market_snapshots where market_slug = :m"),
                  {"m": SLUG})
        s.commit()
    eng._markets[SLUG].last_seen_monotonic = (
        pl.time.monotonic() - pl.POSITION_UNSEEN_RIDE_SECONDS - 10)
    result = eng.cycle()                               # empty cycle -> sweep
    assert result.reprice_finalized == 1
    rows = _reprice_rows()
    assert len(rows) == 1
    r = rows[0]
    assert r.entry_decision_id == entry_id
    assert r.dynamic_outcome == "settlement"
    assert r.dynamic_exit_price is None                # rode; scored at entry settlement
    assert r.side == YES and float(r.entry_price) == pytest.approx(0.60)
    # pairs to the entry with no reconstruction
    with _Session() as s:
        entry = s.query(PulseDecision).filter(
            PulseDecision.id == entry_id).one()
    assert entry.action == "enter" and entry.market_slug == SLUG


def test_dynamic_exit_fills_and_diverges_from_the_static_incumbent():
    with _Session() as s:
        _snap(s, bid=0.60, ask=0.62, at=NOW - dt.timedelta(seconds=40))
    eng = _engine()
    eng.cycle()                                         # entry rests at 0.60
    with _Session() as s:
        _snap(s, bid=0.58, ask=0.60, at=NOW - dt.timedelta(seconds=34))
    eng.cycle()                                         # entry fills at 0.60
    entry_id = next(iter(eng._markets[SLUG].reprice_arms))
    # The game pulls further ahead: FV climbs while the mid stays below the
    # static 0.65, so the repriced target rises above 0.65 BEFORE the mid
    # arrives (fills are checked first, against the resting limit).
    with _Session() as s:
        _snap(s, bid=0.62, ask=0.64, score="75-45",
              at=NOW - dt.timedelta(seconds=20))
    eng.cycle()
    arm = eng._markets[SLUG].reprice_arms.get(entry_id)
    assert arm is not None and arm.target_diverged is True   # held out
    assert arm.limit > static_target(YES, 0.60, 0.05)
    # the mid now reaches the repriced target: the dynamic exit fills, higher.
    with _Session() as s:
        _snap(s, bid=0.82, ask=0.84, score="80-45",
              at=NOW - dt.timedelta(seconds=8))
    result = eng.cycle()
    assert result.reprice_fills == 1
    rows = [r for r in _reprice_rows() if r.entry_decision_id == entry_id]
    assert len(rows) == 1
    r = rows[0]
    assert r.dynamic_outcome == "exit_fill"
    assert r.target_diverged is True
    assert float(r.dynamic_exit_price) > 0.65          # a better exit than static
    assert r.staleness_holds == 0 and r.staleness_fallbacks == 0
