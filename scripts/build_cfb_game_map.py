#!/usr/bin/env python3
"""Bridge ESPN game state to venue prices. Idempotent; safe to re-run.

    python3 scripts/build_cfb_game_map.py --dry-run     # print, write nothing
    python3 scripts/build_cfb_game_map.py               # upsert cfb_game_map
    python3 scripts/build_cfb_game_map.py --days 14     # widen the window

WHY: `espn_cfb_live_plays.game_id` is an ESPN event id and
`market_snapshots.game_id` is a venue id, and they have ZERO overlap. Without
this map a football model has inputs and prices it cannot attach to each other.

WHAT IT REFUSES TO DO
---------------------
A mispaired game is silent and unrecoverable: the model would train one game's
state against another game's prices, and every validation would pass because
both halves are internally consistent. So this script writes `match_confidence`
on every row and, below `--min-confidence`, writes NOTHING and reports the game
as unmatched rather than guessing. An unmatched game is a visible gap; a wrong
match is an invisible one.

THE TWO TRAPS, both measured rather than assumed
-------------------------------------------------
1. ESPN's scoreboard DEFAULTS to `groups=80` (FBS). Fetching "all games" and
   "FBS games" returns the identical list, which reads as "there are no FCS
   games" — a clean, confident, wrong zero. FCS is `groups=81`.
   AND THE TWO SETS OVERLAP: 48 of 126 games appear in both, because an
   FBS-vs-FCS game belongs to each division. Labelling by whichever scoreboard
   answered first therefore encodes FETCH ORDER as division, and reading that
   as FCS-vs-FCS overstates the out-of-population share by more than
   twentyfold. Measured on our own board, the true three-way split is
   FBS-v-FBS 64.7%, CROSS 33.8%, FCS-v-FCS 1.5% of fill volume — and CFBD's
   FBS data covers the first two, because an FBS team's games are in CFBD
   whatever the opponent's division. So the genuinely uncovered population is
   one game, not a third of the board.
2. Slug/event dates are VENUE-LOCAL; ESPN's event date is UTC, so a night
   kickoff lands on the next UTC day. Exact-date matching left 45.3% of fills
   unclassified — including games known to exist (utep-okl, col-gtech,
   mia-stan). A +/-1 day tolerance took that to 1.7%.
"""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SCOREBOARD = ("https://site.api.espn.com/apis/site/v2/sports/football/"
              "college-football/scoreboard")
#: 80 = FBS (ESPN's DEFAULT, hence trap 1), 81 = FCS.
#: THESE SETS OVERLAP. A `groups` filter is not a partition: an FBS-vs-FCS
#: game is listed under BOTH divisions, correctly. Measured 2026-09-05: 48 of
#: 126 games were in both (NAU @ ARIZ, INST @ PUR, NICH @ KSU ...). Labelling
#: by "whichever scoreboard I saw it in first" therefore produces a division
#: that depends on fetch order — and reading it as FCS-vs-FCS overstates the
#: out-of-population share by more than twentyfold (33.8% vs the true 1.5%).
GROUPS = {"FBS": 80, "FCS": 81}

#: The real taxonomy, and the one that decides training coverage:
#:   FBS   both teams FBS          — CFBD covers it
#:   CROSS one of each             — CFBD covers it too, because an FBS team's
#:                                   games are in CFBD whatever the opponent.
#:                                   This is the BLOWOUT TAIL (49.5-pt spreads).
#:   FCS   both teams FCS          — genuinely outside an FBS training set
DIVISIONS = ("FBS", "CROSS", "FCS")


def _norm(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def fetch_espn(days_back: int) -> list[dict]:
    """Every CFB event in the window, from BOTH divisions."""
    import httpx

    today = dt.datetime.now(dt.timezone.utc).date()
    out: list[dict] = []
    by_id: dict[str, dict] = {}
    #: membership per scoreboard — the OVERLAP is what identifies a cross-
    #: division game, so we must not let the first fetch claim the id.
    seen_in: dict[str, set[str]] = {"FBS": set(), "FCS": set()}
    with httpx.Client(timeout=30.0) as c:
        for back in range(days_back + 1):
            d = (today - dt.timedelta(days=back)).strftime("%Y%m%d")
            for div, grp in GROUPS.items():
                try:
                    r = c.get(SCOREBOARD, params={"dates": d, "groups": grp,
                                                  "limit": 400})
                    r.raise_for_status()
                except Exception as exc:                       # noqa: BLE001
                    print(f"  ! scoreboard {d} {div} failed: {exc}",
                          file=sys.stderr)
                    continue
                for e in (r.json().get("events") or []):
                    seen_in[div].add(e["id"])
                    if e["id"] in by_id:
                        continue
                    comps = (e.get("competitions") or [{}])[0].get("competitors", [])
                    if len(comps) != 2:
                        continue
                    side = {}
                    for cc in comps:
                        t = cc.get("team") or {}
                        side[cc.get("homeAway")] = {
                            "id": str(t.get("id") or ""),
                            "name": t.get("displayName") or "",
                            "variants": {_norm(t.get(k)) for k in
                                         ("abbreviation", "shortDisplayName",
                                          "location", "name", "displayName")
                                         if t.get(k)},
                        }
                    if "home" not in side or "away" not in side:
                        continue
                    by_id[e["id"]] = {
                        "espn_game_id": e["id"],
                        "date": dt.date.fromisoformat(e["date"][:10]),
                        "home": side["home"], "away": side["away"]}

    # Division is decided by MEMBERSHIP IN BOTH SETS, not by fetch order.
    for gid, g in by_id.items():
        in_fbs, in_fcs = gid in seen_in["FBS"], gid in seen_in["FCS"]
        g["division"] = ("CROSS" if (in_fbs and in_fcs)
                         else "FBS" if in_fbs else "FCS")
        out.append(g)
    return out


def fetch_venue_games(days_back: int) -> list[dict]:
    """Distinct venue games from the market tape, with their event slug."""
    from sqlalchemy import create_engine, text

    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("set DATABASE_URL")
    eng = create_engine(url, pool_pre_ping=True)
    sql = text("""
        SELECT DISTINCT game_id, event_slug,
               (min(game_start_time) OVER (PARTITION BY game_id))::date AS venue_date
        FROM market_snapshots
        WHERE market_slug ~ '-cfb-'
          AND captured_at > now() - make_interval(days => :d)
          AND game_id IS NOT NULL AND event_slug IS NOT NULL
    """)
    with eng.connect() as c:
        return [dict(r._mapping) for r in c.execute(sql, {"d": days_back + 1})]


def _slug_tokens(event_slug: str) -> tuple[str, str] | None:
    """'cfb-ntx-ind-2026-09-05' -> ('ntx','ind'). Also tolerates a league
    prefix ('asc-cfb-col-gtech-...')."""
    s = re.sub(r"^[a-z]+-(?=cfb-)", "", event_slug)
    m = re.match(r"^cfb-([a-z0-9]+)-([a-z0-9]+)-(\d{4}-\d{2}-\d{2})", s)
    return (m.group(1), m.group(2)) if m else None


def _score(tok: str, variants: set[str]) -> float:
    best = 0.0
    for v in variants:
        if not v:
            continue
        if tok == v:
            return 1.0
        r = difflib.SequenceMatcher(None, tok, v).ratio()
        if v.startswith(tok) and len(tok) >= 3:
            r = max(r, 0.92)
        best = max(best, r)
    return best


def match(venue: list[dict], espn: list[dict], min_conf: float) -> tuple[list[dict], list[dict]]:
    rows, unmatched = [], []
    for vg in venue:
        toks = _slug_tokens(vg["event_slug"] or "")
        if not toks:
            unmatched.append({**vg, "reason": "unparseable event_slug"})
            continue
        a, b = toks
        best, best_s = None, 0.0
        for eg in espn:
            if vg["venue_date"] and abs((eg["date"] - vg["venue_date"]).days) > 1:
                continue
            s = max(_score(a, eg["away"]["variants"]) + _score(b, eg["home"]["variants"]),
                    _score(a, eg["home"]["variants"]) + _score(b, eg["away"]["variants"])) / 2.0
            if s > best_s:
                best_s, best = s, eg
        if best is None or best_s < min_conf:
            unmatched.append({**vg, "reason": f"best confidence {best_s:.3f} < {min_conf}"})
            continue
        rows.append({
            "espn_game_id": best["espn_game_id"],
            "venue_game_id": str(vg["game_id"]),
            "event_slug": vg["event_slug"],
            "division": best["division"],
            "home_espn_team_id": best["home"]["id"],
            "away_espn_team_id": best["away"]["id"],
            "home_espn_name": best["home"]["name"][:96],
            "away_espn_name": best["away"]["name"][:96],
            "espn_date": best["date"],
            "venue_date": vg["venue_date"],
            "match_method": "slug_fuzzy_date_pm1",
            "match_confidence": round(best_s, 3),
            "date_offset_days": ((best["date"] - vg["venue_date"]).days
                                 if vg["venue_date"] else None),
        })
    return rows, unmatched


def write(rows: list[dict]) -> int:
    from sqlalchemy import create_engine
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from core.storage.models_cfb_map import CfbGameMap

    eng = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    n = 0
    with eng.begin() as c:
        for r in rows:
            stmt = pg_insert(CfbGameMap.__table__).values(**r)
            stmt = stmt.on_conflict_do_update(
                index_elements=["espn_game_id"],
                set_={k: stmt.excluded[k] for k in
                      ("venue_game_id", "event_slug", "division",
                       "home_espn_team_id", "away_espn_team_id",
                       "home_espn_name", "away_espn_name", "espn_date",
                       "venue_date", "match_method", "match_confidence",
                       "date_offset_days")})
            c.execute(stmt)
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the ESPN<->venue CFB game map.")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--min-confidence", type=float, default=0.72,
                    help="below this a game is reported UNMATCHED, never guessed")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    espn = fetch_espn(a.days)
    venue = fetch_venue_games(a.days)
    by_div = {}
    for e in espn:
        by_div[e["division"]] = by_div.get(e["division"], 0) + 1
    print(f"ESPN events: {len(espn)}  ({by_div})")
    print(f"venue CFB games on the tape: {len(venue)}")

    rows, unmatched = match(venue, espn, a.min_confidence)
    div = {}
    for r in rows:
        div[r["division"]] = div.get(r["division"], 0) + 1
    print(f"\nMATCHED {len(rows)}  {div}")
    if rows:
        lo = min(float(r["match_confidence"]) for r in rows)
        off = sum(1 for r in rows if r["date_offset_days"])
        print(f"  lowest confidence kept: {lo:.3f}"
              f"   |  needed a date offset: {off}/{len(rows)}")
    # rule 22: an unmatched count never prints bare.
    print(f"UNMATCHED {len(unmatched)} (reported, NOT guessed)")
    for u in unmatched[:8]:
        print(f"    {u['event_slug']}  <- {u['reason']}")

    if a.dry_run:
        print("\n--dry-run: nothing written.")
        return 0
    print(f"\nwrote {write(rows)} rows to cfb_game_map")
    return 0


if __name__ == "__main__":
    sys.exit(main())
