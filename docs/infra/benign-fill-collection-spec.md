# Collection spec — what it takes to measure the benign-fill rate

The benign-fill question cannot be answered from history. `market_trade_stats`
begins 2026-09-03, so the WNBA 200ms book window (07-31 → 08-20) has **zero**
trade rows, and on the CFB slate trade rows are written on ~1.2% of snapshots
with **zero per-market gaps under 10s**. The blocker is **write frequency**, not
schema and not query. Settling it means collecting differently going forward.

## ★ CORRECTION TO THE OBVIOUS ASK: TWO FEEDS ARE SAMPLED, NOT ONE

"Write `market_trade_stats` on every snapshot" fixes half the problem. Measured
over 2026-07-31 → 08-20, 16,752,371 snapshots, 1,123 markets:

| feed | coverage | rows/day today |
|---|---|---|
| touch quotes (`market_snapshots`) | **100%** | 835,698 |
| **book depth (`book_levels`)** | **2.75%** | 450,472 (19.6 levels/snapshot) |
| trade stats (`market_trade_stats`) | **1.2%** | ~10,000 |

**Depth is sampled slightly worse than trades are.** With 100% trade coverage
and depth still at 2.75%, the join still fails — a benign event is *depth
leaving the bid*, so no depth means no event, whatever the trade row says.
**Both must be densified together or neither is worth doing.**

## Minimum viable spec

The measurement needs, per market, consecutive observations ≤2s apart carrying:
`best_bid`, `best_ask`, **bid size at the touch**, and cumulative
`shares_traded`. It does **not** need the ladder.

| option | rows/day | note |
|---|---|---|
| touch depth only (level 0, both sides) | **1,671,396** | 2 rows/snapshot |
| full 19.6-level ladder | 16,379,676 | **9.8× more, buys nothing here** |
| `market_trade_stats` every snapshot | 835,698 | 1 row/snapshot |

**Recommended: touch-level depth + trade stats on every near-tier snapshot ≈
2.5M rows/day**, replacing today's ~460k. Net **+2.0M rows/day**.

**Write rate:** 835,698 snapshots/day is ~9.7/s average. The theoretical peak,
820 near-tier markets all live at 200ms, is 4,100 rows/s — but markets are only
polled at 200ms while live, and the 820 is a union over 20 days, not a
concurrent count. **The real peak-slate concurrency is not in the exports and
should be measured before committing**, because that number, not the daily
total, is what decides whether the near-tier feed degrades.

## What it buys

Current tape yields **118 touch events total** across three weeks — roughly one
event per 108 market-seconds of ≤2s-gap coverage. At full near-tier coverage a
single slate (~50 markets live for ~3 hours ≈ 540,000 market-seconds) yields on
the order of **5,000 events**, with the trade/cancel split resolved per event by
`shares_traded`.

That converts a bound into a measurement in **one slate**. Today's direct
evidence is **9 trades / 4 cancels at n=13** — the right direction, and far too
small to carry a capital decision.

## Fallback if the cost is prohibitive

Near-tier **and** in-game **and** markets within a configurable distance of the
money. Most of the 820 near-tier markets are not simultaneously interesting, and
the benign question only concerns markets we would actually quote. This is
strictly a subset of the above and can be tightened until the write rate fits.

## What this does NOT settle

Densifying collection measures the benign **event** rate and its trade/cancel
split. It does not measure **r** — the benign share of fills *our resting order*
receives — because that depends on queue position and on our own depth changing
the book. Only real resting orders measure that. **The probe remains the sole
direct instrument for r**, and should be sized against p25–p50 touch depth
(36–272 contracts), not a round dollar figure: at $278 the order dominates the
level in 53–79% of touch observations, which tests "be the level" rather than
"join the queue."
