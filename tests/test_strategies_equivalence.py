"""The consolidation is a pure refactor, and this is the check that can fail.

    pytest --noconftest tests/test_strategies_equivalence.py

`strategies/ladder.select` replaced an inline comprehension in
`cfb/run_paper_book.py`. The OLD comprehension is reproduced verbatim below as
the oracle -- not re-expressed, not rewritten in terms of the new code, because
an oracle derived from the thing it checks cannot disagree with it.

    rows = [r for r in rows_by_league.get(st["league"], [])
            if any(r["mtype"].endswith(t) for t in st["types"]) and st["rule"](r)]

The fixture is ~200 priced rows across cfb, nfl, wnba, mlb and cricket, built
to straddle every threshold in the registry (0.20/0.30/0.40/0.60/0.80) rather
than sampled at random, so a boundary that moved would be caught.
"""
from __future__ import annotations

from collections import defaultdict

import pytest

from strategies.base import Bet, price_of
from strategies.ladder import STRATEGIES, select

TYPES = {
    "cfb": ("football_team_full_game_spread", "football_team_full_game_total",
            "football_team_full_game_winner"),
    "nfl": ("football_team_full_game_spread", "football_team_full_game_winner"),
    "wnba": ("basketball_team_full_game_spread", "basketball_team_full_game_total"),
    "mlb": ("baseball_team_full_game_spread", "baseball_team_full_game_total",
            "baseball_team_first_five_total"),
    "cricket": ("cricket_match_winner",),
}
#: every threshold in the registry, each from just below, on, and just above
EDGES = [0.01, 0.19, 0.20, 0.21, 0.29, 0.30, 0.31, 0.39, 0.40, 0.41,
         0.50, 0.59, 0.60, 0.61, 0.79, 0.80, 0.81, 0.99]


def fixture_rows():
    rows = []
    for lg, types in TYPES.items():
        for t in types:
            for i, m in enumerate(EDGES):
                rows.append({
                    "market_slug": f"x-{lg}-{t[:6]}-{i}",
                    "mtype": t,
                    "game_id": f"{lg}-g{i % 4}",
                    "bid": round(m - 0.005, 4),
                    "ask": round(m + 0.005, 4),
                    "league": lg,
                })
    return rows


ROWS = fixture_rows()


def test_the_fixture_is_the_size_and_spread_it_claims():
    assert len(ROWS) == 198
    assert {r["league"] for r in ROWS} == set(TYPES)
    assert len({r["game_id"] for r in ROWS}) == 20


def _old_selection(rows):
    """THE ORIGINAL CODE. Do not refactor this; it is the oracle."""
    rows_by_league = defaultdict(list)
    for r in rows:
        rows_by_league[r["league"]].append(r)
    out = {}
    for name, st in STRATEGIES.items():
        out[name] = [
            r for r in rows_by_league.get(st["league"], [])
            if any(r["mtype"].endswith(t) for t in st["types"]) and st["rule"](r)
        ]
    return out


def _key(name, st, r):
    side = st["side"]
    stake = price_of(side, r["bid"], r["ask"])
    return (name, r["market_slug"], side, stake)


def test_the_chosen_set_is_identical_before_and_after():
    before = {_key(n, STRATEGIES[n], r) for n, rs in _old_selection(ROWS).items() for r in rs}
    after = {(n, b.market_slug, b.side, b.stake) for n, bs in select(ROWS).items() for b in bs}
    assert before == after
    assert before, "an empty comparison would pass whatever the code did"


def test_the_oracle_can_actually_disagree():
    """The control on the control. If the fixture cannot distinguish a changed
    rule, the test above proves nothing -- so break one rule and watch it."""
    broken = dict(STRATEGIES)
    name = "cfb_spread_no_20_30"
    broken[name] = dict(STRATEGIES[name], rule=lambda r: False)
    before = {_key(n, STRATEGIES[n], r) for n, rs in _old_selection(ROWS).items() for r in rs}
    after = {(n, b.market_slug, b.side, b.stake)
             for n, bs in select(ROWS, registry=broken).items() for b in bs}
    assert before != after
    assert {k for k in before if k[0] == name}, "the fixture must reach this strategy"


@pytest.mark.parametrize("name", sorted(STRATEGIES))
def test_every_registered_strategy_agrees_row_for_row(name):
    """Per strategy, so a failure names the one that moved."""
    st = STRATEGIES[name]
    before = [r["market_slug"] for r in _old_selection(ROWS)[name]]
    after = [b.market_slug for b in select(ROWS)[name]]
    assert before == after, f"{name} selects differently"


def test_a_strategy_that_picks_nothing_is_present_and_empty():
    """'registered and picked nothing' and 'not registered' are different facts
    and the book prints them differently."""
    got = select([])
    assert set(got) == set(STRATEGIES)
    assert all(v == [] for v in got.values())


def test_no_side_costs_one_minus_bid():
    bets = select(ROWS)["cfb_spread_no_20_30"]
    assert bets
    for b in bets:
        assert b.side == "no" and b.price == pytest.approx(b.stake)
        assert 0.70 <= b.price <= 0.81, "NO priced at the bid would read ~0.25 here"


def test_a_bet_is_a_choice_not_an_outcome():
    """No pnl, no settlement, no fee on Bet -- those belong to whoever settles."""
    assert set(Bet.__dataclass_fields__) == {
        "market_slug", "side", "price", "stake", "game_id"}


# ------------------------------------------------------- the sandbox's dispatch
def _sandbox():
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
    import sandbox
    return sandbox


def test_the_sandbox_lists_one_table_of_strategy_names():
    sb = _sandbox()
    assert set(STRATEGIES) <= set(sb.STRATEGIES), "ladder names must be listed"
    assert set(sb.QUOTE_STRATEGIES) <= set(sb.STRATEGIES)
    assert not set(STRATEGIES) & set(sb.QUOTE_STRATEGIES), "the two namespaces must not collide"


def test_the_sandbox_refuses_a_ladder_strategy_rather_than_running_the_quote_one():
    """argparse accepts every listed name, so without this the sandbox would run
    the QUOTE query and label the answer with a ladder name."""
    sb = _sandbox()
    with pytest.raises(SystemExit, match="ladder strategy"):
        sb.run(sport="cfb", strategy="cfb_spread_no_20_30", wallet=100.0,
               since="2026-01-01", db=None)


def test_the_sandbox_knows_the_multi_competition_sports():
    sb = _sandbox()
    assert {"cricket", "tabletennis"} <= set(sb.SPORTS)


# --------------------------------------------------------------------- #
# The MLB winner pair. One market per game, YES = the away side.
# --------------------------------------------------------------------- #
def _mlb_winner(slug, mid_price):
    half = 0.005
    return {"market_slug": slug, "game_id": slug, "league": "mlb",
            "mtype": "baseball_team_full_game_winner",
            "bid": mid_price - half, "ask": mid_price + half}


def test_the_mlb_winner_pair_is_disjoint_and_may_select_neither():
    """`mlb_winner_fav_yes` (mid >= 0.60) and `mlb_winner_dog_yes` (mid <= 0.40)
    both take side="yes" on the SAME market type, so whether they are a real
    comparison or an arithmetic identity depends on the board's shape.

    The venue lists ONE winner market per game — `aec-mlb-{away}-{home}-{date}`,
    verified on the tape 2026-09-14, maximum 1 distinct winner slug per
    game_id — and YES is the away side (strategies/ladder.py names nfl/cfb/mlb
    as the exception to YES-is-home). So the two rules partition GAMES by the
    away price, and cannot both hold: a mid cannot be >= 0.60 and <= 0.40.
    They are evidence, not a complement pair.

    They can both MISS, and usually do: on the same tape, of 49 winner markets
    with a two-sided quote, 17 are fav and 4 are dog — 28, fifty-seven per
    cent, are selected by neither. That is by design and is now printed by
    run_paper_book's per-league coverage line rather than being invisible.
    """
    rows = [_mlb_winner("aec-mlb-fav-hhh-2026-09-13", 0.75),
            _mlb_winner("aec-mlb-mid-hhh-2026-09-13", 0.50),
            _mlb_winner("aec-mlb-dog-hhh-2026-09-13", 0.25)]
    chosen = select(rows)
    fav = {b.market_slug for b in chosen.get("mlb_winner_fav_yes", [])}
    dog = {b.market_slug for b in chosen.get("mlb_winner_dog_yes", [])}

    assert not (fav & dog), (
        "the same market was taken by both rules — they would be a complement "
        "pair and 'favourites beat dogs' would be arithmetic, not evidence")
    # Controls: disjointness is also satisfied by two rules that select
    # nothing, so each side must demonstrably hit.
    assert fav == {"aec-mlb-fav-hhh-2026-09-13"}
    assert dog == {"aec-mlb-dog-hhh-2026-09-13"}
    assert "aec-mlb-mid-hhh-2026-09-13" not in (fav | dog), (
        "a market priced between the thresholds was selected by something")


def test_the_mlb_winner_thresholds_leave_a_gap_on_purpose():
    """The boundary, pinned: 0.60 and 0.40 are inclusive on their own side and
    the interval between them belongs to neither. A later widening to
    mid > 0.40 / mid < 0.60 would make them a partition and quietly turn the
    comparison into an identity."""
    rows = [_mlb_winner("aec-mlb-a-h-2026-09-13", 0.60),
            _mlb_winner("aec-mlb-b-h-2026-09-13", 0.40),
            _mlb_winner("aec-mlb-c-h-2026-09-13", 0.55)]
    chosen = select(rows)
    fav = {b.market_slug for b in chosen.get("mlb_winner_fav_yes", [])}
    dog = {b.market_slug for b in chosen.get("mlb_winner_dog_yes", [])}
    assert fav == {"aec-mlb-a-h-2026-09-13"}
    assert dog == {"aec-mlb-b-h-2026-09-13"}
    assert not (fav & dog)
