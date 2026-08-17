# Meridian docs

Short, single-topic docs. Each one should be readable in a few minutes.

The root [`README.md`](../README.md) is the project overview. These go deeper on one thing each.

**Just back? Read this first:** [return-brief-2026-08-07.md](return-brief-2026-08-07.md) — the week's verdicts, what got built, and the click list.
**Start here:** [how-it-all-works.md](how-it-all-works.md) — the whole project in plain language, then the maths.
**What we got wrong:** [findings.md](findings.md) — venue facts, bugs, and retracted claims. **Append as you find more.**
**PULSE queue:** [pulse-hypotheses.md](pulse-hypotheses.md) — all 14 in-game hypotheses in one editable table.
**Handing off / picking up:** [next-build.md](next-build.md) — the three routes, what's built, what to measure next.
**Status snapshot:** [STATUS.md](STATUS.md) — one page: built, measured, stuck.
**Current direction:** [roadmap.md](roadmap.md) — why we stayed WNBA, and the window-hunting plan.
**Terms:** [glossary.md](glossary.md) — every piece of jargon, defined once.

## Math

The modelling, stated precisely enough to argue with.

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
| [venue-gap.md](math/venue-gap.md) | Is Polymarket mispriced against Kalshi? (**the founding question** — no gap found, 7 of 10 games) |
| [ladder-sigma.md](math/ladder-sigma.md) | Is Polymarket's ladder too narrow? (hypothesis, unproven) |
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
| [what-runs.md](infra/what-runs.md) | What the three containers do, and why quiet hours still matter |
| [live-cadence.md](infra/live-cadence.md) | 27s → 200ms: no websocket, the DB was the bottleneck, and storage now needs retention |
| [retention.md](infra/retention.md) | What to keep at 200ms and for how long (~60 GB/season if nothing changes) |
| [board-survey.md](infra/board-survey.md) | Is another league's board worth trading? The V7 method as a tool, for October's NBA decision |
| [local-sync.md](infra/local-sync.md) | Why the local copy could not finish at 837k rows, and what it now omits |
| [live-fv-strip.md](infra/live-fv-strip.md) | The display-only live fair value on /picks, and the three cases where it refuses to print a number |
| [live-odds.md](infra/live-odds.md) | ESPN publishes **no** live in-game odds — measured, and what to record instead |
| [fill-watcher.md](infra/fill-watcher.md) | How order fill state comes back from the venue, and the pre-authorized exit rules |
| [architecture.md](infra/architecture.md) | How the pieces fit together |
| [hosting.md](infra/hosting.md) | Where it runs and what it costs |
| [data-sources.md](infra/data-sources.md) | Every external API, verified |

## Reading order

New to the project? **[how-it-all-works.md](how-it-all-works.md)** first, then **[architecture.md](infra/architecture.md)** → **[fair-value.md](math/fair-value.md)** → **[clv.md](math/clv.md)**. That's the system, the model, and how we judge it.

Re-reading with experience? Go **[findings.md](findings.md)** → **[math/market-shrinkage.md](math/market-shrinkage.md)** → **[math/calibration-problem.md](math/calibration-problem.md)**. That's what's broken, why, and the one thing still unexplained.
