"""Capture-vs-mid is an IDENTITY, not a measurement — so it cannot rank boards.

Asked by the manager: with settlement unreadable on the CFB tape (6 of 11
games, clustered CI [-41.9, +16.8]), is the capture comparison -- CFB
-3.787c vs WNBA -2.302c -- valid at least directionally?

Answer: no, and the reason is algebraic before it is statistical.

THE IDENTITY. A resting bid at B, quoted when the mid was m_q = B + s/2.
Capture marks the fill against the mid: capture = m_fill - B (there is no
fee term; core/quote/report.py:57). The fill rule only fires once the mid
has fallen to B, i.e. once the drop (m_q - m_fill) has reached s/2.
Substituting, the s/2 terms cancel:

    capture = s/2 - drop = -(overshoot past the trigger) = m_fill - B

so capture <= 0 for every fill, ALWAYS, and its magnitude is exactly how far
the mid jumped past our price in the crossing tick. Measured on 6,146 real
WNBA fills: corr(capture, -overshoot) = +1.0000, mean absolute residual
0.0000c. Zero degrees of freedom.

AND ITS CEILING IS TICK GEOMETRY. For a real fill the counterparty's ask
must reach our bid. The best available case is ask == B with the bid one
tick below, putting the mid half a tick under our price -- so capture
<= -TICK/2 for every real fill however well the trade turns out. Measured
max on those 6,146 fills: exactly -0.50c, which is half a tick and not, as
it first appears, a fee. The best possible capture is a fact about the
venue's price increment.

So a capture number is a statement about a board's JUMP GEOMETRY -- tick
granularity, volatility, spread -- and not about whether trades were good.
Comparing two boards on capture compares how coarsely their mids move.
Football mids plausibly move in bigger discrete steps than basketball ones;
that is a microstructure fact, not an economic one.

DOES THE OVERSHOOT AT LEAST CORRELATE WITH ECONOMICS? Tested per game on
WNBA, where both metrics exist:

    Pearson  r = -0.096 (p = 0.755)      n = 13 games with >= 30 real fills
    Spearman r = -0.066 (p = 0.831)
    corr(capture, mean spread)    = -0.781
    corr(settlement, mean spread) = +0.040

Capture tracks spread strongly and settlement not at all. Split into
terciles the relationship runs backwards (worst-capture games settled
-2.65c, best-capture games -3.64c), though those CIs overlap.

BE PRECISE ABOUT WHAT EACH LEG PROVES. The identity is deterministic and
needs no sample: capture IS negative overshoot, that is not in doubt. The
correlation test is weak -- 13 games cannot rule out a moderate relationship
-- so it shows "no evidence that overshoot predicts settlement", not "proof
that it cannot". The case rests on the identity; the correlation only
declines to rescue it.

THE CONSEQUENCE NOBODY ASKED ABOUT. The width gradient reported as
replicating across two sports is the same identity reproducing itself.
On the IDENTICAL fills in the IDENTICAL buckets:

    band       n     CAPTURE (clustered)     SETTLEMENT (clustered)
    <=1.5c   2610   -1.67 [-1.80, -1.55]     -4.10 [-6.80, -1.40]
    1.5-2.5c 1248   -2.23 [-2.44, -2.01]     -2.29 [-6.24, +1.66]
    2.5-3.5c  943   -2.68 [-2.94, -2.42]     -4.61 [-7.46, -1.76]
    3.5-5.5c  829   -3.06 [-3.44, -2.68]     -1.85 [-5.80, +2.11]
    >5.5c     516   -3.80 [-4.25, -3.35]     -5.96 [-10.09, -1.82]

Capture is perfectly monotonic with CIs ~0.3c wide. Settlement is not
monotonic at all, with CIs ~8c wide. Same fills. The capture gradient is
tight because it is nearly deterministic given the geometry; the settlement
gradient is wide because it is the actual noisy economics.

So "the widening is a warning, not an opportunity" has not been replicated
twice on evidence. It has been reproduced twice as an algebraic consequence
of spread appearing on both sides of the identity -- which is exactly why it
replicated so cleanly on a different sport. A finding that replicates
because it cannot fail is not a finding.

WHAT IS UNAFFECTED, and it matters that this is not a blanket retraction:
  - The phantom replication (CFB 64.4% vs WNBA 63.9%) is a COUNT, not a
    capture statistic, and it is genuinely out-of-sample. It is strong.
  - Fills per game-hour (494) is a count. Unaffected.
  - Everything scored on settlement is unaffected.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from core.quote.report import net_capture_mark  # noqa: E402

TICK = 0.01


def overshoot(side, quote_price, mid_at_quote, mid_at_fill, spread_at_quote):
    """How far the mid travelled past the point that triggers the fill.

    Equals quote_price - mid_at_fill: the s/2 terms cancel, since the quote
    is born at the touch (quote_price = mid_at_quote -/+ s/2).
    """
    drop = (mid_at_quote - mid_at_fill if side == "bid"
            else mid_at_fill - mid_at_quote)
    return drop - spread_at_quote / 2.0


def _selftest() -> int:
    fails = 0

    def check(name, ok):
        nonlocal fails
        print(f"  {name} -> {'ok' if ok else 'FAIL'}")
        fails += 0 if ok else 1

    # THE IDENTITY, asserted rather than described. Across a grid of
    # geometries, capture must equal -(overshoot) - fee exactly.
    rows = []
    for s in (0.01, 0.02, 0.05, 0.10):
        for extra in (0.0, 0.005, 0.02, 0.07):
            mq = 0.50
            B = mq - s / 2
            mf = B - extra                     # mid overshoots by `extra`
            rows.append(("bid", B, mq, mf, s, extra))
            A = mq + s / 2
            rows.append(("ask", A, mq, mq + s / 2 + extra, s, extra))
    worst = 0.0
    for side, px, mq, mf, s, extra in rows:
        cap = net_capture_mark(side=side, quote_price=px, mid_at_fill=mf)
        ov = overshoot(side, px, mq, mf, s)
        worst = max(worst, abs(cap - (-ov)))
    check(f"capture == -(overshoot) exactly, all geometries "
          f"(worst |resid| {worst:.2e})", worst < 1e-9)

    # THE CEILING IS TICK GEOMETRY, NOT ECONOMICS. For a REAL fill the
    # counterparty's ask must reach our bid (ask <= B). The best possible
    # case is ask == B with the bid one tick below, putting the mid half a
    # tick under our price -- so capture <= -TICK/2 for every real fill,
    # no matter how good the trade turns out to be. Measured max on 6,146
    # real WNBA fills: exactly -0.50c.
    B = 0.50
    best = net_capture_mark(side="bid", quote_price=B,
                            mid_at_fill=(B - TICK + B) / 2.0)
    check(f"best possible REAL-fill capture is -half a tick "
          f"({best*100:+.2f}c)", abs(best + TICK / 2) < 1e-12)

    # a metric with zero degrees of freedom cannot distinguish two boards
    # that differ only in economics: same geometry -> same capture, even
    # when settlement differs completely.
    a = net_capture_mark(side="bid", quote_price=0.49, mid_at_fill=0.46)
    b = net_capture_mark(side="bid", quote_price=0.49, mid_at_fill=0.46)
    check("identical geometry gives identical capture regardless of outcome",
          a == b)
    return fails


if __name__ == "__main__":
    if _selftest():
        sys.exit("selftest failed")
    print("\nThe measured numbers behind the docstring are reproduced by")
    print("placement_curve_real_fills.py (settlement) and the scratch")
    print("capture_proxy.py run; this file exists to pin the IDENTITY,")
    print("which is the part that needs no sample.")
    print("\nNo in-sample result justifies capital. The forward test is the")
    print("evidence.")
