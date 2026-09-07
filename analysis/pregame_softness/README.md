# Pregame softness: are the venues' NFL prices soft against the sharp book?

The one edge hypothesis that needs no speed: Bartlett–O'Hara's "retail overbets
favourites/YES" cross-subsidy. If a venue's *pregame* winner price sits above
DraftKings' devigged moneyline on favourites by more than the cost of expressing
it, a maker sits on the gap for free. Measured on NFL week 1, 16 games, both
venues, two public keyless APIs, no prod, no model, no lag.

**Devig matters and the result flips on it.** Proportional devig manufactures a
favourite gap of ~1¢ because it ignores the favourite-longshot bias in the
bookmaker's vig. The power method (p_h^k + p_a^k = 1) does not.

| venue | favourites, proportional | favourites, **power** | fav spread | taker fee ~p=0.6 |
|---|---|---|---|---|
| Kalshi | +1.01¢ [+0.53, +1.49] | **+0.20¢ [−0.27, +0.66]** | 1.06¢ | ~1.7¢ |
| Polymarket US | +1.07¢ [+0.57, +1.57] | **+0.26¢ [−0.23, +0.75]** | 0.50¢ | ~1.44¢ (maker 0) |

**Under the devig that handles favourite-longshot bias, neither venue is soft.**
Both sit within a quarter-cent of DraftKings and within 0.1¢ of each other on
favourites — consistent with cross-venue arb being closed on cost. Two of
sixteen games (CHI/CAR +2.1¢, WAS/PHI +1.5¢ on Polymarket after power devig)
exceed 1¢; two outliers on sixteen, saved to be scored, not called.

## Snapshots are pre-registered data, not a look-back

`*_snapshots.csv` carry a UTC timestamp per row. They were taken 2026-09-07
~19:30Z for games kicking off 09-09 to 09-14, and are to be **scored against
settlement** — Brier of venue mid vs Brier of DK power-devigged prob, game-
clustered — after week 1 settles. A snapshot closer to kickoff (lines move) is
worth appending before each slate; re-run both scripts with the same CSV path.

Kalshi fields are `_dollars`/`_fp` (the earlier probe read fields that do not
exist). Venue winner YES = the slug's first team = the away team (196/196).
DraftKings via ESPN's core `odds` endpoint, `homeTeamOdds.moneyLine` /
`awayTeamOdds.moneyLine`.

```bash
python3 analysis/pregame_softness/pregame_softness_kalshi.py     analysis/pregame_softness/pregame_softness_snapshots.csv
python3 analysis/pregame_softness/pregame_softness_polymarket.py analysis/pregame_softness/pregame_softness_polymarket_snapshots.csv
```
