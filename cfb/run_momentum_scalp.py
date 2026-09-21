"""Momentum scalp on the football in-game tape, scored exactly as a taker would live it.

THE IDEA (operator, 2026-09-13, measured not argued): when the offense drives toward the end
zone, buy that team on the winner market; take profit at 1-10 %, stop out fast; rapid small wins.

DESIGN -- registered here before the first outcome run.
 Substrate  market_snapshots winner market (sports_market_type football_team_full_game_winner,
   slug aec-<lg>-<away>-<home>-<date>, YES = away), pulled ONE GAME AT A TIME by venue game_id;
   plays from espn_cfb_live_plays (league column carries cfb AND nfl), joined through
   cfb_game_map espn_game_id -> venue_game_id (NFL rows are present, division='NFL').
 Play filter  down 1..4, 1 <= yards_to_goal <= 99 (offense's distance to goal: kickoff 76,
   punt 92 -- verified), period 1..4, not OT, play_type not timeout / kickoff / end-of-period
   (those rows carry yards_to_goal = 0 and would fire a false red-zone trigger).
 Triggers  once per drive_id: T1 = first play with ytg <= 40; T2 = first play with ytg <= 20;
   T3 = price only, mid moved >= 2c versus the mid 60 s earlier (buy the side it moved toward),
   in-game ticks only, one T3 position at a time (lockout = its 180 s fallback).
 Entry  the first tick with captured_at STRICTLY AFTER trigger time + LATENCY (default 3 s;
   LATENCY=poll anchors on the play's first_seen_at, i.e. when OUR poller saw it -- the header
   prints that lag; it is ~55 s, so 3 s is an optimistic bound).  Offense = away -> YES at ask;
   offense = home -> NO at 1 - bid.  Taker fee c*p*(1-p) per share on entry and on every taker
   exit, c the coefficient recorded on THAT tick (the venue raised it on 2026-09-17, so a run
   spanning it charges two values; no fee on settlement, no maker fee, no rebate).
 Gates (each counted)  trigger play must not share the game's first wall-clock second
   (recorder-start bunch); the mid must have changed within the 120 s before the entry tick
   (frozen board); entry spread <= 10c.
 Exits  evaluated on every later tick at the exit-side executable price (YES: bid; NO: 1-ask):
   take-profit k % of entry price, k in {2,5,10}, stop s %, s in {5,10,20}; else drive end = the
   first tick after (first filtered play of another possession + LATENCY); T3 falls back to a
   180 s time stop.  RIDE holds to settlement from espn_cfb_game_state's latest row with
   state='post' (games without one are skipped and counted).  MAKER rests the sell at
   entry*(1+k) and counts it filled the first time the executable exit price >= that level,
   no exit fee -- OPTIMISTIC (a touch is not a fill); stop / drive end stay taker.
 Game eligibility  settled ('post') or last play older than 4 h (over by the clock); drive-end
   cells use both, RIDE uses settled only.
 Orientation, tested on every game  plays.home/away == map home/away espn ids; on settled games
   sign(last live mid - 0.5) == sign(away won).  Failures are counted, never corrected.
 Statistics  mean net per $1 of ticket in cents, 95 % game-clustered sandwich CI, Kish G_eff,
   gross, total fee, exit shares tp/stop/end, median hold; split by offense home (NO) vs away
   (YES).  G < 25 is UNDERPOWERED.  A cell is a finding only if it excludes 0 after fees on
   G >= 25 AND both home/away twins carry the sign.

RUN (prod, read-only; env flags inside docker run): LEAGUE=cfb|nfl, LATENCY=3|poll
  ssh ubuntu@$SRV 'sudo -n docker run --rm -i --network meridian_default \\
    -e DATABASE_URL=postgresql+psycopg://meridian:meridian@postgres:5432/meridian -e LEAGUE=cfb \\
    -w /app meridian-trainer python3 -' < cfb/run_momentum_scalp.py
"""
import datetime as dt, os, sys
from bisect import bisect_right
from collections import defaultdict

from sqlalchemy import create_engine, event, text
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) if "__file__" in globals() else os.getcwd())  # run bare: the trainer image mounts cfb/ alone; piped over stdin (nightly_scan.sh) there is no __file__ and cwd is the repo root
from core.fees import POLYMARKET_TAKER, recorded_fee, taker_fee  # noqa: E402  every tick on tape is charged its own; taker_fee: the illustrative table only

LG, LAT = os.environ.get("LEAGUE", "cfb"), os.environ.get("LATENCY", "3")
KS, SS, T3_MOVE = (2, 5, 10), (5, 10, 20), 0.02
S3, S60, S120, S180 = (dt.timedelta(seconds=x) for x in (3, 60, 120, 180))
NOW = dt.datetime.now(dt.timezone.utc)
BAD = ("timeout", "kickoff", "end period", "end of", "two-minute", "warning")
eng = create_engine(os.environ["DATABASE_URL"])
@event.listens_for(eng, "connect")
def _np(conn, _rec):
    cur = conn.cursor(); cur.execute("SET max_parallel_workers_per_gather = 0"); cur.close(); conn.commit()

Q_GAMES = """WITH fin AS (SELECT DISTINCT ON (game_id) game_id, state, home_score hs, away_score aws
  FROM espn_cfb_game_state WHERE league = :lg ORDER BY game_id, first_seen_at DESC)
SELECT p.game_id eg, m.venue_game_id vg, m.home_espn_team_id mh, m.away_espn_team_id ma, min(p.home) ph,
       min(p.away) pa, max(p.wall_clock) t1, f.state, f.hs, f.aws
FROM espn_cfb_live_plays p JOIN cfb_game_map m ON m.espn_game_id = p.game_id LEFT JOIN fin f ON f.game_id = p.game_id
WHERE p.league = :lg AND m.venue_game_id IS NOT NULL AND p.wall_clock IS NOT NULL
GROUP BY 1, 2, 3, 4, 8, 9, 10 ORDER BY min(p.wall_clock)"""
Q_PLAYS = """SELECT wall_clock wc, first_seen_at fs, period, is_overtime ot, down, yards_to_goal ytg, pos_team pos,
  drive_id drv, coalesce(play_type, '') pt FROM espn_cfb_live_plays
WHERE game_id = :eg AND league = :lg AND wall_clock IS NOT NULL ORDER BY wall_clock, id"""
Q_TICKS = """SELECT captured_at t, best_bid::float b, best_ask::float a, fee_coefficient::float fc FROM market_snapshots
WHERE game_id = :vg AND sports_market_type = 'football_team_full_game_winner' AND captured_at BETWEEN :lo AND :hi
  AND best_bid > 0 AND best_ask < 1 AND best_ask >= best_bid ORDER BY captured_at"""

def clustered(vals, keys):
    n = len(vals); m = sum(vals) / n; res, size = defaultdict(float), defaultdict(int)
    for v, k in zip(vals, keys): res[k] += v - m; size[k] += 1
    G = len(res); ge = n * n / sum(c * c for c in size.values())
    se = (sum(x * x for x in res.values()) ** 0.5) / n * (G / (G - 1)) ** 0.5 if G > 1 else float("inf")
    return m, 1.96 * se, n, G, ge
def med(xs): xs = sorted(xs); return xs[len(xs) // 2] if xs else float("nan")

C, cells, spreads, lags = defaultdict(int), defaultdict(list), [], []
def ptime(p): return (p["fs"] if LAT == "poll" else p["wc"]) + S3

DBG = os.environ.get("DEBUG_GAME")   # espn game_id: dump every (5,10) taker trade for a by-eye check against raw ticks
def trade(arm, side, t_in, deadline, T, B, A, M, FC, chg, game, away_won):
    """FC[i] is the fee_coefficient recorded on tick i: the entry is charged at its tick's and a taker exit
    at ITS tick's, so one trade can straddle the venue's 2026-09-17 raise. None raises (recorded_fee)."""
    i = bisect_right(T, t_in)                       # first tick STRICTLY after the information
    if i >= len(T): C["entry dropped: no tick after trigger"] += 1; return
    if T[i] - chg[i] > S120: C["TRAP frozen board: no mid change in 120 s"] += 1; return
    if A[i] - B[i] > 0.10: C["entry dropped: spread > 10c"] += 1; return
    p_in = A[i] if side == "YES" else 1 - B[i]; f_in = recorded_fee(p_in, FC[i])
    x = (lambda j: B[j]) if side == "YES" else (lambda j: 1 - A[j])
    def book(key, p_out, taker, kind, j):   # exact split: gross = signed mid drift - half-spreads paid (settle: all drift)
        f_out = recorded_fee(p_out, FC[j]) if taker else 0.0; gross = (p_out - p_in) / p_in * 100
        hs = 0.0 if kind == "settle" else (A[i] - B[i] + A[j] - B[j]) / 2 / p_in * 100
        cells[key].append((gross - (f_in + f_out) / p_in * 100, gross, (f_in + f_out) / p_in * 100, kind,
                           (T[j] - T[i]).total_seconds(), game, side, gross + hs, hs, p_in, (A[i] - B[i]) / p_in * 100))
        if DBG == game and key[1:] == ("taker", 5, 10): print(f"  DBG {arm} {side} in {T[i]:%H:%M:%S} @{p_in:.3f} -> {kind} {T[j]:%H:%M:%S} @{p_out:.3f} net {gross - (f_in + f_out) / p_in * 100:+.2f}")
    j_end = min(bisect_right(T, deadline), len(T) - 1)   # first tick after the drive ended
    for k in KS:
        for s in SS:
            for mode in ("taker", "maker"):
                tp, st = p_in * (1 + k / 100), p_in * (1 - s / 100)
                for j in range(i + 1, j_end + 1):
                    v = x(j)
                    if j == j_end: book((arm, mode, k, s), v, True, "end", j); break
                    if v >= tp: book((arm, mode, k, s), v if mode == "taker" else tp, mode == "taker", "tp", j); break
                    if v <= st: book((arm, mode, k, s), v, True, "stop", j); break
                else: C["trade dropped: no tick after entry"] += 1
    if away_won is not None and arm != "T3":
        book((arm, "ride", 0, 0), 1.0 if (side == "YES") == away_won else 0.0, False, "settle", len(T) - 1)
    elif arm != "T3": C["ride skipped: no 'post' final"] += 1
    return T[j_end]

with eng.connect() as c:
    games = [dict(r._mapping) for r in c.execute(text(Q_GAMES), {"lg": LG})]
    for g in games:
        C["games mapped to venue"] += 1
        if g["ph"] != g["mh"] or g["pa"] != g["ma"]: C["TRAP orientation: plays home/away != map ids"] += 1; continue
        settled = g["state"] == "post" and g["hs"] is not None and g["hs"] != g["aws"]
        if not settled and g["t1"] > NOW - dt.timedelta(hours=4): C["games skipped: in progress / no final"] += 1; continue
        plays = [dict(r._mapping) for r in c.execute(text(Q_PLAYS), {"eg": g["eg"], "lg": LG})]
        first_wc = plays[0]["wc"]
        P = [p for p in plays if p["down"] and 1 <= p["down"] <= 4 and p["ytg"] and 1 <= p["ytg"] <= 99 and p["period"]
             and 1 <= p["period"] <= 4 and not p["ot"] and not any(b in p["pt"].lower() for b in BAD)
             and p["wc"] < first_wc + dt.timedelta(hours=5)]
        if len(P) < 40: C["games skipped: < 40 usable plays"] += 1; continue
        lags.extend((p["fs"] - p["wc"]).total_seconds() for p in P)
        rows = c.execute(text(Q_TICKS), {"vg": g["vg"], "lo": P[0]["wc"] - dt.timedelta(minutes=10),
                                         "hi": P[-1]["wc"] + dt.timedelta(minutes=40)}).fetchall()
        if len(rows) < 50: C["games skipped: no winner tape"] += 1; continue
        C["games scored"] += 1; C["games settled ('post')"] += settled
        T, B, A, FC = [r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows], [r[3] for r in rows]
        M = [(a + b) / 2 for a, b in zip(A, B)]
        chg = [T[0]]
        for i in range(1, len(T)): chg.append(T[i] if M[i] != M[i - 1] else chg[-1])
        spreads.extend((A[i] - B[i]) * 100 for i in range(len(T)) if P[0]["wc"] <= T[i] <= P[-1]["wc"])
        away_won = (g["aws"] > g["hs"]) if settled else None
        if settled:
            C["orientation settle-checked"] += 1
            if (M[-1] > 0.5) != away_won: C["TRAP orientation: last mid disagrees with ESPN winner"] += 1
        fired = set()
        for idx, p in enumerate(P):
            for arm, thr in (("T1", 40), ("T2", 20)):
                if p["ytg"] > thr or (p["drv"], arm) in fired: continue
                fired.add((p["drv"], arm)); C[f"{arm} triggers"] += 1
                if p["wc"] == first_wc: C["TRAP trigger on the game's first wall-clock second"] += 1; continue
                side = "YES" if p["pos"] == g["pa"] else "NO" if p["pos"] == g["ph"] else None
                if side is None: C["trigger dropped: offense not home/away id"] += 1; continue
                nxt = next((q for q in P[idx + 1:] if q["pos"] != p["pos"]), None)
                trade(arm, side, ptime(p), ptime(nxt) if nxt else T[-1], T, B, A, M, FC, chg, g["eg"], away_won)
        lock, j0 = T[0], 0
        for i in range(len(T)):
            if T[i] < lock or not (P[0]["wc"] <= T[i] <= P[-1]["wc"]): continue
            while j0 + 1 < i and T[j0 + 1] <= T[i] - S60: j0 += 1
            if T[j0] > T[i] - S60: continue
            d = M[i] - M[j0]
            if abs(d) >= T3_MOVE:
                C["T3 triggers"] += 1
                lock = trade("T3", "YES" if d > 0 else "NO", T[i] + S3, T[i] + S3 + S180, T, B, A, M, FC, chg, g["eg"], None) or T[i] + S180

print(f"LEAGUE={LG} LATENCY={LAT}  run {NOW:%Y-%m-%d %H:%M}Z  games in plays+map {len(games)}")
for k in sorted(C): print(f"  {k}: {C[k]}")
if not lags: raise SystemExit("NO DATA: no game scored")
S = med(spreads) / 100
print(f"  ESPN play poll lag first_seen_at - wall_clock: median {med(lags):.0f} s (p90 {sorted(lags)[int(0.9 * len(lags))]:.0f} s)"
      f" -- LATENCY=3 assumes the play is tradable 3 s after wall_clock")
print(f"\nFEE TABLE  taker {POLYMARKET_TAKER}*p*(1-p) per share at TODAY's coefficient, both legs (the cells below charge each tick at"
      f" its recorded one); median in-game winner spread S = {S * 100:.2f}c (n={len(spreads)})"
      "\n  YES price  round-trip fee %ticket   mid move (c) needed for +1c/$1 ticket after 2 fees + 1 spread")
for p in (0.2, 0.3, 0.5, 0.7, 0.8):
    print(f"  {p * 100:5.0f}c   {2 * taker_fee(p) / p * 100:7.2f} %            {(S + 2 * taker_fee(p) + 0.01 * p) * 100:6.2f}")  # fee-now: an illustration over hypothetical prices, no row exists

def ci(rows):
    if len(rows) < 2: return "n/a"
    m, hw, n, G, ge = clustered([r[0] for r in rows], [r[5] for r in rows])
    return f"{m:+6.2f} [{m - hw:+6.2f},{m + hw:+6.2f}] n={n:<4d} G={G:<3d}"
for arm in ("T1", "T2", "T3"):
    for mode in ("taker", "maker", "ride"):
        keys = [(arm, mode, k, s) for k in KS for s in SS] if mode != "ride" else [(arm, mode, 0, 0)]
        if not any(cells[k] for k in keys): continue
        E = cells[(arm, "taker", 2, 5)]; ent = lambda sd: [r for r in E if r[6] == sd]
        print(f"\n== {LG.upper()} {arm} {mode.upper()}  net c per $1 ticket after fees, 95% game-clustered.  Entries: median price"
              f" HOME {med([r[9] for r in ent('NO')]):.2f} AWAY {med([r[9] for r in ent('YES')]):.2f}; entry spread %ticket median"
              f" {med([r[10] for r in E]):.1f} p75 {sorted(r[10] for r in E)[int(0.75 * len(E))]:.1f}, share > 5% {100 * sum(r[10] > 5 for r in E) / len(E):.0f}%")
        print("  k%  s% |    n   G  G_eff |  net  [95% CI]         | drift  sprd  gross |  fee | tp/stop/end % | hold s | offense=HOME (NO)             | offense=AWAY (YES)")
        for key in keys:
            R = cells[key]
            if len(R) < 2: continue
            m, hw, n, G, ge = clustered([r[0] for r in R], [r[5] for r in R])
            sh = {k: 100 * sum(1 for r in R if r[3] == k) / n for k in ("tp", "stop", "end")}
            print(f"  {key[2]:>2d}  {key[3]:>2d} | {n:>4d} {G:>3d} {ge:6.1f} | {m:+6.2f} [{m - hw:+6.2f},{m + hw:+6.2f}]"
                  f"{'*' if G >= 25 and (m - hw > 0 or m + hw < 0) else ' '}{'U' if G < 25 else ' '} | {sum(r[7] for r in R) / n:+5.2f} {sum(r[8] for r in R) / n:5.2f} {sum(r[1] for r in R) / n:+5.2f}"
                  f" | {sum(r[2] for r in R) / n:4.2f} | {sh['tp']:3.0f}/{sh['stop']:3.0f}/{sh['end']:3.0f}  | {med([r[4] for r in R]):6.0f}"
                  f" | {ci([r for r in R if r[6] == 'NO'])} | {ci([r for r in R if r[6] == 'YES'])}")
print("\n* = CI excludes 0 with G >= 25;  U = UNDERPOWERED (G < 25).  MAKER tp fills are optimistic (touch != fill)."
      "\ndrift = signed mid move entry->exit in the position's favour; sprd = half-spreads paid at entry and exit; gross = drift - sprd; net = gross - fee.")
