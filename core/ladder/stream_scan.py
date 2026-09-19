"""Turn a slate of recorded tape into the table STATUS 0bv has for one game.

0bv is n = 1: one NFL game, sampled every 30 seconds, 180 pair-episodes and a
best-per-episode sum of $4,333. Two things about it are weak and this module
is what fixes both.

**Resolution.** A 30-second sample cannot see an episode shorter than 30
seconds, and it dates every episode to a grid rather than to the update that
opened it. `core.ladder.stream` records every MARKET_DATA update the venue
sends, so the ladder can be rebuilt AT UPDATE RESOLUTION: the scanner runs on
the instant a rung changed, which is finer than anything measured so far.

**n.** One game. A slate is 49.

How the ladder is rebuilt
-------------------------
The stream sends ONE market per message, so there is no instant at which the
whole ladder arrives. The state carried forward is *last known touch per
rung*, and the scanner runs on that state at every update where a rung
actually changed. Two consequences, both stated rather than smoothed over:

* a violation found this way pairs a rung quoted NOW against a rung whose
  last update may be minutes old. That is exactly the phenomenon -- 0bv's
  money was in mid-ladder rungs a maker had not re-quoted for minutes -- and
  it is the same construction `run_live_ladder`'s sweep makes, which also
  takes seconds to read a ladder. It is NOT a claim that the two prices were
  simultaneously *refreshed*; it is a claim that both were the venue's live
  price, which is what a resting order means.
* an unchanged update runs no scan. Re-running it would re-count the same
  instant and inflate every "fraction of instants with a violation".

An episode is a PAIR that stays in violation across consecutive scans. It
opens at the first update the pair is violated on and closes at the last one
before it disappears, so a pair that appears in exactly one scan has duration
0.0 -- 0bv's "one sample" episodes, now at their true resolution.

`max_size` travels with every total on purpose. 0bv's $4,047 was computed with
the cap OFF (`max_size=1e12`); the default here is the scanner's own cap,
which is a DIFFERENT population, and a number from one compared against a
number from the other is a comparison of two things.

PLACES NOTHING. Reads files off disk and returns dataclasses; no venue client,
no socket, no database.
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
from dataclasses import asdict, dataclass

from core.ladder import scan
from core.ladder.intent import is_mid, is_spread_pair

#: `slate_books_cfb-mia-wake-2026-09-18.jsonl` -> the game prefix.
_BOOKS_PREFIX, _SUFFIX = "slate_books_", ".jsonl"


@dataclass(frozen=True)
class Episode:
    """One pair, from the update its violation opened on to the last update it
    survived. `best_*` is the single best instant inside it -- the most one
    perfectly-timed two-leg order could have taken at displayed size, which is
    the same quantity 0bv summed and is NOT a strategy P&L."""

    game: str
    low_line: float
    high_line: float
    start: str
    end: str
    duration_s: float
    updates: int
    best_edge: float
    best_dollars: float
    best_buy: float
    best_sell: float
    best_size: float
    spread_pair: bool
    mid: bool

    @property
    def pair(self) -> tuple[float, float]:
        return (self.low_line, self.high_line)


def game_of(path: str) -> str:
    """The game prefix a books file is for; the basename if it is not one."""
    base = os.path.basename(path)
    if base.startswith(_BOOKS_PREFIX) and base.endswith(_SUFFIX):
        return base[len(_BOOKS_PREFIX):-len(_SUFFIX)]
    return base


def _epoch(recv: str | None) -> float | None:
    """Seconds from the recorder's ISO arrival stamp. `Z` is accepted as well
    as `+00:00` so a tape hand-written for a test reads the same as one the
    recorder wrote."""
    if not recv:
        return None
    try:
        return dt.datetime.fromisoformat(recv.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


class _Open:
    """A violation episode still running, mutated as updates arrive."""

    __slots__ = ("best", "end", "start", "updates")

    def __init__(self, when: str, v) -> None:
        self.start = self.end = when
        self.updates = 1
        self.best = v

    def extend(self, when: str, v) -> None:
        self.end = when
        self.updates += 1
        if v.dollars > self.best.dollars:
            self.best = v


def _close(game: str, key: tuple[float, float], op: _Open) -> Episode:
    v = op.best
    t0, t1 = _epoch(op.start), _epoch(op.end)
    return Episode(
        game=game, low_line=key[0], high_line=key[1], start=op.start, end=op.end,
        duration_s=round((t1 - t0), 3) if (t0 is not None and t1 is not None) else 0.0,
        updates=op.updates, best_edge=v.edge, best_dollars=v.dollars,
        best_buy=v.buy_price, best_sell=v.sell_price, best_size=v.size,
        spread_pair=is_spread_pair(v), mid=is_mid(v))


def episodes_in_book_file(path: str, *, game: str | None = None,
                          fee_rate: float = scan.DEFAULT_FEE_RATE,
                          max_edge: float = scan.MAX_PLAUSIBLE_EDGE,
                          max_size: float = scan.MAX_PLAUSIBLE_SIZE,
                          ) -> tuple[list[Episode], dict]:
    """Reconstruct one game's ladder update by update and return its episodes.

    Returns ``(episodes, totals)``. `totals` names the population every number
    in it is about -- the fee rate, both caps, how many rows were read, how
    many of them moved a rung, and how many scans found anything -- because a
    best-per-episode sum with no population attached is the figure that gets
    quoted back without its caveats.

    A rung with only one side is REMOVED from the ladder rather than carried
    with a null: `scan_ladder` takes (bid, ask, bid_size, ask_size) and prices
    a pair from one rung's ask and another's bid, so a half-quoted rung has no
    price on one of the two sides it might be needed for. Dropping it is what
    `core.ladder.live.sample` already does with an empty side; counting it is
    how the caller can tell an absent rung from an untouched one.
    """
    game = game or game_of(path)
    rungs: dict[float, tuple[float, float, float, float]] = {}
    open_eps: dict[tuple[float, float], _Open] = {}
    done: list[Episode] = []
    rows = parsed = scans = unchanged = one_sided = with_violation = 0
    first_recv = last_recv = None
    try:
        handle = open(path, encoding="utf-8")  # noqa: SIM115 -- closed by the `with` below
    except OSError:
        return [], {"game": game, "file": path, "readable": False, "rows": 0}
    with handle:
        for raw in handle:
            raw = raw.strip()
            if not raw:
                continue
            rows += 1
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue                       # a torn line is skipped, not fatal
            if not isinstance(row, dict) or row.get("line") is None:
                continue
            recv = row.get("recv")
            if not isinstance(recv, str):
                continue
            parsed += 1
            first_recv = first_recv or recv
            last_recv = recv
            line = float(row["line"])
            bid, ask = row.get("bid"), row.get("ask")
            bsz, asz = row.get("bid_size"), row.get("ask_size")
            if bid is None or ask is None:
                one_sided += 1
                touch = None
            else:
                touch = (float(bid), float(ask), float(bsz or 0.0), float(asz or 0.0))
            before = rungs.get(line)
            if touch == before:
                unchanged += 1
                continue
            if touch is None:
                rungs.pop(line, None)
            else:
                rungs[line] = touch
            scans += 1
            found = {(v.low_line, v.high_line): v for v in scan.scan_ladder(
                game, rungs, fee_rate=fee_rate, max_edge=max_edge, max_size=max_size)}
            with_violation += 1 if found else 0
            for key, v in found.items():
                if key in open_eps:
                    open_eps[key].extend(recv, v)
                else:
                    open_eps[key] = _Open(recv, v)
            for key in [k for k in open_eps if k not in found]:
                done.append(_close(game, key, open_eps.pop(key)))
    for key in list(open_eps):
        done.append(_close(game, key, open_eps.pop(key)))
    done.sort(key=lambda e: (e.start, e.low_line, e.high_line))
    best = [e.best_dollars for e in done]
    totals = {
        "game": game, "file": path, "readable": True,
        "rows": rows, "parsed": parsed, "scans": scans, "unchanged": unchanged,
        "one_sided": one_sided, "rungs": len(rungs),
        "scans_with_violation": with_violation,
        "episodes": len(done),
        "episodes_ge_10": sum(1 for d in best if d >= 10.0),
        "episodes_ge_100": sum(1 for d in best if d >= 100.0),
        "sum_best_usd": round(sum(best), 4),
        "max_best_usd": round(max(best), 4) if best else 0.0,
        "first_recv": first_recv, "last_recv": last_recv,
        "fee_rate": fee_rate, "max_edge": max_edge, "max_size": max_size,
    }
    return done, totals


def book_files(out_dir: str) -> list[str]:
    """Every game's books file under an out dir, in game order."""
    return sorted(glob.glob(os.path.join(out_dir, f"{_BOOKS_PREFIX}*{_SUFFIX}")))


def scan_slate(out_dir: str, **kw) -> tuple[list[Episode], list[dict]]:
    """Every recorded game in one directory. `(episodes, per-game totals)`.

    One pass per file rather than one over a merged stream: games are
    independent ladders and merging them would let a rung of one game pair
    against a rung of another, which is not an arbitrage, it is a model.
    """
    episodes: list[Episode] = []
    totals: list[dict] = []
    for path in book_files(out_dir):
        eps, tot = episodes_in_book_file(path, **kw)
        episodes.extend(eps)
        totals.append(tot)
    return episodes, totals


def slate_summary(totals: list[dict]) -> dict:
    """The slate's row under the per-game ones. Sums what is additive and
    counts the games rather than averaging over them: a mean per game over a
    slate where one game carries the whole number says the wrong thing, and
    the per-game rows are right there for the shape."""
    live = [t for t in totals if t.get("readable")]
    return {
        "games": len(live),
        "games_with_an_episode": sum(1 for t in live if t["episodes"]),
        "rows": sum(t["rows"] for t in live),
        "scans": sum(t["scans"] for t in live),
        "scans_with_violation": sum(t["scans_with_violation"] for t in live),
        "episodes": sum(t["episodes"] for t in live),
        "episodes_ge_10": sum(t["episodes_ge_10"] for t in live),
        "episodes_ge_100": sum(t["episodes_ge_100"] for t in live),
        "sum_best_usd": round(sum(t["sum_best_usd"] for t in live), 2),
        "max_best_usd": round(max((t["max_best_usd"] for t in live), default=0.0), 2),
        "max_size": live[0]["max_size"] if live else None,
        "fee_rate": live[0]["fee_rate"] if live else None,
    }


def episode_rows(episodes: list[Episode]) -> list[dict]:
    """Episodes as plain dicts, for a caller writing JSONL or a table."""
    return [asdict(e) for e in episodes]
