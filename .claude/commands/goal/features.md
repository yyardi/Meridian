---
description: Build the point-in-time feature engineering layer
---

# Goal: Point-in-time feature builder

Build the feature engineering layer for **Meridian**. Build unit **6 of 12**, depends on `/goal:backfill`. Read `README.md` first.

## The one rule that matters

**Every feature must be computed `as_of` a timestamp, using only games strictly before it.**

This is the single place where a backtest most easily lies to you. If a feature accidentally includes information from after the game, the backtest will show a fantastic edge that evaporates on live money. It will look completely plausible while doing so.

So the API is built to make lookahead hard to express:

```python
def build_features(team_id: int, as_of: datetime, session) -> TeamFeatures:
    """Every stat computed ONLY from games with game_date < as_of."""
```

There is no code path that computes "current season stats." `as_of` is mandatory, not optional and not defaulted to `now()`.

## Task

Build `strategies/wnba_totals/model/features.py`.

All features derive from `team_game_logs` (immutable one-row-per-team-per-game), filtered `game_date < as_of`.

### Feature set (from the project brief)

1. **Offense PPG** — mean `points_scored`
2. **Defense PPG allowed** — mean `points_allowed`
3. **Home/away splits** — both of the above, split by `is_home`
4. **Recent-form decay** — weighted mean favoring the last 5–10 games over the full season. Use exponential decay with a configurable half-life (start ~5 games). Rationale: a team's form in July says more about tonight than a game in May, but the full season still carries signal — so decay rather than truncate.
5. **Rest days** — days since that team's previous game
6. **Head-to-head** — prior meetings this season between these two teams
7. **Games played** — needed for the small-sample guard below

### Win-loss record (added post-v1)

**Source rows: regular season only (`season_type = 2`).** Preseason is never in the table; postseason is excluded here because *regular-season* record is the feature, even when predicting a playoff game.

- `wins`, `losses`, `win_pct`
- `pythagorean_win_pct` = `PF^k / (PF^k + PA^k)` over games before `as_of`
  - **`k` default `11.09`**, configurable. This was fit on 2023–2025 WNBA data (769 games, 37 team-seasons, RMSE 0.049 win%). Do **not** use the NBA's ~13.9 — it's materially wrong for this league. Ideally refit walk-forward rather than pinned.
- **`record_residual` = `win_pct − pythagorean_win_pct`** ← the feature that actually gets used
- `is_playoff_game` (bool) — a property of the game *being predicted*, true when its `season_type = 3`

**Why the residual instead of raw win%.** Raw win% is heavily collinear with point differential, which the model already has via offense/defense PPG. Feeding it in directly would double-count that information and destabilize coefficients on a ~250-game season. The residual is *by construction* the part of record that point differential cannot explain — close-game execution and clutch performance — so it's near-orthogonal to the existing features and behaves as a modifier rather than a competing signal.

Apply the **same shrinkage toward league average** used for PPG: a 3-game record is meaningless, and shrinkage degrades gracefully instead of producing wild early-season values. Respect `min_games_required`.

> **Scope limit — document this, don't imply otherwise.** The residual captures close-game execution and clutch. It does **not** capture strength of schedule. SOS requires opponent-adjusted PPG, which is a separate and larger change. Note it as a follow-up.

> **Expect this feature to be weak.** On 2023–2025 data the residual's spread across teams (4.9 win-% pts) is *smaller* than pure binomial noise for a 40-game season (7.9 win-% pts), implying no measurable persistent clutch skill. That is fine and expected: `/goal:fairvalue` fits its coefficient from data, so a noise feature drives the coefficient to zero and does no harm. Build it correctly and let the backtest settle it — do not hand-tune a coefficient to make it look useful.

### Small-sample handling

Early season, a team may have 2 games played. A mean over 2 games is noise.

Implement **shrinkage toward the league average**:
```
adjusted = (n × team_mean + k × league_mean) / (n + k)
```
where `k` is a configurable prior weight (start ~5 games). With few games you get roughly the league average; with many, roughly the team's own. This is a standard, defensible way to avoid over-trusting tiny samples — and it degrades gracefully instead of producing wild projections in April.

Expose a `min_games_required` threshold below which the model declines to predict at all.

## Requirements

- `as_of` is a **required** parameter everywhere. No defaults.
- Pure functions of (team, `as_of`, DB) — same inputs always give the same output. The backtest must be exactly replayable.
- Return a typed `TeamFeatures` dataclass/pydantic model, not a bare dict.
- Include `league_average` computation, itself `as_of`-correct.
- Config in `strategies/wnba_totals/config.py`: decay half-life, shrinkage `k`, `min_games_required`, **Pythagorean exponent (`11.09`)**.
- No pandas `.shift()`-style tricks for time alignment — filter in SQL by `game_date < as_of`. Explicit beats clever here.
- **All record features filter `season_type = 2`.** Getting this wrong (counting playoff or preseason games toward record) is a silent correctness bug, not a crash.

## Tests (this unit needs real tests)

Lookahead bugs are silent, so test for them directly:

1. **No-lookahead test** — build features `as_of` a mid-season date, then insert a later game, rebuild with the same `as_of`, assert the output is byte-identical.
2. **Determinism test** — same inputs twice, same output.
3. **Shrinkage test** — a team with 1 game sits near league average; with 30 games sits near its own mean.
4. **Rest-days test** — hand-built fixture with known dates.
5. **Empty case** — a team with zero prior games returns something sane or refuses to predict, and never divides by zero.
6. **Pythagorean sanity** — a team with `PF == PA` yields `pythagorean_win_pct == 0.5` exactly, for any `k`.
7. **Record excludes non-regular-season** — insert a postseason and a preseason game for a team; neither changes `wins`, `losses`, or `record_residual`.
8. **Residual sign** — a team outperforming its point differential has a positive residual, and vice versa.

## Done when

- All tests pass, especially no-lookahead
- Features for a mid-2025 game use only pre-that-date games (verify by hand against the DB)
- Requesting features for an early-season game with 1 prior game doesn't produce an absurd projection
- No function in this module can be called without `as_of`
- `record_residual` on a real 2025 team is small (roughly ±0.13) — a large value means non-regular-season games leaked into the record
- `is_playoff_game` is true for a known 2025 postseason game
