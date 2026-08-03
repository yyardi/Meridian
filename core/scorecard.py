"""Is the live model beating the market? The ANCHOR gate, read honestly.

Every other route waits on this number, so it is worth getting the counting
right. Three ways it has already been got wrong here:

**Hit rate is not a bet.** The results page once reported 84% by asking "was
the probability on the correct side of 0.50". Most contracts are lopsided, so
that is nearly free. The real bet win rate over the same rows was 38.5%, and
243 rows flagged "correct" were losing positions. A bet exists only where the
model disagreed with the market; the side is which way it disagreed.

**Rows are not the sample.** A prediction is logged every run, so one market
accumulates ~26 identical rows before it settles, and one game has ~18 markets.
"468 resolved predictions" was one game. This dedupes to the last prediction
per market and reports `n_games` everywhere.

**Ladder rungs are not independent.** Eighteen markets on one game are one
opinion expressed eighteen times, all resolving off the same final score.
Intervals are therefore clustered by game — the row-level interval is wrong by
roughly sqrt(rows per game), which was measured to turn a nominal 95% interval
into 11% real coverage.

What passing looks like
-----------------------
Pre-registered, and the second matters more than the first:

* `bet_win_rate` above 0.524 with a game-clustered CI excluding it, and
* `brier_model < brier_market` — the model forecasting better than the thing
  it is betting against.

A model can clear the first on luck. Clearing the second means it is adding
information, which is the claim that has to be true for any of this to work.

    python -m core.scorecard
    python -m core.scorecard --version v4
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.quote.adverse_selection import clustered_mean
from core.storage import Prediction, get_engine, get_sessionmaker

log = structlog.get_logger(__name__)

#: A -110 two-way market needs this to break even.
BREAKEVEN = 0.524

#: Below this the sample cannot support a verdict. Games, not rows.
MIN_GAMES = 10

#: Model and market this close is not a disagreement, so it is not a bet.
NO_BET_TOLERANCE = 0.02


@dataclass(frozen=True)
class Settled:
    """One market's final prediction, deduped from its repeated logs."""

    event_slug: str
    market_slug: str
    market_type: str
    model: float
    market: float
    outcome: int

    @property
    def is_bet(self) -> bool:
        return abs(self.model - self.market) >= NO_BET_TOLERANCE

    @property
    def bet_side(self) -> str | None:
        if not self.is_bet:
            return None
        return "YES" if self.model > self.market else "NO"

    @property
    def bet_won(self) -> bool | None:
        side = self.bet_side
        if side is None:
            return None
        return (self.outcome == 1) if side == "YES" else (self.outcome == 0)


def load_settled(session: Session, *, model_version: str | None = None) -> list[Settled]:
    """One row per market: its LAST prediction before settlement.

    Deduped because a market is re-predicted every run and the repeats carry no
    new information — counting them inflates the apparent sample by whatever
    the logging cadence happens to be.
    """
    stmt = (
        select(
            Prediction.event_slug,
            Prediction.market_slug,
            Prediction.sports_market_type,
            Prediction.model_probability,
            Prediction.market_mid,
            Prediction.resolved_outcome,
            Prediction.predicted_at,
        )
        .where(Prediction.resolved_outcome.is_not(None))
        .where(Prediction.market_mid.is_not(None))
        .where(Prediction.model_probability.is_not(None))
        .order_by(Prediction.predicted_at)
    )
    if model_version:
        stmt = stmt.where(Prediction.model_version == model_version)

    latest: dict[str, Settled] = {}
    for ev, mk, typ, model, market, outcome, _at in session.execute(stmt).all():
        latest[mk] = Settled(
            event_slug=ev or mk,
            market_slug=mk,
            market_type=(typ or "").replace("basketball_team_full_game_", ""),
            model=float(model),
            market=float(market),
            outcome=int(outcome),
        )
    return list(latest.values())


def score(rows: list[Settled]) -> dict:
    """Bet win rate and Brier comparison, both clustered by game."""
    games = {r.event_slug for r in rows}
    bets = [r for r in rows if r.is_bet]

    wins_by_game: dict[str, list[float]] = defaultdict(list)
    for r in bets:
        wins_by_game[r.event_slug].append(1.0 if r.bet_won else 0.0)

    # Brier difference per row, clustered: positive = model beat the market.
    edge_by_game: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        edge_by_game[r.event_slug].append(
            (r.market - r.outcome) ** 2 - (r.model - r.outcome) ** 2
        )

    win = clustered_mean(dict(wins_by_game)) if wins_by_game else None
    brier_edge = clustered_mean(dict(edge_by_game)) if edge_by_game else None

    n = len(rows)
    return {
        "n_markets": n,
        "n_games": len(games),
        "n_bets": len(bets),
        "n_no_bet": n - len(bets),
        "win": win,
        "brier_model": sum((r.model - r.outcome) ** 2 for r in rows) / n if n else None,
        "brier_market": sum((r.market - r.outcome) ** 2 for r in rows) / n if n else None,
        "brier_edge": brier_edge,
    }


def format_report(rows: list[Settled], *, label: str) -> str:
    out: list[str] = []
    add = out.append
    s = score(rows)

    add(f"ANCHOR SCORECARD — {label}")
    add("=" * 76)
    add(f"markets settled : {s['n_markets']}   across {s['n_games']} GAMES")
    add(f"real bets       : {s['n_bets']}   ({s['n_no_bet']} rows had no disagreement)")
    add("")

    if not rows:
        add("NO DATA — nothing has settled under this version yet.")
        return "\n".join(out)

    win = s["win"]
    add("BET WIN RATE  (clustered by game)")
    if win is not None:
        add(f"  {win.mean:.3f}  [{win.lo:.3f}, {win.hi:.3f}]   breakeven {BREAKEVEN}")
        verdict = (
            "clears breakeven" if win.lo > BREAKEVEN
            else "below breakeven" if win.hi < BREAKEVEN
            else "straddles breakeven"
        )
        add(f"  -> {verdict}")
    else:
        # Say it rather than omit the section. A missing number reads as "fine"
        # and this project has already lost 2.5 hours to something that
        # reported nothing and looked healthy.
        raw = [r for r in rows if r.is_bet]
        point = sum(1 for r in raw if r.bet_won) / len(raw) if raw else float("nan")
        add(f"  point estimate {point:.3f} on {len(raw)} bets — NO INTERVAL.")
        add("  A game-clustered interval needs at least 2 games; there is 1.")
        add("  The point estimate is shown so it is not mistaken for missing data,")
        add("  and it is worth nothing on its own.")
    add("")

    add("FORECAST QUALITY  (Brier, lower is better)")
    add(f"  model  {s['brier_model']:.4f}")
    add(f"  market {s['brier_market']:.4f}")
    be = s["brier_edge"]
    if be is not None:
        add(f"  model - market edge: {be.mean:+.4f}  [{be.lo:+.4f}, {be.hi:+.4f}]")
        if be.lo > 0:
            add("  -> the model beats the market, and the interval excludes zero.")
        elif be.hi < 0:
            add("  -> the MARKET beats the model, and the interval excludes zero.")
        else:
            add("  -> indistinguishable at this sample.")
    add("")

    add("VERDICT")
    add("-" * 76)
    if s["n_games"] < MIN_GAMES:
        add(f"  NO VERDICT — {s['n_games']} games against a minimum of {MIN_GAMES}.")
        add("  Rows are not the sample. One market is re-predicted every run and one")
        add("  game carries ~18 markets, so a few hundred settled rows can be a single")
        add("  game. Any interval read now is noise wearing a confidence band.")
    elif win is not None and win.lo > BREAKEVEN and be is not None and be.lo > 0:
        add("  PASS — beats breakeven AND out-forecasts the market, both intervals")
        add("  excluding their thresholds, clustered by game.")
    elif win is not None and win.hi < BREAKEVEN:
        add("  FAIL — the whole interval sits below breakeven.")
    else:
        add("  INCONCLUSIVE — the sample is large enough but the intervals straddle.")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(prog="meridian-scorecard")
    parser.add_argument("--version", type=str, default=None,
                        help="model_version to score, e.g. v4 (default: all)")
    args = parser.parse_args()

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.WARNING)
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))

    Session = get_sessionmaker(get_engine())
    with Session() as session:
        rows = load_settled(session, model_version=args.version)
    print(format_report(rows, label=args.version or "all versions"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
