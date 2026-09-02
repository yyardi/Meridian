# NBA constants — three registrations

**Written by the research agent 2026-09-01, before anything fits. Landed
unmodified.** Three gates on one page; the terms are per-gate. Quant C
executes, the research agent reviews. The cohort/cutoff instant for each gate is
this document's own first commit, read with
`TZ=UTC git log --format=%ct origin/main -- docs/math/nba-constants-registrations.md | tail -1`
and converted from epoch — never from prose.

## Common frame — stated once, applies to all three

**Data.** The NBA physics backfill: **13,143 games / 6,149,099 plays, seasons
2015-16 → 2025-26**, in `meridian_research`.

**PHYSICS-ONLY.** Fitted constant tables, never point-in-time claims. **The
boundary travels with every constant** derived here.

**Design.** Walk-forward by season: fit on seasons ≤ k, evaluate on season k+1,
rolling. **Only out-of-sample seasons score.** Intervals cluster **BY SEASON** —
the honest unit for constants, because regimes shift by season (the ladder-sigma
lesson).

**NBA is a new hypothesis family.** No arm, tie-break, or adoption may ever cite
WNBA performance as evidence. Nothing ports on reputation.

**Mutation per harness, before its first read:** a shuffled-outcome null shows
no arm dominating, and a deliberately distorted constant table must lose.

**Each formula is pinned in a COMMITTED harness file before its first read** —
in git with its own timestamp, not in the author's head. Standing term.

---

## R1 — NBA win-curve sigma

**Estimand.** σ per √minute for `P(win | margin, minutes_left)`, global plus
per-phase implied values. 48-minute regulation; **OT excluded** — there is no
registered OT model.

**Arms** — three constant tables into the *identical* anchored win curve:
(a) NBA-fitted walk-forward · (b) WNBA-ported 2.628 with its phase decay ·
(c) the 2.0 rule of thumb.

**Gate.** Paired Brier across arms on out-of-sample seasons' win predictions,
anchored on de-vigged closing moneyline, season-clustered 95% CI.
**PASS/adopt** = an arm dominates both others with CIs excluding zero.
**Floors:** ≥ 8 evaluated forward seasons.

**Closure.** At all 10 forward seasons with no dominant arm →
**INDISTINGUISHABLE-AT-POWER**, and the **pre-committed** tie-break adopts (a),
the league-matched estimand. **Recorded as adoption-by-tie-break, never as
superiority.**

---

## R2 — NBA reversion-shrink curve

**Estimand.** `shrink(t)` at play resolution, **12 gridpoints** (every 4 minutes
of 48), fitted walk-forward. The physics table β(t) with season-clustered CIs
**reports regardless of gate outcome**.

**Gate.** Does applying the fitted shrink to the anchored FV improve
out-of-sample paired Brier versus the identical FV without it, by season,
season-clustered CI. **Floors:** ≥ 8 forward seasons. **PASS** = CI excludes
zero in the shrink's favour; **FAIL** = excludes zero against.

**Named in advance, ported verbatim from the WNBA pre-gate note (#108):** the
anchor's own drift term already encodes a pull toward pregame expectation, so a
**≈0 result reads as REDUNDANCY OF FORM** — a finding about the FV's arithmetic,
not the absence of the physics. **Both readings are named now; neither is
adoptable retroactively.**

**Closure.** At 10 forward seasons with the CI straddling zero →
**NO-MARGINAL-VALUE**: the term is not added, the physics table stands as
reference, **the gate closes**.

---

## R3 — NBA totals coefficients

**Estimand.** Per-quarter banking coefficients (the Q1-1.32 analog, all three
boundaries) plus phase-resolved totals residual σ.

**Arms.** (a) NBA-fitted walk-forward table · (b) WNBA-ported table ·
(c) naive extrapolation (raw pace projected).

**Gate.** Out-of-sample paired Brier of end-of-quarter total-versus-closing-line
predictions across arms, season-clustered. **PASS/adopt** = dominant arm, CIs
excluding zero. **Floors:** ≥ 8 forward seasons. **Arm (c) is expected to lose
badly and exists as the interpretability floor — never adoptable.**

**Closure.** As R1: indistinguishable at 10 seasons adopts (a) by the
pre-committed league-matched tie-break, recorded as such.

---

**No in-sample result justifies capital. The forward test is the evidence.**

*Results append below this line, never above it.*

## 2026-09-01 — R1 arm (b): the porting convention, fixed before any fit

**A free parameter R1 left open, fixed BEFORE the first read and before any arm
has computed** — the same discipline #20 applied to its foul taxonomy. This
specifies how arm (b) is *constructed*; it changes no gate, floor, or verdict
rule. Written by the research agent, landed verbatim.

> Arm (b) ports the WNBA sigma **AS A RATE, not as a number-in-disguise**:
> **2.628 points per √minute enters the NBA curve unchanged**, because the curve
> consumes `sigma·sqrt(minutes_left)` and the rate is frame-independent — the
> implied full-game margin SD then differs *by construction*
> (2.628·√40 = 16.6 WNBA, 2.628·√48 = 18.2 NBA), **and that difference IS the
> ported hypothesis, not a bug**. The phase-decay multipliers
> (2.98 / 2.77 / 2.40 at end-Q1 / half / end-Q3) port keyed **BY QUARTER
> INDEX** — both leagues play four quarters, so quarter boundaries correspond
> structurally — with `minutes_left` always computed in the NBA's own 12-minute
> clock.
>
> **FORBIDDEN forms of the port, listed so the harness can refuse them:**
> porting the full-game SD 16.6 as if it were the NBA's; porting phase
> multipliers keyed by absolute minutes elapsed (10 / 20 / 30) rather than
> quarter boundaries; any rescale of the 2.628 rate itself.
>
> **If arm (b) loses under this convention, it lost on physics; there is no
> units reading left available.**

**Why this was worth fixing in advance.** Arm (b) exists so the incumbent
constants can *win*. A port that silently mis-scaled would have made (b) lose
for a units reason while the verdict read *"WNBA constants don't transfer"* —
a false finding, unfalsifiable after the fact, and pointing at the wrong
conclusion. The forbidden list is what makes the harness able to refuse the
error rather than the reader having to catch it.

---

## 2026-09-02 — R1 and R3 close as INFEASIBLE-AS-REGISTERED; R1b and R3b supersede

**R1 and R3 could never have passed.** Both anchored on data that does not exist
for enough seasons. Their text above is **untouched**; these supersede them and
are filed beside them.

**The feasibility artifact — odds coverage by season, measured before any fit:**

| season | games | spread | moneyline | total |
|---|---|---|---|---|
| 2015 | 1231 | 1230 | 0 | 0 |
| 2016 | 1231 | 1230 | 24 | 24 |
| 2017 | 1232 | 1230 | 1230 | 1230 |
| 2018 | 1232 | 1230 | 1230 | 1230 |
| 2019 | 973 | 971 | 971 | 971 |
| 2020 | 1081 | 1080 | 1080 | 1080 |
| 2021 | 1231 | 1231 | 1231 | 1231 |
| 2022 | 1231 | 1231 | 1231 | 1231 |
| **2023** | 1232 | **0** | **0** | **0** |
| **2024** | 1234 | **0** | **0** | **0** |
| 2025 | 1235 | 979 | 974 | 979 |

The moneyline anchor exists in 7 seasons with a two-season hole; walk-forward
over a broken chain yields at most ~6 evaluated seasons against a floor of ≥8.
**2023–24 carry the `odds` key with empty arrays** — the absence was verified,
not inferred.

### R1b — supersedes R1

Identical to R1 **except the anchor: de-vigged expected margin from the closing
SPREAD.**

**This is a better design, not merely a coverage fix.** R1's moneyline
construction used a σ-dependent inversion to build the anchor that then
evaluates σ — mildly circular. **The closing spread gives expected margin
directly and severs that loop.** The coverage hole forced the cleaner estimand.

**Walk-forward.** First fit trains on 2015–16; evaluated seasons **2017–2022
contiguous (6)**, plus **2025 as a PARTIAL-COVERAGE season, labelled**,
evaluated with train ≤ 2022. The hole means no 2023/24 evaluations — not a
broken claim.

**Floors: ≥ 6 evaluated seasons scoring.** Gate unchanged: three arms, paired
Brier, season-clustered, dominance to adopt.

**Closure.** At all 7 available evaluated seasons with no dominant arm →
**INDISTINGUISHABLE-AT-POWER**, adopt (a) by the pre-committed league-matched
tie-break, recorded as such.

**Disclosure, stated because it is the point:** *this floor was chosen WITH the
coverage table in view.* That is clean **only** because nothing has computed and
the choice is disclosed inside the registration. The alternative was a gate that
cannot pass.

**Estimands fixed here:** E comes from the closing spread, with the sign
convention **verified empirically per league before first use**. The moneyline
inversion survives as a **labelled sensitivity on ML-covered seasons only, never
gating**. **OT states are excluded; OT games are kept** — regulation-state
predictions score against the eventual final winner, so a regulation tie at 0:00
predicting ≈0.5 against an OT-decided outcome is legitimate and informative.

The σ-port convention (PR #130) carries to R1b arm (b) unchanged.

### R3b — supersedes R3

Identical re-anchoring, coverage citation, floors, closure and disclosure as
R1b. Arms unchanged. The closing-total anchor is replaced by the spread-era
totals lines where present (2015–2022, 2025 partial — same table column).

### RESOLVED 2026-09-02 — the mutation clause, replaced

**The clause inherited from R1/R3 was unsatisfiable and is superseded.** Quant C
demonstrated it before reading any real data; the research agent ruled and
adopted C's replacement verbatim.

**Why the original could not hold.** *"A shuffled-outcome null shows no arm
dominating"* cannot be true under Brier for arms of unequal sharpness:
destroying the signal **mechanically rewards the flattest σ table**, so under a
genuine null the widest arm wins every time. Dominance is **manufactured by
flatness**, not evidence that the harness lied. That makes the original a check
that cannot pass — the documented species, **appearing inside a mutation test,
which is where it hides best because nobody mutation-tests the mutation test.**

**The adopted clause — three parts, each of which CAN fail:**

1. **Distorted tables lose to truth in BOTH directions** (wider and narrower),
   CIs excluding zero. Gives direction sensitivity.
2. **Generator-recovery, both ways:** data generated under table X awards the win
   to X over a rival, run in both directions at real-cohort power. This is the
   correct null/alternative pair for comparing calibration tables.
3. **The literal shuffled null is RETAINED, asserting the known artifact
   direction** — under shuffle, the sharper table must **never** win.

Part 3 is the move worth keeping as a pattern: **do not delete a broken check —
invert it into an assertion of the artifact it exposes.** The broken symmetry
assumption becomes a determinate check of the harness itself.

**Required in the verdict text.** C's generator-recovery at real-cohort power
(arms separable under truth, CIs excluding zero both ways at 6 seasons ×
~1,200 games) **prints beside any INDISTINGUISHABLE verdict as its power
note** — *"this result is a statement about basketball, not about our power, per
the pre-computed separability of [date/commit]."* #20 had to reconstruct its
power note after the fact; **R1b's is pre-computed and reaches the reader in the
same breath as the verdict.**

The same pattern applies to R2's harness wherever its arms differ in sharpness.

**C reads real data once this lands.**

---

## R1b — ADOPTION APPEND, 2026-09-02

**VERDICT: PASS — ADOPTED.** Arm (a), the NBA-fitted walk-forward σ table,
dominates both rivals on the registered terms: paired Brier vs (b) WNBA-port
**−0.00062 [−0.00080, −0.00045]**, vs (c) flat-2.0 **−0.00108 [−0.00140,
−0.00076]**, season-clustered, **7 evaluated seasons against a floor of 6** —
and posts the lowest Brier in **every season individually**, so the pooled
effect is not one good year. Harness pinned at `478d48b` before the gate ran;
selftest passing under the amended mutation clause; **the pre-computed
separability note applies** — at this power the arms are provably
distinguishable under truth, so this dominance is a statement about basketball.

**The structural finding, which outlives the gate:** **NBA σ RISES through the
game** (Q1 ≈ 2.11–2.25 → Q4 ≈ 2.41–2.47 across folds) where **WNBA σ FALLS**
(2.98 → 2.77 → 2.40). The ported table was not merely mis-levelled — **its phase
decay has the WRONG SIGN OF SLOPE for this league.** This is the
arms-not-defaults design paying its bill: carried as a baseline, the inverted
shape would have been inherited by every downstream number. Global σ drifts
**2.30 → 2.45** across training windows — the scoring environment moves, which
is why **the ADOPTED FORM IS THE WALK-FORWARD REFIT, not any frozen table.**

**Effect size, stated so it cannot be over-read: 0.4–0.7% relative Brier. Real,
small, physics not alpha.** This PASS improves the model's uncertainty engine;
**it does not indicate an edge, and no capital implication exists.** The forward
test of any strategy built on it is separate evidence, per the standard.

### Ruling — the ML-inversion sensitivity

**PROCEED.** It was registered inside R1b as a never-gating labelled
sensitivity, so running it after the primary read is **per the registration, not
a post-hoc addition**. The flag-rather-than-slip instinct was the correct
reflex, and the ordering is disclosed regardless: it lands as its own commit,
with results under a **SENSITIVITY** heading carrying the line *"executed after
the primary read, per its registered never-gating status; ordering disclosed,"*
touching nothing in the gate arithmetic.

---

## R2 — AMENDMENT, 2026-09-02, before any read

**Nothing has computed.** The amendment is clean for that reason and would not
be after a read.

### The error being corrected

R2 was ruled *"unaffected, run now on all 11 seasons"* and briefed onward as
*"needs no anchor / no market data."* **All of that is false.** R2's estimand
names its anchor in its second symbol:

```
dev = margin − E·(elapsed/48),   E from the closing spread
```

This is the WNBA #89 / #89-fg form exactly (*"closing-spread anchor, play-level
margins"*), and an anchor-free variant is refused on precedent: **#16/#17
established that team-blind anchors invert reversion results.**

### Coverage, cited per rule 10

Spread coverage is contiguous **2015–2022 plus partial 2025 — 9 seasons**.
Walk-forward evaluations: **2016–2022 plus 2025 (PARTIAL) = 8 available forward
seasons.**

### 1. Anchor — confirmed

**R2 is spread-anchored**, in the #89 form.

### 2. Closure clause — amended to a reachable state

The registered clause said *"at 10 forward seasons"*. **Only 8 exist. That state
cannot occur** — the gate-that-cannot-close species, inside the clause written
against it, caught pre-read. Superseded text left untouched above.

> **At all 8 available forward seasons with the CI straddling zero →
> NO-MARGINAL-VALUE: the term is not added, the physics table stands as
> reference, the gate closes.**

### 3. Floor — moves to ≥ 7 of the 8 available

**Chosen with the coverage table in view, disclosed as such.** A zero-margin
floor converts **any single-season data defect into a mid-run NO DATA**;
R1b's shape (floor 6 of 7 available, margin 1) is the precedent. **One season of
margin is protection against defects, not against results** — the floor still
cannot be met by fewer than 7 honest seasons.

### 4. Pins — approved as proposed

12 gridpoints at elapsed 4…48 with **β(48) = 0 forced** (11 fitted, matching
#89's endpoint convention); `expected_final = E + (1 − s(elapsed))·dev`;
no-intercept regression of `(dev_final − dev_t)` on `dev_t` as primary, with an
intercept variant as robustness; per-season β fits with t-intervals across
seasons; **σ from R1b's ADOPTED arm (a), refit per fold** — the adopted form
used exactly as adopted.

**Both pre-named readings stand unchanged:** a ≈0 result is **redundancy of
form**, a finding about the FV's arithmetic, not the absence of the physics.
Neither reading is adoptable retroactively.

---

## R1b — sensitivity note

**Sensitivity (PR #136, never-gating, executed post-read as registered):** under
the circular ML-inversion construction the arm ordering scrambles — each table's
σ enters its own anchor, partially immunising it against its own mis-level, and
the comparison degrades to self-consistency, where flatness wins for the
shuffled-null reason. **The spread re-anchoring was adopted on coverage grounds;
this is its empirical vindication: the severed loop was load-bearing.**

---

## R2 — ADOPTION APPEND, 2026-09-02

**VERDICT: PASS — ADOPTED.** Paired Brier (shrunk − plain) **−0.001609
[−0.002195, −0.001023]**, 413,553 states / **8 forward seasons** against a floor
of ≥7, the shrink winning **ALL EIGHT seasons individually** (narrowest
COVID-2020 −0.00016, largest 2017 −0.00260), ~2.6× the R1b (a)−(b) gap.
**Adopted form: the walk-forward per-fold pair — R1b's σ and this shrink table,
refit together each season, never frozen.**

**The pre-named reading REFUSED BY DATA.** #108's redundancy-of-form did not
occur: the anchored FV's arithmetic does **not** already capture in-game
reversion, and the explicit term adds material calibration in every season.

**Two readings remain for the WNBA's ≈0 and this append CLAIMS NEITHER:**
(i) 18 games could not have seen an effect of this size in either direction —
the WNBA read was **power-limited, not informative of redundancy**; or (ii) the
leagues genuinely differ. **The NBA answer is measured regardless; the WNBA
question stays open at its own gate and inherits nothing from this one.**

**A pre-named reading being refused is what the note existed for.** A ≈0 here
would have adopted redundancy invisibly; instead the non-occurrence is loud.

**The physics table, standing regardless of the gate:** β monotone **0.430 at 4′
→ 0.086 at 44′**, every gridpoint's CI excluding zero; intercept and
no-intercept variants agree **to the fourth decimal at every point** — the
spread anchor is unbiased in this frame. The NBA reverts **more** than the WNBA
early (0.430 vs 0.355) with the same qualitative decay.

**Stated conservatism:** σ is refit per fold on the **PLAIN** curve per the
approved pin, so the shrunk arm carries a σ fitted to the unshrunk mean and
**slightly under-sizes its own confidence — the PASS is if anything
understated.** The σ-refit-under-shrink variant was **NOT run because it would
be post-hoc**; if anyone wants the sharper number, it gets its own registration.

**Effect size, so it cannot be over-read: ~0.16% relative Brier. Physics, not
alpha. No capital implication; adopted into the model's uncertainty engine,
nothing more.**

---

## R3b — PRE-CHECK AND AMENDMENT, filed before C builds

**Per rule 10, feasibility is established before the harness exists.**

**Totals coverage = 2015–2022 + 2025 partial — the same 8-available shape as
R2** (see the coverage table above; totals column).

- **Floor: ≥ 7 of the 8 available evaluated seasons.**
- **Closure: at all 8 with no dominant arm → the registered tie-break** (adopt
  (a), the league-matched estimand, recorded as adoption-by-tie-break, never as
  superiority).
- **Coverage cited inside this amendment; chosen-with-coverage-in-view
  disclosed.**
- **R1's original 10-season closure language is superseded wherever R3b
  inherited it.**

C builds the totals loader and selftests; **reads nothing until this lands** —
the same sequence that has now worked three times.

### R3b PRE-CHECK — CORRECTED, 2026-09-02, still before any read

**The pre-check filed minutes ago is wrong and its floor was unreachable.** It
asserted *"totals coverage = 2015–2022 + 2025p, the same 8-available shape as
R2"* and set a floor of ≥7. **Totals coverage is NOT the same as spread
coverage**, and the coverage table already on this page said so — column
`totals`, not column `spread`.

**Measured, both columns side by side:**

| season | totals | spread |
|---|---|---|
| 2015 | **0** | 1230 |
| 2016 | **24** | 1230 |
| 2017 | 1230 | 1230 |
| 2018 | 1230 | 1230 |
| 2019 | 971 | 971 |
| 2020 | 1080 | 1080 |
| 2021 | 1231 | 1231 |
| 2022 | 1231 | 1231 |
| 2023 | 0 | 0 |
| 2024 | 0 | 0 |
| 2025 | 979 | 979 |

**Totals begin in 2017, not 2015** (2016's 24 games are unusable). Usable
totals seasons: **2017–2022 + 2025 = 7**. Walk-forward evaluations:
**2018–2022 + 2025 (PARTIAL) = 6 available forward seasons.**

**So the corrected pre-check's own floor of ≥7 exceeded the 6 seasons that
exist — a gate that cannot pass, written inside the amendment created to
prevent gates that cannot pass.** Third instance of the species today, and the
first one to appear in its own countermeasure.

**How it happened, since the mechanism is the useful part:** *"the same shape as
R2"* is an inheritance claim, and inheritance claims are exemptions wearing
different clothes — rule 10's corollary applies exactly. **The disproof was
already printed on this page, one column to the left of the one being read.**

**CORRECTED TERMS, pending the research agent's ruling — nothing computes
against this section until they rule:**

- Available forward evaluations: **6** (2018–2022 + 2025 PARTIAL).
- **Proposed floor: ≥5 of the 6 available** — one season of margin, on the
  R1b (6 of 7) and R2 (7 of 8) precedent: *margin protects against defects, not
  against results.*
- **Closure: at all 6 available with no dominant arm → the registered
  tie-break**, adopt (a) as adoption-by-tie-break, never as superiority.
- Coverage cited above; chosen-with-coverage-in-view disclosed.

### R3b — RULINGS, 2026-09-02, before any read

**1. Corrected terms APPROVED.** 6 available forward evaluations, **floor ≥5**,
closure at all 6 with no dominant arm → the registered tie-break, coverage cited
above, chosen-with-coverage-in-view disclosed. Precedent-consistent with R1b
(6 of 7) and R2 (7 of 8).

**2. The σ-port fork — ruled for (i) RATE-KEYED.** Verbatim for the harness
file:

> Arm (b) ports the WNBA totals σ as **PER-BOUNDARY RATES keyed by quarter
> index** (2.899 / 2.914 / 3.059 per √minute at end-Q1 / half / end-Q3),
> entering `σ_NBA = rate·√(NBA minutes_left)` → **17.4 / 14.3 / 10.6**.
>
> **THE INVARIANT PORTED IS THE MATCHED-BOUNDARY RATE, NOT A WITHIN-GAME √t
> LAW.** The WNBA page's demonstration that √t fails *within* a game (the rate
> rises as the clock runs out) is fully compatible with √minutes scaling
> *across leagues at matched boundaries*, because remaining variance scales with
> remaining scoring opportunity — ~linearly in remaining minutes, hence
> √minutes in SD.
>
> Option (ii) — porting the absolute triple 15.88 / 13.03 / 9.67 unchanged —
> asserts that residual variance is **invariant to 20% more remaining clock**, a
> physics claim nobody holds. **It is NOT ported as arm (b).** It runs instead
> as a **LABELLED NEVER-GATING SENSITIVITY (b′)**, reported beside the verdict,
> so that if absolute-invariance is somehow true it shows up honestly without
> gating anything.
>
> **Forbidden form:** any port mixing the two — rates at some boundaries,
> absolutes at others.

**3. Pins 2–5 APPROVED as proposed, with reasons on record.** Dimensionless
pieces (banking 1.318 / 1.208 / 1.128, cumulative shares) port unchanged by
quarter index — **dimensionless is the invariance class**. Arm (c) receives arm
(a)'s fitted σ, so it loses on **projection naivety, never on an arbitrary σ**.
Outcome `y = (final > closing_total)`, **OT-INCLUSIVE — the settlement frame the
market actually pays** — with the **78 pushes EXCLUDED AND COUNTED** in the
printout (36% integer lines makes push handling load-bearing, not a nuisance).
Arm (a) fits b and σ on OT-inclusive finals with **cumulative shares fitted on
NON-OT games only**: OT mechanically shrinks share denominators, and the
**+22.3-point OT settlement fact** is exactly why the outcome frame keeps OT
while the share fit excludes it. **Print the OT count beside the pushes.**

**4. The loader change APPROVED — and the flagging is the practice.** Additive,
gate-neutral changes get **announced, never discovered**. R1's arithmetic
ignoring the new column is verifiable by diff.

**C reads nothing until this text is on main.**

---

## R3b — ADOPTION APPEND, 2026-09-02

**VERDICT: PASS — ADOPTED.** Arm (a) dominates on the registered terms:
vs (b) **−0.00030 [−0.00050, −0.00011]** with (a) lowest in **all six evaluated
seasons individually**; vs (c) **−0.02055 [−0.02330, −0.01779]** — the
naive-extrapolation floor loses at **~70× the (a)−(b) gap**, confirming (c) as
the interpretability floor it was registered to be. Floor ≥5 met at 6; harness
selftests passing; composition printed: **22,707 boundary states / 7,546 games,
234 pushes excluded and counted, 104 OT games** in the OT-inclusive settlement
frame. **Adopted form: walk-forward per-fold refit, joining R1b's σ and R2's
shrink.**

**SENSITIVITY b′ (never-gating), the ruling measured:** rate-keyed beats
absolute-invariance, **−0.00017 [−0.00030, −0.00003]**. The σ-port fork was
ruled on physics reasoning and **filed with its rival as a live sensitivity
rather than a discard — so the ruling got TESTED instead of obeyed, and
survived.** That pattern — **rule + rival-as-sensitivity** — is precedent.

**DEFECT, disclosed before adoption and governing what may be quoted.** The
registration declared 2016's 23 lined games unusable; the fold builder admitted
them to training and to an equal-weight cluster in the physics table. **The GATE
is invariant** (−0.00031 → −0.00030). **The PHYSICS TABLE was materially
contaminated:** first-read endQ1 b printed **1.181 [0.956, 1.406]**; corrected
**1.087 [1.060, 1.113]** — a **five-fold CI inflation from one junk cluster**.
**Only the corrected table exists for citation; the first-read table is
retracted on sight wherever it appears.**

**STRUCTURAL FINDINGS.** NBA banking is **nearly pure** — b = **1.087 / 1.018 /
1.021** vs WNBA **1.318 / 1.208 / 1.128**, all CIs excluding 1.0: pace
persistence is real and **~5× smaller**; an NBA totals surprise is almost
entirely banked points. **Second instance of the ported table being wrong IN
KIND rather than degree** (R1b: inverted σ slope; R3b: collapsed banking) —
**arms-not-defaults justified twice by shape, never merely by level.**

**The invariance-class contrast worth keeping: quarter-structure constants port
(shares 0.2538 / 0.5066 / 0.7577, near-identical to WNBA); pace-persistence
constants do not. Which class a constant belongs to is now a question to ask
BEFORE porting it.** σ = 15.25 / 12.81 / 9.24, below every ported form.

**Effect size: physics, not alpha. No capital implication.**
