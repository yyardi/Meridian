# What the edge is actually worth

**Question:** the champion beats the close by 1.75 points. In money, is that anything?

Until now the answer was unknown, because points are not money. This doc is the conversion and the number it produces. Experiment 3 of the v4 ledger.

## Points are not comparable to ROI

A 1.75-point beat on a total with sigma 17 is worth more than the same beat with sigma 21, and neither can be set beside a realised ROI. The 2026 scoring environment runs sigma ~21.7 against ~17.3 in earlier seasons, so the *same* headline CLV means materially less edge now than it did then. Quoting CLV in points hides that.

## The conversion

Buchdahl's rule: beat the **no-vig** closing price by X% and expected ROI is about X%. In price terms, for a bet struck at price $p_{\text{paid}}$ whose true probability the close puts at $p_{\text{close}}$,

$$
\mathbb{E}[\text{ROI}] = \frac{p_{\text{close}}}{p_{\text{paid}}} - 1
$$

$p_{\text{paid}}$ is the **vig-included** price, because that is what determines the payout. $p_{\text{close}}$ is **de-vigged**, because the book's margin is nobody's true probability — leaving it in understates our edge on every bet, the mirror of the error [odds_math](../../core/feeds/odds_math.py) warns about.

Getting $p_{\text{close}}$ from a closing *line* needs a distribution. The close says the market's central estimate is `close_line`, so our over struck at `entry_line` has fair probability

$$
p_{\text{close}} = \Phi\!\left(\frac{\text{close\_line} - \text{entry\_line}}{\sigma}\right)
$$

with $\sigma$ the same walk-forward scoring-environment estimate the bet was priced with. That is where points become probability, and why `sigma` is stored on every bet record.

De-vigging is proportional (equal-margin): both sides scaled by one factor to sum to 1. Shin additionally models insider money and shifts probability away from longshots; on a two-sided total at near-symmetric juice the two barely differ, and proportional has no free parameter to fit.

## The result

Seasons 2024–2026, min edge 3.0 points.

> ⚠️ **Superseded on the fill side by C13 (2026-08-07).** The "realistic"
> realised ROI below was computed with a 0.5¢ adverse-selection concession that
> was a guess written before any fill had been observed. The measured pregame
> concession is **2.11¢** [1.83, 2.39] per filled contract (in-game 4.70¢), and
> under it the same 218 filled bets realise **−2.33%** (−1.79% to −2.86% across
> the pregame CI; −7.27% in-game-calibrated). The conversion mathematics below
> and the CLV numbers are untouched; the realised column is what moved.

| Fill model | CLV (points) | CLV (no-vig prob) | E[ROI] from CLV | Realised ROI |
|---|---|---|---|---|
| optimistic | +1.751 | +0.0391 | +2.98% [+1.65%, +4.31%] | +1.67% (re-run 2026-08-07, rebate-free) |
| **realistic (measured 2.11¢ AS)** | **+1.751** | **+0.0416** | **+2.50% [+0.85%, +4.16%]** | **−2.33%** |
| pessimistic | +1.751 | +0.0391 | +0.11% [−1.18%, +1.40%] | −4.04% |

**The revised headline: +1.75 points of CLV is still +4.16pp of no-vig
probability edge — and measured adverse selection on the maker fill costs more
than that edge pays.** E[ROI]-from-CLV assumes the fill is free; the fill is
measured at 2.11¢, which is ~2/3 of the whole per-contract edge on a ~30¢
book, before fill probability is even considered.

The gate asked whether de-vigged CLV predicts what the maker-only ledger pays.
Under the guessed concession it appeared to (predicted +2.50%, realised +1.98%).
Under the measured one it does not: the prediction and the realisation are
separated by exactly the newly-measured cost, which is the honest resolution —
the conversion was right, and its "fills are benign" assumption was wrong.

## Read the caveats before believing the headline

- **Agreement here is weak evidence.** The realised ROI interval is ±13 points wide. It rules out a gross accounting error, not a small persistent one. That width is exactly why [clv.md](clv.md) makes CLV the gate — the CLV-implied interval is 8× tighter than the realised one on the same bets.
- **The edge does not survive pessimistic fills.** At +0.11% [−1.18%, +1.40%] the interval covers zero. Maker-only execution is not a preference, it is load-bearing, and this is the number that says so.
- **It assumes the close is fair.** Moskowitz (2021) finds closing lines overreact to open-to-close drift, which would make the true fair value sit between open and close and overstate everything above.
- **2.50% is a per-bet expectation, not a return on capital.** At ~100 bets a season and quarter-Kelly sizing, the money at stake is small; this is a validation of method, not a business case.

## What changed as a result

Nothing in the model. This is an accounting change and cannot improve an edge — only state it in units that can be checked. What it buys is the ability to answer "is this worth anything?" in money, and the answer is a qualified yes under maker-only fills.

## Status

**Adopted** (2026-08-01). CLV continues to be reported in points as the primary gate; the de-vigged conversion is reported alongside it so the points figure can never again be mistaken for a return.

**Amended** (2026-08-07, C13): the realised column now uses the measured
adverse-selection concession, and the money verdict flipped negative. The live
maker fill sample to date (n=5, descriptive): pregame-placed 0/3 filled;
in-game-placed 2/2 filled in 48 and 111 minutes — the fills that come are in
the regime with the worse concession. See findings C13.
