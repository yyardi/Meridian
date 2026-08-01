# Meridian — Status (2026-08-01)

One page: what exists, what it says, where we are stuck.

## What has been built (all 12 units + extensions)

**Data layer** — Polymarket US recorder (15-min cadence, full order-book depth), ESPN game logs 2020–2026, multi-book odds feed with true closing lines for 2024+, box scores/pace for 787 games, Polymarket settlements. All point-in-time correct; lookahead is structurally impossible (`as_of` mandatory everywhere).
**Model** — v3 fair value: additive strengths (`off_A + def_B − league_mean`), recency-decayed features, walk-forward home advantage, calibrated pricing via market-anchored shrinkage. One projection prices totals, spreads, and moneylines.
**Validation** — walk-forward backtests for all three markets, CLV-primary, three fill models, pre-registered targets and gates ([performance-targets.md](math/performance-targets.md)).
**Execution** — correlation-aware quarter-Kelly; shadow-only executor (market orders unrepresentable, kill switch on, **0 real orders ever**). Live dashboard + analytics charts at `localhost:8008`.
**Ops** — Dockerised recorder/scheduler on Supabase (laptop-hosted), runbook, backups, 192 tests. Book lines now polled every 20 min; PM every 15 min. Recurring cost: **$0**.

## Current data

6,101 market snapshots (60 cycles, no gaps) · 104,916 book levels · 1,645 games · 12,034 odds rows · 1,248 settlements · 923 predictions (252 resolved) · 14 shadow orders.

## Performance — canonical numbers

| Market | Hit | ROI | Mean CLV [95% CI] | Verdict |
|---|---|---|---|---|
| **Totals (champion: recency)** | 53.2% | +1.34% | **+1.75 [+1.45, +2.06]** | passes CLV gate |
| Spread (+HCA) | 51.6% | −1.78% | n/a | market-mirror |
| Moneyline (+HCA) | 39.0% | −2.42% | n/a | miscalibrated |

Breakeven is 52.4%. The champion's CLV CI excludes zero in every season and fill model; ROI does **not** survive taker fills (−4.0%) — maker-only is load-bearing. Live log hit rates (e.g. 94% on one v3 cohort) are **not** performance: the log includes the no-edge control group by design.

**Hypothesis ledger** — adopted: scale fix, HCA, recency (user's call), calibrated pricing. Rejected: home/away splits, record residual (predicted null), shrinkage-as-strategy, possession structure, MLB expansion (measured: 1¢ spreads on PM's MLB board → no venue gap there).

## Where we are stuck

1. **The shadow gate is a clock, not a task.** The champion needs ~60 days of live shadow CLV before the next decision. Nothing accelerates it.
2. **The venue gap has not been observed yet.** Scanner found sub-point gaps on quiet evenings; the hand-observed 6–8 pt gaps are hypothesised to be short *news windows*. The window detector (book moves ≥1.5 pts between polls → measure PM lag) is designed but not built.
3. **2026 is ambiguous**: −9.3% ROI on +1.69 CLV at n=89 — outcome noise and edge decay are indistinguishable at this sample.
4. **Moneyline calibration** remains ~10 pts overconfident (winner's curse survives HCA).
5. **The model cannot see rosters.** Season averages price players who may not play tonight — the pregame injury/lineup flag (planned) is both protection and a window signal.
6. **Laptop hosting**: a sleeping Mac still gaps the unrecoverable snapshot stream (`caffeinate -dis`).

## Next, in order

Window detector → pregame injury/lineup flag → shadow-gate review (~Oct 1) → boosted-trees ceiling probe (queued last). Real money remains gated: backtest CLV ✅ · 60-day shadow CLV ⬜ · calibration tolerance ⬜.
