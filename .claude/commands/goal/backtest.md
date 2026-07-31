---
description: Build the walk-forward backtest engine with CLV as the primary metric
---

# Goal: Walk-forward backtest engine

Build the backtest engine for **Meridian**. Build unit **9 of 12**, depends on `/goal:predictions`. Read `README.md` first.

**This is the priority deliverable of the whole project** — more important than the execution layer. Its job is to answer honestly whether the model has an edge, including (especially) when the answer is no.

## Walk-forward only

Step through time. For each game, fit/compute using **only data available before that game**. Never let a later game influence an earlier prediction.

```python
for game in sorted(games, key=lambda g: g.start_time):
    features = build_features(team_id, as_of=game.start_time, session=s)  # as_of is mandatory
    prediction = model.predict(features)
    record(prediction, actual_outcome=game.outcome)
```

The engine must **structurally** prevent lookahead — every data access goes through an `as_of` filter. If a code path can read future data, that's a bug regardless of whether current results look reasonable.

## Primary metric: CLV, not win rate

**Closing line value** is the headline number.

Why: at a $25–40 bankroll over a few dozen bets, win rate is nearly pure noise — you cannot distinguish a 55% edge from a 45% loser at that sample size. CLV is measured on *every* bet rather than only on outcomes, so it converges far faster.

Track whether the model beat the closing line **even on losing bets**. A bet that got a better-than-closing price and lost is a good bet with a bad outcome. Conflating those two is the most common way small-sample bettors fool themselves.

```
CLV = model_entry_price vs closing_line_price   (in probability terms)
```

⚠️ **Only 2024+ has true closing lines.** 2020–2023 has consensus lines but no `open`/`close` split (see `/goal:backfill`). The report **must** state what fraction of the sample has genuine closing lines. Never silently substitute a current line for a closing line — that fabricates the primary metric.

## Realistic fill simulation

Nuance discovered during research that changes the standard approach:

Measured WNBA book depth at top-of-book: **~$795 on a total, ~$7,452 on a moneyline.** At a $25–40 bankroll you are ~1/20th of the best price level alone. **You cannot move this market, so slippage is not the binding constraint.**

So do **not** model slippage as the main cost. Model instead:

1. **Spread cost** — you don't trade at mid. Buying means the ask, selling the bid. Typical WNBA spread is 1–3¢, which is large relative to any plausible edge.
2. **Fill probability for resting limit orders** — the real question is *"would my limit order have been filled?"* If you post at the bid and the market moves away, you never fill. Model this rather than assuming perfect fills.
3. **Adverse selection** — resting orders fill preferentially when the market moves against you. Naively assuming every resting order fills at a good price overstates returns.
4. **Fees** — real and often omitted:
   ```
   fee = Θ × contracts × price × (1 − price)
   Θ_taker = +0.06     Θ_maker = −0.0125   (maker gets a REBATE)
   ```
   At p=0.50: taker pays 1.5¢/contract, maker earns 0.3¢. Against a 2¢ spread this is a large fraction of any edge. Model maker and taker separately.

Make the fill model **pluggable** — optimistic / realistic / pessimistic — and report all three. If the edge only survives the optimistic model, there is no edge.

## Report the full distribution

Not a headline ROI. At this bankroll variance dominates for a long time, so show the shape:

- **CLV** (primary): mean, distribution, % of bets beating close
- ROI, hit rate, total P&L
- **Max drawdown** and the **full equity curve** — plot it
- Sharpe ratio
- Bet count, average edge, edge-vs-realized-return correlation
- **Calibration table** — predicted probability bucket vs. realized frequency
- Breakdown by market type (totals / spread / moneyline) and by edge bucket

### Required honesty flags

The report must clearly state:
- How much of the backtest ran on **genuinely historical** data vs. recorder-accrued data
- What fraction has **true closing lines** (2024+) vs. consensus only (2020–2023)
- Sample size, and a plain statement about whether it's large enough to conclude anything

A `n=40` backtest with 8% ROI means nothing. The report should say so rather than let the number stand unqualified.

### Model generation isolation

**Group results by `(model_version, config_hash)` and refuse to aggregate across differing hashes** unless explicitly overridden with a loud flag.

This is the concrete mechanism preventing pre- and post-change results from silently mixing. `model_version` is hand-bumped and will eventually be forgotten; `config_hash` is derived from the config actually used, so it can't be. If a run spans multiple hashes, either split the report or fail with a clear message — never quietly average them.

### Record-modifier A/B

The win-loss record modifier must be **measured, not assumed**:

- Run the backtest **with and without** the record modifier (`β` fitted vs. `β = 0`) and report both
- Report the **fitted `β` and its confidence interval per walk-forward window**
- Report **playoff games as a separate cohort** — they carry `reduced_confidence` and a down-weighted modifier, and at ~15–20 games/season no playoff-specific conclusion is supportable

> **A near-zero `β` is an expected, valid result.** On 2023–2025 data the record residual's spread across teams (4.9 win-% pts) is smaller than pure binomial noise for a 40-game season (7.9 win-% pts), implying no measurable persistent clutch skill. If `β` is indistinguishable from zero, **the report must say so plainly** rather than presenting the feature as productive. Do not tune the feature to look useful — the point of the A/B is to let it fail honestly.

## Requirements

- Deterministic and exactly replayable — same inputs, same output. No RNG without a fixed seed, no `datetime.now()` in the path.
- Configurable: date range, market types, fill model, Kelly fraction, starting bankroll.
- Export results to CSV/parquet for notebook analysis.
- Matplotlib equity curve + drawdown chart.

## Tests

1. **Lookahead test** — inject a future game; results for earlier dates must not change. This is the most important test in the repo.
2. Known-outcome fixture produces hand-verifiable P&L
3. Fee math matches the formula
4. Determinism across runs
5. **Config isolation** — a dataset spanning two `config_hash` values either splits or fails, and never silently averages
6. **`β = 0` reproduces the v1 baseline** — the A/B's "without" arm matches a PPG-only run exactly

## Done when

- A walk-forward run over 2024–2026 completes and reports the full metric set
- The lookahead test passes
- The report states closing-line coverage and sample size honestly
- Equity/drawdown curves render
- All three fill models run, and the difference between them is visible
- Results are reproducible across runs
- Results are grouped by `(model_version, config_hash)` and refuse to mix generations
- The record-modifier A/B reports both arms, the fitted `β` with a confidence interval, and playoffs as a separate cohort — **including when the honest answer is "no measurable effect"**
