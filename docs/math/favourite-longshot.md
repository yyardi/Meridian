# ★ RETRACTED — the favourite–longshot finding was a one-sided-sampling artifact ★

**2026-09-04, same day. The +7.88¢ / +7.19¢ edge and the entire band structure
are WITHDRAWN.** Research demanded a known-answer check before anything was
built on it; the check failed, and the mechanism is now measured.

## The check, and why it is decisive

**In a complete two-sided binary market, aggregate miscalibration is ZERO by
construction** — every contract sold to an overpaying buyer was bought from a
counterparty, so YES and NO errors must cancel. Our sample showed a **+6.80¢
one-directional tilt**, impossible for a complete market and therefore proof of
a selected subset.

**Restricting to the 243 markets where BOTH sides are present:**

| | |
|---|---:|
| side A mispricing | **−8.33¢** |
| side B mispricing | **+8.20¢** |
| **net** | **−0.126¢ ≈ 0** |

**Where both sides are observable, prices are calibrated to a tenth of a cent.**
The apparent 10¢ bias was *which side of each binary happened to be in the
table*. The 880 moneyline/total rows carrying the tilt (+10.39¢) are one-sided
observations whose complement we never recorded — calling them overpriced is the
same as noting that the losing side of a fair coin lost.

## Refuted, and the mechanism that was also wrong

**REFUTED:** the +7.88¢ and corrected +7.19¢ edges; the band structure; the
claim that this venue shows an exploitable favourite–longshot bias; and the
Bartlett & O'Hara corroboration, since we were not measuring what they measured.

**The proposed MECHANISM was itself wrong.** Research hypothesised the selector
was our dedup rule — "drop the lower slug" keeps `pos` over `neg`
alphabetically. **Measured: `pos` and `neg` are exactly balanced, 352 each, at
+2.15¢ and +2.46¢.** The dedup selected nothing; the selection is upstream, in
which markets ever had a complement recorded. *Right conclusion, wrong
mechanism — the third time today.*

**SURVIVES:** the construction correction (1,002 positions, not 142,683 — the
table holds 117.6 rows per market) and **crossing the spread = −6.49¢**, which
makes post-only an arithmetic necessity rather than a preference. Neither
depends on the calibration being right.

## Rule candidate

**A calibration measured on one side of a two-sided market is not a
calibration.** The forced-zero aggregate is a free known-answer check costing
one query, and it must be printed FIRST, before any band table, on every
calibration this program runs from now on.

---

# The favourite–longshot bias, and the first positive result — 2026-09-04

**★ EVERYTHING BELOW IS SUPERSEDED BY THE RETRACTION ABOVE ★**


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

## 3b. ★ CORRECTED — the construction, and what it cost ★

Research challenged the construction before building on it: *"on a binary book
at 30/70 both sides sit inside the 20–70 sell band, and selling both collects
100 and pays 100."* **Two real defects, found because they asked.**

**(a) The table holds 117.6 rows per market** — the same market re-predicted at
~118 timestamps. The original "142,683 trades" was 1,584 markets resampled, not
142,683 positions. **(b) 243 complementary pairs exist** — both sides of the
same binary are present, so the rule could take both and wash.

Corrected: **one row per market (earliest prediction), then drop the lower slug
of any complementary pair** so both sides are never taken. 1,584 → 1,372
markets → **1,002 positions across 88 games, 11.4 per game.**

| | as first reported | **corrected** |
|---|---|---|
| positions | "142,683" | **1,002** |
| posted at mid | +7.88¢ [+2.17, +13.59] | **+7.19¢ [+0.60, +13.78]** |
| crossing the spread | +2.10¢ | **−6.49¢** |
| games profitable | 52/88 | 51/88 |

**The edge survives — the point estimate barely moves — but the interval now
only just excludes zero, and the effective sample is 1,002 positions rather
than the six-figure number implied.** Crossing goes from marginally positive to
decisively negative, which *strengthens* the maker-only conclusion: **the bias
is ~10¢ and the spread is ~9¢, so a taker pays away the entire edge.**

**Rule 26, applied to ourselves: the sequence is the record.** The first number
was not wrong so much as counted wrong, and it was published before anyone
asked how it was built.

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
