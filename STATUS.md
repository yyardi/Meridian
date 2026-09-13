# STATUS — Meridian / Gridiron (updated 2026-09-13 18:40Z)

One file. What runs, what it has earned on paper, what is being read next, what
you need to run, and who is building what. Full numbers: `docs/RESEARCH_REPORT_2026-09-13.md`.
Plan for the live candidate: `docs/math/longshot-no-candidate.md`.

## 1. Commands you need to run on the AWS box (from a fresh shell there)

```bash
# 1. start MLB recording (staged on the box; ~55 events/day, 495 markets, boards ~4 days ahead, RPS 3)
cd /opt/meridian && sudo docker compose -f docker-compose.yml -f docker-compose.mlb.yml up -d --build mlb-recorder

# 2. rebuild the api: SCOREBOARD page + honest PULSE page merged 09-13 18:20Z; files and the reads mount are staged on the box
cd /opt/meridian && sudo docker compose up -d --build api

# 3. make prod's git match main (an untracked file blocks the fast-forward; this keeps the two locally-edited files)
cd /opt/meridian && sudo mv cfb/run_making.py cfb/run_making.py.old && sudo git stash && sudo git merge --ff-only origin/main && sudo git stash pop

# 4. (laptop, optional) three recorder containers have run on the laptop since 09-12, one crash-looping; the rule is nothing runs on the laptop
docker stop meridian-kalshi-recorder meridian-nfl-odds-recorder meridian-cfb-odds-recorder
```

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
| CFB / NFL totals: buy UNDER every rung; buy OVER every rung (mirror) | registered 09-13 18:30Z; the two-Saturday back-read is running, labelled a back-read | — |
| MLB first-five totals under/over; first-five spread NO 20–30¢ | registered 09-13 18:30Z, no tape | — |
| **NFL/CFB in-game momentum scalp** (the operator's rule: buy the offence driving into opponent territory / red zone, take profit 2–10%, stop 5–20%, maker-exit variant) | being scored on the in-game tape now, grid by trigger × take-profit × stop, both leagues, home/away split | — |
| DraftKings line move → Polymarket lag, taker on the implied rung (NFL/CFB pregame) | being scored (Quant A) | — |
| Kalshi vs Polymarket same instant: gap distribution, dutch count after both fees, who is stale, the 20–30¢ rung on Kalshi | being scored | — |

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
| Debugger | main's CFB ESPN recorder regression (fa24613, prod's image predates it, 09-12 was not hit) + the leak guard; idempotent index migration (laptop Kalshi crash-loop); health.py's 6 missing containers; Kalshi recorder sets NFL kickoffs from ESPN |
| Builder D | MLB: settlement cache so the paper book can run daily; ladder calibration for MLB from day one settled by the venue; a daily 10:40Z `mlb` cron mode |
| Quant A | DK line move → venue lag: taker P&L after fee on the implied rung, by side, by horizon, raw lag in minutes |
| researcher 1 | CFB 20–30¢ NO decomposed: favourite-fails vs dog-covers, monotone buckets with home-referenced twins, NO-mid definition |
| researcher 2 | Kalshi vs Polymarket cross-venue: gap, dutch count, who is stale, the longshot rung on Kalshi |
| researcher 3 | the momentum scalp grid (§3), fee table first |
| honest dashboard | MERGED 09-13 18:20Z (080aa97); live after command 2 above |
| codebase map / Kalshi–DK lag / shadow lister | merged earlier 09-13 |

## 6. Open questions for the researcher (docs/math/longshot-no-candidate.md §7)

1. Away-team effect vs longshot effect: on this venue YES is always the away team; split every price bucket by side before believing it.
2. Home shift in CFB weeks 1–2: real early-season mispricing or a 1.9σ draw? ~200 games decide.
3. Does the WNBA under-bias exist outside late August? Playoffs answer.
4. Kalshi vs DraftKings during the week: which moves first? Tape now exists.
5. Why 20–30¢ and not 10–20¢? If the mechanism is real it should be monotone.
