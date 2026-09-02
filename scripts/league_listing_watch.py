"""Alert the moment a league's markets first list OPEN on the venue.

Why this exists: on 2026-09-02 the recorder sat idle with `markets_seen: 0`
because the WNBA is on break, and the venue carried NO open basketball markets
at all — MLB 27 and MLS 7 were the only open books. NBA markets exist
historically (V29) but the 2026-27 season is not listed yet.

Opening night is the one moment we cannot record retroactively. A watcher that
notices the listing is cheaper than a person remembering to look, and it turns
"be ready for the season" from a plan into a trigger.

Deliberately dumb: it does not start the recorder. It tells a human that the
markets exist, because the decision to point production at a new league is the
operator's, not a cron job's.

    python -m scripts.league_listing_watch --leagues nba,wnba
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import urllib.request

from core.polymarket.client import PolymarketAuthedClient, USCredentials

#: One page is 500; the venue exposes no cursor on /v1/markets, so we walk
#: `offset` (core/backfill.py's working pattern) rather than inventing one.
PAGE = 500
MAX_SCAN = 8000


def open_markets_by_league(client) -> collections.Counter:
    counts: collections.Counter = collections.Counter()
    for off in range(0, MAX_SCAN, PAGE):
        raw = client.get("/v1/markets", params={"limit": PAGE, "offset": off})
        markets = json.loads(raw.body_text).get("markets", [])
        if not markets:
            break
        for m in markets:
            # `active and not closed` is the venue's own open predicate; a
            # RESOLVED market is active=False. Do not substitute a status
            # string match — the enum has grown before.
            if m.get("active") and not m.get("closed"):
                parts = (m.get("slug") or "").split("-")
                if len(parts) > 1:
                    counts[parts[1]] += 1
    return counts


def notify(title: str, body: str) -> int:
    topic = os.environ["MERIDIAN_NTFY_TOPIC"]
    server = os.environ.get("MERIDIAN_NTFY_SERVER", "https://ntfy.sh")
    req = urllib.request.Request(
        f"{server}/{topic}", data=body.encode(),
        headers={"Title": title, "Priority": "high", "Tags": "basketball"})
    return urllib.request.urlopen(req, timeout=20).status


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--leagues", default="nba,wnba",
                    help="comma-separated league prefixes to watch")
    ap.add_argument("--state", default="/opt/meridian-research/listing_watch.json",
                    help="where the last-seen counts live, so a listing is "
                         "announced ONCE rather than every run")
    args = ap.parse_args()
    watch = [x.strip() for x in args.leagues.split(",") if x.strip()]

    with PolymarketAuthedClient(USCredentials.from_env()) as client:
        counts = open_markets_by_league(client)

    try:
        with open(args.state) as fh:
            seen = json.load(fh)
    except (OSError, ValueError):
        seen = {}

    newly = {lg: counts.get(lg, 0) for lg in watch
             if counts.get(lg, 0) > 0 and seen.get(lg, 0) == 0}

    print(f"open markets by league: {dict(counts.most_common(10))}")
    if newly:
        body = ("\n".join(f"{lg.upper()}: {n} open markets now listed"
                          for lg, n in newly.items())
                + "\n\nThe venue is carrying these for the first time since this "
                  "watcher started. Nothing is recording them yet — pointing "
                  "production at a new league is your call.")
        print("ntfy", notify("A watched league just listed", body))

    with open(args.state, "w") as fh:
        json.dump({lg: counts.get(lg, 0) for lg in watch}, fh)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
