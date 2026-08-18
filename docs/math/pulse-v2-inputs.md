# PULSE v2 inputs — registration and first replay verdict

**Status: BUILT, MEASURED, NOT LIVE.** The v2 estimates exist behind
`MERIDIAN_PULSE_ESTIMATES` (default `v1`), and the first registered replay
(2026-08-18, below the line) says they do not yet beat v1. The flag stays at
v1 until a rerun on restored data clears the registered criterion. Nothing
above the results line may be edited after more data accrues — append.

Modules: `core/pulse/team_form.py` (inputs) ·
`core/pulse/replay_eval.py` (offline comparison) ·
`core/pulse/live.py` (`estimates_version`, per-row labelling).

## What v2 adds to v1

v1 prices every game with the pregame price, the live score/clock, and one
league constant (sigma 2.628/√min). v2 adds two point-in-time inputs from
`team_game_logs`:

1. **Per-matchup fitted volatility.** Within-game quarter-swing variance
   (drift removed by centering on each game's own mean), averaged over each
   team's last 10 completed games strictly before the as-of instant, shrunk
   toward the league moment with 8 pseudo-games, and applied to v1's own
   2.628 as a RATIO — the probit calibration stays; only the cross-section
   moves it. League baseline frozen 2026-08-18: **5.694 pts²/min** over the
   same 787 games that fitted the win curve (implied moment sigma 2.386 —
   deliberately not equal to the probit 2.628, which carries
   misspecification the moment cannot see; hence the ratio).
2. **A recent-form tempo prior for the totals anchor**:
   `mu_v2 = W·mu_v4 + (1−W)·form_total`, where `form_total` is the two
   teams' recent scoring for/against. **The fitted W is 1.0** — see below —
   so this input is currently a measured no-op, not a designed one.

Injury/lineup awareness is NOT in v2: the dispatch conditions it on Builder
B's oracle-arm verdict, which had not been delivered when this registered.
The `EventAnchors`/`ArmParams` seams are where it plugs in if B's result
says roster information can move this model at all.

## Freshness is structural

`matchup_form` refuses (returns None) when either team's newest completed
game is older than **5 days** at the as-of instant, and the engine then
prices with the v1 constants. Every decision row records which estimate set
actually priced it (`estimates_version`, per ROW, not per engine mode), and
`core/pulse/live_report.py` scores versions separately — two model
generations never blend in one number (the era-separation lesson).

This guard bit immediately: **the mirror's `team_game_logs` ends 2026-07-31**
(the ESPN season-type regression, fixed in code by PR #25; the data restore
was pending when this shipped). 36 of the archive's 42 evaluable events sit
behind that staleness.

## The registered comparison (`python -m core.pulse.replay_eval`)

Both arms walk the same recorded ticks (one per 15s bucket per market) of
every finished game with live coverage; same clock model, same anchors where
shared, same decision rule, same fill rule — differences attributable to the
estimates alone. Two measurements, clustered by game (C4):

* **Calibration**: Brier of P(YES) against the settlement-frame outcome
  (winner and spread frames are the verified ones — V19 and the 196/196
  spread measurement in `docs/math/pulse-live.md`). Paired per-game diff CI.
* **Money at price** (C11): the registered PULSE rule at unit size —
  maker entry at the touch past the config's edge threshold, +5¢ target
  exit, 10¢ FV-adverse stop, endpoint fills, unexited fills settled at the
  known outcome. The PULSE floors (≥100 filled entries, ≥10 games) gate any
  performance number per arm.

The stale cohort is evaluated with the guard deliberately disabled and
labelled — it measures degraded-form v2, which is a lower bound on informed
v2, and it is reported apart from the fresh cohort.

**Go-live criterion, registered**: v2 replaces v1 only if the paired Brier
diff's clustered 95% CI excludes zero in v2's favour in a named cohort at
≥10 games, AND v2's money-at-price is not measurably worse. Below that, the
flag stays v1.

## Blend weight: fitted, and the fit said "not yet"

Constrained least squares of final totals on (mu_v4, form_total) over the
only honest sample available — the 6 fresh-form events — clamps at
**W = 1.0**: v4-only RMSE 19.6 beats form-only 21.9, and LOGO confirms the
blend adds nothing at n=6. So `W_BLEND = 1.0` is frozen not as a design
choice but as a measurement; `--fit-blend` reruns the fit when the restored
logs make the other 36 events fittable, and the constant moves only by hand,
with this doc, never silently at runtime.

---

*Registered and first-measured 2026-08-18. Results append below; the section
above does not change.*

## Replay results — 2026-08-18, archive through the afternoon slate

42 events evaluated (6 fresh-form, 36 stale-form). Verbatim from
`core.pulse.replay_eval` (JSON archived with the PR):

```
[fresh-form]  games: 6   calibration points: 8,665
  Brier v1: 0.25440   Brier v2: 0.25431
  paired diff (v1−v2), clustered: +0.00010  95% CI [-0.00331, +0.00351]  (G=6)  -> no separation
  [v1] entries 336 | fills 192 | trips 156 | rides 36 | games 6 | BELOW FLOORS — counts only
  [v2] entries 345 | fills 193 | trips 157 | rides 36 | games 6 | BELOW FLOORS — counts only

[stale-form]  games: 36   calibration points: 104,155
  Brier v1: 0.19730   Brier v2: 0.19703
  paired diff (v1−v2), clustered: +0.00027  95% CI [-0.00020, +0.00074]  (G=36)  -> no separation
  [v1] entries 3,235 | fills 1,875 | trips 1,748 | rides 127 | games 36 | per-$ -0.0088 [-0.0362, +0.0186]
  [v2] entries 3,237 | fills 1,878 | trips 1,749 | rides 129 | games 36 | per-$ -0.0108 [-0.0385, +0.0186]
```

**Verdict: v2 stays offline.** No cohort separates on calibration; trading
capture is indistinguishable between arms. The criterion is not met and the
default remains `v1`.

Two findings worth as much as the verdict:

1. **The comparison is currently starved, not settled.** The fresh cohort is
   6 games; the input most likely to matter (recent form) is exactly what
   the July-31 log staleness suppresses. Rerun after B's backfill:
   `python -m core.pulse.replay_eval` (and `--fit-blend`); tonight's four
   games join the archive automatically.
2. **First measured number on the registered PULSE trading rule itself**:
   at unit size over 36 stale-cohort games, per-$ capture is −0.9¢
   [−3.6¢, +1.9¢] — a CI spanning zero with a mildly negative center, from
   the arm (v1) whose estimates are tonight's live baseline. Not a verdict
   (15s sampling, unit size, no Kelly, floors met only in one cohort), but
   the first evidence either way, and it does not scream edge. The live
   shadow run's own tape remains the registered measurement.
