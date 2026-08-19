# Moneyline and spread — the first pregame baseline

```bash
python -m core.backtest.moneyline
```

Totals had a walk-forward backtest; the operator's primary market did not.
This is that measurement, on the only basis the data honestly supports.

## The numbers, 2024–2026

787 games considered · 2 with no usable odds · 15 with features too thin.

| market | bets | games | ROI | 95% CI (game-clustered) | hit rate @ entry cost |
|---|---|---|---|---|---|
| moneyline | 624 | 624 | +0.85% | **[−7.9%, +9.9%]** | 40.87% @ 0.405 |
| spread | 638 | 638 | −3.95% | **[−11.1%, +3.5%]** | 50.31% @ 0.524 |

**Both intervals cross zero.** Neither market is a measured edge and neither is
a measured loser. That is the headline, and it is a *baseline*, not a verdict.

Read the hit rates only beside their entry costs (C11). Moneyline hits 40.87%
against a 0.405 breakeven and spread hits 50.31% against 0.524 — both land
almost exactly on their own breakeven, which is what an ROI near zero means.

## CLV is absent on purpose

No `mean_clv` is reported, and it is not an oversight.

CLV needs an entry line and a genuinely *different* closing line. Totals have
that — ESPN's historical rows carry `open_total` and `close_total` as two
columns on one row. Moneyline and spread do not, and this was measured:

* 1,697 games carry a moneyline; the multiple rows per game are **different
  sportsbooks** (6.92 on average, up to 16), not a time series.
* Within one provider, only 51 game-provider pairs show any moneyline variation.
* Every odds row was captured **after** the game finished — median ~4 years
  after. `captured_at` is backfill time, not observation time.

So the 1,192 games where the moneyline "changed" are cross-provider
*disagreement*, not market *movement*. Taking another book's number as "the
close" would put a corrupted CLV in the same column as the totals engine's real
one. The venue-specific version is answerable forward from the 200ms Polymarket
archive, and belongs in the in-game replay.

## The sign error this nearly shipped

The first run reported **spread ROI −7.27%, CI [−14.3%, −0.26%] — excluding
zero.** Combined with `ANCHOR_MARKETS = {TOTAL, SPREAD}`, that was one sentence
away from "the executor trades a market that measurably loses."

It was a bug. `sportsbook_odds.spread` is the home **handicap** (negative when
home is favoured); `prob_cover` is `P(home margin > line)` and wants the number
the margin must **exceed**. Negatives of each other. The draft passed the
handicap straight through, so the model priced `P(margin > −5)` while
settlement scored `margin > +5` — betting the opposite side of the one it was
graded on, every game.

Correcting it moved spread to −3.95% [−11.1%, +3.5%], crossing zero. **A wrong
sign is not a missing value** (V19): it yields a confident answer of the wrong
shape, and confident-and-wrong survives review better than blank. The
convention is now asserted directly in `tests/test_moneyline_backtest.py`
rather than implied by an end-to-end number.

## Why the model "barely takes" the moneyline

It is not the model declining. At a 3-point probability threshold it takes the
moneyline in 624 of 787 games. **The executor refuses it**:
`ANCHOR_MARKETS = {TOTAL, SPREAD}`.

That exclusion rests on two claims, and they are not equally strong:

1. *"The market's margin MAE (9.65) beats ours (10.19), so betting our
   disagreement loses."* Independent, and untouched by anything here.
2. *"33.4% hit rate, entire 95% interval [0.178, 0.339] below the 0.524
   breakeven."* This benchmarks a hit rate against **0.524** — the breakeven of
   a −110 two-way market. Moneyline entries here average **0.405**, and a
   40.87% hit rate at 0.405 is breakeven, not a loss.

That is the C11 shape exactly: the category error C11 exists to name. It does
**not** follow that the exclusion is wrong — claim (1) stands on its own, and
the two runs differ in selection rule, shrinkage and sample, so they are not
directly comparable. What follows is narrower and worth doing: re-score that
exact selection in the money frame before the exclusion is cited again.

## Assumptions that are load-bearing

* **Spread juice assumed −110/−110.** `sportsbook_odds` has `over_odds` and
  `under_odds` for totals but no spread-price columns. A systematically wrong
  assumption biases spread ROI, and it is the first thing to check if these
  numbers ever look surprising.
* **Live providers excluded**, reusing `engine._is_live_provider`. A line set
  during the game reflects the score so far — catastrophic lookahead, not a
  small bias.
* **Prices de-vigged proportionally**, so the model is compared against the
  book's belief rather than its margin.
* **Uncertainty is game-clustered** (C4). One game's moneyline and spread bets
  are the same disagreement seen twice; treating them as independent would
  understate the interval by roughly √2 on exactly the games that matter.

## Not yet done

In-game ML/spread replay against the 200ms archive (62 moneyline events, 56
spread events). That is where CLV *is* computable, because the tick archive is
a real time series rather than a backfilled consensus.
