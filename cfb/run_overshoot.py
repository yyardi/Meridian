"""In-game OVERSHOOT on the venue's own winner market, from our tape.

The one regularity that survived the season so far: on Kalshi, after a >=1c
one-minute move, ~6% of the shock reverts within two minutes, in three size
strata, each excluding zero (49 NFL preseason games; CFB replication pending).
This runs the IDENTICAL statistic on Polymarket US from market_snapshots, so
the venue we can actually quote on gets its own number -- and adds the one
thing Kalshi could not answer: whether the reversal clears HALF THE SPREAD, the
maker's whole cost on a venue with no maker fee (findings.md C7).

PRE-REGISTERED (docs/math/e8-nfl-preregistration.md, H1), fixed before any NFL
tape exists: 1-minute mids (last snapshot per minute), kickoff -> +3h40m, one
winner market per game; |jump| >= 1c; continuation at h = 1, 2, 5 min; strata
>= 1c / 2c / 3c at h = 2; game-clustered. GATE: the >= 2c stratum's reversal
excludes zero AND exceeds the mean half-spread at the shock. Nothing else.

LEAGUE=cfb runs it on the covered CFB games now; LEAGUE=nfl on Thursday.
"""
import bisect, datetime as dt, os, sys
from collections import defaultdict
from sqlalchemy import create_engine, text

LEAGUE = os.environ.get("LEAGUE", "cfb")
eng = create_engine(os.environ["DATABASE_URL"])

# The postgres container's /dev/shm is 64MB (Docker default). Parallel workers
# put dynamic shared memory there, and the second-phase queries died with
# "could not resize shared memory segment ... No space left on device" on
# 2026-09-11 once the tape grew. Session-scoped, no config change.
from sqlalchemy import event  # noqa: E402
@event.listens_for(eng, "connect")
def _no_parallel_workers(dbapi_conn, _rec):
    # psycopg3 opens a transaction on the first execute; an uncommitted SET is
    # undone by the pool's first ROLLBACK. Commit it so it is session-wide.
    cur = dbapi_conn.cursor(); cur.execute("SET max_parallel_workers_per_gather = 0"); cur.close()
    dbapi_conn.commit()
with eng.connect() as c:
    c.execute(text("SET max_parallel_workers_per_gather = 0"))
    # kickoff per venue game = first play wall_clock (ESPN), via the map
    games = [dict(r._mapping) for r in c.execute(text("""
        SELECT m.venue_game_id, m.espn_game_id, min(p.wall_clock) AS kickoff
        FROM cfb_game_map m JOIN espn_cfb_live_plays p ON p.game_id = m.espn_game_id
        WHERE p.league = :lg AND p.wall_clock IS NOT NULL AND m.venue_game_id IS NOT NULL
        GROUP BY 1, 2"""), {"lg": LEAGUE})]
    if LEAGUE == "cfb":   # backfill games too
        games += [dict(r._mapping) for r in c.execute(text("""
            SELECT m.venue_game_id, m.espn_game_id, min(b.wall_clock) AS kickoff
            FROM cfb_game_map m JOIN espn_cfb_backfill_plays b ON b.game_id = m.espn_game_id
            WHERE b.wall_clock IS NOT NULL AND m.venue_game_id IS NOT NULL
              AND m.espn_game_id NOT IN (SELECT DISTINCT game_id FROM espn_cfb_live_plays WHERE league='cfb')
            GROUP BY 1, 2"""))]
    vids = sorted({g["venue_game_id"] for g in games})
    lo = min(g["kickoff"] for g in games) - dt.timedelta(minutes=5)
    hi = max(g["kickoff"] for g in games) + dt.timedelta(hours=4)
    snaps = [dict(r._mapping) for r in c.execute(text("""
        SELECT game_id, market_slug, captured_at, best_bid::float AS bid, best_ask::float AS ask
        FROM market_snapshots
        WHERE game_id = ANY(:g) AND sports_market_type LIKE '%winner'
          AND best_bid IS NOT NULL AND best_ask IS NOT NULL AND captured_at BETWEEN :lo AND :hi
        ORDER BY game_id, captured_at"""), {"g": vids, "lo": lo, "hi": hi})]
eng.dispose()
print(f"LEAGUE={LEAGUE}: games {len(games)}   winner snapshots {len(snaps):,}")

by_g = defaultdict(list)
for s in snaps: by_g[s["game_id"]].append(s)
drift = {1: [], 2: [], 5: []}; halfsp = []; used = 0; thin = 0
for g in games:
    rows = by_g.get(g["venue_game_id"], [])
    if not rows: continue
    ko = g["kickoff"]; end = ko + dt.timedelta(hours=3, minutes=40)
    # one market per game: the slug with the most in-window snapshots
    per = defaultdict(list)
    for s in rows:
        if ko < s["captured_at"] <= end: per[s["market_slug"]].append(s)
    if not per: continue
    slug, rs = max(per.items(), key=lambda kv: len(kv[1]))
    # last snapshot per minute -> 1-min mid and half-spread series
    minute = {}
    for s in rs:
        k = int((s["captured_at"] - ko).total_seconds() // 60)
        minute[k] = ((s["bid"] + s["ask"]) / 2, (s["ask"] - s["bid"]) / 2)
    ks = sorted(minute)
    if len(ks) < 60: thin += 1; continue
    used += 1
    # walk consecutive minutes only (a gap in the tape is not a "move")
    for i in range(1, len(ks) - 5):
        if ks[i] - ks[i-1] != 1: continue
        j = minute[ks[i]][0] - minute[ks[i-1]][0]
        if abs(j) < 0.01: continue
        for h in (1, 2, 5):
            if ks[i] + h in minute:
                drift[h].append((j, minute[ks[i]+h][0] - minute[ks[i]][0], g["venue_game_id"]))
        if ks[i] + 2 in minute:
            halfsp.append((abs(j), (minute[ks[i]][1] + minute[ks[i]+2][1]) / 2, g["venue_game_id"]))
print(f"games with >=60 in-game minutes on tape: {used}   too thin: {thin}   (Kalshi comparison: 49 NFL pre / 209 CFB)")

def clustered(vals, keys):
    n = len(vals); m = sum(vals)/n
    res, size = defaultdict(float), defaultdict(int)
    for v, k in zip(vals, keys): res[k] += v-m; size[k] += 1
    G = len(res); ge = n*n/sum(c*c for c in size.values())
    # G=1: the sandwich SE is zero by construction. Return an infinite half-width
    # so no downstream label can read a single game as a measurement.
    se = (sum(x*x for x in res.values())**0.5)/n*(G/(G-1))**0.5 if G > 1 else float("inf")
    return m, 1.96*se, n, G, ge
def slope_clustered(x, y, keys):
    n = len(x); mx, my = sum(x)/n, sum(y)/n
    sxx = sum((a-mx)**2 for a in x); b = sum((a-mx)*(c-my) for a, c in zip(x, y))/sxx
    e = [c - my - b*(a-mx) for a, c in zip(x, y)]
    g = defaultdict(float)
    for a, ei, k in zip(x, e, keys): g[k] += (a-mx)*ei
    G = len(g)
    se = (sum(v*v for v in g.values())**0.5)/sxx*(G/(G-1))**0.5 if G > 1 else float("inf")
    return b, 1.96*se, G

print(f"\n=== POLYMARKET US in-game, after a >=1c one-minute move ===")
print(f"  {'h(min)':>7}{'n':>8}{'beta':>9}{'95% CI':>20}{'G':>5}   {'continuation c':>15}{'95% CI':>18}")
for h in (1, 2, 5):
    ob = drift[h]
    if len(ob) < 50: print(f"  {h:>7}{len(ob):>8}  too few"); continue
    b, hb, G = slope_clustered([j for j,_,_ in ob], [d for _,d,_ in ob], [g for _,_,g in ob])
    cont, hc, n, G2, ge = clustered([100*(d if j > 0 else -d) for j,d,g in ob], [g for _,_,g in ob])
    print(f"  {h:>7}{n:>8,}{b:>+9.3f}   [{b-hb:+.3f}, {b+hb:+.3f}]{G:>5}   {cont:>+14.2f}c   [{cont-hc:+.2f}, {cont+hc:+.2f}]   {'NO INTERVAL (G=1)' if G < 2 else ('CONTINUES' if b-hb > 0 else ('REVERTS' if b+hb < 0 else 'spans zero'))}")
print(f"\n=== OVERSHOOT by shock size at h=2, and the GATE: does it clear half the spread? ===")
print(f"  {'|jump| >=':>10}{'n':>7}{'G':>5}   {'reversal@2min':>14}{'95% CI':>18}   {'% jump':>7}   {'half-spread':>12}   gate")
for thr in (0.01, 0.02, 0.03):
    ob = [(j, d, g) for j, d, g in drift[2] if abs(j) >= thr]
    hs = [(h_, g) for aj, h_, g in halfsp if aj >= thr]
    if len(ob) < 50: print(f"  {100*thr:>9.0f}c{len(ob):>7}  too few"); continue
    cont, hc, n, G, ge = clustered([100*(d if j > 0 else -d) for j,d,g in ob], [g for _,_,g in ob])
    mj = sum(abs(j) for j,_,_ in ob)/n
    hsm = 100*sum(h_ for h_,_ in hs)/len(hs) if hs else float("nan")
    gate = ("NO INTERVAL (G=1)" if G < 2 else
            "PASS" if (cont - hc < 0 and -cont > hsm) else ("excludes 0, under half-spread" if cont + hc < 0 else "spans zero"))
    print(f"  {100*thr:>9.0f}c{n:>7,}{G:>5}   {cont:>+13.2f}c   [{cont-hc:+.2f}, {cont+hc:+.2f}]   {cont/mj:>+6.1f}%   {hsm:>11.2f}c   {gate}")
print("\n  GATE (pre-registered): the >=2c stratum reverts, excludes zero, and |reversal| > mean half-spread.")
print("  A maker fading the move earns the reversal and pays the half-spread to be there; maker fee is 0 on this venue.")
