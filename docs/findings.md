# Findings log

Things we learned by running the system, not by planning it. **Append here whenever
something turns out to be wrong, surprising, or different from what the docs claim.**

Three kinds of entry, kept apart on purpose:

- **Venue facts** — how Polymarket US actually behaves. These constrain strategy.
- **Bugs** — what broke, what it cost, what would have caught it.
- **Corrections** — claims made in this project that turned out to be false.

The third section matters most. A wrong number that nobody retracts gets built on.

---

## 1. Venue facts

Measured on the live board, not assumed.

| # | Finding | Measured | When | Consequence |
|---|---|---|---|---|
| V1 | **Depth at the touch is tiny** | \$5 under 20¢ · \$24 at 20–35¢ · \$118 at 35–65¢ | 2026-08-02 | Cheap contracts cannot absorb size. A \$50 order at 16¢ is 10× the book |
| V2 | **Tick size is 1¢ everywhere** | tick 0.01, min qty 0.01, **96 / 96 markets** | 2026-08-02 | 16.1¢ is not a placeable price. No sub-cent queue jumping. At 16¢ one tick is **6.25%** of contract value |
| V3 | **Cheap contracts move less often** | 7¢ move hit **57%** of the time under ~20¢ vs **88%** near-money | 2026-08-02 | The exit the model assumes is far less likely on exactly the rungs it prefers |
| V4 | **Spread blows out in-game** | 3.1% of live ticks >10¢ · 0.6% >25¢ · worst 50¢ · Q4 p90 (9¢) fatter than Q1–Q3 (7¢) | 2026-08-02 | Quoting into Q4 is quoting into the gap. Gates hypothesis #5 |
| V5 | **In-game price travel** | moneyline 35.5¢ median vs 48¢ for ladder rungs, n=4 games | 2026-08-02 | Weak — one ML market per game against ~9 rungs, and a median washes out close games |
| V6 | **ESPN publishes no live in-game odds** | measured directly | 2026-08-01 | There is no book leg to compare against during a game. [infra/live-odds.md](infra/live-odds.md) |
| V7 | **Polymarket US MLB is 1¢ wide with half-cent ticks** | 30 events, 405 markets | 2026-08-01 | No venue gap in MLB. Decided we stay WNBA. [roadmap.md](roadmap.md) |
| V8 | **Network RTT to the venue is 36ms; our detection is 161ms** | | 2026-08-02 | Our poll loop, not the network, is the latency floor. Write latency still unmeasured — it gates QUOTE. [math/write-latency.md](math/write-latency.md) |

### What V1–V3 mean together

The model's edge concentrates on deep out-of-the-money rungs. Those rungs have
**\$5 of depth, a 6.25%-of-value minimum tick, and a 57% chance of ever reaching the
exit.** Each is survivable alone. Together they say the measured edge sits on the
half of the board that cannot be traded at size.

This is not a modelling problem and no amount of model work fixes it. Either the
edge has to appear nearer the money, or size stays at a few dollars per rung.

---

## 2. Bugs

Every one of these was free because nothing traded. That property is the reason
the list is a curiosity rather than a P&L.

| # | Bug | Cost | Root cause | What would have caught it |
|---|---|---|---|---|
| B1 | **`max(captured_at)` silently killed the pipeline** | 2.5 hours of no predictions, `job_ok` logged throughout | A single global max broke the moment a second writer with a different cadence existed | An alert on *predictions written*, not on job exit status |
| B2 | **Board query returned 1 game of 12** | dashboard wrong, invisible | Same root cause as B1, different query | Same |
| B3 | **Connection pool exhaustion (`EMAXCONNSESSION`)** | recorder crash-loop | SQLAlchemy defaults 5+10 **per engine**; Supabase allows 15 **project-wide** | Knowing the pooler's limit is per-project. Now capped at 2+1 and routed to the transaction pooler |
| B4 | **Injury insert `CompileError`** | recorder dead on deploy | Multi-VALUES insert compiles one statement for the batch; rows with different key sets fail | A test with a mixed batch. Written after the fact |
| B5 | **`Cleared` rows lost `team_id`** | would have left recovered players "Out" forever | Reads filter by team; a synthetic row without one is unreachable | A test that clears a player and then reads them back |
| B6 | **Test fixture deleted real data** | genuine rows wiped from the local mirror | Fixture teardown was `delete where source='espn_injuries'` | Scoping test writes to a `TEST_SOURCE`. Fixed |
| B7 | **Supabase parameter limit (65535)** | sync failed | 5,000-row chunks × 23 columns exceeds the wire limit | Deriving chunk size from column count. Fixed |
| B8 | **Recorder crash-loop after a migration** | ~2 min outage, no data lost | Restarted the container without `--build`, so its Alembic could not find the new revision | **Always `docker compose up -d --build` after a schema change** |
| B9 | **`/api/status` took 3.2s** | dashboard sluggish | `count(*)` on tables growing 5 rows/sec | Now 9ms |
| B10 | **Live path never applied shrinkage** | v2/v3 overstated every edge ~4× | The backtest shrank; the live path did not. Two code paths, one of them wrong | Fixed in v4. The version bump is mandatory — `config_hash` would otherwise blend two model generations |
| B11 | **Transaction-pooler rewrite killed the 200ms recorder for 23 hours** | **2 games of tick data, unrecoverable** | `app_database_url()` matched on port `:5432/` alone, not on the host being Supabase, so it rewrote the *local* recorder's URL to 6543 where nothing listens | Fixed: rewrite now requires a Supabase host. See below — the test that should have caught it passed vacuously |

### B11 in detail — three failures stacked

**The bug.** `app_database_url()` rewrote any URL containing `:5432/` to `:6543/`. Its
own docstring said "rewrites *Supabase's* session port"; the code never checked the
host. `docker-compose.yml` gives the live recorder
`postgresql+psycopg://meridian:meridian@postgres:5432/meridian` — local Postgres,
standard port — so every tick write became `Connection refused`.

**The test that passed vacuously.** `test_local_urls_are_never_rewritten` existed and
was green. It used `localhost:5433`, which never contained `:5432/`, so it could not
fail no matter what the function did. **A test for the right idea, written against a
URL that could not exercise it.** Now asserts both forms.

**Why nothing alerted.** Two compounding reasons:

1. [`core/api.py`](../core/api.py) deliberately excludes the live recorder from the
   health verdict — it is legitimately silent between games, so failing on its age
   would show STALE every night. Correct reasoning, but it makes *dead for a day*
   and *idle at 3pm* indistinguishable.
2. `/api/status` queries **Supabase**, while the live recorder writes **locally**.
   Since the repoint, `live_age_seconds` has been describing a writer that no longer
   writes there. The number was not stale — it was meaningless.

**The fix that is still needed:** the live recorder must emit a heartbeat on every
cycle whether or not a game is in progress, written where the health check can see
it. Then "no heartbeat in 2 minutes" means dead, unambiguously, and silence between
games stops being a valid excuse for silence during them.

**Coverage lost:** local ticks ran to 2026-08-03 04:16 UTC and resumed 2026-08-04
03:02 UTC. The 2026-08-03 evening games — the two that were traded live — have no
200ms data. PULSE Tier 1 stayed at 3 games instead of reaching 5.

### The pattern in B1, B2 and B10

All three are **the same shape**: a computation that was correct once, then quietly
stopped being correct when the world around it changed. None of them threw. All of
them logged success.

The countermeasure is not more tests. It is **asserting on outputs rather than on
exit codes** — predictions written per hour, games on the board, mean shrinkage
applied — so that "ran fine, produced nothing" is loud.

---

## 3. Corrections

Claims made during this project that were wrong, and what is true instead.
**Do not delete entries here.** A retracted number that vanishes gets re-derived.

| # | The claim | Why it was wrong | What is true |
|---|---|---|---|
| C1 | "77% of frames differ, so 200ms recording is justified" | The statistic rises monotonically with sampling interval **by construction** — it measures the interval, not the market | Changes-per-second is the honest metric. The faster cadence is still justified, on different grounds |
| C2 | "Capacity is not the constraint — \$469k is resting" | That was total across **all** levels of **all** markets | At the touch, on the model's actual picks: **\$5–\$24**. See V1 |
| C3 | "Put the sell order in now" | You can only sell contracts you already hold | The sell is placed after the buy fills, not alongside it |
| C4 | "Row-level confidence intervals" on tick data | Rows within a game are not independent | Sample size is **games**. Row-level CI measured at **11% coverage** against a nominal 95%. [math/clustered-errors.md](math/clustered-errors.md) |
| C5 | "94% hit rate" quoted as performance | The live log includes the no-edge control group by design | Bet win rate on actionable rows only. v2/v3 measured **38.5%** over 5 games |
| C6 | Moneyline exclusion treated as a general result | It is a **pregame forecasting** result: market margin MAE 9.65 beats ours 10.19 | It says nothing about a latency strategy. `PULSE_MARKETS` is deliberately empty, to be set from PULSE's own measurements |

---

## 4. Open questions this log has raised

### Q1 — Is the headline CLV number measuring a tradable edge? ⚠️ **unresolved contradiction**

Two docs in this repo disagree, and the disagreement is load-bearing.

[STATUS.md](STATUS.md) reports the champion at **+1.75 CLV [+1.45, +2.06]** and calls
it "passes CLV gate" — it is the primary evidence that the model is worth anything.

[math/calibration-problem.md](math/calibration-problem.md) says, of the same metric
at an earlier model version:

> Do not read the +0.55 CLV as an edge. It is measured against the *opening* line,
> and it does not survive spread and fees.

**The code says the objection still applies.** In
[`core/backtest/engine.py:264`](../core/backtest/engine.py):

```python
entry   = float(chosen.open_total)    # the bet is entered at the sportsbook OPEN
closing = float(chosen.close_total)
...
clv = (closing_line - entry_line) if side == "over" else (entry_line - closing_line)
```

So +1.75 means *the model beats the sportsbook opening line*. Two problems with
reading that as edge:

1. **The open is the least efficient price of the day.** Beating it is a low bar,
   and the closing line is the accurate one.
2. **You cannot transact at the sportsbook open.** You trade Polymarket. The
   backtest measures model-vs-sportsbook; the money question is
   Polymarket-vs-sportsbook.

The number grew from +0.55 to +1.75 across model versions. **The methodological
objection did not go away with it, and nobody has re-stated whether it still holds.**

This needs settling before the +2.50% ROI figure in
[math/what-the-edge-is-worth.md](math/what-the-edge-is-worth.md) means anything —
that chain starts from +1.75.

### Other open questions

2. **Where does the edge live on the price axis?** V1–V3 say the tradable half of the
   board is 35–65¢. Nobody has measured whether the model has any edge there.
3. **What is write latency?** V8 leaves it unmeasured, and it decides whether QUOTE
   is possible at all. Blocked on the signing layer.
4. **Does the model's edge survive a 1¢ tick?** At 16¢ the tick is 6.25% of value —
   larger than most edges the model claims.

---

*Started 2026-08-03. Append, don't rewrite.*
