"""Kalshi settled-market backtest, any football series. Two pre-registered tests:
  1. pregame softness: Kalshi last pre-kickoff mid vs DK CLOSE (ESPN odds), power devig, favourite side, plus Brier vs result
  2. in-game overshoot: after a >=1c one-minute move, continuation at h=1,2,5 min; size strata >=1/2/3c at h=2
usage: kalshi_settled_backtest.py <SERIES> <espn_league_path> <schedule.json> <results.json>
Matching is by DATE (+-1 day, ET) and the market's yes_sub_title against ESPN team names, not by abbreviation.
"""
import json, subprocess, datetime as dt, re, sys
from collections import defaultdict
SERIES, LEAGUE, SCHED, OUT = sys.argv[1:5]
B = "https://api.elections.kalshi.com/trade-api/v2"
def get(url):
    out = subprocess.run(["curl","-s","--max-time","40",url], capture_output=True, text=True).stdout
    try: return json.loads(out)
    except Exception: return {}
def norm(s): return re.sub(r"[^a-z0-9]", "", (s or "").lower())
def amer_to_p(o):
    o = float(o); return 100/(o+100) if o > 0 else -o/(-o+100)
ALIAS = {"WAS": "WSH", "JAC": "JAX", "LA": "LAR"}
def canon(a): return ALIAS.get(a, a)
def power_devig(ph, pa):
    lo, hi = 0.5, 3.0
    for _ in range(60):
        k = (lo+hi)/2; lo, hi = (k, hi) if ph**k + pa**k > 1 else (lo, k)
    return ph**k, pa**k

espn = [e for e in json.load(open(SCHED)) if e["state"] == "post" and e["home_score"] is not None and e["away_score"] is not None]
by_date = defaultdict(list)
for e in espn:
    e["ko"] = dt.datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
    by_date[(e["ko"] - dt.timedelta(hours=4)).date()].append(e)
def names(e, side):
    return {norm(e.get(f"{side}_name")), norm(e.get(f"{side}_loc")), norm(e.get(f"{side}_short")), norm(e.get(side))} - {""}

km = get(f"{B}/markets?series_ticker={SERIES}&status=settled&limit=1000").get("markets", [])
print(f"{SERIES}: settled markets {len(km)}   ESPN completed games {len(espn)}")

dk_cache = {}
def dk_for(e):
    if e["id"] in dk_cache: return dk_cache[e["id"]]
    o = get(f"https://sports.core.api.espn.com/v2/sports/football/leagues/{LEAGUE}/events/{e['id']}/competitions/{e['id']}/odds?limit=3").get("items", [])
    x = next((i for i in o if (i.get("provider") or {}).get("name") == "DraftKings"), o[0] if o else None)
    res = None
    if x:
        def ml(side):
            s = x.get(side) or {}; c = (s.get("close") or {}).get("moneyLine")
            c = c.get("american") if isinstance(c, dict) else c
            return c if c is not None else s.get("moneyLine")
        hm, am = ml("homeTeamOdds"), ml("awayTeamOdds")
        if hm is not None and am is not None:
            ph, pa = amer_to_p(hm), amer_to_p(am); pw = power_devig(ph, pa)
            res = dict(prop_home=ph/(ph+pa), pow_home=pw[0], pow_away=pw[1])
    dk_cache[e["id"]] = res; return res

soft, drift, flipped, dead_book = [], {1: [], 2: [], 5: []}, [], []
no_match = no_dk = no_candles = 0; seen = set()
for m in km:
    mm = re.match(r"^" + re.escape(SERIES) + r"-(\d{2})([A-Z]{3})(\d{2})([A-Z0-9]+)-([A-Z0-9]+)$", m["ticker"])
    if not mm: no_match += 1; continue
    yy, mon, dd, _, suffix = mm.groups()
    date = dt.datetime.strptime(f"20{yy}{mon}{dd}", "%Y%b%d").date()
    sub = m.get("yes_sub_title") or ""
    team = norm(sub)
    nick = norm(sub.split()[-1]) if sub.split() else ""          # "TEN Titans" -> "titans"
    cands = [e for d_ in (date, date + dt.timedelta(days=1), date - dt.timedelta(days=1)) for e in by_date.get(d_, [])]
    hit = None
    # 1. ticker suffix == ESPN abbreviation (with the known aliases) -- what matched 49/49 on NFL
    for e in cands:
        for side in ("home", "away"):
            if canon(suffix) == (e.get(side) or "").upper():
                hit = (e, side); break
        if hit: break
    # 2. sub_title against ESPN names (CFB: "Louisville" vs "Louisville Cardinals")
    if not hit:
        for e in cands:
            for side in ("home", "away"):
                ns = names(e, side)
                if team in ns or any(len(n) >= 5 and (n in team or team in n) for n in ns):
                    hit = (e, side); break
            if hit: break
    # 3. nickname == last token of ESPN displayName ("Titans")
    if not hit and len(nick) >= 4:
        for e in cands:
            for side in ("home", "away"):
                dn = (e.get(f"{side}_name") or "").split()
                if dn and norm(dn[-1]) == nick:
                    hit = (e, side); break
            if hit: break
    if not hit: no_match += 1; continue
    e, side = hit
    dk = dk_for(e)
    if not dk: no_dk += 1; continue
    ko = e["ko"]
    s_ts, e_ts = int((ko - dt.timedelta(hours=6)).timestamp()), int((ko + dt.timedelta(hours=4)).timestamp())
    c = get(f"{B}/series/{SERIES}/markets/{m['ticker']}/candlesticks?start_ts={s_ts}&end_ts={e_ts}&period_interval=1").get("candlesticks") or []
    if not c: no_candles += 1; continue
    def mid(x):
        try: return (float(x["yes_bid"]["close_dollars"]) + float(x["yes_ask"]["close_dollars"])) / 2
        except Exception: return None
    pre = [x for x in c if x["end_period_ts"] <= ko.timestamp() and mid(x) is not None]
    if not pre: continue
    kmid = mid(pre[-1]); ksp = float(pre[-1]["yes_ask"]["close_dollars"]) - float(pre[-1]["yes_bid"]["close_dollars"])
    p_pow = dk["pow_home"] if side == "home" else dk["pow_away"]
    p_prop = dk["prop_home"] if side == "home" else 1 - dk["prop_home"]
    won = 1 if (int(e["home_score"]) > int(e["away_score"])) == (side == "home") else 0
    # SIDE-FLIP GUARD. Name containment pairs "Washington State" with Washington
    # ("washington" in "washingtonstate"), putting the underdog's 5c market under
    # the favourite's 96% line: a -90c row. Three of those made a -20c "edge" on
    # 84 heavy favourites. A correctly matched market cannot sit 60c from the
    # sharp book with a live spread, so that is the fingerprint. Excluded and
    # COUNTED, never silently dropped.
    if abs(kmid - p_pow) > 0.60 and ksp <= 0.20:
        flipped.append((m["ticker"], side, round(kmid, 2), round(p_pow, 2))); continue
    if ksp > 0.20:
        dead_book.append(m["ticker"]); continue
    soft.append(dict(game=e["id"], side=side, k_mid=kmid, k_spread=ksp, dk_pow=p_pow, dk_prop=p_prop, won=won,
                     brier_k=(kmid-won)**2, brier_dk=(p_pow-won)**2))
    if e["id"] in seen: continue
    seen.add(e["id"])
    ing = sorted((x["end_period_ts"], mid(x)) for x in c if ko.timestamp() < x["end_period_ts"] <= (ko + dt.timedelta(hours=3, minutes=40)).timestamp() and mid(x) is not None)
    mids = [v for _, v in ing]
    for i in range(1, len(mids) - 5):
        j = mids[i] - mids[i-1]
        if abs(j) < 0.01: continue
        for h in (1, 2, 5): drift[h].append((j, mids[i+h] - mids[i], e["id"]))

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

G_all = len({r["game"] for r in soft})
print(f"matched {len(soft)} markets / {G_all} games   unmatched {no_match}   no DK line {no_dk}   no candles {no_candles}")
print(f"EXCLUDED: {len(flipped)} suspected side-flips (|mid - DK| > 60c on a live book), {len(dead_book)} dead books (spread > 20c)")
for t, side, km, dk in flipped[:6]: print(f"   flip? {t} side={side} kalshi_mid={km} dk={dk}")
print(f"\n=== TEST 1: PREGAME SOFTNESS -- Kalshi last pre-kickoff mid vs DK close ===")
fav = [r for r in soft if r["dk_pow"] > 0.5]
for lab, key in (("POWER devig (primary)", "dk_pow"), ("proportional (artifact size)", "dk_prop")):
    m, h, n, G, ge = clustered([100*(r["k_mid"] - r[key]) for r in fav], [r["game"] for r in fav])
    print(f"  favourite gap, {lab:<30} {m:+.2f}c  [{m-h:+.2f}, {m+h:+.2f}]  n={n}")
pbar = sum(r["dk_pow"] for r in fav)/len(fav); sp = sum(r["k_spread"] for r in fav)/len(fav)
m, h, n, G, ge = clustered([r["brier_k"] - r["brier_dk"] for r in soft], [r["game"] for r in soft])
print(f"  Brier Kalshi {sum(r['brier_k'] for r in soft)/n:.4f} vs DK {sum(r['brier_dk'] for r in soft)/n:.4f}   diff {m:+.4f} [{m-h:+.4f}, {m+h:+.4f}]  G={G}   "
      f"{'KALSHI WORSE (soft)' if m-h > 0 else ('KALSHI BETTER' if m+h < 0 else 'spans zero -- not soft')}")
print(f"  favourites won {sum(r['won'] for r in fav)}/{len(fav)}   mean fav prob DK {pbar:.3f} / Kalshi {sum(r['k_mid'] for r in fav)/len(fav):.3f}   fav spread {100*sp:.2f}c")
# by favourite strength -- blowout lines are where CFB differs from NFL
print("  by DK favourite prob:")
for lo, hi in ((0.5, 0.7), (0.7, 0.9), (0.9, 1.01)):
    s_ = [r for r in fav if lo <= r["dk_pow"] < hi]
    if len(s_) < 10: print(f"    [{lo:.1f},{hi:.1f})  n={len(s_)}  too few"); continue
    m, h, n, G, ge = clustered([100*(r["k_mid"] - r["dk_pow"]) for r in s_], [r["game"] for r in s_])
    print(f"    [{lo:.1f},{hi:.1f})  n={n:>3}  gap {m:+.2f}c [{m-h:+.2f}, {m+h:+.2f}]   won {sum(r['won'] for r in s_)}/{n}")

print(f"\n=== TEST 2: IN-GAME DRIFT after a >=1c one-minute move, {len({g for _,_,g in drift[1]})} games ===")
print(f"  {'h(min)':>7}{'n':>8}{'beta':>9}{'95% CI':>20}{'G':>5}   {'continuation c':>15}{'95% CI':>18}")
for h in (1, 2, 5):
    ob = drift[h]
    if len(ob) < 50: print(f"  {h:>7}{len(ob):>8}  too few"); continue
    b, hb, G = slope_clustered([j for j,_,_ in ob], [d for _,d,_ in ob], [g for _,_,g in ob])
    cont, hc, n, G2, ge = clustered([100*(d if j > 0 else -d) for j, d, g in ob], [g for _,_,g in ob])
    print(f"  {h:>7}{n:>8,}{b:>+9.3f}   [{b-hb:+.3f}, {b+hb:+.3f}]{G:>5}   {cont:>+14.2f}c   [{cont-hc:+.2f}, {cont+hc:+.2f}]   {'CONTINUES' if b-hb > 0 else ('REVERTS' if b+hb < 0 else 'spans zero')}")
print(f"\n=== OVERSHOOT by shock size at h=2 (strata pre-specified) ===")
print(f"  {'|jump| >=':>10}{'n':>8}{'G':>5}   {'continuation@2min':>18}{'95% CI':>18}   {'% of jump':>10}")
for thr in (0.01, 0.02, 0.03):
    ob = [(j, d, g) for j, d, g in drift[2] if abs(j) >= thr]
    if len(ob) < 50: print(f"  {100*thr:>9.0f}c{len(ob):>8}  too few"); continue
    cont, hc, n, G, ge = clustered([100*(d if j > 0 else -d) for j, d, g in ob], [g for _,_,g in ob])
    mj = sum(abs(j) for j,_,_ in ob)/n
    print(f"  {100*thr:>9.0f}c{n:>8,}{G:>5}   {cont:>+17.2f}c   [{cont-hc:+.2f}, {cont+hc:+.2f}]   {cont/mj:>+9.1f}%")
json.dump({"soft": soft, "drift": drift}, open(OUT, "w"))
