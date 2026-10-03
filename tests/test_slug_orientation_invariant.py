"""The venue names events away-first. These sites must not CARE.

Measured 2026-09-06, two leagues, **701 observations and zero exceptions**:

    CFB, event_slug vs the computed map    away 53   home 0   (20 ambiguous)
    WNBA, slugs joined to team_game_logs   away 648  home 0

So `first_is_home` is False everywhere in production, and the four sites that
compute it -- `team_mapping.resolve_orientation`, `team_mapping.orient_for_slug`,
`resolution.implied_settlement`, `pulse.replay_eval` -- have a True arm that has
never executed.

**That is NOT the same defect as B15, and the difference decides the fix.**

B15's comparison was `event_slug.split("-")[1] == market_slug.split("-")[2]` --
two encodings of ONE ordering, so it could not disagree with itself and the code
was simply wrong. These compare an **ESPN** abbrev to a **slug** abbrev: two
independent sources, measured per game. If the venue flipped tomorrow, these
sites would return True and still be correct.

**Which is why an assertion that away-first holds would be the wrong fix.** It
would raise on a game these functions already handle correctly, creating a
failure mode where none exists. The property worth pinning is not the
convention -- it is INDEPENDENCE from the convention. So every test below runs
each site under BOTH orientations and demands the same answer.

Mutation-tested, because a test of an invariant that already holds is exactly
the kind that can pass without checking anything. Two mutants of
`resolution.py:130`, both killed:

    quoted_is_home = home.team_abbrev != parsed.first_espn   -> 4 of 11 fail
    quoted_is_home = False   # hardcode the observed convention -> 3 of 11 fail

The second is the one that matters: it is correct on every row of real data and
only wrong on a home-first game, so it turns convention-independent code into
convention-dependent code with no production symptom. That is the mutant a
fixture drawn only from the real convention cannot kill. The totals tests
survive both, correctly -- a sum has no orientation to get wrong.
"""
from __future__ import annotations

import dataclasses

import pytest

from core.resolution import implied_settlement
from core.team_mapping import GameOrientation


@dataclasses.dataclass
class _Log:
    """Enough of a TeamGameLog for `implied_settlement`."""
    team_abbrev: str
    points_scored: float


IND, NY = _Log("IND", 90.0), _Log("NY", 80.0)     # IND wins by 10


@pytest.mark.parametrize("home, away, orientation", [
    (NY, IND, "away-first (the real convention)"),
    (IND, NY, "home-first (the hypothetical flip)"),
])
def test_moneyline_settles_on_the_quoted_team_either_orientation(home, away, orientation):
    """The slug names IND first and IND won, so YES settles 1 both ways."""
    assert implied_settlement(market_slug="aec-wnba-ind-ny-2026-08-22",
                              home=home, away=away, line=None) == 1, orientation
    # and the losing side is 0 both ways
    assert implied_settlement(market_slug="aec-wnba-ny-ind-2026-08-22",
                              home=home, away=away, line=None) == 0, orientation


@pytest.mark.parametrize("home, away", [(NY, IND), (IND, NY)])
@pytest.mark.parametrize("line, want", [(-9.5, 1), (-10.5, 0)])
def test_spread_covers_on_the_quoted_margin_either_orientation(home, away, line, want):
    """IND is quoted first and won by 10: covers -9.5, fails -10.5, both ways."""
    assert implied_settlement(market_slug="asc-wnba-ind-ny-2026-08-22",
                              home=home, away=away, line=line) == want


@pytest.mark.parametrize("home, away", [(NY, IND), (IND, NY)])
def test_a_total_ignores_orientation_entirely(home, away):
    """170 points scored. Orientation cannot enter a sum, and must not."""
    assert implied_settlement(market_slug="tsc-wnba-ind-ny-2026-08-22",
                              home=home, away=away, line=169.5) == 1
    assert implied_settlement(market_slug="tsc-wnba-ind-ny-2026-08-22",
                              home=home, away=away, line=170.5) == 0


def _orient(first_is_home: bool) -> GameOrientation:
    import datetime as dt
    return GameOrientation(espn_game_id="1", home_abbrev="IND", away_abbrev="NY",
                           game_date=dt.datetime(2026, 8, 22),
                           first_is_home=first_is_home)


def test_first_abbrev_names_the_quoted_team_under_both_conventions():
    assert _orient(first_is_home=True).first_abbrev == "IND"
    assert _orient(first_is_home=False).first_abbrev == "NY"


@pytest.mark.parametrize("first_is_home, p_home, want_p_first",
                         [(True, 0.70, 0.70), (False, 0.70, 0.30)])
def test_a_home_win_probability_is_reframed_to_the_quoted_side(
        first_is_home, p_home, want_p_first):
    """`replay_eval` scores ESPN's WP against the FIRST team, not the home team.

    Pinned here rather than left to that call site, because the reframing is a
    one-line expression whose wrong version is also a valid probability.
    """
    p_first = p_home if first_is_home else 1.0 - p_home
    assert p_first == pytest.approx(want_p_first)
