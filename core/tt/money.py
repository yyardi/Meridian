"""The MONEY arm: net P&L per contract of betting the rating's disagreements.

Registered beside the signal arm, never instead of it, and reported as a
SEPARATE verdict. The primary test asks "do ratings carry information beyond
price" and its PASS is read — every time — as "this makes money". It is not
the same question. A model with a real 0.5pp edge passes the coefficient test
and loses to the cost bar, which is the wrong-null error in
`check-a-decision-rule-against-its-achievable-image`: excludes-zero when the
null is -cost rather than zero.

THE NULL HERE IS ZERO NET, and that is not a softening. The cost is charged
inside every bet's P&L, so subtracting it again from the mean would
double-charge it (`anchor-is-bookkeeping`, where exactly that flipped PULSE
+$23.65 to -$111.90).

Entry is the LAST PREGAME QUOTE, taken at the executable side — buy YES at the
ask, buy NO at one minus the bid. The registered wording sizes the entry
filter as "disagrees with the price by more than the half-spread plus fee",
written against a mid; entering at the executable price already pays the
half-spread, so the filter here is positive expected value at the price
actually paid and the half-spread term would be the same charge twice.

WHY THE LAST QUOTE AND NOT THE DAY'S BOOK (measured 09-15, 2026, prod
read-only, `market_slug LIKE 'aec-setka%'`, September partitions):

| population                           |      n | median spread | mean fee at ask |
|--------------------------------------|--------|---------------|-----------------|
| all pregame quotes, mid .2-.8        | 42,485 |        17.00c |          1.266c |
| LAST pregame quote, mid .2-.8        |    724 |         2.00c |          1.388c |

The book tightens into the start: the median last quote is 8.2 minutes before
it and most are one cent wide. Both rows are correct computations of different
populations, and the 17c row describes listings nobody trades.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from core.fees import POLYMARKET_TAKER, taker_fee

# --- there is no cost-bar constant in this file, and that is the point ------ #
#
# It has been measured four times and moved every time, because it is a
# property of a WINDOW and a STATISTIC, not of the venue:
#
#   window        n      med half   mean half   MED total   MEAN total
#   09-13..09-15   724     1.000c     2.339c     2.260c      3.728c   pre-raise
#   09-18..09-21  1339     0.500c     4.499c     2.238c      6.065c   post-raise
#
# Between those two the half-spread's median HALVED while its mean nearly
# DOUBLED: the board grew from 724 markets to 1,339 and the right tail of
# wide-quoted matches grew with it. The venue's taker coefficient changed
# underneath as well -- the venue RAISED its coefficient on 2026-09-17 04:07Z
# (core/fees.py owns both values and the row counts; I confirmed the new one on
# 12,713 table-tennis rows with zero variation). Two independent reasons for the
# same number to move, in three days.
#
# Two constants published from those measurements are already retracted: 2.22c
# (a median of a sum with a "fee" back-derived out of it -- medians do not add)
# and 2.39c (a median half-spread plus a MEAN fee, which is not a statistic of
# anything). A fifth point estimate would keep the pattern going, so this file
# carries none: `required_n` takes `resolution` with NO DEFAULT, and the runner
# passes the cost the arm ACTUALLY PAID on the bets it placed
# (`MoneyResult.cost_median` / `cost_mean`). That number cannot go stale, it is
# measured on the same rows as the P&L it gates, and it answers the only
# question the gate is for: can this sample resolve an effect the size of our
# own costs.
#
# Per-bet fees are never a constant either: every bet is charged
# the venue's coefficient at its own entry price, so a change to it reaches this
# module through the one place that defines it.

#: Per-contract standard deviation of the P&L, which is the binary outcome's
#: and therefore irreducible. Measured, not assumed: the 357 settled TT matches
#: in docs/math/tabletennis-player-identity.md give a per-match SE of 0.026,
#: so sd = 0.026*sqrt(357) = 0.491; sqrt(p(1-p)) at the observed mean price
#: 0.5226 is 0.4995. Two routes, one decimal place apart.
#:
#: Its own input, that 0.026, is published to two significant figures, so
#: `required_n` is good to three at most: 0.49 vs 0.491 vs 0.4913 moves the
#: answer by 3 and then by 1 match. Quote the floor as ~1,810, never as 1,814,
#: and do not chase the last digit of a number whose input is rounded.
PNL_SD = 0.491

Z95 = 1.959964
Z80 = 0.8416212                            # one-sided 80% power


def fee(price: float, coefficient: float | None = None) -> float:
    """The venue's taker fee at `price`, from the one place that defines it.

    `coefficient` is the venue's `feeCoefficient` AS RECORDED ON THE ROW the bet
    was priced from. It matters because the coefficient is not a constant of the
    venue, it is a constant of a PERIOD: the venue RAISED it on 2026-09-17 at
    04:07Z (core/fees.py has both values and the row counts). Every settled
    table-tennis match that exists today was played before that instant -- the
    357 measured on 09-15 are all pre-change -- so charging today's coefficient
    to them overstates their cost by 16%.

    The direction is conservative for a go/no-go (it makes the arm look worse
    than it was) and wrong all the same: a point-in-time measurement charged at
    today's prices is not a measurement of what happened. The substrate already
    carries the answer per row, so the fix is to read it rather than to hardcode
    a boundary date that will need editing the next time the venue moves.

    Omitted, it falls back to the current coefficient, which is right only for
    bets priced now.
    """
    return taker_fee(price, POLYMARKET_TAKER if coefficient is None
                     else coefficient)


@dataclass(frozen=True)
class Bet:
    slug: str
    side: str                              # "YES" or "NO"
    entry: float                           # the price actually paid
    pnl: float                             # net per contract, fee charged
    cost: float                            # half-spread paid + fee paid


def bet(slug: str, elo_p: float, bid: float, ask: float, y: int,
        coefficient: float | None = None) -> Bet | None:
    """One bet, or None when neither side has positive EV at its own price.

    `elo_p` is P(YES). Buying YES pays `ask`; buying NO pays `1 - bid`. Both
    legs charge the fee at the price paid, so a bet only qualifies when the
    model's probability clears the executable price AND its fee.
    """
    if not (0.0 <= bid <= ask <= 1.0):
        return None
    half = (ask - bid) / 2.0
    f_yes = fee(ask, coefficient)
    if elo_p > ask + f_yes:
        return Bet(slug, "YES", ask, y - ask - f_yes, half + f_yes)
    entry_no = 1.0 - bid
    f_no = fee(entry_no, coefficient)
    if (1.0 - elo_p) > entry_no + f_no:
        return Bet(slug, "NO", entry_no, (1 - y) - entry_no - f_no, half + f_no)
    return None


def _two_way_se(values: list[float], players_a: list[str], players_b: list[str]
                ) -> float:
    """Cameron-Gelbach-Miller SE of the MEAN, clustered on both players.

    Game-clustering is a no-op here and saying so is the point: this arm places
    at most one bet per match, so a "game-clustered" interval is the iid one
    wearing a label (`estimator-not-named-in-the-label`). Players recur across
    matches, so the dyad is the dependence that exists.
    """
    n = len(values)
    if n < 2:
        return float("nan")
    mean = sum(values) / n
    e = [v - mean for v in values]

    def v_of(keys) -> float:
        by: dict = {}
        for i, k in enumerate(keys):
            by.setdefault(k, 0.0)
            by[k] += e[i]
        return sum(s * s for s in by.values()) / (n * n)

    pairs = [tuple(sorted((a, b))) for a, b in zip(players_a, players_b)]
    v = v_of(players_a) + v_of(players_b) - v_of(pairs)
    return math.sqrt(v) if v > 0 else float("nan")


def required_n(*, resolution: float, sd: float = PNL_SD,
               z: float = Z95) -> int:
    """Matches needed for the 95% interval to be NARROWER than `resolution`.

    `resolution` has NO DEFAULT on purpose. n = (z*sd/X)^2 is a choice of
    target wearing the clothes of a measurement: across the bar's own range it
    reads 1,813 at the median total and 666 at the mean, a factor of 2.7 from
    one unstated word. A bare match count is the shape that survives review, so
    the caller names X or gets a TypeError.

    Ignores clustering, so every value is a LOWER bound: players recur and
    n_eff < n (`dyadic-power-saturates`).
    """
    return math.ceil((z * sd / resolution) ** 2)


def mde(n: int, *, sd: float = PNL_SD) -> float:
    """Smallest net edge this n could detect at 80% power, two-sided 5%."""
    return (Z95 + Z80) * sd / math.sqrt(n) if n > 0 else float("inf")


@dataclass(frozen=True)
class MoneyResult:
    n: int
    mean: float
    se_iid: float
    se_player: float
    lo: float
    hi: float
    mde: float
    cost_mean: float               #: REALISED cost of the matches actually bet
    cost_median: float

    @property
    def half_width(self) -> float:
        return (self.hi - self.lo) / 2.0

    def required(self, resolution: float) -> int:
        """Matches needed to resolve `resolution`. Name it; there is no default.

        `cost_mean` is the right argument once the arm has run: it is what this
        selection actually paid, rather than either end of a population range
        it may not sit at.
        """
        return required_n(resolution=resolution)


def summarise(bets: list[Bet], players_a: list[str], players_b: list[str]
              ) -> MoneyResult:
    """Mean net per contract with the two-way player-clustered interval.

    The interval reported is the PLAYER-clustered one, because it is the wider
    and honest one; the iid SE travels beside it rather than in place of it.

    `cost_mean` is a FIRST-CLASS output, not a footnote. The population bar
    spans 2.260c to 3.728c because of a long tail of wide-quoted matches, and
    which end this arm pays is decided by what the model chooses to bet: if it
    preferentially bets wide quotes it pays the tail and even 3.728c is
    optimistic. That is unknowable until the arm runs, so it is measured on the
    bets placed rather than assumed from the population.
    """
    n = len(bets)
    vals = [b.pnl for b in bets]
    nan = float("nan")
    if n == 0:
        return MoneyResult(0, nan, nan, nan, nan, nan, mde(0), nan, nan)
    mean = sum(vals) / n
    var = sum((v - mean) ** 2 for v in vals) / (n - 1) if n > 1 else nan
    se_iid = nan if math.isnan(var) else math.sqrt(var / n)
    se_p = _two_way_se(vals, players_a, players_b)
    se = se_iid if math.isnan(se_p) else se_p
    costs = sorted(b.cost for b in bets)
    return MoneyResult(n, mean, se_iid, se_p,
                       mean - Z95 * se, mean + Z95 * se, mde(n),
                       sum(costs) / n, costs[n // 2] if n % 2 else
                       (costs[n // 2 - 1] + costs[n // 2]) / 2.0)
