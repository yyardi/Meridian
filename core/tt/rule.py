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


def money_verdict(*, n: int, lo: float, hi: float, resolution: float,
                  required: int) -> tuple[str, str]:
    """The SECOND registered criterion: does the disagreement make money.

    Separate from `verdict` and never collapsed with it. The registered spec
    ran this only on a signal PASS; it runs always, because conditioning the
    P&L on a favourable coefficient draw selects on the same outcomes it then
    measures.

    NOT YET fires when the interval is wider than the bar it is being compared
    against — at that width the arm cannot tell "loses the cost" from "makes
    the cost", so a negative point estimate is not evidence of anything. This
    module stays dependency-free, so the caller supplies the bar and the count
    from `core.tt.money` rather than this file importing them.
    """
    if n <= 0:
        return NOT_YET, "no bet cleared its own entry price plus fee"
    half = (hi - lo) / 2.0
    if not (half == half):
        return NOT_YET, f"interval not estimable on {n} bets"
    if half <= 0.0:
        return NOT_YET, (f"interval has zero width on {n} bets: the outcomes "
                         f"are homogeneous, so the variance collapsed rather "
                         f"than the estimate becoming precise")
    if half > resolution:
        return NOT_YET, (f"interval ±{half * 100:.2f}c is wider than the "
                         f"{resolution * 100:.2f}c bar it is compared against; "
                         f"needs ≥{required} matches")
    if lo > 0.0:
        return PASS, f"net +{lo * 100:.2f}c/contract at the interval's floor"
    return FAIL, "interval is narrow enough to resolve the bar and includes zero"


def report(signal: tuple[str, str], money: tuple[str, str]) -> str:
    """The two verdicts, side by side, in the only form they may be read in.

    `materiality-is-question-relative`: a label must not say what the result
    means if it comes out as expected. SIGNAL yes / MONEY not yet is the
    expected outcome at these sample sizes and is a finding, not a failure.
    """
    return f"SIGNAL {signal[0]} ({signal[1]}) | MONEY {money[0]} ({money[1]})"


def reachable(*, max_predicted: int, max_players: int) -> set[str]:
    """Which verdicts this competition could EVER return, at its ceiling.

    `max_players` is the size of the pool, not today's count: a competition
    whose entire pool is smaller than the floor can never leave NOT YET.
    """
    if max_predicted < MIN_PREDICTED or max_players < MIN_PLAYERS:
        return {NOT_YET}
    return {PASS, FAIL, NOT_YET}
