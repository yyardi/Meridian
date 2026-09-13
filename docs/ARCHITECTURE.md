# Meridian codebase map — 2026-09-13

96,159 lines of Python: `core/` 43,770 · `tests/` 23,659 · `analysis/` 17,985 (14,525 already in `analysis/archive/`) · `cfb/` 5,484 · `scripts/` 3,269 · `strategies/` 1,901. Eight compose files define 24 services plus a one-off trainer. The two existing overviews are stale: `docs/infra/what-runs.md` says "Three containers", `docs/infra/architecture.md`'s repo tree omits `pulse/ quote/ feeds/ kalshi/ backtest/ audit/`. Every claim below carries a path or a grep.

## 1. What runs on prod

Roles: **REC** recorder (irreplaceable tape — never touch casually) · **ENG** engine (shadow loop, places nothing) · **UI** api/dashboard · **JOBS** scheduled batch · **AN** analysis runner. Table = what the closure writes (`__tablename__` grep over each entrypoint's import closure; `core.storage.models` reads excluded).

| container | compose | runs | role | writes | why (one line) |
|---|---|---|---|---|---|
| postgres | base | postgres:16 | DB | everything | the only database since the 08-17 Supabase exit (`docker-compose.yml:39`) |
| recorder | base | `python -m core` → `core.recorder` | REC | market_snapshots, book_levels, service_heartbeats[`pregame_recorder`] | WNBA pregame board, 15–60 min |
| nfl-recorder / cfb-recorder / mlb-recorder | nfl, mlb | same, `MERIDIAN_LEAGUE` | REC | same tables, heartbeat `pregame_recorder_<league>` (`core/recorder.py:77`) | pregame boards per league |
| live-recorder | base | `core.live_recorder --interval 0.2` | REC | market_snapshots, book_levels, market_trade_stats, hb `live_recorder` | 200 ms in-game tape |
| nfl-live-recorder / cfb-live-recorder | nfl | same, 0.5 s / 1.0 s | REC | hb `live_recorder_<league>` (`core/live_recorder.py:756`) | football in-game tape |
| live-odds-recorder / nfl-odds-recorder / cfb-odds-recorder | base | `core.feeds.live_odds_recorder` 15 s / 300 s | REC | sportsbook_odds, hb `live_odds_recorder` — **all three share one key** (`core/feeds/live_odds_recorder.py:191`, no league suffix) | ESPN sportsbook lines |
| kalshi-recorder | base | `python -m core.kalshi` → `core.kalshi.recorder` | REC | kalshi_games, kalshi_contracts, kalshi_snapshots, hb `kalshi_recorder` | second venue, pregame only |
| espn-live-recorder | espn-live | `core.feeds.espn_live_recorder` | REC | espn_live_{box_snapshots,plays,player_snapshots,win_probability,injury_observations}, team_game_logs, hb `espn_live_recorder` | signal side, basketball |
| cfb-espn-recorder / nfl-espn-recorder | cfb-live | `core.feeds.espn_cfb_recorder [--league nfl]` | REC | espn_cfb_game_state, espn_cfb_live_plays, espn_cfb_win_probability — **no heartbeat** (`grep -c 'Heartbeat(' core/feeds/espn_cfb_recorder.py` = 0) | signal side, football |
| wnba-stats-sweeper / nfl-stats-sweeper | quote, nfl | `core.feeds.stats_sweeper --interval 3600` | REC | market_trade_stats (bulk insert, `stats_sweeper.py:91`) — **no heartbeat** | volume trajectory of a board |
| scheduler | base | `core.scheduler --interval-hours 6` | JOBS | team_game_logs, player_game_logs, sportsbook_odds, injury_polls, injury_reports, predictions, resolved_outcomes, shadow_orders, account_balances, hb `scheduler` | pregame loop: stats → odds → predictions → resolution → shadow orders (`core/scheduler.py:54-118`) |
| pulse-engine | pulse | `core.pulse.live` | ENG | pulse_decisions, pulse_abstentions, pulse_reprice_exits, hb `pulse_engine` | in-game directional shadow loop, 1 s |
| quote-engine / gridiron-engine / gridiron-cfb-engine | quote | `core.quote.engine_v2` (`MERIDIAN_LEAGUE`) | ENG | shadow_quote_fills, quote_v2_observations, hb `quote_engine[_nfl|_cfb]` (`core/quote/engine.py:102`) | at-touch shadow maker, 5 s; deployed via `scripts/deploy_engine.sh` |
| api | base | `uvicorn core.api:app` :8008 | UI | orders, pending_exits, account_balances (via `core.executor`), hb `fill_watcher` | 27 routes, 4 pages (`static/`); the only real-order path (`POST /api/orders`) |
| alerter | base | `core.alerter` | JOBS | hb `alerter`; ntfy pushes | `core/healthchecks.py` every 5 min |
| trainer | trainer | image with xgboost; `run --rm` only | AN | artifacts/ (host mount) | the cron read below runs inside it |

**Not containers, still prod:** `scripts/prod_weekend_read.sh` — crontab Sun 15:50 / Mon 10:20 UTC on the box (its header) — runs `cfb/run_making_touch.py`, `run_overshoot.py`, `run_ladder_rv.py`, `run_ladder_calibration.py`, `analysis/pregame_softness/*.py` in the trainer image and pushes one ntfy line. `scripts/build_cfb_game_map.py` writes `cfb_game_map` by hand (`docs/infra/saturday-runbook.md:18`); the cron read joins on it. `python -m core.analytics` is a host job that writes `reports/analytics.json` for `/api/analytics` (`docker-compose.yml:243-257`). `core.retention` runs by hand (`docs/infra/retention.md:126`). The pre-commit hook `exec`s `scripts/check_staged_secrets.py`.

**Coupling that makes "engine" unreadable:** `core/live_fv.py:283` and `core/live_totals_fv.py:284` do `from core.api import _human_market`, so both engines' import closures contain the FastAPI app (39 and 34 core modules vs 10 for a recorder). `core/quote/engine_v2.py:192` imports `analysis.congestion_detector` and `core/pulse/live.py` imports `analysis.guards`, which is why the Dockerfile `COPY analysis` (its own comment: "third occurrence of this exact omission"). `scripts/health.py` names 20 containers; missing: mlb-recorder, cfb-espn-recorder, nfl-espn-recorder, cfb-odds-recorder, nfl-odds-recorder. `docker-compose.trainer.yml:4` documents `python3 -m cfb.train`; no `cfb/train.py` exists — every `cfb/*.py` runs as a file with `sys.path.insert(0, "/app/cfb")`.

## 2. What is research

Classes: **LIVE** run by cron/container/hook/runbook · **REFERENCE** reproduces a documented result · **OPS** operator tool · **DEAD** superseded or uncited and unimported. "cited" = `grep -rl <basename> docs/ README.md */README.md`; "last" = `git log -1 --format=%cs`. Sibling imports in `cfb/` were checked by stem (`grep -rn cfb_data .` etc.).

### cfb/ (28 files, 5,484 lines)

| file | question | cited / imported by | last | class |
|---|---|---|---|---|
| cfb_live_fv.py, cfb_train.py | football GameState → features; two-head XGB fit | run_making_touch (cron), 10 siblings | 09-05 | LIVE |
| cfb_ingest.py | CFBD plays → GameState | run_full_fit, run_cover_fit, run_total_fit | 09-05 | LIVE |
| run_full_fit.py | the CFB WP fit; **writes `artifacts/cfb_wp_regulation.json`** (`:132`) | loaded by run_making_touch `:119` (cron) | 09-05 | LIVE |
| run_nfl_wp_fit.py | E8 NFL WP head; writes `nfl_wp_regulation.json` | e8-nfl-wp-head.md; loaded by cron | 09-07 | LIVE |
| run_making_touch.py | E1/H1c making joined to the touch — **the gate** | cron; 4 docs | 09-11 | LIVE |
| run_overshoot.py, run_ladder_rv.py, run_ladder_calibration.py | H1 overshoot; E5 ladder RV; ladder rung softness | cron; 1–3 docs each | 09-11 | LIVE |
| run_audit_losers.py | E2: what separates the games we lose to ESPN | RESEARCH_UPDATE_2026-09-07 row E2 | 09-06 | REFERENCE |
| run_vs_espn.py | our WP vs ESPN's on the same plays (E2's baseline loop, `run_audit_losers.py:117`) | run_audit_losers | 09-06 | REFERENCE |
| run_cover_fit.py, run_total_fit.py | E3 cover model; E4 total model | e3-cover-model.md, e4-total-model.md | 09-07 | REFERENCE |
| run_drift.py, run_slowside.py | between-play drift; H1b slow side | between-play-drift.md, e8-nfl-preregistration.md | 09-07 | REFERENCE |
| run_kalshi_early_vs_close.py | Kalshi early week vs close | kalshi-early-week.md | 09-11 | REFERENCE |
| run_trigger_replay.py | reconcile `core/quote/move_trigger.py` vs harness | adverse-selection-by-stratum.md | 09-10 | REFERENCE |
| run_longshot_shadow.py | longshot-NO shadow lister (HEAD commit) | longshot-no-candidate.md | 09-13 | REFERENCE |
| run_making.py | making centred on model FV | superseded — `run_making_touch.py:3` | 09-07 | DEAD → archived |
| run_edge.py | taking: cross the spread on model disagreement | superseded — `run_making.py:3` | 09-06 | DEAD → archived |
| edge.py, cfb_validate.py | "primary"/"secondary" validation of the fit | nothing imports either; 0 docs | 09-05 | DEAD → archived |
| cfb_data.py, cfb_names.py | prod row loader; CFBD↔ESPN name bridge | nothing imports either; 0 docs | 09-05 | DEAD → archived |
| run_monotone_probe.py, run_spread_probe.py, run_step3.py | why is `spread_time` 0.04%; is the timeout feature worth it | 0 docs (e8-nfl-wp-head.md reports 24.3% for NFL, not these) | 09-05 | DEAD → archived |
| backfill_cfb.py | one-off backfill of game state before the venue froze | 0 docs, 0 imports | 09-06 | DEAD → archived |

### analysis/ (9 top-level .py + 3 subdirs; archive/ holds 34 more)

| file | question | cited / imported by | last | class |
|---|---|---|---|---|
| congestion_detector.py | congestion-window detector pin | `core/quote/engine_v2.py:192`; 2 docs | 09-02 | LIVE |
| guards.py | WAVE_STANDARD rules as code | `core/pulse/live.py`, `core/pulse/storage.py` | 09-03 | LIVE |
| pregame_softness/{pregame_softness_polymarket,pregame_softness_kalshi,score_softness}.py | H4 pregame softness snapshots + scoring | cron; e8-nfl-preregistration.md | 09-11 | LIVE |
| quote_v2_markout.py | QUOTE v2 markout, toll map | d1-preread-pin.md | 09-02 | REFERENCE |
| a1_oscillation_descriptive.py | oscillation harvest | loaded **by file path** from `quote_v2_markout.py:299` | 09-02 | REFERENCE (path-coupled; moves with markout) |
| pulse_branch_scoring.py | one scoring function for both `pulse_decisions` branches | analysis/PULSE_LIVE_BRANCH_SCORING.md:4 | 09-06 | REFERENCE |
| kalshi_settled/kalshi_settled_backtest.py, kalshi_preseason/kalshi_preseason_backtest.py | pre-registered settled-market tests | their READMEs | 09-07 | REFERENCE |
| kalshi_settled/longshot_side.py | underdog side + two-market vig | uncited; sits with its JSON inputs, longshot line is active | 09-07 | REFERENCE |
| pulse_live_model_first_scoring.py, pulse_vs_market_brier.py | live model scored; PULSE vs market Brier | superseded: PULSE_LIVE_BRANCH_SCORING.md scores both with pulse_branch_scoring "rather than two implementations" | 09-06 | DEAD → archived |
| pulse_sigma_build.py | per-observation σ for PULSE | its successor's docstring: "the sigma build is unnecessary"; 0 docs | 09-06 | DEAD → archived |
| power_loop_and_geff_48.py | power loop on 48 games, G_eff | 0 docs, 0 imports | 09-05 | DEAD → archived |
| archive/ (34 .py) | one-offs archived 09-05 | its README names 3 "live" scripts that are not in the directory (`capture_is_not_a_proxy.py` …) | 09-01/02 | ARCHIVE (stale README) |

### scripts/, sandbox/, strategies/

| file | question / purpose | cited / imported by | last | class |
|---|---|---|---|---|
| health.py | is everything working right now | api healthcheck, alerter, `deploy/aws/health.sh`, 12 docs | 09-03 | LIVE |
| prod_weekend_read.sh | the weekend read (cron) | — it is the cron | 09-11 | LIVE |
| build_cfb_game_map.py | ESPN↔venue game map → `cfb_game_map` | saturday-runbook.md; `core/storage/models_cfb_map.py` | 09-09 | LIVE |
| check_staged_secrets.py | secret guard | `.git/hooks/pre-commit` | 09-05 | LIVE |
| deploy_engine.sh | engine deploy with commit stamp | docker-compose.quote.yml | 09-02 | LIVE |
| export_wnba_trades.py, pin_venue_export.py | operator fills → sheet; pin an export | pyproject `dev`, findings.md, 2 tests | 08-25 | REFERENCE |
| guard_coverage.py, probe_authed_read.py | enforced vs written rules; authed read latency | 2 docs; write-latency.md | 09-03 / 08-05 | REFERENCE |
| sandbox.py | run a strategy on recorded tape → one number (2 strategies) | sandbox/README.md:54 | 09-04 | REFERENCE — the proto strategies interface |
| sandbox/strategy.py | the trading decision, 145 lines | sandbox/README.md | 09-05 | REFERENCE |
| allow_my_ip.sh, pin_tick_export.sh, stop.sh, watch.py, league_listing_watch.py | SSH allow; tick export; laptop stop/tail; listing alert | README.md / pre-slate-checklist.md / uncited | 08-04..09-05 | OPS |
| import_supabase_export.py | one-time Supabase import | supabase-exit.md, aws-history-merge.md (historical) | 08-17 | DEAD — not moved: infra record, not research |
| model_trade_sheet.py | model side of the annotation workbook | 0 docs, 0 imports | 08-25 | DEAD → archived |
| strategies/wnba_totals/ (5 files) | pregame WNBA totals model | `core.predictions` (scheduler), `core.pulse.live`, `core.kelly_sizing`, 8 tests | 07-31..08-02 | LIVE |

## 3. What is dead in core/ (listed, not moved)

Import graph: `ast` over every `.py` in core/ cfb/ scripts/ tests/ strategies/ analysis/ sandbox/ alembic/, roots = the 13 compose entrypoints + `scripts.health` + `alembic.env`. 32 of 107 `core` modules are unreachable from any prod root.

| module | last | importers outside tests | tests | docs | verdict |
|---|---|---|---|---|---|
| crossmarket.py, performance.py | 07-31, 08-05 | none | n | 0 | DEAD |
| backtest/exp_availability.py, exp_margin_shrinkage.py | 08-01/02 | none | n | 0 | DEAD |
| storage/sync_local.py | 08-07 | none | n | 7, all Supabase-era | DEAD — its source left 08-17 |
| backtest/{__main__,report}.py | 08-07 | each other | n | RUNBOOK `python -m core.backtest` | DORMANT CLI |
| backtest/{margin,moneyline,exp_devigged_clv,ingame_replay}.py | 08-02..24 | intra-package | Y | 0–1 | RESEARCH-IN-CORE (tests are the only caller) |
| pulse/{replay,replay_eval,first_score,overreaction,tail_volatility,tight_game_reversion}.py | 08-02..27 | intra-package | Y | each marked FAILED in docs/README.md | RESEARCH-IN-CORE |
| quote/depth_signal.py, window_detector.py | 08-02 | none | Y | FAILED / news-windows.md | RESEARCH-IN-CORE |
| survey.py, scorecard.py, backfill.py, audit/{hand_trades,wnba_trade_sheet}.py | 07-31..08-25 | scripts/export_wnba_trades (audit only) | Y | 1–3 | DORMANT CLI |
| pulse/diagnostics.py | 08-22 | none | n | pulse-diagnostics.md | DORMANT CLI |
| quote/probe.py | 09-06 | none | n | fill-rule-bias.md | DORMANT by design ("inert until armed") |
| quote/move_trigger.py | 09-10 | cfb/run_trigger_replay.py | n | 2 | **strategy candidate** (H1c trigger) — belongs in strategies/ |
| storage/models_cfb_map.py | 09-05 | scripts/build_cfb_game_map.py | n | 0 | LIVE via runbook script; not dead |
| analytics.py, retention.py | 08-18/21 | host jobs only | Y | yes | DORMANT host jobs (see §1) |

## 4. Target layout

```
infra/       recorders (core/recorder, live_recorder, kalshi/, feeds/), storage/ + alembic/, heartbeat, healthchecks, alerter, retention, paths, config, ratelimit, polymarket/, ops/ (health.py, deploy/, deploy_engine.sh); compose files stay at root
engine/      ONE loop: board → strategy.select → paper book (quote/wallet, quote/storage, pulse/storage) + shadow listers (run_longshot_shadow's live half) → tables; plus jobs.py (today's scheduler chain) and executor/fill_watcher (the only real-order path)
strategies/  one file per family, same interface: quote.py (at-touch, guarded), pulse.py, quote_move.py (move_trigger), longshot_no.py, ladder.py, wnba_totals.py; _stats.py = clustered_mean
ui/          api.py + static/ (index, quote, wallet, analytics)
research/    cfb/, analysis/, sandbox/, archive/, core/backtest/, the RESEARCH-IN-CORE rows of §3, core/kalshi/analysis.py
```

Interface (the paper book is the first client; `scripts/sandbox.py` already dispatches on a strategy name):
`select(rows: list[BoardRow]) -> list[Bet]` pure, no I/O, `BoardRow` = what `core/board.py` returns · `score(bets, settlements) -> PnL` money at price, games not rows (`core/quote/adverse_selection.clustered_mean`, imported by 9 prod roots and 6 analysis scripts today).

| today | target |
|---|---|
| core/{recorder,live_recorder,__main__}.py; core/feeds/*; core/kalshi/{client,recorder,mapping,__main__}.py; core/polymarket/; core/storage/; core/{heartbeat,healthchecks,alerter,retention,paths,config,ratelimit}.py; scripts/health.py; deploy/ | infra/ |
| core/scheduler.py + core/{predictions,resolution,bankroll,shadow_run,calibration}.py | engine/jobs.py |
| core/quote/{engine,engine_v2,storage,wallet,report}.py; core/pulse/{live,storage,reprice,live_report}.py; core/{executor,fill_watcher,board,ev_guard,kelly_sizing,era,leagues,team_mapping,game_detail}.py; analysis/{guards,congestion_detector}.py | engine/ |
| sandbox/strategy.py + scripts/sandbox.py STRATEGIES; core/pulse/{signals,team_form,win_curve,guards}.py + core/{live_fv,live_totals_fv}.py; core/quote/move_trigger.py; cfb/run_longshot_shadow.py (select half); cfb/run_ladder_calibration.py (select half); strategies/wnba_totals/ | strategies/{quote,pulse,quote_move,longshot_no,ladder,wnba_totals}.py |
| core/api.py; static/ | ui/ |
| everything in §2 not LIVE, plus §3 RESEARCH-IN-CORE and DEAD rows | research/ |

### Migration order (no step restarts a recorder; each has a check that can fail)

0. **Baseline** (before every step): `docker compose ps` names; `SELECT service, beat_at, rows_written FROM service_heartbeats`; `curl :8008/api/status`; `pytest` count (`deploy/aws/run_suite.sh`). For the four heartbeat-less containers use `max(captured_at)` on their tables.
1. **Pure moves of DEAD research → `archive/<original path>`** (this branch). Check: `grep -rn <basename>` over the tree returns no importer; `pytest --noconftest tests/test_live_odds_days_ahead.py`; no compose/Dockerfile/cron line names a moved path. Nothing rebuilt.
2. **strategies/ interface, paper book first.** Add `strategies/base.py` and port the two `scripts/sandbox.py` strategies into `strategies/quote.py`. Check: run `scripts/sandbox.py --sport cfb --strategy quote` on a pinned export before and after — the printed number must be identical. No container touched.
3. **engine/.** Move `core/quote/engine_v2.py`, `engine.py`, `core/pulse/live.py` and their storage behind `engine/`, leave `core/quote/engine_v2.py` as `from engine.quote import *` so every `command:` line still resolves; move `analysis/guards.py` and `congestion_detector.py` into `engine/` and drop `COPY analysis` from the Dockerfile. Rebuild ONE engine first (`gridiron-cfb-engine`, via `scripts/deploy_engine.sh`). Check: `quote_engine_cfb` `beat_at` advances and `count(*) FROM quote_v2_observations` grows over one cycle; then the other engines.
4. **ui/.** Move `_human_market` out of `core/api.py` into `core/leagues.py` (2 call sites, §1) — this alone cuts the engine closures by ~20 modules; then move api + static to `ui/` with a `core/api.py` shim. Check: every route in `core/api.py` (27 `@app.get/post`) returns 200 on a GET; `tests/test_api_*.py`, `test_landing_page.py`, `test_quote_page.py`.
5. **infra/.** Move recorders/feeds/storage with shims; update `command:` lines one container at a time, **recorders last and one per slate gap**. Check per container: its heartbeat row advances and its table's `max(captured_at)` moves within one interval; `scripts/health.py` (first add the 5 missing containers) all-OK. Give the 3 odds recorders league-suffixed keys and the sweepers/ESPN-football recorders a heartbeat in the same change, or the check cannot fail.
6. **research/.** Fold `cfb/ analysis/ sandbox/ archive/` and §3's RESEARCH-IN-CORE rows under `research/`; update the three mount lines in `scripts/prod_weekend_read.sh` and the `./cfb` mount in `docker-compose.trainer.yml`. Check: run the cron script in `h4` mode by hand; the artifact file is written and the gate line prints.
7. **Delete shims** after one full slate with every heartbeat green and the test count unchanged.
