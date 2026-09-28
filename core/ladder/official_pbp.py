"""The league's own record of every basket, with the wall-clock second it happened.

The speed read (docs/math/thin-league-speed-preregistration.md) times the venue's
price against the venue's OWN score. What that cannot say is how late the venue's
score itself is. EuroLeague publishes, without a key, a shot log whose every row
carries ``UTC`` = the second of the shot (``YYYYMMDDhhmmss``), the game clock and the
running score -- verified 2026-09-28 on 2025-26 game 1 (Efes 85, Maccabi 78: first
basket 17:45:49Z at 09:39, for a 17:45Z tip). Fetched after the game, so its live
refresh rate does not matter.

At the end of each eurolg stream window this writes, beside the venue's tapes:

    <out>/official_<game>.json
      {"source", "fetched_at", "match": {how the venue game was matched to the league's},
       "home", "away", "points": [<the league's rows, verbatim>]}

Matching is explicit, never fuzzy: both venue teams through a hand-written table to
the league's club codes, the same start minute, and the venue's home team must be
the league's local club. Anything else is written as unmatched with the reason and
no points -- a wrong pairing flips every row's direction (a 'Washington' inside
'Washington State' pairing once made a 20c 'edge').
"""
from __future__ import annotations

import datetime as dt
import json
import os

import httpx

GATEWAY = os.environ.get("POLYMARKET_GATEWAY_URL", "https://gateway.polymarket.us")
EL_GAMES = "https://api-live.euroleague.net/v2/competitions/E/seasons/{season}/games"
EL_POINTS = "https://live.euroleague.net/api/Points?gamecode={code}&seasoncode={season}"
EL_SEASON = os.environ.get("MERIDIAN_EUROLEAGUE_SEASON", "E2026")
OFFICIAL_LEAGUES = ("eurolg",)


def _ts(s: str | None) -> dt.datetime | None:
    if not s:
        return None
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(dt.timezone.utc).replace(second=0, microsecond=0)


def venue_game(payload: dict) -> dict:
    """Start (to the minute) and the two team names, home first when the venue says so."""
    e = payload.get("event") if isinstance(payload.get("event"), dict) else payload
    teams = e.get("teams") or []
    home = next((t for t in teams if t.get("ordering") == "home"), None)
    for m in e.get("markets") or []:
        for side in m.get("marketSides") or []:
            t = side.get("team") or {}
            if home is None and t.get("ordering") == "home":
                home = t
    names = [t.get("name") for t in teams]
    hn = (home or {}).get("name")
    away = next((n for n in names if n != hn), None)
    return {"start": _ts(e.get("startTime")), "home": hn, "away": away, "names": names}


#: The venue's EuroLeague team names -> the league's club codes. Written by hand
#: from both lists on 2026-09-28 (20 of 20), by FULL name: the short codes collide
#: across the two sources (venue `par` = Partizan and `prs` = Paris; league PAR =
#: Partizan, PRS = Paris; the venue's `fcb` is Barcelona here and Bayern in bbl),
#: and the league's names carry sponsors ("Fenerbahce Tarfin Istanbul").
VENUE_EUROLEAGUE_CLUB = {
    "ASVEL Lyon-Villeurbanne": "ASV", "Anadolu Efes SK": "IST", "BC Olympiakos Piraeus": "OLY",
    "BC Zalgiris Kaunas": "ZAL", "Baskonia Vitoria-Gasteiz": "BAS", "Bayern Munich": "MUN",
    "Besiktas JK": "BES", "Dubai Basketball": "DUB", "FC Barcelona": "BAR", "Fenerbahce Istanbul": "ULK",
    "Hapoel Tel-Aviv": "HTA", "KK Crvena zvezda Belgrade": "RED", "KK Partizan Belgrade": "PAR",
    "Maccabi Tel-Aviv": "TEL", "Olimpia Milano": "MIL", "Panathinaikos BC": "PAN", "Paris Basketball": "PRS",
    "Real Madrid": "MAD", "Valencia Basket": "PAM", "Virtus Bologna": "VIR",
}


def match_euroleague(vg: dict, schedule: list[dict]) -> tuple[dict | None, dict]:
    """The league's game for the venue's, or None and why: both teams through the table,
    the same start minute, and the venue's home team the league's local club."""
    info = {"venue_start": vg["start"].isoformat() if vg["start"] else None,
            "venue_home": vg["home"], "venue_away": vg["away"]}
    h, a = VENUE_EUROLEAGUE_CLUB.get(vg["home"] or ""), VENUE_EUROLEAGUE_CLUB.get(vg["away"] or "")
    if not h or not a:
        return None, {**info, "why": f"team not in the table: {vg['home'] if not h else vg['away']!r}"}
    games = [g for g in schedule if {g["local"]["club"]["code"], g["road"]["club"]["code"]} == {h, a}
             and _ts(g.get("utcDate")) == vg["start"]]
    if len(games) != 1:
        return None, {**info, "why": f"{len(games)} league games with {h} v {a} at the venue's start"}
    g = games[0]
    info.update(gameCode=g["gameCode"], league_local=g["local"]["club"]["code"], league_road=g["road"]["club"]["code"])
    if g["local"]["club"]["code"] != h:
        return None, {**info, "why": "home/away disagree: the venue's home team is the league's road club"}
    return g, {**info, "why": "both teams by table, same start minute, home = local"}


def save_official(league: str, games: list[str], out_dir: str, client: httpx.Client | None = None) -> list[str]:
    """Fetch and save the league's shot log for each venue game; return the files written."""
    if league not in OFFICIAL_LEAGUES:
        return []
    http = client or httpx.Client(timeout=20.0, headers={"User-Agent": "meridian-official/1"})
    schedule = http.get(EL_GAMES.format(season=EL_SEASON)).json().get("data") or []
    written = []
    for game in games:
        try:
            vg = venue_game(http.get(f"{GATEWAY}/v1/events/slug/{game}").json())
            g, info = match_euroleague(vg, schedule)
            out = {"source": None, "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                   "match": info, "home": vg["home"], "away": vg["away"], "points": []}
            if g is not None:
                url = EL_POINTS.format(code=g["gameCode"], season=EL_SEASON)
                out.update(source=url, league_local=g["local"]["club"]["name"], league_road=g["road"]["club"]["name"],
                           points=http.get(url).json().get("Rows") or [])
            path = os.path.join(out_dir, f"official_{game}.json")
            with open(path, "w") as fh:
                json.dump(out, fh)
            written.append(path)
        except (httpx.HTTPError, ValueError, KeyError) as e:
            print(f"official {game}: {type(e).__name__}: {e}")
    return written


def main() -> int:
    """Backfill: python -m core.ladder.official_pbp <stream-dir> <league>"""
    import sys
    d, league = sys.argv[1], sys.argv[2]
    games = sorted({f[len("slate_books_"):-len(".jsonl")] for f in os.listdir(d) if f.startswith("slate_books_")})
    for p in save_official(league, games, d):
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
