"""The autonomous ladder algorithm, end to end, EXCEPT the send.

    python cfb/run_ladder_executor.py --prefix aec-cfb-mia-wake-2026-09-18 \
        --budget-usd 5 --attempt-usd 1 --floor-usd 25 --every 20 --minutes 240

Every step a trading algorithm has -- observe the venue's live ladder
simultaneously, detect a fee-netted self-contradiction, apply the registered
rule (docs/math/ladder-fill-test.md), size under a hard budget, and write a
fully-formed two-leg ORDER INTENT with exact prices and quantities -- runs
here on its own. The one step it does not do is submit. It has no order path,
by construction and by test: the intent is appended to a JSONL file and pushed
to the operator's phone, and a person places it.

Why the last step is a person: this is a fill test. The question is whether a
displayed size on a mispriced rung fills at all. That is answered by one small
order a human watches, not by an executor -- and Meridian places nothing.

Budget accounting is on INTENTS ISSUED, persisted in the JSONL, so a restart
cannot re-issue past the cap. With --attempt-usd 1 and prices near the
$189-shape (YES 0.22 + NO 0.735 = 0.955 per pair) each intent is ONE contract:
$5 buys five one-contract attempts across five games. One contract answers
"is there a real order there"; it does not answer "is 8,215 real". Say so.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.ladder import scan  # noqa: E402
from cfb.run_live_ladder import sample, slugs_for  # noqa: E402

#: Registered in docs/math/ladder-fill-test.md: the money and the minutes are
#: on the mid-ladder; liquid pairs break for ~30s and pennies.
MID_LADDER = (3.5, 20.5)


def is_mid(v) -> bool:
    return all(MID_LADDER[0] <= abs(x) <= MID_LADDER[1] for x in (v.high_line, v.low_line))


def gate(locked: bool, cands: list) -> list:
    """The operator's lock. While the lock file exists nothing is issued or
    pushed; the loop keeps sampling so the tape is still recorded."""
    return [] if locked else cands


def intent_for(v, game: str, when: str, attempt_usd: float) -> dict:
    """One fully-formed two-leg order, sized to the attempt budget. qty >= 1."""
    no_px = round(1.0 - v.sell_price, 4)
    pair_cost = v.buy_price + no_px               # < 1 whenever E > 0
    qty = max(1, int(attempt_usd // pair_cost))
    qty = min(qty, int(v.size))                   # never more than the smaller displayed side
    return {
        "ts": when, "game": game,
        "leg1": {"market_line": v.high_line, "side": "BUY YES", "price": round(v.buy_price, 4), "qty": qty},
        "leg2": {"market_line": v.low_line, "side": "BUY NO", "price": no_px, "qty": qty},
        "displayed_size": v.size, "edge_c": round(v.edge * 100, 2),
        "cost_usd": round(qty * pair_cost, 4),
        "guaranteed_usd": round(qty * (1.0 - pair_cost), 4),   # = qty * (B - A), gross
        "expected_net_usd": round(qty * v.edge, 4),             # after both fees
        "placed_by": "operator", "meridian_placed": False,
    }


def spent_so_far(path: str) -> float:
    if not os.path.exists(path):
        return 0.0
    tot = 0.0
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                tot += float(json.loads(line).get("cost_usd", 0.0))
            except (ValueError, TypeError):
                continue
    return tot


def push(intent: dict) -> bool:
    """Phone alert with the two buttons. Topic from env, never printed."""
    import urllib.request
    topic = os.environ.get("MERIDIAN_NTFY_TOPIC", "").strip().strip('"').strip("'")
    if not topic:
        return False
    l1, l2 = intent["leg1"], intent["leg2"]
    msg = (f"LADDER INTENT {intent['game']} {intent['ts']}Z  edge {intent['edge_c']:+.2f}c\n"
           f"1) line {l1['market_line']:+.1f}: {l1['side']} @ {l1['price']:.3f} x {l1['qty']}  <- FIRST\n"
           f"2) line {l2['market_line']:+.1f}: {l2['side']} @ {l2['price']:.3f} x {l2['qty']}\n"
           f"cost ${intent['cost_usd']:.2f}, pays ${l1['qty']:.2f} at settlement any score. "
           f"You place it; Meridian did not.")[:480]
    try:
        req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=msg.encode(),
                                     headers={"Title": "Meridian order intent"})
        urllib.request.urlopen(req, timeout=10).read()
        return True
    except Exception:  # noqa: BLE001
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--budget-usd", type=float, default=5.0, help="HARD cap on total intent cost")
    ap.add_argument("--attempt-usd", type=float, default=1.0)
    ap.add_argument("--floor-usd", type=float, default=25.0, help="min edge x displayed size to act")
    ap.add_argument("--cooldown", type=float, default=10.0, help="minutes per pair")
    ap.add_argument("--every", type=float, default=20.0)
    ap.add_argument("--minutes", type=float, default=240.0)
    ap.add_argument("--out", default=None, help="JSONL of intents; default artifacts/reads/ladder_intents_<prefix>.jsonl")
    ap.add_argument("--lock-file", default=None,
                    help="while this file exists: observe only, no intents, no pushes (default <out dir>/ladder_lock)")
    a = ap.parse_args()
    from core.polymarket.client import PolymarketGatewayClient

    game = a.prefix.replace("aec-", "")
    out = a.out or os.path.join("/out" if os.path.isdir("/out") else "artifacts/reads",
                                f"ladder_intents_{a.prefix}.jsonl")
    spent = spent_so_far(out)
    lock = a.lock_file or os.path.join(os.path.dirname(out) or ".", "ladder_lock")
    slugs = slugs_for(game)
    print(f"executor (shadow) prefix={a.prefix} rungs={len(slugs)} budget=${a.budget_usd:.2f} "
          f"spent_so_far=${spent:.2f} attempt=${a.attempt_usd:.2f} floor=${a.floor_usd:.0f}")
    last: dict = {}
    end = time.time() + a.minutes * 60
    with PolymarketGatewayClient() as c:
        while time.time() < end:
            rungs, took = sample(c, slugs, a.prefix)
            now = dt.datetime.now(dt.timezone.utc).strftime("%H:%M:%S")
            v = scan.scan_ladder(game, rungs, max_size=1e12)
            cands = [x for x in v if x.dollars >= a.floor_usd]
            cands.sort(key=lambda x: (not is_mid(x), -x.dollars))   # mid-ladder first, then biggest
            issued = None
            locked = os.path.exists(lock)                 # the operator's lock: observe only
            for x in gate(locked, cands):
                key = (x.high_line, x.low_line)
                if time.time() - last.get(key, -1e9) < a.cooldown * 60:
                    continue
                if spent + a.attempt_usd > a.budget_usd + 1e-9:
                    print(f"=== {now}Z  BUDGET EXHAUSTED ${spent:.2f} of ${a.budget_usd:.2f}; observing only")
                    break
                it = intent_for(x, game, now, a.attempt_usd)
                with open(out, "a", encoding="utf-8") as f:
                    f.write(json.dumps(it) + "\n")
                spent += it["cost_usd"]; last[key] = time.time(); issued = it
                push(it)
                break
            print(f"=== {now}Z rungs {len(rungs)} in {took:.1f}s  violations {len(v)}  {'LOCKED ' if locked else ''}"
                  f"candidates {len(cands)}  {'INTENT ' + str(issued['leg1']['market_line']) + '/' + str(issued['leg2']['market_line']) if issued else ''}  spent ${spent:.2f}")
            sys.stdout.flush()
            time.sleep(max(0.0, a.every - took))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
