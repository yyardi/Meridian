"""The account floor annotates in shadow (pulse-live.md, 2026-08-26 note).

The 2026-08-25 five-dollar night: the operator's account drew to ~$5,
effective bankroll read $1.87 against min_bankroll $10, and the shadow
tape recorded ZERO intent all night while the model held +12c edges —
the account's state, not the model's. What is defended here:

* shadow mode records the full desired entry on a below-floor account,
  with the live-faithful truth beside it: binding 'min_bankroll',
  capped_stake_usd 0 (live would not have entered);
* the model-intent gates still refuse on that same tiny account — the
  re-run disables the account floor ALONE, never the model's own gates;
* live mode (enforce_caps) refuses exactly as before.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text

import core.pulse.live as pl
from core.pulse.live import EventAnchors, PulseEngine
from core.pulse.storage import ENTER, PulseDecision
from core.storage import get_engine, get_sessionmaker

UTC = dt.timezone.utc
SLUG = "test-pulse-minbank-a"
EVENT = "test-pulse-minbank-event-a"

_Session = get_sessionmaker(get_engine())

NOW = dt.datetime.now(UTC)

#: The measured five-dollar-night reading, verbatim.
TINY_BANKROLL = 1.87


@pytest.fixture(autouse=True)
def clean():
    yield
    with _Session() as s:
        s.execute(text(
            "delete from pulse_decisions where market_slug like 'test-pulse-minbank%'"))
        s.execute(text(
            "delete from market_snapshots where market_slug like 'test-pulse-minbank%'"))
        s.execute(text(
            "delete from service_heartbeats where service = 'pulse_engine'"))
        s.commit()


def _snap(s, *, bid, ask, at, score="55-45"):
    s.execute(text("""
        insert into market_snapshots
            (market_slug, event_slug, game_id, sports_market_type,
             captured_at, best_bid, best_ask, is_live, event_score,
             event_period, min_trade_qty)
        values (:m, :e, 'minbank-game', :ty, :t, :b, :a, true, :sc, 'Q4', 0.01)
    """), {"m": SLUG, "e": EVENT, "ty": pl.MARKET_WINNER,
           "t": at, "b": bid, "a": ask, "sc": score})
    s.commit()


def _engine(enforce_caps: bool) -> PulseEngine:
    eng = PulseEngine(
        _Session,
        settle_every_seconds=10 ** 9,
        enforce_caps=enforce_caps,
        bankroll_reader=lambda: TINY_BANKROLL,
        settlement_lookup=lambda slug: None,
    )
    eng._anchors[EVENT] = EventAnchors(winner_mid=0.50, totals_mu=165.0)
    return eng


def _enters():
    with _Session() as s:
        return s.query(PulseDecision).filter(
            PulseDecision.market_slug == SLUG,
            PulseDecision.action == ENTER).all()


def test_shadow_records_full_intent_on_a_below_floor_account():
    eng = _engine(enforce_caps=False)
    with _Session() as s:
        _snap(s, bid=0.60, ask=0.62, at=NOW - dt.timedelta(seconds=30))
    eng.cycle()
    rows = _enters()
    assert len(rows) == 1, (
        "the five-dollar night: a clear edge on a live market wrote nothing")
    row = rows[0]
    # Full desired size on the real (tiny) bankroll — nonzero, and no
    # bigger than the account it is a fraction of.
    assert 0 < float(row.stake_usd) < TINY_BANKROLL
    # The live-faithful truth beside it: live would not have entered.
    assert row.binding_constraint == "min_bankroll"
    assert float(row.capped_stake_usd) == 0.0
    assert float(row.capped_contracts) == 0.0
    # And the live-faithful population filter (capped NULL or > 0)
    # excludes this row by construction — no registration amendment.


def test_model_intent_gates_still_refuse_on_the_same_tiny_account():
    """The re-run disables the account floor ALONE: a no-edge market on
    the same $1.87 bankroll still writes nothing."""
    eng = _engine(enforce_caps=False)
    with _Session() as s:
        _snap(s, bid=0.49, ask=0.51, at=NOW - dt.timedelta(seconds=30),
              score="50-50")
    eng.cycle()
    assert _enters() == []


def test_live_mode_still_refuses_below_the_floor():
    eng = _engine(enforce_caps=True)
    with _Session() as s:
        _snap(s, bid=0.60, ask=0.62, at=NOW - dt.timedelta(seconds=30))
    eng.cycle()
    assert _enters() == []
