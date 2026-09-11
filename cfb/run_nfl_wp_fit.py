"""E8 — the NFL win-probability head, same recipe, NFL-native data.

The plan's E8 sketch is "nflfastR native". The CFB WP model is the nflfastR
recipe fitted on CFBD data; pointing it at NFL games would be a transfer with
no test behind it. This fits the IDENTICAL recipe -- same GameState, same
build_features, same fit() with the same monotone constraints, same
degrade-timeouts-to-serving rule -- on nflverse play-by-play 2022-2024, held
out BY GAME, and scores it against nflfastR's own shipped `vegas_wp` on the
same held-out plays. That comparison can fail, which is what makes it a test:
if the recipe does not reproduce the production model it was copied from,
something in the port is wrong.

SIGN CONVENTION, CHECKED NOT ASSUMED. nflfastR's `spread_line` is POSITIVE
when the HOME team is favoured. Ours is NEGATIVE when home is favoured (E2
verified 49/53 on the venue tape; the monotone constraint got inverted once
already by exactly this). So closing_spread = -spread_line, and the flip is
asserted against the data before use: corr(spread_line, result) must be > 0.

SMOKE=1 fits one season at 30 rounds and writes nothing to artifacts/.
"""
import gzip
import io
import json
import math
import os
import sys
import time

import httpx
import pandas as pd

sys.path.insert(0, "/app/cfb")
from cfb_live_fv import GameState  # noqa: E402
from cfb_train import fit, split_by_regime  # noqa: E402
import cfb_live_fv  # noqa: E402

T0 = time.time()
def log(m): print(f"[{time.time()-T0:5.0f}s] {m}", flush=True)

SEASONS = [2022, 2023, 2024]
ARTIFACT = "/app/artifacts/nfl_wp_regulation"
CACHE = "/app/artifacts/nflfastr_wp_cache.json"
ROUNDS = None
if os.environ.get("SMOKE"):
    SEASONS, ARTIFACT, CACHE, ROUNDS = [2024], "/tmp/nfl_wp_smoke", "/tmp/nfl_wp_smoke_cache.json", 30
    print("SMOKE MODE: 2024 only, 30 rounds, artifacts untouched", flush=True)

URL = "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{y}.csv.gz"
COLS = ["game_id", "play_id", "season_type", "qtr", "quarter_seconds_remaining", "down", "ydstogo",
        "yardline_100", "posteam", "home_team", "away_team", "posteam_score", "defteam_score",
        "spread_line", "result", "posteam_timeouts_remaining", "defteam_timeouts_remaining",
        "home_score", "away_score", "vegas_wp", "wp"]

if os.path.exists(CACHE):
    rows = json.load(open(CACHE)); log(f"loaded cache: {len(rows):,} plays")
else:
    rows = []          # [state-dict, closing_spread, label_pos_won, game_id, vegas_wp]
    for y in SEASONS:
        r = httpx.get(URL.format(y=y), follow_redirects=True, timeout=300); r.raise_for_status()
        df = pd.read_csv(io.BytesIO(gzip.decompress(r.content)), usecols=lambda c: c in COLS, low_memory=False)
        missing = [c for c in COLS if c not in df.columns]
        if missing:
            sys.exit(f"nflfastR {y}: missing columns {missing}; refusing to guess. Have: {sorted(df.columns)[:30]}")
        df = df[df["season_type"] == "REG"]
        # sign check on THIS season's data, before anything uses spread_line
        g = df.drop_duplicates("game_id")[["spread_line", "result"]].dropna()
        corr = g["spread_line"].corr(g["result"])
        log(f"{y}: {len(df):,} REG plays, {g.shape[0]} games, corr(spread_line, result) = {corr:+.3f} "
            f"-> {'home-favoured POSITIVE as documented; flipping to our frame' if corr > 0.2 else 'UNEXPECTED SIGN'}")
        if corr <= 0.2:
            sys.exit("spread_line sign convention not as documented; stopping rather than fit an inverted model")
        d = df.dropna(subset=["qtr", "quarter_seconds_remaining", "down", "ydstogo", "yardline_100", "posteam",
                              "posteam_score", "defteam_score", "spread_line", "result",
                              "posteam_timeouts_remaining", "defteam_timeouts_remaining"])
        d = d[(d["qtr"] <= 4) & (d["down"] >= 1) & (d["result"] != 0)]
        n0 = len(rows)
        for t in d.itertuples(index=False):
            qsr = int(t.quarter_seconds_remaining)
            st = dict(period=int(t.qtr), clock_minutes=qsr // 60, clock_seconds=qsr % 60,
                      down=int(t.down), distance=int(t.ydstogo), yards_to_goal=int(t.yardline_100),
                      pos_team_score=int(t.posteam_score), def_pos_team_score=int(t.defteam_score),
                      drive_is_home_offense=(t.posteam == t.home_team),
                      pos_team_timeouts=int(t.posteam_timeouts_remaining),
                      def_pos_team_timeouts=int(t.defteam_timeouts_remaining))
            home_won = t.result > 0
            y_pos = int(home_won if t.posteam == t.home_team else not home_won)
            vwp_pos = float(t.vegas_wp) if pd.notna(t.vegas_wp) else None   # nflfastR wp is POSTEAM frame
            rows.append([st, -float(t.spread_line), y_pos, str(t.game_id), vwp_pos])
        log(f"{y}: +{len(rows)-n0:,} regulation plays")
    json.dump(rows, open(CACHE, "w")); log(f"cached {len(rows):,} plays")

games = sorted({r[3] for r in rows})
hold = {g for i, g in enumerate(games) if i % 5 == 0}
tr = [r for r in rows if r[3] not in hold]; te = [r for r in rows if r[3] in hold]
log(f"train {len(tr):,} plays / {len(games)-len(hold)} games   held-out {len(te):,} / {len(hold)} (DISJOINT)")

def gs(d): return GameState(**d)
heads = split_by_regime([gs(r[0]) for r in tr], [r[1] for r in tr], [r[2] for r in tr], [r[3] for r in tr])
booster, predict, mono = fit(heads["regulation"], **({"num_round": ROUNDS} if ROUNDS else {}))
log(f"fit done; monotonicity: {mono}")
imp = booster.get_score(importance_type="total_gain"); tot = sum(imp.values()) or 1
print("\n=== feature importance (total gain) ===")
for f, v in sorted(imp.items(), key=lambda kv: -kv[1]): print(f"  {f:26s} {100*v/tot:6.2f}%")

th = split_by_regime([gs(r[0]) for r in te], [r[1] for r in te], [r[2] for r in te], [r[3] for r in te])
Xte, yte, gte, cols = th["regulation"]
p = predict(Xte)
# vegas_wp aligned to the same rows: split_by_regime preserves order within the regulation head
vw = [r[4] for r in te if not gs(r[0]).is_overtime and gs(r[0]).period <= 4]
assert len(vw) == len(yte), f"alignment: {len(vw)} vs {len(yte)}"

def brier(ps, ys): return sum((a-b)**2 for a, b in zip(ps, ys)) / len(ys)
def clustered_diff(a, b, ys, keys):
    d = [(x-y)**2 - (z-y)**2 for x, z, y in zip(a, b, ys)]
    n = len(d); m = sum(d)/n
    from collections import defaultdict
    res, size = defaultdict(float), defaultdict(int)
    for v, k in zip(d, keys): res[k] += v-m; size[k] += 1
    G = len(res); ge = n*n/sum(c*c for c in size.values())
    se = (sum(x*x for x in res.values())**0.5)/n*(G/(G-1))**0.5
    return m, 1.96*se, G, ge

base = sum(yte)/len(yte)
print(f"\n=== HELD-OUT GAMES: {len(yte):,} plays / {len(set(gte))} games ===")
print(f"  Brier ours {brier(p, yte):.4f}   base-rate {brier([base]*len(yte), yte):.4f}   "
      f"skill {100*(1-brier(p,yte)/brier([base]*len(yte), yte)):.1f}%")
ok = [(a, b, y, g) for a, b, y, g in zip(p, vw, yte, gte) if b is not None]
if len(ok) > 1000:
    pa, pb, ya, ga = zip(*ok)
    m, h, G, ge = clustered_diff(pa, pb, ya, ga)
    print(f"  vs nflfastR vegas_wp on {len(ok):,} plays: ours {brier(pa, ya):.4f}  vegas_wp {brier(pb, ya):.4f}   "
          f"game-clustered diff {m:+.4f} [{m-h:+.4f}, {m+h:+.4f}]  G={G} G_eff={ge:.1f}  "
          f"{'OURS BETTER' if m+h < 0 else ('VEGAS_WP BETTER' if m-h > 0 else 'SPANS ZERO -- recipe reproduced')}")
print("\n=== CALIBRATION by decile ===")
from collections import defaultdict
b = defaultdict(list)
for pi, yi in zip(p, yte): b[min(9, int(pi*10))].append((pi, yi))
for k in sorted(b):
    v = b[k]
    if len(v) < 200: print(f"  {k*10:3d}-{k*10+10:3d}%  n={len(v):6,}  [THIN]"); continue
    print(f"  {k*10:3d}-{k*10+10:3d}%  n={len(v):6,}  predicted={sum(x for x,_ in v)/len(v):.3f}  "
          f"actual={sum(y for _,y in v)/len(v):.3f}  gap={sum(y for _,y in v)/len(v)-sum(x for x,_ in v)/len(v):+.3f}")

os.makedirs(os.path.dirname(ARTIFACT), exist_ok=True)
booster.save_model(ARTIFACT + ".json")
json.dump({"league": "nfl", "seasons": SEASONS, "source": "nflverse play_by_play csv.gz",
           "spread_frame": "closing_spread = -spread_line (nflfastR positive=home favoured; ours negative=home favoured), sign asserted per season",
           "train_games": len(games)-len(hold), "holdout_games": len(hold), "brier_heldout": float(round(float(brier(p, yte)), 5)),
           "monotone": json.loads(json.dumps(mono, default=lambda o: float(o) if hasattr(o, "__float__") else str(o))), "note": "Model result on held-out games. NOT edge."},
          open(ARTIFACT + ".meta.json", "w"), indent=1,
          default=lambda o: float(o) if hasattr(o, "__float__") else str(o))
log(f"saved {ARTIFACT}.json")
