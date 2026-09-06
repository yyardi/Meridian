# The CFB market anchor — two instruments, and what they agree on

The market-as-feature architecture puts a **pregame market number** in the
feature set as the model's prior. nflfastR's is `spread_line`, the closing
spread, a per-game constant. This page is about which number we use for it,
how well the candidates agree, and what the filters cost.

See [public-wp-models.md](public-wp-models.md) for the architecture, and
[cfb-state-substrate.md](cfb-state-substrate.md) for the state side.

## Why an anchor at all: ESPN has no prior

Measured across three instruments and three routes, all agreeing:

| instrument | sd of the pregame number | strong prior (>0.80 or <0.20) |
|---|---:|---:|
| ESPN first in-game WP, 29 kickoff-observed games | **0.0216** | **0 of 29** |
| venue moneyline anchor, 14 games | **0.2193** | 11 of 14 (78.6%) |
| ESPN `live_spread` → implied, 50 games | 0.1879 *(ce/B's figure, not recomputed here)* | — |

**ESPN opens every game between 52.1% and 62.3% for the home team.** That is
home-field advantage and nothing else. A pure play-state model inherits that
blindness; the anchor is the entire piece of information it otherwise lacks.
**Dispersion ratio 10.2×** on the two figures measured here (0.2193 / 0.0216);
peers measured 10.7× and 12× by other routes, on other cohorts.

This is why nflfastR puts a per-game constant in the feature set. **The
constant is not a weak feature that happens to be constant — it is the prior.**

## Two anchors, and they agree to a third of a point

| | coverage | sd | source |
|---|---:|---:|---|
| **ESPN `live_spread`** | **50 of 50 games** | 15.62 pts | DraftKings, via ESPN, same table as the state |
| venue full-game spread ladder | 12 games | 14.66 pts | our venue, interpolated to P(YES) = 0.5 |

On the 12 overlapping games:

```
corr             +0.999
mean |diff|       0.41 pts
median |diff|     0.32 pts
worst single      1.70 pts
```

Same sign convention, no transform. **Take `live_spread` for coverage; keep the
venue ladder as the validator.** A 40-rung ladder interpolation reproducing a
book's published line to a third of a point is what qualifies it as a
validation instrument.

**They are not independent information.** At r = 0.999, using both as features
is the collinearity trap #18 and #19 already documented — two near-duplicate
readings of one quantity, neither separately identified. Use one; check with
the other.

### What `live_spread` actually is

`line_provider` is **DraftKings** on 100% of 18,627 rows — a real sportsbook
line, not a number ESPN invented. It moves in **4 of 50 games**, and all four
moves are **≤1 point inside the first quarter** (−28.5→−29.5, 3.0→2.5,
−10.5→−11.5, −16.5→−15.5). So it is a pregame line with an early settle rather
than a live line: fidelity-equivalent to `spread_line` in substance.

**Not established: that it is a *close*.** Only 2 rows in the export carry
`state == 'pre'`, so this data cannot show what the number was at kickoff
versus hours before. Provenance also differs from a venue price in a way that
matters downstream — a venue price is one someone could transact at; a
DraftKings line carried by ESPN is not a quote on our book. For a forecast
feature that may not matter. For anything that becomes a P&L claim it does.

## The bracket filter costs 1 game in 7, and not for the reason it looks like

The venue ladder needs quoted mids to **bracket P(YES) = 0.5** to interpolate a
crossing. Of 14 games reaching the stage, **12 keep an anchor and 2 are
dropped**. Zero drop for thin ladders.

The obvious reading is "lopsided games get dropped, because their ladder sits
all one side." **That is not what happens.**

| venue game | lines | mid range | anchor | |
|---|---:|---|---:|---|
| 17399 | 43 | 0.015..**0.515** | 0.993 | KEPT |
| 16485 | 42 | 0.015..**0.485** | 0.993 | DROPPED |
| 16501 | 41 | 0.015..0.500 | 0.987 | DROPPED |

**17399 and 16485 have identical anchors and opposite fates.** The difference
is one rung — 0.515 against 0.485. The filter is keyed to **where the venue
chose to list lines**, not to anything about the game, which makes it
near-arbitrary at the margin and impossible to reason about from the game side.

It still biases the cohort. The two dropped games carry `live_spread` of
**−49.5 and −40.5**, both outside the entire range of the surviving 12-game
cohort (−41.0..+13.7), and **11 of the 50 games are beyond ±40 points** — a
region the venue cohort has one game in. So the coverage gap is not merely
12-vs-50, it is **truncated at the lopsided end**, which is exactly where a
prior carries the most information.

**Therefore: fall back to the moneyline anchor on non-bracketing games rather
than dropping them.** The two-anchor design already supports it.

## The zero-parameter identity cannot be run on the venue anchor

    logit(p̂) = logit(anchor) + [ logit(ESPN_live) − logit(ESPN_at_kickoff) ]

No fitted parameters, so it cannot memorise a near-unique game key — which is
the failure a fitted state+anchor model hits (in-sample 0.003 against
out-of-fold 0.109, on 22 distinct anchor values across 28 outcomes).

On the 09-05/06 cohort the required intersection is **empty**:

```
kickoff-observed (P1, 0-0)        29
settled                           42
venue moneyline anchor            14
kickoff & settled                 26
kickoff & settled & anchored       0   <-- the identity's cohort
settled & anchored                10   <-- exists, but NO kickoff
```

The venue anchor needs the **price** recorder alive ≤15 min before kickoff;
the update term needs the **ESPN** recorder alive at kickoff. On this slate the
two were never alive simultaneously.

**This is a stronger argument for `live_spread` than coverage counts.** It sits
in the same ESPN-keyed table as the state, so it cannot fail to intersect with
kickoff observation. The venue path requires two independent recorders to have
survived the same window, and on 09-05 that never happened.

**A number was computed on the 10 settled-and-anchored games and is withdrawn.**
Not one of those 10 has its first row at kickoff — the earliest is P2 5:04 at
14-0, and several begin in P4 at 49-3 and 38-0. `ESPN_at_kickoff` was in fact
"ESPN when the recorder woke up", mid-blowout, so the update term measured the
change since an already-decided game and the identity collapsed to the anchor.
It is not a measurement of the identity and must not be compared against one.

## What is not established here

* **No skill claim.** No out-of-fold score on this cohort means anything: 10
  settled-and-anchored games, of which the two informative ones are upsets —
  a −20.5 home favourite losing and a +13.5 home underdog winning. Measured
  `corr(anchor, outcome) = −0.134` and `corr(−live_spread, outcome) = −0.003`.
  **Neither anchor predicts outcomes on this cohort**, and that is a fact about
  10 games, not about the anchors.
* **Not that `live_spread` is a closing line** — see above.
* **Orientation** was wrong until 2026-09-06 and every anchor was inverted; see
  B15 in [findings.md](../findings.md). The current frame is pinned by
  `AWAY_TEAM_IS_FIRST` and guarded by `assert_away_first()`.

---

*Measured 2026-09-06 on the 09-05/06 CFB cohort. Venue prices from
`cfb_prices_20260906T194301Z`, state from `espn_cfb_game_state_20260906T174104Z`,
bridge from `cfb_game_map_computed_20260906T221500Z` (the computed CSV — a peer
querying `cfb_game_map` sees 55 rows and a different set).*
