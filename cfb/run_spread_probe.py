"""Why is spread_time 0.04% when the published recipe calls it decisive?

HYPOTHESIS: our sample is dominated by plays where the SCORE already encodes
what the spread would have told us. nflfastR's 27%->23% gain was measured over
whole games including the opening drives, where the score is 0-0 and the
pregame line is the only information that exists.

THE TEST: fit the same model on early / level-score subsets and watch
spread_time's share of total gain.
  * If it rises, the feature is fine and the pooled 0.04% was a sampling
    artefact -- the aggregate invented a shape (a known failure here).
  * If it stays ~0 everywhere, the spread is not reaching the model and the
    whole fit is suspect, because the recipe's single most valuable feature
    would be inert.
"""
import os
import sys

import httpx

sys.path.insert(0, "/app/cfb")
from cfb_ingest import cfbd_row_to_state, label_pos_team_won  # noqa: E402
from cfb_train import fit, split_by_regime  # noqa: E402

K = os.environ["CFBD_API_KEY"]
H = {"Authorization": f"Bearer {K}"}
YEAR, WEEKS = 2024, list(range(1, 9))


def get(path, **p):
    r = httpx.get(f"https://api.collegefootballdata.com/{path}",
                  params=dict(year=YEAR, seasonType="regular", **p),
                  headers=H, timeout=120)
    r.raise_for_status()
    return r.json()


outcome, spread = {}, {}
for wk in WEEKS:
    for g in get("games", week=wk):
        if g.get("homePoints") is not None:
            outcome[g["id"]] = (g["homePoints"], g["awayPoints"])
    for g in get("lines", week=wk):
        d = {}
        for line in (g.get("lines") or []):
            if line.get("spread") is not None:
                # normalise "Draft Kings" / "DraftKings" -- they are one book
                d[(line.get("provider") or "").replace(" ", "").lower()] = float(line["spread"])
        if d:
            spread[g.get("id")] = d.get("draftkings", next(iter(d.values())))

rows = []
for wk in WEEKS:
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

print(f"usable plays={len(rows)}  games={len({r[3] for r in rows})}")
print(f"distinct spreads={len({r[1] for r in rows})}  "
      f"range=[{min(r[1] for r in rows):+.1f}, {max(r[1] for r in rows):+.1f}]")


def share(subset, name):
    # rule 22: a subset too small to fit prints why, never a bare number
    if len(subset) < 500:
        print(f"  {name:28s} n={len(subset):6d}   TOO FEW - refusing to report")
        return
    st = [r[0] for r in subset]
    sp = [r[1] for r in subset]
    la = [r[2] for r in subset]
    gr = [r[3] for r in subset]
    heads = split_by_regime(st, sp, la, gr)
    if "regulation" not in heads:
        print(f"  {name:28s} no regulation rows")
        return
    booster, _, _ = fit(heads["regulation"])
    imp = booster.get_score(importance_type="total_gain")
    tot = sum(imp.values()) or 1.0
    print(f"  {name:28s} n={len(subset):6d}   "
          f"spread_time={100.0 * imp.get('spread_time', 0.0) / tot:6.2f}%   "
          f"score_diff={100.0 * imp.get('score_differential', 0.0) / tot:5.1f}%   "
          f"diff_time_ratio={100.0 * imp.get('diff_time_ratio', 0.0) / tot:5.1f}%")


print("\n=== spread_time share of total gain, BY GAME PHASE ===")
share(rows, "ALL plays (the 0.04% one)")
share([r for r in rows if r[0].period == 1], "period 1 only")
share([r for r in rows if r[0].pos_team_score == r[0].def_pos_team_score],
      "score still TIED")
share([r for r in rows if r[0].period == 1
       and r[0].pos_team_score == r[0].def_pos_team_score],
      "period 1 AND tied")
