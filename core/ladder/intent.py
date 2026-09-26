"""The ticket: one violation turned into two exact legs, and the two filters.

Moved out of `cfb/run_ladder_executor.py` because the dashboard renders the
same ticket for a live violation and the api image COPYs core/ and not cfb/.
The executor imports these back, so the ticket it writes to the intents file
and the one the ARB tab previews are built by one function -- a ticket that
looked different on the two screens would be a wrong-button failure waiting
for a tired operator.

The shape is the executor's intent minus the two stamps (`placed_by`,
`meridian_placed`) that say who placed it; the executor adds those in its own
source, where the test that pins "Meridian places nothing" can read them.

PLACES NOTHING. Arithmetic on a `Violation` and the screen words from
`core.ladder.ui`; no client, no file, no network.
"""
from __future__ import annotations

from core.ladder.ui import ui_wording

#: Registered in docs/math/ladder-fill-test.md: the money and the minutes are
#: on the mid-ladder; liquid pairs break for ~30s and pennies.
MID_LADDER = (3.5, 20.5)


def is_mid(v) -> bool:
    return all(MID_LADDER[0] <= abs(x) <= MID_LADDER[1] for x in (v.high_line, v.low_line))


def is_spread_pair(v) -> bool:
    """Both legs must be spread rungs. The winner market (line 0) is excluded:
    an NFL tie settles the Winner contract at $0.50 while a spread still
    settles 0/1, and a postponed game settles every leg at last fair market
    price -- either breaks the >= $1 guarantee (reviewer's H4, 2026-09-18)."""
    return 0.0 not in (float(v.high_line), float(v.low_line))


#: The TICKET gate, operator-sized (2026-09-26). The operator tests with about
#: $20 a pair, and asked why a $25 floor stood in the way: that floor is edge x
#: the FULL displayed size, a statistic about what the venue showed, never
#: about anyone's bankroll. A crossing is a ticket when the THIN leg displays
#: at least the contracts the attempt buys and the edge is worth crossing for.
#: $25 stays the ledger's statistic (core/ladder/tape.DEFAULT_FLOOR_USD).
DEFAULT_ATTEMPT_USD = 20.0
#: Net of both fees, per contract. Below this a one-tick nudge on either leg
#: is the whole edge.
DEFAULT_MIN_EDGE = 0.02


def pair_cost(v) -> float:
    """What one contract of the pair costs up front: the buy leg's ask plus
    the NO side of the sell leg (1 - bid). Under $1 whenever the gross edge
    is positive; the pair pays $1 at settlement."""
    return round(v.buy_price + round(1.0 - v.sell_price, 4), 4)   # to the tick: 0.41 + 0.47 is 0.88, not 0.8799999


def qty_for(v, attempt_usd: float) -> int:
    """Contracts the attempt buys of this pair, at least one."""
    return max(1, int(attempt_usd // pair_cost(v)))


def clears_ticket_gate(v, attempt_usd: float = DEFAULT_ATTEMPT_USD,
                       min_edge: float = DEFAULT_MIN_EDGE) -> bool:
    """The thin leg shows at least the attempt's contracts, and the net edge
    is at least ``min_edge``. The edge is rounded to a hundredth of a cent
    first: 0.0199999 is 2.00c, not a refusal (round to tick before comparing)."""
    return round(v.edge, 4) >= min_edge and int(v.size) >= qty_for(v, attempt_usd)


def ticket_for(v, game: str, when: str, attempt_usd: float) -> dict:
    """One fully-formed two-leg order, sized to the attempt budget. qty >= 1.

    Leg 1 is BUY YES on the easier (higher) line at its ask -- the stale side,
    sent first; leg 2 is BUY NO on the harder line at ``1 - bid``, the same
    position as selling YES there. Each leg carries the venue's screen row and
    button (core.ladder.ui); those are best-effort, and a game slug the parser
    cannot read never blocks a ticket.
    """
    no_px = round(1.0 - v.sell_price, 4)
    cost = pair_cost(v)                           # < 1 whenever E > 0
    qty = min(qty_for(v, attempt_usd), int(v.size))   # never more than the smaller displayed side
    try:
        row1, btn1 = ui_wording(game, v.high_line, "BUY YES")
        row2, btn2 = ui_wording(game, v.low_line, "BUY NO")
    except ValueError:
        row1 = btn1 = row2 = btn2 = None
    return {
        "ts": when, "game": game,
        "leg1": {"market_line": v.high_line, "side": "BUY YES", "price": round(v.buy_price, 4), "qty": qty,
                 "screen_row": row1, "screen_button": btn1},
        "leg2": {"market_line": v.low_line, "side": "BUY NO", "price": no_px, "qty": qty,
                 "screen_row": row2, "screen_button": btn2},
        "displayed_size": v.size, "edge_c": round(v.edge * 100, 2),
        "cost_usd": round(qty * cost, 4),
        "guaranteed_usd": round(qty * (1.0 - cost), 4),   # = qty * (B - A), gross
        "expected_net_usd": round(qty * v.edge, 4),             # after both fees
    }
