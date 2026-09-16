"""Find pairs where the venue's own ladder contradicts itself.

Two knobs and both are deliberate:

`MAX_PLAUSIBLE_EDGE` -- an "arbitrage" above this is a stale deep rung nobody
has updated, not a market. Measured: USC -17.5 quoted at 0.930 while USC -10.5
sat at 0.040, an 88c "edge" on a rung with no size behind it. Including those
inflates the total by roughly 2.5x and every one of them is untradeable.

`fee_rate` -- 0.06 on Polymarket US, 0.07 on Kalshi, charged at BOTH legs'
traded prices. Netting the fee is what separates 1,107 real violations from the
much larger number of pairs that merely cross the spread.
"""
from __future__ import annotations

from dataclasses import dataclass

#: Above this, a "violation" is a stale rung rather than a tradeable price.
MAX_PLAUSIBLE_EDGE = 0.15

#: Polymarket US taker. Kalshi is 0.07; callers pass their own.
DEFAULT_FEE_RATE = 0.06


def fee(price: float, rate: float = DEFAULT_FEE_RATE) -> float:
    """Taker fee at the price actually paid, not at the mid."""
    return rate * price * (1.0 - price)


@dataclass(frozen=True)
class Violation:
    """One pair that cannot both be right. `size` is the MIN of the two legs:
    an arbitrage is only as large as its smaller side, and on Polymarket that
    side is usually zero even where the wider book shows depth."""

    game: str
    low_line: float
    high_line: float
    buy_price: float
    sell_price: float
    edge: float
    size: float

    @property
    def dollars(self) -> float:
        return self.edge * self.size


def scan_ladder(game: str, rungs: dict[float, tuple[float, float, float, float]],
                *, fee_rate: float = DEFAULT_FEE_RATE,
                max_edge: float = MAX_PLAUSIBLE_EDGE) -> list[Violation]:
    """`rungs` maps line -> (bid, ask, bid_size, ask_size), all from ONE
    snapshot so the legs are simultaneous. A ladder assembled across timestamps
    is not an arbitrage, it is two prices that never coexisted.

    Buy the HIGHER line (easier to cover, so it must be dearer) at its ask and
    sell the LOWER line at its bid.
    """
    out: list[Violation] = []
    lines = sorted(rungs)
    for i, lo in enumerate(lines):
        for hi in lines[i + 1:]:
            buy = rungs[hi][1]
            sell = rungs[lo][0]
            edge = sell - buy - fee(buy, fee_rate) - fee(sell, fee_rate)
            if 0.0 < edge <= max_edge:
                out.append(Violation(game, lo, hi, buy, sell, edge,
                                     min(rungs[hi][3], rungs[lo][2])))
    return out


def best_per_game(violations: list[Violation]) -> dict[str, float]:
    """The defensible total: the single best trade per game, NOT the sum over
    pairs. One mispriced rung generates a violation against every other rung it
    pairs with -- in `uk-txam` a single rung produced six -- and they share a
    leg, so they compete for the same depth. Summing pairs overstated the CFB
    figure by 2.5x ($1,024.95 against $413.90)."""
    best: dict[str, float] = {}
    for v in violations:
        if v.dollars > best.get(v.game, 0.0):
            best[v.game] = v.dollars
    return best
