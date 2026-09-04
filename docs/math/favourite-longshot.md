# The favourite–longshot bias, and the first positive result — 2026-09-04

**PULSE is refuted as a fair value. The market's own mid is mispriced in a
large, price-dependent, exploitable shape. Our quoter centres on the mid, so it
harvests none of it.**

Population: `predictions`, 186,129 usable rows, **88 WNBA games**, through
2026-08-31. All CIs game-clustered.

## 1. PULSE cannot be the quoter's fair value — decisively

| | mean abs error | bias | Brier |
|---|---:|---:|---:|
| market mid | **39.01¢** | +6.32¢ | **1898** |
| PULSE fair value | 40.53¢ | +8.34¢ | 1968 |

**PULSE is 1.51¢ WORSE than simply reading the market.** And it degrades with
conviction: where the two are >5¢ apart, PULSE is **3.08¢ worse**. When PULSE
disagrees strongly, it is strongly wrong. *Wiring it into the quoter would
replace a bad opinion with a worse one.* (Also measured: `fair_value` is NULL in
**all 3,047,245** `quote_v2_observations` — the quoter has a column for its own
opinion and has never once populated it.)

## 2. The mid is mispriced in the classic shape — and it is large

| price | settles | market is |
|---|---:|---:|
| 2–10¢ | 5.3% | +0.34¢ |
| 20–30¢ | 16.0% | **+9.51¢** |
| 30–40¢ | 24.3% | **+10.24¢** |
| 50–60¢ | 44.5% | **+10.16¢** |
| 70–80¢ | 71.4% | +3.27¢ |
| 80–90¢ | 94.3% | **−10.46¢** |
| 90–99¢ | 99.9% | **−6.84¢** |

**Longshots overpriced ~10¢, favourites underpriced ~10¢.** Textbook
favourite–longshot bias. Independently corroborated by a separate measurement
on a different table: first-observation price vs settlement over the same 88
games gives **−6.88¢, CI [−12.22, −1.53]** (`docs/math/the-mispricing.md`).

**The MEAN bias is not the finding and must not be quoted as one:** overall
+5.30¢, CI **[−0.05, +10.65]**, 49/88 games — it touches zero. **The SHAPE is
the finding.**

## 3. ★ The first significant positive result ★

Sell where the market is rich (20–70¢), buy where it is cheap (≥80¢) — a maker
centring on bias-corrected fair value rather than on the mid. 88 games, 142,683
trades:

| | per trade | game-clustered CI |
|---|---:|---|
| **posted at mid (maker)** | **+7.88¢** | **[+2.17, +13.59] — EXCLUDES ZERO** |
| crossing the spread (taker) | +2.10¢ | [−3.63, +7.83] — spans zero |

**52/88 games profitable.** Required capture is +0.11¢.

**The maker/taker split IS the result.** Crossing destroys the edge; posting
keeps it. This is a market-making edge specifically — which is why every
taker-shaped test we ran (the dip signal: +0.62¢ at an unreachable price,
−2.70¢ crossed) came back dead.

## 4. What this does NOT establish — the ways it still dies

1. **IN-SAMPLE.** 88 games, one league, one month. No forward test.
2. **★ FILL SELECTION IS THE REAL RISK.** "+7.88¢ at the mid" assumes we transact
   at the mid. A maker POSTS and waits, and the fills you GET are selected —
   this is exactly the mechanism that made touch-joining lose −3.38¢ while the
   simulator showed better. **The bias says the PRICE is wrong; it does not say
   we can capture it.** A quote posted on the right side of a 10¢ error may
   still be filled only by someone who knows the error has already corrected.
3. `market_mid` in `predictions` is sampled at prediction time, which is a
   chosen instant, not a random one.
4. The favourite side (≥80¢) is 12,303 rows against 100k+ on the longshot side.

## 5. What gets built

**A bias-corrected fair value — one curve, no model.** `fair(mid) = mid −
bias(mid)`, fitted on the table above and refit out-of-sample. Then quote
around THAT rather than the touch, post inside wide books on the favoured side,
and measure the realised fill selection, which is the thing that decides it.

**No in-sample result justifies capital. The forward test is the evidence.**
