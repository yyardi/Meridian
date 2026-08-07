"""The fill watcher, the pre-authorized exit, and the amended invariant.

The scenarios pinned here are the ones from the build spec, each of which is a
real way to lose money silently:

* a partial fill exited at the ordered size (overselling);
* a venue-side cancel the `orders` table never hears about (orders #1–3);
* a hand trade in the same market being attributed to a button order;
* the NO-frame conversion applied twice or not at all;
* an exit the human believes exists failing silently;
* a pre-authorized flag usable outside HUMAN_CONFIRM.
"""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from core import api as api_module
from core import heartbeat as hb
from core.fill_watcher import (
    CANCELLED,
    EXPIRED,
    FILLED,
    OPEN,
    PARTIAL,
    FillWatcher,
    OrderEvent,
    extract_order_events,
    reconcile_order,
)
from core.polymarket.client import OrderSubmissionError, USCredentials
from core.storage import PendingExit, PlacedOrder, get_engine, get_sessionmaker

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 8, 5, 18, 0, tzinfo=UTC)

SLUG = "test-fill-watcher-market"

_Session = get_sessionmaker(get_engine())

CREDS = USCredentials(key_id="test", secret="test")


@pytest.fixture(autouse=True)
def clean():
    """Scoped to this file's own slug (the B6 lesson)."""
    yield
    with _Session() as s:
        s.execute(text(
            "delete from pending_exits where market_slug like :m"), {"m": SLUG + "%"})
        s.execute(text("delete from orders where market_slug like :m"), {"m": SLUG + "%"})
        s.execute(text(
            "delete from predictions where market_slug like :m"), {"m": SLUG + "%"})
        s.commit()


def _entry(*, key, venue_id="v-100", qty="5", price="0.20", outcome="yes",
           accepted=True, fill_status=None, filled=None, slug=SLUG) -> PlacedOrder:
    return PlacedOrder(
        submitted_at=NOW,
        idempotency_key=f"test-fw-{key}",
        mode="HUMAN_CONFIRM",
        market_slug=slug,
        side=f"buy_{outcome}",
        order_type="ORDER_TYPE_LIMIT",
        limit_price=Decimal(price),
        quantity=Decimal(qty),
        accepted=accepted,
        venue_order_id=venue_id,
        fill_status=fill_status,
        filled_quantity=None if filled is None else Decimal(filled),
    )


def _exit_for(s, entry: PlacedOrder, *, outcome="YES",
              limit_price="0.30", typed_price="0.30") -> PendingExit:
    x = PendingExit(
        entry_order_id=entry.id,
        market_slug=entry.market_slug,
        outcome=outcome,
        limit_price=Decimal(limit_price),
        typed_price=Decimal(typed_price),
        state="PENDING",
    )
    s.add(x)
    s.commit()
    return x


# --------------------------------------------------------------------------- #
# Fakes and payload builders — nothing in this file touches the network.
# The payload shapes are copies of the venue's OBSERVED schema (findings V19):
# activities wrap a `trade` whose aggressor/passive executions embed the full
# order object, and the embedded order carries the authoritative `state` and
# `cumQuantity`.
# --------------------------------------------------------------------------- #


def trade_activity(order_id: str, *, state: str, cum, last_shares="1.0000",
                   side="passiveExecution", market=SLUG,
                   transact="2026-08-07T02:05:51.436320896Z") -> dict:
    """One ACTIVITY_TYPE_TRADE in the venue's real nested shape."""
    return {
        "type": "ACTIVITY_TYPE_TRADE",
        "trade": {
            "id": f"T-{order_id}-{transact[-12:]}",
            "aggressorExecution": None,
            "marketSlug": market,
            side: {
                "id": f"E-{order_id}",
                "order": {
                    "id": order_id,
                    "marketSlug": market,
                    "state": state,
                    # The venue serves this as a bare number, rounded to 2dp.
                    "cumQuantity": cum,
                    "leavesQuantity": 0,
                },
                "lastShares": last_shares,
                "type": "EXECUTION_TYPE_FILL",
                "transactTime": transact,
            },
        },
    }


def resolution_activity(market: str) -> dict:
    return {
        "type": "ACTIVITY_TYPE_POSITION_RESOLUTION",
        "positionResolution": {"marketSlug": market, "beforePosition": {}},
    }


class FakeResp:
    def __init__(self, status_code: int, body: str, elapsed_ms: float = 5.0):
        self.status_code = status_code
        self.body_text = body
        self.elapsed_ms = elapsed_ms
        self.server_latency_ms = None


class FakeReadClient:
    """Serves a fixed activities list (one page, eof); positions empty."""

    def __init__(self, activities: list[dict]):
        self.activities = activities

    def get(self, path: str, params=None) -> FakeResp:
        if "activities" in path:
            return FakeResp(200, json.dumps(
                {"activities": self.activities, "nextCursor": "", "eof": True}))
        return FakeResp(200, json.dumps({"positions": {}}))

    def close(self) -> None:
        pass


class FakeOrderClient:
    """Answers submit_limit_order from a scripted list; records every payload."""

    def __init__(self, script):
        self.script = list(script)
        self.payloads: list[dict] = []

    def submit_limit_order(self, payload: dict) -> FakeResp:
        self.payloads.append(payload)
        answer = self.script.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def close(self) -> None:
        pass


def _watcher(activities, order_script=()) -> tuple[FillWatcher, FakeOrderClient]:
    oc = FakeOrderClient(order_script)
    w = FillWatcher(
        _Session, CREDS,
        read_client=FakeReadClient(activities),
        order_client=oc,
    )
    return w, oc


# --------------------------------------------------------------------------- #
# The amended invariant, at the database layer
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("mode", ["SHADOW", "AUTONOMOUS", "human_confirm"])
def test_pre_authorized_outside_human_confirm_is_unrepresentable(mode):
    """The amendment's own constraint: the flag cannot be inherited by any
    other mode, so it can never launder a machine-termed order."""
    with _Session() as s:
        s.add(_entry(key=f"pa-{mode}", accepted=False))
        s.commit()
    with _Session() as s:
        row = _entry(key=f"pa2-{mode}", accepted=False)
        row.mode = mode
        row.pre_authorized = True
        s.add(row)
        with pytest.raises(IntegrityError, match="ck_orders_pre_authorized"):
            s.commit()
        s.rollback()


def test_pre_authorized_human_confirm_accepted_is_allowed():
    with _Session() as s:
        row = _entry(key="pa-ok")
        row.pre_authorized = True
        s.add(row)
        s.commit()
        assert row.accepted and row.pre_authorized


def test_a_pre_authorized_exit_does_not_count_as_autonomous():
    """`orders_autonomous` keeps its meaning: terms no human specified. A
    pre-authorized exit's terms are all the human's, and it is HUMAN_CONFIRM,
    so the counter stays 0."""
    with _Session() as s:
        row = _entry(key="pa-counter")
        row.pre_authorized = True
        s.add(row)
        s.commit()
        counts = api_module._order_counts(s)
    assert counts["orders_autonomous"] == 0
    assert counts["orders_human"] >= 1


# --------------------------------------------------------------------------- #
# Activity parsing and reconciliation
# --------------------------------------------------------------------------- #


def test_the_real_trade_shape_yields_order_events():
    """Pinned against the observed schema, both execution sides."""
    a = trade_activity("v-1", state="ORDER_STATE_PARTIALLY_FILLED", cum=1,
                       side="passiveExecution")
    events, slug, ok = extract_order_events(a)
    assert ok and slug is None
    assert events == [OrderEvent("v-1", "ORDER_STATE_PARTIALLY_FILLED",
                                 Decimal("1"), "2026-08-07T02:05:51.436320896Z")]

    b = trade_activity("v-2", state="ORDER_STATE_FILLED", cum=2.47,
                       side="aggressorExecution")
    events, _, ok = extract_order_events(b)
    assert ok and events[0].cum_quantity == Decimal("2.47")


def test_resolution_and_transfer_activities():
    events, slug, ok = extract_order_events(resolution_activity("some-market"))
    assert ok and events == [] and slug == "some-market"
    # Benign non-trade types carry no order state and are not an error.
    events, slug, ok = extract_order_events({"type": "ACTIVITY_TYPE_TRANSFER"})
    assert ok and events == [] and slug is None


def test_unknown_shapes_are_refused_not_guessed():
    """A trade whose embedded order lacks id/state/cumQuantity is flagged,
    never guessed at — schema drift must be loud (the first parser guessed a
    flat shape and reconciled nothing for a day)."""
    bad = {"type": "ACTIVITY_TYPE_TRADE",
           "trade": {"passiveExecution": {"order": {"id": "v-1"}}}}   # no state
    _, _, ok = extract_order_events(bad)
    assert ok is False


def test_reconcile_takes_the_latest_execution_verbatim():
    """No summing, no comparison against our ordered quantity: the embedded
    order object carries the venue's own cumulative count and state. The venue
    rounds to 2dp (a 1.4645 order reports cum 1.46, state FILLED), so
    'filled >= ordered' would read PARTIAL forever — state is authoritative."""
    events = [
        OrderEvent("v", "ORDER_STATE_PARTIALLY_FILLED", Decimal("1"),
                   "2026-08-07T02:05:51.436320896Z"),
        OrderEvent("v", "ORDER_STATE_FILLED", Decimal("1.46"),
                   "2026-08-07T02:16:08.568502473Z"),
    ]
    assert reconcile_order(events) == (FILLED, Decimal("1.46"))
    assert reconcile_order(events[:1]) == (PARTIAL, Decimal("1"))
    assert reconcile_order([]) is None
    # If the venue ever reports a cancel state on an execution, it maps.
    assert reconcile_order([
        OrderEvent("v", "ORDER_STATE_CANCELED", Decimal("2"), "2026-08-07T03:00:00Z")
    ]) == (CANCELLED, Decimal("2"))


# --------------------------------------------------------------------------- #
# The watcher against the database — the spec's scenarios
# --------------------------------------------------------------------------- #


def test_a_settled_market_expires_an_open_order():
    """Zero-fill venue-side cancels emit NO activity (verified live — the gap
    is documented in the module and V19), but settlement does: an order still
    open on a resolved market can never fill and goes EXPIRED, which is what
    deletes its pending exit."""
    with _Session() as s:
        s.add(_entry(key="expire", venue_id="v-c1", slug=SLUG + "-settled"))
        s.commit()
    w, _ = _watcher([resolution_activity(SLUG + "-settled")])
    result = w.poll_once()
    assert result.updated == 1
    with _Session() as s:
        row = s.query(PlacedOrder).filter_by(idempotency_key="test-fw-expire").one()
        assert row.fill_status == EXPIRED
        assert row.fill_checked_at is not None


def test_venue_rounding_cannot_strand_a_fill():
    """THE bug the first live run hit, pinned exactly: order for 1.4645, venue
    reports cumQuantity 1.46 with state FILLED. Comparing filled >= ordered
    reads PARTIAL forever and the exit never fires. State wins; the exit
    sells the venue's 1.46 — never our 1.4645, which would oversell."""
    with _Session() as s:
        entry = _entry(key="round", venue_id="v-s1", qty="1.4645")
        s.add(entry)
        s.commit()
        _exit_for(s, entry, limit_price="0.31", typed_price="0.31")
    w, oc = _watcher(
        [
            trade_activity("v-s1", state="ORDER_STATE_FILLED", cum=1.46,
                           transact="2026-08-07T02:16:08.568502473Z"),
            trade_activity("v-s1", state="ORDER_STATE_PARTIALLY_FILLED", cum=1,
                           transact="2026-08-07T02:05:51.436320896Z"),
        ],
        order_script=[FakeResp(200, json.dumps({"orderId": "v-exit-r"}))],
    )
    result = w.poll_once()
    with _Session() as s:
        row = s.query(PlacedOrder).filter_by(idempotency_key="test-fw-round").one()
        assert row.fill_status == FILLED
        assert row.filled_quantity == Decimal("1.46")     # venue's number
    assert result.exits_submitted == 1
    assert oc.payloads[0]["quantity"] == "1.4600"          # venue count, not 1.4645


def test_a_hand_trade_in_the_same_market_is_never_attributed():
    """The account holds hand trades. An activity whose order id matches no
    row of ours is ignored, whatever market or price it carries — and it must
    not trigger an attached exit."""
    with _Session() as s:
        entry = _entry(key="hand", venue_id="v-ours", qty="2")
        s.add(entry)
        s.commit()
        _exit_for(s, entry)
    # A hand trade: same market, plausible size, DIFFERENT venue order id.
    w, oc = _watcher([
        trade_activity("v-theirs", state="ORDER_STATE_FILLED", cum=2,
                       side="aggressorExecution", market=SLUG),
    ])
    result = w.poll_once()
    with _Session() as s:
        row = s.query(PlacedOrder).filter_by(idempotency_key="test-fw-hand").one()
        assert row.fill_status == OPEN          # confirmed resting; not filled
        x = s.query(PendingExit).filter_by(entry_order_id=row.id).one()
        assert x.state == "PENDING"             # exit NOT triggered
    assert oc.payloads == []                    # nothing was submitted
    assert result.exits_submitted == 0


def test_partial_fill_exit_sells_the_filled_quantity_never_the_ordered():
    """Rule 3. Entry for 5, filled 2, then the market settles: the exit fires
    for exactly 2. Selling 5 would be selling contracts we do not hold.
    (Settlement stands in for any terminal state after a partial — a
    venue-reported cancel state would take the same path.)"""
    with _Session() as s:
        entry = _entry(key="partial", venue_id="v-p1", qty="5")
        s.add(entry)
        s.commit()
        _exit_for(s, entry, limit_price="0.30", typed_price="0.30")
    # First cycle: the partial fill lands. Second: the market resolves.
    w, oc = _watcher(
        [trade_activity("v-p1", state="ORDER_STATE_PARTIALLY_FILLED", cum=2)],
        order_script=[FakeResp(200, json.dumps({"orderId": "v-exit-1"}))],
    )
    w.poll_once()
    w._read_client = FakeReadClient([resolution_activity(SLUG)])
    result = w.poll_once()
    assert result.exits_submitted == 1
    payload = oc.payloads[0]
    assert payload["quantity"] == "2.0000"
    assert payload["price"]["value"] == "0.30"      # exactly as stored, rule 2
    assert payload["intent"] == "ORDER_INTENT_SELL_LONG"
    with _Session() as s:
        x = s.query(PendingExit).one_or_none()
        assert x.state == "SUBMITTED"
        exit_row = s.get(PlacedOrder, x.submitted_order_id)
        assert exit_row.pre_authorized is True
        assert exit_row.accepted is True
        assert exit_row.quantity == Decimal("2")
        assert exit_row.mode == "HUMAN_CONFIRM"


def test_no_side_exit_sends_the_stored_yes_frame_price_and_sell_short():
    """Rule 4, watcher side: the stored `limit_price` IS the YES-frame
    price.value (converted once, at click time); the watcher must not convert
    again, and a NO exit is ORDER_INTENT_SELL_SHORT."""
    with _Session() as s:
        entry = _entry(key="noexit", venue_id="v-n1", qty="1", outcome="no",
                       price="0.84")
        s.add(entry)
        s.commit()
        # Human typed "sell at 0.26" in the NO cost frame → stored as 0.74.
        _exit_for(s, entry, outcome="NO", limit_price="0.74", typed_price="0.26")
    w, oc = _watcher(
        [trade_activity("v-n1", state="ORDER_STATE_FILLED", cum=1)],
        order_script=[FakeResp(200, json.dumps({"orderId": "v-exit-2"}))],
    )
    w.poll_once()
    payload = oc.payloads[0]
    assert payload["price"]["value"] == "0.74"          # no second inversion
    assert payload["intent"] == "ORDER_INTENT_SELL_SHORT"
    assert payload["outcomeSide"] == "OUTCOME_SIDE_NO"
    assert payload["action"] == "ORDER_ACTION_SELL"


def test_entry_cancelled_unfilled_deletes_the_pending_exit():
    """Rule 5, with a log line. Nothing was bought, so there is nothing to
    sell, and a PENDING exit left behind would eventually fire against a
    position that does not exist."""
    with _Session() as s:
        entry = _entry(key="delexit", venue_id="v-d1", qty="3")
        s.add(entry)
        s.commit()
        _exit_for(s, entry)
    w, oc = _watcher([resolution_activity(SLUG)])
    result = w.poll_once()
    assert result.exits_deleted == 1
    assert oc.payloads == []
    with _Session() as s:
        assert s.query(PendingExit).one().state == "DELETED"


def test_exit_submit_retries_once_then_succeeds():
    """Rule 6, first half: one retry on failure. Safe because the idempotency
    key is identical across attempts."""
    with _Session() as s:
        entry = _entry(key="retry", venue_id="v-r1", qty="1")
        s.add(entry)
        s.commit()
        _exit_for(s, entry)
    w, oc = _watcher(
        [trade_activity("v-r1", state="ORDER_STATE_FILLED", cum=1)],
        order_script=[
            OrderSubmissionError("transport blip"),
            FakeResp(200, json.dumps({"orderId": "v-exit-3"})),
        ],
    )
    result = w.poll_once()
    assert result.exits_submitted == 1
    assert len(oc.payloads) == 2
    assert oc.payloads[0]["clientOrderId"] == oc.payloads[1]["clientOrderId"]


def test_venue_reject_surfaces_as_FAILED_loudly():
    """Rule 6, second half: a definitive venue rejection is not retried (the
    same order gets the same answer) and the exit lands FAILED — never
    silently dropped while the human believes it is protecting them."""
    with _Session() as s:
        entry = _entry(key="reject", venue_id="v-x1", qty="1")
        s.add(entry)
        s.commit()
        _exit_for(s, entry)
    w, oc = _watcher(
        [trade_activity("v-x1", state="ORDER_STATE_FILLED", cum=1)],
        order_script=[FakeResp(400, json.dumps({"error": "market closed"}))],
    )
    result = w.poll_once()
    assert result.exits_failed == 1
    assert len(oc.payloads) == 1               # definitive → no retry
    with _Session() as s:
        x = s.query(PendingExit).one()
        assert x.state == "FAILED"
        assert "market closed" in (x.error or "")
        # The FAILED state is on the dashboard payload too.
        exit_row = s.get(PlacedOrder, x.submitted_order_id)
        assert exit_row.accepted is False


def test_two_transport_failures_is_FAILED_not_a_third_attempt():
    with _Session() as s:
        entry = _entry(key="fail2", venue_id="v-f2", qty="1")
        s.add(entry)
        s.commit()
        _exit_for(s, entry)
    w, oc = _watcher(
        [trade_activity("v-f2", state="ORDER_STATE_FILLED", cum=1)],
        order_script=[
            OrderSubmissionError("down"),
            OrderSubmissionError("still down"),
        ],
    )
    result = w.poll_once()
    assert result.exits_failed == 1
    assert len(oc.payloads) == 2
    with _Session() as s:
        assert s.query(PendingExit).one().state == "FAILED"


def test_an_open_entry_leaves_the_exit_pending():
    """No fill, no action. PARTIAL-and-still-open also waits, on purpose —
    fills may still arrive, and per-slice exits would need amendment logic
    this system refuses to have."""
    with _Session() as s:
        entry = _entry(key="open", venue_id="v-o1", qty="2")
        s.add(entry)
        s.commit()
        _exit_for(s, entry)
    w, oc = _watcher([trade_activity("v-o1", state="ORDER_STATE_PARTIALLY_FILLED", cum=1)])
    w.poll_once()
    assert oc.payloads == []
    with _Session() as s:
        assert s.query(PendingExit).one().state == "PENDING"
        row = s.query(PlacedOrder).filter_by(idempotency_key="test-fw-open").one()
        assert row.fill_status == PARTIAL


# --------------------------------------------------------------------------- #
# The API stores the exit at click time, frame-converted once
# --------------------------------------------------------------------------- #


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("MERIDIAN_ORDER_TOKEN", "test-token")
    return TestClient(api_module.app)


def _seed_prediction(slug: str, *, bid: str, ask: str, model: str):
    from core.storage import Prediction

    with _Session() as s:
        latest = s.scalar(text("select max(predicted_at) from predictions"))
        s.add(Prediction(
            predicted_at=latest, market_slug=slug, model_version="t", strategy="t",
            sports_market_type="basketball_team_full_game_total",
            model_probability=Decimal(model),
            market_bid=Decimal(bid), market_ask=Decimal(ask),
            is_actionable=True,
        ))
        s.commit()


def _post(client, slug, **body):
    payload = {"market_slug": slug, "mode": "HUMAN_CONFIRM", "quantity": 1, **body}
    return client.post("/api/orders", json=payload,
                       headers={"X-Meridian-Order-Token": "test-token"})


def test_yes_exit_is_stored_verbatim_and_yes_frame_equals_typed(client):
    """Frame conversion, YES direction: cost frame == YES frame, no inversion.

    The venue call 503s in the test env (no credentials), which is a
    *definitive* never-sent — so the stored exit must land DELETED, proving
    both the storage-at-click-time and the delete-on-definitive-failure path.
    """
    slug = SLUG + "-apiyes"
    _seed_prediction(slug, bid="0.5200", ask="0.5500", model="0.6000")
    r = _post(client, slug, limit_price=0.52, exit_price=0.60)
    assert r.status_code == 503
    with _Session() as s:
        x = s.query(PendingExit).filter_by(market_slug=slug).one()
        assert x.outcome == "YES"
        assert x.typed_price == Decimal("0.60")
        assert x.limit_price == Decimal("0.60")     # YES: no inversion
        assert x.state == "DELETED"                  # entry was never sent
        entry = s.get(PlacedOrder, x.entry_order_id)
        assert entry.market_slug == slug             # rule 1: copied at click
        # Ticket-displayed price == orders.limit_price (same frame on YES).
        assert entry.limit_price == Decimal("0.52")


def test_no_exit_is_frame_converted_once_at_click_time(client):
    """Frame conversion, NO direction: typed 0.26 (NO cost) stores 0.74 as
    price.value — the V14 rule, applied exactly once, at click time."""
    slug = SLUG + "-apino"
    _seed_prediction(slug, bid="0.8100", ask="0.8400", model="0.7319")
    r = _post(client, slug, limit_price=0.16, exit_price=0.26)
    assert r.status_code == 503
    with _Session() as s:
        x = s.query(PendingExit).filter_by(market_slug=slug).one()
        assert x.outcome == "NO"
        assert x.typed_price == Decimal("0.26")
        assert x.limit_price == Decimal("0.74")     # 1 − 0.26, converted once
        entry = s.get(PlacedOrder, x.entry_order_id)
        # Ticket showed 0.16; the stored YES-frame price is 0.84.
        assert entry.limit_price == Decimal("0.84")
        assert Decimal("1") - entry.limit_price == Decimal("0.16")


def test_a_bad_exit_price_fails_the_whole_request(client):
    """An entry must not go to the venue carrying an exit that could not be
    stored — the human would be un-protected without knowing."""
    slug = SLUG + "-apibad"
    _seed_prediction(slug, bid="0.5200", ask="0.5500", model="0.6000")
    for bad in (0.005, 1.5, 0.515):
        r = _post(client, slug, limit_price=0.52, exit_price=bad)
        assert r.status_code == 422, bad
    with _Session() as s:
        assert s.query(PlacedOrder).filter_by(market_slug=slug).count() == 0
        assert s.query(PendingExit).filter_by(market_slug=slug).count() == 0


def test_an_order_without_an_exit_stores_no_pending_exit(client):
    slug = SLUG + "-apinone"
    _seed_prediction(slug, bid="0.5200", ask="0.5500", model="0.6000")
    r = _post(client, slug, limit_price=0.52)
    assert r.status_code == 503
    with _Session() as s:
        assert s.query(PendingExit).filter_by(market_slug=slug).count() == 0


def test_ticket_displayed_price_equals_stored_price_on_both_intents(client):
    """The spec's closing assertion: what the ticket displays IS what the
    orders table stores, frame-converted — on both intents."""
    yes_slug, no_slug = SLUG + "-tik-yes", SLUG + "-tik-no"
    _seed_prediction(yes_slug, bid="0.5200", ask="0.5500", model="0.6000")
    _seed_prediction(no_slug, bid="0.8100", ask="0.8400", model="0.7319")

    _post(client, yes_slug, limit_price=0.52)
    _post(client, no_slug, limit_price=0.16)
    with _Session() as s:
        yes_row = s.query(PlacedOrder).filter_by(market_slug=yes_slug).one()
        no_row = s.query(PlacedOrder).filter_by(market_slug=no_slug).one()
    assert yes_row.limit_price == Decimal("0.52")             # displayed == stored
    assert Decimal("1") - no_row.limit_price == Decimal("0.16")  # displayed == 1 − stored


# --------------------------------------------------------------------------- #
# Health coverage
# --------------------------------------------------------------------------- #


def test_status_judges_the_fill_watcher_only_where_ordering_is_enabled(monkeypatch):
    """With the token set, a missing fill_watcher beat is DEAD (the B11 shape:
    accepted orders quietly diverging from venue truth). Without it there is
    nothing to reconcile and no verdict at all."""
    monkeypatch.delenv("MERIDIAN_ORDER_TOKEN", raising=False)
    report = api_module._heartbeat_report({})
    assert hb.SERVICE_FILL_WATCHER not in report

    monkeypatch.setenv("MERIDIAN_ORDER_TOKEN", "x")
    report = api_module._heartbeat_report({})
    assert report[hb.SERVICE_FILL_WATCHER]["verdict"] == hb.DEAD

    report = api_module._heartbeat_report({
        hb.SERVICE_FILL_WATCHER: {
            "age_seconds": 10.0, "interval_seconds": 60.0, "rows_written": 1,
        }
    })
    assert report[hb.SERVICE_FILL_WATCHER]["verdict"] != hb.DEAD
