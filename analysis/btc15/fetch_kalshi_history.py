"""Build a research dataset for the 15-minute Bitcoin Up/Down contract.

Kalshi's KXBTC15M settles on the same CF Benchmarks BRTI averages as Polymarket US's
"BTC Up or Down: 15 min" (verified 2026-09-27: same strike, same settlement value).
For each settled window: strike, result, settlement value, and Kalshi's per-minute
yes bid/ask/last and volume. Beside it: Coinbase BTC-USD 1-minute candles.

Outputs (in this directory): windows.jsonl, candles.jsonl, btc_1m.jsonl
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import json
import os
import sys
import threading
import time

import httpx

K = "https://api.elections.kalshi.com/trade-api/v2"
CB = "https://api.exchange.coinbase.com/products/BTC-USD/candles"
DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 45
HERE = os.environ.get("MERIDIAN_BTC_RESEARCH_DIR") or os.path.dirname(os.path.abspath(__file__))


def ts(s: str) -> int:
    return int(dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())


class Pace:
    def __init__(self, rps: float):
        self.gap, self.lock, self.next = 1.0 / rps, threading.Lock(), 0.0

    def wait(self):
        with self.lock:
            now = time.monotonic()
            t = max(now, self.next)
            self.next = t + self.gap
        time.sleep(max(0.0, t - time.monotonic()))


def get(h, url, params, pace, tries=5):
    for i in range(tries):
        pace.wait()
        try:
            r = h.get(url, params=params)
            if r.status_code == 429:
                time.sleep(2 + 2 * i)
                continue
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError):
            time.sleep(1 + i)
    return None


def main():
    h = httpx.Client(timeout=30, headers={"User-Agent": "meridian-research/1"})
    kpace = Pace(8.0)
    cutoff = time.time() - DAYS * 86400
    # 1. settled windows
    wpath = os.path.join(HERE, "windows.jsonl")
    windows = []
    cur = None
    while True:
        p = {"series_ticker": "KXBTC15M", "status": "settled", "limit": 1000}
        if cur:
            p["cursor"] = cur
        j = get(h, f"{K}/markets", p, kpace)
        ms = (j or {}).get("markets") or []
        for m in ms:
            if ts(m["open_time"]) < cutoff:
                continue
            windows.append({"ticker": m["ticker"], "open": ts(m["open_time"]), "close": ts(m["close_time"]),
                            "strike": m.get("floor_strike"), "result": m.get("result"),
                            "settle": m.get("expiration_value"), "volume": m.get("volume_fp")})
        cur = (j or {}).get("cursor")
        if not cur or not ms or ts(ms[-1]["open_time"]) < cutoff:
            break
    windows.sort(key=lambda w: w["open"])
    with open(wpath, "w") as fh:
        fh.write("".join(json.dumps(w) + "\n" for w in windows))
    print(f"windows: {len(windows)} from {dt.datetime.utcfromtimestamp(windows[0]['open'])} "
          f"to {dt.datetime.utcfromtimestamp(windows[-1]['open'])}", flush=True)

    # 2. per-minute candles for each window
    cpath = os.path.join(HERE, "candles.jsonl")
    done = set()
    if os.path.exists(cpath):
        done = {json.loads(l)["ticker"] for l in open(cpath)}
    todo = [w for w in windows if w["ticker"] not in done]
    lock = threading.Lock()

    def one(w):
        j = get(h, f"{K}/series/KXBTC15M/markets/{w['ticker']}/candlesticks",
                {"start_ts": w["open"], "end_ts": w["close"], "period_interval": 1}, kpace)
        rows = []
        for c in (j or {}).get("candlesticks") or []:
            pr, yb, ya = c.get("price") or {}, c.get("yes_bid") or {}, c.get("yes_ask") or {}
            rows.append({"t": c["end_period_ts"],
                         "bid": yb.get("close_dollars"), "ask": ya.get("close_dollars"),
                         "bid_hi": yb.get("high_dollars"), "ask_lo": ya.get("low_dollars"),
                         "last": pr.get("close_dollars"), "lo": pr.get("low_dollars"), "hi": pr.get("high_dollars"),
                         "vol": c.get("volume_fp")})
        with lock, open(cpath, "a") as fh:
            fh.write(json.dumps({"ticker": w["ticker"], "rows": rows}) + "\n")

    with cf.ThreadPoolExecutor(8) as ex:
        for i, _ in enumerate(ex.map(one, todo), 1):
            if i % 500 == 0:
                print(f"candles {i}/{len(todo)}", flush=True)
    print("candles done", flush=True)

    # 3. Coinbase 1-minute BTC candles over the whole span (+2 h of history before)
    bpath = os.path.join(HERE, "btc_1m.jsonl")
    start, end = windows[0]["open"] - 7200, windows[-1]["close"]
    cpace = Pace(5.0)
    out = {}
    t = start
    while t < end:
        t2 = min(t + 300 * 60, end)
        j = get(h, CB, {"granularity": 60, "start": dt.datetime.utcfromtimestamp(t).isoformat(),
                        "end": dt.datetime.utcfromtimestamp(t2).isoformat()}, cpace)
        for row in j or []:
            # [time, low, high, open, close, volume], time = candle START
            out[int(row[0])] = row
        t = t2
    with open(bpath, "w") as fh:
        for k in sorted(out):
            r = out[k]
            fh.write(json.dumps({"t": k, "low": r[1], "high": r[2], "open": r[3], "close": r[4], "vol": r[5]}) + "\n")
    print(f"btc minutes: {len(out)}", flush=True)


if __name__ == "__main__":
    main()
