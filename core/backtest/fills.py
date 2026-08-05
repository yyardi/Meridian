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
    theta_taker = +0.06   (venue-published; measured on 874,267 rows — V9)
    theta_maker = 0       (default; see below)

At p=0.50 a taker pays 1.5c/contract, comparable to the entire edge being
hunted. That is why the executor is limit-only, and why maker and taker are
modelled separately here.

The maker rebate is a sensitivity arm, not a default
----------------------------------------------------
The venue advertises a maker rebate of *25% of the matched taker fee* — a
share of fees collected on the other side, not a guaranteed per-contract
credit. It has **never been observed in this account**, and the old constant
(-0.0125) reconciles neither with the measured theta_taker = 0.06 nor with any
recorded source (findings C7/V9). Booking it as certain was worth roughly a
full percentage point of fictional ROI. The default is therefore zero;
``assume_rebate=True`` turns the arm on explicitly, and stays off until a
rebate shows up on a statement.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

THETA_TAKER = 0.06
#: Default maker coefficient: zero. No rebate is booked unless asked for.
THETA_MAKER = 0.0
#: The unverified rebate coefficient, kept only for the explicit sensitivity
#: arm. Do not promote back to the default without a statement showing it.
THETA_MAKER_REBATE = -0.0125


def fee_per_contract(price: float, *, is_maker: bool, assume_rebate: bool = False) -> float:
    """Signed fee per contract. Negative means a rebate is earned.

    ``assume_rebate`` books the unverified maker rebate (sensitivity arm only).
    """
    if is_maker:
        theta = THETA_MAKER_REBATE if assume_rebate else THETA_MAKER
    else:
        theta = THETA_TAKER
    return theta * price * (1.0 - price)


def fee_total(price: float, contracts: float, *, is_maker: bool,
              assume_rebate: bool = False) -> float:
    return fee_per_contract(price, is_maker=is_maker, assume_rebate=assume_rebate) * contracts


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
        description="every limit order fills at the quoted price; maker fee zero",
    ),
    FillModel.REALISTIC: FillAssumptions(
        name=FillModel.REALISTIC,
        fill_probability=0.70,
        is_maker=True,
        adverse_selection=0.005,
        description="70% of resting orders fill; mild adverse selection; maker fee zero",
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
    assume_rebate: bool = False,
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
        fee=fee_total(price, contracts, is_maker=a.is_maker, assume_rebate=assume_rebate),
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
