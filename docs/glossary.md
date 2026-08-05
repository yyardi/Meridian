# Glossary

Terms used throughout the project. Where a term has a doc of its own, it is linked.

## Market microstructure

**Bid / Ask** — best price someone will buy at / sell at. The gap is the **spread**,
a real round-trip cost.

**Order book depth** — the full queue of resting orders at each price, not just the
best. Determines how much you can trade before moving the price. On this venue it is
**\$5–24 at the touch** on cheap contracts — see [findings.md](findings.md#1-venue-facts).

**Maker / Taker** — a *maker* posts a resting limit order and waits; a *taker*
crosses the spread to fill immediately and **pays a fee** ($\Theta = 0.06$,
venue-published and measured). Maker-only is load-bearing: taker fills turn +0.75%
into −4.0%. A maker *rebate* is advertised by the venue but has **never been
observed in this account** — the code books zero (findings C7) and sizes on the fee
avoided, not the rebate earned. [math/fees-and-spread.md](math/fees-and-spread.md)

**Tick** — the minimum price increment. **0.01 on every market here**, which at 16¢
is 6.25% of contract value.

**Slippage** — filling worse than quoted because your order ate through the book.

**Ladder** — the set of markets on one game at different thresholds (Over 173.5,
176.5, …). Together they imply a probability distribution.
[math/ladder-curve-fit.md](math/ladder-curve-fit.md)

**Settlement** — final resolution: `1` (Yes) or `0` (No).

## Measurement

**CLV (Closing Line Value)** — whether you got a better price than the market's final
pre-game price. The fastest-converging evidence of edge at small samples: it is
measured on every bet rather than only on outcomes, so you can beat the closing line
and still lose the bet. That is a *good* bet with a bad outcome, and CLV tells the two
apart. [math/clv.md](math/clv.md)

**De-vigging** — removing the bookmaker's margin from quoted prices to recover implied
probabilities. Required before CLV in points can be turned into ROI in money.
[math/what-the-edge-is-worth.md](math/what-the-edge-is-worth.md)

**Walk-forward** — test by stepping through time, fitting only on data available
before each game. The only backtest method that does not lie to you.

**Point-in-time correctness** — the guarantee that a backtest of a July 15 game sees
only pre-July-15 information. Enforced structurally: `as_of` is keyword-only with no
default. [math/point-in-time.md](math/point-in-time.md)

**Clustered standard errors** — rows within one game are not independent, so the
sample size is **games**, not rows. Ignoring this measured 11% CI coverage against a
nominal 95%. [math/clustered-errors.md](math/clustered-errors.md)

**Winner's curse / market shrinkage** — when the model disagrees with the market,
most of the disagreement is the model's own error. Measured retention here is
**16–23%**, so a raw edge overstates the real one ~4×.
[math/market-shrinkage.md](math/market-shrinkage.md)

## Modelling

**Kelly criterion** — optimal bet fraction: `f = (bp − q) / b`. Full Kelly is
growth-optimal but assumes your edge estimate is *exact*. Ours is model-derived and
unverified, so we use **quarter Kelly**: far less drawdown for most of the growth.
[math/kelly.md](math/kelly.md)

**Correlation-aware sizing** — moneyline and total on the same game are not
independent bets. Sizing each at full Kelly means a much larger true position than
intended. Size the game as one basket.

**Pythagorean expectation** — predicted win% from points scored and allowed:
`PF^k / (PF^k + PA^k)`. The exponent `k` is league-specific; **fitted at 11.09 for the
WNBA** on 2023–2025 data. Do not borrow the NBA's ~13.9.
[math/pythagorean-record.md](math/pythagorean-record.md)

**Record residual** — `actual_win% − pythagorean_win%`. The part of a team's record
point differential cannot explain: close-game execution and clutch. Measured to carry
no demonstrable signal — the observed spread is *smaller* than pure chance would
produce.

**Config hash** — a deterministic hash of the model's full config, stored on every
prediction. `model_version` is hand-bumped and will eventually be forgotten; the hash
is derived from the config actually used, so two models can never silently share an
identity in backtest results.

## Data

**Season type** — ESPN's `seasonType.id`: `1` Preseason, `2` Regular Season,
`3` Postseason. Preseason is excluded from all stats (it would corrupt PPG and
record); postseason drives playoff down-weighting.

**Measured constants** — fitted from real WNBA data (2023–2025, 769 games, 37
team-seasons). A result far outside these usually means a bug, not a discovery.

| Constant | Value |
|---|---|
| Game total, mean | **164.0** |
| Game total, σ | **17.3** |
| Pythagorean exponent `k` | **11.09** |
| Record residual, σ | **0.049** |
| Binomial noise floor, 40 games | **0.079** |

> A common bug when computing totals σ: `team_game_logs` holds **two rows per game**,
> so aggregate without deduping on `espn_game_id` and you double-count every game.
