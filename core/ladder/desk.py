"""The ladder desk's files: tickets, the operator's records, the lock, the tails.

Moved out of `cfb/ladder_desk_app.py` so the dashboard's ARB tab can read and
write the same files: the api image COPYs core/ and not cfb/. The desk keeps
its routes and calls these; nothing about the file formats changed.

Every function takes the directory explicitly rather than reading a module
constant, because two processes use it with two different defaults. The
executor and the desk see the host directory mounted as `/out`; the api
container sees the same directory at `MERIDIAN_READS_DIR`
(`/opt/meridian/artifacts/reads`). Same files, two names -- a default baked
into the module would be right for one process and silently wrong for the
other. `default_out_dir` gives the scripts' answer and `api_out_dir` the
api's.

The files:

    ladder_intents_<prefix>.jsonl   one intent per line, written by the executor
    ladder_attempts.jsonl           one record per line, appended by the operator
                                    (or by the dashboard's send, with `via`)
    ladder_lock                     exists = LOCKED; the executor re-reads it every cycle
    live_ladder_aec-*.txt           executor stdout, one === line per cycle
    ws_freshness_aec-*.txt          stream-vs-REST instrument, same shape

No venue call. This module reads and writes local files only.
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os

ATTEMPTS_FILE = "ladder_attempts.jsonl"
LOCK_FILE = "ladder_lock"


def default_out_dir() -> str:
    """Where the executor and the desk keep their files: ``LADDER_OUT``, else
    ``/out`` when it is mounted, else the checkout's artifacts/reads."""
    return os.environ.get("LADDER_OUT") or ("/out" if os.path.isdir("/out") else "artifacts/reads")


def api_out_dir() -> str:
    """The same host directory as seen from the api container: it is the
    dashboard's reads directory, not a mount named /out."""
    return (os.environ.get("MERIDIAN_READS_DIR") or "").strip() or "/opt/meridian/artifacts/reads"


def read_jsonl(path: str) -> list[dict]:
    """Every parseable line; a torn or foreign line is skipped, not fatal."""
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    return rows


# --------------------------------------------------------------------- #
# The lock
# --------------------------------------------------------------------- #

def lock_path(out_dir: str) -> str:
    return os.path.join(out_dir, LOCK_FILE)


def armed(out_dir: str) -> bool:
    return not os.path.exists(lock_path(out_dir))


def lock(out_dir: str, who: str = "the desk") -> str:
    """Create the lock. Append-only so a second lock does not erase the first
    line's timestamp; the executor only tests existence."""
    with open(lock_path(out_dir), "a", encoding="utf-8") as f:
        f.write(dt.datetime.now(dt.timezone.utc).isoformat() + f" locked from {who}\n")
    return lock_path(out_dir)


def arm(out_dir: str) -> None:
    if os.path.exists(lock_path(out_dir)):
        os.remove(lock_path(out_dir))


# --------------------------------------------------------------------- #
# Tickets and the operator's records
# --------------------------------------------------------------------- #

def ticket_id(t: dict) -> str:
    return f"{t.get('game')}|{t.get('ts')}|{t['leg1']['market_line']}/{t['leg2']['market_line']}"


def stamp_instants(rows: list[dict], mtime: float | None) -> None:
    """Give each ticket in ONE file a real sortable instant, in place.

    A ticket's `ts` is HH:MM:SS with no date, and a game that kicks off at
    23:00 writes tickets on both sides of midnight. Sorting those strings puts
    yesterday's 00:17 above today's 16:19, which is how the desk spent a live
    Saturday showing Friday night's tickets.

    The anchor is the FILE's last-modified time, not the date in the game slug:
    a game listed under 2026-09-18 that kicks off at 23:58 writes every one of
    its tickets on the 19th, so the slug's date is wrong for all of them. The
    executor only appends, so walk backwards from the end and drop a day each
    time the clock jumps UP going back -- that is a midnight crossing.
    """
    if not rows:
        return
    if mtime is None:
        for r in rows:
            r["at"] = str(r.get("ts") or "")
        return
    end = dt.datetime.fromtimestamp(mtime, dt.timezone.utc)
    day = end.date()
    last = str(rows[-1].get("ts") or "")
    # A final ticket stamped later in the day than the file's own mtime can
    # only be yesterday's.
    if last and last > end.strftime("%H:%M:%S"):
        day -= dt.timedelta(days=1)
    prev = None
    for r in reversed(rows):
        ts = str(r.get("ts") or "")
        if prev is not None and ts > prev:
            day -= dt.timedelta(days=1)
        prev = ts
        r["at"] = f"{day.isoformat()}T{ts}"


def load_tickets(out_dir: str) -> list[dict]:
    """Every intent the executor wrote, newest first, with the operator's
    latest record for it merged in."""
    tickets = []
    for p in sorted(glob.glob(os.path.join(out_dir, "ladder_intents_*.jsonl"))):
        rows = []
        for t in read_jsonl(p):
            if "leg1" in t and "leg2" in t:
                t = dict(t)
                t["id"] = ticket_id(t)
                t["status"] = "open"
                rows.append(t)
        try:
            mtime = os.path.getmtime(p)
        except OSError:
            mtime = None
        stamp_instants(rows, mtime)
        tickets += rows
    attempts = {a["id"]: a for a in read_jsonl(os.path.join(out_dir, ATTEMPTS_FILE)) if "id" in a}
    for t in tickets:
        a = attempts.get(t["id"])
        if a:
            t["status"] = a.get("status", "open")
            t["record"] = a
    # Newest first, by the INSTANT. The old key was (game, ts) reversed, which
    # ordered the list alphabetically by opponent and only then by clock -- so
    # the top of the list was whichever game sorted last in the alphabet, and
    # the page's own `.reverse()` turned that into the oldest ticket of the
    # alphabetically-first game. Two places ordering one list, neither right.
    tickets.sort(key=lambda t: str(t.get("at") or t.get("ts") or ""), reverse=True)
    return tickets


def record_attempt(out_dir: str, tid: str, status: str, fills: dict | None = None, **extra) -> dict:
    """Append one record for a ticket and return it. ``status`` is one of
    open / placed / skipped / recorded; ``fills`` carries l1q,l1p,l1s,l2q,l2p,l2s
    for a recorded attempt (missing qty is 0: "did not fill" is a result).
    ``extra`` rides along -- the dashboard writes `via` ("send" from its SEND,
    "desk" from a hand record), the venue's order ids, and `l1_sent`/`l2_sent`
    (the quantity actually sent, which the tally's 80 % is measured against)
    so a tally can tell a hand order from a sent one."""
    row = {"id": tid, "status": status, "at": dt.datetime.now(dt.timezone.utc).isoformat()}
    if fills is not None:
        row.update({"l1q": fills.get("l1q") or 0.0, "l1p": fills.get("l1p"), "l1s": fills.get("l1s"),
                    "l2q": fills.get("l2q") or 0.0, "l2p": fills.get("l2p"), "l2s": fills.get("l2s")})
    row.update(extra)
    with open(os.path.join(out_dir, ATTEMPTS_FILE), "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    return row


def tally(tickets: list[dict]) -> dict:
    """The registered decision rule (docs/math/ladder-fill-test.md) over the
    first five placed attempts, in the order they were placed."""
    live = [t for t in tickets if t["status"] in ("placed", "recorded")]
    live.sort(key=lambda t: t.get("record", {}).get("at", ""))
    first5 = live[:5]
    rec = [t for t in first5 if t["status"] == "recorded"]
    # 80 % of what was SENT when the record says how much that was (a
    # dashboard send may go for less than the ticket); of the ticket otherwise.
    sent = lambda t, n: t["record"].get(f"l{n}_sent") or t[f"leg{n}"]["qty"]  # noqa: E731
    both = [t for t in rec if (t["record"].get("l1q") or 0) >= 0.8 * sent(t, 1)
            and (t["record"].get("l2q") or 0) >= 0.8 * sent(t, 2)]
    none = [t for t in rec if (t["record"].get("l1q") or 0) == 0]
    if len(both) >= 3:
        verdict = "Displayed size is real. Next build: the multi-game scheduler."
    elif len(none) >= 3:
        verdict = "Resting size is phantom. The lead closes on executability."
    elif len(rec) >= 5:
        verdict = "Mixed -- extend to ten attempts before reading it."
    else:
        verdict = "Not yet -- needs five recorded attempts."
    issued = sum(float(t.get("cost_usd") or 0) for t in tickets)
    return {"placed": len(first5), "recorded": len(rec), "both": len(both), "none": len(none),
            "verdict": verdict, "issued": issued, "open": sum(1 for t in tickets if t["status"] == "open")}


# --------------------------------------------------------------------- #
# The logs
# --------------------------------------------------------------------- #

def tail(path: str, n: int = 3) -> list[str]:
    """The last ``n`` cycle lines (those starting ===) of an executor or
    freshness log; the per-rung detail between them is not a status."""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = [ln.rstrip() for ln in f if ln.startswith("===")]
    return lines[-n:]


def log_files(out_dir: str, kind: str, last: int = 3) -> list[str]:
    """The newest ``last`` logs of one kind: 'executor' -> live_ladder_aec-*.txt,
    'freshness' -> ws_freshness_aec-*.txt. Sorted by name, which for these
    files is by date then game."""
    pattern = {"executor": "live_ladder_aec-*.txt", "freshness": "ws_freshness_aec-*.txt"}[kind]
    return sorted(glob.glob(os.path.join(out_dir, pattern)))[-last:]


def recent_games(out_dir: str, within_s: float = 6 * 3600, now: float | None = None) -> list[str]:
    """Game prefixes (``aec-...``) with an intents or executor file touched in
    the window: what the dashboard offers as "games on tonight". A file's
    mtime, not its contents -- an executor that is sampling but has issued
    nothing still touches its log every cycle."""
    now = dt.datetime.now(dt.timezone.utc).timestamp() if now is None else now
    seen: dict[str, float] = {}
    for pat, head, ext in (("ladder_intents_*.jsonl", "ladder_intents_", ".jsonl"),
                           ("live_ladder_aec-*.txt", "live_ladder_", ".txt")):
        for p in glob.glob(os.path.join(out_dir, pat)):
            try:
                age = now - os.path.getmtime(p)
            except OSError:
                continue
            if age > within_s:
                continue
            name = os.path.basename(p)[len(head):-len(ext)]
            seen[name] = min(age, seen.get(name, age))
    return sorted(seen, key=lambda g: (seen[g], g))
