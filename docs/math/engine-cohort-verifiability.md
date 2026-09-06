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
