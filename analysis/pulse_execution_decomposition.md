# Track D — execution vs prediction: the PULSE loss decomposition

**2026-09-01 wave. In-sample, descriptive, hypothesis-generating. No PASS/FAIL.**
Artifact: `analysis/pulse_execution_decomposition.py`. Reproduce:

    .venv/bin/python analysis/pulse_execution_decomposition.py

Pins: `pulse_decisions_full_20260901T195202Z.csv` (19,333 rows / 34 games /
2026-08-18 → 08-31), `live_ticks_pulse_games_20260901T195202Z.csv.gz`,
`resolved_outcomes_20260901T195202Z.csv`. Mutation-tested before real data
(`--selftest`): the decomposition recovers known spread-only, prediction-only,
mixed and null worlds exactly, and the adverse-selection instrument reads back
an injected 2¢ drift and a 0¢ control.

## The assumption that bounds everything here

A PULSE fill is a **modelled** fill: a resting limit "fills" when a newer
observation's **mid crosses it** (`core/pulse/live.py`, `RestingOrder.fills_at`;
never the tick it was born from; ~1s cadence, two-sided ticks only). Verified: 0
rule violations in 3,751 filled rows, and every recorded `mid_at_fill` matches
the tape's contemporaneous mid exactly (3,751/3,751 within 0.5¢, worst diff
0.0000). How wrong it could be, measured not guessed: after modelled fills the
mid **reverts** 1.5–2.3¢ in our favour (the rule buys dips and sells peaks of
mid noise), while the venue-measured drift on **real** in-game resting orders is
**+4.70¢ against** the filler (quote study; feed-lag mechanism,
`docs/math/feed-lag.md`). The modelled and real execution worlds differ by
~5–6.5¢ per contract-leg, in opposite directions. Losses below are trustworthy;
profits are upper bounds.

## Headline: the decomposition (full-intent population, engine-rule accounting)

Identity per leg `pnl = mid-basis alpha − entry concession − exit concession −
fees`, verified to $0.000000 over 1,944 legs / 34 games:

| component | $ |
|---|---|
| prediction alpha, mid-basis, round trips (1,790) | **+135.29** |
| prediction alpha, mid-basis, rides (154) | **−26.30** |
| entry execution concession (≥0 by rule) | **−44.76** |
| exit execution concession (≥0 by rule) | **−40.58** |
| fees booked (maker-only shadow, θ_maker = 0, C7/V24) | 0.00 |
| **total realized shadow P&L** | **+23.65** |

**The premise of the question inverts on this tape.** Under the engine's own
accounting there is no loss to decompose: full-intent shadow P&L is **+$23.65**
(live-faithful, the registered population: **−$1.40**, n=60 legs / 13 games —
too small to cut). The decomposition instead says: in-sample mid-basis alpha is
**+$108.99 gross** (+3.47¢/ct [+2.27, +4.67], 34 games) and execution
concessions consume **$85.34 (78%)** of it.

**Re-scored under the wave standard's pessimistic rule** (measured in-game
concession 4.70¢ per filled contract-leg, 4,700 contract-legs): execution
charge **−$220.88**, total **−$111.90**. The honest floor: measured real-world
execution cost is ~2× the model's entire in-sample gross alpha. A per-leg toll
of 4.70¢ needs ~9.4¢ of true alpha per round trip to break even before fees —
this model shows 3.47¢ of mid-basis alpha per fill, an upper bound.

So: **prediction is not the measured problem on this tape; execution is — and
under measured concessions it is roughly twice the size of everything the model
knows.** Adverse selection and unavailable exits are *not* material components
(below). Fees are $0.00 by construction (resting maker limits only; the taker
counterfactual is $55.51 had every leg crossed, V9 θ=0.06).

## Component findings

**Adverse selection: absent — inverted, and mechanically so.** Post-fill drift
against the leg is negative at every horizon (entries: −1.78¢ [−2.20, −1.36] at
+10s → −2.34¢ [−3.11, −1.57] at +300s; exits similar; 33 games). The fill rule
triggers at local extremes, so reversion is partly the fill model looking at
itself. The +4.70¢ measured on real resting orders is the number deployment
would face.

**Unfilled entries: the selection filter runs backwards — direction confirmed.**
34.6% of entry intents (1,030/2,974 rows, 2,222/4,674 contracts, 33/34 games)
never filled under the rule. At their limit prices they would have settled to
**+10.88¢/ct [+7.61, +14.14]** vs **+4.76¢ [−1.46, +10.98]** for filled ones;
per-game paired difference **+11.07¢ [+2.92, +19.21]** (33 games). The intents
the rule filtered out were *better* than the ones it kept. Counterfactual
caveat: "unfilled" is rule-unfilled; a real venue fills resting bids from
aggressive sellers without a mid-cross. Direction informative, magnitude not.

State profile (track B's cells, for the one-mechanism-or-two question): unfilled
share is 41.6% in Q4+ vs 33.2% earlier, and 48.9% at minutes_left<5 vs 33.3% at
>10 — but flat across |margin| (35.9% at ≥10 vs 34.1% below). B's ride tail
concentrates in Q4 *and* blowouts. Reading: the late-game excess plausibly
shares B's venue-liquidity mechanism; the ~33% baseline everywhere (thick
early-game books, touch never crossed) and the missing blowout skew look like a
second, price-motion mechanism. One overlap cell, two mechanisms — candidate,
not conclusion.

**Unavailable exits: real, frequent, and cheap on this tape.** 84/136 analysed
rides (24 games) had no two-sided live book in their market's final 5:00
(wallclock proxy; windows end at the last live tick because FT rows carry NULL
books). That matches the 59% bookless-endgame yield measured independently. But
the counterfactual cost of riding vs exiting at the last available two-sided mid
is **+$2.09 total (+$1.73 on the bookless subset)** — by the time books die, mid
≈ settlement. The hazard is the *tail* (no exit at any price when a game turns),
not the average. Bookless rides' P&L −$20.07 vs booked rides −$8.48; no
safe-harbour market type (spreads 27/46 bookless, totals 53/85, winners 4/5).

## Candidates (falsifiable, with confound + forward test)

1. *Unfilled intents outperform filled ones by ~11¢/ct at settle, per-game CI
   excluding zero.* Confound: intent-time game state drives both fillability
   and outcome; and the counterfactual fill may be unobtainable under any
   policy when the touch never trades. Forward test: paper "cross-at-touch"
   arm beside the resting arm, same signals, taker fee charged, scored on
   forward games only.
2. *Mid-basis alpha +3.47¢/ct exists but is below the measured 9.4¢ round-trip
   execution hurdle.* Confound: alpha is measured on rule-selected fills
   (contrarian timing built in). Forward test: the registered live floors,
   plus a CLV-style mid-basis score on ALL intents, filled or not.
3. *Late-game unfilled excess shares B's ride-tail mechanism (venue liquidity),
   early-game baseline does not.* Forward test: joint cut with B's state cells
   on next slate's tape; if one mechanism, the two effects co-move game by game.

## Negatives (mechanism named)

1. **Execution, not prediction, is the binding loss** — measured concession
   (4.70¢/leg, feed-lag pick-off) ≈ 2× total in-sample alpha. Remedy space is
   order placement/fill policy, not model improvement — but no placement can
   beat a toll larger than the alpha; the alpha itself must grow.
2. **Winner markets carry nothing:** 111 legs / 26 games, alpha +$0.76, exec
   −$1.05, P&L −$0.30 — and winner books die in decided endgames anyway.
3. **"Unavailable exits explain the loss" is dead on this tape:** −$2 of
   counterfactual cost against an $85 concession line. Bookless endgames
   remain a risk-sizing constraint, not a P&L driver here.

## Boring list (checked, flat — don't re-mine)

- `mid_at_fill` vs tape: exact agreement, 3,751/3,751.
- Fees: $0 booked; hypothetical all-taker load $55.51, max band $15.25
  (35–65¢); nowhere decisive relative to the concession line.
- Entry limits join the touch in 2,974/2,974 intents (yes→bid, no→ask).
- Exit contracts always equal entry contracts; identity residual $0.000000.
- Price bands: alpha and concessions scale together; no band flips sign
  (35–65¢ carries half the legs, +$9.03 P&L).
- Version cut (v1 +$28.38 / v3 −$6.76 / v4 +$2.03) — different eras and
  games, not comparable; noted for A/C, not ranked here.

## Reconciliation and anomalies for A's ledger

- Full-intent total **+$23.65** (1,790 trips / 154 rides) is the number to
  reconcile with A. **B quotes A at 137 rides; I count 154; the difference is
  exactly the 17 filled exit rows with NULL `entry_id`** (no lineage; both
  live_report's LATERAL join and this script exclude them — a ledger matching
  them by market+time would convert 17 of my rides into trips).
- 18 rides have no exit row at all (engine never rested an exit — restart?).
- 11 entries and 7 exits neither filled nor withdrawn at export time.

## Addendum 2026-09-01 (post cross-check with track B)

- **Orphan-exit reconciliation resolved.** A's ledger re-links the 17 filled
  exits with NULL `entry_id` (`lineage_source='reconstructed'`; rule stated in
  A's report, `analysis/roundtrip_ledger_report.md`); `live_report.py`'s
  LATERAL join drops them; this script follows the drop policy, hence 154
  rides vs A's 137. **The policy choice is load-bearing:** B measures the
  live-faithful subset at −10.0¢/$ under drop-them vs +1.2¢/$ under A's
  re-linking. Any registration touching the live-faithful series must pin
  which policy it scores under.
- **Ride economics corroborated on A's substrate, sharper than my $2.09:**
  exiting every ride at A's `close_yes_value` (last two-sided quote) recovers
  **$0.00** — losing rides are already worthless while the book is still
  alive. Refined mechanism split (B's addendum, branch quant-b/pulse-loss-map):
  booklessness predicts WHERE rides happen; the dollars are adverse selection
  against the *static exit policy* (exit rests at entry+5¢ until the EV stop
  fires). Consistent with this track's negative #3.
- **One-mechanism-two-symptoms verdict, joint:** holds only in the late-game
  cell; my flat |margin| cut against B's 10.8% ride spike at |margin|≥10 is
  the discriminating fact. To be consolidated as one finding with two
  measurements (B: P&L; D: state profile) when the manager calls for it.

## Standing statements

Multiple comparisons: dozens of intervals across types, bands, versions and
horizons; several nominally significant cells are expected by chance. Ranking
here is mechanism plausibility + effect size + robustness, never p-value.

**No in-sample result justifies capital. The forward test is the evidence.**
