"""Execution layer — shadow mode only in v1.

**This module places no real orders.** It records what it *would* have traded
so that, later, those intentions can be compared against what actually
happened.

Limit orders only, enforced by construction
-------------------------------------------
There is deliberately no order-type parameter anywhere in this module. The
order type is a hardcoded internal constant, and :func:`build_order` takes a
**required** ``limit_price``. An aggressive order is not something you are
discouraged from writing — it is not expressible.

Two reasons, both real:

1. A ladder rung was observed quoting ``bid 0.03 / ask 0.39``. Crossing that
   fills nowhere near the intended price.
2. Economics. The taker fee is ``+0.06 * C * p * (1-p)``; the maker coefficient
   is ``-0.0125`` — a *rebate*. At p=0.50 that is 1.5c/contract paid versus
   0.3c earned. Against a 2c spread, that swing is most of the edge.

Credentials
-----------
Read from the environment, never hardcoded and never logged. Shadow mode makes
**zero** authenticated calls, so it does not need them at all.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum

import structlog

from core.backtest.fills import fee_per_contract
from core.kelly_sizing import PositionSize

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc

#: The only order type this system will ever construct. Not a parameter,
#: not a default — a constant, so there is nothing to pass incorrectly.
_ORDER_TYPE = "ORDER_TYPE_LIMIT"

#: Venue constraints, confirmed from live market payloads.
DEFAULT_TICK_SIZE = Decimal("0.01")
DEFAULT_MIN_TRADE_QTY = Decimal("0.01")


class ExecutionMode(str, Enum):
    """Only SHADOW is active in v1."""

    SHADOW = "SHADOW"
    HUMAN_CONFIRM = "HUMAN_CONFIRM"   # v2 scaffold, disabled
    AUTONOMOUS = "AUTONOMOUS"          # future; raises


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class ExecutionBlocked(RuntimeError):
    """Raised when a guard prevents placement."""


@dataclass(frozen=True)
class LimitOrder:
    """A limit order. There is no other kind.

    ``limit_price`` is required and positional-safe: an order cannot be built
    without stating the price it must not cross.
    """

    market_slug: str
    side: OrderSide
    limit_price: Decimal
    quantity: Decimal
    idempotency_key: str

    #: Fixed. Exposed for the payload builder, never settable by a caller.
    order_type: str = field(default=_ORDER_TYPE, init=False)

    def to_payload(self) -> dict:
        """Venue payload. Verify field names against docs.polymarket.us."""
        return {
            "market": self.market_slug,
            "side": self.side.value,
            "type": self.order_type,          # always limit
            "price": str(self.limit_price),
            "quantity": str(self.quantity),
            "clientOrderId": self.idempotency_key,
        }


def round_to_tick(price: float | Decimal, tick: Decimal = DEFAULT_TICK_SIZE) -> Decimal:
    """Round a price to a valid venue tick.

    An unrounded price is rejected by the venue, so a shadow order carrying one
    would not have been a real order — and the log would be fiction.
    """
    p = Decimal(str(price))
    return (p / tick).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * tick


def would_rest(
    *, side: OrderSide, limit_price: Decimal, best_bid: Decimal | None, best_ask: Decimal | None
) -> bool:
    """True if the order would rest on the book (maker) rather than cross (taker).

    Buying at or below the best bid rests; buying at or above the best ask
    crosses immediately and pays the taker fee.
    """
    if side is OrderSide.BUY:
        if best_ask is None:
            return True
        return limit_price < best_ask
    if best_bid is None:
        return True
    return limit_price > best_bid


def make_idempotency_key(*, market_slug: str, decided_at: dt.datetime, limit_price: Decimal) -> str:
    """Deterministic key so a retry cannot double-place.

    Not used in shadow mode (nothing is sent), but the key is recorded now so
    the v2 human-confirm path inherits it rather than bolting it on later.
    """
    raw = f"{market_slug}|{decided_at.isoformat()}|{limit_price}"
    return "mer-" + hashlib.sha256(raw.encode()).hexdigest()[:32]


def build_order(
    *,
    market_slug: str,
    side: OrderSide,
    limit_price: Decimal,
    quantity: Decimal,
    decided_at: dt.datetime,
) -> LimitOrder:
    """Construct a limit order.

    ``limit_price`` is a required keyword argument. There is no code path that
    produces an order without one, and no parameter that selects a different
    order type.
    """
    price = round_to_tick(limit_price)
    if not (Decimal("0") < price < Decimal("1")):
        raise ValueError(f"limit_price {price} outside (0, 1)")
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    return LimitOrder(
        market_slug=market_slug,
        side=side,
        limit_price=price,
        quantity=quantity,
        idempotency_key=make_idempotency_key(
            market_slug=market_slug, decided_at=decided_at, limit_price=price
        ),
    )


@dataclass
class ExecutorConfig:
    mode: ExecutionMode = ExecutionMode.SHADOW
    #: Single flag disabling all placement. Checked before any authenticated
    #: call, in every mode.
    kill_switch: bool = True
    tick_size: Decimal = DEFAULT_TICK_SIZE
    min_trade_qty: Decimal = DEFAULT_MIN_TRADE_QTY


@dataclass
class ExecutionDecision:
    """What the executor decided, and why."""

    market_slug: str
    placed: bool
    order: LimitOrder | None
    would_rest: bool
    expected_fee: Decimal
    reason: str
    notes: tuple[str, ...] = field(default_factory=tuple)


class Executor:
    """Shadow-mode executor.

    Makes **no** authenticated calls. The venue client is accepted only so the
    v2 path has somewhere to plug in, and shadow mode never touches it.
    """

    def __init__(self, config: ExecutorConfig | None = None, client=None) -> None:
        self.config = config or ExecutorConfig()
        self._client = client

    def decide(
        self,
        *,
        market_slug: str,
        side: OrderSide,
        model_probability: float,
        size: PositionSize,
        best_bid: float | None,
        best_ask: float | None,
        decided_at: dt.datetime,
        min_trade_qty: Decimal | None = None,
    ) -> ExecutionDecision:
        """Decide an order without placing it."""
        notes: list[str] = []
        min_qty = min_trade_qty or self.config.min_trade_qty

        if not size.is_tradeable:
            return ExecutionDecision(
                market_slug=market_slug, placed=False, order=None, would_rest=True,
                expected_fee=Decimal("0"),
                reason=f"no position: {size.binding_constraint.value}",
                notes=tuple(size.notes),
            )

        # Post at the near touch: buying rests at the bid, which earns the
        # maker rebate instead of paying the taker fee.
        if side is OrderSide.BUY:
            target = best_bid if best_bid is not None else model_probability
        else:
            target = best_ask if best_ask is not None else model_probability

        limit_price = round_to_tick(target, self.config.tick_size)
        quantity = Decimal(str(round(size.contracts, 4)))

        if quantity < min_qty:
            notes.append(
                f"size {quantity} is below the venue minimum {min_qty} — "
                "not tradeable at this bankroll; NOT rounded up"
            )
            return ExecutionDecision(
                market_slug=market_slug, placed=False, order=None, would_rest=True,
                expected_fee=Decimal("0"),
                reason="below_minimum_trade_qty", notes=tuple(notes),
            )

        order = build_order(
            market_slug=market_slug, side=side, limit_price=limit_price,
            quantity=quantity, decided_at=decided_at,
        )
        rests = would_rest(
            side=side, limit_price=limit_price,
            best_bid=Decimal(str(best_bid)) if best_bid is not None else None,
            best_ask=Decimal(str(best_ask)) if best_ask is not None else None,
        )
        fee = Decimal(str(
            fee_per_contract(float(limit_price), is_maker=rests) * float(quantity)
        ))
        if not rests:
            notes.append("limit would CROSS the spread: taker fee applies, not the rebate")

        return ExecutionDecision(
            market_slug=market_slug, placed=False, order=order, would_rest=rests,
            expected_fee=fee, reason="shadow", notes=tuple(notes),
        )

    def execute(self, decision: ExecutionDecision) -> ExecutionDecision:
        """Placement gate. In v1 this never places anything."""
        if self.config.mode is ExecutionMode.AUTONOMOUS:
            raise NotImplementedError(
                "Autonomous execution is not implemented. It is gated behind a real, "
                "positive, walk-forward-validated track record. The current model is "
                "uncalibrated — see docs/math/calibration-problem.md."
            )

        if self.config.kill_switch:
            log.info("kill_switch_active", market=decision.market_slug)
            return decision

        if self.config.mode is ExecutionMode.SHADOW:
            log.info(
                "shadow_order",
                market=decision.market_slug,
                limit_price=str(decision.order.limit_price) if decision.order else None,
                quantity=str(decision.order.quantity) if decision.order else None,
                would_rest=decision.would_rest,
                expected_fee=str(decision.expected_fee),
            )
            return decision

        if self.config.mode is ExecutionMode.HUMAN_CONFIRM:
            raise ExecutionBlocked(
                "HUMAN_CONFIRM is a v2 scaffold and is not enabled. Placement "
                "requires explicit interactive confirmation that is not built yet."
            )

        raise ExecutionBlocked(f"unknown mode {self.config.mode}")
