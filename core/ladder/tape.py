"""Read the freshness tape back as a ladder anyone can look at.

`cfb/run_ws_freshness.py` already writes, every ~20 s per live game, one JSON
line carrying every rung's REST touch (bid/ask and both sizes), the same rung
as the venue's stream last sent it, and both `transactTime` stamps. That file
is the only per-rung record a file-reading page can reach tonight: the ARB tab
on :8008 samples the venue itself, and it does not exist until the api image
is rebuilt.

So this module turns the newest line of that tape into a ladder table: rungs
ordered by line, the dominance bound each rung must satisfy (YES price is
non-decreasing in the line number, `core.ladder.scan`), which rungs break it,
and how long each book has sat un-requoted. No venue call, no order path --
it reads a file the instrument already wrote.

The bounds are computed here rather than read from the tape because the tape
carries touches, not bounds; the arithmetic is the same relation
`core.ladder.scan.scan_ladder` enforces, stated once more in the one direction
a per-rung table needs:

    a rung's ask must not sit BELOW the best bid of any HARDER rung (lower line)
    a rung's bid must not sit ABOVE the best ask of any EASIER rung (higher line)

Either way round it is the same violation the scanner reports as a pair.

Three choices that are not free, and why they went this way:

REST, not the stream, drives the table. Every tape row carries a REST touch
(`compare()` emits a row only for rungs REST returned) and only some carry a
stream one, so preferring the stream would build the ladder out of two
sources at two instants -- exactly the assembled-across-timestamps ladder
`scan_ladder`'s docstring refuses. REST is also the book the executor acts
on. The stream's disagreement is reported as its own numbers (viol_ws against
viol_rest, and per rung `touch_equal`/`tt_equal`), which is the reviewer's H1
evidence and is worth more kept separate than blended in.

What is LIT is what the scanner says, not what the bound says. The bound is
gross; the scanner nets both fees and drops implausible edges. Deriving the
lit rungs from the scanner's own output means the table and the pair list
below it cannot disagree about which rung is trading against which.

The scanner is called with the executor's arguments (`max_size=1e12`), so the
page shows the population the executor would act on rather than a second,
prettier one. Pairs the executor would NOT take are still counted and named
(above the plausible-edge cap, eaten by fees, winner leg, under the floor) --
a page that silently drops them would print "consistent" over a crossed
ladder. The mid ladder is NOT one of those reasons; see `_why_not`.
"""
from __future__ import annotations

import glob
import json
import os
import time

from core.ladder import scan
from core.ladder.intent import is_mid, is_spread_pair
from core.ladder.live import book_age_s

#: The executor's `--floor-usd` default: edge x displayed size below this is
#: real and untradeable-in-practice, and it is why a lit rung may carry no
#: ticket. Shown so the operator can see the reason rather than infer it.
DEFAULT_FLOOR_USD = 25.0

#: How much of the tail to read on the first pass. One sample of a 12-rung
#: ladder is a few kB, so this holds tens of samples; `samples()` grows it
#: when the caller asks for more history than it found.
_TAIL_BYTES = 262_144


def tape_files(out_dir: str, last: int | None = None) -> list[str]:
    """Freshness tapes, newest modification last; `last` keeps only the
    newest that many. A file that vanishes between the glob and the stat is
    dropped rather than raised on -- the executor rotates these while the
    page is reading them."""
    paths = []
    for p in glob.glob(os.path.join(out_dir, "ws_freshness_*.jsonl")):
        try:
            paths.append((os.path.getmtime(p), p))
        except OSError:
            continue
    paths.sort()
    out = [p for _, p in paths]
    return out[-last:] if last else out


def game_of(path: str) -> str:
    """`ws_freshness_aec-wnba-lv-sea-2026-09-18.jsonl` -> the game prefix."""
    base = os.path.basename(path)
    if base.startswith("ws_freshness_") and base.endswith(".jsonl"):
        return base[len("ws_freshness_"):-len(".jsonl")]
    return base


def same_game(a: str, b: str) -> bool:
    """Game prefixes match with or without the venue's `aec-` head, so a link
    or a typed `?game=` works either way."""
    return a.replace("aec-", "", 1) == b.replace("aec-", "", 1)


def samples(path: str, n: int = 1) -> list[dict]:
    """The newest `n` complete samples, oldest first.

    Read from the END: these files grow all game and the page asks every few
    seconds, so reading the whole file would cost more every quarter. Three
    ways a tail read can lie, all handled here: the writer may be mid-write,
    so the final line is half a JSON object (skipped); our window may start
    inside a line, so the FIRST line of a windowed read is dropped as ours,
    not the writer's; and the window may hold fewer samples than asked for,
    so it grows until it does or until it covers the file.

    A sample with an empty `rows` (the instrument ran before any rung had a
    two-sided book) is a sample and is returned. Only unparseable text and
    objects of another shape are skipped.
    """
    want = _TAIL_BYTES
    while True:
        try:
            size = os.path.getsize(path)
            start = max(0, size - want)
            with open(path, "rb") as f:
                f.seek(start)
                chunk = f.read()
        except OSError:
            return []
        lines = chunk.splitlines()
        if start > 0 and lines:
            lines = lines[1:]           # cut by our seek, not by the writer
        rows = []
        for raw in lines:
            try:
                row = json.loads(raw)
            except ValueError:
                continue
            if isinstance(row, dict) and isinstance(row.get("rows"), list):
                rows.append(row)
        if len(rows) >= n or start == 0:
            return rows[-n:]
        want *= 4


def last_line(path: str) -> dict | None:
    """The newest complete sample in the tape, or None if it holds none."""
    rows = samples(path, 1)
    return rows[-1] if rows else None


def _f(v) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _touch(row: dict, prefer: tuple[str, ...] = ("rest", "ws")) -> dict | None:
    """One rung's touch from the first source that quotes it, or None.

    REST first (see the module docstring). A source that quotes BOTH sides
    wins outright; a source with only one side is remembered and returned
    only if no later source has both, so a half-quoted rung still appears on
    screen -- with `both` False, which keeps it out of the scanner's input.

    A stream-sourced touch is a display row and nothing more: `src` is carried
    out so `ladder()` can keep it out of the scan (`scanned`). Pricing a pair
    off it would assemble the ladder out of two sources at two instants, which
    is what the module docstring says REST is here to prevent -- and it would
    be silent, because the instrument's own `compare()` skips a rung REST has
    no book for, so nothing downstream would ever see the case.
    """
    part = None
    for src in prefer:
        side = row.get(src)
        if not isinstance(side, dict):
            continue
        bid, ask = _f(side.get("bid")), _f(side.get("ask"))
        if bid is None and ask is None:
            continue
        t = {"src": src, "bid": bid, "ask": ask,
             "bid_size": _f(side.get("bsz")) or 0.0, "ask_size": _f(side.get("asz")) or 0.0,
             "tt": side.get("tt"), "both": bid is not None and ask is not None}
        if t["both"]:
            return t
        part = part or t
    return part


def _why_not(v, floor_usd: float) -> str:
    """Why the executor would pass on a pair it can see. Empty string means it
    would ticket it, so a blank cell on the page is a real statement.

    The executor's gate is exactly two tests -- ``x.dollars >= floor_usd and
    is_spread_pair(x)`` (cfb/run_ladder_executor.py) -- and the mid ladder is
    not one of them: `is_mid` is the SORT KEY that decides which candidate goes
    first in a cycle, so a pair off the mid ladder is ticketed, just behind any
    mid one. core/api.py's ARB tab draws the same line (`candidate` is the
    floor and the spread test; `mid_ladder` rides beside it as a flag).

    Naming it here as a reason to pass would print "the executor would skip
    this" over a pair it is about to send, and it would do so on exactly one
    sport: MID_LADDER is (3.5, 20.5) and a WNBA spread ladder runs about +/-1.5
    to +/-9.5, so most of tonight's rungs are outside a band the money was
    measured on in college football.
    """
    why = []
    if not is_spread_pair(v):
        why.append("winner leg — never ticketed")
    if v.dollars < floor_usd:
        why.append(f"under the ${floor_usd:.0f} floor")
    return " · ".join(why)


def ladder(sample: dict, game: str = "", *, fee_rate: float = scan.DEFAULT_FEE_RATE,
           floor_usd: float = DEFAULT_FLOOR_USD, now: float | None = None,
           gross_count: bool = False) -> dict:
    """One sample of the tape as a table: rungs, bounds, violations.

    `lo` is the highest bid among harder rungs and `hi` the lowest ask among
    easier rungs, so a rung is consistent when `ask >= lo` and `bid <= hi`.
    Both are computed over the two-sided rungs ONLY -- the same population the
    scanner is handed -- so a bound and a pair can never disagree about which
    rungs exist.

    The dollar figures are the scanner's own (edge x the smaller displayed
    side) and they are at QUOTED size: nothing here has been filled.

    `now` is the instant book ages are measured from; it defaults to the wall
    clock, because `transactTime` is absolute and the tape's own `t` carries
    no date to anchor it to.

    `gross_count` adds a second, fee-free scan to count the pairs that cross
    before fees and not after. `core.ladder.pnl` calls this once per sample
    over a whole night's tape, so the extra pass is off by default and
    `latest()` turns it on for the ONE sample a page actually draws.
    """
    now = time.time() if now is None else now
    rows = sample.get("rows") or []
    seen: dict[float, dict] = {}
    for row in rows:
        line = _f(row.get("line"))
        touch = _touch(row)
        if line is None or touch is None:
            continue
        ws = row.get("ws") if isinstance(row.get("ws"), dict) else {}
        rest = row.get("rest") if isinstance(row.get("rest"), dict) else {}
        seen[line] = {
            **touch, "line": line, "winner": line == 0.0,
            # What the executor would price this rung off: REST, quoted both
            # sides. Everything else is on screen and out of the scan.
            "scanned": bool(touch["both"] and touch["src"] == "rest"),
            # The book's own last-update stamp, not the sweep's: how long this
            # rung has sat un-requoted (core.ladder.live.book_age_s).
            "age_s": book_age_s(rest.get("tt") or touch.get("tt"), now),
            "ws_age_s": _f(ws.get("recv_age_s")),
            "touch_equal": row.get("touch_equal"), "tt_equal": row.get("tt_equal"),
            "rest_behind_s": _f(row.get("rest_behind_s")),
        }

    # Only two-sided REST rungs reach the scanner: `core.ladder.live.sample`
    # drops the one-sided ones and the executor never reads the stream, so this
    # is the executor's own input, not a superset. A rung quoted on one side,
    # or only by the stream, stays on screen and out of the scan.
    rungs = {k: (r["bid"], r["ask"], r["bid_size"], r["ask_size"])
             for k, r in seen.items() if r["scanned"]}
    lines = sorted(rungs)

    def _scan(rate: float, cap: float):
        return scan.scan_ladder(game, rungs, fee_rate=rate, max_edge=cap, max_size=1e12)

    every = _scan(fee_rate, 1.0)                                   # every fee-netted cross
    live = [v for v in every if v.edge <= scan.MAX_PLAUSIBLE_EDGE]  # what the executor sees
    live.sort(key=lambda v: -v.dollars)
    fee_eaten = len(_scan(0.0, 1.0)) - len(every) if gross_count else None
    lit_ask = {v.high_line for v in live}     # we would buy this rung's ask
    lit_bid = {v.low_line for v in live}      # we would sell this rung's bid

    out = []
    for line in sorted(seen):
        r = dict(seen[line])
        harder = [rungs[x][0] for x in lines if x < line]           # their bids
        easier = [rungs[x][1] for x in lines if x > line]           # their asks
        lo = max(harder) if harder else None
        hi = min(easier) if easier else None
        r.update({
            "lo": lo, "hi": hi,
            "ask_below_lo": bool(r["scanned"] and lo is not None and r["ask"] < lo),
            "bid_above_hi": bool(r["scanned"] and hi is not None and r["bid"] > hi),
            "lit_ask": line in lit_ask, "lit_bid": line in lit_bid,
        })
        out.append(r)

    return {
        "t": sample.get("t"),
        "took_s": _f(sample.get("took_s")),
        "rungs": out,
        "violations": [{
            "high_line": v.high_line, "low_line": v.low_line,
            "buy_price": v.buy_price, "sell_price": v.sell_price,
            "edge_c": round(v.edge * 100, 2), "size": v.size, "dollars": round(v.dollars, 2),
            "spread_pair": is_spread_pair(v), "mid": is_mid(v),
            "why_not": _why_not(v, floor_usd),
        } for v in live],
        #: Pairs the executor would not act on, counted rather than hidden.
        #: `fee_eaten` is None when it was not asked for, which is not zero.
        "above_cap": len(every) - len(live),
        "fee_eaten": fee_eaten,
        "ticketable": sum(1 for v in live if not _why_not(v, floor_usd)),
        "floor_usd": floor_usd,
        "viol_rest": sample.get("viol_rest"), "viol_ws": sample.get("viol_ws"),
        "viol_common": sample.get("viol_common"),
        "ws_trades": sample.get("ws_trades"), "ws_msgs": sample.get("ws_msgs"),
        "ws_reconnects": sample.get("ws_reconnects"),
    }


def _trend(row: dict) -> dict:
    """One sample reduced to the numbers worth a row in the history strip."""
    return {"t": row.get("t"), "viol_rest": row.get("viol_rest"), "viol_ws": row.get("viol_ws"),
            "viol_common": row.get("viol_common"), "ws_trades": row.get("ws_trades"),
            "rungs": len(row.get("rows") or [])}


def latest(out_dir: str, game: str | None = None, *, history: int = 40,
           now: float | None = None) -> dict | None:
    """The newest sample for `game` (or the most recently written tape), with
    the last `history` samples reduced to a trend.

    `tape_age_s` is how long ago the file was last written. A sample's own `t`
    cannot answer "is this instrument still alive" -- a dead writer's last
    line keeps its timestamp forever -- so the file's mtime is carried beside
    it and the page warns on it.
    """
    now = time.time() if now is None else now
    files = tape_files(out_dir)
    if game:
        files = [p for p in files if same_game(game_of(p), game)]
    if not files:
        return None
    path = files[-1]
    rows = samples(path, max(1, history))
    if not rows:
        return None
    name = game_of(path)
    try:
        age = round(now - os.path.getmtime(path), 1)
    except OSError:
        age = None
    trend = [_trend(r) for r in rows]
    seen = [t["ws_trades"] for t in trend if isinstance(t["ws_trades"], (int, float))]
    return {"game": name, "tape_age_s": age, "history": trend,
            # Trades printed since the previous sample: the cumulative counter
            # alone cannot say whether the tape is still moving.
            "trades_delta": (seen[-1] - seen[-2]) if len(seen) >= 2 else None,
            **ladder(rows[-1], name, now=now, gross_count=True)}


def games(out_dir: str) -> list[str]:
    """Every game with a freshness tape, newest written last."""
    return [game_of(p) for p in tape_files(out_dir)]
