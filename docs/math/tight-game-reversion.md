# Hypothesis #17 — tight-game moneyline reversion to 50/50

**FAIL, gated 2026-08-18.** Registered 2026-08-08T02:19Z, computed once, ten
days later. Nothing in the gate moved in between.

```bash
python -m core.pulse.tight_game_reversion
```

## The claim

> *"won a fourth quarter ml on phx cuz i saw it was extremely tight and phx
> suddenly dropped to 33 from 50, bought, sold 45... dallas-gsv is tight so
> deviation shud return to 50/50, buy either side below 35, sell at 50"*
> — the operator, 2026-08-08T02:19Z, real money

In a tight game, a moneyline far from 50/50 comes back toward it.

## The verdict

| | trades | games | mean net P&L | 95% CI (clustered by game) |
|---|---|---|---|---|
| **primary** — revert to 0.50 | 40 | 26 | **−9.12¢** | **[−16.77¢, −1.48¢]** |
| **co-primary (5)** — pregame-anchored | 146 | 26 | **−4.16¢** | **[−5.81¢, −2.51¢]** |

The gate's sample conditions were **met** — 40 filled trades against a bar of
30, over 26 distinct games against a bar of 15, from 50 games of 200ms archive.
So this is a real FAIL and not a NO DATA: the hypothesis was measurable and it
lost money.

Both intervals lie **entirely below zero**. This is not "failed to clear a
cost" — the strategy is losing, significantly, in both frames.

## Why it loses, in one number

**Only 16 of the 40 trades ever reached 0.50.** The other 24 rode to
settlement.

That is the hypothesis refuting itself rather than merely underperforming. The
trade is "buy below 0.35, sell at 0.50", and 60% of the time the sell never
happens — the position is still held when the game ends. A side quoted below
0.35 in a tight Q4 mostly settles at zero, because the market had it right.

Tight games do not revert to a coin flip. **A 0.33 price on a tight game is not
a mispriced 0.50; it is a price.** The market is conditioning on who is playing
and how much time is left, and the flat-0.50 anchor discards both.

## The co-primary was the point, and it agrees

Condition (5) was mandatory in the registration, because #16 passed its gate at
+6.84¢ against a team-blind anchor and inverted to −2.20¢ the moment the anchor
became team-aware (C12). The same trap was pre-registered shut here.

It did not trigger the way #16's did — this time **both** anchors agree the
strategy loses. The anchored arm loses *less* (−4.16¢ vs −9.12¢) for a
mechanical reason worth recording: the anchored target sits much closer to the
entry price than 0.50 does, so it is reachable — **130 of 146 anchored trades
hit their target** against 16 of 40 flat ones. Exiting earlier at a nearer
target loses less than riding to settlement. Cutting a losing trade sooner is
not an edge.

## Cross-references

**#1 run overreaction — FAIL, 2026-08-06.** Killed *price-move* triggered
reversion. #17 tested the *state-conditioned* half, which the operator's
anecdote also contained. **Both halves of the reversion family are now dead on
pre-registered terms.** A variant that re-adds a price-move condition is
re-opening #1 and needs its own registration plus a reason #1 does not already
answer it.

**#5 Q4 tight-game moneyline** remains not built and is not unblocked by this.
It is about violent repricing, and it sits behind adverse selection, which
failed at −2.66¢ per filled quote.

## How it was measured

Exactly as registered: Q4, boxscore margin ≤ 3, moneyline mid ≤ 0.35 on either
side, maker entry only, exit at 0.50 or settlement, P&L net of costs, clustered
by game. `core/pulse/replay.py` resolves fills — an order placed on tick N is
eligible from N+1, so a maker order can never silently become a taker.

Three things the registration did not specify, decided at implementation and
recorded in the module so a later reader can tell a choice from a re-tuning:

1. **One position at a time per market.** The trigger is true for thousands of
   consecutive 200ms ticks (53,581 across the archive); one position per
   qualifying tick would be absurd, and the 2-minute cancel already implies a
   single working order.
2. **Exit crosses the spread.** The target is reached on the *mid*; the fill is
   taken at the far touch. This is what makes P&L net of costs without
   inventing a cost constant — the spread paid is the spread that was quoted.
   Entry is maker and free; the exit cross pays the venue's published
   `theta_taker = 0.06 · p · (1−p)`. **No maker rebate is assumed** (C7/V9 — it
   has never appeared on this account).
3. **Minutes-left is approximated**, and the co-primary is weaker for it. The
   archive stores `event_period` but no game clock, and `raw` was stripped to
   JSON null by `sync_local` on 12.0M of 12.9M live rows. Minutes-left is
   therefore interpolated across each game's own Q4 wall-clock span, capped to
   [0, 10]. Wall time runs longer than game time through stoppages, so this is
   an approximation of a quantity the anchored target is sensitive to. **It
   cannot bias the primary arm, which never consults it.** Were the co-primary
   the only thing standing between this and a PASS, that would be a reason to
   distrust the result — it is not; both arms fail independently.

### One verified fact worth reusing

**The first number in `event_score` is the YES side** — the market's quoted
team. Checked against every settled moneyline market with live ticks: at the
last live tick, `sign(first − second)` is +1 for all 19 markets that settled
YES and −1 for all 31 that settled NO. **50 of 50, no exceptions.** The signed
margin the anchored target needs is meaningless without this, and guessing it
would have inverted the co-primary silently rather than loudly.
