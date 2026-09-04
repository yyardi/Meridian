# Registration draft — the resting-order probe

**Status:** DRAFT, not registered. Written 2026-09-04 by Quant D at the
manager's request. Nothing here has been run.

**What it tests:** the phantom criterion — the modelling assumption under the
central empirical result of this program. It has never been checked against a
real resting order.

---

## 1. The claim under test

The classifier calls a shadow fill REAL when the counterparty crossed to us
(`ask <= B` for our bid at `B`), and PHANTOM otherwise. That rests on a
mechanical assumption about the venue:

> **A1 (necessity).** An order resting at `B` is in the public book, so
> `best_bid >= B`. Therefore the mid cannot reach `B` while `ask > B`, and a
> fill booked in that state could not have happened.

There is a second assumption, unstated in the record, which the exclusion
also relies on:

> **A2 (sufficiency).** When `ask <= B`, our resting order fills.

**A2 is false as written**, and this matters more than it has been given
credit for. `ask <= B` says *someone offered at or below our price*, not that
*we* traded. Queue priority, size, and partial fills all intervene. So the
6,255 "real" fills are an **upper bound** on what we would have got, and the
−3.4c is measured over a population we would not fully have received. The
probe must test both legs or it certifies half the claim.

## 2. What rests on it

The real/phantom separation (63.9% phantom), the −3.4c real-fill settlement
result, the k-curve, the FLATTEN registration, and tomorrow's A/B. If A1 is
materially wrong, the phantom share is overstated and every downstream number
moves toward the blend. If A2 is materially wrong, the real population is
overstated and the true fill count is lower than 6,255 — which changes
capacity and the wallet constraint, though not necessarily the per-fill sign.

## 3. Primary statistics and the pre-registered decision rule

**Analysis unit is declared here, before collection, because it is exactly
the choice that has gone wrong twice in this program.** Ticks inside one
order are heavily correlated; the honest effective N is orders, not ticks.

**Leg A — necessity.**
- *At-risk tick*: our order live and unfilled at `B`, and market `ask > B`
  (the state in which a phantom could be manufactured if `best_bid` fell).
- *Violation*: an at-risk tick with `best_bid < B`.
- *Primary*: violation rate per at-risk tick, **clustered by order** via
  `core/quote/adverse_selection.clustered_mean`.
- *Secondary*: fraction of orders with >= 1 violation (the pilot's unit).

**Leg B — sufficiency.**
- *Crossing episode*: a maximal run of ticks with `ask <= B` while our order
  is live.
- *Primary*: fraction of crossing episodes in which we received a fill (any
  size), clustered by order.
- *Secondary*: filled size / offered size, to separate "no fill" from
  "partial fill behind the queue".

**Decision rule, fixed in advance:**

| outcome | reading |
|---|---|
| Leg A violation rate < 1% (upper CI bound) | A1 CONFIRMED at the precision that matters; phantom share stands |
| Leg A upper bound in 1–8% | A1 SUPPORTED but the phantom share carries an unquantified error band that must travel with it |
| Leg A upper bound > 8% | A1 REFUTED as used; 63.9% is not usable and the separation must be re-derived |
| Leg B fill rate > 90% | A2 usable; "real" ≈ what we would have got |
| Leg B fill rate 50–90% | real fills are an upper bound; capacity claims must be scaled by the measured rate |
| Leg B fill rate < 50% | the real population is mostly aspirational; the −3.4c describes trades we would mostly not have made |

The 8% Leg A threshold is chosen because it is roughly where the phantom
share moves by more than 5 points, which is where downstream conclusions
start to change. It is a judgement and it is being fixed now rather than
after seeing the data.

## 4. What must be recorded

Per order: venue order id, market, side, limit price, insert time, every
amend/cancel, every (partial) fill with size and timestamp, and the terminal
state. Per market: the full book top (`best_bid`, `best_ask`, and sizes)
at the **feed's native cadence**, not a downsampled grid — a 5s grid cannot
resolve a violation that lasts one tick.

Sizes matter and have been absent from every analysis so far. Without
`best_bid_size` we cannot distinguish "our order is the whole touch" from
"we are behind 400 contracts", which is most of Leg B.

## 5. Power, from measured rates rather than assertion

Measured on the WNBA tape (220,946 five-second cycles = 306.9 standing-quote
hours, touch-joining policy):

- **35.1 phantom episodes per quote-hour** — moments the shadow model would
  book a fill that A1 says is impossible.
- **20.9 real fill events per quote-hour** — Leg B opportunities.

Note the asymmetry this creates. Under A1, a *correctly behaving* resting
order produces **zero** phantom episodes: with our order at `B`, `best_bid >= B`,
so the state cannot arise. What we actually count is violations of that
invariant. The 35.1/hour is therefore the rate of *opportunities to be
contradicted* — how often the shadow model would have claimed a fill in that
market at that price.

Rule of three (0 events in N gives a 95% upper bound of 3/N):

| target bound | episodes needed | standing-quote hours |
|---|---|---|
| < 5% | 60 | ~1.7 |
| < 1% | 300 | ~8.5 |

But **clustered by order the binding N is orders, not episodes.** The pilot
(25 real BUY orders, 36,369 ticks) gives a per-order violation rate of 2/25 =
8.0% [2.2%, 25.0%] and a per-tick rate of 2/36,369 = 0.0055%. To bound the
per-order rate below ~7% requires ~40 clean orders; below 3%, ~100.

**So the sample is set by order count, not by time.** ~40 distinct resting
orders spread over >= 6 games — roughly one order per market in a handful of
markets per game — is the smallest design that discriminates. That is days,
not weeks.

## 6. Confounds

1. **Our presence changes the tape.** The counterfactual is not "this book
   plus our order" — narrowing the touch may attract or deter flow. This is
   unfixable by observation and bounds what any probe can conclude. It is
   why the probe tests the *mechanical* assumption A1 and not "what would
   PULSE have earned".
2. **Feed lag vs true violation.** A violation may mean the venue did not
   have our order, or that our book snapshot is stale. Mitigate by recording
   our own order state from the venue's order-status endpoint, not inferring
   it, and by treating single-tick violations separately from sustained runs
   (pilot: all observed runs were length 1, max 1).
3. **Selection on execution.** The pilot's 25 orders all filled — they came
   from passive-execution activity records. Orders that rest and never trade
   are structurally absent, and those are where a stale book is most likely.
   The probe must record orders from placement, not from fills.
4. **Price-level selection.** Resting only at the touch in tight markets
   tests A1 only there. Given CFB's board is ~3x wider than WNBA's and our
   fills sit in its tightest corner, the probe should deliberately sample
   wide-market rungs too, or it will confirm A1 only where we already live.
5. **Size.** A 1-contract order may sit at the back of every queue and never
   fill, understating Leg B. Record size and treat Leg B as conditional on it.

## 7. Cheapest discriminating version

One contract, resting at the touch, in ~6–8 markets per game across 6 games,
maintained through the game with re-quoting on touch moves. Record book top
with sizes at native cadence plus full order lifecycle.

That is ~40–50 orders, which is the Leg A sample above, and it accumulates
Leg B episodes at ~21/quote-hour for free. **It requires no new strategy —
only instrumentation around orders we are already able to place**, since the
pilot's 25 orders show real passive resting orders have been placed before.

## 8. Closure clause

The probe closes when **either**: (a) 40 orders are recorded with the Leg A
interval fully inside one of the decision bands in §3, or (b) 10 games have
been recorded regardless of interval width — at which point the result is
reported as inconclusive with its measured bound, and the phantom share
carries that bound as an explicit caveat wherever it appears.

It does not close on a favourable interim read. No peeking rule: the decision
bands are evaluated once, at closure.

## 9. What this cannot rule out

- The market-impact confound (§6.1). A probe can show our order sits where
  the model assumes; it cannot show the market would have behaved the same
  way had we been quoting continuously at scale.
- Regime dependence. Confirming A1 on in-game WNBA/CFB says nothing about
  pregame, other sports, or thin late-game books.
- **A1 holding while the phantom finding is still wrong for another reason.**
  A1 is one assumption in the classifier; confirming it does not certify the
  rest of the pipeline.

## 10. If real resting orders are not available

If the system is shadow-mode by DB or config constraint and no new orders can
be placed, the best available proxy is the **historical passive-order
reconstruction**: every real order in `venue_activities` with
`passiveExecution`, its rest window, and the book through that window. That
is the pilot, scaled — currently 25 BUY orders.

State plainly what it cannot do:
- It is **conditioned on execution** — every order in it filled, so it cannot
  measure Leg B at all (the denominator, crossing episodes without a fill,
  is missing by construction).
- It cannot be sized to a target; we get whatever the strategies happened to
  place, all BUY, all in markets they chose.
- It is retrospective, so book cadence is whatever was recorded, and a
  one-tick violation may be invisible.

**It can bound Leg A and nothing else.** That is genuinely useful — Leg A is
the assumption the phantom share depends on — but the record should then say
the phantom share is supported by a proxy conditioned on execution, and that
A2, the sufficiency leg, remains entirely untested.

---

No in-sample result justifies capital. The forward test is the evidence.
