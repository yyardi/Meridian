"""In-play: the BTC arm's rule (Kalshi mid vs the venue's touch) on taped thin-league games.

Every 3 s of live play: Kalshi's touch on the venue-YES team's market (tape, polled every 10 s,
a line per change) and the venue's winner book (stream). If Kalshi is two-sided and <= 3c wide
and p - ask - fee beats the margin on either side, buy that side at the venue's ask; one entry
per game per 60 s. Scored three ways: mark-out to the venue mid at +60 s and +300 s, and held to
the result. Instants where the venue book has not pushed for > 30 s are skipped (stalled stream).
Control beside it: a seeded coin's side every 60 s of live play, scored the same way.

The venue's YES team is paired with Kalshi's market by EXACT team name (the tape's `team`
against the venue event's long side); codes are never used -- the venue's `prs` is Paris and
Kalshi's `KPB` is Partizan. Kalshi is polled every 10 s, so its mid can be up to 10 s stale:
this tests a 10-s read, not the BTC arm's same-tick read.

    python analysis/thin/inplay_kalshi_anchor.py <stream-dir> [<stream-dir> ...]
"""
import bisect, datetime as dt, glob, json, math, os, random, sys
from collections import defaultdict

import httpx

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from core.btc15.quant import fee  # noqa: E402  -- 0.0695*p*(1-p) rounded up to the cent
from core.fees import POLYMARKET_TAKER as COEF  # noqa: E402  -- every tape is post-2026-09-17
GATEWAY = os.environ.get("POLYMARKET_GATEWAY_URL", "https://gateway.polymarket.us")
LIVE = {"Q1", "Q2", "Q3", "Q4", "OT"}


def ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def jl(p):
    return [json.loads(l) for l in open(p)]


class Tape:
    def __init__(self, rows, key="recv"):
        rows = sorted(rows, key=lambda r: ts(r[key]))
        self.t = [ts(r[key]) for r in rows]
        self.rows = rows

    def at(self, t):
        i = bisect.bisect_right(self.t, t) - 1
        return (self.rows[i], self.t[i]) if i >= 0 else (None, None)


DIRS = sys.argv[1:]
kal = defaultdict(list)
for d in DIRS:
    for f in glob.glob(os.path.join(d, "kalshi_*.jsonl")):
        for r in jl(f):
            kal[r["ticker"]].append(r)
team_markets = defaultdict(set)
for tk, rs in kal.items():
    team_markets[rs[0].get("team")].add(tk)
books = {}
for d in DIRS:
    for f in glob.glob(os.path.join(d, "slate_books_*.jsonl")):
        g = os.path.basename(f)[len("slate_books_"):-len(".jsonl")]
        if g not in books or os.path.getsize(f) > os.path.getsize(books[g]):
            books[g] = f
tmap = {}
http = httpx.Client(timeout=15, headers={"User-Agent": "meridian-inplay-anchor/1"})
for g in sorted(books):
    e = http.get(f"{GATEWAY}/v1/events/slug/{g}").json()
    e = e.get("event", e)
    ml = next((m for m in e.get("markets") or [] if str(m.get("sportsMarketType", "")).endswith("full_game_winner")), None)
    yes = next((s for s in (ml or {}).get("marketSides") or [] if s.get("long")), None)
    name = ((yes or {}).get("team") or {}).get("name")
    ymd = g[-10:].replace("-", "")[2:]                       # 2026-09-29 -> 260929
    mon = "JANFEBMARAPRMAYJUNJULAUGSEPOCTNOVDEC"[3 * (int(ymd[2:4]) - 1):3 * int(ymd[2:4])]
    tag = f"-{ymd[:2]}{mon}{ymd[4:]}"                          # Kalshi's event date, e.g. -26SEP29
    k = sorted(t for t in team_markets.get(name, ()) if tag in t)
    tmap[g] = {"yes": name, "k_yes": k}
    print(f"  {g:32s} venue YES {name!s:28s} Kalshi {k}")

margins = [0.0, 0.01, 0.02, 0.04, 0.06]
res = {m: [] for m in margins}
rng = random.Random(20260930)
ctl = []
stalled = defaultdict(int)
for g, mp in tmap.items():
    d = books[g]
    book_rows = [r for r in jl(d) if str(r.get("slug", "")).startswith("aec-")]
    anyb = Tape(book_rows)
    vb = Tape([r for r in book_rows if r.get("bid") is not None and r.get("ask") is not None])
    sc = jl(d.replace("slate_books_", "slate_scores_"))
    live = [ts(s["recv"]) for s in sc if s.get("live") and s.get("period") in LIVE]
    if len(live) < 2 or len(mp["k_yes"]) != 1:
        continue
    seen = {}
    for r in kal[mp["k_yes"][0]]:
        seen[(r["recv"], r["ticker"])] = r                  # the two windows tape overlapping hours
    kt = Tape(list(seen.values()))
    fin = sc[-1]
    # the result: the side the book settled toward (the direction check agreed 8/8 with the score)
    last = next((r for r in reversed(vb.rows) if r.get("state") in (None, "MARKET_STATE_OPEN")), None)
    m_last = (float(last["bid"]) + float(last["ask"])) / 2 if last else None
    y = 1.0 if m_last and m_last > 0.9 else 0.0 if m_last is not None and m_last < 0.1 else None
    # CONTROL: the same scoring at every 60th second of live play, side by a seeded coin, same filters
    t = live[0]
    while t < live[-1] - 60:
        t += 60.0
        b, tb = anyb.at(t)
        v, _ = vb.at(t)
        if b is None or t - tb > 30 or v is None or v.get("state") not in (None, "MARKET_STATE_OPEN"):
            continue
        side = rng.choice(("YES", "NO"))
        bid, ask = float(v["bid"]), float(v["ask"])
        price = ask if side == "YES" else 1 - bid
        x, _ = vb.at(t + 60)
        if x is not None:
            mid = (float(x["bid"]) + float(x["ask"])) / 2
            ctl.append((g, (mid if side == "YES" else 1 - mid) - price - fee(price, COEF)))
    for m in margins:
        next_ok = -1e18
        t = live[0]
        while t < live[-1] - 60:
            t += 3.0
            if t < next_ok:
                continue
            b, tb = anyb.at(t)
            if b is None or t - tb > 30:
                stalled[m] += 1
                continue
            v, _ = vb.at(t)
            k, _ = kt.at(t)
            if v is None or k is None or v.get("state") not in (None, "MARKET_STATE_OPEN"):
                continue
            try:
                kb, ka = float(k["yes_bid"]), float(k["yes_ask"])
            except (TypeError, ValueError):
                continue
            if not (0 < kb < ka < 1) or ka - kb > 0.0301:
                continue
            p = (kb + ka) / 2
            bid, ask = float(v["bid"]), float(v["ask"])
            ev_y = p - ask - fee(ask, COEF)
            ev_n = bid - p - fee(1 - bid, COEF)
            if max(ev_y, ev_n) <= m:
                continue
            side = "YES" if ev_y >= ev_n else "NO"
            price = ask if side == "YES" else 1 - bid
            cost = price + fee(price, COEF)
            out = {"g": g, "side": side, "ev": max(ev_y, ev_n), "t": t}
            for hz in (60, 300):
                x, _ = vb.at(t + hz)
                if x is not None:
                    mid = (float(x["bid"]) + float(x["ask"])) / 2
                    out[f"m{hz}"] = (mid if side == "YES" else 1 - mid) - cost
            if y is not None:
                out["settle"] = (y if side == "YES" else 1 - y) - cost
            res[m].append(out)
            next_ok = t + 60


def clustered(vals):
    n = len(vals)
    if n < 2:
        return float("nan"), float("nan"), 0
    mu = sum(v for _, v in vals) / n
    by = defaultdict(float)
    for g, v in vals:
        by[g] += v - mu
    G = len(by)
    if G < 2:
        return mu, float("nan"), G
    return mu, math.sqrt(sum(x * x for x in by.values()) / n ** 2 * G / (G - 1)), G


print(f"games {len(tmap)}; 3-s instants skipped for a stalled venue book (>30 s since a push): {dict(stalled)}")
for m in margins:
    rs = res[m]
    line = f"margin {m*100:3.0f}c  entries {len(rs):4d}  mean model ev {sum(r['ev'] for r in rs)/max(len(rs),1)*100:+5.2f}c"
    for k in ("m60", "m300", "settle"):
        mu, se, G = clustered([(r["g"], r[k]) for r in rs if k in r])
        line += f" | {k} {mu*100:+6.2f}c se {se*100:5.2f} G {G}"
    print(line)
mu, se, G = clustered(ctl)
print(f"CONTROL  coin side, every 60 s of live play: n {len(ctl)}  m60 {mu*100:+6.2f}c se {se*100:5.2f} G {G}")
