# Trade prints resolve the fill question — 2026-09-05

**We had two classifiers, one too strong and one that could not fail, both
asking a QUOTE record a question about TRADES. The venue publishes the trades.
We already record them. Nobody had joined them.**

## The question

A resting bid at B is filled when a seller hits it. In a tape that does not
contain our order, that seller instead consumes the *real* bid, `best_bid`
falls, and the mid drops onto B. **Our model fires — and the book-geometry
classifier calls it a phantom.** So "the bid fell" has two generators quote data
cannot separate:

- **(i) cancelled** — no trade; our order would have held; the fill is impossible
- **(ii) consumed** — a trade; our order would have been HIT; the fill is REAL

## The instrument we already had

`market_trade_stats` carries **`last_trade_px`, `last_trade_at`, `last_trade_qty`**
— actual prints with their own timestamps, 166,689 usable rows over 6,114
markets.

**It was invisible because of a join trap** (the same one recorded in memory for
this exact table): **196,686 of 383,327 rows have a NULL `market_slug`** but a
valid `snapshot_id`. A slug-only join reported **0 of 1,339** filled markets
covered. Resolving through `snapshot_id` gives **1,130 of 1,339 — 84%.**

## The result — an INDEPENDENT confirmation, not a re-derivation

A fill is **consumed** if a print occurred at or through our price near it:

| window | consumed | P&L | not consumed | P&L |
|---:|---:|---:|---:|---:|
| 30s | 8,832 | **−3.244¢** | 33,170 | +0.389¢ |
| 120s | 13,870 | **−2.424¢** | 28,132 | +0.634¢ |
| 300s | 20,084 | **−2.020¢** | 21,918 | +1.131¢ |

**The sign is invariant.** Fills where a trade genuinely occurred at our price
lose 2–3¢; fills with no such trade "gain", and those are the ones that could
not have happened.

**This reaches the same structure as the book classifier through completely
different data** — prints rather than geometry. That is corroboration of the
mechanism, which is the leg our own convergence rule says is usually missing.

## Where it leaves the number

- **−0.610¢** — phantom blend, includes impossible fills. Too kind. Retired.
- **−3.38¢** — book classifier, selects for the market gapping THROUGH us
  (`ask ≤ B`). Too harsh. Retired.
- **−2.0¢ to −3.2¢** — trade-print measured, tightening as the coincidence
  window tightens. **This is the defensible range.**

The window dependence is honest and expected: a print closer in time to the
fill is more likely to *be* the fill, so the tight window selects the most
certainly-real subset and reads worst.

## What it does not settle

A print at our price proves a willing seller existed; it does **not** prove
*our* order was the one filled — **queue position decides that**, and λ(q)
remains the open work. This bounds the answer; it does not close it.

**And it does not change the sign.** Every window, both classifiers, and both
independent instruments agree: **the fills that could really have happened lose
money.** The concession double-count was real and comes off; the strategy is
still negative underneath it.

*No in-sample result justifies capital. The forward test is the evidence.*
