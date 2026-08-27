# Boundary deviation vs the live price (F7 / ledger #18)

**Registered and gated 2026-08-25, same day. VERDICT: FAIL — the deviation adds
nothing beyond the price.**

**Provenance of the registration.** The registration of record is the ledger row
— [pulse-hypotheses.md](../pulse-hypotheses.md) #18, written by the research
agent before computing. This page is the **write-up**, landed 2026-08-27 so the
result has an artifact to audit against rather than only a table cell. Nothing
here restates the gate more favourably than the row does; the row remains
authoritative if the two ever disagree.

## Question

Given the live winner-market mid at a period boundary, does the margin's
deviation from the prorated closing spread carry residual information about the
outcome? Motivated by F1: margins revert ~15–17%, and the tradable question was
whether the market already prices it.

## Method

Period-boundary instants (first ticks of Q2/HT/Q4; mid = median two-sided mid in
the following 30s), slug-first frame per V20, logistic outcome ~ logit(mid) +
c·D, SEs clustered by game. Floor ≥ 15 joined games with a pregame anchor; ran
at 54.

**Harness mutation-tested before the real run:** calibrated synthetic reads
c ≈ 0; injected under-reversion recovered at −0.086.

## Result

**c = +0.0538, 95% CI [−0.0634, +0.1710], 153 observations / 54 games.**

Per boundary: Q2 +0.030, HT +0.054, Q4 +0.079 — **every CI spans zero.** The
mid's own logit coefficient is **0.881**: the boundary price is close to
calibrated by itself. The pre-declared money clause was not computed, because
the primary failed.

## Reading

F1's reversion is real physics **and it is in the price.** What survives is
calibration — the FV should shrink deviations the way the market does, which is
exactly what the reversion-shrink arms
([#89](pulse-reversion-shrink.md), [#89-fg](pulse-reversion-shrink-finegrid.md))
implement.

This is a third distinct way for a hypothesis to die: not "no effect" (#1) and
not "the effect inverts under the right anchor" (#16), but **a real effect you
cannot trade because you are not the first to see it.**

## Window and disclosure

Mirror ticks; the 2026-08-26 full-history per-day parity audit subsequently
verified the source days hole-free. **Disclosure:** the archive's prices were
seen in #16's study; this joint quantity was first computed here.

**Reproduction:** session scratchpad `survey/stage_b.py`.

---

*Result recorded 2026-08-25, written up 2026-08-27. Append below this line,
never above it.*
