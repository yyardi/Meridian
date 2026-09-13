"""The paper book's own JSON, and the endpoint that serves it verbatim.

This replaces 198 lines of fixed-width regex and 262 lines of tests for them.
What is worth testing is now smaller and different: the producer emits exactly
the keys static/scoreboard.html reads, and the endpoint adds nothing.

Every field list here is DERIVED FROM THE PAGE, never written out by hand — a
hand-kept list drifts silently, which is the failure the regex parser had.

    pytest --noconftest tests/test_paper_book_json.py
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

from cfb.run_paper_book import _ci, _wk, dump_json, verdict_kind

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = (ROOT / "static" / "scoreboard.html").read_text(encoding="utf-8")
TOP = set(re.findall(r"BOOK\.([a-z_]+)", PAGE)) - {"note"}   # note: available:false only
ST = {"league": "mlb"}


# the page filters BOTH row lists on `r.league` in render(), outside either
# table function, so a per-function scrape alone would miss the one field that
# decides which league tab a row appears under
FILTERED = set(re.findall(r"rows\.filter\(r => r\.([a-z_]+)", PAGE))


def _fields(func):
    """The `r.<field>` columns one render function prints, plus what render filters on."""
    body = PAGE[PAGE.index(f"function {func}("):]
    return set(re.findall(r"\br\.([a-z_]+)", body[:body.index("\n}")])) | FILTERED


def _doc(tmp_path, **kw):
    p = tmp_path / "paper_book_2026-09-13T1040Z.json"
    dump_json(kw.get("preamble", ["mlb: 12 markets"]),
              kw.get("weekly", [_wk("mlb_a", ST, week="2026-09-07", bets=3, games=3,
                                    unsettled=1, staked=2, pnl=0.5, net_per_dollar=0.25,
                                    ci=_ci(1.0, 0.5), underpowered=True)]),
              kw.get("all_weeks", [{"strategy": "mlb_a", "league": "mlb", "bets": 3,
                                    "games": 3, "staked": 2, "pnl": 0.5,
                                    "net_per_dollar": 0.25, "ci": _ci(1.0, 0.5),
                                    "verdict": "spans 0", "verdict_kind": "spans"}]),
              kw.get("footer", ["nothing here is sized or armed"]), str(p))
    return json.loads(p.read_text(encoding="utf-8")), p


def test_the_document_and_the_page_agree_on_every_top_level_key(tmp_path):
    doc, _ = _doc(tmp_path)
    assert TOP and not TOP - set(doc), f"page reads {TOP - set(doc)}, producer omits it"


@pytest.mark.parametrize("table, key", [("weekTable", "weekly"), ("allTable", "all_weeks")])
def test_every_column_a_table_renders_exists_on_its_rows(tmp_path, table, key):
    doc, _ = _doc(tmp_path)
    want = _fields(table)
    assert want, f"could not read {table}'s columns off the page"
    assert not want - set(doc[key]["rows"][0]), f"{table} reads {want - set(doc[key]['rows'][0])}"


def test_unparsed_is_present_and_empty(tmp_path):
    """The page renders it as 'lines the parser did not recognise' and calls
    `.length` on it. A producer emitting its own rows has none by construction,
    but the key must exist or the page throws."""
    assert _doc(tmp_path)[0]["unparsed"] == []


def test_no_pb_json_writes_nothing(monkeypatch):
    monkeypatch.delenv("PB_JSON", raising=False)
    assert dump_json([], [], [], []) is None


def test_the_path_comes_from_the_environment_when_not_passed(tmp_path, monkeypatch):
    p = tmp_path / "deep" / "paper_book_env.json"
    monkeypatch.setenv("PB_JSON", str(p))
    assert dump_json([], [], [], []) == str(p)
    assert json.loads(p.read_text(encoding="utf-8"))["available"] is True


def test_the_write_is_atomic_and_leaves_no_debris(tmp_path):
    _doc(tmp_path); _doc(tmp_path)
    assert [f.name for f in tmp_path.iterdir()] == ["paper_book_2026-09-13T1040Z.json"]


def test_file_names_the_json_not_the_txt(tmp_path):
    """The page prints BOOK.file as the source; naming the txt would point an
    operator at a file these numbers did not come from."""
    doc, p = _doc(tmp_path)
    assert doc["file"] == p.name and doc["file"].endswith(".json")


@pytest.mark.parametrize("v, kind", [
    ("POSITIVE, excludes 0", "positive"), ("NEGATIVE, excludes 0", "negative"),
    ("UNDERPOWERED (G<25)", "underpowered"), ("spans 0", "spans"),
    ("something new", "unknown")])
def test_verdict_kind_covers_the_producers_own_strings(v, kind):
    assert verdict_kind(v) == kind


def test_every_verdict_the_producer_can_emit_has_a_class():
    """Read off the producer's one verdict expression: an 'unknown' kind
    renders unstyled, which is silent."""
    src = (ROOT / "cfb" / "run_paper_book.py").read_text(encoding="utf-8")
    line = next(l for l in src.splitlines() if "UNDERPOWERED (G<25)" in l and "v =" in l)
    for v in re.findall(r'"([^"]+)"', line):
        assert verdict_kind(v) != "unknown", f"verdict {v!r} would render unstyled"


def test_a_no_markets_row_is_a_note_not_a_row_of_zeros(tmp_path):
    r = _doc(tmp_path, weekly=[_wk("mlb_b", ST, note="no markets on tape")])[0]["weekly"]["rows"][0]
    assert r["note"] == "no markets on tape" and r["week"] is None and r["ci"] is None


def test_ci_is_the_string_the_table_prints():
    assert _ci(1.0, 0.5) == "+1.00 [+0.50, +1.50]"
    assert _ci(-2.0, 0.25) == "-2.00 [-2.25, -1.75]"


def test_the_old_regex_parser_is_gone():
    api = (ROOT / "core" / "api.py").read_text(encoding="utf-8")
    assert not (ROOT / "core" / "paper_book.py").exists()
    assert not (ROOT / "tests" / "test_paper_book.py").exists()
    assert "core.paper_book" not in api and "parse_paper_book" not in api
