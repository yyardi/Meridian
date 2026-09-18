"""Translate a ladder leg into the words on the venue's screen.

The scanner and the executor work in the SLUG frame: every spread market
`asc-<league>-<A>-<B>-<date>-(neg|pos)-Npt5` has one YES contract, and YES
pays iff  A's score + line > B's score  (A is the slug's first team; verified
on settled markets, and again 2026-09-18 on DET-BUF: `pos-13pt5` settled 1
with Detroit losing by 10).

The venue's SCREEN frames the same market from the side that is laying the
points, as one row with a Yes/No pair:

    neg-3pt5   "MIA to win by over 3.5 points"     Yes = MIA -3.5 = our YES
    pos-10pt5  "WAKE to win by over 10.5 points"   Yes = WAKE -10.5 = our NO

(The venue's own `title`/`titleShort` for pos-10pt5 read "Demon Deacons wins
by over 10.5 points" / "WAKE -10.5" while its `question` reads "Will the
Miami (FL) cover 10.5" and the book prices the Miami +10.5 side at 0.98 --
the row is the favourite's, the priced contract is the underdog's.)

So a ticket that says "BUY YES line +10.5" must tell the operator: row
"WAKE to win by over 10.5 points", tap **No**. Getting this wrong is the
"wrong button" failure the fill-test protocol names, and it is the one
mistake a person at a phone cannot see.
"""
from __future__ import annotations

import re

_GAME = re.compile(r"^(?P<league>[a-z0-9]+)-(?P<a>.+?)-(?P<b>[^-]+)-(?P<date>\d{4}-\d{2}-\d{2})$")


def teams_of(game: str) -> tuple[str, str]:
    """('MIA', 'WAKE') from 'cfb-mia-wake-2026-09-18'. Upper-case codes as the
    screen shows them; the first is the slug's YES team."""
    m = _GAME.match(game.replace("aec-", "", 1))
    if not m:
        raise ValueError(f"cannot read teams from game {game!r}")
    return m.group("a").upper(), m.group("b").upper()


def ui_wording(game: str, line: float, side: str) -> tuple[str, str]:
    """(row text, button) for buying `side` ('BUY YES' | 'BUY NO') on `line`
    in the slug frame. The winner market (line 0) is never a ticket leg."""
    a, b = teams_of(game)
    n = abs(float(line))
    if n == 0:
        raise ValueError("the winner market is not a spread row")
    want_yes = side.upper().endswith("YES")
    if line < 0:                       # row belongs to the first team laying points
        return f"{a} to win by over {n:g} points", ("Yes" if want_yes else "No")
    return f"{b} to win by over {n:g} points", ("No" if want_yes else "Yes")   # row belongs to the second team
