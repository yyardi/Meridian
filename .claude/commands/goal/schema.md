---
description: Build the Postgres schema and Alembic migrations for Meridian
---

# Goal: Database schema

Build the Postgres schema and migration setup for **Meridian**, a WNBA prediction-market trading system. This is build unit **1 of 12** — nothing exists yet. Read `README.md` in the repo root first; it documents the architecture, the API surfaces, and the design rules.

## Context you need

Meridian records Polymarket US market prices over time, fetches free stats/odds from ESPN, predicts fair values, logs every prediction, and backtests them. This unit builds only the storage layer.

## Task

Set up `core/storage/` with SQLAlchemy models and Alembic migrations for these tables:

### `market_snapshots`
One row per market per poll. The time series of Polymarket prices.
- `id`, `captured_at` (timestamptz, indexed)
- `market_slug`, `market_id`, `event_slug`, `event_id`, `game_id`
- `sports_market_type` (`basketball_team_full_game_total` / `_spread` / `_winner`)
- `line` (NUMERIC, nullable — moneyline has none)
- `best_bid`, `best_ask` (NUMERIC(6,4))
- `min_tick_size`, `min_trade_qty`, `fee_coefficient`
- `game_start_time`, `is_live`, `event_score`, `event_period`
- `raw` (JSONB — keep the whole payload; schemas change and reparsing beats re-fetching)

### `book_levels`
Order book depth per snapshot. Separate table — depth is many rows per snapshot.
- `id`, `snapshot_id` (FK), `side` (`bid`/`offer`), `price`, `quantity`, `level_index`

### `team_game_logs`
**Immutable one row per team per game.** Never store season aggregates — see the no-lookahead rule below.
- `id`, `game_date` (indexed), `season`, `espn_game_id`, `team_id`, `team_abbrev`, `opponent_id`, `opponent_abbrev`
- `is_home` (bool), `points_scored`, `points_allowed`, `is_completed`
- `season_type` (smallint, indexed) — **`1` = Preseason, `2` = Regular Season, `3` = Postseason**
- Unique constraint on `(espn_game_id, team_id)`

`season_type` is load-bearing in two places, so it is not optional:
- **Preseason (1) must never be written** — it would pollute both PPG and win-loss record
- **Postseason (3)** drives the playoff down-weighting of the record feature (see `/goal:features`)

These values come straight from ESPN's `event.seasonType.id`, which is present on every event. No date heuristics.

### `sportsbook_odds`
ESPN sportsbook lines, live and historical.
- `id`, `espn_game_id` (indexed), `game_date`, `provider_name`, `captured_at`
- `spread`, `over_under`, `over_odds`, `under_odds`, `home_moneyline`, `away_moneyline`
- `open_total`, `close_total` (nullable — only 2024+ has these)
- `is_closing_line` (bool), `raw` (JSONB)

### `predictions`
Every model output, forever. The long-run dataset.
- `id`, `predicted_at` (indexed), `model_version` (indexed), `strategy`
- `market_slug`, `event_slug`, `game_id`, `sports_market_type`, `line`
- `model_probability`, `model_fair_value`, `market_bid`, `market_ask`, `market_mid`
- `edge` (model vs market), `features` (JSONB — snapshot of inputs, for reproducibility)
- `model_config` (JSONB) — **full config snapshot at prediction time**
- `config_hash` (text, indexed) — **deterministic hash of `model_config`**
- `reduced_confidence` (bool, default false), `confidence_notes` (text, nullable)
- `resolved_outcome` (nullable, filled later), `resolved_at`, `was_correct`

**Why `model_version` alone is not enough.** `model_version` is a hand-bumped module constant. Tunable parameters live in `strategies/wnba_totals/config.py` — decay half-life, shrinkage `k`, the Pythagorean exponent, the record coefficient. Changing any of those silently changes the model *without* bumping `model_version`, so two materially different models would share a version tag and the backtest would average them together.

Hashing the actual config makes that impossible by accident. The backtest groups on `(model_version, config_hash)` and refuses to aggregate across differing hashes. Same structural-guarantee philosophy as the no-lookahead rule: don't rely on remembering to bump a constant.

`model_config` stores the readable snapshot; `config_hash` is the index you group by. The hash must be **deterministic** — sort keys, canonical JSON encoding — so identical configs always hash identically across processes and machines.

### `resolved_outcomes`
Ground truth from Polymarket settlement.
- `id`, `market_slug` (unique), `event_slug`, `game_id`
- `settlement` (0 or 1), `resolved_at`, `final_score_home`, `final_score_away`, `actual_total`

## Requirements

- **All prices/money as `NUMERIC`, never `FLOAT`.** Prices `NUMERIC(6,4)`, quantities `NUMERIC(18,4)`. Floats can't represent `0.01` exactly and drift over many rows.
- All timestamps `timestamptz`, stored UTC.
- Index anything the backtest filters on: `captured_at`, `game_date`, `market_slug`, `predicted_at`, `model_version`.
- Alembic configured and an initial migration generated.
- `DATABASE_URL` from env, never hardcoded. Include `.env.example`.
- Add a `docker-compose.yml` with a local Postgres so this runs without cloud setup.
- Stock Postgres only — no vendor-specific extensions. This must run identically on Supabase, AWS RDS, or a €4.49 Hetzner box.

## Design rule: no lookahead, enforced structurally

`team_game_logs` stores immutable per-game rows so that every statistic is derived `as_of` a date, from games strictly before it.

Do **not** create a `team_season_stats` table that gets overwritten nightly. If you did, a backtest of a July 15 game would silently read September's numbers and produce results that look fine but are worthless. Structure makes the bug unwritable.

## Done when

- `alembic upgrade head` creates every table against the Compose Postgres
- `alembic downgrade base` cleanly reverses it
- A short `python -c` snippet inserts and reads back one row per table
- No `FLOAT` anywhere in the schema (`grep -ri float core/storage/` comes back clean)
- `team_game_logs.season_type` exists and is indexed
- `predictions` has `model_config`, `config_hash`, `reduced_confidence`, `confidence_notes`
- The config-hash helper is deterministic: hashing the same dict twice (in separate processes) yields the same value, and reordering its keys does not change it
