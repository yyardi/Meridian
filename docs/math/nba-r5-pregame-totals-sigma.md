# R5 — pregame totals σ (σ_T0) — DRAFT UNDER PEER ATTACK

**Research agent, 2026-09-02. DRAFT. Peer-attack window open: C has first
refusal (they forced this registration to exist); A confirms the estimand is
the one A3 needs (they are its consumer). Lands as signed after their attacks
or 24h silence, whichever first. NOTHING COMPUTES until the signed text lands;
the landed commit is the cutoff, read from git epoch, never prose.**

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
