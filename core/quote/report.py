"""Scoring for the QUOTE shadow run. Money at price, games not rows.

    python -m core.quote.report

Reads `shadow_quote_fills`, scores every SETTLED fill to settlement, and
reports per regime behind the pre-registered floors
(docs/math/quote-shadow.md — registered before the engine's first cycle;
the floors and metrics here may not drift from that document).

The accounting, and the one frame conversion in it
--------------------------------------------------
A filled **bid** is a unit long YES at `quote_price`: staked = price,
returned = settlement (1 or 0). A filled **ask** is a unit short YES — which
on this venue IS the NO side at its complementary price (V14): staked =
`1 − price`, returned = `1 − settlement`. That is C11's money-at-price rule
applied to both sides of a quote; a flat win rate appears nowhere in this
module because most quotes are away from 50¢ and C11 retired that number.

Clustering is by game (C4): one game's ladder emits hundreds of correlated
fills, and the row-level interval would be wrong by roughly the square root
of that. The clustered machinery is imported from the adverse-selection
study, not reimplemented.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import text

from core.quote.adverse_selection import ClusteredMean, clustered_mean
from core.quote.storage import ASK, BID

#: Pre-registered floors (docs/math/quote-shadow.md, fixed 2026-08-09 before
#: the first cycle). Below either, the report prints NO DATA with counts only.
FLOOR_FILLS = 500
FLOOR_GAMES = 10


def score_fill(*, side: str, quote_price: float, settlement: int) -> tuple[float, float]:
    """(staked, returned) for one settled fill, in dollars per contract."""
    if side == BID:
        return quote_price, float(settlement)
    if side == ASK:
        return 1.0 - quote_price, 1.0 - float(settlement)
    raise ValueError(f"unknown side {side!r}")


def net_capture_mark(*, side: str, quote_price: float, mid_at_fill: float) -> float:
    """The static study's mark, for comparability: value at fill minus cost.

    Bid: long at `quote_price`, marked at `mid_at_fill`. Ask: short at
    `quote_price`, marked at `mid_at_fill`. Same decomposition as
    `adverse_selection.QuoteWindow.net_bid/net_ask`.
    """
    if side == BID:
        return mid_at_fill - quote_price
    if side == ASK:
        return quote_price - mid_at_fill
    raise ValueError(f"unknown side {side!r}")


@dataclass
class RegimeReport:
    regime: str
    n_fills: int
    n_settled: int
    n_games: int
    staked: float
    returned: float
    roi_clustered: ClusteredMean | None
    capture_clustered: ClusteredMean | None

    @property
    def at_floor(self) -> bool:
        return self.n_settled >= FLOOR_FILLS and self.n_games >= FLOOR_GAMES

    @property
    def verdict(self) -> str:
        if not self.at_floor:
            return "NO DATA"
        cm = self.roi_clustered
        if cm is None:
            return "NO DATA"
        if cm.mean > 0 and cm.lo > 0:
            return "PASS (upper bound — see the fill-rule caveat)"
        return "FAIL"


def build_report(session) -> dict[str, RegimeReport]:
    rows = session.execute(text("""
        SELECT regime, side, game_id, quote_price, mid_at_fill, settlement
        FROM shadow_quote_fills
    """)).all()

    by_regime: dict[str, list] = defaultdict(list)
    for r in rows:
        by_regime[r.regime].append(r)

    out: dict[str, RegimeReport] = {}
    for regime, fills in by_regime.items():
        roi_by_game: dict[str, list[float]] = defaultdict(list)
        cap_by_game: dict[str, list[float]] = defaultdict(list)
        staked = returned = 0.0
        n_settled = 0
        for f in fills:
            cap_by_game[f.game_id].append(net_capture_mark(
                side=f.side, quote_price=float(f.quote_price),
                mid_at_fill=float(f.mid_at_fill)))
            if f.settlement is None:
                continue
            cost, ret = score_fill(side=f.side, quote_price=float(f.quote_price),
                                   settlement=int(f.settlement))
            if cost <= 0:
                continue
            staked += cost
            returned += ret
            roi_by_game[f.game_id].append(ret / cost - 1.0)
            n_settled += 1
        out[regime] = RegimeReport(
            regime=regime,
            n_fills=len(fills),
            n_settled=n_settled,
            n_games=len({f.game_id for f in fills if f.settlement is not None}),
            staked=staked,
            returned=returned,
            roi_clustered=clustered_mean(roi_by_game),
            capture_clustered=clustered_mean(cap_by_game),
        )
    return out


def format_report(reports: dict[str, RegimeReport]) -> str:
    out: list[str] = []
    add = out.append
    add("QUOTE SHADOW RUN — settlement-scored, money at price (C11), by game (C4)")
    add("=" * 78)
    add(f"floors (pre-registered): >= {FLOOR_FILLS} settled fills AND "
        f">= {FLOOR_GAMES} games per regime")
    add("")
    if not reports:
        add("NO DATA — no fills recorded. The engine has not run against a live")
        add("stream, which is different from running and finding nothing.")
        return "\n".join(out)

    for regime in sorted(reports):
        r = reports[regime]
        add(f"[{regime}]")
        add(f"  fills recorded / settled     : {r.n_fills:,} / {r.n_settled:,}")
        add(f"  distinct games (settled)     : {r.n_games}")
        if not r.at_floor:
            add(f"  VERDICT: NO DATA — floors are {FLOOR_FILLS} fills / "
                f"{FLOOR_GAMES} games. Counts only; no performance number is")
            add("  printed below a floor, and that is the registration, not shyness.")
            add("")
            continue
        add(f"  staked -> returned           : ${r.staked:,.2f} -> ${r.returned:,.2f}")
        cm = r.roi_clustered
        if cm is not None:
            add(f"  per-fill ROI, clustered      : {cm.mean:+.4f}  "
                f"95% CI [{cm.lo:+.4f}, {cm.hi:+.4f}]  (G={cm.n_clusters})")
        cap = r.capture_clustered
        if cap is not None:
            add(f"  net capture at fill (static-study mark): {cap.mean * 100:+.2f}c "
                f"[{cap.lo * 100:+.2f}, {cap.hi * 100:+.2f}]")
        add(f"  VERDICT: {r.verdict}")
        add("")
    add("Fill-rule caveat (inherited from the study): transient dips that fill")
    add("and recover are invisible, so losses are trustworthy and profits are")
    add("upper bounds. A PASS here reopens a question; it authorises nothing.")
    return "\n".join(out)


def main() -> int:
    from core.storage import get_engine, get_sessionmaker

    Session = get_sessionmaker(get_engine())
    with Session() as s:
        print(format_report(build_report(s)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
