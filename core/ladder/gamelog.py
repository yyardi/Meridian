"""Every opportunity one game's tape ever showed, and what we did about it.

The ARB tab's ticket list is a TO-DO list: a ticket that no longer clears is
hidden, because a desk at 23:40 must show what is actionable now. That is the
right rule for a screen you trade off and the wrong one for the end of the
night, when the question is not "what can I send" but "what did this game
offer, and how much of it went past us".

So this module reads the same freshness tape `core.ladder.pnl` aggregates and
returns the thing that aggregate throws away: the CHRONOLOGY. One row per
episode -- a pair that started clearing, kept clearing, and stopped -- with the
operator's own ticket ledger joined onto it. An episode with no ticket beside
it is the interesting row: the instrument saw it and nobody acted.

Why an episode rather than a sample
-----------------------------------
`pnl.tape_summary` counts SAMPLES with a violation. Two samples of the same
pair twenty seconds apart are one opportunity, not two, and a page that listed
them as two rows would report a busy night that was actually one stubborn
rung. `core.ladder.stream_scan` already draws this distinction on the books
stream; this is the same concept on the freshness tape, and the field names
match it (`start`/`end`/`duration_s`/`best_dollars`/`best_size`/`spread_pair`/
`mid`) so a figure from one can be read beside a figure from the other.

Two names deliberately do NOT match, because the quantities are not the same:

* `samples` here against `updates` there. There, one row is one venue update;
  here one row is one ~20 s sweep of the whole ladder. Calling both "updates"
  would invite summing them.
* `best_edge_c` here (cents) against `best_edge` there (a fraction). The tape
  path prices a pair through `tape.ladder`, which rounds the edge to cents on
  its way out; re-deriving a fraction from a rounded cent figure would print
  three digits of precision the input does not carry.

What the 20-second cycle costs
------------------------------
An episode of ONE sample lasted somewhere between an instant and one cycle --
the tape cannot say which -- and its `duration_s` is 0.0, which is a lower
bound and not a measurement. An episode spanning two samples may equally have
closed and reopened in the forty seconds between them. Both directions are
stated on the page rather than smoothed here: the tape is the only per-rung
record that exists for a finished game, and a log that quietly rounded its
resolution away would be read as minute-by-minute truth.

Dollars are edge x the smaller DISPLAYED side, at the executor's own uncapped
size (`tape.ladder` scans with `max_size=1e12`). Nothing here filled.

Reads files. No venue call, no database, no order path.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass

from core.ladder import desk, pnl, scan, tape

#: How far outside an episode's window a ticket may sit and still be ITS
#: ticket. The executor sweeps on its own clock, not the tape's, so a ticket
#: for a pair the tape saw at 23:41:00 is routinely stamped 23:41:07 -- and a
#: one-sample episode has a zero-width window, against which an exact-inclusion
#: test would match nothing at all. One tape cycle is the honest tolerance:
#: it is exactly the interval over which the tape cannot say whether the pair
#: was still there.
CYCLE_S = 20.0

_DAY_S = 86_400.0


# --------------------------------------------------------------------- #
# Dating the tape
# --------------------------------------------------------------------- #

def _seconds_of_day(stamp) -> float | None:
    """`"23:41:07"` -> seconds since midnight, or None if it is not a clock.

    The instrument writes a bare wall clock with no date, which is why this
    module dates a sample by walking deltas rather than by parsing one stamp.
    """
    parts = str(stamp or "").split(":")
    if len(parts) != 3:
        return None
    try:
        h, m, s = (float(p) for p in parts)
    except ValueError:
        return None
    return h * 3600.0 + m * 60.0 + s


def sample_epochs(rows: list[dict], anchor: float) -> list[float]:
    """One absolute instant per sample, newest = `anchor`, walking backwards.

    The tape's `t` is a wall clock with no date on it, so no single line can be
    turned into an instant on its own. What CAN be recovered is the interval
    between two lines, and the file's own mtime dates the newest one -- the
    instrument appends a line per cycle, so the last write is the last sample.

    Differences are taken modulo a day so a game that runs past midnight reads
    forward rather than as a 23-hour jump backwards. One tape is one game on
    one date, so midnight is the only wrap there is.

    An unreadable stamp contributes a zero step rather than dropping the
    sample: a torn clock must not silently shorten every episode after it.
    """
    secs = [_seconds_of_day(r.get("t")) for r in rows]
    out = [anchor] * len(rows)
    for i in range(len(rows) - 2, -1, -1):
        a, b = secs[i], secs[i + 1]
        step = 0.0 if (a is None or b is None) else (b - a) % _DAY_S
        out[i] = out[i + 1] - step
    return out


# --------------------------------------------------------------------- #
# Episodes
# --------------------------------------------------------------------- #

@dataclass(frozen=True)
class Episode:
    """One pair, from the sample its violation first cleared on to the last
    sample it survived.

    `best_*` is the single best instant inside the window: the most one
    perfectly-timed two-leg order could have taken at displayed size. It is
    the same quantity `core.ladder.stream_scan.Episode` carries and it is NOT
    a strategy P&L -- nothing on it has filled.

    `best_high_age_s` / `best_low_age_s` are how long each leg's book had sat
    un-requoted at that instant (the venue's own `transactTime`). They are
    None when the tape could not be dated; see `episodes_in_tape`.
    """

    game: str
    low_line: float
    high_line: float
    start: str
    end: str
    duration_s: float
    samples: int
    best_t: str
    best_edge_c: float
    best_dollars: float
    best_buy: float
    best_sell: float
    best_size: float
    best_high_age_s: float | None
    best_low_age_s: float | None
    spread_pair: bool
    mid: bool

    @property
    def pair(self) -> tuple[float, float]:
        return (self.low_line, self.high_line)


class _Open:
    """An episode still running, mutated as samples arrive."""

    __slots__ = ("best", "best_ages", "best_t", "end", "end_epoch", "samples",
                 "start", "start_epoch")

    def __init__(self, when: str, epoch: float, v: dict, ages: tuple) -> None:
        self.start = self.end = self.best_t = when
        self.start_epoch = self.end_epoch = epoch
        self.samples = 1
        self.best = v
        self.best_ages = ages

    def extend(self, when: str, epoch: float, v: dict, ages: tuple) -> None:
        self.end = when
        self.end_epoch = epoch
        self.samples += 1
        if v["dollars"] > self.best["dollars"]:
            self.best, self.best_t, self.best_ages = v, when, ages


def _close(game: str, key: tuple[float, float], op: _Open) -> Episode:
    v = op.best
    return Episode(
        game=game, low_line=key[0], high_line=key[1],
        start=op.start, end=op.end,
        duration_s=round(op.end_epoch - op.start_epoch, 1),
        samples=op.samples, best_t=op.best_t,
        best_edge_c=v["edge_c"], best_dollars=v["dollars"],
        best_buy=v["buy_price"], best_sell=v["sell_price"], best_size=v["size"],
        best_high_age_s=op.best_ages[0], best_low_age_s=op.best_ages[1],
        spread_pair=v["spread_pair"], mid=v["mid"])


def episodes_in_tape(path: str, *, game: str | None = None,
                     fee_rate: float = scan.DEFAULT_FEE_RATE,
                     max_samples: int = pnl.MAX_SAMPLES,
                     anchor: float | None = None,
                     ) -> tuple[list[Episode], dict]:
    """One game's tape as its chronological episode list.

    Returns ``(episodes, totals)``; `totals` names the population -- how many
    samples were read, over what span, at what fee rate, and whether the tape
    could be dated -- because an episode count with no denominator beside it is
    the figure that gets quoted back without its caveats.

    Winner-leg pairs (line 0) are dropped, the same population
    `pnl.tape_summary` counts and the only one the executor ever ticketed: an
    NFL tie settles the Winner contract at $0.50, so the pair's $1 guarantee is
    not a guarantee. They are COUNTED in `totals["winner_pairs"]` rather than
    silently dropped.

    `anchor` is the instant the newest sample is dated to; it defaults to the
    file's mtime. Durations are differences and survive a bad anchor, but book
    ages are measured FROM it -- so when there is no anchor they are reported
    as None rather than as an age against the wall clock, which for a finished
    game would read as hours.
    """
    game = game or tape.game_of(path)
    rows = tape.samples(path, max_samples)
    if not rows:
        return [], {"game": game, "key": pnl.game_key(game), "file": path,
                    "samples": 0, "episodes": 0, "winner_pairs": 0,
                    "first_t": None, "last_t": None, "span_s": 0.0,
                    "anchored": False, "fee_rate": fee_rate}
    if anchor is None:
        try:
            anchor = os.path.getmtime(path)
        except OSError:
            anchor = None
    epochs = sample_epochs(rows, 0.0 if anchor is None else anchor)

    open_eps: dict[tuple[float, float], _Open] = {}
    done: list[Episode] = []
    winner_pairs = with_violation = 0
    for row, epoch in zip(rows, epochs):
        when = str(row.get("t") or "")
        state = tape.ladder(row, game, fee_rate=fee_rate, now=epoch)
        # An age is only an age if the tape could be dated. Un-anchored, the
        # epochs are relative and `age_s` would be an offset from an arbitrary
        # zero -- a number that reads like seconds and is not.
        ages = {r["line"]: (r.get("age_s") if anchor is not None else None)
                for r in state["rungs"]}
        found: dict[tuple[float, float], dict] = {}
        for v in state["violations"]:
            if not v["spread_pair"]:
                winner_pairs += 1
                continue
            found[(v["low_line"], v["high_line"])] = v
        with_violation += 1 if found else 0
        for key, v in found.items():
            leg_ages = (ages.get(key[1]), ages.get(key[0]))
            if key in open_eps:
                open_eps[key].extend(when, epoch, v, leg_ages)
            else:
                open_eps[key] = _Open(when, epoch, v, leg_ages)
        for key in [k for k in open_eps if k not in found]:
            done.append(_close(game, key, open_eps.pop(key)))
    for key in list(open_eps):
        done.append(_close(game, key, open_eps.pop(key)))
    done.sort(key=lambda e: (e.start, e.low_line, e.high_line))

    totals = {
        "game": game, "key": pnl.game_key(game), "file": path,
        "samples": len(rows), "samples_with_a_pair": with_violation,
        "episodes": len(done), "winner_pairs": winner_pairs,
        "first_t": rows[0].get("t"), "last_t": rows[-1].get("t"),
        "span_s": round(epochs[-1] - epochs[0], 1),
        # Whether the book ages on every row mean anything. False is not an
        # error: it is "this tape has no date, so ages are withheld".
        "anchored": anchor is not None,
        "fee_rate": fee_rate,          # the caller's constant; the tape carries none (core/ladder/tape.py)
    }
    return done, totals


# --------------------------------------------------------------------- #
# What the operator did about it
# --------------------------------------------------------------------- #

def _offset_s(clock, start_clock) -> float | None:
    """Seconds from `start_clock` to `clock`, signed, nearest way round.

    Both are bare wall clocks, so "23:59:50 against 00:00:10" has to read as
    -20 s and not as +86,380. Taking the nearest of the two directions is
    correct for any gap under twelve hours, which every tape is.
    """
    a, b = _seconds_of_day(start_clock), _seconds_of_day(clock)
    if a is None or b is None:
        return None
    d = (b - a) % _DAY_S
    return d - _DAY_S if d > _DAY_S / 2 else d


def _ticket_row(t: dict) -> dict:
    """One ticket reduced to what a log row shows: when, what happened, and
    what it cost. The fill arithmetic is `pnl.attempt_pnl`'s, not a second
    copy -- a game log that disagreed with /pnl about a fill would be worse
    than no game log."""
    r = pnl.attempt_pnl(t)
    return {k: r[k] for k in ("ticket", "ts", "status", "edge_c", "ticket_qty",
                              "qty_filled", "cost", "net_if_settled", "legged")}


def match_tickets(episodes: list[Episode], tickets: list[dict], *,
                  grace_s: float = CYCLE_S) -> list[list[dict]]:
    """For each episode, the tickets written DURING it: one list per episode.

    Matched on game, on the exact pair of lines, and on the ticket's clock
    falling inside the window (widened by one cycle at each end, `CYCLE_S`).

    A ticket is given to AT MOST ONE episode -- the nearest window it fits.
    The same pair can break twice in a night, and letting both episodes claim
    the one ticket would report two acted-on chances where there was one, in
    exactly the column the page uses to say what went past us.
    """
    out: list[list[dict]] = [[] for _ in episodes]
    by_pair: dict[tuple[str, float, float], list[int]] = {}
    for i, e in enumerate(episodes):
        by_pair.setdefault((pnl.game_key(e.game), e.low_line, e.high_line), []).append(i)
    for t in tickets:
        leg1, leg2 = t.get("leg1") or {}, t.get("leg2") or {}
        try:
            key = (pnl.game_key(t.get("game")),
                   float(leg2.get("market_line")), float(leg1.get("market_line")))
        except (TypeError, ValueError):
            continue
        best_i, best_d = None, None
        for i in by_pair.get(key, []):
            off = _offset_s(t.get("ts"), episodes[i].start)
            if off is None:
                continue
            span = episodes[i].duration_s
            dist = 0.0 if -grace_s <= off <= span + grace_s else min(abs(off), abs(off - span))
            if dist > grace_s:
                continue
            if best_d is None or dist < best_d:
                best_i, best_d = i, dist
        if best_i is not None:
            out[best_i].append(_ticket_row(t))
    for rows in out:
        rows.sort(key=lambda r: str(r["ts"] or ""))
    return out


def _outcome(rows: list[dict]) -> str:
    """What became of an episode's tickets, in one word the page can colour.

    "" means no ticket was ever written for it, which is the row the log
    exists to show: an opportunity the instrument saw and nobody acted on.
    """
    if not rows:
        return ""
    status = {r["status"] for r in rows}
    if status & {"recorded", "placed"}:
        return "recorded" if "recorded" in status else "placed"
    return "skipped" if "skipped" in status else "open"


def episode_rows(episodes: list[Episode], tickets_per: list[list[dict]],
                 *, floor_usd: float = pnl.FLOOR_USD) -> list[dict]:
    """Episodes as plain dicts with their tickets joined on, chronological."""
    rows = []
    for e, tks in zip(episodes, tickets_per):
        rows.append({
            **asdict(e),
            "over_floor": e.best_dollars >= floor_usd,
            "tickets": tks,
            "ticketed": len(tks),
            "outcome": _outcome(tks),
            "qty_filled": sum(t["qty_filled"] for t in tks),
            "net_if_settled": sum(t["net_if_settled"] for t in tks),
        })
    return rows


# --------------------------------------------------------------------- #
# The log
# --------------------------------------------------------------------- #

def summarise(rows: list[dict], totals: dict, *,
              floor_usd: float = pnl.FLOOR_USD) -> dict:
    """The line above the table: how many chances, how big, how many taken.

    `sum_best_usd` is the total of the best instant of EACH episode. It is not
    a number anyone could have collected -- it assumes a perfectly-timed pair
    on every one of them at displayed size -- and it is the same construction
    `stream_scan.slate_summary` sums, so the two are readable side by side.
    """
    best = [r["best_dollars"] for r in rows]
    over = [r for r in rows if r["over_floor"]]
    biggest = max(rows, key=lambda r: r["best_dollars"], default=None)
    longest = max(rows, key=lambda r: r["duration_s"], default=None)
    return {
        **totals,
        "episodes": len(rows),
        "episodes_over_floor": len(over),
        "floor_usd": floor_usd,
        "sum_best_usd": round(sum(best), 2),
        "sum_best_over_floor_usd": round(sum(r["best_dollars"] for r in over), 2),
        "max_best_usd": round(max(best), 2) if best else 0.0,
        "biggest_pair": (biggest["high_line"], biggest["low_line"]) if biggest else None,
        "longest_s": longest["duration_s"] if longest else 0.0,
        "longest_pair": (longest["high_line"], longest["low_line"]) if longest else None,
        "ticketed": sum(1 for r in rows if r["ticketed"]),
        "placed": sum(1 for r in rows if r["outcome"] in ("placed", "recorded")),
        "skipped": sum(1 for r in rows if r["outcome"] == "skipped"),
        # The row the log exists for: seen, over the floor, never ticketed.
        "missed_over_floor": sum(1 for r in over if not r["ticketed"]),
        "qty_filled": sum(r["qty_filled"] for r in rows),
    }


def game_log(out_dir: str, game: str | None = None, *,
             tickets: list[dict] | None = None,
             floor_usd: float = pnl.FLOOR_USD, **kw) -> dict | None:
    """One game's whole night: every episode, with its tickets and a summary.

    `game` may carry the venue's `aec-` head or not. None means the most
    recently written tape, which is what an operator opening /log mid-slate
    wants. None is returned when no tape matches -- a game with no tape has no
    log, and inventing an empty one would let a typo'd game read as a quiet
    night.
    """
    files = tape.tape_files(out_dir)
    if game:
        files = [p for p in files if tape.same_game(tape.game_of(p), game)]
    if not files:
        return None
    path = files[-1]
    episodes, totals = episodes_in_tape(path, **kw)
    if tickets is None:
        tickets = desk.load_tickets(out_dir)
    rows = episode_rows(episodes, match_tickets(episodes, tickets), floor_usd=floor_usd)
    return {"game": totals["game"], "key": totals["key"], "file": path,
            "episodes": rows, "summary": summarise(rows, totals, floor_usd=floor_usd)}


def slate_log(out_dir: str, *, last: int = 12, floor_usd: float = pnl.FLOOR_USD,
              tickets: list[dict] | None = None, **kw) -> dict:
    """Every game with a tape: one summary each, plus the roll-up under them.

    The roll-up SUMS what is additive and COUNTS the games rather than
    averaging over them -- one game carrying the whole night is the shape the
    per-game rows are there to show, and a mean would hide exactly that.
    """
    # Same override `game_log` takes, for the same reason: a caller with the
    # tickets already in hand should not re-read the directory, and a test
    # must be able to say "this night, these tickets" without writing files.
    if tickets is None:
        tickets = desk.load_tickets(out_dir)
    games = []
    for path in tape.tape_files(out_dir, last=last):
        episodes, totals = episodes_in_tape(path, **kw)
        rows = episode_rows(episodes, match_tickets(episodes, tickets), floor_usd=floor_usd)
        games.append(summarise(rows, totals, floor_usd=floor_usd))
    games.sort(key=lambda g: g["key"])
    add = ("samples", "episodes", "episodes_over_floor", "ticketed", "placed",
           "skipped", "missed_over_floor", "qty_filled")
    return {
        "games": games,
        "total": {
            "games": len(games),
            **{k: sum(g[k] for g in games) for k in add},
            "sum_best_usd": round(sum(g["sum_best_usd"] for g in games), 2),
            "max_best_usd": round(max((g["max_best_usd"] for g in games), default=0.0), 2),
            "floor_usd": floor_usd,
        },
    }
