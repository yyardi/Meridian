# STATUS — Meridian / Gridiron (updated 2026-09-13 21:30Z)

One file. What runs, what it has earned on paper, what is being read next, what
you need to run, and who is building what. Full numbers: `docs/RESEARCH_REPORT_2026-09-13.md`.
Plan for the live candidate: `docs/math/longshot-no-candidate.md`.

## 1. Commands you need to run — ON THE BOX (paste from the laptop; the 20:00Z run built everything on the laptop instead)

```bash
# one paste from the laptop: builds MLB, api, both paper scalp engines, Kalshi, cricket + table-tennis recorders on the box, then lists them
ssh -i ~/.ssh/meridian-aws.pem ubuntu@$(cat ~/.meridian-server) 'cd /opt/meridian && sudo docker compose -f docker-compose.yml -f docker-compose.mlb.yml up -d --build mlb-recorder && sudo docker compose up -d --build api && sudo docker compose -f docker-compose.yml -f docker-compose.scalp.yml up -d --build scalp-nfl scalp-cfb && sudo docker compose up -d --build kalshi-recorder && sudo docker compose -f docker-compose.yml -f docker-compose.cricket.yml up -d --build cricket-recorder tt-recorder && sudo docker compose -f docker-compose.yml -f docker-compose.cricket-espn.yml up -d --build cricket-espn-recorder && sudo docker ps --format "{{.Names}} {{.Status}}" | grep -E "mlb|api|scalp|kalshi|cricket|tt-"'  # seven services
```
**Verified 19:26Z: the daily MLB read now runs end to end on the box** (`scripts/prod_weekend_read.sh mlb`, exit 0 both jobs, "NOTHING TO REPORT" until the recorder has tape — the honest empty output). The venue-client reads no longer `docker exec` into the api container: they run a one-off container off the api image with `/opt/meridian/core` and `/opt/meridian/strategies` mounted, so they track git, not the last rebuild. That was not cosmetic — `docker exec` died on `No module named 'strategies.ladder'`, so **Monday 10:20Z would have produced no paper book**; it is now safe with or without the rebuild. The rebuild still matters for the dashboard: /scoreboard and the honest PULSE page are in the image, not the mount.

Prod git is at origin/main (main-deploy); compose is classifier-blocked for the manager (an allow rule cannot match the `$(cat …)` prefix; an ssh alias `meridian-prod` would), so the paste is yours. **Hard dependency: Monday 10:20Z's paper book imports strategies/ladder.py and core/settlements.py, neither in the 09-05 api image — the api rebuild must happen before then or the read fails.**

Dashboard: `http://<address in ~/.meridian-server>:8008` — the address rotated on 09-06.

## 2. What is running (AWS, no laptop)

| container | records | league |
|---|---|---|
| cfb-espn-recorder / nfl-espn-recorder | plays, win prob, game state, live DK line | CFB, NFL |
| recorder / cfb-recorder / nfl-recorder | venue boards (every rung, every market) | WNBA, CFB, NFL |
| live-recorder / cfb-live-recorder / nfl-live-recorder | in-game book at 0.2–1s | WNBA, CFB, NFL |
| nfl-odds-recorder / cfb-odds-recorder | DraftKings pregame line path, 7 days ahead | NFL, CFB |
| kalshi-recorder | Kalshi boards, 72h pregame window | CFB, NFL (WNBA when listed) |
| mlb-recorder | venue boards | **MLB — waiting on the command above** |
| cron Sun 15:50Z / Mon 10:20Z | the pre-registered read, to /opt/meridian/artifacts/reads | — |

## 3. Strategies and paper P&L (nothing has ever been placed)

| strategy | status | paper result |
|---|---|---|
| QUOTE shadow maker (3 leagues) | measured negative with power | −2.2% ROI in-game [−3.8, −0.6], −4.1% pregame; 169k fills, 149 games |
| PULSE (WNBA in-game model loop) | paused for lack of games since 08-31; resumes on playoffs | 57 fills, below its 100-fill floor; round trips +8.5% in the unregistered view |
| CFB spread: buy NO on 20–30¢ rungs | paper line, read 09-19 | **+$15.73 on $220 staked**, 289 bets, 107 games: +5.44¢ per $1 [−1.46, +12.35], spans 0 |
| WNBA spread: buy favourites 80–100¢ | paper line, read on playoffs | +$5.84 on $93, 101 bets, 40 games: +5.78¢ [+2.96, +8.60] excludes 0 — BUT its home-side twin is −2.05¢ [−8.27, +4.16]: an away-listing artifact until the playoffs say otherwise |
| WNBA totals: buy UNDER every rung | paper line, read on playoffs | +$43.75 on $414, 792 bets, 88 games: +5.52¢ [−2.10, +13.15], spans 0; two of six weeks carried it |
| CFB: home side every rung ("home shift") | paper line, read 09-19 | +$47.44 on $1,571, 2,503 bets, 117 games: +1.90¢ [−3.83, +7.62], spans 0 |
| NFL: same two rules | paper line, 2 games | −$17.91, UNDERPOWERED |
| MLB: under/over, favourite/dog, 20–30¢ NO | **tape started 2026-09-13 20:22Z**: two manual sweeps, **834 snapshots across 53 games**, 0 errors (477 markets in 156s, then 357 in 116s as started games left the pregame board). Run BY HAND, one sweep per manager check-in, because the recorder container is not up and the classifier refused a cron for it — so the tape has ~hourly holes and stops entirely when this session ends. **The consuming join is verified**: `game_start_time` is populated on 834/834 rows (this is exactly what was NULL for Kalshi NFL and gave that league no data for a week), and the venue's five type strings all match the book's suffixes with no cross-contamination between full-game and first-five. The winner pair is **disjoint** (one winner market per game, max 1 distinct slug per game_id), and the YES frame is confirmed AT THE VENUE — `marketSides[0]` is `ordering=away, long=true` on every MLB market, so YES is the away side as the registry says. **But the two winner rules read only 21 of 49 markets: 28 (57%) match no rule, and the dog arm is n=4** — a fav-versus-dog difference is not quotable off this tape, and until tonight nothing printed the markets no strategy took | first calibration at 100 settled games |
| **In-game: buy the near-certain side at 90–99¢ and hold to settlement** (the fee collapses to 0.3% round trip there, and holding pays entry only) | **measured, and the idea fails for a reason opposite to the scalp's.** CFB, 59 games. Crossing + fee total only **0.45–2.26¢** across all eight cells against the scalp's 8–11¢, so the fee thesis is confirmed on the cost side — but calibration is then the whole term and runs **−18.19 to +2.21¢**. Not dead from cost; unmeasurable from outcome variance. Mid entry moves cells by 0.4–1.8¢, so a resting maker entry cannot rescue any of them. No cell's win rate beats its break-even by more than 1.7pp | the one cell excluding zero, +1.68¢ [+1.41, +1.96], is **degenerate — 7 of 7 games won, so the interval measures the band's price width, not outcome risk. On the binomial it is 7/7 with a 95% lower bound of 65.2% against a 98.3% break-even.** Do not quote it |
| **CFB / NFL spreads: buy NO (home) on rungs whose YES mid is 50–60¢**, twin = buy YES (away) at 40–50¢ | registered 09-13 20:05Z, **CORRECTED 22:30Z by the audit** (`docs/math/preregistration_2026-09-19.md`). The −11.62¢ measurement itself REPRODUCES: independent SQL returns the same 227 rungs and 104 games, the venue settled 227 of 227, and on the 65 rungs where an ESPN final also exists the two agree 65/65 under the stated frame (frame-error rate ≤4.6%). The objection is power and multiplicity, not correctness. This line is the exact complement of the −11.62¢ away cell that motivated it — same 227 rows, opposite side — so its in-sample expectation is +11.62 − 4.17 (round-trip cost) = **+7.45¢, 95% CI [−2.67, +17.57], SPANS ZERO**, and it inherits the source's standard error. It cannot be stronger than the cell that generated it. The source cell was one of ≥10 statistics; at 20 looks the expected number of false "excludes zero" is exactly 1.00. **Interim observation on 09-19, no verdict**; first decision at G ≥ 195, which is 5 Saturdays uncorrected and 12 corrected | +7.45¢ [−2.67, +17.57] in-sample |
| **NFL spreads: the same pair, read Sunday 09-21** | the strongest test on the board and the one I mis-dated: NFL week 3 is a SUNDAY, and these lines carry **no prior** (the cell was never found in NFL tape), so their family is 2–4 names, not 24, and they need almost no correction | no in-sample number by construction |
| CFB / NFL totals: buy UNDER every rung; buy OVER every rung (mirror) | registered 09-13 18:30Z; the two-Saturday back-read is running, labelled a back-read | — |
| **Cricket and table tennis: tape started 2026-09-13 22:23Z** | first sweeps, by hand: cricket **15 markets** across CPL / T20 internationals / ODI / county, table tennis **148 markets** across four Setka Cup competitions. Expected-vs-observed matched per competition on every one, which is the check that makes an empty board distinguishable from a wrong slug | no strategy read yet; six lines registered awaiting tape |
| MLB first-five totals under/over; first-five spread NO 20–30¢ | registered 09-13 18:30Z, no tape | — |
| **NFL/CFB in-game momentum scalp** (buy the offence at the opponent's 40 / red zone / after a 2¢ move; take profit 2–10%, stop 5–20%; taker and maker exits) | **measured negative with power on CFB** (60 games, 27 cells, G 37–42): every cell −7.2 to −11.0¢ per $1 ticket, every interval below zero, home and away both negative. Mid drift after the trigger ≈ 0 (−0.6 to +0.7¢): the loss is half-spreads (3.8–5.7¢) plus two fees (4.1–5.4¢). Maker exit within 0.3¢ of taker. NFL: no finals yet, rerun tonight. Script `cfb/run_momentum_scalp.py`; the live paper loop still deploys so the same number accrues on the dashboard | best cell T2 red zone, TP 10 / stop 5: −7.22¢ [−9.52, −4.93] |
| DraftKings line move → Polymarket lag, take the DK-implied rung at the ask | measured on CFB 09-12 (23 games, 25 bets): venue lags DK by a median 30 min (n 19), but taking the rung is −9.2¢/$1 [−30.7, +12.3] at the first sweep, −13.0 at +1h, −24.5 [−46.7, −2.4] at +3h, all UNDERPOWERED (G 14–15); 5 of 24 moves already at price. Frame audit requested; NFL settles tonight; read 09-19 | — |
| Kalshi vs Polymarket same instant (CFB 09-12, 45 matched games, 66k pairs) | measured: median gap 0.25–0.5¢, <1% of instants beyond 3¢, 49 after-fee dutch instants in 66k (0.07%); who-is-stale underpowered (G 6–7). No pregame cross-venue trade. The 20–30¢ NO rung on Kalshi: −2.33¢/$1 [−13.31, +8.66], 36 games, loses about its fee | — |

**Five of the 29 registered names are arithmetic complements of another five**
(`cfb_total_under_all`/`over_all` and the nfl, mlb, mlb_f5 and cricket pairs):
they select identical rows with opposite sides, so their P&Ls sum to minus the
round-trip cost, a constant. "Under beat over" on such a pair is **guaranteed**
whenever under clears −½ round-trip, and is not evidence of anything. Read one
of each pair. There are 24 distinct statistics on the table, not 29.

"Measured negative with power" means: bet it and you lose, on the evidence. The
code stays; the bet does not get money. All lines above are scored every Monday
by `cfb/run_paper_book.py` (venue-settled, taker fee charged) and shown on the
dashboard's SCOREBOARD page once that page lands (being built). First run 2026-09-13 17:45Z: `docs/paper_book_2026-09-13.txt`, also on the box in artifacts/reads.

**The decision rule lost a clause tonight, and only a projection catches that
kind.** The registered rule was "G ≥ 25 AND excludes 0 AND the home/away twin
does not contradict". Projected onto the outcomes this design can produce, the
third clause passes on essentially all of them: for the twin to contradict the
away cell it would have to sit below −9.62¢, an 11.59¢ swing from where it
measures. A clause that cannot fire reads as corroboration while testing
nothing, and makes the rule look like three hurdles when it has two. **The twin
is now reported beside the cell and never gated on** — in the rule, in the paper
book's own footer, and in the pre-registration.

**A hand-run sweep must mount the checkout, or it silently records nothing.**
My first cricket sweep reported `markets_seen: 0, errors: 0` and exited 0 — a
clean success. The container runs the api IMAGE, built 09-05, which has no
`venue_leagues`, so it asked the venue for a league called "cricket"; that is
our internal name, not a venue slug, and **an unknown league returns 200 with an
empty list rather than a 404**. The tell was the duration: 0.03s against the
real sweep's 5.5s. Mounting `/opt/meridian/core` and `/opt/meridian/strategies`
fixes it, and the expected-vs-observed coverage line then proves the board was
actually read. MLB is unaffected — "mlb" happens to be the venue's own slug too.

## 3b. Open defects found tonight (none is a strategy question)

| defect | measurement | state |
|---|---|---|
| ~~`/api/games` has no limit bound~~ | `limit=-1` → 500 immediately; `limit=100000` → 200 in **29.1s**; a twelve-digit limit → 200 in 24.2s; `limit=abc` → 422 in 0.25s. An unauthenticated GET holds a worker for half a minute on a service bound to all interfaces | **FIXED, merged** (432cbe9): all five limits declared `Query(ge, le)`, caps sourced from the callers that actually pass one, the silent clamp deleted. Live on the box only after the api rebuild |
| ESPN recorder never observes the final | only ~41% of games reach `state='post'`; 14-day census 105 `post` vs 81 `in`. Cause: `refresh_live` collects only `state=='in'`, so a game leaving the live board is never polled again — it departs BEFORE it is final | **FIXED, merged** (878c0ee), **NOT DEPLOYED**: a departed game is polled at 60s until `post` is observed, exit on the state field never the clock, loud abandon 3h after departure, and an abandoned game is never marked final. Deploys **Tuesday, between slates**, with the plays-regression fix |
| `is_live` is never cleared | over the whole tape: 31,156 markets were ever live, **12,290 still say so on their last row, and 11,227 of those (91.4%) have not been written in 600s** — the same threshold the alarm uses; oldest such row 43 days. (My 30-day cut gave 5,364 of 12,160 over a day: the same fact at a looser threshold.) | **audited**: the scalp engine and the paper book never read it, and `core/board.py:market_state()` already guards it with the same 600s the alarm uses. **FIXED for the fair-value path** (5c8b328): `live_fv` and `live_totals_fv` now decide through `market_state()`, so there is one definition of live in the codebase; the flag stays only as a cheap prefilter. Its filter had been untested — all 58 existing tests passed with it neutralised, because every one was a pure-function test. The six analysis selectors are annotated and deliberately UNCHANGED: their populations are already published, and silently re-cutting them would make earlier findings irreproducible. **How the drag gets measured when someone wants it:** not as a standalone full-tape pass, but as a second column on a study already scanning those rows — the same statistic computed twice, once as published and once with a `captured_at` freshness guard, reported as a pair. One scan, both numbers, and the original stays reproducible beside it |
| `core/retention.py` dropped two indexes | hand-kept index lists missed the tipoff partials that took `/api/picks` from 4.75s to 0.42s | FIXED, merged |

## 4. Registered reads (dates fixed, criteria written before the tape)

- **Sat 09-19 (CFB):** interim observation only — print cell, G and interval, take no verdict. At ~40 games a Saturday a CFB cell must show **16.3¢** to exclude zero on one week, and nothing registered clears that. Full rule and corrections: `docs/math/preregistration_2026-09-19.md`.
- **Sun 09-21 (NFL):** the real test. Same two spread rules, no prior, family of 2–4, so the interval means what it says.
- Kalshi-vs-DraftKings lag on the first full week of tape.
- **ESPN cannot settle a football read; the venue endpoint is the only complete route.** The ESPN recorder stops polling a game before it observes the final transition, so a game has live state but never a result: on the best slate only 18 of 44 mapped games reach `state='post'` (~41%), and a 14-day census over all CFB games is 105 `post` against 81 stuck at `in` (three independent routes agree; there are exactly two terminal values and zero partially-settled games, which is what a per-GAME stage failure looks like). The venue endpoint returned 227 of 227 on the flagship bucket. ESPN keeps the independent frame check (65/65 agreement where it does finalise) and loses the settlement job. **Fix is in the recorder, not the map: keep polling until `post` is observed rather than until the clock runs out.**
- **The gate on every ESPN-settled read is recorder uptime across the slate, not the game map.** The earliest ESPN CFB state row in existence is 2026-09-05 22:08Z: the map wrote 13 of 13 rows for 09-03/09-04 and there was nothing to join to, and 09-05 lost its early games the same way. With the recorder up all day, 09-12 is 44 of 44. If a recorder dies mid-slate the games before it returns are lost silently — which is what `scripts/alarm_v5.py` (merged tonight) exists to catch.
- **WNBA playoffs:** favourite and under lines on the first 25 games; PULSE resumes.
- **MLB:** ladder calibration at 100 settled games (≈ one week after the recorder starts).
- **Mon 09-14 10:20Z:** the automatic NFL/CFB read (maker gate already FAIL at G=43).

## 5. Being built right now (agents, in their own worktrees, reviewed before merge)

Operator priorities set 09-13 evening: NFL in-game first (recorded at 0.5 s), simple take-profit/stop rules scored as paper lines, MLB recording daily. Aim $7k/week; $1k/week matters. Three peer sessions were alive at hand-over (Debugger, Builder D, Quant A); three researcher agents were spawned by the manager; a manager check-in runs every 30 min.

| agent | deliverable |
|---|---|
| Debugger (done) | MERGED 09-13 20:30Z: recorder plays regression + leak guard, idempotent index migration, health.py sees all 24 containers (test fails both ways), Kalshi recorder gives NFL a clock from the venue (kickoff+3h occurrence, applied in the open; the team map is WNBA-only so ESPN linking would mis-pair). Suite 1437→1451 passed, 25→21 failed (residual predates) |
| Builder D (done) | MLB: settlement cache, MLB ladder calibration, daily 10:40Z `mlb` cron mode — MERGED, crontab line installed |
| Quant A | DK line move → venue lag: first pass found the lag (CFB median 30 min, n=19, G=15; NFL median 61 min, n=7) but settled from the idle WNBA resolver table, so P&L had G=0; rerunning on the venue's settlement endpoint |
| researcher 1 | CFB 20–30¢ NO decomposed: favourite-fails vs dog-covers, monotone buckets with home-referenced twins, NO-mid definition |
| researcher 2 | Kalshi vs Polymarket cross-venue: gap, dutch count, who is stale, the longshot rung on Kalshi |
| researcher 3 (done) | momentum scalp grid: measured negative with power, see §3 |
| honest dashboard + JSON scoreboard | MERGED 09-13 (080aa97, 5891b4b, −255 lines); live after command 2 above |
| Builder D (done) | football in-game PAPER taker loop `core/gridiron/scalp.py` — MERGED 09-13 19:40Z, 47 rule tests, read-only by construction; live after command 3 above; parameters get refitted from tonight's backtest |
| Quant B (done) | in-game extreme-price hold to settlement: the fee is 0.06·p(1−p), so a 95¢ ticket pays 0.3% round trip against 6.0% at 50¢, and holding to settlement pays entry only — the one price region every measured strategy never reached. Bands 0.90–0.99 both sides, by period, one entry per game per band |
| research/audit | pre-registration for 09-19 with the multiplicity correction (~20 registered lines, several found in the data they will be read on), and a second-route audit of tonight's decomposition headline |
| researcher 4 (done) | cricket / TT discovery: 15 cricket events (CPL liquid), 4 Setka Cup TT leagues (69 events/day, 1–2¢), YES = home there; ENG v SL was England Lions; ESPN header/summary endpoints give toss, innings, result; Cricinfo 403 |
| Builder D (done) | league sweep: cricket/TT slugs resolved to NO league (fixed, 8 consumers route through one function); strategies/ interface (base.py, ladder.py) with a 198-row oracle proving identical selection; sandbox guard against a ladder name running the quote query — all MERGED |
| Builder D (done) | cricket + table-tennis recorder overlay (docker-compose.cricket.yml, venue_leagues sweep, expected-vs-observed per competition, settlements accept 0.5, six paper lines registered) — MERGED, in the paste above |
| builder (ESPN cricket feed, done) | core/feeds/espn_cricket_recorder.py (197 lines): toss timestamp, innings, result per match, change-detected — MERGED, in the paste |
| Debugger (done) | **production defect**: `core/retention.py` kept its index lists by hand and `migrate()` dropped the two tipoff partial indexes (the ones that took /api/picks from 4.75s to 0.42s); now read from the catalog. Also: the suite's order-dependence was `test_retention`'s destructive fixture on the shared DB, not a flaky test, and the "wallet NULL state cannot exist" claim was RETRACTED by its author — the column is still nullable and the historical tape needs that branch. Full suite 21 failed/1631 passed → 19 failed/1641 passed/0 errors — MERGED |
| Debugger (done) | suite triage: 23 → 3 failures, 0 dead tests, fixtures and guards fixed, stale infra docs reduced to pointers — MERGED |
| Builder D (done) | human_market moved out of core/api.py: the engines no longer load FastAPI on first label call (34 → 10 modules) — MERGED |
| codebase map / Kalshi–DK lag / shadow lister | merged earlier 09-13 |

## 6. Open questions for the researcher (docs/math/longshot-no-candidate.md §7)

1. ANSWERED 09-13 (`cfb/run_longshot_decomp.py`), then narrowed by audit: not a longshot effect. The one cell excluding zero is away at 50–60¢, −11.62 [−21.74, −1.50], G 104, verified end to end by an independent route. Its home twin is +1.97 [−7.65, +11.59], a null — what is established is that the AWAY side is expensive at coin-flip rungs, not that the home side is cheap everywhere.
2. Home shift in CFB weeks 1–2: real early-season mispricing or a 1.9σ draw? ~200 games decide.
3. Does the WNBA under-bias exist outside late August? Playoffs answer.
4. Kalshi vs DraftKings during the week: which moves first? Tape now exists.
5. ANSWERED 09-13: not monotone (−0.05, +2.48, +5.44, −2.64, +1.97 across 0→50¢), so the bucket boundary did the work.
