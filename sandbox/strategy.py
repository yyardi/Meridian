"""THE ALGORITHM. All of it. ~120 lines, no imports beyond the standard library.

The operator asked: *"is there a couple files of code which are the entire
algorithm? If i cant even find the code where the algo lies its kinda cooked."*

They were right. The repo is 283 files and 68,000 lines; the trading decision is
this. Everything else is recording, storage, dashboards and analysis AROUND
these functions. This file is the strategy, written so it can be read start to
finish, and `sandbox/run.py` scores it against recorded tape.

WHAT WE KNOW, encoded here rather than in a doc nobody opens:

  * We are a MAKER. We post and never cross. Polymarket US pays makers a rebate
    (theta = -0.0125) and charges takers (+0.06). Crossing destroys the trade.
  * We have NO FAIR VALUE. `quote_at_touch` copies the market's own prices.
    That is the central weakness: a maker without a pricing model is a mirror.
    PULSE was tested as the missing opinion and is WORSE than the market mid
    (40.53c vs 39.01c mean error), so it cannot fill the hole.
  * Fills that really happen lose 2.0-3.2c (measured against trade prints).
    Fills our simulator invents "profit" +0.6c. The gap is the whole problem.
  * One-sided fills are the loss mechanism: >=80% one-way loses 10.91c against
    1.68c balanced. `OneSidedGuard` is the only measured mitigation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --- venue constants, from the published schedule -------------------------- #
MAKER_THETA = -0.0125   # we RECEIVE this: rebate = 0.0125 * p * (1-p)
TAKER_THETA = 0.06      # we never pay this; we never cross
TICK = 0.01             # venue price increment


def maker_rebate(price: float, contracts: int = 1) -> float:
    """What the venue pays us for posting. Peaks at p=0.50 (0.31c), a third of
    that at the extremes — so WHERE we quote changes what we earn, and nothing
    in this program has ever conditioned on that."""
    return -MAKER_THETA * contracts * price * (1.0 - price)


# --- the market as we see it ---------------------------------------------- #
@dataclass(frozen=True)
class Book:
    bid: float
    ask: float

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread(self) -> float:
        return self.ask - self.bid


@dataclass(frozen=True)
class Quote:
    bid: float
    ask: float


# --- the decision --------------------------------------------------------- #
def is_quotable(book: Book, *, max_spread: float = 0.06,
                min_price: float = 0.05, max_price: float = 0.95) -> bool:
    """Should we be in this market at all?

    A maker does not quote a 20c spread just because it used to be 3c. The
    band is a risk limit, not an opinion — it says nothing about value.
    """
    return (0 < book.spread <= max_spread
            and min_price <= book.mid <= max_price)


def quote_at_touch(book: Book) -> Quote:
    """★ THIS IS THE STRATEGY. ★  Copy the market's own best prices.

    Read it plainly: we have no view. We post where the market already is and
    hope to earn the spread. Measured, this loses 2-3c per real fill, because
    the people who trade against us choose when to do it.

    Every variant we have tested changes WHEN to quote (patience, lateness,
    width) or by how much to lean when holding inventory. **Nobody has ever
    varied the one lever a maker actually has: HOW FAR FROM THE TOUCH TO
    QUOTE.** That is `quote_away` below, and it is untested.
    """
    return Quote(bid=book.bid, ask=book.ask)


def quote_away(book: Book, *, ticks: int = 1) -> Quote:
    """UNTESTED. Post `ticks` behind the touch on both sides.

    Glosten-Milgrom says a maker with no informational edge should widen until
    the spread compensates for adverse selection. We have never tried it. Each
    fill is worth more and arrives less often, and the rebate is unchanged per
    fill — so the rebate-per-unit-risk rises. This is the search we have not run.
    """
    return Quote(bid=round(book.bid - ticks * TICK, 4),
                 ask=round(book.ask + ticks * TICK, 4))


# --- the only measured mitigation ----------------------------------------- #
@dataclass
class OneSidedGuard:
    """Stop quoting a side once fills go one-way in that market.

    A maker should fill BOTH sides. Sustained one-sidedness means the market is
    moving through us — measured -10.91c at >=80% one-way against -1.68c
    balanced, monotone, on real fills. Nearly all the damage sits in 10% of
    volume, and this is the cheapest thing that removes it.
    """
    threshold: float = 0.65
    min_fills: int = 4
    _bids: dict[str, int] = field(default_factory=dict)
    _asks: dict[str, int] = field(default_factory=dict)

    def record(self, market: str, side: str) -> None:
        d = self._bids if side == "bid" else self._asks
        d[market] = d.get(market, 0) + 1

    def allows(self, market: str, side: str) -> bool:
        b, a = self._bids.get(market, 0), self._asks.get(market, 0)
        n = a + b
        if n < self.min_fills:
            return True
        same = b if side == "bid" else a
        return (same / n) < self.threshold


# --- scoring, so a number always means the same thing ---------------------- #
def settlement_pnl(*, side: str, price: float, settlement: int) -> float:
    """Realised money per contract. Buy at p, contract pays 0 or 1.

    This is COMPLETE. Do not also subtract a 'concession' — that is a
    mark-to-market penalty and charging it against a realised outcome
    double-counts (it equals the capture identity rearranged).
    """
    return (settlement - price) if side == "bid" else (price - settlement)


def total_pnl(*, side: str, price: float, settlement: int,
              contracts: int = 1) -> float:
    """What actually lands in the account: the trade plus the rebate."""
    return (settlement_pnl(side=side, price=price, settlement=settlement)
            * contracts) + maker_rebate(price, contracts)
