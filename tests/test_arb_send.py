"""The two-leg SEND and the UNWIND against the orders table, with a scripted venue.

NEEDS POSTGRES (the `orders` table): the idempotency rows are the defence
and the venue's synchronous answer lands on them, so nothing here can be
pinned without the rows. The gates that run before the first row are in
tests/test_arb_tab.py and need no database.

What is being defended, per the fill-test protocol and its 2026-09-18
amendment (docs/math/ladder-fill-test.md):

* both idempotency rows exist BEFORE leg 1 is sent, accepted=False, and a
  second send of the same ticket -- nudged price or not -- calls nothing;
* leg 1 goes first as an IOC synchronous limit at the ticket's price, and
  leg 2 goes only for the quantity leg 1 filled, or not at all;
* "leg 1 filled, leg 2 unfilled" is a first-class outcome in the reply and
  the record, never a success;
* the venue's reply is the row's record: id, state, filled, the average
  price in the YES frame, latency, the error body on a refusal;
* the attempts record the desk tallies is written for every answered send;
* the UNWIND sells what a leg bought, never more than the venue said filled,
  across clicks as well as within one, and an unanswered sell blocks the
  button rather than risk selling twice.

The venue shapes are the create-order doc's (read 2026-09-18), NOT yet seen
live: the first real synchronous reply is the finding this file waits on.
"""

from __future__ import annotations

import datetime as dt
import json
import time
from decimal import Decimal
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from core import api as api_module
from core.ladder import desk
from core.polymarket.client import OrderSubmissionError
from core.storage import PlacedOrder, get_engine, get_sessionmaker

UTC = dt.timezone.utc
#: A game no venue lists: the cleanup below is scoped to it, and a real slug
#: would collide with a peer's rows in the shared test database.
GAME = "cfb-tsta-tstb-2026-09-18"
PREFIX = "aec-" + GAME
SLUGS = [PREFIX, f"asc-{GAME}-pos-10pt5", f"asc-{GAME}-pos-7pt5", f"asc-{GAME}-neg-3pt5"]
INTENT = {"ts": "23:41:07", "game": GAME,
          "leg1": {"market_line": 10.5, "side": "BUY YES", "price": 0.41, "qty": 2},
          "leg2": {"market_line": 7.5, "side": "BUY NO", "price": 0.53, "qty": 2},
          "displayed_size": 966.0, "edge_c": 3.05, "cost_usd": 1.88, "meridian_placed": False}
TICKET_ID = f"{GAME}|23:41:07|10.5/7.5"
TOKEN = {"X-Meridian-Order-Token": "test-token"}
#: The cached ladder the unwind prices from: 10.5 bids 0.40, 7.5 asks 0.49.
RUNGS = {3.5: (0.30, 0.32, 100.0, 50.0), 7.5: (0.47, 0.49, 966.0, 40.0),
         10.5: (0.40, 0.41, 20.0, 966.0), 13.5: (0.60, 0.62, 10.0, 10.0)}

FILLED, PARTIAL, CANCELED = "ORDER_STATE_FILLED", "ORDER_STATE_PARTIALLY_FILLED", "ORDER_STATE_CANCELED"

_Session = get_sessionmaker(get_engine())


@pytest.fixture(autouse=True)
def clean():
    """Scoped to this file's own game (the B6 lesson)."""
    yield
    with _Session() as s:
        s.execute(text("delete from orders where market_slug like :m"), {"m": f"%{GAME}%"})
        s.commit()


@pytest.fixture
def reads(tmp_path, monkeypatch):
    monkeypatch.setenv("MERIDIAN_READS_DIR", str(tmp_path))
    (tmp_path / f"ladder_intents_{PREFIX}.jsonl").write_text(json.dumps(INTENT) + "\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("MERIDIAN_ORDER_TOKEN", "test-token")
    return TestClient(api_module.app)


@pytest.fixture
def desk_ready(monkeypatch):
    """The recorder's slug listing, the bankroll and the sampler stubbed; the
    ladder cache holds one snapshot so the unwind has a touch to price from."""
    import core.bankroll as bk

    monkeypatch.setattr(api_module, "slugs_for", lambda game, engine=None: list(SLUGS))

    def _unavailable(*_a, **_k):
        raise bk.BankrollUnavailable("stubbed")
    monkeypatch.setattr(bk, "current", _unavailable)
    monkeypatch.setattr(api_module, "_arb_ensure_sampler", lambda: None)
    snap = api_module._arb_ladder_snapshot(GAME, RUNGS, {}, 1.0, time.time())
    monkeypatch.setitem(api_module._ARB_LADDER, "cache", {PREFIX: snap})
    monkeypatch.setitem(api_module._ARB_LADDER, "watch", {})


# --------------------------------------------------------------------------- #
# The scripted venue
# --------------------------------------------------------------------------- #


class FakeResp:
    def __init__(self, status_code, body, elapsed_ms=87.5, server_latency_ms=12.0):
        self.status_code = status_code
        self.body_text = body
        self.elapsed_ms = elapsed_ms
        self.server_latency_ms = server_latency_ms


class FakeOrderClient:
    """Answers submit_limit_order from a scripted list; records every payload.
    An Exception in the script is raised in place of an answer."""

    SCRIPT: ClassVar[list] = []
    PAYLOADS: ClassVar[list[dict]] = []

    def __init__(self, creds, **kw):
        self.creds = creds

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def submit_limit_order(self, payload: dict) -> FakeResp:
        FakeOrderClient.PAYLOADS.append(payload)
        assert FakeOrderClient.SCRIPT, "the venue was called more times than the script allows"
        answer = FakeOrderClient.SCRIPT.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def _sync(order_id, state, cum, avg=None) -> str:
    """One create-order reply per the doc: `executions[]` with the embedded
    order carrying `state` and `cumQuantity`, and the execution's `avgPx`."""
    ex = {"id": f"E-{order_id}", "order": {"id": order_id, "marketSlug": "x", "state": state,
                                          "cumQuantity": cum, "leavesQuantity": 0}}
    if avg is not None:
        ex["avgPx"] = {"value": str(avg)}
    return json.dumps({"orderId": order_id, "executions": [ex]})


def _venue(monkeypatch, *script):
    FakeOrderClient.SCRIPT = list(script)
    FakeOrderClient.PAYLOADS = []
    monkeypatch.setattr(api_module, "PolymarketOrderClient", FakeOrderClient)
    monkeypatch.setattr(
        api_module.USCredentials, "from_env",
        staticmethod(lambda env=None: api_module.USCredentials("k", "s")),
    )


def _body(**over) -> dict:
    legs = [{"market_slug": SLUGS[1], "side": "BUY YES", "cost_price": "0.41", "quantity": "2"},
            {"market_slug": SLUGS[2], "side": "BUY NO", "cost_price": "0.53", "quantity": "2"}]
    body = {"ticket_id": TICKET_ID, "mode": "HUMAN_CONFIRM", "legs": legs, "acknowledge": True}
    body.update(over)
    return body


def _rows(note_suffix="") -> dict[int, PlacedOrder]:
    """{leg n: row} for this ticket's buy rows (or its unwind rows)."""
    with _Session() as s:
        out = {}
        for n in (1, 2):
            out[n] = s.scalars(select(PlacedOrder).where(
                PlacedOrder.notes == f"arb ticket {TICKET_ID} leg {n}{note_suffix}"
            ).order_by(PlacedOrder.submitted_at.desc())).first()
            if out[n] is not None:
                s.expunge(out[n])
        return out


def _records(reads) -> list[dict]:
    return desk.read_jsonl(str(reads / desk.ATTEMPTS_FILE))


# --------------------------------------------------------------------------- #
# SEND
# --------------------------------------------------------------------------- #


def test_full_fill_sends_both_legs_and_the_reply_is_the_rows_record(client, reads, desk_ready, monkeypatch):
    _venue(monkeypatch, FakeResp(200, _sync("v-1", FILLED, 2, avg="0.41")),
           FakeResp(201, _sync("v-2", FILLED, 2, avg="0.47")))
    r = client.post("/api/arb/send", json=_body(), headers=TOKEN)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["outcome"] == "both legs filled" and body["ticket_id"] == TICKET_ID
    l1, l2 = body["legs"]
    assert (l1["sent"], l1["accepted"], l1["venue_order_id"], l1["state"]) == (True, True, "v-1", FILLED)
    assert l1["filled_quantity"] == 2.0 and l1["avg_cost_price"] == 0.41 and l1["http_status"] == 200
    assert l1["latency_ms"] == 87.5 and l1["venue_latency_ms"] == 12.0 and l1["error"] is None
    assert l2["filled_quantity"] == 2.0 and l2["avg_cost_price"] == pytest.approx(0.53), \
        "a NO leg's average is reported in the COST frame: 1 - the venue's YES avgPx"
    assert body["pair"]["cost_usd_filled"] == pytest.approx(1.88)
    assert body["pair"]["guaranteed_usd"] == pytest.approx(0.12) and body["pair"]["paired_quantity"] == 2.0
    assert set(body) >= {"orders_human", "orders_autonomous", "orders_rejected"}

    # The two payloads: IOC, not post-only, synchronous, YES-frame prices.
    p1, p2 = FakeOrderClient.PAYLOADS
    for p in (p1, p2):
        assert p["tif"] == "TIME_IN_FORCE_IMMEDIATE_OR_CANCEL"
        assert p["participateDontInitiate"] is False and p["synchronousExecution"] is True
        assert p["type"] == "ORDER_TYPE_LIMIT" and p["action"] == "ORDER_ACTION_BUY"
    assert p1["marketSlug"] == SLUGS[1] and p1["price"]["value"] == "0.41" and p1["quantity"] == "2"
    assert p1["intent"] == "ORDER_INTENT_BUY_LONG" and p1["outcomeSide"] == "OUTCOME_SIDE_YES"
    assert p2["marketSlug"] == SLUGS[2] and p2["price"]["value"] == "0.47" and p2["quantity"] == "2"
    assert p2["intent"] == "ORDER_INTENT_BUY_SHORT" and p2["outcomeSide"] == "OUTCOME_SIDE_NO"

    rows = _rows()
    for n, venue_id, yes_px, side in ((1, "v-1", "0.41", "buy_yes"), (2, "v-2", "0.47", "buy_no")):
        row = rows[n]
        assert row.mode == "HUMAN_CONFIRM" and row.side == side and row.accepted is True
        assert row.venue_order_id == venue_id and row.venue_status == FILLED
        assert row.fill_status == "FILLED" and row.filled_quantity == Decimal("2")
        assert row.avg_fill_price == Decimal(yes_px), "stored in the YES frame like limit_price"
        assert row.limit_price == Decimal(yes_px) and row.quantity == Decimal("2")
        assert row.http_status in (200, 201) and row.submit_latency_ms == Decimal("87.50")
        assert row.venue_latency_ms == Decimal("12.00") and row.would_rest is False
        assert row.fill_checked_at is not None and row.error is None
    assert rows[1].market_bid == Decimal("0.40") and rows[1].market_ask == Decimal("0.41"), \
        "the cached touch at submission, as the human-confirm rows carry"

    # The desk's record: the attempt the tally counts, marked as sent from here.
    rec = _records(reads)[-1]
    assert rec["id"] == TICKET_ID and rec["status"] == "recorded" and rec["via"] == "send"
    assert rec["l1q"] == 2.0 and rec["l2q"] == 2.0 and rec["l1p"] == 0.41
    assert rec["venue_order_ids"] == ["v-1", "v-2"] and rec["outcome"] == "both legs filled"
    assert rec["order_ids"] == [rows[1].id, rows[2].id]
    assert desk.load_tickets(str(reads))[0]["status"] == "recorded"
    # Seconds-to-fill is recorded to the MILLISECOND (core/api.py rounds
    # latency_ms/1000 to 3dp): 87.5 ms lands on 0.087 s, and sub-millisecond
    # precision on a network round trip would be noise in the register.
    assert body["record"]["l1s"] == pytest.approx(0.0875, abs=1e-3)


def test_partial_leg1_sizes_leg2_to_the_fill(client, reads, desk_ready, monkeypatch):
    """An IOC that takes 1 of 2 ends CANCELED with cumQuantity 1; leg 2 is
    sent for 1, and its row's quantity says 1, not the 2 the ticket asked."""
    _venue(monkeypatch, FakeResp(200, _sync("v-3", CANCELED, 1, avg="0.41")),
           FakeResp(200, _sync("v-4", FILLED, 1, avg="0.47")))
    body = client.post("/api/arb/send", json=_body(), headers=TOKEN).json()
    assert body["outcome"] == "both legs filled" and body["pair"]["paired_quantity"] == 1.0
    assert body["legs"][0]["fill_status"] == "CANCELLED" and body["legs"][0]["filled_quantity"] == 1.0
    assert body["legs"][1]["quantity_sent"] == 1.0
    assert FakeOrderClient.PAYLOADS[1]["quantity"] == "1"
    rows = _rows()
    assert rows[1].quantity == Decimal("2") and rows[1].filled_quantity == Decimal("1")
    assert rows[2].quantity == Decimal("1") and rows[2].filled_quantity == Decimal("1")


def test_zero_fill_on_leg1_sends_nothing_more(client, reads, desk_ready, monkeypatch):
    _venue(monkeypatch, FakeResp(200, _sync("v-5", CANCELED, 0)))
    body = client.post("/api/arb/send", json=_body(), headers=TOKEN).json()
    assert body["outcome"] == "leg 1 unfilled"
    assert len(FakeOrderClient.PAYLOADS) == 1, "leg 2 must not be sent"
    l2 = body["legs"][1]
    assert l2["sent"] is False and l2["error"] == "leg 1 unfilled; leg 2 not sent"
    assert body["pair"]["cost_usd_filled"] == 0.0 and body["pair"]["guaranteed_usd"] == 0.0
    rows = _rows()
    assert rows[1].accepted is True and rows[1].filled_quantity == Decimal("0")
    assert rows[1].fill_status == "CANCELLED" and rows[1].avg_fill_price is None
    assert rows[2].accepted is False and rows[2].http_status is None
    assert rows[2].error == "leg 1 unfilled; leg 2 not sent"
    rec = _records(reads)[-1]
    # A terminal zero IS the observation: recorded, and the tally's one
    # "leg 1 filled nothing" count. The record says how much was sent.
    assert body["legs"][0]["observed"] is True and body["pair"]["settled"] is True
    assert rec["status"] == "recorded" and rec["l1q"] == 0.0 and rec["l2q"] == 0.0
    assert rec["venue_order_ids"] == ["v-5", None]
    assert rec["l1_sent"] == 2.0 and rec["l2_sent"] is None and rec["via"] == api_module._ARB_VIA_SEND
    assert desk.tally(desk.load_tickets(str(reads)))["none"] == 1


def test_leg1_filled_leg2_unfilled_is_a_first_class_outcome(client, reads, desk_ready, monkeypatch):
    """The one way the protocol says money is lost. It must be named, never
    read as success, and the record must show the unpaired contracts."""
    _venue(monkeypatch, FakeResp(200, _sync("v-6", FILLED, 2, avg="0.41")),
           FakeResp(200, _sync("v-7", CANCELED, 0)))
    body = client.post("/api/arb/send", json=_body(), headers=TOKEN).json()
    assert body["outcome"] == "leg 1 filled, leg 2 unfilled"
    assert "UNWIND" in body["pair"]["note"] and "+10.5" in body["pair"]["note"]
    assert body["pair"]["guaranteed_usd"] == 0.0 and body["pair"]["cost_usd_filled"] == pytest.approx(0.82)
    assert body["legs"][1]["sent"] is True and body["legs"][1]["filled_quantity"] == 0.0
    rows = _rows()
    assert rows[1].filled_quantity == Decimal("2") and rows[2].filled_quantity == Decimal("0")
    assert rows[2].accepted is True and rows[2].fill_status == "CANCELLED"
    rec = _records(reads)[-1]
    assert rec["outcome"] == "leg 1 filled, leg 2 unfilled" and rec["l1q"] == 2.0 and rec["l2q"] == 0.0


def test_leg1_transport_error_is_502_and_marks_the_ticket_placed(client, reads, desk_ready, monkeypatch):
    """No answer from the venue is ambiguous: leg 1 may exist. Leg 2 is not
    sent into that, both rows say why, and the ticket leaves "open" so a
    second click cannot send the pair again without the operator looking."""
    _venue(monkeypatch, OrderSubmissionError("connection reset"))
    r = client.post("/api/arb/send", json=_body(), headers=TOKEN)
    assert r.status_code == 502 and "leg 2 was not sent" in r.json()["detail"]
    assert len(FakeOrderClient.PAYLOADS) == 1
    rows = _rows()
    assert rows[1].accepted is False and "connection reset" in rows[1].error
    assert rows[2].accepted is False and "transport error" in rows[2].error
    rec = _records(reads)[-1]
    assert rec["status"] == "placed" and rec["via"] == api_module._ARB_VIA_SEND
    assert "connection reset" in rec["error"] and rec["l1_sent"] == 2.0
    assert "l1q" not in rec, "no answer is not a fill observation; the tally must not read a zero"
    assert desk.load_tickets(str(reads))[0]["status"] == "placed"
    # and the second click is refused before the database is touched
    _venue(monkeypatch, FakeResp(200, _sync("v-x", FILLED, 2)))
    r = client.post("/api/arb/send", json=_body(), headers=TOKEN)
    assert r.status_code == 409 and "not open" in r.json()["detail"]
    assert FakeOrderClient.PAYLOADS == []


def test_leg2_transport_error_leaves_leg1_held_and_says_so(client, reads, desk_ready, monkeypatch):
    _venue(monkeypatch, FakeResp(200, _sync("v-8", FILLED, 2, avg="0.41")),
           OrderSubmissionError("timeout"))
    body = client.post("/api/arb/send", json=_body(), headers=TOKEN).json()
    # No answer is not "not sent": leg 2 may exist at the venue, so the
    # outcome says unknown, the note says reconcile before unwinding, and
    # the record is `placed` with no l2q rather than a zero the tally reads.
    assert body["outcome"] == "leg 1 filled, leg 2 unknown" and body["pair"]["pending"] is True
    assert body["legs"][1]["sent"] is False and body["legs"][1]["transport_error"] is True
    assert "timeout" in body["legs"][1]["error"]
    assert "UNWIND" in body["pair"]["note"] and "Reconcile leg 2" in body["pair"]["note"]
    rows = _rows()
    assert rows[1].filled_quantity == Decimal("2") and rows[2].accepted is False
    assert "timeout" in rows[2].error
    rec = _records(reads)[-1]
    assert rec["status"] == "placed" and rec["outcome"] == "leg 1 filled, leg 2 unknown"
    assert "l2q" not in rec and rec["l1_sent"] == 2.0 and rec["l2_sent"] == 2.0


def test_a_rejected_leg1_records_the_refusal_and_stops(client, reads, desk_ready, monkeypatch):
    """A 400 is the venue refusing to take the order, not the order filling
    nothing: the outcome names the refusal, the record is `placed` with the
    error and no fills, and the tally's "leg 1 filled nothing" stays at 0."""
    _venue(monkeypatch, FakeResp(400, '{"code":3,"message":"price out of range"}'))
    body = client.post("/api/arb/send", json=_body(), headers=TOKEN).json()
    assert body["outcome"] == "leg 1 rejected" and body["pair"]["settled"] is False
    l1 = body["legs"][0]
    assert l1["sent"] is True and l1["accepted"] is False and l1["http_status"] == 400
    assert l1["observed"] is False
    assert "price out of range" in l1["error"] and l1["filled_quantity"] == 0.0
    assert len(FakeOrderClient.PAYLOADS) == 1
    rows = _rows()
    assert rows[1].accepted is False and rows[1].http_status == 400
    assert "price out of range" in rows[1].error and rows[1].fill_status is None
    assert rows[2].accepted is False and rows[2].error == "leg 1 rejected; leg 2 not sent"
    assert body["orders_rejected"] >= 1
    rec = _records(reads)[-1]
    assert rec["status"] == "placed" and rec["outcome"] == "leg 1 rejected" and "l1q" not in rec
    assert "price out of range" in rec["error"]
    assert desk.tally(desk.load_tickets(str(reads)))["none"] == 0, "a refusal is not a zero fill"


def test_a_second_send_of_the_same_ticket_calls_nothing(client, reads, desk_ready, monkeypatch):
    """Twice: once on the desk's record (recorded), and -- with that record
    removed -- once on the leg-1 row, which a one-tick nudge cannot dodge the
    way it dodges the idempotency key."""
    _venue(monkeypatch, FakeResp(200, _sync("v-9", FILLED, 2)), FakeResp(200, _sync("v-10", FILLED, 2)))
    assert client.post("/api/arb/send", json=_body(), headers=TOKEN).status_code == 200
    _venue(monkeypatch, FakeResp(200, _sync("v-11", FILLED, 2)))
    r = client.post("/api/arb/send", json=_body(), headers=TOKEN)
    assert r.status_code == 409 and "not open" in r.json()["detail"]
    (reads / desk.ATTEMPTS_FILE).unlink()                       # the record gone; the rows remain
    nudged = _body()
    nudged["legs"][0]["cost_price"] = "0.42"
    r = client.post("/api/arb/send", json=nudged, headers=TOKEN)
    assert r.status_code == 409 and "already sent" in r.json()["detail"]
    assert FakeOrderClient.PAYLOADS == []
    with _Session() as s:
        n = s.scalars(select(PlacedOrder).where(PlacedOrder.market_slug.like(f"%{GAME}%"))).all()
    assert len(n) == 2, "no third row"


def test_missing_credentials_are_503_with_both_rows_marked(client, reads, desk_ready, monkeypatch):
    """The environment blanks the credentials; the rows must still exist
    (written before the venue) and carry the reason."""
    monkeypatch.setattr(api_module, "PolymarketOrderClient", FakeOrderClient)
    FakeOrderClient.SCRIPT, FakeOrderClient.PAYLOADS = [], []
    r = client.post("/api/arb/send", json=_body(), headers=TOKEN)
    assert r.status_code == 503
    rows = _rows(" unsent")
    assert rows[1] is not None and rows[2] is not None
    assert rows[1].accepted is False and "POLYMARKET" in rows[1].error
    assert rows[2].error.startswith("leg 1 not sent")
    assert FakeOrderClient.PAYLOADS == []
    assert _rows()[1] is None, "the unsent rows leave the 'already sent' gate's match"
    assert rows[1].idempotency_key.endswith(f"-unsent-{rows[1].id}"), (
        "the key is released as well as the note: leaving it made the row's own "
        "UNIQUE constraint refuse the retry below, which the notes gate cannot see")
    # Nothing reached the venue, so the ticket is still open and still
    # sendable: with credentials the same click goes through, not 409.
    assert _records(reads) == [] and desk.load_tickets(str(reads))[0]["status"] == "open"
    _venue(monkeypatch, FakeResp(200, _sync("v-c1", FILLED, 2)), FakeResp(200, _sync("v-c2", FILLED, 2)))
    r = client.post("/api/arb/send", json=_body(), headers=TOKEN)
    assert r.status_code == 200, r.text
    assert len(FakeOrderClient.PAYLOADS) == 2


def test_a_pending_zero_fill_on_leg1_is_not_an_observation(client, reads, desk_ready, monkeypatch):
    """A 200 with cumQuantity 0 in PENDING_NEW: no maxBlockTime is sent, so
    whether the venue blocked until the IOC was terminal is unobserved. Leg
    2 is not sent, the row stays OPEN for the fill watcher, the outcome says
    pending, and the record is `placed` with no fills: the tally must not
    count it as "leg 1 filled nothing"."""
    _venue(monkeypatch, FakeResp(200, _sync("v-p1", "ORDER_STATE_PENDING_NEW", 0)))
    body = client.post("/api/arb/send", json=_body(), headers=TOKEN).json()
    assert body["outcome"] == "leg 1 pending at the venue" and body["pair"]["pending"] is True
    assert body["pair"]["settled"] is False and "check it before UNWIND" in body["pair"]["note"]
    assert len(FakeOrderClient.PAYLOADS) == 1, "leg 2 must not be sent"
    l1, l2 = body["legs"]
    assert l1["accepted"] is True and l1["observed"] is False and l1["fill_status"] == "OPEN"
    assert l2["sent"] is False and l2["error"] == "leg 1 pending at the venue; leg 2 not sent"
    rows = _rows()
    assert rows[1].accepted is True and rows[1].fill_status == "OPEN" and rows[1].venue_order_id == "v-p1"
    assert rows[1].filled_quantity == Decimal("0")
    rec = _records(reads)[-1]
    assert rec["status"] == "placed" and rec["outcome"] == "leg 1 pending at the venue"
    assert "l1q" not in rec and rec["venue_order_ids"] == ["v-p1", None]
    assert desk.tally(desk.load_tickets(str(reads)))["none"] == 0
    assert desk.load_tickets(str(reads))[0]["status"] == "placed"


def test_unwind_is_exempt_from_the_lock(client, reads, desk_ready, monkeypatch):
    """The lock refuses a SEND; it must not lock the operator into a
    half-filled pair. UNWIND on a LOCKED desk still sells, with the token,
    the literal and the acknowledge flag as its gates."""
    _held(client, monkeypatch, l1=2, l2=0)
    desk.lock(str(reads), "the test")
    assert desk.armed(str(reads)) is False
    _venue(monkeypatch, FakeResp(200, _sync("v-s11", FILLED, 2)))
    r = client.post("/api/arb/send", json=_body(ticket_id=TICKET_ID), headers=TOKEN)
    assert r.status_code == 409, "a locked desk refuses the send (here: the ticket is not open)"
    leg = _unwind(client, leg=1).json()["legs"][0]
    assert leg["sent"] and leg["accepted"] and leg["filled_quantity"] == 2.0
    assert FakeOrderClient.PAYLOADS[-1]["quantity"] == "2"


# --------------------------------------------------------------------------- #
# UNWIND
# --------------------------------------------------------------------------- #


def _held(client, monkeypatch, l1=2, l2=0):
    """A sent ticket with leg 1 filled `l1` and leg 2 filled `l2`."""
    _venue(monkeypatch, FakeResp(200, _sync("v-b1", FILLED if l1 == 2 else CANCELED, l1, avg="0.41")),
           FakeResp(200, _sync("v-b2", FILLED if l2 == 2 else CANCELED, l2, avg="0.47")))
    body = client.post("/api/arb/send", json=_body(), headers=TOKEN).json()
    assert body["legs"][0]["filled_quantity"] == float(l1)
    return body


def _unwind(client, **over):
    body = {"ticket_id": TICKET_ID, "mode": "HUMAN_CONFIRM", "leg": 1, "acknowledge": True}
    body.update(over)
    return client.post("/api/arb/unwind", json=body, headers=TOKEN)


def test_unwind_sells_what_leg1_filled_at_the_cached_bid(client, reads, desk_ready, monkeypatch):
    _held(client, monkeypatch, l1=2, l2=0)
    _venue(monkeypatch, FakeResp(200, _sync("v-s1", FILLED, 2, avg="0.40")))
    r = _unwind(client, leg=1)
    assert r.status_code == 200, r.text
    leg = r.json()["legs"][0]
    assert leg["sent"] and leg["accepted"] and leg["filled_quantity"] == 2.0
    assert leg["side"] == "SELL YES" and leg["avg_cost_price"] == 0.40
    assert leg["unwind_of"] == _rows()[1].id
    p = FakeOrderClient.PAYLOADS[-1]
    assert p["action"] == "ORDER_ACTION_SELL" and p["intent"] == "ORDER_INTENT_SELL_LONG"
    assert p["price"]["value"] == "0.40" and p["quantity"] == "2", "the cached 10.5 bid, the filled size"
    assert p["tif"] == "TIME_IN_FORCE_IMMEDIATE_OR_CANCEL" and p["synchronousExecution"] is True
    sell = _rows(" unwind")[1]
    assert sell.side == "sell_yes" and sell.accepted and sell.filled_quantity == Decimal("2")
    assert sell.quantity == Decimal("2") and sell.limit_price == Decimal("0.40")
    assert sell.avg_fill_price == Decimal("0.40") and sell.fill_status == "FILLED"
    # a second click on the unwound leg is refused, and calls nothing
    _venue(monkeypatch, FakeResp(200, _sync("v-s2", FILLED, 2)))
    leg = _unwind(client, leg=1).json()["legs"][0]
    assert leg["sent"] is False and "already unwound" in leg["error"]
    assert FakeOrderClient.PAYLOADS == []


def test_unwind_of_a_no_leg_prices_from_the_yes_ask(client, reads, desk_ready, monkeypatch):
    """Selling NO hits the NO bid = 1 - the YES ask (0.49 on 7.5): cost 0.51,
    sent as price.value 0.49 with SELL_SHORT."""
    _held(client, monkeypatch, l1=2, l2=2)
    _venue(monkeypatch, FakeResp(200, _sync("v-s3", FILLED, 2, avg="0.49")))
    leg = _unwind(client, leg=2).json()["legs"][0]
    assert leg["leg"] == 2 and leg["side"] == "SELL NO" and leg["filled_quantity"] == 2.0
    assert leg["limit_cost_price"] == 0.51 and leg["avg_cost_price"] == pytest.approx(0.51)
    p = FakeOrderClient.PAYLOADS[-1]
    assert p["intent"] == "ORDER_INTENT_SELL_SHORT" and p["outcomeSide"] == "OUTCOME_SIDE_NO"
    assert p["price"]["value"] == "0.49" and p["quantity"] == "2"
    assert _rows(" unwind")[2].side == "sell_no"


def test_unwind_with_a_typed_price_and_both_legs(client, reads, desk_ready, monkeypatch):
    _held(client, monkeypatch, l1=2, l2=2)
    _venue(monkeypatch, FakeResp(200, _sync("v-s4", FILLED, 2)), FakeResp(200, _sync("v-s5", FILLED, 2)))
    body = _unwind(client, leg="both", limit_cost_price="0.35").json()
    assert [x["leg"] for x in body["legs"]] == [1, 2]
    p1, p2 = FakeOrderClient.PAYLOADS[-2:]
    assert p1["price"]["value"] == "0.35", "a typed YES cost is the YES price"
    assert p2["price"]["value"] == "0.65", "a typed NO cost 0.35 is sent as YES price 0.65"


def test_unwind_never_sells_more_than_filled_across_clicks(client, reads, desk_ready, monkeypatch):
    """Sell 2, fill 1 (IOC ends CANCELED with cumQuantity 1); the next click
    sells the remaining 1 and no more; the click after that sells nothing."""
    _held(client, monkeypatch, l1=2, l2=0)
    _venue(monkeypatch, FakeResp(200, _sync("v-s6", CANCELED, 1)))
    leg = _unwind(client, leg=1).json()["legs"][0]
    assert leg["filled_quantity"] == 1.0 and leg["fill_status"] == "CANCELLED"
    _venue(monkeypatch, FakeResp(200, _sync("v-s7", FILLED, 1)))
    leg = _unwind(client, leg=1).json()["legs"][0]
    assert leg["sent"] and leg["quantity_sent"] == 1.0 and FakeOrderClient.PAYLOADS[-1]["quantity"] == "1"
    _venue(monkeypatch, FakeResp(200, _sync("v-s8", FILLED, 1)))
    leg = _unwind(client, leg=1).json()["legs"][0]
    assert leg["sent"] is False and "already unwound" in leg["error"] and FakeOrderClient.PAYLOADS == []
    with _Session() as s:
        sells = s.scalars(select(PlacedOrder).where(
            PlacedOrder.notes == f"arb ticket {TICKET_ID} leg 1 unwind")).all()
        assert sum(x.filled_quantity for x in sells) == Decimal("2")


def test_an_unanswered_unwind_blocks_the_button(client, reads, desk_ready, monkeypatch):
    """A sell that got no answer may have filled; until someone looks, the
    whole quantity counts as sold, so the button cannot sell it twice."""
    _held(client, monkeypatch, l1=2, l2=0)
    _venue(monkeypatch, OrderSubmissionError("no answer"))
    leg = _unwind(client, leg=1).json()["legs"][0]
    assert leg["sent"] is False and "no answer" in leg["error"]
    assert _rows(" unwind")[1].accepted is False and "no answer" in _rows(" unwind")[1].error
    _venue(monkeypatch, FakeResp(200, _sync("v-s9", FILLED, 2)))
    leg = _unwind(client, leg=1).json()["legs"][0]
    assert leg["sent"] is False and "sold or pending" in leg["error"]
    assert FakeOrderClient.PAYLOADS == []


def test_a_refused_unwind_sold_nothing_and_the_button_stays(client, reads, desk_ready, monkeypatch):
    _held(client, monkeypatch, l1=2, l2=0)
    _venue(monkeypatch, FakeResp(400, '{"message":"rejected"}'))
    leg = _unwind(client, leg=1).json()["legs"][0]
    assert leg["sent"] and leg["accepted"] is False and leg["filled_quantity"] == 0.0
    _venue(monkeypatch, FakeResp(200, _sync("v-s10", FILLED, 2)))
    leg = _unwind(client, leg=1).json()["legs"][0]
    assert leg["sent"] and leg["filled_quantity"] == 2.0, "the venue refused the first; nothing was sold"


def test_unwind_of_an_unfilled_leg_sends_nothing(client, reads, desk_ready, monkeypatch):
    _held(client, monkeypatch, l1=2, l2=0)
    _venue(monkeypatch)
    body = _unwind(client, leg=2).json()
    assert body["legs"][0]["sent"] is False and "nothing filled" in body["legs"][0]["error"]
    assert FakeOrderClient.PAYLOADS == []
    assert _unwind(client, leg=1, mode="SHADOW").status_code == 403


def test_unwind_without_a_cached_touch_needs_a_typed_price(client, reads, desk_ready, monkeypatch):
    _held(client, monkeypatch, l1=2, l2=0)
    monkeypatch.setitem(api_module._ARB_LADDER, "cache", {})
    _venue(monkeypatch)
    r = _unwind(client, leg=1)
    assert r.status_code == 409 and "no cached ladder touch" in r.json()["detail"]
    assert FakeOrderClient.PAYLOADS == []
