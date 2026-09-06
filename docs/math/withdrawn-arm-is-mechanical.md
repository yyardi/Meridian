# The withdrawn arm looks better because the price ran away — so do not reweight toward it

The reported pair: filled **+4.761pp** [−1.455, +10.978], withdrawn
**+10.857pp** [+7.554, +14.160], read as *"the bets we wanted are the ones
nobody would take"* and proposed as the basis for reweighting the score toward
the unfilled population.

**The gap is real. The reading is not, and the proposed fix runs backwards.**

## First, the statistics — I challenged it and it held

Those two intervals **overlap** over +7.554…+10.978, and a difference between
arms cannot be read off two marginal intervals. So I computed the one that was
missing, paired by game (the arms share games), joining
`resolved_outcomes_20260901T195202Z` — 100% coverage of 2,974 enters,
validated at agreement **1.0000** on the 1,944 rows carrying a native
settlement rather than assumed.

On return-on-cost, my own estimand (so **not** comparable in level to the
figures above):

| arm | n | G | value |
|---|---:|---:|---|
| filled | 1,944 | 34 | +14.320pp [−9.156, +37.797] |
| withdrawn | 1,019 | 33 | +49.879pp [+7.878, +91.879] |
| **withdrawn − filled, paired by game** | 33 games | | **+52.206pp [+10.461, +93.952]** |

**Excludes zero.** The methodological objection was correct in form and did
not overturn the finding. The gap survives a proper paired test.

## Then the mechanism, and it is arithmetic

A resting order fills when the market comes **to** it and fails to fill when
the market moves **away**. So the two arms are sorted by price direction
before any model skill enters.

Measured. Mid movement from decision, signed to the position:

| arm | mid move | interval |
|---|---:|---|
| **filled** (decision → fill) | **−4.545¢** | [−4.199, −4.891] **against** |
| **withdrawn** (decision → withdrawal) | **+3.713¢** | [+2.608, +4.818] **in favour** |

An **8.3¢ swing**, and the two intervals are nowhere near each other.

Robust to the cadence guard the book export requires (p90 gap 921s), and it
grows with the window exactly as a "price ran away" mechanism predicts:

| staleness cut | n | mid move |
|---|---:|---:|
| ≤30s | 608 | +4.041¢ [+2.675, +5.407] |
| ≤60s | 684 | +3.963¢ [+2.694, +5.233] |
| ≤120s | 804 | +3.713¢ [+2.608, +4.818] |
| ≤300s | 1,006 | +7.623¢ [+5.791, +9.456] |

## What follows, and it inverts the proposed fix

The withdrawn arm's advantage exists **only in a counterfactual where the
order filled at its limit** — and it did not fill precisely because the price
left that limit. You cannot buy at 0.20 once the market has gone to 0.24.

**Reweighting the score toward the unfilled population would credit PULSE with
returns that were never capturable.** It is not a correction for selection; it
is the selection bias with the sign reversed, and it would make the strategy
look better in exactly the cases where it captured nothing.

The plainer reading of the same numbers: it is not that *nobody would take*
these bets. It is that **the price moved before the trade could happen** — a
queue-and-latency phenomenon, not a counterparty refusing us. The two have
opposite remedies. The first suggests we are being picked off and should quote
differently; the second suggests we are too slow or too passive and should
reach for the fill.

This does not resolve wave rule 2's actual concern. "46% of intents never
filled" is still real, and a per-fill haircut still does not correct it. But
the unfilled arm's returns are not the missing counterfactual — they are the
one population guaranteed to flatter us.

## Provenance and limits

- The selection asymmetry was already recorded in `3441cc1`: *"entered is
  selected twice, by the model and by a fill process that selects adversely,
  while declined is selected once."* This document measures it.
- `3441cc1`'s own headline is that at G=34 the branch comparison **cannot
  separate** the halves on Brier. That is a different estimand from the P&L
  figures above and does not supersede them, but it is the more conservative
  reading of the same data and it came from shared code.
- **Provenance of +4.761pp — settled by REPRODUCTION, after three conflicting
  identifications in relay.** Computing `s·(S − limit_price)·100`,
  game-clustered, on the pinned export returns:

  | arm | n | G | reproduced | published |
  |---|---:|---:|---:|---:|
  | filled | 1,944 | 34 | **+4.761pp** | +4.761pp |
  | withdrawn | 1,019 | 33 | **+10.857pp** | +10.857pp |

  Exact to three decimals on both. It is a **P&L** statistic — side-signed on
  the YES scale at the quoted limit price — and **not**
  `pulse_branch_scoring.py`'s Brier(market) − Brier(model), whose
  entered/declined differences are ~0.002–0.003 per `3441cc1`, two orders of
  magnitude away. It is committed, in
  `analysis/pulse_money_and_the_taker_join.md` at `3dbe88a`.
  - My clustered half-width comes out **5.900** against the published 6.216 —
    a small estimator difference, not a point-estimate one. It changes no
    verdict (filled spans zero either way, withdrawn excludes it either way)
    but it is unreconciled and named rather than smoothed over.
  - So the comparison here is P&L against P&L, and apt.
  - Consequence, via the anchor rule: because that base is **limit**-anchored,
    the gross 4.70¢ is the *correct* charge against it. No overcharge there.
  - The document carrying it is headed **"MY VERSION, pending reconciliation
    with d5. Not for broadcast."** It has since travelled through two relays.
- My level figures are still not comparable to it — mine is return-on-cost,
  theirs is P&L per contract on the YES scale. Only the **paired difference**
  and the **mid-move mechanism** are offered here.

## Which predicate defines the withdrawn arm — settled, and it is not a convention

Two were circulating: `withdrawn_at.notna()` (n=1,019, **+10.857pp**) and
`filled_at.isna()` (n=1,030, **+10.878pp**). The 11-row gap decides it, and
they are not ordinary unfilled orders:

**All 11 carry `binding_constraint = max_open_per_event`**, from one event in
a single nine-minute window on 2026-08-23. They were **blocked by a position
limit before ever being placed.** No order rested in the market, so there was
no fill to miss.

That makes `filled_at.isna()` the wrong predicate here regardless of taste. It
merges two different non-events — *posted and the price left* with *never
posted* — and this document's whole mechanism is about the first. Use
**`withdrawn_at.notna()`**, which is also what the published figure used.

Numerically nothing rides on it (+10.857 against +10.878, intervals almost
identical). The label is what rides on it.

**A second confirmation of the interval estimator fell out of this.** Computed
with CR1 + t(G−1), the withdrawn arm returns **[+7.554, +14.160]** — the
published interval exactly, on a figure whose half-width I had not previously
reconciled. See [my-clustered-intervals-were-narrow](my-clustered-intervals-were-narrow.md).
- 78.9% of withdrawn rows match a book snapshot within 120s. The rest are
  excluded rather than joined stale.
