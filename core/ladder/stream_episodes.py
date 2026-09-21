"""Fresh crossings on the venue stream, at update resolution, as episodes.

This is the instrument every ladder number is now measured with, moved
into core/ from the one-off script it was proven as on 2026-09-19 so the
nightly ledger and the tests share one implementation.

What it measures. The stream sends one market per message, so the ladder
is rebuilt as last-known touch per rung, and a crossing can only appear
when one of its legs moves. On every update to rung k, each pair (k, j) is
checked with `core.ladder.scan`'s arithmetic, pair for pair: buy the
higher line at its ask, sell the lower at its bid, subtract the taker fee
on each leg. That is O(rungs) per update; the full-ladder rescan it
replaced was O(rungs^2) and did not finish on one afternoon's tape.

The gate, and where it applies. A crossing OPENS an episode only if both
legs were quoted by the venue within `gate_s` seconds of each other at
that moment. That is the test the REST artifact failed: REST reported
prices the stream showed had already changed, on legs a median 884 s
stale. On the stream an UNCHANGED quote is still the venue's live book --
the venue does not re-push a level nobody touched -- so once an episode is
open it is extended for as long as the pair stays crossed and closed by the
update that un-crosses it, whatever the legs' ages by then. The first
draft re-applied the gate on every re-evaluation and cut an episode off
the moment its quiet leg turned two seconds old; the "median 29 s" of
2026-09-19 was measured that way and is therefore a FLOOR on persistence.
Each episode records the older leg's age when it opened, so a ledger can
bucket by freshness without rescanning. `gate_s=None` opens on any age.

An episode is one pair continuously crossed across consecutive updates.
It opens at the first fresh crossed update and closes at the update that
ends the crossing; its duration is wall clock between those two venue
messages, and its dollars are the BEST instant in it, never the sum: one
mispriced rung crosses against every rung it pairs with and they share a
leg. A pair that appears in exactly one update has duration 0.0.

Measured with this on 2026-09-19 (48 CFB games, 697,492 updates, gate 2 s):
3,615 episodes, 8 worth >= $25, and those 8 lasted a median 28.9 s. The
control in tests/test_stream_episodes.py is two crossings that differ only
in staleness; the gate must separate them or the number means nothing.

PLACES NOTHING and reads no network: files in, arithmetic out.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import statistics
from dataclasses import dataclass, field

from core.ladder.scan import DEFAULT_FEE_RATE, MAX_PLAUSIBLE_EDGE, fee

#: Both legs must have been quoted within this many seconds. 2 s is where
#: the measured edge lives; every ungated number is a different population.
DEFAULT_GATE_S = 2.0
#: The desk's floor, so "worth ticketing" means the same thing here.
DEFAULT_FLOOR_USD = 25.0


@dataclass(frozen=True)
class Episode:
    game: str
    low_line: float
    high_line: float
    opened_at: float          # epoch seconds of the venue message that opened it
    closed_at: float          # epoch seconds of the last message it was seen crossed on
    best_usd: float           # best edge x size at any instant inside it
    best_edge: float          # best per-contract edge, in dollars
    opened_leg_age_s: float   # how old the STALER leg was when the crossing opened

    @property
    def duration_s(self) -> float:
        return round(self.closed_at - self.opened_at, 3)

    @property
    def pair(self) -> tuple[float, float]:
        return (self.low_line, self.high_line)


@dataclass
class GameResult:
    game: str
    path: str
    updates: int = 0
    episodes: list[Episode] = field(default_factory=list)

    def over(self, floor_usd: float) -> list[Episode]:
        return [e for e in self.episodes if e.best_usd >= floor_usd]


def _epoch(s: str | None) -> float | None:
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def line_of(slug: str) -> float | None:
    """`asc-...-neg-10pt5` -> -10.5; the winner `aec-...` -> 0.0; else None."""
    if slug.startswith("aec-"):
        return 0.0
    tail = slug.rsplit("-", 2)
    if len(tail) < 3 or tail[-2] not in ("neg", "pos"):
        return None
    try:
        v = float(tail[-1].replace("pt", "."))
    except ValueError:
        return None
    return -v if tail[-2] == "neg" else v


def game_of(path: str) -> str:
    base = os.path.basename(path)
    if base.startswith("slate_books_") and base.endswith(".jsonl"):
        return base[len("slate_books_"):-len(".jsonl")]
    return base


def scan_book_file(path: str, *, gate_s: float | None = DEFAULT_GATE_S,
                   fee_rate: float = DEFAULT_FEE_RATE) -> GameResult:
    """Every episode in one recorded game, from its book tape, that OPENED
    with both legs quoted within ``gate_s`` seconds (None: any age)."""
    game = game_of(path)
    out = GameResult(game=game, path=path)
    bid: dict[float, float] = {}
    ask: dict[float, float] = {}
    bsz: dict[float, float] = {}
    asz: dict[float, float] = {}
    seen: dict[float, float] = {}
    # pair -> [t_open, t_last, best_usd, best_edge, older_leg_age_at_open]
    live: dict[tuple[float, float], list] = {}

    def close(key: tuple[float, float]) -> None:
        o = live.pop(key)
        out.episodes.append(Episode(game, key[0], key[1], o[0], o[1], o[2], o[3], o[4]))

    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                d = json.loads(ln)
            except ValueError:
                continue
            k = line_of(d.get("slug", ""))
            b, a = d.get("bid"), d.get("ask")
            r = _epoch(d.get("recv"))
            if k is None or b is None or a is None or r is None:
                continue
            if bid.get(k) == b and ask.get(k) == a:
                seen[k] = r
                continue                       # unchanged: rescanning re-counts the instant
            bid[k], ask[k], seen[k] = b, a, r
            bsz[k], asz[k] = d.get("bid_size") or 0.0, d.get("ask_size") or 0.0
            out.updates += 1
            if len(bid) < 2:
                continue
            ak, fak = ask[k], fee(ask[k], fee_rate)
            bk, fbk = bid[k], fee(bid[k], fee_rate)
            for j in list(bid):
                if j == k:
                    continue
                if j < k:                      # k is the HIGHER line: buy k, sell j
                    e = bid[j] - ak - fak - fee(bid[j], fee_rate)
                    sz = min(asz[k], bsz[j])
                else:                          # k is the LOWER line: buy j, sell k
                    e = bk - ask[j] - fbk - fee(ask[j], fee_rate)
                    sz = min(asz[j], bsz[k])
                key = (j, k) if j < k else (k, j)
                crossed = 0.0 < e <= MAX_PLAUSIBLE_EDGE
                o = live.get(key)
                if crossed and o is not None:
                    # Open and still crossed: extend, whatever the legs'
                    # ages. An unchanged quote is the live book.
                    o[1] = r
                    o[2] = max(o[2], e * sz)
                    o[3] = max(o[3], e)
                elif crossed:
                    age = r - min(seen[j], seen[k])
                    if gate_s is None or age <= gate_s:
                        live[key] = [r, r, e * sz, e, round(age, 3)]
                elif o is not None:
                    close(key)
    for key in list(live):
        close(key)
    out.episodes.sort(key=lambda e: (e.opened_at, e.low_line, e.high_line))
    return out


def scan_dir(directory: str, **kw) -> list[GameResult]:
    """Every `slate_books_*.jsonl` under one recorder directory."""
    paths = sorted(os.path.join(directory, n) for n in os.listdir(directory)
                   if n.startswith("slate_books_") and n.endswith(".jsonl"))
    return [scan_book_file(p, **kw) for p in paths]


def summarize(results: list[GameResult], *, floor_usd: float = DEFAULT_FLOOR_USD) -> dict:
    """The numbers the ledger keeps, over one slate."""
    eps = [e for r in results for e in r.episodes]
    big = [e for e in eps if e.best_usd >= floor_usd]
    lives = [e.duration_s for e in eps]
    return {
        "games": sum(1 for r in results if r.updates),
        "updates": sum(r.updates for r in results),
        "episodes": len(eps),
        "one_update": sum(1 for e in eps if e.duration_s == 0.0),
        "over_floor": len(big),
        "sum_best_usd": round(sum(e.best_usd for e in eps), 2),
        "sum_over_floor_usd": round(sum(e.best_usd for e in big), 2),
        "biggest_usd": round(max((e.best_usd for e in eps), default=0.0), 2),
        "median_life_s": round(statistics.median(lives), 3) if lives else None,
        "median_life_over_floor_s": round(statistics.median(e.duration_s for e in big), 3) if big else None,
        "floor_usd": floor_usd,
        "games_with_over_floor": sum(1 for r in results if r.over(floor_usd)),
    }
