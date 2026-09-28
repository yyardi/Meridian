# International basketball on the venue — one market a game, and what that allows

2026-09-27. The venue began listing European and other international
basketball this week: EuroLeague (20 events, first tip 2026-09-29 16:00Z),
Mexico's LNBP (16, first 2026-09-27 22:15Z), Germany's Basketball Bundesliga (9),
VTB United (6), the Turkish BSL (1), and the Danish, Slovenian and Hungarian
leagues (2 each). *(Corrected 2026-09-28 from the venue's own descriptions:
`lnbp` is Mexico's LNBP, not France's LNB Pro A; `bbl` is Germany's, not the
UK's.)* Read
off `api.polymarket.us` on the day: **every event carries exactly one market,
`basketball_team_full_game_winner`, and no spread or total.**

## What that rules out

The ladder arbitrage needs rungs. With one market per game there is no pair to
buy and sell against each other, so no detector, sampler or executor is
launched for these leagues; they are **recorder-only** in the daily scheduler
(`core/ladder/live.py: BASKETBALL_INTL_LEAGUES`), like cricket.

## What it allows, registered before a price is read

Two reads, both on the winner market, both needing nothing but the tape and
the settlement:

1. **Pregame calibration and movement.** Brier and log loss of the venue's
   price at T−6h and T−1h against settlement, per league, game-clustered; the
   size of the T−6h → T−1h move and whether it sticks — the same design as
   docs/math/cricket-preregistration.md §3, with no toss to split on. If the
   late price is not better calibrated than the early one, the movement is
   noise; if it is, the movement is information.
2. **In-play calibration by drawdown.** The stream tape at update resolution
   (`launch_stream_slate.sh <league>` from the planner, 150-minute windows):
   Brier of the in-play price by the pregame favourite's drawdown bucket, as
   docs/math/cricket-inplay-dip.md §4. **The state feed is the venue's own**:
   its event payload carries score, period, clock and quarter scores, plus a
   `sportradarGameId` (corrected 2026-09-28; ESPN covers none of these
   leagues). The relative-value design built on Kalshi's same-game markets is
   docs/math/intl-basketball-ls-research.md.

Estimator: per-game clusters, sandwich intervals, populations and counts
printed on every number, fee at the row's own coefficient. Sample: the venue
lists ~60 games a week across the eight competitions; a 150-game read is
about a month away.

## What is recorded from today

- `docker-compose.basketball.yml` — the pregame board recorder for
  `basketball-intl` (best bid/ask, size, fee coefficient, live flag, score
  field) every 15 minutes, every minute inside three hours of tip;
- the stream recorder per game window, from the 12:10Z planner;
- the venue's settlement, through the same route the paper book uses.

Nothing here places anything; the first number appears when the tape does.
