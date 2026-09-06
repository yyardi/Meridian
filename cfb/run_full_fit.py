"""The real fit: CFB live win-probability, held out BY GAME, with the
corrected spread_time constraint.

HELD OUT BY GAME, NOT BY ROW. Plays inside one game share that game's single
outcome label, so a random row split puts the same game on both sides and the
model can memorise the answer. That inflates every metric and the inflation is
invisible. Games are the independent unit here for exactly the reason they are
the clustering unit in the edge harness.

WHAT THIS DOES NOT CLAIM. Beating a baseline on held-out games is a MODEL
result, not an EDGE result. Edge is measured against the contemporaneous
market mid and is blocked on a slate where the venue is not frozen. This
script deliberately does not report anything in cents.
"""
import os
import sys
import json
import math

import httpx

sys.path.insert(0, "/app/cfb")
from cfb_ingest import cfbd_row_to_state, label_pos_team_won  # noqa: E402
from cfb_train import fit, split_by_regime  # noqa: E402

K = os.environ["CFBD_API_KEY"]
H = {"Authorization": f"Bearer {K}"}
SEASONS = [2022, 2023, 2024]
WEEKS = list(range(1, 16))


def get(year, path, **p):
    for attempt in range(3):
        try:
            r = httpx.get(f"https://api.collegefootballdata.com/{path}",
                          params=dict(year=year, seasonType="regular", **p),
                          headers=H, timeout=180)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
    return []


rows = []
for year in SEASONS:
    outcome, spread = {}, {}
    for wk in WEEKS:
        for g in get(year, "games", week=wk):
            if g.get("homePoints") is not None:
                outcome[g["id"]] = (g["homePoints"], g["awayPoints"])
        for g in get(year, "lines", week=wk):
            d = {}
            for ln in (g.get("lines") or []):
                if ln.get("spread") is not None:
                    d[(ln.get("provider") or "").replace(" ", "").lower()] = float(ln["spread"])
            if d:
                spread[g.get("id")] = d.get("draftkings", next(iter(d.values())))
    n0 = len(rows)
    for wk in WEEKS:
        for cls in ("fbs", "fcs"):
            for row in get(year, "plays", week=wk, classification=cls):
                gid = row.get("gameId")
                if gid not in outcome or gid not in spread:
                    continue
                try:
                    st = cfbd_row_to_state(row)
                except Exception:
                    continue
                hp, ap = outcome[gid]
                rows.append((st, spread[gid], label_pos_team_won(row, hp, ap), gid))
    print(f"  {year}: +{len(rows) - n0:,} plays  (games with both outcome+spread: {len(set(outcome) & set(spread)):,})")

games = sorted({r[3] for r in rows})
print(f"\nTOTAL plays={len(rows):,}  games={len(games):,}")

# --- split BY GAME, deterministically (no Math.random equivalent needed) --- #
holdout = {g for i, g in enumerate(games) if i % 5 == 0}     # 20% of GAMES
tr = [r for r in rows if r[3] not in holdout]
te = [r for r in rows if r[3] in holdout]
print(f"train: {len(tr):,} plays / {len(games) - len(holdout):,} games")
print(f"test : {len(te):,} plays / {len(holdout):,} games  (DISJOINT games)")

heads = split_by_regime([r[0] for r in tr], [r[1] for r in tr],
                        [r[2] for r in tr], [r[3] for r in tr])
for name, d in heads.items():
    print(f"  head {name}: {len(d[0]):,} rows")

booster, predict, mono = fit(heads["regulation"])
print(f"\nMONOTONICITY: {mono}")

imp = booster.get_score(importance_type="total_gain")
tot = sum(imp.values()) or 1.0
print("\n=== feature importance (total gain) ===")
for f, v in sorted(imp.items(), key=lambda kv: -kv[1]):
    print(f"  {f:26s} {100.0 * v / tot:6.2f}%")

# --- score the held-out GAMES ------------------------------------------- #
th = split_by_regime([r[0] for r in te], [r[1] for r in te],
                     [r[2] for r in te], [r[3] for r in te])
Xte, yte, gte, cols = th["regulation"]
p = predict(Xte)

brier = sum((pi - yi) ** 2 for pi, yi in zip(p, yte)) / len(yte)
base = sum(yte) / len(yte)
brier_base = sum((base - yi) ** 2 for yi in yte) / len(yte)
ll = -sum(yi * math.log(max(pi, 1e-9)) + (1 - yi) * math.log(max(1 - pi, 1e-9))
          for pi, yi in zip(p, yte)) / len(yte)
acc = sum(1 for pi, yi in zip(p, yte) if (pi >= 0.5) == (yi == 1)) / len(yte)
print(f"\n=== HELD-OUT GAMES (n={len(yte):,} plays / {len(set(gte)):,} games) ===")
print(f"  Brier         {brier:.4f}   (always-base-rate: {brier_base:.4f})")
print(f"  log loss      {ll:.4f}")
print(f"  accuracy      {acc * 100:.1f}%")
print(f"  skill vs base {100.0 * (1 - brier / brier_base):.1f}%")

# --- calibration, stratified. NEVER pooled (blowouts are a third of volume) #
print("\n=== CALIBRATION by predicted-probability decile ===")
buckets = {}
for pi, yi in zip(p, yte):
    b = min(9, int(pi * 10))
    buckets.setdefault(b, []).append((pi, yi))
for b in sorted(buckets):
    v = buckets[b]
    if len(v) < 200:
        print(f"  {b * 10:3d}-{b * 10 + 10:3d}%  n={len(v):6,}  [THIN - not a verdict]")
        continue
    pm = sum(x for x, _ in v) / len(v)
    am = sum(y for _, y in v) / len(v)
    print(f"  {b * 10:3d}-{b * 10 + 10:3d}%  n={len(v):6,}  predicted={pm:.3f}  actual={am:.3f}  gap={am - pm:+.3f}")

os.makedirs("/app/artifacts", exist_ok=True)
booster.save_model("/app/artifacts/cfb_wp_regulation.json")
meta = {
    "seasons": SEASONS,
    "train_games": len(games) - len(holdout),
    "test_games": len(holdout),
    "brier_heldout": round(brier, 5),
    "spread_bridge": "UNVERIFIED (n=19 < 30)",
    "note": "Model result on held-out GAMES. NOT an edge result: edge is "
            "measured against the contemporaneous market mid and is blocked "
            "on an unfrozen venue.",
}
with open("/app/artifacts/cfb_wp_regulation.meta.json", "w") as f:
    json.dump(meta, f, indent=2)
print("\nartifact written, TAGGED spread_bridge=UNVERIFIED (serve path must refuse it)")
