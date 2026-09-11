# Kalshi settled backtests: a 20¢ edge that was three artifacts, and a reversal that half-replicates

`kalshi_settled_backtest.py <SERIES> <espn_league> <schedule.json> <out.json>` — any Kalshi
football series, DraftKings **closing** moneyline via ESPN, 1-minute candles, outcomes in
hand. Two pre-registered tests. Run on NFL preseason (49 games) and CFB weeks 0–2 (137 games).

## Test 1 — pregame softness. The number went 20 → 5.9 → 1.5 → 0, and each step is named.

| pass | CFB heavy favourites (DK ≥ 0.9) | removed |
|---|---|---|
| first run | gap **−20.2¢**, Kalshi mid 0.73, won 82/84 | — |
| fixed matcher (suffix → names → nickname) | −5.9¢ [−10.0, −1.7] | most side-flips |
| flip guard (\|mid − DK\| > 60¢ on a live book) | ask **−1.30¢ [−2.08, −0.52]**, n=59 | 3 remaining flips |
| **against outcomes** | Kalshi ask **0.950**, realized **0.949**, DK 0.963 | — |

**The cause:** name containment. Asked to place "Washington State," the matcher found
`"washington" in "washingtonstate"` and paired it with **Washington** — the other side.
The underdog's 5¢ market then sat under the favourite's 96% line as a −90¢ row, and three
of those on 84 rows made a 20¢ "edge." The fingerprint is a heavy favourite priced under
0.5 with a live spread; the script now excludes and counts it.

**What survives:** Kalshi's CFB favourites trade ~1.3–1.5¢ below DraftKings' close — a real
price gap — **and the favourites won at Kalshi's price, not DraftKings'.** EV of buying
favourites at the Kalshi ask, net of fee: −0.37¢ [−6.17, +5.42] (≥0.9), −1.52¢ (0.7–0.9).
Brier Kalshi − DK on clean rows: +0.0064 [−0.0018, +0.0145], spans zero. **Not soft. Not an
edge.** NFL preseason, same script, 49/49 games: gap −0.12¢ [−0.58, +0.33], Brier +0.0022,
spans zero.

## Test 2 — in-game overshoot

| population | h=2 strata (% of jump, 95% CI excludes 0?) | β at h=1/2/5 |
|---|---|---|
| NFL preseason, 49 games, 4,365 moves | −5.0 / **−6.3** / −4.9% — ≥2¢ excludes zero | spans / spans / spans |
| **CFB wk 0–2, 132 games, 8,527 moves** | −2.5 / −2.5 / −4.8% — only ≥3¢ excludes zero | **all three negative, all exclude zero** |
| CFB 30-game sample, traded minutes only | +0.05¢ [−0.36, +0.46] | — |

**Direction replicates** — on a second sport, in season, the slope of subsequent drift on
the jump is negative and excludes zero at every horizon on 132 games. **Magnitude halves**
(~2.5% vs ~6%) and in cents it is marginal (−0.08¢ at ≥1¢, −0.29¢ [−0.58, −0.01] at ≥3¢).
Restricting to traded minutes on a 30-game sample, it vanishes. Read: a small, real
overshoot on the venue, strongest on NFL, well under Kalshi's spreads and fees on either
sport. Whether it exists on Polymarket US — no maker fee, 0.5¢ spread — is pre-registered
(`docs/math/e8-nfl-preregistration.md`, H1; `cfb/run_overshoot.py`).

Inputs: `espn_preseason_2026.json`, `espn_cfb_2026_wk0-2.json`. Outputs: `kalshi_nfl_pre_results_v3.json`,
`kalshi_cfb_results_v2.json`. Kalshi candles must be windowed (5,000 cap); `yes_sub_title` is
"TEN Titans" on NFL and "Louisville" on CFB; aliases WAS→WSH, JAC→JAX, LA→LAR.
