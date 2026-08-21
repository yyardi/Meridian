"""The daily budget: live-mode release-on-return, and shadow annotate-not-bind.

LIVE MODE (enforce_caps=True): the 2026-08-20 starvation, pinned — the
release-on-return fix. SHADOW MODE (the default, operator decision
2026-08-21): exposure caps never shrink or block; rows carry full desired
size plus the live-faithful capped size as annotation.

Original module docstring follows.

The daily-budget release: the 2026-08-20 starvation, pinned.

What happened: the in-memory daily exposure counter accumulated gross entry
stakes and never released money. The day's first game (ind-dal, 9 entries,
$3.85 against a $3.84 cap at bankroll $19.21) exhausted the budget by
01:20Z, and the 02:00Z pair sized to zero IN SILENCE for the rest of the
UTC day — zero enters, zero positions, zero holds, zero rows.

What is defended:

* an unfilled entry that stands down releases its budget (money never left);
* a closed round trip releases its entry stake (money came back) — the roll
  works across a whole day, not just inside the first game's budget;
* an OPEN position and a ride-to-settlement keep their budget held — the
  brake still brakes on genuinely committed money;
* the Wednesday shape end-to-end: game A consumes the budget and closes;
  game B, same UTC day, can still enter — the exact scenario that produced
  zero rows;
* and the silence itself: a live market with edge sized to zero now logs
  (throttled), instead of skipping invisibly.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text

from core.pulse import live as pl
from core.pulse.live import EventAnchors, PulseEngine
from core.pulse.storage import ENTER, PulseDecision
from core.storage import get_engine, get_sessionmaker

UTC = dt.timezone.utc
SLUG_A = "test-pulse-budget-a"
SLUG_B = "test-pulse-budget-b"
EVENT_A = "test-pulse-budget-event-a"
EVENT_B = "test-pulse-budget-event-b"

_Session = get_sessionmaker(get_engine())

NOW = dt.datetime.now(UTC)

#: Daily room = 20% × 25 = $5.00; each entry sizes to 5% × 25 = $1.25 (the
#: position cap binds first), so exhausting the budget takes four entries —
#: Wednesday's game took nine. Tests reach the cap with one REAL entry plus a
#: direct top-up of the counter (standing in for the earlier game's other
#: entries; the accumulator itself is one `+=`), then exercise the release
#: paths through real cycles.
BANKROLL = 25.0
ENTRY_STAKE = 1.25          # 5% position cap at this bankroll
DAILY_CAP = 5.0             # 20% at this bankroll


@pytest.fixture(autouse=True)
def clean():
    yield
    with _Session() as s:
        s.execute(text("delete from pulse_decisions where market_slug like 'test-pulse-budget%'"))
        s.execute(text("delete from market_snapshots where market_slug like 'test-pulse-budget%'"))
        s.execute(text("delete from service_heartbeats where service = 'pulse_engine'"))
        s.commit()


def _snap(s, *, slug, event, bid, ask, at, score="55-45"):
    s.execute(text("""
        insert into market_snapshots
            (market_slug, event_slug, game_id, sports_market_type,
             captured_at, best_bid, best_ask, is_live, event_score,
             event_period, min_trade_qty)
        values (:m, :e, 'budget-game', :ty, :t, :b, :a, true, :sc, 'Q4', 0.01)
    """), {"m": slug, "e": event, "ty": pl.MARKET_WINNER,
           "t": at, "b": bid, "a": ask, "sc": score})
    s.commit()


def _engine(enforce_caps=True):
    """enforce_caps=True is the LIVE-mode arm these budget tests pin; the
    shadow default (annotate, never bind) has its own tests below."""
    eng = PulseEngine(
        _Session,
        settle_every_seconds=10 ** 9,
        enforce_caps=enforce_caps,
        bankroll_reader=lambda: BANKROLL,
        settlement_lookup=lambda slug: None,
    )
    for ev in (EVENT_A, EVENT_B):
        eng._anchors[ev] = EventAnchors(winner_mid=0.50, totals_mu=165.0)
    return eng


def _enters(slug):
    with _Session() as s:
        return s.query(PulseDecision).filter(
            PulseDecision.market_slug == slug,
            PulseDecision.action == ENTER).all()


def test_the_wednesday_shape_a_closed_first_game_no_longer_starves_the_second():
    """Game A's entry fills and round-trips (money back), then game B tips on
    the SAME UTC day. Before the fix, B sized to zero; now it enters."""
    eng = _engine()
    with _Session() as s:
        _snap(s, slug=SLUG_A, event=EVENT_A, bid=0.60, ask=0.62,
              at=NOW - dt.timedelta(seconds=30))
    eng.cycle()
    assert len(_enters(SLUG_A)) == 1
    assert eng._daily_staked == pytest.approx(ENTRY_STAKE)
    # The rest of Wednesday's nine entries, standing in by direct top-up.
    eng._note_daily_stake(DAILY_CAP - ENTRY_STAKE, NOW)

    # Game B is starved while the budget is held — the pre-fix behaviour.
    with _Session() as s:
        _snap(s, slug=SLUG_B, event=EVENT_B, bid=0.60, ask=0.62,
              at=NOW - dt.timedelta(seconds=28))
    eng.cycle()
    assert _enters(SLUG_B) == []

    with _Session() as s:                              # A fills...
        _snap(s, slug=SLUG_A, event=EVENT_A, bid=0.55, ask=0.59,
              at=NOW - dt.timedelta(seconds=25))
    eng.cycle()
    # ...and round-trips out. The exit-filling tick is DELIBERATELY out of
    # band (mid 0.975 >= the 0.65 target fills the exit; mid > 0.95 blocks
    # A's own re-entry). Markets are processed in slug order within a cycle,
    # so A's release lands BEFORE B is considered — and B, starved a moment
    # ago, enters with the freed room IN THE SAME CYCLE. The release is
    # proven by B's entry: without it, B stays at zero forever (Wednesday).
    with _Session() as s:
        _snap(s, slug=SLUG_A, event=EVENT_A, bid=0.96, ask=0.99,
              at=NOW - dt.timedelta(seconds=20))
    eng.cycle()

    enters_b = _enters(SLUG_B)
    assert len(enters_b) >= 1, (
        "game B sized to zero on a released budget — the Wednesday starvation")
    assert float(enters_b[0].stake_usd) == pytest.approx(ENTRY_STAKE)
    # Freed 1.25, redeployed 1.25: the counter sits back at the cap, now
    # metering COMMITTED money instead of money-ever.
    assert eng._daily_staked == pytest.approx(DAILY_CAP)


def test_a_withdrawn_entry_releases_its_budget():
    eng = _engine()
    with _Session() as s:
        _snap(s, slug=SLUG_A, event=EVENT_A, bid=0.60, ask=0.62,
              at=NOW - dt.timedelta(seconds=30))
    eng.cycle()
    assert eng._daily_staked == pytest.approx(ENTRY_STAKE)
    with _Session() as s:                    # edge flips; entry stands down
        _snap(s, slug=SLUG_A, event=EVENT_A, bid=0.62, ask=0.66,
              score="45-55", at=NOW - dt.timedelta(seconds=20))
    eng.cycle()
    assert eng._daily_staked == pytest.approx(0.0)


def test_an_open_position_keeps_its_budget_held():
    """Committed money stays counted: entry filled, exit still resting."""
    eng = _engine()
    with _Session() as s:
        _snap(s, slug=SLUG_A, event=EVENT_A, bid=0.60, ask=0.62,
              at=NOW - dt.timedelta(seconds=30))
    eng.cycle()
    with _Session() as s:
        _snap(s, slug=SLUG_A, event=EVENT_A, bid=0.55, ask=0.59,
              at=NOW - dt.timedelta(seconds=25))
    eng.cycle()                              # filled; exit resting; no release
    assert eng._daily_staked == pytest.approx(ENTRY_STAKE)
    eng._note_daily_stake(DAILY_CAP - ENTRY_STAKE, NOW)   # cap held elsewhere
    # And a same-day game B is correctly still starved while A holds the money.
    with _Session() as s:
        _snap(s, slug=SLUG_B, event=EVENT_B, bid=0.60, ask=0.62,
              at=NOW - dt.timedelta(seconds=10))
    eng.cycle()
    assert _enters(SLUG_B) == []


def test_sized_zero_is_loud_now():
    """The silent skip is the bug's other half: with the budget held, game
    B's skip must LOG (throttled), not vanish."""
    eng = _engine()
    with _Session() as s:
        _snap(s, slug=SLUG_A, event=EVENT_A, bid=0.60, ask=0.62,
              at=NOW - dt.timedelta(seconds=30))
    eng.cycle()
    with _Session() as s:
        _snap(s, slug=SLUG_A, event=EVENT_A, bid=0.55, ask=0.59,
              at=NOW - dt.timedelta(seconds=25))
    eng.cycle()                              # position open, budget held
    eng._note_daily_stake(DAILY_CAP - ENTRY_STAKE, NOW)   # cap fully held
    with _Session() as s:
        _snap(s, slug=SLUG_B, event=EVENT_B, bid=0.60, ask=0.62,
              at=NOW - dt.timedelta(seconds=10))
    eng.cycle()
    assert SLUG_B in eng._sized_zero_logged  # the warning fired for B
    first = eng._sized_zero_logged[SLUG_B]
    eng.cycle()                              # within the throttle window
    assert eng._sized_zero_logged[SLUG_B] == first


# --------------------------------------------------------------------- #
# Shadow semantics (the default): caps annotate, never bind
# --------------------------------------------------------------------- #


def test_shadow_mode_records_full_intent_when_the_daily_cap_would_block():
    """The Wednesday shape under the new semantics: the budget is exhausted,
    and the entry STILL lands — full desired size, cap label, capped size 0.
    Two games of model intent can never again be silently discarded."""
    eng = _engine(enforce_caps=False)
    eng._note_daily_stake(DAILY_CAP, NOW)              # budget fully consumed
    with _Session() as s:
        _snap(s, slug=SLUG_B, event=EVENT_B, bid=0.60, ask=0.62,
              at=NOW - dt.timedelta(seconds=10))
    eng.cycle()
    enters = _enters(SLUG_B)
    assert len(enters) == 1, "shadow mode must never block on an exposure cap"
    r = enters[0]
    # Full desired fractional-Kelly size: raw f* = 0.2856/0.40 = 0.714,
    # quarter-Kelly x $25 = $4.46.
    assert float(r.stake_usd) == pytest.approx(0.714 * 0.25 * BANKROLL, rel=1e-2)
    assert r.binding_constraint in ("max_daily_exposure_pct",
                                    "below_minimum_trade_qty")
    assert r.capped_stake_usd is not None
    assert float(r.capped_stake_usd) == pytest.approx(0.0)


def test_shadow_mode_annotates_a_shrinking_cap_and_keeps_desired_size():
    """Uncapped path: at this bankroll the position cap (5%) would shrink a
    $4.46 desire to $1.25 — shadow records $4.46 with the $1.25 annotation."""
    eng = _engine(enforce_caps=False)
    with _Session() as s:
        _snap(s, slug=SLUG_A, event=EVENT_A, bid=0.60, ask=0.62,
              at=NOW - dt.timedelta(seconds=10))
    eng.cycle()
    r = _enters(SLUG_A)[0]
    assert float(r.stake_usd) == pytest.approx(0.714 * 0.25 * BANKROLL, rel=1e-2)
    assert r.binding_constraint == "max_position_size_pct"
    assert float(r.capped_stake_usd) == pytest.approx(ENTRY_STAKE)
    assert float(r.capped_contracts) == pytest.approx(ENTRY_STAKE / 0.60, rel=1e-3)


def test_shadow_mode_still_refuses_what_the_model_does_not_want():
    """No edge is a model opinion, not a cap: shadow refuses it too."""
    eng = _engine(enforce_caps=False)
    with _Session() as s:
        # Trailing badly: fv ~0.11 vs mid 0.61 -> edge on NO side...
        # so use a book where NEITHER side clears the threshold: fv ~ mid.
        _snap(s, slug=SLUG_A, event=EVENT_A, bid=0.88, ask=0.90,
              at=NOW - dt.timedelta(seconds=10))
    eng.cycle()
    assert _enters(SLUG_A) == []
