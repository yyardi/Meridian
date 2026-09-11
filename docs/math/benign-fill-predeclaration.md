# Benign-fill frequency — pre-declaration

Written **before** the statistic was computed. Sample size was checked first
(that is not an outcome); no classification was run until this file existed.

## Question

a1 established that the simulator books a fill only when the book moves
adversely through us (`mid <= bid` requires the mid to FALL). The benign case —
a seller crosses to our resting bid while the ask stays put — produces no row.
Every making number we hold is therefore measured on a censored population.

**How often does the benign case occur, relative to the adverse case the
simulator does record?**

## Instrument

`eval_delta_book_levels.csv.gz` (price + **size** per level, 9,030,144 rows,
459,855 snapshots) joined to `eval_delta_snapshot_keys.csv.gz` (market_slug,
captured_at) on `snapshot_id`. WNBA, 2026-07-31 → 2026-08-20.

**Population:** consecutive covered snapshots of the same market with gap
**≤ 2.0s** — 7,100 transitions across 645 markets.

## Classification (declared before computing)

For consecutive snapshots `t → t+1` of one market:

- **ADVERSE** — best-bid PRICE fell. *This is the simulator's only fill condition.*
- **BENIGN CANDIDATE** — best-bid price unchanged **and** best-ask price
  unchanged **and** best-bid SIZE decreased.
- **OTHER** — everything else.

**Statistic:** `benign / (benign + adverse)`.

## ★ Declared ceilings — the numerator is an UPPER BOUND

1. **CANNOT DISTINGUISH A TRADE FROM A CANCEL.** A maker pulling an order
   decreases size with no price move, identically to a seller hitting the bid.
   Separating them needs trade prints at book cadence, and **no export has
   both**: `cfb_trade_stats` carries prints but its per-market poll gap is
   **220s median** (0.0% under 10s); `eval_delta_book_levels` carries depth but
   the exported subset is **11s median** per market; `live_ticks` /
   `market_snapshots` carry touch prices only and are **structurally blind** —
   a benign fill leaves the touch unchanged and so writes nothing;
   `qv2_queue_ahead`'s own README pre-declares that crossing size is
   unavailable. So BENIGN CANDIDATE counts **trades and cancels together.**

2. **THE TEST IS THEREFORE ONE-SIDED, AND THIS IS THE POINT.** A **small**
   upper bound is decisive: if even trades-plus-cancels is rare, benign fills
   are rarer still. A **large** upper bound is **uninformative** — cancels could
   account for all of it. This test can kill passive joining; it cannot save it.

3. 2s sampling can miss sub-2s round trips: the book may move and revert inside
   a gap and read as unchanged.

4. Measures **opportunity at the touch**, not fills we would receive. Queue
   position is not modelled (`qv2_queue_ahead` is a separate instrument).

5. Different population from the fills export — WNBA Jul–Aug here versus CFB
   Sept in `quote_fills_classified`. Not cross-validatable.

6. **The rate must NOT be estimated from `quote_fills_classified`.** That file
   contains only booked fills, so by construction it cannot contain the benign
   event. A rate from it would be inferred from a population that could not hold
   the phenomenon.

## Decision rule (declared before seeing the number)

- **Upper bound < 10%** → benign fills are rare. Passive joining is dead
  regardless of pricing, and the $278 probe would only confirm it.
- **Upper bound ≥ 10%** → uninformative alone. The censoring cannot be ruled
  out, and the probe becomes the only instrument that settles it.

## RESULT — run 2026-09-06, after the above was written

Registered test, gap ≤ 2.0s: **6,407 transitions, 591 markets.**

| | n |
|---|---|
| ADVERSE (bid fell — the simulator's only fill condition) | 86 |
| BENIGN CANDIDATE (touch held, bid size fell) | 18 |
| OTHER (no touch-level bid event) | 6,303 |

**Upper bound = 17.3%, 95% CI [10.0, 24.6], n = 104.**
**Verdict by the registered rule: UNINFORMATIVE — the probe is required.**

### ★ Two things that must travel with that number

**1. It is underpowered, and its CI lower bound sits EXACTLY on the decision
threshold (10.0% against a 10% rule).** A rule firing within a rounding error of
its own boundary is not a verdict. Only **1.6%** of transitions carry any
touch-level bid event, so the population that can contain the phenomenon is
n=104, not n=6,407 — two orders of magnitude smaller than the population
sampled.

**2. Post-hoc sensitivity (NOT the registered test) — the estimate rises with
the gap, which is contamination, not signal:**

| gap | events | adverse | benign | upper bound | 95% CI |
|---|---|---|---|---|---|
| 1s | 32 | 27 | 5 | 15.6% | [3.0, 28.2] |
| **2s (registered)** | **104** | **86** | **18** | **17.3%** | **[10.0, 24.6]** |
| 5s | 556 | 433 | 123 | 22.1% | [18.7, 25.6] |
| 10s | 2,157 | 1,618 | 539 | 25.0% | [23.2, 26.8] |
| 30s | 35,309 | 26,736 | 8,573 | 24.3% | [23.8, 24.7] |

Longer gaps admit more book-moved-and-reverted, so the tighter n is the
*cleaner* estimate and the larger n the *dirtier* one. **Do not quote the 30s
row because it has the narrowest interval** — its precision is bought with
contamination.

## ★ AMENDMENT 1 — the registered definition was too narrow, and correcting it
## RAISES the number while making it a defensible bound

Registered BENIGN required the bid PRICE to hold. But a1's benign case is *"a
seller crosses to our resting bid while the ask stays put"* — and a seller who
takes our **whole** level drops the bid while the ask still stays put. Those
events were registered as ADVERSE. Full cross-tab at gap ≤2s, n=118:

| | ask HELD | ask MOVED |
|---|---|---|
| **bid HELD, size down** | **18** | 14 |
| **bid FELL** | **10** | 76 |

- Registered benign (bid held + size down + ask held) = **18** → 17.3% of 104.
- a1's benign, the ask-HELD column = **18 + 10 = 28** → **23.7% of 118**.

**This means the earlier "upper bound" label was under-derived.** Ceiling 1
(cancels) pushes the number UP; this newly-measured effect pushed it DOWN. Two
contaminations in opposite directions is not a bound in either direction — I
declared one and missed the other. It is now measured and worth **10 events**,
so 23.7% absorbs it and **is** an upper bound on the true benign *trade* share,
with cancels still inflating it.

**64% of touch events (76/118) moved BOTH sides** — two-sided repricing, not
anyone crossing to us.

**Queue position then pushes the realised rate below the event rate:** an
adverse sweep clears the level so everyone resting fills; a benign cross is
partial and fills only the front of the queue.

## Conclusion

**The test could only ever have killed passive joining, and it failed to kill
it.** Every threshold puts the upper bound above the 10% line, so the one cheap
decisive outcome — *benign fills are rare, do not bother* — did not occur.

**This does NOT establish that benign fills are common.** The numerator counts
cancels as well as trades, so a large upper bound is exactly as consistent with
"makers pull often" as with "sellers hit the bid often". Separating them needs
trade prints at book cadence, which **no export in `backups/exports/` carries**.

**So: the exports cannot answer the question, and the $278 probe is now the
load-bearing instrument rather than a confirmation.** That is a stronger
statement than the one we could have made before running this, because the
cheap route has been tried and its ceiling measured rather than assumed.

## ★★ ALWAYS NAME WHICH LINE THE VERDICT IS AGAINST

My registered kill line was **10%**. Quant A's break-even floor for the making
thesis is **r ≥ 48%** (up to 70% once queue and partials bite). Both were set
independently, before either of us saw the other's work.

- **Against my 10% line:** the test FAILED to kill passive joining.
- **Against A's 48% line:** 23.7% — with cancels still inflating it and queue
  effects pushing the realised rate lower — **kills it.**

**The same number, opposite verdicts, because the thresholds answer different
questions.** Any statement of this result that does not name its line is
uninterpretable. Reconciliation with A is open on the one thing I cannot check
alone: whether A's denominator (fills a resting order receives) and mine
(touch-level bid events in the tape) are the same set. They coincide only if we
are at the touch whenever such an event occurs.

**If A confirms they are commensurable, the probe becomes a confirmation rather
than an experiment — a different spending decision, and the operator's.**
