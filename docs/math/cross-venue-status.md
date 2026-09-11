# Cross-venue: UNMEASURED, not dead — 2026-09-04

**Three analyses, two of them wrong, and the honest state is that our recording
cannot yet answer the question. This documents the method so nobody repeats it.**

## The methodological trap, which produced a fake edge

**Polymarket ticks every ~9s. We poll Kalshi every ~120s.** Comparing them by
time-bucketing averages the fast venue within the bucket and compares it to the
slow venue's single stale reading. **That manufactures gaps exactly when prices
move fast — which is exactly when arbitrage would appear.**

Worked example, my own error:
```
02:39:18  Kalshi      0.29 / 0.30
02:39:29  Polymarket  0.30 / 0.31
02:39:53  Polymarket  0.44 / 0.46   <- 14c move in 24 seconds
```
The minute bucket averaged Polymarket's 0.30 and 0.44 to ~0.37 and compared it
to Kalshi's single reading. **Reported gap: 7c. Real gap: none.** Both venues
were live and updating; the dislocation was in the measurement.

> **You cannot measure a cross-venue gap with unequal sampling cadences.**
> Match INSTANTS (nearest tick, bounded lag), never buckets.

## The three measurements, in order

| method | max gap | ≥2¢ | verdict |
|---|---:|---:|---|
| single snapshot (B) | +1.00¢ | 0 / 620 | no arb — but one instant only |
| minute-bucketed (mine) | +7.00¢ | 16 / 861 | **ARTIFACT — withdrawn** |
| **instant-matched, ≤10s lag** | **+5.00¢** | **5 / 558** | preliminary |

Instant-matched is the only valid one: **mean lag 3.3s, mean gap −1.85¢**, so
no arbitrage on average, with **5 instants (0.9%) at ≥2¢** against a Kalshi fee
of ~1.34¢.

## What the 5 qualifying instants actually show

**All five are the same game (UAB/Illinois), in-play.** That concentration means
this is one game's behaviour, not a board-level property — it cannot be
generalised and is not an edge claim.

**But two are not staleness artifacts**, and that matters:

| time | lag | Kalshi | Polymarket | gross |
|---|---:|---|---|---:|
| 02:51:31 | **0.4s** | 0.61/0.62 | 0.66/0.67 | **4.0¢** |
| 02:15:54 | **0.2s** | 0.51/0.56 | 0.48/0.49 | **2.0¢** |

At sub-second lag the two books genuinely disagreed by 2–4¢. Net of the ~1.3¢
fee that is ~2.7¢ on the best one. **Real dislocations exist; their frequency is
unestablished.**

## ★ What the close actually rests on (2026-09-06) — concentration, not room

**The close rests on ONE GAME (UAB/Illinois), five instants, 0.9% of 558. That
is a sample too concentrated to support either verdict.** Not "closed with a
caveat" — a verdict a sample cannot support is not a verdict, in either
direction. This section exists because the close was briefly restated on a
different and weaker basis, and that basis does not hold.

**The superseded framing, and why it fails.** "Maximum observed gap one tick,
zero cells reaching two ticks across 620 cells" is the **single-snapshot** row of
the table above, which this document already annotates *"one instant only"*. The
instant-matched row — *"the only valid one"* — finds **5 instants ≥2¢ and a
maximum of 5.00¢ across 558**, including two at sub-second lag that are not
staleness artifacts.

**On the valid row the close is NOT insensitive to the Kalshi fee coefficient.**
Best genuine instant, gross **4.0¢** at 0.4s lag, against a bar of
`(kalshi + 0.06)·p(1−p)`:

| Kalshi coefficient | bar at p=0.5 | net on the best instant | |
|---|---:|---:|---|
| **0.070** (published, unverified) | 3.25¢ | **+0.75¢** | below one tick — closed |
| 0.050 | 2.75¢ | +1.25¢ | **over a tick** |
| 0.035 | 2.38¢ | +1.62¢ | **over a tick** |

**Halving the coefficient flips that instant from closed to profitable.** So a
"room against the bar" argument is available only on the row this document
supersedes. **The concentration argument is the one that survives, because it
never depended on the coefficient at all.**

## ★ Kalshi's 0.07 — UNVERIFIABLE FROM THE VENUE (asked properly, 2026-09-06)

Recorded so the next reader does not re-ask. Polymarket's **0.06 is verified**
(`findings.md` V9, `fee_coefficient` across 874,267 rows / 241 markets). Kalshi's
0.07 is not, and the venue's own API does not expose it:

| endpoint (base `https://api.elections.kalshi.com/trade-api/v2`) | result |
|---|---|
| `GET /markets?limit=1` | 43 keys returned, **no fee-bearing key** |
| `GET /exchange/status` | **no fee-bearing key** |
| `GET /exchange/schedule` | **no fee-bearing key** |

Unauthenticated and read-only — `KalshiConfig` has no credential field
(`core/config.py:139`), so nothing here is blocked on access.

**The second authoritative route is also closed: we are read-only on Kalshi and
hold no settled trade of our own showing a fee actually charged.**

**No documentation page was consulted, deliberately.** A docs page, help-centre
article or web search is NOT authoritative for a venue fact — this project put a
retracted maker rebate back into its numbers from a web search on 2026-09-06,
hours after `findings.md` C7 had retracted it with account-level evidence.
**An honest UNVERIFIABLE is worth more than a sourced-looking 0.07.**

## Why our data cannot settle it, and what would

1. **Coverage.** My substring matcher pairs ~10 contracts. B's proper map
   (built from both venues' payloads, zero conflicts) reaches **177 games / 220
   codes** — roughly 20× the observable surface. **It is unpushed**, so this
   analysis ran on a twentieth of what exists.
2. **Cadence.** 558 matched instants across days is starvation sampling. Kalshi
   at 120s cannot resolve dislocations that live for seconds.

**The two changes that make it answerable:** land B's map, and poll Kalshi at
Polymarket's cadence — at minimum for contracts that have a Polymarket
counterpart, which bounds the rate cost to the matched set rather than the board.

## Standing conclusion

**Cross-venue arbitrage is UNMEASURED.** It is not refuted — the snapshot that
appeared to refute it measured one instant, and the time series that appeared
to confirm it measured our own recorder. **Neither analysis was about the
market.**

*No in-sample result justifies capital. The forward test is the evidence.*
