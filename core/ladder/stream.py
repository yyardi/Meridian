"""Record a whole slate off the venue's stream, because REST cannot hold one.

`cfb/run_live_ladder.py` fetches every rung of ONE game with its own
`get_book`. That is what made the ladder result measurable -- the two legs of
a violation coexisted -- and it is also why it does not scale: the venue
allows 20 requests a second per IP, the live recorder already holds 12 of
them, and a 40-rung game on a 20-second cadence is two requests a second. Four
games starve the recorder. Saturday is **49 CFB games / 1,856 spread markets**,
Sunday 13 NFL games / 533, and MLB adds ~20 games a day.

The markets WebSocket costs no request budget at all. One subscription takes
at most **100 market slugs** (verified 2026-09-18), so a slate is several
subscriptions; this module splits them, opens as few sockets as that needs,
and writes what arrives to disk.

What it records, and why in two files per game
----------------------------------------------
`<out>/slate_books_<game>.jsonl`   one line per MARKET_DATA update: the touch,
                                   the venue's `transactTime`, the state.
`<out>/slate_trades_<game>.jsonl`  one line per TRADE print, with both intents.

Per game, not per slate: 49 games interleaved into one file is a file nobody
can read a single game's ladder out of without holding the whole slate in
memory, and `core.ladder.stream_scan` reconstructs a ladder ONE GAME AT A
TIME. 49 games is 98 files, which is the point.

Rows are written as they arrive, including one-sided and empty books. An
absent side is a fact about the venue and is recorded as null rather than
dropped -- a file that contains only two-sided books cannot answer "was there
a bid?", and a statistic computed over what arrived is blind to what did not.

What this does NOT do
---------------------
No rotation, no run length, no schedule: the caller decides how long to run
and the manager decides when. No REST call, no book fetch, no venue write --
the only socket opened is the PUBLIC markets stream, and the counters below
are the only thing this module reports upward.

PLACES NOTHING. The private stream is a different path and is never opened;
a test pins the absence of any such path in this file.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import threading
import time

from core.ladder.live import game_and_line
from core.polymarket.ws_min import ConnectionClosed, WSClient

WS_URL = "wss://api.polymarket.us/v1/ws/markets"
WS_PATH = "/v1/ws/markets"

#: The venue's cap on ONE subscription, verified 2026-09-18. More slugs than
#: this is not an error you see -- it is a subscription that quietly carries
#: fewer markets than you asked for, which reads as a quiet slate.
MAX_SLUGS_PER_SUBSCRIPTION = 100

#: How many slugs one socket carries. There is NO measured per-connection cap
#: -- only the 100-slug subscription cap is verified -- so this is a blast
#: radius choice, not a venue fact: at 400, a CFB slate is five sockets and a
#: socket that dies takes a fifth of the slate down for one backoff instead of
#: all of it. Raising it to 2,000 would be one socket and is untested.
DEFAULT_SLUGS_PER_CONNECTION = 400

#: Reconnect backoff doubles from 1s and stops here. The same cap
#: `cfb/run_ws_freshness.py` has run with.
MAX_BACKOFF_S = 30.0

#: Where a message whose slug does not parse as a ladder rung is written.
#: Kept rather than dropped: every slug here was chosen by the resolver, so a
#: row landing in this file means the two parses disagree and that is a thing
#: to find, not to silently discard.
UNMAPPED_GAME = "unmapped"


def subscribe_msgs(request_id: str, sub_type: str, slugs: list[str],
                   debounced: bool = False) -> list[dict]:
    """Both spellings the docs show (camelCase on the markets page, snake_case
    with numeric types on the overview), in the order to try them.

    Identical to `cfb/run_ws_freshness.py`'s handshake, which is the one that
    has run live; a test pins the two against each other rather than trusting
    that they were copied correctly. `debounced` asks the venue to batch
    updates on high-frequency markets, which is worth having on a slate and
    not on a single-game freshness read.
    """
    num = {"SUBSCRIPTION_TYPE_MARKET_DATA": 1, "SUBSCRIPTION_TYPE_MARKET_DATA_LITE": 2,
           "SUBSCRIPTION_TYPE_TRADE": 3}[sub_type]
    camel = {"requestId": request_id, "subscriptionType": sub_type, "marketSlugs": slugs}
    snake = {"request_id": request_id, "subscription_type": num, "market_slugs": slugs}
    if debounced:
        camel["responsesDebounced"] = True
        snake["responses_debounced"] = True
    return [{"subscribe": camel}, {"subscribe": snake}]


def batch_slugs(slugs: list[str], size: int = MAX_SLUGS_PER_SUBSCRIPTION) -> list[list[str]]:
    """Split into subscription-sized chunks, order preserved, none over `size`.

    Plain chunking, not balancing: 101 slugs become 100 + 1 rather than 51 +
    50. Balance buys nothing here (a subscription's cost is its slug count,
    not its fullness) and a rule anyone can check by eye is worth more on a
    slate night than a rule that is one line cleverer.
    """
    if size < 1:
        raise ValueError(f"subscription size must be >= 1, got {size}")
    return [slugs[i:i + size] for i in range(0, len(slugs), size)]


def plan_connections(slugs: list[str], *, per_subscription: int = MAX_SLUGS_PER_SUBSCRIPTION,
                     per_connection: int = DEFAULT_SLUGS_PER_CONNECTION) -> list[list[list[str]]]:
    """`slugs` -> one list of subscription batches per connection to open.

    A connection is a whole number of batches, so no subscription is ever
    split across two sockets: resubscribing after a reconnect then means
    re-sending exactly the batches that socket owned.
    """
    batches = batch_slugs(slugs, per_subscription)
    per_conn = max(1, per_connection // per_subscription)
    return [batches[i:i + per_conn] for i in range(0, len(batches), per_conn)]


def _num(x) -> float | None:
    """A venue number, whichever of its two shapes arrived.

    A book level carries `{"px": {"value": "0.41"}, "qty": "100"}` -- price
    nested, quantity bare -- while a trade carries both nested. Both are
    observed in the stream `cfb/run_ws_freshness.py` has been reading, so the
    reader accepts either rather than encoding which field is which.
    """
    if isinstance(x, dict):
        x = x.get("value")
    if x is None or isinstance(x, bool):
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _level(levels, index: int = 0) -> tuple[float | None, float | None]:
    """(price, size) at one side's touch, or (None, None) if that side is empty."""
    if not isinstance(levels, list) or len(levels) <= index:
        return None, None
    lv = levels[index]
    if not isinstance(lv, dict):
        return None, None
    return _num(lv.get("px")), _num(lv.get("qty"))


def _iso(now: float | None = None) -> str:
    """Arrival stamp, milliseconds, UTC and explicit about it."""
    when = dt.datetime.fromtimestamp(now, dt.timezone.utc) if now else dt.datetime.now(dt.timezone.utc)
    return when.isoformat(timespec="milliseconds")


def book_row(md: dict, recv: str) -> dict | None:
    """One MARKET_DATA update as a line of `slate_books_<game>.jsonl`.

    Returns None only when the message carries no slug at all -- an empty or
    one-sided book still produces a row with nulls, because "no bid" and "we
    were not looking" must not be the same line in the file.
    """
    slug = md.get("marketSlug") or md.get("market_slug")
    if not slug:
        return None
    parsed = game_and_line(slug)
    bid, bid_size = _level(md.get("bids"))
    ask, ask_size = _level(md.get("offers"))
    return {"recv": recv, "slug": slug, "line": parsed[1] if parsed else None,
            "bid": bid, "ask": ask, "bid_size": bid_size, "ask_size": ask_size,
            "tt": md.get("transactTime") or md.get("transact_time"),
            "state": md.get("state") or md.get("marketState") or md.get("market_state")}


def trade_row(tr: dict, recv: str) -> dict | None:
    """One TRADE print as a line of `slate_trades_<game>.jsonl`.

    Both intents are kept whole. They are the only record of who crossed --
    which side was resting and which side took it -- and an episode that ends
    in a print on the stale leg is the closest thing to fill evidence that
    exists short of an order.
    """
    slug = tr.get("marketSlug") or tr.get("market_slug")
    if not slug:
        return None
    parsed = game_and_line(slug)
    taker = tr.get("taker") or {}
    maker = tr.get("maker") or {}
    return {"recv": recv, "slug": slug, "line": parsed[1] if parsed else None,
            "price": _num(tr.get("price")), "quantity": _num(tr.get("quantity")),
            "tradeTime": tr.get("tradeTime") or tr.get("trade_time"),
            "taker_intent": taker.get("intent") if isinstance(taker, dict) else None,
            "maker_intent": maker.get("intent") if isinstance(maker, dict) else None}


class SlateSink:
    """Two append-only files per game prefix, opened on first write.

    Line-buffered on purpose: `core.ladder.stream_scan` and any status page
    read these files WHILE the slate is running, and a 4 kB block buffer
    would make a live game look like a dead one for minutes at a time.

    Thread-safe because one sink is shared by every connection thread, and
    two sockets can carry rungs of the same game (a game's ladder is split
    across batches whenever it straddles a boundary).
    """

    def __init__(self, out_dir: str) -> None:
        self.out_dir = out_dir
        os.makedirs(out_dir, exist_ok=True)
        self._files: dict[str, object] = {}
        self._lock = threading.Lock()
        self.books_by_game: dict[str, int] = {}
        self.trades_by_game: dict[str, int] = {}

    def path_for(self, kind: str, game: str) -> str:
        return os.path.join(self.out_dir, f"slate_{kind}_{game}.jsonl")

    def _write(self, kind: str, game: str, row: dict, tally: dict[str, int]) -> None:
        line = json.dumps(row, separators=(",", ":"))
        with self._lock:
            key = f"{kind}/{game}"
            f = self._files.get(key)
            if f is None:
                # The handle is DELIBERATELY long-lived (hence the SIM115
                # waiver): a context manager per line would reopen 98 files
                # on every update of a 49-game slate.
                f = open(self.path_for(kind, game), "a", encoding="utf-8", buffering=1)  # noqa: SIM115
                self._files[key] = f
            f.write(line + "\n")
            tally[game] = tally.get(game, 0) + 1

    def book(self, game: str, row: dict) -> None:
        self._write("books", game, row, self.books_by_game)

    def trade(self, game: str, row: dict) -> None:
        self._write("trades", game, row, self.trades_by_game)

    def games(self) -> list[str]:
        with self._lock:
            return sorted(set(self.books_by_game) | set(self.trades_by_game))

    def close(self) -> None:
        with self._lock:
            for f in self._files.values():
                try:
                    f.close()
                except OSError:                       # noqa: PERF203
                    pass
            self._files.clear()


class StreamConnection:
    """One socket, its batches, its own thread, its own counters.

    The reconnect loop is `cfb/run_ws_freshness.py`'s, with two differences a
    slate needs:

    * **resubscribe is every batch this socket owns**, not one. A socket that
      comes back with one of its four subscriptions restored is a socket
      whose counters keep rising while three quarters of its games are dark.
    * **a torn message costs no reconnect.** A frame that does not parse as
      JSON is counted and skipped; dropping the socket for it would turn one
      bad frame into a backoff during which nothing on it is recorded.
    """

    def __init__(self, name: str, batches: list[list[str]], sink: SlateSink, *,
                 open_socket=None, debounced: bool = False,
                 stop: threading.Event | None = None,
                 max_backoff: float = MAX_BACKOFF_S, sleep=time.sleep) -> None:
        self.name, self.batches, self.sink = name, batches, sink
        self.slugs = [s for b in batches for s in b]
        self.debounced, self.max_backoff, self.sleep = debounced, max_backoff, sleep
        self.stop = stop or threading.Event()
        self._open_socket = open_socket or self._default_socket
        self._lock = threading.Lock()
        self._ws = None
        self._spelling = 0            # index into subscribe_msgs; 0 until probed
        self.msgs = self.books = self.trades = 0
        self.heartbeats = self.errors = self.torn = self.unmapped = 0
        self.reconnects = self.subscribes = 0
        self.connected = False
        self.last_msg_at: float | None = None
        self.last_heartbeat_at: float | None = None
        self.last_error = ""

    # -- socket -------------------------------------------------------------
    def _default_socket(self):
        """The real one. Imported here so the module can be exercised, and its
        handler tested, without credentials in the environment."""
        from core.polymarket.client import USCredentials, us_auth_headers
        ws = WSClient(WS_URL, us_auth_headers(USCredentials.from_env(), "GET", WS_PATH))
        ws.connect()
        return ws

    def run(self) -> None:
        """Sessions until `stop` is set, with doubling backoff between them."""
        backoff = 1.0
        while not self.stop.is_set():
            try:
                self._session()
                backoff = 1.0
            except (ConnectionClosed, OSError, ValueError) as e:      # noqa: PERF203
                with self._lock:
                    self.last_error = f"{type(e).__name__}: {str(e)[:100]}"
                    self.reconnects += 1
                    self.connected = False
                if self.stop.is_set():
                    return
                self.sleep(backoff)
                backoff = min(backoff * 2, self.max_backoff)

    def request_stop(self) -> None:
        """Set the flag and close the socket under the reader, so a thread
        blocked in `recv` for the next update returns now rather than at the
        socket timeout."""
        self.stop.set()
        with self._lock:
            ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except OSError:
                pass

    def _session(self) -> None:
        ws = self._open_socket()
        with self._lock:
            self._ws, self.connected = ws, True
        try:
            self._subscribe(ws)
            while not self.stop.is_set():
                try:
                    msg = ws.recv_json()
                except json.JSONDecodeError as e:
                    with self._lock:
                        self.torn += 1
                        self.last_error = f"torn: {str(e)[:60]}"
                    continue
                self.handle(msg)
        finally:
            with self._lock:
                self._ws, self.connected = None, False
            try:
                ws.close()
            except OSError:
                pass

    def _subscribe(self, ws) -> None:
        """Subscribe every batch for both MARKET_DATA and TRADE.

        The spelling is probed ONCE, on the first batch, exactly as the
        freshness runner does it: send, read one reply, and fall through to
        the other spelling if that reply is an error. Everything after it is
        sent without waiting, because once data is flowing a "reply" may be
        an update for a market rather than an ack -- reading one and calling
        it an ack would accept a subscription that failed. Errors for the
        unread ones arrive in the main loop and land in `errors`/`last_error`,
        where the status line shows them.
        """
        for i, batch in enumerate(self.batches):
            for kind, sub in (("md", "SUBSCRIPTION_TYPE_MARKET_DATA"),
                              ("tr", "SUBSCRIPTION_TYPE_TRADE")):
                rid = f"{self.name}-{kind}{i}"
                attempts = subscribe_msgs(rid, sub, batch, self.debounced)
                if i == 0 and kind == "md":
                    self._probe(ws, attempts)
                    continue
                ws.send_json(attempts[self._spelling])
                with self._lock:
                    self.subscribes += 1

    def _probe(self, ws, attempts: list[dict]) -> None:
        for idx, attempt in enumerate(attempts):
            ws.send_json(attempt)
            with self._lock:
                self.subscribes += 1
            reply = ws.recv_json()
            self.handle(reply)
            if not (isinstance(reply, dict) and "error" in reply):
                self._spelling = idx
                return
        self._spelling = 0

    # -- messages -----------------------------------------------------------
    def handle(self, msg) -> None:
        """One inbound message. Never raises on shape: a message that is not a
        dict, or is a dict this build has never seen, is counted and dropped
        rather than taking the socket down with it."""
        now = time.time()
        with self._lock:
            self.msgs += 1
            self.last_msg_at = now
        if not isinstance(msg, dict):
            with self._lock:
                self.torn += 1
            return
        if "heartbeat" in msg:
            with self._lock:
                self.heartbeats += 1
                self.last_heartbeat_at = now
            return
        if "error" in msg:
            with self._lock:
                self.errors += 1
                self.last_error = json.dumps(msg.get("error"), default=str)[:120]
            return
        md = msg.get("marketData") or msg.get("market_data")
        if isinstance(md, dict):
            self._record(md, book_row, self.sink.book, "books")
            return
        tr = msg.get("trade")
        if isinstance(tr, dict):
            self._record(tr, trade_row, self.sink.trade, "trades")

    def _record(self, payload: dict, build, write, counter: str) -> None:
        recv = _iso()
        row = build(payload, recv)
        if row is None:
            with self._lock:
                self.torn += 1
            return
        parsed = game_and_line(row["slug"])
        game = parsed[0] if parsed else UNMAPPED_GAME
        write(game, row)
        with self._lock:
            setattr(self, counter, getattr(self, counter) + 1)
            if parsed is None:
                self.unmapped += 1

    # -- reporting ----------------------------------------------------------
    def counters(self, now: float | None = None) -> dict:
        """What the caller prints. `last_msg_age_s` is the liveness read: a
        connection whose message count is high and whose last message is two
        minutes old is not a healthy connection, and the total alone says it
        is."""
        now = now or time.time()
        with self._lock:
            return {
                "name": self.name, "slugs": len(self.slugs),
                "subscriptions": 2 * len(self.batches), "subscribes_sent": self.subscribes,
                "connected": self.connected, "messages": self.msgs, "books": self.books,
                "trades": self.trades, "heartbeats": self.heartbeats, "errors": self.errors,
                "torn": self.torn, "unmapped": self.unmapped, "reconnects": self.reconnects,
                "last_msg_age_s": None if self.last_msg_at is None else round(now - self.last_msg_at, 1),
                "last_heartbeat_age_s": (None if self.last_heartbeat_at is None
                                         else round(now - self.last_heartbeat_at, 1)),
                "last_error": self.last_error,
            }


class SlateRecorder:
    """Every connection a slate needs, their threads, and one sink.

    `start()` is non-blocking: the caller runs its own status loop and calls
    `stop()` when its clock says to. Nothing here decides how long to run.
    """

    def __init__(self, slugs: list[str], out_dir: str, *,
                 per_subscription: int = MAX_SLUGS_PER_SUBSCRIPTION,
                 per_connection: int = DEFAULT_SLUGS_PER_CONNECTION,
                 open_socket=None, debounced: bool = False,
                 max_backoff: float = MAX_BACKOFF_S) -> None:
        self.slugs = list(dict.fromkeys(slugs))       # a slug subscribed twice is two copies of every update
        self.sink = SlateSink(out_dir)
        self.stop_event = threading.Event()
        plan = plan_connections(self.slugs, per_subscription=per_subscription,
                                per_connection=per_connection)
        self.connections = [
            StreamConnection(f"c{i}", batches, self.sink, open_socket=open_socket,
                             debounced=debounced, stop=self.stop_event, max_backoff=max_backoff)
            for i, batches in enumerate(plan)]
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        for conn in self.connections:
            t = threading.Thread(target=conn.run, name=f"stream-{conn.name}", daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self, timeout: float = 5.0) -> None:
        """Stop reading, join what joins, and close the files. Threads that do
        not come back are daemons and the files are already flushed line by
        line, so a socket wedged in `recv` cannot cost the tape."""
        self.stop_event.set()
        for conn in self.connections:
            conn.request_stop()
        for t in self._threads:
            t.join(timeout=timeout)
        self.sink.close()

    def counters(self, now: float | None = None) -> list[dict]:
        now = now or time.time()
        return [c.counters(now) for c in self.connections]

    def totals(self, now: float | None = None) -> dict:
        """The slate in one row. `stalest_s` is the max over connections
        because a slate is only as recorded as its worst socket."""
        rows = self.counters(now)
        ages = [r["last_msg_age_s"] for r in rows if r["last_msg_age_s"] is not None]
        return {
            "connections": len(rows), "slugs": len(self.slugs),
            "games": len(self.sink.games()),
            "connected": sum(1 for r in rows if r["connected"]),
            "messages": sum(r["messages"] for r in rows),
            "books": sum(r["books"] for r in rows),
            "trades": sum(r["trades"] for r in rows),
            "heartbeats": sum(r["heartbeats"] for r in rows),
            "errors": sum(r["errors"] for r in rows),
            "torn": sum(r["torn"] for r in rows),
            "reconnects": sum(r["reconnects"] for r in rows),
            "stalest_s": max(ages) if ages else None,
            "silent_connections": sum(1 for r in rows if r["last_msg_age_s"] is None),
        }

    def top_games(self, n: int = 5) -> list[tuple[str, int]]:
        """Games by trade count, busiest first -- the cheap read on where the
        slate's attention actually is."""
        counts = dict(self.sink.trades_by_game)
        return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:n]
