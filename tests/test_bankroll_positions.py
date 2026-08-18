"""Positions make the bankroll live — and the payload's one ambiguous field
is handled so that being wrong about it cannot cost more than the position.

What this pins
--------------
The operator held an open position while the balances payload read
``assetNotional: 0`` — on this venue, positions are simply not in the
balances response. They live at ``GET /v1/portfolio/positions``: a MAP of
market slug to position (observed live 2026-08-18 on a flat account:
``{"positions": {}, "nextCursor": "", "eof": true}``).

The venue's own docs disagree about ``cashValue``: the REST reference calls
it "unrealized PnL", the SDK reference "current unrealized value" (market
value). Until an open position has been observed against our own book, the
module clamps every position's value to ±quantity — the most a binary
contract can be worth — and cross-checks against the recorder's mid when it
can (``verify_position_value``).

Two numbers leave the module and they are NOT the same:
``bankroll`` (sizing) stays ``min(cash, buyingPower)`` — position value is
not spendable on the next order. ``equity`` (display) adds the clamped
position values.
"""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal

import pytest

from core import bankroll as bk

UTC = dt.timezone.utc


def _pos_payload(**over):
    base = {
        "netPositionDecimal": "2.48",
        "qtyBoughtDecimal": "2.48",
        "qtySoldDecimal": "0",
        "qtyAvailableDecimal": "2.48",
        "cost": {"value": "0.67", "currency": "USD"},
        "cashValue": {"value": "0.77", "currency": "USD"},
        "realized": {"value": "0", "currency": "USD"},
        "expired": False,
        "marketMetadata": {"slug": "tsc-wnba-la-min-2026-08-18-197pt5",
                           "outcome": "YES", "title": "LA/MIN over 197.5"},
    }
    base.update(over)
    return base


def _body(positions=None, eof=True, cursor=""):
    return {"positions": positions or {}, "nextCursor": cursor, "eof": eof,
            "availablePositions": []}


class _Resp:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.body_text = body if isinstance(body, str) else json.dumps(body)


class _MultiClient:
    """`get` and nothing else; answers per path, in order for repeats."""

    def __init__(self, routes):
        self._routes = {k: list(v) for k, v in routes.items()}
        self.calls = []

    def get(self, path, params=None, **kw):
        self.calls.append((path, dict(params or {})))
        queue = self._routes[path]
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def close(self):
        pass


BAL = _Resp(200, {"balances": [{
    "currentBalance": 23.5704, "currency": "USD", "buyingPower": 23.5704,
    "assetNotional": 0, "assetAvailable": 0, "pendingCredit": 0,
    "openOrders": 0, "unsettledFunds": 0, "pendingWithdrawals": [],
    "marginRequirement": 0}]})


# ------------------------------------------------------------------ #
# Parsing the venue's map shape
# ------------------------------------------------------------------ #


def test_the_observed_flat_account_parses_as_no_positions():
    assert bk.parse_positions(_body()) == []


def test_positions_is_a_map_not_a_list():
    """Unlike activities. Reading the wrong container shape as flat would be
    the balances bug all over again — silence where there is money."""
    with pytest.raises(bk.BankrollUnavailable):
        bk.parse_positions({"positions": [], "eof": True})
    with pytest.raises(bk.BankrollUnavailable):
        bk.parse_positions({"eof": True})


def test_a_position_parses_with_amount_objects_and_decimal_strings():
    [p] = bk.parse_positions(_body({"m": _pos_payload()}))
    assert p.quantity == Decimal("2.48")
    assert p.cost == Decimal("0.67")
    assert p.cash_value == Decimal("0.77")
    assert p.market_slug == "tsc-wnba-la-min-2026-08-18-197pt5"
    assert p.outcome == "YES"


def test_bare_numbers_are_tolerated_where_docs_show_amounts():
    [p] = bk.parse_positions(_body({"m": _pos_payload(cost="0.5",
                                                     cashValue=0.6)}))
    assert p.cost == Decimal("0.5")
    assert p.cash_value == Decimal("0.6")


# ------------------------------------------------------------------ #
# The clamp: wrong docs cannot cost more than the position
# ------------------------------------------------------------------ #


def test_value_is_clamped_to_what_a_binary_position_can_be_worth():
    """2.48 contracts can be worth at most $2.48. A cashValue beyond that —
    whichever documented reading produced it — is capped, so a semantics
    error mis-states equity by at most the position's own size."""
    [p] = bk.parse_positions(_body({"m": _pos_payload(
        cashValue={"value": "9.99", "currency": "USD"})}))
    assert p.value == Decimal("2.48")
    [p] = bk.parse_positions(_body({"m": _pos_payload(
        netPositionDecimal="-2.48",
        cashValue={"value": "-9.99", "currency": "USD"})}))
    assert p.value == Decimal("-2.48")


def test_a_sane_cash_value_passes_through_unclamped():
    [p] = bk.parse_positions(_body({"m": _pos_payload()}))
    assert p.value == Decimal("0.77")


def test_unrealized_is_value_minus_cost_per_supports_definition():
    """Support (2026-08-18): cashValue is market value; unrealized PnL is
    cashValue − cost. Stated as a field so nobody re-derives it wrong from
    the once-ambiguous docs."""
    [p] = bk.parse_positions(_body({"m": _pos_payload()}))
    assert p.unrealized == Decimal("0.10")
    assert p.to_dict()["unrealized"] == 0.10


# ------------------------------------------------------------------ #
# bankroll vs equity — sizing must not inherit display's optimism
# ------------------------------------------------------------------ #


def _snap(positions=(), read_ok=True):
    return bk.AccountSnapshot(
        observed_at=dt.datetime.now(UTC), currency="USD",
        cash=Decimal("23.57"), buying_power=Decimal("23.57"),
        asset_notional=bk.ZERO, open_orders=bk.ZERO, unsettled_funds=bk.ZERO,
        pending_credit=bk.ZERO, margin_requirement=bk.ZERO,
        positions=tuple(positions), positions_read_ok=read_ok)


def test_equity_adds_positions_and_bankroll_does_not():
    [p] = bk.parse_positions(_body({"m": _pos_payload()}))
    snap = _snap([p])
    assert snap.bankroll == Decimal("23.57"), "sizing input must not change"
    assert snap.equity == Decimal("24.34")
    d = snap.to_dict()
    assert d["bankroll"] == 23.57
    assert d["equity"] == 24.34
    assert d["n_positions"] == 1
    assert d["positions"][0]["value"] == 0.77


def test_a_flat_account_has_equal_bankroll_and_equity():
    snap = _snap([])
    assert snap.equity == snap.bankroll


# ------------------------------------------------------------------ #
# fetch: two GETs, and a positions failure degrades instead of failing
# ------------------------------------------------------------------ #


def test_fetch_reads_both_endpoints_and_pages_with_params():
    page1 = _Resp(200, _body({"m1": _pos_payload()}, eof=False, cursor="c2"))
    page2 = _Resp(200, _body({"m2": _pos_payload(
        marketMetadata={"slug": "other-slug"})}, eof=True))
    client = _MultiClient({bk.BALANCES_PATH: [BAL],
                           bk.POSITIONS_PATH: [page1, page2]})
    snap = bk.fetch(client)
    assert snap.positions_read_ok
    assert len(snap.positions) == 2
    pos_calls = [c for c in client.calls if c[0] == bk.POSITIONS_PATH]
    assert pos_calls[0][1] == {"limit": bk.POSITIONS_PAGE_LIMIT}
    assert pos_calls[1][1]["cursor"] == "c2", (
        "the cursor must travel as params — a query string embedded in the "
        "path signs the wrong message and 401s (observed live)")


def test_positions_failure_degrades_the_snapshot_not_the_balance():
    client = _MultiClient({bk.BALANCES_PATH: [BAL],
                           bk.POSITIONS_PATH: [_Resp(503, "nope")]})
    snap = bk.fetch(client)
    assert snap.bankroll == Decimal("23.5704"), "the balance is still true"
    assert snap.positions_read_ok is False
    assert snap.positions == ()
    assert snap.to_dict()["positions_read_ok"] is False


# ------------------------------------------------------------------ #
# The semantics cross-check — the observation that retires the ambiguity
# ------------------------------------------------------------------ #


def test_verify_prefers_value_reading_when_it_fits():
    """qty 2.48 @ mid 0.31: cashValue 0.77 ≈ qty*mid → the SDK reading."""
    [p] = bk.parse_positions(_body({"m": _pos_payload()}))
    assert bk.verify_position_value(p, mid=0.31) == "value"


def test_verify_prefers_pnl_reading_when_that_fits():
    """Same book, but cashValue ≈ qty*mid − cost → the REST reading."""
    [p] = bk.parse_positions(_body({"m": _pos_payload(
        cashValue={"value": "0.10", "currency": "USD"})}))
    assert bk.verify_position_value(p, mid=0.31) == "pnl"


def test_verify_says_ambiguous_when_it_cannot_tell():
    """A near-zero cost makes the two readings coincide; the check must say
    so rather than pick one."""
    [p] = bk.parse_positions(_body({"m": _pos_payload(
        cost={"value": "0.01", "currency": "USD"},
        cashValue={"value": "0.77", "currency": "USD"})}))
    assert bk.verify_position_value(p, mid=0.31) == "ambiguous"
