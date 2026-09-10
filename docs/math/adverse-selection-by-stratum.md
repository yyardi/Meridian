# Adverse selection by stratum: the one clear statement the making programme can make

> **RETRACTED 2026-09-10 14:14Z — the H1c row below was a look-ahead artifact.** The harness
> posted the move-side quote at the FIRST snapshot of the minute whose CLOSE
> defined the move (`first.setdefault(k + 1, r)` stored minute k's first
> snapshot under key k+1), i.e. one minute before the move was knowable. Found
> when an independent implementation of the same rule (`core/quote/move_trigger.py`,
> replayed by `cfb/run_trigger_replay.py`) counted 862 moves against the
> harness's 865. With the post instant corrected to the first snapshot of the
> NEXT minute, the move-side maker on the same CFB tape is **−1.28¢ [−2.33, −0.23]
> markout at +2 min, 8/21 games positive, G=21 / G_eff 8.2 — it loses, like
> quoting at plays.** Pooled with NE@SEA: −1.21¢ [−2.15, −0.27], 8/22, under
> wall-clock minute phase −1.62¢ [−2.98, −0.27], 8/23. The E1 and E6 rows do not
> use that code path and stand. Everything below the table that reads the H1c
> row as positive is superseded by this note.

Same harness (`cfb/run_making_touch.py`), same fill rule (trade prints, θ_maker=0,
optimistic queue), same 70 pooled CFB games, same naive touch-joined maker with
no model. Only the *when* and *which side* change.

| stratum | how quotes are placed | fills | settlement net/fill | **markout +2 min (primary)** | adverse by markout | G / G_eff |
|---|---|---|---|---|---|---|
| **E1** at plays | every play, both sides, +30s | 1,813 | −2.51¢ [−5.34, +0.33] | **−0.82¢ [−1.26, −0.37]** excludes 0 | **49.0%** | 37 / 15.7 |
| **E6** dead windows | no play 45s, no score 120s, both sides | 4,030 | +0.58¢ [−1.10, +2.25] | **−0.07¢ [−0.34, +0.20]** break-even | **26.3%** | 33 / 7.1 |
| **H1c** on the move's side — ~~as first run~~ RETRACTED (look-ahead) | ~~after a ≥1¢ one-minute mid move, that side only, rest 2 min~~ | ~~122~~ | ~~+1.49¢ [−4.38, +7.35]~~ | ~~+3.58¢ [+1.24, +5.92]~~ | ~~15.6%~~ | ~~17 / 7.1~~ |
| **H1c** on the move's side — CORRECTED (post after the move is known) | after a ≥1¢ one-minute close-to-close move, first snapshot of the next minute, that side only, rest 2 min | 276 | −1.50¢ (pooled arm line) | **−1.28¢ [−2.33, −0.23]** excludes 0, the wrong side | **56.5%** (pooled) | 21 / 8.2 |

**Markout — fill price vs the mid two minutes later, the estimator a maker who can flatten actually earns — is now primary (pre-registered 2026-09-08 before any NFL tape). Settlement carries a whole game's binary noise on each fill and is kept beside it.** On markout the pattern that was only visible in point estimates becomes measured at both ends: quoting at plays *loses* and excludes zero; dead windows are exactly break-even with a tight interval; the move's side is *positive* and excludes zero — on 17 games, G_eff 7, exploratory, with the concentration check in `markout_move.out`. Adverse selection
falls monotonically — 47% → 30% → 16% — and net per fill rises monotonically as
quotes move away from plays and onto the side of the venue's own momentum. E1
and E6 were pre-registered; H1c is exploratory on CFB and registered for NFL
(`e8-nfl-preregistration.md`). The pattern is consistent with one mechanism:
**informed flow arrives at plays, and the venue's quoting engine walks its price
for 2–3 minutes afterwards; a maker who stays out of the first and sits with the
second faces the least toxic flow this tape contains.**

**Concentration (`markout_move.out`):** 15 of 17 games have positive 2-minute
markout; leave-one-game-out mean ranges **[+2.66, +4.37]¢**; the two non-positive
games are −0.00 and −0.13¢. A game-level sign test — every game weighted equally,
no fill weighting, no clustering model — gives P(≥15 of 17 | fair coin) =
**0.0012**. It is broad, not two games.

What it is not: a result. G_eff 7 on the last row. Power arrives with NFL's
denser fills, and the gate is written: H1c net per fill positive and excluding
zero at G ≥ 25.

Context that bounds it: the continuation the maker would ride is +0.59¢ at the
mid over 2 minutes; a *taker* chasing the same move loses −0.80¢ net of fee
(`slowside_cfb_2026-09-08.out`). The only reading that clears costs is the
maker's, and only if fills on the move's side keep arriving at 16% adverse when
G is 25 rather than 7.
