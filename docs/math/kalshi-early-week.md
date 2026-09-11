# Kalshi, early in the week: the test your friend's strategy needs, and why this tape cannot run it yet

Written 2026-09-11 18:10Z. Script `cfb/run_kalshi_early_vs_close.py`, output
`kalshi_early_vs_close_2026-09-11.out`.

**The claim being tested.** "A sports model traded against Kalshi's NFL/CFB
prices makes money." Kalshi's close is not soft against DraftKings (measured
three ways: NFL wk-1 favourites +0.20¢ power-devigged, 49 preseason games
−0.18¢, 137 CFB games "Kalshi ask 0.950 vs realised 0.949"). So if the claim is
true, the money is EARLIER than the close: Kalshi lags the sharp line during
the week and a model that tracks the line, or the line itself, takes the lag.
That is a well-known mechanism and it is testable — with the right tape.

**What this tape can say.** The Kalshi recorder polls a game only from
`KALSHI_PREGAME_HOURS` = 6 before tip (an env knob, default 6.0). Every winner
ticker on the tape has 6.0–7.4 hours of pregame history and nothing earlier, so
T−72h and T−24h cannot be asked. On the 23 Kalshi CFB games that match a
settled ESPN game (containment-last code matching, 0 side-ambiguous), in the
last six hours before ESPN's first play:

| T−h | tickers | G | early half-spread | \|close − early\| median / p90 | moved ≥ 1¢ | buy YES always | buy NO always |
|---|---|---|---|---|---|---|---|
| 6 | 36 | 18 | 0.50¢ | 0.0¢ / 3.0¢ | 15 | −1.16¢ | −1.11¢ |
| 3 | 40 | 20 | 0.51¢ | 0.0¢ / 3.0¢ | 15 | −1.12¢ | −1.09¢ |
| 1 | 40 | 20 | 0.51¢ | 0.0¢ / 1.0¢ | 9 | −1.11¢ | −1.09¢ |

In the last six hours Kalshi's winner prices do not move (median zero, p90
three cents) and the controls earn exactly minus the fee. There is nothing to
lag in that window. Whether there is something to lag on Tuesday is the
question, and it is unanswered, not answered no.

**What has to change, and it is one line.** Widen the recorder's window to the
three days its occurrence-stamp horizon already covers:

```
KALSHI_PREGAME_HOURS=72   # kalshi-recorder environment, then: docker compose up -d kalshi-recorder
```

Rate arithmetic (the recorder's own): worst case inside 72h is a Saturday CFB
slate (~50 games) plus the NFL week (16) = 66 games × 3 series per 120 s cycle
= 1.65 req/s against the 5 req/s bucket. Row volume rises ~12× on the pregame
portion, a few million rows a week against a 30M-row snapshot table. No code
change; the operator runs it.

**And the second tape.** A lag needs something to lag. DraftKings' pregame line
path for football is not recorded (`sportsbook_odds` is the WNBA feed; its last
row is 08-30). ESPN's scoreboard carries DK's current football lines and the
softness scripts already read it; extending `core/feeds/espn_odds.py` to poll
NFL/CFB hourly is a small change on this branch, to be written next.

**The pre-registered read, once both tapes exist (one week of games):** at
every hour h before kickoff, DK power-devigged probability vs Kalshi mid on the
same market; where they differ by more than fee + half-spread, buy the Kalshi
side DK favours at the Kalshi touch, settle at ESPN's final, net of
0.07·p(1−p). Game-clustered, G ≥ 25, positive and excluding zero passes. This
is your friend's strategy with DraftKings as the model, which is the strongest
free model there is; a Monte Carlo that beats it is a separate claim.
