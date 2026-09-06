"""Is spread_time's 0.00% importance caused by an inverted monotone constraint?

CLAIM: MONOTONE["spread_time"] = +1 forces win probability to RISE with
spread_time. But a NEGATIVE spread means FAVOURED, so after the
possession-flip on line 119 the true relationship is NEGATIVE. Under a +1
constraint every useful split violates the constraint, so xgboost never splits
on the feature -- producing exactly the 0.00% we observe, from a feature whose
values are perfectly good (125 distinct spreads, -54.5..+30.0).

TEST, on the subset where the score carries NO information (period 1, tied),
so the spread is the only thing left to learn from:
    +1 (as shipped)  ->  expected ~0%
     0 (unconstrained) -> if it jumps, the constraint was the cause
    -1 (corrected)   ->  should be usable AND correctly signed

DISCRIMINATING: if the share stays ~0 under all three, the constraint is
innocent and the fault is upstream in how the spread reaches the model.
"""
import os
import sys

import httpx

sys.path.insert(0, "/app/cfb")
import cfb_live_fv  # noqa: E402
from cfb_ingest import cfbd_row_to_state, label_pos_team_won  # noqa: E402
from cfb_train import REG_FEATURES, split_by_regime  # noqa: E402

K = os.environ["CFBD_API_KEY"]
H = {"Authorization": f"Bearer {K}"}


def get(path, **p):
    r = httpx.get(f"https://api.collegefootballdata.com/{path}",
                  params=dict(year=2024, seasonType="regular", **p),
                  headers=H, timeout=120)
    r.raise_for_status()
    return r.json()


outcome, spread = {}, {}
for wk in range(1, 9):
    for g in get("games", week=wk):
        if g.get("homePoints") is not None:
            outcome[g["id"]] = (g["homePoints"], g["awayPoints"])
    for g in get("lines", week=wk):
        d = {}
        for ln in (g.get("lines") or []):
            if ln.get("spread") is not None:
                d[(ln.get("provider") or "").replace(" ", "").lower()] = float(ln["spread"])
        if d:
            spread[g.get("id")] = d.get("draftkings", next(iter(d.values())))

rows = []
for wk in range(1, 9):
    for row in get("plays", week=wk, classification="fbs"):
        gid = row.get("gameId")
        if gid not in outcome or gid not in spread:
            continue
        try:
            st = cfbd_row_to_state(row)
        except Exception:
            continue
        hp, ap = outcome[gid]
        rows.append((st, spread[gid], label_pos_team_won(row, hp, ap), gid))

# the clean room: score identical, so score_differential/diff_time_ratio are
# constant and the spread is the ONLY feature carrying signal
sub = [r for r in rows if r[0].period == 1
       and r[0].pos_team_score == r[0].def_pos_team_score]
print(f"clean-room subset (period 1, score tied): n={len(sub)} "
      f"games={len({r[3] for r in sub})}")

st = [r[0] for r in sub]
sp = [r[1] for r in sub]
la = [r[2] for r in sub]
gr = [r[3] for r in sub]
heads = split_by_regime(st, sp, la, gr)
X, y, _, cols = heads["regulation"]

import xgboost as xgb  # noqa: E402

print("\n=== spread_time share of total gain, by its MONOTONE constraint ===")
for setting in (1, 0, -1):
    p = dict(cfb_live_fv.XGB_PARAMS)
    mono = dict(cfb_live_fv.MONOTONE)
    mono["spread_time"] = setting
    p["monotone_constraints"] = "(" + ",".join(str(mono.get(c, 0)) for c in cols) + ")"
    d = xgb.DMatrix(X, label=y, feature_names=cols, missing=float("nan"))
    b = xgb.train(p, d, num_boost_round=cfb_live_fv.XGB_ROUNDS)
    imp = b.get_score(importance_type="total_gain")
    tot = sum(imp.values()) or 1.0
    got = 100.0 * imp.get("spread_time", 0.0) / tot

    # and check the DIRECTION the fitted model actually learned
    base = list(X[0])
    i = cols.index("spread_time")
    probs = []
    for v in (-20.0, -7.0, 0.0, 7.0, 20.0):
        r = list(base)
        r[i] = v
        probs.append(float(b.predict(xgb.DMatrix([r], feature_names=cols))[0]))
    trend = ("rises with spread_time" if probs[-1] > probs[0] + 1e-6
             else "falls with spread_time" if probs[0] > probs[-1] + 1e-6
             else "flat")
    label = {1: "+1 (as shipped)", 0: " 0 (unconstrained)", -1: "-1 (corrected)"}[setting]
    print(f"  {label:20s} spread_time={got:6.2f}%   WP {trend}")
    print(f"      WP at spread_time -20/-7/0/+7/+20: "
          + " ".join(f"{x:.3f}" for x in probs))

print("\nA favoured team has a NEGATIVE spread, so the correct model must show "
      "WP FALLING as spread_time rises.")
