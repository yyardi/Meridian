"""The venue's own score, clock and period for each game on a stream slate, as a tape.

The stream (core/ladder/stream.py) records every touch and trade the venue
pushes, but the venue's websocket carries no game state: MARKET_DATA,
MARKET_DATA_LITE and TRADE are its only subscriptions. The event payload
(``GET /v1/events/slug/<event>``) does: ``eventState.score`` ("62-78"),
``period`` ("Q4"), ``elapsed`` ("03:05"), ``live``/``ended``, per-period scores,
and ``eventState.updatedAt`` -- the venue's own stamp of its last state change.

This polls that payload for every game on the slate and writes one line to
``<out>/slate_scores_<game>.jsonl`` each time the state CHANGES:

    {"recv": <our receipt, ms>, "prev_recv": <the poll before, which still saw the old state>,
     "game", "score", "period", "elapsed", "live", "ended",
     "state_updated_at": <eventState.updatedAt>, "polls": <polls of this game so far>}

so the change happened in (prev_recv, recv], and the venue stamped it at
``state_updated_at``. Beside the book tape that answers the speed question in
thin leagues: how long after the venue's own score changes does its price
move, and what size stood at the old price meanwhile.

Request budget: REST, unlike the stream, costs the shared gateway budget
(20 req/s, of which the live recorder takes about 12). The poller therefore
paces ALL games together at ``max_rps`` (default 1/s) and each game at no
more than one request per ``interval_s``; ten live games is one poll per game
every ten seconds. A game that has ended leaves the rotation.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import threading
import time

import httpx

GATEWAY = os.environ.get("POLYMARKET_GATEWAY_URL", "https://gateway.polymarket.us")
_FIELDS = ("score", "period", "elapsed", "live", "ended")


def _iso(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat(timespec="milliseconds")


def state_of(payload: dict) -> dict:
    """The comparable game state out of an events/slug payload (top level or ``event``)."""
    e = payload.get("event") if isinstance(payload.get("event"), dict) else payload
    st = e.get("eventState") or {}
    out = {k: st.get(k, e.get(k)) for k in _FIELDS}
    out["state_updated_at"] = st.get("updatedAt")
    out["period_scores"] = [
        [p.get("label"), [s.get("score") for s in (p.get("scores") or [])]]
        for p in (st.get("periodScores") or [])]
    return out


class ScorePoller:
    """Round-robin over the slate's events at a shared pace; append a line per state change."""

    def __init__(self, events: dict[str, str], out_dir: str, *, interval_s: float = 4.0,
                 pregame_interval_s: float = 30.0,
                 max_rps: float = 1.0, client: httpx.Client | None = None,
                 clock=time.time, sleep=time.sleep) -> None:
        self.events = dict(events)                 # game key -> event slug
        self.out_dir = out_dir
        self.interval_s = interval_s
        self.pregame_interval_s = pregame_interval_s
        self.min_gap_s = 1.0 / max_rps if max_rps > 0 else 0.0
        self._http = client or httpx.Client(timeout=8.0, headers={"User-Agent": "meridian-scores/1"})
        self._clock, self._sleep = clock, sleep
        self._last: dict[str, dict] = {}
        self._last_poll: dict[str, float] = {}
        self._polls: dict[str, int] = {}
        self._done: set[str] = set()
        self.changes = 0
        self.errors = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ one poll
    def poll(self, game: str) -> bool:
        """Fetch one game's state; write a line if it changed. True if a line was written."""
        slug = self.events[game]
        before = self._last_poll.get(game)
        try:
            r = self._http.get(f"{GATEWAY}/v1/events/slug/{slug}")
            r.raise_for_status()
            st = state_of(r.json())
        except (httpx.HTTPError, ValueError):
            self.errors += 1
            return False
        now = self._clock()
        self._last_poll[game] = now
        self._polls[game] = self._polls.get(game, 0) + 1
        if st.get("ended"):
            self._done.add(game)
        if self._last.get(game) == st:
            return False
        self._last[game] = st
        self.changes += 1
        line = {"recv": _iso(now), "prev_recv": None if before is None else _iso(before), "game": game,
                **{k: st[k] for k in _FIELDS}, "state_updated_at": st["state_updated_at"],
                "period_scores": st["period_scores"], "polls": self._polls[game]}
        with open(os.path.join(self.out_dir, f"slate_scores_{game}.jsonl"), "a") as fh:
            fh.write(json.dumps(line) + "\n")
        return True

    def due(self) -> str | None:
        """The game polled longest ago whose interval has passed: ``interval_s`` once the
        venue calls it live, ``pregame_interval_s`` before (the first poll is always due)."""
        now = self._clock()
        best, best_t = None, None
        for g in self.events:
            if g in self._done:
                continue
            t = self._last_poll.get(g)
            live = bool((self._last.get(g) or {}).get("live"))
            gap = self.interval_s if live else self.pregame_interval_s
            if t is not None and now - t < gap:
                continue
            t = t or 0.0
            if best_t is None or t < best_t:
                best, best_t = g, t
        return best

    # ------------------------------------------------------------------ the loop
    def run(self) -> None:
        while not self._stop.is_set() and len(self._done) < len(self.events):
            g = self.due()
            if g is None:
                self._sleep(0.25)
                continue
            self.poll(g)
            self._sleep(self.min_gap_s)

    def start(self) -> None:
        self._thread = threading.Thread(target=self.run, name="scores", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def status(self) -> str:
        live = sum(1 for g in self.events if g not in self._done)
        return f"scores  games {len(self.events)}  live-or-pending {live}  changes {self.changes}  errors {self.errors}"
