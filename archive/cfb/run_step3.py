"""Step 3: is the timeout feature worth its machinery?

Low importance -> drop it from BOTH sides: that retires the degrade-the-
training-data path AND recovers the plays refused for a missing
defenseTimeouts. High importance -> the degraded-training fix is mandatory
rather than tidy. Either way it is one number that decides a design choice,
taken BEFORE the fit rather than after.
"""
import os, sys, httpx, collections
sys.path.insert(0, "/app/cfb")
from cfb_ingest import cfbd_row_to_state, label_pos_team_won, MissingField
from cfb_train import split_by_regime, fit, REG_FEATURES

K = os.environ["CFBD_API_KEY"]; H = {"Authorization": f"Bearer {K}"}
YEAR, WEEKS = 2024, list(range(1, 9))

def get(path, **p):
    r = httpx.get(f"https://api.collegefootballdata.com/{path}",
                  params=dict(year=YEAR, seasonType="regular", **p),
                  headers=H, timeout=120)
    r.raise_for_status(); return r.json()

outcome, spread = {}, {}
for wk in WEEKS:
    for g in get("games", week=wk):
        if g.get("homePoints") is not None:
            outcome[g["id"]] = (g["homePoints"], g["awayPoints"])
    for g in get("lines", week=wk):
        d = {}
        for l in (g.get("lines") or []):
            if l.get("spread") is not None:
                d[(l.get("provider") or "").replace(" ", "").lower()] = float(l["spread"])
        if d: spread[g.get("id")] = d.get("draftkings", next(iter(d.values())))
print(f"games with outcome={len(outcome)}  with spread={len(spread)}")

states, spreads, labels, groups = [], [], [], []
refused = collections.Counter()
for wk in WEEKS:
    for row in get("plays", week=wk, classification="fbs"):
        gid = row.get("gameId")
        if gid not in outcome or gid not in spread:
            refused["no outcome or spread"] += 1; continue
        try:
            st = cfbd_row_to_state(row)
        except MissingField as e:
            refused[str(e).split("'")[1]] += 1; continue
        except Exception as e:
            refused[type(e).__name__] += 1; continue
        hp, ap = outcome[gid]
        states.append(st); spreads.append(spread[gid])
        labels.append(label_pos_team_won(row, hp, ap)); groups.append(gid)
print(f"usable plays={len(states)}  games={len(set(groups))}  refused={dict(refused)}")

heads = split_by_regime(states, spreads, labels, groups)
for name, d in heads.items():
    print(f"  head {name}: {len(d[0])} rows, {len(d[3])} features")

booster, predict, mono = fit(heads["regulation"])
print(f"\nMONOTONICITY ASSERTION PASSED -- {mono}")

print("\n=== FEATURE IMPORTANCE (regulation head, total gain) ===")
imp = booster.get_score(importance_type="total_gain")
tot = sum(imp.values()) or 1.0
for f, v in sorted(imp.items(), key=lambda kv: -kv[1]):
    star = "  <== TIMEOUTS" if "timeout" in f else ""
    print(f"  {f:26s} {100.0*v/tot:6.2f}%{star}")
missing = [f for f in REG_FEATURES if f not in imp]
if missing: print(f"  (never split on: {missing})")
to = sum(v for f, v in imp.items() if "timeout" in f)
print(f"\n>> TIMEOUTS COMBINED: {100.0*to/tot:.2f}% of total gain")
