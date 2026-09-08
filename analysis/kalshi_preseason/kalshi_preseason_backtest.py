"""Kalshi NFL 2026 PRESEASON, 49 settled games: two pre-registered tests, no prod.

POPULATION, stated first: preseason. Starters sit, books are softest, retail is
thinnest. A negative here is a strong negative (if a venue is not soft against
DK when DK is least sharp, it will not be soft in September). A positive does
NOT transfer to the regular season without re-testing there.

TEST 1 -- PREGAME SOFTNESS. Kalshi's last pre-kickoff mid vs DraftKings' CLOSING
moneyline (ESPN odds .close), devigged by the POWER method (proportional devig
manufactured a +1c artifact on week 1). Favourite side. Plus Brier of Kalshi mid
vs Brier of DK prob against the actual result, game-clustered (49 clusters).
  Edge exists if: favourite gap excludes zero AND exceeds the Kalshi taker fee
  (~0.07*p*(1-p)), OR Kalshi's Brier is worse than DK's with the interval
  excluding zero. Otherwise: not soft.

TEST 2 -- IN-GAME DRIFT on a dense venue tape. 1-minute mids from kickoff to
kickoff+3h40m. After a 1-min move of >= 1c, does the next h minutes continue
(beta > 0), revert (< 0), or nothing? h in {1, 2, 5}. Same design as the CFB
run, but with 741/755 minutes traded there is no recorder gap and no
"next play arrived" censoring -- this is what the venue itself does minute to
minute. Also: fraction of the eventual 5-min move realised in the first minute.
"""
import json, subprocess, datetime as dt, re, sys, math
from collections import defaultdict
B = "https://api.elections.kalshi.com/trade-api/v2"
def get(url):
    out = subprocess.run(["curl","-s","--max-time","40",url], capture_output=True, text=True).stdout
    try: return json.loads(out)
    except Exception: return {}
def amer_to_p(o):
    o = float(o); return 100/(o+100) if o > 0 else -o/(-o+100)
def power_devig(ph, pa):
    lo, hi = 0.5, 3.0
    for _ in range(60):
        k = (lo+hi)/2; lo, hi = (k, hi) if ph**k + pa**k > 1 else (lo, k)
    return ph**k, pa**k
ALIAS = {"WAS": "WSH", "JAC": "JAX", "LA": "LAR"}
def canon(a): return ALIAS.get(a, a)

espn = json.load(open(sys.argv[1]))
espn = [e for e in espn if e["state"] == "post" and e["home_score"] is not None]
by_date = defaultdict(list)
for e in espn:
    ko = dt.datetime.fromisoformat(e["date"].replace("Z", "+00:00")); e["ko"] = ko
    et = (ko - dt.timedelta(hours=4)).date()          # ET game date, matches Kalshi's ticker date
    by_date[et].append(e)

km = get(f"{B}/markets?series_ticker=KXNFLGAME&status=settled&limit=1000").get("markets", [])
print(f"Kalshi settled markets {len(km)}   ESPN completed preseason games {len(espn)}")

# DK closing moneyline per game (one call per game)
dk = {}
for e in espn:
    o = get(f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/events/{e['id']}/competitions/{e['id']}/odds?limit=3").get("items", [])
    x = next((i for i in o if (i.get("provider") or {}).get("name") == "DraftKings"), o[0] if o else None)
    if not x: continue
    def ml(side):
        s = x.get(side) or {}; c = (s.get("close") or {}).get("moneyLine")
        c = c.get("american") if isinstance(c, dict) else c
        return c if c is not None else s.get("moneyLine")
    hm, am = ml("homeTeamOdds"), ml("awayTeamOdds")
    if hm is None or am is None: continue
    ph, pa = amer_to_p(hm), amer_to_p(am); pw = power_devig(ph, pa)
    dk[e["id"]] = dict(ml_home=hm, ml_away=am, prop_home=ph/(ph+pa), pow_home=pw[0], pow_away=pw[1])
print(f"DK closing lines found: {len(dk)}")

soft, drift_obs, no_match, no_candles = [], {1: [], 2: [], 5: []}, 0, 0
seen_games = set()
for m in km:
    mm = re.match(r"^KXNFLGAME-(\d{2})([A-Z]{3})(\d{2})([A-Z]+)-([A-Z]+)$", m["ticker"])
    if not mm: continue
    yy, mon, dd, teams, team = mm.groups()
    date = dt.datetime.strptime(f"20{yy}{mon}{dd}", "%Y%b%d").date()
    cands = [e for d_ in (date, date + dt.timedelta(days=1), date - dt.timedelta(days=1)) for e in by_date.get(d_, [])]
    e = next((e for e in cands if canon(team) in (e["home"], e["away"])), None)
    if e is None or e["id"] not in dk: no_match += 1; continue
    side = "home" if canon(team) == e["home"] else "away"
    ko = e["ko"]
    s_ts, e_ts = int((ko - dt.timedelta(hours=6)).timestamp()), int((ko + dt.timedelta(hours=4)).timestamp())
    c = get(f"{B}/series/KXNFLGAME/markets/{m['ticker']}/candlesticks?start_ts={s_ts}&end_ts={e_ts}&period_interval=1").get("candlesticks") or []
    if not c: no_candles += 1; continue
    def mid(x):
        try: return (float(x["yes_bid"]["close_dollars"]) + float(x["yes_ask"]["close_dollars"])) / 2
        except Exception: return None
    pre = [x for x in c if x["end_period_ts"] <= ko.timestamp() and mid(x) is not None]
    if not pre: continue
    kmid = mid(pre[-1]); kspread = float(pre[-1]["yes_ask"]["close_dollars"]) - float(pre[-1]["yes_bid"]["close_dollars"])
    p_dk = dk[e["id"]]["pow_home"] if side == "home" else dk[e["id"]]["pow_away"]
    p_prop = dk[e["id"]]["prop_home"] if side == "home" else 1 - dk[e["id"]]["prop_home"]
    won = 1 if (int(e["home_score"]) > int(e["away_score"])) == (side == "home") else 0
    soft.append(dict(game=e["id"], team=team, side=side, k_mid=kmid, k_spread=kspread, dk_pow=p_dk, dk_prop=p_prop, won=won,
                     brier_k=(kmid-won)**2, brier_dk=(p_dk-won)**2))
    # TEST 2: in-game 1-min mids, ONE market per game (the first seen) to avoid double-counting mirrored series
    if e["id"] in seen_games: continue
    seen_games.add(e["id"])
    ing = [(x["end_period_ts"], mid(x)) for x in c if ko.timestamp() < x["end_period_ts"] <= (ko + dt.timedelta(hours=3, minutes=40)).timestamp() and mid(x) is not None]
    ing.sort()
    mids = [v for _, v in ing]
    for i in range(1, len(mids) - 5):
        jump = mids[i] - mids[i-1]
        if abs(jump) < 0.01: continue
        for h in (1, 2, 5):
            drift_obs[h].append((jump, mids[i+h] - mids[i], e["id"]))

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
    e = [c - my - b*(a-mx) for a, c in zip(x, y)]
    g = defaultdict(float)
    for a, ei, k in zip(x, e, keys): g[k] += (a-mx)*ei
    G = len(g); se = (sum(v*v for v in g.values())**0.5)/sxx*(G/(G-1))**0.5
    return b, 1.96*se, G

print(f"\nmatched Kalshi markets {len(soft)} ({len({r['game'] for r in soft})} games)   unmatched {no_match}   no candles {no_candles}")
print("\n=== TEST 1: PREGAME SOFTNESS, Kalshi last pre-kickoff mid vs DK close, preseason ===")
fav = [r for r in soft if r["dk_pow"] > 0.5]
for lab, key in (("POWER devig (primary)", "dk_pow"), ("proportional (for the artifact size)", "dk_prop")):
    m, h, n, G, ge = clustered([100*(r["k_mid"] - r[key]) for r in fav], [r["game"] for r in fav])
    print(f"  favourite gap, {lab:<38} {m:+.2f}c  [{m-h:+.2f}, {m+h:+.2f}]  n={n} games")
sp = sum(r["k_spread"] for r in fav)/len(fav); pbar = sum(r["dk_pow"] for r in fav)/len(fav)
print(f"  Kalshi favourite spread at close: {100*sp:.2f}c   taker fee at p={pbar:.2f}: ~{100*0.07*pbar*(1-pbar):.2f}c")
m, h, n, G, ge = clustered([r["brier_k"] - r["brier_dk"] for r in soft], [r["game"] for r in soft])
print(f"  Brier Kalshi {sum(r['brier_k'] for r in soft)/len(soft):.4f}  vs  DK power {sum(r['brier_dk'] for r in soft)/len(soft):.4f}   "
      f"diff {m:+.4f} [{m-h:+.4f}, {m+h:+.4f}]  G={G}   {'KALSHI WORSE (soft)' if m-h > 0 else ('KALSHI BETTER' if m+h < 0 else 'spans zero -- not soft')}")
print(f"  favourites won {sum(r['won'] for r in fav)}/{len(fav)}   mean DK fav prob {pbar:.3f}   mean Kalshi fav mid {sum(r['k_mid'] for r in fav)/len(fav):.3f}")

print("\n=== TEST 2: IN-GAME DRIFT on Kalshi 1-min mids, after a >=1c one-minute move ===")
print(f"  {'h(min)':>7}{'n':>8}{'beta':>9}{'95% CI':>20}{'G':>5}   {'continuation c':>15}{'95% CI':>18}")
for h in (1, 2, 5):
    ob = drift_obs[h]
    if len(ob) < 50: print(f"  {h:>7}{len(ob):>8}  too few"); continue
    b, hb, G = slope_clustered([j for j, _, _ in ob], [d for _, d, _ in ob], [g for _, _, g in ob])
    cont, hc, n, G2, ge = clustered([100*(d if j > 0 else -d) for j, d, g in ob], [g for _, _, g in ob])
    print(f"  {h:>7}{n:>8,}{b:>+9.3f}   [{b-hb:+.3f}, {b+hb:+.3f}]{G:>5}   {cont:>+14.2f}c   [{cont-hc:+.2f}, {cont+hc:+.2f}]   "
          f"{'CONTINUES' if b-hb > 0 else ('REVERTS' if b+hb < 0 else 'spans zero')}")
print("  beta<0 = the venue overshoots and comes back within h minutes (a maker fades it); beta>0 = it keeps going (a follower rides it).")
print("\n=== ROBUSTNESS: does the h=2 reversal SCALE with shock size? strata pre-specified ===")
print(f"  {'|jump| >=':>10}{'n':>8}{'G':>5}   {'continuation@2min':>18}{'95% CI':>18}   {'as % of jump':>13}")
for thr in (0.01, 0.02, 0.03):
    ob = [(j, d, g) for j, d, g in drift_obs[2] if abs(j) >= thr]
    if len(ob) < 50: print(f"  {100*thr:>9.0f}c{len(ob):>8}  too few"); continue
    cont, hc, n, G, ge = clustered([100*(d if j > 0 else -d) for j, d, g in ob], [g for _, _, g in ob])
    mj = sum(abs(j) for j, _, _ in ob)/n
    print(f"  {100*thr:>9.0f}c{n:>8,}{G:>5}   {cont:>+17.2f}c   [{cont-hc:+.2f}, {cont+hc:+.2f}]   {100*cont/(100*mj):>+12.1f}%")
print("  A real overshoot reverts a roughly constant FRACTION of the shock; noise does not scale.")
json.dump({"soft": soft, "drift": {h: v for h, v in drift_obs.items()}}, open(sys.argv[2], "w"))
