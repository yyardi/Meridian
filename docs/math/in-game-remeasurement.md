# In-game hypotheses, re-measured on the 50-game archive

**DESCRIPTIVE. NOTHING HERE IS A VERDICT, AND NOTHING HERE CHANGES ONE.**

Every gated verdict in [pulse-hypotheses.md](../pulse-hypotheses.md) stands
exactly as written. This page reports what the same code computes against a
larger tick archive, and draws no conclusion from it. If you want to know
whether a hypothesis passed, that page is the answer and this one is not.

## Why this page exists, and why it is not the ledger

The operator asked for every in-game hypothesis to be replayed against the
200ms archive, on the standing complaint that in-game hypotheses were never
tested in-game.

**That complaint turns out to be wrong on the facts**, and the ledger is the
evidence: #1 was gated on 444 runs across 11 games, #2 on 75 trades across 11,
#6 on 28,514 windows across 17, #7 on 473 appearances across 15, #16 on 40
observations across 19, #17 on 40 trades across 26. All of those are live
in-game tick data. There is no untested in-game signal. The one hypothesis
never measured is **#5**, which is not blocked by effort — it is blocked by
adverse selection having FAILED, which is the thing it depends on.

So the sweep as literally requested would mean re-running settled hypotheses
and issuing fresh verdicts. The gate policy of 2026-08-08 — the operator's own
directive — forbids exactly that:

> Existing gated verdicts are NOT reopened. [...] Re-running a dead hypothesis
> to a longer gate **after seeing its numbers** is exactly the re-tuning this
> preamble's own rule forbids: *the gate is written before the number is
> computed.* Extending a gate is only honest when it is done blind.

The honest thing that remains is a **descriptive re-measurement**: run the same
code on today's archive, report what it says, and let the verdicts alone. That
is the same distinction [`core/audit/hand_trades.py`](../../core/audit/hand_trades.py)
already draws — it is descriptive by construction and is not permitted a
verdict, for the same reason.

**If the operator wants a verdict reopened**, the way to do it honestly is to
fix a NEW gate blind — written down before these numbers are looked at — and
run against that. Reading the table below and then choosing a gate is the
failure mode the policy exists to prevent. The numbers are already computed, so
that door is now closed for anyone who reads this page.

## What is in scope

| # | hypothesis | in-game? | standing verdict — UNCHANGED |
|---|---|---|---|
| 1 | run overreaction | yes | **FAIL**, gated 2026-08-06 · 444 runs / 11 games · −0.32¢ at +5min, CI [−2.69, +2.05] vs a 6¢ round trip |
| 2 | first-score overreaction | yes | **FAIL**, gated 2026-08-07 · 75 trades / 11 games · −3.88¢/contract, CI [−9.73, +1.97] |
| 6 | tail volatility | yes | **FAIL**, gated 2026-08-08 · 28,514 windows / 17 games · open edge −0.651¢, CI [−0.888, −0.415] |
| 7 | whale / depth | yes | **FAIL**, gated 2026-08-06 · 473 appearances / 15 games · +0.22¢ at +60s, CI [−0.25, +0.68] |
| 16 | trailing-team ML underpricing | yes | **PASS on its terms, NOT TRADABLE**, 2026-08-07 · inverts to −2.20¢ against a team-aware anchor |
| 17 | tight-game ML reversion | yes | **FAIL**, gated 2026-08-18 · 40 trades / 26 games · −9.12¢, CI [−16.77, −1.48] |
| — | adverse selection | yes | **FAIL** · −2.66¢ per filled quote |
| 3, 4 | lead cut, late runs | yes | dead by inheritance with #1 — same mechanism |
| 5 | Q4 tight-game ML | yes | **never measured** — blocked on adverse selection, which failed |

**Deliberately NOT in scope: ladder-sigma.** It appeared on the sweep list, but
its own registration is **pregame** — 362 recorded *pregame* ladders against
final totals. Quoting the mismatch rather than resolving it silently, per the
instruction covering ambiguous registrations.

## Caveats that apply to every row below

1. **The archive grew far less than the game counts suggest, and I had this
   wrong at first.** "11 games then, 50 now" is not the comparison. The live
   archive begins **2026-07-31** and had already accumulated ~26 games by
   2026-08-06 (when #1 and #7 were gated), ~31 by 08-07 and ~36 by 08-08 —
   while those studies cited 11, 15, 11 and 17 games respectively. So the
   per-study counts were never archive size; they are **eligible** games, after
   each study's own filters (usable tick density, an open-phase window, a
   qualifying run). The honest comparison is eligible-then vs eligible-now, and
   the archive itself grew roughly 40–90%, not five-fold.
2. **A larger archive is not automatically a better test.** More games raise
   power, and they also change the population: the games recorded since the
   original runs are a different slate, not more of the same one. The whole
   archive spans 2026-07-31 to 2026-08-18 — about three weeks of one season.
3. **These runs print their own gate line.** The modules were written to
   verdict themselves, so their stdout says PASS or FAIL against their original
   gate. That output is *not* reproduced here as a verdict and must not be
   quoted as one.
4. **Costs and fill models are unchanged** from each registration. Nothing was
   re-tuned to make a number move.
5. **The team-form staleness window does NOT reach these replays**, and the
   check is worth stating rather than assuming. `team_game_logs` was frozen
   from 2026-07-31 to 2026-08-18 by a silent ESPN field rename (found by
   Builder B; backfill pending). Every hypothesis re-measured on this page
   reads **only `market_snapshots`** — grepped, not assumed: #1, #2, #6, #17
   and adverse selection carry zero references to `TeamGameLog` or the feature
   layer. So a frozen game log cannot move any number here.

   It does reach **`core/pulse/win_curve.py`**, which has eight such
   references and backs ledger rows **#15 and #16**. Neither is on this page —
   #16 is a settled PASS-not-tradable and #15 an ungated diagnostic — but
   anyone re-running either during the freeze window is reading stale form,
   and that is where the caveat belongs.

## Measurements

*(Added as each run completes. Each row states what the module computed today,
beside the standing verdict it does not replace.)*
