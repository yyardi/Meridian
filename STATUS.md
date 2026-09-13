# STATUS — Meridian / Gridiron (updated 2026-09-13 20:40Z)

One file. What runs, what it has earned on paper, what is being read next, what
you need to run, and who is building what. Full numbers: `docs/RESEARCH_REPORT_2026-09-13.md`.
Plan for the live candidate: `docs/math/longshot-no-candidate.md`.

## 1. Commands you need to run — ON THE BOX (paste from the laptop; the 20:00Z run built everything on the laptop instead)

```bash
# one paste from the laptop: builds MLB, api, both paper scalp engines, Kalshi, cricket + table-tennis recorders on the box, then lists them
ssh -i ~/.ssh/meridian-aws.pem ubuntu@$(cat ~/.meridian-server) 'cd /opt/meridian && sudo docker compose -f docker-compose.yml -f docker-compose.mlb.yml up -d --build mlb-recorder && sudo docker compose up -d --build api && sudo docker compose -f docker-compose.yml -f docker-compose.scalp.yml up -d --build scalp-nfl scalp-cfb && sudo docker compose up -d --build kalshi-recorder && sudo docker compose -f docker-compose.yml -f docker-compose.cricket.yml up -d --build cricket-recorder tt-recorder && sudo docker ps --format "{{.Names}} {{.Status}}" | grep -E "mlb|api|scalp|kalshi|cricket|tt-"'
```
Prod git is at origin/main (main-deploy); compose is classifier-blocked for the manager, so the paste is yours.

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
| MLB: under/over, favourite/dog, 20–30¢ NO | registered, no tape yet | — |
| **CFB / NFL spreads: buy NO (home) on rungs whose YES mid is 50–60¢**, twin = buy YES (away) at 40–50¢ | registered 09-13 20:05Z from the decomposition grid: away side at 50–60¢ lost −11.62¢/contract [−21.74, −1.50] on 104 games, one of ~20 cells; read 09-19 | — |
| CFB / NFL totals: buy UNDER every rung; buy OVER every rung (mirror) | registered 09-13 18:30Z; the two-Saturday back-read is running, labelled a back-read | — |
| MLB first-five totals under/over; first-five spread NO 20–30¢ | registered 09-13 18:30Z, no tape | — |
| **NFL/CFB in-game momentum scalp** (buy the offence at the opponent's 40 / red zone / after a 2¢ move; take profit 2–10%, stop 5–20%; taker and maker exits) | **measured negative with power on CFB** (60 games, 27 cells, G 37–42): every cell −7.2 to −11.0¢ per $1 ticket, every interval below zero, home and away both negative. Mid drift after the trigger ≈ 0 (−0.6 to +0.7¢): the loss is half-spreads (3.8–5.7¢) plus two fees (4.1–5.4¢). Maker exit within 0.3¢ of taker. NFL: no finals yet, rerun tonight. Script `cfb/run_momentum_scalp.py`; the live paper loop still deploys so the same number accrues on the dashboard | best cell T2 red zone, TP 10 / stop 5: −7.22¢ [−9.52, −4.93] |
| DraftKings line move → Polymarket lag, take the DK-implied rung at the ask | measured on CFB 09-12 (23 games, 25 bets): venue lags DK by a median 30 min (n 19), but taking the rung is −9.2¢/$1 [−30.7, +12.3] at the first sweep, −13.0 at +1h, −24.5 [−46.7, −2.4] at +3h, all UNDERPOWERED (G 14–15); 5 of 24 moves already at price. Frame audit requested; NFL settles tonight; read 09-19 | — |
| Kalshi vs Polymarket same instant (CFB 09-12, 45 matched games, 66k pairs) | measured: median gap 0.25–0.5¢, <1% of instants beyond 3¢, 49 after-fee dutch instants in 66k (0.07%); who-is-stale underpowered (G 6–7). No pregame cross-venue trade. The 20–30¢ NO rung on Kalshi: −2.33¢/$1 [−13.31, +8.66], 36 games, loses about its fee | — |

"Measured negative with power" means: bet it and you lose, on the evidence. The
code stays; the bet does not get money. All lines above are scored every Monday
by `cfb/run_paper_book.py` (venue-settled, taker fee charged) and shown on the
dashboard's SCOREBOARD page once that page lands (being built). First run 2026-09-13 17:45Z: `docs/paper_book_2026-09-13.txt`, also on the box in artifacts/reads.

## 4. Registered reads (dates fixed, criteria written before the tape)

- **Sat 09-19:** CFB 20–30¢ NO, held-out and pooled (G ≥ 25, positive, excludes 0); centre-rung home-shift rate by favourite side; Kalshi-vs-DraftKings lag (your friend's mechanism) on the first full week of tape.
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
| researcher 4 (done) | cricket / TT discovery: 15 cricket events (CPL liquid), 4 Setka Cup TT leagues (69 events/day, 1–2¢), YES = home there; ENG v SL was England Lions; ESPN header/summary endpoints give toss, innings, result; Cricinfo 403 |
| Builder D (done) | cricket + table-tennis recorder overlay (docker-compose.cricket.yml, venue_leagues sweep, expected-vs-observed per competition, settlements accept 0.5, six paper lines registered) — MERGED, in the paste above |
| builder (ESPN cricket feed) | core/feeds/espn_cricket_recorder.py: toss timestamp, innings, result per venue-listed match — building |
| codebase map / Kalshi–DK lag / shadow lister | merged earlier 09-13 |

## 6. Open questions for the researcher (docs/math/longshot-no-candidate.md §7)

1. ANSWERED 09-13 (`cfb/run_longshot_decomp.py`): home-shift, not longshot. Home side beats its price at every rung, away loses at every rung (5/5 twin pairs, 5–14¢); the 20–30¢ cell is where a noisy home series peaks. Only cell excluding 0: away at 50–60¢, −11.62 [−21.74, −1.50], G 104.
2. Home shift in CFB weeks 1–2: real early-season mispricing or a 1.9σ draw? ~200 games decide.
3. Does the WNBA under-bias exist outside late August? Playoffs answer.
4. Kalshi vs DraftKings during the week: which moves first? Tape now exists.
5. ANSWERED 09-13: not monotone (−0.05, +2.48, +5.44, −2.64, +1.97 across 0→50¢), so the bucket boundary did the work.
