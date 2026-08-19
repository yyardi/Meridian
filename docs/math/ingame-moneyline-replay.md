# In-game moneyline — replayed against the 200ms archive

```bash
python -m core.backtest.ingame_replay
```

This is the measurement the `/picks` live-FV strip has been waiting for. That
strip renders `core/live_fv.py`'s formula beside the book with a caption saying
it is unvalidated and nothing trades on it. Here it is, replayed.

**It is also the one place CLV is real.** The pregame ML/spread backtest
reports none, because the odds history has no open→close pair
(`moneyline-spread-baseline.md`). The tick archive is a genuine time series of
the venue's own book, so a price struck at 21:14 and the same market's price at
21:19 are two observations of one market moving.

## The numbers

62 moneyline markets in the archive · 53 entries across **53 games** · 8
skipped for no pregame prior · 0 for an unusable clock · 0 unsettled.

| | value | 95% CI (game-clustered) | crosses zero |
|---|---|---|---|
| money-at-price ROI | **+5.96%** | [−12.25%, +23.16%] | **yes** |
| mean CLV | **+0.96¢** | [−0.73¢, +2.56¢] | **yes** |
| hit rate | 66.0% @ entry cost 0.623 | — | — |

**Both cross zero at 53 games.** Point estimates lean positive and neither is a
measurement yet. The hit rate sits a little above its own breakeven (0.660 vs
0.623), which is what a small positive ROI looks like in the C11 frame.

## The CLV I nearly reported was the outcome restated

The first draft took the reference price from the market's **last** observed
tick. By then 87% of markets had effectively settled — mid above 0.95 or below
0.05 — and the resulting "CLV" correlated **+0.980** with realised P&L.

That is not a second, faster-converging metric. It is the same number wearing a
different name, and printing the two side by side would have implied
corroboration that did not exist.

The reference is now the market's own mid **300 seconds after entry, required
to still be in play**. Measured effect of the correction:

| | first draft | corrected |
|---|---|---|
| references effectively settled | 87% | **0%** |
| corr(CLV, realised P&L) | **+0.980** | **+0.240** |
| mean CLV | +2.45¢ | **+0.96¢** |

The inflation was the outcome leaking in. An entry struck closer to the whistle
than the horizon now has **no** CLV and says so, rather than falling back to a
price that is really just the result.

The general form is worth more than the instance: **a metric that cannot
disagree with the metric beside it is not evidence.**

## What the replay assumes, stated because it is load-bearing

* **Entries cross the spread** and pay the far touch, charged the taker fee.
  The executor is limit-only in production, so a resting order would usually do
  better — but it also sometimes does not fill, and assuming the good half of
  that is how a replay flatters itself. Crossing is the conservative floor:
  whatever survives it is not a fill-model artifact.
* **One entry per market, ever.** Compounding turns one disagreement into a
  position size, which is a sizing question rather than a signal question.
* **A market with no pre-live tick is skipped**, never defaulted to 0.5. A
  coin-flip prior on a 0.68/0.30 matchup is the assumption that made hypothesis
  #16 look like a 6.8¢ edge before the confound check inverted it.
* **Overtime and unknown periods are skipped**, not approximated —
  `Clock.usable` is False for both. Past regulation the pregame edge is spent
  and the 40-minute denominator describes nothing.
* **Minutes remaining is an estimate** inside a period; the ticks carry
  `event_period` and no game clock. Only a period boundary is exact. This is
  inherited from `live_fv.py` and is not re-litigated here.

## What this does not say

That the strip should start trading. 53 games, both intervals spanning zero,
and a formula whose one prior hypothesis inverted under a confound check. The
right reading is a registered, accruing measurement with a positive lean —
worth re-running as the archive grows, and worth nothing as a green light.

Spread is not replayed: no in-game spread fair value exists to replay. The
win-curve machinery generalises to `P(final margin > line | time)` and that is
the natural next build.
