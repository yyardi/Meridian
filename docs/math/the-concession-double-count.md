# The concession double-counts, and it is the only number that matters

**One constant decides whether this programme is up or catastrophically down,
and it is applied to a metric it does not belong to.** Raised for review, not
changed unilaterally.

## The ladder — one book, every assumption stated

| sport | fills | raw fill | +rebate | +guard | **wallet's view** |
|---|---:|---:|---:|---:|---:|
| cfb | 42,018 | −0.390¢ | −0.107¢ | **+0.157¢** | **−4.543¢** |
| wnba | 17,339 | −0.610¢ | −0.326¢ | **+0.023¢** | **−4.677¢** |

**The 4.70¢ concession is 16× the rebate and 30× the guard. It alone flips the
sign.** Everything else we have argued about this week is noise beside it.

## What it is

C13 (2026-08-07) defines it exactly:

> `concession = E[−dmid | filled] = mean(half-spread) − mean(net capture)`

The **adverse movement of the mid at the moment of fill**, in-game 4.70¢
[4.41, 5.00], pregame 2.11¢ [1.83, 2.39].

## Why charging it against SETTLEMENT is a double-count

The wallet scores each fill by settlement: buy at `p`, contract pays `y`,
money is `y − p`. **That is the complete, realised P&L.** It already contains
whatever the mid did — if the mid fell because the game turned, the settlement
records exactly that.

**The concession then charges us again for the same event.** It is a
mark-to-market penalty applied on top of a realised outcome.

The concession is the correct adjustment for a **markout** metric (mid at
`t+h`), where the adverse move is the thing being measured and is not otherwise
captured. It is not correct against settlement.

## And its provenance is now suspect independently

`E[−dmid | filled]` is conditioned on the fill rule — and that rule fills when
the mid reaches our price, which **forces `dm ≤ −s/2` on every filled path**
(meridian-14). Restated: `capture ≡ E[dm] + s/2`, so
`E[−dm] = s/2 − capture` — **which is the concession formula exactly.**

**The concession is not an independent measurement. It is the capture identity
rearranged**, and capture was retired as an identity rather than a measurement.

## The correct way to model fill optimism

Our simulator is optimistic about *whether* we get filled, not about *what
price* we get. **A maker who posts and is hit receives their posted price** —
that is what a limit order is. So:

> **Fill optimism belongs in the fill PROBABILITY, not in the fill PRICE.**

Charging a price penalty for a fill we either got or did not get is a category
error. The honest correction is fewer fills, not worse fills — which is exactly
what the queue-position work (λ(q)) is for, and why it is the right priority.

## What I am NOT claiming

That we are profitable. Removing the concession leaves **+0.157¢ (CFB)** and
**+0.023¢ (WNBA)**, both with intervals spanning zero, on a fill model whose
selection is unvalidated. **This changes which number is defensible, not
whether we have edge.**

**Review requested before any wallet change.** If the concession is right and
this reasoning is wrong, the wallet's −4.5¢ stands and the guard and rebate are
rounding errors on a dead strategy. That is worth being sure about.
