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

> **RETRACTED 2026-09-06.** The claim below is superseded and the corrected
> figure is NEGATIVE and significant. See the correction directly under it.

~~**Guarded book, both sports, game-clustered over 24 games: +0.061¢,
CI [−0.762, +0.883].** The point estimate is POSITIVE for the first time in
this programme.~~

## CORRECTION (2026-09-06)

**The table above is captioned "real settled fills" and its counts are
all-settled.** Verified by a bound that needs no reconstruction: it reports
16,672 guarded WNBA fills, and the pinned export contains only **6,255 real
WNBA fills in total**. A real-only count cannot exceed the real population.

**64% of the kept fills are phantom** — events that could not have happened,
because the mid crossed while the book never came to us. The circuit breaker
withdraws one-sided **markets**; it never removed phantom **fills** inside
two-sided markets. Phantoms score **+0.951¢** each, and they are what pulled
the pooled figure positive.

Two further levers, both toward spurious positivity:

- **Equal-weight on a stale tape.** +0.061¢ is `avg(avg(pnl))` — mean of game
  means — from `scripts/sandbox.py:99,103`, computed on a 24-game partial tape.
  The pin has 61 games. The fills-weighted sandwich's *point* IS the
  fills-weighted mean, so no version of it yields +0.061¢; the two published
  "true" values pool to **−0.021¢**.
- **An undeclared small-market exemption.** `sandbox.py` keeps markets with
  `s.n < 4` however one-sided they are — exactly the low-fill markets that
  equal-weighting then up-weights. Equal-weight swings **−2.569¢ with the
  exemption to +0.278¢ without it**: a 2.85¢ move from 13 tiny markets.
- The published CI used **1.96, not t** (t₂₃ = 2.069, ~6% too narrow at G=24)
  and a naive game-level SE rather than a cluster-robust one.

**CORRECTED — real fills only, + circuit-breaker guard, rebate included,
fills-weighted cluster-robust sandwich, current pin:**

| sport | real+guard fills | P&L | rebate | true | game-clustered CI |
|---|---:|---:|---:|---:|---|
| wnba | 5,527 | −2.462¢ | +0.287¢ | **−2.175¢** | [−3.264, −1.085] (G=13, G_eff 11.2) |
| cfb | 16,535 | −1.357¢ | +0.283¢ | **−1.074¢** | [−2.472, +0.325] (G=35, G_eff 19.9) |
| **pooled** | 22,062 | | | **−1.349¢** | **[−2.411, −0.288]** (G=48, G_eff 29.5) |

The guarded book is **negative and the pooled interval excludes zero**. The
rebate (~+0.28¢) and the circuit breaker each do genuine work — pooled
real+rebate −2.12¢ improves to −1.349¢ with the guard — but it does not cross
zero. WNBA alone excludes zero; CFB alone spans it. No single sport is
individually positive.

Variants, named with estimator and phantom share:

- all-settled+guard (the population the table actually used, 64% phantom),
  fills-weighted sandwich, rebate: **+0.117¢ [−0.400, +0.633]** — positive only
  because it keeps phantoms.

Corrected figures measured by Quant Agent A on
`backups/exports/quote_fills_classified_20260906T024500Z.csv`; the caption
mislabel, the estimator and the `n < 4` exemption verified independently
against `scripts/sandbox.py`.

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
