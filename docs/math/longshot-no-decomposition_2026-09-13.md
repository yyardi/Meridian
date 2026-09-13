# CFB spread 0.2-0.3 buy-NO: decomposition (agent_cfb_split)

Data: sat_ladder.csv, CFB only (5967 rows; 83 games with spread ladders, 3346 spread rows). Estimator everywhere: fills-weighted mean, cluster-robust sandwich SE, cluster = vg; cells read `mean [lo,hi] n G G_eff`, G<25 flagged UNDERPOWERED. Primary reproduces exactly: **+6.36 [-1.12,+13.85] n=211 G=76 G_eff=63.2**. Scripts: cfb_split.py, cfb_split2.py in this directory. Every split I ran is in this file; nothing was dropped.

## Summary (read this, then the tables)

1. **Away-team vs longshot cannot be separated by the requested split.** 75 of 83 games have the away team as underdog (median centre line +23: early-season home cupcake games), so 195/211 bucket rows are "away dog" and the away-favourite cell is 8 games. Away, underdog and "visiting cupcake" are one variable on this sample. (Q1a)
2. **It is not a cheap-rung effect.** In probability terms the away side under-performed its mid at the CENTRE (+9.6pp; centre rung 33/83 = 0.398 [0.292,0.503]) as much as at the 0.25 rung (+9.3pp; 11/76 = 0.145 [0.066,0.224]), and in cents buy-NO at [0.40,0.50) is +6.17 [-5.27,+17.60] vs +6.36 at [0.20,0.30). The [0.20,0.30) bucket is where the *interval* is tightest (smaller p(1-p)), not where the effect lives; adjacent buckets [0.15,0.20) and [0.30,0.40) are ~0 and the deep tail [0.05,0.10) is ~0 in cents. Not monotone. (Q2, Q2b, realised-vs-mid table)
3. **Distance and time-to-kickoff are degenerate**, not informative: 190/211 bucket rows are 8-14 pts from the centre (none <3.5); 204/211 have ttk<=60 (151 <=5). The 6h window is a 1h window. (Q3, Q4)
4. **What the ladder shape is consistent with is a whole-ladder SHIFT**, not a tail effect: the away side under-performed its mid in every spread bucket but one (+2.0, +5.0, +9.3, +3.0, +9.6, +7.1, -0.6, +7.4, +9.3 pp), i.e. home teams beat the market's number by roughly 4 points on average (a ~0.25 sd shift gives +9-10pp at the median and +8-9pp at the 75th percentile). That is either "the venue under-rated home favourites in weeks 1-2" or a ~1.9 sigma draw on 83 games; this file cannot tell them apart. Totals show no pattern; team totals show the REVERSE (both ~0.75 sides lose ~10c, the cheap side paid out more than priced), so a venue-wide longshot story is not supported. (Q6) The 09-12 held-out is same-signed on every split and G=12-18 everywhere: it decides nothing. (Q5 columns)
5. **Register next: the centre-rung away-cover rate, one Bernoulli per game, reported pooled and split by sign of the centre line.** It has no fee, spread, price-level or ladder-truncation confound, it is quoted in every game, "shift" predicts <50% and "longshot" predicts 50%, and as the season's home-favourite share falls from 90% the sign split starts to separate away from underdog. Caveat: I chose it after seeing that the centre carries the same gap as the bucket, so this is itself a look; the money metric (buy NO at YES-mid [0.20,0.30), ttk<=360) should keep accruing under its pre-set definition and not be re-cut. Power: binomial SE 0.035 at 200 games (~5 weekends) to resolve a 10pp deficit.

Caveats that change how the tables below should be read (each is repeated at its table):
- The venue quotes the spread ladder around ZERO (about -34.5..+34.5), not around the centre. With centre lines at +23 median, the away-friendly half (YES-mid > 0.5) is truncated: median 11 pts above centre vs 57 below. So the mirror bucket [0.70,0.80) exists in only 45 games and those are the CLOSER games (centre median +13.5 vs +37.0 for the rest). Q1b/Q1c are not a within-game mirror of Q1a.
- 28/83 games ended with the home team beyond the ladder's top line. The per-game PIT dispersion test is therefore bounded, not measured ([0.386,0.663] straddles 0.50) and is reported as unusable. Only the upper tail (away better than the 75th percentile: 14/83 = 0.169 vs 0.25) is clean.
- 1343 of 3346 spread rows have YES-mid < 0.05 (dead rungs on the home-friendly side); they are outside every bucket used here.

---
# CFB spread 0.2-0.3 buy-NO decomposition

Source: sat_ladder.csv, CFB rows only (5967 rows, 83 games with spread rungs). Estimator: fills-weighted mean, cluster-robust sandwich SE, cluster = vg. Cells: mean cents per $1, [95% lo, hi], n markets, G games, G_eff. G<25 flagged UNDERPOWERED.
Centre rung = spread rung whose YES-mid is nearest 0.5 (max |mid-0.5| across games = 0.045). Centre line > 0 => away is the underdog; < 0 => away is the favourite. All lines are half-points, so |line - centre line| is an integer; distance bins used: <3.5 = {0..3}, 3.5-7 = {4..7}, 7.5-14 = {8..14}, >14 = {15+}.
Held-out = event_slug ends 2026-09-12; earlier = 09-03..09-11.

## Reproduction of the primary

CFB spread, YES mid [0.20,0.30), ttk<=360, buy NO: +6.36 [-1.12,+13.85] n=211 G=76 Ge=63.2

## Q1. Away-team split (sign of the centre line)

What the cheap YES (mid 0.2-0.3) means, given YES = away covers +line, and a 0.2-0.3 rung has a line BELOW the centre line (away must do more):
- Away UNDERDOG game (centre line > 0, e.g. +10.5): the 0.25 rung is e.g. line +3.5 -> YES = 'away underdog loses by <3.5 or wins'. Buy NO = 'home favourite wins by MORE than 3.5' = home favourite covers a number SMALLER than the spread.
- Away FAVOURITE game (centre line < 0, e.g. -10.5): the 0.25 rung is e.g. line -17.5 -> YES = 'away favourite wins by >17.5'. Buy NO = 'home underdog loses by LESS than 17.5 (or wins)' = home underdog covers a number BIGGER than the spread.
So buy-NO is always 'buy the HOME side at ~0.75', but in away-dog games it is a favourite-blowout-lite bet and in away-fav games it is an underdog-stays-close bet.
Mirror bucket (YES mid 0.7-0.8, buy YES at ask): line ABOVE the centre. Away dog: YES = 'away dog keeps it within a number BIGGER than the spread'. Away fav: YES = 'away fav wins by MORE than a number SMALLER than the spread'. Buy YES is always 'buy the AWAY side at ~0.75'. If the primary is a home/away effect the mirror should LOSE; if it is a longshot/cheap-side effect the mirror should also WIN (NO is the cheap side there).

### Q1a. YES mid [0.20,0.30), ttk<=360, buy NO at 1-bid

| split | ALL | EARLIER (09-03..09-11) | HELD-OUT 09-12 |
|---|---|---|---|
| all | +6.36 [-1.12,+13.85] n=211 G=76 Ge=63.2 | +6.88 [-1.27,+15.03] n=164 G=60 Ge=49.6 | +4.56 [-13.80,+22.92] n=47 G=16 Ge=13.6 UNDERPOWERED |
| away underdog (centre>0) | +7.16 [-0.41,+14.74] n=195 G=68 Ge=57.2 | +8.67 [+0.88,+16.46] n=156 G=56 Ge=46.4 | +1.14 [-20.85,+23.14] n=39 G=12 Ge=10.8 UNDERPOWERED |
| away favourite (centre<0) | -3.42 [-39.26,+32.42] n=16 G=8 Ge=6.4 UNDERPOWERED | -28.06 [-88.99,+32.87] n=8 G=4 Ge=3.6 UNDERPOWERED | +21.22 [+19.59,+22.84] n=8 G=4 Ge=2.9 UNDERPOWERED |
NOTE (Q1a): 75 of 83 games have the away team as underdog (median centre line +23, i.e. early-season home cupcake games), so 'away' and 'underdog' coincide in 195/211 bucket rows; this split CANNOT separate an away-team effect from a favourite effect on this sample, and the away-favourite cell is 8 games. All 8 away-favourite games contribute to the bucket.

### Q1b. MIRROR: YES mid [0.70,0.80), ttk<=360, buy YES at ask

| split | ALL | EARLIER (09-03..09-11) | HELD-OUT 09-12 |
|---|---|---|---|
| all | -2.27 [-15.61,+11.08] n=101 G=45 Ge=36.3 | +1.74 [-12.45,+15.92] n=73 G=33 Ge=26.5 | -12.70 [-42.83,+17.43] n=28 G=12 Ge=9.8 UNDERPOWERED |
| away underdog (centre>0) | +2.79 [-8.87,+14.45] n=72 G=37 Ge=29.8 | +3.12 [-10.41,+16.66] n=58 G=29 Ge=23.4 | +1.41 [-21.32,+24.15] n=14 G=8 Ge=6.5 UNDERPOWERED |
| away favourite (centre<0) | -14.82 [-50.93,+21.30] n=29 G=8 Ge=7.9 UNDERPOWERED | -3.63 [-53.72,+46.46] n=15 G=4 Ge=3.9 UNDERPOWERED | -26.81 [-84.39,+30.77] n=14 G=4 Ge=3.9 UNDERPOWERED |
NOTE (Q1b): the mirror bucket exists in only 45 games and they are a DIFFERENT set from the primary's: the ladder is quoted roughly -34.5..+34.5 around ZERO, not around the centre, so for big home favourites the away-friendly side (YES-mid > 0.5) is truncated (ladder extends a median 11 pts above the centre vs 57 below; top-rung YES-mid median 0.755). Mirror games have centre line median +13.5 (mean +10.4); the 38 games with no mirror rung have median +37.0. Q1b/Q1c vs Q1a is therefore a between-game comparison of closer games vs blowout games, not a within-game mirror. Both Q1b and Q1c sit at about minus (half-spread + fee) = -2 to -4c, i.e. neither side of the 0.7-0.8 rung shows an edge on the games where it is quoted.

### Q1c. reference: same mirror bucket, buy NO at 1-bid (buying the cheap side, expect the negative of Q1b minus two spreads)

| split | ALL | EARLIER (09-03..09-11) | HELD-OUT 09-12 |
|---|---|---|---|
| all | -3.64 [-17.09,+9.81] n=101 G=45 Ge=36.3 | -8.07 [-22.42,+6.28] n=73 G=33 Ge=26.5 | +7.90 [-21.99,+37.80] n=28 G=12 Ge=9.8 UNDERPOWERED |
| away underdog | -9.58 [-21.30,+2.14] n=72 G=37 Ge=29.8 | -10.23 [-23.83,+3.37] n=58 G=29 Ge=23.4 | -6.90 [-29.64,+15.85] n=14 G=8 Ge=6.5 UNDERPOWERED |
| away favourite | +11.10 [-24.61,+46.81] n=29 G=8 Ge=7.9 UNDERPOWERED | +0.27 [-49.83,+50.38] n=15 G=4 Ge=3.9 UNDERPOWERED | +22.70 [-33.80,+79.21] n=14 G=4 Ge=3.9 UNDERPOWERED |

Games with away underdog: 75; away favourite: 8 (of 83).

## Q2. Monotonicity in cheapness (CFB spread, ttk<=360, buy NO at 1-bid)


### Q2. buy NO by YES-mid bucket

| split | ALL | EARLIER (09-03..09-11) | HELD-OUT 09-12 |
|---|---|---|---|
| [0.05,0.10) | -0.19 [-5.28,+4.90] n=364 G=79 Ge=62.4 | +0.93 [-3.55,+5.41] n=291 G=63 Ge=49.8 | -4.64 [-22.73,+13.45] n=73 G=16 Ge=12.7 UNDERPOWERED |
| [0.10,0.15) | +3.32 [-2.21,+8.85] n=206 G=73 Ge=42.0 | +2.87 [-3.59,+9.33] n=165 G=58 Ge=31.1 | +5.14 [-4.66,+14.95] n=41 G=15 Ge=12.5 UNDERPOWERED |
| [0.15,0.20) | +0.82 [-8.27,+9.91] n=141 G=70 Ge=57.3 | +1.56 [-8.36,+11.48] n=112 G=56 Ge=45.8 | -2.04 [-24.70,+20.62] n=29 G=14 Ge=11.5 UNDERPOWERED |
| [0.20,0.25) | +7.36 [-0.35,+15.07] n=118 G=65 Ge=52.0 | +8.05 [-0.13,+16.23] n=91 G=52 Ge=41.2 | +5.02 [-15.08,+25.11] n=27 G=13 Ge=10.9 UNDERPOWERED |
| [0.25,0.30) | +5.10 [-4.81,+15.00] n=93 G=58 Ge=48.3 | +5.41 [-5.71,+16.53] n=73 G=45 Ge=37.3 | +3.94 [-18.61,+26.49] n=20 G=13 Ge=11.1 UNDERPOWERED |
| [0.30,0.35) | -0.19 [-12.79,+12.40] n=97 G=67 Ge=53.2 | +0.03 [-14.17,+14.23] n=74 G=52 Ge=40.9 | -0.93 [-28.91,+27.06] n=23 G=15 Ge=12.3 UNDERPOWERED |
| [0.35,0.40) | +0.41 [-12.61,+13.43] n=85 G=61 Ge=52.7 | +2.13 [-11.88,+16.13] n=68 G=49 Ge=42.8 | -6.43 [-39.69,+26.82] n=17 G=12 Ge=10.0 UNDERPOWERED |
NOTE (Q2): not monotone in cents. The cheapest three buckets are ~0 in cents because buying NO at 0.90-0.95 caps the gain at 5-10c before ~1-2c of half-spread+fee; see Q2b below for the fee-free probability gap, which is the right unit for a longshot question. In cents the edge sits in [0.20,0.30) AND in [0.40,0.50) (+6.17) with the same magnitude; the [0.20,0.30) interval is narrower only because p(1-p) is smaller there.

### Q2 (coarser, for power)

| split | ALL | EARLIER (09-03..09-11) | HELD-OUT 09-12 |
|---|---|---|---|
| [0.05,0.20) | +1.03 [-4.19,+6.24] n=711 G=79 Ge=65.7 | +1.62 [-3.76,+6.99] n=568 G=63 Ge=52.3 | -1.31 [-16.34,+13.72] n=143 G=16 Ge=13.4 UNDERPOWERED |
| [0.20,0.30) | +6.36 [-1.12,+13.85] n=211 G=76 Ge=63.2 | +6.88 [-1.27,+15.03] n=164 G=60 Ge=49.6 | +4.56 [-13.80,+22.92] n=47 G=16 Ge=13.6 UNDERPOWERED |
| [0.30,0.40) | +0.09 [-11.51,+11.69] n=182 G=74 Ge=61.3 | +1.04 [-11.59,+13.66] n=142 G=58 Ge=48.7 | -3.27 [-31.68,+25.15] n=40 G=16 Ge=12.7 UNDERPOWERED |
| [0.40,0.50) | +6.17 [-5.27,+17.60] n=180 G=78 Ge=66.9 | +5.85 [-7.29,+18.99] n=141 G=60 Ge=50.3 | +7.30 [-16.49,+31.10] n=39 G=18 Ge=17.1 UNDERPOWERED |

### Q2-mirror. buy YES at ask by YES-mid bucket (NO is the cheap side here)

| split | ALL | EARLIER (09-03..09-11) | HELD-OUT 09-12 |
|---|---|---|---|
| [0.60,0.65) | -10.83 [-28.04,+6.38] n=63 G=41 Ge=33.4 | -1.43 [-21.15,+18.28] n=41 G=27 Ge=21.8 | -28.35 [-56.09,-0.60] n=22 G=14 Ge=11.5 UNDERPOWERED |
| [0.65,0.70) | -8.32 [-25.72,+9.08] n=47 G=34 Ge=29.5 | -3.46 [-24.16,+17.25] n=33 G=23 Ge=19.8 UNDERPOWERED | -19.79 [-52.86,+13.27] n=14 G=11 Ge=9.8 UNDERPOWERED |
| [0.70,0.75) | -4.92 [-21.08,+11.25] n=54 G=37 Ge=31.7 | -1.81 [-21.52,+17.89] n=38 G=25 Ge=21.2 | -12.29 [-42.01,+17.43] n=16 G=12 Ge=10.7 UNDERPOWERED |
| [0.75,0.80) | +0.78 [-14.03,+15.59] n=47 G=32 Ge=26.6 | +5.59 [-6.92,+18.10] n=35 G=25 Ge=20.8 | -13.25 [-56.11,+29.62] n=12 G=7 Ge=6.0 UNDERPOWERED |
| [0.80,0.85) | -12.62 [-30.15,+4.90] n=47 G=32 Ge=25.4 | -19.16 [-45.39,+7.07] n=26 G=21 Ge=16.1 UNDERPOWERED | -4.53 [-24.94,+15.88] n=21 G=11 Ge=9.8 UNDERPOWERED |
| [0.85,0.90) | -7.28 [-25.01,+10.45] n=62 G=28 Ge=22.1 | -4.13 [-21.46,+13.21] n=41 G=18 Ge=14.6 UNDERPOWERED | -13.44 [-52.89,+26.00] n=21 G=10 Ge=7.5 UNDERPOWERED |
| [0.90,0.95) | -11.18 [-32.39,+10.03] n=48 G=18 Ge=15.0 UNDERPOWERED | -8.45 [-33.81,+16.90] n=29 G=12 Ge=10.1 UNDERPOWERED | -15.34 [-55.39,+24.71] n=19 G=6 Ge=5.1 UNDERPOWERED |

## Q3. Distance from the centre rung, |line - centre line| (CFB spread, ttk<=360, buy NO)


### Q3. YES mid [0.20,0.30) by distance

| split | ALL | EARLIER (09-03..09-11) | HELD-OUT 09-12 |
|---|---|---|---|
| <3.5 (0..3) | n=0 | n=0 | n=0 |
| 3.5-7 (4..7) | -7.59 [-37.66,+22.47] n=12 G=10 Ge=9.0 UNDERPOWERED | +5.73 [-21.62,+33.07] n=10 G=8 Ge=7.1 UNDERPOWERED | -74.18 [-76.09,-72.28] n=2 G=2 Ge=2.0 UNDERPOWERED |
| 7.5-14 (8..14) | +7.23 [-0.30,+14.76] n=190 G=76 Ge=64.2 | +7.00 [-1.51,+15.51] n=147 G=60 Ge=51.1 | +8.01 [-8.63,+24.66] n=43 G=16 Ge=13.3 UNDERPOWERED |
| >14 (15+) | +6.65 [-0.34,+13.63] n=9 G=6 Ge=3.9 UNDERPOWERED | +5.97 [-2.16,+14.10] n=7 G=4 Ge=2.6 UNDERPOWERED | +9.03 [-6.82,+24.88] n=2 G=2 Ge=2.0 UNDERPOWERED |

### Q3. YES mid [0.10,0.20) by distance

| split | ALL | EARLIER (09-03..09-11) | HELD-OUT 09-12 |
|---|---|---|---|
| <3.5 (0..3) | n=0 | n=0 | n=0 |
| 3.5-7 (4..7) | n=0 | n=0 | n=0 |
| 7.5-14 (8..14) | +3.02 [-5.93,+11.97] n=106 G=58 Ge=43.9 | +2.24 [-8.87,+13.35] n=76 G=45 Ge=33.2 | +5.01 [-9.72,+19.73] n=30 G=13 Ge=11.0 UNDERPOWERED |
| >14 (15+) | +1.99 [-4.62,+8.59] n=241 G=74 Ge=43.3 | +2.37 [-5.15,+9.89] n=201 G=61 Ge=34.0 | +0.04 [-13.15,+13.22] n=40 G=13 Ge=10.4 UNDERPOWERED |
NOTE (Q3): degenerate. 190/211 primary rows are 8-14 pts from the centre and none are <3.5; in [0.10,0.20) all rows are 8+ pts. Cheapness and distance are the same axis on this ladder (a 0.25 rung is ~10 pts from centre, i.e. the market's implied margin sd is ~15 pts), so distance cannot be separated from price here.

### Q3x. YES mid [0.20,0.30) distance x away-dog/fav (all cells shown; most are underpowered)

| split | ALL | EARLIER (09-03..09-11) | HELD-OUT 09-12 |
|---|---|---|---|
| <3.5 (0..3) / away dog | n=0 | n=0 | n=0 |
| <3.5 (0..3) / away fav | n=0 | n=0 | n=0 |
| 3.5-7 (4..7) / away dog | -7.59 [-37.66,+22.47] n=12 G=10 Ge=9.0 UNDERPOWERED | +5.73 [-21.62,+33.07] n=10 G=8 Ge=7.1 UNDERPOWERED | -74.18 [-76.09,-72.28] n=2 G=2 Ge=2.0 UNDERPOWERED |
| 3.5-7 (4..7) / away fav | n=0 | n=0 | n=0 |
| 7.5-14 (8..14) / away dog | +8.26 [+0.74,+15.78] n=175 G=68 Ge=57.9 | +9.02 [+0.96,+17.08] n=139 G=56 Ge=47.7 | +5.33 [-14.72,+25.38] n=36 G=12 Ge=10.5 UNDERPOWERED |
| 7.5-14 (8..14) / away fav | -4.79 [-42.03,+32.45] n=15 G=8 Ge=6.8 UNDERPOWERED | -28.06 [-88.99,+32.87] n=8 G=4 Ge=3.6 UNDERPOWERED | +21.80 [+20.75,+22.85] n=7 G=4 Ge=3.3 UNDERPOWERED |
| >14 (15+) / away dog | +5.34 [-1.31,+12.00] n=8 G=5 Ge=3.2 UNDERPOWERED | +5.97 [-2.16,+14.10] n=7 G=4 Ge=2.6 UNDERPOWERED | +0.94 [-inf,+inf] n=1 G=1 Ge=1.0 UNDERPOWERED |
| >14 (15+) / away fav | +17.11 [-inf,+inf] n=1 G=1 Ge=1.0 UNDERPOWERED | n=0 | +17.11 [-inf,+inf] n=1 G=1 Ge=1.0 UNDERPOWERED |

## Q4. Time to kickoff (CFB spread, YES mid [0.20,0.30), buy NO)


### Q4. by ttk_min of the last quote

| split | ALL | EARLIER (09-03..09-11) | HELD-OUT 09-12 |
|---|---|---|---|
| <=60 | +6.77 [-0.79,+14.32] n=204 G=73 Ge=60.8 | +7.43 [-0.79,+15.65] n=157 G=57 Ge=47.3 | +4.56 [-13.80,+22.92] n=47 G=16 Ge=13.6 UNDERPOWERED |
| 60-360 | -5.52 [-57.40,+46.36] n=7 G=4 Ge=3.8 UNDERPOWERED | -5.52 [-57.40,+46.36] n=7 G=4 Ge=3.8 UNDERPOWERED | n=0 |
| >360 (excluded from primary) | +2.62 [-1.25,+6.50] n=42 G=6 Ge=3.1 UNDERPOWERED | +2.67 [-1.41,+6.74] n=41 G=5 Ge=2.9 UNDERPOWERED | +0.94 [-inf,+inf] n=1 G=1 Ge=1.0 UNDERPOWERED |
| all ttk | +5.74 [-0.57,+12.05] n=253 G=78 Ge=46.6 | +6.04 [-0.60,+12.67] n=205 G=62 Ge=34.8 | +4.48 [-13.49,+22.46] n=48 G=16 Ge=13.9 UNDERPOWERED |
NOTE (Q4): degenerate. 204/211 primary rows have ttk<=60 (151 have ttk<=5), so the 6h window is effectively a 1h window; the 60-360 and >360 cells are 4 and 6 games.

### Q4 finer, <=60

| split | ALL | EARLIER (09-03..09-11) | HELD-OUT 09-12 |
|---|---|---|---|
| <=5 | +5.19 [-3.44,+13.81] n=151 G=57 Ge=46.4 | +3.72 [-6.38,+13.81] n=111 G=43 Ge=34.9 | +9.26 [-7.88,+26.39] n=40 G=14 Ge=11.6 UNDERPOWERED |
| 5-60 | +11.28 [-4.36,+26.92] n=53 G=16 Ge=14.6 UNDERPOWERED | +16.39 [+3.37,+29.41] n=46 G=14 Ge=12.6 UNDERPOWERED | -22.30 [-117.06,+72.47] n=7 G=2 Ge=2.0 UNDERPOWERED |

## Q6. Totals and team totals (ttk<=360, YES mid [0.20,0.30), buy NO)


### Q6. type=total

| split | ALL | EARLIER (09-03..09-11) | HELD-OUT 09-12 |
|---|---|---|---|
| [0.20,0.30) buy NO | -2.96 [-12.11,+6.18] n=215 G=82 Ge=74.9 | -0.97 [-10.59,+8.66] n=166 G=64 Ge=57.6 | -9.72 [-33.07,+13.62] n=49 G=18 Ge=17.3 UNDERPOWERED |
| [0.10,0.20) buy NO | -1.35 [-8.85,+6.16] n=262 G=80 Ge=75.3 | -0.54 [-9.04,+7.95] n=204 G=63 Ge=59.6 | -4.17 [-20.68,+12.34] n=58 G=17 Ge=15.7 UNDERPOWERED |
| [0.30,0.40) buy NO | -6.24 [-16.65,+4.17] n=169 G=82 Ge=75.8 | -7.40 [-19.38,+4.59] n=137 G=64 Ge=59.2 | -1.32 [-21.35,+18.71] n=32 G=18 Ge=17.1 UNDERPOWERED |

### Q6-mirror. type=total, buy YES at ask

| split | ALL | EARLIER (09-03..09-11) | HELD-OUT 09-12 |
|---|---|---|---|
| [0.70,0.80) buy YES | -0.48 [-9.89,+8.94] n=191 G=81 Ge=74.0 | +2.07 [-8.20,+12.34] n=155 G=63 Ge=57.6 | -11.45 [-34.23,+11.34] n=36 G=18 Ge=17.1 UNDERPOWERED |
| [0.80,0.90) buy YES | -4.75 [-13.24,+3.75] n=226 G=80 Ge=69.8 | -5.07 [-14.80,+4.66] n=184 G=63 Ge=56.6 | -3.34 [-20.30,+13.62] n=42 G=17 Ge=13.2 UNDERPOWERED |
| [0.60,0.70) buy YES | +3.76 [-6.10,+13.62] n=162 G=82 Ge=75.8 | +7.51 [-3.19,+18.21] n=122 G=64 Ge=58.6 | -7.68 [-30.54,+15.17] n=40 G=18 Ge=17.4 UNDERPOWERED |

### Q6. type=team_tot

| split | ALL | EARLIER (09-03..09-11) | HELD-OUT 09-12 |
|---|---|---|---|
| [0.20,0.30) buy NO | -10.16 [-19.62,-0.70] n=110 G=64 Ge=56.5 | -9.75 [-21.35,+1.86] n=78 G=47 Ge=41.1 | -11.16 [-27.78,+5.46] n=32 G=17 Ge=15.5 UNDERPOWERED |
| [0.10,0.20) buy NO | -7.24 [-18.20,+3.73] n=48 G=33 Ge=25.6 | -7.45 [-19.26,+4.36] n=42 G=27 Ge=21.0 | -5.76 [-37.83,+26.31] n=6 G=6 Ge=6.0 UNDERPOWERED |
| [0.30,0.40) buy NO | -4.67 [-13.95,+4.61] n=118 G=66 Ge=54.8 | -5.72 [-16.72,+5.28] n=87 G=48 Ge=40.0 | -1.73 [-19.47,+16.01] n=31 G=18 Ge=14.8 UNDERPOWERED |

### Q6-mirror. type=team_tot, buy YES at ask

| split | ALL | EARLIER (09-03..09-11) | HELD-OUT 09-12 |
|---|---|---|---|
| [0.70,0.80) buy YES | -10.85 [-20.34,-1.36] n=94 G=58 Ge=46.5 | -10.92 [-21.49,-0.35] n=73 G=45 Ge=36.8 | -10.59 [-32.77,+11.59] n=21 G=13 Ge=9.8 UNDERPOWERED |
| [0.80,0.90) buy YES | -15.71 [-42.89,+11.47] n=20 G=17 Ge=14.3 UNDERPOWERED | -20.38 [-51.16,+10.40] n=17 G=14 Ge=11.6 UNDERPOWERED | +10.75 [+3.09,+18.42] n=3 G=3 Ge=3.0 UNDERPOWERED |
| [0.60,0.70) buy YES | -10.29 [-20.55,-0.03] n=128 G=68 Ge=56.1 | -9.54 [-20.78,+1.70] n=98 G=52 Ge=42.1 | -12.74 [-37.26,+11.78] n=30 G=16 Ge=14.1 UNDERPOWERED |

### Q6-pooled. spread+total+team_tot, buy NO

| split | ALL | EARLIER (09-03..09-11) | HELD-OUT 09-12 |
|---|---|---|---|
| spread | +6.36 [-1.12,+13.85] n=211 G=76 Ge=63.2 | +6.88 [-1.27,+15.03] n=164 G=60 Ge=49.6 | +4.56 [-13.80,+22.92] n=47 G=16 Ge=13.6 UNDERPOWERED |
| total | -2.96 [-12.11,+6.18] n=215 G=82 Ge=74.9 | -0.97 [-10.59,+8.66] n=166 G=64 Ge=57.6 | -9.72 [-33.07,+13.62] n=49 G=18 Ge=17.3 UNDERPOWERED |
| team_tot | -10.16 [-19.62,-0.70] n=110 G=64 Ge=56.5 | -9.75 [-21.35,+1.86] n=78 G=47 Ge=41.1 | -11.16 [-27.78,+5.46] n=32 G=17 Ge=15.5 UNDERPOWERED |
| all three | -0.77 [-6.31,+4.77] n=536 G=82 Ge=74.9 | +0.51 [-5.69,+6.70] n=408 G=64 Ge=58.0 | -4.84 [-16.99,+7.31] n=128 G=18 Ge=16.9 UNDERPOWERED |
NOTE (Q6): spread-only. Totals: buy-NO at cheap YES is -3c (about the cost of crossing). Team totals: BOTH sides at ~0.75 lose ~10c (buy NO on YES 0.2-0.3: -10.16; buy YES on YES 0.7-0.8: -10.85), i.e. the cheap side of team-total ladders paid out MORE than priced -- the reverse of the spread pattern -- so a venue-wide 'cheap side overpriced' longshot story is not supported. Pooled over the three types the cheap-YES buy-NO is -0.77 [-6.31,+4.77].

## Diagnostics: realised YES frequency vs implied, per bucket (CFB spread, ttk<=360)

| bucket | n | G | mean mid | mean bid | mean ask | realised P(YES) | NO cost (1-bid) | fee |
|---|---|---|---|---|---|---|---|---|
| [0.05,0.10) | 364 | 79 | 0.072 | 0.053 | 0.091 | 0.052 | 0.947 | 0.30c |
| [0.10,0.15) | 206 | 73 | 0.121 | 0.097 | 0.145 | 0.058 | 0.903 | 0.51c |
| [0.15,0.20) | 141 | 70 | 0.173 | 0.158 | 0.189 | 0.142 | 0.842 | 0.79c |
| [0.20,0.25) | 118 | 65 | 0.224 | 0.202 | 0.246 | 0.119 | 0.798 | 0.96c |
| [0.25,0.30) | 93 | 58 | 0.272 | 0.256 | 0.288 | 0.194 | 0.744 | 1.13c |
| [0.30,0.35) | 97 | 67 | 0.324 | 0.310 | 0.339 | 0.299 | 0.690 | 1.28c |
| [0.35,0.40) | 85 | 61 | 0.376 | 0.359 | 0.394 | 0.341 | 0.641 | 1.37c |
| [0.40,0.50) | 180 | 78 | 0.450 | 0.443 | 0.457 | 0.367 | 0.557 | 1.48c |
| [0.50,0.60) | 155 | 73 | 0.544 | 0.534 | 0.554 | 0.432 | 0.466 | 1.49c |
| [0.60,0.65) | 63 | 41 | 0.622 | 0.610 | 0.634 | 0.540 | 0.390 | 1.42c |
| [0.65,0.70) | 47 | 34 | 0.673 | 0.658 | 0.687 | 0.617 | 0.342 | 1.34c |
| [0.70,0.75) | 54 | 37 | 0.723 | 0.705 | 0.741 | 0.704 | 0.295 | 1.24c |
| [0.75,0.80) | 47 | 32 | 0.772 | 0.754 | 0.791 | 0.809 | 0.246 | 1.11c |
| [0.80,0.85) | 47 | 32 | 0.822 | 0.803 | 0.842 | 0.723 | 0.197 | 0.94c |
| [0.85,0.90) | 62 | 28 | 0.878 | 0.866 | 0.890 | 0.823 | 0.134 | 0.69c |
| [0.90,0.95) | 48 | 18 | 0.926 | 0.910 | 0.942 | 0.833 | 0.090 | 0.49c |

## Q2b. Probability gap at MID, (mid - y) x100 pp, clustered (fee-free, spread-free; positive = YES/away side overpriced)

| YES-mid bucket | ALL | EARLIER | HELD-OUT 09-12 | gap / mid (relative, ALL) |
|---|---|---|---|---|
| [0.05,0.10) | +1.97 [-3.16,+7.11] n=364 G=79 Ge=62.4 | +3.02 [-1.48,+7.53] n=291 G=63 Ge=49.8 | -2.22 [-20.58,+16.14] n=73 G=16 Ge=12.7 UNDERPOWERED | +0.27 |
| [0.10,0.15) | +6.28 [+0.63,+11.93] n=206 G=73 Ge=42.0 | +6.06 [-0.58,+12.71] n=165 G=58 Ge=31.1 | +7.15 [-2.73,+17.03] n=41 G=15 Ge=12.5 UNDERPOWERED | +0.52 |
| [0.15,0.20) | +3.14 [-5.92,+12.21] n=141 G=70 Ge=57.3 | +3.88 [-6.10,+13.85] n=112 G=56 Ge=45.8 | +0.31 [-21.71,+22.33] n=29 G=14 Ge=11.5 UNDERPOWERED | +0.18 |
| [0.20,0.25) | +10.50 [+2.70,+18.30] n=118 G=65 Ge=52.0 | +11.43 [+3.15,+19.71] n=91 G=52 Ge=41.2 | +7.37 [-12.89,+27.63] n=27 G=13 Ge=10.9 UNDERPOWERED | +0.47 |
| [0.25,0.30) | +7.86 [-1.93,+17.65] n=93 G=58 Ge=48.3 | +8.09 [-2.97,+19.15] n=73 G=45 Ge=37.3 | +7.03 [-14.78,+28.83] n=20 G=13 Ge=11.1 UNDERPOWERED | +0.29 |
| [0.30,0.35) | +2.54 [-9.93,+15.00] n=97 G=67 Ge=53.2 | +2.66 [-11.42,+16.73] n=74 G=52 Ge=40.9 | +2.15 [-25.44,+29.74] n=23 G=15 Ge=12.3 UNDERPOWERED | +0.08 |
| [0.35,0.40) | +3.52 [-9.54,+16.58] n=85 G=61 Ge=52.7 | +5.14 [-8.96,+19.24] n=68 G=49 Ge=42.8 | -2.97 [-36.09,+30.15] n=17 G=12 Ge=10.0 UNDERPOWERED | +0.09 |
| [0.40,0.50) | +8.33 [-3.12,+19.78] n=180 G=78 Ge=66.9 | +8.03 [-5.12,+21.17] n=141 G=60 Ge=50.3 | +9.41 [-14.42,+33.25] n=39 G=18 Ge=17.1 UNDERPOWERED | +0.19 |
| [0.50,0.60) | +11.16 [-0.91,+23.23] n=155 G=73 Ge=59.6 | +6.53 [-7.52,+20.57] n=111 G=56 Ge=46.8 | +22.85 [+0.03,+45.67] n=44 G=17 Ge=13.8 UNDERPOWERED | +0.21 |
| [0.60,0.70) | +7.10 [-7.76,+21.96] n=110 G=49 Ge=38.8 | -0.48 [-16.73,+15.77] n=74 G=35 Ge=26.6 | +22.69 [-4.90,+50.27] n=36 G=14 Ge=12.2 UNDERPOWERED | +0.11 |
| [0.70,0.80) | -0.63 [-14.01,+12.75] n=101 G=45 Ge=36.3 | -4.84 [-19.08,+9.40] n=73 G=33 Ge=26.5 | +10.34 [-19.67,+40.35] n=28 G=12 Ge=9.8 UNDERPOWERED | -0.01 |
| [0.80,0.90) | +7.39 [-9.13,+23.90] n=109 G=36 Ge=27.7 | +7.91 [-12.50,+28.32] n=67 G=24 Ge=18.0 UNDERPOWERED | +6.55 [-22.50,+35.60] n=42 G=12 Ge=9.8 UNDERPOWERED | +0.09 |
| [0.90,0.95) | +9.28 [-12.06,+30.62] n=48 G=18 Ge=15.0 UNDERPOWERED | +6.29 [-19.35,+31.93] n=29 G=12 Ge=10.1 UNDERPOWERED | +13.84 [-26.19,+53.87] n=19 G=6 Ge=5.1 UNDERPOWERED | +0.10 |

## Centre rung, one row per game (did the away side cover the centre line?)

- all games: away covered centre in 33/83 = 0.398 (binomial 95% [0.292,0.503]); mean centre mid 0.498; mean centre line +22.9
- earlier: away covered centre in 27/65 = 0.415 (binomial 95% [0.296,0.535]); mean centre mid 0.496; mean centre line +24.8
- held-out 09-12: away covered centre in 6/18 = 0.333 (binomial 95% [0.116,0.551]); mean centre mid 0.502; mean centre line +16.0
- away dog: away covered centre in 30/75 = 0.400 (binomial 95% [0.289,0.511]); mean centre mid 0.496; mean centre line +26.6
- away fav: away covered centre in 3/8 = 0.375 (binomial 95% [0.040,0.710]); mean centre mid 0.509; mean centre line -12.5
Centre lines (away +line), by game: -24.5, -24.5, -23.5, -13.5, -4.5, -4.5, -2.5, -2.5, +1.5, +1.5, +2.5, +2.5, +3.5, +5.5, +5.5, +6.5, +6.5, +6.5, +7.5, +7.5, +10.5, +10.5, +10.5, +13.5, +14.5, +14.5, +16.5, +17.5, +17.5, +18.5, +19.5, +20.5, +20.5, +20.5, +21.5, +21.5, +21.5, +22.5, +22.5, +23.5, +23.5, +23.5, +24.5, +24.5, +27.5, +27.5, +27.5, +27.5, +28.5, +28.5, +29.5, +29.5, +30.5, +30.5, +31.5, +31.5, +31.5, +31.5, +33.5, +35.5, +35.5, +35.5, +36.5, +36.5, +37.5, +37.5, +39.5, +40.5, +40.5, +40.5, +41.5, +41.5, +42.5, +42.5, +43.5, +45.5, +46.5, +48.5, +48.5, +50.5, +55.5, +58.5, +59.5

## Ladder geometry (why the mirror bucket has fewer rows)

- ladder extent above centre (pts): median 11, min 0, max 56; below centre: median 57, min 10, max 93
- games with >=1 rung in primary bucket [0.2,0.3): 76 ; in mirror [0.7,0.8): 45 ; rungs per game primary 2.54, mirror 1.22
- YES-mid at the highest line rung: median 0.755 (min 0.455); at the lowest line rung: median 0.015 (max 0.260)
- lines are quoted from -34.5 to +59.5; per-game line span median 69 pts

## PIT: realised margin vs the market's ladder-implied distribution, one u per game

For each game, F(m) = P(away margin <= m) from the ladder: YES-mid at line L = P(M + L > 0) = P(M > -L), so F(-L) = 1 - mid. Realised M is bracketed by the y flip (y=1 iff L > -M). u = F at realised M (midpoint of bracket, linear interpolation in the ladder; clipped to the ladder edge if unbracketed). Calibrated market => u ~ U(0,1). Mean u < 0.5 => away did worse than priced (shift). Hump (too many u in the middle) => market over-dispersed = both tails overpriced (longshot/tails story). U-shape => under-dispersed.
- games: 83; ladders with a non-monotone y (inconsistent settlement): 0; realised margin outside the ladder: 30
- clipped games: 30 = 28 all-NO ladders (home won by MORE than the ladder's top line; true u <= clip) + 2 all-YES ladders (away beat the bottom line; true u >= clip). Clip values for the all-NO games: 0.120, 0.170, 0.190, 0.195, 0.235, 0.355, 0.385, 0.385, 0.385, 0.385, 0.435, 0.435, 0.440, 0.465, 0.465, 0.465, 0.475, 0.485, 0.488, 0.490, 0.495, 0.495, 0.495, 0.505, 0.515, 0.530, 0.530, 0.545
- all-NO games whose clip value lands INSIDE [0.25,0.75): 23 -- their true u is unknown below the clip, so the centre fraction is only bounded, and mean u is an UPPER bound.
- deciles of u (all 83): [4, 5, 8, 11, 17, 11, 6, 11, 5, 5]; frac u<0.5 = 0.542 (centre rung said away covered 0.398, i.e. frac u<0.5 should be ~0.60); median u = 0.490
- VERDICT on the PIT dispersion test: NOT USABLE on this ladder. Bounds on the centre fraction are [0.386, 0.663] (all clipped-in-band games as tails / as centre), which straddle 0.50. The upper tail u>=0.75 IS clean (only 2 games clipped high and they count as tail): 14/83 = 0.169 vs 0.25 expected, binomial SE 0.048 -> the away-good tail beyond the market's 75th percentile came in thin by ~8pp (z ~ -1.7). The lower tail is unbounded by the ladder.
- centre fraction EXCLUDING clipped games: 32/53 = 0.604  (conditional on being inside the ladder, so not a clean uniform test; shown for the reader)
- centre fraction treating every clipped game as a TAIL (lower bound on over-dispersion): 32/83 = 0.386, binomial SE 0.055

| games | n | mean u [95%] (0.5 = no shift; <0.5 away underperformed) | quintile counts of u | frac in [0.25,0.75) (0.50 = calibrated dispersion; >0.5 = market over-dispersed) | frac u<0.25 / u>=0.75 | KS D |
|---|---|---|---|---|---|---|
| all | 83 | 0.503 +-0.050 | [9, 19, 28, 17, 10] | 0.663 +-0.102 | 0.169 / 0.169 | 0.135 (crit .05 ~ 0.149) |
| earlier | 65 | 0.514 +-0.055 | [7, 12, 24, 14, 8] | 0.677 +-0.114 | 0.154 / 0.169 | 0.171 (crit .05 ~ 0.169) |
| held-out 09-12 | 18 | 0.462 +-0.120 | [2, 7, 4, 3, 2] | 0.611 +-0.225 | 0.222 / 0.167 | 0.172 (crit .05 ~ 0.321) |
| away dog | 75 | 0.515 +-0.051 | [7, 17, 26, 16, 9] | 0.693 +-0.104 | 0.147 / 0.160 | 0.153 (crit .05 ~ 0.157) |
| away fav | 8 | 0.394 +-0.209 | [2, 2, 2, 1, 1] | 0.375 +-0.335 | 0.375 / 0.250 | 0.235 (crit .05 ~ 0.481) |

total: ladders 83, usable 83, inconsistent 0, clipped 15, orientation used {1: 83} (+1 = YES is over). Sample slugs: ['tsc-cfb-tarl-bowlgr-2026-09-05-total-26pt5', 'tsc-cfb-tarl-bowlgr-2026-09-05-total-28pt5']

| ladders | n | mean u | quintiles | frac centre | low/high | KS D |
|---|---|---|---|---|---|---|
| total all | 83 | 0.523 +-0.058 | [18, 10, 15, 26, 14] | 0.530 +-0.107 | 0.217 / 0.253 | 0.105 (crit .05 ~ 0.149) |
| total earlier | 65 | 0.527 +-0.063 | [13, 7, 14, 22, 9] | 0.554 +-0.121 | 0.200 / 0.246 | 0.117 (crit .05 ~ 0.169) |
| total held-out | 18 | 0.509 +-0.140 | [5, 3, 1, 4, 5] | 0.444 +-0.230 | 0.278 / 0.278 | 0.123 (crit .05 ~ 0.321) |

team_tot: ladders 158, usable 154, inconsistent 0, clipped 89, orientation used {1: 154} (+1 = YES is over). Sample slugs: ['tsc-cfb-tarl-bowlgr-2026-09-05-tt-bowlgr-19pt5', 'tsc-cfb-tarl-bowlgr-2026-09-05-tt-bowlgr-22pt5']

| ladders | n | mean u | quintiles | frac centre | low/high | KS D |
|---|---|---|---|---|---|---|
| team_tot all | 154 | 0.499 +-0.032 | [7, 54, 38, 46, 9] | 0.812 +-0.062 | 0.078 / 0.110 | 0.177 (crit .05 ~ 0.110) |
| team_tot earlier | 118 | 0.499 +-0.036 | [6, 42, 28, 35, 7] | 0.805 +-0.071 | 0.085 / 0.110 | 0.173 (crit .05 ~ 0.125) |
| team_tot held-out | 36 | 0.502 +-0.067 | [1, 12, 10, 11, 2] | 0.833 +-0.122 | 0.056 / 0.111 | 0.212 (crit .05 ~ 0.227) |

## One row per game: away-cover rate at three rungs (binomial CI, games independent)

| rung (nearest YES-mid, within 0.05, ttk<=360) | away covered | rate [95%] | priced | note |
|---|---|---|---|---|
| 0.25 rung = the primary bucket, one row per game | 11/76 | 0.145 [0.066,0.224] | ~0.25 | quoted in 76/83 games |
| centre rung | 33/83 | 0.398 [0.292,0.503] | ~0.50 | clean: quoted in every game |
| 0.75 rung = the mirror, one row per game | 31/42 | 0.738 [0.605,0.871] | ~0.75 | quoted in 42 games only (closer games, see Q1b note) |

## Realised P(YES) vs mean mid by bucket and market type (ttk<=360, fills-weighted, no CI -- shape only)

| type | YES-mid bucket | n | ladders | mean mid | realised P(YES) | gap pp (mid - realised) |
|---|---|---|---|---|---|---|
| spread | [0.05,0.10) | 364 | 79 | 0.072 | 0.052 | +2.0 |
| spread | [0.10,0.20) | 347 | 76 | 0.142 | 0.092 | +5.0 |
| spread | [0.20,0.30) | 211 | 76 | 0.245 | 0.152 | +9.3 |
| spread | [0.30,0.40) | 182 | 74 | 0.349 | 0.319 | +3.0 |
| spread | [0.40,0.60) | 335 | 82 | 0.493 | 0.397 | +9.6 |
| spread | [0.60,0.70) | 110 | 49 | 0.644 | 0.573 | +7.1 |
| spread | [0.70,0.80) | 101 | 45 | 0.746 | 0.752 | -0.6 |
| spread | [0.80,0.90) | 109 | 36 | 0.854 | 0.780 | +7.4 |
| spread | [0.90,0.95) | 48 | 18 | 0.926 | 0.833 | +9.3 |
| total | [0.05,0.10) | 96 | 59 | 0.077 | 0.062 | +1.5 |
| total | [0.10,0.20) | 262 | 80 | 0.145 | 0.141 | +0.4 |
| total | [0.20,0.30) | 215 | 82 | 0.246 | 0.247 | -0.1 |
| total | [0.30,0.40) | 169 | 82 | 0.349 | 0.385 | -3.6 |
| total | [0.40,0.60) | 309 | 82 | 0.500 | 0.544 | -4.3 |
| total | [0.60,0.70) | 162 | 82 | 0.651 | 0.716 | -6.5 |
| total | [0.70,0.80) | 191 | 81 | 0.751 | 0.775 | -2.4 |
| total | [0.80,0.90) | 226 | 80 | 0.850 | 0.823 | +2.7 |
| total | [0.90,0.95) | 83 | 51 | 0.920 | 0.928 | -0.8 |
| team_tot | [0.05,0.10) | 14 | 10 | 0.079 | 0.214 | -13.5 |
| team_tot | [0.10,0.20) | 48 | 39 | 0.158 | 0.146 | +1.2 |
| team_tot | [0.20,0.30) | 110 | 91 | 0.252 | 0.273 | -2.1 |
| team_tot | [0.30,0.40) | 118 | 102 | 0.349 | 0.339 | +1.0 |
| team_tot | [0.40,0.60) | 204 | 130 | 0.495 | 0.544 | -4.9 |
| team_tot | [0.60,0.70) | 128 | 100 | 0.653 | 0.633 | +2.1 |
| team_tot | [0.70,0.80) | 94 | 79 | 0.738 | 0.723 | +1.5 |
| team_tot | [0.80,0.90) | 20 | 19 | 0.831 | 0.750 | +8.1 |
NOTE: on spreads the YES (away) side under-performed its mid in EVERY bucket except [0.70,0.80): +2.0, +5.0, +9.3, +3.0, +9.6, +7.1, -0.6, +7.4, +9.3 pp. The gap is as large at the CENTRE (+9.6pp at [0.40,0.60)) as at the primary rung (+9.3pp). Totals and team totals show no such pattern. Team-tot PIT above has 89/154 ladders clipped and is not interpretable.

## NFL
NFL spread rows in file: 72, games 2. Not analysed (G far below 25).
