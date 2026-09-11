# Meridian — CFB Fair Value Model: Status for Research Review

**Date:** 2026-09-06
**Venue:** Polymarket US (binary contracts, 0/1 settlement)
**Prepared for:** external research review

---

## 1. Executive summary

We built the in-game college football win probability model described in the
research brief (nflfastR/cfbfastR recipe, XGBoost, time-decayed closing spread).
**The model works.** It beats ESPN's production win probability on calibration.

We then tested both trading arms on it, on the same 27 games:

| arm | result | verdict |
|---|---|---|
| **Taking** (cross the spread on disagreement) | −0.59¢ / trade, CI [−4.31, +3.12] | **no edge** |
| **Making** (quote around FV, collect rebate) | −8.93¢ / fill, CI [−11.98, −5.87] | **loses, significantly** |

The making loss is **monotone in quote width** — it worsens to −18.61¢ at a 5¢
half-width — and that shape identifies the mechanism. It also implies **a better
model would not fix it.**

**Largest caveat:** all of this is the moneyline market, which is **under 2% of
the board** and is a *different instrument* from the other 98%.

---

## 2. The model

### 2.1 Construction

Reproduced published methodology rather than inventing one, per the brief:

- **Algorithm:** XGBoost, `binary:logistic`, `eta 0.05`, `max_depth 5`,
  `min_child_weight 7`, 534 rounds, monotonicity constraints
- **Target:** did the possession team win
- **Features:** score differential; seconds remaining in half and game;
  `yardline_100`; down; yards-to-go; timeouts each team; second-half-kickoff
  indicator; posteam-is-home; plus the two decayed terms —
  `diff_time_ratio = point_diff · exp(4·(3600−gsr)/3600)` and
  `spread_time = pos_team_spread · exp(−4·(3600−gsr)/3600)`
- **Training data:** CollegeFootballData play-by-play, 2022–2024, both divisions
- **Two heads:** regulation and overtime. Overtime carries **no time features at
  all** — college OT has no clock, so `game_seconds_remaining` is undefined and
  every decayed term with it. They are absent rather than imputed as zero.

### 2.2 Held out BY GAME, not by row

Plays within a game share a single outcome label. A random row split puts the
same game on both sides and lets the model memorise the answer, inflating every
metric invisibly. 20% of **games** held out — 813 games.

### 2.3 Model quality

| metric | model | baseline |
|---|---|---|
| Brier (813 held-out games) | **0.1145** | 0.2498 (base rate) |
| log loss | 0.3574 | — |
| accuracy | 83.4% | — |
| skill vs base rate | **54.1%** | — |

Calibration by predicted-probability decile, held-out games:

| bucket | n | predicted | actual | gap |
|---|---:|---:|---:|---:|
| 0–10% | 37,089 | 0.025 | 0.040 | +0.016 |
| 10–20% | 10,810 | 0.148 | 0.161 | +0.013 |
| 20–30% | 9,436 | 0.249 | 0.261 | +0.012 |
| 30–40% | 8,785 | 0.349 | 0.379 | +0.030 |
| 40–50% | 7,752 | 0.449 | 0.470 | +0.021 |
| 50–60% | 7,085 | 0.550 | 0.547 | −0.003 |
| 60–70% | 9,086 | 0.651 | 0.629 | −0.022 |
| 70–80% | 9,137 | 0.750 | 0.740 | −0.010 |
| 80–90% | 12,187 | 0.853 | 0.827 | −0.027 |
| 90–100% | 40,591 | 0.975 | 0.963 | −0.012 |

Largest gap +0.030. Honest across the range.

### 2.4 Versus ESPN's production model — out of sample

Trained 2022–2024, tested on **2026** games. Both converted to the **home
frame** before comparison: ESPN reports home win probability, our model reports
possession-team; comparing directly would score a frame error as a modelling
difference on roughly half the plays.

| | ours | ESPN |
|---|---:|---:|
| Brier (7,348 plays / 48 games) | **0.0540** | 0.0651 |
| accuracy | 93.2% | **95.0%** |
| games we beat ESPN on | **37 of 48** | |
| game-clustered Brier difference | **−0.0144**, CI [−0.0397, +0.0108] | spans zero |

We are better **calibrated**; ESPN is better at the **binary call**. For pricing,
calibration is the relevant property — a price *is* a probability, and `argmax`
is a decision we never take. Reported anyway for completeness.

**A caveat that cuts against us.** The win/loss magnitudes are asymmetric:

| | n | mean | median | largest |
|---|---:|---:|---:|---:|
| wins | 37 | −0.0441 | −0.0344 | −0.1910 |
| losses | 11 | **+0.0873** | +0.0088 | **+0.3085** |

Mean loss is **2× mean win**. The loss median (0.0088) is far below the loss
mean (0.0873), so the losses are a handful of catastrophic games rather than
broad weakness. The 37-of-48 sign test (z=3.75, p≈0.0002) is therefore
**flattering**; the mean, which spans zero, is the economically honest number.

---

## 3. Result 1 — Taking

Act when the model disagrees with the contemporaneous market mid; cross the
spread; hold to settlement.

| threshold | trades | games | net / trade | 95% CI | |
|---|---:|---:|---:|---|---|
| \|edge\| > 3¢ | 724 | 27 | −0.59¢ | [−4.31, +3.12] | spans zero |
| \|edge\| > 5¢ | 461 | 25 | −2.51¢ | [−6.89, +1.87] | spans zero |
| \|edge\| > 8¢ | 235 | 25 | −1.85¢ | [−6.39, +2.69] | spans zero |
| \|edge\| > 12¢ | 139 | 25 | +0.27¢ | [−5.49, +6.03] | spans zero |

**Conditions applied:**
- **Feed lag charged.** We act at `wall_clock + 30s`, never at the play instant.
  Measured lag from ESPN's own play stamp to our observation is ~30 seconds.
- **Stale markets excluded and counted.** A quote counts only if that market's
  `(bid, ask)` actually changed in the preceding 10 minutes. 2,983 of 5,442
  candidate rows excluded on this basis.
- **Taker fee charged:** `0.06 · p · (1−p)` ≈ 1.5¢ at mid prices, less at wings.
- **Game-clustered intervals.** 27 games clears the pre-registered 25-game power
  floor, so this is a verdict rather than a refusal.

**Conclusion: no edge.**

---

## 4. Result 2 — Making (the strategy from the brief)

Quote a two-sided market around the model's fair value at a chosen half-width.
Never cross. Collect the maker rebate.

| half-width | fills | games | net / fill | 95% CI | |
|---|---:|---:|---:|---|---|
| **1.0¢** | 1,343 | 27 | **−8.93¢** | [−11.98, −5.87] | **excludes zero** |
| 2.0¢ | 1,063 | 27 | −13.21¢ | [−17.15, −9.27] | **excludes zero** |
| 3.0¢ | 894 | 26 | −15.17¢ | [−19.61, −10.72] | **excludes zero** |
| 5.0¢ | 630 | 25 | −18.61¢ | [−24.58, −12.63] | **excludes zero** |

**Fill rule — the conservative one.** A resting bid at *B* is filled when the
market's **ask** falls to *B* or below: someone was willing to sell at our price.

This differs from the production simulator, which books a fill when the **mid**
crosses our price. With a positive spread `mid ≤ bid` is arithmetically
impossible, so that rule fires only when the book moves *through* us — it books
**only adverse fills**, and the profitable case produces no row at all. Every
prior making result in this project was computed on a population where
capture ≤ 0 by construction.

**Economics:** maker rebate `0.0125 · p · (1−p)` **added** (we receive it); no
crossing cost, because we never cross. On this venue a maker is paid 0.31¢ at
mid prices where a taker pays 1.50¢ — a 1.81¢ swing in making's favour before
anything else happens.

**Conclusion: making loses 9–19¢ per fill, and the intervals exclude zero.**
This is not an absence of edge. It is a measured, significant negative.

---

## 5. The mechanism — why a better model does not fix this

**The loss is monotone in quote width.** That is the finding, not the level.

When the model's fair value differs from the market's price, our quote sits
*away* from the market. The only event that fills it is **the market moving
toward our price** — which is the market moving against the position we are
about to hold.

So the fill and the loss have the same cause. Quoting further out does not buy
protection; it selects harder for the cases where we were wrong, which is
exactly the worsening from −8.93¢ to −18.61¢.

This is Glosten–Milgrom (1985) operating as specified, with one consequence
worth stating plainly:

> **Improving the model moves our quote further from the market, which makes the
> adverse selection sharper. The mechanism is adverse to accuracy, not to
> inaccuracy.**

This is the single most important claim in this document and the one most worth
attacking. If it is wrong, making is back on the table.

---

## 6. Scope — the largest limitation

### 6.1 Under 2% of the board, measured independently twice

| measurement | winner rows | of total | share |
|---|---:|---:|---:|
| this analysis | 229,498 | ~12.6M | **1.8%** |
| independent, different vintage | 23,460 | 1,564,036 | **1.50%** |

Denominators differ by 8×. These are **two independent measurements agreeing
within 0.3pp**, not one figure restated.

### 6.2 And the share understates it

The other 98% is a **different instrument**, not more of the same one. There is
**one winner market per game**, against roughly **81 spread and 64 total
markets**.

So a moneyline result does not generalise by volume *or* by contract type.
"Under 2% of the board" invites the reading that this is a sampling problem more
data would fix. **It is not** — the model prices a game winner, and nothing here
prices a margin or a total.

### 6.3 If you recompute this, the definition is the trap

A winner market is one whose slug carries **nothing after the date**. Quarter and
half markets carry **no keyword at all**:

```
-total-N    -pos-N    -neg-N            full game
-3q-N       -3q-pos-N  -1h-neg-N        quarter / half  <- NO KEYWORD
(nothing after the date)                WINNER, 132 slugs
```

Classifying by searching for `-pos-` / `-neg-` / `-total-` returns **46.30% of
rows** — thirty times the true figure — by misreading ~2,770 quarter and half
slugs as winners. That error was caught only because a second independent number
existed to disagree with.

---

## 7. Other limitations

- **Queue position is unmodelled and unmodellable from tape.** We assume a fill
  whenever the price reaches us. The venue publishes price and **aggregate size**
  per level and **no order count at any level**, so our place in the queue cannot
  be recovered at any sampling rate. **Every making figure above is an upper
  bound** — the true result is worse.
- **Game state is ESPN's corrected end-of-game data**, not the provisional data a
  live system sees. Divergence measured on 19 games captured both ways:
  possession 0.00%, period 0.00%, down 0.25%, yards-to-goal 0.25%, distance
  0.89%, score 2.22%. Small, non-zero, and in the flattering direction.
- **~30-second feed lag.** By the time we observe a play, the price already
  reflects it. There is **no speed component available** — the only possible edge
  is a better state→probability map, exercised in the stable intervals *between*
  plays. A system sold as reacting to plays would be false.
- **Cross-venue is closed on cost.** Kalshi charges makers
  `0.07 · p · (1−p)` where Polymarket pays them, giving 0.13 combined
  (3.25¢ at p=0.5) against a maximum observed gap of one tick. Separately, the
  two venues sample at 163s and 3.4s per market respectively — a 48× mismatch
  that manufactured a false "7¢ arbitrage" in an earlier analysis when the data
  was time-bucketed rather than instant-matched.

---

## 8. Data assets

| table | rows | coverage |
|---|---:|---|
| `market_snapshots` | 38.4M | top-of-book time series, both leagues |
| `book_levels` | 24.7M | full depth ladder, 30+ levels both sides |
| `espn_cfb_live_plays` | live | per-play state: down, distance, yards-to-goal, possession, `wall_clock` |
| `espn_cfb_backfill_plays` | 9,544 / 55 games | ESPN's corrected finished-game data |
| `espn_cfb_game_state` | live | per-poll: timeouts, live line, ESPN's own WP |
| `cfb_game_map` | 55 | ESPN event id ↔ venue game id, with match confidence |

**The join that makes any of this tradeable, verified end to end:** 1,709 plays
across 14 games find a market price a **median 0.9 seconds** from their own
`wall_clock`.

ESPN event ids and venue game ids have **zero overlap** — the bridge is a fuzzy
match on team names with a ±1-day window (venue dates are local, ESPN's are UTC).
Below a confidence floor the builder writes **nothing** rather than guessing: a
mispaired game trains one game's state against another game's prices and every
validation passes.

NFL game state recording is now live ahead of the 2026-09-10 opener. The NFL
payload shape was verified against an archived completed game — plays nest under
`drives` exactly as CFB does, so no parser branch is needed.

---

## 9. Defects found and fixed before these numbers

Listed because each produced a confident wrong result first, and a reviewer
should know what this pipeline has already been caught doing.

**1 · Inverted monotone constraint on `spread_time`.** A favoured team carries a
*negative* spread, so win probability **falls** as the feature rises. The
constraint said rise. XGBoost could make no legal split, so the recipe's most
valuable feature was **completely inert**: 0.00% of total gain, and win
probability **flat at 0.553** for a 20-point favourite *and* a 20-point
underdog. Corrected, it is **62% of gain** and win probability runs 0.982 →
0.038. Nothing in the harness could see this — a model that *ignores* a feature
satisfies any monotone constraint on it trivially, and calibration cannot
distinguish "ignores the spread" from "mildly miscalibrated".

**2 · YES-frame inversion.** The venue quotes `P(first team wins)`, and the
slug's first team is the **away** team (verified 50/55, 0 contradicting, 5
ambiguous and excluded). The scoring script compared `P(home)`, inverting the
sign on every market where away is listed first. **The taker result went from
+3.33¢ to −2.28¢.** The tell was that 96% of plays read as disagreements, which
is not plausible.

**3 · `down = 0` sentinel.** ESPN emits down 0 with distance 0 and no possession
team on end-of-game markers. Down 0 does not exist in football, and it passes
every `down IS NOT NULL` filter. 63 live and 86 backfilled rows were eligible to
reach the model. Found only by inspecting a *completed* game — a game in
progress has no end-of-game marker, so no amount of live testing surfaces it.

All three were found by measurement rather than review.

---

## 10. Open questions

**1 · Is the 98% worth building?** Spread and total markets carry nearly all the
volume and need a different target: margin and total *distributions* rather than
P(win). The literature covers this — nflfastR's expected-points model, and the
normal-approximation margin model where end-of-game margin ≈ N(current
differential + expected points, σ ≈ 13.45·√(fraction remaining)). This is the
largest untested surface and the clearest next build. **It is a new model, not a
tweak.**

**2 · Does the mechanism argument generalise to a ladder?** On the moneyline,
quoting away from the market selects for adverse fills. On a spread ladder our
quote can sit at a rung the market has not priced at all. Does the rung structure
break the equivalence, or is it the same argument with more strikes? Worth
reasoning through before building.

**3 · Is there any state where making is not adverse?** The −8.93¢ is pooled.
Dead time between plays, deep pregame, and blowouts have different flow and the
result has not been stratified. **Caution:** this is a subset search on a null.
Any positive stratum needs pre-registration before it means anything.

**4 · Is passive joining worth one live measurement?** A resting-order probe is
built and inert. Break-even needs a **49.7%–57.8% benign fill rate** [CORRECTED
2026-09-06: was a 57.8% point estimate. H's population is not identifiable — H is
what a BENIGN fill earns and benign fills live in the phantom bucket, which mixes
them with true phantoms. Guarded-real H gives 57.8%, guarded-phantom 49.7%,
guarded-both 52.4%] against a measured **23.7% ceiling, upper bound 31.4%** [was
35.8%; that widening was assumed, not measured — deff 1.05 not 2.5]. **The verdict
is invariant across the range, clearing the ceiling by 18–26 points, and breaks
only if H > 3.569¢ — 2.16× the phantom bucket's own mean.** Current recommendation
is **do not arm it** — and the probe is the only instrument that can separate a true
phantom from a real benign fill, which is exactly what makes the floor a range. But it is the only way to
observe the benign side, which the simulator mixes with true phantoms and cannot
separate at any sampling rate.

---

## 11. Methodology notes for critique

- All intervals are **game-clustered**. Plays within a game are not independent —
  one winner per game, and consecutive plays share the label.
- The 25-game power floor is **pre-registered** and the harness **refuses** to
  report below it rather than reporting a wide interval.
- Stale and unknown-freshness rows are **excluded and counted**, never silently
  dropped. Absence of a freshness flag is treated as *unknown*, not as fresh.
- Settlement is derived from the **game outcome**, not from our own simulated
  fills. An earlier version joined settlement through the fill table, which made
  the sample a selection on our own behaviour sitting inside an edge estimate —
  and limited it to 7 games.
- Fee schedules are read from each **venue's published schedule**, not inferred
  from our own fills.
