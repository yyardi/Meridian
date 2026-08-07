# Meridian — Status (2026-08-04)

One page: what exists, what it says, where we are stuck.
Companion: [findings.md](findings.md) — what we got wrong, and the venue facts that
constrain everything below.

## What has been built (all 12 units + extensions)

**Data layer** — Polymarket US recorder (15-min cadence, full order-book depth), ESPN game logs 2020–2026, multi-book odds feed with true closing lines for 2024+, box scores/pace for 787 games, Polymarket settlements. All point-in-time correct; lookahead is structurally impossible (`as_of` mandatory everywhere).
**Model** — **v4** fair value (v3 + live winner's-curse shrinkage; the shadow clock restarted with the bump): additive strengths (`off_A + def_B − league_mean`), recency-decayed features, walk-forward home advantage, calibrated pricing via market-anchored shrinkage. One projection prices totals, spreads, and moneylines.
**Validation** — walk-forward backtests for all three markets, CLV-primary, three fill models, pre-registered targets and gates ([performance-targets.md](math/performance-targets.md)).
**Execution** — correlation-aware quarter-Kelly; shadow-only executor (market orders unrepresentable, kill switch on, **0 real orders ever**). Live dashboard + analytics charts at `localhost:8008`.
**Ops** — Dockerised recorder/scheduler on Supabase (laptop-hosted), runbook, backups, 464 tests. Live recorder writes locally at **200ms**; book lines polled every 20 min. Recurring cost: **$0**.
**PULSE (Route B)** — replay engine ([`core/pulse/replay.py`](../core/pulse/replay.py), no lookahead, fills earned not assumed), overreaction and first-score studies, ANCHOR scorecard ([`core/scorecard.py`](../core/scorecard.py), clustered by game). All built; all waiting on games.

## Current data

839,811 market snapshots · 830,838 book levels · 3,290 team game logs · **18,145 player-games** · 12,658 sportsbook odds rows · 11,609 predictions (**8,937 on v4**) · 1,356 resolved · 1,333 shadow orders · 82 injury change rows.

**Game coverage — the number that gates PULSE and QUOTE** (local mirror, 2026-08-04):
**20** games have snapshot data · **10** have live ticks · **3** have full 200ms
coverage (+1 partial, 835s). Every Tier-1 gate is written in games and needs 10.
The phrase "20 games with tick data" appeared here previously and was wrong — 20 is
games with *any* snapshot, most of them pregame-only.

## Performance — canonical numbers

| Market | Hit | ROI | Mean CLV [95% CI] | Verdict |
|---|---|---|---|---|
| **Totals (champion: recency)** | 53.2% | **−2.33%** (measured fills, C12; was +0.75% on a guessed concession) | **+1.75 [+1.45, +2.06]** | ⚠️ **negative under measured fills — see C12, and Q1 on the CLV** |
| Spread (market-shrunk) | 54.1% | +2.83% (pre-C12 fill model; not re-run) | n/a | promising, n=37 |
| Moneyline | 25–33% | −9.5% to −17.9% | n/a | **not traded** |

> ⚠️ **Two live objections sit underneath this table. Read them before quoting any
> number in it.**
>
> 1. **The CLV is measured against the sportsbook *opening* line**
>    ([`engine.py:264`](../core/backtest/engine.py#L264): `entry = float(chosen.open_total)`).
>    So +1.75 means *the model anticipates sportsbook line movement*. You cannot
>    transact at a sportsbook open, and the venue is Polymarket — so this scores a
>    skill the live ANCHOR strategy does not use, since ANCHOR takes the book number
>    as an *input*. Unresolved: [findings.md Q1](findings.md#q1--is-the-headline-clv-number-measuring-a-tradable-edge-️-unresolved-contradiction).
> 2. **C7 (the unobserved maker rebate) is now resolved in code** (2026-08-05):
>    $\Theta_{\text{maker}} = 0$ is the default everywhere, and the table above shows
>    the rebate-free number. Booking the rebate (`--assume-maker-rebate`, an explicit
>    sensitivity arm) restores the old +1.34% exactly — the 0.59pp gap was entirely
>    the unverified credit. CLV and hit rate are unchanged; the rebate never altered
>    bet selection. [findings.md C7](findings.md#3-corrections).
>
> 3. **C12 (2026-08-07): the fill model's adverse selection is now MEASURED, and
>    the +0.75% did not survive it.** REALISTIC carried a 0.5¢ concession guessed
>    before any fill existed; measured pregame — ANCHOR's regime — it is **2.11¢**
>    [1.83, 2.39] (in-game **4.70¢**). Recalibrated: **−2.33%** primary, −1.79% to
>    −2.86% across the pregame CI, −7.27% in-game-calibrated. Same bets, same CLV —
>    only the cost of being filled changed. Positive only under OPTIMISTIC, which
>    the engine's own report defines as not-an-edge.
>
> All three objections are upstream of the money figure below. Q1 remains unsettled.

**What the edge is worth, in money** (Experiment 3, **superseded on the fill side
by C12**): +1.75 points of CLV still de-vigs to +4.16pp of probability edge →
E[ROI] +2.50% [+0.85%, +4.16%] *if fills were benign* — but measured adverse
selection costs 2.11¢ per filled contract pregame, and the realised canonical ROI
under it is **−2.33%**. The CLV is real; the maker fill eats it. Maker-only was
load-bearing against the taker fee; C12 shows maker fills carry their own
measured cost too. [what-the-edge-is-worth.md](math/what-the-edge-is-worth.md)

Breakeven is 52.4%. The champion's CLV CI excludes zero in every season and fill model; ROI does **not** survive taker fills (−4.0%) — maker-only is load-bearing. Live log hit rates (e.g. 94% on one v3 cohort) are **not** performance: the log includes the no-edge control group by design.

**Hypothesis ledger** — adopted: scale fix, HCA, recency (user's call), calibrated pricing. Rejected: home/away splits, record residual (predicted null), shrinkage-as-strategy, possession structure, MLB expansion (measured: 1¢ spreads on PM's MLB board → no venue gap there), **roster availability** (measured: even an oracle that knows the true lineup gains no CLV — the close already prices lineups; see [availability.md](math/availability.md)).

## Where we are stuck

1. **The shadow gate is a clock, not a task.** The champion needs ~60 days of live shadow CLV before the next decision. Nothing accelerates it.
2. **The venue gap has not been observed yet.** The window detector is now BUILT (`python -m core.window_detector`) but has **zero triggers** — 0 book moves >=1.5 pts in 61 consecutive poll pairs. Not a null result; the experiment has not run. Binding constraint is cadence, not modelling: PM idles at 60 min and the lag is measured in minutes. [news-windows.md](math/news-windows.md)
   Background: the scanner found sub-point gaps on quiet evenings; the hand-observed 6–8 pt gaps are hypothesised to be short *news windows*.
3. **2026 is ambiguous**: −9.3% ROI on +1.69 CLV at n=89 — outcome noise and edge decay are indistinguishable at this sample.
4. ~~**Moneyline calibration**~~ **Settled — and it was never a calibration problem.** The model's win probabilities are already well calibrated across all games (0.75→0.772, 0.85→0.847); isotonic would have fixed nothing. The measured fault is *selection*: the incremental slope of the model over the market is +0.18 [−0.03, +0.38], and the market's margin MAE (9.65) beats the model's (10.19). The model is dominated by the market, so betting its raw disagreement overbets a 0.18-weight signal ~5×. **The executor no longer trades the moneyline** (it was producing 254 actionable predictions and 80 shadow orders). [market-shrinkage.md](math/market-shrinkage.md)
5. ~~**The model cannot see rosters.**~~ **Settled, and not the way we expected.** The model still cannot see rosters, but an oracle arm that reads the true lineup off the box score gains no CLV (+0.06 pts on absence games, CI [−0.10, +0.21]) — lineups are public before tip-off and the close already prices them. ROI rose (+1.3% → +6.8%) but the bands overlap almost entirely — [−11.4%, +14.0%] vs [−5.0%, +18.7%] at n≈250. Roster awareness is worth *speed*, not *information*, which folds it into the window question. [availability.md](math/availability.md)
6. **Laptop hosting**: a sleeping Mac still gaps the unrecoverable snapshot stream (`caffeinate -dis`).
7. **Backtests now run locally.** `python -m core.storage.sync_local` mirrors the primary into the warm standby; a paired experiment went from **11m28s to 13s** with byte-identical results. Run experiments against `localhost:5433`, not Supabase — an experiment that costs 11 minutes gets run once and stands unchallenged.

8. **The tradable half of the board may not be where the edge is.** Depth at the touch
   is **$5** under 20¢ and **$24** at 20–35¢; the tick is **1¢ everywhere** (6.25% of
   value at 16¢); and cheap contracts reach a 7¢ move **57%** of the time against
   **88%** near-money. The model prefers deep out-of-the-money rungs. Nobody has
   measured whether it has any edge at 35–65¢, where size is actually available.
   [findings.md](findings.md#what-v1v3-mean-together)
9. ~~**PULSE Tier 1 is blocked on games, not code.**~~ **The games arrived, and three
   verdicts landed 2026-08-06, all FAIL:** run overreaction (444 runs / 11 games,
   reversion −0.32¢ vs 6¢ cost — with #3/#4 dying as covariates), adverse selection
   (−2.66¢ net capture per filled quote, CI [−2.96, −2.36] — naive quoting is dead,
   QUOTE stays unbuilt), and whale/depth (+0.22¢ at 60s, 0.15× half-spread — the book
   beyond the top predicts nothing). First-score (#2) reports at 10 games; it stands
   at 9. In-game prices, on this evidence, **reprice rather than overreact**.
10. ~~**Write latency is unmeasured**~~ **Measured 2026-08-05 (V17):** 93–124ms
    round-trip, 14–23ms venue-side, n=3 real human-confirmed orders. Detection
    (~260ms) remains the dominant term. Moot for QUOTE unless a faster detector
    revives the adverse-selection question with a much tighter horizon.
11. **⚠️ Silent outages are still not alerted.** Two on 2026-08-03, both caught by hand,
    neither alerted — the pooler rewrite (B11, cost **2 games of 200ms data**) and ESPN
    beginning to 403. Both bugs are fixed; **the monitoring gap is not.** `/api/status`
    queries Supabase while the 200ms recorder writes to local Postgres, and
    [`core/api.py`](../core/api.py) deliberately excludes the live recorder from the
    health verdict because it is legitimately silent between games — so *dead for a
    day* and *idle at 3pm* were indistinguishable. **The per-cycle heartbeat is now
    built** (2026-08-05, [infra/heartbeats.md](infra/heartbeats.md)): every writer
    beats every cycle into its own database, a beat older than 3× its interval is
    DEAD regardless of game state, and a live game with a fresh beat and zero rows
    is DEGRADED. **Alerting is now built too** (2026-08-07,
    [infra/alerter.md](infra/alerter.md)): a container evaluates the same checks
    every 5 minutes and pushes transitions to the phone via ntfy, with a 9:00 CT
    digest that always sends — so the alarm's own death is loud as well.
12. **The headline CLV still rests on a contested input** — Q1 (CLV measured
    against a price you cannot trade). C7 (the unobserved maker rebate) is resolved:
    the ROI in the table is now rebate-free (+0.75%; the rebate arm restores +1.34%).
    See the warning under the performance table.

## Next, in order

**Tighten the poll cadence** (the one thing blocking Experiment 4) → accrue windows → shadow-gate review on **v4** (~Oct 1, restarted) → boosted-trees ceiling probe (queued last). Real money remains gated: backtest CLV ✅ · 60-day shadow CLV ⬜ (reset by the v4 bump) · calibration tolerance ⬜.

Done since: Exp 1 availability ❌ · Exp 2 market shrinkage ✅ (moneyline switched off) · Exp 3 de-vigged CLV ✅ · Exp 4 detector built, no data · Exp 5 pace interaction ❌ · **live shrinkage bug fixed (v4)**.
