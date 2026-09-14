"""The conditional move after a drive crosses midfield. No rule, no fees, no P&L.

Registered in docs/math/drive-move-preregistration.md before any outcome was read.

WHY THIS AND NOT THE SCALP. cfb/run_momentum_scalp.py already measures the operator's rule
end to end: 27 of 27 cells -7.2 to -11.0c, drift ~0, loss entirely half-spreads plus two
taker fees. That drift is a per-cell MEAN. A take-profit/stop-loss pair has an ASYMMETRIC
payoff, so what it earns depends on the SHAPE of the conditional move, not its first moment,
and nothing in the project measures the shape. A symmetric thin-tailed move kills every grid
corner structurally; a skewed one could pay at zero mean.

THREE ARMS, one side convention, so the comparison is a comparison:
  MIDFIELD  first play of a drive with yards_to_goal < 50   <- the operator's trigger
  OWN HALF  first play of a drive with yards_to_goal >= 50  <- baseline, must also centre on 0
  SCORING   plays with scoring_play = true                  <- POSITIVE CONTROL, must move

★ THE POSITIVE CONTROL IS THE POINT. A drift measured against zero proves only that the
instrument is not broken: an efficient mid is a martingale, so ANY conditional set gives zero
and a null is uninformative on its own. If SCORING is flat, this measurement cannot detect a
real conditional move and no null from MIDFIELD means anything.

Side is the POSSESSING team's: offence away -> YES mid, offence home -> 1 - YES mid. YES is
the away team on every slug. Horizons take the last tick at or before anchor + h.

RUN prod read-only, env flags INSIDE docker run:
  ssh ubuntu@$SRV 'sudo -n docker run --rm -i --network meridian_default -e DATABASE_URL=... \
    -e LEAGUE=cfb -v /opt/meridian/core:/app/core -w /app <api image> python -' < this
Nothing is placed.
"""
import datetime as dt, os, statistics as st, sys
from bisect import bisect_left, bisect_right
from collections import defaultdict

from sqlalchemy import create_engine, event, text

LG = os.environ.get("LEAGUE", "cfb")
HORIZONS = (30, 60, 120, 300)
EXCURSIONS = (2.0, 5.0, 10.0)     # cents; the operator's grid is 1-10c
BAD = ("timeout", "kickoff", "end period", "end of", "two-minute", "warning")
sys.stdout.reconfigure(line_buffering=True)
eng = create_engine(os.environ["DATABASE_URL"])
@event.listens_for(eng, "connect")
def _np(c, _r):
    cur = c.cursor(); cur.execute("SET max_parallel_workers_per_gather = 0"); cur.close(); c.commit()

Q_GAMES = """SELECT p.game_id eg, m.venue_game_id vg, m.home_espn_team_id mh,
       m.away_espn_team_id ma, min(p.home) ph, min(p.away) pa, max(p.wall_clock) t1
FROM espn_cfb_live_plays p JOIN cfb_game_map m ON m.espn_game_id = p.game_id
WHERE p.league = :lg AND m.venue_game_id IS NOT NULL AND p.wall_clock IS NOT NULL
GROUP BY 1,2,3,4 ORDER BY min(p.wall_clock)"""
Q_PLAYS = """SELECT wall_clock wc, period, is_overtime ot, down, yards_to_goal ytg,
  pos_team pos, drive_id drv, coalesce(play_type,'') pt, coalesce(scoring_play,false) sc
FROM espn_cfb_live_plays WHERE game_id = :eg AND league = :lg AND wall_clock IS NOT NULL
ORDER BY wall_clock, id"""
Q_TICKS = """SELECT captured_at t, best_bid::float b, best_ask::float a FROM market_snapshots
WHERE game_id = :vg AND sports_market_type = 'football_team_full_game_winner'
  AND captured_at BETWEEN :lo AND :hi AND best_bid > 0 AND best_ask < 1
  AND best_ask >= best_bid ORDER BY captured_at"""


def clustered(vals, keys):                        # verbatim from cfb/run_paper_book.py
    n = len(vals); m = sum(vals) / n
    res, size = defaultdict(float), defaultdict(int)
    for v, k in zip(vals, keys): res[k] += v - m; size[k] += 1
    G = len(res); ge = n * n / sum(c * c for c in size.values())
    se = (sum(x * x for x in res.values()) ** 0.5) / n * (G / (G - 1)) ** 0.5 if G > 1 else float("inf")
    return m, 1.96 * se, n, G, ge


def pct(xs, q): xs = sorted(xs); return xs[min(len(xs) - 1, int(q * len(xs)))]


C, ARMS = defaultdict(int), defaultdict(lambda: defaultdict(list))
with eng.connect() as c:
    games = [dict(r._mapping) for r in c.execute(text(Q_GAMES), {"lg": LG})]
    for g in games:
        C["games in plays+map"] += 1
        if g["ph"] != g["mh"] or g["pa"] != g["ma"]: C["TRAP orientation"] += 1; continue
        plays = [dict(r._mapping) for r in c.execute(text(Q_PLAYS), {"eg": g["eg"], "lg": LG})]
        if not plays: continue
        f0 = plays[0]["wc"]
        P = [p for p in plays if p["down"] and 1 <= p["down"] <= 4 and p["ytg"]
             and 1 <= p["ytg"] <= 99 and p["period"] and 1 <= p["period"] <= 4 and not p["ot"]
             and not any(b in p["pt"].lower() for b in BAD)
             and p["wc"] < f0 + dt.timedelta(hours=5)]
        if len(P) < 40: C["skipped: <40 usable plays"] += 1; continue
        rows = c.execute(text(Q_TICKS), {"vg": g["vg"], "lo": P[0]["wc"],
                                         "hi": P[-1]["wc"] + dt.timedelta(minutes=10)}).fetchall()
        if len(rows) < 50: C["skipped: no winner tape"] += 1; continue
        C["games scored"] += 1
        if C["games scored"] % 25 == 0: print(f"  ... {C['games scored']} games")
        T = [r[0] for r in rows]
        M = [round((r[1] + r[2]) / 2, 4) for r in rows]
        seen = set()
        for p in P:
            if p["pos"] == g["pa"]: flip = False
            elif p["pos"] == g["ph"]: flip = True
            else: C["play dropped: offence not home/away id"] += 1; continue
            arms = []
            if p["sc"]: arms.append("SCORING")
            key = (p["drv"], p["ytg"] < 50)
            if key not in seen:
                seen.add(key)
                arms.append("MIDFIELD" if p["ytg"] < 50 else "OWN HALF")
            if not arms: continue
            i = bisect_right(T, p["wc"])                 # first tick STRICTLY after the play
            if i >= len(T): C["no tick after play"] += 1; continue
            m0 = (1 - M[i]) if flip else M[i]
            for arm in arms:
                C[f"{arm} anchors"] += 1
                for h in HORIZONS:
                    j = bisect_right(T, T[i] + dt.timedelta(seconds=h)) - 1
                    if j <= i: continue
                    mt = (1 - M[j]) if flip else M[j]
                    # EXCURSIONS, not just the endpoint: a take-profit/stop-loss rule fires on
                    # a TOUCH. The operator remembers a case that worked, so the question is
                    # whether the favourable touch is more common than the adverse one -- if
                    # they are equal, memorable cases exist both ways and only one is recalled.
                    path = [((1 - M[q]) if flip else M[q]) - m0 for q in range(i + 1, j + 1)]
                    mfe, mae = max(path) * 100, min(path) * 100
                    ARMS[(arm, h)][0].append(((mt - m0) * 100, g["eg"], mfe, mae))

print(f"\nLEAGUE={LG}  {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M}Z")
for k in sorted(C): print(f"  {k}: {C[k]}")
print("\nCONDITIONAL MOVE ON THE POSSESSING TEAM'S SIDE, cents. No rule, no fees, no spread.")
print("SCORING is the POSITIVE CONTROL: if it is flat, no null here means anything.\n")
print(f"  {'arm':9} {'h':>5} {'mean [95% game-clustered]':>28} {'med':>6} {'sd':>6} "
      f"{'p10':>6} {'p90':>6} {'>0':>6} {'E[+]':>6} {'E[-]':>6} {'n':>6} {'G':>4} {'G_eff':>6}")
for arm in ("MIDFIELD", "OWN HALF", "SCORING"):
    for h in HORIZONS:
        d = ARMS[(arm, h)][0]
        if len(d) < 5: continue
        v = [x for x, _, _, _ in d]
        m, hw, n, G, ge = clustered(v, [k for _, k, _, _ in d])
        pos = [x for x in v if x > 0]; neg = [x for x in v if x < 0]
        print(f"  {arm:9} {h:>4}s {m:+8.3f} [{m-hw:+7.3f},{m+hw:+7.3f}] {st.median(v):>6.2f} "
              f"{st.pstdev(v):>6.2f} {pct(v,0.10):>6.2f} {pct(v,0.90):>6.2f} "
              f"{len(pos)/n:>5.1%} {(st.mean(pos) if pos else 0):>6.2f} "
              f"{(st.mean(neg) if neg else 0):>6.2f} {n:>6,} {G:>4} {ge:>6.1f}"
              + ("  UNDERPOWERED" if G < 25 else ""))
print("\n  E[+] and E[-] are the means of the positive and negative halves. An asymmetric")
print("  take-profit/stop-loss payoff cares about those two numbers, not about their sum.\n")

print("★ EXCURSIONS: the fraction of triggers whose mid TOUCHED +/-x cents inside the")
print("  horizon, which is what a take-profit or a stop-loss actually fires on. The")
print("  operator remembers a case that worked; if fav and adv are close to equal, the")
print("  memorable cases exist in BOTH directions and only one kind gets recalled.\n")
print(f"  {'arm':9} {'h':>5} " + " ".join(f"{'+'+str(int(x))+'c':>7} {'-'+str(int(x))+'c':>7} {'ratio':>6}"
                                          for x in EXCURSIONS) + f" {'n':>6}")
for arm in ("MIDFIELD", "OWN HALF", "SCORING"):
    for h in HORIZONS:
        d = ARMS[(arm, h)][0]
        if len(d) < 5: continue
        n = len(d); cells = []
        for x in EXCURSIONS:
            fav = sum(1 for _, _, mfe, _ in d if mfe >= x) / n
            adv = sum(1 for _, _, _, mae in d if mae <= -x) / n
            cells.append(f"{fav:>6.1%} {adv:>7.1%} {(fav/adv if adv else float('inf')):>6.2f}")
        print(f"  {arm:9} {h:>4}s " + " ".join(cells) + f" {n:>6,}")
