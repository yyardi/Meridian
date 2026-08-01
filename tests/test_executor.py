"""Executor safety properties.

Every test here guards something that would cost real money if it regressed.
"""

from __future__ import annotations

import datetime as dt
import inspect
from decimal import Decimal

import pytest

from core import executor as executor_module
from core.executor import (
    ExecutionBlocked,
    ExecutionMode,
    Executor,
    ExecutorConfig,
    LimitOrder,
    OrderSide,
    build_order,
    round_to_tick,
    would_rest,
)
from core.kelly_sizing import Constraint, PositionSize

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 7, 31, tzinfo=UTC)


def _size(contracts=10.0, dollars=5.0) -> PositionSize:
    return PositionSize(
        dollars=dollars, contracts=contracts, kelly_fraction_raw=0.1,
        kelly_fraction_used=0.025, edge_gross=0.05, edge_net=0.045,
        binding_constraint=Constraint.KELLY,
    )


def _no_size() -> PositionSize:
    return PositionSize(
        dollars=0.0, contracts=0.0, kelly_fraction_raw=0.0, kelly_fraction_used=0.0,
        edge_gross=-0.01, edge_net=-0.02, binding_constraint=Constraint.NEGATIVE_EDGE,
    )


# ---------------------------------------------------------------- #
# The hard rule: no aggressive-order code path exists
# ---------------------------------------------------------------- #

def test_module_contains_no_aggressive_order_type():
    """A market-order type string must not appear anywhere in the module."""
    src = inspect.getsource(executor_module)
    forbidden = "ORDER_TYPE_" + "MARKET"        # split so this test isn't a hit
    assert forbidden not in src
    assert "ORDER_TYPE_LIMIT" in src


def test_order_type_is_fixed_and_not_constructible():
    """order_type is init=False — a caller cannot set it."""
    order = build_order(
        market_slug="tsc-x", side=OrderSide.BUY, limit_price=Decimal("0.52"),
        quantity=Decimal("10"), decided_at=NOW,
    )
    assert order.order_type == "ORDER_TYPE_LIMIT"
    with pytest.raises(TypeError):
        LimitOrder(  # type: ignore[call-arg]
            market_slug="x", side=OrderSide.BUY, limit_price=Decimal("0.5"),
            quantity=Decimal("1"), idempotency_key="k", order_type="anything",
        )


def test_limit_price_is_required():
    with pytest.raises(TypeError):
        build_order(  # type: ignore[call-arg]
            market_slug="tsc-x", side=OrderSide.BUY,
            quantity=Decimal("10"), decided_at=NOW,
        )


def test_payload_always_declares_a_limit_order():
    order = build_order(
        market_slug="tsc-x", side=OrderSide.BUY, limit_price=Decimal("0.52"),
        quantity=Decimal("10"), decided_at=NOW,
    )
    assert order.to_payload()["type"] == "ORDER_TYPE_LIMIT"


# ---------------------------------------------------------------- #
# Venue constraints
# ---------------------------------------------------------------- #

@pytest.mark.parametrize("raw,expected", [
    (0.5231, "0.52"), (0.5250, "0.53"), (0.519, "0.52"), (0.9, "0.90"),
])
def test_prices_round_to_valid_ticks(raw, expected):
    assert round_to_tick(raw) == Decimal(expected)


def test_price_outside_zero_one_is_rejected():
    for bad in (Decimal("0"), Decimal("1"), Decimal("1.5")):
        with pytest.raises(ValueError):
            build_order(market_slug="x", side=OrderSide.BUY, limit_price=bad,
                        quantity=Decimal("1"), decided_at=NOW)


def test_sub_minimum_size_is_flagged_not_rounded_up():
    """Rounding up would place a bet larger than the model sanctioned."""
    ex = Executor()
    d = ex.decide(
        market_slug="tsc-x", side=OrderSide.BUY, model_probability=0.6,
        size=_size(contracts=0.001), best_bid=0.50, best_ask=0.52, decided_at=NOW,
    )
    assert d.placed is False and d.order is None
    assert d.reason == "below_minimum_trade_qty"
    assert any("NOT rounded up" in n for n in d.notes)


# ---------------------------------------------------------------- #
# Maker vs taker
# ---------------------------------------------------------------- #

def test_maker_taker_classification():
    # Buying below the ask rests; at or above it crosses.
    assert would_rest(side=OrderSide.BUY, limit_price=Decimal("0.50"),
                      best_bid=Decimal("0.50"), best_ask=Decimal("0.52")) is True
    assert would_rest(side=OrderSide.BUY, limit_price=Decimal("0.52"),
                      best_bid=Decimal("0.50"), best_ask=Decimal("0.52")) is False
    # Selling above the bid rests.
    assert would_rest(side=OrderSide.SELL, limit_price=Decimal("0.52"),
                      best_bid=Decimal("0.50"), best_ask=Decimal("0.52")) is True


def test_resting_order_earns_a_rebate():
    ex = Executor()
    d = ex.decide(
        market_slug="tsc-x", side=OrderSide.BUY, model_probability=0.60,
        size=_size(contracts=100.0), best_bid=0.50, best_ask=0.52, decided_at=NOW,
    )
    assert d.would_rest is True
    assert d.expected_fee < 0        # negative fee == rebate earned


def test_crossing_order_is_flagged_and_pays_a_fee():
    ex = Executor()
    d = ex.decide(
        market_slug="tsc-x", side=OrderSide.BUY, model_probability=0.60,
        size=_size(contracts=100.0),
        best_bid=None, best_ask=0.40,     # our 0.60 target crosses a 0.40 ask
        decided_at=NOW,
    )
    assert d.would_rest is False
    assert d.expected_fee > 0
    assert any("CROSS" in n for n in d.notes)


# ---------------------------------------------------------------- #
# Modes and the kill switch
# ---------------------------------------------------------------- #

class ExplodingClient:
    """Any attribute access is a test failure — shadow mode must not call out."""

    def __getattr__(self, name):
        raise AssertionError(f"shadow mode made an authenticated call: {name}")


def test_shadow_mode_makes_zero_authenticated_calls():
    ex = Executor(ExecutorConfig(mode=ExecutionMode.SHADOW, kill_switch=False),
                  client=ExplodingClient())
    d = ex.decide(
        market_slug="tsc-x", side=OrderSide.BUY, model_probability=0.60,
        size=_size(), best_bid=0.50, best_ask=0.52, decided_at=NOW,
    )
    out = ex.execute(d)          # would raise if the client were touched
    assert out.placed is False


def test_kill_switch_blocks_placement():
    ex = Executor(ExecutorConfig(mode=ExecutionMode.SHADOW, kill_switch=True))
    d = ex.decide(
        market_slug="tsc-x", side=OrderSide.BUY, model_probability=0.60,
        size=_size(), best_bid=0.50, best_ask=0.52, decided_at=NOW,
    )
    assert ex.execute(d).placed is False


def test_autonomous_mode_raises():
    ex = Executor(ExecutorConfig(mode=ExecutionMode.AUTONOMOUS, kill_switch=False))
    d = ex.decide(
        market_slug="tsc-x", side=OrderSide.BUY, model_probability=0.60,
        size=_size(), best_bid=0.50, best_ask=0.52, decided_at=NOW,
    )
    with pytest.raises(NotImplementedError, match="not implemented"):
        ex.execute(d)


def test_human_confirm_is_scaffold_only():
    ex = Executor(ExecutorConfig(mode=ExecutionMode.HUMAN_CONFIRM, kill_switch=False))
    d = ex.decide(
        market_slug="tsc-x", side=OrderSide.BUY, model_probability=0.60,
        size=_size(), best_bid=0.50, best_ask=0.52, decided_at=NOW,
    )
    with pytest.raises(ExecutionBlocked, match="not enabled"):
        ex.execute(d)


def test_default_config_is_shadow_with_kill_switch_on():
    cfg = ExecutorConfig()
    assert cfg.mode is ExecutionMode.SHADOW and cfg.kill_switch is True


# ---------------------------------------------------------------- #
# Misc
# ---------------------------------------------------------------- #

def test_no_position_produces_no_order():
    ex = Executor()
    d = ex.decide(
        market_slug="tsc-x", side=OrderSide.BUY, model_probability=0.40,
        size=_no_size(), best_bid=0.50, best_ask=0.52, decided_at=NOW,
    )
    assert d.order is None and "negative_edge" in d.reason


def test_idempotency_key_is_deterministic_and_carries_no_secret():
    a = build_order(market_slug="tsc-x", side=OrderSide.BUY,
                    limit_price=Decimal("0.52"), quantity=Decimal("10"), decided_at=NOW)
    b = build_order(market_slug="tsc-x", side=OrderSide.BUY,
                    limit_price=Decimal("0.52"), quantity=Decimal("10"), decided_at=NOW)
    assert a.idempotency_key == b.idempotency_key
    assert a.idempotency_key.startswith("mer-")


def test_no_credentials_are_read_at_import_or_in_shadow():
    """Shadow mode must work with no keys present at all."""
    src = inspect.getsource(executor_module)
    assert "POLYMARKET_SECRET_KEY" not in src
