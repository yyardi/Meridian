# R4b — the fitting-order fix: σ refit under the shrunk mean — DRAFT for research sign-off

**Status: DRAFT by Quant C, 2026-09-02, per the research agent's R4 ruling 1
("the cleaner form gets its own registration immediately"). NOTHING COMPUTES
until the signed text lands on main; the landed commit is the cutoff, read
with the git `%ct` convention, never from prose.**

## What this is

R4's verdict named the mechanism: the lead-band tilt was a stack-composition
artifact — R2's shrink contracts the mean while σ_phase stayed fitted to the
UNSHRUNK curve, leaving stack variance too wide; R4's g (near-uniform ≈0.83)
is functionally the missing σ-refit, adopted as an effective parameter. R4b
is the structurally-correct form of the same correction: **fit σ_phase under
the mean the stack actually uses.**

**Boundary, carried verbatim:** calibration work on the model's uncertainty
engine. Not edge work; says nothing about any market; Track 2 separate.

## The pinned form

Fitting order (this IS the estimand — the fix is the order):

    step 1: β fitted exactly as R2 registered (on deviations; never
            references σ). The R2 table's fit is untouched.
    step 2: σ'_phase by MLE with the mean FROZEN at the SHRUNK expectation:
            P = Φ( (E + (1−s(elapsed))·dev) / (σ'·√t) )
            global σ' first, then the four phase buckets (R1b's two-step
            discipline, phase buckets unchanged: (36,48] (24,36] (12,24] (0,12]).

**No g anywhere in R4b** — the claim under test is that the uniform-in-z
refit suffices. No new free parameters exist beyond the refit itself; the
phase buckets, anchor, shrink table, outcome frame, and OT handling are all
inherited unchanged (amendment-1 standard: nothing here is tunable).

**FORBIDDEN FORMS:** (1) any z- or margin-dependence (that is R4's g; if the
gradient carries information, this gate is DESIGNED to show it by R4b
losing); (2) refitting β jointly with σ' (couples the arms; β's registered
fit stands); (3) output-side remapping; (4) touching anchor/outcome/OT;
(5) phase-bucket changes.

## Arms and gate

(a) incumbent = the ADOPTED post-R4 stack: σ_phase (unshrunk-fit) + R2
shrink + R4 g. (b) R4b = σ'_phase (shrunk-fit) + R2 shrink, no g.

Folds and floor exactly R4's. Coverage, cited: closing spreads 2015–2022
contiguous + 2025 partial (979/1,235), hole 2023–24, per the season coverage
table (#140 lineage) — 7 evaluated forward seasons feasible, floor ≥ 6 met
by construction.

**Gate:** paired per-state Brier (R4b − incumbent), season-clustered.
**PASS** = CI excludes zero in R4b's favour → R4b REPLACES g (constants v3,
g retired). **FAIL** = CI excludes zero against → g carries information the
uniform refit does not; g stands, and the z-gradient theory gains its first
positive evidence — recorded as such, a finding R4 itself could not deliver.

**PRE-COMMITTED SIMPLICITY TIE-BREAK (the research agent's term, verbatim
in spirit):** at all 7 seasons with the CI straddling → **the
structurally-correct form REPLACES the effective-parameter form** — fewer
free parameters (4 vs 7), and its parameters mean what they say; a kludge
may hold the fort but does not get squatter's rights. Recorded as
replacement-by-tie-break, never as superiority.

**Power expectation, stated before the read:** both arms approximate the
same variance correction, so near-indistinguishability is the EXPECTED
outcome and the tie-break is expected to decide. That is by design, not a
defect: the informative branches are FAIL (the z-gradient is real) and a
PASS with margin (the effective form was also mis-shaped). A straddle here
is not the R4 closure's uninformative straddle — it affirmatively licenses
the simpler form via the pre-committed rule.

**O4 (firing rate): NOT APPLICABLE** — calibration arm; stated so the
checklist reads considered rather than skipped.

**Reported beside the gate, descriptive, never gated:** band-tilt under both
arms; σ'_phase vs σ_phase·ḡ comparison per fold; per-season σ' fits with
t-intervals (the physics table).

## Mutation, per the adopted clause

Before first read: (1) generator whose truth is the shrunk-mean form with
known σ' — the step-2 fitter recovers it within tolerance; (2) distorted σ'
loses to fitted in BOTH directions, CIs excluding zero; (3) the
DISCRIMINATION pair at real-gate power: (i) under a uniform
variance-reduction generator, R4b must beat the PRE-R4 stack (no refit, no
g) — the instrument sees the correction; (ii) under a generator with a TRUE
z-gradient, the g-incumbent must beat R4b — the instrument can detect when
g carries real information, which is exactly what the gate's FAIL branch
claims to measure; (4) a generator matching the incumbent's own form reads
the gate as a straddle; (5) shuffled-outcome null asserts the artifact
direction (the sharper arm must never win).

## Standing terms

Physics only. n in seasons; season-clustered intervals only. Composition
before ratios. Rule-13-audited loader (8639152 lineage). If R4b replaces:
nba_constants_v3.json carries σ' and retires g, lineage in header.

**No in-sample result justifies capital. The forward test is the evidence.**

---

*Results append below this line, never above it.*
