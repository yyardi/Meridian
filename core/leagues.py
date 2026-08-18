"""The leagues this system knows about, as an explicit table.

Until now "WNBA" was a fact spread across the codebase in three different
shapes: a slug in `core/config.py`, an ESPN path beside it, a hardcoded regex
in `core/team_mapping.py`, and the literal string in three page headers. None
of them knew about each other, so "which league is this" had four answers and
no single place to change.

Same shape as `core.team_mapping.POLYMARKET_TO_ESPN` and for the same reason:
**an explicit table fails loudly where a derivation fails silently.** Asking
for a league that is not here raises; guessing a slug from a string would
quietly produce an empty board that looks like a quiet night.

What this is not
----------------
This is not a claim that the model works on any of these. The model is fitted,
gated and measured on WNBA alone, and moving it to another league is a
modelling question — new priors, a refitted sigma, a different pace and
possession distribution — not a routing question. `recorded` marks the
difference between *"the plumbing reaches this league"* and *"there is data
here"*, and the dashboard says so in as many words rather than showing an
empty table that reads as a bug.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


class UnknownLeagueError(KeyError):
    """Raised for a league slug that is not in the table.

    Deliberately loud, exactly like `UnknownTeamError`: a silently unknown
    league produces an empty board, and an empty board looks like a quiet
    evening rather than a bug.
    """


@dataclass(frozen=True)
class League:
    """One league, as the venue and ESPN each name it."""

    #: The venue's slug, and the prefix of every event slug in it
    #: (``wnba-ny-chi-2026-08-18``). The join key for everything on the
    #: dashboard.
    slug: str
    #: What the header shows.
    name: str
    #: ESPN's path segment, matching `core.config.ESPNConfig.league_path`.
    espn_path: str
    #: True when snapshots for this league actually exist. False is not a
    #: failure — it is the honest state of a league we are wired for and have
    #: not recorded.
    recorded: bool
    #: Shown in place of an empty table. Says *why* it is empty.
    empty_state: str


LEAGUES: dict[str, League] = {
    "wnba": League(
        slug="wnba",
        name="WNBA",
        espn_path="basketball/wnba",
        recorded=True,
        empty_state="No games recorded yet.",
    ),
    "nba": League(
        slug="nba",
        name="NBA",
        espn_path="basketball/nba",
        recorded=False,
        empty_state=(
            "No NBA data yet — the season starts in October. The recorder, the "
            "board and this page are league-parameterised and will fill in on "
            "their own; the model is a separate question. It is fitted and "
            "gated on WNBA alone, and pointing it at NBA without refitting "
            "would produce numbers, not predictions."
        ),
    ),
}

#: The league the dashboard opens on. Same env var `core.config` already reads,
#: so the two cannot disagree about the default.
DEFAULT_LEAGUE = (os.environ.get("MERIDIAN_LEAGUE") or "wnba").strip().lower()


def get_league(slug: str | None) -> League:
    """Look up a league, or raise. Never guesses."""
    key = (slug or DEFAULT_LEAGUE).strip().lower()
    if key not in LEAGUES:
        raise UnknownLeagueError(
            f"unknown league {slug!r}. Known: {', '.join(sorted(LEAGUES))}. "
            "Add it to core/leagues.py rather than deriving it from a slug."
        )
    return LEAGUES[key]


def default_league() -> League:
    """The configured default, falling back to WNBA if the env names a league
    the table does not have — a bad env var should not take the board down."""
    try:
        return get_league(DEFAULT_LEAGUE)
    except UnknownLeagueError:
        return LEAGUES["wnba"]


def league_of_slug(event_or_market_slug: str | None) -> League | None:
    """The league an event or market slug belongs to, or None.

    Market slugs carry a type prefix (``tsc-wnba-...``); event slugs do not
    (``wnba-...``). Both are matched, longest slug first so a future league
    whose name prefixes another cannot shadow it.
    """
    s = (event_or_market_slug or "").strip().lower()
    if not s:
        return None
    for slug in sorted(LEAGUES, key=len, reverse=True):
        if s.startswith(f"{slug}-") or f"-{slug}-" in s:
            return LEAGUES[slug]
    return None
