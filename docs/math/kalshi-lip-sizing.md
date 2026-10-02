# Kalshi's Liquidity Incentive Program, sized across every slow series (2026-10-01)

The one place in reach where a venue pays for resting quotes rather than charging for them.
Sized from public data only: the program list is `GET /trade-api/v2/incentive_programs`
(no auth; `period_reward` in centi-cents, `target_size_fp`, `discount_factor_bps`, dates) and
the books are `GET /markets/<t>/orderbook`. The scoring rule, from the venue's own article
(help.kalshi.com 13823851, read 2026-10-01): a snapshot once a second at a random moment; the
**reference price** is found walking down from the best bid to the first level whose cumulative
size reaches one fifth of the Target Size; orders at or better than it score size × 1.0, orders
k ticks worse score size × discount^k (discount 0.5 on every program read); the yes and no sides
score separately and your snapshot score is your share of each; your period reward is your share
of all participants' snapshot scores × the period reward; a snapshot counts only if the market is
open and two-sided depth ≥ Target Size exists; **fills do not matter**.

On 2026-10-01 20:30Z: 8,140 active liquidity programs across 687 series, **$344,598 a day as a
24-hour rate; $251,256 per calendar day** once each sub-day program's reward is counted once
(a 15-minute program's $20 is a $1,920 "rate"; KXTEMPMIAH's ten programs are $1,000 a day, not
$25,656). The slow families (daily state gas averages, rain, temperatures) $78,682 a day as a
rate, about two thirds of that per calendar day.

**Correction, 2026-10-02 04:10Z, at the table it corrects.** The "pool $/day" and "$/day" columns
below are 24-hour RATES (`period_reward ÷ period length`). The daily gas programs pay **$100 per
market over a 16-hour period, 12:00Z → 03:59Z**, and the next day's programs are listed around
12:00Z, so no one is paid 04–12Z: the money per calendar day is the rate × 16/24. Read every gas
figure below at two thirds: GA $91 a day at 200 a side (not $136), FL $227, MD $236; the slow-series
total ~$2,540 a day on $50.7k (not $3,807), the five best states ~$790 a day on ~$8.7k. The scorer's
"implied $/day" in its status is the same rate; the 48-hour read integrates over live hours. Found
when the scorer idled at 04:01Z: its reload returned no programs and, as first written, it replaced
475 markets with none; it now keeps a live set through an empty answer and idles only when every
program has ended (e238e50 and the commit after it).

## Share after the incumbent, per series (books read 20:40Z; rates — see the correction above)

A 200-contract (or 500) quote per side resting AT each side's reference price, scored against
the incumbents' score at that instant (one or two makers resting 3k–26k a side), every snapshot
counted, no fills. Collateral is the two bids' prices × size per strike (≈ $1 a contract pair).

| series | strikes two-sided | pool $/day | median width | median vol 24 h | incumbent score/side | share @200 | $/day @200 | collateral @200 | $/day @500 | collateral @500 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GA gas | 20 | 4,514 | 65c | 63 | 9,365 | 3.0 % | 136 | 1,224 | 306 | 3,060 |
| FL gas | 21 | 4,158 | 76c | 15 | 10,792 | 8.2 % | 341 | 1,334 | 521 | 3,335 |
| OH gas | 22 | 4,158 | 58c | 5 | 9,201 | 3.1 % | 127 | 2,098 | 289 | 5,245 |
| MO gas | 15 | 4,137 | 1c | 48 | 5,187 | 2.5 % | 102 | 2,032 | 227 | 5,080 |
| MD gas | 15 | 2,553 | 8c | 200 | 4,552 | 13.9 % | 354 | 1,948 | 497 | 4,870 |
| AZ gas | 17 | 2,553 | 10c | 0 | 3,779 | 7.6 % | 193 | 2,450 | 340 | 6,125 |
| CA gas | 12 | 2,553 | 8c | 17 | 3,705 | 6.0 % | 154 | 1,792 | 275 | 4,480 |
| NY gas | 15 | 2,553 | 1c | 13 | 4,291 | 5.9 % | 151 | 2,422 | 324 | 6,055 |
| 20 further states | 10–17 each | 2,553 each | 1–59c | 0–723 | 3.5k–10k | 2–6 % | 60–150 | 0.9–2.6k | 136–270 | 2.3–6.5k |
| rain (28 cities) | 28 | 3,004 | 1c | 1,526 | 646 | 11.4 % | 342 | 5,286 | 607 | 13,215 |
| **slow series total** | | **78,682** | | | | | **3,807** | **50,726** | **7,345** | **126,815** |

Rain's 1c-wide books with 1,500 contracts a day of volume are not a no-fill market; it is in the
table for the number, not the plan. The five best gas states at 200 a side: ~$1,180 a day on
~$8.7k of collateral, if the shares held.

## The money at risk, per state and day

A quote at the reference sits where the book is 60c wide by construction, so a fill is a
position held to settlement at a price nobody else wanted. From each state's settled history
(`expiration_value` by day), the 95th-percentile day-over-day move of the settlement and the
strikes it crosses on the 0.5c grid; the worst day assumes every crossed quote filled against
us for the full size:

| state | settled days | median move | p95 move | strikes crossed at p95 | worst day @200 | worst day @500 |
|---|---:|---:|---:|---:|---:|---:|
| GA | 30 | 0.58c | 5.9c | 12 | $2,368 | $5,920 |
| FL | 37 | 2.59c | 8.8c | 18 | $3,516 | $8,790 |
| MD | 15 | 0.65c | 4.0c | 8 | $1,616 | $4,040 |
| AZ | 22 | 0.97c | 4.3c | 9 | $1,732 | $4,330 |
| OH | 30 | 2.34c | 16.8c | 34 | $6,712 | $16,780 |
| TX | 39 | 0.91c | 5.6c | 11 | $2,256 | $5,640 |
| NY | 37 | 0.66c | 2.4c | 5 | $952 | $2,380 |
| CA | 37 | 1.60c | 4.6c | 9 | $1,840 | $4,600 |

The worst day is 7–50× the state's daily reward. The program pays only if fills stay rare,
which the volumes (0–63 contracts a day across 15–22 strikes) say they are, and if the one
informed moment — the AAA number, once a day — is a window the quoter is out of. Both are
claims about fills, and **fills are the one thing the public data cannot show**.

## What this is and is not

- It is the largest number in this codebase by an order of magnitude, from the venue's own
  rule and books, and it is linear in size until the incumbents react — which they can do at
  will, since the share formula is linear in resting size and they hold 10–50× ours.
- It needs a Kalshi account with trading enabled and funded (the API key on prod is read-only
  by use), collateral of $5–50k, and an order engine for Kalshi that does not exist (post-only
  GTC quotes at the reference on every strike, re-quoted when the reference moves, pulled around
  the release, inventory limits, batch cancel) — live money, the operator's switch.
- What can run this week: a **paper scorer** — the venue's order-book stream, the published rule,
  our hypothetical quotes scored every second per market, the share and $/day written down for
  two days — which is exact (public rule, public book) except for fills. If the paper number
  holds at a quarter of the table, the order engine is worth building; if the incumbents' size
  moves against a paper quote nobody can see, it will not, and that is also an answer.

Operator on 2026-09-30: "i dont rlly care too much bout this LIP". The table is here because
on 2026-10-01 the ask was for edge, and this is where the venue's own numbers put it.

## The paper scorer, and the read registered before it runs (2026-10-02)

`core/kalshi/lip_scorer.py` (service `lip-scorer`, `docker-compose.lip.yml`, 128 MB, image
`meridian-api`, `core/` read-only, writes `/opt/meridian/artifacts/lip/lip_scorer.sqlite` and
`lip_status.json`). It loads the active liquidity programs for the configured series
(`MERIDIAN_LIP_SERIES`, default the 25 daily gas states), subscribes to those markets'
`orderbook_delta` on Kalshi's one websocket — the handshake signed with the same `KALSHI_*`
lines the BRTI relay reads from `.env`; nothing of the key is written anywhere — keeps the books
from snapshot plus deltas with `seq` tracking (a gap resubscribes for a fresh snapshot), and once a
second scores a hypothetical quote of ours of 200 and 500 contracts resting AT each side's
reference by the published rule: the share of each side's score, and whether the snapshot would
count (two-sided depth ≥ target). Per market: hourly rows (seconds, valid seconds, summed share
per size, median incumbent score per side) and a once-a-minute sample of the book's touch,
references, scores and depths; 3-day retention. The status file carries the socket's counters and
the implied $/day by series. `--once` prints the same scoring from one REST read.

**Registered read, written before the first scored second.** After 48 hours of scoring (first
look at 24 h only for liveness), per series and in total, over all program markets:

1. the mean share at 200 and at 500 a side over VALID seconds, the valid fraction, and the implied
   $/day = Σ_markets mean share × valid fraction × the market's $/day — beside the static table
   above (the paper number equals the static one only if the incumbents' books held);
2. the incumbents' median score per side by hour — did their resting size move during the 48 h
   (which it cannot have done in response to a paper quote nobody can see, so a move is their
   own cadence, and the live quote would face it too);
3. the valid fraction by hour of day — when the snapshots do not count, no one is paid.

Decision rule: the order engine is worth building only if the 48-h implied $/day at 200 a side
over the five best states is ≥ $300 (a quarter of the static table) with a valid fraction ≥ 0.8
and the incumbents' median score within 2× of the 20:40Z read; if it is, the operator decides
on a Kalshi account and collateral (the live path does not exist and is live money); if it is not,
this closes in one line. The paper number cannot see fills; the live step's first registered read
is fills per day per state at the smallest size, before any scaling.
