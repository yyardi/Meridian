# E8 pre-registration — written 2026-09-07, before any NFL tape exists

Everything below is fixed now so Thursday's numbers are a test, not a search.
Population: Polymarket US NFL, live recorder tape, week 1 (16 games) then
cumulative. **25-game floor** before any arm is read as a verdict; week 1 alone
is reported as directional only. All intervals game-clustered, G and G_eff
printed, estimator named on every row.

## H1 — in-game overshoot (the one lead with a mechanism)

Kalshi preseason: after a ≥1¢ one-minute move, ~6% of the shock reverts within
two minutes, in three size strata, each excluding zero. **Hypothesis: the same
overshoot exists on Polymarket US's in-game NFL winner market.**

- Data: winner-market mids at 1-minute resolution from `market_snapshots`,
  kickoff → kickoff+3h40m, one market per game.
- Statistic: mean continuation sign(jump)·(mid[t+2] − mid[t]) after |jump| ≥ 1¢,
  strata ≥1¢ / ≥2¢ / ≥3¢, game-clustered. Exactly these three strata.
- **Gate to matter:** the ≥2¢ stratum's reversal excludes zero **and** exceeds
  half the contemporaneous spread (the maker's cost of being there). Polymarket
  maker fee is 0 (findings.md C7), so half-spread is the whole hurdle.
- If it exists but is under half-spread: a fact about the venue, not a trade.
- If absent: the Kalshi regularity is Kalshi's. Nothing is fitted to rescue it.

## H2 — E1 making, NFL-trained shield

`LEAGUE=nfl`, arms A/B/C as on CFB, θ_maker=0, prints-based fills, dead-window
stratum as E6. Pre-stated expectation from CFB: A and B span zero; adverse-by-
markout lower in dead windows. **Read only after 25 games.** No new arms.

## H3 — E5 ladder relative value, NFL cover model

τ=0.05 primary, 0.03/0.08 secondary, leg spread ≤6¢, one position per game×pair,
exactly as on CFB. Model: `nfl_cover_regulation.json`, chosen on nflverse
held-out, not on this tape. **Precondition to report at all:** stale fraction
of pair-instants < 50% (CFB was 96%; if NFL's ladder is sampled as sparsely,
the test cannot run and that is the finding).

## H4 — pregame softness, scored

The week-1 snapshots in `analysis/pregame_softness/` are scored against
settlement: Brier of venue mid vs DK power-devigged prob, favourite side,
game-clustered. Expectation from Kalshi preseason and the live snapshot: even.

## What is not on this list and will not be added after the tape arrives

Any stratum, threshold, horizon, model, or feature not named above. If
something interesting appears outside these four, it is written down as a
hypothesis for week 2 and not reported as a week-1 result.

---

## Addendum 2026-09-08 — H1 ran on CFB; the gate failed; H1b is registered before NFL tape

`cfb/run_overshoot.py`, LEAGUE=cfb, 42 covered games, 782 moves ≥1¢, output in
`overshoot_cfb_2026-09-08.out`:

| h | β | continuation |
|---|---|---|
| 1 | +0.059 [+0.002, +0.116] | **+0.28¢ [+0.04, +0.52]** |
| 2 | +0.107 [−0.002, +0.216] | **+0.53¢ [+0.18, +0.88]** |
| strata ≥1/2/3¢ @2 | +16.0 / +15.6 / +13.2% of jump | +0.53 / **+0.73 [+0.22, +1.23]** / +0.77¢ vs half-spread 0.42 / 0.45 / 0.47¢ |

**H1 (reversal > half-spread): FAILS.** Polymarket does the opposite of Kalshi:
the move *continues* by ~15% within two minutes, every stratum excluding zero,
each above the half-spread. **This is not reported as a result.** It was not
the registered direction. It is registered now, before any NFL tape, as:

**H1b — continuation, decomposed by the slow side.** Hypothesis: the mid
continues because one side of the book reprices first and the other catches up
a minute later; the exploitable quantity is the stale quote on the slow side,
not the mid. Statistic, fixed now: classify each ≥1¢ minute by which side moved
(ask-led / bid-led / both); measure over the next 2 minutes (i) the other side's
move, (ii) the change in the price a taker would get *against the slow side*.
Gate: on NFL, the slow-side capture excludes zero and exceeds the taker fee at
the mid where it occurs (0.06·p(1−p)) plus the half-spread crossed. Same
strata, same clustering, 25-game floor. Nothing else added after the tape.

---

## Addendum 2026-09-08 (later) — H1b's population is empty; replaced before NFL tape, with the reason

`cfb/run_slowside.py` on the same 42 games (`slowside_cfb_2026-09-08.out`): of 803
≥1¢ minutes, **791 moved both sides together**, 9 ask-led, 3 bid-led. There is no
slow side — the venue's book reprices as a unit. H1b as written cannot be
evaluated on any tape; it is withdrawn as a mechanism, not deferred.

What the same run measured on the "both" population, exploratory on CFB:
other-side follow-through +0.59¢ [+0.18, +0.99]; **a taker chasing the move:
+0.15¢ gross [−0.22, +0.51], −0.80¢ net of fee [−1.19, −0.41] — loses.**

**H1c — registered now, before NFL tape.** *Maker on the side of the move.*
After a ≥1¢ one-minute mid move, post at the new touch on the move's side (bid
after an up-move, ask after a down-move), rest 2 minutes, fills from trade prints
as in E1, θ_maker = 0, optimistic queue as in E1. Compare net-per-fill and
adverse-by-markout against E1 arm A on the same tape. Gate on NFL: net per fill
excludes zero and is positive, G ≥ 25. That is the last reading of the
continuation that could clear costs; if it fails, the continuation is a fact
about the quoter's cadence and not a trade.

> **2026-09-10 14:14Z: the CFB prior for this hypothesis (+3.58¢, 15/17 games) is RETRACTED
> as a look-ahead artifact; corrected it is −1.28¢ [−2.33, −0.23], 8/21. The
> hypothesis and its gate stand as registered and will be graded on the corrected
> harness. See the addendum of the same time below.**

Three looks at 42 CFB games have now been taken (H1, slow-side, H1c-exploratory).
Whatever H1c shows on CFB is a prior for NFL, nothing more.

---

## The morning after each NFL game — run exactly this, in this order

All scripts are piped over stdin into the trainer image; nothing is written to
the prod checkout. Set `H` from `~/.meridian-server`. The DB URL is the compose
default for the `trainer` service.

```bash
# Env vars go INSIDE docker run as -e flags. `LEAGUE=nfl ssh … sudo docker run …` sets the
# variable for the remote shell, sudo drops it, and docker never sees it: every script then
# runs its CFB default and prints "LEAGUE=cfb". This happened on the first NE@SEA run.
# Check the FIRST LINE of every output names LEAGUE=nfl before reading anything else.
D='sudo -n docker run --rm -i --network meridian_default -e DATABASE_URL=postgresql+psycopg://meridian:meridian@postgres:5432/meridian -v /opt/meridian/cfb:/app/cfb -v /opt/meridian/artifacts:/app/artifacts -w /app'
# 0. did the recorders write the game? (plays, WP, game_state under league='nfl'; venue winner snapshots during the game)
# 1. H1  overshoot direction on Polymarket NFL          -> gate: reversal > half-spread (expected to FAIL as on CFB; record it)
ssh ubuntu@$H "$D -e LEAGUE=nfl meridian-trainer python3 -" < cfb/run_overshoot.py
# 2. H1c maker on the move's side                       -> gate: markout +2min > 0, excludes zero, G >= 25; >=70% of games positive
ssh ubuntu@$H "$D -e LEAGUE=nfl -e MOVE_STRATUM=1 meridian-trainer python3 -" < cfb/run_making_touch.py
# 3. H2  E1 arms, NFL-trained shield (auto-selected by LEAGUE)
ssh ubuntu@$H "$D -e LEAGUE=nfl meridian-trainer python3 -" < cfb/run_making_touch.py
ssh ubuntu@$H "$D -e LEAGUE=nfl -e DEAD_WINDOW=1 meridian-trainer python3 -" < cfb/run_making_touch.py
# 4. H3  ladder RV, NFL cover model                     -> precondition: stale fraction < 50%, else "cannot run" is the result
ssh ubuntu@$H "$D -e LEAGUE=nfl meridian-trainer python3 -" < cfb/run_ladder_rv.py
# 5. H4  score the pregame snapshots against settlement (public APIs, no prod): append a fresh row first
python3 analysis/pregame_softness/pregame_softness_polymarket.py analysis/pregame_softness/pregame_softness_polymarket_snapshots.csv
python3 analysis/pregame_softness/pregame_softness_kalshi.py     analysis/pregame_softness/pregame_softness_snapshots.csv
```

Before kickoff on Wednesday (and Sunday): re-run step 5's two scripts to append
a near-kickoff snapshot — lines move, and a Monday snapshot for a Sunday game is
the weakest version of the test.

**Read nothing as a verdict until G ≥ 25.** Week 1 is 16 games. Report every
number with its interval, G and G_eff, estimator named, and the pre-registered
gate beside it. Anything outside H1–H4 is written down as a hypothesis for
week 2 and not reported as a week-1 result.

---

## Addendum 2026-09-08 — two changes to the READ, registered before Saturday's CFB slate and Wednesday's NFL tape

**1. Pool by venue.** The mechanism under H1c is Polymarket's quoting engine,
which is the same engine on CFB and NFL. H1c is therefore read **pooled across
both leagues on Polymarket**, cluster = game, 25-game floor on the pooled G.
Saturday 09-12 (~40 covered CFB games) plus Sunday 09-13 (13 NFL) clears the
floor by Monday 09-14. Per-league splits are reported beside the pool, not
instead of it. Kalshi is a different engine (it reverts) and is never pooled in.

**2. Markout is the primary maker metric; settlement is secondary.** Settlement
P&L puts a whole game's binary outcome on every fill, which is why 122 fills at
G_eff 7 said nothing. A maker who can flatten earns fill-price-vs-mid-later, so
the primary statistic for every making arm is **markout at +2 and +5 minutes,
in cents, game-clustered**, reported beside settlement. Gate for H1c becomes:
markout at +2 min positive and excluding zero, pooled G ≥ 25; settlement must not
contradict it in sign. This is the variance-reduction question from the
researcher update, answered with the standard estimator rather than a novel one.
Registered before it is computed on any NFL tape; CFB values below are the prior.


---

## Addendum 2026-09-08 — secondary criterion for H1c, registered before NFL tape

Primary (unchanged): pooled CFB+NFL markout at +2 min for the move-side maker,
positive and excluding zero, game-clustered, G ≥ 25.

**Secondary, added now:** game-level sign test — the fraction of games with
positive mean 2-minute markout must be ≥ 70% at G ≥ 25 (one-sided binomial
p < 0.05 against 0.5). It weights every game equally and depends on no clustering
model, so it cannot be rescued by a few high-fill games. The CFB prior is 15/17
(p = 0.0012) — **RETRACTED 2026-09-10 14:14Z: that prior came from the look-ahead post
instant; corrected, 8/21.** Both criteria must hold; if they disagree, the disagreement is
the result and is reported as such.

---

## 2026-09-10 00:55Z — NE@SEA live, both recorders verified, H3 precondition MET

Mid-slate check, first quarter: ESPN NFL recorder writing plays / WP / game state
with the live line on every state row (SEA −3.0); venue game 19457 live, **1,483
trade prints in ten minutes** (a CFB Friday produced 6 across 17 markets), 32
spread rungs quoted; map join 401872656 → 19457 verified; 33 of 33 plays have a
venue quote inside the posting window.

**H3 precondition** (stale fraction of pair-instants must be < 50%): measured on
the first 32 plays, rungs within ±14 of the line — **10.7% stale** (CFB: 96%), 576
of 672 K/K+7 pairs both quoted, **median live spread on quoted rungs 1.0¢** (CFB:
4¢ median, 17¢ p75). E5 could not run on CFB; it can run on NFL.

A session-local monitor watches both recorders through the game (heartbeat 30 min,
speaks on silence, exits at the final). Its first version false-alarmed on its
own parsing — psql's `SET` echo read as the plays count — and was replaced; a
check that fires gets the same scrutiny as one that doesn't. The pre-registered
block runs on this game after the final.

## 2026-09-10 03:50Z — NE@SEA final (SEA 13, NE 10): the block ran; one game, G=1, nothing is a verdict

Every script ran under `-e LEAGUE=nfl` and said so on its first line. The numbers
below are recorded because the pre-registration says to record them, not because
any of them means anything: with one cluster the game-clustered interval is
zero-width **by construction**, so the harness now prints `NO INTERVAL (G=1)`
where an earlier run printed `EXCLUDES 0`. That earlier label was a lie and has
been removed from all three scripts (`run_making_touch.py`, `run_overshoot.py`,
`run_ladder_rv.py`); the overshoot script also crashed on G=1 (`ZeroDivisionError`
in the clustered slope) and is fixed.

| step | population | point estimate | interval | gate |
|---|---|---|---|---|
| H1 overshoot, ≥1¢ move, h=2 | 50 moves, 2,494 winner snapshots | continuation −0.89¢ (reversal 19% of jump; half-spread 0.27¢) | none, G=1 | NO INTERVAL |
| H1c maker on the move's side | 56 quotable instants | — | — | refused, below floor |
| H2 E1 at plays | 165 quotable instants | — | — | refused, below floor |
| H2 E6 dead window, A_naive | 936 posted, 175 fills | markout +2min −1.37¢, +5min −4.28¢ | none, G=1 | NO INTERVAL |
| H2 E6 dead window, B_shield | 531 posted, 405 pulled, 87 fills | markout +2min +0.93¢, +5min +1.70¢ | none, G=1 | NO INTERVAL |
| H3 ladder RV, τ=0.05 | 21 positions | net +0.84¢, mid-to-mid +4.38¢, inside-rate 0.33 | none, G=1 | NO INTERVAL, underpowered |

Three things ARE established by this game, none of them a P&L claim:

1. **The NFL pipeline works end to end.** Both recorders wrote the whole game; the
   map join held; the NFL WP shield and NFL cover model loaded and scored live
   rows; the block completes in under ten minutes per game.
2. **H3's precondition is met on NFL** (10.7% stale, 1.0¢ median rung spread), so
   Sunday's 13 games will produce E5 positions — the first time E5 has had a
   population at all.
3. **The E6 shield acted** (405 of 531 postings pulled, adverse-by-markout moved
   in the direction the shield is meant to move it). Whether it acts *usefully* is
   what G ≥ 25 is for.

One direction worth writing down as a hypothesis for week 2 and nothing more:
the E5 long-interval and short-interval halves split +13.95¢ (n=11) against
−13.58¢ (n=10). On one game that is two coin flips; if it survives 13 games it
is the first thing to look at.

**Next read:** Sunday 2026-09-13's slate, pooled with Saturday's CFB on the
Polymarket engine (never with Kalshi), against the H1c gate: markout +2min > 0,
interval excluding zero, G ≥ 25, and ≥ 70% of games positive. That read decides
scrap or a bounded live probe. This game contributes one cluster to it.

## 2026-09-10 03:59Z — H4 has a scorer; the weekend map is written

**H4.** The run block's step 5 named a scoring step that did not exist. It now
does: `analysis/pregame_softness/score_softness.py` reads both snapshot files,
takes the last snapshot before kickoff per game (primary) and the registration
snapshot (secondary), recomputes DK's power devig from the two moneylines (it
matches the Polymarket file's `dk_pow` to four places, max gap 0.0000 — a second
route that could have disagreed and did not), fetches settlement from ESPN's
public summary, and prints the registered metric: venue-mid Brier minus DK-power
Brier on the favourite, one observation per game, venues separate.

NE@SEA, the only settled game: SEA favourite, DK power 0.6105, Polymarket mid
0.6275, Kalshi mid 0.6250, SEA won. Brier difference −0.0130 (Polymarket) and
−0.0111 (Kalshi): the venues sat *above* DK on the favourite and the favourite
won, so one game says "venue closer". One game; no interval; the read is after
Sunday (16 settled). The 2026-09-10 00:50Z post-kickoff snapshot was correctly
excluded from NE@SEA's primary pick and serves the remaining 16 games.

**Weekend map.** The CFB map held nothing past 09-07; Saturday's slate would have
had no venue join. The builder now matches 49 of the venue's 51 listed CFB games
(Fri 5, Sat 44). Seven Saturday games fell under the 0.72 name-confidence floor;
the builder now prints the nearest ESPN candidate for every miss, and six were
admitted by eye against that candidate (`--admit`, written with
`match_method='reviewed_near_miss'` so the override is visible in the row
forever). No threshold could have done this: the seventh miss
(`cfb-wkent-ga`, 0.667) scores *higher* than three of the correct six and its
nearest candidate is a different game. It stays unmapped.

## 2026-09-10 04:04Z — the Monday read is one command, and it grades itself

The harness had no pooled mode: H1c was registered as a CFB+NFL Polymarket pool
and could only be run one league at a time. `LEAGUE=both` now loads CFB
(backfill + live, deduplicated by game) and NFL (live), scores every play with
its own league's shield head, clusters on the union, prints each league's split
beside the pool, and prints the pre-registered gate verdict on its own line:

```bash
ssh ubuntu@$H "$D -e LEAGUE=both -e MOVE_STRATUM=1 meridian-trainer python3 -" < cfb/run_making_touch.py
# read the line beginning "H1c GATE:" -- PASS / FAIL / SPLIT / UNDERPOWERED. Nothing else is the verdict.
```

Run tonight on everything that exists (CFB through 09-06 plus NE@SEA), so the
pooling is verified before it matters:

> **RETRACTED 2026-09-10 14:14Z.** This table was produced with the post instant one minute
> early (look-ahead). The corrected table is in the addendum of that time. It is
> left here struck so the retraction sits at the numbers it retracts.

| | +2min markout | interval | fills | G / G_eff | games positive |
|---|---|---|---|---|---|
| ~~pooled~~ | ~~+3.20¢~~ | ~~[+1.08, +5.31]~~ | ~~141~~ | ~~18 / 8.1~~ | ~~16/18 (89%, p = 0.0007)~~ |
| ~~cfb split~~ | ~~+3.58¢~~ | ~~[+1.24, +5.92]~~ | ~~122~~ | ~~17 / 7.1~~ | ~~15/17~~ |
| ~~nfl split~~ | ~~19 scored fills on 1 game~~ | — | ~~19~~ | ~~1~~ | ~~too few to print~~ |

Gate line: ~~UNDERPOWERED (G=18 < 25): not a read.~~ ~~Both criteria would hold
at this G; the floor is the floor.~~ Seven more fill-carrying games clear it, and
the weekend brings 44 mapped CFB games and 12 NFL games. Note what G counts:
games that *carried a move-side fill*, not games on tape (75 games are loaded;
57 produced no ≥1¢ move with a book behind it, mostly thin CFB winner markets).

## 2026-09-10 14:14Z — RETRACTION: the move-side maker was a look-ahead; corrected, it loses

**What was wrong.** In `cfb/run_making_touch.py`'s MOVE_STRATUM block the minute
close series was built with `minute[k] = mid; first.setdefault(k + 1, r)`. That
stores the FIRST snapshot OF minute k under the key k+1, so `r0 = first[k + 1]` —
meant to be the first snapshot of the minute AFTER the move — was the first
snapshot of the move minute itself. The quote was posted at the start of the
minute whose close, sixty seconds later, defined the move it was supposedly
reacting to. A bid posted at the start of a minute that is about to close ≥1¢
higher, marked out two minutes later, is positive by construction: the +3.58¢ was
roughly one cent of guaranteed move plus half a spread.

**How it was found.** Not by review. The live trigger (`core/quote/move_trigger.py`)
was written as an independent implementation of the rule for the bounded probe,
and `cfb/run_trigger_replay.py` fed it the same tape to reconcile move counts
before anything else was built on it. It counted 862 (kickoff phase) and 850
(wall-clock phase) against the harness's 865 and 852. The three extra moves
were minutes with no snapshot in the following minute — which the harness could
still "post" in, because it was posting in the wrong minute. Explaining the
difference exposed the off-by-one. With the fix the two implementations agree
exactly: 862 and 850.

**Corrected numbers, same tape (CFB through 09-06 + NE@SEA), same fill rule:**

| phase | +2min markout | interval | fills | G / G_eff | games positive | gate line |
|---|---|---|---|---|---|---|
| kickoff (registered) | **−1.21¢** | [−2.15, −0.27] excludes 0 | 313 | 22 / 9.2 | 8/22 (36%, p = 0.93) | UNDERPOWERED (G=22 < 25) |
| wall-clock | **−1.62¢** | [−2.98, −0.27] excludes 0 | 283 | 23 / 8.9 | 8/23 (35%, p = 0.95) | UNDERPOWERED (G=23 < 25) |
| cfb split, kickoff | −1.28¢ | [−2.33, −0.23] | 276 | 21 / 8.2 | 8/21 | — |
| +5 min, kickoff | −2.03¢ | [−3.45, −0.60] | 313 | 22 / 9.2 | — | — |

The shield arms (B/C) on the corrected stratum: −0.61¢ [−1.45, +0.24] at +2 min,
spans zero; −1.36¢ [−1.90, −0.83] at +5 min. Adverse-by-markout on the naive arm
rose from 15.6% to 56.5%: the "least toxic flow on the tape" was the harness
looking at the answer. Fill rate rose from 16% to 36% because a quote posted
after an up-move sits at a higher touch and gets hit more.

**What stands.** E1 (at plays, −0.82¢) and E6 (dead windows, −0.07¢) do not use
this code path. H1 (overshoot) buckets close-to-close and measures from the
move minute's close forward — no look-ahead. The overshoot's "Polymarket
continues" finding stands. The three-strata table in
`adverse-selection-by-stratum.md` carries the retraction at its H1c row.

**What this means for the gate.** The pre-registered H1c gate is unchanged and
will be graded Monday on the corrected harness; nothing may be added to rescue
it. On the evidence tonight the move-side maker loses at both markout horizons
with intervals excluding zero and 8 of 22 games positive. The honest
expectation for Monday is FAIL, and the operator's agreed rule for FAIL is
scrap. The three scheduled reads (Friday, Sunday, Monday) run the corrected
code and print the gate line mechanically.

**The lesson, written where the number was:** the reconciliation was scheduled
as a formality before building the live probe. It was the only instrument
that could disagree with the harness, and it did by three moves out of 865.
Every number this programme has reported from a second-hand bucketing should
be assumed to have a post instant until its post instant has been checked to
lie strictly after the information it conditions on.

## 2026-09-11 13:50Z — Friday: NFL game 2 (SF@LAR) on the corrected harness

Run by hand: the scheduled Friday task started at 11:00Z and stalled on its
first shell call (a permission prompt no one was there to answer). The read is
the same either way.

**Coverage.** SF@LAR (venue `nfl-sf-lar-2026-09-10`): 168 ESPN plays, final
LAR 7 SF 27, 2,528 venue winner snapshots. Both recorders wrote the whole game.

**H1c GATE (pooled CFB + 2 NFL, corrected post instant):**
`+2min markout −1.23¢ [−2.13, −0.34] G=23 G_eff=9.9; games positive 8/23 (35%, one-sided binomial p=0.9534) → UNDERPOWERED (G=23 < 25): not a read`

| | +2min markout | interval | fills | G / G_eff | games positive |
|---|---|---|---|---|---|
| pooled | −1.23¢ | [−2.13, −0.34] excludes 0 | 328 | 23 / 9.9 | 8/23 |
| cfb split | −1.28¢ | [−2.33, −0.23] excludes 0 | 276 | 21 / 8.2 | 8/21 |
| nfl split | −0.99¢ | [−1.76, −0.22] excludes 0 | 52 | 2 / 1.7 | 0/2 |
| +5 min, pooled | −2.06¢ | [−3.42, −0.70] excludes 0 | 328 | 23 / 9.9 | — |

Shield arms on the stratum: −0.59¢ [−1.40, +0.21] at +2 min (spans zero),
−1.31¢ [−1.84, −0.78] at +5 min. NFL's first two games lose on the move side
just as CFB does; the pooled sign has not moved since the retraction.

**H1 overshoot, NFL (G=2):** β +0.203 [+0.034, +0.372] at 2 min — continues, as
on CFB; in cents +0.02¢ [−0.26, +0.29], spans zero. Two games.

**H4 softness, 2 settled games per venue (PRIMARY, last snapshot before
kickoff):** Polymarket −0.0054 [−0.0202, +0.0094] venue closer 1/2; Kalshi
−0.0061 [−0.0159, +0.0037] venue closer 2/2. Both span zero.

**Infrastructure:** the harness's second-phase queries died with
`could not resize shared memory segment ... No space left on device` once the
window reached eight days (the 64 MB `/dev/shm` cap; disk was 34% used). All
three prod scripts now set `max_parallel_workers_per_gather = 0` on every
connection and COMMIT it — an uncommitted SET was undone by the pool's first
rollback and the second attempt died identically. The run takes ~12 minutes
without parallel workers; Monday's task should expect that.

Two games from the floor. Sunday brings twelve.

## 2026-09-11 14:10Z — Friday: NFL game 2, re-run independently; plus the Friday CFB coverage

The 13:50Z section above is the same read, run by hand. This section exists
because the scheduled task ran it again from the committed harness. Two things
here are NOT in that section: the five Friday CFB games' coverage (the runbook
asks for it and it was not recorded), and two defective guard lines found by
reading the output that the hand-run did not print or did not question.

**What a re-run can and cannot check.** Same script, same tape, unchanged data:
every number below reproduced the 13:50Z section to the digit. That establishes
determinism, not correctness — this route could not have disagreed. The checks
that *could* fail are the code audit and the arithmetic, and two of those failed.

**Coverage, SF@LAR** (`nfl-sf-lar-2026-09-10`, espn 401872657, venue 19454):
168 ESPN plays and 486 `espn_cfb_game_state` rows, both spanning
00:41:24Z → 03:24:36Z, `live_spread` non-null on all 486; 2,528 venue winner
snapshots (09-02 22:52Z → 03:24:46Z).

All 486 state rows are `state='in'`. **There is no post row.** The recorder
stopped at P4 0:14 with LAR 7 SF 27 and never wrote a settled row. ESPN's
summary endpoint says `post`, Final LAR 7 SF 27 — so the score above is correct
but it is ESPN's, not our tape's. The same night the CFB recorder wrote 2 post
rows for FAMU@MIA, so this is specific to the NFL game, not a global stop.

**Coverage, the five Friday CFB games** (`division <> 'NFL'`, `espn_date::date
= '2026-09-11'`). Four of the five have zero plays and zero state rows. That is
correct, not a gap: ESPN has them `state=pre`, kicking off tonight.

| game | plays | state rows | winner snaps | status |
|---|---|---|---|---|
| cfb-flam-mia-2026-09-10 | 175 | 546 (spread 546, 2 post) | 4,043 | Final MIA 77 FAMU 7 |
| cfb-norfst-vir-2026-09-11 | 0 | 0 | 117 | `pre`, kickoff 23:00Z |
| cfb-rich-ncst-2026-09-11 | 0 | 0 | 118 | `pre`, kickoff 23:00Z |
| cfb-rutger-boscol-2026-09-11 | 0 | 0 | 117 | `pre`, kickoff 23:30Z |
| cfb-vill-lou-2026-09-11 | 0 | 0 | 117 | `pre`, kickoff 23:30Z |

Only FAMU@MIA (kickoff 2026-09-11T00:00Z, Thursday night ET) has tape. The four
pregame games are on an ~88-minute snapshot sweep; nothing in `market_snapshots`
anywhere is newer than 12:45:40Z against a 13:54Z database clock, which is
within that cadence. Tonight's slate needs the sweep to go live at 23:00Z.

**H1c GATE, verbatim** (`LEAGUE=both MOVE_STRATUM=1`, 892 one-minute >=1c moves,
328 fills):

`H1c GATE: +2min markout -1.23c [-2.13, -0.34] G=23 G_eff=9.9; games positive 8/23 (35%, one-sided binomial p=0.9534)  ->  UNDERPOWERED (G=23 < 25): not a read`

Beside it, verbatim:

```
A_naive              892     892    328  36.8%      -1.34c     57.3%
MARKOUT +2min   -1.23c  [-2.13, -0.34]  n=328 G=23 G_eff=9.9  EXCLUDES 0
MARKOUT +5min   -2.06c  [-3.42, -0.70]  n=328 G=23 G_eff=9.9  EXCLUDES 0
per-game +2min markout: 8/23 games positive; leave-one-game-out mean range [-1.50, -0.85]c
  cfb split: +2min -1.28c [-2.33, -0.23] n=276 G=21 G_eff=8.2 EXCLUDES 0; 8/21 games positive
  nfl split: +2min -0.99c [-1.76, -0.22] n=52 G=2 G_eff=1.7 EXCLUDES 0; 0/2 games positive
```

**Name the estimator.** `-1.23c` is the mean over the 328 *fills*, with a
*game-clustered* interval: "game-clustered" names the interval, not the
estimate. The equal-weight per-game mean is a different number and is not what
the gate tests. G=23 is the games carrying fills (the tape is G=77); G_eff=9.9
is the clustering-effective count, so 23 markets behave like ~10.

Two qualifiers the 13:50Z section does not carry. First, **876 of the 892
quotes used the optimistic no-queue assumption** (full FIFO priority); only 16
had queue modelled from recorded depth. The -1.23c is already the optimistic
case and it still loses. Second, the leave-one-game-out range [-1.50, -0.85]c
never crosses zero, so no single game carries the sign.

**DEFECT — the "could this have come out the other way" guard is wrong.** It
prints:

`B posts a strict SUBSET of A's sides (1,251 of 892 withdrawn).`

1,251 of 892 is impossible on its face. In the move stratum line 551 wants
exactly one side (`want_bid, want_ask = (move_side=="bid"), (move_side=="ask")`),
so the *unposted opposite side* is counted as "withdrawn" for every arm,
including A_naive — which withdraws nothing by model. Hence posted+pulled =
2 x 892 = 1,784 for all three arms. The shield's real action is
892 - 533 = **359 of A's 892 posted sides (40.2%)**; the printed figure
overstates it by 3.5x. The same inflated count feeds "it withdrew 1,251 sides
rather than 0 or all", and the `pulled` column showing 892 for A_naive.
No markout is affected — fills drive those — so every headline above stands.
The damage is to the guard that is supposed to establish the design was not
rigged, which is the one line you cannot check by re-running.

**H1 overshoot, NFL (G=2), verbatim:**

```
     2      81   +0.203   [+0.034, +0.372]    2            +0.02c   [-0.26, +0.29]   CONTINUES
     1c     81    2           +0.02c   [-0.26, +0.29]     +0.4%          0.27c   spans zero
     2c     64    2           +0.18c   [+0.04, +0.32]     +3.3%          0.27c   spans zero
     3c     47  too few
```

**DEFECT — that second "spans zero" is false.** [+0.04, +0.32] excludes zero.
The label at line 134 is a fall-through: it prints "spans zero" for anything
not lying entirely *below* zero, so an interval excluding zero on the
*continuation* side is reported as if it carried no information. The gate's
DECISION is right (fading the move needs a reversal; +0.18c is a continuation,
and 0.18c < the 0.27c half-spread anyway), but the ">=2c" stratum is mild
evidence *against* overshoot, not an absence of evidence. This is shared code:
CFB prints the same wrong label on any positive-continuation stratum.

**H4 softness, PRIMARY, 2 settled games per venue:**

```
polymarket_us  games 2  mean diff -0.0054  [-0.0202, +0.0094]  venue closer 1/2  spans zero  (unsettled 15)
kalshi         games 2  mean diff -0.0061  [-0.0159, +0.0037]  venue closer 2/2  spans zero  (unsettled 15)
```

This scorer reads the committed CSVs, so running it again reproduces the
13:50Z block by construction — it is not a second measurement of softness. What
it does confirm independently is the outcome coding: its LAR row is `won 0`,
matching the venue tape and ESPN's 7-27.

**Post instant, audited by reading (the one check a re-run cannot do).** The
move is defined at the close of minute k (`dm = minute[k] - minute[k-1]`, last
mid of each minute); the post is `first[k+1]`, the first snapshot of the NEXT
minute; the game state is the last play at or before `t0 - 30s` (FEED_LAG).
Strictly after the information it conditions on. The retracted look-ahead
(`setdefault(k+1, r)`) is gone. 892 moves now vs 865 at the retraction.

Two games, G_eff=1.7 on the NFL split. Nothing here is a read. Twelve Sunday.
