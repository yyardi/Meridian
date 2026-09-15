"""Elo over table-tennis matches, fitted only on what was settled before.

Registered: K=24, start 1500, both players >=10 prior settled matches IN THE
SAME COMPETITION, no price input, no future information
(docs/math/tabletennis-rating-preregistration.md). Specifications in
docs/math/tabletennis-elo-harness.md.

The two rules that are easy to get wrong and are therefore structural here:

* IDENTITY IS `(competition, token)`, never the token alone. That implements
  both "prior matches in the same competition" and "a name in two competitions
  is two entities until proven otherwise" as ONE decision, so no code path can
  hold the two definitions apart. `cross_competition_tokens` surfaces the
  event; it does not change the arithmetic.
* TOKENS ARE NOT FIXED WIDTH. 704 of 712 appearances are six characters, four
  are seven (`demciva`) and four are four (`mars`). Splitting on `-` and
  counting is why that costs nothing; slicing at six would lose a player.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

K_DEFAULT = 24.0
START_RATING = 1500.0
MIN_PRIOR_MATCHES = 10

#: Elo's scale constant. 400 points is a 10:1 expected-score ratio.
SCALE = 400.0


@dataclass(frozen=True)
class Match:
    """One settled match. `y` is 1 when the FIRST-listed player won.

    The frame is confirmed by calibration, not assumed: realized rate rises
    monotonically with the first-listed player's price
    (docs/math/tabletennis-player-identity.md §4).
    """

    slug: str
    competition: str
    p1: str
    p2: str
    y: int
    started_at: dt.datetime | None
    price_yes: float | None = None


@dataclass(frozen=True)
class Prediction:
    slug: str
    competition: str
    p1: str
    p2: str
    y: int
    price_yes: float | None
    elo_p: float
    prior_p1: int
    prior_p2: int
    eligible: bool
    reason: str


def parse_slug(slug: str) -> tuple[str, str, str] | None:
    """`aec-<competition>-<p1>-<p2>-<YYYY>-<MM>-<DD>` -> (competition, p1, p2).

    Returns None when the slug does not yield EXACTLY two player tokens, so a
    caller can count the failures instead of discovering it filtered them.
    """
    parts = slug.split("-")
    if len(parts) < 6:
        return None
    date = "-".join(parts[-3:])
    try:
        dt.date.fromisoformat(date)
    except ValueError:
        return None
    mid = parts[2:-3]
    if len(mid) != 2:
        return None
    return parts[1], mid[0], mid[1]


def expected(rating_a: float, rating_b: float) -> float:
    """P(a beats b) under Elo."""
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / SCALE))


def update(rating_a: float, rating_b: float, y: int, k: float = K_DEFAULT
           ) -> tuple[float, float]:
    """Both ratings after a match a-vs-b that a won when `y` is 1.

    Zero-sum by construction: whatever a gains, b loses. A test pins that,
    because an updater that is not zero-sum drifts the whole pool.
    """
    e = expected(rating_a, rating_b)
    delta = k * (y - e)
    return rating_a + delta, rating_b - delta


def cross_competition_tokens(matches: list[Match]) -> dict[str, list[str]]:
    """Tokens appearing in more than one competition, with those competitions.

    A NOTICE, not an error. Identity already treats them as separate players;
    this exists because the two definitions are indistinguishable while the
    answer is empty (0 of 180 tokens on 2026-09-15) and diverge silently the
    first time it is not.
    """
    seen: dict[str, set[str]] = defaultdict(set)
    for m in matches:
        seen[m.p1].add(m.competition)
        seen[m.p2].add(m.competition)
    return {t: sorted(c) for t, c in sorted(seen.items()) if len(c) > 1}


def replay(matches: list[Match], *, k: float = K_DEFAULT,
           min_prior: int = MIN_PRIOR_MATCHES) -> list[Prediction]:
    """Walk the matches in start-time order, predicting before updating.

    Ordering is `started_at` (the venue's own start instant), NOT the slug's
    date: 94% of the settled set falls on one day, so date granularity would
    force a choice between leaking same-day information into its own
    prediction and throwing a day of accrual away. A match with no
    `started_at` is REFUSED and counted — never silently ordered last.

    Returns one Prediction per match, eligible or not, so the caller counts
    exclusions rather than receiving a filtered list.
    """
    rating: dict[tuple[str, str], float] = defaultdict(lambda: START_RATING)
    played: dict[tuple[str, str], int] = defaultdict(int)

    dated = [m for m in matches if m.started_at is not None]
    undated = [m for m in matches if m.started_at is None]
    out: list[Prediction] = []

    for m in sorted(dated, key=lambda m: (m.started_at, m.slug)):
        a, b = (m.competition, m.p1), (m.competition, m.p2)
        na, nb = played[a], played[b]
        p = expected(rating[a], rating[b])
        if na >= min_prior and nb >= min_prior:
            ok, why = True, ""
        else:
            ok, why = False, f"prior {na}/{nb} < {min_prior}"
        out.append(Prediction(m.slug, m.competition, m.p1, m.p2, m.y,
                              m.price_yes, p, na, nb, ok, why))
        rating[a], rating[b] = update(rating[a], rating[b], m.y, k)
        played[a] += 1
        played[b] += 1

    for m in undated:
        out.append(Prediction(m.slug, m.competition, m.p1, m.p2, m.y,
                              m.price_yes, float("nan"), -1, -1, False,
                              "no game_start_time: cannot be ordered"))
    return out


def ratings_after(matches: list[Match], *, k: float = K_DEFAULT
                  ) -> dict[tuple[str, str], float]:
    """Final ratings, for the positive control to compare against."""
    rating: dict[tuple[str, str], float] = defaultdict(lambda: START_RATING)
    for m in sorted([m for m in matches if m.started_at is not None],
                    key=lambda m: (m.started_at, m.slug)):
        a, b = (m.competition, m.p1), (m.competition, m.p2)
        rating[a], rating[b] = update(rating[a], rating[b], m.y, k)
    return dict(rating)
