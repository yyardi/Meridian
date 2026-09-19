"""The game log: every opportunity a night produced, and what we did with it.

    pytest --noconftest tests/test_gamelog.py

The ticket list on /arb is a to-do list and hides what no longer clears, so
nothing else on the dashboard answers "what did this game actually offer?".
That question is the point of the page, and the row that answers it best is
the episode with NO ticket against it: an opportunity the system saw and
nobody took.
"""
from __future__ import annotations

import importlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core.ladder import gamelog, gamelog_page  # noqa: E402

GAME = "aec-cfb-tsta-tstb-2026-09-19"
SRC = pathlib.Path(gamelog.__file__).read_text(encoding="utf-8")


def _rung(bid, ask, bsz=500.0, asz=500.0, tt=None):
    return {"bid": bid, "ask": ask, "bsz": bsz, "asz": asz, "tt": tt}


def _sample(t, rungs):
    """A freshness-tape line: {t, rows:[{line, rest:{...}}]}."""
    return {"t": t, "took_s": 3.3,
            "rows": [{"line": ln, "rest": _rung(*v)} for ln, v in rungs.items()]}


def _tape(tmp_path, samples, game=GAME):
    p = tmp_path / f"ws_freshness_{game}.jsonl"
    p.write_text("\n".join(json.dumps(s) for s in samples) + "\n", encoding="utf-8")
    return str(p)


#: A clean ladder: every ask at or above the harder rung's bid.
CLEAN = {3.5: (0.40, 0.42), 5.5: (0.44, 0.46), 7.5: (0.50, 0.52)}
#: +7.5 offered at 0.41, below +5.5's bid of 0.44 -- a crossed pair.
CROSSED = {3.5: (0.40, 0.42), 5.5: (0.44, 0.46), 7.5: (0.41, 0.41)}


def test_a_pair_that_clears_across_consecutive_samples_is_one_episode(tmp_path):
    path = _tape(tmp_path, [_sample("01:00:00", CROSSED),
                            _sample("01:00:20", CROSSED),
                            _sample("01:00:40", CROSSED)])
    eps, totals = gamelog.episodes_in_tape(path)
    assert len(eps) == 1, "three samples of the same crossing is ONE opportunity"
    e = eps[0]
    assert e.samples == 3 and e.start == "01:00:00" and e.end == "01:00:40"
    assert (e.low_line, e.high_line) == (5.5, 7.5)
    assert e.best_dollars > 0 and e.best_edge_c > 0
    assert totals["samples"] == 3


def test_a_gap_starts_a_new_episode(tmp_path):
    """It cleared, it stopped, it cleared again. Two chances, not one: the
    second one needed a second decision."""
    path = _tape(tmp_path, [_sample("01:00:00", CROSSED),
                            _sample("01:00:20", CLEAN),
                            _sample("01:00:40", CROSSED)])
    eps, _ = gamelog.episodes_in_tape(path)
    assert len(eps) == 2
    assert [e.samples for e in eps] == [1, 1]


def test_two_pairs_crossing_together_are_independent_episodes(tmp_path):
    both = {3.5: (0.40, 0.42), 5.5: (0.44, 0.35), 7.5: (0.41, 0.41)}
    path = _tape(tmp_path, [_sample("01:00:00", both)])
    eps, _ = gamelog.episodes_in_tape(path)
    pairs = {e.pair for e in eps}
    assert len(eps) >= 2 and len(pairs) == len(eps), "one episode per pair, not per sample"


def test_an_empty_tape_and_a_missing_directory_are_not_errors(tmp_path):
    path = _tape(tmp_path, [_sample("01:00:00", CLEAN)])
    eps, totals = gamelog.episodes_in_tape(path)
    assert eps == [] and totals["samples"] == 1
    assert gamelog.game_log(str(tmp_path / "nope")) is None, "no tape is None, not an empty log"
    assert gamelog.game_log(str(tmp_path), game="aec-cfb-not-a-game-2026-09-19") is None


def test_the_log_marks_an_episode_nobody_ticketed(tmp_path):
    """The whole point of the page: an opportunity the system saw and nobody
    took must be visibly different from one that was ticketed."""
    path = _tape(tmp_path, [_sample("01:00:00", CROSSED), _sample("01:00:20", CROSSED)])
    log = gamelog.game_log(str(tmp_path), tickets=[])
    assert log is not None and log["episodes"], path
    row = log["episodes"][0]
    assert not row.get("tickets"), "no ticket was written for it"
    assert log["summary"]["episodes"] >= 1
    assert log["summary"]["ticketed"] == 0


def test_a_ticket_inside_the_window_is_matched_and_one_outside_is_not(tmp_path):
    path = _tape(tmp_path, [_sample("01:00:00", CROSSED), _sample("01:00:20", CROSSED)])
    inside = {"ts": "01:00:10", "game": "cfb-tsta-tstb-2026-09-19", "status": "open",
              "leg1": {"market_line": 7.5}, "leg2": {"market_line": 5.5},
              "edge_c": 1.5, "cost_usd": 0.96}
    outside = {**inside, "ts": "05:00:00"}
    log = gamelog.game_log(str(tmp_path), tickets=[inside, outside])
    row = log["episodes"][0]
    assert len(row["tickets"]) == 1, "the 05:00 ticket is the same pair in another window"
    assert row["tickets"][0]["ts"] == "01:00:10"
    assert log["summary"]["ticketed"] == 1


def test_the_summary_sums_best_per_episode_never_every_pair(tmp_path):
    """One mispriced rung crosses against every rung it pairs with and they
    share a leg; summing pairs overstated an earlier figure 2.5x."""
    body = SRC[SRC.index("def summarise("):]
    assert "best_dollars" in body
    assert "sum(" in body and "violations" not in body.split("return")[0], \
        "the total is over EPISODES, not over every violating pair"


def test_winner_leg_pairs_are_excluded(tmp_path):
    """The executor never tickets a winner leg -- an NFL tie settles it at
    $0.50 -- so counting one here would credit a chance it declined."""
    with_winner = {0.0: (0.90, 0.90), 5.5: (0.44, 0.46), 7.5: (0.41, 0.41)}
    path = _tape(tmp_path, [_sample("01:00:00", with_winner)])
    eps, _ = gamelog.episodes_in_tape(path)
    assert all(e.spread_pair for e in eps), "no episode may carry line 0"
    assert all(0.0 not in e.pair for e in eps)


def test_the_page_renders_with_no_files_and_with_a_game_that_has_no_tickets(tmp_path):
    empty = gamelog_page.render(None, {"games": []}, [], str(tmp_path))
    assert "<" in empty and "tape" in empty.lower()
    _tape(tmp_path, [_sample("01:00:00", CROSSED), _sample("01:00:20", CROSSED)])
    log = gamelog.game_log(str(tmp_path), tickets=[])
    page = gamelog_page.render(log, gamelog.slate_log(str(tmp_path), tickets=[]),
                               gamelog.__dict__.get("tape").games(str(tmp_path)), str(tmp_path))
    assert "7.5" in page and "5.5" in page, "the pair is on the page"
    assert "quoted" in page.lower(), "it says the dollars are quoted size, not fills"


def test_the_log_says_a_sample_is_20_seconds_and_does_not_pretend_otherwise():
    """An episode of one sample lasted somewhere between a moment and a
    cycle; the page must not imply it timed anything finer."""
    page_src = pathlib.Path(gamelog_page.__file__).read_text(encoding="utf-8")
    assert "sample" in page_src.lower()
    assert "CYCLE_S" in SRC, "the cycle length is named, not hard-coded at each use"
