"""Hypothesis #17 — does a tight game's moneyline revert toward 50/50?

REGISTERED 2026-08-08T02:19Z. NOTHING HAS BEEN COMPUTED.
=========================================================
This module is a **pre-registration only**. It contains no analysis, and it
must not be given any until the gate below is met. It was written while
GS-DAL (2026-08-08) was still in progress and **before that game's Q4
resolved**.

Games recorded *before* this timestamp may be used — the hypothesis was stated
before tonight's Q4 played out, which is the property that matters. What is
forbidden is looking at a number and then adjusting anything below.


The hypothesis, from the operator
----------------------------------
> *"won a fourth quarter ml on phx cuz i saw it was extremely tight and phx
> suddenly dropped to 33 from 50, bought, sold 45... dallas-gsv is tight so
> deviation shud return to 50/50, buy either side below 35, sell at 50."*
> — 2026-08-08T02:19Z

In a **tight** game — small boxscore margin — a live moneyline that has
deviated far from 50/50 reverts toward it.


PRE-REGISTERED GATE — fixed before any number was computed
----------------------------------------------------------
Trigger, exit and bar, all fixed here on 2026-08-08:

    TRIGGER   during Q4, boxscore margin <= 3 points, and the moneyline mid
              for either side <= 0.35. The cheap side is bought.
    ENTRY     maker only: a resting limit buy at the touch, filled only when
              the book trades through it on a LATER tick (core/pulse/replay.py).
              Unfilled after 2 minutes it is cancelled and is not a trade.
    EXIT      the first of: mid reaches 0.50, or settlement (0 or 1).
    P&L       net of costs, in the position's own frame.

    PASS  requires ALL of:
      (1) mean net P&L per filled trade > 0
      (2) its 95% CI, clustered by game, lies entirely above 0
      (3) n >= 30 filled trades
      (4) across >= 15 DISTINCT GAMES

    FAIL  if (3) and (4) are met but (1) or (2) is not.
    NO DATA  if (3) or (4) is not met.

**15 games, per the operator's own policy of 2026-08-08** — this is the first
hypothesis registered under it. See the gate policy in
`docs/pulse-hypotheses.md`.


THE ANCHORING CHECK, AND WHY IT IS INSIDE THE GATE
---------------------------------------------------
**This is the part that would otherwise repeat correction C12, and it is
mandatory rather than advisory.**

"Reverts toward 50/50" assumes 50/50 is where a tight game belongs. It is not.
A tight game between a strong team and a weak one should *not* be priced 50/50
— the market conditions on who is playing, and a 0.33 price on a tight game
may be exactly right. Hypothesis #16 passed its gate at +6.84c by comparing a
team-blind base rate against a team-aware price, and inverted to -2.20c the
moment the base rate was anchored on the pregame price.

The ledger's standing rule, written after #16: *any hypothesis of the form
"the market disagrees with a reference level" must carry the anchoring check
inside its gate, written before it runs.* So:

    CO-PRIMARY, and a PASS requires it too:
      (5) the same statistic, computed against a PREGAME-ANCHORED reversion
          target instead of 0.50, must also satisfy (1) and (2).

The anchored target is the live win probability implied by carrying the
pregame moneyline forward at the observed margin — `anchored_probability` in
core/pulse/win_curve.py, the same function the #16 control used.

If the effect exists only against the flat 0.50 anchor and vanishes against
the pregame-anchored one, **that is a FAIL, not a partial pass.** It would mean
the strategy is buying underdogs in close games and calling their price wrong
because a coin-flip anchor says so.


HONEST CROSS-REFERENCES
------------------------
**#1 run overreaction — FAILED, gated, 2026-08-06.** 444 runs / 11 games,
reversion -0.32c at +5 min against a 6c round trip. That killed *price-move*
triggered reversion: a price that lurched does not come back.

The operator's own anecdote contains **both** a state condition ("extremely
tight") and a price-move condition ("suddenly dropped to 33 from 50"). The
price-move half is the part #1 already tested and killed. **#17 registers only
the state-conditioned half**, which is untested: the trigger is the boxscore,
not the size or speed of a price change. A future variant that re-adds "and
the price moved N cents recently" is re-opening #1 and needs its own
registration and a reason why #1 does not already answer it.

**#16 trailing-team ML underpricing — PASSED and NOT TRADABLE, 2026-08-07.**
Same market, same game states, and the reason condition (5) exists.

**#5 Q4 tight-game moneyline** is the same neighbourhood and remains not built
— it is about violent repricing, and it is blocked behind adverse selection,
which FAILED. #17 does not unblock it.


WHAT COULD MAKE THIS UNTRADABLE EVEN IF IT PASSES
--------------------------------------------------
Recorded now so it is not discovered as a surprise later:

* **Q4 is where spreads blow out** (V4: 3.1% of live ticks exceed 10c, 0.6%
  exceed 25c, and Q4's p90 spread is fatter than Q1-Q3's). A 0.35 mid in a
  tight Q4 may not be a transactable 0.35.
* **Adverse selection FAILED** at -2.66c per filled quote. A resting maker bid
  in a tight Q4 is filled precisely when the game turns against it.
* Depth at the touch is thin (V1), and 0.35 is in the band where it is
  thinnest.

None of these are reasons not to test it. They are reasons the P&L bar is net
of costs and the fills are earned rather than assumed.


    python -m core.pulse.tight_game_reversion     # refuses until implemented
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from dataclasses import dataclass

from core.backtest.fills import fee_per_contract
from core.pulse.replay import Order, ReplayContext, Tick, load_ticks, replay_game
from core.pulse.win_curve import RULE_OF_THUMB_SIGMA, anchored_probability
from core.quote.adverse_selection import clustered_mean

#: The moneyline market type this hypothesis is about.
MARKET_MONEYLINE = "basketball_team_full_game_winner"

#: WNBA quarter length, for the minutes-left approximation only.
QUARTER_MINUTES = 10.0

#: Fixed 2026-08-08. Changing any of these after seeing a number is the
#: re-tuning the ledger's preamble forbids.
REGISTERED_AT = dt.datetime(2026, 8, 8, 2, 19, tzinfo=dt.timezone.utc)

#: Trigger.
MAX_MARGIN = 3                  # boxscore points, absolute
MAX_ENTRY_MID = 0.35            # buy the side quoted at or below this
TRIGGER_PERIOD = "Q4"

#: Exit.
EXIT_MID = 0.50                 # or settlement, whichever comes first

#: Entry patience, inherited from overreaction.RUN_MINUTES rather than invented.
ENTRY_PATIENCE_MINUTES = 2.0

# -- the gate --------------------------------------------------------- #
GATE_MIN_TRADES = 30
GATE_MIN_GAMES = 15             # the operator's 2026-08-08 policy


# ===================================================================== #
# IMPLEMENTATION — added 2026-08-18. Nothing above this line changed.
# ===================================================================== #
#
# Every constant in the gate above is byte-identical to the 2026-08-08
# registration. What follows implements it and adds no parameter of its own
# that the trigger, exit or bar depends on.
#
# THREE THINGS THE REGISTRATION DID NOT SPECIFY, decided here and recorded
# because a later reader must be able to tell an implementation choice from a
# re-tuned parameter:
#
# 1. ONE POSITION AT A TIME PER MARKET. The trigger is a tick-level condition
#    that stays true for thousands of consecutive 200ms ticks — 53,581 of them
#    across the archive. Opening one position per qualifying tick would be
#    absurd, and "unfilled after 2 minutes it is cancelled" already implies a
#    single working order. So: a market that is flat and has no working order
#    may place one; after an exit it may trigger again.
#
# 2. EXIT CROSSES THE SPREAD. "Exit at 0.50" is reached when the MID reaches
#    the target, and the exit fill is taken at the far touch — a long YES sells
#    at the bid. This is what makes the P&L "net of costs" without inventing a
#    cost constant: the spread paid is the spread that was actually quoted.
#    Entry is maker and pays no fee; the exit cross pays the venue's published
#    taker fee via core.backtest.fills, theta = 0.06 * p * (1-p), no rebate
#    assumed (C7/V9 — the maker rebate has never been observed on this
#    account).
#
# 3. MINUTES LEFT IS APPROXIMATED, and condition (5) is weaker for it. The
#    anchored target needs minutes remaining; the archive stores `event_period`
#    but no game clock, and `raw` was stripped to JSON null by sync_local on
#    12.0M of 12.9M live rows. So minutes-left is interpolated linearly across
#    each game's own Q4 wall-clock span, capped to [0, 10]. Wall time runs
#    longer than game time through stoppages, so this is an approximation of a
#    quantity the co-primary is sensitive to. It is reported as a limitation
#    rather than hidden, and it is the one thing that would make a borderline
#    (5) result untrustworthy. It cannot bias the PRIMARY arm, which never
#    consults it.


@dataclass
class Trade:
    """One filled maker entry and its exit, in the bought side's own frame."""

    event_slug: str
    market_slug: str
    side: str                       # 'yes' | 'no' — which side was bought
    entered_at: dt.datetime
    entry_cost: float               # price paid per contract, own frame
    exited_at: dt.datetime | None = None
    exit_proceeds: float | None = None
    exit_reason: str = "open"       # 'target' | 'settlement' | 'open'
    exit_fee: float = 0.0

    @property
    def is_closed(self) -> bool:
        return self.exit_proceeds is not None

    @property
    def net_pnl(self) -> float | None:
        """Per contract, net of costs. Entry is maker and free; the exit cross
        pays the taker fee. Settlement pays no fee."""
        if self.exit_proceeds is None:
            return None
        return self.exit_proceeds - self.entry_cost - self.exit_fee


def minutes_left_in_q4(now: dt.datetime, q4_start: dt.datetime,
                       q4_end: dt.datetime) -> float:
    """Linear interpolation across a game's Q4 wall-clock span, capped [0, 10].

    An approximation, and a documented one — see note 3 above. The archive has
    no game clock.
    """
    span = (q4_end - q4_start).total_seconds()
    if span <= 0:
        return QUARTER_MINUTES / 2.0
    frac = (now - q4_start).total_seconds() / span
    return max(0.0, min(QUARTER_MINUTES, QUARTER_MINUTES * (1.0 - frac)))


class TightGameReversion:
    """The registered strategy. One instance per game (replay_all guarantees
    it), so no state crosses a game boundary.

    ``target_for`` maps a tick to the reversion target in the YES frame. The
    primary arm returns EXIT_MID constantly; the co-primary returns the
    pregame-anchored live probability. Nothing else differs between the arms.
    """

    def __init__(self, target_for) -> None:
        self.target_for = target_for
        self.orders: dict[str, Order] = {}          # market -> working order
        self.positions: dict[str, Trade] = {}       # market -> open position
        self.trades: list[Trade] = []

    # -- the registered trigger ---------------------------------------- #

    @staticmethod
    def triggers(tick: Tick) -> str | None:
        """'yes' / 'no' for the cheap side, or None. Q4, margin <= 3, and a
        mid at or below MAX_ENTRY_MID on one side."""
        if tick.sports_market_type != MARKET_MONEYLINE:
            return None
        if tick.period != TRIGGER_PERIOD or not tick.is_live:
            return None
        pts = tick.points
        if pts is None or abs(pts[0] - pts[1]) > MAX_MARGIN:
            return None
        mid = tick.mid
        if mid is None:
            return None
        if mid <= MAX_ENTRY_MID:
            return "yes"
        if mid >= 1.0 - MAX_ENTRY_MID:
            return "no"
        return None

    def on_tick(self, tick: Tick, ctx: ReplayContext) -> None:
        slug = tick.market_slug

        # 1. A working order may have filled before this tick (replay resolves
        #    fills first), which opens a position.
        order = self.orders.get(slug)
        if order is not None and order.filled_at is not None:
            self.orders.pop(slug, None)
            side = order.note
            cost = (order.fill_price if side == "yes"
                    else 1.0 - order.fill_price)
            self.positions[slug] = Trade(
                event_slug=tick.event_slug, market_slug=slug, side=side,
                entered_at=order.filled_at, entry_cost=cost,
            )
            order = None

        # 2. An open position exits at the target, crossing the spread.
        position = self.positions.get(slug)
        if position is not None:
            target = self.target_for(tick)
            # A one-sided book has no mid, and is common in a thin Q4. No mid
            # means no exit decision on this tick — the position simply waits.
            if target is not None and tick.mid is not None:
                reached = (tick.mid >= target if position.side == "yes"
                           else tick.mid <= 1.0 - target)
                if reached and tick.bid is not None and tick.ask is not None:
                    proceeds = (tick.bid if position.side == "yes"
                                else 1.0 - tick.ask)
                    position.exit_proceeds = proceeds
                    position.exit_fee = fee_per_contract(proceeds, is_maker=False)
                    position.exited_at = tick.captured_at
                    position.exit_reason = "target"
                    self.trades.append(position)
                    self.positions.pop(slug, None)
            return          # one position at a time; do not re-enter this tick

        # 3. Patience: cancel a working order older than the registered window.
        if order is not None:
            age = (tick.captured_at - order.placed_at).total_seconds() / 60.0
            if age >= ENTRY_PATIENCE_MINUTES:
                ctx.cancel(order)
                self.orders.pop(slug, None)
                order = None
            else:
                return      # still working

        # 4. Flat and unencumbered: place a maker order if the trigger fires.
        side = self.triggers(tick)
        if side is None:
            return
        if side == "yes" and tick.bid is not None:
            self.orders[slug] = ctx.place(
                market_slug=slug, side="buy", limit_price=tick.bid,
                quantity=1.0, note="yes")
        elif side == "no" and tick.ask is not None:
            # Buying NO at its touch IS resting a sell of YES at the ask.
            self.orders[slug] = ctx.place(
                market_slug=slug, side="sell", limit_price=tick.ask,
                quantity=1.0, note="no")



# --------------------------------------------------------------------------- #
# Running it
# --------------------------------------------------------------------------- #
#
# SCORE-STRING ORIENTATION, verified rather than assumed (2026-08-18). The
# signed margin the co-primary needs is only meaningful if we know which team
# `event_score` names first. Checked against every settled moneyline market
# with live ticks: at the last live tick, sign(first - second) is +1 for all 19
# markets that settled YES and -1 for all 31 that settled NO. 50 of 50, no
# exceptions. So the FIRST score is the YES side — the market's quoted team —
# and margin from the YES frame is points[0] - points[1].


def _pregame_mid(session, market_slug: str) -> float | None:
    """The market's last pre-tipoff mid — the anchor for condition (5)."""
    from sqlalchemy import select

    from core.storage import MarketSnapshot

    row = session.execute(
        select(MarketSnapshot.best_bid, MarketSnapshot.best_ask)
        .where(MarketSnapshot.market_slug == market_slug,
               MarketSnapshot.is_live.is_(False),
               MarketSnapshot.best_bid.isnot(None),
               MarketSnapshot.best_ask.isnot(None))
        .order_by(MarketSnapshot.captured_at.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    return (float(row[0]) + float(row[1])) / 2.0


def _settlements(session) -> dict[str, int]:
    from sqlalchemy import select

    from core.storage import ResolvedOutcome

    return {
        slug: int(s) for slug, s in session.execute(
            select(ResolvedOutcome.market_slug, ResolvedOutcome.settlement)
        ).all()
    }


def _q4_span(ticks: list[Tick]) -> tuple[dt.datetime, dt.datetime] | None:
    q4 = [t.captured_at for t in ticks if t.period == TRIGGER_PERIOD and t.is_live]
    return (min(q4), max(q4)) if q4 else None


def _flat_target(_tick: Tick) -> float:
    """The primary arm: revert to 0.50, exactly as registered."""
    return EXIT_MID


def _anchored_target_factory(pregame: dict[str, float | None],
                             span: tuple[dt.datetime, dt.datetime] | None):
    """The co-primary arm (condition 5): revert to the PREGAME-ANCHORED live
    probability instead of 0.50.

    Returns None when the anchor is unavailable, which suppresses the exit
    rather than falling back to 0.50 — falling back would quietly turn the
    co-primary into a second copy of the primary.
    """
    def target(tick: Tick) -> float | None:
        anchor = pregame.get(tick.market_slug)
        if anchor is None or span is None:
            return None
        pts = tick.points
        if pts is None:
            return None
        minutes = minutes_left_in_q4(tick.captured_at, span[0], span[1])
        return anchored_probability(
            margin=float(pts[0] - pts[1]),      # YES frame — verified above
            minutes_left=minutes,
            sigma=RULE_OF_THUMB_SIGMA,
            pregame_price=anchor,
        )
    return target


def _settle_open(strategy: TightGameReversion, settlements: dict[str, int]) -> int:
    """Close positions still open at the last tick, at the venue's 0/1.

    Returns the number that could NOT be settled — reported, never guessed.
    """
    unsettled = 0
    for slug, position in list(strategy.positions.items()):
        outcome = settlements.get(slug)
        if outcome is None:
            unsettled += 1
            continue
        won = (outcome == 1) if position.side == "yes" else (outcome == 0)
        position.exit_proceeds = 1.0 if won else 0.0
        position.exit_fee = 0.0                 # settlement is not a trade
        position.exit_reason = "settlement"
        strategy.trades.append(position)
        strategy.positions.pop(slug, None)
    return unsettled


def _score(trades: list[Trade], *, arm: str, unsettled: int) -> dict:
    """Score one arm's trades. Clustered by game, per the registration."""
    closed = [t for t in trades if t.is_closed]
    by_game: dict[str, list[float]] = {}
    for t in closed:
        by_game.setdefault(t.event_slug, []).append(t.net_pnl)
    cl = clustered_mean(by_game)
    return {
        "arm": arm,
        "n_trades": len(closed),
        "n_games": len(by_game),
        "unsettled_positions": unsettled,
        "exits_at_target": sum(1 for t in closed if t.exit_reason == "target"),
        "exits_at_settlement": sum(1 for t in closed if t.exit_reason == "settlement"),
        "mean_net_pnl": None if cl is None else round(cl.mean, 5),
        "ci_lo": None if cl is None else round(cl.lo, 5),
        "ci_hi": None if cl is None else round(cl.hi, 5),
        "_cl": cl,
    }


def _arm_passes(arm: dict) -> bool:
    """Conditions (1) and (2) for one arm."""
    return (arm["_cl"] is not None
            and arm["mean_net_pnl"] > 0
            and arm["ci_lo"] > 0)


def report(session) -> dict:
    """Run hypothesis #17 exactly as registered and return its verdict.

    The gate is read from the constants above, which are the 2026-08-08
    pre-registration. Nothing here may change them.
    """
    from core.pulse.replay import available_games

    settlements = _settlements(session)
    games = [slug for slug, _ in available_games(session, min_ticks=100)]

    # Each game's ticks are loaded ONCE and fed to both arms. The DB read
    # dominates the run (~380k rows a game), and the arms differ only in their
    # exit target, so loading twice would double a 40-minute measurement for
    # no change in result. Only moneyline ticks are kept: the strategy returns
    # None for every other market type, so dropping them is a speed-up with
    # identical semantics, not a filter on the hypothesis.
    flat_trades: list[Trade] = []
    anchored_trades: list[Trade] = []
    flat_unsettled = anchored_unsettled = 0

    for event_slug in games:
        ticks = [t for t in load_ticks(session, event_slug=event_slug)
                 if t.sports_market_type == MARKET_MONEYLINE]
        if not ticks:
            continue
        span = _q4_span(ticks)
        slugs = {t.market_slug for t in ticks}
        pregame = {slug: _pregame_mid(session, slug) for slug in slugs}

        flat = TightGameReversion(_flat_target)
        replay_game(ticks, flat, event_slug=event_slug)
        flat_unsettled += _settle_open(flat, settlements)
        flat_trades.extend(flat.trades)

        anchored = TightGameReversion(_anchored_target_factory(pregame, span))
        replay_game(ticks, anchored, event_slug=event_slug)
        anchored_unsettled += _settle_open(anchored, settlements)
        anchored_trades.extend(anchored.trades)

        # Progress to stderr explicitly: this is a ~40 minute run and its
        # stdout is a JSON document.
        print(f"  {event_slug}: {len(ticks):,} ml ticks, "
              f"flat={len(flat.trades)} anchored={len(anchored.trades)}",
              file=sys.stderr, flush=True)

    primary = _score(flat_trades, arm="flat_0.50", unsettled=flat_unsettled)
    coprimary = _score(anchored_trades, arm="anchored", unsettled=anchored_unsettled)

    # (3) and (4) are judged on the PRIMARY arm's sample: it is the registered
    # trigger, and the co-primary differs only in where it exits.
    enough_trades = primary["n_trades"] >= GATE_MIN_TRADES
    enough_games = primary["n_games"] >= GATE_MIN_GAMES

    if not (enough_trades and enough_games):
        verdict = "NO DATA"
    elif _arm_passes(primary) and _arm_passes(coprimary):
        verdict = "PASS"
    else:
        verdict = "FAIL"

    return {
        "hypothesis": 17,
        "registered_at": REGISTERED_AT.isoformat(),
        "verdict": verdict,
        "gate": {
            "min_trades": GATE_MIN_TRADES, "min_games": GATE_MIN_GAMES,
            "condition_3_met": enough_trades, "condition_4_met": enough_games,
            "condition_1_2_primary": _arm_passes(primary),
            "condition_5_coprimary": _arm_passes(coprimary),
        },
        "primary": {k: v for k, v in primary.items() if k != "_cl"},
        "coprimary": {k: v for k, v in coprimary.items() if k != "_cl"},
        "games_replayed": len(games),
        "limitations": [
            ("minutes-left is interpolated across each game's Q4 wall-clock "
             "span; the archive stores no game clock (raw stripped to JSON "
             "null on 12.0M of 12.9M live rows). Affects the co-primary only."),
            ("maker rebate not assumed (C7/V9); entry pays no fee, the exit "
             "cross pays theta_taker = 0.06 * p * (1-p)."),
        ],
    }


def _print_text(r: dict) -> None:
    p, c = r["primary"], r["coprimary"]
    print(f"\nHYPOTHESIS #17 — tight-game ML reversion    VERDICT: {r['verdict']}")
    print("=" * 74)
    print(f"registered {r['registered_at']} · {r['games_replayed']} games replayed")
    print(f"\ngate: n>={r['gate']['min_trades']} trades "
          f"[{'MET' if r['gate']['condition_3_met'] else 'NOT MET'}] · "
          f">={r['gate']['min_games']} games "
          f"[{'MET' if r['gate']['condition_4_met'] else 'NOT MET'}]")
    for label, arm in (("PRIMARY — revert to 0.50", p),
                       ("CO-PRIMARY (5) — pregame-anchored", c)):
        print(f"\n{label}")
        print(f"  trades {arm['n_trades']} over {arm['n_games']} games "
              f"({arm['exits_at_target']} hit target, "
              f"{arm['exits_at_settlement']} settled)")
        if arm["mean_net_pnl"] is None:
            print("  mean net P&L: n/a — too few clusters to form an interval")
        else:
            print(f"  mean net P&L {arm['mean_net_pnl']:+.4f}/contract, "
                  f"95% CI [{arm['ci_lo']:+.4f}, {arm['ci_hi']:+.4f}]")
        if arm["unsettled_positions"]:
            print(f"  !! {arm['unsettled_positions']} positions unsettled, excluded")
    print("\nlimitations")
    for line in r["limitations"]:
        print(f"  - {line}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(prog="meridian-h17")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    import logging
    logging.basicConfig(format="%(message)s", stream=sys.stderr, level=logging.WARNING)

    from core.analytics import LOCAL_URL
    from core.storage import get_engine, get_sessionmaker

    Session = get_sessionmaker(get_engine(LOCAL_URL))
    with Session() as session:
        result = report(session)
    print(json.dumps(result, indent=2) if args.json else "", end="")
    if not args.json:
        _print_text(result)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
