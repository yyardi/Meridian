"""H1b -- EXPLORATORY on CFB (registered for NFL). Decompose mid continuation by
which side of the book moved first, and price the follow-through at what a
TAKER would actually get, not at the mid.

For each minute t with |mid_t - mid_{t-1}| >= 1c:
  ask-led  the ask moved by >= 1c and the bid by < 0.5c  (a seller hit / an offer was pulled)
  bid-led  the bid moved by >= 1c and the ask by < 0.5c
  both     both moved
Then over the next 2 minutes:
  other_side  how much the side that did NOT lead moves in the same direction
  taker_pnl   trade AGAINST the slow side at t (ask-led DOWN move -> sell at the
              stale bid; ask-led UP -> buy at the stale ask; mirrored for bid-led),
              mark at the mid at t+2, minus the fee 0.06*p*(1-p) at the trade price.
If the slow side catches up, other_side > 0 and taker_pnl > 0. The fee is the
whole hurdle: no maker rebate, taker pays. Game-clustered.
"""
import datetime as dt, os, sys
from collections import defaultdict
from sqlalchemy import create_engine, text
LEAGUE = os.environ.get("LEAGUE", "cfb")
eng = create_engine(os.environ["DATABASE_URL"])
with eng.connect() as c:
    c.execute(text("SET max_parallel_workers_per_gather = 0"))
    games = [dict(r._mapping) for r in c.execute(text("""
        SELECT m.venue_game_id, min(p.wall_clock) AS kickoff FROM cfb_game_map m
        JOIN espn_cfb_live_plays p ON p.game_id = m.espn_game_id
        WHERE p.league = :lg AND p.wall_clock IS NOT NULL AND m.venue_game_id IS NOT NULL GROUP BY 1"""), {"lg": LEAGUE})]
    if LEAGUE == "cfb":
        games += [dict(r._mapping) for r in c.execute(text("""
            SELECT m.venue_game_id, min(b.wall_clock) AS kickoff FROM cfb_game_map m
            JOIN espn_cfb_backfill_plays b ON b.game_id = m.espn_game_id
            WHERE b.wall_clock IS NOT NULL AND m.venue_game_id IS NOT NULL
              AND m.espn_game_id NOT IN (SELECT DISTINCT game_id FROM espn_cfb_live_plays WHERE league='cfb') GROUP BY 1"""))]
    vids = sorted({g["venue_game_id"] for g in games})
    lo = min(g["kickoff"] for g in games) - dt.timedelta(minutes=5); hi = max(g["kickoff"] for g in games) + dt.timedelta(hours=4)
    snaps = [dict(r._mapping) for r in c.execute(text("""
        SELECT game_id, market_slug, captured_at, best_bid::float AS bid, best_ask::float AS ask FROM market_snapshots
        WHERE game_id = ANY(:g) AND sports_market_type LIKE '%winner' AND best_bid IS NOT NULL AND best_ask IS NOT NULL
          AND captured_at BETWEEN :lo AND :hi ORDER BY game_id, captured_at"""), {"g": vids, "lo": lo, "hi": hi})]
eng.dispose()
by_g = defaultdict(list)
for s in snaps: by_g[s["game_id"]].append(s)
obs = defaultdict(list)   # kind -> (other_side_follow_c, taker_pnl_c, game)
for g in games:
    rows = by_g.get(g["venue_game_id"], []); ko = g["kickoff"]; end = ko + dt.timedelta(hours=3, minutes=40)
    per = defaultdict(list)
    for s in rows:
        if ko < s["captured_at"] <= end: per[s["market_slug"]].append(s)
    if not per: continue
    rs = max(per.values(), key=len)
    minute = {}
    for s in rs: minute[int((s["captured_at"] - ko).total_seconds() // 60)] = (s["bid"], s["ask"])
    ks = sorted(minute)
    for i in range(1, len(ks) - 2):
        if ks[i] - ks[i-1] != 1 or ks[i] + 2 not in minute: continue
        b0, a0 = minute[ks[i-1]]; b1, a1 = minute[ks[i]]; b2, a2 = minute[ks[i]+2]
        dm = ((b1+a1) - (b0+a0)) / 2
        if abs(dm) < 0.01: continue
        db, da = b1 - b0, a1 - a0
        if abs(da) >= 0.01 and abs(db) < 0.005: kind, lead, slow = "ask-led", da, "bid"
        elif abs(db) >= 0.01 and abs(da) < 0.005: kind, lead, slow = "bid-led", db, "ask"
        else: kind, lead, slow = "both", dm, None
        sgn = 1 if lead > 0 else -1
        if slow == "bid":     # ask moved; the bid is stale. Trade against the bid.
            follow = sgn * (b2 - b1)
            px = b1;  pnl = (sgn * (((b2+a2)/2) - px))          # up-move: buy? no -- against the STALE side:
            # ask-led DOWN (sgn<0): sellers hit; bid is stale HIGH -> SELL at b1, mark at mid2: pnl = b1 - mid2
            # ask-led UP   (sgn>0): offers lifted; bid is stale LOW -> we cannot buy the bid; buy the ask a1, mark mid2
            if sgn < 0: pnl = px - (b2+a2)/2
            else:       px = a1; pnl = (b2+a2)/2 - px
        elif slow == "ask":   # bid moved; the ask is stale
            follow = sgn * (a2 - a1)
            if sgn > 0: px = a1; pnl = (b2+a2)/2 - px            # bid-led UP: ask stale LOW -> BUY at a1
            else:       px = b1; pnl = px - (b2+a2)/2            # bid-led DOWN: ask stale HIGH -> cannot sell the ask; sell bid b1
        else:
            follow = sgn * (((b2+a2)/2) - ((b1+a1)/2)); px = a1 if sgn > 0 else b1
            pnl = ((b2+a2)/2 - px) if sgn > 0 else (px - (b2+a2)/2)
        fee = 0.06 * px * (1 - px)
        obs[kind].append((100*follow, 100*(pnl - fee), 100*pnl, g["venue_game_id"], abs(dm)))
def clustered(vals, keys):
    n=len(vals); m=sum(vals)/n; res=defaultdict(float); size=defaultdict(int)
    for v,k in zip(vals,keys): res[k]+=v-m; size[k]+=1
    G=len(res); se=(sum(x*x for x in res.values())**0.5)/n*(G/(G-1))**0.5 if G>1 else 0
    return m,1.96*se,n,G
print(f"LEAGUE={LEAGUE}  games {len(games)}  (EXPLORATORY on CFB; registered H1b for NFL)")
print(f"\n=== who moved first, and did the other side follow within 2 min? ===")
print(f"  {'kind':<9}{'n':>6}{'G':>4}   {'other side follows':>19}{'95% CI':>18}   {'taker vs slow side, GROSS':>26}   {'NET of 0.06p(1-p) fee':>24}")
for kind in ("ask-led", "bid-led", "both"):
    ob = obs[kind]
    if len(ob) < 40: print(f"  {kind:<9}{len(ob):>6}  too few"); continue
    f,fh,n,G = clustered([o[0] for o in ob],[o[3] for o in ob]); gp,gh,_,_ = clustered([o[2] for o in ob],[o[3] for o in ob]); np_,nh,_,_ = clustered([o[1] for o in ob],[o[3] for o in ob])
    print(f"  {kind:<9}{n:>6}{G:>4}   {f:>+18.2f}c   [{f-fh:+.2f}, {f+fh:+.2f}]   {gp:>+13.2f}c [{gp-gh:+.2f}, {gp+gh:+.2f}]   {np_:>+11.2f}c [{np_-nh:+.2f}, {np_+nh:+.2f}]  {'CLEARS FEE' if np_-nh > 0 else ('spans 0' if np_+nh > 0 else 'loses')}")
print("\n  'other side follows' > 0 = the stale side catches up (the continuation is a stale quote).")
print("  'taker vs slow side' = hit/lift the stale quote at t, mark at mid t+2. NET must exclude zero to count -- and it is one venue, one sport, exploratory.")
