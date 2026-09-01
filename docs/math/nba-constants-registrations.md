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
