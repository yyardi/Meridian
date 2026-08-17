"""The EV stop-loss guard: hypothesis #9 as an alert, #11 as its mirror.

What is defended here:

* the frame conventions, both directions — a NO position's entry cost and FV
  are complements of the stored YES-frame numbers, converted exactly once;
* both verdict directions — EDGE GONE when FV crosses the entry, PRICE NOISE
  when only the price does;
* alert discipline — one push per crossing, an all-clear on recovery, never a
  re-push while the state holds;
* and the structural claim: this module cannot sell. No import of the
  executor or the order client exists in its source.
"""

from __future__ import annotations

import datetime as dt
import inspect
from decimal import Decimal

import pytest
from sqlalchemy import text

from core import ev_guard as ev
from core.storage import PlacedOrder, get_engine, get_sessionmaker

UTC = dt.timezone.utc
SLUG = "test-ev-guard-market"

_Session = get_sessionmaker(get_engine())


@pytest.fixture(autouse=True)
def clean():
    yield
    with _Session() as s:
        s.execute(text("delete from orders where market_slug like :m"), {"m": SLUG + "%"})
        s.commit()


def _position(*, key, side="buy_yes", price="0.23", filled="2",
              fill_status="FILLED", slug=SLUG, market_type="basketball_team_full_game_winner",
              age_hours=1.0) -> int:
    with _Session() as s:
        row = PlacedOrder(
            submitted_at=dt.datetime.now(UTC) - dt.timedelta(hours=age_hours),
            idempotency_key=f"test-ev-{key}",
            mode="HUMAN_CONFIRM",
            market_slug=slug,
            sports_market_type=market_type,
            side=side,
            order_type="ORDER_TYPE_LIMIT",
            limit_price=Decimal(price),
            quantity=Decimal(filled),
            accepted=True,
            venue_order_id=f"v-ev-{key}",
            fill_status=fill_status,
            filled_quantity=Decimal(filled),
        )
        s.add(row)
        s.commit()
        return row.id


# --------------------------------------------------------------------- #
# Frames — both directions, because every frame bug so far cost something
# --------------------------------------------------------------------- #


def test_yes_position_frame_is_the_stored_price():
    assert ev.position_frame("buy_yes", Decimal("0.23")) == ("YES", 0.23)
    assert ev.fv_in_position_frame(0.18, "YES") == 0.18
    assert ev.mid_in_position_frame(0.20, "YES") == 0.20


def test_no_position_frame_is_the_complement_converted_once():
    """A buy_no at stored price.value 0.77 cost the human 0.23, and a formula
    FV of 0.82 (YES frame) is 0.18 on their side. Both conversions, one place."""
    outcome, cost = ev.position_frame("buy_no", Decimal("0.77"))
    assert outcome == "NO"
    assert cost == pytest.approx(0.23)
    assert ev.fv_in_position_frame(0.82, "NO") == pytest.approx(0.18)
    assert ev.mid_in_position_frame(0.80, "NO") == pytest.approx(0.20)


# --------------------------------------------------------------------- #
# Verdicts — the two directions and their boundaries
# --------------------------------------------------------------------- #


def test_edge_gone_when_fv_falls_to_or_below_entry():
    verdict, msg = ev.evaluate(entry_cost=0.23, fv=0.18, mid=0.25)
    assert verdict == ev.EDGE_GONE
    assert "0.18" in msg and "0.23" in msg and "edge gone" in msg
    # Boundary: equal IS gone — at FV == entry the position holds zero edge.
    assert ev.evaluate(entry_cost=0.23, fv=0.23, mid=0.30)[0] == ev.EDGE_GONE


def test_edge_gone_fires_even_while_the_price_is_up():
    """The #9 trigger is the MODEL's number crossing the entry, not the
    market's. A position can be up money with the edge gone."""
    assert ev.evaluate(entry_cost=0.23, fv=0.20, mid=0.30)[0] == ev.EDGE_GONE


def test_price_noise_when_price_falls_but_fv_holds():
    """The #11 mirror: an honest signal for averaging-down."""
    verdict, msg = ev.evaluate(entry_cost=0.23, fv=0.31, mid=0.19)
    assert verdict == ev.PRICE_NOISE
    assert "price noise" in msg and "FV intact" in msg


def test_intact_and_no_fv():
    assert ev.evaluate(entry_cost=0.23, fv=0.31, mid=0.28)[0] == ev.INTACT
    assert ev.evaluate(entry_cost=0.23, fv=None, mid=0.10)[0] == ev.NO_FV


# --------------------------------------------------------------------- #
# Rows from the database
# --------------------------------------------------------------------- #


def test_spread_positions_are_covered_honestly_as_no_fv(monkeypatch):
    """Spreads have no live formula. The row says so — never silently skipped.

    Superseded 2026-08-07: this test used to assert the same of TOTALS, which
    were then uncovered. `core/live_totals_fv.py` closed that gap, so the
    honest-absence contract now applies to spreads, the one remaining type.
    """
    monkeypatch.setattr(ev, "build_live_fv", lambda s: [])
    monkeypatch.setattr(ev, "build_live_totals_fv", lambda s: [])
    _position(key="spr", market_type="basketball_team_full_game_spread")
    with _Session() as s:
        rows = [r for r in ev.build_guard_rows(s) if r.market_slug == SLUG]
    assert len(rows) == 1
    assert rows[0].verdict == ev.NO_FV
    assert "spreads are not priced live" in rows[0].message


def test_totals_positions_now_get_a_verdict_from_the_totals_formula(monkeypatch):
    """The coverage gap order-path named, closed.

    A totals position must be judged by `core/live_totals_fv.py` rather than
    reported as uncoverable. This is the half that matters: the hand-trade
    audit's one measured-positive pocket is live totals.
    """
    monkeypatch.setattr(ev, "build_live_fv", lambda s: [])
    monkeypatch.setattr(
        ev, "build_live_totals_fv",
        lambda s: [_FakeLive(SLUG, fair_value=0.20, mid=0.30)])
    _position(key="tot", market_type="basketball_team_full_game_total", price="0.40")
    with _Session() as s:
        rows = [r for r in ev.build_guard_rows(s) if r.market_slug == SLUG]
    assert len(rows) == 1
    # FV 0.20 has fallen below a 0.40 entry: the #9 trigger.
    assert rows[0].verdict == ev.EDGE_GONE
    assert "no formula FV" not in rows[0].message


def test_unfilled_and_stale_positions_are_not_guarded(monkeypatch):
    monkeypatch.setattr(ev, "build_live_fv", lambda s: [])
    _position(key="open", fill_status="OPEN", filled="0")      # no position
    _position(key="old", age_hours=48)                          # settled long ago
    with _Session() as s:
        rows = [r for r in ev.build_guard_rows(s) if r.market_slug == SLUG]
    assert rows == []


class _FakeLive:
    """Stands in for LiveFV: fair_value/mid in the YES frame."""

    def __init__(self, market_slug, fair_value, mid):
        self.market_slug = market_slug
        self.fair_value = fair_value
        self._mid = mid

    @property
    def mid(self):
        return self._mid


def test_no_side_position_judged_in_its_own_frame(monkeypatch):
    """YES-frame FV 0.85 on a buy_no at price.value 0.77: the human's cost is
    0.23 and their FV is 0.15 — edge gone, judged entirely on their side of
    the book."""
    monkeypatch.setattr(
        ev, "build_live_fv",
        lambda s: [_FakeLive(SLUG, fair_value=0.85, mid=0.80)],
    )
    _position(key="no", side="buy_no", price="0.77")
    with _Session() as s:
        rows = [r for r in ev.build_guard_rows(s) if r.market_slug == SLUG]
    assert rows[0].outcome == "NO"
    assert rows[0].entry_cost == pytest.approx(0.23)
    assert rows[0].fv == pytest.approx(0.15)
    assert rows[0].verdict == ev.EDGE_GONE


# --------------------------------------------------------------------- #
# Alert discipline — transitions only
# --------------------------------------------------------------------- #


def _guard_with(monkeypatch, fv_sequence):
    """An EVGuard whose live FV steps through `fv_sequence` across cycles."""
    pushes: list[tuple[str, str]] = []
    seq = iter(fv_sequence)

    def fake_live(_s):
        fv = next(seq)
        return [] if fv is None else [_FakeLive(SLUG, fair_value=fv, mid=fv)]

    monkeypatch.setattr(ev, "build_live_fv", fake_live)
    guard = ev.EVGuard(
        _Session, topic="test-topic",
        pusher=lambda topic, title, body, **kw: pushes.append((title, body)) or True,
    )
    return guard, pushes


def test_edge_gone_pushes_once_per_crossing_with_all_clear(monkeypatch):
    _position(key="push", side="buy_yes", price="0.23")
    # FV path: intact -> gone -> still gone -> recovered -> gone again.
    guard, pushes = _guard_with(monkeypatch, [0.30, 0.18, 0.17, 0.30, 0.18])

    guard.check_once()                       # intact: nothing
    assert pushes == []
    guard.check_once()                       # crossing: ONE push
    assert len(pushes) == 1
    assert "EDGE GONE" in pushes[0][0]
    assert "0.18" in pushes[0][1] and "0.23" in pushes[0][1]
    assert "unvalidated" in pushes[0][1]     # the caption rides every alert
    guard.check_once()                       # still gone: no re-push
    assert len(pushes) == 1
    guard.check_once()                       # recovery: the all-clear
    assert len(pushes) == 2
    assert "recovered" in pushes[1][0]
    guard.check_once()                       # second crossing re-arms
    assert len(pushes) == 3


def test_no_topic_means_no_pushes_but_rows_still_serve(monkeypatch):
    _position(key="quiet", side="buy_yes", price="0.23")
    monkeypatch.setattr(
        ev, "build_live_fv", lambda s: [_FakeLive(SLUG, fair_value=0.10, mid=0.10)])
    calls = []
    guard = ev.EVGuard(_Session, topic=None,
                       pusher=lambda *a, **k: calls.append(a) or True)
    rows = guard.check_once()
    assert any(r.verdict == ev.EDGE_GONE for r in rows)
    assert calls == []


# --------------------------------------------------------------------- #
# The structural claim: this module cannot sell
# --------------------------------------------------------------------- #


def test_the_guard_has_no_path_to_an_order():
    """NO automatic selling, NO order integration — pinned the same way the
    live-FV strip pins it. If this fails, the alert became an execution path,
    and that must be a decision someone makes out loud.

    Checked on the actual import statements (the docstring is allowed to SAY
    'core.executor' while promising not to import it)."""
    import ast

    tree = ast.parse(inspect.getsource(ev))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            imported.update(f"{node.module}.{a.name}" for a in node.names)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    for forbidden in ("core.executor", "core.polymarket.client", "core.polymarket"):
        assert not any(i == forbidden or i.startswith(forbidden + ".")
                       for i in imported), f"ev_guard imports {forbidden}"
    # And no call sites for the order verbs, docstrings aside.
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not {"submit_limit_order", "cancel_order"} & calls


def test_endpoint_serves_rows_with_the_unvalidated_caption(monkeypatch):
    from fastapi.testclient import TestClient

    from core import api as api_module

    monkeypatch.setattr(ev, "build_live_fv", lambda s: [])
    _position(key="api")
    with TestClient(api_module.app) as c:
        body = c.get("/api/ev-guard").json()
    assert body["tradable"] is False
    assert "unvalidated" in body["caption"]
    ours = [r for r in body["rows"] if r["market_slug"] == SLUG]
    assert ours and ours[0]["verdict"] == ev.NO_FV
