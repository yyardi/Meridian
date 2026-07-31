"""Fill simulation and fee maths.

What actually costs money here
------------------------------
Measured WNBA book depth at top-of-book is ~$795 on a total and ~$7,452 on a
moneyline. At a $25-40 bankroll you are ~1/20th of the best price level alone,
so **you cannot move this market and slippage is not the binding constraint.**

The real costs are:

1. the bid/ask spread (1-3c, large against any plausible edge),
2. whether a resting limit order fills at all,
3. adverse selection — resting orders fill preferentially when the market has
   moved against you,
4. fees.

Fees, from the Polymarket US schedule::

    fee = theta * contracts * price * (1 - price)
    theta_taker = +0.06        theta_maker = -0.0125   (maker earns a rebate)

At p=0.50 a taker pays 1.5c/contract and a maker earns 0.3c — a 1.8c swing,
comparable to the entire edge being hunted. That is why the executor is
limit-only, and why maker and taker are modelled separately here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

THETA_TAKER = 0.06
THETA_MAKER = -0.0125


def fee_per_contract(price: float, *, is_maker: bool) -> float:
    """Signed fee per contract. Negative means a rebate is earned."""
    theta = THETA_MAKER if is_maker else THETA_TAKER
    return theta * price * (1.0 - price)


def fee_total(price: float, contracts: float, *, is_maker: bool) -> float:
    return fee_per_contract(price, is_maker=is_maker) * contracts


class FillModel(str, Enum):
    """How optimistic to be about getting filled and at what price.

    Reporting all three is the point: if an edge only survives OPTIMISTIC,
    there is no edge.
    """

    OPTIMISTIC = "optimistic"
    REALISTIC = "realistic"
    PESSIMISTIC = "pessimistic"


@dataclass(frozen=True)
class FillAssumptions:
    """Parameters for one fill model."""

    name: FillModel
    #: Probability a resting limit order gets filled at all.
    fill_probability: float
    #: Whether we are the maker (rebate) or taker (fee).
    is_maker: bool
    #: Extra price concession in probability terms, on top of the quoted price.
    #: Represents adverse selection: the fills you get are the ones the market
    #: moved against.
    adverse_selection: float
    description: str


ASSUMPTIONS: dict[FillModel, FillAssumptions] = {
    FillModel.OPTIMISTIC: FillAssumptions(
        name=FillModel.OPTIMISTIC,
        fill_probability=1.0,
        is_maker=True,
        adverse_selection=0.0,
        description="every limit order fills at the quoted price, maker rebate earned",
    ),
    FillModel.REALISTIC: FillAssumptions(
        name=FillModel.REALISTIC,
        fill_probability=0.70,
        is_maker=True,
        adverse_selection=0.005,
        description="70% of resting orders fill; mild adverse selection; maker rebate",
    ),
    FillModel.PESSIMISTIC: FillAssumptions(
        name=FillModel.PESSIMISTIC,
        fill_probability=1.0,
        is_maker=False,
        adverse_selection=0.015,
        description="cross the spread every time: taker fee plus adverse selection",
    ),
}


@dataclass(frozen=True)
class Fill:
    """Result of attempting one bet."""

    filled: bool
    price: float              # effective entry price, after concession
    contracts: float
    fee: float                # signed; negative is a rebate
    is_maker: bool


def simulate_fill(
    *,
    quoted_price: float,
    contracts: float,
    model: FillModel,
    rng_value: float,
) -> Fill:
    """Simulate one fill.

    `rng_value` is passed in (rather than drawn here) so the engine stays
    deterministic and exactly replayable — a seeded sequence lives in the
    caller.
    """
    a = ASSUMPTIONS[model]

    if rng_value > a.fill_probability:
        return Fill(filled=False, price=quoted_price, contracts=0.0, fee=0.0,
                    is_maker=a.is_maker)

    # Adverse selection worsens the effective entry price.
    price = min(max(quoted_price + a.adverse_selection, 1e-4), 1 - 1e-4)
    return Fill(
        filled=True,
        price=price,
        contracts=contracts,
        fee=fee_total(price, contracts, is_maker=a.is_maker),
        is_maker=a.is_maker,
    )


def american_to_price(odds: float) -> float:
    """American odds -> implied probability (price per $1 contract)."""
    if odds < 0:
        return (-odds) / ((-odds) + 100.0)
    return 100.0 / (odds + 100.0)


def pnl_for_contract(price: float, won: bool) -> float:
    """P&L per contract on a binary market, excluding fees.

    Buying at `price` pays $1 on a win, $0 on a loss.
    """
    return (1.0 - price) if won else -price
