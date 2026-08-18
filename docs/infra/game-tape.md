# Game tape — the per-game deep dive

`/picks` used to end with a flat table of the 60 most recent resolved
predictions. It could tell you the model went 3-for-11 and it could not tell
you **what the model was looking at when it decided any of them**, which is the
question actually asked after a bad night.

Click any game on the tape and you get every shadow trade in it, grouped by the
instant it was decided.

## The as-of rule

Every context field on a trade — score, margin, period, minutes left — is read
from **the latest snapshot at or before `decided_at`**, never a later one.

This is the whole design. Reading "the newest snapshot for this market" is one
clause of SQL shorter and would attach a fourth-quarter score to a decision
made two hours before tip, showing the model trading a 46-34 game it never saw.
On a page whose purpose is judging decisions, that is the one error that cannot
ship. `tests/test_game_detail.py::test_context_never_reads_the_future` seeds a
game that goes 0-0 → 18-15 → 88-70 and fails if the bound is removed; deleting
that one line turns five tests red.

The game's own path (score margin + market mid, from the 200ms archive) is
rendered **separately**, above the timeline, labelled as what happened *after*.
It is context for the reader and was not an input to anything.

## Why the score column mostly says "pregame"

Because the model is pregame-only, and that is the honest answer rather than a
gap. Measured across the whole shadow run on 2026-08-17 — 11,283 orders, every
one of which joined to a snapshot:

| decided | orders |
|---|---|
| pregame | 11,273 |
| while the market was live | 10 (0.09%) |

and all ten live ones land on a single instant, `2026-07-31 23:34:06Z`, the
first day of the run. The columns are kept rather than dropped for two reasons:
they are what an in-game strategy lights up with no change to this page, and
"the model has never traded inside a game" is itself a finding a deep-dive page
should make obvious at a glance.

## Minutes left is an estimate

`market_snapshots` carries a period and **no game clock**. Time remaining is
interpolated from wall-clock since the period was first seen — wrong whenever
the clock stops — and is printed with `est.`. The estimator is
`core.live_fv.minutes_remaining`, imported rather than reimplemented so this
page and the live FV strip cannot disagree about what quarter it is.

## P&L if filled is not a return

A shadow order is a limit order the system decided and never sent, and most of
them would have **rested** on the book — a resting limit fills only when
somebody crosses it. `pnl_if_filled` is what the bet would have paid *had it
filled at its limit*, the most optimistic fill assumption available. It must
never be summed into anything presented as performance; the backtest's fill
model (`core/backtest/fills.py`) exists because this number needs one.

## Endpoints

| route | what |
|---|---|
| `GET /api/games?league=` | games with shadow trades, newest decision first |
| `GET /api/game/{event_slug}` | the deep dive: trades + as-of context + outcome + timeline |

The timeline is downsampled server-side (one reading per 30s bucket, capped at
900 points): a live game is 200ms × ~14 markets, which is tens of thousands of
rows nobody can read and no browser should be handed.

## Retired with this change

The live board's **Edge > 2%** and **Shadow orders** filter tabs. Both asked a
question this page answers better — the first was a threshold with no evidence
behind it, the second a list of orders with no context attached. The board's
per-row `Shadow` column stays: it describes a market currently on the board,
which the historical tape does not cover.
