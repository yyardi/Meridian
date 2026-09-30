# Niche leagues against Kalshi: does the BTC arm's rule carry over?

2026-09-30 ~01:30Z. The Kalshi-anchored taker on Bitcoin buys the venue when Kalshi's
same-window mid clears the venue's ask plus the fee by a margin. This asks whether the
venue's long-tail sports offer the same trade. There are two reads.

## 1. Pregame snapshot (`analysis/thin/cross_venue_snapshot.py`)

The venue lists 130 leagues with open events. 29 were checked against a Kalshi twin
series, and 20 of them paired. For each game, the Kalshi event must be on the same US-Eastern date (±1 day), and
both team names must match in full, one to one. Team codes are never used, because the
venues disagree: the venue's `prs` is Paris, and Kalshi's `KPB` is Partizan. Up to 12
games per league were sampled, with the venue book and Kalshi market read about a second
apart.

| league | paired | Kalshi ≤ 3¢ wide | median Kalshi width | median venue width | median gap at the mid (tight pairs) |
|---|---:|---:|---:|---:|---:|
| ATP / WTA | 12 / 12 | 12 / 12 | 1¢ | 1¢ | 0.0¢ |
| ITF men / women | 12 / 12 | 10 / 7 | 2–3¢ | 1¢ | 0.5¢ |
| UFC | 12 | 12 | 1¢ | 1¢ | 1.0¢ |
| CS2 / Dota 2 / Valorant / LoL | 12 / 12 / 6 / 12 | 6 / 8 / 6 / 5 | 1–22¢ | 1–10¢ | 0.5–1.0¢ |
| KBO / EuroLeague / EuroCup | 7 / 12 / 9 | 4 / 7 / 6 | 1–3¢ | 2–5¢ | 0.5¢ |
| VTB | 3 | 2 | 2¢ | 10¢ | 4.5¢ |
| NPB, LNBP, BBL, Liiga, NBL, OW, KHL | 2–12 each | 0–3 each | 5–85¢ | 8–95¢ | — |

Of 174 paired games, 105 had a tight Kalshi book. **The rule fired on none of those 105**,
at a 2¢ margin or at 4¢. The best expected value on any game was +0.5¢. Where Kalshi is tight, the two venues quote the same
mid to within about a cent. Where Kalshi is wide, the venue is wide too, so there is no
sharp price to lean on.

These leagues have **no Kalshi twin** open: table tennis (Setka Cup Ukraine, Czechia and
Moldova, Czech Liga Pro; about 300 games), darts (PDC, MODUS), boxing, PREM rugby and the
Japan B.League. SHL and NHL did not pair on names and were not pursued.

## 2. In-play, 8 EuroLeague games (`analysis/thin/inplay_kalshi_anchor.py`)

This replays the rule every 3 s of live play, one entry per game per 60 s. It uses the
venue's streamed book and Kalshi's tape, which is polled every 10 s. Instants where the
venue book is stalled (no push for more than 30 s) are skipped.

| margin | entries | model EV | mark-out 60 s | mark-out 300 s | held to result |
|---:|---:|---:|---:|---:|---:|
| 2¢ | 111 | +3.03¢ | **−3.36¢** (se 0.36) | −2.24¢ (1.61) | +3.03¢ (4.80) |
| 4¢ | 43 | +5.34¢ | −1.99¢ (1.46) | −1.73¢ (4.10) | +2.88¢ (4.50) |
| control: coin side every 60 s | 891 | — | **−2.94¢** (0.20) | — | — |

G = 8 games; intervals are clustered by game. At 60 s the rule does no better than a coin.
The gaps it trades on are mostly Kalshi's reading being up to 10 s stale, not the venue
lagging behind Kalshi.

## What this does and does not say

- It **does not** test a same-tick Kalshi read in play. The Bitcoin arm reads both venues
  in the same 3-s tick. A 2–3 s Kalshi tape on the thin-league windows would test it, and
  that needs only a recorder parameter change.
- Pregame, the two venues agree, which suggests shared or linked market makers. Any
  cross-venue edge in sports would have to come from in-play timing, not from a standing
  mispricing.
- The Bitcoin checkpoint is unaffected. It still reads when `llm_agent` has 40 and
  `kalshi_taker_wide` has 300 trades counted from 2026-09-29 20:02Z
  ([btc15-v2-arms.md](btc15-v2-arms.md)).
