# Run overreaction — do prices overshoot a run and come back?

**Status: NO DATA.** Re-run 2026-08-02 under the 200ms recorder: **149 runs
across 4 games**, against a pre-registered minimum of 30 across 10. The run
count is now met; six more games are needed. Reversion at the gated horizon is
flat (−0.01¢) with an interval entirely below the 6¢ round trip — a direction,
not a verdict.

Module: [`core/pulse/overreaction.py`](../../core/pulse/overreaction.py) · Gates **PULSE**

## Why this is the first question, not the second

In-game directional trading has two candidate edges: a better live model, or a
behavioural one. The behavioural one is cheaper to test, and if it fails the
modelling one almost certainly fails too — a market that does not overshoot is
a market pricing runs correctly, and out-pricing it live is a far harder bar
than out-pricing a stale line.

So do not build a live model before this answers yes.

## There is a prior, and it is specific

Already measured on 787 games: Q1 combined total correlates **+0.55** with the
final total, and **each extra Q1 point is worth 1.32 on the final, not 4.0**.
Hot starts regress about 3×.

That gives the hypothesis a number. If the market prices a run closer to 4.0
than to 1.32, there is an overreaction to trade. If it already prices 1.32,
there is not.

## Definitions

A **run** is either trigger, inside 2 minutes:

- **score** — one team scores ≥ 8 unanswered points (from the recorded
  `event_score`)
- **price** — the mid moves ≥ 10% on a quotable rung

The price trigger exists because the score trigger is only as good as the score
feed, and a run the venue smoothed over is invisible to it. Observing the
market's reaction directly is the same reasoning
[news-windows.md](news-windows.md) uses for seeing news through the book rather
than through a headline.

**Reversion** is signed toward profit, so positive always means "it came back":

$$
\text{reversion}(H) = -\operatorname{sign}(\Delta_{\text{run}}) \cdot \big(m(t_{\text{end}}+H) - m(t_{\text{end}})\big)
$$

## The pre-registered gate

Fixed 2026-08-02, before any number was computed.

| | |
|---|---|
| **PASS** | mean reversion at **+5 min** > 6¢, **and** its 95% CI (clustered by game) lies **entirely above 6¢**, **and** n ≥ 30 runs, **and** ≥ 10 games |
| **FAIL** | sample size met, but the mean or the interval fails |
| **NO DATA** | sample size not met |

Two details that are doing real work:

**The bar is the round-trip cost, not zero.** ~3¢ each way. A statistically
real 2¢ reversion is a confirmed phenomenon *and a losing trade*, and this
project has been burned before by edges that were real and smaller than their
costs.

**+5 min is the primary; +2 and +10 carry no gate.** Nominating the best of
three after the fact turns a 5% test into a 14% one.

**Windows do not overlap.** A run starting inside another run's horizon is
dropped — overlapping windows share a price path, and counting them separately
inflates $n$ against a gate stated in independent observations.

## Second run, 2026-08-02, under the 200ms recorder

**Still NO DATA — but the binding constraint moved.** 149 runs across **4
games**, against 30 runs across 10. The run count is now comfortably met; the
game count is not, and it is the one that was always going to bind.

682,847 live ticks examined, 4,162 observed score changes, cadence 100% under
2 minutes.

| horizon | n | mean reversion | 95% CI (clustered) |
|---|---:|---:|---|
| +2 min | 146 | −0.67¢ | [−2.95¢, +1.62¢] |
| **+5 min** | 145 | **−0.01¢** | **[−4.06¢, +4.03¢]** ← gate |
| +10 min | 144 | +0.93¢ | [−5.87¢, +7.74¢] |

Reversion at the primary horizon is **flat to four decimal places**, and the
interval sits entirely below the 6¢ round trip. Read that as a direction, not a
verdict: at four clusters the pre-registered sample condition is unmet and the
answer is NO DATA. But if this shape survives to ten games it is a **FAIL**,
and the first run's −7.25¢ can now be set aside as the one-game noise it was
reported to be.

### The camera got fixed, and it mattered

The first run's headline problem was that the score trigger fired **zero**
times — at a 910s median gap both teams have usually scored between samples, so
nothing reads as *unanswered*. At 200ms that is gone:

| threshold | runs (score trigger alone) |
|---|---:|
| ≥ 12 unanswered pts | 0 |
| ≥ 10 | 0 |
| **≥ 8** | **25** |
| ≥ 6 | 65 |
| ≥ 4 | 152 |

The study now runs on both legs. All 149 detected runs are still *labelled*
`price`, because when both triggers are live the price move almost always fires
first inside the same 2-minute window and the non-overlap rule blocks the
second — that is the detector working as specified, not the score leg failing.

Mean |price move| inside a run: **11.34¢**.

## What would change the verdict

**Six more games at 200ms.** Rows are not the constraint and never were: three
games supply **99.8%** of the 682,847 eligible ticks here, and the fourth game
in the count contributes 430 of them. See
[first-score.md](first-score.md) for the per-game table that makes the two
sampling regimes explicit.
