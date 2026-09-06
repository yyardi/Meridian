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

---

# RESULT — run once, decision rule applied

    POOLED              -0.01119 [-0.04316, +0.02077]  G=28  hw 0.0320

    subset                 n    G      diff            95% CI       hw    proj
    4th down             387   28  -0.02015 [-0.0556,+0.0153]   0.0355  0.0320
    red zone             473   27  -0.02184 [-0.0663,+0.0226]   0.0445  0.0320
    two-score, 2nd half  917   14  -0.03898 [-0.1003,+0.0224]   0.0613  0.0437
    3rd and long         315   28  -0.01196 [-0.0477,+0.0238]   0.0358  0.0320
    late (<=5 min)       395   25  -0.09277 [-0.2107,+0.0252]   0.1179  0.0339

    cells inspected 5 | clearing zero uncorrected 0 | Bonferroni 0

## ★ NO SUBSET FOUND — and the pre-registered words apply

**Zero of five clear zero, uncorrected or corrected.** The registered
expectation was *"insufficient power to tell"* and that is the result.

**And it is stronger than that: every point estimate is negative.** The model is
at or behind ESPN in all five subsets, so this is not a case of an edge hiding
somewhere the pooled test could not see. The worst cell is the one most likely
to be traded — **late game, −0.09277** — where a live model would be expected to
earn if anywhere.

## ★ MY NAMED ASSUMPTION FAILED, IN THE PESSIMISTIC DIRECTION

I projected on constant between-game variance and flagged that a subset could
come in **tighter**. **Every subset came in WIDER**, and the late cut by 3.5x
(0.1179 against 0.0339 projected).

**Between-game variance RISES under within-game subsetting**, which is the
opposite of the escape route I left open. Late-game plays are where games
diverge, so the per-game means spread out exactly where the row count falls —
both effects push the same way. **The structural argument was right and my
quantification of it was too kind.**

## What this closes and what it does not

**Closes:** there is no identifiable, ex-ante, football-structural subset of
this cohort on which the plays-only model beats ESPN. That is not "we could not
find one by searching" — the five were declared in a commit before the run.

**Does not close:** whether a market feature changes any of it. This model has
no price input. d5's frozen-anchor architecture is the next fit, and its
baseline is the pooled −0.01119 above rather than anything in this table.

---

# a1's down=0 sentinel, checked against this cohort

    export        63 rows with down==0 of 8,634   (0 NULL)
    my cohort     44 of 4,828   (0.91%)
    LATE cut       3 of 408     (0.74%), from ONE game

## Impact: none of the published numbers move

    pooled, as published          -0.01119 [-0.04316, +0.02077]
    pooled, sentinels excluded    -0.01039 [-0.04189, +0.02112]
    LATE, as published            -0.09277 [-0.21070, +0.02516]
    LATE, sentinels excluded      -0.08847 [-0.20222, +0.02528]

Both shifts are ~4% of their own half-width. **No verdict changes and
−0.09277 stands**, now with the contamination bounded rather than assumed.
Sentinels are also **not concentrated late** — 0.74% of the late cut against
1.47% mid-game and 0.85% early — so the cut was never differentially exposed.

## ★ TWO CORRECTIONS TO THE CHARACTERISATION

**1. They are not end-of-game markers.** By `play_type`: **Timeout 52,
Penalty 7**, Two Point Pass 2, Defensive 2pt Conversion 1, End Period 1. The
sentinel flags **non-snap events**, which occur throughout a game — that is why
they are spread evenly across the clock rather than piling up at the end.

**2. The feature values ARE fabricated, and I nearly reported the opposite.**
Seeing `distance` and `yards_to_goal` populated, I was about to flag a1's fix
(null the whole start block when down is falsy) as over-broad — discarding real
field position at a stoppage. **Checking whether the values were carried or
invented reversed that:**

    (distance, yards_to_goal) = (3,3) on  79.4% of down==0 rows
                               against    0.3% of normal plays   — 265x
    matches the PRECEDING play's distance   6.3%
    matches the preceding play's ytg        9.5%
    distinct values: distance {0,3,8,35,65}, ytg {3,8,35,65}

**`distance == yards_to_goal` on nearly all of them.** That is not a football
state — it is one number written into two fields. On a real play those are
independent and coincide only at the goal line. **The values are invented, they
are not carried, and a1's fix is correct as written.**

"Populated" is not "real", and the check that separates them is whether the
value tracks the preceding play or a constant.
