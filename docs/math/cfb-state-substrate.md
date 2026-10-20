# The CFB game-state substrate: what it can and cannot answer

**DESCRIPTIVE. NO GATE, NO VERDICT REGISTERED.** Computed 2026-09-06 against
pinned exports; nothing here may feed a registered measurement.

Two things were asked, in this order: measure the CFB feed lag, then report
whether ESPN's win probability is calibrated on our sample. **The first is not
computable on this substrate and the second cannot be answered at this sample
composition.** Both are findings about the data rather than obstacles to route
around, and the evidence for each is below.

**Sources (pinned):** `espn_cfb_game_state_20260906T174104Z.csv.gz` (18,775
rows, 50 games, 2026-09-05/06) · `cfb_game_map_20260906T174104Z.csv.gz` (55).

---

## The clock transform, hand-verified

`display_clock` is a string and `period` is separate, so seconds-remaining has
to be constructed. Verified against the data rather than assumed:

| period | rows (state=`in`) | `clock_s` range |
|---|---:|---|
| 1–4 | 18,521 | 0 – 900 |
| 5–7 (OT) | 68 | 0 – 0 |

Quarters run 0–900s, confirming 15-minute quarters and **3600s of regulation**.

```
reg_left = (4 − period) × 900 + clock_s      for period ≤ 4
reg_left = 0                                  for period ≥ 5
```

Hand checks: `P1 14:56 → 3596`, `P2 5:04 → 2104`, `P4 15:00 → 900`, `P5 0:00 →
0`. Range across all rows is exactly [0, 3600].

**The overtime convention is the trap and it is handled by not extrapolating.**
College overtime is untimed — possession-based, no clock — and every OT row in
this export carries `display_clock = '0:00'`. Treating OT as "period 5, so
−900s remaining" would manufacture negative time; OT is pinned to 0 and flagged
instead.

**Post-game rows carry no clock at all** (`period` and `display_clock` both NULL
on all 28), so the "post-game clocks are junk" trap does not bite here — but
filtering is on `state`, never on clock, as instructed.

---

## The outcome cohort: 42 of 50 games

Recording does not reach a `post` row for every game, so the outcome is not
knowable for all 50.

| | games | outcome |
|---|---:|---|
| ends `post` | 28 | certain |
| ends `in` at P4 `0:00`, not tied | 14 | regulation expired, no tie — certain |
| ends `in` at P4 with time left | 7 | **excluded** (margins 7–68, but the clock is live) |
| ends mid-game | 1 | **excluded** |

**Cohort = 42 games.** The 7 excluded games include six with margins ≥17 that
are morally decided; including them is a sensitivity arm, not the base case,
because "surely nothing changes in 1:41" is an inference and the others are
observations.

**`cfb_game_map` gated nothing.** 29 of 55 maps clear confidence ≥0.9 (all by
`slug_fuzzy_date_pm1`), but no venue join was required for any result here —
everything is computed in ESPN `game_id` space. The confidence floor becomes
load-bearing only when venue prices enter, which the next section explains they
cannot.

---

## 1. The feed-lag measurement is not computable here

Three independent reasons, any one of which is sufficient.

**There is no ESPN wallclock.** The table carries `first_seen_at` — our row —
and no event timestamp from ESPN. The WNBA F8 measurement is defined as *"time
from the play's ESPN wallclock to our feed learning it"*; that first endpoint
does not exist in this export. Half of the measurement has no operand.

**The "live" line does not move.** `live_spread` is constant within **46 of 50
games**; the four exceptions move by 0.5–1.0 points across an entire game.
`live_over_under` is constant in 48 of 50.

> It is a **pregame DraftKings line carried forward**, not an in-game price
> series. The completion-fraction half of F8 asks what proportion of a price
> move is finished when our row lands — and there is no move.

**The cadence is 25.6s.** Median gap between consecutive rows within a game
(min 22.6s, max 27.4s). Even with both operands present, a sampling interval of
~26s cannot resolve the sub-minute dynamics the question is about.

**So my earlier extrapolation stands unsettled, and I am not able to settle it
here.** F8's 36.4s and its 100% completion figure are measured on the WNBA
`espn_live_*` feed. Whether CFB behaves the same is still a hypothesis, and this
substrate cannot test it. It would need a CFB play table with ESPN wallclock and
a genuine venue price series at sub-minute cadence — neither is in this box.

---

## 2. ESPN's win probability: discriminating, and not assessable for calibration

`espn_home_win_pct` is a real series — median **114 distinct values per game** —
and it is the only in-game model on these rows.

**It discriminates well.**

| | Brier |
|---|---:|
| ESPN WP, game-clustered | **0.0488 ± 0.0227** |
| base rate (always predict 0.905) | 0.1031 |

**But calibration cannot be read off this sample**, and the reason is in the
sample rather than in the model.

| ESPN WP bucket | rows | **games** | mean WP | observed | gap |
|---|---:|---:|---:|---:|---:|
| [0.0, 0.1) | 275 | **5** | 0.019 | 0.138 | +0.119 |
| [0.1, 0.3) | 489 | **5** | 0.210 | 0.039 | −0.171 |
| [0.3, 0.5) | 742 | **11** | 0.401 | 0.195 | −0.206 |
| [0.5, 0.7) | 2336 | 32 | 0.611 | 0.800 | +0.189 |
| [0.7, 0.9) | 3265 | 33 | 0.812 | 0.962 | +0.150 |
| [0.9, 1.0) | 9202 | 38 | 0.982 | 1.000 | +0.018 |

**This sample's home win rate is 0.905** — 38 of 42 games. That is early-season
FBS hosting, and it is not a population any win-probability model is calibrated
to.

**A correctly calibrated model MUST look "under-confident on home" in a sample
where home teams win 90% of the time.** The +0.19 and +0.15 gaps in the 0.5–0.9
buckets are exactly the signature of sample composition, and they cannot be
distinguished from genuine miscalibration without a sample whose home rate is
near normal.

The low buckets do not rescue it: `[0.0, 0.1)` and `[0.1, 0.3)` rest on **five
distinct games each**, and the entire 0.3–0.7 middle — 3,078 rows — comes from
**32 games in which home won 87.5%**. Row counts in the thousands are one
opinion per game repeated ~120 times, not independent evidence.

**So the honest answer to "is ESPN's WP calibrated on our sample" is: this
sample cannot say.** What it does show is that the series is monotone,
well-ordered, and far better than the base rate — enough to take seriously as a
benchmark, not enough to certify.

---

## What would change the answer

* **For the lag question** — a CFB play feed carrying ESPN's own wallclock, and
  a venue price series sampled faster than the move it is meant to resolve. The
  state table has neither.
* **For the calibration question** — games whose home win rate is not 0.90.
  More rows from the same 42 games add nothing; the binding quantity is games,
  and mid-range games specifically.
* **Not more modelling.** A fit on this cohort was declined on power grounds
  before any of the above was known ([public-wp-models.md](public-wp-models.md)):
  at G=50 the minimum detectable paired Brier difference is ~0.038 against real
  effects of 0.0100–0.0182. Everything found here reinforces that: the cohort is
  42, not 50, and the composition is extreme.

---

*Computed 2026-09-06. Descriptive only.*
