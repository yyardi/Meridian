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

Run these four, in order, from `/Users/yayardia/Documents/Quant/Meridian`.

**1. Stop the Mac sleeping** — snapshots are unrecoverable; a sleeping laptop is
a hole in the record that nothing can backfill.

```bash
nohup caffeinate -dims > /dev/null 2>&1 &
```

**2. Start the background services**

```bash
docker compose up -d
```

**3. Start the dashboard**

```bash
nohup .venv/bin/uvicorn core.api:app --host 127.0.0.1 --port 8008 > /tmp/meridian-dashboard.log 2>&1 &
```

**4. Check it all worked**

```bash
.venv/bin/python scripts/health.py
```

Then open **<http://localhost:8008>**.

Step 4 must say `Verdict: ALL GOOD`. If it doesn't, the red lines say what is
broken and there is no need to guess.

## Watch the data arrive

The dashboard shows the *model's* view. These show the raw rows landing.

```bash
.venv/bin/python scripts/watch.py
```

The **200ms tick recorder**, refreshed every 2 seconds. During a live game the
`rows/min` counter should be in the hundreds. **If it reads 0 while a game is on,
recording is dead and that data is gone for good.**

```bash
.venv/bin/python scripts/watch.py --slow
```

The same view of the 15-minute pregame recorder — the one the dashboard reads.

`Ctrl-C` stops either.

## What `nohup ... &` means

Steps 1 and 3 above are wrapped in it. Three separate pieces:

| Piece | Does |
|---|---|
| `&` | run in the background and give the prompt back |
| `nohup` | keep running after the terminal is closed |
| `> /tmp/x.log 2>&1` | send output to a file instead of the screen |

Running `caffeinate -dims` **without** the wrapper works exactly as well — it
just occupies that terminal window until `Ctrl-C`, so the window has to stay
open. The wrapper only frees the window.

## Other commands

| Command | Does |
|---|---|
| `docker compose up -d --build` | **use instead of step 2 after any code or schema change** |
| `docker compose ps` | are the containers up |
| `docker compose logs scheduler --tail 50` | why predictions aren't appearing |
| `docker compose logs live-recorder --tail 50` | why tick data isn't appearing |
| `docker compose restart scheduler` | nudge a stuck job |
| `pmset -g assertions` | confirm the sleep guard is actually held |
| `pkill caffeinate` | let the Mac sleep again |
| `pkill -f uvicorn` | stop the dashboard |
| `.venv/bin/python -m pytest -q` | run the 464 tests |

> **`--build` is not optional after a schema change.** Skipping it once put the
> recorder in a crash-loop — its Alembic could not find the new revision.

## Gotchas that have already cost data

**The dashboard is not a container.** `docker compose` does not start it and will
not restart it. Nine times out of ten a dead UI means step 3 was never run, or
its terminal was closed. Run step 3 again.

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
| `/picks` | Today's picks as trade tickets, and resolved results |
| `/analytics` | CLV, calibration, equity charts |

Localhost only and **unauthenticated by construction** — it must not be exposed to a
network. Read-only today: there is no write endpoint and no order path in
[`core/api.py`](core/api.py).

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
