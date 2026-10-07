"""Every public trade of every settled Coin Race market (Kalshi series KXCRYPTOLEAD15M), from the
public REST API (no key), newest windows first, at most 4 requests a second, 60-s back-off on 429.

    python analysis/coinrace/fetch_trades.py markets   --out DIR   # settled market list -> DIR/markets.jsonl
    python analysis/coinrace/fetch_trades.py trades    --out DIR   # per-market trades -> DIR/parts/*.jsonl (resumable)
    python analysis/coinrace/fetch_trades.py assemble  --out DIR [--since ISO] [--dest PATH]  # -> trades.parquet

Trade semantics (checked on the tape, see docs/math/coinrace-research.md): taker_side is the side the
taker BOUGHT. taker_side='no' fills a resting YES bid at yes_price; taker_side='yes' fills a resting NO
bid at no_price. taker_outcome_side always equals taker_side and taker_book_side is a function of it
(yes->bid, no->ask), so neither adds information; both are kept.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import glob
import json
import os
import sys
import threading
import time

import httpx

API = "https://api.elections.kalshi.com/trade-api/v2"
SERIES = "KXCRYPTOLEAD15M"


class Limiter:
    """Global start-to-start spacing (rate per second) plus a shared pause after a 429."""

    def __init__(self, rate: float) -> None:
        self.gap = 1.0 / rate
        self.lock = threading.Lock()
        self.next_at = 0.0
        self.pause_until = 0.0
        self.n = 0
        self.n429 = 0

    def acquire(self) -> None:
        while True:
            with self.lock:
                now = time.monotonic()
                start = max(now, self.next_at, self.pause_until)
                self.next_at = start + self.gap
                self.n += 1
            if start > now:
                time.sleep(start - now)
            if time.monotonic() >= self.pause_until:
                return

    def backoff(self, seconds: float = 60.0) -> None:
        with self.lock:
            self.pause_until = max(self.pause_until, time.monotonic() + seconds)
            self.n429 += 1


def get(client: httpx.Client, lim: Limiter, path: str, params: dict) -> dict:
    for attempt in range(8):
        lim.acquire()
        try:
            r = client.get(API + path, params=params, timeout=30)
        except httpx.HTTPError as e:                                   # network blip: short retry
            print(f"  net error {e!r}; retry", file=sys.stderr, flush=True)
            time.sleep(2 + 2 * attempt)
            continue
        if r.status_code == 429:
            print("  429: backing off 60 s", file=sys.stderr, flush=True)
            lim.backoff(60.0)
            continue
        if r.status_code >= 500:
            time.sleep(2 + 2 * attempt)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"gave up on {path} {params}")


def cmd_markets(out: str, lim: Limiter) -> None:
    rows, cursor = [], None
    with httpx.Client() as c:
        while True:
            p = {"series_ticker": SERIES, "status": "settled", "limit": 1000}
            if cursor:
                p["cursor"] = cursor
            d = get(c, lim, "/markets", p)
            rows += d.get("markets", [])
            cursor = d.get("cursor")
            print(f"markets {len(rows)}", flush=True)
            if not cursor or not d.get("markets"):
                break
    keep = ("ticker", "event_ticker", "open_time", "close_time", "result", "expiration_value", "volume_fp", "status",
            "settlement_ts", "yes_sub_title")
    with open(os.path.join(out, "markets.jsonl"), "w") as f:
        for m in rows:
            f.write(json.dumps({k: m.get(k) for k in keep}) + "\n")
    print(f"wrote {len(rows)} markets", flush=True)


def load_markets(out: str) -> list[dict]:
    with open(os.path.join(out, "markets.jsonl")) as f:
        ms = [json.loads(x) for x in f]
    seen, uniq = set(), []
    for m in ms:
        if m["ticker"] not in seen:
            seen.add(m["ticker"]); uniq.append(m)
    uniq.sort(key=lambda m: (m["close_time"], m["ticker"]), reverse=True)    # newest windows first
    return uniq


def cmd_trades(out: str, lim: Limiter, workers: int) -> None:
    parts = os.path.join(out, "parts")
    os.makedirs(parts, exist_ok=True)
    done_path = os.path.join(out, "done.txt")
    done = set()
    if os.path.exists(done_path):
        with open(done_path) as f:
            done = {x.split("\t")[0] for x in f if x.strip()}
    todo = [m for m in load_markets(out) if m["ticker"] not in done]
    print(f"{len(todo)} markets to fetch ({len(done)} done)", flush=True)
    wlock = threading.Lock()
    part_f = open(os.path.join(parts, f"trades_{int(time.time())}.jsonl"), "a")
    done_f = open(done_path, "a")
    t0 = time.time()
    state = {"k": 0, "trades": 0, "oldest": None}

    def one(m: dict) -> tuple[dict, list[dict]]:
        if float(m.get("volume_fp") or 0) == 0:
            return m, []
        tr, cursor = [], None
        with httpx.Client() as c:
            while True:
                p = {"ticker": m["ticker"], "limit": 1000}
                if cursor:
                    p["cursor"] = cursor
                d = get(c, lim, "/markets/trades", p)
                tr += d.get("trades", [])
                cursor = d.get("cursor")
                if not cursor or not d.get("trades"):
                    break
        return m, tr

    with cf.ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(one, m) for m in todo]
        for fu in cf.as_completed(futs):
            m, tr = fu.result()
            with wlock:
                for x in tr:
                    part_f.write(json.dumps(x) + "\n")
                part_f.flush()
                done_f.write(f"{m['ticker']}\t{len(tr)}\t{m['close_time']}\n"); done_f.flush()
                state["k"] += 1; state["trades"] += len(tr)
                state["oldest"] = min(state["oldest"] or m["close_time"], m["close_time"])
                if state["k"] % 250 == 0:
                    el = time.time() - t0
                    print(f"{state['k']}/{len(todo)} markets, {state['trades']} trades, oldest window {state['oldest']}, "
                          f"{el/60:.1f} min, {lim.n/el:.2f} req/s, 429s {lim.n429}", flush=True)
    part_f.close(); done_f.close()
    print(f"done: {state['k']} markets, {state['trades']} trades in {(time.time()-t0)/60:.1f} min", flush=True)


def cmd_assemble(out: str, since: str | None, dest: str | None = None) -> None:
    import duckdb
    con = duckdb.connect()
    parts = glob.glob(os.path.join(out, "parts", "*.jsonl"))
    where = f"WHERE m.close_time >= TIMESTAMPTZ '{since}'" if since else ""
    con.execute(f"""
      CREATE TABLE m AS SELECT ticker, split_part(ticker, '-', 3) AS coin, CAST(close_time AS TIMESTAMPTZ) AS close_time,
             CAST(open_time AS TIMESTAMPTZ) AS open_time, result, expiration_value, CAST(volume_fp AS DOUBLE) AS volume
      FROM read_json('{os.path.join(out, 'markets.jsonl')}', format='newline_delimited',
                     columns={{ticker:'VARCHAR', event_ticker:'VARCHAR', open_time:'VARCHAR', close_time:'VARCHAR',
                              result:'VARCHAR', expiration_value:'VARCHAR', volume_fp:'VARCHAR', status:'VARCHAR',
                              settlement_ts:'VARCHAR', yes_sub_title:'VARCHAR'}})""")
    con.execute(f"""
      CREATE TABLE t AS SELECT DISTINCT trade_id, ticker, CAST(created_time AS TIMESTAMPTZ) AS created_time,
             CAST(yes_price_dollars AS DOUBLE) AS yes_price, CAST(no_price_dollars AS DOUBLE) AS no_price,
             CAST(count_fp AS DOUBLE) AS count, taker_side, taker_outcome_side, taker_book_side, is_block_trade
      FROM read_json({parts!r}, format='newline_delimited',
                     columns={{trade_id:'VARCHAR', ticker:'VARCHAR', created_time:'VARCHAR', yes_price_dollars:'VARCHAR',
                              no_price_dollars:'VARCHAR', count_fp:'VARCHAR', taker_side:'VARCHAR', taker_outcome_side:'VARCHAR',
                              taker_book_side:'VARCHAR', is_block_trade:'BOOLEAN'}})""")
    con.execute("SET TimeZone='UTC'")
    dest = dest or os.path.join(out, "trades.parquet")
    tmp = dest + ".tmp"
    con.execute(f"""COPY (
      SELECT t.ticker, m.coin, m.close_time AS window_end_utc, t.created_time, t.yes_price, t.no_price, t.count,
             t.taker_side, m.result, m.expiration_value AS winner_coin, t.taker_outcome_side, t.taker_book_side,
             t.is_block_trade, t.trade_id
      FROM t JOIN m USING (ticker) {where}
      ORDER BY window_end_utc, t.ticker, t.created_time, t.trade_id) TO '{tmp}' (FORMAT parquet)""")
    os.replace(tmp, dest)
    s = con.execute(f"""SELECT count(*), sum(count), count(DISTINCT ticker), CAST(min(window_end_utc) AS VARCHAR), CAST(max(window_end_utc) AS VARCHAR)
                        FROM read_parquet('{dest}')""").fetchone()
    mk = con.execute(f"SELECT count(*), CAST(min(close_time) AS VARCHAR), CAST(max(close_time) AS VARCHAR) FROM m {where.replace('m.close_time', 'close_time')}").fetchone()
    print("trades rows, contracts, markets with trades, first/last window:", s)
    print("settled markets in scope, first/last window:", mk)


def contiguous_since(out: str) -> tuple[str | None, int, int]:
    """The oldest window close such that EVERY settled market closing at or after it has been fetched (the
    fetch runs newest first with 4 workers, so completion is only nearly ordered). Returns (close_time,
    markets covered, markets total)."""
    with open(os.path.join(out, "done.txt")) as f:
        done = {x.split("\t")[0] for x in f if x.strip()}
    ms = load_markets(out)                                            # newest first
    since, k = None, 0
    for m in ms:
        if m["ticker"] not in done:
            break
        since, k = m["close_time"], k + 1
    # a window counts only when all five of its markets are in
    if since is not None:
        same = [m for m in ms if m["close_time"] == since]
        if not all(m["ticker"] in done for m in same):
            since = min(m["close_time"] for m in ms[:k] if m["close_time"] > since)
    return since, k, len(ms)


def cmd_publish(out: str, dest_dir: str, min_days: float) -> None:
    """trades.parquet over the contiguous newest coverage, then COVERAGE.txt, then the READY marker (only when
    coverage >= min_days). The parquet is written to a temp name and renamed, so a reader never sees half."""
    since, k, total = contiguous_since(out)
    newest = load_markets(out)[0]["close_time"]
    span = (dt.datetime.fromisoformat(newest.replace("Z", "+00:00")) - dt.datetime.fromisoformat(since.replace("Z", "+00:00"))).total_seconds() / 86400 + 15 / 1440
    print(f"contiguous coverage: windows closing {since} .. {newest} = {span:.2f} days, {k}/{total} markets")
    if span < min_days:
        print("below the minimum; nothing published")
        return
    dest = os.path.join(dest_dir, "trades.parquet")
    full = k == total
    # 'since' is the oldest close INCLUDED: assemble filters close_time >= since
    cmd_assemble(out, since, dest)
    import duckdb
    s = duckdb.sql(f"""SELECT count(*), sum(count), count(DISTINCT ticker), count(DISTINCT window_end_utc),
                         CAST(min(window_end_utc) AS VARCHAR), CAST(max(window_end_utc) AS VARCHAR), CAST(min(created_time) AS VARCHAR),
                         CAST(max(created_time) AS VARCHAR) FROM read_parquet('{dest}')""").fetchone()
    with open(os.path.join(dest_dir, "trades.COVERAGE.txt"), "w") as f:
        f.write(f"written {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} by analysis/coinrace/fetch_trades.py publish\n"
                f"source: GET /trade-api/v2/markets/trades?ticker=<each settled KXCRYPTOLEAD15M market> (public, no key), every page\n"
                f"coverage: {'FULL HISTORY' if full else 'NEWEST WINDOWS ONLY (fetch continues; this file is replaced by a larger one when it ends)'}\n"
                f"windows closing {since} .. {newest} ({span:.2f} days); markets fetched {k} of {total} settled\n"
                f"rows (trades) {s[0]}, contracts {s[1]:.2f}, markets with >=1 trade {s[2]}, windows with >=1 trade {s[3]}\n"
                f"window_end_utc {s[4]} .. {s[5]}; created_time {s[6]} .. {s[7]}\n"
                f"markets with zero volume in the listing were not requested and have no rows\n"
                f"columns: ticker, coin, window_end_utc (= market close_time), created_time, yes_price, no_price, count (fractional\n"
                f"  contracts exist), taker_side (the side the taker BOUGHT: 'no' fills a resting YES bid at yes_price), result\n"
                f"  (yes/no/scalar; scalar = a two-coin tie, settlement 0.5), winner_coin, taker_outcome_side, taker_book_side,\n"
                f"  is_block_trade, trade_id\n")
    open(os.path.join(dest_dir, "trades.READY"), "a").close()
    print("published", s)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("markets", "trades", "assemble", "publish"))
    ap.add_argument("--dest-dir", default=None)
    ap.add_argument("--min-days", type=float, default=21.0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--rate", type=float, default=3.9)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--since", default=None)
    ap.add_argument("--dest", default=None, help="assemble: output parquet (default OUT/trades.parquet)")
    a = ap.parse_args()
    assert a.rate <= 4.0, "at most 4 requests a second to Kalshi"
    os.makedirs(a.out, exist_ok=True)
    lim = Limiter(a.rate)
    if a.cmd == "markets":
        cmd_markets(a.out, lim)
    elif a.cmd == "trades":
        cmd_trades(a.out, lim, a.workers)
    elif a.cmd == "publish":
        cmd_publish(a.out, a.dest_dir, a.min_days)
    else:
        cmd_assemble(a.out, a.since, a.dest)


if __name__ == "__main__":
    main()
