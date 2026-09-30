"""Live probe: are the two REST quotes the BTC harness trades on fresh?

Each second for N seconds, for the 15-minute window in play: the venue's REST book
(`/v1/markets/<slug>/book`, which the arms read and paper-fill at), Kalshi's `/markets` list
touch (which the Kalshi arms and the quote tape read), and Kalshi's `/markets/<t>/orderbook`.
Prints how often the list and the order book disagree, the locked-pair profit computed off
each, and how long each source sits unchanged. The first run (2026-09-30 02:16Z, 97 samples
with a venue book): Kalshi's order book changed every second; its list touch held 32 s on
average (longest 58 s); the venue's REST book, sizes included, held 24 s (longest 30 s).

    python analysis/btc15/quote_freshness_probe.py [seconds]      # writes kalshi_probe.json here
"""
import datetime as dt, json, math, os, sys, time
import httpx

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from core.fees import KALSHI_TAKER, POLYMARKET_TAKER  # noqa: E402  -- a live read: this period's constants

GW, KX = "https://gateway.polymarket.us", "https://api.elections.kalshi.com/trade-api/v2"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 120
h = httpx.Client(timeout=5, headers={"User-Agent": "meridian-probe/1"})
fee_v = lambda p: math.ceil(round(POLYMARKET_TAKER * p * (1 - p) * 100, 9)) / 100
fee_k = lambda p: math.ceil(round(KALSHI_TAKER * p * (1 - p) * 100, 9)) / 100


def px(level):
    p = (level or {}).get("px")
    p = p.get("value") if isinstance(p, dict) else p
    return float(p) if p is not None else None


def lock(va, vb, ka, kb):
    if None in (va, vb, ka, kb):
        return None
    a = va + fee_v(va) + (1 - kb) + fee_k(1 - kb)
    b = ka + fee_k(ka) + (1 - vb) + fee_v(1 - vb)
    return round(1 - min(a, b), 4)


rows = []
for i in range(N):
    t = time.time()
    start = dt.datetime.fromtimestamp(t - t % 900, dt.timezone.utc)
    slug = f"cpc-btc-updown-15m-{start:%Y-%m-%d-%H%M}z"
    try:
        t0 = time.time()
        vbk = h.get(f"{GW}/v1/markets/{slug}/book").json().get("marketData") or {}
        t1 = time.time()
        ms = h.get(f"{KX}/markets", params={"series_ticker": "KXBTC15M", "status": "open", "limit": 10}).json()["markets"]
        t2 = time.time()
        close = start + dt.timedelta(minutes=15)
        m = next(m for m in ms if dt.datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")) == close)
        obr = h.get(f"{KX}/markets/{m['ticker']}/orderbook").json()
        ob = obr.get("orderbook_fp") or obr.get("orderbook") or {}
        t3 = time.time()
    except Exception as e:  # noqa: BLE001
        print("err", e); time.sleep(1); continue
    vb, va = px((vbk.get("bids") or [None])[0]), px((vbk.get("offers") or [None])[0])
    lb, la = float(m["yes_bid_dollars"]), float(m["yes_ask_dollars"])
    yes = ob.get("yes_dollars") or [[p / 100, q] for p, q in (ob.get("yes") or [])]
    no = ob.get("no_dollars") or [[p / 100, q] for p, q in (ob.get("no") or [])]
    ob_b = max((float(p) for p, q in yes if float(q) > 0), default=None)
    ob_nb = max((float(p) for p, q in no if float(q) > 0), default=None)
    q_b = next((float(q) for p, q in yes if ob_b is not None and float(p) == ob_b), None)
    q_nb = next((float(q) for p, q in no if ob_nb is not None and float(p) == ob_nb), None)
    ob_a = None if ob_nb is None else round(1 - ob_nb, 4)
    rows.append({"left": 900 - (t % 900), "vb": vb, "va": va, "lb": lb, "la": la, "ob": ob_b, "oa": ob_a,
                 "lock_list": lock(va, vb, la, lb), "lock_ob": lock(va, vb, ob_a, ob_b), "kq_bid": q_b, "kq_ask": q_nb,
                 "vq_bid": float(vbk["bids"][0]["qty"]) if vbk.get("bids") else None,
                 "vq_ask": float(vbk["offers"][0]["qty"]) if vbk.get("offers") else None,
                 "ms_v": round(1000 * (t1 - t0)), "ms_k": round(1000 * (t2 - t1)), "ms_ob": round(1000 * (t3 - t2)),
                 "k_updated": m.get("updated_time") or m.get("last_updated_time")})
    time.sleep(max(0, 1 - (time.time() - t)))

json.dump(rows, open("kalshi_probe.json", "w"), indent=1)
diff = [r for r in rows if (r["lb"], r["la"]) != (r["ob"], r["oa"])]
print(f"{len(rows)} samples; Kalshi list touch != orderbook touch on {len(diff)}")
for name in ("lock_list", "lock_ob"):
    v = sorted(r[name] for r in rows if r[name] is not None)
    if v:
        print(f"  {name}: >0 on {sum(1 for x in v if x > 0)}/{len(v)}; median {v[len(v)//2]*100:+.1f}c max {v[-1]*100:+.1f}c")
def runs(sample, key):
    """Lengths, in samples, of the stretches over which ``key`` does not change."""
    out, cur, n = [], object(), 0
    for r in sample:
        k = key(r)
        if k == cur:
            n += 1
        else:
            if n:
                out.append(n)
            cur, n = k, 1
    return out + [n]


booked = [r for r in rows if r["vb"] is not None]
for name, key in (("venue REST book (px+qty)", lambda r: (r["vb"], r["va"], r["vq_bid"], r["vq_ask"])),
                  ("Kalshi order book (px+qty)", lambda r: (r["ob"], r["oa"], r["kq_bid"], r["kq_ask"])),
                  ("Kalshi list touch (px)", lambda r: (r["lb"], r["la"]))):
    x = runs(booked, key)
    print(f"  {name:28s} {len(booked)} samples -> {len(x)} states; mean run {sum(x) / len(x):.1f} s, longest {max(x)} s")
for r in rows[:: max(1, len(rows) // 12)]:
    print(f"  {r['left']:5.0f}s left  venue {r['vb']}/{r['va']}  kalshi list {r['lb']}/{r['la']}  book {r['ob']}/{r['oa']}  "
          f"lock list {r['lock_list']} book {r['lock_ob']}  qty v {r['vq_bid']}/{r['vq_ask']} k {r['kq_bid']}/{r['kq_ask']}  ms {r['ms_v']}/{r['ms_k']}/{r['ms_ob']}")
