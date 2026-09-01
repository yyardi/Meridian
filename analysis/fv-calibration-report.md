# Track C — is `fair_value` calibrated, and where does it break?

**IN-SAMPLE, DESCRIPTIVE, HYPOTHESIS-GENERATING.** Nothing here gates anything.
*No in-sample result justifies capital. The forward test is the evidence.*

Artifact: [`fv_calibration.py`](fv_calibration.py), run against the wave pins
(`pulse_decisions_full_20260901T195202Z.csv`, `resolved_outcomes_20260901T195202Z.csv`).

```bash
.venv/bin/python analysis/fv_calibration.py --selftest   # mutation-test first
.venv/bin/python analysis/fv_calibration.py
```

The instrument was mutation-tested before touching real data (wave rule 4): a
synthetic calibrated series reads REL≈0.0002, an injected overconfidence of
size 0.0122 is recovered at 0.0116, an uninformative forecaster reads RES=0,
the head-to-head detects a known better forecaster with a clustered CI
excluding zero, and PAVA removes an injected miscalibration.

## Frames — verified on this export, not assumed

`fair_value` and `market_bid/ask` are **always YES-frame** regardless of `side`
(no-side entries satisfy `edge_net == market_ask − fair_value` to 1e-9).
`settlement` is the market's YES outcome: totals YES = over (226/226), spread
YES = first-named margin + line > 0 (223/223), winner YES = first-named team
wins (31/31). The script asserts all of this on every run.

## Composition before ratios

12,689 hold rows with fv+book · **33 games** · 373 markets · 2026-08-18 → 08-31.
~60s per-market cadence. Rows: 6,957 total / 4,870 spread / 862 winner.
**Three model versions share the window** (v1 1,306 · v3 6,226 · v4 5,157 rows),
confounded with dates and games. Base rate P(YES) = 0.455 [0.298, 0.612].

Two selection caveats, stated up front:

- **Every hold row carries `reason='position_open'`** — holds are logged only
  while a position is open. They are unselected on the *current tick's*
  fv-vs-market gap (the manager's selection concern), but the market was
  selected by a past entry and by not-yet-exited. Least-selected sample the
  system logs; not a random sample of game states.
- Entries are conditioned on the disagreement being tested; they are shown
  separately and labelled.

All intervals are game-clustered (`clustered_mean`, the house sandwich) or
by-game bootstrap; a 1-per-market-per-5-game-minutes resample (12,689 → 1,502
rows) reruns every headline number as the autocorrelation sensitivity.

## The answer, plainly

**Q: Is the FV calibrated?** In the bulk, yes — indistinguishably from the
market's own mid *on this window's power*. Murphy REL = 0.0060 [0.0021,
0.0414] vs the mid's 0.0062; REL difference −0.0002 [−0.0041, +0.0057]. The
reliability curve's apparent tilt (realized below forecast through the 0.1–0.8
bins) is **shared by the mid on the same rows** — it is this window's
realization noise at 33 games, not model-specific bias.

**Q: Calibration failure or resolution failure?** **Resolution.** The pooled
Brier deficit vs the mid (+0.0061 [−0.0111, +0.0233], CI spans zero at 33
games; direction matches the wave prior measured on 45.8k) decomposes as ~0
REL difference and −0.0069 [−0.0242, +0.0117] RES difference. The decisive
exhibit: **leave-one-game-out isotonic recalibration makes the model worse,
not better** (+0.0055 vs raw fv; +0.0116 vs mid; point REL rises 0.0060 →
0.0110). There is no stable monotone mapping error to fix. Recalibrating the
existing FV is a dead end; the deficit is information content, with one
exception below that is really an *input-integrity* failure.

**Q: Where does it break?** Not uniformly. The bulk is market-shaped noise
(fv–mid correlation 0.94); the losses concentrate in nameable places:

| slice (holds, model − mid Brier) | diff | 95% CI | rows / games |
|---|---|---|---|
| all | +0.0061 | [−0.0111, +0.0233] | 12,689 / 33 |
| totals | +0.0144 | [−0.0137, +0.0425] | 6,957 / 25 |
| spread | −0.0044 | [−0.0284, +0.0196] | 4,870 / 32 |
| **clock estimated** (v1-only — see confound) | **+0.0420** | [−0.0438, +0.1277] | 1,055 / 22 |
| clock real | +0.0029 | [−0.0145, +0.0202] | 11,634 / 31 |
| v1 unflagged (thin control) | +0.0044 | [−0.0159, +0.0247] | 251 / 10 |
| mid 0.35–0.65 (the size band) | +0.0176 | [−0.0111, +0.0462] | 3,046 / 32 |
| \|fv−mid\| > 0.05 (disagreements) | +0.0120 | [−0.0229, +0.0468] | 6,151 / 32 |
| \|fv−mid\| ≤ 0.05 (agreements) | +0.0006 | [−0.0022, +0.0035] | 6,538 / 33 |
| entries (selection-conditioned) | +0.0037 | [−0.0117, +0.0191] | 2,974 / 34 |

Every CI spans zero — 33 games is 33 games. The *pattern* is what travels:
whenever the model disagrees with the market, the market is the one that tends
to be right, and the tendency is largest exactly where the system would trade
(totals, the 35–65¢ band, big claimed gaps).

## The extreme-confidence tail — the sharpest fact in the run

At claimed confidence ≥0.98 the model missed **22 of 389** rows (5.7%, vs its
own claim of ≤2%). The mid at ≥0.98 missed **0 of 170**. All 32 extreme misses
(both tails) are **totals** markets, they sit in **6 games**, and they carry
17% of the pooled Brier gap by themselves. Row-level inspection names three
doors, none of which is "slightly wrong probabilities":

1. **Corrupted state in, certainty out.** sea-dal 08-23: score 91 points at
   "Q2, 30:00 left" — jointly impossible (the game finaled 162) — and *not*
   flagged (`minutes_left_is_estimate='f'`, and a **v3** row, so state
   corruption is not confined to v1's clock estimator). The projection
   extrapolated to 235.1 and emitted P(over 171.5) = 1.0000 against a market
   at 0.62. Under won.
2. **Under-shrunk pace with too-small σ mid-game.** conn-dal 08-30: 105 points
   at the half → projection 200.6, σ 13.0 → P(over 173.5) = 0.98 for 19
   consecutive minutes. Second half scored 63; final 168. (The mid also missed
   at ~0.91 — but it never manufactures 0.98.)
3. **A Gaussian endgame cannot price discrete scoring.** por-atl: 181 on the
   board, line 183.5, 9 seconds left, σ = 0.14 → P(over) = 0.0000 while the
   market bid 0.63–0.97; the foul game produced 3 points, over won. ind-ny:
   184 with 2:05 left, P(over 200.5) = 0.0004, market bid 0.82 — the game went
   to overtime (88-96 → final 102-109, total 211) and the projection
   converges to `total_so_far` at the buzzer, so **P(OT points) is
   structurally zero in the model** while the market prices it.

The market posts no 0.98s it cannot cash because its extremes are made of
orders; the model's extremes are made of a parametric tail fed by whatever
state arrives.

## Top-3 candidate hypotheses (each: sentence · confound check · forward test)

1. **State-integrity, not probability, is the model's worst input** — with a
   confound that must travel with it (B's catch, verified here): the
   `minutes_left_is_estimate` flag exists **only on v1 rows** (v3/v4 read the
   venue clock by construction), so the raw flagged-vs-unflagged contrast
   (+0.042 vs +0.003) is mostly v1-vs-rest. Within v1 the point contrast
   survives (flagged +0.042 / 22 games vs unflagged +0.004 / 251 rows, 10
   games) but the control cell is too thin to separate clock quality from
   version. What is NOT confounded: the row-level door — a jointly-impossible
   clock/score state on a **v3 unflagged** row priced as P=1.0000. Forward
   test: log a score-vs-elapsed plausibility check per tick on the current
   version, and score plausible vs implausible cohorts in the next N games.
2. **The totals endgame needs an event-driven tail (fouling + OT), not a
   Gaussian:** every ≥0.98 miss is a total, and the two endgame misses are
   exactly the discrete-scoring regimes σ→0 cannot represent. Confound: 6
   games; endgame rows are few. Forward test: a registered arm that floors
   σ near the line at low clock and adds an explicit P(OT) term, scored on
   paired Brier vs the incumbent, floors in games.
3. **Where the FV disagrees with the mid by >5¢, the mid is right** (+0.0120
   on disagreement rows vs +0.0006 on agreement rows), i.e. `edge_net`
   measures model error, not edge — converging with B's finding that edge_net
   fails to order realized outcomes anywhere. Confound: disagreement
   correlates with wide books and broken states; recheck excluding flagged
   clocks and width>0.10. Forward test: the #20-family paired comparison on
   forward games, disagreement-bucketed. Cross-lane note (B, post-hoc on A's
   ledger): this Brier-level damage does **not** show up in trip P&L — a
   5¢-target roll pays on price oscillation and exit availability, not on the
   belief being right — so it should surface on the ride-to-settlement leg,
   where B's n is still too thin (15 est-clock rides) to see it. Entries
   claiming ≥0.25 edge carry the estimate flag at 42.7% vs 19.8% baseline,
   but per the same confound this largely restates "v1 wrote the big-edge
   tail" (70 of 157 ≥0.25-edge entries are v1).

## Top-3 negatives, mechanism named

1. **Recalibration is a dead end.** LOGO isotonic recalibration *worsens* the
   FV (+0.0055 vs raw, +0.0116 vs mid) because the miscalibration is not a
   stable mapping — it is episodic state corruption plus window noise, and an
   isotonic map fit on 32 games' quirks imports them into the 33rd.
2. **There is no period/price/width slice where the FV beats the mid with a
   CI excluding zero.** Best point estimates (spread −0.0044, Q1 −0.0022,
   |margin|<5 −0.0055) are noise-sized and sign-unstable across the 5-minute
   resample. The FV is a 0.94-correlated echo of the mid plus error.
3. **The model is not miscalibrated on average** — REL 0.006, same as the
   market's. The manager's prior (worse Brier everywhere) is *resolution*,
   which is the unfixable-by-mapping kind: the model must know something the
   mid does not, and on holds it demonstrably does not.

## Boring list (checked, flat)

- Book width ≤0.05 vs >0.05: both small, CIs span zero.
- minutes_left buckets [0,10) / [10,20) / [20,40): all span zero; [10,20)
  worst point (+0.0136), consistent with totals-midgame but not separable.
- Entries in the 35–65¢ band: +0.0015 [−0.0198, +0.0229] — flat.
- v3 vs v4 head-to-head: v3 −0.0010, v4 +0.0074, both span zero (confounded
  with different games; not evidence v4 regressed).
- Winner markets: −0.0011 [−0.0093, +0.0070] — flat, and only 862 rows.
- 5-minute resample moves no headline sign (+0.0061 → +0.0065 pooled).
- fv==0.0 exactly (217 rows, 17 games): the mid also sits ≈0.025 there;
  only 3 missed — not a sentinel-value bug.

## Multiple comparisons

~30 slices were read in this track alone, across four agents' dozens more;
several sub-0.05-looking patterns are expected by chance. Ranking above is by
mechanism plausibility and cross-slice robustness, never p-value. The
extreme-tail mechanisms rest on **6 games** and are row-inspected, not
statistically established.

*No in-sample result justifies capital. The forward test is the evidence.*
