"""Cross-venue snapshot: does the BTC arm's Kalshi-anchored rule fire on the venue's niche leagues?

For every venue league with a Kalshi twin series: pair each open game with the Kalshi event on
the same US-Eastern date (+-1) whose two team markets match BOTH venue names in full, one to one
(partial matches paired ITF doubles with singles; team CODES differ between venues -- the
venue's `prs` is Paris, Kalshi's `KPB` is Partizan -- so codes are never used). Read the venue's
winner book and, straight after, Kalshi's market for the venue's YES team; apply the rule
(Kalshi two-sided and <= 3c wide; buy the venue side where Kalshi mid - ask - fee > margin).

REST, a second or two apart per pair; mostly pregame. A scouting snapshot, not a measurement.

    python analysis/thin/cross_venue_snapshot.py [--per-league 12] [--out snapshot.json]
"""
import datetime as dt, json, math, re, sys, time, unicodedata
from collections import defaultdict
import httpx

GW = "https://gateway.polymarket.us"
KX = "https://api.elections.kalshi.com/trade-api/v2"
COEF = 0.0695
PAIRS = {
    "kbo": ["KXKBOGAME"], "npb": ["KXNPBGAME"], "eurocup": ["KXEUROCUPGAME"], "eurolg": ["KXEUROLEAGUEGAME"],
    "nbl": ["KXNBLGAME"], "jpbl": ["KXJBLEAGUEGAME"], "bbl": ["KXBBLGAME"], "vtb": ["KXVTBGAME"],
    "lnbp": ["KXLNBPGAME"], "khl": ["KXKHLGAME"], "liiga": ["KXLIIGAGAME"], "shl": ["KXSHLGAME"],
    "ufc": ["KXUFCFIGHT"], "boxing": ["KXBOXINGFIGHT"], "cs2": ["KXCS2GAME"], "dota2": ["KXDOTA2GAME"],
    "lol": ["KXLOLGAME"], "ow": ["KXOWGAME"], "valorant": ["KXVALORANTGAME"],
    "pdcdarts": ["KXDARTSMATCH"], "modus": ["KXDARTSMATCH"],
    "czechligapro": ["KXTTELITEGAME", "KXTTMATCH", "KXTABLETENNISMATCH", "KXITTFMENMATCH"],
    "setkameua": ["KXTTELITEGAME", "KXTTMATCH", "KXTABLETENNISMATCH"],
    "setkamecz": ["KXTTELITEGAME", "KXTTMATCH", "KXTABLETENNISMATCH"],
    "itfme": ["KXITFMATCH"], "itfwo": ["KXITFWMATCH"], "atp": ["KXATPMATCH", "KXATPCHALLENGERMATCH"],
    "wta": ["KXWTAMATCH", "KXWTACHALLENGERMATCH"], "prem": ["KXRUGBYGPREMMATCH"],
}
PER_LEAGUE = int(sys.argv[sys.argv.index("--per-league") + 1]) if "--per-league" in sys.argv else 12
OUT = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
h = httpx.Client(timeout=15, headers={"User-Agent": "meridian-scan/1"})


def fee(p):
    return math.ceil(round(COEF * p * (1 - p) * 100, 6)) / 100


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return [t for t in re.split(r"[^a-z0-9]+", s) if t and t not in {"fc", "the", "team", "esports", "gaming", "club", "bc", "hc"}]


def sim(a, b):
    A, B = set(norm(a)), set(norm(b))
    if not A or not B:
        return 0.0
    return len(A & B) / min(len(A), len(B))


def px(level):
    if not level:
        return None
    p = level.get("px")
    if isinstance(p, dict):
        p = p.get("value")
    try:
        return float(p)
    except (TypeError, ValueError):
        return None


def kalshi_markets(series):
    out = []
    for s in series:
        cursor = None
        for _ in range(5):
            params = {"series_ticker": s, "status": "open", "limit": 1000}
            if cursor:
                params["cursor"] = cursor
            r = h.get(f"{KX}/markets", params=params)
            if r.status_code == 429:
                time.sleep(2); continue
            r.raise_for_status()
            d = r.json()
            out += d.get("markets") or []
            cursor = d.get("cursor")
            if not cursor:
                break
        time.sleep(0.3)
    by_event = defaultdict(list)
    for m in out:
        by_event[m["event_ticker"]].append(m)
    return by_event


MON = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


def kdate(event_ticker):
    """Kalshi's event tickers carry the game's US-Eastern date: KXKBOGAME-26OCT010530... -> 2026-10-01."""
    m = re.search(r"-(\d\d)([A-Z]{3})(\d\d)", event_ticker)
    if not m or m.group(2) not in MON:
        return None
    return dt.date(2000 + int(m.group(1)), MON[m.group(2)], int(m.group(3)))


def kmid(m):
    try:
        b, a = float(m["yes_bid_dollars"]), float(m["yes_ask_dollars"])
    except (TypeError, ValueError, KeyError):
        return None, None
    if b <= 0 or a >= 1 or a <= b:
        return None, None
    return (a + b) / 2, a - b


rows = []
for league, series in PAIRS.items():
    try:
        ev = h.get(f"{GW}/v2/leagues/{league}/events", params={"limit": 200}).json().get("events") or []
    except Exception as e:  # noqa: BLE001
        print(league, "venue error", e); continue
    kev = kalshi_markets(series)
    kgames = []
    for et, ms in kev.items():
        names = [m.get("yes_sub_title") or "" for m in ms]
        kgames.append((et, ms, names))
    n_pair = n_seen = 0
    for e in ev:
        if e.get("ended") or e.get("closed"):
            continue
        ml = next((m for m in e.get("markets") or [] if str(m.get("sportsMarketType", "")).endswith("full_game_winner")
                   or m.get("marketType") == "moneyline"), None)
        if not ml:
            continue
        sides = ml.get("marketSides") or []
        yes = next((s for s in sides if s.get("long")), None)
        no = next((s for s in sides if not s.get("long")), None)
        if not yes or not no:
            continue
        yname = (yes.get("team") or {}).get("name") or yes.get("description") or ""
        nname = (no.get("team") or {}).get("name") or no.get("description") or ""
        n_seen += 1
        vdate = (dt.datetime.fromisoformat(e["startTime"].replace("Z", "+00:00")) - dt.timedelta(hours=4)).date()
        # the Kalshi event, on the same US-Eastern date (+-1), whose two team markets match both names one to one
        best = None
        for et, ms, names in kgames:
            kd = kdate(et)
            if kd is None or abs((kd - vdate).days) > 1:
                continue
            for i, nm in enumerate(names):
                sy = sim(yname, nm)
                other = [sim(nname, x) for j, x in enumerate(names) if j != i]
                so = max(other) if other else 0.0
                score = min(sy, so) - 0.01 * abs((kd - vdate).days)
                if best is None or score > best[0]:
                    best = (score, et, ms[i], nm, names)
        if not best or best[0] < 0.95:          # both names match fully; partial matches paired doubles with singles
            continue
        if n_pair >= PER_LEAGUE:
            continue
        n_pair += 1
        try:
            md = h.get(f"{GW}/v1/markets/{ml['slug']}/book").json().get("marketData") or {}
        except Exception:  # noqa: BLE001
            md = {}
        t_v = time.time()
        # re-read the Kalshi market at the same moment (the listing is minutes old by now)
        try:
            km = h.get(f"{KX}/markets/{best[2]['ticker']}").json().get("market") or best[2]
        except Exception:  # noqa: BLE001
            km = best[2]
        t_k = time.time()
        bids, offers = md.get("bids") or [], md.get("offers") or []
        vb, va = px(bids[0] if bids else None), px(offers[0] if offers else None)
        k, kw = kmid(km)
        r = {"league": league, "venue": f"{yname} v {nname}", "kalshi": " / ".join(best[4]), "k_side": best[3],
             "score": round(best[0], 2), "start": e.get("startTime"), "live": e.get("live"),
             "k_ticker": best[2]["ticker"], "v_slug": ml["slug"],
             "vb": vb, "va": va, "v_ask_qty": float(offers[0]["qty"]) if offers else None,
             "v_bid_qty": float(bids[0]["qty"]) if bids else None,
             "k_mid": k, "k_wide": kw, "k_vol": km.get("volume_fp"), "skew_s": round(t_k - t_v, 2)}
        if k is not None and vb is not None and va is not None:
            r["gap_mid"] = (vb + va) / 2 - k
            r["ev_yes"] = k - va - fee(va)
            r["ev_no"] = vb - k - fee(1 - vb)
        rows.append(r)
        time.sleep(0.35)
    print(f"{league:13s} venue games {n_seen:4d}  kalshi events {len(kev):4d}  paired (sampled) {n_pair}", flush=True)

if OUT:
    json.dump(rows, open(OUT, "w"), indent=1)
R = rows


# ---------------------------------------------------------------- per league
by = defaultdict(list)
for r in R:
    by[r["league"]].append(r)


def med(xs):
    xs = sorted(x for x in xs if x is not None)
    return xs[len(xs) // 2] if xs else None


def c(x):
    return "   -  " if x is None else f"{x * 100:5.1f}c"


print(f"{'league':9s} {'n':>3s} {'k2side':>6s} {'k<=3c':>5s} {'k wide':>7s} {'v wide':>7s} {'|gap|':>7s} "
      f"{'fires@2c':>8s} {'fires@4c':>8s} {'best ev':>8s}  size@ask")
for lg, rows in by.items():
    k2 = [r for r in rows if r.get("k_mid") is not None]
    sharp = [r for r in k2 if r["k_wide"] <= 0.0301]
    vw = [r["va"] - r["vb"] for r in rows if r.get("va") is not None and r.get("vb") is not None]
    gaps = [abs(r["gap_mid"]) for r in sharp if r.get("gap_mid") is not None]
    ev = [max(r["ev_yes"], r["ev_no"]) for r in sharp if r.get("ev_yes") is not None]
    f2 = sum(1 for e in ev if e > 0.02)
    f4 = sum(1 for e in ev if e > 0.04)
    size = med([r.get("v_ask_qty") for r in sharp])
    print(f"{lg:9s} {len(rows):3d} {len(k2):6d} {len(sharp):5d} {c(med([r['k_wide'] for r in k2])):>7s} "
          f"{c(med(vw)):>7s} {c(med(gaps)):>7s} {f2:8d} {f4:8d} {c(max(ev) if ev else None):>8s}  {size}")
print("\nrows where the 4c rule fires (Kalshi <= 3c wide):")
for r in R:
    if r.get("ev_yes") is None or r["k_wide"] > 0.0301:
        continue
    e = max(r["ev_yes"], r["ev_no"])
    if e > 0.04:
        side = "YES" if r["ev_yes"] >= r["ev_no"] else "NO"
        print(f"  {r['league']:8s} {r['venue'][:44]:44s} v {r['vb']:.2f}/{r['va']:.2f}  k mid {r['k_mid']:.3f} "
              f"(w {r['k_wide']*100:.0f}c)  buy {side} ev {e*100:+.1f}c  live={r['live']}  skew {r['skew_s']}s  {r.get('k_ticker','')}")
