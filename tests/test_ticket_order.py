"""The ticket list's order, and one row per opportunity.

    pytest --noconftest tests/test_ticket_order.py

Two defects the operator hit on a live Saturday, both visible on one
screenshot: the pane showed FRIDAY NIGHT's tickets while the ladder beside it
streamed Saturday's game, and a pair that had been crossing for ten minutes
filled the pane with thirty identical rows.

The first was two places ordering one list. The server sorted by
(game, ts) reversed, so the list ran alphabetically by opponent before it ran
by clock, and the page then called `.reverse()` on that believing it had been
handed raw file order. The second is that the executor writes a ticket every
cycle a crossing stands, which is the right thing for a record and the wrong
thing for a to-do list.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import re  # noqa: E402

from core.ladder import desk  # noqa: E402

PAGE = (pathlib.Path(__file__).resolve().parents[1] / "static" / "arb.html").read_text(encoding="utf-8")


def _tkt(game, ts, hi=10.5, lo=7.5):
    return {"ts": ts, "game": game,
            "leg1": {"market_line": hi, "side": "BUY YES", "price": 0.41, "qty": 1},
            "leg2": {"market_line": lo, "side": "BUY NO", "price": 0.53, "qty": 1},
            "edge_c": 1.5, "cost_usd": 0.94}


def _file(tmp_path, game, rows, mtime_iso):
    p = tmp_path / f"ladder_intents_aec-{game}.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    t = dt.datetime.fromisoformat(mtime_iso).replace(tzinfo=dt.timezone.utc).timestamp()
    os.utime(p, (t, t))
    return p


def test_a_game_that_crosses_midnight_keeps_its_tickets_in_one_run():
    rows = [_tkt("g", "23:41:07"), _tkt("g", "23:59:51"), _tkt("g", "00:17:17")]
    desk.stamp_instants(rows, dt.datetime(2026, 9, 19, 0, 20, tzinfo=dt.timezone.utc).timestamp())
    assert [r["at"] for r in rows] == [
        "2026-09-18T23:41:07", "2026-09-18T23:59:51", "2026-09-19T00:17:17"]
    assert rows[0]["at"] < rows[1]["at"] < rows[2]["at"], "the run is monotone"


def test_the_anchor_is_the_file_not_the_date_in_the_slug():
    """A game listed under the 18th that kicks off at 23:58 writes every one
    of its tickets on the 19th. Anchoring on the slug would date them all a
    day early and sink them below an earlier game's."""
    rows = [_tkt("cfb-hou-txtech-2026-09-18", "00:17:17"),
            _tkt("cfb-hou-txtech-2026-09-18", "03:19:02")]
    desk.stamp_instants(rows, dt.datetime(2026, 9, 19, 3, 20, tzinfo=dt.timezone.utc).timestamp())
    assert all(r["at"].startswith("2026-09-19") for r in rows), [r["at"] for r in rows]


def test_a_last_ticket_later_in_the_day_than_the_file_is_yesterdays():
    rows = [_tkt("g", "22:00:00"), _tkt("g", "23:30:00")]
    desk.stamp_instants(rows, dt.datetime(2026, 9, 19, 1, 0, tzinfo=dt.timezone.utc).timestamp())
    assert all(r["at"].startswith("2026-09-18") for r in rows), [r["at"] for r in rows]


def test_an_empty_file_and_a_missing_mtime_are_not_errors():
    desk.stamp_instants([], None)
    rows = [_tkt("g", "01:02:03")]
    desk.stamp_instants(rows, None)
    assert rows[0]["at"] == "01:02:03"


def test_load_tickets_puts_the_newest_first_across_games(tmp_path):
    _file(tmp_path, "cfb-hou-txtech-2026-09-18",
          [_tkt("cfb-hou-txtech-2026-09-18", "00:17:17"),
           _tkt("cfb-hou-txtech-2026-09-18", "03:19:02")], "2026-09-19T03:20")
    _file(tmp_path, "cfb-ncar-clmsn-2026-09-19",
          [_tkt("cfb-ncar-clmsn-2026-09-19", "15:58:40"),
           _tkt("cfb-ncar-clmsn-2026-09-19", "16:19:12")], "2026-09-19T16:20")
    got = desk.load_tickets(str(tmp_path))
    assert [t["ts"] for t in got] == ["16:19:12", "15:58:40", "03:19:02", "00:17:17"], \
        "strictly by instant, not by opponent name"
    assert got[0]["game"].endswith("2026-09-19"), "today is at the top"


def _code(fn: str) -> str:
    """A function's body with its comments stripped. Checking source for an
    absent call has to ignore the comment that explains why it is absent."""
    body = PAGE[PAGE.index(fn):]
    body = body[:body.index("\n}")]
    return re.sub(r"/\*.*?\*/", "", body, flags=re.S)


def test_the_page_does_not_reorder_what_the_server_sorted():
    """One list, one order. The `.reverse()` that used to be here is what
    turned a correct server sort into Friday night at the top."""
    body = _code("function renderTickets(")
    assert ".reverse()" not in body, "the page must not re-sort the server's order"
    assert "const newest = heads" in body


def test_the_page_shows_one_row_per_pair_and_counts_the_repeats():
    body = _code("function renderTickets(")
    assert "byPair" in body and "g.reps++" in body, "repeats of a pair collapse"
    assert "groups.map(g => ticketRow(g.head, g))" in body, "one row per group"
    assert "pair${groups.length === 1" in body, "the count names pairs, not writes"
    assert "reps" in PAGE[PAGE.index("function ticketRow("):][:1600], \
        "the row carries how many writes it stands for"


def test_the_age_comes_from_the_stamped_instant_not_a_bare_clock():
    """A bare HH:MM:SS wraps: a ticket from two days ago reads as this
    morning, which is exactly the confusion the order bug caused."""
    fn = PAGE[PAGE.index("function ticketAge("):]
    fn = fn[:fn.index("\n}")]
    assert "t.at" in fn, "prefer the server's dated instant"
    assert "86400" in fn, "the bare-clock fallback stays for older files"


def test_the_tails_follow_the_clock_not_the_league_name(tmp_path):
    """`ws_freshness_aec-<league>-...` sorts by LEAGUE first, so `wnba` beat
    `cfb` whatever the date and the desk showed the stream tail of a
    basketball game that had ended twelve hours earlier."""
    old = tmp_path / "ws_freshness_aec-wnba-por-gsv-2026-09-18.txt"
    new = tmp_path / "ws_freshness_aec-cfb-ga-ark-2026-09-19.txt"
    for f in (old, new):
        f.write_text("x\n", encoding="utf-8")
    os.utime(old, (1_000, 1_000))
    os.utime(new, (2_000, 2_000))
    got = desk.log_files(str(tmp_path), "freshness", last=1)
    assert [os.path.basename(g) for g in got] == [new.name], \
        "the newest WRITTEN tail, not the one whose league sorts last"
    both = desk.log_files(str(tmp_path), "freshness", last=2)
    assert [os.path.basename(g) for g in both] == [old.name, new.name], "oldest first, newest last"


def test_a_tail_that_vanishes_between_the_glob_and_the_stat_is_not_an_error(tmp_path):
    (tmp_path / "live_ladder_aec-cfb-a-b-2026-09-19.txt").write_text("x\n", encoding="utf-8")
    assert len(desk.log_files(str(tmp_path), "executor")) == 1
    assert desk.log_files(str(tmp_path / "gone"), "executor") == []


def test_a_ticket_whose_game_left_the_board_counts_as_past():
    """The third kind of history, and the one that was missing. A ticket the
    server cannot price -- because nobody is sampling that game any more --
    gets no live block, so a GONE test was False for it and it stayed in the
    list forever, while today's tickets were hidden the moment their crossing
    closed. Absence of a verdict is not a pass."""
    body = _code("function renderTickets(")
    assert "const onBoard = new Set((STATE.games || []).map(plainGame))" in body
    assert "!onBoard.has(plainGame(t.game))" in body
    d = body[body.index("const dead ="):body.index("const mine")]
    assert "GONE" in d and "over_budget" in d and "onBoard" in d, \
        "all three kinds of past in one predicate"


def test_the_row_carries_the_staler_leg_s_book_age():
    """A pair is only as live as its older side, and that number had no column
    while being the most decision-relevant fact on the row: on 2026-09-19,
    across 48 games of venue stream, crossings with both legs quoted inside
    two seconds held 19 of the 20 worth over $25, while the ones only the slow
    REST book saw sat on legs a median 884 seconds old."""
    assert "const legAge = t =>" in PAGE and "Math.max(...xs)" in PAGE, "the STALER leg"
    assert "leg1_book_age_s" in PAGE and "leg2_book_age_s" in PAGE
    row = _code("function ticketRow(")
    assert "ageCls(legAge(t))" in row and "agef(legAge(t))" in row
    grid = PAGE[PAGE.index(".tkr{"):PAGE.index(".tkr>span")]
    assert grid.count("px") >= 6, "the grid gained a column for it"


def test_the_state_route_sends_only_tickets_for_games_on_the_board():
    """Pricing every ticket ever written against the ladder on each poll was
    7.2 s and 451 KB per call on 2026-09-20; the page hid all but today's
    anyway. The tally keeps the full file, because 'placed' is about all
    time and needs no pricing."""
    src = pathlib.Path(__file__).resolve().parents[1] / "core" / "api.py"
    body = src.read_text(encoding="utf-8")
    body = body[body.index("def arb_state("):body.index("def ", body.index("def arb_state(") + 10)]
    assert "games = _ladder_desk.recent_games(out)" in body
    assert body.index("recent_games") < body.index("load_tickets"), "games first, then filter"
    assert "in on_board]" in body, "the view is built only for on-board games"
    assert '"tally": _ladder_desk.tally(raw)' in body, "the tally sees the whole file"
    assert '"tickets_on_file": len(raw)' in body


def test_a_game_the_stream_detector_watches_is_on_the_board(tmp_path):
    """It logs to stream_exec_*.txt and touches its intents file only when it
    tickets; the board must not wait for a ticket to admit the game exists."""
    f = tmp_path / "stream_exec_aec-nfl-phi-ten-2026-09-20.txt"
    f.write_text("stream executor prefix=... rungs=42\n", encoding="utf-8")
    assert desk.recent_games(str(tmp_path)) == ["aec-nfl-phi-ten-2026-09-20"]
