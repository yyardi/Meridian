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
    "nfl": League(
        slug="nfl",
        name="NFL",
        espn_path="football/nfl",
        # GRIDIRON records NFL live from 2026-09-02 (077c0b9); shadow_quote_fills
        # is mixed-league from there on. This entry is the SLUG-ROUTING table
        # only (league_of_slug + the dashboard + the paper wallet routing an NFL
        # fill to the GRIDIRON ledger). GRIDIRON's modelling registrations —
        # cohorts, saturation, gates — live in its OWN registry (docs/gridiron/),
        # not here; adding the slug here does not import any NFL constant.
        recorded=True,
        empty_state=(
            "No NFL games recorded yet — GRIDIRON's board fills on the first "
            "slate (first game 2026-09-09). The model is a separate question: "
            "NFL is an unmeasured domain, maker-only descriptive-first, no "
            "ported constants."
        ),
    ),
    "cfb": League(
        slug="cfb",
        name="College Football",
        espn_path="football/college-football",
        recorded=True,
        empty_state=(
            "No CFB games recorded yet. Recording started 2026-09-03 ahead of "
            "the Sept 5 slate — ~100 games in a single Saturday against NFL's "
            "16 a week. Recording only: no model, no constants, no gates. "
            "GRIDIRON covers NFL and CFB; the modelling attention is NFL's."
        ),
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
    the table does not have — a bad env var should not take the board down.

    **DISPLAY ONLY. Engines must use `strict_default_league()`.** See its
    docstring: this fallback is correct for a dashboard and dangerous for a
    writer.
    """
    try:
        return get_league(DEFAULT_LEAGUE)
    except UnknownLeagueError:
        return LEAGUES["wnba"]


def strict_default_league() -> League:
    """The configured default, RAISING on an unknown league. For any process
    that WRITES.

    Why the two forms differ (2026-09-03, learned by shipping the bug): a
    dashboard that falls back to WNBA on a bad env var shows the wrong board
    and someone notices. **An ENGINE that falls back becomes a SECOND WNBA
    QUOTER** — it collides on WNBA's heartbeat row, writes WNBA rows under a
    different engine_commit, and thereby breaks the single-engine-identity
    assertion that amendment 12 exists to guarantee. It announced itself as
    `league=wnba` in its own startup line and was caught only because a human
    read that line.

    The file's own opening argument applies to itself: *an explicit table
    fails loudly where a derivation fails silently* — and a silent fallback
    is a derivation wearing a table's clothes.
    """
    return get_league(DEFAULT_LEAGUE)


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
