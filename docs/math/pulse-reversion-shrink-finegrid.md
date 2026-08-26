# Reversion shrink — fine-grid arm ("#89-fg")

Registration. **Written before anything was computed for this arm.**
Authored by the research agent 2026-08-26; landed unmodified.

This arm exists alongside [pulse-reversion-shrink.md](pulse-reversion-shrink.md).
It does not replace it, amend it, or correct it. **#89 runs and reports as
registered, untouched.**

## Definition

Identical to #89 in every respect **except the shrink table**.

`s(elapsed)` is piecewise-linear through the nine play-resolution gridpoints:

| elapsed | 4′ | 8′ | 12′ | 16′ | 20′ | 24′ | 28′ | 32′ | 36′ |
|---|---|---|---|---|---|---|---|---|---|
| β | 0.355 | 0.311 | 0.243 | 0.191 | 0.158 | 0.159 | 0.151 | 0.107 | 0.063 |

held flat at 0.355 before 4′, linear to 0 at 40′ — matching #89's endpoint
convention, because banked points cannot revert.

Adopted **verbatim** from the 2026-08-26 fit: 797 games, closing-spread anchor,
play-level margins, standard errors clustered by game, every gridpoint's 95% CI
excluding zero. **Nothing further is fit here.** Totals are untouched.

## Relation to the incumbent — stated for the reader

**#89 is a LOW-RESOLUTION INSTANCE OF THE SAME CURVE, not a rejected
alternative.** F1's three boundary betas — (10′, 0.28), (20′, 0.157),
(30′, 0.137) — interpolate cleanly on this fine grid.

The two arms differ in **exactly one respect: grid resolution.** The paired
comparison between them measures what resolution is worth, which is the reason
to run both rather than to replace one with the other. The visible difference is
early: #89 holds 0.28 below 10′ where this arm reads 0.355 at 4′.

## Source boundary — travels with the constants

The constants come from the **physics-only backfill**: fine for a fitted
constant table, **NEVER for point-in-time claims.** This constraint is part of
the registration, not a footnote to it, because the next person to reach for
these numbers will look here first.

## Gate

Mirrors #89's registered gate in form — same metrics, same floors, same
machinery: paired Brier (incumbent − shrunk) clustered by game, 95% CI excluding
zero in the shrunk arm's favour at floor, AND paired money-at-price not
measurably worse. **Floors: ≥ 10 signal-covered games first recorded after this
registration AND ≥ 3,000 paired points.** Adopted into live estimates only on
PASS, as its own dated regime change.

## The cutoff instant

The gate counts games first recorded after **this document's first commit**.

That instant is established by

    TZ=UTC git log --format=%cI --follow -- docs/math/pulse-reversion-shrink-finegrid.md | tail -1

and **never from prose in this file.** #89's registration was stamped from its
author's sense of the day and drifted a day in the permissive direction; the
correction is recorded at the end of that document. Naming the command instead
of the timestamp removes the failure mode rather than repeating the fix.

---

*Results append below this line, never above it.*
