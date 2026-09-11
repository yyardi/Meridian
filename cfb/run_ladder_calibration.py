"""Pregame ladder calibration: is any rung of the venue's football ladders soft?

The well-known test, run broadly and model-free. For every full-game spread,
total, team-total and winner market on a settled CFB/NFL game: the LAST quote
before kickoff (kickoff = the first ESPN play's wall clock when we have plays,
else the venue's game_start_time, and the two are compared where both exist),
settled from ESPN finals under the venue's frames:

    winner      YES = the slug's first team (away) wins
    spread      YES = (away - home) + line > 0          (196/196 in the tape)
    total       YES = home + away > line
    team total  YES = that team's points > line         (tt-<team> names the side)

Frames are cross-checked against the venue's own settlement endpoint on a sample
by the caller (public, unauthenticated) -- a derived settlement is a claim.

Reported per market type x pregame-mid bucket: n markets, G games, the
calibration gap E[settle - mid] in cents with a game-clustered 95% interval,
and the TAKER P&L of buying YES at the ask and of buying NO at 1-bid, each net
of the 0.06*p*(1-p) fee. Both sides are printed for every bucket; nothing is
selected on the outcome. EXPLORATORY: nothing here is pre-registered. A bucket
whose taker P&L is positive, excludes zero, G >= 25, and clears fee + half
spread is a HYPOTHESIS for the next weekend's games, which are held out.

    ssh ubuntu@$H "$D meridian-trainer python3 -" < cfb/run_ladder_calibration.py
"""
import datetime as dt
import os
import sys
from collections import defaultdict

from sqlalchemy import create_engine, event, text

FEE = 0.06
TYPES = ("football_team_full_game_winner", "football_team_full_game_spread",
         "football_team_full_game_total", "football_team_points_full_game_total")
SHORT = {"football_team_full_game_winner": "winner", "football_team_full_game_spread": "spread",
         "football_team_full_game_total": "total", "football_team_points_full_game_total": "team_tot"}

eng = create_engine(os.environ["DATABASE_URL"])
@event.listens_for(eng, "connect")
def _np(dbapi_conn, _rec):
    cur = dbapi_conn.cursor(); cur.execute("SET max_parallel_workers_per_gather = 0"); cur.close(); dbapi_conn.commit()

# Settled games with a venue id: finals from backfill (CFB) or the last live
# game_state row (CFB live-only + NFL); kickoff from the first play if any.
GAMES_SQL = """
WITH bf AS (
  SELECT g.game_id eg, g.home_score h, g.away_score a, 'cfb' lg
  FROM espn_cfb_backfill_games g WHERE g.home_score IS NOT NULL AND g.away_score IS NOT NULL),
lv AS (
  SELECT DISTINCT ON (game_id) game_id eg, home_score h, away_score a, league lg
  FROM espn_cfb_game_state WHERE home_score IS NOT NULL AND league IN ('cfb','nfl')
    AND period >= 4
  ORDER BY game_id, first_seen_at DESC),
fin AS (SELECT * FROM bf UNION ALL SELECT * FROM lv WHERE eg NOT IN (SELECT eg FROM bf)),
ko AS (
  SELECT game_id eg, min(wall_clock) ko FROM espn_cfb_backfill_plays WHERE wall_clock IS NOT NULL GROUP BY 1
  UNION ALL
  SELECT game_id, min(wall_clock) FROM espn_cfb_live_plays WHERE wall_clock IS NOT NULL
    AND game_id NOT IN (SELECT game_id FROM espn_cfb_backfill_plays WHERE wall_clock IS NOT NULL) GROUP BY 1)
SELECT m.venue_game_id vg, m.espn_game_id eg, m.event_slug, f.h, f.a, f.lg, k.ko
FROM cfb_game_map m JOIN fin f ON f.eg = m.espn_game_id
LEFT JOIN ko k ON k.eg = m.espn_game_id
WHERE m.venue_game_id IS NOT NULL
"""

# Last pregame quote per market for ONE game (bounded window, DISTINCT ON).
CLOSE_SQL = """
SELECT DISTINCT ON (market_slug) market_slug, sports_market_type, line::float line,
       best_bid::float bid, best_ask::float ask, captured_at, game_start_time
FROM market_snapshots
WHERE game_id = :vg AND captured_at BETWEEN :lo AND :ko
  AND best_bid IS NOT NULL AND best_ask IS NOT NULL
  AND sports_market_type = ANY(:types)
ORDER BY market_slug, captured_at DESC
"""
START_SQL = """
SELECT min(game_start_time) FROM market_snapshots
WHERE game_id = :vg AND captured_at > now() - interval '60 days' AND game_start_time IS NOT NULL
"""

def settle(slug, mtype, line, h, a):
    """Derived settlement under the venue's frames; None = push / undecidable."""
    if mtype == "football_team_full_game_winner":
        return None if a == h else int(a > h)
    if line is None:
        return None
    if mtype == "football_team_full_game_spread":
        v = (a - h) + line
        return None if abs(v) < 1e-9 else int(v > 0)
    if mtype == "football_team_full_game_total":
        v = (h + a) - line
        return None if abs(v) < 1e-9 else int(v > 0)
    if mtype == "football_team_points_full_game_total":
        toks = slug.split("-")
        try:
            i = toks.index("tt")
        except ValueError:
            return None
        team = toks[i + 1]
        pts = a if team == toks[2] else (h if team == toks[3] else None)
        if pts is None:
            return None
        v = pts - line
        return None if abs(v) < 1e-9 else int(v > 0)
    return None


def clustered(vals, keys):
    n = len(vals); m = sum(vals) / n
    res, size = defaultdict(float), defaultdict(int)
    for v, k in zip(vals, keys): res[k] += v - m; size[k] += 1
    G = len(res); ge = n * n / sum(c * c for c in size.values())
    se = (sum(x * x for x in res.values()) ** 0.5) / n * (G / (G - 1)) ** 0.5 if G > 1 else float("inf")
    return m, 1.96 * se, n, G, ge


with eng.connect() as c:
    games = [dict(r._mapping) for r in c.execute(text(GAMES_SQL))]
    rows, ko_gap, no_ko, no_start = [], [], 0, 0
    for g in games:
        start = c.execute(text(START_SQL), {"vg": g["vg"]}).scalar()
        ko = g["ko"]
        if ko is not None and start is not None:
            ko_gap.append(abs((ko - start).total_seconds()) / 60)
        if ko is None:
            if start is None:
                no_start += 1; continue
            no_ko += 1; ko = start
        q = c.execute(text(CLOSE_SQL), {"vg": g["vg"], "lo": ko - dt.timedelta(days=3), "ko": ko,
                                        "types": list(TYPES)})
        for r in q:
            r = dict(r._mapping)
            y = settle(r["market_slug"], r["sports_market_type"], r["line"], g["h"], g["a"])
            if y is None:
                continue
            r.update(vg=g["vg"], lg=g["lg"], y=y, ttk_min=(ko - r["captured_at"]).total_seconds() / 60,
                     event_slug=g["event_slug"])
            rows.append(r)

print(f"settled mapped games {len(games)}  (kickoff from plays for {len(games) - no_ko - no_start}, "
      f"from venue start time for {no_ko}, neither {no_start})")
if ko_gap:
    ko_gap.sort()
    print(f"ESPN first play vs venue game_start_time, minutes: median {ko_gap[len(ko_gap)//2]:.0f}  "
          f"p90 {ko_gap[int(len(ko_gap)*0.9)]:.0f}  max {ko_gap[-1]:.0f}")
print(f"markets with a pregame close and a derived settlement: {len(rows):,}")
by_lg = defaultdict(set)
for r in rows: by_lg[r["lg"]].add(r["vg"])
print("  games by league: " + "  ".join(f"{k} {len(v)}" for k, v in sorted(by_lg.items())))

def bucket(mid):
    return min(int(mid * 10), 9)

def report(title, sel, key=lambda r: bucket((r["bid"] + r["ask"]) / 2), labels=None):
    print(f"\n=== {title} ===")
    print(f"  {'bucket':<10}{'n':>6}{'G':>5}{'G_eff':>7}   {'gap E[y-mid] c':>16}{'95% CI':>18}   "
          f"{'buy YES @ask net':>17}{'95% CI':>18}   {'buy NO @1-bid net':>18}{'95% CI':>18}   {'half-sprd':>9}")
    groups = defaultdict(list)
    for r in sel: groups[key(r)].append(r)
    for k in sorted(groups):
        rs = groups[k]
        if len(rs) < 20:
            print(f"  {str(labels[k] if labels else k):<10}{len(rs):>6}   too few"); continue
        keys = [r["vg"] for r in rs]
        gap, gh, n, G, ge = clustered([100 * (r["y"] - (r["bid"] + r["ask"]) / 2) for r in rs], keys)
        by, byh, *_ = clustered([100 * (r["y"] - r["ask"] - FEE * r["ask"] * (1 - r["ask"])) for r in rs], keys)
        bn, bnh, *_ = clustered([100 * ((1 - r["y"]) - (1 - r["bid"]) - FEE * r["bid"] * (1 - r["bid"])) for r in rs], keys)
        hs = 100 * sum((r["ask"] - r["bid"]) / 2 for r in rs) / n
        lab = str(labels[k] if labels else k)
        flag = ""
        if G >= 25 and ((by - byh > 0) or (bn - bnh > 0)):
            flag = "  <- positive taker side, excludes 0: HYPOTHESIS for the held-out weekend"
        print(f"  {lab:<10}{n:>6}{G:>5}{ge:>7.1f}   {gap:>+16.2f}{'[%+.2f, %+.2f]' % (gap-gh, gap+gh):>18}   "
              f"{by:>+17.2f}{'[%+.2f, %+.2f]' % (by-byh, by+byh):>18}   "
              f"{bn:>+18.2f}{'[%+.2f, %+.2f]' % (bn-bnh, bn+bnh):>18}   {hs:>9.2f}{flag}")

BL = {i: f"{i/10:.1f}-{(i+1)/10:.1f}" for i in range(10)}
close = [r for r in rows if r["ttk_min"] <= 360]
print(f"\nPRIMARY population: last quote within 6h of kickoff: {len(close):,} markets "
      f"(all pregame quotes within 3 days: {len(rows):,})")
for t in TYPES:
    sel = [r for r in close if r["sports_market_type"] == t]
    report(f"{SHORT[t]} -- by pregame mid, close within 6h of kickoff", sel, labels=BL)
# distance from the line for spreads (rung far from the market's own centre = the venue's 'longshots')
sp = [r for r in close if r["sports_market_type"] == "football_team_full_game_spread"]
centre = defaultdict(list)
for r in sp: centre[r["vg"]].append(r)
def dist_key(r):
    rs = centre[r["vg"]]
    # the rung whose mid is nearest 0.5 is the market's centre; distance in points
    c0 = min(rs, key=lambda x: abs((x["bid"] + x["ask"]) / 2 - 0.5))
    d = abs(r["line"] - c0["line"])
    return 0 if d < 3.5 else 1 if d < 7.5 else 2 if d < 14.5 else 3
report("spread -- by distance from the centre rung (points)", sp, key=dist_key,
       labels={0: "<3.5", 1: "3.5-7", 2: "7.5-14", 3: ">14"})
for lg in ("cfb", "nfl"):
    sel = [r for r in close if r["lg"] == lg and r["sports_market_type"] == "football_team_full_game_spread"]
    report(f"spread, {lg} only -- by pregame mid", sel, labels=BL)

print("\n=== WHAT THIS CANNOT SAY ===")
print("  Exploratory, no pre-registration; every bucket is one of ~40 looks. A flagged bucket is a")
print("  hypothesis to write down BEFORE Saturday's 44 CFB / Sunday's 12 NFL closes, then read there.")
print("  Settlement is DERIVED from ESPN finals under the venue's frames; the caller spot-checks it")
print("  against the venue's settlement endpoint before any number travels.")
print("\n### CSV")
print("lg,vg,event_slug,type,slug,line,bid,ask,ttk_min,y")
for r in rows:
    print(f"{r['lg']},{r['vg']},{r['event_slug']},{SHORT[r['sports_market_type']]},{r['market_slug']},"
          f"{'' if r['line'] is None else r['line']},{r['bid']},{r['ask']},{r['ttk_min']:.0f},{r['y']}")
