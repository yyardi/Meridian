# Open problem: the model is not calibrated

**Status:** open, logged 2026-07-31. Blocks any move to live sizing.

The v2 model produces probabilities that carry almost no information about game outcomes. This is the headline finding of the first clean backtest and the thing to fix before anything else.

## The evidence

Walk-forward, 2024–2026, realistic fills, n=249 filled bets.

### Calibration is flat

| Predicted | Realised | n |
|---|---|---|
| 0.55 | **0.50** | 88 |
| 0.65 | **0.49** | 132 |
| 0.75 | 0.56 | 27 |
| 0.85 | 0.50 | 2 |

A calibrated model's 65% predictions win ~65% of the time. Ours win **49%**. The realised rate is ~0.50 across *every* confidence bucket — the model's stated confidence is uncorrelated with whether it is right.

### Bigger edge does not mean better returns

| Quartile by \|edge\| | n | avg \|edge\| | avg P&L | hit rate |
|---|---|---|---|---|
| Q1 (smallest) | 62 | 0.055 | −0.054 | 0.500 |
| Q2 | 62 | 0.079 | −0.049 | 0.500 |
| Q3 | 62 | 0.111 | **+0.045** | 0.548 |
| Q4 (largest) | 63 | 0.183 | **−0.124** | 0.460 |

No monotonic relationship. The bets the model is *most* confident about are the **worst** performers. Overall edge-vs-realised correlation is **+0.001**.

## Diagnosis

There are two candidate explanations and the data distinguishes them.

**Hypothesis A — σ is too small.** If the projection had signal but we understated variance, calibration would be *monotonic but compressed*: 0.65 predicted → maybe 0.55 realised, 0.75 → 0.60. Directionally right, overconfident in magnitude.

**Hypothesis B — the projection has no signal about which side of the line a game lands.** Then realised sits at ~0.50 regardless of predicted confidence.

**The data shows a flat ≈0.50, so B.** This is not a variance-estimation problem — it is a signal problem.

## The part that complicates the story

CLV is mildly positive: **+0.55 points**, 95% CI [+0.28, +0.83], and on the 66% of games where the line actually moved the model called direction **59.2%** of the time.

So two things are simultaneously true:

- The model has some information about **which way the line will move**
- The model has ~no information about **which side of the line the game lands**

That combination is coherent, and the likely reading is that the projection is picking up information already flowing into the price — it is directionally correct but *late*, and by the time we would trade, the price has moved. Beating the open while not beating the close is exactly what a slow signal looks like.

It also means the positive CLV should not be over-read. Beating a *sportsbook* open is a low bar; the closing line is the accurate one.

## What to try, in order

1. **Pace.** The single biggest known gap. Two fast teams produce more possessions and a higher total than their PPG averages imply. The current model has no possessions term at all — it is pure points-per-game. This is the most likely source of real signal.
2. **Refit σ empirically per line distance**, rather than one season-wide σ. Even under Hypothesis B, a better σ improves probability quality once a signal exists.
3. **Check the projection against the *closing* line rather than the open.** If the model's projection is closer to the close than the open is, the signal is real but slow, and the fix is timing rather than modelling.
4. **Opponent adjustment (strength of schedule).** Currently absent — see [pythagorean-record.md](pythagorean-record.md).

## What NOT to do

- **Do not tune thresholds until the ROI looks positive.** With n=249 and a flat calibration curve, any positive-looking configuration is overfitting to noise.
- **Do not size this with Kelly.** Kelly on an edge estimate that is uncorrelated with returns converts a small negative expectation into a faster one.
- **Do not read the +0.55 CLV as an edge.** It is measured against the *opening* line, and it does not survive spread and fees.

## Related

- [clv.md](clv.md) — why CLV converges faster than win rate, and its limits
- [fair-value.md](fair-value.md) — the projection, and the 2026 regime shift
- [fees-and-spread.md](fees-and-spread.md) — the ~2.5¢/contract cost this must clear
