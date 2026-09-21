# The fee coefficient — the venue raised it, and the tree did not notice

**Question:** what does a taker pay on Polymarket US, and how would we know if it changed?

The venue charges `fee = Θ · p · (1 − p)` per contract at the price paid, and it
publishes Θ on every market object as `feeCoefficient`. The recorder stores that
field on every snapshot as `market_snapshots.fee_coefficient`. That column is the
whole history:

| Θ | rows | first seen | last seen |
|---:|---:|---|---|
| 0.060000 | 63,539,087 | 2026-07-31 | 2026-09-17 04:00:44Z |
| 0.069500 | 21,656,635 | 2026-09-17 04:07:24Z | 2026-09-21 (still) |

(prod, 2026-09-21: `SELECT fee_coefficient, count(*), min(captured_at), max(captured_at) FROM market_snapshots GROUP BY 1`.)

So **V9 was right on its day** — 0.06 on 874,267 rows, 2026-08-04 — and every
docs/math derivation written before 2026-09-17 used the coefficient then in force.
Between 04:00 and 04:07 UTC on 2026-09-17 (midnight Eastern, Wednesday night) the venue raised it by 16 %. At p = 0.50 the taker fee went from
1.50¢ to 1.74¢ per contract; a ladder pair at even prices pays about half a cent
more round trip.

## What was wrong

Not the number. The tree carried `0.06` as a literal in ten places — the ladder
scanner (`DEFAULT_FEE_RATE`), the backtest fill model (`THETA_TAKER`), the gridiron
scalp (`FEE_RATE`), the quote wallet's fallback, and six research runners — under
two different provenance claims for one quantity ("venue-published" and "measured
on 874,267 rows — V9"). Nothing compared any of them to the field the venue sends.
From 2026-09-17 to 2026-09-21 every fee in the system was charged 16 % light, with
every log green: **configured is not measured**.

Artifacts computed in that window at 0.06 undercharge the fee: the in-play ladder
figures retracted in STATUS §0cd (retracted for a larger reason), the nightly paper
book and ladder scans of 09-18..09-21, and the preregistration of 2026-09-19 (see
that file's note). Anything recomputed from the tapes after 2026-09-21 is at 0.0695.

## What changed on 2026-09-21

- `core/fees.py` is the one source: `POLYMARKET_TAKER = 0.0695`, `POLYMARKET_MAKER = 0.0`,
  `KALSHI_TAKER = 0.07`, `taker_fee(p)`. Every computing site imports it.
- `tests/test_fee_is_one_constant.py` parses `core/`, `cfb/` and `scripts/` and fails on
  any fee-shaped `0.06` literal in code or in prose. Its first run found a tenth runner
  (`cfb/run_scan.py`) and three prose sites the hand sweep had missed.
- `scripts/fee_drift.py` runs in the nightly slate verdict: the distinct coefficients
  recorded in the last day against the constant. A mismatch is a `FEE DRIFT` line in
  the report and the push, the morning after the venue moves.
- 33 test pins recomputed; the fee correction moved one fixture pair to $24.996, which
  exposed that the executors gated on the raw value while the desk printed $25.00 —
  now every gate goes through `clears_floor()`.

## What this does not settle

The maker side. Θ_maker = 0 is what the account has ever shown; the advertised 25 %
rebate has never appeared on a statement (docs/math/the-rebate.md). The venue's
coefficient can move again; the drift check is the only thing that would say so.
