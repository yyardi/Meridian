# The NBA game-dynamics atlas

**Descriptive, measured, season-clustered. Not a gate; nothing here is a signal.**
Built from the pins `nba_games_20260901T225326Z.csv` and `nba_plays_20260901T225326Z.csv.gz`:
**13116 games, 11 seasons (2015–2025), 616449 minute-grid states.**

Three boundaries, before any number:

1. **No market data exists for NBA in-game.** Nothing in this atlas scores entries
   against prices, and nothing in it can say a state is tradable.
2. **Physics only** — fitted constant tables, never point-in-time claims.
3. **The honest n for any property of a constant is 11 seasons**, not
   13116 games. Every interval is season-clustered.

No in-sample result justifies capital. The forward test is the evidence.

## 1. Lead safety — P(leader wins | lead, time left)

Raw frequencies with season-clustered CIs; n is state-rows (games appear once per cell).

| min left | lead 1-3 | lead 4-6 | lead 7-9 | lead 10-14 | lead 15-19 | lead 20+ |
|---|---|---|---|---|---|---|
| **36** | 0.549 [0.530, 0.568] n=3674 | 0.634 [0.618, 0.651] n=3031 | 0.677 [0.658, 0.696] n=2455 | 0.764 [0.749, 0.779] n=2278 | 0.851 [0.824, 0.878] n=812 | 0.919 [0.895, 0.943] n=259 |
| **30** | 0.540 [0.519, 0.560] n=3060 | 0.642 [0.616, 0.667] n=2720 | 0.711 [0.688, 0.735] n=2302 | 0.781 [0.765, 0.798] n=2548 | 0.853 [0.831, 0.874] n=1235 | 0.948 [0.933, 0.963] n=672 |
| **24** | 0.563 [0.539, 0.586] n=2785 | 0.650 [0.634, 0.666] n=2486 | 0.737 [0.708, 0.766] n=2105 | 0.824 [0.809, 0.839] n=2707 | 0.887 [0.867, 0.907] n=1497 | 0.972 [0.963, 0.981] n=1108 |
| **18** | 0.586 [0.576, 0.595] n=2548 | 0.668 [0.645, 0.690] n=2305 | 0.757 [0.729, 0.784] n=1948 | 0.857 [0.835, 0.878] n=2572 | 0.926 [0.910, 0.943] n=1710 | 0.980 [0.974, 0.986] n=1638 |
| **12** | 0.610 [0.588, 0.632] n=2363 | 0.694 [0.671, 0.716] n=2093 | 0.807 [0.791, 0.823] n=1917 | 0.904 [0.890, 0.918] n=2511 | 0.967 [0.955, 0.979] n=1754 | 0.997 [0.994, 1.000] n=2085 |
| **6** | 0.616 [0.584, 0.648] n=2173 | 0.769 [0.749, 0.788] n=2093 | 0.887 [0.876, 0.897] n=1818 | 0.955 [0.950, 0.961] n=2467 | 0.991 [0.985, 0.998] n=1762 | 1.000 [0.999, 1.001] n=2431 |
| **4** | 0.635 [0.615, 0.655] n=2229 | 0.806 [0.788, 0.824] n=2054 | 0.925 [0.913, 0.938] n=1784 | 0.983 [0.977, 0.989] n=2422 | 0.999 [0.997, 1.001] n=1696 | 1.000 [1.000, 1.000] n=2548 |
| **2** | 0.692 [0.668, 0.716] n=2297 | 0.886 [0.870, 0.902] n=1988 | 0.973 [0.966, 0.980] n=1792 | 0.999 [0.997, 1.000] n=2274 | 1.000 [1.000, 1.000] n=1795 | 1.000 [1.000, 1.000] n=2572 |
| **1** | 0.749 [0.731, 0.767] n=2411 | 0.949 [0.938, 0.959] n=1987 | 0.989 [0.982, 0.995] n=1677 | 1.000 [1.000, 1.000] n=2292 | 1.000 [1.000, 1.000] n=1819 | 1.000 [1.000, 1.000] n=2493 |

Cells where the adopted model's mean P(leader wins) disagrees with the raw frequency (season-clustered CI off zero; positive = model UNDERRATES the leader):

| min left | lead | realized − model | 95% CI | rows |
|---|---|---|---|---|
| 36 | 4-6 | +0.032 | [+0.007, +0.056] | 2110 |
| 36 | 10-14 | +0.036 | [+0.016, +0.055] | 1584 |
| 36 | 15-19 | +0.041 | [+0.019, +0.063] | 568 |
| 36 | 20+ | +0.060 | [+0.016, +0.105] | 184 |
| 30 | 4-6 | +0.025 | [+0.008, +0.042] | 1890 |
| 30 | 7-9 | +0.038 | [+0.002, +0.074] | 1576 |
| 30 | 10-14 | +0.028 | [+0.007, +0.048] | 1768 |
| 30 | 20+ | +0.038 | [+0.013, +0.062] | 485 |
| 24 | 10-14 | +0.037 | [+0.017, +0.057] | 1865 |
| 24 | 20+ | +0.028 | [+0.015, +0.042] | 785 |
| 18 | 1-3 | +0.031 | [+0.021, +0.040] | 1824 |
| 18 | 10-14 | +0.030 | [+0.002, +0.057] | 1775 |
| 18 | 20+ | +0.011 | [+0.003, +0.019] | 1158 |
| 12 | 1-3 | +0.023 | [+0.009, +0.037] | 1673 |
| 12 | 7-9 | +0.041 | [+0.022, +0.059] | 1342 |
| 12 | 10-14 | +0.029 | [+0.017, +0.042] | 1752 |
| 12 | 15-19 | +0.027 | [+0.009, +0.045] | 1220 |
| 12 | 20+ | +0.010 | [+0.007, +0.013] | 1421 |
| 6 | 7-9 | +0.028 | [+0.016, +0.040] | 1291 |
| 4 | 7-9 | +0.018 | [+0.005, +0.031] | 1260 |
| 1 | 7-9 | -0.009 | [-0.018, -0.001] | 1176 |

These are the states where the model would misprice against reality — candidates for scrutiny, not for trading (no prices exist here).


## 2. Comebacks

A double-digit lead entering Q4 (12:00 left) loses **4.8%** of the time [0.043, 0.053] (6350 games). Split: lead 10-14 loses 9.6% [0.082, 0.110]; lead 15+ loses 1.7% [0.011, 0.022].

Largest deficit the eventual winner faced (minute resolution, 13116 games): median **5**, p90 **13**, max **35**. Winners came back from 10+ in 22.6% of games, from 15+ in 7.3%, from 20+ in 1.5% (about 18 twenty-point comebacks per season; season range 12-29).

## 3. Run structure (context only)

Unanswered-run structure over 13116 games (860518 runs; a run = consecutive points by one team):

- Runs per game: mean 65.6.
- Share of runs reaching 6+ points: 12.8%; 8+: 5.2%; 10+: 2.0%.
- Per game: 3.39 runs of 8+ and 1.34 runs of 10+ — a 10-0 run is roughly an every-other-game event, not an anomaly.
- By period, share of that period's runs reaching 8+: Q1: 4.7%, Q2: 5.3%, Q3: 5.4%, Q4: 5.2%.

Context only: F8 established runs cannot be traded reactively (the move is priced before a reactive entry fills). This section exists so nobody re-derives run frequency from vibes; it is not a signal.

## 4. Endgame dynamics

- Close game (margin ≤5) with **2:00 left**: 4035 games; **91.1%** [0.900, 0.922] score 6+ more points in regulation; **15.0%** [0.138, 0.161] reach overtime.
- Close game (margin ≤5) with **1:00 left**: 4201 games; **64.3%** [0.630, 0.656] score 6+ more points in regulation; **15.9%** [0.146, 0.171] reach overtime.
- Scoring pace in the final 2:00: close games 5.8 pts/min vs blowouts (margin ≥10) 4.8 pts/min — the foul game runs ~1.2× the blowout pace.
- Overtime: 701 of 13116 games (5.3%). An OT period adds 24.2 points on average (p10 15, p90 36); 11.8% of OT games need 2+ periods.

This is the tail R3b showed a Gaussian endgame cannot price — measured instead of assumed.

## 5. The FV replay — calibration of the adopted stack

The adopted stack (R1b σ arm (a) + R2 shrink), walk-forward, out-of-sample seasons only: [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2025] — 9170 games, 430990 states.

Murphy decomposition: Brier 0.1550 = UNC 0.2455 − RES 0.0901 + REL **0.0005** (reliability ~0 is calibrated).

| predicted P(home win) | realized | 95% CI (season-clustered) | rows |
|---|---|---|---|
| 0.033 | 0.020 | [0.016, 0.023] | 34843 |
| 0.152 | 0.126 | [0.119, 0.133] | 24413 |
| 0.252 | 0.234 | [0.219, 0.249] | 31978 |
| 0.351 | 0.339 | [0.321, 0.356] | 39616 |
| 0.450 | 0.448 | [0.423, 0.473] | 44069 |
| 0.551 | 0.562 | [0.549, 0.575] | 49299 |
| 0.650 | 0.680 | [0.665, 0.695] | 53648 |
| 0.749 | 0.786 | [0.767, 0.806] | 51428 |
| 0.848 | 0.883 | [0.872, 0.894] | 42489 |
| 0.967 | 0.978 | [0.973, 0.983] | 59207 |

Per-season Brier: 2016: 0.1583, 2017: 0.1564, 2018: 0.1519, 2019: 0.1568, 2020: 0.1550, 2021: 0.1555, 2022: 0.1611, 2025: 0.1435

## 6. The engine constants

Constants written to `nba_constants_v1.json` — R1b σ global 2.596, phase 2.317/2.577/2.649/2.707; R2 β 0.452/0.407/0.346/0.322/0.296/0.251/0.231/0.205/0.161/0.132/0.093; R3b b 1.088/1.014/1.020, σ 16.03/13.74/10.48.

---
*Generated by `analysis/nba_atlas.py` — rerun the command in its docstring to
reproduce every number above from the pins.*

*No in-sample result justifies capital. The forward test is the evidence.*
