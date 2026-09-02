# A1 oscillation harvest — descriptive pass

**IN-SAMPLE, DESCRIPTIVE, HYPOTHESIS-GENERATING. Nothing gates.**

Pins: `live_ticks_pulse_games_20260901T195202Z.csv.gz`, `roundtrip_ledger_20260901T195202Z.csv`. Reproduce: `python3 analysis/a1_oscillation_descriptive.py` (self-tests first).

Feature (pinned): variance ratio on 2s bars, 120s window, k=6; revert<0.8 / trend>1.2.


## Synthesis — the wave's central live question

The null was three-for-three on BELIEF properties (edge_net; the coupling; Q1 edge-source, B's split). A1 is the first candidate ordering on a MARKET property — realized oscillation. What this pass found:

1. **Character persists (demand #4): PASS.** At the ~90s trip horizon a reverting state stays reverting 52% of the time vs a 34% base — lift +0.174 [+0.159, +0.188], game-clustered, well off zero. Not a noise label.
2. **A maker-frame ordering exists but is COMPOSITION-FRAGILE.** Pooled, reverting entries +4.35% [+1.59%, +7.11%] (CI excludes zero), above rw -3.12% and trend -1.15% — the only maker-frame ordering on a market property in the wave. BUT counts-before-ratios (wave rule 1): equal-weighted BY GAME the revert per-$ is only +0.77% — the pooled positive is carried by a few high-count games (per-game revert count ranges 1–82). The pooled number is game-composition-weighted; the ordering is real but not robust to game weighting, and the paired-placebo test below shows selection adds ~0.
3. **It does NOT clear the uniform pessimistic bar (demand #6).** At the measured 4.70¢/leg concession every character is negative (revert -23.89%) — the freshness shape. BUT the ordering survives (revert less-negative than rw), and A1's mechanism makes a SPECIFIC further prediction the uniform re-score cannot test: reverting states carry BELOW-average adverse selection (that IS the mechanism — an oscillation is not an informed aggressor picking you off). The uniform concession assumes one number for all characters; **only the gate (real per-character fills) measures whether revert entries actually pay less.** So A1 is neither cleared nor dead: its kill condition points straight at what the gate must measure.
4. **Not purely mechanical (placebo, demand #3).** Random entries also show revert>rest, but weakly (placebo revert +0.45% [-5.83%, +9.19%], CI spans zero) vs real +4.35%. Pairing (D's refinement): the PAIRED game-level diff (real − placebo, same games) is +0.04% [-10.10%, +7.81%] over 32 games — CI still spans zero, so the selection-above-mechanical split is not resolved in-sample even paired — the honest answer, and the gate settles it.
5. **Incremental to B's frozen P(ride) (demand #5).** Revert beats non-revert INSIDE every P(ride) quintile (strongest in Q5), where B's own read has per-$ flat across quintiles. Not the ride mask renamed.

**Verdict (aligned with the research agent's ruling).** A1 FAILED demand #6 as written — negative in every character under the uniform concession. The pilot justifies NOTHING on its own: the maker-frame ordering is composition-fragile (pooled +4.35%, equal-weighted +0.77%), and the paired-placebo test shows selection adds ~0 over the roll's mechanical harvest. TWO nested in-sample artifacts reproduce this tape without any market truth: (a) engine payoff coupling (the 5¢ roll harvests oscillation by construction — the placebo shows ~80% of the ORDERING present in coin-flip entries), and (b) fill-model optimism CORRELATED WITH THE FEATURE (the mid-cross rule books favourable drift largest exactly in oscillating states — 'revert character' and 'fill-model profit' are near-synonyms on this tape). Nothing on the pinned tape can separate 'revert states are genuinely maker-friendly' from those two artifacts. **Only real fills can — which is why the gate is the only instrument, not a consolation.** What survives to justify running it: the persistence result (+0.174 at 90s, robust) and one sharp falsifiable claim — that reverting fills pay measurably below-average concession. Breakeven burden (linear between the two published arms): c* in **[0.13, 0.72]¢/leg** (equal-weighted to pooled) vs the 4.70¢ average — an ~85–97% concession reduction. Large, a one-number band, printed so no 3.9¢ result is later called 'directionally supportive'. Not a capital claim.

*Two framing notes carried from the manager's routing:* A1 leans on NO 'margin-driven = suspect' reasoning (B's Q1 split closed that door; this is a vol-character feature, orthogonal to edge source). And it does not build on B's lone unranked Q1-mixed ≥10¢ interval — a different partition; no cell here is derived from it.


## DEMAND #4 — does vol character persist? (the make-or-break)

Adjacent-window autocorrelation of VR (C's 'FIRST' demand):

- lag 1 window(s) (120s): Spearman +0.214 (n=24166)
- lag 2 window(s) (240s): Spearman +0.210 (n=23423)
- lag 3 window(s) (360s): Spearman +0.192 (n=22787)

Feature[t-120,t] -> forward[t,t+H], game-clustered (34 games; the trip horizon is ~90s). Lift = P(revert ahead | reverting now) − base rate:

| H (s) | n | games | Spearman [95%] | base revert | cond\|past revert | lift [95% clustered] |
|---|---|---|---|---|---|---|
| 60 | 87127 | 34 | +0.197 [+0.178, +0.215] | 0.366 | 0.537 | +0.171 [+0.156, +0.185] |
| 90 | 92668 | 34 | +0.201 [+0.178, +0.223] | 0.343 | 0.516 | +0.174 [+0.159, +0.188] |
| 120 | 96067 | 34 | +0.222 [+0.198, +0.246] | 0.361 | 0.542 | +0.181 [+0.165, +0.197] |
| 300 | 102305 | 34 | +0.274 [+0.249, +0.298] | 0.387 | 0.600 | +0.213 [+0.193, +0.230] |

## DEMAND #2/#6 — pilot per-$ by character, over ALL fills (PILOT, contaminated — informs, never gates)

n fills with feature: 1688/1944 (33 games). Char counts: {'revert': 1099, 'rw': 401, 'trend': 188}

| character | maker per-$ [95% clustered] | pessimistic per-$ [95%] | n | games |
|---|---|---|---|---|
| revert | +4.347% [+1.590%, +7.107%] | -23.888% [-28.183%, -20.123%] | 1099 | 32 |
| rw | -3.121% [-8.156%, +1.903%] | -34.621% [-40.707%, -28.913%] | 401 | 29 |
| trend | -1.152% [-7.227%, +4.586%] | -24.957% [-30.576%, -19.348%] | 188 | 31 |

## DEMAND #3 — payoff-structure placebo (random entries, coin-flip side)

n placebo rolls: 2128 (34 games). If the revert>rest gradient appears HERE, it is the engine's payoff coupling, not selection.

| character | placebo maker per-$ [95% clustered] | n | games |
|---|---|---|---|
| revert | +0.450% [-5.829%, +9.192%] | 786 | 34 |
| rw | -5.512% [-9.491%, -1.259%] | 962 | 34 |
| trend | -4.527% [-10.618%, +1.564%] | 380 | 34 |

**Paired game-level diff (revert, real − placebo, same games)** — removes shared game variance (D's refinement): **+0.044% [-10.096%, +7.810%]** over 32 games (real +0.770% vs placebo +0.726% in-game means). Spans zero: unresolved in-sample even paired — the gate settles it.


## DEMAND #5 — incremental to B's frozen P(ride) (per-$ within quintile)

B's own read: per-$ is flat across P(ride) quintiles. If revert only re-orders within-quintile what P(ride) already captures, A1 is the ride mask renamed.

| P(ride) quintile | revert maker per-$ | non-revert maker per-$ | n |
|---|---|---|---|
| 1 | +4.281% (n=228) | +2.397% (n=132) | 360 |
| 2 | +2.776% (n=239) | -1.705% (n=100) | 339 |
| 3 | +4.954% (n=229) | -3.204% (n=102) | 331 |
| 4 | +2.459% (n=206) | -0.975% (n=123) | 329 |
| 5 | +7.597% (n=197) | -8.844% (n=132) | 329 |

## DEMAND #1 — the gate (real resting fills): NO DATA, and its spec

`shadow_quote_fills` is not in the pinned exports (live DB only), so the evidence-grade gate reads **NO DATA** here. This pass is the instrument and the pilot; the gate is a forward / DB study (feature AND outcome on the quote engine's own tape, per the pinned spec).

**The gate scores TWO things, not one (D's refinement):**

1. **Concession-by-character — the MECHANISM test, fast.** A1's whole claim is concession HETEROGENEITY: reverting-character fills carry below-average adverse selection. That concession is measured directly per quote-engine fill (`mid_at_quote` vs `mid_at_fill`), per-fill and tight — far fewer games than P&L significance needs. If reverting fills do NOT show below-average concession, the mechanism is dead long before the slower per-$ floors fill (see the dated horizon below).

2. **Per-$-by-character — the ECONOMICS test, slow.** The registration's gate proper: does the character order per-$ over all fills on real fills, surviving the (now per-character, not uniform) concession, game-clustered. This is the floors-in-games arm.

Score both; the concession split is the leading indicator, the per-$ the verdict.


### Gate accrual and floors (rule 10)

Accrual measured by the research agent against PRODUCTION, read-only, **query stamped 2026-09-02 15:25Z** (not computable from the pinned exports; cited here with its provenance, not re-derived):

- in-game fills **17,032 over 13 games** (2026-08-18 → 08-22), pregame 307 over 13 — a ~1,310 in-game-fills-per-game rate (2,400–5,000/day over 3–5 games/day).

- At this tape's character shares (~87% featured, ~65% revert) the FILL floors (≥120 revert / ≥60 non-revert) clear inside a single game; the **GAME floors are the only binding constraint** (≥12 revert-games / ≥8 non-revert-games) ≈ **3–4 slate days**. Dated horizon **~Sept 26–30** if the quoter runs from the Sept 17 resumption, caveated for late-season slate density.

- **DEPLOYMENT HOLD (a fact, not a suspicion):** fills STOP on 2026-08-22 and the production health check shows no quote-engine (or PULSE) container running — the overlay is not deployed. The registration's clock does not tick until redeploy (operator-gated, Sept 17 deadline). **Cohort accrual begins at the first fill after the landing epoch; if no fills exist 7 days after WNBA resumption, the registration surfaces a DEPLOYMENT HOLD rather than silently aging toward exhaustion** — an undeployed quoter is a named operational state, never data.


### Weighting and breakeven, pinned BEFORE any forward number (research amendment)

- **Primary = POOLED per-$ with a game-clustered CI** — the economic quantity (pooled is what you earn if sizing follows fill availability). **Robustness clause:** if the game-equal-weighted point estimate disagrees IN SIGN with the pooled read, the verdict downgrades to straddle regardless of the pooled CI. No weighting shopping after the fact.

- **Both breakevens printed** (linear interpolation between the two published arms, slope ≈6.01%/(¢/leg)): **c\* ≈ 0.72¢/leg** from the pooled arm (+4.35% at 0¢), **c\* ≈ 0.13¢/leg** from the equal-weighted arm (+0.77% at 0¢). The mechanism's burden lives in that band; the gate measures where the real per-character concession falls (vs the 4.70¢ average).

- **Prior, stated plainly:** with the paired placebo at +0.04% [−10.10%, +7.81%], the in-sample null (engine coupling + fill-model optimism concentrated in oscillating states) is STRONGLY FAVORED. A1 is not a promising candidate; it is a cheap discriminator on a live question. Stating the prior as adverse also protects the PASS branch: clearing a stated-adverse prior on real fills cannot be discounted as expectation-confirmation.


## Multiple comparisons & capital

Several character×horizon×quintile cells are read here; a few sub-0.05 patterns are expected by chance. Ranking is mechanism + persistence + placebo-separation, never a single cell's CI.

**No in-sample result justifies capital. The forward test is the evidence.**



---

**DATED LEAGUE-FILTER LINE (research agent, 2026-09-02, landed by manager
BEFORE the first NFL datum):** the gate's cohort is **league = WNBA
(basketball) ONLY** — `shadow_quote_fills` goes mixed-league the moment
GRIDIRON's NFL recording produces ticks the filterless quoter observes.
This gate's floors, c* band, and economics are WNBA-derived; NFL fills
silently entering would contaminate the program's foundational read.
Cohort filters key on the event slug's league prefix.
