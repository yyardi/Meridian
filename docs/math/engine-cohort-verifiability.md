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
