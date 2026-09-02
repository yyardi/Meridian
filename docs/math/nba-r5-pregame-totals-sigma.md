# R5 — pregame totals σ (σ_T0) — READ AND ADOPTED

**Research agent, 2026-09-02. REGISTERED, SIGNED (C, on the amended text),
READ same day: σ_T0 = 18.2735 points (SE 0.1449) — see the adoption append.
Original window terms preserved below for the record; the amendment trail
(1–7) and the signature paragraph are the registration's history.**

## Estimand

**σ_T0 := SD(final total INCLUDING overtime − closing total line), NBA.**

The t=0 boundary condition the totals stack has never stated: R3b's rates
describe within-game decay; the shares describe when deviation arrives;
**nothing in the R-series says how wide the pregame distribution is.**
Settlement on the venue includes OT, so **the estimand matches settlement, not
regulation** — C's OT-loader lesson written into the estimand instead of
waiting to become a defect.

## Substrate & coverage (rule 10)

The pinned NBA exports under the corrected OT loader (lineage d52fe89 →
constants 990cd14); closing totals from the sportsbook odds table. **CLAIM:**
totals closing lines exist 2017-18 onward — cited from R3b's landed per-season
coverage table, **not re-derived**. **DUTY** (the R3b inheritance lesson
applied to itself): the harness prints the per-season (season,
games-with-closing-total) table **BEFORE any fit**. A season is EVALUABLE at
≥900 lined games. If the print contradicts the claim, floors re-derive from
the print and the discrepancy is disclosed by name — **the claim is mine; the
print is the fact.**

## Floors (C4 — games, not rows)

**≥5 evaluable forward-eval seasons** (6 expected; first eval after two fit
seasons). Below 5 → **INFEASIBLE-AS-REGISTERED**: the registration closes and
re-registers. No silent floor-lowering.

## Protocol

Walk-forward by season, season-clustered. Two pre-named forms:

- **Arm T (points):** σ from the expanding window, in points.
- **Arm L (relative):** expanding-window coefficient of variation × the eval
  season's mean closing line — totals levels have moved across the pace era;
  if σ scales with level, the points form ports stale.

**Primary read:** one-season-ahead Gaussian log-score of (final − line) under
each arm, paired difference, season-clustered CI. **Decision rule, written
now:** L beats T outside CI → relative adopted; T beats L outside CI → points
adopted; **straddle → points on parsimony** (the level term is the extra
parameter; mirror of the R4b tie-break — which just taught us the tie-break
clause sometimes never fires; either way the loser is recorded). Adopted
constant = terminal expanding-window estimate in the winning form, with SE,
landed as an APPEND to nba_constants (new keys, lineage line). **Consumer:**
A3's ladder-shape audit — A3 merges into queue #2's totals half only after
this lands.

## Mutation suite (all pass before the real read)

1. **Shuffle-null:** permute finals across games within season → the
   form-selection instrument reads flat AND the recovered σ equals the
   unconditional within-season SD (prints both).
2. **Generator recovery at two levels:** synthetic finals ~ N(line, σ_inj),
   σ_inj ∈ {14, 22} — both recovered within printed CI. Two levels prove the
   needle moves.
3. **Artifact-direction-asserted:** OT inclusion must RAISE measured σ vs a
   regulation-only recompute — mechanical, direction known in advance; the
   harness prints the OT/regulation decomposition and ASSERTS the direction.
   Flat or inverted is an instrument flag, never a finding.

## Forbidden forms (so the harness can refuse them)

- Regulation-only σ ported to OT-inclusive settlement — a wrong reading of a
  right number; nothing downstream would disagree with it.
- Anchoring on the OPENING line or any model total: the anchor is the CLOSING
  line (C12 — condition on what the price conditions on).
- Any read of a season the fit contains; all reads one-season-ahead.
- Winsorizing or trimming high totals: garbage-time and OT inflation are part
  of the distribution the market prices.
- Rows-not-games floors.

## O4 line

Not a niche filter — **σ_T0 applies to every pregame totals quote: 100% of
listings at t=0.** Firing rate is total by construction.

## Novel exposure

Three numbers exist nowhere in our record: **the pregame totals dispersion
itself, the OT share of totals variance, and the points-vs-relative form
outcome.** The registration predicts unmeasured things; it cannot merely
re-confirm.

## Closure

**Single-shot on the pinned substrate; no accrual clock.** Due when the
mutation suite passes; INFEASIBLE-AS-REGISTERED is the only non-reading exit.
The honest shape: existence of an SD cannot FAIL — **the registered risk is
FORM mis-selection**, and the decision rule is the entire discipline. Both
branches yield an adoptable constant; they differ in what ports.

## Capital

Calibration work, never edge work. **No in-sample result justifies capital;
the forward test is the evidence.** No branch of this registration has a
capital implication.

---

## DATED AMENDMENTS 1–3 (research agent, 2026-09-02, consumer confirmation — A credited)

**Amendment 1 — Arm L is redefined PER-GAME.** As drafted, Arm L scaled by the
eval season's MEAN closing line — a season-level effective parameter that could
only capture cross-season drift. The level-dependence thesis is a **PER-GAME
claim**: a 210-line game and a 225-line game must carry different σ. Corrected
form: **CV fit on the expanding window as SD((final − line)/line); Arm L scores
each eval game under N(0, (CV·line_i)²) with the game's OWN line.** The
season-mean version was the effective-parameter smudge R4→R4b taught us to
refuse — structurally-correct forms only, this time BEFORE fitting.

**Amendment 2 — the adopted constant matches the winning form's units:** points
if T wins; **the DIMENSIONLESS CV coefficient itself if L wins** — never a
season-mean-scaled points number. A3 needs per-game σ = CV × that game's line,
and dimensionless is what ports.

**Amendment 3 — shuffle-null sharpened:** permuting finals across games
destroys the line–final pairing, so under shuffle **Arm L must NOT beat Arm
T** — level-dependence must die with the pairing. Asserted explicitly.

**Confirmed unchanged, on the record:** the no-winsorizing forbidden form is
**load-bearing, not hygiene** — A3 measures residual skew/kurtosis of
(final − line) from the same untrimmed substrate to distinguish *"venue's σ
wrong"* from *"no single Gaussian σ can be right."* **Any future hand that
trims the tails breaks a consumer it can't see.** Consumer confirmation
complete; C's first-refusal window continues on this amended text.

---

## DATED AMENDMENTS 4–7 (research agent, 2026-09-02, C's attack window — all four attacks accepted)

**Amendment 4 — floor arithmetic corrected; the drafted floor was zero-margin.**
Coverage per R3b's table is SEVEN seasons (2017–22 + 2025; the 2023–24 hole).
Under the drafted two-fit-season rule that yields FIVE evals — and a floor of
≥5 of 5 is the zero-margin species R3b's pre-check corrected. Fix adopted:
**first eval after ONE fit season** — evals 2018–22 + 2025, six in all; floor
≥5 of 6, margin one. Rationale, in the text because it licenses the change:
this estimand is a plain SD (a scaled-residual SD for Arm L) — one season of
~1,200 games fits it with tight SE, unlike the multi-season regression curves
R2/R4 needed; the walk-forward exists to test drift, not fit noise. Disclosure
(research agent, verbatim): "my '6 expected per R3b's table' was an
inheritance mis-derivation — my second on totals coverage — the print-before-
fit duty would have caught it at runtime; C's window caught it before a
harness had to be built to fail." The sentence stays in, because the amendment
record is where the pattern becomes visible.

**Amendment 5 — the Gaussian reading pinned, OT robustness printed.**
(a) Verdict language: the winning arm is adopted as the better GAUSSIAN
APPROXIMATION for the stack — no distributional-truth claim; A3's
skew/kurtosis analysis retains authority over whether any single Gaussian is
right. (b) Descriptive print, never gated: the paired T-vs-L difference with
and without OT games — the atlas's ~5% right-tail mass at +24 points is
exactly where log-scores under misspecification take leverage. If the form
choice flips on the OT split, the adoption append says so and the constant
carries the sensitivity disclosure.

**Amendment 6 — an L-win must name its mechanism.** The per-game Arm L
(amendment 1) now differs from T in BOTH within-season level scaling AND
cross-season drift adaptation; a T-win is clean, an L-win is ambiguous between
them. Decomposition print, never gated, split pinned now: paired T-vs-L diff
on games in the inner two quartiles of |line − season median| vs the outer
two. If L's advantage concentrates in the outer/cross-season part, the
adoption append names cross-season adaptation as the operative mechanism and
FLAGS TO A3 that the per-game inheritance (σ_i = CV·line_i) is weaker than
the headline — the R4 attribution lesson applied before the port instead of
after.

**Amendment 7 — the ≥900 evaluability bar's provenance declared:** chosen a
priori as a round ≈73% of the 1,230-game season, blind to the per-season
counts; changing it is a new registration, not an amendment.

**Window closure:** C's four attacks of 2026-09-02 are all accepted and landed
above; C signs on this landed text. A's consumer confirmation is unaffected
(none of 4–7 touch the estimand or units). With C's signature, R5 is through
both gates — consumer (1–3) and attack (4–7); the mutation suite runs next,
then the read.

**SIGNED — C, 2026-09-02, on the landed amended text (message of record to
the manager: "R5: SIGNED on the landed text — through both gates, suite and
read next"). This paragraph is the manager's durable record of that
signature; the registration cutoff for computation is the commit carrying
it, read from git epoch.**

---

## ADOPTION APPEND (research agent, 2026-09-02 — landed by the manager after
reproducing the full printed run from the committed harness, not the relay)

READ 2026-09-02, single-shot on the pin; suite passed in the same invocation
(shuffle-null: L strictly worse once the pairing is destroyed, −0.0034;
generator recovery at 14/22 both within 3·SE; OT direction asserted).
**VERDICT: STRADDLE → POINTS ON PARSIMONY. ADOPTED: σ_T0 = 18.2735 points
(SE 0.1449, n=7,952 games, terminal expanding window over 2017–2022 +
2025-partial).** Primary L−T = +0.000601 [−0.001418, +0.002621], 6 evals,
floor 5 met with margin. Tie-break loser recorded: per-game relative form,
terminal cv 0.0824, drifting down 0.0849→0.0824 across seasons.

AMENDMENT-5b DISCLOSURE: the form DECISION is invariant to the OT split but
its ROUTE flips — excluding OT games T wins OUTRIGHT (−0.002564 [−0.004892,
−0.000236]); including them, straddle. OT tail games are the only thing
keeping the relative form in the race — the pre-registered leverage warning
confirmed in the benign direction. The winner is the better Gaussian
approximation only; A3's shape authority stands.

AMENDMENT-6 print: no mechanism concentration (inner +0.000452, outer
+0.000595, both straddle) — moot, L lost.

NOVEL EXPOSURE DELIVERED: OT share of pregame totals variance = 9.75%
(18.27 OT-inclusive vs 17.36 regulation-only, 421 OT games) — a number that
existed nowhere in our record this morning. 2025-partial (979/1,235) and the
2023–24 gap-jump fold disclosed as amended. Calibration work, never edge
work; no capital implication.

Constant appended to `analysis/nba_constants_v3.json` (block `r5_sigma_t0`);
harness `analysis/nba_r5_sigma.py` committed alongside; manager reproduced
every number above from a fresh invocation before landing (suite 3/3 then
read, byte-for-byte on the adopted constant, primary CI, both descriptive
prints, and the cv drift endpoints).
