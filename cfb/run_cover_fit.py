"""E3 — spread-rung cover model. P(final HOME margin > K) for any rung K.

WHY THIS AND NOT MORE WP WORK. Winner markets are 1.8% of the board. The other
98% is spread and total ladders, and a ladder needs a DISTRIBUTION of final
margin, not P(win). This is the greerreNFL construction ported to CFB: same
recipe as the WP model, target swapped to cover_result, one feature added --
spread_line_differential = current margin - K, "how many points home still
needs" -- and a monotone constraint in K so the ladder is coherent by
construction: P(margin > K) cannot rise as K rises.

FRAME. Everything here is HOME frame. The WP model is possession-frame because
its recipe is; a ladder is quoted per game, not per possession, so the natural
frame is the one the rung is written in. spread is home-frame, NEGATIVE = home
favoured, on both CFBD (formattedSpread 'Tennessee -49.5' with spread=-49.5,
homeTeam=Tennessee) and ESPN pickcenter (verified 49/53 games in E2). The
bridge between the two sources is re-verified below by name-matching week-1
lines, because the last attempt stopped at n=19 < 30 and was left UNVERIFIED.

K AUGMENTATION. One model, queried at any K. Each training play is replicated
at a handful of random half-point rungs with y_K = 1[final_margin > K].
Half-points so there are no pushes to adjudicate. Replicated rows from one
play are not independent, which is why every interval below is clustered by
GAME, never by row.

TWO BASELINES, because "beats nothing" is not a result:
  normal     Stern (1991) extended in-game: final ~ N(m + E*t/T, (sigma*sqrt(t/T))^2)
             with E = -spread, sigma = 15 (Sides-Harvill), t = seconds left.
             This is what "just use the line and the score" prices a rung at.
             If XGBoost cannot beat it, the ladder model adds nothing.
  espn       spreadCoverProbHome from ESPN's core probabilities feed, at the
             game's own line only (ESPN publishes no ladder). Benchmark, not
             ground truth; settlement is the game outcome.

WHAT THIS IS NOT. A model result on held-out games. Not edge. Edge on a rung
is measured against that rung's contemporaneous venue price and that is E5.
"""
import json
import math
import os
import random
import sys
import time
from collections import defaultdict

import httpx
import xgboost as xgb

sys.path.insert(0, "/app/cfb")
from cfb_live_fv import (GameState, XGB_PARAMS, XGB_ROUNDS, REGULATION_SECONDS,  # noqa: E402
                         game_seconds_remaining, half_seconds_remaining)
from cfb_ingest import cfbd_row_to_state  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

random.seed(20260907)
T0 = time.time()
def log(msg):
    print(f"[{time.time()-T0:6.0f}s] {msg}", flush=True)

SEASONS = [2022, 2023, 2024]
WEEKS = list(range(1, 16))
SIGMA = 15.0
K_GRID = [k + 0.5 for k in range(-35, 35)]          # -34.5 .. +34.5, half-points
K_PER_PLAY = 5
PLAY_KEEP = 0.30
# K_NEAR_LINE=1: 3 of the 5 rungs per play are drawn within +-10.5 of the
# expected margin (-spread) and 2 from the full grid, instead of all 5 from the
# full grid. Hypothesis, stated before running: random-K puts most training
# rows at easy rungs far from the line, so capacity goes where the
# game's-own-line evaluation (and ESPN) is not. The far rungs keep 2 draws so
# the ladder tails still see data. This is the ONE retrain; stop after it.
K_NEAR_LINE = bool(os.environ.get("K_NEAR_LINE"))
NEAR_BAND = 10.5
EVAL_K = [-20.5, -13.5, -10.5, -6.5, -3.5, -0.5, 0.5, 3.5, 6.5, 10.5, 13.5, 20.5]
CACHE = "/app/artifacts/cfbd_cover_cache.json"
ARTIFACT = "/app/artifacts/cfb_cover_regulation"

# SMOKE=1: one week, 30 rounds, nothing written to artifacts/. Exists because
# the E1 harness died on a Decimal*float AFTER a 25s query, and this one has a
# ~15-minute fetch in front of its first feature build.
if os.environ.get("SMOKE"):
    SEASONS, WEEKS, XGB_ROUNDS = [2024], [1], 30
    CACHE, ARTIFACT = "/tmp/smoke_cache.json", "/tmp/smoke_cover"
    print("SMOKE MODE: 2024 wk1 only, 30 rounds, artifacts untouched", flush=True)
# Must come AFTER every other ARTIFACT assignment. The first version of this
# override sat above the base assignment and was silently overwritten, so
# v2 saved over v1. Verified by reading the meta on disk, not by reading this.
elif K_NEAR_LINE:
    ARTIFACT = "/app/artifacts/cfb_cover_regulation_nearline"

COLS = ["home_margin", "K", "sld", "gsr", "hsr", "exp_margin", "margin_time",
        "exp_margin_time", "home_has_ball", "down", "distance", "ytg", "period"]
MONO = {"home_margin": 1, "K": -1, "sld": 1, "exp_margin": 1,
        "margin_time": 1, "exp_margin_time": 1}


# ------------------------------------------------------------------ features
def home_state(st: GameState):
    """(home_margin, gsr, hsr, home_has_ball, down, distance, ytg, period) or
    None in overtime, which has no clock and no rung this model can price."""
    gsr = game_seconds_remaining(st)
    hsr = half_seconds_remaining(st)
    if gsr is None or hsr is None:
        return None
    m = st.pos_team_score - st.def_pos_team_score
    if not st.drive_is_home_offense:
        m = -m
    return (m, gsr, hsr, int(bool(st.drive_is_home_offense)),
            st.down or 0, st.distance or 0, st.yards_to_goal or 0, st.period)


def featurize(hs, spread_home, K):
    m, gsr, hsr, hb, down, dist, ytg, per = hs
    elapsed = REGULATION_SECONDS - gsr
    E = -spread_home
    return [m, K, m - K, gsr, hsr, E,
            m * math.exp(4.0 * elapsed / REGULATION_SECONDS),
            E * math.exp(-4.0 * elapsed / REGULATION_SECONDS),
            hb, down, dist, ytg, per]


def normal_baseline(hs, spread_home, K):
    m, gsr = hs[0], hs[1]
    frac = gsr / REGULATION_SECONDS
    mu = m + (-spread_home) * frac
    s = max(SIGMA * math.sqrt(frac), 0.5)
    return 0.5 * (1.0 - math.erf((K - mu) / (s * math.sqrt(2.0))))


# ------------------------------------------------------- our 2026 tape (test)
eng = create_engine(os.environ["DATABASE_URL"])
with eng.connect() as c:
    # home/away on backfill_games are ESPN team IDs (e.g. 2116), not names.
    # The bridge check below needs NAMES, and those live on cfb_game_map.
    games26 = {r.game_id: dict(r._mapping) for r in c.execute(text(
        "SELECT b.game_id, m.home_espn_name AS home, m.away_espn_name AS away, "
        "b.home_score, b.away_score, b.spread::float AS spread "
        "FROM espn_cfb_backfill_games b LEFT JOIN cfb_game_map m ON m.espn_game_id = b.game_id "
        "WHERE b.spread IS NOT NULL AND b.home_score IS NOT NULL AND b.away_score IS NOT NULL"))}
    plays26 = [dict(r._mapping) for r in c.execute(text(
        "SELECT game_id, play_id, period, clock_minutes, clock_seconds, down, distance, "
        "yards_to_goal, pos_team_score, def_pos_team_score, drive_is_home_offense, is_overtime "
        "FROM espn_cfb_backfill_plays WHERE down IS NOT NULL AND down > 0 AND period IS NOT NULL "
        "AND NOT is_overtime"))]
eng.dispose()                       # nothing below touches the DB; hold no connection
log(f"2026 tape: {len(games26)} games, {len(plays26):,} regulation plays")

tape26 = []                         # (hs, spread_home, final_margin, game_id, play_id)
for p in plays26:
    g = games26.get(p["game_id"])
    if not g:
        continue
    st = GameState(period=p["period"], clock_minutes=p["clock_minutes"] or 0,
                   clock_seconds=p["clock_seconds"] or 0, down=p["down"],
                   distance=p["distance"], yards_to_goal=p["yards_to_goal"],
                   pos_team_score=p["pos_team_score"] or 0,
                   def_pos_team_score=p["def_pos_team_score"] or 0,
                   drive_is_home_offense=bool(p["drive_is_home_offense"]),
                   pos_team_timeouts=3, def_pos_team_timeouts=3)
    hs = home_state(st)
    if hs is None:
        continue
    tape26.append((hs, g["spread"], g["home_score"] - g["away_score"],
                   p["game_id"], p["play_id"]))
log(f"2026 tape usable: {len(tape26):,} plays / {len({t[3] for t in tape26})} games")

# ---------------------------------------------------------------- CFBD train
K = os.environ["CFBD_API_KEY"]
H = {"Authorization": f"Bearer {K}"}

def get(year, path, **p):
    for attempt in range(3):
        try:
            r = httpx.get(f"https://api.collegefootballdata.com/{path}",
                          params=dict(year=year, seasonType="regular", **p),
                          headers=H, timeout=180)
            if r.status_code == 200:
                return r.json()
        except Exception:
            time.sleep(2)
    return []

def spread_of(lines_row):
    d = {}
    for ln in (lines_row.get("lines") or []):
        if ln.get("spread") is not None:
            d[(ln.get("provider") or "").replace(" ", "").lower()] = float(ln["spread"])
    return d.get("draftkings", next(iter(d.values()))) if d else None

if os.path.exists(CACHE):
    with open(CACHE) as fh:
        raw = json.load(fh)
    log(f"loaded CFBD cache: {len(raw):,} plays")
else:
    raw = []                        # [hs, spread, final_margin, game_id]
    for year in SEASONS:
        outcome, spread = {}, {}
        for wk in WEEKS:
            for g in get(year, "games", week=wk):
                if g.get("homePoints") is not None and g.get("awayPoints") is not None:
                    outcome[g["id"]] = g["homePoints"] - g["awayPoints"]
            for g in get(year, "lines", week=wk):
                sp = spread_of(g)
                if sp is not None:
                    spread[g.get("id")] = sp
        n0 = len(raw)
        for wk in WEEKS:
            for cls in ("fbs", "fcs"):
                for row in get(year, "plays", week=wk, classification=cls):
                    gid = row.get("gameId")
                    if gid not in outcome or gid not in spread:
                        continue
                    try:
                        hs = home_state(cfbd_row_to_state(row))
                    except Exception:
                        continue
                    if hs is None:
                        continue
                    raw.append([list(hs), spread[gid], outcome[gid], gid])
            log(f"  {year} wk{wk:2d}: {len(raw):,} plays so far")
        log(f"  {year}: +{len(raw)-n0:,} plays, games with outcome+spread {len(set(outcome)&set(spread)):,}")
    with open(CACHE, "w") as fh:
        json.dump(raw, fh)
    log(f"cached CFBD to {CACHE}")

games_all = sorted({r[3] for r in raw})
holdout = {g for i, g in enumerate(games_all) if i % 5 == 0}
train = [r for r in raw if r[3] not in holdout]
test_cfbd = [r for r in raw if r[3] in holdout]
log(f"CFBD: train {len(train):,} plays / {len(games_all)-len(holdout):,} games   "
    f"holdout {len(test_cfbd):,} plays / {len(holdout):,} games (DISJOINT)")

# ------------------------------------------------- spread bridge, CFBD vs ESPN
def norm(s):
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())

cfbd26 = {}
for wk in (1, 2):
    for g in get(2026, "lines", week=wk):
        sp = spread_of(g)
        if sp is not None:
            cfbd26[(norm(g.get("homeTeam")), norm(g.get("awayTeam")))] = sp
matched, agree, diffs = 0, 0, []
for gid, g in games26.items():
    h, a = norm(g["home"]), norm(g["away"])
    hit = None
    for (ch, ca), sp in cfbd26.items():
        if (ch in h or h in ch) and (ca in a or a in ca) and ch and ca:
            hit = sp
            break
    if hit is None:
        continue
    matched += 1
    d = abs(hit - g["spread"])
    diffs.append(d)
    if d <= 0.51:
        agree += 1
print("\n=== SPREAD BRIDGE: CFBD (train) vs ESPN pickcenter (serve), 2026 wk1-2 ===")
print(f"  matched by name {matched}/{len(games26)}   agree within 0.5pt {agree}/{matched}"
      f"   max |diff| {max(diffs) if diffs else float('nan'):.1f}")
if matched < 30:
    print(f"  BRIDGE UNVERIFIED: {matched} < 30 matches. Same-sign is checked per game "
          "below; magnitudes may differ between books.")
elif agree / matched < 0.8:
    print("  BRIDGE DISAGREES on >20% of games. Train/serve spread asymmetry is real; "
          "2026-tape results below carry that caveat. CFBD-holdout results do not.")
else:
    print("  BRIDGE OK -- same frame, same sign, magnitudes agree.")
# the sign alone, which is the part that would silently invert a ladder
signs_ok = sum(1 for gid, g in games26.items()
               for (ch, ca), sp in cfbd26.items()
               if ch and ca and (ch in norm(g["home"]) or norm(g["home"]) in ch)
               and (ca in norm(g["away"]) or norm(g["away"]) in ca)
               and (sp < 0) == (g["spread"] < 0))
print(f"  sign agreement {signs_ok}/{matched}")

# ------------------------------------------------------------ build + fit
def build_rows(rows, keep=1.0, k_per=K_PER_PLAY):
    X, y, grp = [], [], []
    for hs, sp, fm, gid in rows:
        if keep < 1.0 and random.random() > keep:
            continue
        if K_NEAR_LINE:
            E = -sp
            near = [k for k in K_GRID if abs(k - E) <= NEAR_BAND] or K_GRID
            ks = random.sample(near, min(3, len(near))) + random.sample(K_GRID, 2)
        else:
            ks = random.sample(K_GRID, k_per)
        for K_ in ks:
            X.append(featurize(hs, sp, K_))
            y.append(1 if fm > K_ else 0)
            grp.append(gid)
    return X, y, grp

cal_games = {g for i, g in enumerate(sorted({r[3] for r in train})) if i % 10 == 0}
train_fit = [r for r in train if r[3] not in cal_games]
train_cal = [r for r in train if r[3] in cal_games]
log(f"K_NEAR_LINE={K_NEAR_LINE}   fit games {len({r[3] for r in train_fit}):,}   "
    f"calibration games {len(cal_games):,} (disjoint from fit AND from every test set)")
Xtr, ytr, gtr = build_rows(train_fit, keep=PLAY_KEEP)
log(f"training rows {len(Xtr):,}  (plays x {K_PER_PLAY} rungs, {PLAY_KEEP:.0%} of plays)")
params = dict(XGB_PARAMS)
params["tree_method"] = "hist"
params["monotone_constraints"] = "(" + ",".join(str(MONO.get(c, 0)) for c in COLS) + ")"
dtr = xgb.DMatrix(Xtr, label=ytr, feature_names=COLS, missing=float("nan"))
booster = xgb.train(params, dtr, num_boost_round=XGB_ROUNDS)
log("fit done")
del Xtr, ytr, dtr

imp = booster.get_score(importance_type="total_gain")
tot = sum(imp.values()) or 1.0
print("\n=== feature importance (total gain) ===")
for f, v in sorted(imp.items(), key=lambda kv: -kv[1]):
    print(f"  {f:18s} {100.0*v/tot:6.2f}%")


def predict_raw(X):
    return booster.predict(xgb.DMatrix(X, feature_names=COLS, missing=float("nan")))

# isotonic layer, fit on the calibration games only
from sklearn.isotonic import IsotonicRegression  # noqa: E402
Xc, yc, _ = build_rows(train_cal, keep=1.0)
iso = IsotonicRegression(out_of_bounds="clip").fit(predict_raw(Xc), yc)
log(f"isotonic fit on {len(yc):,} calibration rows")
del Xc, yc

USE_ISO = False
def predict(X):
    p = predict_raw(X)
    return iso.predict(p) if USE_ISO else p


# ------------------------------------------------------------ evaluation
def clustered(vals, keys):
    n = len(vals)
    if n == 0:
        return None
    m = sum(vals) / n
    res, size = defaultdict(float), defaultdict(int)
    for v, k in zip(vals, keys):
        res[k] += v - m
        size[k] += 1
    G = len(res)
    g_eff = n * n / sum(c * c for c in size.values())
    if G < 2:
        return m, 0.0, n, G, g_eff
    se = (sum(x * x for x in res.values()) ** 0.5) / n * (G / (G - 1)) ** 0.5
    return m, 1.96 * se, n, G, g_eff


def evaluate(rows, label):
    """Per-rung Brier: model vs in-game normal, game-clustered difference."""
    print(f"\n=== {label}: per-rung Brier, model vs in-game normal (sigma={SIGMA:.0f}) ===")
    print(f"  {'K':>6}{'n':>9}{'model':>9}{'normal':>9}{'diff':>9}  {'95% CI (game-clustered)':<26}{'G':>5}{'G_eff':>7}")
    allmod, allnrm, allkey = [], [], []
    for K_ in EVAL_K:
        X = [featurize(hs, sp, K_) for hs, sp, fm, gid in rows]
        pm = predict(X)
        pn = [normal_baseline(hs, sp, K_) for hs, sp, fm, gid in rows]
        ys = [1 if fm > K_ else 0 for hs, sp, fm, gid in rows]
        keys = [gid for hs, sp, fm, gid in rows]
        bm = [(p - y) ** 2 for p, y in zip(pm, ys)]
        bn = [(p - y) ** 2 for p, y in zip(pn, ys)]
        d = [a - b for a, b in zip(bm, bn)]
        m, h, n, G, ge = clustered(d, keys)
        tag = "MODEL" if m + h < 0 else ("normal" if m - h > 0 else "spans 0")
        print(f"  {K_:>+6.1f}{n:>9,}{sum(bm)/n:>9.4f}{sum(bn)/n:>9.4f}{m:>+9.4f}  "
              f"[{m-h:+.4f}, {m+h:+.4f}] {tag:<8}{G:>5}{ge:>7.1f}")
        allmod += bm; allnrm += bn; allkey += keys
    d = [a - b for a, b in zip(allmod, allnrm)]
    m, h, n, G, ge = clustered(d, allkey)
    print(f"  {'ALL':>6}{n:>9,}{sum(allmod)/n:>9.4f}{sum(allnrm)/n:>9.4f}{m:>+9.4f}  "
          f"[{m-h:+.4f}, {m+h:+.4f}]          {G:>5}{ge:>7.1f}")
    print(f"  negative diff = model better. Pooled skill vs normal: "
          f"{100*(1 - (sum(allmod)/n)/(sum(allnrm)/n)):+.1f}%")


def monotone_check(rows, n_states=2000):
    """P(margin > K) must be non-increasing in K on real states."""
    sample = random.sample(rows, min(n_states, len(rows)))
    viol = tot_ = 0
    worst = 0.0
    for hs, sp, fm, gid in sample:
        ps = predict([featurize(hs, sp, K_) for K_ in K_GRID])
        for a, b in zip(ps, ps[1:]):
            tot_ += 1
            if b > a + 1e-6:
                viol += 1
                worst = max(worst, b - a)
    print(f"\n=== MONOTONICITY in K on {len(sample):,} real states x {len(K_GRID)-1} steps ===")
    print(f"  violations {viol}/{tot_}   worst upward step {worst:.2e}   "
          f"{'OK' if viol == 0 else 'VIOLATED -- constraint not binding'}")


def calibration(rows, label):
    print(f"\n=== CALIBRATION by predicted decile, {label}, all EVAL_K pooled ===")
    buckets = defaultdict(list)
    for K_ in EVAL_K:
        X = [featurize(hs, sp, K_) for hs, sp, fm, gid in rows]
        for p, (hs, sp, fm, gid) in zip(predict(X), rows):
            buckets[min(9, int(p * 10))].append((float(p), 1 if fm > K_ else 0))
    for b in sorted(buckets):
        v = buckets[b]
        if len(v) < 500:
            print(f"  {b*10:3d}-{b*10+10:3d}%  n={len(v):7,}  [THIN]"); continue
        pm = sum(x for x, _ in v) / len(v); am = sum(y for _, y in v) / len(v)
        print(f"  {b*10:3d}-{b*10+10:3d}%  n={len(v):7,}  predicted={pm:.3f}  actual={am:.3f}  gap={am-pm:+.3f}")


cf = [(tuple(r[0]), r[1], r[2], r[3]) for r in test_cfbd]
t26 = [(hs, sp, fm, gid) for hs, sp, fm, gid, pid in tape26]
for USE_ISO in (False, True):
    tag = "ISOTONIC" if USE_ISO else "RAW"
    evaluate(cf, f"[{tag}] CFBD HELD-OUT GAMES ({len(holdout):,} games, {len(cf):,} plays)")
    evaluate(t26, f"[{tag}] OUR 2026 TAPE ({len({t[3] for t in t26})} games, {len(t26):,} plays)")
    calibration(cf, f"[{tag}] CFBD holdout")
USE_ISO = False
monotone_check(cf)

# -------------------------------------------- ESPN spreadCoverProbHome benchmark
log("fetching ESPN core probabilities for the 2026 games")
ESPN = ("https://sports.core.api.espn.com/v2/sports/football/leagues/college-football"
        "/events/{g}/competitions/{g}/probabilities?limit=1000")
espn_cover = {}                      # (game_id, play_id) -> spreadCoverProbHome
for gid in games26:
    try:
        r = httpx.get(ESPN.format(g=gid), timeout=60)
        if r.status_code != 200:
            continue
        for it in r.json().get("items", []):
            ref = it.get("play", {}).get("$ref", "")
            pid = ref.rsplit("/", 1)[-1].split("?")[0]
            cp = it.get("spreadCoverProbHome")
            if pid and cp is not None:
                espn_cover[(gid, pid)] = float(cp)
    except Exception:
        continue
log(f"ESPN cover probabilities: {len(espn_cover):,} plays across "
    f"{len({g for g, _ in espn_cover})} games")

matched = [(hs, sp, fm, gid, espn_cover[(gid, pid)]) for hs, sp, fm, gid, pid in tape26
           if (gid, pid) in espn_cover]
print(f"\n=== vs ESPN spreadCoverProbHome, at each game's OWN line, matched on play_id ===")
if len(matched) < 500:
    print(f"  only {len(matched)} matched plays -- refusing to report.")
else:
    Xe = [featurize(hs, sp, -sp) for hs, sp, fm, gid, cp in matched]
    ys = [1 if fm > -sp else 0 for hs, sp, fm, gid, cp in matched]
    keys_e = [gid for hs, sp, fm, gid, cp in matched]
    be_e = [(cp - y) ** 2 for (hs, sp, fm, gid, cp), y in zip(matched, ys)]
    for USE_ISO in (False, True):
        pm = predict(Xe)
        bm_e = [(p - y) ** 2 for p, y in zip(pm, ys)]
        d = [a - b for a, b in zip(bm_e, be_e)]
        m, h, n, G, ge = clustered(d, keys_e)
        print(f"  [{'ISOTONIC' if USE_ISO else 'RAW':<8}] plays {n:,} / games {G} / G_eff {ge:.1f}   "
              f"Brier model {sum(bm_e)/n:.4f}  espn {sum(be_e)/n:.4f}   "
              f"diff {m:+.4f} [{m-h:+.4f}, {m+h:+.4f}]  "
              f"{'MODEL BETTER' if m+h < 0 else ('ESPN BETTER' if m-h > 0 else 'SPANS ZERO')}")
    USE_ISO = False
    print("  (E2 lesson applies: ESPN's WP was line-blind. Check whether its cover")
    print("   prob is too before reading a win here as skill rather than line knowledge.)")

# ------------------------------------------------------------------- persist
os.makedirs("/app/artifacts", exist_ok=True)
booster.save_model(ARTIFACT + ".json")
with open(ARTIFACT + ".meta.json", "w") as fh:
    json.dump({"seasons": SEASONS, "k_near_line": K_NEAR_LINE, "cols": COLS, "monotone": MONO, "sigma_baseline": SIGMA,
               "k_grid": [K_GRID[0], K_GRID[-1]], "train_games": len(games_all) - len(holdout),
               "holdout_games": len(holdout), "tape26_games": len({t[3] for t in tape26}),
               "frame": "HOME; spread negative = home favoured; y_K = 1[final_home_margin > K]",
               "note": "Model result on held-out games. NOT edge. Edge per rung is E5."},
              fh, indent=1)
log(f"saved {ARTIFACT}.json")
