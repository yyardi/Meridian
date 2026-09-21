#!/usr/bin/env python3
"""Did anyone trade THROUGH the displayed quote while a crossing stood?

    python3 phantom_check.py [--ledger /out/edge_ledger.jsonl] [--root /out/stream] [--gate 2]

The threat. On 2026-09-21 a discovery agent found the venue FREEZING a
market's book on the deciding score change while its score field kept
updating, and prints landing through the frozen display: a buyer paid 0.99
inside a window that displayed an offer at 0.83. A resting offer at 0.83
would have been matched first. So a displayed quote that prints trade
through is not a resting order; it is a picture. If the crossings in the
ledger are of that kind, every dollar on them is zero.

The test, per over-floor episode in the ledger's latest rows: replay the
game's book tape to the instant the episode opened and take both legs'
displayed touch; then read every print on either leg's slug from open to
close. The leg we would BUY is lifted at its displayed ask A: any taker LIFT
(taker buys YES, or sells NO -- either way the ask side is hit) at a price
ABOVE A while the episode stood says the offer at A was not there. The leg
we would SELL is hit at its displayed bid B: any taker HIT at a price BELOW
B says the bid at B was not there. Prints AT the display, on the other hand,
are the offer being consumed, which is what a real resting order does.

Taker intent on the venue's trade message: ORDER_INTENT_BUY_LONG (buys YES,
lifts the ask), ORDER_INTENT_SELL_SHORT (sells NO, i.e. buys YES, lifts the
ask), ORDER_INTENT_BUY_SHORT (buys NO, i.e. sells YES, hits the bid),
ORDER_INTENT_SELL_LONG (sells YES, hits the bid). `price` is the YES price.

Reads files only. Places nothing.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import sys

sys.path.insert(0, "/app" if os.path.isdir("/app/core") else
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core.ladder.stream_episodes import line_of  # noqa: E402

LIFTS = ("ORDER_INTENT_BUY_LONG", "ORDER_INTENT_SELL_SHORT")
HITS = ("ORDER_INTENT_BUY_SHORT", "ORDER_INTENT_SELL_LONG")
SLACK_S = 0.5


def _epoch(s):
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


def latest_rows(ledger: str, gate) -> list[dict]:
    rows = {}
    for ln in open(ledger, encoding="utf-8"):
        if ln.strip():
            r = json.loads(ln)
            if r.get("gate_s") == gate and "opened_ts" in json.dumps(r.get("over_floor_episodes", [{}])[:1]):
                rows[(r["date"], r["league"])] = r
    return list(rows.values())


def find_dir(root: str, dirs: list[str], game: str) -> str | None:
    for d in dirs:
        p = os.path.join(root, d, f"slate_books_{game}.jsonl")
        if os.path.exists(p):
            return os.path.join(root, d)
    return None


def touch_at(book_path: str, t: float) -> dict[float, tuple]:
    """Last displayed (bid, ask) per line at or before ``t``."""
    touch = {}
    with open(book_path, encoding="utf-8") as f:
        for ln in f:
            if not ln.strip():
                continue
            d = json.loads(ln)
            r = _epoch(d.get("recv"))
            if r is None:
                continue
            if r > t:
                break
            k = line_of(d.get("slug", ""))
            if k is not None and d.get("bid") is not None and d.get("ask") is not None:
                touch[k] = (d["bid"], d["ask"], d.get("slug"))
    return touch


def prints_in(trades_path: str, slugs: set[str], t0: float, t1: float) -> list[dict]:
    out = []
    if not os.path.exists(trades_path):
        return out
    with open(trades_path, encoding="utf-8") as f:
        for ln in f:
            if not ln.strip():
                continue
            d = json.loads(ln)
            if d.get("slug") not in slugs:
                continue
            r = _epoch(d.get("recv"))
            if r is None or r < t0 - SLACK_S:
                continue
            if r > t1 + SLACK_S:
                break
            out.append(d)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default="/out/edge_ledger.jsonl")
    ap.add_argument("--root", default="/out/stream")
    ap.add_argument("--gate", type=float, default=2.0)
    a = ap.parse_args()
    rows = latest_rows(a.ledger, a.gate)
    if not rows:
        print("no ledger rows with episode timestamps at that gate")
        return 0
    print(f"{'game':<28}{'pair':>12}{'$':>7}{'life':>7} | {'buy leg disp':>13}{'lifts':>6}{'thru':>5} | "
          f"{'sell leg disp':>14}{'hits':>5}{'thru':>5} | verdict")
    tot = thru = quiet = 0
    for r in rows:
        for e in r.get("over_floor_episodes", []):
            if "opened_ts" not in e:
                continue
            game, (lo, hi) = e["game"], e["pair"]
            d = find_dir(a.root, r["dirs"], game)
            if d is None:
                print(f"{game:<28} tape not found under {r['dirs']}")
                continue
            t0, t1 = e["opened_ts"], e["closed_ts"]
            touch = touch_at(os.path.join(d, f"slate_books_{game}.jsonl"), t0)
            if hi not in touch or lo not in touch:
                print(f"{game:<28}{f'{hi}/{lo}':>12} legs not both displayed at open")
                continue
            buy_bid, buy_ask, buy_slug = touch[hi]      # we lift the ask on the higher line
            sell_bid, sell_ask, sell_slug = touch[lo]   # we hit the bid on the lower line
            pr = prints_in(os.path.join(d, f"slate_trades_{game}.jsonl"), {buy_slug, sell_slug}, t0, t1)
            lifts = [p for p in pr if p["slug"] == buy_slug and p.get("taker_intent") in LIFTS]
            hits = [p for p in pr if p["slug"] == sell_slug and p.get("taker_intent") in HITS]
            thru_buy = [p for p in lifts if float(p["price"]) > buy_ask + 1e-9]
            thru_sell = [p for p in hits if float(p["price"]) < sell_bid - 1e-9]
            tot += 1
            if thru_buy or thru_sell:
                verdict = "PHANTOM: prints through the display"
                thru += 1
            elif not lifts and not hits:
                verdict = "no prints on either leg (unproven either way)"
                quiet += 1
            else:
                verdict = "prints AT or inside the display: consistent with resting"
            print(f"{game:<28}{f'{hi}/{lo}':>12}{e['best_usd']:>7,.0f}{e['life_s']:>6.1f}s | "
                  f"{f'{buy_bid:.3f}/{buy_ask:.3f}':>13}{len(lifts):>6}{len(thru_buy):>5} | "
                  f"{f'{sell_bid:.3f}/{sell_ask:.3f}':>14}{len(hits):>5}{len(thru_sell):>5} | {verdict}")
    print(f"\n{tot} episodes: {thru} phantom, {quiet} with no prints to judge by, "
          f"{tot - thru - quiet} consistent with a resting order")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
