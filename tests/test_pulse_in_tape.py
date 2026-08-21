"""PULSE's decisions join the game tape, per the recorded contract.

The contract (core/pulse/storage.py docstring, PR #22) sat honored on the
serializer side and unwired on the tape side: MIN-GSV showed "0 decided
in-play · model was pregame-only" while the server held 70 in-play PULSE
rows for that game. These tests pin the wiring and the never-blend rule.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from core.api import app
from core.storage import get_engine, get_sessionmaker

UTC = dt.timezone.utc
EV = "wnba-pittest-9999-01-03"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def Session():
    return get_sessionmaker(get_engine())


def _fn(html: str, signature: str) -> str:
    i = html.index(signature)
    depth, j = 0, html.index("{", i)
    for k in range(j, len(html)):
        if html[k] == "{":
            depth += 1
        elif html[k] == "}":
            depth -= 1
            if depth == 0:
                return html[i:k + 1]
    raise AssertionError(f"unbalanced braces after {signature!r}")


@pytest.fixture()
def game_rows(Session):
    """One ANCHOR pregame trade + a PULSE lifecycle: a round-trip entry (exit
    filled), a ride entry (settled unexited), and a hold."""
    now = dt.datetime.now(UTC)
    with Session() as s:
        for tbl in ("shadow_orders", "pulse_decisions", "market_snapshots"):
            s.execute(text(f"DELETE FROM {tbl} WHERE market_slug LIKE '%pittest%'"))
        s.execute(text("""
            INSERT INTO shadow_orders (decided_at, idempotency_key, market_slug,
                event_slug, side, limit_price, quantity, would_rest, mode)
            VALUES (:at, 'pittest-a1', 'tsc-wnba-pittest-1', :ev,
                    'BUY_YES', 0.5, 1, true, 'SHADOW')
        """), {"at": now - dt.timedelta(hours=3), "ev": EV})
        # round trip: NO entry 0.40, exit filled 0.30 -> capture = 0.40-0.30
        eid = s.execute(text("""
            INSERT INTO pulse_decisions (decided_at, event_slug, market_slug,
                sports_market_type, strategy, phase, action, side, limit_price,
                contracts, stake_usd, minutes_left_is_estimate, filled_at,
                score, margin, period, minutes_left, reason)
            VALUES (:at, :ev, 'aec-wnba-pittest-2', 'winner', 'winner',
                    'in_play', 'enter', 'no', 0.40, 2.0, 1.2, true, :at,
                    '50-45', 5, 'Q3', 12.5, 'edge over threshold')
            RETURNING id
        """), {"at": now - dt.timedelta(hours=1), "ev": EV}).scalar()
        s.execute(text("""
            INSERT INTO pulse_decisions (decided_at, event_slug, market_slug,
                sports_market_type, strategy, phase, action, side, limit_price,
                contracts, stake_usd, minutes_left_is_estimate, entry_id,
                filled_at)
            VALUES (:at, :ev, 'aec-wnba-pittest-2', 'winner', 'winner',
                    'in_play', 'exit', 'no', 0.30, 2.0, 0, true, :eid, :at)
        """), {"at": now - dt.timedelta(minutes=50), "ev": EV, "eid": eid})
        # ride: YES entry 0.60, settled 1 -> (1 - 0.60) per contract
        s.execute(text("""
            INSERT INTO pulse_decisions (decided_at, event_slug, market_slug,
                sports_market_type, strategy, phase, action, side, limit_price,
                contracts, stake_usd, minutes_left_is_estimate, filled_at,
                settlement)
            VALUES (:at, :ev, 'tsc-wnba-pittest-3', 'total', 'total',
                    'in_play', 'enter', 'yes', 0.60, 1.0, 0.6, true, :at, 1)
        """), {"at": now - dt.timedelta(minutes=40), "ev": EV})
        s.execute(text("""
            INSERT INTO pulse_decisions (decided_at, event_slug, market_slug,
                sports_market_type, strategy, phase, action, side, limit_price,
                contracts, stake_usd, minutes_left_is_estimate)
            VALUES (:at, :ev, 'tsc-wnba-pittest-3', 'total', 'total',
                    'in_play', 'hold', 'yes', 0.55, 0, 0, true)
        """), {"at": now - dt.timedelta(minutes=30), "ev": EV})
        s.commit()
    yield
    with Session() as s:
        for tbl in ("shadow_orders", "pulse_decisions", "market_snapshots"):
            s.execute(text(f"DELETE FROM {tbl} WHERE market_slug LIKE '%pittest%'"))
        s.commit()


def test_pulse_rounds_join_the_tape_and_the_counter_counts_them(client, game_rows):
    d = client.get(f"/api/game/{EV}").json()
    assert d["n_live_decisions"] == 4, "every phase != 'pregame' row counts"
    assert d["n_anchor"] == 1 and d["n_pulse"] == 4
    pulse = [t for t in d["trades"] if t["model"] == "pulse"]
    assert len(pulse) == 4
    assert all(t["context"]["is_live"] for t in pulse), (
        "phase maps to boolean is_live, per the contract")
    assert pulse[0]["context"]["score"] == "50-45", (
        "the engine's own recorded context rides the row")
    assert pulse[0]["context"]["note"] == "edge over threshold", (
        "note synthesized from reason, per the contract")


def test_scoring_is_the_engines_not_rederived(client, game_rows):
    """Round trip and ride P&L must equal the engine's own functions."""
    from core.pulse.live_report import round_trip_capture, settlement_score

    d = client.get(f"/api/game/{EV}").json()
    by = {(t["market_slug"], t["action"]): t for t in d["trades"]
          if t["model"] == "pulse"}

    trip = by[("aec-wnba-pittest-2", "enter")]
    want = round_trip_capture(side="no", entry_price=0.40, exit_price=0.30) * 2.0
    assert trip["pnl_if_filled"] == pytest.approx(want)
    # None, not False: the market has not settled, so there is no win verdict
    # — the round-trip P&L stands alone, independent of settlement. The first
    # draft asserted False and was wrong about its own comment.
    assert trip["bet_won"] is None

    ride = by[("tsc-wnba-pittest-3", "enter")]
    staked, returned = settlement_score(side="yes", entry_price=0.60, settlement=1)
    assert ride["pnl_if_filled"] == pytest.approx((returned - staked) * 1.0)
    assert ride["bet_won"] is True

    hold = by[("tsc-wnba-pittest-3", "hold")]
    assert hold["pnl_if_filled"] is None and hold["bet_won"] is None, (
        "a hold is not a bet and scores nothing")


def test_a_no_side_position_label_says_no(client, game_rows):
    d = client.get(f"/api/game/{EV}").json()
    trip = next(t for t in d["trades"]
                if t["market_slug"] == "aec-wnba-pittest-2" and t["action"] == "enter")
    assert t_no(trip), "the NO side must not be labelled as a YES position"


def t_no(t):
    return "NO" in (t["position"] or "").upper() or t["side"] == "no"


def test_the_banner_only_prints_when_actually_true(client, game_rows):
    """The dispatch's bug in one line: n_live_decisions > 0 must suppress
    'model was pregame-only'. The page keys the banner off this count."""
    d = client.get(f"/api/game/{EV}").json()
    assert d["n_live_decisions"] > 0
    html = Path("static/index.html").read_text()
    assert "d.n_live_decisions ? " in html or "${d.n_live_decisions" in html


# ------------------------------------------------------------------ #
# The page: never blend
# ------------------------------------------------------------------ #


def test_rounds_group_by_instant_AND_model():
    html = Path("static/index.html").read_text()
    fn = _fn(html, "function renderGame(d){")
    assert "x.at === t.decided_at && x.model === model" in fn, (
        "two models' decisions must never share a round, even at the same "
        "timestamp")
    assert '>PULSE</span>' in fn, "PULSE rounds wear the badge"


def test_pulse_rows_show_their_action_not_rest_cross():
    html = Path("static/index.html").read_text()
    fn = _fn(html, "function renderGame(d){")
    assert 't.model === "pulse"' in fn
    assert "t.action.toUpperCase()" in fn
