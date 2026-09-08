# Kalshi NFL 2026 preseason, 49 settled games: neither lag-free edge exists

Two pre-registered tests on the one settled dataset reachable without prod:
Kalshi's `KXNFLGAME` preseason markets (98 markets / 49 games, Aug 7–29, all
settled), 1-minute candles via the public API, DraftKings' **closing** moneyline
via ESPN's odds feed. No model, no lag, outcomes in hand.

**Population caveat first.** Preseason: starters sit, books are softest, retail
thinnest. A negative here is a *strong* negative — if a venue is not soft against
DraftKings when DraftKings is least sharp, it will not be soft in September. A
positive would not have transferred without re-testing.

## Test 1 — pregame softness (favourite side, n=49 games)

| | value |
|---|---|
| Kalshi last pre-kickoff mid − DK close, **power devig** | **−0.18¢ [−0.61, +0.25]** |
| same, proportional devig (artifact direction) | +0.37¢ [−0.07, +0.81] |
| Brier Kalshi 0.2684 vs DK 0.2665, 98 markets | +0.0019 [−0.0027, +0.0065], G=49 |
| Kalshi favourite spread at close / taker fee | 1.02¢ / ~1.70¢ |
| mean favourite prob: DK 0.589, Kalshi 0.587 | favourites went 22/49 |

**Not soft.** The venue and the sharp book agree to two-tenths of a point, and
Kalshi's price is as good a forecast as DraftKings' close. Consistent with the
in-season week-1 snapshot on both venues (`../pregame_softness/`).

## Test 2 — in-game drift (4,361 one-minute moves ≥1¢, 49 games)

| h (min) | β, drift on jump | continuation |
|---|---|---|
| 1 | −0.013 [−0.039, +0.013] | −0.04¢ [−0.16, +0.08] |
| **2** | −0.045 [−0.098, +0.008] | **−0.18¢ [−0.34, −0.02]** |
| 5 | +0.038 [−0.041, +0.117] | −0.02¢ [−0.28, +0.24] |

**No continuation at any horizon** — the underreaction hypothesis is dead on
this venue as it was on ours. One statistic excludes zero: a 0.18¢ reversal at
two minutes. One of three horizons, marginal after multiplicity, a tenth of the
fee. So it was stratified by shock size, three strata pre-specified:

| \|jump\| ≥ | n | continuation @2 min | as % of jump |
|---|---|---|---|
| 1¢ | 4,361 | −0.18¢ [−0.34, −0.02] | −5.5% |
| 2¢ | 2,655 | −0.29¢ [−0.53, −0.05] | −6.4% |
| 3¢ | 1,765 | −0.30¢ [−0.59, −0.00] | −5.2% |

**It scales.** A constant ~6% of the shock reverts within two minutes, in every
stratum, each excluding zero. Noise does not do that; an overshoot does. This is
the first microstructure regularity of the season that excludes zero,
replicates, and has a mechanism. It is also small — 0.2–0.3¢ on typical shocks —
which is under Kalshi's fee for either side. **Where it could matter is
Polymarket US, whose maker fee is zero and whose NFL winner spread is 0.5¢.**
That test is pre-registered in `../../docs/math/e8-nfl-preregistration.md`.

Script: `kalshi_preseason_backtest.py <espn_preseason_2026.json> <results.json>`.
Kalshi ticker `KXNFLGAME-26AUG29CHITEN-CHI` = date + AWAY+HOME + team; aliases
WAS→WSH, JAC→JAX, LA→LAR against ESPN. Candle windows must be bounded (5,000 cap).
