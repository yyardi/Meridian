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
