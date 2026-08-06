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
    normalize_activity,
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
# Fakes — injected clients; nothing in this file touches the network
# --------------------------------------------------------------------------- #


class FakeResp:
    def __init__(self, status_code: int, body: str, elapsed_ms: float = 5.0):
        self.status_code = status_code
        self.body_text = body
        self.elapsed_ms = elapsed_ms
        self.server_latency_ms = None


class FakeReadClient:
    """Serves a fixed activities list; positions is an empty 200."""

    def __init__(self, activities: list[dict]):
        self.activities = activities

    def get(self, path: str) -> FakeResp:
        if "activities" in path:
            return FakeResp(200, json.dumps({"activities": self.activities}))
        return FakeResp(200, json.dumps({"positions": []}))

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


def test_fill_cancel_and_expire_labels_are_recognised():
    base = {"orderId": "v-1", "quantity": "2"}
    assert normalize_activity({**base, "type": "FILL"}).kind == "fill"
    assert normalize_activity({**base, "type": "ACTIVITY_TYPE_TRADE"}).kind == "fill"
    assert normalize_activity({"orderId": "v-1", "type": "ORDER_CANCELLED"}).kind == "cancel"
    assert normalize_activity({"orderId": "v-1", "status": "EXPIRED"}).kind == "expire"


def test_unknown_shapes_are_refused_not_guessed():
    """Attribution needs a venue order id and a recognisable type. Anything
    less is ignored — never matched by market/price/size similarity."""
    assert normalize_activity({"type": "FILL", "quantity": "2"}) is None       # no id
    assert normalize_activity({"orderId": "v-1", "type": "SOMETHING_ELSE"}) is None
    assert normalize_activity({"orderId": "v-1", "type": "FILL"}) is None      # no qty
    assert normalize_activity({"id": "act-9", "type": "FILL", "quantity": 1}) is None


def test_reconcile_partial_then_full_then_cancel():
    from core.fill_watcher import Activity

    fills = [Activity("v", "fill", Decimal("2"))]
    assert reconcile_order(Decimal("5"), fills) == (PARTIAL, Decimal("2"))
    fills.append(Activity("v", "fill", Decimal("3")))
    assert reconcile_order(Decimal("5"), fills) == (FILLED, Decimal("5"))
    # Cancel after a partial keeps the fills: the position exists.
    acts = [Activity("v", "fill", Decimal("2")), Activity("v", "cancel")]
    assert reconcile_order(Decimal("5"), acts) == (CANCELLED, Decimal("2"))
    assert reconcile_order(Decimal("5"), [Activity("v", "expire")]) == (EXPIRED, Decimal("0"))
    assert reconcile_order(Decimal("5"), []) == (OPEN, Decimal("0"))


# --------------------------------------------------------------------------- #
# The watcher against the database — the spec's scenarios
# --------------------------------------------------------------------------- #


def test_venue_side_cancel_is_detected():
    """Orders #1–3: `accepted=True` while the human cancelled two in the app.
    The watcher is the only thing that can notice."""
    with _Session() as s:
        s.add(_entry(key="cancel", venue_id="v-c1"))
        s.commit()
    w, _ = _watcher([{"orderId": "v-c1", "type": "ORDER_CANCEL"}])
    result = w.poll_once()
    assert result.updated == 1
    with _Session() as s:
        row = s.query(PlacedOrder).filter_by(idempotency_key="test-fw-cancel").one()
        assert row.fill_status == CANCELLED
        assert row.fill_checked_at is not None


def test_counters_reconcile_against_activities():
    """filled_quantity is the sum of the venue's own fill activities for that
    order id — not a guess, and not a position delta."""
    with _Session() as s:
        s.add(_entry(key="sum", venue_id="v-s1", qty="5"))
        s.commit()
    w, _ = _watcher([
        {"orderId": "v-s1", "type": "FILL", "filledQuantity": "1.5"},
        {"orderId": "v-s1", "type": "FILL", "filledQuantity": "2"},
    ])
    w.poll_once()
    with _Session() as s:
        row = s.query(PlacedOrder).filter_by(idempotency_key="test-fw-sum").one()
        assert row.fill_status == PARTIAL
        assert row.filled_quantity == Decimal("3.5")


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
        {"orderId": "v-theirs", "type": "FILL", "quantity": "2",
         "marketSlug": SLUG, "price": "0.20"},
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
    """Rule 3. Entry for 5, filled 2, then cancelled: the exit must sell
    exactly 2. Selling 5 would be selling contracts we do not hold."""
    with _Session() as s:
        entry = _entry(key="partial", venue_id="v-p1", qty="5")
        s.add(entry)
        s.commit()
        _exit_for(s, entry, limit_price="0.30", typed_price="0.30")
    w, oc = _watcher(
        [
            {"orderId": "v-p1", "type": "FILL", "quantity": "2"},
            {"orderId": "v-p1", "type": "CANCEL"},
        ],
        order_script=[FakeResp(200, json.dumps({"orderId": "v-exit-1"}))],
    )
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
        [{"orderId": "v-n1", "type": "FILL", "quantity": "1"}],
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
    w, oc = _watcher([{"orderId": "v-d1", "type": "CANCELLED"}])
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
        [{"orderId": "v-r1", "type": "FILL", "quantity": "1"}],
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
        [{"orderId": "v-x1", "type": "FILL", "quantity": "1"}],
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
        [{"orderId": "v-f2", "type": "FILL", "quantity": "1"}],
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
    w, oc = _watcher([{"orderId": "v-o1", "type": "FILL", "quantity": "1"}])
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
