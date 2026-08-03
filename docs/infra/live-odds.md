# ESPN publishes no live in-game odds

**Measured 2026-08-02 against a live WNBA game. The in-game update cadence is
not "slow" — it is never.**

Module: [`core/feeds/live_odds_recorder.py`](../../core/feeds/live_odds_recorder.py)

## What was asked, and what the measurement said

The plan was to poll ESPN's live odds for in-progress games at the highest
useful cadence, on the reasoning that PULSE cannot work against a 20-minute-old
anchor. The first step was to measure how often the endpoint actually changes.

It does not change, because it is not there.

| Surface | Behaviour during an in-progress game |
|---|---|
| `scoreboard` → `odds` | **Empty.** 0 providers across 120 frames / 238s. Pregame events *in the same payload* carry DraftKings; the block is stripped the moment a game tips. |
| `summary` → `pickcenter` | Present but **frozen**. 0 changes across 83 frames / 7 min, holding spread −1.5 and total 186.5 while the score moved 43-37 → 49-43. |
| `summary` → `winprobability` | Genuinely live — 15 updates in 7 min. But it is ESPN's own model output, not a market price. |
| core API `…/competitions/{id}/odds` | 404 until the game is final. |

The `pickcenter` case is the dangerous one. It looks exactly like a live line:
it is present, it is well-formed, and it sits next to a score that *is*
updating. It is the pregame number surviving into the game. A poller that wrote
it every 15 seconds would produce thousands of rows carrying a stale line, and
PULSE would read them as a live anchor. **That would be worse than having no
data at all**, because it would be wrong rather than absent.

So the answer to "what cadence should we poll live odds at?" is: none. There is
no live sportsbook line obtainable from ESPN at any polling rate. Getting one
means a paid odds feed.

## What the module does instead

The complaint that prompted this is still real. Odds land only when the
6-hourly scheduler happens to run, which is why the database holds **3**
in-play-adjacent odds rows in total. That same under-sampling starved
[news-windows.md](../math/news-windows.md), which reported zero triggers with
its book leg polled every ~20 minutes against a lag the literature measures in
minutes.

So the recorder captures **pregame line movement at fine resolution**, which is
the thing that both exists and is tradable:

- polls the scoreboard continuously — one small request, 29ms median latency,
  ~0.07 req/s against an `ESPN_RPS` budget of 3;
- writes a row **only when a provider's numbers change**, so the table stays
  small and "the line moved" is a query rather than a diff across thousands of
  identical rows;
- re-writes an unchanged line every 30 min as a heartbeat, so "no rows for six
  hours" is not ambiguous between a still market and a dead recorder — the same
  ambiguity `InjuryPoll` exists to remove;
- keeps polling during games, so if ESPN ever does start publishing a live line
  we capture it the day it appears rather than the day someone notices.

## The quarantine rule

Anything captured while a game is in progress is written under a modified
provider name:

```
DraftKings  ->  DraftKings (live)
```

`core.backtest.engine._is_live_provider` matches on the substring `live` and
already excludes such rows from every backtest, CLV calculation and entry
price. Pregame rows keep their plain name and stay fully usable.

This matters because no provider name in the database contained `live` before
this module existed — so the existing exclusion, while correct, had never
actually excluded anything. `test_in_progress_odds_are_quarantined_as_live`
pins it.

`is_closing_line` is never set here. The scoreboard nests current prices under
keys literally named `close`, even for unplayed games; trusting that name would
mark upcoming games as closing lines and corrupt CLV, which is the headline
metric.

## Status: built, tested, not running

The container is defined but **stopped**. It cannot write: Supabase's
session-mode pooler allows 15 clients across the whole project and that ceiling
is already saturated — the container logged `EMAXCONNSESSION` on its first
write, and the scheduler has logged it too.

This is a live operational problem independent of this module; see
[live-cadence.md](live-cadence.md#the-connection-ceiling). Start the container
once the pooler question is settled:

```bash
docker compose up -d live-odds-recorder
```

## What is still unmeasured

**How fast pregame lines actually move.** No line moved during any observation
window, so the 15s default interval is a safe guess rather than a measured
choice. Once this has run through a slate, the observed inter-change gaps
should set it — polling faster than the book reprices buys nothing, which is
the same discipline applied to the Polymarket board in
[live-cadence.md](live-cadence.md).
