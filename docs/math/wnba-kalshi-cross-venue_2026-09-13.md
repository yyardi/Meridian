# Kalshi WNBA: do the two Polymarket pregame-ladder biases replicate?

Date 2026-09-13. Read-only prod. Scripts: scratchpad/kalshi_wnba{,2,3,4}.py, raw outputs kalshi_wnba_out*.txt.
Estimator everywhere: the specified game-clustered sandwich (cluster = game_key); "mean [lo, hi] n G G_eff". Fees: Kalshi 0.07·p(1−p), Polymarket 0.06·p(1−p) (docs/math/longshot-no-candidate.md). Close = last snapshot < game_start_time within 6h.

## Headline (5 lines)
1. **A (totals): SAME DIRECTION.** Kalshi UNDER (NO@1−bid, every rung) **+8.91c [+0.85, +16.97]** n=675 G=75; OVER (YES@ask) **−12.99c [−21.05, −4.93]**; over settles **10.95c** less often than priced [−19.01, −2.89], negative in all 8 mid buckets (−5.6 … −16.3c).
2. **But it is the same price on the same games.** Kalshi's close equals Polymarket's to within a tick (median |Δmid| 0.00c winners/spreads, 0.50c totals; 375 matched rungs, 375/375 settle identically). On the 160 total rungs both venues list, UNDER is +9.08c (Kalshi) vs +9.06c (Polymarket). Kalshi adds **zero independent evidence** on A; it shows the bias lives in the shared price (crowd / market-wide), not in a venue engine.
3. **B (spreads, YES-mid 0.8–1.0): UNDERPOWERED on Kalshi's own frame** (n=28–29, G=13–14: Kalshi's YES is always "TEAM wins by over X", so only heavy favourites' 1.5/3.5 rungs reach 0.8). The frame-equivalent bet ("favourite does not lose by more than X" = NO on "DOG wins by over X", YES-mid ≤ 0.2) is **+3.70c [−3.10, +10.50]** n=139 G=66 — same sign, interval contains 0 and +5.78: uninformative, not contrary.
4. **B decomposes into an away-favourite slice on BOTH venues.** Polymarket's mid-0.8+ universe in these 75 games is 100% "away favourite does not lose by > L" (89 rungs/35 games, +5.22c [+2.12, +8.32]) because its slugs are away-referenced; its own home-favourite twin (NO on 'away −L' at mid ≥ 0.8) is **−2.51c [−10.09, +5.07]** n=118 G=39, pooled both sides **+0.81c [−3.75, +5.37]** n=207 G=74. Kalshi: away-fav games +10.9c (60/60 rungs won — degenerate CI), home-fav games **−1.78c [−13.42, +9.87]** n=79 G=35. "Favourites underpriced at the top" is a listing-frame selection (away-referenced ladder), not a favourite effect and not a venue effect.
5. **Regime, not structure, is the live alternative for A**: actual total − ladder-implied median = **−3.89 pts** (se 1.64), 49/75 under (p=0.011); Aug 5–18: −5.40, 26/37 (p=0.02); Aug 19–30: −2.42, 23/38 (p=0.26); by week −3.7/−6.4/+0.4/−6.4. The 13 Polymarket games *before* Kalshi's tape (Jul 31–Aug 4) ran the other way: UNDER −15.58c n=117 G=13. The clustered CI treats 75 games as independent and cannot price a calendar-level shock.

## Provenance check (reproduces the parent's numbers exactly)
Same close/fee conventions on all 88 Polymarket WNBA events: UNDER **+5.40c [−2.24, +13.04]** n=792 G=88; OVER **−10.63c [−18.28, −2.97]**; spreads mid 0.8–1.0 YES@ask **+5.78c [+2.96, +8.60]** n=101 G=40 G_eff=31.4. Split: in-window 75 games UNDER +9.03c [+1.13, +16.94]; out-of-window 13 games −15.58c [−37.40, +6.25] (G=13, underpowered). B in-window +5.22c n=89 G=35; out-of-window +9.96c n=12 G=5.

## Substrate and controls
- kalshi_games wnba: 75 games, 2026-08-05..08-30, all with polymarket_event_slug + game_start_time. Tape per game runs −359 min … −0.5 min before start; never past tip. Close age: median 0.48 min, max 1.1 min.
- **Kalshi `result` is populated on 0 of 530,061 WNBA snapshot rows** (NULL or ''); `raw` is null. The requested "verify frame on rows with a populated result" cannot be done: agreement count 0/0. Settled instead from ESPN `team_game_logs` (all 75 games matched, 1 candidate each).
- Home/away: Kalshi `second_code` is ESPN `is_home` in **75/75**, `first_code` in 0/75. Polymarket slug order away-home confirmed: `aec` (winner) settles YES iff away(first) wins **75/75**.
- Score cross-check: `resolved_outcomes` carries final scores for only **38/75** events; those 38 agree with ESPN **38/38**.
- Polymarket frames vs ESPN scores: `tsc` YES iff total > line **675/675**; `asc` YES iff away margin + line > 0 **600/600**.
- Kalshi frames: `rules_primary` explicit ("more than X points"; spread "TEAM wins by more than X"); ticker suffix number − 0.5 == floor_strike **1437/1437**; suffix code ∈ game codes **912/912**; `yes_sub_title` names the suffix team **912/912**. Polymarket settlement == ESPN-settled Kalshi analogue on every matched rung **375/375**.
- Calibration control (would show rate ≈ 1−mid if a frame were inverted): monotone increasing in all three types. Totals: bucket mid→rate 0.1→0.06, 0.2→0.15, 0.3→0.23, 0.4→0.32, 0.5→0.39, 0.6→0.58, 0.7→0.65, 0.8→0.77.

## Coverage, spread, cross-venue agreement
| type | contracts | usable close (bid>0, ask<1) | games | Kalshi median half-spread | Polymarket median half-spread |
|---|---|---|---|---|---|
| winner | 150 | 150 | 75 | 0.50c | 0.50c |
| spread | 762 | 762 | 75 | 0.50c | 1.00c |
| total | 675 | 675 | 75 | 0.50c | 1.00c |

Closing price range across all 1,587 contracts: bid 0.01–0.94, ask 0.02–0.95 (Kalshi lists no rung beyond ~0.95).
Mid agreement on identical rungs (game+type+strike, flip applied for Polymarket pos-L spreads): winner n=75 median|Δ|=0.00c mean|Δ|=0.29c; spread n=140 median 0.00c mean 0.37c; total n=160 median 0.50c mean 0.50c; signed mean (K−P) ≤ 0.42c in every bucket. Only 160/675 totals and 140/598 spreads match exactly because both venues list 3-point ladders with a per-game phase that differs (Kalshi e.g. 152.5,155.5,…; Polymarket 151.5,154.5,… or offset); Kalshi spread rungs alternate sides (DAL2, WSH2, WSH4, DAL5, WSH7, DAL8, WSH10, DAL11, DAL14).

## A. Totals (Kalshi), by YES-mid bucket
| mid | UNDER NO@1−bid | OVER YES@ask | y − mid | n | G | G_eff |
|---|---|---|---|---|---|---|
| all | +8.91 [+0.85, +16.97] | −12.99 [−21.05, −4.93] | −10.95 [−19.01, −2.89] | 675 | 75 | 75.0 |
| 0.1–0.2 | +9.85 [−1.70, +21.41] | −12.96 | −11.38 | 17 | 14 | 11.6 UNDERPOWERED |
| 0.2–0.3 | +8.16 [−0.42, +16.74] | −11.89 [−20.45, −3.32] | −10.00 | 110 | 71 | 64.4 |
| 0.3–0.4 | +10.35 [+0.83, +19.87] | −14.60 [−24.13, −5.07] | −12.46 | 110 | 75 | 67.2 |
| 0.4–0.5 | +10.33 [−1.05, +21.71] | −14.83 [−26.21, −3.44] | −12.58 | 93 | 74 | 66.0 |
| 0.5–0.6 | +14.09 [+2.98, +25.20] | −18.58 [−29.70, −7.47] | −16.34 | 101 | 75 | 66.7 |
| 0.6–0.7 | +4.61 [−6.77, +15.99] | −8.84 [−20.22, +2.53] | −6.74 | 115 | 75 | 67.8 |
| 0.7–0.8 | +7.73 [−3.98, +19.44] | −11.43 [−23.14, +0.28] | −9.60 | 103 | 71 | 63.5 |
| 0.8–0.9 | +3.97 [−12.95, +20.89] | −7.10 [−24.02, +9.83] | −5.56 | 26 | 23 | 19.9 UNDERPOWERED |

Polymarket, same 75 games: UNDER +9.03c [+1.13, +16.94]; OVER −14.44c [−22.34, −6.54]; y−mid −11.73c [−19.63, −3.83]. Kalshi UNDER on rungs Polymarket does NOT list: +8.86c [−0.15, +17.88] n=515 G=59.
Date halves (Kalshi UNDER): Aug 5–18 +12.48c [+1.94, +23.01] n=333 G=37; Aug 19–30 +5.45c [−6.75, +17.64] n=342 G=38. Largest game misses: ATL/LA 08-24 imp 181.3 act 149; CHI/NY 08-29 181.3→151; WSH/PDX 08-23 166.6→205; ATL/LA 08-20 180.6→212.

## B. Spreads (Kalshi)
| selector | bet | mean | n | G | G_eff |
|---|---|---|---|---|---|
| all rungs | YES@ask | −1.04 [−5.07, +2.99] | 762 | 75 | 73.9 |
| all rungs | NO@1−bid | −2.63 [−6.64, +1.39] | 762 | 75 | 73.9 |
| yes_ask ∈ [0.80, 1.00) | YES@ask | −4.37 [−27.08, +18.35] | 29 | 14 | 12.6 UNDERPOWERED |
| same | NO@1−bid (mirror) | +1.58 [−21.04, +24.19] | 29 | 14 | UNDERPOWERED |
| mid ∈ [0.80, 1.00] (Polymarket selector) | YES@ask | −5.20 [−28.70, +18.30] | 28 | 13 | 11.9 UNDERPOWERED |
| yes_ask ≤ 0.20 (mirror rungs) | YES@ask | −3.81 [−9.26, +1.64] | 203 | 75 | 65.3 |
| yes_ask ≤ 0.20 | NO@1−bid | +1.14 [−4.31, +6.60] | 203 | 75 | 65.3 |
| mid ≤ 0.20 | NO@1−bid | +1.23 [−4.21, +6.66] | 204 | 75 | 65.4 |
| DOG rungs, mid ≤ 0.2 ("fav does not lose by > X") | NO@1−bid | +3.70 [−3.10, +10.50] | 139 | 66 | 53.2 |
|   … away-favourite games (Polymarket B's universe) | NO@1−bid | +10.92 [+9.25, +12.59] — 60/60 won, CI degenerate | 60 | 31 | 23.7 UNDERPOWERED |
|   … home-favourite games | NO@1−bid | −1.78 [−13.42, +9.87] | 79 | 35 | 29.6 |
|   … mid ∈ [0.1, 0.2] only | NO@1−bid | +8.91 [+2.95, +14.87] | 80 | 57 | 50.8 |
|   … mid < 0.1 only | NO@1−bid | −3.36 [−15.06, +8.34] | 59 | 30 | 22.5 UNDERPOWERED |
| FAV rungs, mid ≥ 12.5 strikes ("dog stays within X") | NO@1−bid | −4.07 [−14.70, +6.56] | 65 | 55 | 48.6 |

By YES-mid bucket (all spread rungs, YES@ask): 0.0 +0.97; 0.1 −5.87 [−11.54, −0.20]; 0.2 −4.40; 0.3 +3.00; 0.4 +1.08; 0.5 −1.76; 0.6 +0.56; 0.7 **+15.15 [+5.45, +24.85]** (n=34 G=28 — one bucket of ten, neighbours ≈0, do not read); 0.8 −4.20 (G=13); 0.9 −8.87 (G=5).
Closing favourite: away in 36 games (won 23), home in 39 (won 30). Only 10 of Polymarket's 89 B rungs have an exact Kalshi twin (strike-phase mismatch); on those 10 Kalshi NO@1−bid is −6.82c (G=6, meaningless).

Polymarket, same 75 games, both frames of "favourite does not lose by more than L": away-fav YES on 'away +L' mid ≥ 0.8 **+5.22 [+2.12, +8.32]** n=89 G=35; home-fav NO on 'away −L' mid ≥ 0.8 **−2.51 [−10.09, +5.07]** n=118 G=39; pooled **+0.81 [−3.75, +5.37]** n=207 G=74 G_eff=60.6.

## Winner (context)
YES@ask all 150 tickers −2.12c [−2.23, −2.01] (that is the fee+spread, variance across sides cancels); favourite YES@ask −0.96c [−10.84, +8.91] n=75 G=75.

## What this says
- A: crowd/market-wide, not venue-engine — the two venues quote the same ladder to a tick and the under-bias is in that shared price; but the Kalshi "replication" is the same 75 games at the same prices and adds no independent power. The sign flipped in the 4 days before the tape and in 1 of 4 weeks inside it; treat as a late-August-2026 regime until it survives a different month.
- B: not a favourite effect and not a venue effect — a listing-frame selection (Polymarket's away-referenced ladder can only express "favourite stays within L" as a YES ≥ 0.8 rung when the favourite is the away team). The home-favourite twin is ≤ 0 on both venues; pooled ≈ 0.
- Costs: identical prices, Kalshi 0.07 vs 0.06 fee (~0.2c/contract at p≈0.5), Kalshi books 1c wide on every rung vs 2c on Polymarket spreads/totals.
