# QUOTE shadow run — registration

**Status: REGISTERED, NOTHING COMPUTED.** This document is written before the
engine's first cycle, and this section may not be edited after data accrues —
append below the line instead.

Module: `core/quote/engine.py` (shadow quoter) · `core/quote/report.py` (scoring)

## Why run a quoter whose measured edge is negative

The adverse-selection study already answered the naive question: in-game, a
resting quote loses **−2.74¢ per fill** (95% CI [−3.03, −2.44], 13 games) and
pregame **−0.86¢** ([−1.14, −0.58], 30 games) — C13's inputs. QUOTE stays
unbuilt as a strategy. So why build the shadow engine at all?

Because the study's numbers come from a *static* rule: a quote born at one
snapshot, marked at a fixed horizon, never requoted. A real maker requotes
when the touch moves, and requoting is the one behaviour the horizon method
cannot price — it may cut the adverse tail (you pull before the worst fills)
or worsen it (you chase the touch into every move). **The sign of requoting's
effect is not known, and this engine exists to measure it, not to assume it.**
If the requoting quoter still loses, QUOTE is dead twice and stays dead.

## What the shadow run measures — registered before first run

One shadow maker per quotable market (the adverse-selection study's own band:
mid ∈ [0.20, 0.80], spread ∈ [0.01, 0.15]): a bid resting at the venue's best
bid and an offer at the best ask, one contract each, requoted to the touch
every cycle. **No order exists anywhere in this** — fills are simulated from
the recorded stream by the study's own rule (mid reaching the quote), which
undercounts exactly the fills that hurt. That bias is signed: **a loss here
is trustworthy; a profit here is an upper bound and authorises nothing.**

Primary metric, per regime (pregame / in-game, tagged at quote birth):

* **Money at price, at settlement** (C11): each simulated fill is a unit
  position held to settlement — a filled bid is long YES at the quote price;
  a filled offer is short YES, i.e. the NO side at `1 − price`. Dollars
  staked → dollars returned, ROI, **clustered by game** (C4).
* Secondary, for comparability with the static study: mean net capture at the
  next observation (`s/2 + Δmid`), same clustering.

Floors, fixed now: **≥ 500 fills AND ≥ 10 games per regime**, else the report
prints NO DATA with counts only. No performance claim below the floor; no
metric added after data accrues counts as registered.

**PASS** (would reopen the QUOTE question, nothing more): settlement-scored
mean ROI > 0 with the game-clustered 95% CI excluding zero, in a named
regime, at floor. **FAIL**: floor met, CI at or below zero. Anything else is
NO DATA.

## Deliberate limitations, stated up front

* Runs against the **local tick database only** (v1): in-game quoting sees
  the 1s/200ms stream; "pregame" here means the pre-tip window that stream
  covers, not the daytime 15-minute sweeps (those live in the app database).
  A daytime-pregame arm is a separate, later run and may not be blended in.
* Fills are per-side and scored independently; there is no inventory netting.
  A real maker's P&L nets — this scores the raw material makers are made of.
* Settlement comes from the venue's public settlement endpoint, explicit 0/1
  only (the fill-watcher lesson: a failure to ask is never an answer).

## Ops notes (constraints of the shared tree, 2026-08-09)

The house-standard files (`docker-compose.yml`, `.env.example`,
`core/heartbeat.py` service roster, `core/storage/models.py`) were carrying
another session's uncommitted work when this shipped, so to avoid sweeping
(the C12-numbering lesson):

* the compose service lives in **`docker-compose.quote.yml`** — run
  `docker compose -f docker-compose.yml -f docker-compose.quote.yml up -d quote-engine`;
  fold the block into the main file when it is clean;
* the heartbeat service name (`quote_engine`) is defined in the engine module;
  add it to `APP_DB_SERVICES` when `core/heartbeat.py` is clean so
  `/api/status` and `scripts/health.py` judge it;
* the `shadow_quote_fills` model lives in `core/quote/storage.py` beside its
  only consumer; migration `a7d94e02c5b1` (chains the retention migration);
* env vars (`MERIDIAN_QUOTE_INTERVAL_SECONDS`, default 5;
  `MERIDIAN_QUOTE_SETTLE_EVERY_SECONDS`, default 600) are documented here and
  read with defaults — add to `.env.example` when it is clean.

---

*Registered 2026-08-09, before the first cycle. Results append below this
line, never above it.*

## 2026-08-19 — accruing (recorded retroactively with the verdict row below)

First status read after the engine's first full slates: ingame 927 fills /
1 settled game, pregame 19 / 1 — both regimes NO DATA, counts only
(rendered on /quote from 2026-08-18 onward with the "accruing — no verdict
yet" chip).

## 2026-08-22 — INGAME VERDICT: FAIL (registered floors crossed)

Verbatim from `python -m core.quote.report`, run against production
2026-08-22 04:47Z:

```
[ingame]
  fills recorded / settled     : 17,032 / 15,614
  distinct games (settled)     : 12
  staked -> returned           : $7,566.95 -> $7,486.00
  per-fill ROI, clustered      : -0.0287  95% CI [-0.0825, +0.0251]  (G=12)
  net capture at fill (static-study mark): -1.60c [-1.69, -1.50]
  VERDICT: FAIL
```

Both floors crossed (15,614 settled ≥ 500; 12 games ≥ 10). The report's
registered rule prints FAIL: at floor and not PASS (primary ROI mean is
negative and its clustered CI does not exclude zero in QUOTE's favour —
it spans zero, which under the registered implementation is a FAIL, not a
suspension of judgment).

**The question this engine was built to answer is answered.** Requoting
was the one behaviour the static study could not price. Against C13's
static in-game −2.74¢/fill, the 5s-requoting quoter captures −1.60¢
[−1.69, −1.50] — **requoting recovered ~1.1¢/fill: real, measurable, and
insufficient.** The residual −1.6¢ is the adverse-selection floor at 5s
reaction latency, and its CI excludes zero decisively.

The optimism caveat cuts the right way: the fill rule undercounts exactly
the fills that hurt, so the true in-game number is likely WORSE than
−1.60¢. A FAIL under a flattering fill model is the trustworthy kind.
QUOTE's in-game arm is dead twice — once static (C13), once requoting
(this row) — and stays unbuilt as a strategy.

Observation, not verdict (registered-scope note): the pregame regime
remains below its fill floor (307 recorded / 277 settled of 500; 12 games)
and continues accruing. Nothing here reads on it.
