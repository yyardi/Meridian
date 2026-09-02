# Congestion-window detector — registration

**Quant B, 2026-09-02. REGISTERS AS AN INSTRUMENT:** this document makes
NO performance claim; any claim about congestion's effect on quoting
belongs to the QUOTE v2 congestion arm's gate, which cites this object
and adds its own floors, closure, and freeze commit. Signed by the
research agent (amendment-3 window, closed with the corrections folded
below).

## (1) The object

`analysis/congestion_detector.py` — **the file is the pin** (rule 12).
Authored at `d1fb6de` (quant-b/pulse-loss-map); on main via cherry-pick,
adding commit `cec9453`, content-identical.

Definition, normatively: a **self-clocked pure function of the consumer's
OWN observation stream** (t, ladder, rung, mid) in the consumer's own
receive clock — no cross-process timestamp join exists by construction;
venue-level pooling across all observed ladders. A **trigger** is a ≥3¢
rung mid-move; it **resolves** if another rung of the same ladder posts a
same-direction ≥2¢ move within 5s; otherwise it **CONFIRMS** as a
long-lag episode at exactly t0+5s, the earliest causally knowable
instant. A **congestion window** is the union of [confirm, confirm+30s).
The window opens at confirm, never at trigger — 5 seconds of every window
is structurally unquotable-around, a causality cost any consumer
inherits. Canonical input ordering (t, ladder, rung) per the c78432d tie
discipline; explicit datetime64[ns] normalization is load-bearing.

## (2) Constants provenance — adopted, never optimized

TRIGGER_MOVE 3¢, RESPONSE_MOVE 2¢, LONG_S 5s (the census episode
primitives, `analysis/cross_market_census.py` canonical at c78432d) and
WINDOW_S 30s (the clustering analysis's nearest-neighbour radius) — all
four ADOPTED from the in-sample WNBA census. The 55–70%-vs-7–12%
wall-clock clustering result is in-sample evidence for the mechanism and
is NOT part of this registration or any gate.

## (3) Mutation suite

`--selftest`, all passing at the pinned commit: **causal replay**
(shuffled input → identical windows; streaming and batch share one code
path); the **lookahead-must-fail proof** (a mutant opening windows at
trigger time DISAGREES — the suite provably detects causality
violations); **jitter null** (±1¢ flicker → zero windows); **planted
episode** asserting the EXACT boundary (confirm at t0+5s, span 30s).

Provenance, per rule 18 (this incident is its type specimen; cited, not
re-argued): the planted-boundary mutation caught a datetime64[us]
inference bug — a silent ~1000× duration rescale under which real-data
replay "passed" with a wrong window count — before first use.

## (4) Cutoff instant

**`1788366953`** — the committer epoch of the commit adding the file to
main, read by the pinned command and never from prose:

    git log origin/main --diff-filter=A --format=%ct -- analysis/congestion_detector.py

No prose rendering of the epoch appears in this document by design:
three authors produced three wrong renderings of this one epoch in one
night; anyone wanting ISO runs `date -u -r 1788366953`. (`%ct`, never
`%at`: a cherry-pick preserves the author instant, which predated this
object being citable on main.)

Windows computed over observations before the cutoff are calibration
history. **Any gate consuming this instrument accrues strictly after its
own registration's cutoff, which may not precede this one.**

## (5) No performance claims

Restated as the closing clause because the operator reads for hope: this
instrument detects; it does not promise.

**No in-sample result justifies capital. The forward test is the evidence.**

---

*Results append below this line, never above it.*
