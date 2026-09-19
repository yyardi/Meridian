"""The stream-driven detector: same arithmetic, fresher book, one ticket per
opportunity.

    pytest --noconftest tests/test_stream_executor.py

Measured on 2026-09-19, 48 college games, 697,492 stream updates. The REST
book the old executor polls ran a median 62 s behind the stream and was never
once ahead of it, so a 20-second poll of it cannot see a two-second-old
crossing. On the stream, with both legs required to have been quoted within
two seconds of each other, the slate held 3,615 distinct crossings, 62.9 % of
which lived for exactly one update. The EIGHT worth $25 or more lasted a
median 28.9 seconds. Those are what this is for.

What must hold: the pair arithmetic is `scan.scan_ladder`'s and not a second
implementation that drifts from it; the freshness gate reads the STALER leg;
and a crossing that stands for four minutes is one ticket.
"""
from __future__ import annotations

import importlib
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core.ladder import scan  # noqa: E402

SE = importlib.import_module("cfb.run_stream_executor")
SRC = pathlib.Path(SE.__file__).read_text(encoding="utf-8")
GAME = "cfb-tsta-tstb-2026-09-19"

#: line -> (bid, ask, bid_size, ask_size). +7.5 is offered at 0.41, below
#: +5.5's bid of 0.44: one crossed pair.
LADDER = {3.5: (0.40, 0.42, 500.0, 500.0),
          5.5: (0.44, 0.46, 500.0, 500.0),
          7.5: (0.41, 0.41, 900.0, 700.0)}


def _fresh(now=1000.0):
    return {k: now for k in LADDER}


def test_it_finds_exactly_what_scan_ladder_finds():
    """Two implementations of one formula is how a threshold stops meaning
    what it meant. Every pair the production scanner reports on this ladder
    must come back, with the same edge and the same size."""
    ref = {(v.low_line, v.high_line): v for v in scan.scan_ladder(GAME, LADDER, max_size=1e12)}
    got = {}
    for k in LADDER:
        for v in SE.crossings(k, LADDER, _fresh(), 1000.0, 2.0, GAME, scan.DEFAULT_FEE_RATE):
            got[(v.low_line, v.high_line)] = v
    assert set(got) == set(ref), (sorted(got), sorted(ref))
    for key, v in ref.items():
        assert got[key].edge == pytest.approx(v.edge, abs=1e-12)
        assert got[key].size == pytest.approx(v.size)
        assert got[key].buy_price == v.buy_price and got[key].sell_price == v.sell_price


def test_a_clean_ladder_yields_nothing():
    clean = {3.5: (0.40, 0.42, 500.0, 500.0), 5.5: (0.44, 0.46, 500.0, 500.0),
             7.5: (0.50, 0.52, 500.0, 500.0)}
    for k in clean:
        assert SE.crossings(k, clean, {j: 1000.0 for j in clean}, 1000.0, 2.0,
                            GAME, scan.DEFAULT_FEE_RATE) == []


def test_the_gate_reads_the_STALER_leg_and_drops_the_pair():
    """A pair is only as live as its older side. With +5.5 last quoted 30 s
    ago the pair is stale even though +7.5 arrived this instant."""
    seen = _fresh()
    seen[5.5] = 970.0
    assert SE.crossings(7.5, LADDER, seen, 1000.0, 2.0, GAME, scan.DEFAULT_FEE_RATE) == []
    wide = SE.crossings(7.5, LADDER, seen, 1000.0, 60.0, GAME, scan.DEFAULT_FEE_RATE)
    assert [(v.low_line, v.high_line) for v in wide] == [(5.5, 7.5)], \
        "the same pair is there; only the gate changed"


def test_it_checks_only_pairs_touching_the_rung_that_moved():
    """O(rungs), not O(rungs^2): the full rescan did not finish on one
    afternoon's tape."""
    got = SE.crossings(3.5, LADDER, _fresh(), 1000.0, 2.0, GAME, scan.DEFAULT_FEE_RATE)
    assert all(3.5 in (v.low_line, v.high_line) for v in got)
    assert not any((v.low_line, v.high_line) == (5.5, 7.5) for v in got), \
        "a pair neither of whose legs moved cannot have changed"


def test_one_ticket_per_episode_not_one_per_message():
    """A crossing that holds for four minutes is ONE opportunity. Writing it
    every update is what filled the desk with thirty identical rows."""
    body = SRC[SRC.index("for key, v in hits.items():"):]
    assert "if key in open_eps:" in body and "continue" in body
    assert "open_eps[key] = now" in body
    closing = SRC[SRC.index("for key in [k2 for k2 in open_eps"):]
    assert "k in k2" in closing and "open_eps.pop" in closing, \
        "an episode closes when the crossing stops, so the next one is new"


def test_it_makes_no_rest_call_and_can_place_nothing():
    """Not a promise in a docstring: the module imports nothing that can
    reach the venue, and the only thing it opens is the intents file."""
    import ast
    tree = ast.parse(SRC)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported |= {f"{node.module}.{a.name}" for a in node.names}
    assert not any("polymarket" in m.lower() or "gateway" in m.lower() for m in imported), imported
    assert not any(m.startswith(("requests", "httpx", "urllib")) for m in imported), imported
    calls = {ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert not any(c.endswith((".post", ".put", ".delete", ".send_order")) for c in calls), calls
    # and the stamp that says so rides on every ticket, from ONE place
    from cfb.run_ladder_executor import intent_for
    v = scan.scan_ladder(GAME, LADDER, max_size=1e12)[0]
    it = intent_for(v, GAME, "01:02:03", 1.0)
    assert it["meridian_placed"] is False and it["placed_by"] == "operator"
    assert '"placed_by"' not in SRC, "the stamp is intent_for's, not a second copy here"


def test_the_ticket_carries_its_freshness_and_its_source():
    """The desk shows the staler leg's book age; a stream ticket must fill
    the same fields the REST one does, plus say where it came from."""
    body = SRC[SRC.index("it[\"source\"]"):SRC.index("with open(out")]
    for field in ("source", "fresh_s", "leg1_book_age_s", "leg2_book_age_s"):
        assert field in body, field
    assert '"stream"' in body


def test_the_default_gate_is_where_the_measured_edge_is():
    assert '"--fresh-s", type=float, default=2.0' in SRC
    assert '"--floor-usd", type=float, default=25.0' in SRC
