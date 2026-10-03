# Kalshi incentive farming on the renewing 15-minute series

Written 2026-10-03 19:00–20:30Z, before any live quote. Companion to `kalshi-lip-sizing.md`
(the daily gas programs). Every dollar figure here is a paper share **before anyone responds to
our quote**; the incumbents can step one tick in front of us inside a window, and only a live
quote measures that.

## What pays

Kalshi's Liquidity Incentive Program pays a per-market **Time Period Reward** to resting orders by
their share of qualifying size near a reference price, snapshot once a second. The legal text is
Appendix A of the July 15, 2026 CFTC filing as modified July 30, 2026 (PDFs linked from
kalshi.com/regulatory/notices; saved as scratchpad `lip2/lip_jul30.txt`). The rule as written:

- Walk down from the highest bid. At each price level add the level's whole size to the Qualifying
  Total Size and **all bids at that price** to the Qualifying Bids. The Reference Price is the
  first level at which the cumulative reaches one fifth of the Target Size. **Stop after the level
  that reaches the Target Size**; levels below never qualify. If the bids run out first, nothing
  on that side qualifies. If the highest bid is at the highest possible price (99c), nothing on
  that side qualifies.
- A qualifying bid scores `discount^(ticks below the reference) × size`, normalised over its side.
  A user's snapshot score is their yes share plus their no share (max 2.0 per snapshot).
- Payout = the user's share of all snapshot scores over the period × the Time Period Reward ×
  (non-excluded snapshots ÷ total), rounded down, paid if ≥ $1. A snapshot is excluded when the
  market is closed or either side rests less than the Target Size.
- Eligible: all members except IB/FCM customers. The July 30 text **removed** the exclusion of
  members with a Market Maker Agreement: the designated market makers farm these too.

`core/kalshi/lip_scorer.py`: `our_share` is the registered estimator of the gas read (q at the
reference, whole discounted ladder in the denominator; a lower bound on the venue's share);
`share_qualifying` is the rule above with our order merged into its price level, at the reference
or one tick in front.

## The series

| series | windows | $ per market-window | markets/window | target | live | pool |
|---|---|---|---|---|---|---|
| KXCRYPTOLEAD15M (Coin Race: BTC/ETH/SOL/XRP/HYPE, CF Benchmarks) | 15 min, back to back, 24/7 since 2026-10-02 20:00Z | $20 | 5 | 1000 | always | **$9,600/day** |
| KXEURUSD15M, KXUSDJPY15M, KXGBPUSD15M (Pyth) | 15 min, back to back, FX hours (programs listed from Sun 21:15Z) | $20 | 1 | 300 | ~24/5 | $1,920/day each |
| KXNATGAS15M, KXCOPPER15M, KXPLATINUM15M, KXPALLADIUM15M (Pyth) | 15 min, back to back, futures hours | $20 | 1 | 300 | ~23/5 | $1,920/day each |

Discount factor 0.5 everywhere; no per-account cap in the listing. Programs appear under
`status=upcoming` about nine hours ahead (`next_cursor` paginates; a pull keyed on `cursor` stops
at 1,000). The FX and metals series have traded since 2026-09-29/30 at 7,000–22,000 contracts a
window (median), so they are liquid and already farmed; the Coin Race is one day old.

## What the farmers already do, and what it costs them (public trades, 80 settled Coin Race windows, 10-02 23:15Z → 10-03 19:00Z)

Books at 19:04Z: 1,000–1,100 resting at 1c and 3c on both sides of every market (the farmers),
a 120-lot ladder at many levels (a market maker), retail prints in the middle. 3,481 trades,
120,349 contracts; 19,190 contracts printed into yes bids ≤ 5c and 5,518 into no bids ≤ 5c.

Realised P&L of **all** resting bids ≤ 5c, both sides, settled at the market result:
**−$25.24 over 80 windows (−$0.32 a window) against $8,000 of reward**; yes-side bids −$58.52,
no-side bids +$33.26 (yes buyers at 97–99c were sometimes wrong).

The tail, which is what a 1000-lot in front eats (max contracts printed at ≤ 5c into one
market-side per window): p50 96, p90 500, p99 1,002, max 1,002 (one side of 231 that printed
exceeded 1,000). For a 1000-lot resting at the printed prices: loss if every fill is wrong p50
$2.16, p90 $12.02, max $25.75; realised per window mean −$0.32, p10 −$7.59, min −$25.75, max
+$129.98. Worst windows 01:45Z, 02:15Z, 03:15Z on 10-03 (−$25.75, −$24.66, −$20.40).

Spot check, window 26OCT030145 (the worst), every print into a ≤ 5c bid, reproducible from
`GET /markets/trades?ticker=KXCRYPTOLEAD15M-26OCT030145-<coin>` with the market results
(all five resolved no except the winner):

```
05:31:09 ETH yes-bid 0.04 x 100     result no  -4.00
05:31:09 BTC yes-bid 0.04 x 71+28+1 result no  -4.00
05:33:46 BTC yes-bid 0.01 x 50      result no  -0.50
05:36:27 XRP yes-bid 0.03 x 118+2   result no  -3.60
05:36:27 ETH yes-bid 0.04 x 120     result no  -4.80
05:39-05:41 BTC yes-bid 0.01 x 10,10,10,10,53,2,50  result no  -1.45
05:40-05:42 SOL yes-bid 0.03/0.02/0.01 x 28,10,10,10,10,10,2,50,50,10,2.4  result no  -3.40
05:44:20 BTC yes-bid 0.01 x 400     result no  -4.00
window total -25.75; reward pool for the window $100 (5 x $20)
```

## Paper shares on today's books (19:13Z, two minutes before a window close; `lip2/coinrace_books_now.txt`)

Per window over the five markets, of the $100: registered estimator at the reference, 1000 a side:
$73; term-sheet rule at the reference: $60; **one tick in front, 1000 a side: $96**. By
construction a lot that reaches the Target Size alone, one tick in front, takes 100% of a side
until someone steps in front of it. The number that is not by construction is how often a side is
cheap enough to stand in front of: late in a window the leading coin's yes bid sits at 90–95c
(and at 99c the side is disqualified), so the **capped** policy (stand in front only where the
reference is ≤ 10c) is the one with the farmers' fill profile above; the uncapped one carries
real fill risk on the leading coin and is recorded only as a ceiling.

## Registered paper read (terms fixed here, before data)

Instrument: `kalshi-farm-scorer` (docker-compose.lip.yml), the LIP scorer on the eight series
above with `MERIDIAN_LIP_HORIZON_S=7200`, `FRONT_SIZES=1000,300`, `FRONT_CAP=0.10`, reload 900 s;
its own `farm_scorer.sqlite` / `farm_status.json`. Per market-hour it records seconds, valid
seconds, the summed shares under keys `200/500/1000` (registered estimator), `f1000`, `f1000c`,
`f300`, `f300c`, the incumbents' median scores, and `lip_disq` (seconds each side's best bid was
99c).

Read at **2026-10-05 12:05Z** (Coin Race: ≥ 40 h, ≥ 160 windows; FX/metals: Sunday 21:15Z to
Monday 12:00Z only, ≈ 55 windows each and all of them Asian/European hours, so their figure is
a thin weekend-edge sample and is reported as such, not decided on), once, by whoever is up.
Deployed 2026-10-03 19:24:25Z as kalshi-farm-scorer; first minute, 45 Coin Race markets, 0 gaps:
registered 1000 → $4,836/day, f1000 → $8,577, f1000c → $3,603, f300c → $519, before anyone
responds. Reads: 12:05Z (this session) and 12:20Z (Manager), same terms, once each:

1. Coin Race, `f1000c`: paper reward per market-window = (summed share ÷ seconds scored) × $20 ×
   (seconds scored ÷ 900), summed over every market-window in the run and **divided by the run's
   elapsed days** — never Σ(share × per_day_usd) across windows of different quarter hours, which
   counts each window as if it were live all day (the gas read's first pass summed 2.3 days of
   markets and read 3× high). Also the valid fraction and the fraction of seconds a side was
   disqualified. **Go to the live step if ≥ $2,000/day** (a fifth of the pool after the
   leading-coin sides are skipped) **with valid ≥ 0.8**. The scorer's own `implied_per_day` is a
   rate from the current hour's accumulators and is NOT the read.
2. FX/metals, same key per series; list those ≥ $400/day.
3. Fill tail re-read on the same windows from public trades (the table above, extended): the
   p90 and max per-window loss at a 1000-lot in front must stay under $15 and $50.
4. Headline sentence of the result names the estimator (`f1000c`), the window count, and the
   phrase "before anyone responds".

If 1 fails the series is closed in one line; nothing deploys from a smaller cut.

## The live step is the operator's switch

It needs a Kalshi trading key and collateral, both theirs. Registered now so the design is not
chosen after the data: **one window's five Coin Race markets, 1000 a side (the smallest size that
reaches the Target Size alone), one tick in front of the reference on every side whose reference
is ≤ 10c, re-posted when stepped in front of (one tick, up to the cap) and pulled at T−60 s.**
Collateral per window ≈ 1000 × price × sides ≈ $50–$500; fee none (maker; `fee_type quadratic`
charges takers). Run N = 48 windows (12 hours). Measured: our paid reward per window from the
venue's statement vs the paper figure; **the response**: windows until our paper share falls below
half of what it was in the first window; fills and their settlement P&L. Pass: realised reward ≥
60% of the paper figure over the 48 windows and net of fills ≥ $0. Then size: more series, not
more size per market (the Target Size caps what one lot can earn).

## Risks that are not in the numbers

- **Term-sheet risk.** The venue amended the Program on July 15 and July 30, 2026. A rule that pays
  96% of a window to whoever rests a Target-Size lot one tick in front is the kind of thing that is
  amended again (a maximum distance from the midpoint, a minimum spread, per-account caps). The
  pool figures depend on the current text; a change ends this, it does not merely dent it.
- **Response.** The incumbents are bots at 1,000–1,100 a side and designated market makers; the
  paper share is the share before they move. The live step measures nothing else.
- **Eligibility and tax.** "Most regular U.S. members"; rewards are credits with an SSN on file
  above IRS thresholds; monitoring for "abusive behavior" is at Kalshi's discretion.
- **Tail.** The worst of 80 windows was −$25.75 at a 1000-lot; a coin that is dumped at 5c for
  1,000 contracts and then wins is +$950, which happened once (+$129.98 window). The realised
  distribution is from one day of a one-day-old series.
