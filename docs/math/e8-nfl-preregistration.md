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

Three looks at 42 CFB games have now been taken (H1, slow-side, H1c-exploratory).
Whatever H1c shows on CFB is a prior for NFL, nothing more.

---

## The morning after each NFL game — run exactly this, in this order

All scripts are piped over stdin into the trainer image; nothing is written to
the prod checkout. Set `H` from `~/.meridian-server`. The DB URL is the compose
default for the `trainer` service.

```bash
RUN='sudo -n docker run --rm -i --network meridian_default -e DATABASE_URL=postgresql+psycopg://meridian:meridian@postgres:5432/meridian -v /opt/meridian/cfb:/app/cfb -v /opt/meridian/artifacts:/app/artifacts -w /app meridian-trainer python3 -'
# 0. did the recorders write the game? (plays, WP, game_state under league='nfl'; venue winner snapshots during the game)
# 1. H1  overshoot direction on Polymarket NFL          -> gate: reversal > half-spread (expected to FAIL as on CFB; record it)
ssh ubuntu@$H "LEAGUE=nfl $RUN" < cfb/run_overshoot.py
# 2. H1c maker on the move's side                       -> gate: net/fill > 0, excludes zero, G >= 25
ssh ubuntu@$H "LEAGUE=nfl MOVE_STRATUM=1 $RUN" < cfb/run_making_touch.py
# 3. H2  E1 arms, NFL-trained shield (auto-selected by LEAGUE)
ssh ubuntu@$H "LEAGUE=nfl $RUN" < cfb/run_making_touch.py
ssh ubuntu@$H "LEAGUE=nfl DEAD_WINDOW=1 $RUN" < cfb/run_making_touch.py
# 4. H3  ladder RV, NFL cover model                     -> precondition: stale fraction < 50%, else "cannot run" is the result
ssh ubuntu@$H "LEAGUE=nfl $RUN" < cfb/run_ladder_rv.py
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
(p = 0.0012). Both criteria must hold; if they disagree, the disagreement is
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
