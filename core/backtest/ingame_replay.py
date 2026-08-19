"""Replay the live moneyline fair value against the 200ms tick archive.

    python -m core.backtest.ingame_replay
    python -m core.backtest.ingame_replay --min-edge 0.04 --decision-seconds 30

**This is where CLV is real.** The pregame moneyline/spread backtest
(`core.backtest.moneyline`) reports no CLV, and the reason is structural: the
odds history carries one consensus value per game per provider, every row
backfilled after the game ended, so there is no open→close pair to measure
against. The tick archive is the opposite — a genuine time series of the
venue's own book at 200ms, so a price struck at 21:14 and the same market's
price at 22:03 are two observations of one market moving.

What is replayed
----------------
`core.live_fv.fair_value` — the win-curve formula the `/picks` strip renders
and which nothing trades on. Replaying it is the point: the strip carries a
caption saying it is unvalidated, and this is the measurement that caption is
waiting for.

The formula needs a pregame prior, and refuses without one:

    P_live = Phi( (margin + pregame_edge * minutes_left / 40)
                  / (sigma * sqrt(minutes_left)) )

Honesty carried over from the model being replayed
--------------------------------------------------
Every caveat in `core/live_fv.py` applies here and is not re-litigated:

* **Minutes remaining is an estimate.** The ticks carry `event_period` and no
  game clock, so time inside a period is interpolated on wall clock. Only a
  period boundary is exact. Decisions taken where `Clock.usable` is False are
  **skipped**, not approximated — that excludes overtime and unknown periods.
* **Overtime is not regulation** and is excluded by the same rule.
* **The pregame price is the prior.** A market with no pre-live tick is
  skipped rather than defaulted to 0.5: a coin-flip prior on a 0.68/0.30
  matchup is the assumption that made hypothesis #16 look like a 6.8¢ edge
  before the confound check inverted it.

Fills, deliberately pessimistic
-------------------------------
An entry crosses the spread and pays the far touch, and is charged the taker
fee. The executor is limit-only in production, so a resting order would
usually do better — but a resting order also sometimes does not fill, and
"assume the good half of that" is how a replay flatters itself. Crossing is
the conservative floor: whatever edge survives it is not an artifact of the
fill model.

One entry per market, ever. Compounding within a market would turn one
disagreement into a position size, which is a sizing question rather than a
signal question.

The two metrics
---------------
* **Money-at-price** (C11): settle 0/1 at the game's actual result, ROI over
  dollars staked, uncertainty **game-clustered** (C4) because a game's
  moneyline and its spread are the same disagreement seen twice.
* **CLV**: the market's own price a fixed horizon later, against our entry.
  The first draft used the market's LAST observed mid, and that was wrong in a
  way that flattered the result — 87% of those references had effectively
  settled, and the resulting "CLV" correlated **+0.980** with realised P&L. It
  was the outcome restated. A five-minute horizon that must still be in play
  brings that correlation to +0.240 and the mean from +2.45¢ to +0.96¢. An
  entry struck closer to the whistle than the horizon has no CLV and says so.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import logging
import os
import random
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass, field

import structlog
from sqlalchemy import text as sql

from core.backtest.fills import fee_per_contract, pnl_for_contract
from core.live_fv import (
    DEFAULT_SIGMA,
    fair_value,
    minutes_remaining,
    parse_score,
)

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc

MARKET_WINNER = "basketball_team_full_game_winner"

#: The tick archive is local (200ms writes go to local postgres, not the
#: primary). Reading it from the app database returns zero rows and looks like
#: "no data" rather than "wrong database".
LOCAL_TICKS_URL_ENV = "MERIDIAN_LOCAL_DATABASE_URL"
DEFAULT_LOCAL_TICKS_URL = "postgresql+psycopg://meridian:meridian@localhost:5433/meridian"


@dataclass
class Entry:
    """One simulated in-game entry, with everything needed to audit it."""

    event_slug: str
    market_slug: str
    at: dt.datetime
    period: str | None
    score: str
    margin: int
    minutes_left: float
    pregame_price: float
    fair_value: float
    side: str                # 'YES' | 'NO'
    entry_price: float       # cost per contract in the side's own frame
    edge: float
    #: The market's price a fixed horizon LATER, in our side's cost frame, and
    #: None when the entry was struck too close to the end for one to exist.
    #: Never the settled price — see `CLV_HORIZON_SECONDS`.
    reference_price: float | None
    won: bool | None
    pnl: float | None
    fee: float

    @property
    def clv(self) -> float | None:
        """Later price minus entry, in our side's cost frame. Positive means
        the market moved toward us after we struck it.

        None when no mid-game reference exists. That is a real answer: an entry
        struck two minutes before the whistle has no "later price" that is not
        simply the result.
        """
        if self.reference_price is None:
            return None
        return self.reference_price - self.entry_price


@dataclass
class ReplayResult:
    min_edge: float
    decision_seconds: float
    entries: list[Entry] = field(default_factory=list)
    markets_seen: int = 0
    markets_no_pregame: int = 0
    markets_no_usable_clock: int = 0
    markets_unsettled: int = 0

    @property
    def games(self) -> int:
        return len({e.event_slug for e in self.entries})

    @property
    def staked(self) -> float:
        return sum(e.entry_price for e in self.entries if e.pnl is not None)

    @property
    def pnl(self) -> float:
        return sum(e.pnl for e in self.entries if e.pnl is not None)

    @property
    def roi(self) -> float | None:
        return None if self.staked == 0 else self.pnl / self.staked

    @property
    def hit_rate(self) -> float | None:
        scored = [e for e in self.entries if e.won is not None]
        return None if not scored else sum(1 for e in scored if e.won) / len(scored)

    @property
    def entry_cost(self) -> float | None:
        scored = [e for e in self.entries if e.pnl is not None]
        return None if not scored else self.staked / len(scored)

    @property
    def mean_clv(self) -> float | None:
        vals = [e.clv for e in self.entries if e.clv is not None]
        return None if not vals else statistics.mean(vals)

    def clustered_ci(self, attr: str, *, resamples: int = 4000, seed: int = 42):
        """Game-clustered bootstrap on ROI ('roi') or mean CLV ('clv')."""
        by_game: dict[str, list[Entry]] = defaultdict(list)
        for e in self.entries:
            by_game[e.event_slug].append(e)
        keys = sorted(by_game)
        if len(keys) < 2:
            return None
        rng = random.Random(seed)
        out = []
        for _ in range(resamples):
            sample = [by_game[rng.choice(keys)] for _ in keys]
            flat = [e for grp in sample for e in grp]
            if attr == "roi":
                staked = sum(e.entry_price for e in flat if e.pnl is not None)
                pnl = sum(e.pnl for e in flat if e.pnl is not None)
                if staked > 0:
                    out.append(pnl / staked)
            else:
                vals = [e.clv for e in flat if e.clv is not None]
                if vals:
                    out.append(statistics.mean(vals))
        if len(out) < 2:
            return None
        out.sort()
        return out[int(0.025 * len(out))], out[int(0.975 * len(out))]

    def as_dict(self) -> dict:
        roi_ci = self.clustered_ci("roi")
        clv_ci = self.clustered_ci("clv")
        return {
            "min_edge": self.min_edge,
            "decision_seconds": self.decision_seconds,
            "entries": len(self.entries),
            "games": self.games,
            "markets_seen": self.markets_seen,
            "markets_no_pregame_prior": self.markets_no_pregame,
            "markets_no_usable_clock": self.markets_no_usable_clock,
            "markets_unsettled": self.markets_unsettled,
            "staked": round(self.staked, 2),
            "pnl": round(self.pnl, 2),
            "roi": None if self.roi is None else round(self.roi, 4),
            "roi_ci95_game_clustered": None if roi_ci is None else
                [round(roi_ci[0], 4), round(roi_ci[1], 4)],
            "roi_ci_crosses_zero": None if roi_ci is None else bool(roi_ci[0] < 0 < roi_ci[1]),
            "hit_rate": None if self.hit_rate is None else round(self.hit_rate, 4),
            "entry_cost_stake_weighted": None if self.entry_cost is None
                else round(self.entry_cost, 4),
            "mean_clv": None if self.mean_clv is None else round(self.mean_clv, 5),
            "clv_ci95_game_clustered": None if clv_ci is None else
                [round(clv_ci[0], 5), round(clv_ci[1], 5)],
            "clv_ci_crosses_zero": None if clv_ci is None else bool(clv_ci[0] < 0 < clv_ci[1]),
        }


def _ticks_engine(url: str | None = None):
    from core.storage import get_engine
    return get_engine(
        url or os.environ.get(LOCAL_TICKS_URL_ENV) or DEFAULT_LOCAL_TICKS_URL,
        pool_size=2, max_overflow=2,
    )


#: How far after an entry to read the market's own later price for CLV.
#:
#: The first draft used the market's LAST observed mid, which was wrong in a
#: way that flattered the result: 87% of those references sat above 0.95 or
#: below 0.05 — the market had effectively settled — and the resulting "CLV"
#: correlated **+0.980** with realised P&L. That is the outcome restated, not a
#: second and faster-converging measurement, and reporting the two side by side
#: would have implied corroboration where there was only one number.
#:
#: A fixed horizon after entry measures what CLV is for: did the market move
#: toward us before anyone knew the result. An entry struck closer to the end
#: than this simply has no CLV, and says so.
CLV_HORIZON_SECONDS = 300.0


def _reference_mid(live_ticks, *, after: dt.datetime) -> float | None:
    """The mid at least `CLV_HORIZON_SECONDS` after `after`, still in play.

    Returns None rather than falling back to a later or settled price: a
    missing reference is honest, and a substituted one is how the first draft
    came to report the outcome as CLV.
    """
    cutoff = after + dt.timedelta(seconds=CLV_HORIZON_SECONDS)
    for t in live_ticks:
        if t.captured_at < cutoff:
            continue
        mid = (float(t.best_bid) + float(t.best_ask)) / 2.0
        # Still a live market, not a resolved one.
        return mid if 0.02 < mid < 0.98 else None
    return None


_TICKS_SQL = sql("""
    SELECT market_slug, event_slug, captured_at, event_period, event_score,
           is_live, best_bid, best_ask
      FROM market_snapshots
     WHERE sports_market_type = :mtype
       AND best_bid IS NOT NULL AND best_ask IS NOT NULL
     ORDER BY market_slug, captured_at
""")


def replay(
    *,
    min_edge: float = 0.03,
    decision_seconds: float = 30.0,
    sigma: float = DEFAULT_SIGMA,
    ticks_url: str | None = None,
    rows: list | None = None,
) -> ReplayResult:
    """Walk the archive market by market and take at most one entry each.

    `rows` is injectable so the arithmetic can be tested without a database.
    """
    result = ReplayResult(min_edge=min_edge, decision_seconds=decision_seconds)

    if rows is None:
        with _ticks_engine(ticks_url).connect() as c:
            rows = c.execute(_TICKS_SQL, {"mtype": MARKET_WINNER}).all()

    by_market: dict[str, list] = defaultdict(list)
    for r in rows:
        by_market[r.market_slug].append(r)

    for market_slug, ticks in sorted(by_market.items()):
        result.markets_seen += 1
        entry = _replay_one_market(
            ticks, min_edge=min_edge, decision_seconds=decision_seconds,
            sigma=sigma, result=result,
        )
        if entry is not None:
            result.entries.append(entry)
    return result


def _replay_one_market(ticks, *, min_edge, decision_seconds, sigma, result) -> Entry | None:
    pregame = [t for t in ticks if not t.is_live]
    live = [t for t in ticks if t.is_live]
    if not pregame or not live:
        result.markets_no_pregame += 1
        return None

    # The prior: the last price before the game went live, mid of the touch.
    last_pre = pregame[-1]
    pregame_price = (float(last_pre.best_bid) + float(last_pre.best_ask)) / 2.0
    if not (0.0 < pregame_price < 1.0):
        result.markets_no_pregame += 1
        return None

    # The settlement, taken from the LAST live tick's score rather than from a
    # separate table: it is the same frame the market is quoted in, and the
    # archive is the thing being replayed.
    final = parse_score(live[-1].event_score)
    if final is None or final[0] == final[1]:
        result.markets_unsettled += 1
        return None
    yes_won = final[0] > final[1]


    period_first_seen: dict[str, dt.datetime] = {}
    last_decision: dt.datetime | None = None
    saw_usable_clock = False

    for t in live:
        period = (t.event_period or "").upper() or None
        if period and period not in period_first_seen:
            period_first_seen[period] = t.captured_at
        if last_decision is not None and \
                (t.captured_at - last_decision).total_seconds() < decision_seconds:
            continue
        last_decision = t.captured_at

        score = parse_score(t.event_score)
        if score is None:
            continue
        seconds_in = (
            (t.captured_at - period_first_seen[period]).total_seconds()
            if period else 0.0
        )
        clock = minutes_remaining(period, seconds_into_period=seconds_in)
        if not clock.usable:
            continue
        saw_usable_clock = True

        fv = fair_value(
            margin=score[0] - score[1], minutes_left=clock.minutes_left,
            pregame_price=pregame_price, sigma=sigma,
        )
        if fv is None:
            continue

        bid, ask = float(t.best_bid), float(t.best_ask)
        if not (0.0 < bid <= ask < 1.0):
            continue

        # Crossing costs the far touch. YES pays the ask; NO pays 1 - bid.
        yes_cost, no_cost = ask, 1.0 - bid
        edge_yes, edge_no = fv - yes_cost, (1.0 - fv) - no_cost
        reference_mid = _reference_mid(live, after=t.captured_at)
        if edge_yes >= edge_no:
            side, cost, edge = "YES", yes_cost, edge_yes
            ref = reference_mid
            won = yes_won
        else:
            side, cost, edge = "NO", no_cost, edge_no
            ref = None if reference_mid is None else 1.0 - reference_mid
            won = not yes_won
        if edge < min_edge or not (0.0 < cost < 1.0):
            continue

        return Entry(
            event_slug=t.event_slug or "", market_slug=t.market_slug, at=t.captured_at,
            period=period, score=t.event_score or "?", margin=score[0] - score[1],
            minutes_left=clock.minutes_left, pregame_price=pregame_price,
            fair_value=fv, side=side, entry_price=cost, edge=edge,
            reference_price=ref, won=won, pnl=pnl_for_contract(cost, won),
            fee=fee_per_contract(cost, is_maker=False),
        )

    if not saw_usable_clock:
        result.markets_no_usable_clock += 1
    return None


def _print(result: ReplayResult) -> None:
    d = result.as_dict()
    print("\nIN-GAME MONEYLINE REPLAY — 200ms archive, formula FV")
    print("=" * 72)
    print(f"markets seen {d['markets_seen']} · entries {d['entries']} "
          f"across {d['games']} games")
    print(f"  skipped: {d['markets_no_pregame_prior']} no pregame prior · "
          f"{d['markets_no_usable_clock']} no usable clock · "
          f"{d['markets_unsettled']} unsettled")
    if not d["entries"]:
        print("\nNo entries at this threshold. That is a result, not an error.")
        return
    print(f"\nmoney-at-price  ROI {d['roi']:+.2%}   CI {d['roi_ci95_game_clustered']}"
          f"  crosses zero: {d['roi_ci_crosses_zero']}")
    print(f"  hit {d['hit_rate']:.1%} @ entry cost {d['entry_cost_stake_weighted']:.3f}"
          "   (the hit rate's own breakeven)")
    print(f"\nCLV             mean {d['mean_clv']:+.4f}   CI {d['clv_ci95_game_clustered']}"
          f"  crosses zero: {d['clv_ci_crosses_zero']}")
    print(f"  reference = the market's own mid {CLV_HORIZON_SECONDS:.0f}s later, "
          "still in play — never the settled price")


def main() -> int:
    p = argparse.ArgumentParser(prog="meridian-ingame-replay")
    p.add_argument("--min-edge", type=float, default=0.03)
    p.add_argument("--decision-seconds", type=float, default=30.0)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    logging.basicConfig(format="%(message)s", stream=sys.stderr, level=logging.WARNING)
    import core.storage  # noqa: F401

    result = replay(min_edge=args.min_edge, decision_seconds=args.decision_seconds)
    if args.json:
        print(json.dumps(result.as_dict(), indent=2))
    else:
        _print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
