# Pre-registration: does the WP model beat ESPN on any identifiable subset?

**Declared before running. Subsets are football-structural, not fitted.**

Cohort: the plays-only CFB WP model, 4,828 rows / 28 games, pooled result
Brier −0.01119 [−0.04316, +0.02077] against ESPN — indistinguishable.

## The five subsets, fixed now

    4th down                      down == 4
    red zone                      yards_to_goal <= 20
    two-score, second half        period >= 3 AND |home_score_diff| <= 16
    3rd and long                  down == 3 AND distance >= 7
    late (<= 5 min regulation)    reg_left <= 300

No subset may be added, dropped or re-bounded after the numbers exist.

## ★ POWER, AND IT IS ALREADY DAMNING — sizes measured, performance untouched

    subset                  rows  games  home-win  projected half-width
    4th down                 506     28     0.893              0.0320
    red zone                 611     28     0.893              0.0320
    two-score, 2nd half      989     15     0.800              0.0437
    3rd and long             406     28     0.893              0.0320
    late (<=5 min)           408     25     0.880              0.0339

**Every projection is 3–4x the pooled point difference of 0.011.**

**The structural reason, which is the real finding: the outcome varies only at
the GAME level, and a within-game subset keeps G almost unchanged.** Every game
has 4th downs, so the 4th-down subset still has 28 games — the same 28 outcome
draws — while shedding 90% of its rows. **Subsetting by play type cannot buy
independent information; it can only spend it.**

**Assumption named, because it is the one way the projection could be wrong:**
the scaling `0.032 * sqrt(28/G)` holds the between-game variance of the
per-game mean constant. A subset with genuinely lower between-game variance
could come in tighter than projected. **That is why the run happens rather than
being skipped — the actual half-widths are reported beside the projections, and
if any subset beats its projection materially that is itself the finding.**

## The decision rule

A subset counts as a real edge only if **its interval excludes zero at a
Bonferroni-corrected level for five tests** (alpha 0.01, widening intervals a
further ~1.3x). Anything else — including an uncorrected cell clearing zero — is
reported as **no subset found**, with the value shown and labelled as not
meeting the rule.

**Expected outcome, stated in advance: no subset resolves anything the pooled
test could not, and the correct report is "insufficient power to tell" rather
than a tuned model.** ce asked for that result in those words if it is what
comes back.

## What is NOT the bar

**A's CFB taker bar of 2.0–2.5pp is WITHDRAWN** — it was measured on the frozen
09-05 tape. Nothing here is compared to it. The honest bar is **unmeasured**,
with a WNBA proxy near 3.0–3.75pp, and A is measuring the real one tonight.
Brier differences are not money either way; that conversion needs the traded
subset, which this cohort does not have.
