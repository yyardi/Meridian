# PostgreSQL

**Role:** the system of record. Market snapshots, game logs, odds, predictions, outcomes.

## Why Postgres

| Alternative | Why not |
|---|---|
| SQLite | Can't be shared with an always-on remote recorder writing from a different host |
| Time-series DB (Timescale, Influx) | Overkill. ~100 rows/cycle × 96 cycles/day ≈ 10k rows/day — Postgres handles this without noticing |
| MongoDB | We want joins and constraints. The unique constraint on `(market_slug, captured_at)` is what makes the recorder idempotent |

Postgres also gives exact decimal arithmetic, which turns out to be load-bearing.

## NUMERIC, never floating point

**Every price and quantity is `NUMERIC`. This is not stylistic.**

IEEE-754 binary floats cannot represent `0.01` exactly:

```python
>>> 0.1 + 0.2
0.30000000000000004
>>> sum([0.01] * 100) == 1.0
False
```

Contract prices move in 1¢ ticks and P&L is accumulated over thousands of fills. Float drift compounds into real accounting errors, and — worse — into a backtest that disagrees with reality for reasons you can't see.

```
best_bid  NUMERIC(6,4)   -- 0.0000 to 1.0000, exact
quantity  NUMERIC(18,4)
line      NUMERIC(8,2)   -- 144.50
```

`tests/test_schema_roundtrip.py` introspects the live database and fails if any approximate column type ever appears. The rule is enforced, not documented.

Python side: prices arrive as strings (`"0.9100"`) and are parsed to `Decimal`, never `float`.

## timestamptz everywhere, UTC

All timestamps are `timestamptz` stored in UTC. WNBA games are US-scheduled, the recorder runs in a cloud region, and you'll analyse from a laptop in a third zone. Naive local timestamps are a reliable source of off-by-hours bugs that look like real signal.

Convert to local only at display time.

## Indexes

Indexed on what the backtest actually filters:

| Table | Index | Serves |
|---|---|---|
| `market_snapshots` | `(market_slug, captured_at)` | one market's price history |
| `market_snapshots` | `captured_at` | "everything at time T" |
| `team_game_logs` | `(team_id, game_date)` | the `as_of` query |
| `team_game_logs` | `season_type` | excluding preseason |
| `predictions` | `(model_version, config_hash)` | performance grouping |

## Idempotency via constraints

```sql
UNIQUE (market_slug, captured_at)   -- uq_snapshot_market_time
```

The recorder inserts with `ON CONFLICT DO NOTHING`. A crash mid-cycle followed by a rerun re-inserts the same rows harmlessly. Correctness comes from the database, not from application-level bookkeeping that can drift.

## Stock Postgres only

No extensions, no vendor features. The same schema runs on local Docker, Supabase, AWS RDS, or a €4.49 Hetzner box. Since cloud credits expire, portability is a requirement — see [hosting.md](../infra/hosting.md).

## Local development

```bash
docker compose up -d
```

Postgres 16 on host port **5433** (not 5432, to avoid colliding with any local install).
