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

Run these three, in order, from `/Users/yayardia/Documents/Quant/Meridian`.

**1. Start the background services**

```bash
docker compose up -d
```

**2. Start the dashboard**

```bash
nohup .venv/bin/uvicorn core.api:app --host 127.0.0.1 --port 8008 > /tmp/meridian-dashboard.log 2>&1 &
```

**3. Check it all worked**

```bash
.venv/bin/python scripts/health.py
```

Then open **<http://localhost:8008>**.

Step 3 must say `Verdict: ALL GOOD`. If it doesn't, the red lines say what is
broken and there is no need to guess.

### If the UI is down

**The dashboard is not a container.** `docker compose` does not start it and
will not restart it. Nine times out of ten the UI being down means step 2 was
never run, or its terminal was closed. Just run step 2 again.

### Other commands

| Command | Does |
|---|---|
| `docker compose up -d --build` | **use this instead of step 1 after any code or schema change** |
| `docker compose ps` | are the containers up |
| `docker compose logs scheduler --tail 50` | why predictions aren't appearing |
| `docker compose logs live-recorder --tail 50` | why tick data isn't appearing |
| `docker compose restart scheduler` | nudge a stuck job |
| `.venv/bin/python -m pytest -q` | run the 464 tests |

> **`--build` is not optional after a schema change.** Skipping it once put the
> recorder in a crash-loop — its Alembic could not find the new revision.

### Before a game night

Run step 3. It checks containers, ESPN, book lines, the autonomous-order
counter, and **both databases** — the dashboard only ever sees Supabase, while
the 200ms tick recorder writes locally. That blind spot let the tick recorder die
for 23 hours while the UI looked perfectly healthy.

During a live game, the `local ticks (200ms)` line must show **seconds**. If it
shows hours while a game is on, tick recording is dead and the data is
unrecoverable.

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
