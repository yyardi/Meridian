"""Coin Race (KXCRYPTOLEAD15M) pricing screen — data.

Writes two Parquet files under the archive (never the repo):

  pricing_markets.parquet   every settled Coin Race market: ticker, event, coin, open/close
                            (UTC), result, winner (the event's expiration_value), volume
  pricing_candles_1m.parquet  Coinbase Exchange 1-minute candles for BTC, ETH, SOL, XRP, HYPE
                            (all five are listed on Coinbase Exchange as <COIN>-USD)

The settlement index is CF Benchmarks' spot rate, which is not freely available; Coinbase
candles are a PROXY for it, and pricing_screen.py measures how often the proxy picks the
settled winner.

Rate limits (the brief): Kalshi <= 4 req/s, Coinbase <= 3 req/s, HTTP 429 -> back off 60 s.

Usage:  python analysis/coinrace/pricing_data.py [markets|candles|all]
"""
from __future__ import annotations

import datetime as dt
import os
import re
import sys
import threading
import time
from zoneinfo import ZoneInfo

import duckdb
import httpx
import pandas as pd

KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
COINBASE = "https://api.exchange.coinbase.com/products/{pair}/candles"
SERIES = "KXCRYPTOLEAD15M"
COINS = ("BTC", "ETH", "SOL", "XRP", "HYPE")
DATA_DIR = os.environ.get("COINRACE_DATA_DIR", "/Users/yayardia/MeridianArchive/coinrace/data")
CANDLE_START = dt.datetime(2026, 8, 24, tzinfo=dt.timezone.utc)
ET = ZoneInfo("America/New_York")
_MON = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], start=1)}


def ticker_close_utc(event_ticker: str) -> dt.datetime:
    """The ticker's yyMONddHHMM is the window END in US Eastern time; return it in UTC."""
    m = re.search(r"-(\d{2})([A-Z]{3})(\d{2})(\d{2})(\d{2})$", event_ticker)
    if not m:
        raise ValueError(f"no time code in {event_ticker!r}")
    yy, mon, dd, hh, mi = m.groups()
    local = dt.datetime(2000 + int(yy), _MON[mon], int(dd), int(hh), int(mi), tzinfo=ET)
    return local.astimezone(dt.timezone.utc)


class Pace:
    """A shared minimum gap between requests to one host."""

    def __init__(self, rps: float):
        self.gap, self.lock, self.next = 1.0 / rps, threading.Lock(), 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            t = max(now, self.next)
            self.next = t + self.gap
        time.sleep(max(0.0, t - time.monotonic()))


def get_json(client: httpx.Client, url: str, params: dict, pace: Pace, tries: int = 8):
    for i in range(tries):
        pace.wait()
        try:
            r = client.get(url, params=params)
        except httpx.HTTPError as e:
            print(f"  http error {e!r}; retry", file=sys.stderr)
            time.sleep(2 + 2 * i)
            continue
        if r.status_code == 429:
            print("  429; backing off 60 s", file=sys.stderr)
            time.sleep(60)
            continue
        if r.status_code >= 500:
            time.sleep(2 + 2 * i)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"gave up on {url} {params}")


def write_parquet(df: pd.DataFrame, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    con = duckdb.connect()
    con.execute("SET threads=2")  # the operator's laptop: keep DuckDB to two threads
    con.register("df", df)
    con.execute(f"COPY (SELECT * FROM df) TO '{tmp}' (FORMAT parquet, COMPRESSION zstd)")
    con.close()
    os.replace(tmp, path)


def read_parquet(path: str) -> pd.DataFrame:
    con = duckdb.connect()
    con.execute("SET threads=2")
    con.execute("SET TimeZone='UTC'")  # else timestamps come back in the Mac's local zone
    df = con.execute(f"SELECT * FROM read_parquet('{path}')").df()
    con.close()
    return df


def fetch_markets(client: httpx.Client) -> pd.DataFrame:
    pace = Pace(4.0)
    rows, cursor, page = [], None, 0
    while True:
        p = {"series_ticker": SERIES, "status": "settled", "limit": 1000}
        if cursor:
            p["cursor"] = cursor
        j = get_json(client, f"{KALSHI}/markets", p, pace)
        ms = j.get("markets") or []
        page += 1
        for m in ms:
            rows.append({
                "ticker": m["ticker"],
                "event_ticker": m["event_ticker"],
                "coin": (m.get("custom_strike") or {}).get("Cryptocurrency") or m["ticker"].rsplit("-", 1)[1],
                "open_time": m["open_time"],
                "close_time": m["close_time"],
                "result": m.get("result"),
                "winner": m.get("expiration_value"),
                "settlement_value": float(m.get("settlement_value_dollars") or "nan"),
                "volume": float(m.get("volume_fp") or 0.0),
                "status": m.get("status"),
                "rules_secondary": m.get("rules_secondary"),
            })
        cursor = j.get("cursor")
        print(f"  markets page {page}: {len(ms)} (total {len(rows)})", file=sys.stderr)
        if not cursor or not ms:
            break
    df = pd.DataFrame(rows).drop_duplicates("ticker")
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], utc=True)
    # The rule text is identical across markets save for the name; keep one copy per event.
    df["ticker_close_utc"] = [ticker_close_utc(e) for e in df["event_ticker"]]
    return df.sort_values(["close_time", "coin"]).reset_index(drop=True)


def fetch_candles(client: httpx.Client, coin: str, start: dt.datetime, end: dt.datetime) -> pd.DataFrame:
    """Coinbase Exchange 1-minute candles [start, end); 300 per request; minutes without a
    trade are ABSENT from Coinbase's answer (not zero-volume rows)."""
    pace = Pace(3.0)
    url = COINBASE.format(pair=f"{coin}-USD")
    out = []
    t = start
    step = dt.timedelta(minutes=300)
    n = 0
    while t < end:
        t2 = min(t + step, end)
        # Coinbase's `end` is inclusive; ask for [t, t2 - 1 min] so chunks do not overlap.
        j = get_json(client, url, {"granularity": 60, "start": t.isoformat(),
                                   "end": (t2 - dt.timedelta(minutes=1)).isoformat()}, pace)
        for c in j:
            out.append((int(c[0]), float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5])))
        t = t2
        n += 1
        if n % 50 == 0:
            print(f"  {coin}: {n} requests, through {t2:%Y-%m-%d %H:%M}Z", file=sys.stderr)
    df = pd.DataFrame(out, columns=["ts", "low", "high", "open", "close", "volume"])
    df["coin"] = coin
    return df.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)


def fetch_book(client: httpx.Client, markets: pd.DataFrame, events_per_request: int = 11) -> pd.DataFrame:
    """Kalshi's per-minute candlesticks for every market: yes bid/ask OHLC and last-trade OHLC.

    The batch endpoint caps a request at 10,000 candles counted as tickers x minutes of the
    requested range, so 11 consecutive events (55 tickers x 165 minutes = 9,075) go per request.
    A candle's close is the book at its end_period_ts; minute t of a window is the candle whose
    end_period_ts = open_time + 60 t.
    """
    pace = Pace(4.0)
    ev = (markets.groupby("event_ticker")
          .agg(open=("open_time", "min"), close=("close_time", "max"), tickers=("ticker", list))
          .sort_values("open"))
    rows = []
    # Greedy runs of consecutive events whose (tickers x minutes spanned) stays under the cap;
    # a gap in the listing (e.g. 08-21 -> 08-24) starts a new run instead of costing the cap.
    groups, i = [], 0
    while i < len(ev):
        j = i + 1
        while j < len(ev) and j - i < events_per_request:
            span = (ev["close"].iloc[j] - ev["open"].iloc[i]).total_seconds() / 60
            if 5 * (j - i + 1) * span > 9500:
                break
            j += 1
        groups.append(ev.iloc[i:j])
        i = j
    for gi, g in enumerate(groups):
        tickers = [t for ts in g["tickers"] for t in ts]
        st, en = int(g["open"].min().timestamp()), int(g["close"].max().timestamp())
        j = get_json(client, f"{KALSHI}/markets/candlesticks",
                     {"market_tickers": ",".join(tickers), "start_ts": st, "end_ts": en,
                      "period_interval": 1}, pace)
        win = {t: (int(o.timestamp()), int(c.timestamp()))
               for o, c, ts in zip(g["open"], g["close"], g["tickers"]) for t in ts}
        for mk in j.get("markets") or []:
            t = mk.get("market_ticker") or mk.get("ticker")
            o, c = win[t]
            for k in mk.get("candlesticks") or []:
                e = int(k["end_period_ts"])
                if not (o < e <= c):
                    continue
                ya, yb, pr = k.get("yes_ask") or {}, k.get("yes_bid") or {}, k.get("price") or {}
                f = lambda d, key: float(d[key]) if d.get(key) is not None else float("nan")
                rows.append((t, e, f(yb, "close_dollars"), f(ya, "close_dollars"),
                             f(ya, "low_dollars"), f(pr, "close_dollars"), f(pr, "previous_dollars"),
                             float(k.get("volume_fp") or 0.0)))
        if (gi + 1) % 50 == 0:
            print(f"  book: {gi + 1}/{len(groups)} requests, {len(rows)} candles", file=sys.stderr)
    return pd.DataFrame(rows, columns=["ticker", "end_period_ts", "yes_bid_close", "yes_ask_close",
                                       "yes_ask_low", "price_close", "price_previous", "volume"])


def main(which: str = "all", start: str | None = None, end: str | None = None) -> None:
    client = httpx.Client(timeout=60, headers={"User-Agent": "meridian-research/1"})
    mpath = os.path.join(DATA_DIR, "pricing_markets.parquet")
    if which in ("markets", "all"):
        mk = fetch_markets(client)
        write_parquet(mk, mpath)
        print(f"markets: {len(mk)} rows, {mk['event_ticker'].nunique()} events, "
              f"{mk['open_time'].min()} .. {mk['close_time'].max()}")
    if which in ("candles", "all"):
        t0 = dt.datetime.fromisoformat(start).replace(tzinfo=dt.timezone.utc) if start else CANDLE_START
        t1 = (dt.datetime.fromisoformat(end).replace(tzinfo=dt.timezone.utc) if end
              else dt.datetime.now(dt.timezone.utc).replace(second=0, microsecond=0))
        frames = []
        for coin in COINS:
            frames.append(fetch_candles(client, coin, t0, t1))
            print(f"candles {coin}: {len(frames[-1])} rows", file=sys.stderr)
        cd = pd.concat(frames, ignore_index=True)
        cpath = os.path.join(DATA_DIR, "pricing_candles_1m.parquet")
        if os.path.exists(cpath):  # merge with what is already there (a second range)
            cd = pd.concat([read_parquet(cpath), cd], ignore_index=True)
        cd = cd.drop_duplicates(["coin", "ts"], keep="last").sort_values(["coin", "ts"]).reset_index(drop=True)
        write_parquet(cd, cpath)
        print(f"candles: {len(cd)} rows; per coin {cd.groupby('coin').size().to_dict()}")
    if which in ("book", "all"):
        bk = fetch_book(client, read_parquet(mpath))
        write_parquet(bk, os.path.join(DATA_DIR, "pricing_book_1m.parquet"))
        print(f"book: {len(bk)} candles, {bk['ticker'].nunique()} markets")




# ---------------------------------------------------------------- a second exchange (sensitivity)
BITSTAMP = "https://www.bitstamp.net/api/v2/ohlc/{pair}/"


def fetch_bitstamp(client: httpx.Client, coin: str, start: dt.datetime, end: dt.datetime) -> pd.DataFrame:
    """Bitstamp 1-minute OHLC (1,000 a request; minutes without a trade repeat the last close
    with zero volume). Used only to measure whether a two-exchange composite tracks the
    settlement index better than Coinbase alone."""
    pace = Pace(2.0)
    out, t = [], int(start.timestamp())
    end_s = int(end.timestamp())
    while t < end_s:
        j = get_json(client, BITSTAMP.format(pair=f"{coin.lower()}usd"),
                     {"step": 60, "limit": 1000, "start": t}, pace)
        rows = (j.get("data") or {}).get("ohlc") or []
        if not rows:
            break
        for r in rows:
            out.append((int(r["timestamp"]), float(r["low"]), float(r["high"]), float(r["open"]),
                        float(r["close"]), float(r["volume"])))
        t = int(rows[-1]["timestamp"]) + 60
    df = pd.DataFrame(out, columns=["ts", "low", "high", "open", "close", "volume"])
    df["coin"] = coin
    return df[df["ts"] < end_s].drop_duplicates("ts").sort_values("ts").reset_index(drop=True)


def main_bitstamp() -> None:
    client = httpx.Client(timeout=60, headers={"User-Agent": "meridian-research/1"})
    t0 = dt.datetime(2026, 8, 10, tzinfo=dt.timezone.utc)
    t1 = dt.datetime.now(dt.timezone.utc).replace(second=0, microsecond=0)
    cd = pd.concat([fetch_bitstamp(client, c, t0, t1) for c in COINS], ignore_index=True)
    write_parquet(cd, os.path.join(DATA_DIR, "pricing_candles_bitstamp_1m.parquet"))
    print(f"bitstamp candles: {len(cd)} rows; per coin {cd.groupby('coin').size().to_dict()}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "bitstamp":
        main_bitstamp()
    else:
        main(a[0] if a else "all", a[1] if len(a) > 1 else None, a[2] if len(a) > 2 else None)
