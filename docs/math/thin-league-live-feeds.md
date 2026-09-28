# Free live score feeds for the thin basketball leagues

2026-09-28. Surveyed by a research agent that fetched every source it names; the
**EuroLeague row was re-checked by hand** (the shot log's `UTC` field and the 2026-27
schedule), the others are the agent's measurements, not re-derived. Raw notes and sample
responses were kept outside the repository. What matters for the speed read
(docs/math/thin-league-speed-preregistration.md) is a per-play **wall-clock** time that can
be pulled after the game; live refresh speed matters only for trading on it.

| venue | source | venue game -> source id | wall clock per play | verdict |
|---|---|---|---|---|
| eurolg | `live.euroleague.net/api/Points` (+ `PlaybyPlay`, `Header`) | `api-live.euroleague.net/v2/competitions/E/seasons/E2026/games`: club table + start minute + home = local | **yes**, `UTC` to the second (checked) | usable, no key; saved per game from 2026-09-29 |
| lnbp | Sportradar Connect public embed, `fixture_detail` play-by-play | `/v1/embed/14/fixtures` (`startTimeUTC`, `isHome`) | inferred from UUIDv1 event ids (502 of 502 decode) | usable with care; live refresh ~30 s (median 30.2 s over 28 polls) |
| bbl | easycredit-bbl.de game page, server-rendered `realTime` | ids from page links | yes | partial: page cached ~60 s; the JSON API needs a token |
| vtb | Infobasket `org.infobasket.su/Widget/GetOnline/<id>` | `/Comp/GetCalendar/?comps=55613` | yes, Moscow time | usable |
| bsl | Genius Sports `data.json` | no 2026-27 ids found; federation site behind a bot challenge | no | none yet |
| denbl | Sportality API behind basketligaen.dk (+ a push stream) | `/api/sports-v2/game-schedule` | yes, `realWorldTime` | usable |
| slnbl | KZS public API -> Genius `data.json` | `api.kzs.si/.../matches?competitionId=608` | no | partial (score only) |
| hunbl | MKOSZ `film.php` score by game-second | match code only after the game | no | partial |

**One observation, not a measurement** (agent, LNBP, 2026-09-28): the winning 3-pointer
decodes to 01:44:45.98Z and the venue's score updated at 01:44:50.23Z, 4.2 s later.

Next in order of value: VTB and Denmark (wall clock, free), then LNBP through the embed.
Nothing here needs an account or a key.
