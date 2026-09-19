"""Episode reconstruction from a recorded tape, on a hand-built book file.

The fixture is a three-rung ladder that is monotone (so it must produce
nothing), then has its +4.5 rung re-quoted DOWN -- easier to cover and yet
cheaper than the winner, which cannot both be true -- then has the winner's
bid lifted while +4.5 stays stale, then has +4.5 re-quoted back.

Every expected number below was worked out from the prices with
fee = 0.06 p (1-p) charged at BOTH legs and written down, not read off the
code. A test that recomputes the thing it is testing checks nothing.

    t3  buy +4.5 @ 0.36, sell 0.0 @ 0.48
        0.12 - 0.06(.36)(.64) - 0.06(.48)(.52) = 0.12 - 0.013824 - 0.014976
                                               = 0.091200  x min(1000,900)=900 -> $82.08
    t3  buy +4.5 @ 0.36, sell -4.5 @ 0.40
        0.04 - 0.013824 - 0.06(.40)(.60)       = 0.011776  x min(1000,300)=300 -> $3.5328
    t5  buy +4.5 @ 0.36, sell 0.0 @ 0.50
        0.14 - 0.013824 - 0.06(.50)(.50)       = 0.111176  x min(1000,900)=900 -> $100.0584

so two episodes, both opening at t3 and closing at t5, and the (0.0,+4.5) one
peaking at t5 rather than where it opened -- which is why an episode carries a
best instant rather than its first one.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core.ladder import scan, stream_scan  # noqa: E402

GAME = "cfb-mia-wake-2026-09-18"
DAY = "2026-09-19T00:00:"


def at(second: float) -> str:
    return f"{DAY}{second:06.3f}+00:00"


def row(recv: str, line: float, bid, ask, bsz, asz) -> str:
    return json.dumps({"recv": recv, "slug": f"asc-{GAME}", "line": line, "bid": bid, "ask": ask,
                       "bid_size": bsz, "ask_size": asz, "tt": None, "state": "MARKET_STATE_OPEN"})


#: The monotone ladder: YES price non-decreasing in the line number.
CLEAN = [(-4.5, 0.40, 0.42, 300, 300), (0.0, 0.48, 0.50, 900, 900), (4.5, 0.56, 0.58, 200, 800)]

TAPE = [
    row(at(0.0), *CLEAN[0]),
    row(at(0.5), *CLEAN[1]),
    row(at(1.0), *CLEAN[2]),
    "{not json at all",                                   # a torn line mid-tape
    row(at(10.0), 4.5, 0.34, 0.36, 200, 1000),            # +4.5 re-quoted down: the violation
    row(at(20.0), 4.5, 0.34, 0.36, 200, 1000),            # identical: no rung moved
    row(at(30.0), 0.0, 0.50, 0.52, 900, 900),             # the winner lifts, +4.5 stays stale
    row(at(40.0), *CLEAN[2]),                             # +4.5 back: the episodes close
]


def write(tmp_path, lines, game: str = GAME) -> str:
    p = tmp_path / f"slate_books_{game}.jsonl"
    p.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return str(p)


def test_a_violation_that_appears_and_disappears_is_one_episode_per_pair(tmp_path):
    eps, _ = stream_scan.episodes_in_book_file(write(tmp_path, TAPE))
    assert [e.pair for e in eps] == [(-4.5, 4.5), (0.0, 4.5)]
    big = next(e for e in eps if e.pair == (0.0, 4.5))
    assert big.start == at(10.0) and big.end == at(30.0), "opens on the update, closes on the last one"
    assert big.duration_s == 20.0 and big.updates == 2
    assert abs(big.best_edge - 0.111176) < 1e-12 and abs(big.best_dollars - 100.0584) < 1e-9
    assert (big.best_buy, big.best_sell, big.best_size) == (0.36, 0.50, 900.0)
    assert big.spread_pair is False, "the winner market is a leg: not a spread pair"
    assert big.mid is False
    small = next(e for e in eps if e.pair == (-4.5, 4.5))
    assert abs(small.best_edge - 0.011776) < 1e-12 and abs(small.best_dollars - 3.5328) < 1e-9
    assert small.spread_pair is True and small.mid is True, "both legs inside the mid ladder"
    assert small.duration_s == 20.0 and small.updates == 2


def test_the_totals_name_the_population_every_number_is_about(tmp_path):
    _, t = stream_scan.episodes_in_book_file(write(tmp_path, TAPE))
    assert t["game"] == GAME and t["readable"] is True
    assert t["rows"] == 8 and t["parsed"] == 7, "the torn line is read and skipped"
    assert t["scans"] == 6 and t["unchanged"] == 1, "the repeated quote runs no scan"
    assert t["scans_with_violation"] == 2 and t["rungs"] == 3 and t["one_sided"] == 0
    assert t["episodes"] == 2 and t["episodes_ge_10"] == 1 and t["episodes_ge_100"] == 1
    assert abs(t["sum_best_usd"] - 103.5912) < 1e-9 and t["max_best_usd"] == 100.0584
    assert t["first_recv"] == at(0.0) and t["last_recv"] == at(40.0)
    assert t["fee_rate"] == scan.DEFAULT_FEE_RATE and t["max_size"] == scan.MAX_PLAUSIBLE_SIZE


def test_an_unchanged_update_cannot_re_count_the_instant_it_repeats(tmp_path):
    """Two identical quotes of +4.5 are ONE instant of disorder. Scanning both
    would inflate every "fraction of instants with a violation" by however
    often the venue repeats itself."""
    doubled = TAPE[:6] + [TAPE[5], TAPE[5]] + TAPE[6:]
    eps, t = stream_scan.episodes_in_book_file(write(tmp_path, doubled))
    assert t["scans"] == 6 and t["unchanged"] == 3
    assert [e.updates for e in eps] == [2, 2], "the repeats join no episode"


def test_the_size_cap_is_part_of_the_answer_not_a_detail(tmp_path):
    """0bv's $4,047 was computed with the cap OFF. A number from one cap
    compared against a number from another is a comparison of two things, so
    the cap rides on the totals and changing it changes the dollars."""
    _, capped = stream_scan.episodes_in_book_file(write(tmp_path, TAPE), max_size=100.0)
    assert capped["max_size"] == 100.0
    assert abs(capped["max_best_usd"] - 11.1176) < 1e-9, "0.111176 x 100, not x 900"


def test_a_rung_that_only_ever_has_one_side_never_enters_the_ladder(tmp_path):
    """-10.5 bids 0.60 -- above the winner's own ask, so as a SELL leg it
    would violate against everything above it. Its ask never arrives, so it
    has no price on the side the other half of a pair needs, and it is
    excluded. The control is that including it is not inert."""
    tape = [row(at(0.0), *CLEAN[0]), row(at(0.5), *CLEAN[1]), row(at(1.0), *CLEAN[2])]
    tape += [row(at(2.0 + i), -10.5, 0.60, None, 500, None) for i in range(3)]
    eps, t = stream_scan.episodes_in_book_file(write(tmp_path, tape))
    assert eps == [] and t["episodes"] == 0
    assert t["one_sided"] == 3 and t["rungs"] == 3, "the three real rungs, not four"
    assert t["scans"] == 3, "the first one-sided row changes nothing; the next two are unchanged"
    complete = {line: (b, a, bs, asz) for line, b, a, bs, asz in CLEAN}
    would_be = scan.scan_ladder(GAME, {**complete, -10.5: (0.60, 0.62, 500, 500)})
    #   sell -10.5 @ 0.60, buy 0.0 @ 0.50:  0.10 - 0.015 - 0.0144 = 0.0706 -> a violation
    #   sell -10.5 @ 0.60, buy +4.5 @ 0.58: 0.02 - 0.014616 - 0.0144 < 0   -> the fees eat it
    assert [(v.low_line, v.high_line) for v in would_be] == [(-10.5, 0.0)], (
        "with both sides that rung violates, so excluding it is load-bearing, not inert")
    assert abs(would_be[0].edge - 0.0706) < 1e-12


def test_a_rung_that_loses_a_side_leaves_the_ladder_and_closes_its_episodes(tmp_path):
    """The venue pulling one side is not the same as the price staying put.
    An episode whose leg has no quote on the side it needs is over."""
    tape = TAPE[:6] + [row(at(30.0), 4.5, 0.34, None, 200, None)]
    eps, t = stream_scan.episodes_in_book_file(write(tmp_path, tape))
    assert len(eps) == 2 and {e.end for e in eps} == {at(10.0)}, "closed at the last two-sided scan"
    assert all(e.duration_s == 0.0 and e.updates == 1 for e in eps)
    assert t["rungs"] == 2 and t["one_sided"] == 1


def test_an_episode_still_open_at_the_end_of_the_tape_is_still_an_episode(tmp_path):
    """The recorder stops when the operator's clock says so, not when the
    venue tidies its book. Dropping the open ones would delete exactly the
    episodes that were running at the whistle."""
    eps, t = stream_scan.episodes_in_book_file(write(tmp_path, TAPE[:-1]))
    assert len(eps) == 2 and {e.end for e in eps} == {at(30.0)}
    assert t["scans"] == 5 and t["episodes"] == 2


def test_an_empty_file_is_zero_episodes_and_not_a_crash(tmp_path):
    eps, t = stream_scan.episodes_in_book_file(write(tmp_path, []))
    assert eps == []
    assert t["rows"] == 0 and t["parsed"] == 0 and t["scans"] == 0 and t["episodes"] == 0
    assert t["sum_best_usd"] == 0.0 and t["max_best_usd"] == 0.0
    assert t["first_recv"] is None and t["last_recv"] is None
    assert t["readable"] is True, "an empty tape is a game that was quiet, not a missing file"


def test_a_missing_file_says_so_rather_than_reporting_a_quiet_game(tmp_path):
    _, t = stream_scan.episodes_in_book_file(str(tmp_path / "slate_books_nothing.jsonl"))
    assert t["readable"] is False and t["rows"] == 0


def test_a_slate_is_scanned_one_game_at_a_time(tmp_path):
    """Merging games would let a rung of one pair against a rung of another,
    which is not an arbitrage, it is a model."""
    write(tmp_path, TAPE)
    write(tmp_path, TAPE, game="cfb-hou-ttu-2026-09-18")
    eps, totals = stream_scan.scan_slate(str(tmp_path))
    assert len(totals) == 2 and {t["game"] for t in totals} == {GAME, "cfb-hou-ttu-2026-09-18"}
    assert len(eps) == 4 and {e.game for e in eps} == {GAME, "cfb-hou-ttu-2026-09-18"}
    s = stream_scan.slate_summary(totals)
    assert s["games"] == 2 and s["games_with_an_episode"] == 2 and s["episodes"] == 4
    assert abs(s["sum_best_usd"] - 207.18) < 0.01 and s["episodes_ge_100"] == 2
    assert s["max_size"] == scan.MAX_PLAUSIBLE_SIZE, "the population rides on the slate row too"


def test_the_game_name_comes_off_the_filename_the_recorder_wrote():
    assert stream_scan.game_of(f"/out/slate_books_{GAME}.jsonl") == GAME
    assert stream_scan.game_of("/out/something_else.jsonl") == "something_else.jsonl"


def test_episode_rows_are_plain_json(tmp_path):
    eps, _ = stream_scan.episodes_in_book_file(write(tmp_path, TAPE))
    rows = stream_scan.episode_rows(eps)
    assert json.loads(json.dumps(rows))[0]["game"] == GAME
    assert "best_dollars" in rows[0] and "duration_s" in rows[0]


def test_the_recorder_writes_the_file_the_scanner_reads(tmp_path):
    """The one thing neither half can check alone.

    Every test above hand-builds a book file and every test in
    `test_stream_recorder.py` reads the recorder's own output, so a renamed
    field would leave both green and the slate unreadable. This drives real
    MARKET_DATA messages through the recorder's handler and then runs the
    scanner over what landed on disk -- no hand-built row anywhere in it.
    """
    from core.ladder import stream

    def md(slug, bid, ask, bsz, asz):
        return {"marketData": {"marketSlug": slug, "transactTime": "2026-09-19T00:00:00Z",
                               "state": "MARKET_STATE_OPEN",
                               "bids": [{"px": {"value": str(bid)}, "qty": str(bsz)}],
                               "offers": [{"px": {"value": str(ask)}, "qty": str(asz)}]}}

    sink = stream.SlateSink(str(tmp_path))
    conn = stream.StreamConnection("c0", [[]], sink, open_socket=lambda: None)
    for slug, (bid, ask, bsz, asz) in (
            (f"asc-{GAME}-neg-4pt5", (0.40, 0.42, 300, 300)),
            (f"aec-{GAME}", (0.48, 0.50, 900, 900)),
            (f"asc-{GAME}-pos-4pt5", (0.56, 0.58, 200, 800))):
        conn.handle(md(slug, bid, ask, bsz, asz))
    eps, _ = stream_scan.scan_slate(str(tmp_path))
    assert eps == [], "the monotone ladder the recorder just wrote violates nothing"
    conn.handle(md(f"asc-{GAME}-pos-4pt5", 0.34, 0.36, 200, 1000))
    sink.close()
    eps, totals = stream_scan.scan_slate(str(tmp_path))
    assert [e.pair for e in eps] == [(-4.5, 4.5), (0.0, 4.5)]
    assert abs(next(e for e in eps if e.pair == (0.0, 4.5)).best_dollars - 82.08) < 1e-9
    assert totals[0]["game"] == GAME and totals[0]["scans"] == 4 and totals[0]["one_sided"] == 0
