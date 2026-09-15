"""The pre-committed decision rule (docs/math/tabletennis-elo-harness.md §5).

Per competition, NEVER pooled: pooling the four competitions is named in the
pre-registration as the error that produced three false descriptions in one
day.

Written as code so its achievable image can be tested rather than argued —
`check-a-decision-rule-against-its-achievable-image`. A rule with an
unreachable branch is not a decision, and one of the four competitions has
exactly that: setkawoua's 6 players cannot meet a >=25 floor, so NOT_YET is
its only reachable outcome, permanently.
"""

from __future__ import annotations

MIN_PREDICTED = 200
MIN_PLAYERS = 25

PASS = "PASS"
FAIL = "FAIL"
NOT_YET = "NOT YET"


def verdict(*, predicted: int, players: int, interval_excludes_zero: bool
            ) -> tuple[str, str]:
    """(verdict, reason). NOT YET is not a FAIL and must not be read as one."""
    if predicted < MIN_PREDICTED:
        return NOT_YET, f"{predicted} predicted matches < {MIN_PREDICTED}"
    if players < MIN_PLAYERS:
        return NOT_YET, f"{players} distinct players < {MIN_PLAYERS}"
    if interval_excludes_zero:
        return PASS, "Elo coefficient's game-clustered interval excludes zero"
    return FAIL, "floors met and the interval includes zero"


def reachable(*, max_predicted: int, max_players: int) -> set[str]:
    """Which verdicts this competition could EVER return, at its ceiling.

    `max_players` is the size of the pool, not today's count: a competition
    whose entire pool is smaller than the floor can never leave NOT YET.
    """
    if max_predicted < MIN_PREDICTED or max_players < MIN_PLAYERS:
        return {NOT_YET}
    return {PASS, FAIL, NOT_YET}
