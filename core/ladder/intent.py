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


def ticket_for(v, game: str, when: str, attempt_usd: float) -> dict:
    """One fully-formed two-leg order, sized to the attempt budget. qty >= 1.

    Leg 1 is BUY YES on the easier (higher) line at its ask -- the stale side,
    sent first; leg 2 is BUY NO on the harder line at ``1 - bid``, the same
    position as selling YES there. Each leg carries the venue's screen row and
    button (core.ladder.ui); those are best-effort, and a game slug the parser
    cannot read never blocks a ticket.
    """
    no_px = round(1.0 - v.sell_price, 4)
    pair_cost = v.buy_price + no_px               # < 1 whenever E > 0
    qty = max(1, int(attempt_usd // pair_cost))
    qty = min(qty, int(v.size))                   # never more than the smaller displayed side
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
        "cost_usd": round(qty * pair_cost, 4),
        "guaranteed_usd": round(qty * (1.0 - pair_cost), 4),   # = qty * (B - A), gross
        "expected_net_usd": round(qty * v.edge, 4),             # after both fees
    }
