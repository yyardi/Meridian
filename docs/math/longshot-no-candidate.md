# The longshot-NO candidate: the one bet the tape has produced, and the plan to prove or kill it in six days

Written 2026-09-12 (Saturday night, after 118 CFB games). Status: **hypothesis
with one registered read left**, not a result. This document is the plan, the
researcher's brief, and the pre-registration of everything that happens next.

## 1. The bet

Before kickoff, on every CFB full-game spread rung whose YES mid sits in
[0.20, 0.30), buy NO at 1 − bid (a limit order at the touch, never through it),
hold to settlement. Net of the 0.06·p(1−p) taker fee. That is the entire rule.
Nothing in-game, no model, no discretion.

## 2. Evidence so far (game-clustered, estimator = fills-weighted sandwich)

| population | buy-NO net per $1 bet | 95% interval | markets | G | settle − mid |
|---|---|---|---|---|---|
| games through 09-06 (where it was found) | +6.88¢ | [−1.27, +15.03] | 164 | 60 | −9.94¢ [−18.07, −1.82] |
| ~~held-out Saturday 09-12 (partial slate, 34 games final)~~ | ~~+4.56¢~~ | ~~[−13.80, +22.92]~~ | ~~47~~ | ~~16~~ | ~~−7.22¢~~ |
| **held-out Saturday 09-12, FULL slate (shadow lister, T−60..T−5 quote)** | **+0.84¢** | [−12.55, +14.24] | 116 | 37 | NO won 78.4% |
| 09-05 slate, same lister | +10.16¢ | [−1.26, +21.58] | 88 | 31 | NO won 87.5% |
| pooled | +6.36¢ | [−1.12, +13.85] | 211 | 76 | −9.34¢ [−16.76, −1.92] |

Same sign out of sample; interval still spans zero because each bet is +24¢
or −75¢ and sixteen games is sixteen games. The calibration gap (rungs settle
YES 9¢ less often than priced) excludes zero on the pool.

## 3. What the mirror says about the mechanism (pooled 76 games)

If the venue's ladder tails were simply too wide, the other tail would be
overpriced too. It is not:

| bucket | the fade | net | interval | markets / G |
|---|---|---|---|---|
| 0.10–0.20 | buy NO | +2.30¢ | [−4.16, +8.76] | 347 / 76 |
| **0.20–0.30** | **buy NO** | **+6.36¢** | [−1.12, +13.85] | 211 / 76 |
| 0.30–0.40 | buy NO | +0.09¢ | [−11.51, +11.69] | 182 / 74 |
| 0.60–0.70 | buy YES | −9.76¢ | [−24.82, +5.30] | 110 / 49 |
| 0.70–0.80 | buy YES | −2.27¢ | [−15.61, +11.08] | 101 / 45 |
| 0.80–0.90 | buy YES | −9.58¢ | [−26.14, +6.97] | 109 / 36 |

Fading the expensive side loses. The effect is one-sided: **cheap YES is
overpriced; expensive YES is not underpriced.** That is the favourite–longshot
bias in its classic form (retail overpays for the cheap ticket), not a
symmetric pricing-engine error. Within the bucket, the deepest rungs carry
most of it: rungs > 14 points from the centre +11.89¢ [+5.47, +18.31] on 16
markets / 12 games; rungs 7–14 points +5.58¢ [−2.52, +13.68] on 192 / 75.
Twelve games is not evidence; it is where to look.

> **Status 2026-09-13 evening: every "excludes zero" positive this candidate
> family produced has been traced to the venue's away-referenced listing or to
> a calendar regime (see §3b and `wnba-kalshi-cross-venue_2026-09-13.md`).
> The registered 09-19 money read stands because it was registered, and the
> centre-rung home-shift read beside it is the one that can actually tell a
> mechanism from a draw.**

## 3b. Decomposition, 2026-09-13 (full tables: `longshot-no-decomposition_2026-09-13.md`)

**The mechanism in §3 is probably wrong, and this note sits above the read it
affects.** Splitting the bucket every way the brief asked:

- **It is not a cheap-rung effect.** The fee-free gap (mid − realised) on the
  away side is +2.0, +5.0, +9.3, +3.0, +9.6, +7.1, −0.6, +7.4, +9.3 pp across
  YES-mid buckets 0.05 → 0.50: as large at the centre of the ladder as at the
  25¢ rung, and not monotone in cheapness. The [0.20, 0.30) bucket is where
  the *interval* is tightest (smallest p(1−p)), not where the effect lives.
- **Away and underdog cannot be separated on this tape.** 75 of 83 games are
  away-underdog (median centre line +23: weeks 1–2 cupcakes), so "cheap YES =
  away covers" and "cheap YES = underdog covers" are one variable. The
  away-favourite cell has 8 games.
- **Distance and time-to-kickoff carry nothing:** 190/211 rows sit 8–14 points
  from the centre, 204/211 were quoted inside the last hour.
- **Totals and team totals show nothing like it** (−2.96¢ and −10.16¢ for the
  same bet; the cheap side of team totals paid out MORE than priced).
- **Shape:** a whole-ladder shift of about 4 points toward the home team over
  two weekends reproduces the gaps. Per game, the away team covered the centre
  line 33/83 = 0.398 [0.292, 0.503]. Either the venue under-rated home
  favourites in weeks 1–2, or it is a 1.9σ draw; 83 games cannot say which.
- 40% of spread rungs (1,343 of 3,346) have a YES mid under 5¢: the ladder is
  quoted around zero, so it is dead on the home-friendly side and truncated on
  the away-friendly side for big favourites. Every mirror comparison on this
  venue is shaped by that.

**Consequence for the money read:** the §4 read stands exactly as registered
(the money metric under its pre-set definition). Added BESIDE it, chosen after
a look and labelled so: the **centre-rung away-cover rate, split by the sign
of the centre line**. No fee, spread, price level or truncation confound; quoted
in every game; a home-shift predicts under 50%, a longshot story predicts 50%.
About 200 games (five weekends) resolve 10 points. If week 3's home-favourite
share falls from 90%, the sign split starts to say which story it is.

## 3c. The shadow lister, and what the full Saturday said (2026-09-13)

`cfb/run_longshot_shadow.py` (replay and live modes; places nothing) reproduces
the bet as a live process would see it: the last quote in [T−60, T−5] before
ESPN's first play, depth at the bid from `book_levels`, ESPN settlement.
On the FULL 09-12 slate the bet is **+0.84¢ [−12.55, +14.24] on 116 rungs /
37 games** — the +4.56¢ in §2 was the 16 games that had finished when it was
computed, and it is struck above. The 09-05 slate under the same process is
+10.16¢ [−1.26, +21.58] on 88 / 31. Depth is not the constraint (median 1,000–
2,400 contracts at the bid, $800–1,800 per rung at NO ≈ 0.76). Two things a
live process must handle, measured: the venue's `game_start_time` disagrees
with itself inside a game on some slugs, and ESPN's first play differed from
the venue start by more than an hour on 7 of 95 games — replay follows the
play, live can only follow the venue clock, so the live rung set will differ
from the backtest's on delayed games. Wide rungs (bid 0.01 / ask 0.51) land in
the bucket by mid; a spread cap is needed before anything goes live.

## 4. The registered read (Saturday 2026-09-19; nothing else is added)

1. **Held-out:** the rule in §1 on 09-19's games alone. Positive and excluding
   zero passes on its own.
2. **Pooled:** 09-05 → 09-19, G ≥ 25 games carrying a rung in the bucket.
   Positive and excluding zero passes.
3. Beside it, never instead: the 0.10–0.20 and 0.30–0.40 neighbours, and the
   > 14-point sub-bucket, so the shape is visible. They do not decide.

Pass on either 1 or 2 → the bounded live week in §6. Fail on both → the
candidate joins the maker in the graveyard and this document says so at the top.

## 5. Between now and then: the operational path, built in shadow

A passed read is worthless if the bet cannot be placed. This week:

- **Shadow lister (`cfb/run_longshot_shadow.py`, to build by Wednesday):**
  from T−60 to T−5 minutes before each Saturday kickoff, list every rung in
  the bucket with a live book, the NO price (1 − bid), the size resting at the
  bid, and log the intended order. Score it against settlement afterwards.
  This proves timing, liquidity, and that the rungs the backtest counted are
  the rungs a live process sees.
- **Depth is the binding constraint.** Median touch depth on this venue is
  $177. Sizing starts inside that.
- **Order type is already fixed:** `core/executor.py` can only build limit
  orders (buy NO = `ORDER_INTENT_BUY_SHORT` at 1 − bid). Arming it is the
  operator's script with the order token; nothing here places anything.

## 6. If it passes: the bounded live week (2026-09-26), pre-registered now

- **Size:** $25 per rung, every qualifying rung, no selection. ~3 rungs per
  game, ~50 games → ~$3,750 at risk in a week, expected +$225 at +6¢.
- **Weekly loss cap:** −$600 (roughly two standard deviations of a week at
  this size). Hit it, stop for the week.
- **Programme kill:** two consecutive losing weeks, OR realised net per bet
  below the backtest's lower interval bound after 100 live bets. Either one
  ends it; no "one more week".
- **No per-position stop.** On a binary contract a −20% mark is the underdog
  scoring, and selling into that is exactly the adverse trade this venue's
  in-game tape says loses (Polymarket CONTINUES after moves). The bet is held
  to settlement; risk is controlled by size and the two caps above.
- **Scale rule:** size doubles only after a week that finishes positive AND
  inside the backtest interval. Never on a good day.

## 7. Questions for the researcher (answers change what we do)

1. **Mechanism.** Cheap YES overpriced, expensive YES not underpriced. Which
   side is retail buying? Is the YES side (the slug's first team, always
   the away team) the tell, i.e. is this an away-team effect wearing a
   longshot costume? Test: split the bucket by whether the cheap YES is the
   favourite failing to cover or the underdog covering.
2. **Does it survive the venue's own devig?** Ladders are quoted both sides;
   the bucket is defined on YES mid. Re-define on NO mid (0.70–0.80) and
   confirm it is the same set of markets, not a spread artefact.
3. **Depth and impact.** How much NO is resting at 1 − bid on these rungs at
   T−30 min, and does hitting it move the ladder? The $177 median touch is
   venue-wide; these are far rungs and may be thinner.
4. **Kalshi.** The same rungs exist there with a 7% fee. Kalshi's early-week
   tape started 09-12 (72h window) and DraftKings' line path is now recorded
   hourly; the first Kalshi-vs-DK lag read is 09-19 too. If the same
   longshot gap exists on Kalshi pregame, that is a second venue for the same
   bet and a cross-check that it is a crowd effect, not a venue-engine one.
5. **Why 20–30¢ and not 10–20¢?** +2.30¢ [−4.16, +8.76] there. If the
   mechanism is longshot love it should be monotone in cheapness; if it is
   not, the bucket boundary is doing work and the read on 09-19 should be
   treated as one look, not two.
