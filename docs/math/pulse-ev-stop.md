# PULSE #9 — the EV stop (registration)

**Status: REGISTERED, NOTHING BUILT.** Written 2026-08-24, before
implementation. This section may not be edited after the eval first runs at
floor — append below the line.

## The hypothesis, from the ledger it has waited in

Ledger #9, verbatim: **"Stop-loss in EV terms. Exit when *fair value*
falls to your price — not when the price falls."** Marked "missing, and
the important one" since the ledger was written; blocked then on a live
fair value that now exists.

## The rule — zero new tunables

The current stop anchors to sunk cost: it fires only when FV moves 10¢
through the ENTRY price, holding through ten cents of believed-lost value
first. The EV stop replaces the trigger with edge exhaustion:

    yes position:  reprice the exit to the touch when fv <= entry_price
    no  position:  reprice the exit to the touch when fv >= entry_price

— the model no longer believes the position carries positive expected
value at the price it was taken, so it stops resting at the profit target
and asks to leave. Still a limit, never a cross; the existing one-way stop
latch prevents flapping; exits carry `reason='ev_stop'`, so rows
self-describe their rule regime. No threshold exists to tune: the trigger
is the ledger's own sentence.

## Tape semantics

This is a POSITION-MANAGEMENT rule change, mid-accrual, and is marked like
every semantics change before it: a dated note in docs/math/pulse-live.md
at deploy, with the exit `reason` values ('fv_adverse' before, 'ev_stop'
after) as the per-row regime marker. Sizing populations are untouched.

## Gate and deployment

* **Eval**: the registered decision rule in `simulate_market` gains the EV
  stop as an arm; paired money-at-price (old stop − EV stop) clustered by
  game is the criterion, floors the standard 10 post-registration games /
  100 filled entries in the arm. Calibration is untouched by construction
  (the stop changes no estimate) and is asserted as a consistency check.
* **Deployment is not a verdict** (the v4 precedent): the operator has
  prioritised this rule; it may deploy to the shadow engine on build, with
  the gate reading offline as data accrues. A FAIL at floor reverts the
  live rule — registered now so reverting is mechanical, not a debate.
* State-based, untouched by F8's feed-lag finding.

---

*Registered 2026-08-24. Results append below this line, never above it.*

## 2026-08-26 — correction: the registration's true instant

The header's "Written 2026-08-24" and the eval's original gate constant
(2026-08-24T23:00Z) were a conversation-date drift by the author: this
document's first commit is c375aab, **2026-08-25T23:08:20Z**, merged at
23:09Z the same night. The error runs in the dangerous direction — the
2026-08-25 00:00–04:15Z slate would have gated on a registration that did
not exist while those games were being recorded. `EV_STOP_REGISTERED_AT`
is corrected to the commit instant. No at-floor number has ever been read
from the wrong cutoff (the gate cohort printed NO DATA on every run to
date), so the correction is costless — which is exactly why it happens
now and not after the first read.

## 2026-08-27 — known limit: the exit book is not always there

**Recorded before the first gate read.** Bounds interpretation and adds a
diagnostic; changes no registered term. Source:
[bookless-endgames.md](bookless-endgames.md).

The stop's exit book exists precisely while the game is in question and
evaporates once it isn't. Measured across the 22 signal-covered games: **9
endgames carried no two-sided winner quote inside the final 5:00**, several
one-sided from Q3 onward (atl-la 08-20: 7,866 Q4 rows, zero two-sided). An exit
rule works where you least need it and disappears where you would most want out.

Therefore:

1. **A PASS at this gate is a statement about games where an exit existed.** The
   honest reading is *"the stop works where the venue quoted an exit"* — never
   *"the stop works."*
2. **Sizing that leans on the stop must price the possibility that there is no
   exit at any price** once a position is sufficiently wrong: the states where
   the stop would fire hardest overlap the states where the book is gone.
3. The eval report should carry a **stop-unreachable count** — windows where the
   rule fired and no two-sided book existed — so this limit is measured as the
   cohort accrues rather than assumed. **Diagnostic line, never gate-eligible.**
