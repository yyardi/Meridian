# Cross-venue price difference: the cost floor closes it

**DESCRIPTIVE. NO GATE.** Cost computed before any gap was quoted, as
instructed. No new data was harvested — this reads B's existing measurement
(`5dabfa5`, `quant-b/cross-venue-cfb`) and adds the half it did not compute.

## What B already established

Kalshi ↔ Polymarket CFB code map built from **both venues' own payloads**, 461
Kalshi events → 250 games, 241 Polymarket games, **177 matched, 220 codes**.

* **Over-determined, zero conflicts in either direction** — the positive
  control. A wrong name match would have surfaced as a conflict.
* **Only 30.5% of codes are identical.** A lowercase-and-compare join loses
  69.5% of the board and **mis-joins one**: Kalshi `SDST` is South Dakota St.,
  Polymarket `sdst` is San Diego St. (Kalshi `SDSU`). It produces a confident
  row for a game that does not exist.
* **620 (game, line) cells across 72 games. Max gross gap either direction is
  +1.00¢ — exactly one tick — on 2.9% of cells. Zero cells reach 2¢.**
* Kalshi's fee averages 1.34¢, exceeding the largest gross gap.

**What B left open, in their own words: it is ONE SNAPSHOT.** It gives the
cross-sectional distribution at an instant, not the frequency or duration of
gaps.

## The cost side, both legs

An arbitrage must cross **both** books as taker. Both formulas are read from the
venues, not assumed:

| leg | fee | source |
|---|---|---|
| Kalshi | `0.07·p·(1−p)` | `fee_type = quadratic_with_maker_fees`, `fee_multiplier = 1`, read from `/series/KXNCAAFTOTAL` |
| Polymarket | `0.06·p·(1−p)` | `core/quote/wallet.py:42` |

`p(1−p)` is symmetric, so the two legs — one near `p`, the other near `1−p` —
carry the same fee. **Combined floor = `0.13·p·(1−p)`.**

| price | Kalshi | Polymarket | combined | vs the 1.00¢ max gap ever observed |
|---:|---:|---:|---:|---|
| 0.50 | 1.75¢ | 1.50¢ | **3.25¢** | gap loses by 2.25¢ |
| 0.30 | 1.47¢ | 1.26¢ | 2.73¢ | gap loses |
| 0.20 | 1.12¢ | 0.96¢ | 2.08¢ | gap loses |
| 0.10 | 0.63¢ | 0.54¢ | 1.17¢ | gap loses |
| 0.05 | 0.33¢ | 0.29¢ | **0.62¢** | gap would clear fees |

**Fees fall below one tick only for `p < 0.084` or `p > 0.916`.**

## And the tails are closed by the spread

That extreme region is exactly where the book is worst. Measured and recorded in
three places (`live-cadence.md:83`, `live_recorder.py:65`, `:192`): the
**0.95/0.05 rungs carry 22–26¢ spreads and do not trade.**

So a 1¢ gap at `p = 0.05` clears the 0.62¢ of fees and then pays **22–26¢** to
cross — twenty-plus times the gap.

## The close

The two regions are exhaustive:

* **`0.084 < p < 0.916`** — fees alone are 1.0–3.25¢ against a largest-ever
  observed gap of 1.00¢. **Dead on fees.**
* **`p < 0.084` or `p > 0.916`** — fees drop to 0.25–0.62¢, but the spread is
  22–26¢. **Dead on spread, by a wider margin.**

**Stated as a requirement rather than an impossibility:** at mid prices a
profitable gap must exceed **4 ticks** plus spread. B observed a maximum of
**one** tick across 620 cells, with **zero** cells reaching two. The gap between
what is needed and what has ever been seen is a factor of four at the maximum,
not at the median.

## What this does and does not settle

**Settles:** the strategy does not clear costs at any price, and the argument is
structural — it rests on the two fee formulas, 1¢ tick quantisation, and the
measured tail spreads. None of those is a property of B's snapshot.

**Does not settle:** whether 4-tick gaps occur at all. B's snapshot says the
maximum was one tick and nothing reached two, which argues against it but cannot
exclude it — a snapshot cannot measure frequency or duration.

**Recommended:** close it. Re-opening should require someone first showing a
≥4-tick gap exists at mid prices; measuring frequency before that is measuring
the duration of an event that would not be profitable if it happened.

---

*Computed 2026-09-06. Reads `5dabfa5`; no new harvest. Descriptive only.*
