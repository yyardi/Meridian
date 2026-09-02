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

## APPEND A (2026-09-02, B + research — cadence compliance)

The detector's semantics require observation cadence ≪ LONG_S (rule of
thumb: ≤1s). Near 5s cadence the response test DEGENERATES: a sibling's
response is first observed at the next cycle, landing at or past the 5s
deadline by construction — every trigger confirms, and the instrument
measures the consumer's cadence, not the venue. Implicit in "self-clocked
pure function of the consumer's stream"; explicit here because it decided
a real question: v1 observed at ~5s and recorded no stream, so NO
COMPLIANT IN-SAMPLE FEED EXISTS — the program registration's amendment 9
impossibility, with its mechanism named. Any consumer's gate cites its
stream's cadence beside this line.

## APPEND B (2026-09-02, B + research — selectivity + pre-registered revision condition)

Coverage diagnostic on the non-compliant recorder tape (labelled proxy,
diagnostics-only): ~75% of game time / 90.6% of v1 fills marked
congested — near-saturation, not a lever. Beyond the clock, a structural
cause: the detector confirms every UNANSWERED trigger (quiet deep rungs
rarely answer), while the registered mechanism evidence was the CLUSTERING
of long lags.

PRE-REGISTERED REVISION CONDITION, written before any compliant data
exists: if on the v2 quoter's own compliant stream, over its first 10
games, congested share of game time exceeds 50% — the a-priori bar:
suppression is only a lever if a MAJORITY of time remains quotable — then
detector v2 registers with DENSITY GATING (the window opens on the SECOND
confirm within WINDOW_S, tying the object to its own clustering evidence),
constants carried, as a new pinned version landing BEFORE the CONGESTION
arm's gate cutoff; the arm cites exactly one registered detector version
for its entire cohort.

MEASUREMENT DEFINITION, pinned before any compliant data exists:
"congested share of game time" = the window-union coverage of IN-PLAY time
(first to last live observation of that game on the quoter's own stream),
computed PER GAME; the 50% bar reads on the MEDIAN across the first 10
compliant games. Median a-priori: one pathological game — an outage, an OT
circus — must not decide an instrument revision in either direction. Bar
and definition jointly authored: research (number and lever rationale), B
(definition and median), both blind to forward data.

Justification recorded now, ahead of any temptation: the diagnostic
numbers are coverage statistics — an instrument property; no P&L was
consulted; this is design-from-diagnostics, not optimization-on-outcomes.
A's forward schema records raw confirms beside windows so any v2 evaluates
on the same recorded stream without re-instrumentation.


## DATED LINE on append B (research agent, 2026-09-02 — landed before the first NFL datum)

Append B's "first 10 compliant games" means **10 WNBA games**. GRIDIRON's
NFL games arrive FIRST (Thursday 2026-09-04 vs WNBA's Sept 17), and the
saturation read must not run on a league whose detector constants are
WNBA-census-derived. GRIDIRON gets its OWN saturation read on NFL games,
with the cross-league constants provenance disclosed as a first guess —
registered in GRIDIRON's registry, not here.

## 2026-09-02 — NFL pre-data note (GRIDIRON; appended before first NFL data)

The detector was built and its constants adopted on WNBA structure.
Venue-measured NFL differences, written down while no data exists so the
first read cannot be interpreted conveniently:

* **Board scale**: WNBA ladders ran ~9 rungs, 2–4 concurrent games; the
  Kalshi-verified NFL structure implies Polymarket-scale boards of ~25
  spread + ~19 total rungs per game and up to ~13 concurrent games on a
  Sunday slate. Long-lag confirms come disproportionately from quiet deep
  rungs, and the NFL board has many more of them — **saturation risk is
  structurally HIGHER**, which is exactly what the 50%-coverage revision
  bar (median of the first 10 compliant games, board-agnostic by text)
  exists to read. No constant changes pre-data.
* **Scoring shape**: NFL scoring is bursty (0/3/7-point jumps, long quiet
  stretches) — triggers will be larger and more synchronized WITHIN a
  game than basketball's continuous flow. Between games, dynamics are
  independent.
* **The falsifiable pre-data prediction this enables**: on a multi-game
  NFL slate, game dynamics cannot produce CROSS-GAME clustering — so if
  long-lag episodes still cluster across games in wall-clock, the
  venue-congestion interpretation strengthens materially; if clustering
  measured cross-game-only vanishes, the WNBA clustering (55–70% vs
  7–12%) may have been game-local dynamics misread as venue congestion.
  The forward stream should be read BOTH ways (pooled, and
  cross-game-only), declared here before either number exists.
* **Pooling**: the registered definition pools venue-level. On a 13-game
  board a GAME-LOCAL window variant becomes plausible — if ever wanted,
  that is a NEW registered version per the one-version-per-arm-cohort
  rule, never a silent reinterpretation.

No in-sample result justifies capital. The forward test is the evidence.
