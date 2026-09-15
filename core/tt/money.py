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

from core.backtest.fills import fee_per_contract

#: Half the median spread of the LAST pregame quote (2.00c), i.e. what crossing
#: costs on the population this arm actually enters. NOT the 8.5c that pooling
#: all pregame quotes implies.
HALF_SPREAD = 0.0100

#: Mean 0.06*p*(1-p) at the ask over that same 724-market population. Every
#: statistic of it on that population is 1.39-1.46c (mean/median x mid/ask,
#: harness doc §7); STATUS §0bc's 1.22c is not reproducible there, and the bar
#: it published is 0.17c low. That 0.17c is the whole distance between
#: "marginal" and "negative" for the programme's last live path.
MEAN_FEE = 0.01388

#: The sizing constant for power only. No bet is ever charged this: each pays
#: `fee_per_contract` at its own entry price.
COST_BAR = HALF_SPREAD + MEAN_FEE          # 0.0239

#: Per-contract standard deviation of the P&L, which is the binary outcome's
#: and therefore irreducible. Measured, not assumed: the 357 settled TT matches
#: in docs/math/tabletennis-player-identity.md give a per-match SE of 0.026,
#: so sd = 0.026*sqrt(357) = 0.491; sqrt(p(1-p)) at the observed mean price
#: 0.5226 is 0.4995. Two routes, one decimal place apart.
PNL_SD = 0.49

Z95 = 1.959964
Z80 = 0.8416212                            # one-sided 80% power


def fee(price: float) -> float:
    """The venue's taker fee at `price`, from the one place that defines it."""
    return fee_per_contract(price, is_maker=False)


@dataclass(frozen=True)
class Bet:
    slug: str
    side: str                              # "YES" or "NO"
    entry: float                           # the price actually paid
    pnl: float                             # net per contract, fee charged


def bet(slug: str, elo_p: float, bid: float, ask: float, y: int) -> Bet | None:
    """One bet, or None when neither side has positive EV at its own price.

    `elo_p` is P(YES). Buying YES pays `ask`; buying NO pays `1 - bid`. Both
    legs charge the fee at the price paid, so a bet only qualifies when the
    model's probability clears the executable price AND its fee.
    """
    if not (0.0 <= bid <= ask <= 1.0):
        return None
    if elo_p > ask + fee(ask):
        return Bet(slug, "YES", ask, y - ask - fee(ask))
    entry_no = 1.0 - bid
    if (1.0 - elo_p) > entry_no + fee(entry_no):
        return Bet(slug, "NO", entry_no, (1 - y) - entry_no - fee(entry_no))
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


def required_n(*, resolution: float = COST_BAR, sd: float = PNL_SD,
               z: float = Z95) -> int:
    """Matches needed for the 95% interval to be NARROWER than `resolution`.

    Below this the arm cannot tell "loses the bar" from "makes the bar", which
    is the only thing anyone will read it for. Ignores clustering, so it is a
    LOWER bound: players recur, n_eff < n (`dyadic-power-saturates`).
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
    required: int
    mde: float

    @property
    def half_width(self) -> float:
        return (self.hi - self.lo) / 2.0


def summarise(bets: list[Bet], players_a: list[str], players_b: list[str]
              ) -> MoneyResult:
    """Mean net per contract with the two-way player-clustered interval.

    The interval reported is the PLAYER-clustered one, because it is the wider
    and honest one; the iid SE travels beside it rather than in place of it.
    """
    n = len(bets)
    vals = [b.pnl for b in bets]
    if n == 0:
        return MoneyResult(0, float("nan"), float("nan"), float("nan"),
                           float("nan"), float("nan"), required_n(), mde(0))
    mean = sum(vals) / n
    var = sum((v - mean) ** 2 for v in vals) / (n - 1) if n > 1 else float("nan")
    se_iid = math.sqrt(var / n) if var == var else float("nan")
    se_p = _two_way_se(vals, players_a, players_b)
    se = se_p if se_p == se_p else se_iid
    return MoneyResult(n, mean, se_iid, se_p,
                       mean - Z95 * se, mean + Z95 * se,
                       required_n(), mde(n))
