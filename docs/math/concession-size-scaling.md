# The concession is applied per contract, and was measured where size ≡ 1

`analysis/pulse_execution_decomposition.py:285` charges the pessimistic
execution rule as

```python
contract_legs = legs.contracts.sum() + trips.contracts.sum()
pess_exec = MEASURED_CONCESSION_INGAME * contract_legs      # 4.70¢ × Σ size
```

A flat rate times total size. That is a **linearity assumption**: cost per
contract does not depend on order size.

## The measurement that produced the constant cannot test it

4.70¢ per contract per leg comes from the QUOTE study. `ShadowQuoteFill` has
no size field — every fill is a unit YES position. So the study has **no size
variation at all**, and its power to detect size dependence is not low, it is
**zero**. This is not an unverified assumption; it is one the originating
design cannot speak to even in principle.

The two units are also different in kind and only coincide by construction:
QUOTE's "per filled quote" equals "per contract" because size ≡ 1. PULSE's
sizes vary, so the two come apart there — the collision recorded in
[estimator-not-named-in-the-label](../../MEMORY.md), one level down.

## Why it could fail: the two components scale differently

| component | scales with size? |
|---|---|
| feed-lag / adverse selection — the mid moves between decision and fill | **no**, constant per contract |
| book-walking — the order consumes past the touch into worse levels | **yes**, convex once size exceeds touch depth |

A pure feed-lag concession is genuinely linear, so the code is right for that
part. The book-walking part is zero while an order fits inside the touch and
convex after. Everything therefore turns on **D, the depth at the touch**.

## Sensitivity to D

Filled PULSE legs, pin `20260901T195202Z`: 3,751 fills, 4,725.5 contracts,
flat charge $222.10. Suppose cost per contract rises linearly once size
exceeds D. The flat rate then **understates** by:

| D (contracts at the touch) | understatement | as a share of the charge |
|---:|---:|---:|
| 1 | +$281.50 | **127%** |
| 2 | +$103.54 | 47% |
| 5 | +$17.19 | 7.7% |
| 10 | +$2.46 | 1.1% |
| 25 | $0.00 | 0% |

The answer is dominated by D and by nothing else.

## Size distribution: the assumption barely binds for typical orders

Per filled decision: median **0.70** contracts, mean 1.26, **max 21.27**.

| threshold | orders | % of orders | % of contract volume |
|---|---:|---:|---:|
| > 1 | 1,360 | 36.3% | 77.5% |
| > 5 | 141 | 3.8% | 22.1% |
| > 10 | 14 | 0.4% | **4.2%** |
| > 25 | 0 | 0% | 0% |

**The max FILLED size is 21.27, not 200.75.** The 200.75 figure is the max
over *all* decisions including the 15,582 that never filled; quoting it as a
traded size overstates the largest real order by 9.4×. Corrected here because
I circulated it myself.

96% of volume sits at ≤ 10 contracts, so for the typical order linearity is
almost certainly harmless. The exposure is concentrated in the top ~4%.

## D is not measurable for PULSE's markets from anything pinned

The only book export with touch quantities,
`book_trade_joined_20260906T193102Z`, covers **4,291 CFB markets**. The PULSE
decisions pin covers **480**. The overlap is **zero markets and zero
decisions**. There is no join to make, and I did not force one.

For scale only, and **explicitly from a different league, date and price
regime** — CFB 09-06, mid-range prices (0.05–0.95), n = 48,159 snapshots:

| p5 | p25 | median |
|---:|---:|---:|
| 2 | 15 | 61 contracts at the touch |

32% of those snapshots have touch depth below 21.27. If anything like that
depth held in PULSE's markets, the largest orders would walk the book a
non-trivial fraction of the time and D would sit in the range where the
understatement is material rather than the range where it vanishes. **That is
a reason to measure, not a measurement** — a clean number from the wrong
regime is the failure mode this project has already recorded once.

## What would close it

A book export carrying `ask_qty_touch`/`bid_qty_touch` for PULSE's own 480
markets, ASOF-joined to `decided_at`, giving the realised distribution of
`contracts / touch_depth`. If the p95 of that ratio is below 1, linearity is
safe and this document can be closed. If not, the pessimistic re-score needs a
convex charge and is currently **not pessimistic enough** — which matters
precisely because it is the conservative branch of the decision rule.

## Status

**Open.** Unresolvable from pinned data; not a defect in the code, an
unmeasured assumption in it. The direction of any error is known — flat-rate
understates, never overstates — so every number the pessimistic rule produces
is a **lower bound on the execution charge**.
