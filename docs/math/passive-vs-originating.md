# We built the wrong game — 2026-09-04

**Practitioner sources (operator-supplied, r/PredictionsMarkets + Polymarket
docs) name two market-making businesses. We built the one we cannot win.**

> *"passive liquidity is a really hard game, that requires a ton of capital,
> you want to be up on as many markets as you can as much of the time as you
> can, and you'll be competing for very thin margins. **if you're originating
> it doesn't require any more capital than other strategies, you can build high
> margin positions and you can be very selective about what and when you
> quote.**"*

**PASSIVE** — quote everything, always, at the touch, thin margins, needs size.
**That is precisely our quoter, on a $1,000 book.** Up on every market it can
see, at the touch, symmetric, always on. It is the capital-intensive game, run
without the capital.

**ORIGINATING** — selective, early, high margin, needs an opinion not a
balance sheet. And the practitioner's own description of it is our measurement:

> *"i started by quoting the best price in market **early week** on the right
> side of nfl lines **i knew would move later based on my own model**, just to
> get a discount over what was available retail."*

That is the favourite–longshot result restated by someone doing it for money:
**quote early, on the side the price is wrong, and let retail come to you.**
Ours is measured at **+7.88¢/trade, game-clustered CI [+2.17, +13.59]**
(`docs/math/favourite-longshot.md`), and the bias is **largest early** (−6.88¢
at first observation, decaying to +0.06¢ by settlement).

## The rewards-farming game does not exist for us — checked, not assumed

> *"a lot of the market making bots on polymarket are actually making much more
> from farming liquidity rewards than from their actual market making"*

True, and **not available on our venue.** Probed the live payload for every CFB
market: **fields matching reward/incentive/rebate/liquidity/maker: NONE.** The
$1M liquidity-reward pools in the docs are allocated to **crypto** 5m/15m/4h
markets on polymarket.com; we trade the US regulated venue, sports only.

And maker rebates cannot carry us either. Sports rebate = 15% of taker fees,
`fee = C × rate × p × (1−p)`:

| price | taker fee | **max** maker rebate |
|---|---:|---:|
| 0.20 / 0.80 | 0.800¢ | 0.120¢ |
| 0.35 / 0.65 | 1.137¢ | 0.171¢ |
| 0.50 | 1.250¢ | **0.188¢** |

**Best case 0.19¢ per fill against a measured −3.38¢ loss — it recovers 6%.**
Rebates are a rounding error on a losing book; they are not a strategy.

## ★ OPEN AND MATERIAL: does the MAKER pay the fee here? ★

Every CFB market on our venue carries **`feeCoefficient = 0.06`** — *higher*
than polymarket.com's 0.05 sports rate. At p=0.50 that is **1.5¢ per contract**.

**Our shadow fills model no fee at all** (`capture = mid_at_fill − quote_price`,
no fee term). So:

- if only takers pay → our −3.38¢ stands, and that fee is what funds rebates;
- **if makers pay → our true loss is ≈ −4.9¢ and every number in this program
  is 1.5¢ too kind.**

This must be established against the venue before any capital decision. It is
the single largest unpriced term we have found.

## What changes

1. **Stop building passive.** Quoting everything at the touch on $1,000 is the
   game the practitioners say needs a balance sheet and yields thin margins.
2. **Build originating.** Selective, early, few markets, wide margins — quote
   inside the wide early book on the side the bias favours. The 16–18¢ first
   spreads are room, not danger.
3. **Resolve the fee question first**, because it moves every number.
4. **Infrastructure the sources say is required and we already have**: pricing
   engine, order-book awareness, trade/position logging, risk circuit breakers.
   *We have all of it.* What we lack is the opinion to point it at.

**No in-sample result justifies capital. The forward test is the evidence.**
