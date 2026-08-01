# Performance targets — what "good" actually looks like

Set 2026-08-01, so results get judged against pre-registered bars instead of
vibes. Breakeven at standard −110 pricing is **52.38%**; on Polymarket as a
maker it is roughly the model's probability minus ~1¢ of costs.

## Tiers

| Tier | Hit rate (vs spread/total) | Mean CLV vs true close | What it means |
|---|---|---|---|
| Broken | < 50% | negative | worse than random, stop |
| Market-mirror | 50–52.4% | ≈ 0 | matches the book, loses the vig — **where v3 is now** |
| Viable | 52.4–54% | > 0, CI still crossing 0 | pays for itself, not yet provable |
| **Good** | **54–55% sustained** | **> +0.5 pts, 95% CI > 0** | real, defensible edge |
| Elite | 55%+ long-run | > +1.0 pts | professional-grade; rare, verify for leaks |

Calibration target at every tier: realised frequency within **±3 points** of
predicted in every bucket with n ≥ 30, and edge→return correlation **> +0.10**
with a CI excluding zero. (v3 today: buckets off by ~8–15 points, correlation ≈ 0.)

## Sample sizes — the part everyone skips

Distinguishing a 54% bettor from the 52.4% breakeven at 95% confidence needs
roughly **n ≈ 1,500–3,000 bets**. A WNBA season produces ~250–300 games.

Consequences:
- Nothing under ~300 bets is evidence of anything. Three days of wins is noise
  by construction — as is three days of losses.
- **CLV is the fast metric**: measured on every bet, it reaches significance in
  low hundreds. It is the primary gate; ROI is the slow confirmation.
- Multi-season backtests are not optional. They are the only way to reach n.

## Gates before real money

1. **Backtest gate:** mean CLV > 0 with 95% CI excluding zero on n ≥ 300, under
   the *realistic* fill model, calibration within tolerance.
2. **Shadow gate:** ≥ 60 days of shadow orders whose live CLV (vs recorded
   Polymarket prices) is positive with CI excluding zero.
3. **Sizing gate:** quarter-Kelly, and edges shrunk by the measured incremental
   slope (~0.4) before sizing — raw model-minus-market gaps are mostly our own
   error (see [research-notes.md](research-notes.md)).

No tier of ROI overrides a failed calibration check: an uncalibrated model
that is winning is winning by luck.

## Current standing (walk-forward 2024–2026, realistic fills)

| Market | Hit | ROI | Verdict |
|---|---|---|---|
| Totals (v3) | 51.0% | −3.05% | market-mirror |
| Spread (v3) | 50.8% | −3.35% | market-mirror |
| Moneyline (v3) | — | −6.13% | miscalibrated (no HCA term; winner's curse) |

The cross-market gap strategy has **no backtest yet** — its paired
Polymarket-vs-book data began accruing 2026-07-31.
