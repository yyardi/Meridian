"""Pregame softness, Kalshi leg: is a liquid venue's pregame NFL price soft
against the sharp book? DraftKings moneyline (via ESPN, public) devigged
two-way vs Kalshi YES mid, per team, week 1. Snapshot with UTC timestamp;
scored after settlement. No lag anywhere in this: both are pregame quotes."""
import json, urllib.request, datetime as dt, re, sys, csv
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

# ESPN NFL events, next 8 days, with DK moneylines
events = []
for i in range(0, 8):
    d = (now + dt.timedelta(days=i)).strftime("%Y%m%d")
    for e in get(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates={d}&limit=100").get("events", []):
        c = e["competitions"][0]; teams = {x["homeAway"]: x["team"] for x in c["competitors"]}
        odds = get(f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/events/{e['id']}/competitions/{e['id']}/odds?limit=3").get("items", [])
        dk = next((o for o in odds if (o.get("provider") or {}).get("name") == "DraftKings"), odds[0] if odds else None)
        if not dk: continue
        hm, am = (dk.get("homeTeamOdds") or {}).get("moneyLine"), (dk.get("awayTeamOdds") or {}).get("moneyLine")
        if hm is None or am is None: continue
        ph, pa = amer_to_p(hm), amer_to_p(am); s = ph + pa
        events.append(dict(id=e["id"], date=e["date"], home=teams["home"], away=teams["away"],
                           ml_home=hm, ml_away=am, vig=s-1, p_home=ph/s, p_away=pa/s, spread=dk.get("spread")))
print(f"ESPN NFL events with DK moneyline: {len(events)}")

# Kalshi NFL game markets
km = get("https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker=KXNFLGAME&status=open&limit=1000").get("markets", [])
print(f"Kalshi KXNFLGAME open markets: {len(km)}")
def f(x,k):
    try: return float(x.get(k))
    except: return None

rows = []
for m in km:
    team = m.get("yes_sub_title") or ""
    bid, ask = f(m,"yes_bid_dollars"), f(m,"yes_ask_dollars")
    if bid is None or ask is None: continue
    # match to an ESPN event: the Kalshi team name must hit one side, and the event title the other
    hit = None
    for e in events:
        for side in ("home","away"):
            t = e[side]; names = {norm(t.get(k)) for k in ("displayName","shortDisplayName","name","location","abbreviation") if t.get(k)}
            if norm(team) in names or any(n and (n in norm(team) or norm(team) in n) for n in names if len(n) >= 4):
                other = e["away" if side=="home" else "home"]
                onames = {norm(other.get(k)) for k in ("displayName","shortDisplayName","name","location","abbreviation") if other.get(k)}
                if any(n and n in norm(m.get("title","")+m.get("event_ticker","")) for n in onames if len(n) >= 3) or norm(other.get("abbreviation","")) in norm(m.get("event_ticker","")):
                    hit = (e, side); break
        if hit: break
    if not hit: continue
    e, side = hit
    p_dk = e["p_home"] if side == "home" else e["p_away"]
    mid = (bid+ask)/2
    rows.append(dict(ts=now.isoformat(timespec="seconds"), kalshi=m["ticker"], team=team, side=side, espn_event=e["id"],
                     kickoff=e["date"], dk_ml=(e["ml_home"] if side=="home" else e["ml_away"]), dk_prob=round(p_dk,4),
                     k_bid=bid, k_ask=ask, k_mid=round(mid,4), k_spread_c=round(100*(ask-bid),1),
                     gap_c=round(100*(mid-p_dk),2), vol=f(m,"volume_fp")))
rows.sort(key=lambda r: r["kickoff"])
print(f"matched Kalshi markets to DK lines: {len(rows)}\n")
print(f"  {'kalshi ticker':<34}{'side':<5}{'DK ml':>7}{'DK p':>7}{'K mid':>7}{'spr':>5}{'gap c':>7}{'vol':>9}")
for r in rows:
    print(f"  {r['kalshi']:<34}{r['side']:<5}{r['dk_ml']:>+7}{r['dk_prob']:>7.3f}{r['k_mid']:>7.3f}{r['k_spread_c']:>5.1f}{r['gap_c']:>+7.2f}{r['vol']:>9.0f}")
if rows:
    g = [r["gap_c"] for r in rows]; n=len(g); m=sum(g)/n; sd=(sum((x-m)**2 for x in g)/(n-1))**0.5
    fav = [r["gap_c"] for r in rows if r["dk_prob"] > 0.5]; dog = [r["gap_c"] for r in rows if r["dk_prob"] <= 0.5]
    print(f"\n  gap = Kalshi mid - DK devigged prob, cents.  n={n}  mean {m:+.2f}c  sd {sd:.2f}  |gap|>=2c: {sum(1 for x in g if abs(x)>=2)}")
    print(f"  favourites (DK p>0.5): mean gap {sum(fav)/len(fav):+.2f}c (n={len(fav)})   underdogs: {sum(dog)/len(dog):+.2f}c (n={len(dog)})")
    print("  + means Kalshi prices the team HIGHER than DK. Bartlett-O'Hara predicts retail overbets favourites/YES.")
    print("  Each game contributes two rows that sum to ~0 by construction; the FAVOURITE row is the informative one.")
    with open(sys.argv[1], "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); 
        if fh.tell() == 0: w.writeheader()
        w.writerows(rows)
    print(f"  snapshot appended to {sys.argv[1]}")
