"""The stream episode scanner: the instrument the ledger measures the edge
with, and the control that proves its gate can fail.

    pytest --noconftest tests/test_stream_episodes.py

The one thing this file must never let through is a scanner that reports
the same number whatever the data. So the first test is two crossings
that differ ONLY in how stale the older leg was, one second against a
hundred, and the gate has to separate them.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core.ladder import scan, stream_episodes as SE  # noqa: E402

GAME = "cfb-tsta-tstb-2026-09-19"
LO, HI = f"asc-{GAME}-pos-5pt5", f"asc-{GAME}-pos-7pt5"
T0 = dt.datetime(2026, 9, 19, 12, 0, 0, tzinfo=dt.timezone.utc)


def _line(sec, slug, bid, ask, bs=900.0, asz=900.0):
    return {"recv": (T0 + dt.timedelta(seconds=sec)).isoformat().replace("+00:00", "Z"),
            "slug": slug, "line": None, "bid": bid, "ask": ask,
            "bid_size": bs, "ask_size": asz, "tt": None, "state": "MARKET_STATE_OPEN"}


def _tape(tmp_path, rows, game=GAME):
    p = tmp_path / f"slate_books_{game}.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return str(p)


#: +5.5 bids 0.44; +7.5 offered at 0.41 is below it: crossed.
FRESH_THEN_STALE = [
    _line(0,   LO, 0.44, 0.46),
    _line(1,   HI, 0.38, 0.38),    # crossed, older leg 1 s old
    _line(20,  HI, 0.50, 0.52),    # clean again
    _line(40,  LO, 0.44, 0.46),
    _line(140, HI, 0.38, 0.38),    # crossed, older leg 100 s old
]


def test_the_gate_separates_a_fresh_crossing_from_a_stale_one(tmp_path):
    """The control. Same prices, same sizes, same pair; only the age of the
    older leg differs. A scanner that finds both at 2 s is not measuring
    freshness, and a scanner that finds neither is not measuring anything."""
    path = _tape(tmp_path, FRESH_THEN_STALE)
    tight = SE.scan_book_file(path, gate_s=2.0)
    loose = SE.scan_book_file(path, gate_s=300.0)
    assert len(tight.episodes) == 1, "only the 1-second crossing is fresh"
    assert len(loose.episodes) == 2, "both are crossings once the gate is loosened"
    assert tight.updates == loose.updates == 4, "an unchanged update is not a scan"


def test_the_arithmetic_is_scan_ladder_s_pair_for_pair(tmp_path):
    """Two copies of one formula is how a threshold stops meaning what it
    meant. On the same two rungs the episode's best edge must equal what
    the production scanner reports, and so must the size."""
    path = _tape(tmp_path, FRESH_THEN_STALE[:2])
    ep = SE.scan_book_file(path).episodes[0]
    rungs = {5.5: (0.44, 0.46, 900.0, 900.0), 7.5: (0.38, 0.38, 900.0, 900.0)}
    ref = scan.scan_ladder(GAME, rungs, max_size=1e12)[0]
    assert ep.pair == (ref.low_line, ref.high_line) == (5.5, 7.5)
    assert ep.best_edge == pytest.approx(ref.edge, abs=1e-12)
    assert ep.best_usd == pytest.approx(ref.dollars, abs=1e-9)


def test_an_episode_spans_consecutive_crossed_updates_and_keeps_its_best(tmp_path):
    # 0.38 and 0.37 clear the two fees against a 0.44 bid; 0.385 still does
    # (+0.57c); 0.415 would NOT (-0.4c) and would close the episode -- the
    # first draft of this test priced the third update there and blamed
    # the scanner for closing early. The scanner was right.
    rows = [_line(0, LO, 0.44, 0.46),
            _line(1, HI, 0.38, 0.38, asz=100.0),      # opens, size 100
            _line(2, HI, 0.37, 0.37, asz=500.0),      # still crossed, bigger
            _line(3, HI, 0.385, 0.385, asz=50.0),     # still crossed, smaller
            _line(9, HI, 0.60, 0.62)]                 # closes
    r = SE.scan_book_file(_tape(tmp_path, rows))
    assert len(r.episodes) == 1
    e = r.episodes[0]
    assert e.opened_at == pytest.approx(T0.timestamp() + 1) and e.closed_at == pytest.approx(T0.timestamp() + 3)
    assert e.duration_s == 2.0
    best = scan.scan_ladder(GAME, {5.5: (0.44, 0.46, 900.0, 900.0), 7.5: (0.37, 0.37, 900.0, 500.0)},
                            max_size=1e12)[0]
    assert e.best_usd == pytest.approx(best.dollars), "the best instant, not the last and not the sum"


def test_a_one_update_crossing_has_duration_zero_and_is_counted_as_such(tmp_path):
    r = SE.scan_book_file(_tape(tmp_path, FRESH_THEN_STALE[:3]))
    assert [e.duration_s for e in r.episodes] == [0.0]
    s = SE.summarize([r])
    assert s["episodes"] == 1 and s["one_update"] == 1


def test_a_clean_ladder_yields_nothing_and_an_empty_file_is_not_an_error(tmp_path):
    clean = [_line(0, LO, 0.44, 0.46), _line(1, HI, 0.50, 0.52), _line(2, LO, 0.45, 0.47)]
    assert SE.scan_book_file(_tape(tmp_path, clean)).episodes == []
    empty = tmp_path / "slate_books_x-y-2026-09-19.jsonl"
    empty.write_text("", encoding="utf-8")
    r = SE.scan_book_file(str(empty))
    assert r.updates == 0 and r.episodes == [] and r.game == "x-y-2026-09-19"


def test_summarize_reports_the_ledger_s_fields(tmp_path):
    # 0.34 against a 0.44 bid is +7.2c net, x5000 = $359: over the floor and
    # under the plausibility cap. (0.20 would be +21.6c, which the cap
    # refuses as a bad reading; see the next test.)
    rows = [_line(0, LO, 0.44, 0.46), _line(1, HI, 0.34, 0.34, asz=5000.0),   # big, fresh, opens
            _line(2, HI, 0.35, 0.35, asz=5000.0),                             # still crossed
            _line(3, HI, 0.60, 0.62),                                         # closes
            _line(10, LO, 0.44, 0.46), _line(11, HI, 0.38, 0.38, asz=10.0)]   # tiny, fresh
    s = SE.summarize([SE.scan_book_file(_tape(tmp_path, rows))], floor_usd=25.0)
    assert s["episodes"] == 2 and s["over_floor"] == 1 and s["games_with_over_floor"] == 1
    assert s["biggest_usd"] > 25 and s["sum_over_floor_usd"] == s["biggest_usd"]
    assert s["median_life_over_floor_s"] == 1.0, "opened at +1, last seen crossed at +2"
    for k in ("games", "updates", "one_update", "sum_best_usd", "median_life_s", "floor_usd"):
        assert k in s, k


def test_scan_dir_reads_only_book_tapes(tmp_path):
    _tape(tmp_path, FRESH_THEN_STALE[:2])
    (tmp_path / "slate_trades_x.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "_recorder.log").write_text("x\n", encoding="utf-8")
    rs = SE.scan_dir(str(tmp_path))
    assert [r.game for r in rs] == [GAME]


def test_line_of_reads_the_slug_grammar():
    assert SE.line_of("aec-nfl-a-b-2026-09-20") == 0.0
    assert SE.line_of("asc-nfl-a-b-2026-09-20-neg-10pt5") == -10.5
    assert SE.line_of("asc-nfl-a-b-2026-09-20-pos-0pt5") == 0.5
    assert SE.line_of("tsc-nfl-a-b-2026-09-20-45pt5") is None, "a total is not a spread rung"


def test_a_quiet_leg_does_not_cut_a_persisting_crossing_short(tmp_path):
    """The gate applies when a crossing OPENS. Once open, an unchanged quote
    is still the venue's live book -- it does not re-push a level nobody
    touched -- so the episode runs until an update un-crosses it. The first
    draft re-applied the gate on every re-evaluation and closed this one
    at +1 s; the 'median 29 s' of 2026-09-19 was measured that way and is a
    floor on true persistence."""
    rows = [_line(0, LO, 0.44, 0.46),
            _line(1, HI, 0.38, 0.38),          # opens, older leg 1 s old
            _line(60, HI, 0.40, 0.40),         # still crossed, LO now 60 s quiet
            _line(70, HI, 0.60, 0.62)]         # un-crossed: closes
    r = SE.scan_book_file(_tape(tmp_path, rows), gate_s=2.0)
    assert len(r.episodes) == 1
    e = r.episodes[0]
    assert e.opened_at == pytest.approx(T0.timestamp() + 1)
    assert e.closed_at == pytest.approx(T0.timestamp() + 60)
    assert e.duration_s == 59.0
    assert e.opened_leg_age_s == 1.0, "the staler leg's age at the moment it opened"


def test_gate_none_opens_on_any_leg_age_and_records_it(tmp_path):
    r = SE.scan_book_file(_tape(tmp_path, FRESH_THEN_STALE), gate_s=None)
    assert [e.opened_leg_age_s for e in r.episodes] == [1.0, 100.0]
    r2 = SE.scan_book_file(_tape(tmp_path, FRESH_THEN_STALE), gate_s=2.0)
    assert [e.opened_leg_age_s for e in r2.episodes] == [1.0]


def test_an_implausible_edge_is_a_bad_reading_not_an_episode(tmp_path):
    """The production scanner refuses an edge above MAX_PLAUSIBLE_EDGE as a
    reading the substrate cannot support; so does this, with the same
    constant, or the two would count different populations."""
    rows = [_line(0, LO, 0.44, 0.46), _line(1, HI, 0.20, 0.20, asz=5000.0)]   # +21.6c net
    assert SE.scan_book_file(_tape(tmp_path, rows)).episodes == []
    assert scan.scan_ladder(GAME, {5.5: (0.44, 0.46, 900.0, 900.0), 7.5: (0.20, 0.20, 900.0, 5000.0)},
                            max_size=1e12) == []
    assert 0.216 > scan.MAX_PLAUSIBLE_EDGE


def test_it_reads_no_network_and_places_nothing():
    import ast
    src = pathlib.Path(SE.__file__).read_text(encoding="utf-8")
    names = {n.module or "" for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ImportFrom)}
    names |= {a.name for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Import) for a in n.names}
    assert not any(m.split(".")[0] in ("requests", "httpx", "websockets", "urllib") for m in names)
    assert "polymarket" not in " ".join(names).lower()
