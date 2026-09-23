# WNBA player-based winner model — pre-registration, written before any price is compared

2026-09-22, WNBA playoffs on. Registered **before** `cfb/run_wnba_player_model.py`
has been run against a single venue price. Operator's ask, verbatim: "build a Monte
Carlo model on just the winning team based on the players". House rule: register
and measure, never shoot down — and never claim an edge the estimator cannot support.

Everything below is fixed now. Nothing in it is fitted to the evaluation games
except one walk-forward scale (σ), and the constants are named so a later change
is a new registration, not a tune.

## The model — one, not a menu

For a game between teams A and B, predicted at **T−1h** before the venue's
`game_start_time`, from player logs that are *visible* at that instant:

1. **Player rating** `r_i` = on-court margin per minute, shrunk to zero:

       r_i = Σ_g plus_minus_ig / (Σ_g minutes_ig + RATING_SHRINK_MINUTES)

   over every `player_game_logs` row of player *i* that is visible (below) and whose
   `season` is the game's season or the one before. `RATING_SHRINK_MINUTES = 400`:
   a player with 400 minutes on file is shrunk halfway to zero; a player with none is
   exactly zero (league average by construction). DNP rows carry NULL and are skipped.

2. **Expected minutes** `m_i` = the player's mean minutes over her team's last
   `RECENT_TEAM_GAMES = 10` visible games, **zero-filled** — a game the team played
   without her counts as 0 minutes for her. This is the rule from
   docs/math/availability.md and the single most important line in the model: a
   player who has been out for weeks decays toward zero on her own, so the injury
   step below does not deduct her twice.

3. **Injury status**: if the latest `injury_reports` row for player *i* with
   `captured_at <= T−1h` has `status = 'Out'`, `m_i := 0`. `Day-To-Day` is
   unchanged. The injury log exists only from 2026-08-01 (point-in-time, forward
   only); before that this step is a no-op and the report says how many games it
   touched.

4. **Team strength** `S_A = (1/5) · Σ_i m̃_i · r_i` where `m̃_i` are the expected
   minutes rescaled so they sum to `TEAM_MINUTES = 200` (5 slots × 40). The 1/5 is
   not a tuning constant: five players share every minute, so an unshrunk
   minutes-weighted sum of plus-minus per minute over a team's own past games is
   exactly five times its point differential.

5. **Expected margin** `μ = S_A − S_B + HOME_EDGE_POINTS · (+1 if A is home, −1 if
   B is home)`. `HOME_EDGE_POINTS = 3.0`, fixed from the literature, not fitted; the
   runner prints the realised mean home margin of the sample beside it as a
   diagnostic, never as a refit.

6. **Margin scale** `σ`, walk-forward: before game *k* in date order,

       σ_k² = (SIGMA_PRIOR_POINTS² · SIGMA_PRIOR_GAMES + Σ_{j<k} e_j²) / (SIGMA_PRIOR_GAMES + (k−1))

   with `e_j` the residual (actual margin − μ_j) of every *earlier* evaluated game
   and `SIGMA_PRIOR_POINTS = 12`, `SIGMA_PRIOR_GAMES = 20`. The first game uses the
   prior alone. σ is the only quantity the evaluation games touch, and each game
   only ever sees the ones before it.

7. **Monte Carlo**: `MC_DRAWS = 20,000` margins `~ N(μ, σ_k)` with seed
   `MC_SEED = 20260922`; `P(A wins) = fraction of draws > 0`. Basketball has no
   ties. The closed form Φ(μ/σ) is printed beside it as a check, and the test pins
   the two within 1 pp.

**Why this one, in three sentences.** Plus-minus per minute is the only statistic
in `player_game_logs` that is already a margin, so a minutes-weighted sum of it is
on the points scale with no calibration step and no invented replacement level. A
40-minute game is ~80 possessions of small, nearly independent increments, so the
margin is normal to the accuracy this sample can resolve, and P(win) then needs
exactly one fitted number, σ, kept walk-forward. A possession-level draw would need
pace, efficiency and lineup-interaction terms that `player_game_logs` does not carry
(it has minutes, points and plus-minus and nothing else), so every one of them would
be assumed rather than measured.

**What this model actually is, said plainly.** With a stable rotation the
minutes-weighted sum collapses to the team's recent point differential. The only
information here that a team-margin model lacks is *who plays tonight* — minutes
drift, and an `Out` designation. docs/math/availability.md already measured that
lineups are priced into the close on this venue (oracle CLV +0.03 [−0.06, +0.12]).
**The registered expectation is therefore that the gate below fails.** It is run
because the operator asked, because it costs one runner, and because the playoff
row is the one place a lineup-aware model could differ (rotations tighten to seven
players). If any row passes, it is that one, and it is registered now as a
hypothesis for the 2027 season — not as a 2026 result.

## Point-in-time, stated as the runner enforces it

A `player_game_logs` row with `game_date = t_log` is **visible** for a game predicted
at `T_pred = game_start_time − PREDICTION_OFFSET_SECONDS (3600)` iff

    t_log + LOG_LAG_SECONDS (3·3600) <= T_pred

i.e. a box score exists three hours after its own tip. A same-night earlier game is
visible if it tipped ≥ 4h before this one; the game being predicted is never
visible to itself; nothing dated later is visible. `injury_reports` filter on
`captured_at <= T_pred` (the recorder's own clock, never ESPN's `reported_at`).
`tests/test_wnba_player_model.py::test_a_log_dated_after_the_game_changes_nothing`
inserts a log after the game and one inside the 4h blind window and asserts the
prediction is bit-identical.

## Orientation

The venue's winner slug is `aec-wnba-<first>-<second>-<date>` and **YES = the
first team**. On US team sports the first team is the away team (memory: *YES is
always the away team*) — but core/team_mapping.py measured 18 of 285 early-May 2026
markets with the first team at home, so the runner never trusts the slug for
home/away. It resolves the ESPN game from the unordered team pair and a 30h UTC
window (`resolve_orientation` semantics), takes `is_home` from `team_game_logs`,
applies the home edge to whichever side ESPN says is home, and prints
`n_first_is_away` and `n_first_is_home`. The model's probability is always
`P(first team wins)`, in the venue's YES frame, and the test asserts that the home
edge lands on the YES side exactly when ESPN says the first team is home.

## Population and sample — printed before any result

One row per ESPN game. A game is in the sample iff:

* a `basketball_team_full_game_winner` market with slug `aec-wnba-…` exists whose
  team pair and date resolve to exactly one ESPN game (ambiguous → excluded, counted);
* the market has a quote with `best_bid`, `best_ask` and `fee_coefficient` all
  non-NULL, `captured_at` in `[tip − QUOTE_WINDOW_SECONDS (6h), tip − 1h]` and
  `captured_at <= now()` (the local mirror carries rows stamped 2099; they are
  excluded and counted); the **last** such quote is the venue's price;
* both teams have ≥ `MIN_PRIOR_TEAM_GAMES = 5` visible games with player rows;
* the venue has settled the market (paper-book route: `core.settlements` over the
  venue's own settlement endpoint). ESPN's final is read beside it as a cross-check;
  disagreements are printed. `--settlement espn` runs the whole read on ESPN finals
  and labels every line `espn-settled`.

The runner prints, before any Brier: markets on tape, unresolvable slugs, ambiguous
matches, no-quote-in-window, future-stamped rows excluded, cold teams excluded,
unsettled, and the final `n_games` per row (all / regular / playoffs / first-is-away
/ first-is-home). No number below is read without its `n_games`.

**Coverage count for the manager to run on prod** (one line; an upper bound, since
the slug→ESPN join is done in Python — the runner prints the exact matched count):

    WITH g AS (SELECT market_slug, min(game_start_time) ko FROM market_snapshots WHERE market_slug LIKE 'aec-wnba-%' AND sports_market_type = 'basketball_team_full_game_winner' AND game_start_time IS NOT NULL GROUP BY 1), q AS (SELECT g.market_slug, g.ko FROM g WHERE g.ko < now() - interval '4 hours' AND EXISTS (SELECT 1 FROM market_snapshots s WHERE s.market_slug = g.market_slug AND s.captured_at BETWEEN g.ko - interval '6 hours' AND g.ko - interval '1 hour' AND s.captured_at <= now() AND s.best_bid IS NOT NULL AND s.best_ask IS NOT NULL AND s.fee_coefficient IS NOT NULL)) SELECT count(*) AS winner_markets_with_t1h_quote, count(*) FILTER (WHERE EXISTS (SELECT 1 FROM player_game_logs p WHERE p.game_date BETWEEN q.ko - interval '2 hours' AND q.ko + interval '2 hours')) AS with_player_logs_at_that_tip FROM q;

## Evaluation — walk-forward, scored against the venue and against a coin

Per game, with `y = 1` if the first team won, `p` the model, `v` the venue mid
`(bid+ask)/2` at the T−1h quote, `c = 0.5`:

* Brier: `(p−y)²`, `(v−y)²`, `(c−y)² = 0.25`.
* Log loss: `−[y ln p + (1−y) ln(1−p)]` with `p` clipped to `[LOGLOSS_CLIP, 1−LOGLOSS_CLIP]`, `LOGLOSS_CLIP = 1e−6`; same for `v` and `c`.

**Estimator, named.** Every mean is over games (one row per game, so games are the
clusters; the runner still clusters by `espn_game_id` so a duplicate slug cannot
double-count). Intervals are the cluster-robust sandwich with the `G/(G−1)`
correction and a 1.96 critical value, as `cfb/run_paper_book.py::clustered`; the
runner prints the row-level interval beside it labelled `(WRONG)` so the ratio is
visible. The paired difference `Δ = Brier_model − Brier_venue` is the registered
statistic; its interval is on the *paired* per-game differences.

**Rows, exactly these:** all games; regular season (`season_type = 2`); playoffs
(`season_type = 3`); first-is-away; first-is-home. The last two are a twin
diagnostic, printed beside, never gated on (audit 2026-09-13).

**Power floor:** `POWER_FLOOR_GAMES = 50` venue-settled games on the *all* row
before any verdict word is printed. Below it the runner prints counts and the
word `UNDERPOWERED`, and nothing else is quotable.

**Gate (primary, the only one):** on ≥ 50 games, `mean Δ < 0` **and** its
game-clustered 95% interval excludes zero. Log loss is printed as a secondary and
must point the same way to be mentioned; it gates nothing.

## Decision rule — scored only if the gate passes

Registered now, threshold named now, never searched:

* buy **YES at the ask** when `p − ask ≥ EDGE_THRESHOLD`;
* buy **NO at 1 − bid** when `bid − p ≥ EDGE_THRESHOLD`;
* `EDGE_THRESHOLD = 0.05`. Reason: at even prices the taker fee at today's
  coefficient is 1.7¢ and the WNBA winner half-spread on this tape is 1–2¢, so
  5¢ is roughly twice the round-trip cost of being wrong about the price.
* $1 contracts, P&L `y − ask − fee` (YES) or `(1−y) − (1−bid) − fee` (NO), with
  `fee = core.fees.recorded_fee(price, row.fee_coefficient)` — the coefficient the
  venue carried **on that row**. The venue raised it at 2026-09-17 04:07Z and this
  sample spans that instant; a row with no coefficient is refused, never charged
  at today's. The test charges a pre-change and a post-change row in one run and
  asserts each as an expression in its own coefficient.

If the gate fails, the runner prints the number of bets the rule *would* have
taken and the words `NOT SCORED: Brier gate failed`; no P&L is printed, so there
is nothing to quote.

## What would kill it — written before it can be excused

1. **The gate fails on ≥ 50 games.** Dead as a pregame line. No refit of K, N,
   home edge, σ prior or threshold; no added feature; no re-cut by row. A
   different model is a different registration.
2. **`mean Brier_model > 0.25`** — worse than a coin. Dead, whatever the venue row says.
3. **Fewer than 50 matched, settled games by the end of the 2026 playoffs.**
   Underpowered; the report says so and stops. Not a verdict either way.
4. **Any leakage or orientation test failing**, or the runner's
   `n_first_is_home` disagreeing with ESPN's `is_home` on any game. The read is
   void until fixed, and the fix is re-registered.
5. **Venue-unsettled fraction above 50 %.** Then the settlement route, not the
   model, is what was measured; the `espn-settled` row is reported as such and is
   not the primary.
6. **Playoffs row passes while the all row fails.** That is a hypothesis for 2027
   on a fresh tape, printed with its `n_games`, and nothing is placed on it.

## What is not on this list and will not be added after the tape

Any window, weight, decay, shrinkage, threshold, feature (points per minute,
starters, positions, rest days, pace) or estimator not named above. If something
interesting appears outside these rows, it is written down as a hypothesis for the
next season and not reported as a result of this read.

## Runner and tests

* `cfb/run_wnba_player_model.py` — read-only SQL over `DATABASE_URL`; prints every
  count above before any Brier; `--dry-run` runs the whole pipeline on the
  fixture dataset the tests use; `--settlement venue|espn`.
* `tests/test_wnba_player_model.py` — leakage (a later log and a blind-window log
  change nothing), orientation (home edge lands on YES iff the first team is home,
  and P(YES) < 0.5 for equal teams when the first team is away), fee (pre/post
  change rows in one run, each an expression in its own coefficient, NULL refused),
  estimator (duplicated rows widen the clustered interval and leave the naive one
  unchanged; the sandwich carries `G/(G−1)`), and MC-vs-Φ agreement.

---

## Addendum 2026-09-22 — first read, LOCAL MIRROR, ESPN-settled, not the primary

Run after the registration above was committed (e302786), against the analysis
mirror at `localhost:5433/meridian`, `--settlement espn`. **This is not the
registered primary**: the primary is venue-settled on prod, and the mirror's
`team_game_logs` end 2026-08-27 and `player_game_logs` end 2026-08-20, so the
sample is regular season only and stops before the playoffs. Printed here so the
prod read has a number to disagree with, not as a verdict.

Population: 89 WNBA winner markets on tape (last 90 days), 3 future-stamped rows
excluded, 76 with a quote in [tip−6h, tip−1h], 76 matched to exactly one ESPN game,
76 with an ESPN final. `n_first_is_away = 76, n_first_is_home = 0`. 63 of 76
games had an `Out` designation zero a rotation player. Realised mean home margin
+1.82 on 76 games (the fixed edge is 3.0).

| row | G | Brier model | Brier venue | Brier coin | Δ model − venue [95 % game-clustered] | LL model / venue / coin |
|---|---:|---:|---:|---:|---|---|
| all (= regular = first-is-away) | 76 | 0.1977 | 0.1839 | 0.2500 | +0.0139 [−0.0073, +0.0350] spans 0 | 0.5836 / 0.5485 / 0.6931 |
| playoffs | 0 | — | — | — | not a row | — |

On this slice the gate is **not passed**: Δ is positive (the venue is better) and
spans zero at G = 76 ≥ 50. Kill condition 2 does not fire (0.1977 < 0.25: the
model beats a coin, i.e. it knows *something* — the team's point differential).
The paper line would have taken 51 bets on 51 games (16 YES, 35 NO) and is
**NOT SCORED**. The prod run decides; if it adds the September regular season and
the playoffs and the all row still spans or favours the venue, condition 1 applies
and the model is dead as a pregame line.
