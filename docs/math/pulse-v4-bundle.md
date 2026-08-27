# PULSE v4 — the full-signal bundle (registration)

**Status: REGISTERED BEFORE BUILT.** Written 2026-08-24 ~16:20Z, before any
v4 code or number exists. Floors and criterion are fixed here and gate only
on games recorded after this document's timestamp. This section may not be
edited after the eval first runs at floor — append below the line.

## The deliberate trade-off, stated for the record

Protocol #38's one-input-per-gate cadence bought clean attribution at the
cost of weeks per signal. The operator's constraint ("if the model had more
data from the in-game realtime stuff then we can design strategies around
those") makes that cadence the binding cost, so **v4 registers the signal
set as ONE BUNDLE with ONE gate**. What is lost: per-signal attribution up
front. How it is bought back: **ablation on a passing bundle** — if v4
gates PASS, each component is removed one at a time in the replay eval and
its marginal contribution measured on the same games. Ablation on a FAILED
bundle is also registered: it localizes the damage before any component is
re-registered alone. This paragraph exists so the record shows a choice,
not a lapse.

## The arm

**v4 = v3's venue clock + the following consumptions.** Per-row honesty as
always: a row is labelled `v4` only when at least one v4 input actually
priced it; per-component fallbacks degrade toward v3 behaviour with the
loud-fallback pattern (#59), never silently.

1. **Totals: pace/efficiency-decomposed projection.** The v1 surprise
   coefficient treated all excess scoring as one blob; v4 splits it because
   pace persists and shooting luck mean-reverts:

       poss_rate_obs = possessions_so_far / elapsed          (box counts,
                                                              sides averaged)
       ppp_obs       = total_so_far / (2 · possessions_so_far)
       pace_blend    = shrink(poss_rate_obs → poss_rate_exp, k_pace)
       ppp_blend     = shrink(ppp_obs → ppp_exp,            k_eff)
       projected_v4  = total_so_far
                       + remaining_minutes · 2 · pace_blend · ppp_blend

   `shrink(x → prior, k) = (elapsed·x + k·prior) / (elapsed + k)` with
   **k_pace = 10 game-minutes, k_eff = 30 game-minutes** — a priori
   PRIORS, not fits (pace is believed after a quarter; efficiency is
   distrusted for three), stated as such; the gate judges them. Priors:
   `poss_rate_exp` from the two teams' recent-form possessions
   (`team_form`, point-in-time, league fallback when stale);
   `ppp_exp = mu_v4_pregame / (2 · poss_rate_exp · 40)` so the pregame
   anchor is preserved exactly at tip-off. Shooting splits are consumed
   HERE: they are the observed-efficiency measurement. Totals sigma stays
   the fitted per-period table (v1's own) — variance modelling is not
   re-invented in this bundle.

2. **Winner/spread: uncertainty widening from availability flags.** Foul
   trouble (any starter with PF ≥ 4 before Q4, ≥ 5 in Q4), star-off (the
   team's top-minutes starter absent from the floor in Q4 per
   substitution/box state), and in-game ejection each widen the margin
   sigma: `sigma_v4 = sigma · 1.15` while any flag is active (a priori
   constant, one for all flags). **Direction is deliberately NOT modelled**:
   a mean shift per player requires a fitted player-value model that does
   not exist, and inventing one inside a bundle is how bundles die. Flags
   push FV toward the market (wider sigma → less certainty → fewer
   entries), which is the conservative consumption. This is also where the
   operator's in-game availability shock is carried: ejection/DNP-mid-game
   IS the flag; B's oracle verdict on PREGAME injuries is untouched.

3. **Scoring runs: annotation only, never an FV input.** The fade family
   is CLOSED by registered FAILs; a run-based pricing term is a fade claim
   in disguise. Runs are computed (windowed score deltas over plays) and
   surfaced for strategy DESIGN — the operator's stated purpose — via the
   signal functions and engine logs. Any run-based entry rule requires its
   own hypothesis registration.

Inventory honesty: after v4, consumed = clock, box possession counts,
shooting splits, player fouls/minutes/on-off, ejections. Still recorded and
unconsumed = ESPN's win probability (benchmark only, permanently), pregame
injuries (B's verdict), scoring runs (annotation only).

## Floors, criterion, and the incumbent

* **Incumbent: v3** (the live regime). The bundle must beat what runs, not
  what ran in July.
* **Floors: ≥ 10 signal-covered games first recorded after 2026-08-24
  16:20Z AND ≥ 3,000 paired calibration points.** Below either: NO DATA,
  counts only.
* **PASS**: paired Brier diff (v3 − v4) game-clustered 95% CI excludes zero
  in v4's favour at floor, AND v4's money-at-price not measurably worse
  than v3's (paired trading diff CI not entirely below zero) — the v3a
  criterion family, both clauses, implemented from day one this time.
* **Ablation (registered now, run after the gate resolves either way)**:
  remove {pace/eff decomposition}, {availability widening} one at a time;
  report each paired marginal on the same games. No ablation result gates
  anything by itself; re-registration of a single component uses fresh
  games.

## v3d releases from hold, and the composition

* **v3d** (docs/math/pulse-v3d-entry-discipline.md) builds now as
  registered — unchanged, its own gate, its own floors.
* **The composition "v4d" — registered here**: v4's beliefs + v3d's entry
  discipline (entries only in the mutual-coverage region). They compose
  cleanly by construction: v4 changes WHAT the model believes, v3d changes
  WHERE it may enter, and the mechanisms are disjoint (estimates vs entry
  eligibility). v4d is reported as a third arm in every eval run; it may
  go live only if BOTH parents pass their own gates, and its own paired
  read (v4d − v3, both clauses) must not be worse than v4's. No separate
  floors: it reads on the same games as its parents.

## Deployment discipline

Live v4 (`MERIDIAN_PULSE_ESTIMATES=v4`) deploys only after this
registration merges, off-slate, with the artifact-level verification the
2026-08-23 skew taught (import the symbol in the running container; the
flag is never the thing to verify). Until the gate resolves, v4 live means
v4-labelled SHADOW rows — the gate is offline replay, as ever; nothing
about deployment is a verdict.

---

*Registered 2026-08-24 ~16:20Z, before the build. Results append below
this line, never above it.*

## 2026-08-27 — pre-gate note: the Brier sign reverses across the boundary

**Named in advance, before the v4 gate cohort reaches floor.** Day-one read:

```
backtest (15 pre-registration games)   paired diff (v3−v4)  +0.00578 [-0.00208, +0.01364]   favours v4
gate      (7 post-registration games)  paired diff (v3−v4)  −0.00578 [-0.01862, +0.00705]   favours v3
```

**Both CIs comfortably include zero; neither is evidence; the mirrored
magnitudes are coincidence until shown otherwise.** What is worth naming now is
that the two cohorts disagree in *direction*, and only one of them can ever
gate.

**Three readings are consistent with today's numbers. None is privileged.**

- **(a) Noise.** ±0.006 point estimates flipping sign across two small disjoint
  cohorts is what noise does. *A gate that recovers toward the backtest at floor
  supports this.*
- **(b) Cohort composition.** The post-registration week was blowout-heavy (see
  [bookless-endgames.md](bookless-endgames.md)); if the bundle's inputs earn
  their keep in competitive games, a decided-heavy week reads against them. The
  per-game flag-widened and pace-fallback diagnostics are the check — and they
  are **diagnostics, never gates**.
- **(c) Development-data optimism — #16's family.** The bundle was designed while
  the pre-boundary games accrued and their diagnostics were visible.
  Seen-data-good, unseen-data-flat is the classic in-sample signature. *A gate
  that stays at or below zero at floor while the backtest stays positive
  supports this*, and the response is the **already-registered ablation** —
  which input carries the regression — **never a retune of the bundle against
  gate data.**

**The registration boundary exists precisely so (c) is distinguishable from
(a).** This note exists so that no reading can be adopted retroactively as "what
we always expected."
