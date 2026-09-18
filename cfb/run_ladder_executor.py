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
# sample / slugs_for / book_age_s moved to core.ladder.live so the dashboard
# can call them (its image has no cfb/); book_age_s is re-exported here
# because cfb/run_ws_freshness.py and the tests import it from this module.
from core.ladder.live import book_age_s, sample, slugs_for  # noqa: E402,F401
# The ticket builder and the two filters moved to core.ladder.intent so the
# dashboard previews the same ticket this file writes; re-exported here
# because the tests and cfb/ read them from this module.
from core.ladder.intent import MID_LADDER, is_mid, is_spread_pair, ticket_for  # noqa: E402,F401
# The one door to the phone. Kind "tickets" is the default scope, so these
# pushes reach the operator while summaries and health flaps are muted to disk
# (docs/ops/notifications.md). core.notify is stdlib-only, by the same test
# that pins this file carries no HTTP client library.
from core import notify


def gate(locked: bool, cands: list) -> list:
    """The operator's lock. While the lock file exists nothing is issued or
    pushed; the loop keeps sampling so the tape is still recorded."""
    return [] if locked else cands


def intent_for(v, game: str, when: str, attempt_usd: float) -> dict:
    """One fully-formed two-leg order, sized to the attempt budget. qty >= 1.

    The legs, prices and screen words are `core.ladder.intent.ticket_for`'s;
    this file adds the two stamps that say who places it, in its own source,
    so the test that pins "Meridian places nothing" reads them here."""
    it = ticket_for(v, game, when, attempt_usd)
    it.update({"placed_by": "operator", "meridian_placed": False})
    return it


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
    topic = os.environ.get("MERIDIAN_NTFY_TOPIC", "").strip().strip('"').strip("'")
    if not topic:
        return False
    l1, l2 = intent["leg1"], intent["leg2"]
    msg = (f"LADDER INTENT {intent['game']} {intent['ts']}Z  edge {intent['edge_c']:+.2f}c\n"
           f"1) {l1.get('screen_row') or ('line %+.1f' % l1['market_line'])} -> tap {l1.get('screen_button') or l1['side']}, limit {l1['price']:.3f} x {l1['qty']}  <- FIRST\n"
           f"2) {l2.get('screen_row') or ('line %+.1f' % l2['market_line'])} -> tap {l2.get('screen_button') or l2['side']}, limit {l2['price']:.3f} x {l2['qty']}\n"
           f"cost ${intent['cost_usd']:.2f}, pays ${l1['qty']:.2f} at settlement any score. "
           f"books last updated {intent.get('leg1_book_age_s')}s / {intent.get('leg2_book_age_s')}s ago. "
           f"You place it; Meridian did not.")[:480]
    try:
        return notify.push("tickets", "Meridian order intent", msg, timeout=10) == notify.SENT
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
            meta: dict = {}
            rungs, took = sample(c, slugs, a.prefix, meta)
            now_ts = time.time()
            now = dt.datetime.now(dt.timezone.utc).strftime("%H:%M:%S")
            v = scan.scan_ladder(game, rungs, max_size=1e12)
            cands = [x for x in v if x.dollars >= a.floor_usd and is_spread_pair(x)]
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
                it["leg1_book_age_s"] = book_age_s(meta.get(x.high_line), now_ts)
                it["leg2_book_age_s"] = book_age_s(meta.get(x.low_line), now_ts)
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
