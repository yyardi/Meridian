# Intent-crossing arms — registration

**Written by the research agent 2026-09-01. NOTHING COMPUTED FORWARD.**
Landed unmodified. The cohort cutoff is this document's own first commit
instant, read with
`TZ=UTC git log --format=%ct --follow -- docs/math/intent-crossing-arms.md | tail -1`
and converted from epoch — never from prose in this file.

## Motivation, disclosed

Quant D's decomposition of 1,019 unfilled intents (PR #126): the **+33.34¢**
counterfactual lives **entirely in the never-reachable third**; patience earns
nothing (the 63.9% the market came back to are worth −1.06¢); resting is
adversely selected by construction. **The hypothesis is post-hoc from seen
tape; the TEST is forward.** That ordering is stated because it is the point.

## Arms — both scored off the decision tape, no engine change, no new plumbing

**(a) CROSS-ALWAYS.** Every entry intent scores as a taker fill at the
intent-time far touch. Per contract: `s·(S − touch_at_intent) − fee`, with
`fee = 0.06·p·(1−p)` at the touch. **CONTEXT ARM: never gates, expected
negative.** It exists so that (b)'s selectivity is distinguishable from
"crossing was simply fine."

**(b) CROSS-SELECTIVE.** Identical scoring; eligibility only where the tape's
own decision-time fields show `fair_value` clearing the touch plus fee. **The
exact eligibility formula is pinned in the harness before the first read. No
post-hoc slicing of eligibility.**

## Score

Money-at-price, unit size, settlement from resolved outcomes, **game-clustered
(C4)**. The **linking policy is pinned to D's live-faithful orphan-join rule
from #126 exactly** — the −10.0¢ → +1.2¢/$ sensitivity is why it is pinned
here rather than chosen at read time.

## Cohort

**Forward only** — intents recorded after this registration's landing commit.
The existing tape is descriptive context permanently; it has been seen.

## Floors

**≥ 15 games containing ≥ 1 arm-(b)-eligible intent AND ≥ 200 arm-(b)
intents.**

## Gate — arm (b) only

- **PASS**: game-clustered per-$ CI entirely positive at floor.
- **FAIL**: CI entirely negative at floor.

## Closure clause

At **2× both floors** with arm (b)'s CI still straddling zero:
**FAIL-BY-EXHAUSTION** — whatever the effect is, it is smaller than is worth
trading at these costs. **The gate CLOSES; it does not ride.** (Third-species
rule, `findings.md`: a gate must name the condition under which it closes, not
only how it passes or fails.)

## Confounds carried

- The late-game reached-later window is **mechanically shorter**; this rides
  with any late cell.
- Spreads regime-shift within games (**4–7¢ early, 8–10¢ late** medians), so
  arm (b)'s eligibility is **spread-conditional by construction** — priced in,
  never sliced out.

## Mutation, before the first real read

The scorer reads **≈0 on a shuffled-settlement tape** and **recovers an
injected edge**.

---

**No in-sample result justifies capital. The forward test is the evidence.**

*Results append below this line, never above it.*

## 2026-09-02 — linking-pin harmonization (report layer; the gate is untouched)

D's scorer surfaced that this registration's context line pins the **drop**
rule while the companion pins the **repaired** rule — opposite sides of the
sign-flipping sensitivity, in two texts that claim to share a policy. **The
research agent's resolution: both gates' CONTEXT lines harmonize on the
REPAIRED `lineage_source` rule** (it corrected an attribution bug; the
artifact-correct side), **with the drop-rule number printed beside wherever a
linked context figure appears** — the both-sides #147/#148 convention.

**No gated quantity in either registration depends on linking** — both scorers
are linking-free by construction. This is a report-layer harmonization, not a
gate change; the original pin text stands above this note untouched. The
scorer's NOTICE retires with this note's landing.
