# Research brief for outside reviewers — Meridian, 2026-09-13 (evening UTC)

One file: what the venue is, what we record, every strategy tested with its number, what is
running on paper right now, and the open questions where advice changes what we do next.
Every number is a backtest on recorded venue prices, settled by the venue's own settlement
endpoint unless stated, game-clustered (sandwich), 95% interval, G = games. G < 25 is
UNDERPOWERED and is reported, not dropped. Nothing has ever been traded with money.

## 1. The venue and the tape

- Polymarket US (api.polymarket.us), CFTC-regulated binaries, $1 contracts, taker fee
  0.06·p·(1−p) per contract per side (verified against the venue; no maker rebate, maker fee 0).
  Round trip at 50¢ = 3.0¢ = 6.0% of the ticket; at 80¢ = 1.92¢ = 2.4%; at 20¢ = 1.92¢ = 9.6%.
- Market families per game: winner, spread ladder (every rung), total ladder, team totals,
  quarter/half markets. Slug is `<away>-<home>`; **YES is always the away side on every rung**
  (196/196 spread rows: YES = away margin + line > 0). Any price-bucket effect is therefore
  confounded with "away team" until split by side and checked against its home-referenced twin.
- Recorded on AWS since Aug (WNBA), 09-03 (CFB), 09-02 (NFL), 09-12 (Kalshi CFB/NFL, 72 h
  pregame window; DraftKings line path 7 days ahead, change-detected), MLB overlay ready 09-13.
  Pregame boards: full ladders every 15–60 min. In-game: 0.5–1 s poll, change-detected writes
  (winner market ≈ one tick per 8 s during NFL play). ESPN play-by-play with possession,
  yards-to-goal, down, clock, win probability for CFB/NFL; injuries and box scores for WNBA.
- Second venue: Kalshi (same games, 7% fee formula), pregame only.

## 2. Tested and measured negative with power (do not reopen without a new mechanism)

| idea | number | G |
|---|---|---|
| Market making at the touch, join after every play | −0.82¢/fill markout [−1.26, −0.37] | 37 |
| Making only after a ≥1¢ move, on its side | −1.17¢ [−1.89, −0.46] (an earlier +3.58¢ was a one-minute look-ahead, retracted) | 43 |
| Shadow maker, 3 leagues, 169k paper fills | −2.2% ROI in-game [−3.8, −0.6]; −4.1% pregame | 149 |
| In-game WP model (XGB) vs venue mid, taker, net of fee | never positive; venue prices NFL/CFB off DraftKings within 0.3¢ | — |
| NFL WP head vs nflfastR | +0.0007 Brier [−0.0044, +0.0059]: equal to the public model | — |
| Pregame softness vs DraftKings close (Polymarket, Kalshi) | +0.26¢, +0.20¢, −0.18¢, all span 0 | — |
| Chasing a ≥1¢ move | Polymarket continues +0.53¢ gross, loses net of fee; Kalshi reverts ~6% | — |
| PULSE (WNBA in-game directional loop) | 57 fills, below its 100-fill floor; the "ride the tail" branch is where the losses sit | — |

## 3. Paper lines alive (scored weekly by `cfb/run_paper_book.py`, venue-settled, fee charged)

| line | bets | G | net per $1 | 95% CI on the mean bet (¢) | verdict |
|---|---|---|---|---|---|
| CFB spreads: buy NO on rungs whose YES mid is 20–30¢ | 289 | 107 | +0.071 | +5.44 [−1.46, +12.35] | spans 0; read 09-19 |
| CFB: home side, every rung | 2,503 | 117 | +0.030 | +1.90 [−3.83, +7.62] | spans 0; read 09-19 |
| WNBA totals: UNDER every rung | 792 | 88 | +0.106 | +5.52 [−2.10, +13.15] | spans 0; late-Aug regime; playoffs |
| WNBA spreads: favourites 80–100¢ | 101 | 40 | +0.063 | +5.78 [+2.96, +8.60] | excludes 0 BUT home twin −2.05 [−8.27, +4.16]: away-listing artifact |
| NFL, same two CFB rules | 70 | 2 | −0.46 | — | UNDERPOWERED |
| CFB/NFL totals under and over every rung | registered 09-13 | | | | back-read pending |
| MLB: totals, favourite/dog, 20–30¢ NO, first-five totals/spread | registered 09-13 | | | | no tape yet |

Decomposition of the CFB 20–30¢ line (09-13): the "cheap ticket" and "away underdog" are one
variable on a tape that is 90% away underdogs; the effect is consistent with a ~4-point
whole-ladder home shift in CFB weeks 1–2 (or a 1.9σ draw). Centre-rung away cover rate 33/83.

## 4. Reads that ran tonight (09-13) — filled in as they land

- **In-game momentum scalp (the operator's rule, done, `cfb/run_momentum_scalp.py`, CFB 60 games):**
  buy the offence at the opponent's 40 (T1), the red zone (T2), or after a ≥2¢ move (T3); take
  profit 2/5/10%, stop 5/10/20%; taker and maker exits; 3 s latency. Every one of 27 cells nets
  −7.2 to −11.0¢ per $1 ticket with the 95% game-clustered interval entirely below zero (G 37–42),
  home and away twins both negative. Exact decomposition: mid drift after the trigger ≈ 0
  (−0.6 to +0.7¢) in every cell; the loss is half-spreads paid (3.8–5.7¢, wide books at stop and
  drive-end ticks) plus two taker fees (4.1–5.4¢). Maker exit within 0.3¢ of taker. Holding to
  settlement: no interval (G 16). NFL: no finals yet. Measured negative with power: the venue
  already prices field position; the rule buys the spread and the fee.

- **CFB 20–30¢ NO decomposed (done, `cfb/run_longshot_decomp.py`, 117 games):** the +5.44¢ is
  carried by away-underdog games (+7.83 [+1.03, +14.64], G 94); 102 of 115 games are away
  underdogs, so "away" and "underdog" are one variable. The one cell excluding zero is
  **buy AWAY at YES-mid 50–60¢: −11.62¢/contract [−21.74, −1.50], n 227, G 104** (one of ~20 cells
  looked at, and ~10 distinct statistics — each appears once as a cell and once as a mirror's twin).
  Its home twin is **+1.97¢ [−7.65, +11.59], n 282, G 113**, a null. **The pair is one measurement
  and one null, not symmetric evidence of a home edge**; an earlier draft of this brief said "home
  beats at every rung and away loses at every rung" as though those were two findings. What is
  established is that the AWAY side is expensive at coin-flip rungs. Not a longshot effect. **The measurement reproduces**: independent SQL returns the same 227 rungs
  and 104 games, the venue settled 227/227, and the 65 rungs with an ESPN final agree 65/65 under
  the stated frame. **What the audit corrected was what I did with it:** the registered fade is the exact
  complement of that cell (same 227 rows, other side), so its in-sample expectation is
  +11.62 − 4.17 round-trip = +7.45¢ [−2.67, +17.57], spanning zero, and it inherits the source's
  standard error. The source was one of ≥10 statistics; at 20 looks the expected number of false
  "excludes zero" results is exactly 1.00, so one such result is the modal outcome of noise.
  Readable at G ≥ 195 (5 Saturdays uncorrected, 12 corrected), not on 09-19.
  NO-mid re-definition selects the same rungs to the boundary (venue publishes one YES book).
- **Kalshi vs Polymarket same instant (done for A/B, CFB 09-12, 45 matched games, 66k pairs):**
  median |gap| 0.25¢ (winner) to 0.5¢ (spread, total); < 1% of instants beyond 3¢; 49 after-fee
  dutch instants in 66k (0.07%). Who-is-stale: episodes too rare on one Saturday (G 6–7), the
  median > 3¢ gap persists unchanged at the next sweep. No pregame cross-venue trade exists on
  this tape. Kalshi's own 20–30¢ rung (C, 36 games, fee 0.07·p(1−p)): −2.33¢/$1 [−13.31, +8.66]
  pooled, away −3.15 [−22.30, +16.00] (G 18), home −1.75 [−16.33, +12.84] (G 35): loses about
  the fee; nothing supports moving the CFB line to Kalshi. Script `cfb/run_cross_venue.py`.
- **DraftKings move → venue lag (pregame, CFB 09-12, 23 settled games):** census 15 spread / 10
  total moves ≥ 0.5 pt; venue lags DK by a median 30 min (q25 20, q75 65, n 19; sweep cadence
  ≈ 68 min so an upper bound); 5 of 24 moves were already at the implied price. Taking the
  DK-implied rung at the venue ask, net of fee: −9.2¢/$1 [−30.7, +12.3] at the first sweep,
  −13.0 at +1 h, −24.5 [−46.7, −2.4] at +3 h; all UNDERPOWERED (G 14–15). Directional: the lag is
  real, the crossing cost plus fee exceeds it. Frame audit pending; NFL settles tonight.

## 5. Running on paper from the next deploy

- `core/gridiron/scalp.py`: the operator's rule live on paper for NFL and CFB (trigger, TP,
  stop, size from env; `paper_scalps` table; reads only the recorded tape, opens no venue socket).
- MLB recorder (pregame ladders, ~55 events/day) + a daily 10:40Z MLB paper book and ladder
  calibration; 100 settled games in about a week.
- Cricket / table tennis: venue discovery in progress (the operator saw ENG v SL priced 50/50
  pregame and 80% minutes later; the UI presentation is suspected wrong). Recorder next, then a
  fair-value model from ESPNcricinfo data.

## 6. Where advice changes what we do

1. Edge × volume: at $25 a bet and single-digit-cent edges, $500/week needs ~$7–10k staked a
   week. Which of the lines above deserves size first, and what stops a 3-Saturday CFB read
   from being a multiple-comparisons artifact (≈40 buckets have been looked at)?
2. Away-team confound: is there a cleaner design than the home-referenced twin for a venue
   where YES is always the away side?
3. In-game: the venue prices football off DraftKings within 0.3¢; where, if anywhere, does
   public play-by-play beat that (timeouts, injuries, weather, red-zone sequences)?
4. Cross-venue: Kalshi reverts after moves, Polymarket continues. Is there a fee-clearing
   dutch or lag trade between them, and how would you size it?
5. Niche markets (cricket, table tennis): how would you model fair value fast enough to be
   useful, and what is the right test that the crowd is wrong rather than early?

Details: `STATUS.md`, `docs/RESEARCH_REPORT_2026-09-13.md`, `docs/math/longshot-no-candidate.md`,
`docs/math/longshot-no-decomposition_2026-09-13.md`, `docs/ARCHITECTURE.md`.
