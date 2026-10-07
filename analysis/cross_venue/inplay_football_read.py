"""Polymarket vs Kalshi in play, football, at message cadence: the registered read, run once.

The registration is docs/math/cross-venue-inplay-football.md, section "The read, written
before any tape exists". This file runs it as written on the 2026-10-03/04 tapes and prints
every n. A replay over recorded books is a MEASUREMENT of what the two venues displayed; it
is never a result, an edge or a profit, and nothing here places, quotes or opens a venue
socket (the only network call is ESPN's public scoreboard/summary, for the in-play window).

    python analysis/cross_venue/inplay_football_read.py \
        --reads /path/to/artifacts/reads --espn-cache /tmp/espn --out read.json

WHAT IS MATCHED (NFL; CFB is attempted and reported separately)
* Polymarket game `nfl-<first>-<second>-<date>`: YES on the winner `aec-` is the slug's FIRST
  team winning; YES on spread `asc-...-{neg,pos}-<n>pt5` is first-team margin + line > 0, neg
  -> negative line (core.ladder.live.game_and_line). The first team is the AWAY team on US
  team sports (venue fact, docs memory "YES is always the away team"); ESPN's scoreboard is
  read here as an independent cross-check and a game whose first team is not ESPN's away
  team is dropped.
* Kalshi `KXNFLGAME-<key>-<TEAM>` pays if TEAM wins; `KXNFLSPREAD-<key>-<TEAM><N>` pays if
  TEAM wins by over N - 0.5 (the line is ALSO read from yes_sub_title and the two must agree).
* Identity: Kalshi code -> ESPN via core.kalshi.mapping.KALSHI_TO_ESPN_NFL; Polymarket code ->
  ESPN via POLYMARKET_NFL_TO_ESPN below (core.team_mapping holds WNBA only). The two games
  join on (unordered ESPN pair, date). Orientation: the Kalshi team's ESPN code equals the
  Polymarket FIRST team's (Kalshi YES = Polymarket YES on the rung with line -L) or the
  SECOND team's (Kalshi YES = Polymarket NO on the rung with line +L). Anything else is
  DROPPED and counted, never guessed.

EVERY CONTRACT IS READ IN ONE FRAME: outcome O = the Kalshi market's YES.
  Kalshi : bid_O = yes_bid (size yes_bid_size); ask_O = 1 - no_bid (size no_bid_size).
  Poly   : sign +1 -> bid_O = bid, ask_O = ask; sign -1 -> bid_O = 1 - ask (size ask_size),
           ask_O = 1 - bid (size bid_size).

KALSHI GHOST LEVELS (found running this read, 2026-10-07). core/kalshi/lip_scorer.Books keeps
a level until its float size falls to 1e-9; a level of 10^6-10^7 contracts that is fully
cancelled leaves a float residue above that, and the residue stays at its price as the
displayed "best" level with a size that rounds to 0.00. The venue's size resolution is 0.01,
so a displayed side under 0.01 cannot be a real order. Every crossed or locked Kalshi touch on
these tapes carries such a side (crossed with both sizes >= 0.01: 0). A Kalshi state with a
side under 0.01, or crossed/locked, is INVALID here: excluded and counted, like a stale one.
The true level behind a ghost is not on the tape (deltas were not recorded), so it cannot be
repaired.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import gzip
import json
import math
import os
import re
import sys
import urllib.request
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core.fees import (
    KALSHI_TAKER,
    POLYMARKET_TAKER,
)
from core.kalshi.mapping import (
    KALSHI_TO_ESPN_NCAAF,
    KALSHI_TO_ESPN_NFL,
    LEAGUE_CFB,
    LEAGUE_NFL,
    local_date_from_game_key,
    parse_game_key,
)
from core.ladder.live import game_and_line

# ----------------------------------------------------------------------------- registered constants
STALE_S = 1.0            # the other venue's last message must be <= 1 s before the instant
GAP_MIN_CENTS = 1.0      # net gap >= 1 cent
HORIZONS_S = (1, 2, 5, 10)
HOLD_S = 60.0
MIN_TAKE_SIZE = 1.0      # rule 3 counts only where the lagging side displays >= 1 contract
KALSHI_SIZE_RESOLUTION = 0.01   # below this a displayed Kalshi side is a float ghost, not an order
CONCENTRATION = 0.80
MIN_GAMES_FOR_ARM = 10
GHOST = 0.005            # touch sizes are written rounded to 2 dp; < 0.005 means it printed 0.00

#: The tapes this read is registered on (reads/<dir>). nfl-10050010 is the SUNDAY-night game
#: (DET at CAR, kick 2026-10-05 00:20Z) and IS covered by Kalshi nfl-1004 (tag 26OCT04). The
#: MONDAY-night game (ATL at NO, kick 10-06 00:15Z) is stream/nfl-10060005 and has no Kalshi
#: tape at all (the 26OCT05 Kalshi recorder never ran), so it cannot be paired.
NFL_POLY_DIRS = ("stream/nfl-10041320", "stream/nfl-10041955", "stream/nfl-10050010")
NFL_KALSHI_DIR = "kalshi/nfl-1004"
CFB_POLY_DIRS = ("stream/cfb-10031450", "stream/cfb-10031850", "stream/cfb-10032250")
CFB_KALSHI_DIR = "kalshi/cfb-1003"
ESPN_DATES = {LEAGUE_NFL: ("20261004", "20261005")}
ESPN_PATH = {LEAGUE_NFL: "football/nfl"}

#: Polymarket US NFL slug code -> ESPN abbreviation. Explicit for the reason
#: core.team_mapping.POLYMARKET_TO_ESPN is: a table fails loudly, `.upper()` fails silently.
#: Thirty of these were seen on the 10-04/05 slugs; `cle` and `pit` (bye) were not.
POLYMARKET_NFL_TO_ESPN: dict[str, str] = {
    "ari": "ARI", "atl": "ATL", "bal": "BAL", "buf": "BUF", "car": "CAR", "chi": "CHI",
    "cin": "CIN", "cle": "CLE", "dal": "DAL", "den": "DEN", "det": "DET", "gb": "GB",
    "hou": "HOU", "ind": "IND", "jax": "JAX", "kc": "KC", "lac": "LAC", "lar": "LAR",
    "lv": "LV", "mia": "MIA", "min": "MIN", "ne": "NE", "no": "NO", "nyg": "NYG",
    "nyj": "NYJ", "phi": "PHI", "pit": "PIT", "sea": "SEA", "sf": "SF", "tb": "TB",
    "ten": "TEN",
    "was": "WSH",    # <- differs (Kalshi WAS, ESPN WSH)
}

UTC = dt.timezone.utc


# ----------------------------------------------------------------------------- fees
def poly_fee(p):
    """Polymarket US taker, per contract, unrounded as registered: 0.0695 * p * (1 - p)."""
    return POLYMARKET_TAKER * p * (1.0 - p)


def kalshi_fee(p):
    """Kalshi quadratic_with_maker_fees taker, per contract, rounded UP to the cent.
    The product is rounded to 1e-9 cents first so float noise cannot push an exact
    cent over the edge (round to the tick before comparing)."""
    raw = np.asarray(KALSHI_TAKER * np.asarray(p, dtype=float) * (1.0 - np.asarray(p, dtype=float)) * 100.0)
    out = np.ceil(np.round(raw, 9)) / 100.0
    return float(out) if out.ndim == 0 else out


def net_gap(k_bid, k_bid_size, k_ask, k_ask_size, p_bid, p_bid_size, p_ask, p_ask_size):
    """The registered net gap, in the outcome-O frame, both directions; returns (net, dir, size).

    dir 1: buy O on Polymarket at its ask, sell O on Kalshi at its bid.
    dir 2: buy O on Kalshi at its ask, sell O on Polymarket at its bid.
    net = dearer bid - cheaper ask - both taker fees at those prices; size = min of the two
    displayed sizes on the legs used. Vectorised over numpy arrays."""
    g1 = k_bid - p_ask - poly_fee(p_ask) - kalshi_fee(k_bid)
    g2 = p_bid - k_ask - kalshi_fee(k_ask) - poly_fee(p_bid)
    s1 = np.minimum(p_ask_size, k_bid_size)
    s2 = np.minimum(k_ask_size, p_bid_size)
    use1 = g1 >= g2
    return np.where(use1, g1, g2), np.where(use1, 1, 2), np.where(use1, s1, s2)


# ----------------------------------------------------------------------------- identity and orientation
_POLY_GAME = re.compile(r"^(?P<lg>nfl|cfb)-(?P<a>[a-z0-9]+)-(?P<b>[a-z0-9]+)-(?P<date>\d{4}-\d{2}-\d{2})$")
_K_SPREAD_SUB = re.compile(r"^(?P<tok>\S+) .* wins by over (?P<line>\d+(?:\.\d+)?) points?$")


@dataclass(frozen=True)
class KalshiMarket:
    ticker: str
    kind: str            # 'winner' | 'spread'
    game_key: str        # 26OCT04DETCAR
    team_code: str       # venue code from the ticker suffix
    line: float          # 0 for winners, L for "wins by over L"


def parse_kalshi_market(m: dict) -> KalshiMarket | None:
    """One tickers.json row -> KalshiMarket, or None when the ticker and the venue's own
    sub-title disagree (the line, or the team token). Never infers."""
    tk = m.get("ticker") or ""
    series = m.get("series") or tk.split("-", 1)[0]
    parts = tk.split("-")
    if len(parts) != 3:
        return None
    _, gk, suffix = parts
    if series in ("KXNFLGAME", "KXNCAAFGAME"):
        return KalshiMarket(tk, "winner", gk, suffix, 0.0)
    if series in ("KXNFLSPREAD", "KXNCAAFSPREAD"):
        mm = re.match(r"^([A-Z]+)(\d+)$", suffix)
        sub = _K_SPREAD_SUB.match((m.get("yes_sub_title") or "").strip())
        if not mm or not sub:
            return None
        code, n = mm.group(1), int(mm.group(2))
        line = float(sub.group("line"))
        if abs(line - (n - 0.5)) > 1e-9:
            return None
        if not code.startswith(sub.group("tok")):     # 'LA' for LAC/LAR, 'NY' for NYG/NYJ
            return None
        return KalshiMarket(tk, "spread", gk, code, line)
    return None


def poly_game_teams(game: str) -> tuple[str, str, dt.date] | None:
    """'nfl-det-car-2026-10-04' -> ('det', 'car', date). First = the slug's YES team."""
    m = _POLY_GAME.match(game)
    if not m:
        return None
    return m.group("a"), m.group("b"), dt.date.fromisoformat(m.group("date"))


def orient(kalshi_team_espn: str, poly_first_espn: str, poly_second_espn: str) -> int | None:
    """+1: Kalshi YES is Polymarket YES. -1: Kalshi YES is Polymarket NO. None: not established."""
    if not kalshi_team_espn or poly_first_espn == poly_second_espn:
        return None
    if kalshi_team_espn == poly_first_espn:
        return +1
    if kalshi_team_espn == poly_second_espn:
        return -1
    return None


def poly_slug_for(game: str, kind: str, line: float, sign: int) -> str:
    """The Polymarket market that carries the Kalshi contract's outcome (or its complement).

    Kalshi "T wins by over L": T is the slug's first team (sign +1) -> first margin - L > 0
    = YES on the rung with line -L (`neg`); T is the second team (sign -1) -> first margin <
    -L = NO on the rung with line +L (`pos`). Half-point lines only, so no push."""
    if kind == "winner":
        return f"aec-{game}"
    n = line - 0.5
    if abs(n - round(n)) > 1e-9 or line <= 0:
        raise ValueError(f"not a half-point spread line: {line}")
    return f"asc-{game}-{'neg' if sign > 0 else 'pos'}-{round(n)}pt5"


def settles_yes_kalshi(kind: str, team_margin: int, line: float) -> bool:
    """Kalshi: winner pays if the team wins; spread pays if the team wins by over `line`."""
    return team_margin > 0 if kind == "winner" else team_margin > line


def settles_yes_poly(first_margin: int, poly_line: float) -> bool:
    """Polymarket (slug frame, 196/196 verified): YES iff first-team margin + line > 0."""
    return first_margin + poly_line > 0


@dataclass(frozen=True)
class Pair:
    league: str
    game: str            # polymarket game key
    espn_id: str
    kalshi_ticker: str
    poly_slug: str
    sign: int
    kind: str
    line: float


def match_contracts(league: str, kalshi_markets: list[dict], poly_games: list[str],
                    espn_games: dict[str, dict]) -> tuple[list[Pair], dict]:
    """Pair every Kalshi market with the Polymarket market of the same outcome.

    Returns (pairs, log) where log counts every drop by reason. espn_games: id -> {away,
    home, date (UTC date str), ...}."""
    log: dict = defaultdict(int)
    log["drops"] = []
    ktable = KALSHI_TO_ESPN_NFL if league == LEAGUE_NFL else KALSHI_TO_ESPN_NCAAF
    # Polymarket games -> ESPN pair
    pidx: dict[tuple[frozenset, dt.date], tuple[str, str, str]] = {}
    for g in poly_games:
        t = poly_game_teams(g)
        if t is None:
            log["poly_game_unparsed"] += 1
            continue
        a, b, d = t
        if league != LEAGUE_NFL:
            log["poly_game_no_code_table"] += 1          # no Polymarket CFB code table exists
            continue
        try:
            ea, eb = POLYMARKET_NFL_TO_ESPN[a], POLYMARKET_NFL_TO_ESPN[b]
        except KeyError:
            log["poly_code_unknown"] += 1
            continue
        pidx[(frozenset({ea, eb}), d)] = (g, ea, eb)
    # ESPN cross-check: first team must be ESPN's away team on the slug date or the next UTC day
    espn_by_pair: dict[frozenset, list[dict]] = defaultdict(list)
    for eid, e in espn_games.items():
        espn_by_pair[frozenset({e["away"], e["home"]})].append({**e, "id": eid})

    pairs: list[Pair] = []
    seen_games: set = set()
    for m in kalshi_markets:
        km = parse_kalshi_market(m)
        if km is None:
            log["kalshi_market_unparsed_or_self_inconsistent"] += 1
            continue
        pk = parse_game_key(km.game_key, league)
        if pk is None:
            log["kalshi_game_key_unparsed"] += 1
            continue
        try:
            kteam = ktable[km.team_code]
            k1, k2 = ktable[pk.first_code], ktable[pk.second_code]
        except KeyError:
            log["kalshi_code_unknown"] += 1
            continue
        if kteam is None or k1 is None or k2 is None:
            log["kalshi_code_has_no_espn_identity"] += 1
            continue
        hit = pidx.get((frozenset({k1, k2}), pk.local_date))
        if hit is None:
            log["no_polymarket_game"] += 1
            log["drops"].append(("no_polymarket_game", km.ticker))
            continue
        game, pfirst, psecond = hit
        sign = orient(kteam, pfirst, psecond)
        if sign is None:
            log["orientation_not_established"] += 1
            log["drops"].append(("orientation_not_established", km.ticker))
            continue
        cands = [e for e in espn_by_pair.get(frozenset({pfirst, psecond}), [])
                 if e["date"] in (pk.local_date.isoformat(), (pk.local_date + dt.timedelta(days=1)).isoformat())]
        if len(cands) != 1:
            log["espn_game_not_unique"] += 1
            log["drops"].append(("espn_game_not_unique", km.ticker))
            continue
        if cands[0]["away"] != pfirst:
            log["poly_first_is_not_espn_away"] += 1
            log["drops"].append(("poly_first_is_not_espn_away", km.ticker))
            continue
        slug = poly_slug_for(game, km.kind, km.line, sign)
        gl = game_and_line(slug)
        if gl is None or gl[0] != game or abs(gl[1] - (-sign * km.line)) > 1e-9:
            log["slug_grammar_disagrees"] += 1
            continue
        pairs.append(Pair(league, game, cands[0]["id"], km.ticker, slug, sign, km.kind, km.line))
        seen_games.add(game)
    log["matched_contracts"] = len(pairs)
    log["matched_games"] = len(seen_games)
    return pairs, log


# ----------------------------------------------------------------------------- tape loading
def _open(path: str):
    return gzip.open(path, "rt", encoding="utf-8") if path.endswith(".gz") else open(path, encoding="utf-8")


def _epoch(iso: str) -> float:
    return dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def _tt_ns(tt: str | None) -> int:
    """Venue transactTime '2026-10-05T00:11:04.182294738Z' -> integer ns (dedupe key)."""
    if not tt:
        return -1
    base, _, frac = tt.rstrip("Z").partition(".")
    sec = int(dt.datetime.fromisoformat(base).replace(tzinfo=UTC).timestamp())
    return sec * 1_000_000_000 + int((frac + "000000000")[:9])


def _nan(x):
    return np.nan if x is None else float(x)


def load_poly(reads: str, dirs: tuple[str, ...], slugs: set[str]) -> tuple[dict[str, dict], dict]:
    """Per slug: arrays t, bid, ask, bid_size, ask_size, open (state OPEN), sorted by receipt.

    Two slate recorders overlapped for ~50 minutes on the early games (19:56-20:47Z). The
    same venue update then appears twice, same transactTime and touch; the copy from the
    second directory is dropped. A row repeated within ONE recorder is kept (it is a
    message, and a message is liveness). Read one game at a time to bound memory."""
    by_game: dict[str, list] = defaultdict(list)
    for di, d in enumerate(dirs):
        for p in sorted(glob.glob(os.path.join(reads, d, "slate_books_*.jsonl*"))):
            game = os.path.basename(p)[len("slate_books_"):].split(".jsonl")[0]
            by_game[game].append((di, p))
    want_games = {s.split("-", 1)[1].split("-neg-")[0].split("-pos-")[0] for s in slugs}
    stats = {"files": 0, "rows_read": 0, "rows_kept_slugs": 0, "cross_dir_duplicates": 0}
    out = {}
    for game, files in sorted(by_game.items()):
        if game not in want_games:
            continue
        raw: dict[str, list] = defaultdict(list)
        for di, p in files:
            stats["files"] += 1
            with _open(p) as f:
                for line in f:
                    stats["rows_read"] += 1
                    i = line.find('"slug":"')
                    if i < 0:
                        continue
                    j = line.find('"', i + 8)
                    if line[i + 8:j] not in slugs:
                        continue
                    r = json.loads(line)
                    raw[r["slug"]].append((_epoch(r["recv"]), _tt_ns(r.get("tt")), di, _nan(r.get("bid")),
                                           _nan(r.get("ask")), _nan(r.get("bid_size")), _nan(r.get("ask_size")),
                                           1.0 if (r.get("state") in (None, "MARKET_STATE_OPEN")) else 0.0))
        for s, rows in raw.items():
            a = np.array(rows, dtype=float)
            # dedupe across directories: sort by (tt, dir, recv); drop a row identical in tt and
            # touch to the previous one when it comes from a different directory
            b = a[np.lexsort((a[:, 0], a[:, 2], a[:, 1]))]
            same = np.zeros(len(b), dtype=bool)
            if len(b) > 1:
                key_eq = (b[1:, 1] == b[:-1, 1]) & (b[1:, 1] >= 0)
                for c in (3, 4, 5, 6):
                    x, y = b[1:, c], b[:-1, c]
                    key_eq &= (x == y) | (np.isnan(x) & np.isnan(y))
                same[1:] = key_eq & (b[1:, 2] != b[:-1, 2])
            stats["cross_dir_duplicates"] += int(same.sum())
            b = b[~same]
            b = b[np.argsort(b[:, 0], kind="stable")]
            stats["rows_kept_slugs"] += len(b)
            out[s] = {"t": b[:, 0], "bid": b[:, 3], "ask": b[:, 4], "bid_size": b[:, 5], "ask_size": b[:, 6],
                      "open": b[:, 7] > 0.5, "tt": np.where(b[:, 1] >= 0, b[:, 1] / 1e9, np.nan)}
    return out, stats


def load_kalshi(reads: str, d: str, tickers: set[str]) -> tuple[dict[str, dict], dict]:
    """Per ticker: arrays t, yes_bid, yes_bid_size, no_bid, no_bid_size from the `touch` lines."""
    out = {}
    stats = {"tickers": 0, "touch_rows": 0}
    for tk in sorted(tickers):
        cands = [os.path.join(reads, d, f"books_{tk}.jsonl.gz"), os.path.join(reads, d, f"books_{tk}.jsonl")]
        p = next((c for c in cands if os.path.exists(c)), None)
        if p is None:
            continue
        rows = []
        with _open(p) as f:
            for line in f:
                if '"type":"touch"' not in line:
                    continue
                r = json.loads(line)
                rows.append((_epoch(r["recv"]), _nan(r.get("yes_bid")), _nan(r.get("yes_bid_size")),
                             _nan(r.get("no_bid")), _nan(r.get("no_bid_size"))))
        if not rows:
            continue
        a = np.array(rows, dtype=float)
        a = a[np.argsort(a[:, 0], kind="stable")]
        out[tk] = {"t": a[:, 0], "yb": a[:, 1], "ys": a[:, 2], "nb": a[:, 3], "ns": a[:, 4]}
        stats["tickers"] += 1
        stats["touch_rows"] += len(a)
    return out, stats


# ----------------------------------------------------------------------------- one frame
def kalshi_frame(k: dict) -> dict:
    """Kalshi touch -> outcome-O (= Kalshi YES) book with validity and the reason it fails."""
    yb, ys, nb, ns = k["yb"], k["ys"], k["nb"], k["ns"]
    bid, ask = yb, 1.0 - nb
    one_sided = np.isnan(yb) | np.isnan(nb)
    ghost = (~one_sided) & ((ys < GHOST) | (ns < GHOST))
    crossed = (~one_sided) & (np.round((yb + nb) * 100.0) >= 100.0)     # locked or crossed
    valid = ~(one_sided | ghost | crossed)
    return {"t": k["t"], "bid": bid, "ask": ask, "bid_size": ys, "ask_size": ns, "valid": valid,
            "one_sided": one_sided, "ghost": ghost, "crossed": crossed}


def poly_frame(p: dict, sign: int) -> dict:
    """Polymarket YES book -> outcome-O book (O = YES when sign +1, NO when sign -1)."""
    if sign > 0:
        bid, ask, bs, as_ = p["bid"], p["ask"], p["bid_size"], p["ask_size"]
    else:
        bid, ask, bs, as_ = 1.0 - p["ask"], 1.0 - p["bid"], p["ask_size"], p["bid_size"]
    one_sided = np.isnan(bid) | np.isnan(ask)
    crossed = (~one_sided) & (np.round(bid * 1e4) >= np.round(ask * 1e4))
    valid = ~one_sided & ~crossed & p["open"] & (bs > 0) & (as_ > 0)
    return {"t": p["t"], "bid": bid, "ask": ask, "bid_size": bs, "ask_size": as_, "valid": valid,
            "one_sided": one_sided, "crossed": crossed, "closed": ~p["open"], "tt": p["tt"]}


def retime_by_venue_clock(pf: dict) -> dict:
    """The same Polymarket rows placed at the venue's own transactTime instead of our receive
    stamp (rows without one dropped), for the lead diagnostic only."""
    ok = np.isfinite(pf["tt"])
    order = np.argsort(pf["tt"][ok], kind="stable")
    out = {k: (v[ok][order] if isinstance(v, np.ndarray) and len(v) == len(ok) else v) for k, v in pf.items()}
    out["t"] = out["tt"]
    return out


def _changed(fr: dict) -> np.ndarray:
    """True where the displayed touch (prices and sizes) differs from the previous row."""
    n = len(fr["t"])
    ch = np.ones(n, dtype=bool)
    if n > 1:
        same = np.ones(n - 1, dtype=bool)
        for c in ("bid", "ask", "bid_size", "ask_size"):
            x, y = fr[c][1:], fr[c][:-1]
            same &= (x == y) | (np.isnan(x) & np.isnan(y))
        ch[1:] = ~same
    return ch


def asof_mid(fr: dict, grid: np.ndarray) -> np.ndarray:
    """Mid of the last row at or before each grid time; NaN where that row is not a valid
    two-sided book or no row exists yet."""
    idx = np.searchsorted(fr["t"], grid, side="right") - 1
    mid = (fr["bid"] + fr["ask"]) / 2.0
    ok = idx >= 0
    out = np.full(len(grid), np.nan)
    ii = idx[ok]
    v = fr["valid"][ii]
    vals = np.where(v, mid[ii], np.nan)
    out[ok] = vals
    return out


# ----------------------------------------------------------------------------- read 1: the gap
def instants_for_pair(pf: dict, kf: dict, t0: float, t1: float) -> dict:
    """Every touch change on either venue inside [t0, t1], with the other venue's state."""
    pch, kch = _changed(pf), _changed(kf)
    pi = np.nonzero(pch & (pf["t"] >= t0) & (pf["t"] <= t1))[0]
    ki = np.nonzero(kch & (kf["t"] >= t0) & (kf["t"] <= t1))[0]
    t = np.concatenate([pf["t"][pi], kf["t"][ki]])
    src = np.concatenate([np.zeros(len(pi), dtype=np.int8), np.ones(len(ki), dtype=np.int8)])
    order = np.lexsort((src, t))
    t, src = t[order], src[order]
    # own index and other index
    p_idx = np.where(src == 0, np.concatenate([pi, np.zeros(len(ki), dtype=int)])[order],
                     np.searchsorted(pf["t"], t, side="right") - 1)
    k_idx = np.where(src == 1, np.concatenate([np.zeros(len(pi), dtype=int), ki])[order],
                     np.searchsorted(kf["t"], t, side="right") - 1)
    other_t = np.where(src == 0, kf["t"][np.maximum(k_idx, 0)], pf["t"][np.maximum(p_idx, 0)])
    missing = np.where(src == 0, k_idx < 0, p_idx < 0)
    age = np.where(missing, np.inf, t - other_t)
    stale = age > STALE_S
    pi_ = np.maximum(p_idx, 0); ki_ = np.maximum(k_idx, 0)
    pvalid = pf["valid"][pi_] & ~(p_idx < 0)
    kvalid = kf["valid"][ki_] & ~(k_idx < 0)
    evaluable = ~stale & pvalid & kvalid
    evaluable_any_age = ~missing & pvalid & kvalid
    net, direction, size = net_gap(kf["bid"][ki_], kf["bid_size"][ki_], kf["ask"][ki_], kf["ask_size"][ki_],
                                   pf["bid"][pi_], pf["bid_size"][pi_], pf["ask"][pi_], pf["ask_size"][pi_])
    net_c = np.round(net * 100.0, 6)
    qual = evaluable & (net_c >= GAP_MIN_CENTS)
    qual_any_age = evaluable_any_age & (net_c >= GAP_MIN_CENTS)
    return {"t": t, "src": src, "p_idx": p_idx, "k_idx": k_idx, "age": age, "stale": stale,
            "p_invalid": ~stale & ~pvalid, "k_invalid": ~stale & ~kvalid,
            "k_ghost": ~stale & kf["ghost"][ki_] & ~(k_idx < 0),
            "k_crossed": ~stale & kf["crossed"][ki_] & ~(k_idx < 0),
            "evaluable": evaluable, "net_c": net_c, "dir": direction,
            "evaluable_any_age": evaluable_any_age, "qual_any_age": qual_any_age,
            "stale_k": stale & (src == 0), "stale_p": stale & (src == 1),
            "dollars": np.where(qual, size * net, 0.0), "qual": qual,
            "p_content_age": np.where(p_idx >= 0, t - pf["tt"][pi_], np.nan),
            "mid_diff": np.where(evaluable, (pf["bid"][pi_] + pf["ask"][pi_] - kf["bid"][ki_] - kf["ask"][ki_]) / 2.0, np.nan)}


def episodes_from(ins: dict, qual: np.ndarray | None = None) -> list[dict]:
    """Maximal runs of consecutive qualifying instants in one direction. Life = start to the
    first later instant (of any kind) that is not part of the run; censored at the last
    instant if the run never ends inside the window."""
    out = []
    q, d, t = (ins["qual"] if qual is None else qual), ins["dir"], ins["t"]
    n = len(t)
    i = 0
    while i < n:
        if not q[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and q[j + 1] and d[j + 1] == d[i]:
            j += 1
        end_i = j + 1 if j + 1 < n else j
        dol = ins["dollars"][i:j + 1]
        out.append({"start": float(t[i]), "life": float(t[end_i] - t[i]), "censored": j + 1 >= n,
                    "instants": j - i + 1, "dir": int(d[i]),
                    "first_dollars": float(dol[0]), "peak_dollars": float(dol.max()),
                    "peak_net_c": float(ins["net_c"][i:j + 1].max())})
        i = j + 1
    return out


def games_for_share(by_game: dict[str, float], share: float = CONCENTRATION) -> int:
    """How many games (largest first) carry `share` of the total."""
    tot = sum(by_game.values())
    if tot <= 0:
        return 0
    acc = 0.0
    for i, v in enumerate(sorted(by_game.values(), reverse=True), 1):
        acc += v
        if acc >= share * tot - 1e-12:
            return i
    return len(by_game)


def _pct(x, q):
    x = np.asarray(x, dtype=float)
    return float(np.percentile(x, q)) if len(x) else float("nan")


# ----------------------------------------------------------------------------- read 2: the lead
def cluster_corr(x: np.ndarray, y: np.ndarray, g: np.ndarray, boot: int = 2000, seed: int = 7) -> dict:
    """Pooled Pearson r with a game-cluster SE two ways: the influence-function sandwich and a
    game-cluster bootstrap (a duplicate measurement; they should agree)."""
    n = len(x)
    if n < 3:
        return {"r": float("nan"), "n": n, "games": 0, "se": float("nan"), "se_boot": float("nan")}
    xc, yc = x - x.mean(), y - y.mean()
    sx, sy = math.sqrt((xc * xc).mean()), math.sqrt((yc * yc).mean())
    if sx == 0 or sy == 0:
        return {"r": float("nan"), "n": n, "games": len(np.unique(g)), "se": float("nan"), "se_boot": float("nan")}
    zx, zy = xc / sx, yc / sy
    r = float((zx * zy).mean())
    psi = zx * zy - r / 2.0 * (zx * zx + zy * zy)
    ug, inv = np.unique(g, return_inverse=True)
    sums = np.bincount(inv, weights=psi)
    G = len(ug)
    se = float(math.sqrt((sums ** 2).sum()) / n * math.sqrt(G / (G - 1))) if G > 1 else float("nan")
    # bootstrap over games: per-game sufficient statistics
    sxs = np.bincount(inv, weights=x); sys_ = np.bincount(inv, weights=y)
    sxx = np.bincount(inv, weights=x * x); syy = np.bincount(inv, weights=y * y); sxy = np.bincount(inv, weights=x * y)
    cnt = np.bincount(inv).astype(float)
    rng = np.random.default_rng(seed)
    rs = []
    for _ in range(boot):
        w = np.bincount(rng.integers(0, G, G), minlength=G).astype(float)
        N = (w * cnt).sum()
        mx, my = (w * sxs).sum() / N, (w * sys_).sum() / N
        vx = (w * sxx).sum() / N - mx * mx; vy = (w * syy).sum() / N - my * my
        cv = (w * sxy).sum() / N - mx * my
        if vx > 0 and vy > 0:
            rs.append(cv / math.sqrt(vx * vy))
    return {"r": r, "n": n, "games": G, "se": se, "se_boot": float(np.std(rs, ddof=1)) if len(rs) > 2 else float("nan")}


def lead_lag(pairs: list[Pair], frames: dict, windows: dict) -> dict:
    """corr(A's mid change over the last h, B's mid change over the next h) on a 1-s grid of
    as-of mids inside each game's in-play window, pooled over contracts, clustered by game."""
    acc = {(a, h): ([], [], []) for a in ("P->K", "K->P") for h in HORIZONS_S}
    grid_points = 0
    gcode = {g: i for i, g in enumerate(sorted({p.espn_id for p in pairs}))}
    for pr in pairs:
        pf, kf = frames[pr.kalshi_ticker]
        t0, t1 = windows[pr.espn_id]
        grid = np.arange(math.ceil(t0), math.floor(t1) + 1, 1.0)
        mp, mk = asof_mid(pf, grid), asof_mid(kf, grid)
        grid_points += len(grid)
        for h in HORIZONS_S:
            if len(grid) <= 2 * h:
                continue
            past_p = mp[h:-h] - mp[:-2 * h]; fut_p = mp[2 * h:] - mp[h:-h]
            past_k = mk[h:-h] - mk[:-2 * h]; fut_k = mk[2 * h:] - mk[h:-h]
            for name, x, y in (("P->K", past_p, fut_k), ("K->P", past_k, fut_p)):
                ok = np.isfinite(x) & np.isfinite(y)
                xs, ys, gs = acc[(name, h)]
                xs.append(x[ok]); ys.append(y[ok]); gs.append(np.full(int(ok.sum()), gcode[pr.espn_id], dtype=np.int32))
    out = {"grid_points": grid_points, "by": {}}
    for (name, h), (xs, ys, gs) in acc.items():
        if not xs:
            continue
        x = np.concatenate(xs); y = np.concatenate(ys); g = np.concatenate(gs)
        res = cluster_corr(x, y, g)
        res["nonzero_x"] = int((x != 0).sum()); res["nonzero_y"] = int((y != 0).sum())
        out["by"][f"{name}@{h}s"] = res
    return out


def lead_exists(ll: dict) -> tuple[str | None, int | None]:
    """A direction leads at horizon h when its r > 0 with the cluster 95% interval above zero
    (both SEs) and it exceeds the reverse direction at that h. Returns the strongest such."""
    best = None
    for h in HORIZONS_S:
        a, b = ll["by"].get(f"P->K@{h}s"), ll["by"].get(f"K->P@{h}s")
        if not a or not b:
            continue
        for name, me, other in (("P->K", a, b), ("K->P", b, a)):
            se = max(me["se"], me["se_boot"])
            if (math.isfinite(me["r"]) and me["r"] - 1.96 * se > 0 and me["r"] > other["r"]
                    and (best is None or me["r"] > best[2])):
                best = (name, h, me["r"])
    return (best[0], best[1]) if best else (None, None)


# ----------------------------------------------------------------------------- read 3: the rule
def taker_rule(pairs: list[Pair], frames: dict, windows: dict, leader: str, h: int) -> dict:
    """Taker on the lagging venue at its displayed touch when the leader's mid has moved by more
    than the lagging venue's round-trip taker fees over the last h seconds; one position per
    contract at a time; held 60 s; marked to the lagging venue's mid (entry fee paid, exit
    neither crossed nor charged -- as registered). Counted only where the lagging side shows
    >= 1 contract and its last message is <= 1 s old."""
    fills = []
    skipped = defaultdict(int)
    for pr in pairs:
        pf, kf = frames[pr.kalshi_ticker]
        L, G = (pf, kf) if leader == "P->K" else (kf, pf)
        gfee = kalshi_fee if G is kf else poly_fee
        t0, t1 = windows[pr.espn_id]
        lch = _changed(L)
        li = np.nonzero(lch & (L["t"] >= t0 + h) & (L["t"] <= t1 - HOLD_S))[0]
        if len(li) == 0:
            continue
        ts = L["t"][li]
        m_now = asof_mid(L, ts); m_then = asof_mid(L, ts - h)
        gi = np.searchsorted(G["t"], ts, side="right") - 1
        m_exit = asof_mid(G, ts + HOLD_S)
        busy_until = -np.inf
        for j in range(len(ts)):
            t = ts[j]
            if t < busy_until:
                continue
            mv = m_now[j] - m_then[j]
            if not np.isfinite(mv):
                continue
            g = gi[j]
            if g < 0:
                continue
            gb, ga = G["bid"][g], G["ask"][g]
            if not G["valid"][g]:
                if abs(mv) > 0.0:
                    skipped["lagger_invalid"] += 1
                continue
            rt = float(gfee(ga)) + float(gfee(gb))
            if abs(mv) <= rt:
                continue
            if t - G["t"][g] > STALE_S:
                skipped["lagger_stale"] += 1
                continue
            if mv > 0:
                if G["ask_size"][g] < MIN_TAKE_SIZE:
                    skipped["lagger_size_under_1"] += 1
                    continue
                if not np.isfinite(m_exit[j]):
                    skipped["unmarked"] += 1
                    continue
                pnl = m_exit[j] - ga - float(gfee(ga))
                price = ga
            else:
                if G["bid_size"][g] < MIN_TAKE_SIZE:
                    skipped["lagger_size_under_1"] += 1
                    continue
                if not np.isfinite(m_exit[j]):
                    skipped["unmarked"] += 1
                    continue
                pnl = gb - m_exit[j] - float(gfee(gb))
                price = gb
            gm = (gb + ga) / 2.0
            side = 1.0 if mv > 0 else -1.0
            fills.append({"game": pr.espn_id, "ticker": pr.kalshi_ticker, "kind": pr.kind, "t": float(t),
                          "move": float(mv), "price": float(price), "pnl": float(pnl),
                          "markout": float(side * (m_exit[j] - gm)), "half_spread": float(abs(price - gm)),
                          "fee": float(gfee(price)),
                          "lagger_content_age": float(t - G["tt"][g]) if "tt" in G else float("nan")})
            busy_until = t + HOLD_S
    out = {"fills": fills, "skipped": dict(skipped),
           **cluster_mean([f["pnl"] for f in fills], [f["game"] for f in fills])}
    if fills:
        out["decomposition"] = {k: float(np.mean([f[k] for f in fills])) for k in ("markout", "half_spread", "fee")}
        fresh = [f for f in fills if not (f["lagger_content_age"] > STALE_S)]
        out["content_fresh"] = cluster_mean([f["pnl"] for f in fresh], [f["game"] for f in fresh])
        for kind in ("winner", "spread"):
            sub = [f for f in fills if f["kind"] == kind]
            out[f"by_kind_{kind}"] = cluster_mean([f["pnl"] for f in sub], [f["game"] for f in sub])
    return out


def cluster_mean(v, g, boot: int = 4000, seed: int = 11) -> dict:
    """Mean per fill with a game-cluster 95% interval (sandwich with t(G-1), and a game
    bootstrap percentile interval as the duplicate)."""
    from scipy import stats
    v = np.asarray(v, dtype=float); g = np.asarray(g, dtype=str)
    n = len(v)
    if n == 0:
        return {"n": 0, "games": 0, "mean": float("nan"), "ci": (float("nan"), float("nan")), "ci_boot": (float("nan"), float("nan"))}
    m = float(v.mean())
    ug, inv = np.unique(g, return_inverse=True)
    G = len(ug)
    if G < 2:
        return {"n": n, "games": G, "mean": m, "ci": (float("nan"), float("nan")), "ci_boot": (float("nan"), float("nan"))}
    s = np.bincount(inv, weights=v - m)
    se = math.sqrt((s ** 2).sum()) / n * math.sqrt(G / (G - 1))
    tq = stats.t.ppf(0.975, G - 1)
    sums = np.bincount(inv, weights=v); cnt = np.bincount(inv).astype(float)
    rng = np.random.default_rng(seed)
    bs = []
    for _ in range(boot):
        w = np.bincount(rng.integers(0, G, G), minlength=G).astype(float)
        bs.append((w * sums).sum() / (w * cnt).sum())
    return {"n": n, "games": G, "mean": m, "se": se, "ci": (m - tq * se, m + tq * se),
            "ci_boot": (float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5)))}


# ----------------------------------------------------------------------------- ESPN in-play windows
def espn_games(league: str, cache: str) -> dict[str, dict]:
    """ESPN id -> {away, home, date (UTC), kick, first_play, last_play}. In play = ESPN's first
    to last play wallclock. Cached as fetched; nothing else is read from ESPN."""
    os.makedirs(cache, exist_ok=True)

    def get(url: str, name: str) -> dict:
        p = os.path.join(cache, name)
        if not os.path.exists(p):
            req = urllib.request.Request(url, headers={"User-Agent": "meridian-research/1"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            with open(p, "wb") as f:
                f.write(data)
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    out = {}
    base = f"https://site.api.espn.com/apis/site/v2/sports/{ESPN_PATH[league]}"
    for d in ESPN_DATES[league]:
        sb = get(f"{base}/scoreboard?dates={d}", f"{league}_scoreboard_{d}.json")
        for e in sb.get("events", []):
            comp = (e.get("competitions") or [{}])[0]
            cs = {c.get("homeAway"): (c.get("team") or {}).get("abbreviation") for c in comp.get("competitors", [])}
            kick = dt.datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
            out[str(e["id"])] = {"away": cs.get("away"), "home": cs.get("home"), "date": kick.date().isoformat(),
                                 "kick": kick.timestamp()}
    if league == LEAGUE_NFL:
        for eid in list(out):
            s = get(f"{base}/summary?event={eid}", f"{league}_summary_{eid}.json")
            walls = [pl["wallclock"] for drv in (s.get("drives") or {}).get("previous", [])
                     for pl in drv.get("plays", []) if pl.get("wallclock")]
            if walls:
                out[eid]["first_play"] = _epoch(min(walls))
                out[eid]["last_play"] = _epoch(max(walls))
    return out


# ----------------------------------------------------------------------------- the run
def _iso(t: float) -> str:
    return dt.datetime.fromtimestamp(t, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def cadence(arrs: list[np.ndarray]) -> dict:
    gaps = np.concatenate([np.diff(a) for a in arrs if len(a) > 1]) if arrs else np.array([])
    return {"n_gaps": len(gaps), "p50": _pct(gaps, 50), "p90": _pct(gaps, 90), "p99": _pct(gaps, 99),
            "share_le_1s": float((gaps <= 1.0).mean()) if len(gaps) else float("nan")}


def run_nfl(reads: str, espn_cache: str) -> dict:
    with open(os.path.join(reads, NFL_KALSHI_DIR, "tickers.json"), encoding="utf-8") as f:
        kt = json.load(f)
    poly_games = sorted({os.path.basename(p)[len("slate_books_"):].split(".jsonl")[0]
                         for d in NFL_POLY_DIRS for p in glob.glob(os.path.join(reads, d, "slate_books_*.jsonl*"))})
    eg = espn_games(LEAGUE_NFL, espn_cache)
    pairs, mlog = match_contracts(LEAGUE_NFL, kt["markets"], poly_games, eg)
    windows = {}
    for pr in pairs:
        e = eg[pr.espn_id]
        windows[pr.espn_id] = (e["first_play"], e["last_play"])
    P, pstats = load_poly(reads, NFL_POLY_DIRS, {p.poly_slug for p in pairs})
    K, kstats = load_kalshi(reads, NFL_KALSHI_DIR, {p.kalshi_ticker for p in pairs})
    frames = {}
    usable = []
    for pr in pairs:
        if pr.poly_slug not in P or pr.kalshi_ticker not in K:
            mlog["no_rows_on_a_tape"] += 1
            continue
        frames[pr.kalshi_ticker] = (poly_frame(P[pr.poly_slug], pr.sign), kalshi_frame(K[pr.kalshi_ticker]))
        usable.append(pr)
    # contracts with zero in-play overlap (the London game ended before Kalshi's recorder began)
    inplay = []
    for pr in usable:
        t0, t1 = windows[pr.espn_id]
        pf, kf = frames[pr.kalshi_ticker]
        if kf["t"].max() < t0 or kf["t"].min() > t1 or pf["t"].max() < t0 or pf["t"].min() > t1:
            mlog["no_inplay_overlap"] += 1
            continue
        inplay.append(pr)

    # cadence, in play, per venue and kind
    cad = {}
    for kind in ("winner", "spread"):
        for ven, k in (("polymarket_all_rows", 0), ("kalshi_touch_rows", 1)):
            arrs = []
            for pr in inplay:
                if pr.kind != kind:
                    continue
                fr = frames[pr.kalshi_ticker][k]
                t0, t1 = windows[pr.espn_id]
                arrs.append(fr["t"][(fr["t"] >= t0) & (fr["t"] <= t1)])
            cad[f"{ven}/{kind}"] = cadence(arrs)
        arrs = []
        for pr in inplay:
            if pr.kind != kind:
                continue
            fr = frames[pr.kalshi_ticker][0]
            t0, t1 = windows[pr.espn_id]
            ch = _changed(fr)
            arrs.append(fr["t"][ch & (fr["t"] >= t0) & (fr["t"] <= t1)])
        cad[f"polymarket_touch_changes/{kind}"] = cadence(arrs)

    # Polymarket delivery: receive stamp minus the venue's own transactTime, every in-play row
    lat, lat_by_game = [], defaultdict(list)
    for pr in inplay:
        pf = frames[pr.kalshi_ticker][0]
        t0, t1 = windows[pr.espn_id]
        m = (pf["t"] >= t0) & (pf["t"] <= t1) & np.isfinite(pf["tt"])
        x = pf["t"][m] - pf["tt"][m]
        lat.append(x)
        lat_by_game[pr.espn_id].append(x)
    lat = np.concatenate(lat) if lat else np.array([])
    poly_delivery = {"rows": len(lat), "p50": _pct(lat, 50), "p90": _pct(lat, 90), "p99": _pct(lat, 99),
                     "max": float(lat.max()) if len(lat) else float("nan"),
                     "share_gt_1s": float((lat > STALE_S).mean()) if len(lat) else float("nan"),
                     "share_gt_1s_by_game": {g: float((np.concatenate(v) > STALE_S).mean()) for g, v in lat_by_game.items()}}

    # read 1, twice: as registered (freshness on receive stamps), and with Polymarket's book
    # CONTENT also <= 1 s old by its own transactTime (a backlogged stream delivers old books
    # on fresh receive stamps; see the doc)
    tot = defaultdict(int)
    eps = {"registered": [], "content_checked": [], "no_staleness_rule": []}
    ages = []
    by_kind = defaultdict(lambda: defaultdict(int))
    flips = []
    spot = None
    per_contract = []
    qual_content_age = []
    for pr in inplay:
        pf, kf = frames[pr.kalshi_ticker]
        t0, t1 = windows[pr.espn_id]
        ins = instants_for_pair(pf, kf, t0, t1)
        n = len(ins["t"])
        content_old = ins["evaluable"] & ~(ins["p_content_age"] <= STALE_S)
        qual2 = ins["qual"] & ~content_old
        c = {"instants": n, "stale": int(ins["stale"].sum()), "p_invalid": int(ins["p_invalid"].sum()),
             "k_invalid": int(ins["k_invalid"].sum()), "k_ghost": int(ins["k_ghost"].sum()),
             "k_crossed": int(ins["k_crossed"].sum()), "evaluable": int(ins["evaluable"].sum()),
             "qual": int(ins["qual"].sum()), "evaluable_content_fresh": int((ins["evaluable"] & ~content_old).sum()),
             "qual_content_fresh": int(qual2.sum()),
             "stale_kalshi_side": int(ins["stale_k"].sum()), "stale_poly_side": int(ins["stale_p"].sum())}
        fresh_content_any_age = ins["evaluable_any_age"] & (ins["p_content_age"] <= STALE_S)
        q3 = ins["qual_any_age"] & fresh_content_any_age
        c["evaluable_no_staleness_rule"] = int(fresh_content_any_age.sum())
        c["qual_no_staleness_rule"] = int(q3.sum())
        for kk, v in c.items():
            tot[kk] += v
            by_kind[pr.kind][kk] += v
        ages.append(ins["age"][np.isfinite(ins["age"])])
        qual_content_age.append(ins["p_content_age"][ins["qual"]])
        md = ins["mid_diff"][np.isfinite(ins["mid_diff"])]
        med_abs = float(np.median(np.abs(md))) if len(md) else float("nan")
        per_contract.append({"ticker": pr.kalshi_ticker, "slug": pr.poly_slug, "sign": pr.sign, **c,
                             "median_abs_mid_diff": med_abs})
        if len(md) and med_abs > 0.15:
            flips.append((pr.kalshi_ticker, pr.poly_slug, med_abs))
        for name, q in (("registered", ins["qual"]), ("content_checked", qual2), ("no_staleness_rule", q3)):
            for e in episodes_from(ins, q):
                e.update({"game": pr.espn_id, "ticker": pr.kalshi_ticker, "slug": pr.poly_slug, "kind": pr.kind})
                if name == "registered":
                    i0 = int(np.searchsorted(ins["t"], e["start"]))
                    e["p_content_age"] = float(ins["p_content_age"][i0])
                eps[name].append(e)
        if spot is None and pr.kind == "winner" and qual2.any():
            j = int(np.nonzero(qual2)[0][0])
            spot = {"pair": pr, "j": j, "t": float(ins["t"][j]), "src": int(ins["src"][j]),
                    "p_t": float(pf["t"][ins["p_idx"][j]]), "k_t": float(kf["t"][ins["k_idx"][j]]),
                    "net_c": float(ins["net_c"][j]), "dir": int(ins["dir"][j]),
                    "p_content_age": float(ins["p_content_age"][j]), "other_age": float(ins["age"][j])}
    ages = np.concatenate(ages) if ages else np.array([])
    qca = np.concatenate(qual_content_age) if qual_content_age else np.array([])

    def summarize(el: list[dict], qual_n: int, eval_n: int) -> dict:
        first, peak = defaultdict(float), defaultdict(float)
        for e in el:
            first[e["game"]] += e["first_dollars"]
            peak[e["game"]] += e["peak_dollars"]
        lives = np.array([e["life"] for e in el])
        long_ = [e for e in el if e["life"] >= 0.25]
        return {"qualifying_instants": qual_n, "evaluable_instants": eval_n,
                "share_qual_of_evaluable": qual_n / eval_n if eval_n else float("nan"),
                "episodes": len(el), "episode_games": len({e["game"] for e in el}),
                "episodes_censored": sum(e["censored"] for e in el),
                "life_p50": _pct(lives, 50), "life_p90": _pct(lives, 90),
                "episodes_life_ge_250ms": len(long_), "episodes_life_ge_1s": int((lives >= 1.0).sum()) if len(lives) else 0,
                "dollars_first_total": sum(first.values()), "dollars_peak_total": sum(peak.values()),
                "dollars_peak_life_ge_250ms": sum(e["peak_dollars"] for e in long_),
                "games_for_80pct_first": games_for_share(first), "games_for_80pct_peak": games_for_share(peak),
                "dollars_peak_by_game": dict(sorted(peak.items(), key=lambda kv: -kv[1])),
                "dollars_first_by_game": dict(sorted(first.items(), key=lambda kv: -kv[1])),
                "episodes_by_kind": {k: sum(1 for e in el if e["kind"] == k) for k in ("winner", "spread")},
                "top_episodes": sorted(el, key=lambda e: -e["peak_dollars"])[:12]}

    read1 = {
        "contracts": len(inplay), "games": len({p.espn_id for p in inplay}),
        "counts": dict(tot), "by_kind": {k: dict(v) for k, v in by_kind.items()},
        "other_venue_age": {"p50": _pct(ages, 50), "p90": _pct(ages, 90),
                            "share_le_1s": float((ages <= STALE_S).mean()) if len(ages) else float("nan")},
        "qualifying_poly_content_age": {"p50": _pct(qca, 50), "p90": _pct(qca, 90),
                                        "share_gt_1s": float((qca > STALE_S).mean()) if len(qca) else float("nan")},
        "registered": summarize(eps["registered"], tot["qual"], tot["evaluable"]),
        "content_checked": summarize(eps["content_checked"], tot["qual_content_fresh"], tot["evaluable_content_fresh"]),
        "no_staleness_rule": summarize(eps["no_staleness_rule"], tot["qual_no_staleness_rule"], tot["evaluable_no_staleness_rule"]),
        "flipped_side_fingerprints": flips,
    }
    # read 2, and the same correlation with Polymarket placed at the venue's transactTime
    # (diagnostic: how much of a receive-time lead is our feed's delivery delay)
    ll = lead_lag(inplay, frames, windows)
    leader, h = lead_exists(ll)
    frames_vc = {k: (retime_by_venue_clock(pf), kf) for k, (pf, kf) in frames.items()}
    ll_vc = lead_lag(inplay, frames_vc, windows)
    read3 = None
    if leader is not None:
        read3 = taker_rule(inplay, frames, windows, leader, h)
    return {"match_log": {k: v for k, v in mlog.items() if k != "drops"}, "drops": mlog["drops"],
            "pairs": [p.__dict__ for p in inplay], "windows": {k: (_iso(a), _iso(b)) for k, (a, b) in windows.items()},
            "espn": {k: v for k, v in eg.items()}, "poly_stats": pstats, "kalshi_stats": kstats, "cadence": cad,
            "poly_delivery": poly_delivery,
            "read1": read1, "per_contract": per_contract, "read2": ll, "read2_venue_clock": ll_vc,
            "leader": leader, "lead_h": h,
            "read3": read3, "spot": spot}


def run_cfb(reads: str) -> dict:
    """CFB, attempted second: orientation must come from both code tables, and neither exists
    in usable form (Kalshi's NCAAF table maps every code to None ON PURPOSE; Polymarket has no
    CFB code table), so every pair is dropped. Exact string coincidence of both codes is
    counted as a diagnostic of what a future table would have to adjudicate, never used."""
    with open(os.path.join(reads, CFB_KALSHI_DIR, "tickers.json"), encoding="utf-8") as f:
        kt = json.load(f)
    poly_games = sorted({os.path.basename(p)[len("slate_books_"):].split(".jsonl")[0]
                         for d in CFB_POLY_DIRS for p in glob.glob(os.path.join(reads, d, "slate_books_*.jsonl*"))})
    pairs, mlog = match_contracts(LEAGUE_CFB, kt["markets"], poly_games, {})
    events = defaultdict(list)
    for m in kt["markets"]:
        events[m["event_ticker"]].append(m)
    pk = {}
    for g in poly_games:
        t = poly_game_teams(g)
        if t:
            pk[(frozenset({t[0].upper(), t[1].upper()}), t[2])] = g
    coincide = []
    for ev, ms in events.items():
        codes = frozenset(m["ticker"].rsplit("-", 1)[1] for m in ms)
        d = local_date_from_game_key(ev.split("-", 1)[1])
        if d is None:
            continue
        g = pk.get((codes, d))
        if g:
            coincide.append((ev, g, [m.get("title") for m in ms]))
    return {"kalshi_markets": len(kt["markets"]), "kalshi_series": kt.get("series"), "kalshi_events": len(events),
            "poly_games": len(poly_games), "matched_contracts": len(pairs),
            "match_log": {k: v for k, v in mlog.items() if k != "drops"},
            "exact_code_pair_coincidences": coincide}


def raw_row(reads: str, dirs: tuple[str, ...], fname_glob: str, want_t: float, key: str, val: str) -> str | None:
    """The tape line at receive time `want_t` (ms) with row[key] == val, verbatim."""
    for d in dirs:
        for p in sorted(glob.glob(os.path.join(reads, d, fname_glob))):
            with _open(p) as f:
                for line in f:
                    if val not in line:
                        continue
                    r = json.loads(line)
                    if r.get(key, val) == val and abs(_epoch(r["recv"]) - want_t) < 5e-4:
                        return line.strip()
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--reads", required=True, help="the artifacts/reads directory (stream/ and kalshi/)")
    ap.add_argument("--espn-cache", required=True)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    nfl = run_nfl(a.reads, a.espn_cache)
    cfb = run_cfb(a.reads)
    sp = nfl["spot"]
    if sp:
        pr = sp["pair"]
        game_file = f"slate_books_{pr.game}.jsonl*"
        sp["poly_raw"] = raw_row(a.reads, NFL_POLY_DIRS, game_file, sp["p_t"], "slug", pr.poly_slug)
        sp["kalshi_raw"] = raw_row(a.reads, (NFL_KALSHI_DIR,), f"books_{pr.kalshi_ticker}.jsonl*", sp["k_t"], "type", "touch")
        sp["pair"] = pr.__dict__
    res = {"nfl": nfl, "cfb": cfb}
    fills = (nfl["read3"] or {}).pop("fills", None) if nfl["read3"] else None
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1, default=str)
        if fills is not None:
            with open(a.out + ".fills.json", "w", encoding="utf-8") as f:
                json.dump(fills, f, default=str)
    r1, r2 = nfl["read1"], nfl["read2"]
    print(json.dumps({"match_log": nfl["match_log"], "poly": nfl["poly_stats"], "kalshi": nfl["kalshi_stats"]}, default=str))
    print(json.dumps({"cadence": nfl["cadence"]}, indent=1, default=str))
    print(json.dumps({"poly_delivery": nfl["poly_delivery"]}, default=str))
    print(json.dumps({k: ({kk: vv for kk, vv in v.items() if kk != "top_episodes"} if isinstance(v, dict) else v)
                      for k, v in r1.items()}, indent=1, default=str))
    for k, v in r2["by"].items():
        print(k, json.dumps(v))
    for k, v in nfl["read2_venue_clock"]["by"].items():
        print("venue-clock", k, json.dumps(v))
    print("leader", nfl["leader"], nfl["lead_h"])
    print("read3", json.dumps(nfl["read3"], default=str))
    print("spot", json.dumps(sp, default=str, indent=1))
    print("cfb", json.dumps(cfb, default=str, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
