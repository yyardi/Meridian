"""The human cancel path: same invariants as SEND, plus the V21 evidence trail.

What is being defended:

* Only a human can initiate a cancel — the endpoint is token-gated and no
  machine path (the fill watcher above all) references `cancel_order`.
* Only a resting HUMAN_CONFIRM order of ours can be cancelled; terminal and
  never-accepted rows are refused with the reason.
* The venue's answer is recorded verbatim on the row (`cancel_response`), with
  the round-trip latency — the last unmeasured number in write-latency.md —
  because the endpoint shape itself is UNVERIFIED until the first live cancel
  (V21), and that first response IS the finding.
* A 2xx ack marks the row CANCELLED with fills preserved; anything else
  leaves fill state untouched (an unacknowledged cancel proves nothing).
"""

from __future__ import annotations

import datetime as dt
import inspect
from decimal import Decimal

import pytest
from sqlalchemy import text

from core import api as api_module
from core.polymarket import client as pm_client
from core.storage import PlacedOrder, get_engine, get_sessionmaker

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 8, 7, 18, 0, tzinfo=UTC)
SLUG = "test-cancel-path-market"

_Session = get_sessionmaker(get_engine())


@pytest.fixture(autouse=True)
def clean():
    yield
    with _Session() as s:
        s.execute(text("delete from orders where market_slug = :m"), {"m": SLUG})
        s.commit()


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("MERIDIAN_ORDER_TOKEN", "test-token")
    return TestClient(api_module.app)


def _order(*, key, accepted=True, venue_id="v-cx-1", fill_status=None,
           filled=None, mode="HUMAN_CONFIRM") -> int:
    with _Session() as s:
        row = PlacedOrder(
            submitted_at=NOW,
            idempotency_key=f"test-cx-{key}",
            mode=mode,
            market_slug=SLUG,
            side="buy_yes",
            order_type="ORDER_TYPE_LIMIT",
            limit_price=Decimal("0.20"),
            quantity=Decimal("2"),
            accepted=accepted,
            venue_order_id=venue_id,
            fill_status=fill_status,
            filled_quantity=None if filled is None else Decimal(filled),
        )
        s.add(row)
        s.commit()
        return row.id


class FakeCancelResp:
    def __init__(self, status_code, body='{"ok":true}'):
        self.status_code = status_code
        self.body_text = body
        self.elapsed_ms = 87.5
        self.server_latency_ms = 12.0


class FakeOrderClient:
    def __init__(self, creds, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def cancel_order(self, venue_order_id):
        return FakeCancelResp(self.RESP_STATUS, self.RESP_BODY)


def _fake_venue(monkeypatch, status=200, body='{"ok":true}'):
    FakeOrderClient.RESP_STATUS = status
    FakeOrderClient.RESP_BODY = body
    monkeypatch.setattr(api_module, "PolymarketOrderClient", FakeOrderClient)
    monkeypatch.setattr(
        api_module.USCredentials, "from_env",
        staticmethod(lambda env=None: api_module.USCredentials("k", "s")),
    )


# --------------------------------------------------------------------------- #
# Gates
# --------------------------------------------------------------------------- #


def test_no_token_is_403(client):
    oid = _order(key="tok")
    assert client.post(f"/api/orders/{oid}/cancel").status_code == 403


def test_unknown_order_is_404(client):
    r = client.post("/api/orders/999999999/cancel",
                    headers={"X-Meridian-Order-Token": "test-token"})
    assert r.status_code == 404


def test_never_accepted_order_is_409(client):
    oid = _order(key="unacc", accepted=False)
    r = client.post(f"/api/orders/{oid}/cancel",
                    headers={"X-Meridian-Order-Token": "test-token"})
    assert r.status_code == 409
    assert "never accepted" in r.json()["detail"]


@pytest.mark.parametrize("terminal", ["FILLED", "CANCELLED", "EXPIRED"])
def test_terminal_orders_are_409(client, terminal):
    oid = _order(key=f"term-{terminal}", fill_status=terminal)
    r = client.post(f"/api/orders/{oid}/cancel",
                    headers={"X-Meridian-Order-Token": "test-token"})
    assert r.status_code == 409
    assert terminal in r.json()["detail"]


# --------------------------------------------------------------------------- #
# The venue's answer becomes the row's record
# --------------------------------------------------------------------------- #


def test_acknowledged_cancel_marks_cancelled_and_records_latency(client, monkeypatch):
    """The success path: 2xx → CANCELLED, fills preserved, latency and the
    verbatim response on the row (the V21 evidence)."""
    _fake_venue(monkeypatch, status=200, body='{"state":"canceled"}')
    oid = _order(key="ok", fill_status="PARTIAL", filled="0.5")
    r = client.post(f"/api/orders/{oid}/cancel",
                    headers={"X-Meridian-Order-Token": "test-token"})
    assert r.status_code == 200
    body = r.json()
    assert body["acknowledged"] is True
    assert body["cancel_latency_ms"] == 87.5
    with _Session() as s:
        row = s.get(PlacedOrder, oid)
        assert row.fill_status == "CANCELLED"
        assert row.filled_quantity == Decimal("0.5")       # fills preserved
        assert row.cancel_requested_at is not None
        assert row.cancel_http_status == 200
        assert row.cancel_latency_ms == Decimal("87.50")
        assert "canceled" in row.cancel_response


def test_rejected_cancel_leaves_fill_state_untouched(client, monkeypatch):
    """An unacknowledged cancel proves nothing: the order may still rest, so
    OPEN stays OPEN and the settlement fallback stays the terminal backstop.
    The refusal is still recorded — it is V21 evidence too."""
    _fake_venue(monkeypatch, status=404, body='{"code":5}')
    oid = _order(key="rej", fill_status="OPEN")
    r = client.post(f"/api/orders/{oid}/cancel",
                    headers={"X-Meridian-Order-Token": "test-token"})
    assert r.json()["acknowledged"] is False
    with _Session() as s:
        row = s.get(PlacedOrder, oid)
        assert row.fill_status == "OPEN"                   # untouched
        assert row.cancel_http_status == 404
        assert row.cancel_requested_at is not None         # attempt visible


def test_missing_credentials_still_record_the_attempt(client):
    """conftest blanks the credentials, so the raw endpoint 503s — and the
    attempt must still be visible on the row (recorded before the call)."""
    oid = _order(key="nocreds", fill_status="OPEN")
    r = client.post(f"/api/orders/{oid}/cancel",
                    headers={"X-Meridian-Order-Token": "test-token"})
    assert r.status_code == 503
    with _Session() as s:
        row = s.get(PlacedOrder, oid)
        assert row.cancel_requested_at is not None
        assert row.fill_status == "OPEN"


# --------------------------------------------------------------------------- #
# A machine may never initiate a cancel
# --------------------------------------------------------------------------- #


def test_the_fill_watcher_cannot_cancel():
    """The watcher may submit pre-authorized exits and nothing else. If this
    fails, a machine path gained the cancel verb — that must be a decision
    someone makes on purpose, here."""
    import core.fill_watcher as fw

    assert "cancel_order" not in inspect.getsource(fw)


def test_order_client_gained_cancel_and_nothing_else():
    """Deliberate update of the old shape test: `cancel_order` was added for
    the human cancel button (V21). Modify/amend remains inexpressible, and
    the read-only client is untouched."""
    public = {n for n in dir(pm_client.PolymarketOrderClient) if not n.startswith("_")}
    assert public == {"submit_limit_order", "cancel_order", "close"}
    src = inspect.getsource(pm_client.PolymarketOrderClient)
    for verb in ("_client.put", "_client.patch"):
        assert verb not in src
    read_only = {n for n in dir(pm_client.PolymarketAuthedClient) if not n.startswith("_")}
    assert read_only == {"get", "close"}


def test_cancel_signs_the_delete_verb_and_path_only():
    """Same scheme as every other request: Ed25519 over ts + METHOD + path,
    no body term — and the method signed is DELETE, verbatim."""
    src = inspect.getsource(pm_client.PolymarketOrderClient.cancel_order)
    assert '"DELETE"' in src
    assert "sign_body" not in src
