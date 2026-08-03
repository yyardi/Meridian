# Market shrinkage on spreads and moneylines

**Question:** the moneyline hits 33% and loses 9.5%. Is it miscalibrated, or is it something worse?

Something worse. Experiment 2 of the v4 ledger, and the answer changed what got built.

## The prescribed fix was aimed at the wrong thing

The ledger called for isotonic/Platt recalibration to correct "~10 points of moneyline overconfidence". Measured first, that premise does not hold. Across **all** games, the model's win probability is already well calibrated:

| p_model | 0.45 | 0.55 | 0.65 | 0.75 | 0.85 |
|---|---|---|---|---|---|
| realised | 0.436 | 0.553 | 0.663 | 0.772 | 0.847 |

A monotone recalibration of a scale that is already correct has nothing to fix. But condition on *having bet*, and every bucket collapses:

| p_model | 0.25 | 0.35 | 0.45 | 0.55 | 0.65 |
|---|---|---|---|---|---|
| realised | 0.14 | 0.25 | 0.32 | 0.30 | 0.57 |

A **uniform** downward shift, not the asymmetric fan-out that overconfidence produces. The probabilities are fine. The *selection* is what fails.

## The real diagnosis

Regress (actual − market) on (model − market) over 2024–2026, walk-forward safe:

$$
\text{slope} = +0.176 \quad 95\%\ \text{CI}\ [-0.031,\ +0.382] \qquad n = 677
$$

| | model | market |
|---|---|---|
| margin MAE | 10.19 | **9.65** |
| corr with actual | +0.411 | **+0.482** |

**The model is dominated by the market.** It retains at most ~18% of its stated disagreement; the other ~82% is its own error, and the CI does not exclude zero. Betting the raw gap treats a 0.18-weight signal as weight 1.0 — overbetting roughly fivefold. That is how a calibrated model hits 33%.

This is the same winner's curse the totals model already corrects for, never applied to the margin markets.

## The fix, and the result

Shrink the model-vs-market gap by the walk-forward incremental slope before selecting or pricing, since $\mathbb{E}[\text{actual} - \text{mkt} \mid \text{model} - \text{mkt}] = \text{slope} \times (\text{model} - \text{mkt})$ is the correct predictor and the raw gap is not.

| Market | Arm | n | Hit rate [95% Wilson] | ROI |
|---|---|---|---|---|
| Spread | raw | 236 | 0.513 [0.449, 0.576] | −2.48% |
| Spread | **shrunk** | 37 | **0.541** [0.384, 0.690] | **+2.83%** |
| Moneyline | raw | 311 | 0.334 [0.284, 0.389] | −9.48% |
| Moneyline | **shrunk** | 108 | 0.250 [0.178, 0.339] | **−17.91%** |

Breakeven is 0.524.

**Spread: promising, not proven.** Shrinkage moves the point estimate above breakeven and flips ROI positive, but it also cuts the bet count from 236 to 37 and the interval still contains breakeven. Adopt the correction; do not size on it.

**Moneyline: dead.** The entire interval sits below breakeven, and shrinkage makes it *worse*.

## Why shrinkage helps the spread and hurts the moneyline

They are different bets on the same opinion. After shrinkage both markets select the same extreme-disagreement tail — overwhelmingly large underdogs. A big underdog **covers** far more often than it **wins outright**. So the surviving bets can be good against the number and terrible on the moneyline, with no contradiction.

## What changed as a result

The executor now refuses the moneyline outright. `ExecutorConfig.tradable_market_types` allows totals and spreads only.

This lives on the **executor**, not in `WNBATotalsConfig`, and that placement is deliberate: it is an execution policy, not a model parameter. Putting it in the model config would change `config_hash`, split the prediction log's history, and reset the 60-day shadow gate over a decision that has nothing to do with how the model prices anything.

Moneyline predictions are still *logged* — the log records everything, including what we decline to trade. They are just never sized or ordered. At the time of the change the live path had produced **254 actionable moneyline predictions and 80 shadow orders** on this market.

## Caveats

- **Neither number is a CLV result.** ESPN keeps no open/close pair for spreads or moneylines, so these are outcome-based and converge slowly — the exact weakness [clv.md](clv.md) exists to avoid.
- **n=37 is not a result.** The shrunk spread arm is a direction, not evidence.
- **The slope's CI includes zero.** "The model has ~18% incremental information" is the point estimate; "the model may have none" is inside the interval.

## Status

**Moneyline: rejected for trading** (2026-08-01). **Spread: shrinkage available** via `MarginBacktestConfig.shrink_to_market`, off by default pending a larger sample. Totals are unaffected — they already shrink.

## Postscript: the live path was never shrinking

Discovered 2026-08-01 while answering "if the dashboard says +13%, would I lose money?"

The backtest has always applied this correction (`calibrate_probabilities`), so every validated number — the +1.75 CLV champion included — describes a **shrunk** model. `predict_market` did not. The deployed model was not the model under test, and the dashboard reported raw model-minus-market gaps.

At the measured totals slope (0.161–0.231), the overstatement is roughly fourfold:

| Dashboard showed | True edge |
|---|---|
| +5% | 1.2% |
| +10% | 2.3% |
| +13% | 3.1% |
| +20% | 4.8% |

Fixed in **v4**: `estimate_market_slope` + `shrink_to_market` in the live path, anchored to the median book total for the game. The version bump is mandatory rather than cosmetic — `config_hash` derives from `WNBATotalsConfig` and this change lives outside it, so v3's unshrunk rows and v4's shrunk rows would otherwise share a grouping key and silently blend two model generations.

Two consequences worth stating plainly:

- **The 60-day shadow record restarts.** Correct: the old record describes a model that is no longer running.
- **Games with no book line yet cannot be shrunk** — there is nothing to anchor to. Those show the largest raw edges and are now marked `reduced_confidence` and **never actionable**, rather than sitting on the board looking identical to a validated price.

The slope is refreshed daily into `model_calibration` and read from cache by the 20-minute prediction leg; recomputing it walks every completed game, which is seconds locally and minutes against Supabase.
