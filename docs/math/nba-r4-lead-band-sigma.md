# R4 — margin-conditional σ (the lead-band correction arm)

**Status: SIGNED OFF by the research agent 2026-09-02 — final, amendments
1–6 all applied below verbatim. NOTHING COMPUTES until this text lands on
main; the landed commit is the cutoff**, read with the git `%ct` convention,
never from prose. Drafted by Quant C; the sign-off travels with the research
agent's messages of record; selftest lineage ef0557a.

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

    z            = |m + E·t/48| / (σ_phase(t) · √t)
    σ_R4(t, ...) = σ_phase(t) · g(bucket(z))
    bucket(z)    : z ∈ [0, 0.5) · [0.5, 1.5) · [1.5, ∞)

z is computed from the anchored, UNSHRUNK expectation — pinned as the formula
states. The bucket edges 0.5 and 1.5 are fixed A PRIORI as round units on the
z scale, chosen without reference to the atlas's diagnostic cells; they are
not fitted, not tuned, and any future re-bucketing is a new registration.

with g a per-bucket multiplier fitted by walk-forward MLE on training seasons
only (σ_phase refit per fold exactly as adopted, then g on top with σ_phase
frozen — two-step, matching R1b's fitting discipline). Everything else in the
adopted stack — the anchor E = −closing_spread, the R2 shrink table, the
settlement frame — is untouched.

Why this form: the physical reading of the band gap is that **decided-ness
suppresses remaining variance** (clock burn, benches, possession play) beyond
what a margin-independent σ can express. Expressing it in a standardized z
(the anchored, unshrunk expectation over the phase-σ horizon), not raw |m| or
a time band, makes the claim self-consistent across the clock: the band is where mid-size leads produce mid-size z, so a z-effect
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
5. **Computing z from the shrink-adjusted expectation** — plausible, but it
   couples this arm to R2's table and creates two-z ambiguity; it is a
   different registration if anyone ever wants it.

## Arms and gate

Arms into the identical stack: (a) incumbent = adopted R1b σ + R2 shrink ·
(b) R4 = incumbent with σ_phase → σ_R4. Same states, same anchor, same
folds as R1b: eval **2017–2022 + 2025 (PARTIAL, train ≤ 2022)** = 7 forward
seasons, **floor ≥ 6**. Coverage, cited: closing spreads 2015–2022
contiguous + 2025 partial (979/1,235), hole 2023–24, per the season coverage
table (#140 lineage) — 7 evaluated forward seasons feasible, floor ≥ 6 met
by construction.

**O4 (firing rate): NOT APPLICABLE** — calibration arm, no entries, no
firing; stated so the checklist reads considered rather than skipped.

**Gate:** paired per-state Brier (R4 − incumbent), season-clustered
(`clustered_mean`, clusters = evaluation season). **PASS/adopt** = CI
excludes zero in R4's favour. **FAIL** = excludes zero against.

**POWER PROGNOSIS, from the mutation suite's test 3 at real-gate power
(ef0557a):** an injected effect STRONGER than the atlas tilt clears zero only
marginally (−0.000146 [−0.000245, −0.000047]). A σ-correction's Brier value
is second-order, so AT ATLAS-TRUE MAGNITUDE A STRADDLE IS A LIKELY OUTCOME
EVEN IF THE EFFECT IS ENTIRELY REAL. Consequently — the inverse of R1b's
separability note — the closure's NO-MARGINAL-VALUE verdict is UNINFORMATIVE
about the z-family theory and may never be quoted against it; it states only
that the correction is not worth adding at measurable Brier value. What
remains informative at this power: a PASS (effect stronger or better-shaped
than prognosis), a FAIL with CI against (the correction actively damages
bulk calibration), and the descriptive band-tilt diagnostic, which answers
"did the band signature shrink" regardless of the global gate.

Closure: at all 7 with the CI straddling → **NO-MARGINAL-VALUE**, g is not
added, the band gap stands as a documented model limitation with its theory
untested at achievable power, the gate closes.

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

**Caveats from the mutation suite, recorded here so nobody re-learns them:**
(i) The two-step fit lets σ_phase absorb clock-collinear z-effects; fitted g
is an EFFECTIVE parameter of the residual and UNDERSTATES the physical
effect — g's magnitude may not be quoted as the size of the decided-ness
physics. (ii) Fitting g on shuffled outcomes inflates it toward the wide
bound — the flatness artifact, instance recorded for the artifact-direction
pattern; the suite's diagnostic print is the guard.

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

## VERDICT — 2026-09-02, appended per the research agent's ruling

VERDICT: PASS — ADOPTED. Paired Brier (R4 − incumbent) −0.000548 [−0.000821,
−0.000275], 373,227 states / 7 forward seasons, R4 lower in all seven. Per
the pre-registered power frame this is the INFORMATIVE branch (~3.7× the
prognosis injection). THE ATTRIBUTION DIAGNOSTIC ANSWERS ITS PRE-NAMED
QUESTION DECISIVELY: band tilt +0.0271 [+0.0148,+0.0394] under the incumbent
stack; −0.0020 [−0.0145,+0.0104] under R4; −0.0277 [−0.0392,−0.0163] under
σ-only. **The lead-band tilt was a STACK-COMPOSITION ARTIFACT, not margin
physics**: R2 shrinks the mean while σ remained fitted to the unshrunk
curve, leaving stack variance too wide; fitted g is near-uniform (~0.83,
flat-to-reversed vs the z-gradient) and functions as the missing σ-refit,
which is why the gate passes while the z-gradient theory is UNCONFIRMED.
Amendment 6 governs: g may not be quoted as decided-ness physics, and the
fit shows it mostly is not. R2's adoption stands untouched (its gate
compared both arms under the same σ frame; its stated conservatism is what
R4 just priced). The atlas band GAP was real as measured; its NAME changes:
an artifact of our stack's composition, not a property of smooth families —
the corrected stack fits the band at −0.002.
