"""Buy the near-certain side in-game at the ask and HOLD TO SETTLEMENT: one fee, not two.

WHY THIS CELL AND NOT ANOTHER. The fee is 0.06*p*(1-p) per side, so it collapses at the
extremes: a round trip costs 6.0% of the ticket at 50c but 1.2% at 90c and 0.4% at 95c. Every
strategy measured so far died at mid prices paying two fees plus two half-spreads. Holding to
settlement pays ONE fee and ONE half-spread, and pays them where they are smallest.

THE NULL IS NOT ZERO, AND THAT IS THE POINT OF THE DECOMPOSITION. Against a perfectly
calibrated market, buying at the ask when the MID is in the band loses exactly
(ask - mid) + fee. So every cell is split, exactly and additively, into
    net = (y - mid)          calibration: is the market's own mid wrong?
        - (ask - mid)        crossing:    what we pay to take the offer
        - fee(p)             the venue's 0.06*p*(1-p)
A cell that is negative with calibration ~0 is a cost result, not a mispricing result. That
split is what made the momentum scalp legible and it is the only way to read these tables.

PRE-REGISTERED BEFORE THE FIRST RUN. Primary = band x side, POOLED over periods: 4 bands x 2
sides = 8 cells. The period/half splits are EXPLORATORY and labelled so. The brief records
~40 buckets already looked at on this tape; this file adds 8 primary and 48 exploratory, and
nothing here is a discovery unless it survives its twin.

YES IS ALWAYS THE AWAY TEAM. So "buy YES at 0.95" is an away near-certain winner and "buy NO
at 0.95" (YES mid in the mirror band) is a HOME one. CFB weeks 1-2 carry a measured whole-
ladder home shift (cfb/run_longshot_decomp.py: home beats its price at all five rung pairs),
so the NO side is expected to look better for a reason that has nothing to do with extremity.
Every band prints beside its mirror twin; a band that works on one side only is an artifact.

TRAPS, each gated and counted rather than described:
  * change-detected writes mean a frozen board looks like a held price -> an entry counts only
    if the mid CHANGED within the prior 120 s; drops are counted.
  * a recorder that started mid-game has its first tick at an extreme price -> the tradeable
    window is bounded by ESPN PLAY wall-clock, never by the first tick row.
  * a tick after the game's last play is not tradeable -> window ends at the last usable play.
  * ESPN UN-POSTS: 2 of 29 games change margin at or after their first 'post' row and one
    changes the WINNER, so settlement is the LAST state row, never the first 'post'.
  * bands share games (a game climbing 0.90 -> 0.98 enters several), so cells are NOT
    independent of each other; the clustered interval covers within-cell dependence only.

RUN (prod, read-only; env flags INSIDE docker run, which sudo would otherwise drop):
  ssh ubuntu@$SRV 'sudo -n docker run --rm -i --network meridian_default \\
    -e DATABASE_URL=postgresql+psycopg://meridian:meridian@postgres:5432/meridian -e LEAGUE=cfb \\
    -w /app meridian-trainer python3 -' < cfb/run_extreme_hold.py
Nothing is placed. G < 25 is UNDERPOWERED, reported and kept.
"""
import datetime as dt, os, sys
from bisect import bisect_right
from collections import defaultdict

from sqlalchemy import create_engine, event, text

sys.stdout.reconfigure(line_buffering=True)   # a long per-game run must show progress
LG = os.environ.get("LEAGUE", "cfb")
FEE, S120 = 0.06, dt.timedelta(seconds=120)
NOW = dt.datetime.now(dt.timezone.utc)
BANDS = [(0.900, 0.925), (0.925, 0.950), (0.950, 0.975), (0.975, 0.990)]
BAD = ("timeout", "kickoff", "end period", "end of", "two-minute", "warning")
eng = create_engine(os.environ["DATABASE_URL"])
@event.listens_for(eng, "connect")
def _np(conn, _rec):
    cur = conn.cursor(); cur.execute("SET max_parallel_workers_per_gather = 0"); cur.close(); conn.commit()

Q_GAMES = """WITH fin AS (SELECT DISTINCT ON (game_id) game_id, state, home_score hs, away_score aws
  FROM espn_cfb_game_state WHERE league = :lg ORDER BY game_id, first_seen_at DESC)
SELECT p.game_id eg, m.venue_game_id vg, m.home_espn_team_id mh, m.away_espn_team_id ma,
       min(p.home) ph, min(p.away) pa, max(p.wall_clock) t1, f.state, f.hs, f.aws
FROM espn_cfb_live_plays p JOIN cfb_game_map m ON m.espn_game_id = p.game_id
LEFT JOIN fin f ON f.game_id = p.game_id
WHERE p.league = :lg AND m.venue_game_id IS NOT NULL AND p.wall_clock IS NOT NULL
GROUP BY 1,2,3,4,8,9,10 ORDER BY min(p.wall_clock)"""
Q_PLAYS = """SELECT wall_clock wc, period, is_overtime ot, down, yards_to_goal ytg,
  coalesce(play_type,'') pt FROM espn_cfb_live_plays
WHERE game_id = :eg AND league = :lg AND wall_clock IS NOT NULL ORDER BY wall_clock, id"""
Q_TICKS = """SELECT captured_at t, best_bid::float b, best_ask::float a, fee_coefficient::float fc
FROM market_snapshots WHERE game_id = :vg AND sports_market_type = :mt
  AND captured_at BETWEEN :lo AND :hi AND best_bid > 0 AND best_ask < 1 AND best_ask >= best_bid
ORDER BY captured_at"""
MT = "football_team_full_game_winner"


def fee(p): return FEE * p * (1 - p)


def clustered(vals, keys):                     # verbatim from cfb/run_paper_book.py
    n = len(vals); m = sum(vals) / n
    res, size = defaultdict(float), defaultdict(int)
    for v, k in zip(vals, keys): res[k] += v - m; size[k] += 1
    G = len(res); ge = n * n / sum(c * c for c in size.values())
    se = (sum(x * x for x in res.values()) ** 0.5) / n * (G / (G - 1)) ** 0.5 if G > 1 else float("inf")
    return m, 1.96 * se, n, G, ge


def med(xs): xs = sorted(xs); return xs[len(xs) // 2] if xs else float("nan")


def cell(bets):
    """bets: dicts with net/calib/cross/fe (dollars per $1 contract), win, game, secs, dips."""
    if not bets: return "n=0"
    m, h, n, G, ge = clustered([100 * b["net"] for b in bets], [b["game"] for b in bets])
    ca = 100 * sum(b["calib"] for b in bets) / n
    cr = 100 * sum(b["cross"] for b in bets) / n
    fe = 100 * sum(b["fe"] for b in bets) / n
    wr = sum(b["win"] for b in bets) / n
    be = sum(b["p"] + fee(b["p"]) for b in bets) / n
    return (f"{m:+6.2f} [{m - h:+6.2f},{m + h:+6.2f}] n={n:<4} G={G:<3} G_eff={ge:5.1f} "
            f"| calib{ca:+6.2f} cross{cr:+6.2f} fee{fe:+6.2f} | win {wr:5.1%} need {be:5.1%} "
            f"| {med([b['secs'] for b in bets]) / 60:4.0f}m {med([b['dips'] for b in bets]):3.0f}dip"
            + ("  UNDERPOWERED" if G < 25 else ""))


C, cells = defaultdict(int), defaultdict(list)
with eng.connect() as c:
    games = [dict(r._mapping) for r in c.execute(text(Q_GAMES), {"lg": LG})]
    for g in games:
        C["games in plays+map"] += 1
        if g["ph"] != g["mh"] or g["pa"] != g["ma"]: C["TRAP orientation: plays vs map ids"] += 1; continue
        settled = g["state"] == "post" and g["hs"] is not None and g["hs"] != g["aws"]
        if not settled: C["skipped: no settled final (last state row)"] += 1; continue
        plays = [dict(r._mapping) for r in c.execute(text(Q_PLAYS), {"eg": g["eg"], "lg": LG})]
        if not plays: continue
        f0 = plays[0]["wc"]
        P = [p for p in plays if p["period"] and 1 <= p["period"] <= 4 and not p["ot"]
             and not any(b in p["pt"].lower() for b in BAD) and p["wc"] < f0 + dt.timedelta(hours=5)]
        if len(P) < 40: C["skipped: < 40 usable plays"] += 1; continue
        rows = c.execute(text(Q_TICKS), {"vg": g["vg"], "mt": MT, "lo": P[0]["wc"],
                                         "hi": P[-1]["wc"]}).fetchall()
        if len(rows) < 50: C["skipped: no in-game winner tape"] += 1; continue
        if any(abs(r[3] - FEE) > 1e-9 for r in rows if r[3] is not None):
            C["TRAP fee_coefficient != 0.06 on some tick"] += 1; continue
        C["games scored"] += 1
        if C["games scored"] % 20 == 0: print(f"  ... {C['games scored']} games scored")
        T = [r[0] for r in rows]; B = [r[1] for r in rows]; A = [r[2] for r in rows]
        M = [round((a + b) / 2, 4) for a, b in zip(A, B)]          # round to tick before bucketing
        chg = [T[0]]
        for i in range(1, len(T)): chg.append(T[i] if M[i] != M[i - 1] else chg[-1])
        pw = [p["wc"] for p in P]
        away_won = g["aws"] > g["hs"]
        if (M[-1] > 0.5) != away_won: C["TRAP last in-game mid disagrees with ESPN winner"] += 1
        fired = set()
        for i in range(len(T)):
            for lo, hi in BANDS:
                for side in ("YES", "NO"):
                    key = (lo, hi, side)
                    if key in fired: continue
                    m = M[i]
                    hit = (lo <= m < hi) if side == "YES" else (1 - hi < m <= 1 - lo)
                    if not hit: continue
                    fired.add(key)
                    if T[i] - chg[i] > S120: C["TRAP frozen board: no mid change in 120 s"] += 1; continue
                    p = A[i] if side == "YES" else B[i]          # fee prices on the YES price either way
                    paid = A[i] if side == "YES" else 1 - B[i]
                    y = 1 if away_won else 0
                    win = y if side == "YES" else 1 - y
                    calib = (y - m) if side == "YES" else (m - y)
                    cross = -(A[i] - m) if side == "YES" else -(m - B[i])
                    net = win - paid - fee(p)
                    per = P[bisect_right(pw, T[i]) - 1]["period"] if bisect_right(pw, T[i]) else 1
                    dips = sum(1 for j in range(i + 1, len(T))
                               if (M[j] < lo if side == "YES" else M[j] > 1 - lo)
                               and (M[j - 1] >= lo if side == "YES" else M[j - 1] <= 1 - lo))
                    b = dict(net=net, calib=calib, cross=cross, fe=-fee(p), win=win, p=paid,
                             game=g["eg"], secs=(T[-1] - T[i]).total_seconds(), dips=dips)
                    cells[key].append(b); cells[(lo, hi, side, per)].append(b)
                    cells[(lo, hi, side, "H1" if per <= 2 else "H2")].append(b)
                    C[f"entries {side}"] += 1

print(f"LEAGUE={LG}  run {NOW:%Y-%m-%d %H:%M}Z  fee 0.06*p*(1-p) VERIFIED on every scored tick")
for k in sorted(C): print(f"  {k}: {C[k]}")
if not cells: raise SystemExit("NO DATA: no entry taken")
hdr = ("cents per $1 contract [95% game-clustered sandwich] n G G_eff | exact split: calibration "
       "(y-mid), crossing (ask-mid), fee | win rate vs break-even | median minutes held, median dips below band")
print(f"\nPRIMARY (pre-registered): band x side, pooled over periods\n  {hdr}")
for lo, hi in BANDS:
    print(f"  [{lo:.3f},{hi:.3f})  YES/away  {cell(cells[(lo, hi, 'YES')])}")
    print(f"  mirror ({1 - hi:.3f},{1 - lo:.3f}]  NO/home   {cell(cells[(lo, hi, 'NO')])}")
print("\nEXPLORATORY: by period and half (not pre-registered; 48 cells)")
for lo, hi in BANDS:
    for side in ("YES", "NO"):
        for per in (1, 2, 3, 4, "H1", "H2"):
            b = cells[(lo, hi, side, per)]
            if b: print(f"  [{lo:.3f},{hi:.3f}) {side:<3} {str(per):<3} {cell(b)}")
