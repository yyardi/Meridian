"""E4 — total-rung model. P(final total > T) for any half-point rung T.

E3's construction applied to totals: one model queried at any T, replicated
training rows at random rungs, monotone in T so the ladder cannot invert --
which is what "price all total rungs from one distribution, no cross-rung arb"
means with the tool we have (a monotone CDF is a distribution). No home/away
frame: a total is symmetric.

BASELINE, MEASURED NOT BORROWED. In-game normal for totals:
    final ~ N(cur_total + line * t/T, (sigma * sqrt(t/T))^2)
with sigma = sd(final_total - total_line) computed on the TRAINING games and
printed. A constant from a betting blog would be the "configured is not
measured" mistake in a new place.

RUNGS ARE RELATIVE TO THE LINE. A fixed absolute grid puts a 45-total game and
an 80-total game at different ends of it; offsets from the game's own line keep
the evaluation where the market is. Half-point snapping avoids pushes.

LEAGUE=nfl: nflverse (total_line, total). LEAGUE=cfb: CFBD (/lines overUnder,
/games points). CFB 2026 tape: over/under from CFBD 2026 lines matched by name
(19/55 have it on our own tape), ESPN totalOverProb from the core feed.
"""
import bisect, gzip, io, json, math, os, random, sys, time
from collections import defaultdict
import httpx
import xgboost as xgb
sys.path.insert(0, "/app/cfb")
from cfb_live_fv import GameState, XGB_PARAMS, XGB_ROUNDS, REGULATION_SECONDS, game_seconds_remaining, half_seconds_remaining  # noqa
from cfb_ingest import cfbd_row_to_state  # noqa
from sqlalchemy import create_engine, text  # noqa

random.seed(20260907); T0 = time.time()
def log(m): print(f"[{time.time()-T0:5.0f}s] {m}", flush=True)

LEAGUE = os.environ.get("LEAGUE", "cfb")
SEASONS = [2022, 2023, 2024]; WEEKS = list(range(1, 16))
T_GRID = [t + 0.5 for t in range(20, 80)] if LEAGUE == "nfl" else [t + 0.5 for t in range(20, 110)]
OFFSETS = [-21, -14, -10, -7, -3, 0, 3, 7, 10, 14, 21]
T_PER_PLAY, PLAY_KEEP = 5, 0.30
CACHE = f"/app/artifacts/{LEAGUE}_total_cache.json"; ARTIFACT = f"/app/artifacts/{LEAGUE}_total_regulation"
ROUNDS = XGB_ROUNDS
if os.environ.get("SMOKE"):
    SEASONS, WEEKS, ROUNDS = [2024], [1], 30
    CACHE, ARTIFACT = "/tmp/smoke_total_cache.json", "/tmp/smoke_total"
    print("SMOKE MODE: one slice, 30 rounds, artifacts untouched", flush=True)

COLS = ["cur_total", "T", "tld", "gsr", "hsr", "line", "exp_rem", "proj", "proj_minus_T",
        "home_has_ball", "down", "distance", "ytg", "period"]
MONO = {"cur_total": 1, "T": -1, "tld": 1, "line": 1, "exp_rem": 1, "proj": 1, "proj_minus_T": 1}

def tstate(st):
    gsr, hsr = game_seconds_remaining(st), half_seconds_remaining(st)
    if gsr is None or hsr is None: return None
    return (st.pos_team_score + st.def_pos_team_score, gsr, hsr, int(bool(st.drive_is_home_offense)),
            st.down or 0, st.distance or 0, st.yards_to_goal or 0, st.period)

def featurize(ts, line, T):
    cur, gsr, hsr, hb, down, dist, ytg, per = ts
    frac = gsr / REGULATION_SECONDS; exp_rem = line * frac; proj = cur + exp_rem
    return [cur, T, cur - T, gsr, hsr, line, exp_rem, proj, proj - T, hb, down, dist, ytg, per]

def snap(x): return math.floor(x) + 0.5

# ------------------------------------------------------------- training rows
def fetch_nflverse():
    import pandas as pd
    out = []
    for y in SEASONS:
        r = httpx.get(f"https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{y}.csv.gz",
                      follow_redirects=True, timeout=300); r.raise_for_status()
        want = ["game_id", "season_type", "qtr", "quarter_seconds_remaining", "down", "ydstogo", "yardline_100",
                "posteam", "home_team", "posteam_score", "defteam_score", "total_line", "total"]
        df = pd.read_csv(io.BytesIO(gzip.decompress(r.content)), usecols=lambda c: c in want, low_memory=False)
        miss = [c for c in want if c not in df.columns]
        if miss: sys.exit(f"nflfastR {y}: missing {miss}")
        df = df[df["season_type"] == "REG"].dropna(subset=want)
        d = df[(df["qtr"] <= 4) & (df["down"] >= 1)]
        log(f"nflverse {y}: {len(d):,} plays, {d['game_id'].nunique()} games")
        for t in d.itertuples(index=False):
            qsr = int(t.quarter_seconds_remaining)
            st = GameState(period=int(t.qtr), clock_minutes=qsr // 60, clock_seconds=qsr % 60, down=int(t.down),
                           distance=int(t.ydstogo), yards_to_goal=int(t.yardline_100), pos_team_score=int(t.posteam_score),
                           def_pos_team_score=int(t.defteam_score), drive_is_home_offense=(t.posteam == t.home_team),
                           pos_team_timeouts=3, def_pos_team_timeouts=3)
            ts = tstate(st)
            if ts: out.append([list(ts), float(t.total_line), int(t.total), str(t.game_id)])
    return out

def fetch_cfbd():
    K = os.environ["CFBD_API_KEY"]; H = {"Authorization": f"Bearer {K}"}
    def get(year, path, **p):
        for _ in range(3):
            try:
                r = httpx.get(f"https://api.collegefootballdata.com/{path}", params=dict(year=year, seasonType="regular", **p), headers=H, timeout=180)
                if r.status_code == 200: return r.json()
            except Exception: time.sleep(2)
        return []
    out = []
    for year in SEASONS:
        final, ou = {}, {}
        for wk in WEEKS:
            for g in get(year, "games", week=wk):
                if g.get("homePoints") is not None and g.get("awayPoints") is not None:
                    final[g["id"]] = g["homePoints"] + g["awayPoints"]
            for g in get(year, "lines", week=wk):
                d = {(ln.get("provider") or "").replace(" ", "").lower(): float(ln["overUnder"])
                     for ln in (g.get("lines") or []) if ln.get("overUnder") is not None}
                if d: ou[g.get("id")] = d.get("draftkings", next(iter(d.values())))
        n0 = len(out)
        for wk in WEEKS:
            for cls in ("fbs", "fcs"):
                for row in get(year, "plays", week=wk, classification=cls):
                    gid = row.get("gameId")
                    if gid not in final or gid not in ou: continue
                    try: ts = tstate(cfbd_row_to_state(row))
                    except Exception: continue
                    if ts: out.append([list(ts), ou[gid], final[gid], gid])
            log(f"  {year} wk{wk:2d}: {len(out):,} plays so far")
        log(f"  {year}: +{len(out)-n0:,} plays, games with final+O/U {len(set(final)&set(ou)):,}")
        # A season that returns no plays is a QUOTA or endpoint failure, not a
        # season with no football. The first full run silently fitted 2022
        # alone and labelled it 2022-2024. Refuse, and say which season.
        if len(out) - n0 == 0:
            sys.exit(f"CFBD returned 0 plays for {year} (quota exhausted or endpoint failing). "
                     f"Refusing to fit and label a partial season set as {SEASONS}.")
    return out

if os.path.exists(CACHE):
    raw = json.load(open(CACHE)); log(f"loaded cache {len(raw):,} plays")
else:
    raw = fetch_nflverse() if LEAGUE == "nfl" else fetch_cfbd()
    json.dump(raw, open(CACHE, "w")); log(f"cached {len(raw):,} plays")

games_all = sorted({r[3] for r in raw}); hold = {g for i, g in enumerate(games_all) if i % 5 == 0}
train = [r for r in raw if r[3] not in hold]; test = [r for r in raw if r[3] in hold]
log(f"{LEAGUE.upper()}: train {len(train):,} plays / {len(games_all)-len(hold):,} games   held-out {len(test):,} / {len(hold):,} (DISJOINT)")

# sigma MEASURED on training games: sd(final_total - line)
per_game = {r[3]: (r[2] - r[1]) for r in train}
_v = list(per_game.values()); _m = sum(_v)/len(_v)
SIGMA = (sum((x-_m)**2 for x in _v)/(len(_v)-1))**0.5
print(f"\n=== totals baseline sigma, MEASURED on {len(_v):,} training games: sd(final - line) = {SIGMA:.2f}  (mean residual {_m:+.2f}) ===")

def normal_baseline(ts, line, T):
    cur, gsr = ts[0], ts[1]; frac = gsr / REGULATION_SECONDS
    mu = cur + line * frac; s = max(SIGMA * math.sqrt(frac), 0.5)
    return 0.5 * (1.0 - math.erf((T - mu) / (s * math.sqrt(2.0))))

# ------------------------------------------------------------------- fit
X, y = [], []
for ts, line, fin, gid in train:
    if random.random() > PLAY_KEEP: continue
    for T in random.sample(T_GRID, T_PER_PLAY):
        X.append(featurize(ts, line, T)); y.append(1 if fin > T else 0)
log(f"training rows {len(X):,}")
params = dict(XGB_PARAMS); params["tree_method"] = "hist"
params["monotone_constraints"] = "(" + ",".join(str(MONO.get(c, 0)) for c in COLS) + ")"
booster = xgb.train(params, xgb.DMatrix(X, label=y, feature_names=COLS), num_boost_round=ROUNDS)
log("fit done"); del X, y
def predict(rows): return booster.predict(xgb.DMatrix(rows, feature_names=COLS))
imp = booster.get_score(importance_type="total_gain"); tot = sum(imp.values()) or 1
print("\n=== feature importance ==="); [print(f"  {f:14s} {100*v/tot:6.2f}%") for f, v in sorted(imp.items(), key=lambda kv: -kv[1])]

# ------------------------------------------------------------- evaluation
def clustered(vals, keys):
    n = len(vals); m = sum(vals)/n
    res, size = defaultdict(float), defaultdict(int)
    for v, k in zip(vals, keys): res[k] += v-m; size[k] += 1
    G = len(res); ge = n*n/sum(c*c for c in size.values())
    if G < 2: return m, 0.0, n, G, ge
    se = (sum(x*x for x in res.values())**0.5)/n*(G/(G-1))**0.5
    return m, 1.96*se, n, G, ge

def evaluate(rows, label):
    print(f"\n=== {label}: per-rung Brier at line+offset, model vs in-game normal (sigma={SIGMA:.1f}) ===")
    print(f"  {'off':>5}{'n':>9}{'model':>9}{'normal':>9}{'diff':>9}  {'95% CI (game-clustered)':<26}{'G':>5}{'G_eff':>7}")
    am, an, ak = [], [], []
    for off in OFFSETS:
        Ts = [snap(line + off) for ts, line, fin, gid in rows]
        Xe = [featurize(ts, line, T) for (ts, line, fin, gid), T in zip(rows, Ts)]
        pm = predict(Xe); pn = [normal_baseline(ts, line, T) for (ts, line, fin, gid), T in zip(rows, Ts)]
        ys = [1 if fin > T else 0 for (ts, line, fin, gid), T in zip(rows, Ts)]
        keys = [gid for ts, line, fin, gid in rows]
        bm = [(p-yy)**2 for p, yy in zip(pm, ys)]; bn = [(p-yy)**2 for p, yy in zip(pn, ys)]
        m, h, n, G, ge = clustered([a-b for a, b in zip(bm, bn)], keys)
        tag = "MODEL" if m+h < 0 else ("normal" if m-h > 0 else "spans 0")
        print(f"  {off:>+5}{n:>9,}{sum(bm)/n:>9.4f}{sum(bn)/n:>9.4f}{m:>+9.4f}  [{m-h:+.4f}, {m+h:+.4f}] {tag:<8}{G:>5}{ge:>7.1f}")
        am += bm; an += bn; ak += keys
    m, h, n, G, ge = clustered([a-b for a, b in zip(am, an)], ak)
    print(f"  {'ALL':>5}{n:>9,}{sum(am)/n:>9.4f}{sum(an)/n:>9.4f}{m:>+9.4f}  [{m-h:+.4f}, {m+h:+.4f}]          {G:>5}{ge:>7.1f}")
    print(f"  pooled skill vs normal {100*(1-(sum(am)/n)/(sum(an)/n)):+.1f}%")

def monotone_check(rows, n=2000):
    viol = tot_ = 0
    for ts, line, fin, gid in random.sample(rows, min(n, len(rows))):
        ps = predict([featurize(ts, line, T) for T in T_GRID])
        for a, b in zip(ps, ps[1:]):
            tot_ += 1; viol += b > a + 1e-6
    print(f"\n=== MONOTONICITY in T: violations {viol}/{tot_}  {'OK' if viol == 0 else 'VIOLATED'} ===")

cf = [(tuple(r[0]), r[1], r[2], r[3]) for r in test]
evaluate(cf, f"{LEAGUE.upper()} HELD-OUT ({len(hold):,} games, {len(cf):,} plays)")
monotone_check(cf)

# ------------------------------------------- our 2026 CFB tape + ESPN totalOverProb
if LEAGUE == "cfb" and not os.environ.get("SMOKE"):
    eng = create_engine(os.environ["DATABASE_URL"])
    with eng.connect() as c:
        g26 = {r.game_id: dict(r._mapping) for r in c.execute(text(
            "SELECT b.game_id, m.home_espn_name AS home, m.away_espn_name AS away, b.home_score+b.away_score AS final_total, "
            "(SELECT avg(live_over_under)::float FROM espn_cfb_game_state s WHERE s.game_id=b.game_id AND s.live_over_under IS NOT NULL) AS ou_tape "
            "FROM espn_cfb_backfill_games b LEFT JOIN cfb_game_map m ON m.espn_game_id=b.game_id WHERE b.home_score IS NOT NULL"))}
        p26 = [dict(r._mapping) for r in c.execute(text(
            "SELECT game_id, play_id, period, clock_minutes, clock_seconds, down, distance, yards_to_goal, pos_team_score, "
            "def_pos_team_score, drive_is_home_offense FROM espn_cfb_backfill_plays WHERE down > 0 AND period IS NOT NULL AND NOT is_overtime"))]
    eng.dispose()
    # O/U for all 55 from CFBD 2026 lines by name; fall back to tape
    K = os.environ.get("CFBD_API_KEY"); H = {"Authorization": f"Bearer {K}"} if K else {}
    def norm(s): return "".join(ch for ch in (s or "").lower() if ch.isalnum())
    cf26 = {}
    for wk in (1, 2):
        try:
            for g in httpx.get("https://api.collegefootballdata.com/lines", params=dict(year=2026, week=wk, seasonType="regular"), headers=H, timeout=60).json():
                d = {(ln.get("provider") or "").replace(" ", "").lower(): float(ln["overUnder"]) for ln in (g.get("lines") or []) if ln.get("overUnder") is not None}
                if d: cf26[(norm(g.get("homeTeam")), norm(g.get("awayTeam")))] = d.get("draftkings", next(iter(d.values())))
        except Exception as e: log(f"CFBD 2026 wk{wk} lines failed: {e}")
    src = {"cfbd": 0, "tape": 0, "none": 0}
    for gid, g in g26.items():
        h, a = norm(g["home"]), norm(g["away"]); hit = None
        for (ch, ca), v in cf26.items():
            if ch and ca and (ch in h or h in ch) and (ca in a or a in ca): hit = v; break
        if hit is not None: g["line"], src["cfbd"] = hit, src["cfbd"]+1
        elif g["ou_tape"] is not None: g["line"], src["tape"] = g["ou_tape"], src["tape"]+1
        else: g["line"] = None; src["none"] += 1
    print(f"\n2026 tape over/under source: {src}")
    t26 = []
    for p in p26:
        g = g26.get(p["game_id"])
        if not g or g["line"] is None: continue
        st = GameState(period=p["period"], clock_minutes=p["clock_minutes"] or 0, clock_seconds=p["clock_seconds"] or 0, down=p["down"],
                       distance=p["distance"], yards_to_goal=p["yards_to_goal"], pos_team_score=p["pos_team_score"] or 0,
                       def_pos_team_score=p["def_pos_team_score"] or 0, drive_is_home_offense=bool(p["drive_is_home_offense"]),
                       pos_team_timeouts=3, def_pos_team_timeouts=3)
        ts = tstate(st)
        if ts: t26.append((ts, g["line"], g["final_total"], p["game_id"], p["play_id"]))
    rows26 = [(ts, line, fin, gid) for ts, line, fin, gid, pid in t26]
    if rows26: evaluate(rows26, f"OUR 2026 TAPE ({len({r[3] for r in rows26})} games, {len(rows26):,} plays)")
    # ESPN totalOverProb at the game's own line
    espn = {}
    for gid in g26:
        try:
            for it in httpx.get(f"https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/events/{gid}/competitions/{gid}/probabilities?limit=1000", timeout=60).json().get("items", []):
                pid = it.get("play", {}).get("$ref", "").rsplit("/", 1)[-1].split("?")[0]
                if pid and it.get("totalOverProb") is not None: espn[(gid, pid)] = float(it["totalOverProb"])
        except Exception: pass
    m_ = [(ts, line, fin, gid, espn[(gid, pid)]) for ts, line, fin, gid, pid in t26 if (gid, pid) in espn and fin != line]
    print(f"\n=== vs ESPN totalOverProb at each game's OWN total line, matched on play_id ===")
    if len(m_) < 500: print(f"  only {len(m_)} matched -- refusing to report.")
    else:
        pm = predict([featurize(ts, line, line) for ts, line, fin, gid, cp in m_])
        ys = [1 if fin > line else 0 for ts, line, fin, gid, cp in m_]
        bm = [(p-yy)**2 for p, yy in zip(pm, ys)]; be = [(cp-yy)**2 for (ts, line, fin, gid, cp), yy in zip(m_, ys)]
        pn = [normal_baseline(ts, line, line) for ts, line, fin, gid, cp in m_]; bn = [(p-yy)**2 for p, yy in zip(pn, ys)]
        keys = [gid for ts, line, fin, gid, cp in m_]
        m, h, n, G, ge = clustered([a-b for a, b in zip(bm, be)], keys)
        m2, h2, *_ = clustered([a-b for a, b in zip(be, bn)], keys)
        print(f"  plays {n:,} / games {G} / G_eff {ge:.1f}   Brier model {sum(bm)/n:.4f}  espn {sum(be)/n:.4f}  normal {sum(bn)/n:.4f}")
        print(f"  model - espn  {m:+.4f} [{m-h:+.4f}, {m+h:+.4f}]  {'MODEL BETTER' if m+h<0 else ('ESPN BETTER' if m-h>0 else 'SPANS ZERO')}")
        print(f"  espn - normal {m2:+.4f} [{m2-h2:+.4f}, {m2+h2:+.4f}]  (is ESPN's total prob a real bar, as its cover prob was?)")

os.makedirs(os.path.dirname(ARTIFACT), exist_ok=True)
booster.save_model(ARTIFACT + ".json")
json.dump({"league": LEAGUE, "seasons": SEASONS, "cols": COLS, "monotone": MONO, "sigma_measured": round(float(SIGMA), 3),
           "t_grid": [T_GRID[0], T_GRID[-1]], "train_games": len(games_all)-len(hold), "holdout_games": len(hold),
           "note": "Model result on held-out games. NOT edge."}, open(ARTIFACT + ".meta.json", "w"), indent=1,
          default=lambda o: float(o) if hasattr(o, "__float__") else str(o))
log(f"saved {ARTIFACT}.json")
