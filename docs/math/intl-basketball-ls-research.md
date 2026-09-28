# International basketball, "long/short": what it can be, the free anchor, one registration

2026-09-27 (US), fetches 2026-09-28 00:08–00:20Z. The operator's idea: a long/short,
relative-value book on the European and other niche basketball leagues the venue has just
listed, on the theory that nobody watches them so prices are soft. This asks what L/S can
mean when every game has **one** market, and whether a free external price exists to
anchor it. It sits beside docs/math/intl-basketball-winner.md (the pregame and in-play
calibration reads, registered 09-27) and does not repeat them. No prod access: everything
below was read from public endpoints on the day; nothing on the recorded tape was queried.

## 1. Two corrections to the premise, read off the venue

`gateway.polymarket.us/v2/sports` names each league, and every market's `description`
names its settlement source ([sports listing](https://gateway.polymarket.us/v2/sports),
[events, e.g. lnbp](https://gateway.polymarket.us/v2/leagues/lnbp/events)):

| venue slug | the venue's own name | teams on the board | settles from | recorded in the repo as |
|---|---|---|---|---|
| `lnbp` | "LNBP" | Diablos Rojos del México, Astros de Jalisco, Lobos de Puebla | "LNBP" | **LNB Pro A (France) — wrong: this is Mexico's LNBP** |
| `bbl` | "Basketball Bundesliga" | Alba Berlin, Bamberg, SC Jena, Rasta Vechta | "Basketball Bundesliga" | **BBL (UK) — wrong: this is Germany** |

"LNB Pro A" stands in intl-basketball-winner.md, STATUS §0ci, and the
comments in core/leagues.py, core/ladder/live.py and docker-compose.basketball.yml;
intl-basketball-winner.md also calls `bbl` "the British BBL". The slugs, and therefore the
recording, are right; the names are not, and they decide which external source can
anchor a price (Kalshi's `KXLNBPGAME` and `KXBBLGAME` are these two leagues; its French
and British series are `KXLNBELITEGAME` and `KXSLBGAME`).

Second: intl-basketball-winner.md says "there is no state feed" for these leagues. The
venue's own event payload carries one. `lnbp-dia-ast-2026-09-27`, in play at 00:08Z:
`eventState.score '62-78'`, `period 'Q4'`, `elapsed '03:05'`, quarter-by-quarter
`periodScores`, and a `sportradarGameId` on every event in all eight leagues. ESPN has
nothing (§3).

All 58 listed events carry one market, `basketball_team_full_game_winner`, and
`marketSides[0]` is `long: true, ordering: 'home'` on 58 of 58: **YES is the home team**.

## 2. What "soft" looks like on the book

At 00:09Z, **39 of 58 events had no book at all** (`bestBidQuote` null; the side prices
shown are placeholders around 0.04/0.97). Of the 19 with a book, the ten EuroLeague games
of 09-29/30, 36–42 h before tip
([book endpoint](https://gateway.polymarket.us/v1/markets/aec-eurolg-efs-rma-2026-09-29/book)):

| | venue, 10 EuroLeague games | Kalshi, the same 10 games |
|---|---|---|
| touch spread | 2–10¢, median 7¢ | 1–6¢ per team market; tighter still combining both team markets |
| touch size | median ~30 contracts bid / ~22 offer (5 to 2,524) | 1 to 731 |
| traded so far | 0–113 contracts per game | 0–1,353 contracts per market |
| last season, settled | — (not listed) | median **139,277 contracts per market**, 307 games |

"Nobody cares" is true of the venue: thin, wide, two thirds of the board unquoted. It is not
true of the game — the same fixtures trade six figures a market on Kalshi.

## 3. Reference prices — what a program may fetch for free

| source | opened | covers | returns | limits / cost | terms | pregame / in play | verdict |
|---|---|---|---|---|---|---|---|
| **Kalshi public API** | [series?category=Sports](https://api.elections.kalshi.com/trade-api/v2/series?category=Sports), [markets?series_ticker=KXEUROLEAGUEGAME](https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker=KXEUROLEAGUEGAME&status=open), [historical/markets](https://api.elections.kalshi.com/trade-api/v2/historical/markets?series_ticker=KXEUROLEAGUEGAME&limit=1000), [series/KXEUROLEAGUEGAME](https://api.elections.kalshi.com/trade-api/v2/series/KXEUROLEAGUEGAME) | EuroLeague `KXEUROLEAGUEGAME` (10 of 10 venue games of 09-29/30, matched by full team name); Mexico `KXLNBPGAME` (2 of 2 tonight); `KXVTBGAME` (2 games 09-30); Slovenia `KXSKLGAME` (Krka–Zlatorog); German `KXBBLGAME` and `KXBSLGAME` exist with **0 open** today (171 and 115 historical events); **no Danish or Hungarian basketball series** | two markets per game (one per team), touch + sizes, volume, OI, rules; settled markets before the 2026-07-29 cutoff under `/historical/` with **hourly bid/ask candlesticks** ([example](https://api.elections.kalshi.com/trade-api/v2/historical/markets/KXEUROLEAGUEGAME-26MAR311445PARVIB-PAR/candlesticks?start_ts=1774958400&end_ts=1774990800&period_interval=60)) and trades | token budgets per authenticated tier, Basic 200 read tokens/s ([rate limits](https://docs.kalshi.com/getting_started/rate_limits)); unauthenticated limits not published | "public endpoints that don't require API keys" ([quick start](https://docs.kalshi.com/getting_started/quick_start_market_data)); market data is "public information on the exchange" ([help](https://help.kalshi.com/en/articles/13823854-kalshi-api)); the Developer Agreement did not open (HTTP 429) | both; markets list ~3 days before tip | **the anchor.** Already recorded by `core/kalshi/events` for other series; adding these is an allowlist change |
| **The Odds API** | [sports list](https://the-odds-api.com/sports-odds-data/sports-apis.html), [plans](https://the-odds-api.com/), [v4 guide](https://the-odds-api.com/liveapi/guides/v4/), [bookmakers](https://the-odds-api.com/sports-odds-data/bookmaker-apis.html), [terms](https://the-odds-api.com/terms-and-conditions.html) | `basketball_euroleague` only (plus `basketball_nbl`); **none of the seven national leagues** | h2h per bookmaker; region `eu` includes `pinnacle` and `betfair_ex_eu` | free: 500 credits/month; cost = markets × regions (h2h × eu = 1); historical odds **paid only** (10 per market per region) | internal models permitted; no resale or redistribution as a data product | "live and upcoming games" | **second EuroLeague anchor** at ~16 calls/day free — enough for T−6h and T−1h per slate. Whether Pinnacle actually quotes EuroLeague in the payload is unverified (needs a key) |
| Pinnacle direct | [README](https://github.com/pinnacleapi/pinnacleapi-documentation/blob/master/README.md) | — | — | — | "closed for the general public since July 23rd, 2025"; by application | — | **not proposed**; reachable only through The Odds API `eu` |
| Betfair Exchange | [app keys](https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687105/Application+Keys), [restricted regions](https://support.developer.betfair.com/hc/en-us/articles/28271961503516-Which-IP-regions-are-restricted-from-accessing-the-Betfair-API) | — | — | delayed key 1–180 s snapshots; live key £499 | personal betting only; **USA is a restricted IP region** | — | **not proposed** |
| EuroLeague "Competition Engine" | [E2026 games](https://api-live.euroleague.net/v2/competitions/E/seasons/E2026/games), [E2025 games](https://api-live.euroleague.net/v2/competitions/E/seasons/E2025/games), [swagger spec](https://api-live.euroleague.net/swagger/v2/swagger.json) | EuroLeague only | schedule and results: 2026-27 has 380 games (10 played); 2025-26 has 402 (380 regular season, **home win rate 0.637**) | answered without a key | the spec declares an `ApiKey` scheme and publishes **no terms or licence** | schedule, results | schedule/results cross-check only, not a dependency, until terms are confirmed. No odds |
| ESPN site API | [basketball leagues](https://sports.core.api.espn.com/v2/sports/basketball/leagues?limit=200), [euroleague scoreboard](https://site.api.espn.com/apis/site/v2/sports/basketball/euroleague/scoreboard?dates=20260924) | 15 basketball leagues, **none European**; the `euroleague` slug answers 200 with **zero events** on 2025-12-04, 2026-03-31, 2026-05-24 (the Final) and 2026-09-24 | — | — | — | — | **no coverage** |
| Rating sites | [Eurohoops rankings](https://www.eurohoops.net/en/trademarks/2010226/eurohoops-2026-27-euroleague-power-rankings/) (09-20) | — | editorial ordinal ranking, no ratings or probabilities | — | — | — | nothing machine-readable found; an Elo would have to be built, i.e. a model |

Two joins that will bite. **Codes collide across the three spaces**: Kalshi `PAR` is
Paris and `KPB` is Partizan; the venue's `par` and EuroLeague's `PAR` are Partizan and
`prs`/`PRS` is Paris; on the venue `fcb` is Barcelona in `eurolg` and Bayern Munich in
`bbl`, where the same club is `bay` in `eurolg`.
**Names differ in small leagues**: exact normalised full names matched 10/10 EuroLeague
games and failed on Slovenia (venue "Krka", Kalshi "KK Krka Novo Mesto"). An explicit
per-league table, never codes and never containment.

**Settlement differs on postponement.** The venue waits up to two weeks, then settles at
"the last fair market price"; Kalshi settles "to a fair price" if the game has not started
within 48 h. Kalshi fair-priced **3 of 307** EuroLeague games last season (0.50/0.50 twice
on 2026-03-05, 0.70/0.30 on 2025-12-04). A hedged pair can settle apart on ~1 % of games.

## 4. What "long/short" can mean with one market a game

Fees per contract at the price paid: venue `0.0695·p(1−p)` (core/fees.py, the row's own
coefficient on history), Kalshi `0.07·p(1−p)` model fee (`KXEUROLEAGUEGAME`: `quadratic`,
multiplier 1, no scheduled change; the charged fee is rounded to the account's grid,
[fee rounding](https://docs.kalshi.com/getting_started/fee_rounding)). At p = 0.5: 1.74¢
and 1.75¢.

**A basic fact about the book first.** Game outcomes are independent binaries, so a book
balanced long-home against long-away across N games has variance `Σ p_i(1−p_i) ≈ N/4`
whether or not it is balanced. **Balancing hedges common factors only** — a league-wide
home edge the anchor gets wrong, an early-season drift in team strength — never the
outcomes. "Short" on one market means buying the complement.

**(a) Cross-venue: the same game on two venues.** Exists for every EuroLeague game Kalshi
has listed so far (10 of 10) and the Kalshi-listed national games. Buy home on the venue
at `a_V`, buy away on Kalshi at
`1 − b_K` (b_K = Kalshi's effective home bid, the better of the home market's bid and
one minus the away market's ask):

    π = b_K − a_V − 0.0695·a_V(1−a_V) − 0.07·b_K(1−b_K)        (and the mirror)

locked at entry, no outcome variance except the postponement basis. Hurdle ≈ 3.5¢ of
gross crossing at even prices, 2.2¢ at 0.8/0.2. Needs matched instants
(docs/math/cross-venue-status.md: buckets manufacture gaps) and a Kalshi account. Power
is not the question — it is a
**count** of crossings at displayed size. Precedent: CFB pregame, 72 of 76 games within
10¢ at a mean gap of 1.8¢ against ~3.25¢ of cost, no arbitrage (STATUS §0aj). The matched
REST snapshot today:

| 00:12Z, home first | venue bid/ask | Kalshi effective bid/ask | venue mid − Kalshi mid | best locked π |
|---|---|---|---:|---:|
| Dubai – Barcelona | 0.65/0.74 | 0.68/0.69 | +1.0¢ | −7.1¢ |
| Efes – Real Madrid | 0.48/0.54 | 0.49/0.51 | +1.0¢ | −6.5¢ |
| Zalgiris – Olympiacos | 0.39/0.43 | 0.41/0.43 | −1.0¢ | −5.4¢ |
| Fenerbahce – Bayern | 0.80/0.82 | 0.81/0.80 (crossed 1¢ gross, −2.2¢ after two Kalshi fees) | +0.5¢ | −2.2¢ |
| Crvena zvezda – Hapoel TA | 0.50/0.58 | 0.51/0.55 | +1.0¢ | −8.5¢ |
| Valencia – Baskonia | 0.74/0.81 | 0.75/0.76 | +2.0¢ | −4.6¢ |
| Milano – Virtus | 0.69/0.76 | 0.71/0.73 | +0.5¢ | −6.9¢ |
| Paris – Partizan | 0.52/0.61 | 0.54/0.58 | +0.5¢ | −9.4¢ |
| Maccabi – Besiktas | 0.62/0.72 | 0.64/0.67 | +1.5¢ | −8.2¢ |
| Panathinaikos – ASVEL | 0.86/0.90 | 0.87/0.87 | +1.0¢ | −2.6¢ |

One REST instant, 40 h before tip: a picture, not a measurement (REST ran a median
54–62 s behind the stream in play, STATUS §0cd). What it shows is the shape: **the
venue's wide book brackets Kalshi's in 10 of 10**, the mids agree to 2¢, nothing crosses.
Kalshi's tickers put the away team first on all ten (`FCBDUB`: Dubai at home). Nine of
ten mid gaps are positive (home slightly richer on the venue) — a hypothesis at most, and
a YES-side one.

**(b) Anchor versus price.** Long the venue side an external price says is cheap, short
(buy the complement) where it says rich. With Kalshi or Pinnacle as the anchor, one leg,
held to settlement:

    E[π | anchor = truth] = m_K − a_V − 0.0695·a_V(1−a_V)

Scored on settlement, each $1 contract carries sd ≈ 0.5; games for 80 % power at 5 %:
`n = (2.80 × 0.5 / e)²` = **196 at 10¢, 784 at 5¢, 2,178 at 3¢, 4,900 at 2¢**. Even
if all ~60 listed games a week were tradeable that is 3, 13, 36 and 82 weeks; at this read
only 12 of 58 carried a two-sided book within 10¢, and nothing like a 10¢ gap to an anchor
that agrees to 2¢ is on offer. With a home-built **rating** as the anchor it is worse:
the error is team-linked, EuroLeague has 20 teams, and dyadic power saturates at
`n_eff → 20/(2ρ)` (100 at ρ = 0.1, 33 at ρ = 0.3) however many games accrue — and
docs/math/wnba-player-model-preregistration.md already watched a lineup-aware model fail
to beat the venue's own T−1h price on 106 games (the venue better in every row). What
rescues (b) is scoring it on something with less variance than the outcome and that the
selector did not use — §5.

**(c) Intra-venue relative value.** Home/away or favourite/longshot across the league,
e.g. "home favourites overpriced". YES is home, so every YES-price bucket is a home-side
bucket and must be printed beside its away twin; a fade is the same rows at
`−source − (spread + both fees)`, never a second hypothesis (the complement property,
four appearances in two days: docs/math/kalshi-tennis-preregistration.md §0). The base it
must beat: EuroLeague home teams won **0.637** of 380 regular-season games in 2025-26.
Detecting a 3¢ calibration error in a bucket needs ~1,900 games (sd of `y − p` ≈ 0.47);
5¢ needs ~700. Not a four-week read; it is read #1 of intl-basketball-winner.md, sliced,
and slicing does not create information.

## 5. Pre-registration — venue staleness against Kalshi, pregame

Written before any registered statistic has been computed. **Disclosed:** the ten-game
REST snapshot in §4 was read to confirm the anchor exists and joins; it is 40 h before
tip, outside the window below, and the rule was chosen with it in view. No trigger, CLV
or settlement number has been computed on any game.

**5.0 Pre-flight: is the anchor calibrated?** Before any venue price is scored, from
Kalshi's historical endpoint (no venue data): the 307 EuroLeague games of 2025-26 on
Kalshi, less the 3 fair-priced ones; home side from the competition's schedule
(local/road), cross-checked against the ticker's away-first order; Kalshi's home mid at
the last hourly candle ending at or before tip − 1 h, against the result. Brier of that
price, of the constant 0.637 (the same season's home rate — in-sample, which favours the
baseline), and of a coin; the interval of `Brier_Kalshi − Brier_0.637` over games. **If
it does not exclude zero on the favourable side, the anchor is void and §5.1–5.7 do not
run.** Measure the baseline before tying anything to it.

**5.1 Hypotheses.** *H1*: the venue's quotes on these leagues are stale relative to
Kalshi's; when a venue quote sits beyond Kalshi's mid by more than the venue fee, the
venue later moves toward Kalshi. *H0*: the venue is efficient on its own information; the
disagreement is Kalshi's noise, and the venue's price does not follow it.

**5.2 Population and instrument.** Every venue game in a league Kalshi also lists —
`eurolg`, `lnbp`, `bbl`, `vtb`, `bsl`, `slnbl` (`denbl` and `hunbl` have no Kalshi series) —
tipping 2026-09-29 00:00Z to 2026-10-26 23:59Z whose Kalshi twin exists, joined by
an explicit per-league name table (unmatched and ambiguous games excluded and counted).
Decision instants are the Kalshi polls from tip − 3 h to tip − 5 min (the events recorder,
60 s; a trigger that lives between polls is missed, which biases against H1). The venue's
state at each instant is its **stream** as of that instant — never REST. Both require
configuration before the first game counts: the Kalshi series on the events allowlist,
the basketball stream window opened at tip − 3 h. Games before that are excluded and
counted.

**5.3 Trigger — the decision rule, fixed now.** At instant t, with Kalshi's effective home
touch `(b_K, a_K)` from both team markets and `m_K = (b_K + a_K)/2`:

- the anchor exists only if `a_K − b_K ≤ 0.04`; otherwise no decision at t;
- **buy home (YES)** at the venue ask `a_V` if `a_V + 0.0695·a_V(1−a_V) ≤ m_K`;
- **buy away (NO)** at `1 − b_V` if `b_V − 0.0695·b_V(1−b_V) ≥ m_K`;
- the first trigger per game only, one ticket, held to settlement; size scored per $1
  contract, the displayed venue size printed beside.

No threshold is fitted: the trigger is "outside Kalshi's mid by at least the venue fee".

**5.4 Primary statistic, estimator, gate.** Per triggered game, CLV against **the venue's
own** close, net of the entry fee:

    YES:  CLV_V = c_V − a_V − f(a_V)          NO:  CLV_V = b_V − c_V − f(b_V)

`c_V` = the venue's mid at its last two-sided quote with spread ≤ 10¢ in the 30 minutes
before tip; a game with no such quote has no CLV (counted, and still scored on
settlement). Not Kalshi's close: the selector used Kalshi, so under a Kalshi martingale
`CLV_K ≥ 0` by construction and cannot fail. Under H0 `E[CLV_V] = −half-spread − fee < 0`;
it can.

Mean over games; interval the cluster-robust sandwich by **game** with G/(G−1), 1.96,
as `cfb/run_paper_book.py::clustered`, and the same **by slate date** printed beside (a
venue-wide freeze is slate-level, as on 2026-09-05, docs/findings.md C16). **Gate: G ≥ 40
triggered games, mean CLV_V > 0, and both intervals exclude zero.** Fee at each row's
recorded `fee_coefficient` (`core.fees.recorded_fee`; NULL refuses).

**5.5 Sample and power.** EuroLeague alone has 60 games in the window (rounds 2–7, the
competition's schedule endpoint); the Kalshi-listed national games add perhaps 60–80 more
if Kalshi lists them all, which it did not today for BBL or BSL. The trigger rate is
unknown; the snapshot suggests low. With per-game sd of CLV_V at 4.5¢, 40 games detect a
2¢ mean at 80 %; the realised sd and the minimum detectable effect at the realised G are
printed. **Below 40, the read prints UNDERPOWERED and its count, and the count is the
answer**: how often the venue sits outside the anchor by more than its own fee.

**5.6 Printed beside, never gated.**

- Settlement P&L of the same tickets, `y − a_V − f(a_V)` / `(1−y) − (1−b_V) − f(b_V)`,
  labelled UNDERPOWERED with its minimum detectable effect (~5¢ needs ~780 games).
- `CLV_K` against Kalshi's close, labelled "shares the selector".
- **Who moved**: of the gap `m_K(t) − m_V(t)` at trigger, the share closed by the venue
  and by Kalshi at tip.
- **The locked twin**: triggers where Kalshi's own touch and fee also clear (§4a),
  executable size `min(venue touch, Kalshi touch)`, count and dollar sum, no interval —
  a lookup, not an inference.
- Rows: per league; home (YES) and away (NO) triggers separately — a home-only result is
  a home-price result.
- Phantom check: venue prints through the displayed ask/bid while the trigger stood.

**5.7 Kill conditions, written before they can be excused.**

1. §5.0 fails: no anchor, nothing runs.
2. The gate fails at G ≥ 40: dead as a pregame rule. No second threshold, window, anchor
   spread, league cut or exit rule.
3. Fewer than 40 triggered games by 2026-10-26: UNDERPOWERED; the count is reported and
   the design is not extended by re-cutting — only by more weeks under this text.
4. Frame: any pairing whose flip gives a smaller mean |venue mid − Kalshi mid| than
   as-is (the STATUS §0aj test: 2.57¢ vs 73.36¢), or any ambiguous name, voids that
   league's rows until the table is fixed and re-registered.
5. A third or more of triggers phantom (printed through), or inside a venue-wide freeze
   (≥ 80 % of a slate's venue books unchanged for ≥ 10 min while Kalshi moved): the tape
   is a picture; P&L rows void.
6. More than two games settled apart by the two venues: the locked-twin row is void.

**5.8 Not on this list and not added after the tape:** Pinnacle as a second trigger (it
may be printed as a diagnostic agreement rate if a key exists), in-play instants (they
need Kalshi's websocket, which needs an account), maker quoting, any Elo, any window,
threshold or league added later. Each is a new registration.

## 6. What could not be verified

- Kalshi's Developer Agreement (HTTP 429) and fee schedule PDF (HTTP 429). The 0.07
  coefficient is the repo's constant, also flagged UNVERIFIED in
  docs/math/kalshi-tennis-preregistration.md.
- Whether The Odds API returns Pinnacle or Betfair prices for `basketball_euroleague`
  today: that needs an API key, which means creating an account; not done.
- The EuroLeague API's terms: none published; it answered without the key its own spec
  declares.
- Whether Kalshi will list BBL and BSL games this season (171 and 115 last season, 0
  open today) and how far ahead it lists (round 1 opened ~3 days before tip).
- Whether the venue's REST side prices lag its stream pregame as they do in play; the
  registration uses the stream only.
- Nothing on prod: recorder coverage for these leagues since 09-27 was not checked.
