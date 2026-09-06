# Engine cohorts: the sensitivity was uninformative, and how to make that structural

**Written 2026-09-05 by Quant D.** Two findings: the engine-purity sensitivity
attached to the CFB headline measures nothing, and the fix that would have
prevented it is a one-line change to what we stamp.

---

## 1. ★ The two "engine commits" are the same quoting engine

The CFB tape spans `4529951a` → `63e7f1b8`, deployed mid-slate, with **9 of 61
games straddling the boundary**. That looked like a confound and I reported it
as one. It is not.

    git diff 4529951a 63e7f1b8 -- core/quote     ->  EMPTY

`core/quote/` is **byte-identical** across the two commits. So is `core/pulse/`.
The diff touches 21 files — Dockerfile, Kalshi mapping and recorder, a Kalshi
migration, health checks, docs, dashboards, tests, `analysis/guards.py` — and
the only two that could plausibly reach behaviour do not:

- `core/config.py`: `KalshiConfig.poll_interval_seconds` 60 → 120. Kalshi
  polling cadence, cannot affect QUOTE fills.
- `core/storage/models.py`: adds a nullable `venue_occurrence_time` column to
  `KalshiGame`. A new column on a Kalshi table.

**Nothing that produces a quote changed.** The straddling games are not
contaminated, because there was nothing to contaminate them with.

## 2. So the sensitivity was random game removal, and it behaves like it

Restricting to "single-commit" CFB games drops 9 games chosen by an event that
is irrelevant to quoting. Tested against that null directly — drop 9 CFB games
at random, 4,000 draws, and compare the shift:

    CFB, all 35 games          -2.077c
    single-commit, 26 games    -1.559c      shift +0.517c

    random 9-game drop:  sd 0.464c,  5-95% [-0.738, +0.788]
    observed shift +0.517c is exceeded in magnitude by **25.1%** of random drops

**Entirely typical.** The sensitivity's failure to clear zero is power loss from
dropping a quarter of the games, and its point-estimate shift is unremarkable.

> **The engine-purity caveat should not travel with the headline.** It was a
> reasonable precaution when the commits were opaque; once opened, the two
> binaries quote identically and the restriction carries no information.

The headline stands as measured: **CFB −2.077c [−3.630, −0.523], 19,075 real
fills, 35 games.**

## 3. ★ The fix: cohort identity is the DECISION PATH, not the repo commit

This whole detour existed because we stamp `engine_commit` — a **repo** commit,
which changes for docs, dashboards and unrelated subsystems. Under a decision-path
identity, **both commits carry the same cohort id, zero games straddle, and the
sensitivity is never needed.**

    engine_commit    : repo HEAD          — provenance, keep it
    decision_hash    : tree hash of the quoting decision path — COHORT IDENTITY

`decision_hash` = hash over the source that determines a quote: `core/quote/`
plus the modules it imports that carry behaviour, plus the config values it
reads. Stamped per fill exactly as `engine_commit` is, fail-closed.

Two properties follow:

- **Cohorts stop fragmenting on irrelevant deploys.** Most deploys do not touch
  the decision path; today's did not. Under commit identity we lost 9 games to
  a Kalshi cadence change.
- **A genuine behaviour change is unmissable.** If `decision_hash` moves, the
  quoting logic really did change, and a straddling game really is contaminated.
  The signal stops being drowned in noise from unrelated commits.

This programme already has the precedent: the D1 pre-read pin recorded
`core/quote/` as "byte-identical to 0addd69" rather than naming a commit.

## 4. Verifiable, not reconstructable — the missing artifact is a deploy log

Today the deploy boundary was **reconstructed** by noticing `engine_commit`
change inside the fill tape. That fails silently in the case that matters most:
**a deploy during a quiet period leaves no trace in the tape at all**, yet
changes the binary for every fill afterwards.

So a cohort is only verifiable with a second, independent record:

    deploy_log(ts, from_commit, to_commit, from_decision_hash, to_decision_hash)

and the validity check that makes it worth having:

> Every fill's `decision_hash` must equal the deploy log's active hash at its
> `filled_at`. Disagreement means the stamping is broken — which per-fill
> stamping alone can never reveal, because it is self-consistent by
> construction.

That is the integrity-versus-validity distinction: per-fill stamps reconcile
with themselves; only a second source can falsify them.

## 5. And if the decision path *does* change, the quiet window is nearly free

Measured on the CFB tape (2026-09-03 → 09-05, 48 games):

    wall-clock minutes spanned          2,822
    minutes with ANY game live          1,112  (39.4%)
    quiet gaps                          1,018 min (17.0h) and 692 min (11.5h)

**Two multi-hour daily windows with no game live.** So "never change the
decision path while a game is in progress" costs almost nothing — the mid-slate
deploy that started this was avoidable, not forced. The rule only needs to bind
on decision-path changes, which are rare; everything else can deploy whenever.

---

No in-sample result justifies capital. The forward test is the evidence.

---

## 6. ★ The failure mode fired the same day it was written — measured, not hypothetical

§4's caveat said equal `decision_hash` does not mean comparable fills. The
2026-09-05 slate supplied the instance within the hour:

    hour   games  markets     rows       FILLS
    17:00     16     2655  1,138,926     4,937
    18:00     17     2807  1,171,813         0
    19:00     29     4448  1,181,502         3   <- peak of the slate
    21:00     16     2599  1,252,211         0

**Recording never faltered and volume ROSE.** Fills fell ~1000x at a constant
`decision_hash`, with the code byte-identical throughout.

The mechanism is arithmetic (a1): `engine.py:260` books on `mid <= bid`, which
with a positive spread requires the mid to FALL THROUGH our bid. A frozen book
cannot produce that, so a frozen board yields zero fills no matter how much
volume the recorder writes.

**So the sentence is no longer a caution, it is a measurement**: on 2026-09-05
the code agreed exactly and the fills went to zero.

## 7. The minimum regime stamp — two dimensions, each earned by an observed failure

A regime stamp answers what `decision_hash` cannot: were these two windows
*comparable markets*. The temptation is a rich schema nobody validates. The
disciplined version is the smallest set that catches the failures we have
actually seen.

**Dimension 1 — BOOK UPDATE FRACTION.** Share of live markets showing more
than one distinct (bid, ask) pair in the window. Measured on the freeze it
separated **0.0% against 74.4%** — total separation, not marginal, which is
the strongest possible case for a stamp dimension. Catches the 09-05 failure.

**Dimension 2 — SPREAD DISTRIBUTION** (median and p75 of quoted spread across
live markets). Catches the board-composition failure: CFB median 11c against
WNBA's 4c, identical hash, different economics — the spread sets both which
markets are quotable and how large the overshoot is when a fill books.

**That is the whole minimum.** Volatility, rung density and time-to-settlement
are all plausible third dimensions and none of them has yet produced a failure
that dimensions 1 and 2 would miss. **Rule for adding a third: only when a
pooling error is observed that neither existing dimension catches.** A stamp
grows on evidence, not on imagination.

### ★ The hazard that constrains the design

**A regime stamp must record the market's STATE, not our RESULTS.** The
tempting dimension is something like "how often the mid crossed down through a
touch" — it is closest to what the fill rule needs, and it is computable from
the tape without our quotes. It is still wrong, because it is a near-proxy for
our own fill rate: pooling only windows with similar fill rates conditions on
the outcome and makes the comparison tautological.

So prefer exogenous, upstream quantities — does the book update, how wide is
it — over anything that approximates how well we would have done. Both
dimensions above satisfy that; the discarded one does not.

## 8. Closing the two blind spots — costed, and both estimates were wrong

### Dependency versions: cheap to implement, expensive in fragmentation

The decision path's third-party imports are exactly **three**: `scipy 1.18.0`,
`sqlalchemy 2.0.51`, `structlog 26.1.0`. Hashing resolved versions is one line.

**But `scipy` is used only at `adverse_selection.py:320` and `:339`, both
`stats.t.ppf` for confidence intervals — pure SCORING.** The quotable band
uses none of it. So a naive dependency hash would fragment every cohort on a
scipy bump, for a library that cannot touch a quote. That is the disease this
whole scheme exists to cure, reintroduced one level down.

**Real cost** = curate the dependency list the same way `DECISION_FILES` is
curated: named, with a written reason each, drift-guarded against new imports.
Cheap, but it is curation work rather than a lockfile hash. A lockfile hash
specifically is the wrong instrument — it moves on dev-only bumps.

### ORM / schema: mostly already closed, and not via the ORM

The decision path does **not** reach the database through the ORM. It uses raw
`text("""...""")` SQL literals at `engine.py:207, 354, 364` — **which are
inside a file the hash already covers.** Any change to what the engine asks for
already moves `decision_hash`, for free.

**Residual, and it is narrower than "a schema hash":** a schema change that
alters what those queries RETURN without changing their TEXT — a column's
semantics changing under a stable name, a view redefinition, a trigger. A full
schema hash would fragment on every additive migration and is the wrong trade.
The proportionate instrument is the existing validity discipline: a second
independent source (the migration history) checked against the deploy log, not
a hash.

### The unifying point

Files, environment variables, dependencies — **at every level the structural
closure is wrong in the same direction**, because it tracks what the code
mentions rather than what the decision uses. Each level needs the same
treatment: a named list, a written reason per entry, and a drift guard that
fails the build when something new appears unclassified.

## 9. ★ Where the deploy-log write goes — and why the obvious answer makes the check vacuous

The log is worthless if a human has to remember it: it will be complete when
nothing interesting happens and empty on the day of the unintended mid-slate
deploy. The failure and the record would share a cause, which is the same
defect as per-fill stamping being self-consistent.

**The obvious fix is to have the engine write the log at startup. That is
wrong**, and the reason is the trap this document exists to avoid: if the
engine writes both the log entry and the per-fill stamps, it computes the hash
once and both sides agree **by construction**. The reconciliation would be
vacuous — an integrity check wearing a validity check's clothes.

**The provenances must differ. That is the whole value.**

    scripts/deploy_engine.sh   computes decision_hash FROM GIT at the deployed
                               ref, writes the deploy_log row
    the engine at startup      computes decision_hash FROM ITS OWN FILESYSTEM
                               plus resolved env, stamps every fill with it

The chokepoint already exists and already has the discipline:
`docker-compose.quote.yml` requires `GIT_COMMIT` and the engine **refuses to
start** when it is empty (amendment 12, fail-closed). The log write belongs
next to that stamp, in the same script, for the same reason.

**What the differing provenance catches**, none of which a single computation
could: a hand-edit made before start, a stale image that does not match the
commit deployed, a deploy that silently did not take, and a compose file whose
env differs from what was intended.

**The restart gap closes itself.** `restart: unless-stopped` means a crash or
host reboot restarts the engine without passing through the deploy script, so
no log row is written. That is fine: a restart of an unchanged image produces
a hash equal to the last log entry, and if the image *did* change, the engine's
self-computed hash disagrees with the log and the check fires. The check does
not need an entry per start, only per change.

**What remains uncloseable, narrower than "a hand-edit":** a hot-patch applied
*after* the engine has computed its hash. Editing the source on a running
container before start is caught; editing it after is not.

Cheap mitigation, and it is nearly free because the machinery already runs:
**recompute the hash on each heartbeat rather than once at startup.** The
exposure window then becomes one heartbeat interval instead of the process
lifetime. Whether that is worth the cycles is a judgement; the guarantee
without it should be stated as "matches at start" rather than "matches".

## 10. The latency question does not bear on QUOTE at all

Two of our own measurements are ~8x apart (36.4s with the price move already
complete, against a 4.46s pipeline and 7.7s at a rested decision) and it is
load-bearing for whether joined game state is tradeable. **For QUOTE the
question does not arise**, and this is checkable rather than arguable:

`engine.py:207` reads, per cycle:

    market_slug, game_id, captured_at, best_bid, best_ask, is_live
    FROM market_snapshots

**No score, no period, no clock, no ESPN.** QUOTE consumes the book and nothing
else, so game-state latency cannot reach a quote by any path. The debate is a
PULSE question wearing a program-wide coat.

**And for QUOTE the binding clock is one we chose, not one the world gave us.**
`MERIDIAN_QUOTE_INTERVAL_SECONDS = 5`, so our quote is exposed at a stale price
for up to a full cycle regardless of how fast anything upstream is. **Any
pipeline improvement below ~5s is invisible in our own behaviour** — a 4.46s
pipeline and a 1s pipeline produce identical quoting. If maker latency ever
matters, the first lever is the cycle, not the feed.

For a taker the clock is genuinely different: event → actionable, and "the
price move already complete" is the damning half of d5's number, not the 36.4s
itself. So both measurements can be correct and measuring different intervals
for different strategies. Naming the endpoints settles it; adjudicating the
numbers without them cannot.

## 11. ★ A third failure mode — and a naming hazard bigger than it

Debugger's finding: 13 CFB games exist only inside the frozen window, and in a
**by-game** statistic each would carry the weight of a game with 880 fills.
Cluster-size heterogeneity moves a by-game mean 5x with a CI 4.7x wider,
depending purely on inclusion. So a cohort can be **code-identical, correctly
regime-flagged, and still not poolable.** That is a real third axis alongside
code identity (§3) and regime comparability (§7), caught by neither.

### It does not reach the CFB headline, for two independent reasons

**(a) The 13 games are excluded twice over.** Checked against the pin: they
hold **49 fills, all 49 PHANTOM, all 49 at or after the 17:39Z freeze**
(20:07Z–20:51Z). The real-population filter alone removes them; the freeze
exclusion alone removes them. Neither depended on the other.

**(b) The headline's point estimate is not a by-game statistic at all.**

    clustered_mean point estimate   -2.0765c
    pooled per-fill mean            -2.0765c   <- identical to 1e-12
    unweighted mean of game means   -3.3526c

`clustered_mean` returns the **per-fill** mean; games enter only through the
confidence interval. Cluster-size heterogeneity cannot move a fill-weighted
estimate. And this population is not heterogeneous in the way described: sizes
run 4 / 180 / 487 / 818 / 1858 (min, p25, median, p75, max), with exactly one
game under 10 fills holding **0.02%** of the sample.

### ★ THE NAMING HAZARD, which is the part that will actually bite

**"Game-clustered" describes the interval, not the estimate.** A reader who
takes it to mean "averaged over games" computes **−3.35c** where we published
**−2.08c** — a gap of **1.28c, larger than the CI half-width of 1.55c** — and
will believe they have reproduced the number.

The two answer different questions and both are legitimate:

    per-fill   what a dollar deployed earns          <- what we report
    per-game   what a typical game looks like

This is the same estimator ambiguity that produced a −3.419c/−3.376c
disagreement earlier in the programme. It recurred because the label survived
the resolution. **Anything quoting one of these must name which**, and
"game-clustered mean" is not a name — it describes the CI and leaves the
estimator implicit.

**So the third failure mode is real and general, and the immediate risk on our
own numbers is not instability but mislabelling.**

## 12. ★ The labelling rule binds in the RETURN TYPE — and one extraction fixes three things

### Where it binds

Not in a doc. Prose cannot be enforced and this label has already survived one
resolution. **It binds in the estimator's return type**, because that is the
only place a number and its basis cannot be separated.

`ClusteredMean` already carries `n` (fills) and `n_clusters` (games) — it has
the information and lacks only self-description. Three mechanical steps:

1. **`ClusteredMean` gains a `basis` of `"per-fill"`**, and a `__str__` /
   `format()` that always renders it. Printing the object then carries the
   label; extracting `.mean` to hand-format becomes a *visible* choice rather
   than the default one.
2. **A sibling `per_game_mean()` returning the same type with
   `basis="per-game"`.** Two self-describing functions instead of one function
   plus a naming convention. The ambiguity exists precisely because there is
   one function whose basis lives in prose.
3. **A guard test** in the `scripts/guard_coverage.py` pattern: flag a cent
   figure in analysis output that is not adjacent to a basis word. Crude, and
   it is the existing house mechanism for exactly this.

This is the same move as the `game_start_time` answer — remove the failure mode
structurally rather than by discipline — and here the analogy holds, unlike the
boundary/granularity case where I resisted it.

### ★ But it cannot be done without an extraction, and the measurement is stark

`core/quote/adverse_selection.py` is **663 lines**, and it is in
`DECISION_FILES`. Its contents:

    Quote                24 lines   <- DECISION (all engine.py imports)
    band constants        ~8 lines  <- DECISION
    QuoteWindow, build_windows, ClusteredMean, clustered_mean, naive_mean,
    load_quotes, Cadence, cadence, format_report (147), run, main
                        ~630 lines  <- scoring, reporting, CLI

**About 5% of the file is decision content, and 95% is scoring.** So today:

- adding a `basis` label to `ClusteredMean` **moves `decision_hash`** and
  fragments the cohort, for a purely presentational change;
- so does any report formatting tweak, or a change to `main()`;
- and `scipy` sits in the decision-path dependency closure while being used
  only at lines 320/339, inside the scoring half.

**One ~35-line extraction resolves all three.** Move the band constants and
`Quote` into a small module; point `DECISION_FILES` at it; leave the rest in
`adverse_selection.py`. Then scoring changes stop moving cohort identity,
`scipy` leaves the decision closure, and the labelling fix becomes free.

### The recursion, which should be planned rather than discovered

**The fix for cohort fragmentation is itself a decision-path change, so it
fragments the cohort once.** That is unavoidable and it is the *last* break we
should need to take for this reason. By the discipline in §5 it belongs in a
quiet window (17.0h and 11.5h gaps exist), and the deploy log should record it
with a note saying the move is intentional and non-behavioural — a hash change
whose diff provably touches no logic.

### The heartbeat recompute has the same shape, and dodges it

Adding a hash recompute to `engine.py` would also move `decision_hash` — an
observability change altering the identity of what it observes. **`core/heartbeat.py`
is NOT in `DECISION_FILES`**, and the engine already imports it
(`from core import heartbeat as hb`). Putting the recompute there gives the
per-heartbeat check without touching the decision path at all.

Accepted cost: the recompute can then be disabled without moving the hash. That
is correct — it is a monitor, not a decision, and a monitor that changed cohort
identity would be the disease again.
