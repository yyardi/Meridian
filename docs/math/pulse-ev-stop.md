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
