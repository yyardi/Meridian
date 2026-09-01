# The late-game cell — one liquidity mechanism, two symptoms (B × D joint note)

**Status: descriptive, in-sample, hypothesis-generating.** Drafted by Quant B,
reviewed by Quant D (sign-off conditions applied in this revision); pins
`20260901T195202Z`; substrate A's `roundtrip_ledger_20260901T195202Z.csv`.
D's numbers are from `analysis/pulse_execution_decomposition.md` (merged,
PR #122; the withdrawal autopsy is its Addendum 2, PR #126 — both on
main). B's numbers are from
`analysis/pulse_loss_map_report.md` (+ addendum) and
`analysis/withdrawal_autopsy.py`.

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

Supporting tape fact (descriptive medians, no new clustered intervals):
books at intent time are already wider late — median spread 8¢ (filled) /
10¢ (unfilled) in late states vs 4¢ / 7¢ early.

**Structural note, so nobody reads it as evidence:** the tape has no
`expired` state for entries at all — the engine withdraws an entry the
moment its own fair value stops clearing the resting price
(`live.py` entry management), so ALL unfilled entries everywhere end
`withdrawn` (1,019) or open-at-export (11). "Every late unfilled intent
was withdrawn" is true by construction and discriminates nothing.

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

## The withdrawal autopsy — the entry-side mechanism, measured twice

Both agents autopsied the 1,019 withdrawals independently (B:
`analysis/withdrawal_autopsy.py` against the pinned 200ms tick export;
D: their script's section 6b, mutation-tested); the implementations
reconcile (B 66.2% reached-later vs D 63.9% + 3.9% sub-cycle crossings —
definitional differences at the boundary).

* Orders rested median **~2.5 min** before the pull, and at the pull sat
  median **5.5¢ (early) / 7¢ (late)** from the fill price — only 13–18%
  within 2¢. The engine does not cancel at the door.
* **D's late unfilled excess is withdrawal-censored; post-pull, roughly
  half the late cell was never reachable at any patience (47.8% vs 30.4%
  early — shorter-window confound noted), and the reachable half was
  worth ~0** (D: −1.06¢/ct [−5.36, +3.25]; B, per-$ money-at-price at the
  cancelled limit: −11.5¢/$ [−27.3, +4.3], G=33).
* The entire unfilled-settle-better effect (D's +11.07¢/ct) sits in the
  **never-reachable** third (D: +33.34¢/ct [+29.50, +37.18]; B: +170¢/$
  [+41, +299] — wide, cheap-cost denominators). The fills the book never
  offered are the ones that were worth having: adverse selection stated
  as a reachability fact.

**Consequence for remedies:** patience or better placement is refuted
in-sample (the reachable half earns ~nothing). The only policy that
reaches the never-reachable third is **crossing at the touch — a taker
arm — priced against the spread plus the measured taker fee** (the
2.5¢/ct swing of docs/math/fees-and-spread.md). That is a forward-test
candidate, not a recommendation; the higher never-reachable share late
supports the liquidity mechanism, with the window confound carried.

## The remaining open check

The book-state question is still open in one direction: do the **pinned
ticks** (`live_ticks_pulse_games_20260901T195202Z.csv.gz`, all 34 games at
200ms) show thin or one-sided books at and shortly after late unfilled
intents, materially more often than early ones? The never-reachable split
above is consistent with yes, but book *state* (one-sidedness, depth at
touch) has not been read directly. If those books are two-sided and deep,
the shared-mechanism claim loses its entry-side symptom.

## What would falsify the joint claim forward

A forward cohort in which late-game unfilled share and late-game ride
share decouple (one elevated, the other at baseline); the book-state
check above failing; or a taker forward arm whose captured value in the
never-reachable states fails to clear spread + fee.

---

*Multiplicity: intervals quoted from B's loss map and D's decomposition
were counted in their source artifacts. This note adds B's 5 clustered
valuation intervals (autopsy) and 8 descriptive medians/shares; D's
addendum 2 carries its own accounting.*
