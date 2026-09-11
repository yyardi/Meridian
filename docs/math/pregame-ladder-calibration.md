# Pregame ladder calibration: is any rung of the venue's football ladders soft?

Written 2026-09-11 18:02Z (prod clock 2026-09-11T18:02Z). Script `cfb/run_ladder_calibration.py`,
output `ladder_calibration_2026-09-11.out`. **Exploratory: ~40 looks, nothing
pre-registered.** Its job is to produce hypotheses for the held-out weekend, not
results.

**The test.** Every full-game spread rung, total rung, team total and winner
market on the 77 settled, mapped CFB/NFL games (60 CFB + 2 NFL carried a quote
within six hours of kickoff), priced at the last quote before the first ESPN
play, settled from ESPN finals under the venue's frames. Per market type and
pregame-mid bucket: the calibration gap E[settle − mid], and the taker P&L of
buying YES at the ask and of buying NO at 1−bid, each net of the 0.06·p(1−p)
fee, game-clustered. Both sides printed for every bucket; no side selected on
the outcome.

**Frames verified against the venue, not assumed.** 48 markets sampled across
the four types and checked against the venue's settlement endpoint (from the
prod API container; it now requires API headers): **39 agree, 0 disagree**, 9
returned 404 (the venue has no settlement record for some 09-05 CFB markets).

**Result: no bucket is flagged.** 4,258 markets, no (type, bucket) where either
taker side is positive with an interval excluding zero at G ≥ 25. The venue's
pregame ladders are calibrated to within fee plus half-spread everywhere we
have power.

| population | n | G | gap E[y−mid] | buy YES @ask net | buy NO @1−bid net |
|---|---|---|---|---|---|
| spread, all rungs >14 pts from centre | 1,542 | 61 | −1.68¢ [−5.03, +1.67] | −3.53¢ [−6.97, −0.10] | −0.04¢ [−3.35, +3.27] |
| spread, mid 0.0–0.1 | 1,227 | 60 | −0.85¢ [−4.04, +2.35] | −2.34¢ [−5.56, +0.87] | −0.52¢ [−3.70, +2.66] |
| total, mid 0.0–0.1 | 73 | 46 | −3.40¢ [−8.08, +1.28] | −5.42¢ [−10.07, −0.77] | +1.54¢ [−3.20, +6.29] |
| **CFB spread, mid 0.2–0.3** | 154 | 56 | **−11.00¢ [−18.92, −3.09]** | −14.29¢ [−22.34, −6.24] | **+7.85¢ [−0.12, +15.81]** |

**The one thing worth writing down before Saturday.** CFB spread rungs priced
20–30¢ settled YES 11¢ less often than priced; buying NO at 1−bid nets +7.85¢
with an interval whose lower bound is −0.12¢, G = 56. It is the longshot side
of the favourite–longshot bias, in the direction the literature predicts, and
it is one of forty looks, so its 95% interval is worth about nothing as
evidence. It is registered here as the SINGLE hypothesis for the held-out
weekend: **on Saturday 2026-09-12's CFB closes, buy NO at 1−bid on every
full-game spread rung whose pregame mid is in [0.20, 0.30); read the taker
P&L net of fee, game-clustered, G ≥ 25; positive and excluding zero passes.**
Nothing else from this scan is read on the weekend. The adjacent buckets
(0.1–0.2: +1.71¢ spans zero; 0.3–0.4: +0.33¢ spans zero) are printed so the
reader can see the shape is not monotone, which is the argument against it.

**What the winner rows say.** 61 winner markets, 43 with the away team priced
under 10¢ — the venue lists CFB winner markets mostly on mismatches
(FCS-at-FBS), and those longshots settled about as priced (+1.23¢ [−5.02, +7.48]).

**Kickoff anchor.** ESPN's first play vs the venue's `game_start_time`: median
3 minutes, p90 30, max 1,169 (one game listed a day off). The first play is
the anchor; the venue field is not.
