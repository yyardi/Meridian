# Thin-league speed: does the venue reprice late after its own score changes?

Registered 2026-09-28 ~02:10Z, before any tape it reads exists. The first stream window
with the score tape opens 2026-09-28 13:00Z (BSL, tip 16:00Z). Operator's thesis
(2026-09-28): in dead markets the edge is information and speed. This read tests the
cheapest half of it: speed off **the venue's own** score, which any participant can
poll. A faster external feed is a second registration, written only if this one
says the venue's own feed is already too slow to act on (kill condition 1).

## Instruments (all under `artifacts/reads/stream/<tag>/`, per game)

| tape | what | clock |
|---|---|---|
| `slate_books_<game>.jsonl` | the winner market's touch (bid, ask, sizes), every venue push | `tt` venue, `recv` ours |
| `slate_trades_<game>.jsonl` | every print | venue |
| `slate_scores_<game>.jsonl` | the venue's score/period/clock, a line per change, `competitors`, `yes_team_id` | `state_updated_at` venue; change in `(prev_recv, recv]` ours |
| `kalshi_<league>.jsonl` | Kalshi's touch on the same league's games, every 10 s | `updated_time` Kalshi, `recv` ours |

Code: core/ladder/scores.py, core/ladder/kalshi_tape.py, cfb/run_stream_slate.py;
windows from tip − 3 h to tip + 150 min (scripts/schedule_slate.py).

## Population

Every game in `eurolg, lnbp, bbl, vtb, bsl, denbl, slnbl, hunbl` whose window ran with the
score tape, tipping 2026-09-28 to 2026-10-26. A game whose tapes are missing or whose book
tape has a gap > 60 s during play is excluded and counted.

**Event.** A score line with `live = true`, period Q1–Q4 or OT, whose previous line for the
game was also live, where exactly one team's points rose by 1–3 ("simple"). A larger or
two-team jump means the poll skipped a state; those are counted as "compound" and not
scored. The scoring side is YES if the scorer's competitor id equals `yes_team_id`, else
NO. Instants: `t_V` = `state_updated_at`; `t_R` = `recv`; entry `t_E = t_R + 1.0 s`.

**Direction check before any statistic.** On five games checked by hand against the
final (and Kalshi's settlement where it lists the game), the side the score order and
`yes_team_id` give must match. One mismatch voids every row until fixed and re-registered.

## Primary statistic

For each simple event: buy one contract of the scoring side at its ask **as visible at
t_E** (the last book line with `recv ≤ t_E`; NO's ask = 1 − YES bid). Mark-out:

    M60 = mid of the scoring side at t_E + 60 s − entry ask − fee(entry ask)

fee = 0.0695 · p · (1 − p), the venue's coefficient for this period (raised to 0.0695 at
2026-09-17 04:07Z; the nightly fee_drift job would flag a change inside the window, and a
change voids the rows after it until they are re-priced at their own coefficient).
An event whose book is not `MARKET_STATE_OPEN` at t_E, or has no ask, is not scored and is
counted.

Estimate: mean of M60 over events. Interval: cluster-robust by **game**, G/(G−1), 1.96
(as cfb/run_paper_book.py::clustered), and by slate date printed beside.

**Control, computed identically and printed beside:** the same M60 at instants drawn
uniformly over each game's live play, buying the side given by a fair coin keyed on the
instant (reproducible). Under no information its mean is −(half-spread + fee) < 0; it must
come out negative or the instrument is measuring its own plumbing and nothing is read.

**Gate:** G ≥ 30 games with ≥ 1 scored event, mean M60 > 0 and both intervals exclude
zero, and the control's mean < 0.

## Printed beside, never gated

- **Already repriced:** the share of events whose scoring-side ask at t_E is already above
  its value at `prev_recv` (someone moved first) — by league.
- **Venue latency:** time from `t_V` to the first scoring-side mid change ≥ 1 tick (venue
  `tt`), median and p90, by league; share with no change within 60 s.
- **Stale size:** the displayed size at the entry ask, and the dollar sum of M60 × size
  capped at the displayed size — a lookup, not an inference.
- **Kalshi:** time from `t_V` to Kalshi's next `updated_time` change on the scorer's team
  market (10-s resolution: an upper bound).
- M10 and M30 beside M60; rows per league, per period, home (YES) vs away (NO) scorers.

## Kill conditions, written before they can be excused

1. ≥ 90 % of scored events already repriced at t_E: the venue's own feed is no speed edge
   at a 1-s reaction. Stop. Only a strictly faster external feed can reopen it, as a new
   registration naming that feed and its measured lead.
2. The gate fails at G ≥ 30: dead as a rule. No re-cut by league, period, margin, clock,
   scorer side or horizon.
3. Fewer than 30 games by 2026-10-26: UNDERPOWERED, the count is the answer.
4. The direction check fails, or the control is not negative: void until fixed.
5. More than half of events not scored because the book was closed or empty in play: the
   market is not tradeable in play in these leagues, and that is the finding.

## Power, stated before the first number

Basketball has ~80–110 scoring plays a game, so 30 games give a few thousand events, but
they are clustered: what the interval sees is ~30 games. With a per-game sd of mean M60 of
~3¢ (unmeasured; it will be printed), 30 games detect a ~1.5¢ mean at 80 %. The realised
sd and the minimum detectable effect at the realised G are printed with the result.

## Addendum, 2026-09-28 ~03:00Z, still before any tape exists: the league's own clock

EuroLeague publishes a shot log (`live.euroleague.net/api/Points`) whose every row carries
`UTC`, the second of the shot, checked on a finished 2025-26 game. Each eurolg window now
saves it as `official_<game>.json` when it ends (core/ladder/official_pbp.py), matched to
the venue's game by a hand-written table of the 20 clubs, the start minute, and the venue's
home team equal to the league's local club (10 of 10 games of 09-29/30 matched). Printed
beside, **never gated**:

- **Venue score latency:** for each league scoring shot at `t_L`, the venue's
  `state_updated_at` on the first score line equal to the league's running score after
  it; median and p90 by game.
- **Information mark-out:** M60 computed exactly as above but entered at `t_L + 1 s`
  instead of `t_R + 1 s` — the best a poller of the league's live feed could do; that
  feed's live refresh was not measured and would only add delay.

A positive information mark-out is a hypothesis for a new registration that names a live
feed and its measured refresh; it is not a result of this one.
