---
description: Build the fair-value projection model and ladder curve fit
---

# Goal: Fair-value model + ladder curve fit

Build the prediction model for **Meridian**. Build unit **7 of 12**, depends on `/goal:features`. Read `README.md` first.

## Two pieces

### A. Fair-value projection — `strategies/wnba_totals/model/fair_value.py`

The baseline, deliberately crude:

```
projected_A = (teamA_offense_ppg + teamB_defense_ppg_allowed) / 2
projected_B = (teamB_offense_ppg + teamA_defense_ppg_allowed) / 2
projected_total  = projected_A + projected_B
projected_spread = projected_A - projected_B
```

Use home/away-split and form-decayed features from `/goal:features`, all `as_of` the prediction timestamp.

#### Win-loss record modifier (spread + moneyline only)

Applied on top of the PPG projection, as a **modifier** — never as a standalone signal:

```
record_edge       = teamA.record_residual − teamB.record_residual
projected_spread += β × record_edge × playoff_weight
```

Four rules, all load-bearing:

1. **`β` is fit from historical data walk-forward, never hand-set.** This is the whole safety mechanism — see the note below.
2. **Totals are untouched.** Clutch execution has no plausible mechanism for moving a game's *combined* score; including it would only inject noise into the primary market. Keep it configurable with totals defaulting to off, so the backtest can test the claim rather than assume it.
3. **`playoff_weight`** — `1.0` regular season, configurable default **`0.25`** when `is_playoff_game`. Regular-season record loses predictive value in the playoffs: seeding is locked, rotations tighten, and short-series intensity differs from a Tuesday in July.
4. **Playoff games set `reduced_confidence = true`** with a `confidence_notes` string explaining why.

> **Why down-weight instead of fitting a playoff-specific coefficient:** the WNBA postseason is only ~15–20 games per season. There is nowhere near enough data to fit playoff-specific behavior; a configurable down-weight plus an explicit confidence flag is the defensible choice at that sample size.

> **Expect `β ≈ 0`.** On 2023–2025 data the record residual's spread across teams (4.9 win-% pts) is *smaller* than pure binomial noise for a 40-game season (7.9 win-% pts) — no measurable persistent clutch skill. Because `β` is fitted, a noise feature collapses to zero on its own and harms nothing. **Do not hand-tune `β` to make the feature look productive.** A near-zero coefficient is a valid, informative result and the backtest must be free to report it.

**Why start this simple.** A WNBA season is ~250–300 games league-wide — far fewer per team or per market type. Complex models memorize small datasets and generalize badly. This is the baseline every future model must beat *out-of-sample* before earning its complexity. Do not add ML here.

To convert a projected total into a probability for a given line, you need a **standard deviation** of game totals, not just a mean. Compute it from `team_game_logs` rather than hardcoding.

Measured baseline for sanity-checking your computation: on 2023–2025 regular-season data (769 games), WNBA game totals have **mean 164.0, σ 17.3**. If your computed σ lands far outside ~15–18, suspect a bug (double-counting each game from both teams' rows is the likely culprit — dedupe on `espn_game_id`).

Then:

```
P(total > line) = 1 - Φ((line - projected_total) / σ)
```

Make `σ` estimation explicit and configurable; it drives every probability the system emits.

### B. Ladder curve fit — `strategies/wnba_totals/model/curve_fit.py`

Polymarket lists a **ladder** of totals on one game — Over 173.5, 176.5, ..., 197.5 — each with its own price. Those prices trace a cumulative distribution. Fit a normal to recover **the market's** implied mean and σ:

```python
def fit_ladder(points: list[tuple[float, float]]) -> LadderFit:
    """[(line, implied_prob_over), ...] -> (implied_mean, implied_stdev, fit_quality)"""
```

Use `scipy.optimize` to minimize squared error between observed probabilities and `1 - Φ((line - μ)/σ)`.

This lets you compare your projection to the market's projection **in the same units** (points), instead of comparing a point estimate to a probability. A 4-point gap in implied mean is far more interpretable than a 6% gap in probability.

## Data quality guards (important)

Ladder prices come from real books with real problems:

- **Filter wide spreads.** A rung showing `bid 0.03 / ask 0.39` carries no information. Drop rungs whose spread exceeds a configurable threshold (start ~10¢) before fitting.
- **Use mid prices** — `(bid + ask) / 2` — for implied probability, and record the spread alongside.
- **Enforce monotonicity.** P(Over) must be non-increasing as the line rises. Violations mean stale quotes; flag and either drop the offending rungs or refuse the fit.
- **Require a minimum rung count** (start ~4) for a meaningful fit.
- **Report fit quality** (R² or RMSE). A poor fit means the ladder isn't normal-shaped and the implied mean shouldn't be trusted.

## Output

A typed `Prediction` per market:
- `model_probability`, `model_fair_value` (price 0–1)
- `market_bid`, `market_ask`, `market_mid`
- `edge` = model probability − market mid
- `features` — the full input snapshot, for reproducibility
- `model_version` — bump on any logic change so the prediction log stays interpretable
- `model_config` + `config_hash` — the full config snapshot and its deterministic hash
- `reduced_confidence`, `confidence_notes`

Handle all three market types: totals, spreads, moneyline.

### Model version

Set **`MODEL_VERSION = "v2"`** — the record modifier is a genuine logic change from the v1 PPG-only baseline.

No historical predictions exist yet, so nothing needs migrating; this matters going forward, not retroactively. But it must land *with* this change, not after, or the first runs will be mislabelled.

`model_version` alone does not protect you: it's a hand-bumped constant, and tuning `β`, the Pythagorean exponent, or shrinkage `k` in `config.py` would change the model without changing the version. That's what `config_hash` is for — see `/goal:schema`.

## Requirements

- Pure and deterministic — same inputs, same output, always. The backtest must replay exactly.
- No network calls and no `datetime.now()` inside the model. Time comes in as `as_of`.
- `model_version` as a module constant, bumped on logic changes.
- Refuse to predict when features are too thin (`min_games_required` from `/goal:features`), rather than emitting a confident bad number.

## Tests

1. Known features → hand-computed projection matches
2. Synthetic ladder from a known (μ, σ) → `fit_ladder` recovers them within tolerance
3. Non-monotonic ladder is detected
4. Wide-spread rungs are excluded
5. Determinism: same inputs twice, identical output
6. **Totals are unaffected by the record modifier** — vary `record_residual` across its full range and assert the totals projection is bit-identical
7. **Playoff down-weighting applies** — the same matchup as a playoff game produces a smaller record adjustment than as a regular-season game, and sets `reduced_confidence`
8. **`β = 0` is a no-op** — with the coefficient zeroed, spread/ML projections match the v1 PPG-only baseline exactly

## Done when

- A fair value is produced for every current WNBA market
- Ladder fit on real Polymarket data returns a plausible implied mean (within a few points of the mid-ladder line) and σ near the measured ~17.3
- Recovers known parameters from synthetic ladders
- Model refuses to predict on insufficient data instead of guessing
- `MODEL_VERSION` is `v2`, and every prediction carries `config_hash`
- The record modifier moves spread/ML projections and leaves totals untouched
- The fitted `β` is reported with a confidence interval, not silently embedded
