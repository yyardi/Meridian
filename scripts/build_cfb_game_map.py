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

# __file__ is absent when this is piped over stdin (how analysis runs reach
# prod); fall back to the mounted repo root rather than NameError.
sys.path.insert(0, os.environ.get("MERIDIAN_ROOT") or (
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if "__file__" in globals() else os.getcwd()))

#: ONE builder, two leagues. The football-shaped tables hold NFL rows under
#: league='nfl' (see espn_cfb_storage), and the venue's NFL slugs have the
#: same shape as CFB's with 'nfl' in the league slot: 'aec-nfl-sf-lar-2026-09-10'.
#: The ESPN scoreboard differs in path and in having no division groups.
LEAGUE_PATHS = {"cfb": "college-football", "nfl": "nfl"}
LEAGUE = "cfb"                       # set by --league in main()


def scoreboard_url() -> str:
    return ("https://site.api.espn.com/apis/site/v2/sports/football/"
            f"{LEAGUE_PATHS[LEAGUE]}/scoreboard")


SCOREBOARD = scoreboard_url()        # kept for any caller that reads the name
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


def fetch_espn(days_back: int, days_ahead: int = 0) -> list[dict]:
    """Every event in the window. CFB: from BOTH divisions. NFL: one
    scoreboard, no groups. `days_ahead` exists because the NFL map has to be
    built BEFORE kickoff from ESPN's scheduled (state=pre) events, and a
    builder that only looks back dry-runs to a clean, confident, useless zero."""
    import httpx

    today = dt.datetime.now(dt.timezone.utc).date()
    out: list[dict] = []
    by_id: dict[str, dict] = {}
    #: membership per scoreboard — the OVERLAP is what identifies a cross-
    #: division game, so we must not let the first fetch claim the id.
    groups = GROUPS if LEAGUE == "cfb" else {"NFL": None}
    seen_in: dict[str, set[str]] = {k: set() for k in groups}
    with httpx.Client(timeout=30.0) as c:
        for back in range(-days_ahead, days_back + 1):
            d = (today - dt.timedelta(days=back)).strftime("%Y%m%d")
            for div, grp in groups.items():
                params = {"dates": d, "limit": 400}
                if grp is not None:
                    params["groups"] = grp
                try:
                    r = c.get(scoreboard_url(), params=params)
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
        if LEAGUE == "nfl":
            g["division"] = "NFL"
        else:
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
        WHERE market_slug ~ :pat
          AND captured_at > now() - make_interval(days => :d)
          AND game_id IS NOT NULL AND event_slug IS NOT NULL
    """)
    with eng.connect() as c:
        return [dict(r._mapping) for r in c.execute(
            sql, {"d": days_back + 1, "pat": f"-{LEAGUE}-"})]


def _slug_tokens(event_slug: str) -> tuple[str, str] | None:
    """'cfb-ntx-ind-2026-09-05' -> ('ntx','ind'). Also tolerates a league
    prefix ('asc-cfb-col-gtech-...')."""
    s = re.sub(rf"^[a-z]+-(?={LEAGUE}-)", "", event_slug)
    m = re.match(rf"^{LEAGUE}-([a-z0-9]+)-([a-z0-9]+)-(\d{{4}}-\d{{2}}-\d{{2}})", s)
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


def match(venue: list[dict], espn: list[dict], min_conf: float,
          admit: frozenset = frozenset()) -> tuple[list[dict], list[dict]]:
    """`admit` is a set of venue slugs a HUMAN has reviewed against the printed
    nearest candidate; for those the threshold is waived and the row is written
    with match_method='reviewed_near_miss' so the override is visible forever."""
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
        admitted = (vg["event_slug"] or "") in admit and best is not None
        if not admitted and (best is None or best_s < min_conf):
            # Name the nearest candidate so a human can judge the miss. It is
            # printed, never written: a near-miss that LOOKS right is exactly the
            # containment trap ('Washington' in 'Washington State').
            cand = (f"  nearest: {best['away']['name']} @ {best['home']['name']}"
                    if best is not None else "  nearest: none within +-1 day")
            unmatched.append({**vg, "reason": f"best confidence {best_s:.3f} < {min_conf}{cand}"})
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
            "match_method": "reviewed_near_miss" if admitted else "slug_fuzzy_date_pm1",
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
    ap.add_argument("--league", choices=sorted(LEAGUE_PATHS), default="cfb")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--days-ahead", type=int, default=0,
                    help="also fetch ESPN's scheduled events this many days "
                         "forward; needed to build a map BEFORE kickoff")
    ap.add_argument("--min-confidence", type=float, default=0.72,
                    help="below this a game is reported UNMATCHED, never guessed")
    ap.add_argument("--admit", default="",
                    help="comma-separated venue slugs reviewed by a human against "
                         "the printed nearest candidate; written below threshold "
                         "with match_method=reviewed_near_miss")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--emit-csv", metavar="PATH",
                    help="write the MATCHED rows to a CSV instead of (or as well "
                         "as) the DB. Read-only when combined with --dry-run — "
                         "the bridge is derived data, so a consumer that only "
                         "needs the mapping does not need a prod write.")
    a = ap.parse_args()

    global LEAGUE
    LEAGUE = a.league
    espn = fetch_espn(a.days, a.days_ahead)
    venue = fetch_venue_games(a.days)
    by_div = {}
    for e in espn:
        by_div[e["division"]] = by_div.get(e["division"], 0) + 1
    print(f"ESPN events: {len(espn)}  ({by_div})")
    print(f"venue {LEAGUE.upper()} games on the tape: {len(venue)}")

    rows, unmatched = match(venue, espn, a.min_confidence,
                             admit=frozenset(x for x in a.admit.split(',') if x))
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

    if a.emit_csv:
        import csv as _csv
        cols = ["espn_game_id", "venue_game_id", "event_slug", "division",
                "home_espn_team_id", "away_espn_team_id", "home_espn_name",
                "away_espn_name", "espn_date", "venue_date", "match_method",
                "match_confidence", "date_offset_days"]
        with open(a.emit_csv, "w", newline="") as fh:
            w = _csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        print(f"\nemitted {len(rows)} matched rows -> {a.emit_csv}")

    if a.dry_run:
        print("--dry-run: nothing written to the DB.")
        return 0
    print(f"\nwrote {write(rows)} rows to cfb_game_map")
    return 0


if __name__ == "__main__":
    sys.exit(main())
