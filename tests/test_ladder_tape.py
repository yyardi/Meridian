"""The live ladder page: the bound arithmetic, the torn tape, and the page.

The fixtures are two WNBA ladders that differ in ONE rung. The clean one is
monotone (YES price non-decreasing in the line number, which is the whole
relation `core.ladder.scan` enforces) and must produce nothing; the crossed
one has +4.5 re-quoted down to 0.28/0.30 and must produce exactly the two
pairs hand-counted below, with the dollars the scanner's own arithmetic gives.

Hand-counted, because a test that recomputes the thing it is testing checks
nothing. Every expected number in this file was worked out from the prices
(fee = 0.06 p (1-p) per leg) and written down, not read off the code.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from cfb import ladder_tape_page
from core.ladder import scan, tape
from core.ladder.intent import is_spread_pair

GAME = "aec-wnba-lv-sea-2026-09-18"

#: line -> (bid, ask, bid size, ask size). Monotone in the line number: a
#: ladder no pair of which contradicts any other.
CLEAN = {
    -10.5: (0.31, 0.32, 400, 400),
    -4.5: (0.44, 0.46, 300, 400),
    0.0: (0.46, 0.48, 900, 900),
    4.5: (0.58, 0.60, 200, 800),
    10.5: (0.70, 0.72, 400, 400),
}

#: The same ladder with +4.5 stale at 0.28/0.30 -- easier to cover than +4.5
#: and cheaper than the winner, which cannot both be true.
CROSSED = {**CLEAN, 4.5: (0.28, 0.30, 200, 800)}

#: A WNBA ladder as the venue actually hangs one: rungs at +/-2.5 and +/-5.5,
#: i.e. INSIDE the 3.5 floor of `core.ladder.intent.MID_LADDER`, which was
#: measured on college football. +2.5 is stale at 0.30/0.32 while -2.5 bids
#: 0.46 -- the easier line cheaper than the harder one, the same contradiction
#: as CROSSED, on lines a CFB fixture never reaches.
WNBA_TIGHT = {
    -5.5: (0.30, 0.32, 400, 400),
    -2.5: (0.46, 0.48, 500, 500),
    0.0: (0.49, 0.51, 900, 900),
    2.5: (0.30, 0.32, 600, 900),
    5.5: (0.66, 0.68, 400, 400),
}

# Hand arithmetic on WNBA_TIGHT, fee = 0.06 p (1-p) at BOTH legs:
#   buy +2.5 ask 0.32, sell -2.5 bid 0.46:
#       0.14 - 0.013056 - 0.014904 = 0.11204 -> 11.20c, size min(900,500)=500
#                                               -> $56.02, a spread pair
#   buy +2.5 ask 0.32, sell  0.0 bid 0.49:
#       0.17 - 0.013056 - 0.014994 = 0.14195 -> 14.19c, size min(900,900)=900
#                                               -> $127.75, a WINNER leg
# Nothing else crosses: every other pair has the easier line dearer.

# Hand arithmetic on CROSSED, fee = 0.06 p (1-p) charged at BOTH legs:
#   buy +4.5 ask 0.30, sell -4.5 bid 0.44:
#       0.14 - 0.0126 - 0.014784 = 0.112616 -> 11.26c, size min(800,300)=300
#                                              -> $33.78, a spread pair
#   buy +4.5 ask 0.30, sell  0.0 bid 0.46:
#       0.16 - 0.0126 - 0.014904 = 0.132496 -> 13.25c, size min(800,900)=800
#                                              -> $106.00, a WINNER leg
#   buy +4.5 ask 0.30, sell -10.5 bid 0.31:
#       0.01 - 0.0126 - 0.012834 < 0 -> crosses gross, eaten by the fees
VIOL_REST = 2


def _rows(rungs: dict, *, ws: dict | None = None, tt: str = "2026-09-18T23:40:00.0Z") -> list[dict]:
    """The instrument's row shape (cfb/run_ws_freshness.py `compare`): every
    row carries a REST touch, only some carry the stream's."""
    out = []
    for line, (bid, ask, bsz, asz) in sorted(rungs.items()):
        row = {"line": line, "rest": {"bid": bid, "ask": ask, "bsz": bsz, "asz": asz, "tt": tt}}
        if ws and line in ws:
            w = ws[line]
            row["ws"] = {"bid": w[0], "ask": w[1], "bsz": w[2], "asz": w[3], "tt": tt,
                         "recv_age_s": 4.2}
            row["touch_equal"] = (w[0], w[1]) == (bid, ask)
            row["tt_equal"] = True
            row["rest_behind_s"] = 0.0
        out.append(row)
    return out


def _sample(rungs: dict, t: str = "23:40:07", **kw) -> dict:
    s = {"t": t, "took_s": 1.4, "rows": _rows(rungs), "viol_rest": 0, "viol_ws": 0,
         "viol_common": 0, "ws_msgs": 120, "ws_trades": 3, "ws_reconnects": 0}
    s.update(kw)
    return s


def _tape(tmp_path, samples: list[dict], game: str = GAME) -> pathlib.Path:
    p = tmp_path / f"ws_freshness_{game}.jsonl"
    p.write_text("".join(json.dumps(s) + "\n" for s in samples), encoding="utf-8")
    return p


def _rung(snap: dict, line: float) -> dict:
    return next(r for r in snap["rungs"] if r["line"] == line)


# --------------------------------------------------------------------- #
# The arithmetic
# --------------------------------------------------------------------- #

def test_a_clean_ladder_produces_no_bound_breach_and_no_pair():
    snap = tape.ladder(_sample(CLEAN), GAME, gross_count=True)
    assert len(snap["rungs"]) == 5
    assert snap["violations"] == []
    assert (snap["above_cap"], snap["fee_eaten"], snap["ticketable"]) == (0, 0, 0)
    for r in snap["rungs"]:
        assert not r["ask_below_lo"] and not r["bid_above_hi"], r["line"]
        assert not r["lit_ask"] and not r["lit_bid"], r["line"]
    # The bound is the dominance relation, stated per rung.
    assert _rung(snap, 4.5)["lo"] == 0.46      # highest bid among harder rungs
    assert _rung(snap, 4.5)["hi"] == 0.72      # lowest ask among easier rungs
    assert _rung(snap, -10.5)["lo"] is None and _rung(snap, 10.5)["hi"] is None


def test_one_stale_rung_breaks_the_bound_and_prices_the_pair():
    snap = tape.ladder(_sample(CROSSED), GAME, gross_count=True)
    stale, winner, harder = _rung(snap, 4.5), _rung(snap, 0.0), _rung(snap, -4.5)

    # +4.5 is quoted BELOW the best bid of every harder rung: its ask is the
    # side we would buy, so that is the side that lights.
    assert stale["lo"] == 0.46 and stale["ask"] == 0.30
    assert stale["ask_below_lo"] and stale["lit_ask"] and not stale["lit_bid"]
    # and the two rungs we would sell into light on their bid.
    assert harder["bid_above_hi"] and harder["lit_bid"] and not harder["lit_ask"]
    assert winner["bid_above_hi"] and winner["lit_bid"]
    assert _rung(snap, 10.5)["ask_below_lo"] is False       # untouched by one bad rung

    v = {(x["high_line"], x["low_line"]): x for x in snap["violations"]}
    assert set(v) == {(4.5, -4.5), (4.5, 0.0)}
    assert v[(4.5, -4.5)]["edge_c"] == 11.26 and v[(4.5, -4.5)]["size"] == 300
    assert v[(4.5, -4.5)]["dollars"] == 33.78
    assert v[(4.5, 0.0)]["edge_c"] == 13.25 and v[(4.5, 0.0)]["dollars"] == 106.0
    # biggest first, so the operator reads the largest number at the top
    assert [x["dollars"] for x in snap["violations"]] == [106.0, 33.78]


def test_a_winner_leg_pair_is_never_a_spread_pair_and_says_so():
    snap = tape.ladder(_sample(CROSSED), GAME)
    v = {(x["high_line"], x["low_line"]): x for x in snap["violations"]}
    assert v[(4.5, 0.0)]["spread_pair"] is False
    assert "winner" in v[(4.5, 0.0)]["why_not"]
    # The spread-vs-spread pair clears every filter the executor applies:
    # both legs mid-ladder, both spreads, $33.78 over the $25 floor.
    assert v[(4.5, -4.5)]["spread_pair"] is True and v[(4.5, -4.5)]["mid"] is True
    assert v[(4.5, -4.5)]["why_not"] == "" and snap["ticketable"] == 1


def test_a_wnba_pair_off_the_mid_ladder_is_one_the_executor_would_ticket():
    """The page's verdict column must be the EXECUTOR's predicate, not a
    stricter one of its own.

    The executor gates on two tests -- `x.dollars >= floor and
    is_spread_pair(x)` (cfb/run_ladder_executor.py) -- and uses `is_mid` only
    to sort, so a +/-2.5 pair is ticketed and pushed. MID_LADDER starts at 3.5,
    so a page that treated it as a gate would print "the executor would: off
    the mid ladder" over a $56 ticket the operator's phone is buzzing about,
    and would do it on every WNBA game while the CFB fixtures above, whose
    rungs sit inside the band, stayed green.
    """
    snap = tape.ladder(_sample(WNBA_TIGHT), GAME, gross_count=True)
    v = {(x["high_line"], x["low_line"]): x for x in snap["violations"]}
    assert set(v) == {(2.5, -2.5), (2.5, 0.0)}

    pair = v[(2.5, -2.5)]
    assert pair["edge_c"] == 11.2 and pair["size"] == 500 and pair["dollars"] == 56.02
    assert pair["spread_pair"] is True
    assert pair["mid"] is False              # outside the band, and still a ticket
    assert pair["why_not"] == ""
    assert "winner" in v[(2.5, 0.0)]["why_not"]

    # The count on the page against the executor's own filter, recomputed here
    # from the scanner with the executor's arguments rather than read off the
    # page: one predicate, two measurements of it.
    gate = [x for x in scan.scan_ladder(GAME, WNBA_TIGHT, max_size=1e12)
            if x.dollars >= tape.DEFAULT_FLOOR_USD and is_spread_pair(x)]
    assert snap["ticketable"] == len(gate) == 1

    page = ladder_tape_page.render({**snap, "game": GAME, "tape_age_s": 1.0, "history": []},
                                   [GAME], GAME, "/out")
    assert "ticket it" in page and "off the mid ladder" not in page
    assert "mid-ladder pairs go first" in page      # an ordering, said as one


def test_a_sub_floor_pair_is_the_only_dollar_reason_the_page_gives():
    """The floor is a gate (the executor's `--floor-usd`); the mid ladder is
    not. Shrinking the displayed size is what must silence the ticket."""
    thin = {**WNBA_TIGHT, 2.5: (0.30, 0.32, 600, 100), -2.5: (0.46, 0.48, 100, 500)}
    snap = tape.ladder(_sample(thin), GAME)
    pair = next(x for x in snap["violations"] if x["spread_pair"])
    assert pair["dollars"] == 11.2 and pair["why_not"] == "under the $25 floor"
    assert snap["ticketable"] == 0


def test_a_gross_bound_breach_is_not_a_tradeable_leg():
    """-10.5's bid (0.31) sits a cent above the stale rung's ask, so the bound
    is broken -- and both fees eat the cent, so nothing lights. Two different
    claims, and the page must not print one as the other."""
    snap = tape.ladder(_sample(CROSSED), GAME, gross_count=True)
    r = _rung(snap, -10.5)
    assert r["bid_above_hi"] is True and r["hi"] == 0.30
    assert r["lit_bid"] is False
    assert snap["fee_eaten"] == 1


def test_the_page_recomputes_the_count_the_instrument_wrote_itself():
    """The instrument scans the REST book live and writes `viol_rest`; this
    module re-derives it from the touches the same line recorded. They are two
    measurements of one quantity and must agree, which is the check that the
    table is built from REST and not from a blend of REST and the stream."""
    snap = tape.ladder(_sample(CROSSED, viol_rest=VIOL_REST), GAME)
    assert len(snap["violations"]) == snap["viol_rest"] == VIOL_REST


def test_a_rung_quoted_on_one_side_only_is_shown_and_kept_out_of_the_scan():
    s = _sample(CLEAN)
    s["rows"].append({"line": 14.5, "rest": {"bid": 0.80, "ask": None, "bsz": 50, "asz": 0,
                                             "tt": "2026-09-18T23:40:00.0Z"}})
    snap = tape.ladder(s, GAME)
    one = _rung(snap, 14.5)
    assert one["both"] is False and one["ask"] is None and one["bid"] == 0.80
    # The bound the OTHER rungs impose on it still holds and is still worth
    # showing -- when its ask comes back it must be at or above 0.70.
    assert one["lo"] == 0.70 and one["hi"] is None
    # But it is not scanned and cannot light: `core.ladder.live` drops
    # one-sided rungs from the executor's sample, so the scanner here sees the
    # same population it would, and a half-quoted rung prices no pair.
    assert not one["ask_below_lo"] and not one["bid_above_hi"]
    assert not one["lit_ask"] and not one["lit_bid"]
    assert snap["violations"] == [] and len(snap["rungs"]) == 6


def test_a_rung_only_the_stream_quotes_is_drawn_and_never_priced(tmp_path):
    """A rung REST has no book for is a display row, not a leg.

    Today the instrument's `compare()` drops such a rung before it is written,
    so this case lives one file away from the guarantee that keeps it out --
    which is exactly the kind of promise that stops being true without a test
    failing. Priced off the stream, the rung below would print a $9 pair
    against a book the executor cannot act on and could not see.
    """
    s = _sample(CLEAN)
    s["rows"].append({"line": 14.5,
                      "ws": {"bid": 0.35, "ask": 0.37, "bsz": 500, "asz": 500,
                             "tt": "2026-09-18T23:40:00.0Z", "recv_age_s": 1.1}})
    snap = tape.ladder(s, GAME)
    ws_only = _rung(snap, 14.5)
    assert ws_only["src"] == "ws" and ws_only["both"] is True
    assert ws_only["scanned"] is False           # two-sided, and still not the scan's input
    # 0.37 sits below every harder rung's bid, so a scan that took it would
    # report pairs; the executor's own input has no such rung at all.
    assert snap["violations"] == [] and snap["ticketable"] == 0
    assert not ws_only["lit_ask"] and not ws_only["bid_above_hi"]
    page = ladder_tape_page.render({**snap, "game": GAME, "tape_age_s": 1.0, "history": []},
                                   [GAME], GAME, str(tmp_path))
    assert "ws only — not scanned" in page


def test_the_stream_is_reported_beside_rest_never_blended_into_it():
    """Every row carries REST; only some carry the stream. Building the table
    from whichever is present would assemble one ladder out of two sources at
    two instants -- so REST drives it and the stream gets its own column."""
    s = _sample(CROSSED, viol_ws=1, viol_common=1, ws_trades=17)
    s["rows"] = _rows(CROSSED, ws={4.5: (0.58, 0.60, 200, 800), -4.5: (0.44, 0.46, 300, 400)})
    snap = tape.ladder(s, GAME)
    assert _rung(snap, 4.5)["ask"] == 0.30 and _rung(snap, 4.5)["src"] == "rest"
    assert _rung(snap, 4.5)["touch_equal"] is False       # the stream disagrees here
    assert _rung(snap, -4.5)["touch_equal"] is True
    assert _rung(snap, -4.5)["ws_age_s"] == 4.2
    assert len(snap["violations"]) == 2                   # unchanged by the stream
    assert (snap["viol_rest"], snap["viol_ws"], snap["viol_common"]) == (0, 1, 1)
    assert snap["ws_trades"] == 17


# --------------------------------------------------------------------- #
# The file, as it is while it is being written
# --------------------------------------------------------------------- #

def test_a_half_written_last_line_is_skipped_not_raised_on(tmp_path):
    p = _tape(tmp_path, [_sample(CLEAN, "23:40:07"), _sample(CROSSED, "23:40:27")])
    torn = json.dumps(_sample(CLEAN, "23:40:47"))[:120]        # writer caught mid-write
    assert not torn.endswith("}")
    with open(p, "a", encoding="utf-8") as f:
        f.write(torn)
    assert tape.last_line(str(p))["t"] == "23:40:27"
    assert [s["t"] for s in tape.samples(str(p), 5)] == ["23:40:07", "23:40:27"]
    snap = tape.latest(str(tmp_path))
    assert snap["t"] == "23:40:27" and len(snap["violations"]) == 2


def test_a_tape_longer_than_the_tail_window_still_reads_from_the_end(tmp_path, monkeypatch):
    """A 20 s cycle over four hours is ~720 samples of a 12-rung ladder, which
    outgrows one tail read. The window has to GROW until it holds the history
    asked for, and the newest sample has to stay the newest.

    The window is shrunk here rather than the file inflated to megabytes: the
    branch under test is the growth loop, not the size of the constant.
    """
    monkeypatch.setattr(tape, "_TAIL_BYTES", 2048)
    many = [_sample(CLEAN, f"23:{m:02d}:{s:02d}") for m in range(40, 60) for s in (7, 27, 47)]
    many.append(_sample(CROSSED, "23:59:59"))
    p = _tape(tmp_path, many)
    assert p.stat().st_size > 20 * 2048        # many windows' worth
    assert tape.last_line(str(p))["t"] == "23:59:59"
    got = tape.samples(str(p), 40)
    assert len(got) == 40 and got[-1]["t"] == "23:59:59"
    assert [s["t"] for s in got] == [s["t"] for s in many[-40:]]
    # More history than the file holds is the file, not an error.
    assert len(tape.samples(str(p), 5000)) == len(many)
    snap = tape.latest(str(tmp_path))
    assert snap["t"] == "23:59:59" and len(snap["violations"]) == 2
    assert len(snap["history"]) == 40


def test_a_tape_with_no_rows_is_a_sample_not_a_missing_tape(tmp_path):
    """The instrument writes a row before any rung has a two-sided book. That
    is a live tape with an empty ladder, and reporting it as "no tape" would
    say the instrument is not running when it is."""
    p = _tape(tmp_path, [{"t": "23:28:00", "took_s": 0.9, "rows": [], "viol_rest": 0,
                          "viol_ws": 0, "viol_common": 0, "ws_msgs": 2, "ws_trades": 0}])
    assert tape.last_line(str(p)) is not None
    snap = tape.latest(str(tmp_path))
    assert snap["rungs"] == [] and snap["violations"] == [] and snap["t"] == "23:28:00"
    page = ladder_tape_page.render(snap, tape.games(str(tmp_path)), None, str(tmp_path))
    assert "two-sided book" in page


def test_an_empty_or_unreadable_directory_reads_as_no_tape(tmp_path):
    assert tape.latest(str(tmp_path)) is None
    assert tape.games(str(tmp_path)) == []
    assert tape.tape_files(str(tmp_path)) == []
    assert tape.last_line(str(tmp_path / "nothing.jsonl")) is None
    assert tape.latest(str(tmp_path / "no-such-dir")) is None
    empty = tmp_path / f"ws_freshness_{GAME}.jsonl"
    empty.write_text("", encoding="utf-8")
    assert tape.latest(str(tmp_path)) is None


def test_game_of_reads_both_sports_and_matches_with_or_without_the_venue_head():
    assert tape.game_of(f"/out/ws_freshness_{GAME}.jsonl") == GAME
    assert tape.game_of("/out/ws_freshness_aec-cfb-mia-wake-2026-09-18.jsonl") == \
        "aec-cfb-mia-wake-2026-09-18"
    assert tape.game_of("/out/something-else.txt") == "something-else.txt"
    assert tape.same_game(GAME, "wnba-lv-sea-2026-09-18")
    assert not tape.same_game(GAME, "aec-cfb-mia-wake-2026-09-18")


def test_the_switcher_lists_every_game_and_picks_the_one_asked_for(tmp_path):
    _tape(tmp_path, [_sample(CLEAN)], GAME)
    _tape(tmp_path, [_sample(CROSSED)], "aec-cfb-mia-wake-2026-09-18")
    assert set(tape.games(str(tmp_path))) == {GAME, "aec-cfb-mia-wake-2026-09-18"}
    # Asked for the WNBA game, we get the WNBA game whichever was written last.
    snap = tape.latest(str(tmp_path), "wnba-lv-sea-2026-09-18")
    assert snap["game"] == GAME and snap["violations"] == []
    assert tape.latest(str(tmp_path), "aec-nba-not-playing-2026-09-18") is None
    page = ladder_tape_page.render(snap, tape.games(str(tmp_path)), GAME, str(tmp_path))
    assert "/ladder?game=aec-cfb-mia-wake-2026-09-18" in page
    assert "wnba-lv-sea-2026-09-18</a>" in page


def test_history_and_tape_age_come_from_the_file_not_from_the_sample(tmp_path):
    """A dead writer's last sample keeps its timestamp forever, so liveness is
    the file's mtime and the page must warn on that, not on `t`."""
    _tape(tmp_path, [_sample(CLEAN, "23:40:07", ws_trades=3),
                     _sample(CROSSED, "23:40:27", ws_trades=9)])
    snap = tape.latest(str(tmp_path))
    assert [h["t"] for h in snap["history"]] == ["23:40:07", "23:40:27"]
    assert snap["trades_delta"] == 6
    assert snap["tape_age_s"] is not None and snap["tape_age_s"] < 60


# --------------------------------------------------------------------- #
# The page
# --------------------------------------------------------------------- #

def test_the_page_draws_the_rungs_the_pairs_and_the_stream_counts(tmp_path):
    _tape(tmp_path, [_sample(CROSSED, viol_rest=VIOL_REST, viol_ws=1, viol_common=1,
                             ws_trades=17, ws_msgs=204)])
    snap = tape.latest(str(tmp_path))
    page = ladder_tape_page.render(snap, tape.games(str(tmp_path)), GAME, str(tmp_path))
    assert "+4.5" in page and "-10.5" in page and "winner" in page
    assert "0.300" in page and "0.460" in page                  # the touch, to the tick
    assert "ask &ge; 0.460" in page                             # the bound, per rung
    assert "$106.00" in page and "$33.78" in page and "+13.25&cent;" in page
    assert "ticket it" in page and "winner leg" in page
    # The winner market is line 0 and must never print as a rung number.
    assert "+4.5 / winner" in page and "+0" not in page
    # A bound the fees eat is not a bound the scanner would trade.
    assert "crossed, fees eat it" in page and "broken" in page
    # H1: what the stream saw against what REST saw, and the prints.
    for n in ("17", "204", "1"):
        assert f">{n}<" in page or f">{n} " in page
    assert "trade prints seen" in page and "violations in the venue&#x27;s own stream" in page
    assert "money" in page and "href='/pnl'" in page            # the P&L page owns the money
    assert "location.reload()" in page                          # it refreshes itself


def test_the_page_says_where_it_looked_when_there_is_no_tape(tmp_path):
    """An empty page that does not name its directory reads as "nothing
    happened" when it means "wrong directory"."""
    page = ladder_tape_page.render(None, [], None, str(tmp_path))
    assert "No freshness tape yet" in page and str(tmp_path) in page
    assert "WNBA" in page and "location.reload()" in page


def test_one_game_missing_its_tape_is_not_reported_as_the_instrument_being_down(tmp_path):
    """Five games sampling and one not is a different state from nothing
    running, and the switcher must still be there to get out of it."""
    page = ladder_tape_page.render(None, [GAME, "aec-cfb-mia-wake-2026-09-18"],
                                   "aec-wnba-min-phx-2026-09-18", str(tmp_path))
    assert "No freshness tape yet for" in page and "aec-wnba-min-phx-2026-09-18" in page
    assert "2 other game(s) are sampling" in page
    assert "/ladder?game=aec-cfb-mia-wake-2026-09-18" in page


@pytest.mark.parametrize("name", ["core/ladder/tape.py", "cfb/ladder_tape_page.py"])
def test_neither_new_module_can_reach_the_venue_or_an_order_path(name):
    """The same ban tests/test_ladder_desk.py puts on the desk: this page is
    part of the desk, so it carries the desk's rule."""
    src = (pathlib.Path(__file__).resolve().parents[1] / name).read_text(encoding="utf-8")
    for bad in ("PolymarketGatewayClient", "PolymarketOrderClient", "place_order", "create_order",
                "/orders", "httpx", "MERIDIAN_ORDER_TOKEN", "api.polymarket"):
        assert bad not in src, f"{name} names {bad}"
