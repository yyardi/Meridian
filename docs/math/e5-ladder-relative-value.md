# E5 — ladder relative value: could-not-measure, and the tape is the reason

**Long-K / short-(K+7) pairs on the full-game spread ladder, held to
settlement, one position per game×pair at the first instant the model's
interval probability disagrees with the market's by more than τ.** Taker
entry on both legs, 0.06·p(1−p) fee per leg, no rebate. Everything
pre-registered in the script docstring before the first run: τ=0.05 primary,
0.03/0.08 secondary; leg spread > 6¢ skipped; stale (>5 min) excluded and
counted; settlement from final scores; game-clustered; model = E3 v2, chosen
on the 813-game CFBD holdout, not on this tape.

## Result

| arm (τ=0.05) | n | G / G_eff | net of spreads + fees | mid-to-mid, no costs |
|---|---|---|---|---|
| all pairs | 311 | 43 / 27.1 | **−0.53¢ [−5.87, +4.80]** | +3.79¢ [−1.50, +9.07] |
| long interval only | 170 | 37 / 21.5 | −1.18¢ [−9.63, +7.27] | +3.13¢ [−5.26, +11.52] |
| short interval only | 141 | 41 / 27.7 | +0.25¢ [−6.55, +7.04] | +4.58¢ [−2.18, +11.34] |
| τ=0.03 (secondary) | 330 | 44 / 28.3 | −2.20¢ [−7.41, +3.01] | +2.13¢ |
| τ=0.08 (secondary) | 260 | 42 / 23.6 | −2.37¢ [−9.32, +4.57] | +1.90¢ |

**Gate ("positive game-clustered edge net of fees"): fails.** Every arm spans
zero. The 25-game floor is met (G_eff 27) and it is not enough: a pair is a
~16% binary event and its per-position variance swamps 43 games.

The decomposition does not settle *why*. The model claims a mean 7.7¢ of edge
per pair and realises +3.8¢ mid-to-mid — directionally right, half the size,
not distinguishable from zero. Crossing two spreads plus fees costs ~4.3¢ on
a 17¢ mean premium. So the point estimates say "the disagreements lean right
and the costs eat them," and neither half is established.

## The finding that is not about the model

**210,725 stale against 12,259 tradeable instants.** At 94% of (play, pair)
instants, at least one of the two rungs had no snapshot on our tape within 5
minutes. Stated precisely: *our tape has no snapshot* — the recorder samples
deep rungs on a slow tier, so this conflates the venue not quoting with the
recorder not looking. Whichever it is, **a pair cannot be traded from this
tape**, and the 311 positions that survived sit near the line where the
recorder samples often, which is a selection this doc does not correct for.

Ladder spreads are also wide: live median 4¢, p75 17¢, against winner
markets' 0.5¢. 15,444 instants were dropped for a leg over 6¢.

## Guards that fired the right way

- Frame (YES ⇔ home margin < line): 1,697 agree / 95 disagree at last live
  snapshot. An inverted frame would fail nearly every rung.
- Model identity is printed from the meta on disk, because the E3 artifact
  paths crossed once (v2 saved over v1 — an override sat above the assignment
  it was meant to override, and I read the code instead of the file).
- Each τ has its own first-qualifying instant. A shared entry let the loosest
  arm consume a pair before a stricter arm ever saw it qualify; that would
  have under-counted the primary.

## What this is not

Not a verdict on ladder relative value. It is a verdict on what 43 games of a
sparsely-sampled ladder can measure, which is nothing at this effect size.
Two things would change it: more Saturdays, and a recorder tier that samples
the near-the-money ladder as often as it samples the winner market.

Script: `cfb/run_ladder_rv.py`. Model: `artifacts/cfb_cover_regulation_nearline.json`
(v2; the v1-path file was v2 at run time, see meta).

## Pooled re-run, 2026-09-07 — 73 games after the map rebuild

| arm (τ=0.05) | n | G / G_eff | net of spreads + fees | mid-to-mid |
|---|---|---|---|---|
| all pairs | 347 | 45 / 29.5 | **−2.41¢ [−8.46, +3.63]** | +1.92¢ [−4.05, +7.90] |

Eighteen more games, 36 more positions, no resolution. Stale instants rose to 296,094
against 11,936 tradeable — the added Saturday games are sampled even more sparsely.
