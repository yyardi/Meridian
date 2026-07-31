"""American odds, implied probability, and vig removal.

Why vig removal matters
-----------------------
A sportsbook's two-sided prices deliberately sum to more than 100%. That excess
is the book's margin (the "vig"). A -110/-110 market implies 52.4% + 52.4% =
104.8%.

Comparing a raw book probability against a Polymarket price therefore overstates
the gap on *both* sides — you would appear to have edge on every market you
looked at. Since the cross-market gap is the strategy's strongest signal, failing
to de-vig would manufacture fake edge systematically. Always compare de-vigged
probabilities.
"""

from __future__ import annotations

import statistics
from decimal import Decimal, InvalidOperation
from typing import Any, Sequence


def parse_american(value: Any) -> Decimal | None:
    """Parse American odds from ESPN's several encodings.

    Seen in the wild: -1400 (int, core API), "+515" (string, scoreboard),
    "-110" (string), "EVEN", "" and None.
    """
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        if value.upper() in {"EVEN", "EV", "PK"}:
            return Decimal(100)
        value = value.replace("+", "")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def parse_line(value: Any) -> Decimal | None:
    """Parse a line like "o186.5", "u186.5", "+12.5", "-3.5", 186.5."""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().lstrip("ouOU").replace("+", "")
        if not value:
            return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def american_to_probability(odds: Any) -> Decimal | None:
    """Convert American odds to implied probability (vig included).

        -150  ->  150 / 250       = 0.600
        +150  ->  100 / 250       = 0.400
    """
    o = parse_american(odds)
    if o is None or o == 0:
        return None
    if o < 0:
        return (-o) / ((-o) + Decimal(100))
    return Decimal(100) / (o + Decimal(100))


def remove_vig(prob_a: Decimal | None, prob_b: Decimal | None) -> tuple[Decimal | None, Decimal | None]:
    """Normalise two implied probabilities so they sum to exactly 1.

    Uses the standard proportional ("multiplicative") method: each side keeps
    its share of the total. This assumes the book applies its margin
    proportionally, which is the usual first-order approximation. It is known
    to be imperfect on heavy favourites, where books typically load more vig
    onto the longshot — so treat de-vigged longshot probabilities with some
    caution.
    """
    if prob_a is None or prob_b is None:
        return None, None
    total = prob_a + prob_b
    if total <= 0:
        return None, None
    return prob_a / total, prob_b / total


def two_sided_no_vig(odds_a: Any, odds_b: Any) -> tuple[Decimal | None, Decimal | None]:
    """American odds for both sides -> de-vigged probabilities summing to 1."""
    return remove_vig(american_to_probability(odds_a), american_to_probability(odds_b))


#: Plausible range for a WNBA game total. Real totals cluster near 164
#: (measured mean 164.0, sd 17.3); this range is deliberately wide.
MIN_PLAUSIBLE_TOTAL = Decimal(100)
MAX_PLAUSIBLE_TOTAL = Decimal(400)
#: How far a candidate total may sit from the known line before we distrust it.
MAX_TOTAL_DEVIATION = Decimal(30)


def plausible_total(
    value: Decimal | None, reference: Decimal | None = None
) -> Decimal | None:
    """Return `value` only if it is credibly a game total, else None.

    ESPN overloads ``close.total.american``: for 2024+ it holds the *line*
    ("166.5"), but for earlier seasons the same field holds the *odds*
    ("-115"). Trusting the field name writes juice into `close_total` and then
    flags the row as a closing line — silently corrupting CLV, which is the
    backtest's primary metric.

    Two guards:
      * a total is positive and within a plausible basketball range
      * where the line is independently known (``overUnder``), a genuine
        closing total sits close to it; a value 80 points away is not a total
    """
    if value is None:
        return None
    if not (MIN_PLAUSIBLE_TOTAL <= value <= MAX_PLAUSIBLE_TOTAL):
        return None
    if reference is not None and abs(value - reference) > MAX_TOTAL_DEVIATION:
        return None
    return value


def consensus(values: Sequence[Decimal | None]) -> Decimal | None:
    """Median across sportsbooks.

    Median rather than mean on purpose: with 6-15 books, one stale or
    mis-scraped line would drag a mean noticeably. The median ignores it.
    """
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return Decimal(str(statistics.median(clean)))
