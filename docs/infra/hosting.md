# Hosting and costs

**Current recurring cost: \$0.** All data sources are free; compute and database run on startup credits.

## Target setup

| Component | Choice | Cost now | Cost after credits |
|---|---|---|---|
| Postgres | Supabase **Pro** (YC credits ~\$3k/12mo) | \$0 | \$25/mo |
| Recorder host | AWS `t4g.small` (Activate credits) | \$0 | ~\$12/mo |
| Data (all sources) | Polymarket gateway + ESPN | \$0 | \$0 |

## ⚠️ Supabase must be Pro, not Free

The **free tier pauses after 7 days of inactivity.** For a recorder this is a silent, total failure: the process keeps running, writes start failing, and you find out weeks later when a backtest comes up short.

Credits put you on Pro, which doesn't pause. **Verify the project is actually on Pro** before relying on it.

## Portability is a requirement

Credits expire. So:

- Stock Postgres only — no Supabase extensions, no vendor auth, no edge functions
- Connect via plain `DATABASE_URL`
- Everything in Docker

When credits run out, moving to a **Hetzner CX22** (2 vCPU / 4 GB, ~€4.49/mo) running both the recorder and Postgres on one box is a config change, not a rewrite. That's the entire system for under €5/month.

## Rejected alternatives

| Option | Cost | Why not |
|---|---|---|
| The Odds API | \$30/mo | ESPN provides the same data free |
| SportsDataIO | sales-quoted | no public pricing, overkill |
| Neon Postgres | ~\$77/mo always-on | compute-hour pricing punishes 24/7 workloads |
| Supabase Free | \$0 | **pauses after 7 days** |
| Fly.io | \$2–25/mo | free tier removed in 2024; AWS credits are better |
| stats.wnba.com | \$0 | blocks datacenter IPs; ESPN is more reliable |

## Monitoring — the part that actually matters

The dominant failure mode is **silent death**. Design monitoring around that, not around CPU graphs.

| Signal | Purpose |
|---|---|
| **Staleness alert** | no snapshot in >2× expected interval — *the single most important alert* |
| Heartbeat | timestamp written each successful cycle |
| Status query | `SELECT max(captured_at) FROM market_snapshots` |
| Auto-restart | `restart: unless-stopped` or a systemd unit |
| Error-rate alert | repeated API failures, DB connection loss |

Alerting can be email or a webhook. It only has to reach you.

```bash
python -m core --status     # snapshots: 291 / most recent: 2026-07-31 21:37:11+00
```

## Backups

Supabase Pro includes automated backups — **verify they're enabled**, and add a periodic `pg_dump` to object storage.

The prediction log and snapshot history are irreplaceable. A season of recorded line movement cannot be reconstructed at any price, from anyone. **Test a restore**, don't just configure one.

## Local development

```bash
docker compose up -d          # Postgres 16 on port 5433
alembic upgrade head
python -m core --once         # single cycle
python -m core                # run forever
```

Measured: ~97 markets and ~1,750 book levels per cycle, ~9 seconds, ~98 requests at ~10.9 req/s (ceiling is 20).

## Secrets

`DATABASE_URL` and Polymarket keys come from the environment, never the image. `.env` is gitignored; `.env.example` is committed. Never log them.

Polymarket credentials are needed **only** for the executor — the whole data layer runs unauthenticated.
