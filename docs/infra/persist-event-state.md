# Persist the event-level state block — spec, not deployed

**We store three of the venue's game-state fields and drop the rest. One of the
dropped ones is the only field the liveness fix is allowed to stop recording
on, and another is a freeze detector that needs no second source.**

## What we store vs what arrives

`market_snapshots` has `is_live`, `event_score`, `event_period` as columns, and
the **market**-level payload in `raw`. The **event**-level block is not stored
at all.

The venue sends it three times over — top level, `eventState`, and
`metadata.gameState` — with identical values (same `id`, 132022472):

| field | stored? | decision it would change |
|---|---|---|
| `live` | yes (`is_live`) | — |
| `score` | yes (`event_score`) | — |
| `period` | yes (`event_period`) | — |
| **`ended`** | **no** | the only field permitted to stop recording under [liveness-predicate.md](liveness-predicate.md) |
| **`updatedAt`** | **no** | see below — freeze detection from one source |
| `elapsed` | no | game-clock context; would let us bucket by phase without ESPN |
| `periodScores` | no | per-period scoring; useful for totals, not for liveness |
| `sportradarGameId` | no | **dead end** — neither ESPN nor Kalshi carries it (checked both) |

## `updatedAt` is the find

It is **the venue's own stamp of when it last changed the game state.** A live
game whose `updatedAt` stops advancing while wall-clock time passes is a frozen
feed, stated by the venue about itself, with no second provider required:

```
now - eventState.updatedAt > N minutes AND not ended  ->  state is stale
```

This is a different signal from `live`, which is a claim the venue can get
wrong. `updatedAt` is a fact about when the claim was last revised.

**But it is NOT single-source, and that was the thing that made it attractive.**
Observed live on 2026-09-06: `cfb-scarst-flam` showed `live=True` with
`updatedAt` 44 minutes stale — and ESPN's status detail read **"Delayed"**. A
delayed game genuinely stops producing state revisions, so stale `updatedAt` is
*correct* there.

**A delayed game and a frozen feed are indistinguishable by `updatedAt` alone.**
Both show `live=True` over a state block that stopped moving. Separating them
needs game status from outside the venue, so the detector is
**necessary-but-not-sufficient** and requires the ESPN cross-check it was
supposed to replace.

We have **no history of it**, so it cannot be tested against the 09-05 freeze.
It is a candidate, not a validated detector, and should be labelled that way
until a freeze occurs with it recorded.

## The honest limit of this change

**It does not help historically.** `ended` was never stored, so the liveness
predicate cannot be validated retroactively against the freeze window. What
survives from that window is only the weaker demonstration already made: that
`period` and `score` alone would have rescued 8,667–11,047 rows/hour.

The predicate rests on that. This change makes it *auditable from deployment
forward*, and nothing before.

## The change

Add to `market_snapshots`: `event_ended boolean`, `event_state_updated_at
timestamptz`, `event_elapsed text`. Populate from the event-level block already
in the parsed response.

Read the block from **one** of the three places it appears and record which —
they agree today, and a future divergence between them should surface as a
contradiction rather than be resolved silently by field-precedence order.

## Status

Specified, not deployed. Prod goes through the operator. The monitor in
[liveness-predicate.md](liveness-predicate.md) (`cycles == 0 while games are
scheduled in progress`) needs none of this and remains the first line.
