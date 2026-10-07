# Meridian docs

Short, single-topic docs. Each one should be readable in a few minutes.

The root [`README.md`](../README.md) is the project overview. These go deeper on one thing each.

**Start here:** the root [`README.md`](../README.md) — what Meridian is now — and [`STATUS.md`](../STATUS.md), the running record (newest sections last).
**What we got wrong:** [findings.md](findings.md) — venue facts, bugs, and retracted claims. **Append as you find more.**
**Codebase map:** [ARCHITECTURE.md](ARCHITECTURE.md) — every container, what it writes, why it exists (a 2026-09-13 snapshot).
**Terms:** [glossary.md](glossary.md) — every piece of jargon, defined once.

## Now: the questions the system works on today

| Doc | Question it answers |
|---|---|
| [ladder-fill-test.md](math/ladder-fill-test.md) | The ladder arbitrage: when the venue's spread ladder contradicts itself, can both legs be filled? (pre-registered) |
| [fee-coefficient.md](math/fee-coefficient.md) | The venue's fee as a constant of a period, charged per row |
| [btc15-harness.md](math/btc15-harness.md) | The Bitcoin Up-or-Down harness: the model, the ledger, the $10 limit, the cost caps |
| [thin-league-speed-preregistration.md](math/thin-league-speed-preregistration.md) | Thin basketball leagues: does the venue reprice late after its own score changes? |
| [thin-league-live-feeds.md](math/thin-league-live-feeds.md) | Which leagues publish a free live feed with the second of every basket |
| [niche-cross-venue-scan.md](math/niche-cross-venue-scan.md) | Niche leagues against Kalshi: the BTC arm's rule fired on 0 of 105 tight pregame pairs and matched a coin in play |
| [ladder-capture-read.md](math/ladder-capture-read.md) | Of the stream-measured ladder crossings over $25, $655 across 7 lived ≥ 0.5 s in four football days: $70–580 a weekend at displayed size, before fills |
| [intl-basketball-ls-research.md](math/intl-basketball-ls-research.md) | International basketball against Kalshi: the anchor and the pregame read |
| [cricket-inplay-dip.md](math/cricket-inplay-dip.md) | Cricket in play: buying the dip, registered |
| [tabletennis-preregistration.md](math/tabletennis-preregistration.md) | Table tennis: a rating model against the venue, registered |
| [pulse-live-scorecard.md](math/pulse-live-scorecard.md) | The in-game model's live decisions, scored against the price |

## First phase: the WNBA fair-value model (August 2026), kept as history

Meridian began as a WNBA fair-value model on Polymarket US. These documents record
that phase, what it measured and what failed; they describe the project as it was
then, not as it is now.

**Then:** [how-it-all-works.md](how-it-all-works.md) — the first phase in plain language, then the maths.
**Then:** [return-brief-2026-08-07.md](return-brief-2026-08-07.md) · [next-build.md](next-build.md) · [STATUS.md](STATUS.md) (2026-08-04) · [roadmap.md](roadmap.md) · [pulse-hypotheses.md](pulse-hypotheses.md).

### First-phase maths

The WNBA modelling, stated precisely enough to argue with.

| Doc | Question it answers |
|---|---|
| [fair-value.md](math/fair-value.md) | How do we project a game's score? |
| [ladder-curve-fit.md](math/ladder-curve-fit.md) | How do we recover the market's implied mean and σ? |
| [fees-and-spread.md](math/fees-and-spread.md) | What does a trade actually cost? |
| [clv.md](math/clv.md) | Why closing line value instead of win rate? |
| [kelly.md](math/kelly.md) | How much do we bet? |
| [pythagorean-record.md](math/pythagorean-record.md) | Does win-loss record add anything to point differential? |
| [point-in-time.md](math/point-in-time.md) | How do we make lookahead bias structurally impossible? |
| [availability.md](math/availability.md) | Does knowing tonight's lineup beat the closing line? (No — measured) |
| [what-the-edge-is-worth.md](math/what-the-edge-is-worth.md) | What is +1.75 points of CLV worth in money? (+2.50% ROI) |
| [market-shrinkage.md](math/market-shrinkage.md) | Why the moneyline loses, and why recalibration was the wrong fix |
| [venue-gap.md](math/venue-gap.md) | Is Polymarket mispriced against Kalshi? (**the founding question — FAILED** at pregame resolution: 0.00¢ median gap, 36 games, 3.6× the gate) |
| [ladder-sigma.md](math/ladder-sigma.md) | Is Polymarket's ladder too narrow? (**FAILED** — gated 2026-08-25, 69 games: neither tail's CI excludes zero, in either declared reference-price arm) |
| [feed-lag.md](math/feed-lag.md) | **The F8 bound** — how far behind the market our ESPN feed is, and what that kills (measured 2026-08-25: p50 36.4s over 16 games; the move is already complete when we learn the play) |
| [espn-wp-vs-price.md](math/espn-wp-vs-price.md) | Does ESPN's win probability beat the live price? (**PASSED its gate, NOT TRADABLE** — 2026-08-25: k +2.54, but r=0.973 with the mid and the pre-declared money clause reads −14.3%) |
| [q4-endgame-state.md](math/q4-endgame-state.md) | Does Q4 endgame state (possession, bonus, timeouts) improve win-probability calibration? (REGISTERED 2026-08-25, **amended before any real data** — the original Brier gate was unwinnable; nothing real computed) |
| [news-windows.md](math/news-windows.md) | Does the thin venue lag the books on news? (no data yet) |
| [adverse-selection.md](math/adverse-selection.md) | Does the spread survive being filled? (**FAILED** — −2.66¢ per filled quote; QUOTE stays unbuilt) |
| [run-overreaction.md](math/run-overreaction.md) | Do prices overshoot scoring runs? (**FAILED** — prices reprice, they don't panic) |
| [first-score.md](math/first-score.md) | Does the opening basket move the price too much? (**FAILED** — no reversion, and Tier 1 closes with it) |
| [tail-volatility.md](math/tail-volatility.md) | Do the far rungs move most at the edges of a game? (**FAILED** — quieter at the open, and the close is a whole-board effect) |
| [live-totals-fv.md](math/live-totals-fv.md) | What is a live game's total worth? (display only, ungated — serves the audit's one positive pocket) |
| [win-curve.md](math/win-curve.md) | P(win \| margin, time) from 787 games, σ=2.628 — and why hypothesis #16 passed its gate and still is not tradable |
| [depth-signal.md](math/depth-signal.md) | Does a whale in the book predict the next move? (**FAILED** — resting size predicts nothing) |
| [clustered-errors.md](math/clustered-errors.md) | Why sample size is games, not rows — and why a faster recorder doesn't help |
| [write-latency.md](math/write-latency.md) | How fast can we *act*? (our poll loop beats the venue's network cost 7:1) |
| [calibration-problem.md](math/calibration-problem.md) | ⚠️ **Open problem** — why the model's probabilities carry no signal |
| [hand-trade-audit.md](math/hand-trade-audit.md) | The human's app trading scored at prices (descriptive — n too small for any verdict) |
| [ingame-moneyline-replay.md](math/ingame-moneyline-replay.md) | Does the live-FV strip have an edge in-game? (53 games — ROI +5.96%, CLV +0.96¢, **both CIs cross zero**) |
| [moneyline-spread-baseline.md](math/moneyline-spread-baseline.md) | Do the moneyline and spread have an edge? (**neither** — both CIs cross zero; CLV structurally unavailable) |
| [injury-delta.md](math/injury-delta.md) | Is injury awareness worth anything? (**not yet measurable** — wired and point-in-time correct, but zero overlapping games) |
| [research-notes.md](math/research-notes.md) | What the betting-markets literature says, tied to actions here |
| [performance-targets.md](math/performance-targets.md) | Pre-registered bars for "good", sample sizes, gates before real money |

## Stack

One doc per tool: what it does, why it was chosen, what it replaced.

| Doc | Covers |
|---|---|
| [postgres.md](stack/postgres.md) | Database, and why NUMERIC not float |
| [sqlalchemy-alembic.md](stack/sqlalchemy-alembic.md) | ORM and migrations |
| [httpx-tenacity.md](stack/httpx-tenacity.md) | HTTP and retries |
| [pydantic.md](stack/pydantic.md) | Boundary validation |
| [structlog.md](stack/structlog.md) | Logging |
| [scientific-python.md](stack/scientific-python.md) | pandas / numpy / scipy / statsmodels |

## Infra

| Doc | Covers |
|---|---|
| [what-runs.md](infra/what-runs.md) | Superseded — pointer to ARCHITECTURE.md |
| [live-cadence.md](infra/live-cadence.md) | 27s → 200ms: no websocket, the DB was the bottleneck, and storage now needs retention |
| [artifact-paths.md](infra/artifact-paths.md) | One artifact root (`MERIDIAN_DATA_DIR`), two archive subtrees, and the compose mount contract |
| [analytics-path.md](infra/analytics-path.md) | Why the model-performance page was empty: writer on the host, reader in an unmounted container |
| [game-tape.md](infra/game-tape.md) | The per-game deep dive, and the as-of rule that keeps it from reading the future |
| [leagues.md](infra/leagues.md) | League as a parameter: the table, the tabs, and what is deliberately not parameterised |
| [supabase-exit.md](infra/supabase-exit.md) | One database: the import design (natural keys, id remaps) and the repoint |
| [retention.md](infra/retention.md) | What to keep at 200ms and for how long (~60 GB/season if nothing changes) |
| [board-survey.md](infra/board-survey.md) | Is another league's board worth trading? The V7 method as a tool, for October's NBA decision |
| [local-sync.md](infra/local-sync.md) | Why the local copy could not finish at 837k rows, and what it now omits |
| [landing-page.md](infra/landing-page.md) | Why `/` is the picks page now, what came across from the live board, and what did not |
| [live-fv-strip.md](infra/live-fv-strip.md) | The display-only live fair value under the picks table, and the three cases where it refuses to print a number |
| [live-odds.md](infra/live-odds.md) | ESPN publishes **no** live in-game odds — measured, and what to record instead |
| [bankroll.md](infra/bankroll.md) | The account balance, read from the venue — and the stale `35.68` it replaced |
| [fill-watcher.md](infra/fill-watcher.md) | How order fill state comes back from the venue, and the pre-authorized exit rules |
| [architecture.md](infra/architecture.md) | Superseded — pointer to ARCHITECTURE.md |
| [aws-history-merge.md](infra/aws-history-merge.md) | Folding the laptop's history into the live server DB: natural keys, server-wins, and the restore-in-flight guard |
| [aws-migration.md](infra/aws-migration.md) | Moving the stack to EC2: the click list, the row-count verification, and what the cutover actually is |
| [hosting.md](infra/hosting.md) | Where it runs and what it costs |
| [data-sources.md](infra/data-sources.md) | Every external API, verified |

## Reading order

New to the project? The root **[README](../README.md)**, then **[STATUS.md](../STATUS.md)** from §0cd on, then **[findings.md](findings.md)** and the "Now" table above.

Want the history? **[how-it-all-works.md](how-it-all-works.md)** → **[math/market-shrinkage.md](math/market-shrinkage.md)** → **[math/calibration-problem.md](math/calibration-problem.md)**: how the first phase worked, and why forecasting the WNBA better than the market was not where the edge was.
- [cross-venue-inplay-football.md](math/cross-venue-inplay-football.md) — Polymarket vs Kalshi in play at message cadence, registered 10-02; read Monday 10-05
- [coinrace-research.md](math/coinrace-research.md) — Kalshi Coin Race: the contract, 4,000 windows of history, four screens registered 10-07
