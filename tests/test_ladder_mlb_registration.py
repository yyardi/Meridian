"""The MLB strategies registered 2026-09-14, and the property every pair must have.

MLB had exactly one settled game when these were written, so no outcome could
have chosen them. What a test can still check is the thing that has gone wrong
every time a price bucket produced a headline in this project: that a strategy
and its mirror are actually mirrors, and that the pair is declared so the paper
book prints them together.
"""
from __future__ import annotations

import itertools

from strategies.ladder import COMPLEMENTS, STRATEGIES, select

NEW = ("mlb_winner_away_all", "mlb_winner_home_all",
       "mlb_spread_yes_70_100", "mlb_spread_no_00_30",
       "mlb_f5_spread_yes_40_60", "mlb_f5_spread_no_40_60")


def _rows():
    """A synthetic MLB board spanning the whole price range, both market types."""
    out = []
    for i, mid in enumerate([x / 100 for x in range(5, 100, 5)]):
        for mtype in ("baseball_team_full_game_winner", "baseball_team_full_game_spread",
                      "baseball_team_first_five_spread", "baseball_team_full_game_total",
                      "baseball_team_first_five_total"):
            out.append({"market_slug": f"m{i}-{mtype}", "game_id": f"g{i}",
                        "league": "mlb", "mtype": mtype,
                        "bid": round(mid - 0.005, 4), "ask": round(mid + 0.005, 4)})
    return out


def test_every_new_strategy_is_registered_and_picks_something():
    picks = select(_rows())
    for name in NEW:
        assert name in STRATEGIES, f"{name} not registered"
        assert picks[name], f"{name} selected nothing on a board spanning 0.05-0.95"


def test_the_declared_complements_select_identical_rows():
    """A complement pair must be the SAME rows on opposite sides -- that is what
    makes their P&Ls sum to minus the round trip, and what makes one beating the
    other arithmetic rather than evidence. A pair that selects different rows is
    two strategies wearing one label."""
    picks = select(_rows())
    for a, b in COMPLEMENTS.items():
        if not (a.startswith("mlb") and b.startswith("mlb")):
            continue
        if a not in picks or b not in picks:
            continue
        # NOT a `continue` on empty. The first version of this test compared two
        # EMPTY sets, because the fixture carried no totals rows, and
        # `set() != set()` is False -- so the side assertion failed for a reason
        # that had nothing to do with the sides. An empty pair means the fixture
        # does not exercise the pair, which is a hole in the test, not a pass.
        assert picks[a] or picks[b], f"the fixture selects nothing for {a}/{b}"
        assert {p.market_slug for p in picks[a]} == {p.market_slug for p in picks[b]}, \
            f"{a} and {b} are declared complements but select different rows"
        assert {p.side for p in picks[a]} != {p.side for p in picks[b]}, \
            f"{a} and {b} are declared complements but take the same side"


def test_the_two_spread_arms_are_disjoint_and_are_not_complements():
    """`mlb_spread_yes_70_100` backs the away favourite and `mlb_spread_no_00_30`
    the home favourite. They are the home/away split of one bet, NOT complements:
    they select different rows, so both can be positive or both negative without
    any arithmetic forcing it. Declaring them as complements would be wrong and
    would suppress exactly the comparison they exist for."""
    picks = select(_rows())
    away = {p.market_slug for p in picks["mlb_spread_yes_70_100"]}
    home = {p.market_slug for p in picks["mlb_spread_no_00_30"]}
    assert away and home
    assert not (away & home), "the two arms must not share a row"
    assert COMPLEMENTS.get("mlb_spread_no_00_30") != "mlb_spread_yes_70_100"
    assert COMPLEMENTS.get("mlb_spread_yes_70_100") != "mlb_spread_no_00_30"


def test_no_two_strategies_share_a_name_and_a_rule():
    """Changing a registered rule must be a NEW name, per the module docstring.
    This catches the copy-paste that silently redefines an accruing strategy."""
    seen = {}
    for name, st in STRATEGIES.items():
        key = (st["league"], st["types"], st["side"])
        seen.setdefault(key, []).append(name)
    for key, names in seen.items():
        if len(names) < 2:
            continue
        rows = _rows() if key[0] == "mlb" else []
        if not rows:
            continue
        picks = select(rows)
        for a, b in itertools.combinations(names, 2):
            if {p.market_slug for p in picks[a]} == {p.market_slug for p in picks[b]}:
                assert COMPLEMENTS.get(a) == b or COMPLEMENTS.get(b) == a, \
                    f"{a} and {b} select identical rows on the same side and are not declared a pair"
