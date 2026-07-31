---
description: Deploy the recorder to always-on hosting with Supabase Postgres
---

# Goal: Deployment

Deploy **Meridian**'s recorder to always-on hosting. Build unit **12 of 12**, depends on `/goal:recorder`. Read `README.md` first.

**Run this early — right after `/goal:recorder`.** Market snapshots are unrecoverable: every night the recorder isn't running is line movement that no longer exists anywhere. Stats and odds can be backfilled at any time; snapshots cannot. This is the one piece where delay has a permanent cost.

## Target setup

| Component | Choice | Cost |
|---|---|---|
| Postgres | **Supabase Pro** (YC credits) | $0 on credits → $25/mo |
| Recorder host | **AWS t4g.small** (Activate credits) | $0 on credits → ~$12/mo |
| Fallback | Hetzner CX22, both on one box | ~€4.49/mo |

### ⚠️ Supabase must be Pro, not Free

The **free tier pauses after 7 days of inactivity**, which would silently kill the recorder — and you'd likely notice only when a backtest came up short weeks later. Credits put you on Pro, which doesn't pause. Verify the project is actually on Pro before relying on it.

### Portability is a requirement, not a nice-to-have

Credits expire. Use **stock Postgres only** — no Supabase-specific extensions, no vendor auth, no edge functions. Connect via plain `DATABASE_URL`. When credits run out, moving the whole system to a €4.49 Hetzner box must be a config change, not a rewrite.

## Task

### 1. Containerize
- `Dockerfile` for the recorder (slim Python 3.10+ base)
- `docker-compose.yml` for local dev with local Postgres
- Same image runs locally and in production; only env differs

### 2. Scheduling
Adaptive cadence from `/goal:recorder`: 15 min within 6h of tip-off, 60 min otherwise. Either an internal scheduler in a long-running process, or systemd timers / cron. **Prefer a long-running process with an internal scheduler** — fewer moving parts, and it can hold rate-limiter state across cycles.

### 3. Migrations on deploy
`alembic upgrade head` runs before the recorder starts. Never hand-run migrations against production.

### 4. Monitoring — the part that actually matters

The dominant failure mode is **silent death**: the recorder stops at 2am, nobody notices for two weeks, and that data is gone forever. So:

- **Heartbeat** — write a timestamp each successful cycle
- **Staleness alert** — alert if no snapshot has been written in >2× the expected interval. This is the single most important alert in the system.
- **Health endpoint** or a status query (`SELECT max(captured_at) FROM market_snapshots`)
- Structured logs shipped somewhere durable, not just the container's stdout
- Alert on repeated API failures and on DB connection loss
- Auto-restart on crash (`restart: unless-stopped`, or a systemd unit)

Keep alerting cheap and simple — email or a webhook is fine. It just has to reach you.

### 5. Secrets
- `DATABASE_URL` and any Polymarket keys via environment, never in the image
- `.env` gitignored; `.env.example` committed
- Never log secrets

### 6. Backups
Supabase Pro includes automated backups — **verify they're enabled**. Also add a periodic `pg_dump` to object storage. The prediction log and snapshot history are irreplaceable; a season of recorded line movement cannot be reconstructed at any price.

## Deliverables

- `Dockerfile`, `docker-compose.yml`, `.dockerignore`
- `deploy/` with setup instructions for AWS + Supabase
- `deploy/RUNBOOK.md`: how to deploy, check health, read logs, restart, restore from backup, and migrate off Supabase when credits expire
- Health-check script

## Requirements

- Recorder survives reboots (auto-restart configured)
- Timezone handling explicit — store UTC everywhere; WNBA games are US-scheduled and this is a real source of off-by-hours bugs
- Graceful shutdown: finish the in-flight cycle, don't corrupt a partial write
- Resource limits set so a leak can't take the box down

## Done when

- Recorder runs on the remote host, writing to Supabase Pro
- Rows keep appearing for 24h+ unattended, across a reboot
- `SELECT max(captured_at)` from a laptop shows fresh data
- Killing the container auto-restarts it
- Staleness alert fires when the recorder is deliberately stopped
- Runbook is complete enough to recover without re-deriving anything
- A `pg_dump` restore has actually been tested, not just configured
