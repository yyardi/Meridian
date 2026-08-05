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
2. Economics. The taker fee is ``+0.06 * C * p * (1-p)``; a maker pays
   nothing. At p=0.50 that is 1.5c/contract paid versus zero. Against a 2c
   spread, that swing is most of the edge. (The venue advertises a maker
   rebate, but it has never been observed in this account and is not booked —
   findings C7.)

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

#: (action, outcome) -> the venue's order intent, from
#: docs.polymarket.us/api-reference/orders. Written as an exhaustive table
#: rather than nested conditionals because the failure mode of getting one cell
#: wrong is a real position on the wrong side of a real market, and a table can
#: be read against the documentation line by line.
#:
#:     ORDER_INTENT_BUY_LONG    buy YES  (go long the Yes outcome)
#:     ORDER_INTENT_SELL_LONG   sell YES (close a long Yes position)
#:     ORDER_INTENT_BUY_SHORT   buy NO   (go long the No outcome)
#:     ORDER_INTENT_SELL_SHORT  sell NO  (close a long No position)
_ORDER_INTENT: dict[tuple, str] = {}   # populated below, after the enums exist

#: Venue constraints, confirmed from live market payloads.
DEFAULT_TICK_SIZE = Decimal("0.01")
DEFAULT_MIN_TRADE_QTY = Decimal("0.01")

#: Absolute exchange limits on `price.value`, per
#: docs.polymarket.us/api-reference/orders: "Orders must have price.value
#: between 0.01 and 0.99." Enforced locally so a price the venue would reject
#: never becomes a submitted order — and, more importantly, so a NO order
#: derived from a 1.00 ask fails here rather than at the venue.
VENUE_MIN_PRICE = Decimal("0.01")
VENUE_MAX_PRICE = Decimal("0.99")


class ExecutionMode(str, Enum):
    """Only SHADOW is active in v1."""

    SHADOW = "SHADOW"
    HUMAN_CONFIRM = "HUMAN_CONFIRM"   # v2 scaffold, disabled
    AUTONOMOUS = "AUTONOMOUS"          # future; raises


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OutcomeSide(str, Enum):
    """Which outcome of the binary contract is being traded.

    A totals market is **one** contract per line: YES is OVER. There is no
    separate UNDER slug, so betting UNDER means buying the NO outcome of the
    same contract. Verified against 490 settled markets — settlement flips
    exactly at the line, e.g. GSV-TOR finished 158 and every line below it
    settled 1 while every line above settled 0.

    This distinction did not exist while the system only ever bought YES. It
    has to exist now, because a NO position sent as a YES buy is not a rounding
    error, it is the opposite trade.
    """

    YES = "YES"
    NO = "NO"


_ORDER_INTENT.update({
    (OrderSide.BUY,  OutcomeSide.YES): "ORDER_INTENT_BUY_LONG",
    (OrderSide.SELL, OutcomeSide.YES): "ORDER_INTENT_SELL_LONG",
    (OrderSide.BUY,  OutcomeSide.NO):  "ORDER_INTENT_BUY_SHORT",
    (OrderSide.SELL, OutcomeSide.NO):  "ORDER_INTENT_SELL_SHORT",
})


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
    #: **Always the YES-side price**, because that is what the venue's
    #: ``price.value`` field means regardless of which outcome you are buying.
    #: For a NO order this is *not* what you pay — see :attr:`cost_per_contract`.
    limit_price: Decimal
    quantity: Decimal
    idempotency_key: str

    #: Which outcome. Defaults to YES so every existing caller — the shadow
    #: pipeline, the backtest — keeps its current behaviour unchanged.
    outcome: OutcomeSide = OutcomeSide.YES

    #: Fixed. Exposed for the payload builder, never settable by a caller.
    order_type: str = field(default=_ORDER_TYPE, init=False)

    @property
    def cost_per_contract(self) -> Decimal:
        """What one contract actually costs you.

        For YES this is the limit price. For NO it is ``1 - limit_price``,
        because the price field is quoted from the YES side either way.

        This is the number a human should see on a ticket. Showing them
        ``limit_price`` on a NO order would display 0.84 for a bet that costs
        0.16 — which is not a cosmetic difference, it is the wrong side at four
        times the price, and it is exactly the confusion this property exists
        to prevent.
        """
        if self.outcome is OutcomeSide.NO:
            return Decimal("1") - self.limit_price
        return self.limit_price

    @property
    def stake(self) -> Decimal:
        """Total cash at risk: cost per contract × quantity."""
        return self.cost_per_contract * self.quantity

    def to_payload(self, *, post_only: bool = True) -> dict:
        """Venue payload, per docs.polymarket.us/api-reference/orders.

        ``type`` is ``self.order_type``, which is ``init=False`` and therefore
        not settable by any caller — a market order cannot be expressed through
        this method because it cannot be expressed by this dataclass.

        ``post_only`` maps to the venue's ``participateDontInitiate``: the order
        may rest but must never cross. It defaults to True because the entire
        economic case for this system is being a maker — the taker fee is
        ``+0.06·C·p·(1-p)`` against a maker coefficient of at best 0, and
        against a 2c spread that swing is most of the edge. An order that would
        cross is rejected by the venue rather than filled expensively, which is
        the outcome we want: a crossed limit is a mispriced decision, not a
        trade worth having.

        ``manualOrderIndicator`` is a CFTC-facing field and is truthfully
        MANUAL: every order this system sends was clicked by a human.

        **The price is always the YES side.** The venue documents this
        explicitly: "The ``price.value`` field always represents the long
        side's price, regardless of which order intent you use", with the
        worked example that trading NO at 0.83 means sending 0.17. This class
        stores ``limit_price`` in that convention already, so no inversion
        happens here — the inversion lives in whoever *chooses* the price, and
        :attr:`cost_per_contract` is how a human sees what they pay.
        """
        return {
            "marketSlug": self.market_slug,
            "type": self.order_type,          # always ORDER_TYPE_LIMIT
            "price": {"value": str(self.limit_price), "currency": "USD"},
            "quantity": str(self.quantity),
            "tif": "TIME_IN_FORCE_GOOD_TILL_CANCEL",
            "intent": _ORDER_INTENT[(self.side, self.outcome)],
            # The venue accepts either `intent` alone or this pair, and
            # documents that **when both are sent the pair wins**. Sending both
            # is therefore not redundant belt-and-braces — it makes the
            # authoritative field the explicit one. `outcomeSide` names the
            # outcome directly, where `intent` encodes it as long/short and
            # relies on the reader knowing that "short" means buying NO.
            "outcomeSide": f"OUTCOME_SIDE_{self.outcome.value}",
            "action": (
                "ORDER_ACTION_BUY" if self.side is OrderSide.BUY
                else "ORDER_ACTION_SELL"
            ),
            "manualOrderIndicator": "MANUAL_ORDER_INDICATOR_MANUAL",
            "participateDontInitiate": post_only,
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


def make_idempotency_key(
    *,
    market_slug: str,
    decided_at: dt.datetime,
    limit_price: Decimal,
    outcome: OutcomeSide = OutcomeSide.YES,
) -> str:
    """Deterministic key so a retry cannot double-place.

    The outcome is folded in **only for NO**, deliberately. A YES order's key is
    byte-identical to what this function produced before outcomes existed, so
    the 1,700 rows already in `shadow_orders` keep their keys and
    `on_conflict_do_nothing` keeps working. A NO order on the same market at the
    same price is a genuinely different order and must not collide with its YES
    counterpart — which it otherwise would, since both quote the same YES-side
    price.
    """
    raw = f"{market_slug}|{decided_at.isoformat()}|{limit_price}"
    if outcome is OutcomeSide.NO:
        raw += "|NO"
    return "mer-" + hashlib.sha256(raw.encode()).hexdigest()[:32]


def build_order(
    *,
    market_slug: str,
    side: OrderSide,
    limit_price: Decimal,
    quantity: Decimal,
    decided_at: dt.datetime,
    outcome: OutcomeSide = OutcomeSide.YES,
) -> LimitOrder:
    """Construct a limit order.

    ``limit_price`` is a required keyword argument and is **always the YES-side
    price**, whichever outcome is being bought — that is the venue's
    convention for ``price.value`` and keeping one convention end to end is
    what stops an inversion getting applied twice or not at all.

    The bound is the venue's own: ``price.value`` must be between 0.01 and
    0.99. That is stricter than "inside (0, 1)" and it is the real constraint —
    a NO order priced off a 1.00 ask would otherwise be built here and rejected
    at the venue.
    """
    price = round_to_tick(limit_price)
    if not (VENUE_MIN_PRICE <= price <= VENUE_MAX_PRICE):
        raise ValueError(
            f"price.value {price} outside the venue's "
            f"[{VENUE_MIN_PRICE}, {VENUE_MAX_PRICE}] range"
        )
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    return LimitOrder(
        market_slug=market_slug,
        side=side,
        limit_price=price,
        quantity=quantity,
        outcome=outcome,
        idempotency_key=make_idempotency_key(
            market_slug=market_slug, decided_at=decided_at,
            limit_price=price, outcome=outcome,
        ),
    )



# --------------------------------------------------------------------- #
# Market policies, one per strategy
# --------------------------------------------------------------------- #

MARKET_TOTAL = "basketball_team_full_game_total"
MARKET_SPREAD = "basketball_team_full_game_spread"
MARKET_WINNER = "basketball_team_full_game_winner"

#: ANCHOR — pregame, hold to settlement.
#:
#: The moneyline is excluded on measured evidence: 2024-2026, the model hits
#: 33.4% on raw selection and 25.0% after market shrinkage, with the entire 95%
#: interval [0.178, 0.339] below the 0.524 breakeven. Not a marginal loser, a
#: decisive one. See docs/math/market-shrinkage.md.
#:
#: **What that evidence is actually about.** It measures our ability to
#: *forecast a winner from team ratings better than the market can*, pregame.
#: The market's margin MAE (9.65) beats ours (10.19), so betting our
#: disagreement loses. It says nothing about a market whose edge comes from
#: reacting faster than the venue reprices — a completely different claim,
#: tested against different data.
ANCHOR_MARKETS = frozenset({MARKET_TOTAL, MARKET_SPREAD})

#: PULSE — in-game. **Undecided, deliberately.**
#:
#: The moneyline is the market most likely to matter here: it swings hardest in
#: close games, and a lead being cut moves it far more than it moves a deep
#: ladder rung. Carrying ANCHOR's exclusion across would be applying a pregame
#: forecasting result to a latency strategy, which is not what it measured.
#:
#: It is empty rather than permissive, because "no policy" is the honest state
#: for a strategy with no evidence: PULSE's gates all currently report NO DATA.
#: Set this from PULSE's own measurements once they exist — do not default it
#: to ANCHOR's, and do not default it to everything.
PULSE_MARKETS: frozenset[str] = frozenset()

#: Research runs that need to observe a market before deciding on it. Empty set
#: means `is_tradable` allows everything; safe only because the kill switch and
#: SHADOW mode sit in front of it.
RESEARCH_MARKETS: frozenset[str] = frozenset()


@dataclass
class ExecutorConfig:
    mode: ExecutionMode = ExecutionMode.SHADOW
    #: Single flag disabling all placement. Checked before any authenticated
    #: call, in every mode.
    kill_switch: bool = True
    tick_size: Decimal = DEFAULT_TICK_SIZE
    min_trade_qty: Decimal = DEFAULT_MIN_TRADE_QTY

    #: Market types this executor is allowed to trade.
    #:
    #: **This is a per-strategy policy, not a fact about the moneyline.**
    #:
    #: The default is ANCHOR's (see `ANCHOR_MARKETS`), which excludes the
    #: moneyline on strong measured evidence — but that evidence is about
    #: *pregame forecasting*, and it does not transfer to a strategy whose edge
    #: comes from somewhere else. Constructing an executor for a different
    #: strategy means passing that strategy's own policy; inheriting ANCHOR's by
    #: accident is how a measurement about one thing silently governs another.
    #:
    #: It lives on the *executor* rather than in the model config on purpose.
    #: It is an execution policy, not a model parameter: putting it in
    #: `WNBATotalsConfig` would change `config_hash` and split the prediction
    #: log's history, resetting the shadow gate for a decision that has nothing
    #: to do with how the model prices anything. Predictions for refused markets
    #: are still logged — the log records everything, including what we decline
    #: to trade.
    tradable_market_types: frozenset[str] = ANCHOR_MARKETS

    def is_tradable(self, sports_market_type: str | None) -> bool:
        """False for markets this policy refuses.

        An empty set means "no policy" — used by research runs that want to
        measure a market before deciding whether to trade it.
        """
        if not self.tradable_market_types:
            return True
        return (sports_market_type or "") in self.tradable_market_types


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
