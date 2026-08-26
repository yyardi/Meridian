"""Take one activities export and pin it as an artifact.

Walks the feed exactly as scripts.export_wnba_trades.fetch_activities does —
same path, page size, cursor and pause — but keeps the PAGES rather than
flattening them, and stamps fetched_at. That envelope is what makes a sheet
reproducible and what the preflight needs to bound its window; a flat dump is
undated and is refused downstream, correctly.

REFUSES TO WRITE A TRUNCATED ARTIFACT. If the walk does not reach eof the file
is not created at all, so a short export cannot be pinned and then trusted
later by someone who wasn't here.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

import core.storage  # noqa: F401  loads .env
from core.polymarket.client import PolymarketAuthedClient, USCredentials
from scripts.export_wnba_trades import (
    ACTIVITIES_PATH, MAX_PAGES, PAGE_LIMIT, PAGE_PAUSE_SECONDS,
)


def page_is_last(body: dict) -> bool:
    """The walk is done — mirrors fetch_activities' own termination rule."""
    return bool(body.get("eof")) or not body.get("nextCursor")


def build_envelope(pages: list[dict], stamp: str) -> dict:
    """The pinned artifact, or a refusal.

    **A truncated export must not be pinnable.** The live path guarantees
    completeness by walking to ``eof``; an artifact is read later by someone who
    was not there and cannot re-derive that. So the envelope is only built when
    the last page actually terminated the walk — otherwise nothing is written and
    the oldest trades cannot go quietly missing from a file that looks whole.
    """
    if not pages:
        raise SystemExit("REFUSING TO PIN: no pages fetched. Nothing written.")
    if not page_is_last(pages[-1]):
        raise SystemExit(
            "REFUSING TO PIN: the walk did not reach eof, so the OLDEST trades "
            "are missing. Nothing written. Raise MAX_PAGES and re-run."
        )
    return {"pages": pages, "page_count": len(pages), "fetched_at": stamp}


def main() -> int:
    parser = argparse.ArgumentParser(prog="meridian-pin-venue-export")
    parser.add_argument("out_dir", type=Path, nargs="?", default=Path("."),
                        help="directory to write venue_activities_<stamp>.json into")
    out_dir = parser.parse_args().out_dir
    started = dt.datetime.now(dt.timezone.utc)
    client = PolymarketAuthedClient(USCredentials.from_env())
    pages: list[dict] = []
    cursor: str | None = None
    try:
        for i in range(MAX_PAGES):
            params: dict = {"limit": PAGE_LIMIT}
            if cursor:
                params["cursor"] = cursor
            resp = client.get(ACTIVITIES_PATH, params=params)
            if resp.status_code != 200:
                raise SystemExit(
                    f"activities HTTP {resp.status_code}: {resp.body_text[:200]}")
            body = json.loads(resp.body_text)
            pages.append(body)
            n = len(body.get("activities") or [])
            cursor = body.get("nextCursor")
            print(f"  page {i + 1:>3}: {n:>4} activities  eof={bool(body.get('eof'))}")
            if page_is_last(body):
                break
            time.sleep(PAGE_PAUSE_SECONDS)
    finally:
        client.close()

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    envelope = build_envelope(pages, stamp)          # refuses if truncated
    path = out_dir / f"venue_activities_{stamp}.json"
    total = sum(len(p.get("activities") or []) for p in envelope["pages"])
    path.write_text(json.dumps(envelope, indent=1))
    print(f"\npinned {total:,} activities across {len(pages)} pages")
    print(f"started {started:%Y-%m-%d %H:%M:%SZ}  fetched_at {stamp}")
    print(f"-> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
