---
description: Build the prediction log and outcome resolution job
---

# Goal: Prediction log + resolution job

Build the prediction logging and resolution system for **Meridian**. Build unit **8 of 12**, depends on `/goal:fairvalue`. Read `README.md` first.

## Why this is the centerpiece

From the project brief: *the model bootstraps its own dataset.* Every fair value the model emits gets logged with the live market price and a timestamp; once the game resolves, the outcome is filled in.

That log **is** the real dataset. It compounds daily. The system must be able to answer, at any moment:

> "How would every prediction I've ever made have performed?"

Design for that question directly — it is the primary use case, not a reporting afterthought.

## Task

### A. Prediction logger — `core/predictions.py`

On each run:
1. Pull current markets from the latest `market_snapshots`
2. Build features `as_of` now
3. Generate fair values via `strategies/wnba_totals/model/`
4. Write one `predictions` row per market

Each row records the model price, the live market bid/ask/mid, the edge, the full feature snapshot (JSONB), `model_version`, **`model_config` + `config_hash`**, and **`reduced_confidence` + `confidence_notes`**.

**Compute `config_hash` at prediction time**, from the live config object — never from a hardcoded string. A deterministic canonical-JSON hash (sorted keys) so the same config always hashes identically across processes. This is what lets the backtest refuse to mix model generations; see `/goal:schema`.

Playoff predictions arrive from `/goal:fairvalue` with `reduced_confidence = true` — persist it rather than recomputing.

**Log every prediction, not just actionable ones.** Predictions with no edge are the control group — without them you can't tell whether the model is skilled or whether you just remember the winners. Store an `is_actionable` flag rather than filtering rows out.

### B. Resolution job — `core/resolution.py`

For finished games, fill in ground truth:

1. **Polymarket settlement** (authoritative, free, no key):
   ```
   GET https://gateway.polymarket.us/v1/markets/{slug}/settlement
   → {"slug":"...","settlement":0}     # 1 = Yes, 0 = No
   ```
2. **ESPN final scores** as a cross-check and for `actual_total`:
   ```
   GET https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard?dates=YYYYMMDD
   ```
3. Write `resolved_outcomes`; back-fill `resolved_outcome`, `resolved_at`, `direction_correct` on matching `predictions`.
4. **Reconcile the two sources.** If Polymarket settlement disagrees with what ESPN's final score implies, log a loud warning and do not silently pick one. Disagreement means either a data bug or a market resolution edge case, and both are worth knowing about.

### ⚠️ Joining Polymarket to ESPN — three verified hazards

There is **no shared identifier**. All three of these were confirmed against live data and each would silently break resolution:

**1. The IDs are different ID spaces.** Polymarket `gameId` is `13002440`; ESPN's is `401856953`. They are unrelated. You cannot join on ID.

**2. Team abbreviations differ.** Polymarket is lowercase and disagrees on two teams:

| Team | Polymarket | ESPN |
|---|---|---|
| Golden State | `gsv` | `GS` |
| Connecticut | `conn` | `CON` |
| *(all others)* | lowercase | uppercase |

Build an explicit mapping table. Do **not** rely on `.upper()` — it silently fails on exactly these two and you'd lose Golden State and Connecticut games without an error.

**3. Slug dates are US-local; ESPN `game_date` is UTC.** Market `aec-wnba-gsv-phx-2026-05-10` corresponds to an ESPN `game_date` of `2026-05-11 00:30:00+00`. Any evening game crosses midnight UTC, so an exact date join loses roughly half the schedule.

**Recommended join:** normalised team pair **+** a UTC time window around `startTime` (±24h), asserting exactly one match. Log and skip ambiguous matches rather than guessing — a wrong join attaches the wrong outcome to a prediction, which is worse than a missing one.

Verified example to test against: `aec-wnba-gsv-phx-2026-05-10` has `settlement = 1`, its `long=True` side is "Valkyries", and ESPN records Golden State beating Phoenix **95–79**. Settlement and reality agree.

### C. Performance query layer

Functions answering the core question, sliceable by **`(model_version, config_hash)`**, market type, date range, edge bucket, and season type:

- Hit rate, ROI, average edge
- **Calibration**: bucket predictions by predicted probability (0–10%, 10–20%, ...) and compare to realized frequency. A well-calibrated model's 70% predictions win ~70% of the time. This catches systematic over-confidence that hit rate alone hides. **Report regular season and playoffs separately** — playoff predictions carry `reduced_confidence` and shouldn't be blended into headline calibration.
- Cumulative P&L over time
- Edge decay: does predicted edge actually correlate with realized return?

**Grouping must default to `(model_version, config_hash)`.** Aggregating across different config hashes averages together materially different models and is the exact failure this schema exists to prevent. If a caller wants a cross-config view, it should be an explicit opt-in, not the default.

## Requirements

- Idempotent — the resolution job must be safe to run repeatedly.
- Never overwrite a resolved outcome once written.
- `model_version` on every row, so a logic change doesn't silently contaminate historical performance stats.
- Predictions are **append-only**. Never update a prediction's model price after the fact — that destroys the record's integrity.
- Handle unresolved/void markets gracefully (postponements happen).
- CLI: `python -m core.predictions --run` and `python -m core.resolution --backfill`.

## Done when

- A prediction run writes one row per current WNBA market with features attached
- The resolution job fills outcomes for finished games
- Polymarket settlement and ESPN scores agree (or disagreements are logged loudly)
- The performance query returns hit rate, ROI, and a calibration table
- Rerunning resolution changes nothing
- Filtering by `(model_version, config_hash)` correctly isolates each model generation
- **Changing any value in `config.py` produces a different `config_hash` on the next run**, and the two generations do not blend in performance queries
- Playoff predictions carry `reduced_confidence = true` and appear as a separate calibration cohort
