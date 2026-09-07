"""Between-play drift: does the venue keep moving after it has moved?

The research report's one speed-independent edge hypothesis: prediction-market
prices on news "move only ~64% of the way at first and take ~80 minutes to
finish". If the same underreaction exists between football plays, a follower
with a 30s lag still has something to buy, because the price it sees has not
finished moving. This measures that directly, with no model in the loop.

PRE-SPECIFIED, one pass, no search:
  pre    mid at the last snapshot BEFORE the play (wall_clock)
  obs    mid at the first snapshot >= wall_clock + 30s   (what a lagged follower sees)
  later  mid at the first snapshot >= obs_time + h, h in {30, 60, 120, 300}s,
         ONLY if the next play has not yet happened (else the horizon is
         contaminated by new information and is dropped, counted)
  jump   obs - pre        the move we observe
  drift  later - obs      what happens next, inside the dead window
Statistic: slope of drift on jump (game-clustered), and mean continuation
sign(jump)*drift in cents, restricted to |jump| >= 1c so a tick of noise is
not a "move". beta > 0 continuation (underreaction), < 0 reversal, ~0 efficient.
Also the fraction of the eventual move realised by obs: jump / (later - pre).

Winner markets only: densest ticks (0.5c median spread, ~115k snapshots).
"""
import bisect, datetime as dt, os, sys
from collections import defaultdict
from sqlalchemy import create_engine, text

LAG, HORIZONS, MIN_JUMP = 30, (30, 60, 120, 300), 0.01
eng = create_engine(os.environ["DATABASE_URL"])
with eng.connect() as c:
    c.execute(text("SET max_parallel_workers_per_gather = 0"))
    plays = [dict(r._mapping) for r in c.execute(text("""
        WITH bf AS (SELECT b.game_id, b.wall_clock, m.venue_game_id FROM espn_cfb_backfill_plays b
                    JOIN cfb_game_map m ON m.espn_game_id=b.game_id AND m.venue_game_id IS NOT NULL
                    WHERE b.wall_clock IS NOT NULL AND NOT b.is_overtime),
             lv AS (SELECT p.game_id, p.wall_clock, m.venue_game_id FROM espn_cfb_live_plays p
                    JOIN cfb_game_map m ON m.espn_game_id=p.game_id AND m.venue_game_id IS NOT NULL
                    WHERE p.league='cfb' AND p.wall_clock IS NOT NULL AND NOT p.is_overtime
                      AND p.game_id NOT IN (SELECT game_id FROM espn_cfb_backfill_plays))
        SELECT * FROM bf UNION ALL SELECT * FROM lv ORDER BY game_id, wall_clock"""))]
    vids = sorted({p["venue_game_id"] for p in plays})
    lo = min(p["wall_clock"] for p in plays) - dt.timedelta(minutes=10)
    hi = max(p["wall_clock"] for p in plays) + dt.timedelta(minutes=15)
    snaps = [dict(r._mapping) for r in c.execute(text("""
        SELECT game_id, captured_at, (best_bid+best_ask)::float/2 AS mid FROM market_snapshots
        WHERE game_id = ANY(:g) AND sports_market_type LIKE '%winner' AND best_bid IS NOT NULL AND best_ask IS NOT NULL
          AND captured_at BETWEEN :lo AND :hi ORDER BY game_id, captured_at"""), {"g": vids, "lo": lo, "hi": hi})]
eng.dispose()
print(f"plays {len(plays):,} / games {len({p['game_id'] for p in plays})}   winner snapshots {len(snaps):,}")

tape = defaultdict(lambda: ([], []))
for s in snaps:
    ts, ms = tape[s["game_id"]]; ts.append(s["captured_at"]); ms.append(s["mid"])
def mid_before(vg, t):
    ts, ms = tape[vg]; i = bisect.bisect_left(ts, t) - 1
    return ms[i] if i >= 0 and (t - ts[i]).total_seconds() <= 300 else None
def mid_at_or_after(vg, t, within=120):
    ts, ms = tape[vg]; i = bisect.bisect_left(ts, t)
    return ms[i] if i < len(ts) and (ts[i] - t).total_seconds() <= within else None

by_game = defaultdict(list)
for p in plays: by_game[p["game_id"]].append(p)
obs = {h: [] for h in HORIZONS}          # (jump, drift, frac_realised, game)
dropped = {h: 0 for h in HORIZONS}; no_pre = no_obs = 0
for gid, ps in by_game.items():
    ps.sort(key=lambda r: r["wall_clock"])
    for i, p in enumerate(ps):
        vg, t0 = p["venue_game_id"], p["wall_clock"]
        pre = mid_before(vg, t0); tobs = t0 + dt.timedelta(seconds=LAG)
        mo = mid_at_or_after(vg, tobs)
        if pre is None: no_pre += 1; continue
        if mo is None: no_obs += 1; continue
        nxt = ps[i+1]["wall_clock"] if i + 1 < len(ps) else None
        jump = mo - pre
        for h in HORIZONS:
            th = tobs + dt.timedelta(seconds=h)
            if nxt is not None and th > nxt: dropped[h] += 1; continue
            ml = mid_at_or_after(vg, th)
            if ml is None: dropped[h] += 1; continue
            total = ml - pre
            frac = (jump / total) if abs(total) >= MIN_JUMP else None
            obs[h].append((jump, ml - mo, frac, gid))
print(f"no pre-play mid {no_pre:,}   no obs mid {no_obs:,}")

def clustered(vals, keys):
    n = len(vals); m = sum(vals)/n
    res, size = defaultdict(float), defaultdict(int)
    for v, k in zip(vals, keys): res[k] += v-m; size[k] += 1
    G = len(res); ge = n*n/sum(c*c for c in size.values())
    se = (sum(x*x for x in res.values())**0.5)/n*(G/(G-1))**0.5 if G > 1 else 0.0
    return m, 1.96*se, n, G, ge
def slope_clustered(x, y, keys):
    n = len(x); mx, my = sum(x)/n, sum(y)/n
    sxx = sum((a-mx)**2 for a in x); b = sum((a-mx)*(c-my) for a, c in zip(x, y))/sxx
    # cluster-robust SE for OLS slope: sum over clusters of (sum x_i e_i)^2 / sxx^2
    e = [c - my - b*(a-mx) for a, c in zip(x, y)]
    g = defaultdict(float)
    for a, ei, k in zip(x, e, keys): g[k] += (a-mx)*ei
    G = len(g); se = (sum(v*v for v in g.values())**0.5)/sxx*(G/(G-1))**0.5
    return b, 1.96*se, G

print("\n=== POST-PLAY DRIFT on the venue winner market, moves with |jump| >= 1c ===")
print(f"  {'h(s)':>5}{'n':>8}{'dropped':>9}{'beta(drift~jump)':>19}{'95% CI':>20}{'G':>5}   {'continuation c':>15}{'95% CI':>20}   {'realised by obs':>16}")
for h in HORIZONS:
    sel = [(j, d, f, g) for j, d, f, g in obs[h] if abs(j) >= MIN_JUMP]
    if len(sel) < 100: print(f"  {h:>5}{len(sel):>8}   too few"); continue
    b, hb, G = slope_clustered([j for j, *_ in sel], [d for _, d, *_ in sel], [g for *_, g in sel])
    cont, hc, n, G2, ge = clustered([100*(d if j > 0 else -d) for j, d, f, g in sel], [g for *_, g in sel])
    fr = [f for j, d, f, g in sel if f is not None and -2 < f < 3]
    frm, frh, *_ = clustered(fr, [g for j, d, f, g in sel if f is not None and -2 < f < 3]) if len(fr) > 50 else (float('nan'), 0, 0, 0, 0)
    verdict = "CONTINUES" if b - hb > 0 else ("REVERTS" if b + hb < 0 else "efficient (spans 0)")
    print(f"  {h:>5}{n:>8,}{dropped[h]:>9,}{b:>+19.3f}   [{b-hb:+.3f}, {b+hb:+.3f}]{G:>5}   {cont:>+14.2f}c   [{cont-hc:+.2f}, {cont+hc:+.2f}]   {frm:>15.2f} ±{frh:.2f}   {verdict}")
print("\n  beta = slope of subsequent drift on the observed jump. >0 the move continues (underreaction,")
print("  a lagged follower has something left); <0 it reverts; ~0 the price is done by the time we see it.")
print("  'realised by obs' = jump/(later-pre): 1.0 means the whole move was in by +30s; the report's news figure is 0.64.")
