"""Kalshi ticker parsing and the Kalshi -> ESPN team mapping.

Kalshi's WNBA event tickers look like ``KXWNBAGAME-26AUG05PHXATL``: a series
ticker, then ``yyMONdd`` and **two team codes concatenated with no
delimiter**. The shared suffix (``26AUG05PHXATL``) is the same across the
moneyline, spread, and total series for one game, so it serves as the game
key.

Two hazards, both the same species as the Polymarket ones in
`core.team_mapping`:

1. **Kalshi's codes are a third abbreviation space.** Two differ from ESPN:
   ``CONN`` -> ``CON`` and ``PDX`` -> ``POR``. The table below is explicit and
   complete for the same reason POLYMARKET_TO_ESPN is: an explicit table fails
   loudly on a new franchise, a transform fails silently.

2. **The concatenated pair has no delimiter**, so parsing tries every split
   point and demands exactly one where both halves are known codes.
   `tests/test_kalshi.py` proves that property holds for every franchise pair,
   so a future code addition that introduces ambiguity breaks a test instead
   of silently mis-parsing (e.g. all-star exhibition codes like ``SPNCOO``
   simply fail to parse, which is correct — those are not games we compare).

Ticker order is stored verbatim but treated as **positional only**, never
home/away. Polymarket's slug order flipped convention mid-season; Kalshi's
order earns the same distrust until measured. Orientation, when needed, comes
from ESPN via the existing `core.team_mapping` machinery on the unordered
pair.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from core.team_mapping import UnknownTeamError

#: Kalshi code -> ESPN abbreviation. Codes observed on the venue 2026-08-05
#: across every open KXWNBAGAME event.
KALSHI_TO_ESPN: dict[str, str] = {
    "ATL": "ATL",
    "CHI": "CHI",
    "CONN": "CON",   # <- differs
    "DAL": "DAL",
    "GS": "GS",
    "IND": "IND",
    "LA": "LA",
    "LV": "LV",
    "MIN": "MIN",
    "NY": "NY",
    "PDX": "POR",    # <- differs
    "PHX": "PHX",
    "SEA": "SEA",
    "TOR": "TOR",
    "WSH": "WSH",
}

#: Kalshi NFL code -> ESPN abbreviation. Codes harvested from the venue
#: 2026-09-02 via each open KXNFLGAME event's own market-ticker suffixes
#: (the two per-team markets name the codes exactly — no split-guessing),
#: with yes_sub_title confirming the franchise. Two differ from ESPN,
#: the same species as CONN/PDX above.
KALSHI_TO_ESPN_NFL: dict[str, str] = {
    "ARI": "ARI", "ATL": "ATL", "BAL": "BAL", "BUF": "BUF", "CAR": "CAR",
    "CHI": "CHI", "CIN": "CIN", "CLE": "CLE", "DAL": "DAL", "DEN": "DEN",
    "DET": "DET", "GB": "GB", "HOU": "HOU", "IND": "IND",
    "JAC": "JAX",    # <- differs
    "KC": "KC", "LAC": "LAC", "LAR": "LAR", "LV": "LV", "MIA": "MIA",
    "MIN": "MIN", "NE": "NE", "NO": "NO", "NYG": "NYG", "NYJ": "NYJ",
    "PHI": "PHI", "PIT": "PIT", "SEA": "SEA", "SF": "SF", "TB": "TB",
    "TEN": "TEN",
    "WAS": "WSH",    # <- differs
}

LEAGUE_WNBA = "wnba"
LEAGUE_NFL = "nfl"

#: One explicit table per league. Seven codes exist in BOTH tables (ATL,
#: CHI, DAL, IND, LV, MIN, SEA), so a game key alone does not identify a
#: league — parsing takes the league, and kalshi_games keys on
#: (league, game_key). A same-date cross-league pair (SEA/ATL in both
#: leagues on one Sunday) is a real collision, not a hypothetical.
LEAGUE_TABLES: dict[str, dict[str, str]] = {
    LEAGUE_WNBA: KALSHI_TO_ESPN,
    LEAGUE_NFL: KALSHI_TO_ESPN_NFL,
}

#: The three full-game series the pre-registered comparison runs on.
SERIES_MONEYLINE = "KXWNBAGAME"
SERIES_SPREAD = "KXWNBASPREAD"
SERIES_TOTAL = "KXWNBATOTAL"

#: The NFL full-game series (GRIDIRON) — venue-verified 2026-09-02: same
#: event-ticker shape, ~25 team-directional spread rungs and ~19 total
#: rungs per game, no start time on events (the standing WNBA gap).
SERIES_MONEYLINE_NFL = "KXNFLGAME"
SERIES_SPREAD_NFL = "KXNFLSPREAD"
SERIES_TOTAL_NFL = "KXNFLTOTAL"

SERIES_TO_MARKET_TYPE: dict[str, str] = {
    SERIES_MONEYLINE: "winner",
    SERIES_SPREAD: "spread",
    SERIES_TOTAL: "total",
    SERIES_MONEYLINE_NFL: "winner",
    SERIES_SPREAD_NFL: "spread",
    SERIES_TOTAL_NFL: "total",
}

SERIES_TO_LEAGUE: dict[str, str] = {
    SERIES_MONEYLINE: LEAGUE_WNBA,
    SERIES_SPREAD: LEAGUE_WNBA,
    SERIES_TOTAL: LEAGUE_WNBA,
    SERIES_MONEYLINE_NFL: LEAGUE_NFL,
    SERIES_SPREAD_NFL: LEAGUE_NFL,
    SERIES_TOTAL_NFL: LEAGUE_NFL,
}

LEAGUE_SERIES: dict[str, tuple[str, ...]] = {
    LEAGUE_WNBA: (SERIES_MONEYLINE, SERIES_SPREAD, SERIES_TOTAL),
    LEAGUE_NFL: (SERIES_MONEYLINE_NFL, SERIES_SPREAD_NFL, SERIES_TOTAL_NFL),
}

_MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


@dataclass(frozen=True)
class ParsedGameKey:
    """Date and team codes recovered from a Kalshi game key.

    ``first_code``/``second_code`` are positional ONLY — see module docstring.
    ``league`` names which code table parsed it (shared codes make the key
    alone league-ambiguous).
    """

    game_key: str
    local_date: dt.date
    first_code: str
    second_code: str
    league: str = LEAGUE_WNBA

    @property
    def first_espn(self) -> str:
        return _to_espn(self.first_code, self.league)

    @property
    def second_espn(self) -> str:
        return _to_espn(self.second_code, self.league)

    @property
    def espn_pair(self) -> frozenset[str]:
        """Unordered ESPN team pair — the only safe cross-venue join key."""
        return frozenset({self.first_espn, self.second_espn})


def _to_espn(code: str, league: str = LEAGUE_WNBA) -> str:
    table = LEAGUE_TABLES[league]
    key = (code or "").strip().upper()
    if key not in table:
        raise UnknownTeamError(
            f"no ESPN mapping for Kalshi {league} team {code!r}. A franchise "
            "was probably added — update the league's table."
        )
    return table[key]


def parse_game_key(game_key: str, league: str = LEAGUE_WNBA) -> ParsedGameKey | None:
    """Parse ``26AUG05PHXATL`` -> (2026-08-05, PHX, ATL), or None.

    Returns None when the date is malformed, when no split of the team blob
    yields two known codes (all-star exhibitions), or when more than one split
    does (ambiguity — refusing is safer than guessing, same rule as
    `resolve_orientation`).
    """
    key = (game_key or "").strip().upper()
    if len(key) < 9:
        return None
    yy, mon, dd, teams = key[:2], key[2:5], key[5:7], key[7:]
    if mon not in _MONTHS or not yy.isdigit() or not dd.isdigit():
        return None
    try:
        local_date = dt.date(2000 + int(yy), _MONTHS[mon], int(dd))
    except ValueError:
        return None

    table = LEAGUE_TABLES[league]
    splits = [
        (teams[:i], teams[i:])
        for i in range(1, len(teams))
        if teams[:i] in table and teams[i:] in table
    ]
    if len(splits) != 1:
        return None
    first, second = splits[0]
    return ParsedGameKey(
        game_key=key, local_date=local_date, first_code=first,
        second_code=second, league=league,
    )


def game_key_from_event_ticker(event_ticker: str) -> str | None:
    """``KXWNBAGAME-26AUG05PHXATL`` -> ``26AUG05PHXATL``."""
    parts = (event_ticker or "").split("-", 1)
    return parts[1] if len(parts) == 2 and parts[1] else None
