# Next build — handoff

Written 2026-08-02. Self-contained: a fresh agent should be able to work from this plus [how-it-all-works.md](how-it-all-works.md) without the prior conversation.

## The one-paragraph situation

Meridian prices WNBA contracts on Polymarket US. Its edge is **not** better basketball forecasting — measured, the market's margin MAE (9.65) beats the model's (10.19), and only ~16% of the model's disagreement with the market carries information. The edge is a **venue gap**: Polymarket's thin WNBA board prices below the sportsbook consensus, and the model is mostly a translator that turns the book's number into a price for each ladder rung. Everything is shadow mode; **$0 has ever been traded**.

## Three routes

| | Route | Edge source | Status |
|---|---|---|---|
| **A** | Pregame, hold to settlement | venue gap | **built, v4 live** — 12 resolved games, −9.4% at price, CI straddles zero; venue-gap leg being tested by the Kalshi recorder (gate ~Aug 8–9) |
| **B** | In-game directional | ~~run overreaction~~ | **core premise FAILED its gate 2026-08-06** — 444 runs / 11 games, reversion −0.32¢ vs 6¢ cost. Prices reprice, they don't panic. First-score (#2) verdict pending; #5 remains unmeasured but orphaned (no live anchor, no live model with edge) |
| **C** | Market making | the spread itself (3–6¢) | **FAILED its gate 2026-08-06** — net capture **−2.66¢ per filled quote**, CI [−2.96, −2.36], 630k fills / 11 games. Adverse selection ate the spread; depth adds no directional skew (whale FAIL). QUOTE stays unbuilt |

*(Corrected 2026-08-04. This table said "nothing built" for B and C for two days
while the body of this same document described four built modules. The status
column is now the one to trust; if they diverge again, believe the module list.)*

The arithmetic strongly favours frequency: 2 trades/day at +2.5% turns $36 into $41 a season; 60 trades/day turns it into $3,067. **But frequency is an amplifier, not an edge** — at −2.5% those same 60 trades/day go to $0. The sign has to be established before the frequency is worth anything.

## Route A — what's outstanding

v4 shipped 2026-08-02. It applies winner's-curse shrinkage in the live path, which the backtest had always applied and the live path never did (v2/v3 shipped raw model-vs-market gaps, overstating every edge ~4×).

- **3,546 predictions, 562 shadow orders, 0 resolved.** No evidence yet either way.
- ⚠️ **The clock was stopped and nobody knew.** `PredictionLogger.run()` anchored on `max(captured_at)` and then filtered out live markets, so during a game — when the 200ms live recorder owns the newest timestamp — it found nothing to price. Zero predictions were written for the entire duration of the 2026-08-02 la-por game (19:30–21:56) while the scheduler logged `job_ok` every 20 minutes. No predictions means no shadow orders, so **nothing accrued toward the 50-resolved-bet gate at any tip-off**. Fixed 2026-08-02 via [`core/board.py`](../core/board.py); the scheduler now logs `job_degraded` when a job completes without error and does no work. Detail: [infra/live-cadence.md](infra/live-cadence.md).
- The gate is **~50 resolved bets** (CLV converges ~10× faster than P&L), then check `bet_win_rate` vs 0.524 and `brier_model` vs `brier_market` on `/picks`.
- **v2/v3's live record: 38.5% bet win rate over 5 games, and the market beat the model on Brier.** That is the disease v4 targets, measured three independent ways (backtest slope 0.16, live big-disagreement accuracy 41%, live bet win rate 38.5%).
- Nothing to build here. It is a clock.

## Prerequisite for B and C: live data

**Built, running, and now at ~1 second** (`core/live_recorder.py`, container `meridian-live-recorder`). Rows are identical in shape to pregame ones and flagged `is_live`.

The old limitation — ~26–34s per cycle because it re-polled the whole 131-market board — is **fixed as of 2026-08-02**, first to 1s and then to **202ms measured** (p90 252ms, 281 cycles/min). Full write-up: [live-cadence.md](infra/live-cadence.md). Three things worth carrying forward:

- **There is no websocket or SSE.** Every upgrade path 404s and every endpoint returns JSON under `Accept: text/event-stream`. Polling is the only option. Re-check occasionally.
- **The board call already embeds best bid/ask for every market**, so top-of-book for the whole board costs **one request**. The 131 book calls were only ever buying depth. That is the entire reason 1s is now possible; the old design was the wrong shape, not merely slow.
- **The board genuinely moves at 1s** — 43 of 44 consecutive frame-pairs differed. Not cached, so the faster poll resolves real changes.

- **200ms is measured, not chosen.** Detected quote changes/second peak at 5.8/s around 200–300ms and fall to 3.5/s at 1s — the 1s loop was discarding ~40% of observable changes. Beware "% of frames that differ": it rises with the interval by construction and cannot pick a poll rate.

Depth now runs on a background thread over the ~4 rungs nearest the money (10s), with a slow sweep of the deep rungs (120s). Steady-state cost with a four-game slate is ~8.9 req/s against a 12 req/s budget; `MERIDIAN_RPS` was **not** raised.

Two new columns make the sparsity auditable: `market_snapshots.book_tier` and `book_levels.captured_at`. Migration `7c1a9f4b2e10`.

### Three operational things the 200ms work turned up

1. **The database is the bottleneck, not the venue.** The first 200ms deploy achieved 497ms because a Supabase INSERT round trip is ~330ms. Writes now run on their own thread (`SnapshotWriter`), batching whatever accumulates. Cost: a sub-second loss window on a hard kill; a clean shutdown drains.
2. **Storage needs retention.** ~0.5 GB per game before mitigation, 62% of it the `raw` JSONB. That column is now sampled every 30s instead of 5×/second (row 2,576 → ~977 bytes), but **partitioning and a downsampling policy are still outstanding** and should land before the season ends.
3. **⚠️ Supabase's session-mode pooler is saturated** — 15 clients project-wide, and the scheduler is already logging `EMAXCONNSESSION`. The transaction-mode pooler (port 6543) is the fix but breaks Alembic's advisory locks, so it needs a decision. **This currently blocks the live-odds recorder from running at all.**

## Route B — in-game directional

**Hypothesis to test first (do not build a model before this):** do prices *overreact* to scoring runs and then revert? If they do not, B is dead and no model saves it.

**Built 2026-08-02: [`core/pulse/overreaction.py`](../core/pulse/overreaction.py). Verdict: NO DATA.** Re-run the same day against the 200ms stream: **149 runs across 4 games** against a pre-registered gate of 30 runs across 10 games. Write-up: [math/run-overreaction.md](math/run-overreaction.md).

- **The run count is now met; the game count binds.** 8 runs / 1 game → 149 runs / 4 games.
- **The score trigger works now.** It fired zero times at the old ~910s cadence because both teams score between samples; at 200ms it detects 25 runs at ≥8 unanswered points. The study is running on both legs at last.
- Reversion at +5 min is **−0.01¢**, CI [−4.06¢, +4.03¢] — flat, with the whole interval below the 6¢ round trip. A direction, not a verdict, at four clusters. The first run's −7.25¢ was the one-game noise it was reported to be.

**Built 2026-08-02: [`core/pulse/first_score.py`](../core/pulse/first_score.py) — PULSE strategy #1. Verdict: NO DATA.** 18 filled trades across **3 games** against a gate of 30 across 10. Write-up: [math/first-score.md](math/first-score.md).

This is the first thing built against [`core/pulse/replay.py`](../core/pulse/replay.py): a maker-only fade of the price lurch on a game's opening basket, chosen because one basket is worth ~1.3 points of final total against a 16-point residual — as close to a pure-noise event as this sport offers. Gate is on P&L with both spread costs inside the number, so the bar is zero rather than the round trip.

**Both Tier 1 hypotheses now report NO DATA for the same reason, and it is worth stating plainly: only 3 games have usable 200ms coverage.** Counted from the local mirror on 2026-08-04:

| | Games |
|---|---|
| any snapshot data | 20 |
| **live** tick data | 10 |
| **full 200ms coverage** | **3** (+1 partial, 835s only) |

The other six live games are sampled every ~13–15 minutes — 9 to 42 observations across a two-hour game — and cannot resolve a 30-second reaction window. They contribute coverage and no signal. Rows are not the constraint; three games supply **99%** of the ticks replayed. The constraint is games, and the fix is nights.

**The full hypothesis queue lives in [pulse-hypotheses.md](pulse-hypotheses.md)** —
fourteen ideas raised from live observation, sorted into signals, execution
rules and model inputs, with an order of work and the multiple-comparisons
warning that governs all of them (14 hypotheses against ~7 games produces one
"significant" result by chance alone).

**Observed hypotheses worth encoding** (from live watching, unverified):
- Prices overreact hard to the *first* score of a game.
- A big lead being cut (e.g. 15 → 8) moves the chart ~10%.
- Scoring rate per quarter swings totals strongly; the winner market swings hardest.

**Already measured and available:** Q1 combined total correlates +0.55 with the final total (n=787), and **each extra Q1 point is worth 1.32 on the final, not 4.0**. Hot starts regress ~3×. That coefficient is the first brick of any live totals model. Residual sd after conditioning on Q1 is ~16 points.

**The model, if the hypothesis passes:** start from the pregame projection (not the league mean) and update by how far the in-game pace differs from what was expected *for that matchup*. Do not extrapolate raw pace.

### The live anchor does not exist (measured 2026-08-02)

PULSE was to be anchored on a live sportsbook line. **ESPN publishes none.** The
scoreboard's odds block is empty mid-game (0 providers, 120 frames); `summary.pickcenter`
is present but frozen at the pregame number (0 changes in 83 frames while the score moved
43-37 → 49-43); the core API 404s until the game is final. Writing `pickcenter` during a
game would have manufactured thousands of rows carrying a stale line, which PULSE would
read as live — worse than no data. Full write-up: [infra/live-odds.md](infra/live-odds.md).

A live book line means a paid odds feed. What was built instead
([`core/feeds/live_odds_recorder.py`](../core/feeds/live_odds_recorder.py)) records
**pregame** line movement at 15s and quarantines any in-game line behind a `(live)`
provider name. That unblocks [news-windows.md](math/news-windows.md), whose zero triggers
were largely a ~20-minute book cadence. It is built and tested but **not running** —
blocked on the connection ceiling above.

## Route C — market making

**Mechanically:** post a limit buy *and* a limit sell on the same contract simultaneously. Someone hits your bid, someone lifts your offer, you keep the difference and end flat. No forecasting.

**Why it is plausible here despite SIG/Citadel existing:** the at-the-money spread is **3¢ live, 6¢ pregame** — 6–12% of contract value. Equity spreads are ~0.01%. A spread that wide means nobody is making this market. You do not need microsecond infrastructure to compete with nobody. Book depth is real: **$469k of resting offers, $12.7k deepest single top-of-book, $177 median** — capacity is not the constraint at any plausible bankroll.

**Why it is genuinely hard:**
- **Adverse selection.** You get filled precisely when you are wrong. A run starts, your stale bid gets hit, you are long the losing side. This is what kills naive market makers, and it is the whole problem.
- **Inventory risk.** Only one side fills and you are directional whether you wanted to be or not.
- **Presence.** It must be automated; it has to be quoting every second of every game.

**Test before building:** from live snapshots, measure how often the mid moves *against* a resting quote within 30s of it being posted. That is adverse selection, and it is measurable from recorded data alone — no orders required.

**Built 2026-08-02: [`core/quote/adverse_selection.py`](../core/quote/adverse_selection.py). Verdict: NO DATA.** 57 quote-windows across 1 game against a pre-registered gate of 500 across 10. Write-up: [math/adverse-selection.md](math/adverse-selection.md).

The one-game sample is not evidence, but the *shape* is worth carrying: the mid travelled 5.61¢ over a 30s horizon against a 1.55¢ half-spread — about 3.6× the capture. If that survives ten games, the naive both-sides-at-the-touch version of C is dead and it would need a much faster quote-pull or a directional skew to live. **Note also that the measured half-spread here (1.55¢) is half the 3¢ figure quoted above** — 3¢ is the spread, 1.55¢ is what one side of it earns you.

**Latency, measured 2026-08-02 without placing an order:** warm round-trip to the authenticated host is **36ms** (p90 45ms), against a detection delay of ~260ms from our own 200ms poll loop. **We are ~7× slower to notice than to cancel** — the bottleneck is us, not the venue. Venue-side order processing remains unmeasured and cannot be measured without submitting; the smallest safe test is written up in [math/write-latency.md](math/write-latency.md), and the recommendation is **not** to run it yet.

**Also built: [`core/quote/depth_signal.py`](../core/quote/depth_signal.py) (task 4). Verdict: NO DATA.** 46 whale appearances across 6 games against a gate of 100 across 10. Write-up: [math/depth-signal.md](math/depth-signal.md). This is the one most damaged by the old cadence: **zero** appearances had any observation inside the +30s or +60s horizons, so the primary mark was not merely under-powered, it was unmeasurable. Top-of-book notional in the current sample: median $460, p99 $44,827, max $86,651.

## Added 2026-08-02: a fourth measurement worth queuing

**Ladder sigma** ([math/ladder-sigma.md](math/ladder-sigma.md)). Polymarket shapes
its totals ladders with a near-constant ~15.9 implied sigma across 362 recorded
ladders, but 2026 totals land 20.1 points from the line. If that holds, both
tails are structurally cheap and the trade needs no basketball model at all.

It also reframes ANCHOR: the champion's edge may be this volatility effect
rather than the directional venue gap, in which case it evaporates the moment
Polymarket updates its sigma. Worth knowing which.

Gate is pre-registered in the doc. Needs ~40 games of resolved totals; we have 5.

## Rules that apply to anything built here

Non-negotiable, and every one of them has already caught a real bug:

- **Point-in-time.** Every feature computed `as_of` a timestamp, from data strictly before it. `as_of` is keyword-only with no default so lookahead is unexpressible.
- **Maker-only.** Taker fills destroy the edge (−4.0% vs +0.75% on the same bets, no rebate booked — findings C7). Market orders are unrepresentable in `core/executor.py`.
- **Pre-register the gate before looking at the number.** Five ideas died this way cheaply.
- **Sample size is games, not rows.** One game emits ~130 correlated ladder rows — and at 1s sampling, ~130 a *second*. Cluster standard errors by game; see [math/clustered-errors.md](math/clustered-errors.md). A faster camera does not give you more games.
- **Run experiments against local Postgres** (`python -m core.storage.sync_local`, then `DATABASE_URL=postgresql+psycopg://meridian:meridian@localhost:5433/meridian`). 11m28s → 13s. The microstructure experiments also need `market_snapshots` / `book_levels`, which are large and therefore opt-in: `python -m core.storage.sync_local --stream`. **Two things changed here 2026-08-02** and are written up in [infra/local-sync.md](infra/local-sync.md): the copy is keyset- rather than OFFSET-paginated (the OFFSET version could no longer finish at all — it died on a statement timeout at row 31,427 of 837,220), and `market_snapshots.raw` is omitted by default, which is a 24× speedup and the reason "byte-identical" no longer describes the local copy.
- **Bump `MODEL_VERSION` on any logic change** outside `WNBATotalsConfig` — `config_hash` won't catch it, and two generations sharing a grouping key silently corrupts every performance query.

## Fastest path

Rewritten 2026-08-02. All three measurements are **built and returning NO DATA**, so the bottleneck is no longer code — it is games.

1. **Wait.** The 1s recorder is running. Every gate needs ≥10 games; there were 6 in the whole database on 2026-08-02, and only 1 with usable fast-cadence coverage. At ~4 games a slate that is under a week.
2. Re-run all three against fresh data:
   ```
   python -m core.storage.sync_local --stream
   export DATABASE_URL=postgresql+psycopg://meridian:meridian@localhost:5433/meridian
   python -m core.pulse.first_score
   export DATABASE_URL=postgresql+psycopg://meridian:meridian@localhost:5433/meridian
   python -m core.quote.adverse_selection
   python -m core.pulse.overreaction
   python -m core.quote.depth_signal
   ```
3. Whichever passes, build that. If neither B nor C passes, A is what you have, and A needs bankroll rather than code.

**Do not re-tune a gate after seeing a number.** The three gates are pinned in the module docstrings with the date they were fixed. If one of them turns out to have been the wrong question, write down why *before* changing it.

### What the first pass already tells you

Nothing about whether B or C works — every verdict is NO DATA and must be read as such. But it did establish that **the old 30s cadence could not have answered any of the three questions**, which is why the recorder work came first:

| Experiment | Blocked by cadence how |
|---|---|
| adverse selection | 30s horizon was a single hop, no interior |
| overreaction | score trigger fired 0 times — both teams score between samples |
| depth signal | **0** whale appearances had any observation inside +30s or +60s |

That is the real result of this pass: the instrument, not the measurement.
