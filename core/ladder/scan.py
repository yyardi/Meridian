"""Find pairs where the venue's own ladder contradicts itself.

Two knobs and both are deliberate:

`MAX_PLAUSIBLE_EDGE` -- an "arbitrage" above this is a stale deep rung nobody
has updated, not a market. Measured: USC -17.5 quoted at 0.930 while USC -10.5
sat at 0.040, an 88c "edge" on a rung with no size behind it. Including those
inflates the total by roughly 2.5x and every one of them is untradeable.

`fee_rate` -- 0.0695 on Polymarket US, 0.07 on Kalshi, charged at BOTH legs'
traded prices. Netting the fee is what separates 1,107 real violations from the
much larger number of pairs that merely cross the spread.
"""
from __future__ import annotations

from dataclasses import dataclass

#: Above this, a "violation" is a stale rung rather than a tradeable price.
MAX_PLAUSIBLE_EDGE = 0.15

#: Polymarket US taker coefficient in f(p) = rate * p * (1 - p). Kalshi is
#: 0.07; callers pass their own. The value and its provenance live in
#: core/fees.py: 0.0695, the venue's own `feeCoefficient` since it was
#: raised from 0.06 on 2026-09-17; this line was not compared to that field
#: until 2026-09-21 (16 % of the fee, about 0.5c per pair at even prices).
from core.fees import POLYMARKET_TAKER  # noqa: E402

DEFAULT_FEE_RATE = POLYMARKET_TAKER

#: A quoted size above this is not a book, it is a bad reading. `book_levels`
#: carries a 1% tail of implausible NFL quantities: p99 104,552 and a max of
#: 10,729,773, which at $1 a contract would be a $10.7M resting order on a venue
#: whose typical depth is in the hundreds (median 110). Uncapped, ONE such
#: reading -- +2.02c x 978,801 contracts against a median size of 46 -- was 82%
#: of the entire NFL in-play total, turning $5,454 into $24,040. Capping is not
#: conservatism, it is refusing to price a number the substrate cannot support.
#: CFB is unaffected until the cap falls below 1,000, which is how we know the
#: tail is NFL-specific rather than an artifact of the cap itself.
MAX_PLAUSIBLE_SIZE = 10_000.0


def fee(price: float, rate: float = DEFAULT_FEE_RATE) -> float:
    """Taker fee at the price actually paid, not at the mid."""
    return rate * price * (1.0 - price)


def clears_floor(dollars: float, floor_usd: float) -> bool:
    """Whether a pair's dollars (edge x size) reach the floor, on the number
    the operator SEES: dollars to the cent. Every gate -- both executors,
    the ARB tab's `candidate`, the tape's `why_not` -- goes through here, so
    a pair the desk prints as $25.00 cannot also say "under the $25 floor".
    On 2026-09-21 the fee correction moved a fixture pair to $24.996: shown
    as $25.00, refused on the raw value, and the test that says the floor
    "is read off the same number" caught it."""
    return round(dollars, 2) >= floor_usd


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
                max_edge: float = MAX_PLAUSIBLE_EDGE,
                max_size: float = MAX_PLAUSIBLE_SIZE) -> list[Violation]:
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
                                     min(rungs[hi][3], rungs[lo][2], max_size)))
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
