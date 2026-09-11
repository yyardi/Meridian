"""Pregame softness, Polymarket US leg. Public gateway, no credentials, no prod.
Venue winner-market mid (YES = first team on the slug = AWAY wins, 196/196
verified) vs DraftKings moneyline devigged two ways. Favourite side reported.
The venue's MAKER fee is zero and its taker fee 0.06*p*(1-p) (~1.5c at 0.5), so
unlike Kalshi a gap here has a cheap way to be expressed -- IF it exists."""
import json, urllib.request, datetime as dt, re, csv, sys, time
def get(url):
    # urllib, not curl: the trainer image on prod has no curl and the weekend
    # cron runs these there. A failed fetch is an empty dict, as before.
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=30) as r:
            out = r.read().decode("utf-8", "replace")
    except Exception:
        return {}
    return json.loads(out) if out else {}
now = dt.datetime.now(dt.timezone.utc)
def norm(s): return re.sub(r"[^a-z0-9]", "", (s or "").lower())
def amer_to_p(o):
    o = float(o); return 100/(o+100) if o > 0 else -o/(-o+100)
def power_devig(ph, pa):
    lo, hi = 0.5, 3.0
    for _ in range(60):
        k = (lo+hi)/2; lo, hi = (k, hi) if ph**k + pa**k > 1 else (lo, k)
    return ph**k, pa**k
def q(x):
    if x is None: return None
    if isinstance(x, dict): x = x.get("price", x.get("value"))
    try: return float(x)
    except: return None

# DraftKings via ESPN, keyed by (away_abbr, home_abbr) and by names
dk = []
for i in range(0, 8):
    d = (now + dt.timedelta(days=i)).strftime("%Y%m%d")
    for e in get(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates={d}&limit=100").get("events", []):
        c = e["competitions"][0]; t = {x["homeAway"]: x["team"] for x in c["competitors"]}
        odds = get(f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/events/{e['id']}/competitions/{e['id']}/odds?limit=3").get("items", [])
        o = next((o for o in odds if (o.get("provider") or {}).get("name") == "DraftKings"), odds[0] if odds else None)
        if not o: continue
        hm, am = (o.get("homeTeamOdds") or {}).get("moneyLine"), (o.get("awayTeamOdds") or {}).get("moneyLine")
        if hm is None or am is None: continue
        ph, pa = amer_to_p(hm), amer_to_p(am)
        dk.append(dict(id=e["id"], home=t["home"], away=t["away"], ml_home=hm, ml_away=am,
                       prop_home=ph/(ph+pa), prop_away=pa/(ph+pa), pow_home=power_devig(ph,pa)[0], pow_away=power_devig(ph,pa)[1]))
print(f"DK lines: {len(dk)} games")

# venue winner markets via the public gateway
evs = get("https://gateway.polymarket.us/v2/leagues/nfl/events?limit=60").get("events", [])
print(f"venue NFL events: {len(evs)}")
rows = []
for e in evs:
    win = [m for m in (e.get("markets") or []) if (m.get("sportsMarketType") or "") == "football_team_full_game_winner"]
    if not win: continue
    m = win[0]; bid, ask = q(m.get("bestBidQuote")), q(m.get("bestAskQuote"))
    if bid is None or ask is None or ask <= bid: continue
    parts = e.get("participants") or []
    # slug nfl-<away>-<home>-<date>
    mm = re.match(r"^(?:[a-z]+-)?nfl-([a-z0-9]+)-([a-z0-9]+)-(\d{4}-\d{2}-\d{2})", e.get("slug",""))
    if not mm: continue
    away_ab, home_ab = mm.group(1), mm.group(2)
    hit = None
    for g in dk:
        gh, ga = g["home"], g["away"]
        ok_home = norm(gh.get("abbreviation")) == home_ab or any(norm(p.get("name") or p.get("shortName") or "") and norm(p.get("name") or "") in {norm(gh.get(k)) for k in ("displayName","name","location")} for p in parts)
        ok_away = norm(ga.get("abbreviation")) == away_ab
        if norm(gh.get("abbreviation")) == home_ab and norm(ga.get("abbreviation")) == away_ab: hit = g; break
        # loose: team display names inside the event title
        title = norm(e.get("title",""))
        if norm(gh.get("displayName")) in title and norm(ga.get("displayName")) in title: hit = g; break
    if not hit: 
        print(f"  unmatched venue event {e.get('slug')} ({e.get('title')})"); continue
    mid_away = (bid+ask)/2                       # YES = away wins
    mid_home = 1 - mid_away
    for side, mid, prop, pw, ml in (("home", mid_home, hit["prop_home"], hit["pow_home"], hit["ml_home"]),
                                     ("away", mid_away, hit["prop_away"], hit["pow_away"], hit["ml_away"])):
        rows.append(dict(ts=now.isoformat(timespec="seconds"), venue="polymarket_us", slug=m.get("slug"), side=side,
                         team=(hit["home"] if side=="home" else hit["away"]).get("abbreviation"), espn_event=hit["id"],
                         kickoff=m.get("gameStartTime") or e.get("endDate"), dk_ml=ml, dk_prop=round(prop,4), dk_pow=round(pw,4),
                         v_bid=bid, v_ask=ask, v_mid=round(mid,4), v_spread_c=round(100*(ask-bid),1),
                         gap_prop_c=round(100*(mid-prop),2), gap_pow_c=round(100*(mid-pw),2), fee_coef=m.get("feeCoefficient")))
print(f"matched: {len(rows)//2} games\n")
print(f"  {'slug':<34}{'side':<5}{'DK ml':>7}{'prop':>7}{'pow':>7}{'V mid':>7}{'spr':>5}{'gap_prop':>9}{'gap_pow':>8}")
for r in sorted(rows, key=lambda r: (r["kickoff"], r["slug"], r["side"])):
    print(f"  {r['slug']:<34}{r['side']:<5}{r['dk_ml']:>+7}{r['dk_prop']:>7.3f}{r['dk_pow']:>7.3f}{r['v_mid']:>7.3f}{r['v_spread_c']:>5.1f}{r['gap_prop_c']:>+9.2f}{r['gap_pow_c']:>+8.2f}")
fav = [r for r in rows if r["dk_prop"] > 0.5]
if len(fav) >= 5:
    def stats(v):
        n=len(v); m=sum(v)/n; sd=(sum((x-m)**2 for x in v)/(n-1))**0.5; return m, 1.96*sd/n**.5, n
    for lab, key in (("PROPORTIONAL devig", "gap_prop_c"), ("POWER devig", "gap_pow_c")):
        m, h, n = stats([r[key] for r in fav])
        print(f"\n  favourite side, n={n}: venue mid - DK prob, {lab}: {m:+.2f}c  95% ~[{m-h:+.2f}, {m+h:+.2f}]")
    sp = sum(r["v_spread_c"] for r in fav)/len(fav); fc = fav[0]["fee_coef"]
    print(f"  venue favourite spread mean {sp:.2f}c   taker fee at p~0.6 with coef {fc}: ~{100*float(fc or 0.06)*0.6*0.4:.2f}c   maker fee: 0")
    print("  A gap that survives POWER devig AND exceeds half the spread is one a maker could sit on for free.")
    with open(sys.argv[1], "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader() if fh.tell() == 0 else None; w.writerows(rows)
    print(f"  snapshot appended to {sys.argv[1]}")
