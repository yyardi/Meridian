# The maker rebate we were never counting — 2026-09-04

**Polymarket US PAYS makers. We modelled a fee of zero and a rebate of zero,
and the rebate is roughly the size of our whole loss.**

Source: the venue's published schedule (docs.polymarket.us/fees, effective
2026-07-01), not an estimate and not inferred from our own fills.

| role | Θ | formula | at p=0.50 |
|---|---:|---|---:|
| taker | **+0.06** | Θ·C·p·(1−p) | pays $1.50 / 100 |
| **maker** | **−0.0125** | Θ·C·p·(1−p) | **receives $0.31 / 100** |

**Maker rebate is applied at the point of trade.** Our engine posts and never
crosses — by construction, every one of our fills is a maker fill.

## The venue question, settled

Kalshi's NCAAF series are all **`quadratic_with_maker_fees`** (read from
`/series`, multiplier 1): **0.07·p·(1−p) ≈ 1.75¢ per contract CHARGED to the
maker** at mid-book.

> **Polymarket US pays a maker 0.31¢. Kalshi charges one 1.75¢. A 2.06¢ swing
> per contract, against a strategy whose entire loss is under 0.4¢.**

Kalshi's 1¢ median spread is not an advantage: half-spread 0.5¢ against a 1.75¢
maker fee means **−1.25¢ before adverse selection**. Market making there is
structurally impossible at those spreads. **Switching venues would be the most
expensive decision available to us.**

## What it does to our measured results

Rebate computed per fill as `0.0125·p·(1−p)`, on real settled fills:

| sport | arm | fills | P&L | rebate | **true** |
|---|---|---:|---:|---:|---:|
| **wnba** | guarded | 16,672 | −0.262¢ | +0.284¢ | **+0.023¢** |
| cfb | guarded | 18,035 | −0.347¢ | +0.285¢ | **−0.062¢** |
| cfb | excluded by guard | 3,091 | −1.820¢ | +0.279¢ | −1.541¢ |
| wnba | excluded by guard | 667 | −9.318¢ | +0.266¢ | −9.052¢ |

**Guarded book, both sports, game-clustered over 24 games: +0.061¢,
CI [−0.762, +0.883].**

**The point estimate is POSITIVE for the first time in this programme.** It is
NOT significant — the interval spans zero — and it must not be quoted as edge.

## Two effects, both needed, neither speculative

1. **The circuit breaker** withdraws one-sided markets: the excluded rows lose
   1.5¢ (CFB) and 9.1¢ (WNBA) per fill even after the rebate. 10% of volume
   carrying nearly all the damage.
2. **The rebate** adds a flat ~0.28¢ to every fill. It is published, not
   discovered, and it does not depend on any model being right.

Neither alone gets there. Together the point estimate crosses zero.

## What would still kill it

- **The fill model.** Our simulator fills when the mid reaches our price, which
  forces `capture ≤ 0` by construction (meridian-14) — and the phantom
  classifier that was meant to correct for it tested the wrong condition
  (`ask ≤ B` requires the book to gap THROUGH us, which is the adverse tail,
  not a normal maker fill). **Settlement P&L is not subject to that identity,
  but fill SELECTION remains unvalidated.** λ(q) is the open work.
- **24 games, in-sample.** The interval spans zero and would need roughly an
  order of magnitude more games to resolve ±0.1¢.
- **Rebate eligibility.** Verified from the schedule, not from a settled
  statement of our own. The account activity feed exposes no fee fields, so
  this is documented rather than observed. **A real fill would confirm it.**

*No in-sample result justifies capital. The forward test is the evidence.*
