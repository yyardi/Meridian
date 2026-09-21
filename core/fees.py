"""The venues' taker fee coefficients, in one place, with their provenance.

    fee = coefficient * p * (1 - p)     per contract, at the price paid

Polymarket US publishes its coefficient on every market object as
``feeCoefficient`` and the recorder stores it as
``market_snapshots.fee_coefficient``. That column is the history: 0.06 on
63,539,087 rows from 2026-07-31 to 2026-09-17 04:00Z, then 0.0695 on every
row from 04:07Z that day on (21,656,635 rows to 2026-09-21, NFL, CFB, WNBA, MLB and table tennis,
winners, spreads and totals). The venue RAISED its fee on 2026-09-17. V9's
0.06, measured on 2026-08-04, was right on its day.

What was wrong was the tree: 0.06 stood in ten places -- the ladder scanner,
the backtest fill model, the gridiron scalp, the quote wallet and six research
runners -- and nothing compared any of them to the field the venue sends, so
for four days every fee was charged 16 % light (about half a cent per pair
at even prices) with every log green. Every constant now imports from here,
scripts/fee_drift.py compares this number to the last day's recorded
coefficients in the nightly verdict, and tests/test_fee_is_one_constant.py
fails on any fee-shaped 0.06 literal. The next change the venue makes is
caught the following morning; the correction is one line.

Not fees, and not here: MAX_TRADEABLE_SPREAD, MAX_LEG_SPREAD, SKEW_EDGE and
ROUND_TRIP_COST are all 0.06 by coincidence.
"""
from __future__ import annotations

#: Polymarket US, taker. ``feeCoefficient`` on the market object.
POLYMARKET_TAKER = 0.0695
#: Polymarket US, maker: zero. No rebate is booked unless a sensitivity arm
#: asks for one explicitly (see core/backtest/fills.py).
POLYMARKET_MAKER = 0.0
#: Kalshi, taker, ``quadratic`` schedule; no maker fee.
KALSHI_TAKER = 0.07


def taker_fee(price: float, coefficient: float = POLYMARKET_TAKER) -> float:
    """Fee per contract at the price actually paid, not at the mid."""
    return coefficient * price * (1.0 - price)
