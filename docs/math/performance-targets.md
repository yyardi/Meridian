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

## Current standing (walk-forward 2024–2026, realistic fills, updated 2026-08-01)

| Market | Hit | ROI | Mean CLV [95% CI] | Verdict |
|---|---|---|---|---|
| **Totals, recent-form** | 54.1% | **+3.06%** | **+1.75 [+1.45, +2.06]** | passes the CLV gate; see caveats |
| Totals, season means | 51.0% | −3.05% | +0.83 | market-mirror |
| Spread (+HCA) | 51.6% | −1.78% | n/a | market-mirror |
| Moneyline (+HCA) | 39.0% | −2.42% | n/a | still miscalibrated |

**Recent-form caveats, stated before anyone bets it:**
- Per-season ROI is unstable: +1.5% (2024), +5.8% (2025), **−9.3% (2026)** —
  while 2026 CLV stayed +1.69 [+1.14, +2.24]. Beating the close while losing
  money at n=89 is what outcome noise looks like at σ≈21, but it is also what
  a decaying edge looks like. Only more data distinguishes them.
- Calibration still fails above 0.65 (predicted 0.65 → realised 0.55).
- This was the ~5th configuration examined; multiple comparisons inflate the
  best result even when the hypothesis was stated in advance. The shadow log
  is the true out-of-sample test.
- Does not survive pessimistic (taker) fills: −4.0%. Maker-only discipline is
  load-bearing.

**Shrinkage verdict:** shrinking edges by the walk-forward incremental slope
leaves only 67 genuine disagreements with the book in three seasons, and they
hit 50.0%. Against season-mean features there is **no tradeable totals edge vs
the sportsbook** — the recency features and the venue gap are what remain.

Cross-market gap: first paired observations (n=2 resolved) show sub-point
gaps on liquid pregame evenings; the 6–8 point gaps that motivated the
project appear intermittent. The table grows nightly.
