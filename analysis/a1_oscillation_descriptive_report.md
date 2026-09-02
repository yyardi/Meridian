# A1 oscillation harvest — descriptive pass

**IN-SAMPLE, DESCRIPTIVE, HYPOTHESIS-GENERATING. Nothing gates.**

Pins: `live_ticks_pulse_games_20260901T195202Z.csv.gz`, `roundtrip_ledger_20260901T195202Z.csv`. Reproduce: `python3 analysis/a1_oscillation_descriptive.py` (self-tests first).

Feature (pinned): variance ratio on 2s bars, 120s window, k=6; revert<0.8 / trend>1.2.


## Synthesis — the wave's central live question

The null was three-for-three on BELIEF properties (edge_net; the coupling; Q1 edge-source, B's split). A1 is the first candidate ordering on a MARKET property — realized oscillation. What this pass found:

1. **Character persists (demand #4): PASS.** At the ~90s trip horizon a reverting state stays reverting 52% of the time vs a 34% base — lift +0.174 [+0.159, +0.188], game-clustered, well off zero. Not a noise label.
2. **The maker-frame ordering is REAL and best-in-wave.** Reverting entries +4.35% [+1.59%, +7.11%] (CI excludes zero), above rw -3.12% and trend -1.15%. A market property orders the maker frame where three belief properties did not — the tape-vs-model distinction is real AT THE MAKER FRAME.
3. **It does NOT clear the uniform pessimistic bar (demand #6).** At the measured 4.70¢/leg concession every character is negative (revert -23.89%) — the freshness shape. BUT the ordering survives (revert less-negative than rw), and A1's mechanism makes a SPECIFIC further prediction the uniform re-score cannot test: reverting states carry BELOW-average adverse selection (that IS the mechanism — an oscillation is not an informed aggressor picking you off). The uniform concession assumes one number for all characters; **only the gate (real per-character fills) measures whether revert entries actually pay less.** So A1 is neither cleared nor dead: its kill condition points straight at what the gate must measure.
4. **Not purely mechanical (placebo, demand #3).** Random entries also show revert>rest, but weakly: placebo revert +0.45% [-5.83%, +9.19%] (CI spans zero) vs real +4.35%. The real effect sits above the placebo point estimate — selection adds beyond the roll's mechanical harvest — though the intervals overlap, so the split is not sharply resolved in-sample.
5. **Incremental to B's frozen P(ride) (demand #5).** Revert beats non-revert INSIDE every P(ride) quintile (strongest in Q5), where B's own read has per-$ flat across quintiles. Not the ride mask renamed.

**Verdict:** the market-property-orders-outcomes question resolves POSITIVE at the maker frame — the wave's terminal-negative is averted, the tape-vs-model distinction is real. Whether it is TRADABLE turns on the per-character concession, which the uniform pessimistic frame cannot resolve and the quote-engine gate can. A1 earns its gate. Not a capital claim; a hypothesis sharpened to one measurable question.

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

## DEMAND #5 — incremental to B's frozen P(ride) (per-$ within quintile)

B's own read: per-$ is flat across P(ride) quintiles. If revert only re-orders within-quintile what P(ride) already captures, A1 is the ride mask renamed.

| P(ride) quintile | revert maker per-$ | non-revert maker per-$ | n |
|---|---|---|---|
| 1 | +4.281% (n=228) | +2.397% (n=132) | 360 |
| 2 | +2.776% (n=239) | -1.705% (n=100) | 339 |
| 3 | +4.954% (n=229) | -3.204% (n=102) | 331 |
| 4 | +2.459% (n=206) | -0.975% (n=123) | 329 |
| 5 | +7.597% (n=197) | -8.844% (n=132) | 329 |

## DEMAND #1 — the gate (real resting fills): NO DATA

`shadow_quote_fills` is not in the pinned exports (live DB only), so the evidence-grade gate reads **NO DATA** here. This pass is the instrument and the pilot; the gate is a forward / DB study (feature AND outcome on the quote engine's own tape, per the pinned spec).


## Multiple comparisons & capital

Several character×horizon×quintile cells are read here; a few sub-0.05 patterns are expected by chance. Ranking is mechanism + persistence + placebo-separation, never a single cell's CI.

**No in-sample result justifies capital. The forward test is the evidence.**

