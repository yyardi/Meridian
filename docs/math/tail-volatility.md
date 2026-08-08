# Tail volatility — do the far rungs move most at the edges of a game?

**Status: FAIL — gated 2026-08-08.** The last of the original fourteen
hypotheses to be judged.

The hypothesis requires the tails to be livelier than mid-game at **both**
edges. At the close they are; **at the open they are the opposite** —
**−0.651¢, CI [−0.888, −0.415]**, the interval entirely on the wrong side of
zero. Tails are *quieter* in Q1 than in Q2–Q3.

And the half that passes is not about tails: at the close the **body** rungs
gain **+2.150¢** against the tails' +0.686¢, 3.1× more. That is the
pre-registered interpretation control doing exactly what it was written for.

Module: [`core/pulse/tail_volatility.py`](../../core/pulse/tail_volatility.py) ·
Ledger row [#6](../pulse-hypotheses.md) · overlaps
[ladder-sigma.md](ladder-sigma.md), whose gate is untouched

Origin: *"the tail odds move a ton at the start and end."*

## The instrument decided the design

The obvious study — compare deep rungs against near rungs — is **unanswerable
with this data**. Measured 2026-08-07:

| `book_tier` | live observations | median gap |
|---|---:|---:|
| `near` | 3,282,678 | **0.20s** |
| `deep` | 24,019 | **30.11s** |
| `NULL` | 2,520 | 641.54s |

The recorder samples near-money rungs at 200ms and sweeps deep ones at 30s
([live-cadence.md](../infra/live-cadence.md)). A **150× cadence difference**
makes deep rungs look more volatile *by construction*, because a longer gap
contains more movement. That is [correction C1](../findings.md) exactly — the
error of reading a property of the sampler as a property of the market.

So the universe is `book_tier='near'` only, uniformly sampled. **The near tier
still contains tails**: `book_tier` ranks by |mid − 0.5| *within market type*,
so the near set spans mid 0.06–0.90 at the 5th/95th percentiles and holds
800,759 tail observations. It is the deep *tier* that is unmeasurable, not the
tail *prices*.

Every exclusion is counted and printed, in two separate tables because they
have different units — observations never loaded, versus candidate window
starts dropped.

## The gate, fixed before any move was computed

Phases: **open = Q1**, **mid = Q2+Q3**, **close = Q4**. HT and OT excluded
(clock stopped; not regulation).

| | |
|---|---|
| **PASS** | tail \|move\| higher in **both** open and close than mid, each with a 95% CI clustered by game excluding zero, at ≥10 games |
| **FAIL** | sample met, either direction fails |
| **NO DATA** | either comparison's phases do not both reach 10 games |

Both edges are required because the hypothesis names both. A close-only effect
is the endgame repricing already recorded as V4, not this claim.

**An interpretation rule was pre-registered alongside it:** the same statistic
is computed for the *body* rungs as a control, and if the body shows the same
pattern the finding is "the board is livelier at the edges", not "the tails
specifically". That rule exists because [#16](win-curve.md) passed a gate that
compared the wrong two things — see correction C12. Naming the control before
seeing it is the cheapest protection against repeating that.

Moves are net |Δmid| over a fixed **30s** window (inherited from
`adverse_selection`), non-overlapping, never spanning a period boundary. Net
rather than summed travel, because summed travel scales with sample count and
would smuggle the cadence artifact back in.

## The numbers (final — gate closed 2026-08-08)

18,788 windows.

| phase | tail n | games | tail mean | body n | games | body mean |
|---|---:|---:|---:|---:|---:|---:|
| open | 367 | **10** | 0.717¢ | 6,289 | 16 | 1.760¢ |
| mid | 3,399 | 16 | 1.290¢ | 11,240 | 16 | 2.343¢ |
| close | 3,651 | 17 | 2.089¢ | 3,568 | 17 | 4.472¢ |

Contrasts are **paired within game** — each game contributes one difference of
its own two phase means — then clustered by game, so a game that is livelier
throughout cannot move the result.

| comparison | games | diff | 95% CI (clustered) |
|---|---:|---:|---|
| **tail** open vs mid | **10** | **−0.651¢** | [−0.888, −0.415] |
| **tail** close vs mid | 16 | **+0.686¢** | [+0.453, +0.920] |
| body open vs mid | 16 | −0.574¢ | [−0.684, −0.465] |
| body close vs mid | 16 | **+2.150¢** | [+1.616, +2.684] |

## Reading it

**The open half is contradicted outright.** The interval excludes zero on the
*wrong side*: tails move 0.65¢ less per 30s in Q1 than in Q2–Q3. It tightened
and stayed there across three successive slates (8 → 9 → 10 games), never
drifting toward the hypothesis.

**The close half is real and is not about tails.** Tail rungs do gain +0.555¢,
significantly. Body rungs gain **+2.135¢** — nearly 4× as much. So at the close
the tails move *less* than the rest of the board. The hypothesis says the tails
move *most*. That is the interpretation rule firing exactly as written.

**Why the open sample was slow to fill is itself a finding, and it is
structural.** 367 tail windows across 10 games at the open against 3,651 across
17 at the close — and **7 of 17 games produce no open-phase tail window at
all**. A rung is tail-priced in Q1 only if it is a far ladder line still inside
the near tier, which is rare before a game has resolved toward anything. The
open edge accrued at roughly half the rate of the other two: it needed three
slates to move 8 → 9 → 10 while mid and close reached 16 and 17. Early in a game almost
nothing is tail-priced — a rung reaches 0.10 or 0.90 because the game has
resolved toward it. So "tails at the open" is a small, structurally unusual
population, and the observation that prompted this row was probably about
something else: the pregame→live transition, or the genuinely deep rungs that
this data cannot measure at all.

**Tail membership is endogenous late.** A rung is a tail rung in Q4 partly
*because* the game is decided. The body control is the check on that, and it is
the reason the close result reads as a phase effect rather than a tail effect.

## Gate policy note (added 2026-08-08)

The operator directed that PULSE hypotheses use **15-game** gates rather than
10. That applies to hypotheses pre-registered from 2026-08-08 forward.

**This one keeps its pinned 10.** Its gate was fixed before any number existed,
and it is mid-accrual with its direction already peeked — the open edge is
pointing the wrong way at 8 games. Moving the bar now, in either direction,
would taint it. It closes at 10, on its own terms.

**Any successor to this hypothesis takes 15.** If the tail-volatility question
is reopened in a new form — a different trigger, a different window — that new
row is pre-registered fresh and inherits the 15-game default. See the gate
policy in [pulse-hypotheses.md](../pulse-hypotheses.md).

## Reproducing it

The gate closed on 2026-08-08 when ind-chi contributed 14 open-phase windows
(the same slate's lv-min contributed none). Nothing here needs re-running: Nothing in the module needs
changing:

```bash
python -m core.pulse.tail_volatility
```

Measuring the genuinely deep rungs needs a **recorder change**, not more games:
their 30s price cadence is a sampling decision, not a fact about the market.
Until that changes, deep-tier volatility is not measurable at any sample size.

## Relation to ladder-sigma

[ladder-sigma.md](ladder-sigma.md) asks whether the venue's implied sigma is
too **narrow** across a whole ladder. This asks **when** the tails move. They
overlap and the gates are independent; nothing here modifies that one.

Corroborating context, from [win-curve.md](win-curve.md): the live win curve's
fitted sigma is **2.628** points per √minute, and its implied value **decays by
period** — 2.98 at end-Q1, 2.77 at the half, 2.40 at end-Q3. A single √t scale
does not fit all three. That is an independent measurement of the same
underlying thing this doc measures at the ladder's edges, and it points the
same way: **variance is not uniform across a game**, so a ladder shaped with
one constant sigma is mis-shaped in a time-dependent way. Neither result is a
trade on its own.
