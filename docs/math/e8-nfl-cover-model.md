# E8 — the NFL cover model beats the in-game normal, and by more than CFB's did

**Same construction as E3, nflverse-native.** P(final home margin > K) for any
half-point rung, one model queried at any K, monotone in K by constraint,
trained on nflverse play-by-play 2022–2024 held out **by game**. Spread sign
asserted per season before any fit (corr(spread_line, result) +0.385 / +0.426 /
+0.501; nflfastR positive = home favoured, ours negative).

## Result, 163 held-out games, 23,886 plays, vs in-game normal σ=13.5

| | model | normal | diff, game-clustered | G / G_eff |
|---|---|---|---|---|
| pooled over 12 rungs | 0.1016 | 0.1068 | **−0.0052 [−0.0074, −0.0030]** | 163 / 162.5 |

**Excludes zero. +4.9% skill** over line + score + clock. Seven of twelve rungs
win individually (−6.5, −3.5, −0.5, +0.5, +6.5, +10.5), none lose. Monotone
0 / 138,000. Isotonic calibration changes nothing (−0.0049), as in CFB.

For comparison, the CFB cover model's pooled edge over the same baseline on
813 held-out games was −0.0014 [−0.0021, −0.0008], +1.6%. The NFL head earns
three times the skill on a fifth of the games. Two plausible reasons, neither
tested here: NFL margins are tighter (σ 13.5 vs 15) so the normal has less
slack to be right by accident, and nflverse's situational fields are cleaner
than CFBD's.

| feature | gain |
|---|---|
| spread_line_differential | 75.1% |
| K | 11.4% |
| exp_margin_time | 3.4% |

## What is missing, on purpose

No ESPN `spreadCoverProbHome` comparison and no venue bridge — there is no NFL
tape until the 09-09 opener. Both sections exist in the script and switch on
when `games26` is non-empty. The E3 gate ("beat or match ESPN") therefore
cannot be evaluated for NFL yet; what *can* be said is that the model clears
the principled baseline with room, on a sample four times CFB's power.

Model result on held-out games. **Not edge.** Edge per rung is E5 on NFL,
which needs the ladder tape.

Artifact: `artifacts/nfl_cover_regulation.json` (+ meta, + `nflverse_cover_cache.json`).
Script: `cfb/run_cover_fit.py` with `LEAGUE=nfl`.
