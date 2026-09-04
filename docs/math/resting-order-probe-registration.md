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
and P1 is small.

### MEASURED 2026-09-04 — and the validity gate decides the answer

`qv2_queue_ahead_20260904T144200Z`, 623,036 rows carrying `our_bid_qty`:

| | first in queue (qty=0) | median queue-ahead |
|---|---|---|
| ungated | **17.1%** | 15 |
| bid-side price identity | 1.6% | 30 |
| **both-side price identity (registered gate)** | **1.2%** | **28** |

The depth sample is only valid when the touch has not moved since it was
fetched — price identity, not elapsed time, because in-play touch survival is
median 2s while these samples are median 11.4s old (p90 47.8s). 30.6% of rows
fail that gate.

**The zeros are almost entirely a staleness artifact:**

    P(queue-ahead = 0 | touch UNCHANGED) =  1.2%
    P(queue-ahead = 0 | touch MOVED)     = 53.0%
    95.0% of all 106,560 zeros sit in stale-touch rows

The mechanism is direct: when the touch moves, our quote price is no longer
where the stale sample looked, so no size is recorded there and a spurious
zero is manufactured.

**So the countervailing mechanism is close to dead, and P1 is close to
universal.** We are first in queue roughly **one time in eighty**, not one in
six, and otherwise sit behind a median of 28 contracts. A 1-contract order
needs a cross clearing ~28 before it reaches us, nearly always. This is now a
measurement rather than an argument, and it did not come out the way I
guessed when I registered the countervailing case.

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

---

## AMENDMENT 1 — my own decision rule was unreachable, and worse than unreachable

Applying B's registration check (compute the interval width the arm will have,
and ask whether the threshold can distinguish its branches) to §3's Leg A bands
— `<1%` CONFIRMED, `1–8%` SUPPORTED, `>8%` REFUTED — at the §7 sample of ~40
orders:

    best possible outcome is ZERO violations; achievable 95% upper bound:
      n =  25   13.32%
      n =  40    8.76%      <- the planned sample
      n =  60    6.02%
      n = 100    3.70%
      n = 300    1.26%
      n = 500    0.76%      <- first n that can reach the CONFIRMED band

**Two defects, and the second is severe.**

1. The `<1%` CONFIRMED branch is **unreachable at any n below ~500.** As
   written it is decoration.
2. At n=40 a **perfect result — zero violations in every order — yields an
   upper bound of 8.76%, which falls in the `>8%` REFUTED band.** The rule
   returns "A1 REFUTED as used" on a flawless outcome. That is not merely an
   underpowered rule, it is one whose branches are mis-ordered against what the
   design can produce.

**Corrected sample requirement.** The threshold that matters is 8%, because
that is roughly where the phantom share moves by more than 5 points. To
conclude the rate is below it, the upper bound must clear it:

    n >= 60   upper bound 6.02%   MINIMUM for the rule to be able to say
                                  anything favourable
    n >= 100  upper bound 3.70%   comfortable
    n >= 300  upper bound 1.26%   approaches the original CONFIRMED intent

**§7's "~40 orders" is withdrawn and replaced by n >= 60, with n = 100
recommended.** Re-pricing §7's capital at n=100 with the same 10-minute
windows: ~348 expected fills, worst case ~$278, expected P&L ~-$11.8, hard stop
400 contracts. Still small, and now attached to a rule that can return a
favourable verdict.

**The general check, which neither B nor I ran and both of us needed:** before
registering a threshold, compute the interval the arm will actually have and
ask whether the threshold can separate the branches. If the interval spans
both, the rule is decoration. If the best achievable outcome lands in the
adverse branch, the rule is inverted. Cheap, and it belongs at registration
time rather than in the write-up.

## AMENDMENT 2 — the rule was PREDETERMINED at n=40, and CONFIRMED is wallet-bound

B's structural version of the check, which subsumes the clause I proposed:
**compute the achievable outcome range, project it onto the branch structure,
and inspect the image.**

    image is a single branch            -> PREDETERMINED (answer fixed before the run)
    image includes adverse at best case -> INVERTED (success reports as failure)
    a branch outside the image          -> DEAD BRANCH (decoration)
    image spans branches but the
      interval exceeds the band widths  -> CANNOT DISCRIMINATE

**At n=40 the rule was PREDETERMINED, not merely inverted.** The upper bound
runs from ~8.8% (zero violations) to 100%, so **all 41 possible outcomes return
REFUTED.** The probe would have spent real capital to compute an answer fixed
before the first order rested. That is worse than my own diagnosis and B's
framing is what exposes it — I checked only the best case, which finds inversion
but cannot find predetermination.

**And n=100 has a dead branch.** CONFIRMED needs an upper bound below 1%, so at
n=100 (best case ~3.6%) the achievable image is {SUPPORTED, REFUTED}. The rule
is advertised as three-band and is structurally two-band.

**PIN THE INTERVAL METHOD — the threshold moves with it, and we disagreed.**
Smallest n whose best case reaches <1%:

    Clopper-Pearson (exact)   n = 299
    rule of three (3/n)       n = 300
    Wilson                    n = 381   <- mine
    (B computed 368, a fourth answer)

**Registered method: Wilson**, matching `clustered_mean`'s convention elsewhere
in this program, giving **n = 381**. Any future citation of "the n needed for
CONFIRMED" must name the method; it is a 27% spread otherwise.

### ★ CONFIRMED is not reachable within the wallet at the registered window

At the measured 0.348 fills per standing minute, worst case = fills x $0.80:

    n=100 x 10-min   ~348 fills   worst case   $278
    n=381 x 10-min  ~1,326 fills  worst case $1,061   <- EXCEEDS the $1,000 wallet
    n=381 x  5-min    ~663 fills  worst case   $530

**So Leg A CONFIRMED cannot be bought at the registered 10-minute window
without breaching the wallet at unit size.** It is reachable at 5-minute
windows for ~$530 — but shorter windows halve the Leg B crossing episodes,
which is the leg that tests sufficiency and has no other instrument.

**That is a genuine trade-off and it is the operator's to make, not mine:**

    (a) n=100, 10-min   ~$278   Leg A best outcome SUPPORTED; Leg B strongest
    (b) n=381,  5-min   ~$530   Leg A can reach CONFIRMED; Leg B halved
    (c) n=381, 10-min  ~$1,061  both strong; breaches the wallet at unit size

**Recommendation: (a).** SUPPORTED is a real verdict — it says the phantom share
carries a bounded error band — and Leg B is the leg with no alternative
instrument, since A1 has the historical passive-order reconstruction as a proxy
and A2 has nothing. Buying CONFIRMED by weakening the only test of sufficiency
is the wrong trade.

**The CONFIRMED band stays in the rule, explicitly marked unreachable at the
recommended sample**, rather than being deleted. Deleting it would hide that
the probe cannot fully close A1 at any price the wallet allows.

## AMENDMENT 3 — sidedness, not method. And my Leg B argument was an artifact.

B resolved the four-way n disagreement and it was never four methods:

    Clopper-Pearson, ONE-sided 95%     n = 299
    rule of three (approximates it)    n = 300
    Clopper-Pearson, TWO-sided 95%     n = 368
    Wilson, two-sided 95%              n = 381

    sidedness  299 -> 368  = +23%   (same method)
    method     368 -> 381  = +3.5%  (same alpha)

**The 27% spread is ~85% sidedness and ~15% method.** Amendment 2 pinned the
method and left sidedness implicit, which pinned the smaller half. Verified
independently: Clopper-Pearson upper bound for 0/n is `1 - alpha^(1/n)`, giving
299 at alpha=0.05 and 368 at alpha=0.025.

**Registered: ONE-SIDED 95%, n = 299**, and the sidedness is named in every
citation of this number. All three Leg A bands are on the *upper* bound of a
violation rate — nobody wants a lower bound on how often the venue violated —
so the question is one-sided by construction, and a two-sided interval silently
applies a 97.5% standard while the document says 95%.

The switch must be stated loudly because the program's convention elsewhere
(`clustered_mean`) is two-sided 95%. Two numbers both labelled "95%" meaning
different things is precisely the basis-does-not-travel failure catalogued
today. **This is adopted because it matches the question, and it would be
adopted identically if it pushed n up.**

### ★ My recommendation of n=100 is WITHDRAWN. It rested on an artifact.

Amendment 2 recommended n=100 because reaching CONFIRMED appeared to require
halving the window to 5 minutes, which would have halved Leg B's crossing
episodes. **That constraint dissolves under one-sided.** No window shortening
is needed, and Leg B data scales with total standing time (n x window), not
with n alone:

    n=100 x 10-min   1,000 order-min   ~348 episodes    worst case $278
    n=299 x 10-min   2,990 order-min  ~1,041 episodes   worst case $832

**n=299 at the SAME window dominates n=100 on both legs simultaneously** — it
reaches CONFIRMED on Leg A *and* triples Leg B. My "trading away the only test
of sufficiency" argument was correct about the trade and wrong that the trade
existed; it was an artifact of a sidedness convention, not a fact about the
design.

**So the choice is now purely capital appetite, and it is the operator's:**

    n=100   ~$278   dominated on the science; Leg A cannot return CONFIRMED
    n=299   ~$832   reaches CONFIRMED, 3x Leg B; worst case is 83% of the wallet

I do not recommend between them. $832 as a worst case against a $1,000 wallet
is a risk judgement, not an analytical one, and the worst case assumes every
fill settles maximally against us, which cannot occur. What I will say is that
**n=100 is now dominated rather than cheaper-but-adequate**, and it should not
be presented as the analytically preferred option.

**Caps must be rescaled at n=299.** §7's 4 concurrent orders / 5 fills per order
/ 400-contract stop were sized for n=100. At n=299 the total-contract stop
becomes the binding control and should be set from the wallet directly, not
from the order count.

## ★ AMENDMENT 4 — the binomial assumed independence. ALL FOUR n FIGURES ARE VOID.

B's objection, and it is fatal to Amendments 2 and 3 alike: **every n we computed
(299 / 300 / 368 / 381) came from a binomial interval, which treats the orders as
independent.** They are not. This programme maintains `clustered_mean`
specifically because its observations are not, and I repriced a binomial without
asking whether independence held.

**This is my own §3 error one level up.** §3 says: *"Ticks inside one order are
heavily correlated; the honest effective N is orders, not ticks."* Correct, and
it stops one level short. **Orders inside one game are also correlated** — a
venue misbehaving for a stretch, a feed degrading, one session's book behaving
unusually. I congratulated the document on catching the unit error while
committing it at the next level up.

### The allocation dominates the order count, and §7 never specified it

CFB in-game span is ~3.3h = 198 minutes. At 10-minute windows one market hosts
~19 sequential orders, so 6–8 markets per game is **120–150 orders per game**.
§7's "n orders" says nothing about how they are spread, and that choice decides
the test:

    299 orders, design effect 1 + (m-1)*rho at rho = 0.05

    allocation                         G     m    deff   eff n   bound
    concentrated: 2 games              2   150    8.45      35   8.48%   <- fails even SUPPORTED
    moderate: 20 games                20    15    1.70     176   1.71%
    spread: 100 games                100     3    1.10     272   1.10%

    perfectly clustered (rho = 1): effective n = GAMES
      G=20 -> 15.0%    G=100 -> 3.0%    G=300 -> 1.0%

**299 orders concentrated in 2 games is worth ~35 independent observations and
cannot reach even the SUPPORTED band. The same 299 orders spread 3-per-game
across 100 games is worth ~272 and nearly reaches CONFIRMED.** Same capital,
same window, same order count — a factor of ~8 in information, decided by a
parameter the registration never mentioned.

### Registered: the sample requirement is GAMES, not orders

    n >= 100 GAMES, <= 3 orders per game, 10-minute windows

Tomorrow's CFB slate carries 103 games, which is exactly this structure. The
binding constraint is **breadth of games, not depth of orders**, and any
future citation must give the allocation alongside the count.

### Pilot evidence on clustering — real but far too thin to settle it

The two violations in the 25-order pilot fall in **different markets, different
games, 168.5 hours apart**, across 19 distinct markets. That is consistent with
independence and is **two events**. It cannot estimate rho, and rho is what the
whole table above turns on. The honest position is that rho is unmeasured, the
design must be robust to it being non-zero, and the probe should report a
cluster-robust interval with df = games-1 rather than a binomial.

**Amendments 2 and 3's cost tables are void as stated**, since they priced order
counts under an independence assumption that was never checked. The sidedness
argument itself survives — the question is one-sided by construction — but it
may not be cashed as a saving until rho is bounded.

## AMENDMENT 5 — projection check on the corrected design. Four items, all verified here.

The n=40 predetermination is gone: no branch predetermined, none dead, all
verdicts reachable. These are what remains, each recomputed independently
rather than taken from the report.

### 5.1 CONFIRMED is a knife-edge and ONE SLATE CANNOT RELIABLY BUY IT

    one-sided Clopper-Pearson, zero violations
      n=298   1.0002%   SUPPORTED
      n=299   0.9969%   CONFIRMED   <- threshold
      n=309   0.9648%   CONFIRMED

Tomorrow's slate is **103 games**, and `<= 3 orders per game` makes 309 a
CEILING: **headroom is 10 orders against a requirement of 299**, and only if
every game yields its full three. Four games short of full yield ends
CONFIRMED before a single violation occurs.

That is not predetermination and not a dead branch — it is a verdict reachable
only if nothing whatever goes wrong, which a pre-registered band should not be.

**Registered: CONFIRMED requires ACCUMULATION ACROSS SLATES**, with NFL from
2026-09-09 as the second. Raising orders-per-game is the wrong fix — it raises
m, which raises the design effect, which is precisely what Amendment 4 says to
avoid. **More games beats more depth, and one Saturday does not have enough.**
The probe is therefore explicitly not all-or-nothing on a single slate.

### 5.2 ★ TWO REGISTERED METHODS DISAGREE — one must be named

The registration named one-sided Clopper-Pearson AND cluster-robust at
df = games-1. On identical data, one violation in 300 orders over 100 games:

    one-sided Clopper-Pearson   1.571%   SUPPORTED
    cluster-robust df=G-1       0.887%   CONFIRMED

**Opposite verdicts.** Registering both means the verdict is chosen after the
data exist — stage four wearing a different hat, in the document that has been
cataloguing stage four all evening.

**REGISTERED: one-sided Clopper-Pearson, as the sole verdict source.**

The reason is not that it is conservative in this cell — it is that **the
allocation makes it adequate.** CP assumes independence, which is exactly what
Amendment 4 warned about. But `<= 3 orders per game` caps the design effect at
`1 + (m-1)*rho = 1 + 2*rho` — about **1.10 at rho = 0.05, and at most 3.0 even
at rho = 1**. The allocation bounds CP's understatement to something small and
known, rather than leaving it unbounded.

**This is conditional on the allocation and fails with it.** If orders per game
are ever raised above 3, CP stops being adequate and the method must be
revisited. The two constraints are one decision, not two.

Cluster-robust may be reported as a DIAGNOSTIC beside it, never as a verdict.

### 5.3 The cluster-robust interval collapses to zero width on the best case

Zero violations makes every cluster residual zero, so the sandwich's meat is
zero, the standard error is **exactly 0.000000**, and the interval is
**[0, 0]** — the rate reported as exactly zero with no uncertainty, on
precisely the outcome we most hope for. Verified: CP returns a finite 0.9936%
on the same data.

A zero-width interval is a broken computation being read as certainty. This is
the second reason cluster-robust is not the verdict source, and if it is
reported as a diagnostic **the zero-violation case must print "undefined"
rather than [0, 0]**.

### 5.4 The bands cannot be stated as violation COUNTS — a property, not a defect

Under clustering the verdict depends on how violations distribute, not only on
how many. Fifteen violations in 300 orders:

    one per game, 15 games    6.99%   SUPPORTED
    packed into 5 games       8.64%   REFUTED

Correct behaviour — concentrated violations carry less information — but it
means **no violation count maps to a verdict on its own.** Any statement of the
form "k violations gives verdict X" is ill-formed and must not appear in the
write-up. The bands are on the interval, never on the count.

## AMENDMENT 6 — randomised quote offset, pinned. Projection re-run on the augmented design.

**Why:** the coupling design's open parameter is `g = d ln ν / d(price)`, the
fill-intensity semi-elasticity, and it decides the **sign** of the skew
correction (`λ_trade < λ*` iff `g < 1/h`). The probe as registered rests every
order at the touch, so it observes `ν` at one price point and **cannot estimate
`g` at all** — no variation in the independent variable.

### The change, pinned before it runs

    offset_ticks ~ uniform{-1, 0, +1, +2} relative to the best bid,
      negative = inside the spread (more aggressive), post-only clamp respected

    RECORD per order: offset_ticks, touch-at-insert, fill outcome and size,
      and TIME AT RISK (insert -> fill-or-cancel)

**Time at risk is the column that does not exist today**, and without it `ν` is
a count rather than a rate. That alone justifies the change.

**Randomisation discipline (tonight's own lesson):** the offset is drawn from
the fixed set above by a **seeded generator, with the seed and the drawn value
recorded per order**, so the allocation is auditable afterwards. It must be
**independent of market state** — an offset chosen by anything responsive to
spread, volatility or inventory re-introduces exactly the selection this
programme spent the day removing.

### Four-door projection on the augmented design

**No existing verdict is split.** Leg A's invariant — our order in the book
forces `best_bid >= B` — holds at ANY resting price, so all ~300 orders
contribute to Leg A regardless of offset. Leg B's primary can be pooled across
offsets; stratifying it is a bonus, not a requirement. **Only the new `g`
regression uses the four strata.**

**Leg A's exposure improves.** Passive offsets rest longer, so total at-risk
time rises even though order count is unchanged (simulated, g = 50, 10-min
windows, 300 orders):

    all at the touch (registered)   833 order-min at risk   fill share 97.0%
    randomised offsets              979 order-min at risk   fill share 92.0%
                                    => +17% exposure, ~5% fewer fills

    per offset:  -1c  rate 0.574/min  mean life 1.74 min  filled 99.7%
                  0c  rate 0.348/min  mean life 2.80 min  filled 96.9%
                 +1c  rate 0.211/min  mean life 4.17 min  filled 87.6%
                 +2c  rate 0.128/min  mean life 5.64 min  filled 71.7%

So Leg A gains sensitivity, Leg B gains stratification, and **capital falls
slightly** because fewer orders fill.

### What the probe buys on `g`: the SIGN, not the magnitude

Poisson fit on fill counts with a `log(time at risk)` offset, game-clustered,
300 orders over 100 games (40 replications per point):

    true g   mean est   mean se    bias    sign of (g - 1/h) resolved
      20       19.8       5.3      -0.2         100%
      35       34.7       5.5      -0.3          78%
      50       49.0       5.6      -1.0           8%   <- at the threshold
      65       63.9       5.8      -1.1          68%
      90       88.4       6.3      -1.6         100%

**The design resolves the sign when `g` is roughly 15 units or more from
`1/h = 50` — about 30% away — and cannot near the threshold.** The 8% at
`g = 50` exactly is the nominal false-positive rate, which is the correct
behaviour rather than a failure.

**And the failure is benign by construction.** `λ_trade = λ* + (h − 1/g)/d`, so
when `g ≈ 1/h` the correction term is ≈ 0. **The design fails to resolve the
sign exactly when the sign matters least.** An unresolved result therefore
licenses quoting at `λ*` rather than leaving the parameter undetermined.

The **magnitude** of `g` is estimated to about ±11 (2 SE), which is loose. So:
the probe buys the direction of the skew correction, and only a rough size.
The direction is the decision-relevant half.

### A harness defect caught before it was reported

My first power run used `log(max(fills, 0.5)/time)` to dodge log-of-zero. That
floor biased the slope badly — at true `g = 50` it estimated 66 and "resolved"
a sign that is unresolvable at the threshold by construction. **The tell was
the impossible result, not the arithmetic.** Replaced with a Poisson MLE on
counts with a `log(time)` offset, which handles zero-fill cells correctly and
is near-unbiased. Recorded because the same class of harness error was caught
by B an hour earlier, and both times the instrument was the suspect before the
finding was.
