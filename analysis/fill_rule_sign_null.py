"""The fill rule decides the sign — a closed form — 2026-09-04

    .venv/bin/python analysis/fill_rule_sign_null.py [--exports DIR]

D's geometry is correct and I reproduce it. The question is what it is
correct ABOUT. Every geometry-only null built today held the fill rule
fixed and varied something else; this one varies the fill rule itself.

★ THE CLOSED FORM. Let B be our resting bid and m_t the mid. Fair
pricing means E[s | F_t] = m_t.

  RULE A (the simulator): fill at the first t with m_t <= B.
      E[P&L] = E[m_tau] - B  <=  0     by the definition of tau.
      Non-positive on every path. It cannot be positive.

  RULE B (reality): a resting bid is filled when a SELL ORDER arrives
  that reaches price B. Nothing else fills it.
      E[P&L] = E[m_tau] - B - lambda
      where m_tau >= B whenever our quote is not marketable, and lambda
      is the expected adverse move conditional on being hit.
      = (half-spread revenue) - (adverse selection cost).

**Under the same fair market the two rules have opposite structural
signs.** Rule B is the market-making business: earn the spread, pay
adverse selection, and the whole question is which is larger. **Rule A
deletes the revenue term by construction** and retains only the cost,
so it can only ever return a negative number. A simulator built on
Rule A does not represent market making; it represents "buy when the
price falls to you", which is a different strategy with a different
sign.

★ THE CORRECTION THAT MATTERS FOR THE REMEDY. The profitable case is
not misclassified as a phantom. **It is absent from the fills table
entirely**, because the trigger that would have to fire never fires:

    bid fills with mid_at_fill >  quote_price :      0 of 19,254
    ask fills with mid_at_fill <  quote_price :      0 of 19,211
    capture > 0, either population             :      0 of 38,465

Phantoms are a different animal: for a phantom bid, our price ends up
ABOVE the recorded best bid (100%) with the ask unmoved (median 0.0c)
— the BID SIDE fell away beneath us. Real fills are the ones where the
ASK came down through us (median -2.0c). Both are booked only when the
mid reached our price, so **both carry E[P&L | fair] <= 0**: phantom
mean capture -1.872c, real -3.154c, maximum +0.000c across the whole
table.

So no re-classification of these fills can recover the profitable case.
Only trade data, or a different fill rule, can.

★ WHY THE CLASSIFIER'S PREMISE LEAKS. `real <=> ask <= B` encodes
"if the best ask is above B, no seller wanted to sell at B." That is
true of PASSIVE sellers — resting offers — and false of AGGRESSIVE
ones, who cross the spread by definition. A market sell hits the best
bid wherever the ask happens to sit. The criterion therefore tests
whether the BOOK crossed us, not whether a TRADE would have hit us,
and those are different events.

★ THE AMBIGUITY ONLY TRADES CAN SETTLE, stated as a test rather than an
opinion. In the phantom-bid population the queue at our price fell away
beneath us. Two causes, indistinguishable in book data:

  (i)  CONSUMED — sellers traded through that level. Trades occurred at
       or below B, so a real order resting there would very likely have
       been filled, and filled while the ask was still high: the
       profitable case.
  (ii) CANCELLED — the other bids were pulled, no trade occurred. A
       real order would still be resting, unfilled: a true phantom.

`market_trade_stats.shares_traded` differenced across polls gives
interval volume. **Condition on phantom bid fills with the ask
approximately unmoved, and ask whether volume incremented in the
interval.** Common -> (i) is real and the program's central number is
measured on the losing half of the distribution. Near-absent -> (ii)
holds and D's geometry stands as the answer.

★ THE DECOMPOSITION, EXACT TO MACHINE PRECISION. Because we joined the
touch on 100% of fills, B = m_quote - s/2, and therefore

    capture  ==  E[dm]  +  s/2            (max error 1.11e-16 over 38,465)

where dm is the signed mid move from quote to fill. So Rule A's
expectation is NOT missing the maker's revenue — it contains it, and
then buries it:

  REAL fills (n=13,651, G=24, game-clustered)
    RULE A   E[P&L|fair] = capture      -3.154c [-3.742, -2.567]
       revenue term            + s/2    +1.256c [+1.175, +1.338]
       forced move             + E[dm]  -4.411c [-4.982, -3.839]
    RULE B   E[P&L|fair] = s/2          +1.256c   (uninformed arrival)
    SWING between rules on IDENTICAL fills        +4.411c

**The swing is larger than the headline effect it would replace.**

★ WHY E[dm] IS ZERO UNDER RULE B AND CANNOT BE UNDER RULE A. Rule A's
trigger is defined by the price reaching us, so `dm <= -s/2` holds on
every filled path by construction — the mid MUST have fallen to B. It
is not an estimate; it is the trigger written as a number. Rule B's
trigger is the arrival of a sell order. If arrival is independent of
the price path — the definition of uninformed flow — then tau is a
stopping time independent of the martingale and optional stopping gives
E[m_tau] = m_0, hence **E[dm] = 0** and E[P&L] = +s/2.

So the sharpest statement of the whole question:

> **Under Rule B, E[dm] IS the adverse selection — the thing worth
> measuring. Under Rule A, E[dm] is the trigger — a selection we
> imposed on ourselves. They are the same arithmetic and different
> quantities, and only one of them is about the market.**

Rule B with informed flow gives `s/2 - lambda`, and whether that is
positive is the market-making question. **Our data cannot address it**,
because every fill we hold was booked by Rule A.

★ WHAT THE QUEUE COUNTER DOES AND DOES NOT SETTLE. Being first in
queue 1.2% of the time, median 28 contracts behind, bounds **how often**
Rule B fills, not **what sign** they carry. It is evidence about the
VIABILITY of touch-joining — a strategy that rarely fills cannot make
$100/month whatever its edge per fill — and no evidence at all that
-3.4c estimates its P&L. Both questions matter and they are different:
one asks whether the measured number describes the strategy, the other
asks whether the strategy could clear the bar. Conflating them would
answer neither.

There is a second queue effect that cuts deeper than rarity, and it
runs AGAINST the strategy: to reach a 1-contract order sitting behind
28, a market sell must be larger than 28 contracts, and larger sells
are more likely to be informed. **Queue depth therefore raises lambda
as well as lowering the fill rate** — Rule B's edge is `s/2 -
lambda(q)` with lambda increasing in q. That makes the real strategy
harder than the naive `s/2` suggests, without making Rule A a valid
estimator of it.

★ AND THE DISCRIMINATING TEST IS NOT AVAILABLE — the question is
UNDETERMINED, not underpowered. The consumed-vs-cancelled ambiguity in
the phantom population has no book-only resolution:

  * an uninformed market sell consumes the top bid, nobody's fair value
    changes, so the ask stays — the PROFITABLE case;
  * a maker pulls the bid, no trade occurs, the ask stays because only
    one side was pulled — a TRUE phantom.

Both remove size at our price and leave the ask alone. Depth would
separate them, but `book_levels` sits a median 6.8s behind a 200ms
event. Reversion does not: replenishment after a sell and a requote
after a pull revert on the same timescale, and phantom drift measures
~0.5x excursion, which fits either.

A cross-rung co-movement test was proposed and its SIGN is ambiguous
rather than merely weak: an automated maker quotes the whole ladder and
pulls it at once (co-movement from CANCELLATION), while an uninformed
seller wants one strike (isolation from CONSUMPTION) — the opposite of
the intuitive reading. Which way it runs depends on who supplies bid
liquidity, which is unmeasured. A test whose sign flips on an
unmeasured fact cannot discriminate.

**What would answer it, going forward:** Kalshi publishes per-contract
`volume` and `open_interest`, real trade counters for the same GAMES.
They cannot be joined historically because the Kalshi recorder polls
pregame only — its window closes at tip — so no in-game Kalshi data
exists for any game in this study. The CFB recorder polls through the
game (its window runs to `venue_occurrence_time` = kickoff + 3h), so
once that lands, differenced volume gives independent evidence of
whether selling actually occurred in a game-window. Population-level,
not per-fill, and it needs no new plumbing.

★ THE LIMIT THAT OUTRANKS EVERYTHING HERE. **Not one fill in this study
has ever been checked against a real trade.** `market_trade_stats` is
NFL-only, with zero overlap with `shadow_quote_fills` at any time, so
no market we have ever quoted has trade data. This closed form says
what each rule implies UNDER FAIR PRICING. It cannot say which rule the
venue actually ran, and nothing in the recorded book can. The sign
question about the SIMULATOR is settled; the sign question about
TOUCH-JOINING is not, and is not currently answerable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

EXPORT_NAME = "quote_fills_classified_20260904T142200Z.csv"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exports", type=Path, default=REPO / "backups/exports")
    d = pd.read_csv(ap.parse_args().exports / EXPORT_NAME).rename(
        columns={"pop": "population"})
    d["mid_f"] = (d.bb + d.ba) / 2
    d["ask_q"] = d.m_q + d.s_q / 2
    d["bid_q"] = d.m_q - d.s_q / 2
    d["capture"] = np.where(d.side == "bid", d.mid_f - d.qp, d.qp - d.mid_f)

    print("# The fill rule decides the sign\n")
    print("## 1. The profitable case is ABSENT, not misclassified\n")
    b = d[d.side == "bid"]
    a = d[d.side == "ask"]
    print(f"* bid fills with mid_at_fill > quote: **{(b.mid_f > b.qp+1e-9).sum()}** "
          f"of {len(b):,}")
    print(f"* ask fills with mid_at_fill < quote: **{(a.mid_f < a.qp-1e-9).sum()}** "
          f"of {len(a):,}")
    print(f"* capture > 0 anywhere: **{(d.capture > 1e-9).sum()}** of "
          f"{len(d):,}\n")
    print("| population | n | mean capture = E[P&L\\|fair] | max |")
    print("|---|---:|---:|---:|")
    for p, g in d.groupby("population"):
        print(f"| {p} | {len(g):,} | {g.capture.mean()*100:+.3f}c | "
              f"{g.capture.max()*100:+.3f}c |")

    print("\n## 2. The two populations are different events, both trigger-bound\n")
    print("| population | side | joined touch at quote | qp > best bid at fill "
          "| qp >= ask at fill | median ask move |")
    print("|---|---|---:|---:|---:|---:|")
    for p in ("phantom", "real"):
        g = d[(d.population == p) & (d.side == "bid")]
        print(f"| {p} | bid | {np.isclose(g.qp, g.bid_q).mean()*100:.0f}% | "
              f"{(g.qp > g.bb+1e-9).mean()*100:.0f}% | "
              f"{(g.qp >= g.ba-1e-9).mean()*100:.0f}% | "
              f"{(g.ba-g.ask_q).median()*100:+.1f}c |")
    print("\nPhantom: the BID side fell away beneath a quote that joined the "
          "touch, ask unmoved. Real: the ASK came down through us. Neither is "
          "the profitable case, which requires mid ABOVE our bid and is "
          "unreachable by a trigger that fires on mid reaching our bid.\n")
    print("No in-sample result justifies capital. The forward test is the "
          "evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
