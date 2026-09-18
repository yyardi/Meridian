"""Does the REST book lag the venue's own stream? The reviewer's H1, measured.

    python cfb/run_ws_freshness.py --prefix aec-cfb-mia-wake-2026-09-18 --every 20 --minutes 240

Two views of the same ladder, side by side, read-only:

* the markets WebSocket (`/v1/ws/markets`, MARKET_DATA + TRADE), kept in a
  thread that stores the latest full book per rung and appends every trade
  print to `ws_trades_<prefix>.jsonl`;
* the REST book (`/v1/markets/{slug}/book`, what every sampler and the
  executor use), fetched for every rung once per cycle.

Each cycle writes one row per rung to `ws_freshness_<prefix>.jsonl` with both
touches, both `transactTime`s and the gap between them, and runs the ladder
scanner on BOTH books so the status line says whether the violations the
executor would act on are also present in the stream. The decisive reads:

* `touch_equal` and `tt_equal` on nearly every row after live updates -> REST
  is not a stale cache; the violations are the venue's own book (H1 refuted).
  (Smoke 2026-09-18 13:27Z: the SUBSCRIBE-TIME snapshot carries a stamp ~143s
  newer than REST's for an identical book, so `rest_behind_s` is only
  meaningful once the stream has delivered a real update for that rung.)
* the stream re-prices a rung while REST keeps an older transactTime for
  seconds -> REST is cache-backed; the recorded violations are an API
  artifact and the finding is withdrawn (H1 supported).
* a TRADE print on a "stale" rung during an episode -> that resting size was
  real enough to be hit by someone (fillability evidence short of an order).

No order path. The private stream is never opened.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import statistics
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.ladder import scan  # noqa: E402
from core.polymarket.client import USCredentials, us_auth_headers  # noqa: E402
from core.polymarket.ws_min import ConnectionClosed, WSClient  # noqa: E402
from cfb.run_live_ladder import line_of, sample, slugs_for  # noqa: E402
from cfb.run_ladder_executor import book_age_s  # noqa: E402

WS_URL = "wss://api.polymarket.us/v1/ws/markets"
WS_PATH = "/v1/ws/markets"


def subscribe_msgs(request_id: str, sub_type: str, slugs: list[str]) -> list[dict]:
    """Both spellings the docs show (camelCase on the markets page, snake_case
    with numeric types on the overview). Sent in this order; the first that
    is not answered with an error wins."""
    num = {"SUBSCRIPTION_TYPE_MARKET_DATA": 1, "SUBSCRIPTION_TYPE_MARKET_DATA_LITE": 2,
           "SUBSCRIPTION_TYPE_TRADE": 3}[sub_type]
    return [
        {"subscribe": {"requestId": request_id, "subscriptionType": sub_type, "marketSlugs": slugs}},
        {"subscribe": {"request_id": request_id, "subscription_type": num, "market_slugs": slugs}},
    ]


def touch_of(md: dict) -> tuple[float, float, float, float] | None:
    bids, offers = md.get("bids") or [], md.get("offers") or []
    if not bids or not offers:
        return None
    return (float(bids[0]["px"]["value"]), float(offers[0]["px"]["value"]),
            float(bids[0]["qty"]), float(offers[0]["qty"]))


class Stream:
    """Latest MARKET_DATA book per slug + a trade log, fed by a daemon thread."""

    def __init__(self, slugs: list[str], trades_path: str) -> None:
        self.slugs, self.trades_path = slugs, trades_path
        self.latest: dict[str, dict] = {}       # slug -> {"tt", "touch", "recv"}
        self.msgs = self.trades = self.reconnects = 0
        self.last_error = ""
        self._lock = threading.Lock()

    def start(self) -> None:
        threading.Thread(target=self._run, name="ws", daemon=True).start()

    def snapshot(self) -> dict[str, dict]:
        with self._lock:
            return dict(self.latest)

    def _run(self) -> None:
        backoff = 1.0
        while True:
            try:
                self._session()
                backoff = 1.0
            except (ConnectionClosed, OSError, ValueError) as e:      # noqa: PERF203
                self.last_error = str(e)[:80]
                self.reconnects += 1
                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)

    def _session(self) -> None:
        creds = USCredentials.from_env()
        ws = WSClient(WS_URL, us_auth_headers(creds, "GET", WS_PATH))
        ws.connect()
        try:
            for rid, st in (("md", "SUBSCRIPTION_TYPE_MARKET_DATA"), ("tr", "SUBSCRIPTION_TYPE_TRADE")):
                for attempt in subscribe_msgs(rid, st, self.slugs):
                    ws.send_json(attempt)
                    reply = ws.recv_json()
                    self._handle(reply)
                    if "error" not in reply:
                        break
            while True:
                self._handle(ws.recv_json())
        finally:
            ws.close()

    def _handle(self, msg: dict) -> None:
        self.msgs += 1
        if "heartbeat" in msg:
            return
        md = msg.get("marketData") or msg.get("market_data")
        if md:
            slug = md.get("marketSlug") or md.get("market_slug")
            t = touch_of(md)
            if slug and t:
                with self._lock:
                    self.latest[slug] = {"tt": md.get("transactTime") or md.get("transact_time"),
                                         "touch": t, "recv": time.time()}
            return
        tr = msg.get("trade")
        if tr:
            self.trades += 1
            row = {"recv": dt.datetime.now(dt.timezone.utc).strftime("%H:%M:%S.%f")[:-3], **tr}
            with open(self.trades_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
            px = (tr.get("price") or {}).get("value"); q = (tr.get("quantity") or {}).get("value")
            print(f"  TRADE {tr.get('marketSlug') or tr.get('market_slug')} {px} x {q} "
                  f"taker={((tr.get('taker') or {}).get('intent') or '')[13:]}")


def compare(rungs_rest: dict, meta_rest: dict, stream: dict, line_by_slug: dict, now: float) -> list[dict]:
    rows = []
    for slug, k in line_by_slug.items():
        r, w = rungs_rest.get(k), stream.get(slug)
        if r is None:
            continue
        row = {"line": k, "rest": {"bid": r[0], "ask": r[1], "bsz": r[2], "asz": r[3], "tt": meta_rest.get(k)}}
        if w:
            wt = w["touch"]
            rest_age, ws_age = book_age_s(meta_rest.get(k), now), book_age_s(w["tt"], now)
            row["ws"] = {"bid": wt[0], "ask": wt[1], "bsz": wt[2], "asz": wt[3], "tt": w["tt"],
                         "recv_age_s": round(now - w["recv"], 1)}
            row["touch_equal"] = (r[0], r[1]) == (wt[0], wt[1])
            row["tt_equal"] = bool(w["tt"]) and w["tt"] == meta_rest.get(k)
            row["rest_behind_s"] = (None if rest_age is None or ws_age is None else round(rest_age - ws_age, 3))
        rows.append(row)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--every", type=float, default=20.0)
    ap.add_argument("--minutes", type=float, default=240.0)
    ap.add_argument("--out-dir", default="/out" if os.path.isdir("/out") else "artifacts/reads")
    a = ap.parse_args()
    from core.polymarket.client import PolymarketGatewayClient

    game = a.prefix.replace("aec-", "")
    slugs = slugs_for(game)
    line_by_slug = {s: line_of(s, a.prefix) for s in slugs}
    line_by_slug = {s: k for s, k in line_by_slug.items() if k is not None}
    out = os.path.join(a.out_dir, f"ws_freshness_{a.prefix}.jsonl")
    stream = Stream(list(line_by_slug), os.path.join(a.out_dir, f"ws_trades_{a.prefix}.jsonl"))
    stream.start()
    print(f"freshness prefix={a.prefix} rungs={len(line_by_slug)} every={a.every}s -> {out}")
    end = time.time() + a.minutes * 60
    with PolymarketGatewayClient() as c:
        while time.time() < end:
            meta: dict = {}
            rungs, took = sample(c, slugs, a.prefix, meta)
            now = time.time()
            now_s = dt.datetime.now(dt.timezone.utc).strftime("%H:%M:%S")
            snap = stream.snapshot()
            rows = compare(rungs, meta, snap, line_by_slug, now)
            ws_rungs = {k: snap[s]["touch"] for s, k in line_by_slug.items() if s in snap}
            v_rest = scan.scan_ladder(game, rungs, max_size=1e12)
            v_ws = scan.scan_ladder(game, ws_rungs, max_size=1e12) if ws_rungs else []
            common = {(x.high_line, x.low_line) for x in v_rest} & {(x.high_line, x.low_line) for x in v_ws}
            with open(out, "a", encoding="utf-8") as f:
                f.write(json.dumps({"t": now_s, "took_s": round(took, 2), "rows": rows,
                                    "viol_rest": len(v_rest), "viol_ws": len(v_ws), "viol_common": len(common),
                                    "ws_msgs": stream.msgs, "ws_trades": stream.trades,
                                    "ws_reconnects": stream.reconnects}) + "\n")
            cmp_rows = [r for r in rows if "ws" in r]
            behind = [r["rest_behind_s"] for r in cmp_rows if r.get("rest_behind_s") is not None]
            eq = sum(1 for r in cmp_rows if r["touch_equal"])
            tteq = sum(1 for r in cmp_rows if r.get("tt_equal"))
            recv_ages = [r["ws"]["recv_age_s"] for r in cmp_rows]
            print(f"=== {now_s}Z rest {len(rungs)} rungs in {took:.1f}s | ws rungs {len(cmp_rows)} msgs {stream.msgs} "
                  f"trades {stream.trades} reconn {stream.reconnects} {stream.last_error} | touch equal {eq}/{len(cmp_rows)} stamp equal {tteq}/{len(cmp_rows)} "
                  f"ws recv age median {statistics.median(recv_ages) if recv_ages else float('nan'):.0f}s | "
                  f"rest behind median {statistics.median(behind) if behind else float('nan'):.2f}s "
                  f"max {max(behind) if behind else float('nan'):.2f}s | violations rest {len(v_rest)} ws {len(v_ws)} common {len(common)}")
            sys.stdout.flush()
            time.sleep(max(0.0, a.every - took))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
