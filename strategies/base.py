"""The one interface a strategy has: rows in, bets out. Pure, no I/O.

ARCHITECTURE.md §4 step 2. Before this, "a strategy" was a dict in
`cfb/run_paper_book.py` consumed by one inline comprehension, and anything else
that wanted to run the same rule re-derived it. The rule and the thing that
runs it were the same three lines, so there was nowhere to stand to ask "what
does this strategy pick" without a database.

The interface is deliberately small enough to have no opinions:

    select(rows) -> list[Bet]

`rows` are priced market rows as the caller already has them -- dicts with at
least `market_slug`, `mtype`, `game_id`, `bid`, `ask`. **No fetching, no
settlement, no fees, no sizing beyond the ticket.** A strategy says WHICH
markets and WHICH SIDE; what a bet is worth afterwards belongs to whoever
settles it, which is how the same registry can serve the paper book (settles
from the venue) and a backtest (settles from a stored tape) without either
knowing about the other.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Bet:
    """One intended position. No P&L here: this is a choice, not an outcome."""

    market_slug: str
    #: 'yes' buys the YES contract at the ask; 'no' buys NO at 1 - bid. Which
    #: TEAM that is depends on the venue's frame for the league and is not this
    #: layer's business -- YES is the away team on nfl/cfb/mlb and the home
    #: team on every other league the venue lists.
    side: str
    #: The price of our side: the ask for 'yes', 1 - bid for 'no'.
    price: float
    #: Dollars at risk. One $1 contract, so equal to `price` for now; kept
    #: separate because a sized strategy changes one of them and not the other,
    #: and collapsing them would hide that.
    stake: float
    game_id: str


def price_of(side: str, bid: float, ask: float) -> float:
    """What our side costs. YES pays the ask; NO pays 1 - bid.

    The single most repeated arithmetic in this codebase and the one most often
    got wrong: pricing NO at `bid` makes every home-side ticket look roughly
    half its real cost.
    """
    return ask if side == "yes" else 1.0 - bid
