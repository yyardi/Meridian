# The late-game cell — one liquidity mechanism, two symptoms (B × D joint note)

**Status: descriptive, in-sample, hypothesis-generating.** Drafted by Quant B,
reviewed against Quant D's state profile; pins `20260901T195202Z`; substrate
A's `roundtrip_ledger_20260901T195202Z.csv`. D's numbers are quoted from
their execution decomposition (report commit a7d8f26, branch local pending
operator-authorized push — numbers quoted rather than linked for that
reason). B's numbers are from `analysis/pulse_loss_map_report.md` and its
2026-09-01 addendum.

**No in-sample result justifies capital. The forward test is the evidence.**

## The claim

In late-game states, one venue fact — the book withdrawing as the outcome
resolves — produces **two symptoms measured independently**:

* **Entries that never fill** (D): unfilled-intent share **41.6% in Q4+**
  (207/498) and **48.9% at <5 min** (89/182) against a **33.2–33.3%**
  early/mid baseline (1,030/2,974 intents, 33 games).
* **Positions that never exit** (B): ride share **16.6% in Q4** and
  **18.1% at 5–10 min** against a ~4–7% baseline (137/1,944 fills,
  34 games), and the ride leg loses −55 to −100¢/$ in every version ×
  market type.

Supporting tape fact (new here, descriptive — medians, no new clustered
intervals): books at intent time are already wider late — median spread
8¢ (filled) / 10¢ (unfilled) in late states vs 4¢ / 7¢ early — and every
one of the 177 late unfilled intents ended `withdrawn`, none `expired`.

## The discriminator — why "one mechanism" holds ONLY here

D's margin cut is **flat** (unfilled 35.9% at |margin| ≥ 10 vs 34.1%
below) exactly where B's ride share **spikes** (10.8% vs 4–7%). If a
single book-withdrawal mechanism drove both symptoms everywhere, the
blowout cell would show both. It shows only the exit-side symptom: in
decided-but-not-late games, entries still fill — the price simply never
comes back. So:

* **Late-game cell**: one mechanism, two symptoms — write-ups should treat
  D's unfilled excess and B's ride excess as two measurements of one fact.
* **Blowout (early/mid) cell**: the ride excess stands alone, and B's
  addendum applies — the dollars are adverse selection against a static
  exit (rides were worth 0.000 at book close; recovering the last
  two-sided quote saves ~$0 on this tape), with book death as the
  selection into ride status, not the P&L driver.
* **D's ~33% early baseline** is a third, separate phenomenon
  (price-never-came-back with a thick book) and is not claimed here.

## The check that ties the mechanism down before any forward test (D's
proposal — runnable on the same tape)

D's late-game unfilled excess is rule-unfilled (the mid never crossed the
resting limit). The shared-mechanism claim therefore predicts: **the tick
tape around those late unfilled intents should show thin or one-sided
books at and shortly after intent time**, materially more often than
around early unfilled intents. This is answerable now from the local tick
DB (the 200ms stream; note the recorder writes to local postgres, not
Supabase) with no forward data. If those books are two-sided and deep, the
shared-mechanism claim is wrong and the two symptoms are coincidence at
this n.

## What would falsify the joint claim forward

A forward cohort in which late-game unfilled share and late-game ride
share decouple (one elevated, the other at baseline); or the book-state
check above failing in-sample.

---

*Multiplicity: every interval quoted here was already counted in its
source artifact (B: 197+12 post-hoc; D: their report's own accounting).
This note adds 8 descriptive medians/shares and no new clustered
intervals.*
