# ESPN win probability vs the venue's implied probability — conventions

**Registered 2026-09-06, when the only available cohort is G=1.** The point of
writing it now is that the conventions are still choosable on principle rather
than on which choice produces an edge. Saturday supplies the volume.

## The question

We never trade against ESPN — ESPN is a free public model. **We trade against the
venue.** If the venue's implied probability is worse than ESPN's in-game win
probability by more than the execution bar τ, the strategy needs no model of
ours: take the public number, trade it against the venue when they disagree past
the bar. B's own CFB model does not beat ESPN (−0.01119 [−0.043, +0.021] pooled,
0 of 5 pre-declared subsets clearing zero), so this is the remaining route.

## ★ Conventions — a probability quoted without its frame is two measurements

1. **YES-frame.** On `aec-` CFB winner markets, **YES = the AWAY team**, verified
   against settled prices (11 of 12 settled markets agreed; slug order is
   away-home, confirmed against `cfb_game_map`'s home/away names). **Re-verify on
   each new tape and refuse if it falls below 11/12** — this is a sign convention
   and getting it backwards inverts every result.
2. **Venue implied probability of the HOME team = 1 − mid**, where
   `mid = (best_bid + best_ask)/2`. Stated because "the venue's probability" is
   ambiguous between the two sides and between mid and touch.
3. **Mid, not touch, for the FORECAST comparison. Touch for any P&L.** Comparing
   forecasters asks who is closer to the truth, and the mid is the venue's
   estimate; a P&L asks what we could transact, and nobody transacts at the mid.
   **These are different questions and must not share a column.**
4. **Population: rows where the venue market is `is_live`**, joined to ESPN state
   within a **30s** tolerance (60s reported as sensitivity, never as primary).
5. **Games observed from kickoff only** — first ESPN state row must precede
   kickoff. A recorder starting mid-slate delivers fourth quarters, where both
   forecasters are nearly right and the comparison is compressed toward zero. That
   artefact produced this project's 19-game selected cohort on 2026-09-05.
6. **Metrics: Brier and log-loss, both reported.** Two routes, because a single
   metric agreeing with itself is not corroboration.
7. **Clustering by game, and G stated on every figure.** If G = 1, say G = 1 and
   **do not cluster** — a clustered interval on one cluster is not a number.

## ★ Amendment 1 (2026-09-06) — the alignment axis is two questions, not one

A lead-lag on tonight's single game gave corr +0.465 at k=−1 (**venue leads**)
against +0.157 at k=+1 (ESPN leads). **63 increments from ONE game is a design
input, not a result, and must not be quoted as one.** But it is confounded:
ESPN's WP is **play-triggered and polled** (74 updates in 64 min) while the venue
tape is **continuous** (2,425 observations). A one-minute lag is exactly what a
slow *publication* looks like even if the *model* were instantaneous.

**So wall-clock and game-time alignment answer different questions, and the
registration needs both:**

| alignment | question it answers | what it decides |
|---|---|---|
| **game time** — join WP → plays on `play_id`, take `plays.wall_clock` as the event instant, sample the venue there | Does ESPN's model contain information the market lacks? | whether the architecture is worth building at all |
| **publication wall-clock** — ESPN row's own arrival time | Can we trade ESPN's published feed as-is? | whether we can simply consume it |

**Both are primary. Neither substitutes for the other.** A positive on game time
with a negative on publication time means the information is real but arrives too
late to take — which argues for computing the features ourselves rather than
consuming ESPN, and is a different build.

**Use `plays.wall_clock`, never `plays.first_seen_at`** — the recorder backfills
(median lag 1 min, max 159 min), so `first_seen_at` misdates every backfilled
play. Game-time alignment removes our **ingestion** asymmetry; it deliberately
preserves any real **computation** lag, because that lag is economically real.

### ★ Amendment 1a (2026-09-06) — `wall_clock` is the right clock and is NOT monotone

Amendment 1 was right about *which* clock and insufficient without a guard.
**Ordering plays by `wall_clock` puts period-1 rows AFTER period-4 rows.**
Verified independently on `espn_cfb_live_plays_20260906T215629Z`: **24 plays
across 8 of 50 games** go backward in period (ce measured 27 across 9 of 53 on a
later export). **One of the out-of-order rows is a scoring play**, so filtering to
scoring plays is not protection either.

**So a monotonicity guard is required, not optional.** A frame or lead-lag check
that orders all plays by `wall_clock` hits this in ~1 game in 6.

**★ SCOPE — the guard belongs on PLAYS and MUST NOT be applied to STATE.** Both
substrates show backward score steps and the correct response is opposite:
```
STATE  18,775 rows / 50 games   22 backward steps / 18 games   ESPN UN-POSTING — real retractions
PLAYS   8,633 rows / 50 games   38 backward steps / 17 games   wall_clock sort artifact
```
On plays the backward step is an artifact of our sort and removing it is correct.
**On state it is a genuine ESPN retraction, and guarding would silently keep a
withdrawn score and hide the retraction that flips one winner in 29.** Same
symptom, opposite fix.

**★ VARIABLE — guard on the UNION of period AND total score, not either alone.**
Measured on the same export:
```
rows below running-max PERIOD only        5
rows below running-max TOTAL SCORE only 205
rows below both                          35
  period guard alone catches             40
  score  guard alone catches            240
  UNION                                 245
```
**Neither variable catches the other's misses.** A period-only guard misses a
within-period reversal; a score-only guard misses an out-of-order row that did
not change the score. **Drop any row falling below the running max of period OR
of total score.**

### ★ Amendment 1b — never reconstruct the score from the play flags

Two substrate facts, both verified here:

- **`score_value` is NULL on 100% of 8,634 rows.** It cannot reconstruct anything.
- **The extra point is not flagged as a scoring play.** A touchdown carries
  `scoring_play = 't'` at 9-3, and the PAT lands on the following **`Kickoff`**
  row at 10-3 with `scoring_play = 'f'`. **Summing `scoring_play` rows undercounts
  by one point per touchdown.**

**Read the score from `home_score`/`away_score` on the play row. Never derive it
from `scoring_play` or `score_value`.**

**And never DETECT the event with it either.** Measured on the same export:
**726 rows show a score change; only 442 (60.9%) carry `scoring_play = 't'`.
284 score changes — 39.1% — are unflagged, and 56 of them are worth six points
or more.** Whole touchdowns are invisible to the flag. **Detect scoring events by
DIFF on `home_score`/`away_score`, in game order, after the 1a monotonicity
guard.**

### ★ Amendment 1c (2026-09-06) — POST-HOC. The anchor is a free parameter and must be swept

**★ THIS RULE IS POST-HOC AND MUST BE LABELLED AS SUCH WHEREVER THE AWAY-ARM
COUNT APPEARS.** It was written *after* seeing which way the unstable event
pointed, and its first application **removes a contrary data point**: without 1c
the away arm is 1 correct + 1 wrong; with it, 1 correct. **A rule whose first
effect is to improve its own author's instrument does not get the standing of a
pre-registration**, however sound the argument. (Same standard d5 applied to
their own bracket-filter amendment.)

**The even-handedness test, and it is cheap: apply 1c to the HOME arm too.** If
all four home events are anchor-stable, the rule only ever removed a genuinely
unstable event and is neutral. **If any home event also flips, the home arm
shrinks as well — and the rule is even-handed rather than convenient.** A rule
that only ever cuts in the direction its author needs is the thing to distrust.
**Run it on both arms or quote neither.**

The monotonic-response check compares the venue price "before" an event to
"after". **"Before" is not defined by the event time**, because the venue leads
ESPN by roughly a minute, so a price sampled at the ESPN timestamp is already
post-move. Anchoring earlier is required — and *how much* earlier changes the
verdict.

Demonstrated twice. My own first run went **0/3 → 2/3** as the window widened
from 0s to 60s. And a single field-goal event read **0.8525 → 0.8525 (no
evidence)** under one anchor and **0.8225 → 0.8525 (wrong direction)** under
another, **on a 39-second difference**.

**So: sweep the anchor over at least {30, 60, 120, 180}s and report the verdict
at each. An event counts as evidence ONLY if its direction is stable across the
sweep.** An event whose sign or verdict flips under anchor choice is **NOT
EVIDENCE, in either direction** — it does not confirm the frame and it does not
refute it.

By that rule, on 2026-09-06: the away touchdown (−4.5pp on 7 points) is stable
and counts; the away field goal is anchor-sensitive and does not. **Without this
rule the check has an unregistered degree of freedom that decides its answer.**

**Frame check is promoted to primary: monotonic response to scoring events**,
which is available DURING the game. Settled-price agreement drops to fallback —
a check that can only run retrospectively cannot stop a wrong-signed number
being published tonight.

## ★ Amendment 2 (2026-09-06) — tau is a FUNCTION of price, not a scalar

My 1.75pp was wrong and Quant A caught it: it paired a half-spread measured at
mid ~0.04 with the fee term evaluated at p = 0.5. The venue fee is
`0.06 * p(1-p)`, which is **0.22c at p=0.04 and 1.50c at p=0.5** — a 7x range
across the price axis. Corrected tau at tonight's actual trading price is
**0.47pp**, not 1.75pp.

**So the decision rule compares each observation's edge against tau AT THAT
OBSERVATION'S PRICE.** A scalar tau is a fourth mixture on top of the three
already caught today (wrong column, wrong weighting, wrong axis) — this one on
the price axis.

**And the number this test actually needs does not exist yet.** The winner
market on 2026-09-06 traded entirely at extremes: mid p5-p95 = 0.022-0.077,
**ZERO observations in 0.35-0.65** (verified independently). Game 16486 was a
blowout. **The winner-market half-spread at p ~ 0.5 is UNMEASURED.**

The strategic consequence, which is A's and worth keeping: **in blowouts tau is
tiny but the outcome is near-certain so there is little to bet; in close games
there is something to bet and the spread is unmeasured and likely wider.**
Saturday with close games is what measures the regime this test would trade in.

**I flagged the 1.75pp as favouring my own route and asked for extra scrutiny;
A applied it and the number did not survive.** Record that the correction came
from the person it argued against, not from its author.

## Decision rule

Let Δ = Brier(ESPN) − Brier(venue), game-clustered, on the disagreement subset
(|ESPN − venue| > 5¢).

- **Δ < 0 with the interval excluding zero, and |Δ| exceeding τ's implied edge**
  → the first live edge this programme has found. State it with its interval and
  its G before it travels anywhere.
- **Interval spans zero** → no finding, whatever the sign of the point estimate.
- **G < 10** → REHEARSAL. Report the pipeline worked and the direction observed;
  **do not call it a result.**

**τ is A's measurement on the same tape and is not mine to set.** Beating the mid
is necessary and not sufficient: execution happens at bid or ask, so a forecaster
can beat the venue's mid and still lose to the spread.

## Prior result, and why it is not the answer

Run 2026-09-05 tape, 17 games, ESPN better on all four cuts (Brier −0.0003 to
−0.0156, log-loss agreeing), **every interval spanning zero**, on a
fourth-quarter cohort. Direction only. This registration exists so the rerun on
an unselected cohort is not read through the same population.
