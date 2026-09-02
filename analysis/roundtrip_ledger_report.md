# The PULSE round-trip ledger — funnel and top line

**Wave artifact (Quant A).** One row per entry intent, joined to its outcome.
Substrate for B/C/D — descriptive throughout, hypothesis-generating only,
nothing here gates anything.

- **Pins:** `pulse_decisions_full_20260901T195202Z.csv` (19,333 rows),
  `resolved_outcomes_20260901T195202Z.csv` (2,778 rows). Files only, no DB.
- **Reproduce:** `python3 analysis/roundtrip_ledger.py` — mutation tests run
  first and the script refuses to write output if they fail.
- **Artifact:** `backups/exports/roundtrip_ledger_20260901T195202Z.csv`
  (2,974 rows × 62 cols, one per entry intent).
- **Window:** 2026-08-18 → 2026-08-31, **34 games**, in-play only.

## Instrument checks (before any number)

- **Mutation-tested** (Wave Standard rule 4): a synthetic mirrored-pair null
  reads exactly $0.00; a hand-computed injected tape is recovered
  cell-by-cell (signs per side, per-$, both sensitivity arms, holding
  times, every outcome class); flipping the settlement column moves rides by
  exactly the hand-computed amount and moves trips not at all. Expected
  values are literals in the test, sharing no arithmetic with the pipeline.
- **Spot-checked** two real rows (a NO trip, a YES ride) against the raw
  tape by hand: match to 4 decimals.
- **`side` on this tape is economics**, not book mechanics: it is the
  position's direction, written by the engine itself
  (`core/pulse/storage.py`), with no venue row behind it. The V28
  `intent`-vs-`side` hazard belongs to venue activities rows and does not
  arise here.
- **Reconciliation scope:** a literal to-the-cent reconciliation against the
  venue-pinned intent-rule ledger (`core/audit/wnba_trade_sheet.py`, 26/26)
  is impossible for shadow rows — the venue has no record of them, by
  construction. What is matched is the *policy* (booked from economic
  direction, scope labelled, fees explicit); the mutation test substitutes
  for the reconciliation the venue cannot provide.
- **Settlement cross-check:** the decision rows' stamped settlements agree
  with the outcomes CSV on **1,944 of 1,944** filled entries, 0
  disagreements; outcome coverage is 100%.

## The funnel (counts before ratios — 34 games, 2,974 intent rows)

| stage | n | of intents |
|---|---|---|
| entry intents (`action=enter`) | **2,974** | 100% |
| filled (simulated maker fill) | **1,944** | 65.4% |
| withdrawn before fill (edge gone / stream gone) | 1,019 | 34.3% |
| expired unfilled (still resting at export cut) | 11 | 0.4% |
| — closed by exit fill (“trip”) | **1,807** | 60.8% |
| — rode to settlement (“ride”) | **137** | 4.6% |
| — still open | **0** | 0% |
| **scored (reach a terminal price)** | **1,944** | **65.4%** |

Every filled entry reaches a scoreable end; the only attrition is the 34.6%
of intents that never fill (the historical figure is 46% — this engine's
join-the-touch limits fill more often than that). The funnel partitions
exactly; the script asserts it.

**Composition facts B/C/D must not average away:**

- **Live-blocked intents: 2,870 of 2,974 (96.5%).** `capped_stake_usd = 0`
  — mostly `max_open_per_event` (2,759). These rows carry the model's full
  desired size in `stake_usd` and are real intents, but live mode would have
  placed **none** of them. The live-faithful book is **104 intents / 60
  scored rows / $32.54 staked across 13 games** — a far smaller experiment
  than the full-intent tape.
- **Cap-era seam:** 32 rows decided before 2026-08-21 have
  `cap_semantics='enforced'` — caps *shrank the recorded size* and the
  desired size was never written. `live_stake_usd =
  coalesce(capped_stake_usd, stake_usd)` is correct in both eras;
  full-intent sums are only correct after the seam. (The brief's "recorded
  with stake 0" is not what this export does — blocked intent is marked in
  `capped_stake_usd`, never in `stake_usd`, which is nonzero on all 2,974
  rows.)
- **Lineage repair:** 20 exit rows from 2026-08-18/19 predate `entry_id`
  wiring; the 17 filled ones were re-linked (rule in the script docstring,
  `lineage_source='reconstructed'`) — otherwise 17 real trips would book as
  rides. 0 orphans left unlinked.
- Trips close fast (median 90 s hold; median time-to-fill 34 s); rides are
  the tail (median 3.3 h to settlement stamp). Exit reasons on trips:
  profit_target 1,191, ev_stop 486, fv_adverse 130.
- Entry cost sits at median 44¢ (IQR 31–57¢) — mostly inside the 35–65¢
  band the Wave Standard flags as never-yet-sliced.

## Top-line realized P&L (policy: round-trip, YES frame, maker fills at recorded limits, $0 fees)

Fees are $0 by the venue's schedule, not by omission: both legs rest as
maker limits (never a cross), θ_maker = 0 (V9/C7), settlement is not a
trade. The 0.06 taker coefficient is real (V9) and appears as a labelled
arm, not the policy. Window 2026-08-18→31; n = **34 games / 1,944 rows**
(live-faithful: **13 games / 60 rows**); CIs are game-clustered bootstrap
(10,000 resamples of games, seed 20260901) on Σpnl/Σstake.

| frame | total P&L | staked | return on stake, 95% game-clustered CI |
|---|---|---|---|
| full-intent, policy | **+$27.05** | $1,015.40 | **+2.7% [−0.3%, +4.8%]** |
| full-intent, taker-fee arm (θ=0.06 each filled leg) | −$28.44 | $1,015.40 | −2.8% [−6.1%, −0.5%] |
| full-intent, pessimistic arm (4.70¢/contract each filled leg, C13 in-game) | −$194.71 | $1,015.40 | −19.2% [−23.5%, −16.2%] |
| live-faithful, policy | **+$1.34** | $32.54 | +4.1% [−4.5%, +10.6%] |

Split by how positions ended: trips +$55.86 (1,807 rows), rides −$28.82
(137 rows) — full-intent, policy frame. Not interpreted here; that is B's
slice.

**The live-faithful read is decided by the lineage repair.** All 17
reconstructed links fall in the early era — exactly the era where caps
were enforced rather than annotated — so they are 17 of the 60
live-faithful scored rows (28%). With the re-linking, the live-faithful
frame reads +4.1% dollar-weighted (+1.2¢/$ equal-weighted; 55 trips /
5 rides); booking those 17 as rides instead reads **−6.3%** (−10.0¢/$;
38 trips / 22 rides). The full-intent frame barely moves (−$3.40 on
+$27.05). Independently confirmed by B's from-scratch reconstruction,
which matches this ledger to 6 decimals on every row except exactly those
17. Any registered series on the live-faithful population inherits this
sensitivity; filter on `lineage_source` to take either side.

**The ordering of those arms is the finding to carry, not the +2.7%:** the
headline is entirely inside the maker-fill assumption. Under the measured
in-game fill concession the same tape reads −19.2%, and trips pay the
concession twice. Which arm is the right prior for THIS engine's fills is
an open question for the wave (the concession was measured on a different
entry rule), not settled here.

## Caveats

- P&L is one labelled policy + two labelled arms — no third definition
  exists in the artifact. Per-row scope coincides with venue per-position
  average-cost ex-fees (V27) because positions are single-lot and
  non-overlapping.
- Simulated fills use the study's endpoint rule (mid crosses the limit),
  optimism and all; fill-dependent numbers inherit it.
- `settled_at` is when the settlement endpoint answered, which lags game
  end — ride holding times are upper bounds.
- Multiple comparisons: four agents across dozens of slices will produce
  several sub-0.05 patterns by chance alone; ranking is mechanism
  plausibility + effect size + robustness across slices, never p-value.

**No in-sample result justifies capital. The forward test is the evidence.**
