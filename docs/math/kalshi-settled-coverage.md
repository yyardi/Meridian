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

---

# Addendum, same day: what the build needs, and what it cannot have yet

Three answers to the build brief, all read-only, no code.

## 1. The validation plan cannot be executed as specified

The instruction was to validate the derived settlement against Kalshi's 610
CFB `result` values. **There is no population where we hold both Kalshi's
`result` and a joinable final score.**

| | Kalshi settlements | `espn_game_id` | pm slug |
|---|---|---|---|
| CFB | **610** on 85 games | 0 of 492 | 0 of 492 |
| NFL | 0 | 30 of 32 | 0 |
| WNBA | 0 | 75 of 75 | 75 of 75 |

The entire settled inventory is CFB, and CFB is the one league with no join
key. That is not a coincidence — it is the same stop condition seen from two
sides: the leagues whose recorder stops at kickoff never see a settlement,
and CFB, the league that kept polling into the game, is the one that was
never wired to ESPN.

Nor is a name match available as a fallback. `espn_cfb_game_state` stores
teams as **numeric ESPN ids** (`away = 103`, `home = 2116`), not names, so
bridging Kalshi's "Akron vs Wake Forest" to a score needs a school-name →
ESPN-id vocabulary that is not in the tape. Polymarket carries 247 football
games with scores over 09-02 → 09-14, but the Kalshi → Polymarket join is
the same missing key.

## 2. The frame CAN be validated, with no join at all — and it holds

Within one settled totals ladder, every strike below the final total must
settle YES and every strike above it must settle NO. That is checkable from
Kalshi alone, and it is the one thing that would be catastrophic to get
wrong.

| games with settled totals | with BOTH a yes and a no | monotone | violations | mean bracket |
|---|---|---|---|---|
| 81 | 2 | 2 | **0** | 3.00 pts |

```
26SEP05FORNDSU   max yes strike 36.50   min no strike 39.50
26SEP12WEBBLIB   max yes strike 46.50   min no strike 49.50
```

The bracket width equals the 3-point strike spacing, and an inverted frame
would have violated on both. Two games is not a small sample here — the
frame is a binary structural fact, and one correctly-bracketed ladder
settles it. (Only 2 of 81 games have both sides, which is the capture bias
again, from the same direction.)

## 3. The design effect, measured rather than assumed

A totals ladder is ~15 deterministic step functions of ONE scalar (the
total); a spread ladder ~22 of another (the margin); the winner is
`sign(margin)`. So a game contributes at most two outcome scalars, and they
are **not** independent — on 114 CFB finals:

| mean total | sd | mean abs margin | sd | corr(total, abs margin) |
|---|---|---|---|---|
| 54.3 | 17.1 | 26.7 | 19.7 | **0.524** |

At ρ = 0.52 the two scalars are worth about `2/(1+ρ) = 1.31` independent
draws per game. So **14 games behave like 14 clusters for a totals-only
book and ~18 for totals plus spreads** — not 547, and not 6. Six would
require the GAMES to be correlated with each other, which they are not:
different teams, different days. The pessimistic reading of the cluster
caution is wrong in this direction.

Transported with a flag, not silently: ρ is measured on CFB, where the mean
margin is 26.7 with sd 19.7 — a blowout-heavy league. NFL totals and margins
are tighter, so the NFL ρ must be re-measured once there are enough finals.
A defect cannot calibrate its own fix and neither can a league.

## 4. Today's derivable NFL population is 9 games, not 14

The NFL score source does exist: `espn_cfb_game_state` carries
`league='nfl'` (15 games, 09-10 → 09-14) and joins **directly on
`espn_game_id`** — no name matching anywhere. But:

| | games | reached `post` | stuck `in` |
|---|---|---|---|
| ESPN nfl | 15 | **9** | 6 |
| ESPN cfb | 186 | 105 (56.5%) | 81 |
| Kalshi NFL ∩ ESPN | 13 | **9** | 4 |

**Deriving a settlement from a game still in state `in` would be a bias, not
a gap.** A truncated game has a lower total, so "Over" markets would settle
NO when the real total cleared the strike — the same directional error as
the CFB capture bias, from the opposite side. The rule has to be: derive
only from `state='post'`, and count the rest as unsettled rather than as
losses.

So G = 9 today against a floor of 25, and the 09-20 estimate depends on the
ESPN football recorder reaching `post`, which it manages 56.5% of the time
on CFB and 9 of 15 on NFL. **That, not the Kalshi side, is now the binding
constraint** — and it is the same stop-before-the-whistle defect as the
other two found today.

(One correction inside this addendum: `max(state)` is alphabetical, and
`'pre' > 'post' > 'in'`, so a game with a pre-game row reports `pre` no
matter how it ended. Re-run with `bool_or(state = 'post')` the CFB counts
moved 111/84/6 to 105/81/0 and NFL stayed at 9. The conclusion did not move,
but the instrument was wrong and would have gone on being wrong.)
