"""Which OTHER market families carry the spread ladder's defect.

The spread result (STATUS 0bi-0bv) is one instance of a general fact: the venue
lists several markets on the SAME underlying number, and arithmetic pins their
prices to each other. Where the pin is an implication between two events it is
a two-leg trade identical in shape to `scan.scan_ladder`; where it is a
decomposition of one quantity into non-negative parts it is a Frechet bound and
a three-leg basket.

ONE THEOREM, FIVE FAMILIES. Let X = U + V with U, V >= 0.

    containment   {U > n} is a subset of {X > n}            =>  P(U>n) <= P(X>n)
    Frechet up    u + v <= N  =>  P(X>N) <= P(U>u) + P(V>v)
    Frechet down  u + v >= N  =>  P(X>N) >= P(U>u) + P(V>v) - 1

Proofs are two lines each and are written out in docs/math/consistency-families.md.
The asymmetry that matters: **the lower bound survives an unquoted residual and
the upper bound does not.** If X = U + V + W with W >= 0 unquoted (overtime in a
half/half decomposition), then U>u and V>v still force X > u+v, so the lower
bound holds; but U<=u and V<=v no longer force X <= u+v, so the upper bound is
NOT implied. Every relation below is tagged with which of the two it is.

ORIENTATION IS THE TRAP. A totals ladder runs the OTHER WAY to a spread ladder:
a larger spread line is EASIER to cover (dearer), a larger total line is HARDER
to clear (cheaper). Feeding totals rungs to `scan.scan_ladder` finds violations
with the sign inverted, which is a scanner that reports the correct board as
broken and the broken board as correct. The two generators below exist so the
orientation is a named, tested object rather than a convention someone holds in
their head.

FEES ARE CHARGED AT THE YES-FRAME PRICE ON EVERY LEG, including the legs the
screen expresses as "buy NO at 1 - bid". That is not an approximation:
f(p) = r*p*(1-p) is symmetric under p -> 1-p, so f(1 - bid) == f(bid) exactly,
and the NO leg's fee is written as f(bid) throughout. Every leg pays; a basket
with k legs pays k fees, which is why three-leg baskets need materially more
gross disorder than two-leg pairs to clear zero.

PLACES NOTHING. Pure arithmetic over quotes a caller has already read; imports
no venue client and no session.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from core.ladder.scan import (
    DEFAULT_FEE_RATE,
    MAX_PLAUSIBLE_EDGE,
    MAX_PLAUSIBLE_SIZE,
    fee,
)

#: Relation name -> (legs, is_exact, what has to be true for it to be exact).
#:
#: A relation is EXACT when it follows from the settlement rules alone and
#: EXPECTED when it needs a view on the sport. Nothing merely expected is
#: scanned here: an "expected" relation prices a model, and a violation of it
#: is a trade with a loss state, which is the opposite of what this programme
#: is for. They are listed so the reader can see they were considered and
#: rejected, not overlooked.
RELATIONS: dict[str, tuple[int, bool, str]] = {
    "totals_ladder": (
        2, True,
        "P(Over N) is non-increasing in N. Needs nothing beyond the line "
        "ordering; the mirror of the spread ladder."),
    "spread_ladder": (
        2, True,
        "P(margin + L > 0) is non-decreasing in L. The measured family."),
    "winner_is_line_zero": (
        2, True,
        "The winner market IS the spread at line 0 (YES = away on both), so "
        "the two prices must agree in BOTH directions. Exact only where a "
        "draw is impossible; a tie settles the winner NO and the 0-line "
        "spread as a push, and the two are then different objects."),
    "segment_in_whole": (
        2, True,
        "A segment's points are part of the whole's, so P(segment > n) <= "
        "P(whole > n) at the same line. Survives an unquoted residual."),
    "frechet_lower": (
        3, True,
        "Parts over their lines force the whole over the sum of them. "
        "Survives an unquoted non-negative residual (overtime)."),
    "frechet_upper": (
        3, True,
        "The whole over N forces some part over its line -- ONLY if the parts "
        "exhaust the whole. An unquoted residual breaks this one."),
    "segment_spread_in_whole": (
        2, False,
        "EXPECTED, NOT EXACT, AND NOT SCANNED. Leading at half does not imply "
        "winning: half margins are not non-negative, so nothing is contained "
        "in anything. A scanner over these would report model disagreement as "
        "arbitrage."),
    "quarter_additivity_of_price": (
        2, False,
        "EXPECTED, NOT EXACT, AND NOT SCANNED. E[H1] = E[Q1] + E[Q2] is exact "
        "for the MEANS, but a binary option is not a mean and recovering one "
        "from the ladder needs every integer line quoted. The venue quotes a "
        "handful of half-point rungs."),
}


@dataclass(frozen=True)
class Claim:
    """One quoted binary market in the YES frame, at one instant.

    `key` is whatever the caller uses to name the rung -- this module never
    parses a slug, because a sign convention read off a slug is exactly the
    thing that produced an 88c phantom arbitrage on the spread ladder and it
    belongs in the caller where it can be validated against settlements.
    """

    key: str
    bid: float
    ask: float
    bid_size: float
    ask_size: float


@dataclass(frozen=True)
class Leg:
    """One side of a basket, in the form the venue's screen takes.

    `buy_no` is how the UI expresses "sell YES": the operator is never asked to
    translate, because the ladder protocol's only non-price loss state is
    clicking the wrong side (docs/math/ladder-fill-test.md).
    """

    key: str
    side: str  # 'buy_yes' | 'buy_no'
    price: float
    size: float


@dataclass(frozen=True)
class Basket:
    """A set of legs that cannot all be right, priced net of every leg's fee.

    `size` is the MIN over legs for the same reason `scan.Violation` takes the
    min of two: a basket is only as large as its smallest side. With three legs
    that min is taken over three quotes rather than two, which is why the
    three-leg families are expected to price smaller than the two-leg ones even
    where the price disorder is identical.
    """

    game: str
    relation: str
    legs: tuple[Leg, ...]
    edge: float
    size: float

    @property
    def dollars(self) -> float:
        return self.edge * self.size


def _capped(sizes: Iterable[float], max_size: float) -> float:
    return min(list(sizes) + [max_size])


def dominance(game: str, subset: Claim, superset: Claim, relation: str, *,
              fee_rate: float = DEFAULT_FEE_RATE,
              max_edge: float = MAX_PLAUSIBLE_EDGE,
              max_size: float = MAX_PLAUSIBLE_SIZE) -> Basket | None:
    """`subset`'s event implies `superset`'s, so P(subset) <= P(superset).

    Sell the subset at its bid, buy the superset at its ask. The pair pays
    1[superset] - 1[subset] >= 0 in every state, so any positive net receipt is
    free. This is `scan.scan_ladder`'s arithmetic with the ordering supplied by
    the caller instead of by the line, which is what lets one function serve the
    totals ladder, the winner/0-line identity and the segment containments.
    """
    edge = (subset.bid - superset.ask
            - fee(subset.bid, fee_rate) - fee(superset.ask, fee_rate))
    if not 0.0 < edge <= max_edge:
        return None
    return Basket(
        game, relation,
        (Leg(subset.key, "buy_no", 1.0 - subset.bid, subset.bid_size),
         Leg(superset.key, "buy_yes", superset.ask, superset.ask_size)),
        edge, _capped((subset.bid_size, superset.ask_size), max_size))


def frechet_upper(game: str, whole: Claim, parts: Sequence[Claim], *,
                  relation: str = "frechet_upper",
                  fee_rate: float = DEFAULT_FEE_RATE,
                  max_edge: float = MAX_PLAUSIBLE_EDGE,
                  max_size: float = MAX_PLAUSIBLE_SIZE) -> Basket | None:
    """P(whole > N) <= sum of P(part_i > n_i), when sum(n_i) <= N and the parts
    exhaust the whole.

    Sell the whole, buy every part. Payoff is 1[union of parts] - 1[whole] >= 0
    because the whole clearing N forces at least one part to clear its own line.
    THE CALLER OWNS THE PRECONDITION: this function is given claims, not lines,
    and cannot check either sum(n_i) <= N or that nothing is left over. Pass
    only splits built by `frechet_splits`, and only decompositions with no
    unquoted residual -- see the module docstring.
    """
    edge = whole.bid - fee(whole.bid, fee_rate)
    for p in parts:
        edge -= p.ask + fee(p.ask, fee_rate)
    if not 0.0 < edge <= max_edge:
        return None
    legs = (Leg(whole.key, "buy_no", 1.0 - whole.bid, whole.bid_size),) + tuple(
        Leg(p.key, "buy_yes", p.ask, p.ask_size) for p in parts)
    return Basket(game, relation, legs, edge,
                  _capped([whole.bid_size] + [p.ask_size for p in parts], max_size))


def frechet_lower(game: str, whole: Claim, parts: Sequence[Claim], *,
                  relation: str = "frechet_lower",
                  fee_rate: float = DEFAULT_FEE_RATE,
                  max_edge: float = MAX_PLAUSIBLE_EDGE,
                  max_size: float = MAX_PLAUSIBLE_SIZE) -> Basket | None:
    """P(whole > N) >= sum of P(part_i > n_i) - (k - 1), when sum(n_i) >= N.

    Buy the whole, sell every part. Payoff is 1[whole] + sum 1[not part_i],
    which is at least 1 because the only state with every part over its line
    has the whole over sum(n_i) >= N. Unlike `frechet_upper` this one tolerates
    an unquoted non-negative residual, so it is the bound to reach for whenever
    overtime or an unlisted segment is in play.
    """
    edge = (sum(p.bid - fee(p.bid, fee_rate) for p in parts)
            - (len(parts) - 1) - whole.ask - fee(whole.ask, fee_rate))
    if not 0.0 < edge <= max_edge:
        return None
    legs = (Leg(whole.key, "buy_yes", whole.ask, whole.ask_size),) + tuple(
        Leg(p.key, "buy_no", 1.0 - p.bid, p.bid_size) for p in parts)
    return Basket(game, relation, legs, edge,
                  _capped([whole.ask_size] + [p.bid_size for p in parts], max_size))


def totals_ladder_pairs(lines: Iterable[float]) -> list[tuple[float, float]]:
    """(subset, superset) line pairs for an Over ladder: the HIGHER line is the
    subset, because clearing 52.5 implies clearing 48.5.

    The mirror of `spread_ladder_pairs`. Both exist, and are tested against each
    other, because the one-word difference between them is the whole sign of the
    scan.
    """
    ordered = sorted(lines)
    return [(hi, lo) for i, lo in enumerate(ordered) for hi in ordered[i + 1:]]


def spread_ladder_pairs(lines: Iterable[float]) -> list[tuple[float, float]]:
    """(subset, superset) line pairs for a spread ladder: the LOWER line is the
    subset, because covering -17.5 implies covering -10.5. Reproduces the
    ordering `scan.scan_ladder` hard-codes."""
    ordered = sorted(lines)
    return [(lo, hi) for i, lo in enumerate(ordered) for hi in ordered[i + 1:]]


def containment_pairs(segment_lines: Iterable[float],
                      whole_lines: Iterable[float]) -> list[tuple[float, float]]:
    """(segment line, whole line) pairs where the containment actually bites:
    a segment clearing n implies the whole clearing N only for N <= n.

    This generator is deliberately printed rather than assumed to be rich. At
    the venue's quoted lines a first-half total sits near half the full-game
    total, so `n >= N` is satisfied by almost no listed pair and this relation
    has close to zero COVERAGE even though it is exactly true. The bound with
    power is the Frechet one.
    """
    whole = sorted(whole_lines)
    return [(n, N) for n in sorted(segment_lines) for N in whole if N <= n]


def frechet_splits(whole_lines: Iterable[float],
                   part_line_sets: Sequence[Iterable[float]],
                   ) -> list[tuple[float, tuple[float, ...], str]]:
    """Every (whole line, part lines, which bound) the arithmetic licenses.

    Yields the UPPER bound where the part lines sum to at most the whole's line
    and the LOWER bound where they sum to at least it; an exact split licenses
    both. Equality is included on both sides because the derivation uses
    non-strict inequalities.

    ON THIS VENUE THAT EQUALITY BRANCH IS UNREACHABLE and the count it
    contributes to `coverage` is therefore always zero. Every recorded line is a
    half point, so two part lines sum to an INTEGER while the whole is quoted at
    a half point and `sum(parts) == N` cannot hold. The branch is kept -- it is
    the correct arithmetic and a venue that lists an integer line would need it
    -- but a reader must not count it as coverage, and
    `test_an_exact_frechet_split_cannot_occur_on_the_venues_real_lines` pins
    that it does not fire on the real grid.
    """
    out: list[tuple[float, tuple[float, ...], str]] = []
    sets = [sorted(s) for s in part_line_sets]
    combos: list[tuple[float, ...]] = [()]
    for s in sets:
        combos = [c + (x,) for c in combos for x in s]
    for N in sorted(whole_lines):
        for combo in combos:
            total = sum(combo)
            if total <= N:
                out.append((N, combo, "frechet_upper"))
            if total >= N:
                out.append((N, combo, "frechet_lower"))
    return out


def coverage(lines_by_family: dict[str, Sequence[float]], *,
             totals: str, spread: str, winner: str,
             segments: Sequence[tuple[str, str, str]] = (),
             ) -> dict[str, int]:
    """How many baskets each relation can form AT ALL, before any price is read.

    This is the obs count that has to be printed beside every violation rate,
    and it is not a formality: two of the five candidate relations turn out to
    have a denominator of ZERO on this venue's line grid, which no violation
    count can reveal. A scan that reports "0 violations" over 0 formable pairs
    and a scan that reports "0 violations" over 96,620 of them are different
    results, and only this function distinguishes them.

    THE GRID IS ALL HALF-POINTS. Every one of the 4,617 rung slugs recorded in
    this repo ends `pt5`; not one integer line has ever been observed, on any
    family or league. Two consequences follow and both are counted here rather
    than argued:

    * `winner_is_line_zero` is EXACT AND VACUOUS. There is no 0.0 spread rung to
      compare the moneyline against, so the count is 0 wherever the grid is
      half-point. The spread scanner already *inserts* the winner AS line 0.0
      (`run_ladder_scan.py`, "57 ladders including the winner rung"), which is
      where STATUS 0bi's winner coverage comes from -- the venue lists one
      object, not two that could disagree.
    * An EXACT Frechet split is unreachable. Two half-point part lines sum to an
      integer, and the whole is quoted at a half-point, so `sum(parts) == N`
      never holds and every split is strict in one direction only. The equality
      branch in `frechet_splits` is correct and cannot fire on this board.

    Keys are relation names as `RELATIONS` spells them, suffixed `:tag` for the
    segment decompositions exactly as the baskets are, so a caller can divide a
    violation count by its own denominator without re-deriving which is which.
    """
    got = {k: sorted(v) for k, v in lines_by_family.items() if v}
    out: dict[str, int] = {
        "totals_ladder": len(totals_ladder_pairs(got.get(totals, []))),
        "winner_is_line_zero": (
            2 if winner in got and 0.0 in got.get(spread, []) else 0),
    }
    for part_a, part_b, whole in segments:
        if whole not in got:
            continue
        tag = whole
        out[f"segment_in_whole:{tag}"] = sum(
            len(containment_pairs(got[p], got[whole]))
            for p in (part_a, part_b) if p in got)
        if part_a not in got or part_b not in got:
            continue
        splits = frechet_splits(got[whole], [got[part_a], got[part_b]])
        for which in ("frechet_upper", "frechet_lower"):
            out[f"{which}:{tag}"] = sum(1 for _, _, w in splits if w == which)
    return out
