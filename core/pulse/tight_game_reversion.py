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

import datetime as dt

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


def report(session) -> dict:
    """Not implemented, deliberately.

    This module is a registration. Implementing it is a separate piece of work
    that must not happen in the same breath as writing the gate — the point of
    the timestamp above is that the bar existed before anyone went looking.
    """
    raise NotImplementedError(
        "Hypothesis #17 is registered, not implemented. Implement it against "
        "core/pulse/replay.py exactly as this docstring specifies — including "
        "condition (5), the pregame-anchored co-primary — and change nothing "
        "in the gate while doing so."
    )


if __name__ == "__main__":
    raise SystemExit(
        "Hypothesis #17 is a pre-registration (2026-08-08T02:19Z). "
        "Nothing to run yet."
    )
