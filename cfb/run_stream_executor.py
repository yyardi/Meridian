#!/usr/bin/env python3
"""Ticket a ladder from the venue's STREAM, at update resolution, fresh only.

    python cfb/run_stream_executor.py --prefix aec-cfb-ga-ark-2026-09-19 \
        --minutes 215 --floor-usd 25 --fresh-s 2

Why this exists, measured on 2026-09-19 across 48 college games and 697,492
book updates:

* The REST book the existing executor polls is a median 62 SECONDS behind the
  stream and was never once ahead of it. Crossings only REST could see sat on
  legs a median 884 s stale. A 20-second poll of a 60-second-old book cannot
  find a crossing that is two seconds old.
* On the stream, gated so that BOTH legs were quoted by the venue within
  `--fresh-s` of each other, the slate held 3,615 distinct crossings. 62.9 %
  of them existed in a single update and are worth pennies.
* The eight worth $25 or more lasted a MEDIAN OF 28.9 SECONDS, several over a
  minute, one 256 s. Those are reachable -- by this, and by a person pressing
  SEND on the desk.

So the thing worth ticketing is not the 3,615, it is the handful that are
both fresh and large, and they stand long enough to act on. This writes ONE
ticket per episode, not one per update: a crossing that holds for four
minutes is one opportunity and the desk's ticket list said so all afternoon.

It PLACES NOTHING. It writes to the same ladder_intents_<prefix>.jsonl the
desk reads, so its tickets appear on /arb with the operator's SEND, and it
makes no REST call at all -- the live recorder's request budget is untouched.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cfb.run_ws_freshness import Stream  # noqa: E402
from cfb.run_ladder_executor import intent_for  # noqa: E402
from core.ladder.live import line_of, slugs_for  # noqa: E402
from core.ladder.scan import (DEFAULT_FEE_RATE, MAX_PLAUSIBLE_EDGE,  # noqa: E402
                              Violation, clears_floor, fee)
from core.ladder.intent import is_spread_pair  # noqa: E402


def crossings(line: float, touch: dict, seen: dict, now: float, fresh_s: float,
              game: str, rate: float) -> list[Violation]:
    """Every pair involving `line` that is crossed AND fresh, right now.

    Only pairs touching the rung that just moved can have changed, so this is
    O(rungs) per update rather than O(rungs^2). The arithmetic is
    `scan.scan_ladder`'s, pair for pair: buy the higher line at its ask, sell
    the lower at its bid, subtract the taker fee on each.
    """
    out: list[Violation] = []
    bid_k, ask_k, bsz_k, asz_k = touch[line]
    f_ask_k, f_bid_k = fee(ask_k, rate), fee(bid_k, rate)
    for j, (bid_j, ask_j, bsz_j, asz_j) in touch.items():
        if j == line:
            continue
        if now - min(seen[j], seen[line]) > fresh_s:
            continue                      # a pair is only as live as its staler leg
        if j < line:                      # `line` is the HIGHER, easier rung
            edge = bid_j - ask_k - f_ask_k - fee(bid_j, rate)
            lo, hi, buy, sell, size = j, line, ask_k, bid_j, min(asz_k, bsz_j)
        else:
            edge = bid_k - ask_j - f_bid_k - fee(ask_j, rate)
            lo, hi, buy, sell, size = line, j, ask_j, bid_k, min(asz_j, bsz_k)
        if 0.0 < edge <= MAX_PLAUSIBLE_EDGE:
            out.append(Violation(game, lo, hi, buy, sell, edge, size))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--minutes", type=float, default=240.0)
    ap.add_argument("--floor-usd", type=float, default=25.0,
                    help="min edge x displayed size to ticket")
    ap.add_argument("--fresh-s", type=float, default=2.0,
                    help="both legs must have been quoted within this many seconds "
                         "of each other; 2 is where the measured edge lives")
    ap.add_argument("--attempt-usd", type=float, default=1.0)
    ap.add_argument("--out-dir", default="/out" if os.path.isdir("/out") else "artifacts/reads")
    ap.add_argument("--status-every", type=float, default=60.0)
    a = ap.parse_args()

    game = a.prefix.replace("aec-", "")
    slugs = slugs_for(game)
    line_by_slug = {s: line_of(s, a.prefix) for s in slugs}
    line_by_slug = {s: k for s, k in line_by_slug.items() if k is not None}
    out = os.path.join(a.out_dir, f"ladder_intents_{a.prefix}.jsonl")
    stream = Stream(list(line_by_slug), os.path.join(a.out_dir, f"stream_exec_trades_{a.prefix}.jsonl"))
    stream.start()
    print(f"stream executor prefix={a.prefix} rungs={len(line_by_slug)} "
          f"floor=${a.floor_usd:.0f} fresh={a.fresh_s:g}s -> {out}  (places nothing)",
          flush=True)

    touch: dict[float, tuple] = {}
    seen: dict[float, float] = {}
    open_eps: dict[tuple, float] = {}      # pair -> when this episode opened
    written = scans = 0
    end = time.time() + a.minutes * 60
    next_status = time.time() + a.status_every
    while time.time() < end:
        snap = stream.snapshot()
        now = time.time()
        moved = []
        for slug, w in snap.items():
            k = line_by_slug.get(slug)
            if k is None:
                continue
            if touch.get(k) != w["touch"]:
                touch[k] = w["touch"]
                moved.append(k)
            seen[k] = w["recv"]
        for k in moved:
            if len(touch) < 2:
                continue
            scans += 1
            hits = {}
            for v in crossings(k, touch, seen, now, a.fresh_s, game, DEFAULT_FEE_RATE):
                if clears_floor(v.dollars, a.floor_usd) and is_spread_pair(v):
                    hits[(v.low_line, v.high_line)] = v
            for key, v in hits.items():
                if key in open_eps:
                    continue               # same episode: one ticket, not one a message
                open_eps[key] = now
                it = intent_for(v, game, dt.datetime.now(dt.timezone.utc).strftime("%H:%M:%S"),
                                a.attempt_usd)
                it["source"] = "stream"
                it["fresh_s"] = round(now - min(seen[key[0]], seen[key[1]]), 3)
                it["leg1_book_age_s"] = round(now - seen[key[1]], 1)
                it["leg2_book_age_s"] = round(now - seen[key[0]], 1)
                with open(out, "a", encoding="utf-8") as f:
                    f.write(json.dumps(it) + "\n")
                written += 1
                print(f"  TICKET {it['ts']}Z {key[1]}/{key[0]} {it['edge_c']:+.2f}c "
                      f"${v.dollars:,.0f} fresh {it['fresh_s']}s", flush=True)
            for key in [k2 for k2 in open_eps if k2 not in hits and (k in k2)]:
                open_eps.pop(key, None)    # the crossing closed; the next one is new
        if time.time() >= next_status:
            next_status = time.time() + a.status_every
            ages = [now - t for t in seen.values()]
            print(f"=== {dt.datetime.now(dt.timezone.utc):%H:%M:%S}Z rungs {len(touch)} "
                  f"msgs {stream.msgs} scans {scans} tickets {written} open {len(open_eps)} "
                  f"newest rung {min(ages, default=0):.1f}s reconn {stream.reconnects}",
                  flush=True)
        time.sleep(0.05)
    print(f"done: {written} tickets from {scans} scans")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
