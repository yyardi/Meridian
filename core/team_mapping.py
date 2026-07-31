"""Mapping between Polymarket and ESPN team identifiers, and slug parsing.

There is **no shared identifier** between the two systems, and three separate
mismatches will each silently break a join:

1. **Different ID spaces.** Polymarket ``gameId`` is ``13002440``; ESPN's is
   ``401856953``. Unrelated. You cannot join on ID.

2. **Different abbreviations.** Polymarket is lowercase and disagrees on two
   teams: ``gsv``/``GS`` and ``conn``/``CON``. A naive ``.upper()`` silently
   drops every Golden State and Connecticut game with no error at all — which
   is why the mapping below is explicit.

3. **Different timezones.** Slug ``...-2026-05-10`` is ESPN ``game_date``
   ``2026-05-11 00:30:00+00``. Evening games cross midnight UTC, so an exact
   date join loses roughly half the schedule.

⚠️ **Slug order does NOT reliably encode home/away.** Measured across 285
closed WNBA markets:

    first slug team is AWAY : 267
    first slug team is HOME :  18   (all early May 2026, season opening)

Polymarket changed convention partway through the season's first week. Trusting
the slug would silently invert spread and moneyline predictions for those
games — a wrong sign, not a missing value, so nothing would look broken.

Therefore the slug is parsed only for the **unordered team pair and date**, and
home/away is resolved from ESPN, which is authoritative. The first slug team is
still meaningful — it is the side the market is quoted from ("Will the Seattle
cover +19.5") — it just cannot be assumed to be the away team.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

#: Polymarket abbreviation -> ESPN abbreviation.
#: Only two genuinely differ; the rest are a case change. Listed in full
#: anyway, because an explicit table fails loudly when a franchise is added
#: whereas `.upper()` fails silently.
POLYMARKET_TO_ESPN: dict[str, str] = {
    "atl": "ATL",
    "chi": "CHI",
    "conn": "CON",   # <- differs
    "dal": "DAL",
    "gsv": "GS",     # <- differs
    "ind": "IND",
    "la": "LA",
    "lv": "LV",
    "min": "MIN",
    "ny": "NY",
    "phx": "PHX",
    "por": "POR",
    "sea": "SEA",
    "tor": "TOR",
    "wsh": "WSH",
}

ESPN_TO_POLYMARKET: dict[str, str] = {v: k for k, v in POLYMARKET_TO_ESPN.items()}


class UnknownTeamError(KeyError):
    """Raised when a Polymarket abbreviation has no ESPN counterpart.

    Deliberately loud: a silently unmapped team means missing predictions that
    nobody notices.
    """


def to_espn_abbrev(polymarket_abbrev: str) -> str:
    key = (polymarket_abbrev or "").strip().lower()
    if key not in POLYMARKET_TO_ESPN:
        raise UnknownTeamError(
            f"no ESPN mapping for Polymarket team {polymarket_abbrev!r}. "
            "A franchise was probably added — update POLYMARKET_TO_ESPN."
        )
    return POLYMARKET_TO_ESPN[key]


# Market slug prefixes.
PREFIX_TOTAL = "tsc"
PREFIX_SPREAD = "asc"
PREFIX_MONEYLINE = "aec"

_EVENT_SLUG = re.compile(
    r"^wnba-(?P<away>[a-z]+)-(?P<home>[a-z]+)-(?P<date>\d{4}-\d{2}-\d{2})$"
)
_MARKET_SLUG = re.compile(
    r"^(?P<prefix>tsc|asc|aec)-wnba-(?P<away>[a-z]+)-(?P<home>[a-z]+)-"
    r"(?P<date>\d{4}-\d{2}-\d{2})(?P<rest>.*)$"
)


@dataclass(frozen=True)
class ParsedSlug:
    """Teams and date recovered from a Polymarket slug.

    ``first``/``second`` are positional ONLY. They do not mean away/home — see
    the module docstring. ``first`` is the side the market is quoted from.
    """

    first_polymarket: str
    second_polymarket: str
    local_date: dt.date
    market_type: str | None = None   # 'tsc' | 'asc' | 'aec'

    @property
    def first_espn(self) -> str:
        return to_espn_abbrev(self.first_polymarket)

    @property
    def second_espn(self) -> str:
        return to_espn_abbrev(self.second_polymarket)

    @property
    def espn_pair(self) -> frozenset[str]:
        """Unordered team pair — the only safe join key from a slug."""
        return frozenset({self.first_espn, self.second_espn})


def parse_event_slug(slug: str) -> ParsedSlug | None:
    m = _EVENT_SLUG.match(slug or "")
    if not m:
        return None
    return ParsedSlug(
        first_polymarket=m.group("away"),
        second_polymarket=m.group("home"),
        local_date=dt.date.fromisoformat(m.group("date")),
    )


def parse_market_slug(slug: str) -> ParsedSlug | None:
    m = _MARKET_SLUG.match(slug or "")
    if not m:
        return None
    return ParsedSlug(
        first_polymarket=m.group("away"),
        second_polymarket=m.group("home"),
        local_date=dt.date.fromisoformat(m.group("date")),
        market_type=m.group("prefix"),
    )


def utc_window(local_date: dt.date, hours: int = 30) -> tuple[dt.datetime, dt.datetime]:
    """UTC window around a Polymarket local date.

    Slug dates are US-local; ESPN stores UTC. A 7:30pm ET tip-off is the next
    day in UTC, so matching on date alone loses those games. The window is
    asymmetric-friendly: from midnight UTC on the slug date to `hours` later,
    which covers every US tip-off time.
    """
    start = dt.datetime.combine(local_date, dt.time.min, tzinfo=dt.timezone.utc)
    return start, start + dt.timedelta(hours=hours)


@dataclass(frozen=True)
class GameOrientation:
    """Which team is actually home, resolved from ESPN — never from the slug."""

    espn_game_id: str
    home_abbrev: str
    away_abbrev: str
    game_date: dt.datetime
    first_is_home: bool          # is the market's quoted side the home team?

    @property
    def first_abbrev(self) -> str:
        return self.home_abbrev if self.first_is_home else self.away_abbrev


def resolve_orientation(*, session, parsed: ParsedSlug) -> GameOrientation | None:
    """Find the ESPN game for a parsed slug and determine true home/away.

    Joins on the **unordered** team pair plus a UTC window (slug dates are
    US-local; evening games cross midnight UTC). Returns None on no match or
    an ambiguous match — a wrong join attaches the wrong outcome to a
    prediction, which is worse than no join at all.
    """
    from sqlalchemy import and_, select

    from core.config import SEASON_TYPE_PRESEASON
    from core.storage import TeamGameLog

    try:
        a, b = parsed.first_espn, parsed.second_espn
    except UnknownTeamError:
        raise

    start, end = utc_window(parsed.local_date)
    rows = session.scalars(
        select(TeamGameLog).where(
            and_(
                TeamGameLog.team_abbrev.in_([a, b]),
                TeamGameLog.opponent_abbrev.in_([a, b]),
                TeamGameLog.is_home.is_(True),
                TeamGameLog.game_date >= start,
                TeamGameLog.game_date < end,
                TeamGameLog.season_type != SEASON_TYPE_PRESEASON,
            )
        )
    ).all()

    if len(rows) != 1:
        return None

    home_row = rows[0]
    return GameOrientation(
        espn_game_id=home_row.espn_game_id,
        home_abbrev=home_row.team_abbrev,
        away_abbrev=home_row.opponent_abbrev,
        game_date=home_row.game_date,
        first_is_home=(home_row.team_abbrev == a),
    )


def orientation_from_scoreboard(
    *, espn_client, dates: list[dt.date]
) -> dict[tuple[frozenset[str], dt.date], GameOrientation]:
    """Build an orientation map for UPCOMING games from ESPN's scoreboard.

    `resolve_orientation` reads `team_game_logs`, which only holds *completed*
    games — so it cannot orient a game that has not been played. Predictions
    are made on upcoming games, hence this second path.

    Keyed by (unordered team pair, UTC date) so it tolerates the slug-order
    inconsistency entirely.
    """
    out: dict[tuple[frozenset[str], dt.date], GameOrientation] = {}
    for day in dates:
        try:
            board = espn_client.get_scoreboard(day.strftime("%Y%m%d"))
        except Exception:
            continue
        for event in board.get("events", []):
            comps = event.get("competitions") or []
            if not comps:
                continue
            competitors = comps[0].get("competitors") or []
            home = next((c for c in competitors if c.get("homeAway") == "home"), None)
            away = next((c for c in competitors if c.get("homeAway") == "away"), None)
            if not home or not away:
                continue
            h = (home.get("team") or {}).get("abbreviation")
            a = (away.get("team") or {}).get("abbreviation")
            if not h or not a:
                continue
            raw_date = event.get("date") or ""
            try:
                game_dt = dt.datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            except ValueError:
                continue
            key = (frozenset({h, a}), game_dt.date())
            out[key] = GameOrientation(
                espn_game_id=str(event.get("id")),
                home_abbrev=h,
                away_abbrev=a,
                game_date=game_dt,
                first_is_home=False,   # caller sets this against its own slug
            )
    return out


def orient_for_slug(
    parsed: ParsedSlug,
    orientation_map: dict[tuple[frozenset[str], dt.date], GameOrientation],
) -> GameOrientation | None:
    """Look up orientation for a slug, trying the slug date and the next UTC day.

    Slug dates are US-local, so a 7:30pm ET game is the following UTC date.
    """
    pair = parsed.espn_pair
    for offset in (0, 1):
        key = (pair, parsed.local_date + dt.timedelta(days=offset))
        found = orientation_map.get(key)
        if found is not None:
            return GameOrientation(
                espn_game_id=found.espn_game_id,
                home_abbrev=found.home_abbrev,
                away_abbrev=found.away_abbrev,
                game_date=found.game_date,
                first_is_home=(found.home_abbrev == parsed.first_espn),
            )
    return None
