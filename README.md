# Meridian

An algorithmic trading system for WNBA prediction markets on **Polymarket US**.

This file is the entry point and nothing more. Everything of substance lives in
[`docs/`](docs/README.md) as short, single-topic documents.

**New here?** Read [docs/how-it-all-works.md](docs/how-it-all-works.md) — the whole
project in plain language, then the maths.

---

## Status — 2026-08-03

| | |
|---|---|
| **Model** | v4 (v3 + winner's-curse shrinkage in the live path) |
| **Real orders ever placed** | **0** |
| **Execution mode** | SHADOW, kill switch on, market orders unrepresentable |
| **Tests** | 464 |
| **Recurring cost** | \$0 |

**Data:** 839k market snapshots · 831k book levels · 3,290 team game logs · 18,145
player games · 12,658 sportsbook odds rows · 11,609 predictions (8,937 on v4) · 1,356
resolved · 1,333 shadow orders.

**Where we are stuck:** ANCHOR is at 4 games post-v4 and cannot be judged yet. PULSE's
two Tier-1 hypotheses both report NO DATA — 3 of 20 recorded games have 200ms
coverage. **The bottleneck is games, not code.**

> ⚠️ **Open problem:** the model's probabilities carry no demonstrable signal —
> ~50% realised across every confidence bucket, edge-vs-return correlation +0.001.
> [docs/math/calibration-problem.md](docs/math/calibration-problem.md). Do not size
> this live until resolved.

Full picture: [docs/STATUS.md](docs/STATUS.md) · what to build next:
[docs/next-build.md](docs/next-build.md) · what we got wrong:
[docs/findings.md](docs/findings.md).

---

## Start everything

**One terminal tab per thing, each left open.** Every tab shows its own logs and
stops with `Ctrl-C` in that tab. Nothing is hidden in the background.

All commands run from `/Users/yayardia/Documents/Quant/Meridian`.

### Tab 1 — keep the Mac awake

```bash
caffeinate -dims
```

Prints nothing and just sits there. That is correct. Snapshots cannot be
backfilled, so a sleeping laptop is a permanent hole in the record.

### Tab 2 — the services, with live logs

```bash
docker compose up
```

**No `-d`.** All eight containers stream their logs into this tab, so you can
watch the recorder and scheduler work. `Ctrl-C` stops all eight.

After changing code or the schema, use `docker compose up --build` instead.

**The dashboard is one of the eight** (`meridian-api`, since 2026-08-07) — open
**<http://localhost:8008>** once the stack is up. There is no separate uvicorn
tab any more: the host `nohup uvicorn` was the only component that died on
reboot, which is disqualifying on a machine that runs unattended. The fill
watcher lives inside that container and starts with it.

**So is the phone alerter** (`meridian-alerter`): the health checks below,
evaluated every 5 minutes, pushed to `ntfy.sh/$MERIDIAN_NTFY_TOPIC` on any
transition to DEAD, plus a 9:00 CT daily digest that always sends — a missing
digest means the alerter itself is dead. Subscribe to the topic in the ntfy
app before leaving the machine alone; test the channel with
`docker compose exec alerter python -m core.alerter --test`.

### Tab 3 — checks and live data

This tab stays free for one-off commands.

```bash
.venv/bin/python scripts/health.py
```

Must say `Verdict: ALL GOOD`. If not, the red lines say exactly what is broken.

```bash
.venv/bin/python scripts/watch.py
```

Live tail of the **200ms tick recorder**, refreshed every 2 seconds. During a
game the `rows/min` counter should be in the hundreds. **If it reads 0 while a
game is on, recording is dead and that data is gone for good.** Add `--slow` to
watch the 15-minute pregame recorder instead. `Ctrl-C` stops it.

## Stop everything

`Ctrl-C` in tabs 1 and 2. That is the whole procedure.

If something was started in the background and you have lost track of it:

```bash
./scripts/stop.sh
```

Stops the dashboard, the containers and the sleep guard wherever they are, then
verifies each one actually went away. Safe to run when things are already
stopped, and **it deletes no data** — every recorded row survives.

Recording stops too. Don't leave it off through a game.

## Running in the background instead

Only if you want to close the terminals. Prefix any of the above with `nohup`
and suffix with `&`:

```bash
nohup caffeinate -dims > /dev/null 2>&1 &
```

`&` backgrounds it, `nohup` keeps it alive after the terminal closes, and the
redirect sends output to a file instead of the screen. For containers the
equivalent is `docker compose up -d`, then `docker compose logs -f` to watch.
**For an unattended stretch (vacation), `docker compose up -d` is the right
mode** — `restart: unless-stopped` brings every container back after a crash
or reboot, and the alerter's startup push tells your phone the reboot happened.

**The cost is that you can no longer `Ctrl-C` any of it** — you need
`./scripts/stop.sh` or `pkill`. Prefer the tabs.

## Other commands

| Command | Does |
|---|---|
| `docker compose up --build` | **use instead of tab 2 after any code or schema change** |
| `docker compose ps` | are the containers up |
| `docker compose logs scheduler --tail 50` | why predictions aren't appearing |
| `docker compose logs live-recorder --tail 50` | why tick data isn't appearing |
| `docker compose logs kalshi-recorder --tail 50` | why Kalshi snapshots aren't appearing |
| `docker compose restart scheduler` | nudge a stuck job |
| `docker compose logs api --tail 50` | why the dashboard is misbehaving |
| `docker compose logs alerter --tail 50` | what the alerter last pushed |
| `docker compose exec alerter python -m core.alerter --test` | test push to the phone |
| `pmset -g assertions` | confirm the sleep guard is actually held |
| `pkill caffeinate` | let the Mac sleep again |
| `.venv/bin/python -m pytest -q` | run the tests |

> **`--build` is not optional after a schema change.** Skipping it once put the
> recorder in a crash-loop — its Alembic could not find the new revision.

## Gotchas that have already cost data

**The dashboard used to be a host process, and that cost a reboot's worth of
coverage.** Since 2026-08-07 it is the `meridian-api` container and restarts
with everything else. If the UI is dead now, `docker compose ps` — not a
terminal tab — is where to look.

**`caffeinate -s` only applies on AC power.** On battery the machine can still
sleep. `health.py` warns about this explicitly.

**`caffeinate` does not override the lid switch.** Closing the lid sleeps the
machine regardless of what is running — carrying the laptop between rooms stops
recording. There is no flag that fixes this. On a game night: **plugged in, lid
open.**

**The dashboard and the tick recorder use different databases.** The UI reads
Supabase; the 200ms recorder writes to local Postgres. A healthy-looking
dashboard says nothing about tick recording — that blind spot let the tick
recorder die for 23 hours unnoticed. `health.py` checks both, which is why it
exists.

### The dashboard pages

| Page | Shows |
|---|---|
| `/` | Live board — every market, model price, edge |
| `/picks` | Today's picks as trade tickets, and the game tape — click a game for every shadow trade in it |
| `/analytics` | CLV, calibration, equity charts |

Published on **all interfaces** (operator decision, 2026-08-07) so the dashboard
is readable over the tailnet while away — which also makes the unauthenticated
read endpoints reachable from the LAN. The one write path — the human-confirm
order endpoint — is separately gated by `MERIDIAN_ORDER_TOKEN` and fails closed
without it. Revert to `127.0.0.1:8008:8008` in docker-compose.yml when remote
access is no longer needed.

**Reading the edge column:** an edge is tradable only if the row is *actionable*.
Rows marked `reduced_confidence` are usually games the sportsbooks have not priced
yet — with no book line there is nothing to anchor against, so the number shown is
raw model opinion and is typically the largest and least trustworthy figure on the
page.

### Environment

```bash
DATABASE_URL=postgresql://...   # Supabase
MERIDIAN_TX_POOLER=1            # route to the transaction pooler (port 6543)
POLYMARKET_KEY_ID=...           # executor only
POLYMARKET_SECRET_KEY=...       # executor only
MERIDIAN_NTFY_TOPIC=...         # phone alerts — subscribe to it in the ntfy app
```

Never commit these. `.env` is gitignored.

---

## What it does

1. **Records** Polymarket US WNBA prices and full book depth, forever
2. **Fetches** team stats and sportsbook odds from free sources
3. **Predicts** a fair value for each market
4. **Logs** every prediction alongside the live market price
5. **Backtests** those predictions against what happened
6. **Sizes** hypothetical positions with fractional Kelly
7. **Shadow-trades** — logs what it would have done, places nothing

Execution on real money is the last milestone, gated behind a human confirm step and
a validated track record.

## Design rules — non-negotiable

1. **Limit orders only, enforced by construction.** No market-order code path exists.
   The type signature makes one unrepresentable.
2. **No lookahead, enforced by construction.** `as_of` is keyword-only with no
   default everywhere. [docs/math/point-in-time.md](docs/math/point-in-time.md)
3. **Log every prediction, forever.** Including the no-edge control group — which is
   why raw log hit rates are not performance.
4. **Start simple; add complexity only on evidence.** Every adopted change traces to
   a pre-registered gate. [docs/math/performance-targets.md](docs/math/performance-targets.md)
5. **Human in the loop.** Nothing reaches the venue without a person deciding.

## Layout

| Path | Contains |
|---|---|
| `core/` | recorder, feeds, predictions, executor, backtest, API |
| `core/pulse/` | in-game strategy research (replay engine, overreaction, first-score) |
| `core/quote/` | market-making research (adverse selection, depth signal) |
| `strategies/` | the WNBA totals model |
| `docs/` | everything explained — [start here](docs/README.md) |
| `tests/` | 464 tests |

## Reference

[Glossary](docs/glossary.md) · [Data sources](docs/infra/data-sources.md) ·
[Hosting and costs](docs/infra/hosting.md) · [Architecture](docs/infra/architecture.md) ·
[Tech stack](docs/README.md#stack)
