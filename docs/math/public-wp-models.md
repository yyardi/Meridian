# Public win-probability models, and what happens when the best one meets our tape

**DESCRIPTIVE. NO GATE, NO VERDICT REGISTERED.** Everything here was computed
after seeing the tape and nothing on this page may feed a registered
measurement. Two deliverables, reported separately: a survey of public work, and
a fit against `pulse_predictions_20260904T183000Z`.

---

## Part 1 — The survey

The bias throughout is toward what is **falsifiable**: real code, real features,
and an out-of-sample scheme you can inspect.

### nflfastR — the one whose numbers mean something

Read from the repository rather than from write-ups about it:
[`data-raw/MODELS.R`](https://github.com/nflverse/nflfastR/blob/master/data-raw/MODELS.R)
and `data-raw/_tune_spread_wp.R`.

**Target:** `label = ifelse(posteam == Winner, 1, 0)` — did the team in
possession win. Ties filtered out, `qtr <= 4`.

**Feature set of the spread-aware model (`wp_model_spread`), complete:**

| | |
|---|---|
| market | **`spread_time`** — the point spread, time-decayed |
| clock | `half_seconds_remaining`, `game_seconds_remaining` |
| score | `score_differential`, `Diff_Time_Ratio` |
| field | `down`, `ydstogo`, `yardline_100` |
| structure | `home`, `receive_2h_ko`, `posteam_timeouts_remaining`, `defteam_timeouts_remaining` |

Twelve features, with **monotone constraints on all of them**
(`"(0,0,0,0,0,1,1,-1,-1,-1,1,-1)"`) — the model is forbidden from learning that
a bigger lead lowers win probability. A second variant, `wp_model`, is the same
minus `spread_time`.

**Out-of-sample scheme — held out by SEASON, which is stricter than by game:**

```r
folds <- map(0:9, function(x) {
  f <- which(model_data$season %in% c(2000 + x, 2010 + x))
  return(f)
})
```

Ten folds, each withholding two entire seasons. No game, drive, or
within-season correlation can leak across a fold. This is the only public
implementation surveyed whose validation scheme is both published and grouped.

The project reports that adding the spread moved error 27% → 23% and logloss
0.52 → 0.44.

> **A comparison NOT made here.** The spread-aware model trains for 534 rounds
> and the spread-free one for 65, which looks like "the spread gave it far more
> to learn". It is not evidence of that: the two were tuned separately, with
> `eta` 0.05 against 0.2, different depth, and monotone constraints on only one
> of them. The round counts are not comparable and are not used.

### CFBD / cfbfastR — market-anchored, and not falsifiable

CFBD's pregame win probability is, in its own documentation, derived from "the
available point spread and the historical relationship between spreads and game
outcomes" — explicitly "a market-based estimate rather than a CFBD team-rating
forecast". The in-game model adds score, time remaining, down, distance, field
position and possession, with timeouts "where available and reliable".

But: **"the underlying models are proprietary… without publishing fitted
parameters, model artifacts, or the complete production calculation."** Validation
is described only as "evaluated for calibration". There is no published holdout
scheme of any kind, by game or by row.

So by the standard that matters — can an outsider check the number — CFBD is
architecture worth reading and results worth nothing.

### The pattern, which is the actual finding

**Both take the market as an input, not as an opponent.**

Neither system forecasts the game independently and then compares itself to the
price. The market's own estimate is a *feature*; the model's job is to move that
estimate using state the market has not repriced yet — down, distance, field
position, possession, timeouts. Every one of those changes on a timescale of
seconds, and the quote does not.

**So the edge in public WP work is not forecasting skill. It is observation
frequency.** They win by seeing the game state before the price absorbs it, from
a baseline that is already the market's.

---

## Part 2 — The fit

### The architecture cannot be transplanted, and that is the first result

`pulse_predictions_20260904T183000Z.csv.gz` carries: model output
(`model_probability`, `model_fair_value`), market (`market_bid/ask/mid`),
outcome (`settlement`, final scores), and bookkeeping.

**It carries no game state at all.** No score differential, no clock, no
possession, no period — nothing from the column families that make nflfastR
work. A literal refit is not underpowered here; it is impossible.

What *is* answerable on this substrate is the question that decides whether any
of it matters: **does the model carry information the mid does not already
have?**

### Method

* **`model_version == 'v4'` only** — 183,538 of 186,210 rows (98.6%). The tape
  pools three versions and the README says not to pool silently.
* **One row per market, taking the EARLIEST prediction.** The tape logs ~124
  rows per market as the price moves; the dedupe direction chooses which mid you
  score against.
* **Clustered and held out by GAME** (83 games in v4), never by row.
* λ* is the weight on the model in a logit-space blend against the mid:
  `combined = σ((1−λ)·logit(mid) + λ·logit(model))`, λ chosen to minimise
  log-loss. λ* > 0 means the model carries independent information.

### The late-mid trap is live on this tape, and it is worth 2×

| dedupe | Brier (mid) | Brier (model) | model − mid |
|---|---:|---:|---:|
| **earliest** (used here) | 0.1937 | 0.2037 | **+0.0100** |
| latest | 0.1845 | 0.1892 | +0.0047 |

The mid moves a median of **4.5¢** between a market's first and last logged
prediction. Summarising late does not merely flatter the market — it **halves
the model's apparent deficit**, because a drifted mid has absorbed part of the
answer and the comparison inherits it. Every number below uses the earliest
ex-ante mid.

### λ* — the answer

```
λ* = −0.0224      95% CI (game-clustered, 2000 resamples of 83 games) [−0.4413, +0.4104]
```

**The interval contains zero, and the point estimate is negative.** Brier: mid
0.1937, model 0.2037, blend at λ* 0.1937 — the optimal blend is the mid, to four
decimals. **There is no evidence the model adds information beyond the price.**

### Slices, none ranked by p-value

Pre-identified by the tape's own README; reported together because reporting the
one that reads well is how this goes wrong.

| slice | n | G | λ* | 95% CI | Brier model−mkt |
|---|---:|---:|---:|---|---:|
| ALL v4 | 1494 | 83 | −0.022 | [−0.443, +0.400] | +0.0100 |
| winner | 83 | 83 | **+0.940** | **[+0.189, +1.709]** | −0.0135 |
| spread | 664 | 83 | +0.135 | [−0.297, +0.696] | +0.0086 |
| total | 747 | 83 | −0.557 | [−1.000, +0.279] | +0.0138 |
| actionable | 130 | 9 | +0.082 | [−0.836, +1.063] | +0.0040 |
| declined | 1364 | 79 | −0.026 | [−0.473, +0.447] | +0.0106 |
| agreement ≤5¢ | 673 | 83 | +0.321 | [−0.746, +1.581] | −0.0001 |
| **disagreement >5¢** | 821 | 83 | −0.044 | [−0.445, +0.426] | **+0.0182** |

Two things to read off it. The **disagreement** row is the tradable cut — where
the model differs from the price is where it trades — and it is the worst slice
on the board at +0.0182. That reproduces the 34-game finding at 83 games: *the
model is worst exactly where it acts.*

And **winner** is the one slice whose interval excludes zero.

### The winner slice does not survive being held out

Leave-one-game-out: λ refit on the other 82 games, scored on the held-out one.

| slice | λ* range across folds | OOS Brier mid | OOS blend | difference |
|---|---|---:|---:|---|
| ALL v4 | [−0.10, +0.04] | 0.1937 | 0.1945 | **+0.0008 [+0.0005, +0.0011]** |
| winner | [+0.84, +1.04] | 0.2046 | 0.1950 | −0.0096 **[−0.0292, +0.0100]** |
| spread | [+0.07, +0.22] | 0.1642 | 0.1657 | +0.0015 [−0.0001, +0.0031] |
| total | [−0.70, −0.44] | 0.2187 | 0.2185 | −0.0001 [−0.0055, +0.0052] |

**The winner slice's interval spans zero once held out**, where the in-sample
bootstrap excluded it. The blend weight itself is stable across folds
([+0.84, +1.04]) — the weight is estimable; the *improvement* is not
distinguishable from zero at 83 games.

Overall the blend is **worse out of sample**, +0.0008 with an interval excluding
zero on the wrong side. Mixing this model into the price costs Brier.

**Winner is a candidate for a pre-registered test on new games, and nothing
more.** It is one of eight slices, at the smallest n on the board, and it is the
slice that reads well — which is the profile of a result that does not replicate.

---

## What this says about the missing feature

The survey answer and the fit answer are the same answer.

Public WP models work by **conditioning on the market and adding state the
market has not yet repriced.** PULSE does the opposite: it forecasts
independently and compares itself to the price. λ* is precisely the test of
whether that independence buys anything, and at 83 games it buys nothing.

So the architecture worth copying is not a model at all — it is a **frame**:
feed the mid in as a feature and ask what moves it, rather than building a rival
estimate and diffing.

**And the bound on how far that can go is already measured.** The state features
carrying nflfastR's edge change every play, and the edge exists because the
model sees them before the quote does. [F8](feed-lag.md) says our feed learns a
play at **p50 36.4s**, by which time the price move is complete. We can add the
state — it exists in `espn_live_plays` and `espn_live_box_snapshots`, off this
tape — but we would be adding it **after** the market has already priced it.

That is the honest shape of the gap: **the public models' mechanism is not a
feature we are missing, it is a latency we do not have.** Building the state
join is worth doing, because it is the only way to measure how much of the edge
is state and how much is speed — but it should be registered before it is run,
and nobody should expect the nflfastR result to transfer.

---

*Computed 2026-09-06 against `pulse_predictions_20260904T183000Z.csv.gz`
(186,210 rows, 88 games; 183,538 rows / 83 games at v4). Descriptive only.*
