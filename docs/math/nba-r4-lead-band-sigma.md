# R4 — margin-conditional σ (the lead-band correction arm) — DRAFT for research sign-off

**Status: DRAFT by Quant C, 2026-09-02, for the research agent's sign-off.
NOTHING COMPUTES until this text lands on main, amended or not.** The
cutoff/cohort instant, once landed, is this document's first commit, read with
the git `%ct` convention, never from prose.

## What this is, and emphatically what it is not

The atlas measured (out-of-sample, walk-forward, season-clustered): the
adopted stack (R1b arm (a) σ + R2 shrink) **underrates leaders by +2 to +4
probability points in the 18–36-minutes-left band** (leads 4–19), with CIs
off zero, while being calibrated overall (REL 0.0004). This arm tests ONE
pinned functional correction to the model's own uncertainty.

**Boundary, from the disposition that ordered this arm (#172), carried
verbatim in every artifact:** this is calibration work on the model's
uncertainty engine. **It is not edge work, may never be described as edge
work, and says nothing about any market.** Whether the NBA *market* shares
the miscalibration is Track 2 (candidate 7a), graded by the day-one survey,
and the two tracks may not be collapsed.

## The pinned form — and why the form is pinned here

The band gap admits several corrective forms, and the form is a free
parameter of exactly the species the porting conventions kept pinning. This
registration fixes ONE:

**Primary form: a margin-conditional σ multiplier.**

    z            = |m + E·t/48| / (σ_phase(t) · √t)      # the incumbent's own z
    σ_R4(t, ...) = σ_phase(t) · g(bucket(z))
    bucket(z)    : z ∈ [0, 0.5) · [0.5, 1.5) · [1.5, ∞)

with g a per-bucket multiplier fitted by walk-forward MLE on training seasons
only (σ_phase refit per fold exactly as adopted, then g on top with σ_phase
frozen — two-step, matching R1b's fitting discipline). Everything else in the
adopted stack — the anchor E = −closing_spread, the R2 shrink table, the
settlement frame — is untouched.

Why this form: the physical reading of the band gap is that **decided-ness
suppresses remaining variance** (clock burn, benches, possession play) beyond
what a margin-independent σ can express. Expressing it in the incumbent's own
z, not raw |m| or a time band, makes the claim self-consistent across the
clock: the band is where mid-size leads produce mid-size z, so a z-effect
predicts the band signature — and predicts signatures OUTSIDE the diagnostic
band that the diagnosis never measured. That out-of-band behaviour is this
arm's **novel exposure**, stated per the round-3 tiebreaker's standard: if g
only helps inside the cells that motivated it, the gate will show it (the
gate scores ALL states).

**FORBIDDEN FORMS, listed so the harness can refuse them:**

1. **Any correction fitted on the diagnostic cell grid** (cell-indicator
   bumps, band-indicator terms, anything keyed to "18–36 minutes" or
   "lead 4–19" as literals). That is reverse-engineering the finding; it
   cannot generalize and its gate PASS would be unfalsifiable overfit.
2. **Output-side remapping** (isotonic/Platt/monotone recalibration of the
   emitted probability). Track C measured LOGO recalibration making the FV
   WORSE; the deficit species is functional form, not mapping.
3. **Touching the R2 shrink** (e.g., deviation-size-dependent β). Plausible
   physics, but it amends an ADOPTED table and is a different registration;
   the attribution diagnostic below exists to say whether anyone should
   write it. Not this arm.
4. **Touching the anchor, the outcome frame, or OT handling.**

## Arms and gate

Arms into the identical stack: (a) incumbent = adopted R1b σ + R2 shrink ·
(b) R4 = incumbent with σ_phase → σ_R4. Same states, same anchor, same
folds as R1b: eval **2017–2022 + 2025 (PARTIAL, train ≤ 2022)** = 7 forward
seasons, **floor ≥ 6** (R1b precedent).

**Gate:** paired per-state Brier (R4 − incumbent), season-clustered
(`clustered_mean`, clusters = evaluation season). **PASS/adopt** = CI
excludes zero in R4's favour. **FAIL** = excludes zero against. Closure: at
all 7 with the CI straddling → **NO-MARGINAL-VALUE**, g is not added, the
band gap stands as a documented model limitation, the gate closes.

**Pre-named readings, neither adoptable retroactively:**
- PASS = the decided-ness effect is real and z-expressible.
- Straddle/FAIL = the band gap is not a z-family effect, or fixing it in z
  breaks bulk calibration faster than it helps the band. **A FAIL here does
  not retract the atlas finding** — the gap is measured; this arm tests one
  functional theory of it.

**Reported beside the gate, descriptive, never gated:**
- The diagnostic-cell tilt under both arms (does the band signature shrink).
- **Attribution:** the tilt measured under σ-only (no shrink) vs the full
  stack — named now so "does R2's shrink contribute to the band gap" gets an
  answer nobody can be accused of fitting after the fact.
- Fitted g by fold, per-season fits with t-intervals — the physics table.

## Mutation, per the adopted clause (PR #132 form)

Before first read: (1) a generator with known margin-conditional σ (g_true
per bucket, exact by construction) — the fitter recovers g within tolerance;
(2) distorted g loses to fitted in BOTH directions, CIs excluding zero;
(3) generator-recovery both ways at real-cohort power (g_true ≠ 1 vs g = 1);
(4) a homoskedastic generator reads fitted g ≈ 1 AND the gate straddles;
(5) the shuffled-outcome null asserts the artifact direction (the
lower-variance arm is sharper where it differs; the sharper arm must never
win under shuffle).

## Standing terms

Physics only; constants never point-in-time claims. n in seasons; no CI
without season clustering. Composition before ratios. The loader is the
rule-13-audited post-OT-fix loader (commit 8639152 lineage) — OT games kept,
OT states excluded.

**No in-sample result justifies capital. The forward test is the evidence.**

---

*Results append below this line, never above it.*
