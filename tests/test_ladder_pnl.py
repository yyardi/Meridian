"""The money arithmetic of a two-leg pair, and the pages that show it.

The arithmetic is worth a test because three of its cases are easy to get
wrong in the direction that FLATTERS: a pair whose legs filled different
quantities is an arbitrage only to the smaller side, an unpaired leg is not
half a position, and a ticket nobody placed is not a loss. Each is asserted
here against a hand-computed number, not against the implementation.
"""
from __future__ import annotations

import importlib
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core.ladder import pnl, scan  # noqa: E402

GAME = "cfb-mia-wake-2026-09-18"
PREFIX = "aec-" + GAME

#: The ticket the executor writes: buy YES +10.5 at 0.41, buy NO +7.5 at 0.53.
#: The pair costs 0.94 and pays $1.00 in every score.
TICKET = {"ts": "23:41:07", "game": GAME,
          "leg1": {"market_line": 10.5, "side": "BUY YES", "price": 0.41, "qty": 2},
          "leg2": {"market_line": 7.5, "side": "BUY NO", "price": 0.53, "qty": 2},
          "displayed_size": 966.0, "edge_c": 2.1, "cost_usd": 1.88,
          "leg1_book_age_s": 412.0, "leg2_book_age_s": 3.0, "meridian_placed": False}


def _ticket(status: str, **record) -> dict:
    t = dict(TICKET)
    t["id"] = "t1"
    t["status"] = status
    if record:
        t["record"] = record
    return t


def test_a_filled_pair_pays_a_dollar_a_contract_and_the_net_is_what_is_left():
    r = pnl.attempt_pnl(_ticket("recorded", l1q=2, l1p=0.41, l2q=2, l2p=0.53))
    assert r["qty_filled"] == 2
    assert r["cost"] == pytest.approx(2 * 0.41 + 2 * 0.53)          # 1.88
    assert r["guaranteed"] == pytest.approx(2.00)
    assert r["net_if_settled"] == pytest.approx(0.12)
    assert r["bonus_if_between"] == pytest.approx(2.00)             # a second $1 a contract
    assert r["leg_exposure"] == 0 and not r["legged"]
    # both legs charged the venue's taker fee at the price each one traded at
    assert r["fees"] == pytest.approx(2 * scan.fee(0.41) + 2 * scan.fee(0.53))
    assert r["net_after_fees"] == pytest.approx(0.12 - r["fees"])


def test_a_legged_attempt_is_a_directional_holding_not_half_an_arbitrage():
    r = pnl.attempt_pnl(_ticket("recorded", l1q=2, l1p=0.41, l2q=0, l2p=None))
    assert r["legged"] and r["qty_filled"] == 0
    assert r["guaranteed"] == 0.0                     # nothing is guaranteed by one leg
    assert r["cost"] == pytest.approx(0.82)
    assert r["net_if_settled"] == pytest.approx(-0.82)  # the leg is charged in full
    assert r["leg_exposure"] == pytest.approx(0.82)
    assert r["bonus_if_between"] == 0.0


def test_the_mirror_of_a_legged_attempt_is_legged_too():
    """Leg 2 on and leg 1 missed carries the same one-sided exposure to the
    score as the case the fill test was written around, and the arithmetic
    already charges it in full -- only the flag, the /pnl tile that counts it
    and the sentence under the row were blind to it."""
    r = pnl.attempt_pnl(_ticket("recorded", l1q=0, l1p=None, l2q=3, l2p=0.53))
    assert r["legged"] and r["loose_leg"] == 2
    assert r["qty_filled"] == 0 and r["guaranteed"] == 0.0
    assert r["cost"] == pytest.approx(1.59)
    assert r["net_if_settled"] == pytest.approx(-1.59)
    assert r["leg_exposure"] == pytest.approx(1.59)
    # and the ordinary direction still reads as leg 1
    assert pnl.attempt_pnl(_ticket("recorded", l1q=2, l1p=0.41, l2q=0))["loose_leg"] == 1


def test_a_pair_that_filled_different_quantities_counts_at_the_smaller_side():
    r = pnl.attempt_pnl(_ticket("recorded", l1q=5, l1p=0.41, l2q=2, l2p=0.53))
    assert r["qty_filled"] == 2                       # not 5, not 7, not 3.5
    assert r["guaranteed"] == pytest.approx(2.00)
    assert r["cost"] == pytest.approx(5 * 0.41 + 2 * 0.53)          # 3.11
    assert r["net_if_settled"] == pytest.approx(2.00 - 3.11)
    assert r["unpaired_qty"] == 3
    assert r["leg_exposure"] == pytest.approx(3 * 0.41)             # the three loose YES
    assert not r["legged"]                            # leg 2 did fill, just for less


def test_a_skipped_ticket_costs_nothing_and_guarantees_nothing():
    for status in ("skipped", "open"):
        r = pnl.attempt_pnl(_ticket(status))
        assert r["status"] == status
        assert (r["cost"], r["guaranteed"], r["net_if_settled"], r["leg_exposure"]) == (0.0, 0.0, 0.0, 0.0)
        assert r["qty_filled"] == 0 and not r["legged"]


def test_a_recorded_price_left_blank_falls_back_to_the_limit_and_says_so():
    r = pnl.attempt_pnl(_ticket("recorded", l1q=2, l1p=None, l2q=2, l2p=0.53))
    assert r["l1p"] == pytest.approx(0.41) and r["price_source"] == "limit/recorded"
    assert r["cost"] == pytest.approx(1.88)


def test_a_session_with_no_attempts_is_zero_and_not_an_error(tmp_path):
    s = pnl.session(str(tmp_path))
    assert s["attempts"] == [] and s["placed"] == 0 and s["recorded"] == 0
    assert s["pairs_filled"] == 0 and s["committed"] == 0.0 and s["net_if_settled"] == 0.0
    assert s["tally"]["verdict"].startswith("Not yet")
    assert pnl.opportunity(str(tmp_path)) == [] and pnl.game_status(str(tmp_path)) == []


# --------------------------------------------------------------------- #
# Over the files the executor and the instrument actually write
# --------------------------------------------------------------------- #

def _rung(line: float, bid: float, ask: float, size: float = 500.0) -> dict:
    return {"line": line, "rest": {"bid": bid, "ask": ask, "bsz": size, "asz": size, "tt": "1"},
            "ws": None, "touch_equal": True, "tt_equal": True, "rest_behind_s": 0.0}


#: The second ticket of the night: three contracts, and leg 2 never filled.
LEGGED = {"ts": "23:52:11", "game": GAME,
          "leg1": {"market_line": 14.5, "side": "BUY YES", "price": 0.22, "qty": 3},
          "leg2": {"market_line": 10.5, "side": "BUY NO", "price": 0.735, "qty": 3},
          "displayed_size": 8215.0, "edge_c": 3.4, "cost_usd": 2.87,
          "leg1_book_age_s": 98.0, "leg2_book_age_s": 2.0, "meridian_placed": False}

#: Four samples, one per state the page has to tell apart: consistent, a
#: violation worth acting on, one below the floor, and one that exists only
#: against the winner market (line 0) -- which the executor never ticketed.
TAPE = [
    {"t": "23:40:00", "took_s": 1.2, "rows": [_rung(7.5, 0.40, 0.42), _rung(10.5, 0.50, 0.52)],
     "viol_rest": 0, "viol_ws": 0, "viol_common": 0, "ws_msgs": 10, "ws_trades": 0},
    {"t": "23:41:00", "took_s": 1.1, "rows": [_rung(7.5, 0.60, 0.62), _rung(10.5, 0.48, 0.50)],
     "viol_rest": 1, "viol_ws": 1, "viol_common": 1, "ws_msgs": 22, "ws_trades": 3},
    {"t": "23:42:00", "took_s": 1.0, "rows": [_rung(7.5, 0.60, 0.62, 50.0), _rung(10.5, 0.48, 0.50, 50.0)],
     "viol_rest": 1, "viol_ws": 1, "viol_common": 1, "ws_msgs": 31, "ws_trades": 4},
    {"t": "23:43:00", "took_s": 1.0,
     "rows": [_rung(0.0, 0.55, 0.57), _rung(7.5, 0.40, 0.42), _rung(10.5, 0.38, 0.40)],
     "viol_rest": 2, "viol_ws": 2, "viol_common": 2, "ws_msgs": 44, "ws_trades": 6},
]


@pytest.fixture
def out(tmp_path):
    """One game's night: two tickets, the operator's records, and the tape."""
    (tmp_path / f"ladder_intents_{PREFIX}.jsonl").write_text(
        json.dumps(TICKET) + "\n" + json.dumps(LEGGED) + "\n")
    (tmp_path / "ladder_attempts.jsonl").write_text("".join(json.dumps(a) + "\n" for a in (
        {"id": f"{GAME}|23:41:07|10.5/7.5", "status": "recorded", "at": "2026-09-18T23:44:00+00:00",
         "l1q": 2, "l1p": 0.41, "l1s": 4, "l2q": 2, "l2p": 0.53, "l2s": 9},
        {"id": f"{GAME}|23:52:11|14.5/10.5", "status": "recorded", "at": "2026-09-19T00:01:00+00:00",
         "l1q": 3, "l1p": 0.22, "l1s": 7, "l2q": 0, "l2p": None, "l2s": None})))
    (tmp_path / f"ws_freshness_{PREFIX}.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in TAPE))
    return tmp_path


def test_the_session_reads_the_ticket_ledger_off_the_files(out):
    s = pnl.session(str(out))
    assert s["placed"] == 2 and s["recorded"] == 2 and s["pairs_filled"] == 1
    assert s["committed"] == pytest.approx(1.88 + 3 * 0.22)     # 2.54: the loose leg counts
    assert s["guaranteed"] == pytest.approx(2.00)               # only the paired two
    assert s["net_if_settled"] == pytest.approx(2.00 - 2.54)
    assert s["legged"] == 1 and s["leg_exposure"] == pytest.approx(0.66)
    assert {a["game"] for a in s["attempts"]} == {GAME}
    # the totals name their own population: this directory, these games, these
    # dates -- intents files accumulate across nights
    assert s["games"] == [GAME] and s["dates"] == ["2026-09-18"]


def test_the_tape_reports_the_share_of_samples_with_a_ticketable_pair(out):
    g = pnl.opportunity(str(out))[0]
    assert g["key"] == GAME and g["samples"] == 4
    # samples 2 and 3 carry the same pair; only sample 2 is worth the floor,
    # and sample 4's only pairs are against the winner market
    assert g["with_violation"] == 2 and g["share"] == pytest.approx(0.5)
    assert g["over_floor"] == 1 and g["share_over_floor"] == pytest.approx(0.25)
    assert g["floor_usd"] == pnl.FLOOR_USD
    # edge = 0.60 - 0.50 - fee(0.50) - fee(0.60) on 500 displayed
    edge = 0.60 - 0.50 - scan.fee(0.50) - scan.fee(0.60)
    assert g["best_dollars"] == pytest.approx(round(edge * 500, 2), abs=0.01)
    assert len(g["top"]) == 1 and g["top"][0]["t"] == "23:41:00"   # one pair, its best sample
    assert g["ws_trades"] == 6


def test_a_sample_with_no_two_sided_rung_is_still_a_sample(tmp_path):
    """The instrument writes `rows: []` before any rung has a two-sided book,
    and those cycles are exactly the ones in which there was nothing to find.
    Dropping them from the denominator would raise every share on the page
    while the column stayed headed "samples" -- and /ladder's own history strip
    counts the same file the other way, so the two pages would disagree about
    one number in front of the operator."""
    from core.ladder import tape

    rows = [{"t": f"23:{m:02d}:00", "took_s": 1.0, "rows": [], "viol_rest": 0, "viol_ws": 0,
             "viol_common": 0, "ws_msgs": 4, "ws_trades": 0} for m in range(30, 38)]
    rows.insert(4, TAPE[1])                                  # one cycle with a pair
    rows.append(TAPE[0])                                     # one consistent ladder
    p = tmp_path / f"ws_freshness_{PREFIX}.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))

    g = pnl.tape_summary(str(p))
    assert g["samples"] == len(rows) == 10 == len(tape.samples(str(p), 5000))
    assert g["with_violation"] == 1 and g["share"] == pytest.approx(0.1)


def test_a_pair_against_the_winner_market_is_not_an_opportunity(out):
    """Line 0 settles $0.50 on an NFL tie and at last fair price on a
    postponement, so the executor never ticketed one. Counting those pairs
    here would credit the strategy with chances it declines by design."""
    g = pnl.opportunity(str(out))[0]
    assert g["last_pairs"] == 2 and g["last_spread_pairs"] == 0
    assert g["viol_rest"] == 2                 # the instrument's own count, unmerged


def test_the_live_strip_names_both_writers_and_the_tickets_issued(out):
    rows = pnl.game_status(str(out), now=None)
    assert [r["game"] for r in rows] == [PREFIX]
    r = rows[0]
    assert r["tickets"] == 2 and r["issued_usd"] == pytest.approx(1.88 + 2.87)
    assert r["tape_age_s"] is not None and r["tape_age_s"] < 3600
    assert r["executor_age_s"] is None            # no executor log in this fixture
    assert r["best_dollars"] > pnl.FLOOR_USD


# --------------------------------------------------------------------- #
# The pages
# --------------------------------------------------------------------- #

def _client(tmp_path, monkeypatch):
    """The desk, reloaded against `tmp_path`: OUT is read at import."""
    monkeypatch.setenv("LADDER_OUT", str(tmp_path))
    mod = importlib.reload(importlib.import_module("cfb.ladder_desk_app"))
    from fastapi.testclient import TestClient
    return TestClient(mod.app)


def test_the_pages_render_with_no_files_at_all(tmp_path, monkeypatch):
    """An empty directory is the state the desk is in before kickoff. Both
    pages must answer it with a page, not a 500 -- the operator opens them
    early, and a stack trace at 23:00 reads as "the desk is down"."""
    c = _client(tmp_path, monkeypatch)
    assert "no live game" in c.get("/").text
    page = c.get("/pnl").text
    assert c.get("/pnl").status_code == 200
    assert "No tickets yet tonight." in page and "cash committed" in page


def test_the_pages_render_the_fixture_night_with_its_numbers(out, monkeypatch):
    c = _client(out, monkeypatch)
    index = c.get("/").text
    assert "MIA-WAKE" in index and "href='/pnl'" in index and "href='/ladder'" in index
    assert "$32.97" in index                    # best $ seen, at quoted size
    page = c.get("/pnl").text
    assert "$1.88" in page and "$2.00" in page and "+$0.12" in page
    assert "2 @ 0.410" in page and "2 @ 0.530" in page
    # the legged attempt, and the session net it drags negative: the sign goes
    # OUTSIDE the dollar sign, because "$-0.54" is read as a price
    assert "-$0.66" in page and "-$0.54" in page and "$-" not in page
    assert "legged &mdash; leg 1 filled and leg 2 did not" in page
    assert "<td>&mdash;</td>" in page          # leg 2 did not fill: a dash, not "0 @ 0.735"
    # what was SEEN (one sample over the floor, of four) against what was CAUGHT
    assert "Seen vs caught" in page and "<b>1</b> of 4 samples across 1 game" in page
    assert "<b>1</b> pair has actually filled" in page


def test_a_game_with_no_tape_prints_absence_and_not_the_word_none(tmp_path, monkeypatch):
    """The executor has ticketed and the stream instrument has not written, so
    the three stream counts do not exist yet. They are the one column that says
    whether the two books agree, and `None` there reads as a value."""
    (tmp_path / f"ladder_intents_{PREFIX}.jsonl").write_text(json.dumps(TICKET) + "\n")
    index = _client(tmp_path, monkeypatch).get("/").text
    assert "MIA-WAKE" in index and ">None<" not in index and "None / None" not in index
    assert "&mdash;Z" not in index                 # nor a stamp that is only its suffix
    assert "&mdash; / &mdash; / &mdash;" in index


def test_the_index_refreshes_itself_except_while_fills_are_being_typed(out, monkeypatch):
    """The index is the page carrying the writer heartbeats, whose whole job is
    to go stale; /ladder and /pnl already reload on the same timer. The one
    state it must NOT reload in is `placed`, where the operator has the fill
    boxes open."""
    c = _client(out, monkeypatch)
    assert "location.reload()" in c.get("/").text
    tid = json.loads((out / f"ladder_intents_{PREFIX}.jsonl").read_text().splitlines()[0])
    tid = f"{GAME}|{tid['ts']}|10.5/7.5"
    c.post("/ticket", data={"id": tid, "action": "placed"}, follow_redirects=False)
    page = c.get("/").text
    assert "Save fills" in page and "location.reload()" not in page


def test_the_pnl_page_prints_the_thresholds_the_verdict_is_read_against(out, monkeypatch):
    """A verdict with its rule in a doc is a conclusion nobody at the desk can
    check; the criteria belong beside the ledger they are counted off."""
    page = _client(out, monkeypatch).get("/pnl").text
    assert "3 of 5 both filled" in page and "3 of 5 leg 1 unfilled" in page
    assert "Not yet" in page                       # two recorded, so the rule is not read yet


def test_the_ladder_view_answers_with_and_without_a_game(out, monkeypatch):
    """The desk links to /ladder from every page, so the route has to exist on
    this app and not only on the dashboard's."""
    from core.ladder import tape

    c = _client(out, monkeypatch)
    page = c.get("/ladder").text
    # asserted on the DATA the page must be drawing (the last sample's stamp
    # and its rungs), not on wording the tape page owns and keeps revising
    assert "23:43:00" in page and "+10.5" in page
    assert c.get(f"/ladder?game={PREFIX}").status_code == 200
    # a game with no tape gets its own empty state, not another game's ladder
    assert tape.latest(str(out), "aec-cfb-aaa-bbb-2026-01-01") is None
    miss = c.get("/ladder?game=aec-cfb-aaa-bbb-2026-01-01")
    assert miss.status_code == 200 and "23:43:00" not in miss.text


def test_the_pnl_modules_have_no_venue_call_and_no_order_path():
    """The same rule the desk is pinned to, extended to what it now imports:
    these read files, and the property is their imports, not a promise."""
    from cfb import ladder_pnl_page, ladder_tape_page
    from core.ladder import tape
    for mod in (pnl, tape, ladder_pnl_page, ladder_tape_page):
        src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
        for bad in ("PolymarketGatewayClient", "PolymarketOrderClient", "place_order",
                    "create_order", "/orders", "httpx", "MERIDIAN_ORDER_TOKEN", "api.polymarket"):
            assert bad not in src, f"{mod.__name__} carries {bad}"
