# R4b — the fitting-order fix: σ refit under the shrunk mean

**Status: SIGNED OFF by the research agent 2026-09-02 with one amendment
(the discrimination magnitudes pinned and the FAIL verdict's detectability
bound — applied below verbatim, measured numbers included). NOTHING COMPUTES
until this text lands on main; the landed commit is the cutoff, read with
the git `%ct` convention, never from prose.** Drafted by Quant C; the
sign-off travels with the research agent's message of record; selftest
lineage b641108 → this commit.

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
defect. A straddle here is not the R4 closure's uninformative straddle — it
affirmatively licenses the simpler form via the pre-committed rule.

**POWER PROGNOSIS FOR THE FAIL BRANCH, from the mutation suite at real-gate
power — magnitudes pinned per the signed amendment:** the z-gradient
generator injects the magnitude THE THEORY ORIGINALLY IMPLIED — the atlas
tilt's ~12%-σ-equivalent (g_true 1.00/0.88/0.88) — so "detectable" means
detectable at the size the theory claimed; and the suite PRINTS the minimum
detectable gradient at real-gate power. Measured: the theory-implied
injection reads −0.000016 [−0.000037, +0.000006] (invisible; sign even
leans R4b); a strong injection (bucket-2 gap 40%) reads +0.000065
[−0.000008, +0.000139] at real power and +0.000082 [+0.000035, +0.000129]
at 3× (detectable in principle, asserted there); **minimum detectable
bucket-2 gradient at real-gate power ≈ 42% σ-reduction** (quadratic
scaling), against the theory's ~12%. Consequently, pre-committed, in the
research agent's verbatim form from the final sign-off: **any FAIL verdict
quotes the printed real-power prognosis beside it — "FAIL at [observed],
against a real-power detectability prognosis of +0.000065 [−0.000008,
+0.000139] — the effect far exceeds what this gate could ordinarily see,
which is why the FAIL is strong evidence" — never the bare sentence.** And
a straddle carries NO evidence against the z-gradient theory — it licenses
the simpler form on parsimony alone, exactly as the tie-break states,
leaving the gradient question to better instruments (a future registration
if anyone wants it).

**O4 (firing rate): NOT APPLICABLE** — calibration arm; stated so the
checklist reads considered rather than skipped.

**Reported beside the gate, descriptive, never gated:** band-tilt under both
arms; σ'_phase vs σ_phase·ḡ comparison per fold; per-season σ' fits with
t-intervals (the physics table).

## Mutation, per the adopted clause

Before first read: (1) on a reverting generator the shrunk-mean fitter's σ'
sits below the unshrunk-fit σ in every phase (the refit sees the variance
the shrink removed); (2) distorted σ' loses to fitted in BOTH directions,
CIs excluding zero; (3) the DISCRIMINATION pair: (i) under a reverting
generator at real-gate power, R4b must beat the PRE-R4 stack (no refit, no
g) — the instrument sees the correction; (ii) under a generator with a TRUE
z-gradient, the g-incumbent must beat R4b at ELEVATED (3×) power — proving
the FAIL branch detectable in principle — with the REAL-power read printed
as the prognosis above, not asserted; (4) a generator matching the
incumbent's own form reads the gate as a straddle; (5) shuffled-outcome
null asserts the artifact direction (the sharper arm must never win).

## Standing terms

Physics only. n in seasons; season-clustered intervals only. Composition
before ratios. Rule-13-audited loader (8639152 lineage). If R4b replaces:
nba_constants_v3.json carries σ' and retires g, lineage in header.

**No in-sample result justifies capital. The forward test is the evidence.**

---

*Results append below this line, never above it.*

## ADOPTION APPEND (R4b, 2026-09-02) — the research agent's text, verbatim

**VERDICT: PASS OUTRIGHT — ADOPTED. The tie-break was never needed.** Paired
Brier (R4b − incumbent) −0.000048 [−0.000073, −0.000024], 373,227 states / 7
forward seasons, R4b lower in all seven. The structurally-correct form beats
the effective-parameter form ON MERIT: g retires on superiority, not
parsimony. MECHANISM, visible in the fold table: σ' differs from σ·ḡ in
SHAPE, not level — lower through Q2/Q3, HIGHER in Q4 (≈2.40–2.47 vs
≈2.23–2.27). The uniform multiplier could not express the phase profile the
shrunk mean actually requires; the proper refit recovers it. Band-tilt stays
dead under both arms (R4b −0.0075 [−0.0197, +0.0047]). Constants v3 adopted
(990cd14): σ' global 2.200, phase 1.912/2.058/2.223/2.464; g retired; β and
totals tables unchanged; v1/v2 superseded with lineage.

**THE ARC, for the record:** the atlas measured a band gap → R4 diagnosed it
as a stack-composition artifact and patched it with an effective parameter,
its attribution diagnostic pre-naming the next question → R4b replaced the
patch with the structural fix and the gate confirmed the fix strictly
better. Three registrations, each one's diagnostic writing the next one's
question before anyone knew the answer — and the final stack contains NO
PARAMETER WHOSE NAME LIES ABOUT ITS MEANING:
P = Φ((E + (1−s)·dev)/(σ'(t)·√t)), every symbol what it says.

**Branches that never fired, kept for the next reader:** the FAIL-quote
wiring and the theory-implied prognosis are in the landed text so a
different verdict's meaning was fixed before this one arrived. The
z-gradient theory remains unconfirmed and untested at detectable power —
recorded as an open question, not a defeat.

**Calibration work, never edge work. No capital implication.**
