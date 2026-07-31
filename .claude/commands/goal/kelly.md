---
description: Build correlation-aware fractional Kelly position sizing
---

# Goal: Kelly sizing + risk guardrails

Build the position sizing module for **Meridian**. Build unit **10 of 12**, depends on `/goal:backtest`. Read `README.md` first.

## Task

Build `core/kelly_sizing.py`.

### Fractional Kelly

```
f = (bp − q) / b
```
where `b` = net odds, `p` = model probability, `q = 1 − p`.

**Default to quarter Kelly (0.25), configurable.**

Why fractional: full Kelly is growth-optimal *only if your edge estimate is exact*. Ours is model-derived and unverified — this system has an n=2 manual sample behind it, not a proven edge. Overestimating edge with full Kelly produces severe drawdowns and can be ruinous. Quarter Kelly gives up a modest amount of theoretical growth for a large reduction in drawdown, which is the right trade when the edge estimate itself is the uncertain part.

### Correlation-aware basket sizing

**This is the part most implementations get wrong.**

Bets within one game are not independent. Moneyline and Over on the same game are positively correlated — a blowout by the favorite tends to move both. Sizing each at full Kelly means the true combined exposure is much larger than intended.

Requirements:
- Size all positions in a single game as **one basket**, not as independent bets
- Cap total exposure per game (configurable, e.g. ≤ Kelly for the single best edge in that game)
- Estimate correlation between market types within a game — from historical data where available, otherwise conservative fixed assumptions, and **document which is in use**
- Treat same-side ladder rungs (Over 176.5 and Over 179.5) as near-perfectly correlated — they are almost the same bet

### Hard guardrails (independent of Kelly)

These are backstops that apply *after* Kelly, so a model bug can't produce a catastrophic bet:

- `max_position_size_pct` — max % of bankroll in any one position
- `max_game_exposure_pct` — max % across one game
- `max_daily_exposure_pct` — max % deployed in a day
- `min_edge_threshold` — don't bet below this edge; small edges are within model error
- `min_bankroll` — stop trading below this
- **Absolute dollar cap** as a final backstop

Current bankroll is **$25–40**. Note honestly in the output that at this size:
- Position sizes will be very small, possibly below `minimumTradeQty`
- Variance dominates any real edge for a long time
- Kelly's continuous-fraction assumption is strained by discrete minimum trade sizes

### Fees in the edge calculation

Edge must be computed **net of fees**, or you'll size on illusory edge:

```
fee = Θ × contracts × price × (1 − price)
Θ_taker = +0.06     Θ_maker = −0.0125   (rebate)
```

At p=0.50 a taker pays 1.5¢/contract — comparable to the entire edge being hunted. Since the executor is limit-only (maker), sizing should assume the maker rebate but flag when a fill would cross the spread and become a taker.

## Requirements

- Pure functions — no DB or network calls. Inputs → size.
- Typed `PositionSize` return, including the reasoning: which constraint bound the size.
- Every guardrail configurable in `strategies/wnba_totals/config.py`, with safe defaults.
- **Never return a size exceeding any guardrail**, regardless of what Kelly suggests.
- Log which constraint was binding — invaluable when a position looks wrong.

## Tests

1. Known edge/odds → hand-computed Kelly matches
2. Quarter Kelly = 0.25 × full Kelly
3. Correlated same-game bets size below the sum of independent sizes
4. Every guardrail actually clamps
5. Negative edge → zero size, never a negative bet
6. Edge below threshold → zero size
7. Fee-adjusted edge is lower than raw edge

## Done when

- Sizing runs on real predictions from `/goal:predictions`
- A same-game basket (ML + total) sizes smaller than the two independent sizes summed
- Guardrails clamp under adversarial inputs (edge = 0.99)
- Output states the binding constraint
- Backtest integration shows the drawdown difference between quarter and full Kelly
