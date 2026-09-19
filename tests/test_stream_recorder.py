"""The slate recorder: batching, the per-game split, the handler, reconnect.

Everything here runs against a FAKE socket that hands the connection scripted
messages and records what was sent to it. That is the only way to test the
three things a slate recorder can get wrong and a live run cannot show you:

* a subscription over the venue's 100-slug cap, which is not an error you see
  -- it is a subscription quietly carrying fewer markets than you asked for;
* a reconnect that restores ONE of a socket's subscriptions, so the counters
  keep rising while three quarters of its games are dark;
* a torn frame that costs a reconnect, turning one bad message into a backoff
  during which nothing on that socket is recorded.

The expected counts below are hand-worked from the slug lists and the
scripts, not read off the code.
"""
from __future__ import annotations

import json
import pathlib
import sys
import threading

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core.ladder import live, stream  # noqa: E402
from core.polymarket.ws_min import ConnectionClosed  # noqa: E402

GAME_A = "cfb-mia-wake-2026-09-18"
GAME_B = "cfb-hou-ttu-2026-09-18"
WINNER_A = f"aec-{GAME_A}"
SPREAD_A = f"asc-{GAME_A}-pos-10pt5"
SPREAD_B = f"asc-{GAME_B}-neg-3pt5"

#: The two strings this repo's guards look for, never spelled out in a file
#: that is itself scanned for them. Assembled so the scanner below cannot
#: match its own source and report a false positive on this test.
FORBIDDEN = ("place_" + "order", "submit_" + "order", "create_" + "order",
             "/" + "orders", "MERIDIAN_ORDER_TOKEN", "PolymarketOrderClient")


def md_msg(slug, bid=0.41, ask=0.43, bsz=100, asz=200, tt="2026-09-18T23:00:00.1Z"):
    """A MARKET_DATA message in the shape the venue sends: price nested under
    `px.value`, quantity bare. Both shapes are what `ws_min` has read live."""
    return {"marketData": {"marketSlug": slug, "transactTime": tt, "state": "MARKET_STATE_OPEN",
                           "bids": [{"px": {"value": str(bid)}, "qty": str(bsz)}],
                           "offers": [{"px": {"value": str(ask)}, "qty": str(asz)}]}}


def trade_msg(slug, price=0.42, qty=50):
    """A TRADE print: price AND quantity nested, and both intents present."""
    return {"trade": {"marketSlug": slug, "price": {"value": str(price)},
                      "quantity": {"value": str(qty)}, "tradeTime": "2026-09-18T23:00:01.5Z",
                      "taker": {"intent": "TRADE_INTENT_BUY"},
                      "maker": {"intent": "TRADE_INTENT_SELL"}}}


ACK = {"subscribed": {"requestId": "c0-md0"}}


class FakeSocket:
    """Hands out a script, then raises. `sent` is every subscribe it saw."""

    def __init__(self, script):
        self.script = list(script)
        self.sent: list[dict] = []
        self.closed = False

    def send_json(self, obj):
        self.sent.append(obj)

    def recv_json(self):
        if not self.script:
            raise ConnectionClosed("scripted end of tape")
        msg = self.script.pop(0)
        if isinstance(msg, Exception):
            raise msg
        return msg

    def close(self):
        self.closed = True


def _conn(tmp_path, batches, script, **kw):
    sock = FakeSocket(script)
    sink = stream.SlateSink(str(tmp_path))
    conn = stream.StreamConnection("c0", batches, sink, open_socket=lambda: sock, **kw)
    return conn, sock, sink


def _lines(path):
    return [json.loads(x) for x in pathlib.Path(path).read_text(encoding="utf-8").splitlines() if x]


# --------------------------------------------------------------------------- #
# Batching at the venue's cap
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("n,sizes", [(1, [1]), (99, [99]), (100, [100]), (101, [100, 1]),
                                     (250, [100, 100, 50]), (1856, [100] * 18 + [56])])
def test_batching_never_exceeds_the_hundred_slug_subscription_cap(n, sizes):
    """1,856 is Saturday's CFB slate. 100 stays ONE subscription and 101 must
    become two -- the boundary is the whole point, because one slug over the
    cap is silently dropped by the venue rather than refused."""
    slugs = [f"asc-cfb-g{i}-h-2026-09-19-pos-3pt5" for i in range(n)]
    batches = stream.batch_slugs(slugs)
    assert [len(b) for b in batches] == sizes
    assert max(len(b) for b in batches) <= stream.MAX_SLUGS_PER_SUBSCRIPTION
    assert [s for b in batches for s in b] == slugs, "every slug, once, in order"


def test_batch_size_must_be_positive():
    with pytest.raises(ValueError):
        stream.batch_slugs(["a"], 0)


def test_a_saturday_slate_opens_five_sockets_and_loses_no_slug():
    """1,856 slugs / 100 = 19 subscriptions; at 400 slugs a socket that is
    four subscriptions each, so five connections (4,4,4,4,3)."""
    slugs = [f"asc-cfb-g{i}-h-2026-09-19-pos-3pt5" for i in range(1856)]
    plan = stream.plan_connections(slugs)
    assert [len(c) for c in plan] == [4, 4, 4, 4, 3]
    flat = [s for conn in plan for b in conn for s in b]
    assert flat == slugs and len(set(flat)) == 1856
    assert all(len(b) <= 100 for conn in plan for b in conn)


def test_a_connection_holds_whole_subscriptions_only():
    """No batch may straddle two sockets: a resubscribe re-sends exactly the
    batches that socket owned, and a split batch would leave a gap."""
    slugs = [f"s{i}" for i in range(250)]
    plan = stream.plan_connections(slugs, per_subscription=100, per_connection=150)
    assert [[len(b) for b in c] for c in plan] == [[100], [100], [50]]


# --------------------------------------------------------------------------- #
# The handshake
# --------------------------------------------------------------------------- #


def test_subscribe_messages_match_the_handshake_that_has_run_live():
    """`cfb/run_ws_freshness.py` is the version proven against the venue.
    Pinned against it rather than trusted to have been copied correctly."""
    import importlib
    fr = importlib.import_module("cfb.run_ws_freshness")
    for sub in ("SUBSCRIPTION_TYPE_MARKET_DATA", "SUBSCRIPTION_TYPE_TRADE"):
        assert stream.subscribe_msgs("r", sub, ["a", "b"]) == fr.subscribe_msgs("r", sub, ["a", "b"])
    assert stream.WS_URL == fr.WS_URL and stream.WS_PATH == fr.WS_PATH


def test_debouncing_is_off_unless_asked_for_and_reaches_both_spellings():
    plain = stream.subscribe_msgs("r", "SUBSCRIPTION_TYPE_MARKET_DATA", ["a"])
    assert all("responsesDebounced" not in m["subscribe"] for m in plain)
    on = stream.subscribe_msgs("r", "SUBSCRIPTION_TYPE_MARKET_DATA", ["a"], debounced=True)
    assert on[0]["subscribe"]["responsesDebounced"] is True
    assert on[1]["subscribe"]["responses_debounced"] is True


def test_every_batch_is_subscribed_for_both_market_data_and_trades(tmp_path):
    """Two batches: probe (1 send) + trades for batch 0 + both for batch 1 = 4.
    A socket subscribed for MARKET_DATA only records a book and no prints."""
    conn, sock, _ = _conn(tmp_path, [["a", "b"], ["c"]], [ACK])
    conn.stop.set()
    conn._session()
    assert len(sock.sent) == 4
    kinds = [m["subscribe"]["subscriptionType"] for m in sock.sent]
    assert kinds.count("SUBSCRIPTION_TYPE_MARKET_DATA") == 2
    assert kinds.count("SUBSCRIPTION_TYPE_TRADE") == 2
    assert [m["subscribe"]["marketSlugs"] for m in sock.sent] == [["a", "b"], ["a", "b"], ["c"], ["c"]]


def test_the_snake_case_spelling_is_used_when_camel_case_is_refused(tmp_path):
    """The venue's docs show two spellings. If the first is answered with an
    error the second must be tried AND adopted for every later batch."""
    err = {"error": {"code": 3, "message": "unknown field subscriptionType"}}
    conn, sock, _ = _conn(tmp_path, [["a"], ["b"]], [err, ACK])
    conn.stop.set()
    conn._session()
    assert "subscriptionType" in sock.sent[0]["subscribe"], "camelCase tried first"
    assert "subscription_type" in sock.sent[1]["subscribe"], "snake_case is the fallback"
    assert all("subscription_type" in m["subscribe"] for m in sock.sent[1:]), "and is kept"
    assert conn.errors == 1 and "unknown field" in conn.last_error


# --------------------------------------------------------------------------- #
# The handler and the per-game file split
# --------------------------------------------------------------------------- #


def test_market_data_trade_and_heartbeat_each_go_where_they_belong(tmp_path):
    conn, _, sink = _conn(tmp_path, [[WINNER_A]], [])
    conn.handle(md_msg(SPREAD_A))
    conn.handle(trade_msg(SPREAD_A))
    conn.handle({"heartbeat": {}})
    assert (conn.books, conn.trades, conn.heartbeats, conn.msgs) == (1, 1, 1, 3)
    book = _lines(sink.path_for("books", GAME_A))[0]
    assert book["slug"] == SPREAD_A and book["line"] == 10.5
    assert (book["bid"], book["ask"], book["bid_size"], book["ask_size"]) == (0.41, 0.43, 100.0, 200.0)
    assert book["tt"] == "2026-09-18T23:00:00.1Z" and book["state"] == "MARKET_STATE_OPEN"
    assert book["recv"].endswith("+00:00"), "arrival stamp is UTC and says so"
    trade = _lines(sink.path_for("trades", GAME_A))[0]
    assert trade["price"] == 0.42 and trade["quantity"] == 50.0 and trade["line"] == 10.5
    assert trade["taker_intent"] == "TRADE_INTENT_BUY" and trade["maker_intent"] == "TRADE_INTENT_SELL"
    assert not pathlib.Path(sink.path_for("books", GAME_B)).exists(), "no file for a silent game"


def test_two_games_are_two_pairs_of_files_not_one_stream(tmp_path):
    """49 games is 98 files. One file would be unreadable one game at a time,
    which is exactly how `stream_scan` reads them."""
    conn, _, sink = _conn(tmp_path, [[WINNER_A, SPREAD_B]], [])
    for msg in (md_msg(WINNER_A), md_msg(SPREAD_A), md_msg(SPREAD_B), trade_msg(SPREAD_B)):
        conn.handle(msg)
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == [f"slate_books_{GAME_B}.jsonl", f"slate_books_{GAME_A}.jsonl",
                     f"slate_trades_{GAME_B}.jsonl"]
    assert len(_lines(sink.path_for("books", GAME_A))) == 2, "winner and spread, one ladder"
    assert sink.books_by_game == {GAME_A: 2, GAME_B: 1}
    assert sink.trades_by_game == {GAME_B: 1}
    sink.close()


def test_a_one_sided_book_is_recorded_as_a_null_side_not_dropped(tmp_path):
    """"No bid" and "we were not looking" must not be the same line in the
    file; a tape holding only two-sided books cannot tell them apart."""
    conn, _, sink = _conn(tmp_path, [[SPREAD_A]], [])
    conn.handle({"marketData": {"marketSlug": SPREAD_A, "bids": [],
                                "offers": [{"px": {"value": "0.43"}, "qty": "200"}]}})
    row = _lines(sink.path_for("books", GAME_A))[0]
    assert row["bid"] is None and row["bid_size"] is None
    assert row["ask"] == 0.43 and row["ask_size"] == 200.0
    assert conn.books == 1


def test_a_torn_or_shapeless_message_is_counted_and_ignored(tmp_path):
    conn, _, _ = _conn(tmp_path, [[SPREAD_A]], [])
    for junk in ("not a dict", ["also", "not"], 17, None, {}, {"marketData": {"bids": []}},
                 {"trade": {"price": {"value": "0.4"}}}, {"marketData": "torn"}):
        conn.handle(junk)
    assert conn.books == 0 and conn.trades == 0
    assert conn.torn == 6, "4 non-dicts plus a slugless book and a slugless trade"
    assert conn.msgs == 8
    assert not list(tmp_path.iterdir()), "nothing written from a message with no slug"


def test_a_torn_frame_costs_no_reconnect(tmp_path):
    """A frame that is not JSON must not drop the socket: the backoff would
    cost every market on it, and the next frame is usually fine."""
    conn, _, _ = _conn(tmp_path, [[SPREAD_A]], [ACK, json.JSONDecodeError("x", "{", 0),
                                                   md_msg(SPREAD_A)])
    conn.sleep = lambda s: conn.stop.set()
    conn.run()
    assert conn.torn == 1 and conn.books == 1
    assert conn.reconnects == 1, "the reconnect is the scripted end of tape, not the torn frame"


def test_a_slug_that_does_not_parse_is_kept_under_its_own_name(tmp_path):
    """Every slug was chosen by the resolver, so a row here means the two
    parses disagree. Dropping it would hide that; the file names it."""
    conn, _, sink = _conn(tmp_path, [["weird"]], [])
    conn.handle(md_msg("tsc-mlb-col-det-2026-09-13-8pt5"))
    assert conn.unmapped == 1 and conn.books == 1
    row = _lines(sink.path_for("books", stream.UNMAPPED_GAME))[0]
    assert row["line"] is None and row["slug"].startswith("tsc-")


# --------------------------------------------------------------------------- #
# Reconnect, resubscribe, counters
# --------------------------------------------------------------------------- #


def test_a_reconnect_resubscribes_every_batch_that_socket_owned(tmp_path):
    """The failure this exists for: a socket that comes back with one of its
    four subscriptions restored keeps counting messages while the rest of its
    games are dark."""
    socks = [FakeSocket([ACK, md_msg(SPREAD_A)]), FakeSocket([ACK, trade_msg(SPREAD_B)])]
    made = []
    sink = stream.SlateSink(str(tmp_path))
    stop = threading.Event()
    slept: list[float] = []

    def sleep(s):
        slept.append(s)
        if len(slept) == 2:
            stop.set()

    def open_socket():
        made.append(socks[len(made) % len(socks)])
        return made[-1]

    conn = stream.StreamConnection("c0", [["a", "b"], ["c"]], sink, open_socket=open_socket,
                                   stop=stop, sleep=sleep)
    conn.run()
    assert conn.reconnects == 2 and slept == [1.0, 2.0], "backoff doubles from one second"
    assert len(socks[1].sent) == 4, "both batches, both subscription types, again"
    assert [m["subscribe"]["marketSlugs"] for m in socks[1].sent] == [
        ["a", "b"], ["a", "b"], ["c"], ["c"]], "the second socket resubscribes all of its own"
    assert all(s.closed for s in socks), "the dead socket is closed, not leaked"
    assert conn.books == 1 and conn.trades == 1, "both sessions recorded"


def test_backoff_is_capped(tmp_path):
    socks = [FakeSocket([]) for _ in range(6)]
    stop = threading.Event()
    slept: list[float] = []

    def sleep(s):
        slept.append(s)
        if len(slept) == 5:
            stop.set()

    conn = stream.StreamConnection("c0", [["a"]], stream.SlateSink(str(tmp_path)),
                                   open_socket=lambda: socks[len(slept)], stop=stop,
                                   sleep=sleep, max_backoff=4.0)
    conn.run()
    assert slept == [1.0, 2.0, 4.0, 4.0, 4.0], "doubles, then stops at the cap"


def test_counters_report_liveness_not_just_volume(tmp_path):
    """A connection with 400,000 messages and a last message two minutes old
    is a dark quarter of the slate, and the total alone says it is healthy."""
    conn, _, _ = _conn(tmp_path, [["a"] * 100, ["b"]], [])
    now = 1_800_000_000.0
    fresh = conn.counters(now)
    assert fresh["last_msg_age_s"] is None and fresh["last_heartbeat_age_s"] is None
    assert fresh["slugs"] == 101 and fresh["subscriptions"] == 4 and fresh["connected"] is False
    conn.handle({"heartbeat": {}})
    conn.handle(md_msg(SPREAD_A))
    later = conn.counters(conn.last_msg_at + 42.0)
    assert later["messages"] == 2 and later["books"] == 1 and later["heartbeats"] == 1
    assert later["last_msg_age_s"] == 42.0 and later["last_heartbeat_age_s"] >= 42.0


def test_the_slate_totals_are_the_sum_and_the_worst_connection(tmp_path):
    rec = stream.SlateRecorder([f"asc-cfb-g{i}-h-2026-09-19-pos-3pt5" for i in range(250)],
                               str(tmp_path), per_subscription=100, per_connection=200,
                               open_socket=lambda: FakeSocket([]))
    assert len(rec.connections) == 2 and [len(c.slugs) for c in rec.connections] == [200, 50]
    now = 1_800_000_000.0
    rec.connections[0].handle(md_msg(SPREAD_A))
    rec.connections[0].last_msg_at = now - 90.0
    totals = rec.totals(now)
    assert totals["books"] == 1 and totals["connections"] == 2 and totals["games"] == 1
    assert totals["stalest_s"] == 90.0, "the max over connections: a slate is its worst socket"
    assert totals["silent_connections"] == 1, "a connection that has never spoken is named"
    rec.connections[0].handle(trade_msg(SPREAD_B))
    rec.connections[0].handle(trade_msg(SPREAD_B))
    rec.connections[0].handle(trade_msg(SPREAD_A))
    assert rec.top_games(1) == [(GAME_B, 2)]
    rec.stop(timeout=0.1)


def test_a_slug_subscribed_twice_is_subscribed_once(tmp_path):
    """Two copies of a slug is two copies of every update for it, which
    double-counts that rung in the tape and in every episode built from it."""
    rec = stream.SlateRecorder(["a", "b", "a"], str(tmp_path), open_socket=lambda: FakeSocket([]))
    assert rec.slugs == ["a", "b"]


# --------------------------------------------------------------------------- #
# The slate resolver
# --------------------------------------------------------------------------- #


class _Conn:
    def __init__(self, rows, seen):
        self.rows, self.seen = rows, seen

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, stmt, params):
        self.seen["sql"], self.seen["params"] = str(stmt), params
        return self

    def all(self):
        return self.rows


class _Engine:
    def __init__(self, rows, seen):
        self.rows, self.seen = rows, seen

    def connect(self):
        return _Conn(self.rows, self.seen)


def test_the_slate_resolver_groups_by_game_and_orders_by_kickoff():
    import datetime as _dt
    now = _dt.datetime(2026, 9, 19, 20, 0, tzinfo=_dt.timezone.utc)
    late = _dt.datetime(2026, 9, 19, 23, 30, tzinfo=_dt.timezone.utc)
    early = _dt.datetime(2026, 9, 19, 19, 0, tzinfo=_dt.timezone.utc)
    seen: dict = {}
    rows = [(f"asc-{GAME_B}-neg-3pt5", late), (f"aec-{GAME_B}", late),
            (f"asc-{GAME_A}-pos-10pt5", early), (f"aec-{GAME_A}", early),
            (f"asc-{GAME_A}-pos-10pt5", early),                 # a duplicate row
            ("tsc-mlb-col-det-2026-09-13-8pt5", early)]         # a totals slug
    out = live.slate_slugs("cfb", None, _Engine(rows, seen), now=now)
    assert list(out) == [GAME_A, GAME_B], "earliest kickoff first, so --max-games keeps it"
    assert out[GAME_A] == [f"aec-{GAME_A}", f"asc-{GAME_A}-pos-10pt5"], "deduplicated, sorted"
    assert all("mlb-col-det" not in s for g in out for s in out[g]), "a totals ladder runs the other way"
    assert seen["params"]["p"] == "%-cfb-%"
    assert seen["params"]["from_ts"] == now - _dt.timedelta(hours=6), "CFB's live window"
    assert seen["params"]["to_ts"] == now + _dt.timedelta(hours=3)
    assert "game_start_time >= :from_ts" in seen["sql"] and "market_snapshots" in seen["sql"]
    assert "date_trunc('month'" in seen["sql"], "only a month boundary prunes partitions"


def test_a_date_narrows_the_window_but_never_widens_it_into_finished_games():
    import datetime as _dt
    now = _dt.datetime(2026, 9, 19, 20, 0, tzinfo=_dt.timezone.utc)
    seen: dict = {}
    live.slate_slugs("nfl", "2026-09-19", _Engine([], seen), now=now)
    assert seen["params"]["from_ts"] == now - _dt.timedelta(hours=5), "NFL's window, not the day's start"
    assert seen["params"]["to_ts"] == now + _dt.timedelta(hours=3), "and not the day's end"
    live.slate_slugs("nfl", "2026-09-20", _Engine([], seen), now=now)
    assert seen["params"]["from_ts"] == _dt.datetime(2026, 9, 20, tzinfo=_dt.timezone.utc)
    assert seen["params"]["to_ts"] == now + _dt.timedelta(hours=3)


def test_the_slate_query_uses_exactly_the_families_slugs_for_uses():
    """Two listings of the same ladder. A family added to one and not the
    other halves a slate silently, so the two sets are pinned equal rather
    than both trusted to have been updated."""
    import inspect
    import re
    src = inspect.getsource(live.slugs_for)
    assert set(re.findall(r"[a-z]+_team_full_game_(?:winner|spread)", src)) == set(
        live.LADDER_MARKET_TYPES)
    assert len(live.LADDER_MARKET_TYPES) == 6


def test_the_slug_parse_agrees_with_the_line_parse_it_replaces():
    """`game_and_line` reads the line WITHOUT being handed the winner slug.
    It must agree with `line_of`, which is the parse verified on 84,646
    settled pairs."""
    for slug in (WINNER_A, SPREAD_A, f"asc-{GAME_A}-neg-3pt5"):
        game, line = live.game_and_line(slug)
        assert game == GAME_A and line == live.line_of(slug, WINNER_A)
    assert live.game_and_line("tsc-mlb-col-det-2026-09-13-8pt5") is None
    assert live.game_and_line("asc-cfb-cencon-toledo-2026-09-12-2") is None


# --------------------------------------------------------------------------- #
# The guarantee
# --------------------------------------------------------------------------- #


def test_no_module_in_this_build_can_place_an_order():
    import cfb.run_stream_slate as runner
    from core.ladder import stream_scan
    for mod in (stream, stream_scan, live, runner):
        src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
        for bad in FORBIDDEN:
            assert bad not in src, f"{mod.__name__} carries {bad!r}"
        assert "ws/private" not in src, "the private stream is a different path"
    assert stream.WS_URL.endswith("/v1/ws/markets"), "the public markets stream, and only it"


def test_the_recorder_reaches_the_venue_only_through_the_public_stream():
    """Checked over the IDENTIFIERS the module actually references, not over
    its text: the docstring explains why REST is the thing being avoided and
    names `get_book` to do it, and a substring scan cannot tell an
    explanation from a call."""
    import ast
    tree = ast.parse(pathlib.Path(stream.__file__).read_text(encoding="utf-8"))
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    used |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    used |= {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)
             for a in n.names}
    for bad in ("get_book", "PolymarketGatewayClient", "post", "httpx", "requests"):
        assert bad not in used, f"the recorder references {bad}: REST is the budget it exists to save"
