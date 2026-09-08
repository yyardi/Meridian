# Adverse selection by stratum: the one clear statement the making programme can make

Same harness (`cfb/run_making_touch.py`), same fill rule (trade prints, θ_maker=0,
optimistic queue), same 70 pooled CFB games, same naive touch-joined maker with
no model. Only the *when* and *which side* change.

| stratum | how quotes are placed | fills | net per fill, game-clustered | adverse by markout | G / G_eff |
|---|---|---|---|---|---|
| **E1** at plays | every play, both sides, +30s | 1,635 | −1.94¢ [−4.83, +0.96] | **47.4%** | 36 / 15.1 |
| **E6** dead windows | no play 45s, no score 120s, both sides | 2,760 | +0.50¢ [−1.95, +2.94] | **30.3%** | 32 / 11.2 |
| **H1c** on the move's side | after a ≥1¢ one-minute mid move, that side only, rest 2 min | 122 | +1.49¢ [−4.38, +7.35] | **15.6%** | 17 / 7.1 |

**Every interval spans zero. Read the columns, not the cells.** Adverse selection
falls monotonically — 47% → 30% → 16% — and net per fill rises monotonically as
quotes move away from plays and onto the side of the venue's own momentum. E1
and E6 were pre-registered; H1c is exploratory on CFB and registered for NFL
(`e8-nfl-preregistration.md`). The pattern is consistent with one mechanism:
**informed flow arrives at plays, and the venue's quoting engine walks its price
for 2–3 minutes afterwards; a maker who stays out of the first and sits with the
second faces the least toxic flow this tape contains.**

What it is not: a result. G_eff 7 on the last row. Power arrives with NFL's
denser fills, and the gate is written: H1c net per fill positive and excluding
zero at G ≥ 25.

Context that bounds it: the continuation the maker would ride is +0.59¢ at the
mid over 2 minutes; a *taker* chasing the same move loses −0.80¢ net of fee
(`slowside_cfb_2026-09-08.out`). The only reading that clears costs is the
maker's, and only if fills on the move's side keep arriving at 16% adverse when
G is 25 rather than 7.
