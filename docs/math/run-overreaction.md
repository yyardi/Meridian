# Run overreaction — do prices overshoot a run and come back?

**Status: NO DATA.** 8 runs across 1 game, against a pre-registered minimum of
30 across 10. The detector is built and accruing.

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

## What the first sample looks like

One game. Not a result.

| horizon | n | mean reversion |
|---|---|---|
| +2 min | 8 | −5.56¢ |
| **+5 min** | 8 | **−7.25¢** |
| +10 min | 7 | +4.43¢ |

All eight triggers were **price** triggers; the score trigger fired zero times
at ≥ 8 unanswered points and only five times at ≥ 4. That is a cadence
artifact, not a fact about basketball: at a 910s median gap, both teams have
usually scored between consecutive samples, so almost nothing reads as
*unanswered*.

## What would change the verdict

Ten games under the 1s recorder. The score trigger should start firing properly
at 1s sampling, which is the point — right now the study is running on one of
its two legs.
