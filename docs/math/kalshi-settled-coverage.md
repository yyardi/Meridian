# Kalshi as an equal venue: the coverage table

Measured 2026-09-14 against prod `kalshi_snapshots` (2,917,534 rows,
2026-08-05 → 09-14), read-only. The question asked was whether the settled
Kalshi population supports a paper-book arm. **It does not, and the reason
is not that it is thin.**

First, a trap for anyone re-running this: the **local mirror holds 98 settled
rows against prod's 13,097**. A local run concludes the population is empty.

## The settled set exists, and it is selected

| series | all mkts | games | settled | settled games | result=yes | result=no |
|---|---|---|---|---|---|---|
| KXNCAAFTOTAL | 4,267 | 238 | 525 | 81 | 493 | 32 |
| KXNCAAFSPREAD | 5,276 | 238 | 71 | 4 | 29 | 42 |
| KXNCAAFGAME | 506 | 253 | 14 | 7 | 7 | 7 |

610 settled of **10,049 CFB markets — 6.1%**, on 85 of 238 games. Quote
depth is not the problem: zero settled markets have no two-sided quote, 609
of 610 have five or more, and the median is ~198.

**93.9% of totals settlements are YES**, and that is not a fact about college
football. Within a game, the settled markets are the LOW strikes:

| bucket | mkts | mean strike | mean relative strike rank |
|---|---|---|---|
| settled yes | 493 | 45.7 | **0.264** |
| never settled | 3,742 | 55.8 | 0.562 |
| settled no | 32 | 59.6 | 0.623 |

The mechanism is in the contract. `yes_sub_title` is "Over 29.5 points
scored", so an **Over X market is determined the moment the running total
passes X** — mid-game — while a market that will settle NO cannot be
determined before the final whistle. We capture the first kind and miss the
second: median settlement observed **26.1 minutes before the recorder's last
row** for that game (totals, yes) against **0.0 minutes** for the 32 NO
settlements, which were caught only on the final poll.

So the settled set is the subset whose YES outcome arrived early enough for
the recorder to still be watching. Pricing it at a pre-game close and
settling from `result` would measure "markets that went over early, priced
before the game" and report it as edge. Same shape as the withdrawn-order
arm that always flatters: **settled-in-our-tape MEANS the over hit early.**

## And "pre-game close" is not definable for CFB

| league | kalshi_games rows | with `game_start_time` | with `espn_game_id` | with pm slug |
|---|---|---|---|---|
| cfb | 492 | **0** | **0** | **0** |
| nfl | 32 | **30** | **30** | 0 |
| wnba | 75 | 75 | 0 | 75 |

No kickoff, no ESPN id, no Polymarket link for any CFB game. The only time
field present is `venue_occurrence_time`, which this project has already
measured as tip+3h on the WNBA side — for a 3.5-hour football game that
lands near the final whistle, so using it as a pre-game boundary would admit
the whole in-game tape.

`close_time` is not a boundary either: **it is rewritten at settlement.**
One game, one ladder:

```
KXNCAAFTOTAL-26SEP03AKRWAKE-30  Over 29.5  close_time 2026-09-04 01:49:48  result yes
KXNCAAFTOTAL-26SEP03AKRWAKE-36  Over 35.5  close_time 2026-09-04 01:49:48  result yes
KXNCAAFTOTAL-26SEP03AKRWAKE-39  Over 38.5  close_time 2026-09-05 23:00:00  result (none)
```

The settled strikes carry their settlement instant; the unsettled ones still
carry the placeholder.

## NFL is the clean population, and it was dismissed too early

The NFL recorder **stops at kickoff**, which is why nothing is settled:

```
26SEP13BALIND  last row 2026-09-13 16:59:28   kickoff 17:00
26SEP13GBMIN   last row 2026-09-13 20:24:23   kickoff 20:25
```

That is not a gap. It is exactly the thing the design needs:

| series | mkts | games | quotes each | last quote before ko | band 0.10-0.90 | band spread |
|---|---|---|---|---|---|---|
| KXNFLSPREAD | 354 | 14 | 533 | 0.53 min (p90 1.91) | 305 | **1.51c** |
| KXNFLTOTAL | 266 | 14 | 533 | 0.53 min | 214 | **1.49c** |
| KXNFLGAME | 28 | 14 | 533 | 0.53 min | 28 | **1.00c** |

Every market has a pre-game two-sided quote, the poll is uniform (median =
minimum = 533), the last quote sits a median **32 seconds** before kickoff,
and band spreads are 1.0-1.5c. NFL markets never leave status `active`
(410,067 rows), while CFB reaches `determined` (604) and `finalized` (541) —
the status asymmetry is the same fact from the other side.

**What NFL lacks is Kalshi's `result`, and for a total or a spread that is
not a feed — it is a function of the final score**, which the 30 espn_game_ids
supply. Derive the outcome from the score and Kalshi's 610 CFB `result`
values become the VALIDATOR of the derivation rather than its source. That
removes the selection bias and it can be checked, which settling from
`result` cannot.

## So: no verdict today, either population

**G = 14 games** for NFL, against the paper book's G ≥ 25 floor. And the
Manager's first caution is the binding one: 547 band markets on 14 games is
~39 per game, and within a game a totals ladder and a spread ladder move
with the same score, so the effective sample is at most 14 clusters and
realistically fewer. 525 markets was never 525 observations and 648 is not
648. NFL accrues ~14 games a week, so G = 25 arrives around 2026-09-20.

## The other two cautions

**The fee cannot be read from the tape.** `kalshi_events` and
`kalshi_event_snapshots` are both **empty (0 rows)** — `fee_type` and
`fee_multiplier` exist as columns and carry nothing. The instruction cannot
be followed as written. The substitution: take the venue-declared quadratic
shape, keep the 0.07 rate flagged as unverified (it never was venue-declared
in anything we read), and make the multiplier a per-series INPUT rather than
a constant, so a populated table later changes a value and not the code.

**The frame comes back clean, and it is better than the other venue's.**
`yes_sub_title` names the side on every contract, with `strike_type`
agreeing:

| series | strike_type | YES means | rows matching / rows |
|---|---|---|---|
| KXNCAAFTOTAL | greater | over the strike | "Over 102.5 points scored" — 4,792 / 4,792 |
| KXNCAAFSPREAD | greater | the NAMED team covers | "X wins by over 1.5 points" — 5,347 / 5,347 |
| KXNFLTOTAL | greater | over the strike | 266 / 266 |
| KXNFLSPREAD | greater | the NAMED team covers | 354 / 354 |
| KXWNBATOTAL / SPREAD | greater | as above | 684 / 684, 771 / 771 |
| *GAME | structured | the NAMED team wins | a bare team name |

Zero blank `yes_sub_title` on any series. (I nearly wrote "4,792/4,792" from
a ticker count rather than a row count — the denominator above is measured.)

There is no away-home convention to infer, which is the assumption that
produced three false headlines on Polymarket this month. The containment
trap still applies when JOINING a Kalshi team name to an ESPN game — exact
key first, containment last — but not to deciding what YES is.

## If it is built anyway

Point it at NFL, not CFB. Derive settlement from the final score and
validate against the 610 CFB results. Report G, not market count. And fix
the CFB recorder's stop-at-the-last-poll behaviour before trusting any
future CFB settlement, because today's CFB settled set will keep growing in
the same biased direction.
