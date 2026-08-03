# News windows

**Question:** when news breaks, does Polymarket US lag the sportsbooks long enough to trade?

This is Experiment 4, and it is the successor to the injury experiment. That one established that *being informed* is worth nothing — the closing line already prices lineups. What might still be worth something is *being early*.

## The thesis

Sportsbooks reprice on news within seconds. A thin venue may still be showing the old number minutes later. A resting (maker) order at the stale price captures the move without paying a spread.

## How a window is defined

1. **Trigger** — between two consecutive book polls for the same game, the multi-book consensus total moves ≥ 1.5 points. We never see the headline, only the market's reaction to it, which is the tradable part anyway.
2. **Response** — fit the Polymarket totals ladder to an implied mean at each snapshot cycle and compare it against the **new** book number.
3. **Staleness** — `|PM implied mean − new book line|`. Near the size of the move means PM has not repriced at all; near zero means it repriced before we could look.

Staleness is then converted to a probability edge through the same sigma the model prices with, and fees are subtracted. Only what survives counts. A 2-point stale line is not 2 points of profit.

## Two guards against inventing windows

- **Sampling holes are not events.** Pairs of polls more than 45 minutes apart are skipped. Without this, every overnight gap registers as a huge "move" and the detector reports windows it never observed.
- **Live-odds providers are excluded.** Their lines are set during the game, so every score change would look like news.

## Result: no data

| | |
|---|---|
| Consecutive book-poll pairs examined | 61 |
| Moves ≥ 3.0 pts | 0 |
| Moves ≥ 2.0 pts | 0 |
| **Moves ≥ 1.5 pts (the trigger)** | **0** |
| Moves ≥ 1.0 pts | 2 |

**Zero triggers. The experiment has not run.**

This is not a null result, and the distinction matters. A null result means the hypothesis was tested and failed. Zero triggers means it was never tested. The detector is built, tested (18 cases) and will accrue — what it needs is time and a faster cadence, not a different analysis.

## The structural problem, stated plainly

Even when triggers arrive, the current cadence may not resolve them:

| Leg | Cadence |
|---|---|
| Sportsbook lines | ~20 min |
| Polymarket US | 15 min near tip-off, **60 min idle** |

The literature describes the lag in **minutes**. Samples an hour apart cannot measure it. So a future null from this detector would be ambiguous in a specific way: it could not distinguish "PM repriced quickly" from "PM repriced slowly and we blinked". The report says so rather than reading silence as evidence of efficiency.

**This is the binding constraint on Experiment 4, and it is a cadence decision, not a modelling one.** Book polling only began at 20-minute resolution on 2026-07-31; before that it was every 6 hours and completely blind to windows.

## Gate

Pre-registered: a maker order at the stale PM price shows positive expected CLV surviving fees for ≥ 1 poll interval, at **n ≥ 30 windows**. Below that the report returns INCONCLUSIVE and refuses to quote an edge.

## Status

**Built, accruing, no verdict** (2026-08-01). Run with `python -m core.window_detector`. The injury change log is timestamped and feeds the same question — "star ruled out at 18:42" is exactly the trigger this is looking for, and is the reason that log is kept despite its own experiment failing.
