# E8 — the NFL win-probability head reproduces nflfastR

**Same recipe, NFL-native data.** The CFB WP model is the nflfastR recipe
fitted on CFBD; pointing it at NFL games would have been a transfer with no
test behind it. This fits the *identical* code path — `GameState`,
`build_features`, `fit()`, monotone constraints, degrade-timeouts-to-serving —
on nflverse play-by-play 2022–2024, held out **by game**, and scores it against
nflfastR's own shipped `vegas_wp` on the same held-out plays. That comparison
can fail, which is what makes it a test of the port rather than a description
of it.

## Result

| | value |
|---|---|
| train | 94,452 plays / 650 games |
| held out (disjoint) | 23,886 plays / 163 games |
| Brier | **0.1579** vs base-rate 0.2500 — skill 36.8% |
| vs nflfastR `vegas_wp`, same plays | ours 0.1579, theirs 0.1572 — **+0.0007 [−0.0044, +0.0059]**, G=163, G_eff 162.5 |

**Spans zero at G_eff 162.** The port reproduces the production model it was
copied from, to within 0.0007 Brier. Monotone in score differential: WP
0.280 → 0.958 across −21…+21.

| feature | gain |
|---|---|
| score_differential | 39.1% |
| diff_time_ratio | 24.6% |
| spread_time | 24.3% |
| yards_to_goal | 3.5% |
| game_seconds_remaining | 3.2% |

Calibration is within ±0.01 from the 40th to 80th percentile; slightly
under-confident at 10–20% (+0.053) and over-confident at 90–100% (−0.036).

## Sign convention, asserted not assumed

nflfastR's `spread_line` is **positive when the home team is favoured**; ours
is negative. So `closing_spread = −spread_line`, and before any fit each
season's data is checked: corr(spread_line, result) must exceed 0.2. It did —
+0.385, +0.426, +0.501. This class of sign error inverted the CFB model's
monotone constraint once and made its most valuable feature inert; the check
exists so it cannot happen silently again.

## What it is for, and what it is not

It is the shield for E1 on NFL tape (`LEAGUE=nfl` selects it; the CFB head is
never pointed at NFL games). It is a model result on held-out games. **Not
edge.** E2 showed the CFB head's advantage over ESPN was line knowledge the
market already had; nothing here says the NFL head is different in kind. What
it says is that the recipe is correctly implemented for NFL, which was the
precondition for Thursday meaning anything.

A defect on the way: the first full run left a truncated `meta.json` — the
JSON dump hit a numpy float mid-write while the model artifact, written first,
was sound. I read a grep exit code as the script's and briefly reported the fit
failed. The dump is numpy-safe now.

Artifact: `artifacts/nfl_wp_regulation.json` (+ meta, + `nflfastr_wp_cache.json`).
Script: `cfb/run_nfl_wp_fit.py` (`SMOKE=1` for a 10-second dry run).
