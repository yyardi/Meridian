# Cricket in play — the favourite's dip, registered before the tape exists

2026-09-22. The operator watched Japan v India (Asian Games, T20, rain-cut to
five overs), bought India when its price fell, and asked whether "buy the dip"
in cricket is a strategy. This registers how that will be tested. It sits
beside docs/math/cricket-preregistration.md (2026-09-14), which registered the
PREGAME half of the operator's cricket claim; this is the IN-PLAY half.

## 1. What was observed (motivating episode, not evidence)

`aec-t20icr-japan-india-2026-09-22`, YES = Japan (home; the venue's YES is the
home side on cricket — [core/leagues.py](../../core/leagues.py)). The venue's
pregame sweeps, 15 minutes apart:

| UTC | Japan bid/ask | ESPN state (15 s recorder) |
|---|---|---|
| 09-21 16:53 | 0.06/0.07 | pregame, a day out |
| 09-21 17:08–17:38 | 0.11/0.21 → **0.27/0.30** | pregame — nothing on ESPN; back to 0.12/0.13 by 17:53 |
| 09-22 04:12 | 0.02/0.04 | live flag on |
| 09-22 05:12 | 0.26/0.28 | (rain; a five-over match) |
| 09-22 05:42 | 0.31/0.33 | |
| 09-22 06:42–07:13 | 0.02/0.03 → 0.01/0.02 | India batting, 22/3 (4 ov) at 07:30 |
| 09-22 07:43 | **0.40/0.43** | India 32/4 (5 ov); Japan 1/0 chasing 33 |
| 09-22 07:55 (live book) | 0.10 × 101.8 | Japan 9/2 (2.1/5 ov), 24 needed off 17 |

Two things in that table are facts, and neither is "the market was wrong":

- **The venue's screen does not show the cricket state.** Its `event_score`
  field read `0-0` through India's innings and `0-32` when India were 32/4 in a
  five-over match: no wickets, no overs, no target, no format. A retail reader
  of the venue's page cannot tell 32/4 (5 ov) from 32/0 (5 ov) or from a
  20-over score. ESPN's summary carries all of it every 15 s and we record it
  (`espn_cricket_events`). That is a real informational asymmetry between
  someone who reads ESPN and someone who reads the venue, and it is the
  operator's claim made precise.
- **The pregame spike on 09-21 17:08Z is the shape the 09-14 registration
  named**: a 25-cent move a day before the match with nothing on ESPN, reverted
  within 45 minutes. It goes to that read, not this one.

What is NOT a fact: that 40c for Japan at 1/0 chasing 33 in five overs was too
high. One correct call at a price is `p` against a coin (the 09-14 document,
§1). The match was live when this was written, and its result changes nothing
below.

## 2. The claim, made falsifiable

**H1 (the operator):** during a cricket match, when the pre-toss favourite's
price falls sharply on a bad start, the venue's price over-reacts: the
favourite is under-priced at the dip, because the venue's own display
cannot express the state and its retail reads the price instead of the game.

**H0:** the venue's in-play price is calibrated; a favourite at `p` after a
dip wins `p` of the time, net of the fee the dip is not a trade.

This is the same shape as three in-play reversion reads that found nothing on
US sports (memory: reversion dead; the unfilled arm flatters). Cricket is
tested anyway because the display defect is specific to it and measured.

## 3. What has to exist first — the tape

The cricket recorder sweeps pregame boards every 15 minutes; a T20 innings is
~90 minutes and a five-over one is 20. Six samples per innings cannot place a
dip. So, before any price is read:

- the daily scheduler puts every cricket winner market on the **stream
  recorder** (update resolution, the venue's own pushes) for the match's
  window — `t20icr`, `t20iwcr`, `cplcr` at 240 minutes, `odicr` at 540;
  `county` is multi-day and settles 0.5 on a draw and is **excluded and
  counted**;
- the ESPN cricket recorder (already running, 15 s in play) is the state:
  innings, overs, wickets, runs, target, toss.

The join is by wall clock: each price update gets the last ESPN state at or
before it (ESPN lags the ball by a poll; a price that moves before the state
does is charged to the earlier state, which biases AGAINST H1, and is stated).

## 4. The primary read: calibration by state, not a trade

For every match with a stream tape and an ESPN timeline, at every price update:
`(innings, overs bucket, wickets, runs vs target, pre-toss favourite price,
price now)`. **Primary:** Brier and log loss of the venue's in-play price,
by bucket of the favourite's drawdown from its pre-toss price
(`0–10c, 10–25c, 25c+`) and by innings. If the 25c+ bucket is as well
calibrated as the rest, H1 is false and no decision rule can rescue it.

Estimator: per-match clusters (a match is one outcome); intervals from the
game-clustered sandwich; the population and count named on every number.

## 5. The decision rule, registered so it cannot drift

If and only if §4 shows miscalibration in the dip bucket: BUY the pre-toss
favourite at the displayed ask when its price is ≥ 25c below its last
pre-toss quote, in innings 1 or 2, hold to settlement. One ticket per match.
Scored at the ask actually displayed on the stream, net of the row's
`fee_coefficient` (0.0695 today; core/fees.py — the venue moved it on
2026-09-17 and a read across that instant charges each row its own).

Reported beside it, never instead: the fade (sell the underdog's spike),
which is the same rows with the opposite sign minus spread and both fees.

## 6. Power, stated before the count

The 09-14 document's arithmetic holds: a 60 % hit rate at even money needs
154 calls for 80 % power. Dips of 25c+ on a favourite are a minority of
matches; at ~10–15 cricket events a day across the five competitions, the
first honest read is weeks away, not days, and it will say UNDERPOWERED on
its face until then. Nothing here is a reason to place anything.

## 7. What would kill it

- The 25c+ bucket calibrated (H0) — the display defect exists but the price
  does not carry it.
- Displayed asks at the dip that print through (phantom, as on the ladder):
  a picture, not a fill; the phantom check runs on cricket tapes too.
- A dip that is mostly rain: a Duckworth–Lewis reset moves the true
  probability, and ESPN's `status_detail` and overs cap identify it.
  Rain-affected matches are reported as their own row, never pooled.
