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

### A2 is not only a count problem — a named prediction, sign fixed in advance

My first framing ("a count problem, not a per-fill problem") was wrong in the
unfavourable direction, and the manager's correction is registered here as a
falsifiable prediction rather than a caveat:

> **P1.** The fills we would actually have received are **not a random
> subset** of the 6,255. A small order fills when the cross is large enough to
> sweep the queue ahead of it, so realization is **selected on crossing
> size** — and crossing size is the classic correlate of informed flow. The
> realized subset should therefore be **worse per fill** than the full "real"
> set, not merely smaller. **Predicted sign: realized markout < unrealized
> markout.**

The schema note sharpens this. `quote_v2_observations.our_bid_qty` is
documented as the resting size *at* our own quote price — "the queue we sit
behind (all of it has time priority; we just joined)". **We are always last in
queue at a price that already existed.** So P1's mechanism is the default
case, not an edge case.

**The countervailing mechanism, stated so the test can discriminate.** When
the touch moves to a price where nobody is resting, a quote posted there is
*first* in queue and fills on any cross, including small ones. If most of our
fills come from newly-created levels, queue-ahead is ~0, selection is weak,
and P1 is small. This is measurable directly: the distribution of
`our_bid_qty` at fill time separates the two worlds. A probe that finds
queue-ahead mostly zero refutes P1 without needing a real order.

**Falsification.** If realized fills mark out indistinguishably from
unrealized crossing episodes, P1 is dead and the count-only framing was
right. If they mark out worse, the mechanism is confirmed and −3.4c is
optimistic per fill as well as in count.

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

## 7. This is a proposal to the operator, with the capital stated

**Neither the manager nor I can place or modify a real order. The system is
shadow-mode and a DB constraint enforces it.** The pilot's 25 passive orders
were the operator's. So §7–8 are a request for the operator to spend, and the
number they should read is a dollar figure, not anyone's adjective for it.

**My first "cheapest version" was wrong and I am correcting it here.** I
proposed resting continuously in 6–8 markets through a game. At the measured
20.9 fills per standing-quote hour, six games × 2 hours × 8 markets is ~96
quote-hours and **~2,000 fills** — not the ~40 I implied. Continuous quoting
is a trading programme, not a probe.

**The bounded design.** An order rests for a fixed window, then stops,
whether or not it filled — so Leg B keeps its denominator (crossing episodes
without a fill), which cancelling on first fill would destroy.

At 0.348 fills per standing minute, for 48 orders:

| window | expected fills | worst-case capital | expected P&L at −3.4c |
|---|---|---|---|
| 5 min | ~84 | $67 | −$2.9 |
| **10 min** | **~167** | **$134** | **−$5.7** |
| 20 min | ~334 | $267 | −$11.4 |

Worst-case capital = contracts × max(p, 1−p), and the quotable band caps
that at $0.80 per contract. It assumes every fill settles maximally against
us, which cannot happen but is the number the operator should be shown.

**Recommended: 10-minute windows, 48 orders, hard stop at 200 contracts —
worst case $160, expected −$6.** Caps to enforce in code, not by intention:
max 4 concurrent resting orders, max 5 fills per order, hard total-contract
stop that cancels everything on breach.

**What it needs recorded** is in §4. `quote_v2_observations` already carries
much of it (see §10), so the new instrumentation is the order lifecycle, not
the book.

## 7a. The wide-market arm is blocked on a config decision, not on design

Confound §6.4 is stronger than I wrote it. We do not merely *happen* not to
quote wide markets — `MAX_SPREAD = 0.15` in
`core/quote/adverse_selection.py` gates them out, and there are zero fills
above 15c across all 38,465 in either league. The line sits between the CFB
board's median (11c) and its p75 (30c).

So the wide-market arm **cannot be run at all unless that constant is
changed**, and that is the operator's decision rather than a design choice
available to this registration. Two consequences:

- If the gate stands, the probe confirms A1 only where we already live, and
  every "touch-joining is dead as a family" statement remains scoped to the
  tight corner. That scope should be written into the claim, not left implied.
- Evidence from *below* the gate argues against a hidden opportunity: real
  fills at >=5c run −5.71c [−8.89, −2.52] over 1,044 fills, worse than the
  tight corner, with real share falling monotonically from 48% at <=1c to
  ~20% at 5c+. That is the direction P1's informed-flow mechanism predicts.
  It is not evidence about >15c, where we have never been allowed to look.

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

## 10. The proxy version — what runs with no real order at all

Since we are shadow-mode, this is the version that can start today. It is
better than I first thought, because part of the instrument already exists.

**For Leg A — the historical passive-order reconstruction.** Every real order
in `venue_activities` with `passiveExecution`, its rest window, and the book
through it. This is the pilot, scaled: currently 25 BUY orders, 2 violations.

What it cannot do:
- **Conditioned on execution** — every order in it filled. Orders that rested
  and never traded are structurally absent, and those are where a stale book
  is most likely.
- Cannot be sized to a target; we get whatever the strategies placed, all BUY,
  in markets they chose.
- Retrospective, so book cadence is whatever was recorded and a one-tick
  violation may be invisible.

It bounds Leg A and, being execution-conditioned, **cannot measure Leg B at
all** — the denominator (crossing episodes without a fill) is missing by
construction.

**★ For Leg B — `quote_v2_observations.our_bid_qty` / `our_ask_qty`.** This
changes the picture. Those columns record the **queue ahead of us at our own
quote price**, from the observation's own fresh depth fetch (not joined from
`book_levels`, so no cross-stream point-in-time hazard), gated by price
identity: `depth_best_bid/ask` equal to the touch at `observed_at` means the
sample is valid, different means unusable at any age.

That is the Leg B input, available without placing anything. The estimator:

    P(fill | cross) ~= P(crossing size > queue-ahead at our price)

Both distributions are measurable — queue-ahead from these columns, crossing
size from the trade prints. It yields a **quantitative bound on how much of
the 6,255 we would actually have received**, and it directly tests P1's
mechanism: if `our_bid_qty` is mostly zero we are usually first in queue,
selection is weak and P1 is small; if it is typically large, realization is
strongly size-selected and −3.4c is optimistic per fill too.

Coverage caveat: the table began 2026-09-04 and covers 532 of 833 fill
markets, so it describes the recent, covered subset — the same partial-
substrate hazard that has bitten this program twice. Check coverage before
quoting any number off it.

**What the proxy still cannot rule out, and it is the important residue:**
it estimates whether a cross would have *reached* us. It cannot establish
that our order was *in the book at all* — that is A1, and only a real order
tests it — nor that our presence would not have changed the flow (§6.1).

**So: the proxy bounds A2 quantitatively and A1 only through an
execution-conditioned sample of 25 orders. Until the operator chooses to
spend on real resting orders, the −3.4c carries a permanent asterisk, and
the honest form of that asterisk is: "the population is an upper bound whose
realized fraction is estimated, not measured, and the mechanical premise is
supported by 25 orders that all filled."**

---

No in-sample result justifies capital. The forward test is the evidence.
