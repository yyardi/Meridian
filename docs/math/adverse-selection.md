# Adverse selection — does the spread survive being filled?

**Status: the gate is met and the answer is negative.** In-game, a resting
quote loses **−2.74¢ per fill** (95% CI [−3.03, −2.44], clustered by game),
over **1.94M quote-windows across 13 games** — against a pre-registered
minimum of 500 windows across 10. Pregame: **−0.86¢** ([−1.14, −0.58], 28.2k
windows / 30 games).

Source of record: [findings.md](../findings.md) (the measured table, "In-game
(30s, 1s cadence, local)"). Those are C13's inputs and the numbers
[quote-shadow.md](quote-shadow.md) and `core/quote/engine.py` both cite.

> **Superseded, kept as the record:** this file previously read *"Status: NO
> DATA. 57 quote-windows across 1 game."* That was the 2026-08-02 first run
> and it was true then. The gate was passed later and this document was not
> updated, so for some weeks the study's own write-up said the experiment had
> never reached its gate while the number it reached circulated in three other
> places. Corrected 2026-09-06; the failed first run stays visible because a
> superseded result is part of the record, not an embarrassment to delete.

**Both arms are optimistic bounds** — the fill rule undercounts the fills that
hurt — and the two arms are *different measurements*, not one split by a flag:
different horizons (30s vs 900s), different cadences, and different databases.
The in-game arm ran against the local mirror, which was retired at the
2026-08-20 cutover; it cannot be reproduced, only re-measured on a different
substrate.

Module: [`core/quote/adverse_selection.py`](../../core/quote/adverse_selection.py) · Gates **QUOTE**

## The question

The at-the-money spread here is ~3¢ live and ~6¢ pregame — 6–12% of contract
value, against ~0.01% in equities. That looks like an invitation, and the usual
reading is right: nobody is making this market, so you are not racing Citadel.

But a market maker does not earn the spread. It earns **the spread minus adverse
selection**. Your resting bid fills precisely when someone wants to sell, and
the reason they want to sell is usually that the price is about to fall. Fill
often enough at the wrong moment and a 3¢ spread is a slow way to lose money.

So: *if you had a resting quote at the best bid or offer, how far does the mid
move against you in 30 seconds, and does the half-spread cover it?*

## The decomposition

For a quote at time $t$ with bid $b$, ask $a$, mid $m$, spread $s$, and mid
$m_H$ at the horizon:

$$
\text{net}_{\text{bid}} = m_H - b = \underbrace{(m-b)}_{s/2 \text{ captured}} + \underbrace{(m_H - m)}_{\text{run over by}}
$$

$$
\text{net}_{\text{ask}} = a - m_H = s/2 - (m_H - m)
$$

That identity *is* the question. Positive means the spread covered the adverse
selection; negative means it did not.

Fees are taken as **zero, not as a maker rebate**. A rebate only makes the
result look better, and a gate that can be passed by an accounting assumption
is not a gate.

## The pre-registered gate

Fixed 2026-08-02, before any number was computed.

| | |
|---|---|
| **PASS** | mean net capture > 0, **and** 95% CI (clustered by game) excludes zero, **and** n ≥ 500 windows, **and** ≥ 10 games |
| **FAIL** | sample size met, but the mean or the interval fails |
| **NO DATA** | sample size not met |

Condition four usually binds, and that is deliberate — see
[clustered-errors.md](clustered-errors.md).

## Two constraints that bound what this can say

**The fill rule is optimistic by a known sign.** Between snapshots we see only
endpoints. A mid that dipped below your bid and recovered inside the window
filled you and is invisible here — so the measurement undercounts exactly the
fills that hurt. Therefore:

> A **FAIL** is trustworthy (reality is worse). A **PASS** is an upper bound,
> and would not on its own authorise building QUOTE.

**Cadence.** Snapshots before 2026-08-02 came at a 910s median gap (the pregame
recorder's 15-minute sweep interleaved with the live recorder's ~35s), so a 30s
horizon was a single hop with no interior. The 1s recorder shipped 2026-08-02;
see [../infra/live-cadence.md](../infra/live-cadence.md).

## What the first sample looks like

Not a result — one game, and the gate is ten. Recorded only so the next reader
knows what to expect.

| | |
|---|---|
| Mean half-spread available | +1.55¢ |
| Mean \|mid move\| over 30s | 5.61¢ |
| Windows with a fill | 44 / 57 |
| Mean net capture | **−5.57¢** |

The shape of the problem is visible even here: the mid travels ~3.6× the
half-spread over the horizon. If that survives ten games, QUOTE is dead in its
naive form and would need either a much faster quote-pull or a directional skew
to live. **But one game is one game.** The number above is not evidence.

## What would change the verdict

Ten games of 1s data. At ~4 games a slate that is under a week of recording.
