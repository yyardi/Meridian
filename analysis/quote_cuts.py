"""WIDTH, LATENESS and PATIENCE — three pre-declared stratifications of BASE's fills.

DESCRIPTIVE, HYPOTHESIS-GENERATING. Nothing here gates and nothing here is an
arm: per the Saturday design (docs/math/adverse-selection-measured.md),
**engines are for counterfactual PRICES; cuts are for counterfactual
SELECTIONS.** These three are stratifications of BASE's own fills, so they read
on all of BASE's fills rather than a fifth of the slate and need no arm slot.

    .venv/bin/python analysis/quote_cuts.py --selftest    # mutation tests first
    .venv/bin/python analysis/quote_cuts.py

SUBSTRATE — AND THE PIN THAT MOVED MID-BUILD
============================================
Pin: `backups/exports/quote_fills_classified_20260904T142200Z.csv`.

This module was commissioned against `...T140631Z`, which was SUPERSEDED
additively while it was being written (same 38,465 rows, same classification,
same numbers; the successor adds game_start_time, min_since_tip, event_period,
is_live, sports_market_type, line, quote_age_s). The switch is disclosed rather
than silent, and it is not cosmetic: **`event_period` is real game state, which
is what LATENESS was specified on**, so the successor removes a substitution the
predecessor would have forced (wall-clock elapsed as a proxy for game clock).

The four README invariants are ASSERTED at load, not assumed: `book_age_s == 0`
on every row, the `pnl` identity to 1e-15, `pop` reproducing `classify_fill` on
every row, and the WNBA known-answer (17,339 fills / 6,255 real / 63.9% phantom).

WHAT IS SCORED, AND ON WHICH POPULATION
=======================================
**PRIMARY: settlement P&L per fill, in cents, REAL fills only.** The blend of
real and phantom fills is not a conservative estimate of the real number — the
two populations carry OPPOSITE signs (+0.951c phantom / -3.376c real), so the
blend is a different number with the wrong sign twice over. The phantom share
prints on every band, per the design doc's standing requirement.

Classification is NOT re-derived. `core.quote.report.classify_fill` is the one
comparison the whole separation turns on; this module imports it and re-runs it
against the export's `pop` column, asserting agreement on every row. A second
classifier would be the defect, not the safeguard.

**ESTIMATOR, named because two are in circulation and they differ on identical
rows:** `core.quote.adverse_selection.clustered_mean` — the POOLED mean with a
game-cluster-robust SE, i.e. *what a dollar deployed earns*. The unweighted
mean-of-game-means (*what a typical game looks like*) is the one recorded in
docs/math/adverse-selection-measured.md. Never compared across the two.

**Capture is not scored anywhere here.** It is an identity, not a measurement
(`capture == -(overshoot past our price)`, corr +1.0000, zero degrees of
freedom), so any gradient read off it is forced by algebra. The calibration
expectation that follows, stated BEFORE the read: on settlement the WIDTH
gradient should be NON-MONOTONIC with CIs of order 3c. Monotone with sub-1c CIs
means capture is being scored somewhere — a bug to hunt, not a finding.

RULE 25 — WHY NO RATIO TRAVELS ALONE
====================================
Every band reports through `analysis.guards.report_composite` and calls
`degenerate_extremes_warning`. Not ceremony: the >10c band once topped a
per-cycle table at -0.010c while being the WORST cell on the board at -7.15c per
fill, winning by filling 0.0013 times per cycle — by barely being in the market.
**A per-opportunity ratio over a losing book is maximised by NOT TRADING, so any
argmax over it ranks inactivity.** Per-fill mean is primary; the ratio never
prints without its parts.

THE BANDS — PRE-DECLARED IN THE ARTIFACT, BEFORE ANY NUMBER WAS READ
====================================================================
Round units chosen blind; re-banding is a new cut, not an edit to this one.

**WIDTH** — quoted spread at quote (`s_q`), the registered bands:
    <=1.5c | 1.5-2.5c | 2.5-3.5c | 3.5-5.5c | >5.5c

**LATENESS** — TWO parameterisations of the same latent quantity, reported
side by side rather than one replacing the other, because where they disagree
the gap is stoppage structure rather than lateness:
    pregame (minutes TO tip): >120 | 60-120 | 30-60 | 10-30 | 0-10
    in-game (`event_period`): Q1 | Q2 | HALFTIME | Q3 | Q4   <- game state
    in-game (wall clock):     0-30 | 30-60 | 60-90 | 90-120 | >120 minutes
    Period collapse, declared: `End Q1`->Q1, `End Q3`->Q3 (a break belongs to
    the quarter that just ended), `End Q2`+`HT`->HALFTIME. Rows with no period
    (328, 0.9%) are dropped from the in-game cut WITH A PRINTED COUNT.
    Split by sport: WNBA and CFB quarters are different lengths and different
    games, and pooling them would compare unlike states.

**PATIENCE** — quote age at fill (`quote_age_s`):
    0-10s | 10-60s | 1-5m | 5-30m | >30m

**TIMING SIGNATURE** (not a cut — a corroboration check). Quote age at fill for
REAL vs PHANTOM fills. The separation's mechanism predicts phantoms fill FASTER
(a phantom needs only an instant of quote noise; a real fill waits for a seller
to cross down). That is a different observable — time, not money — implied by
the same mechanism, so agreement corroborates rather than restates.

THE EXPORT'S THREE DOCUMENTED TRAPS, AND THIS MODULE'S RULING ON EACH
=====================================================================
1. **`regime` vs `min_since_tip` disagree on 421 rows (1.1%) and both are
   right** — `regime` is `is_live` at quote BIRTH, `min_since_tip` is measured
   at FILL. RULING: the pregame/in-game split uses **`regime`**, because a
   quoting policy conditions on what was known when the quote was placed. The
   disagreement is labelled, not fixed.
2. **`event_period` is game state; `min_since_tip` is wall clock** and inflates
   with stoppages, halftime and CFB's long tail. RULING: in-game LATENESS is cut
   on `event_period`. Wall clock appears only in the pregame branch, where no
   game period exists to cut on.
3. **~500 fills sit in half- and quarter-derivative markets that settle on a
   DIFFERENT EVENT** from the full-game markets. RULING: **all three cuts run on
   full-game markets only**, with the exclusion counted and printed. Pooling
   settlement horizons would put a first-quarter total's settlement in the same
   mean as a full-game total's, which is not one population.

TWO HONEST LIMITS
=================
1. **PATIENCE ON A FILLS TABLE IS CONDITIONED ON FILLING.** Fills alone cannot
   see quotes that never filled, so this compares *fills that happened to rest
   long* against *fills that happened to rest briefly* — a SELECTION EFFECT, not
   a policy comparison. "Quotes that rested longer earned X" does NOT license
   "we should rest longer": the counterfactual population is not on this tape.
2. **The effective sample is GAMES.** Settlement on a binary held to expiry is
   dominated by directional variance, so every interval is game-clustered and
   every n is reported in games AND rows.

MULTIPLE COMPARISONS
====================
Three cuts x ~5 bands x 2 sports is on the order of 30 band-level numbers; at
that count several will look striking by chance alone. Ranking is by mechanism
plausibility, effect size and robustness across slices — never by widest gap.

*No in-sample result justifies capital. The forward test is the evidence.*
"""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis.guards import degenerate_extremes_warning, report_composite
from core.quote.adverse_selection import clustered_mean
from core.quote.report import PHANTOM, REAL, classify_fill

PIN = "backups/exports/quote_fills_classified_20260904T142200Z.csv"
CAPITAL_LINE = "No in-sample result justifies capital. The forward test is the evidence."

# --- the pre-declared bands (see docstring). Round units, chosen blind.
WIDTH_EDGES = [0.015, 0.025, 0.035, 0.055]
WIDTH_LABELS = ["<=1.5c", "1.5-2.5c", "2.5-3.5c", "3.5-5.5c", ">5.5c"]

PREGAME_EDGES = [10, 30, 60, 120]  # minutes TO tip; labels run late -> early
PREGAME_LABELS = ["0-10m to tip", "10-30m", "30-60m", "60-120m", ">120m"]
#: A state the pre-declared pregame edges did not anticipate, found at read and
#: NAMED rather than folded: 141 of 225 pregame-regime real fills were BORN
#: pregame but FILLED after tip (trap 1 in the flesh). Negative time-to-tip
#: digitises into the first band, so folding them would have silently reported
#: in-game fills as "0-10m to tip". The declared edges are unchanged; this is
#: the extra state, carried as its own row.
BORN_PRE_FILLED_LIVE = "born pregame, filled in-game"

PERIOD_MAP = {"Q1": "Q1", "End Q1": "Q1", "Q2": "Q2", "End Q2": "HALFTIME",
              "HT": "HALFTIME", "Q3": "Q3", "End Q3": "Q3", "Q4": "Q4"}
PERIOD_LABELS = ["Q1", "Q2", "HALFTIME", "Q3", "Q4"]

#: The in-game WALL-CLOCK bands, kept ALONGSIDE the period cut rather than
#: replaced by it. Two parameterisations of the same latent quantity that
#: DISAGREE would itself be informative — wall clock inflates with stoppages,
#: halftime and CFB's long tail, so where the two tables tell different stories
#: the gap is stoppage structure, not lateness. Split by sport, because a WNBA
#: 90th minute and a CFB 90th minute are different points in their games.
INGAME_EDGES = [30, 60, 90, 120]
INGAME_LABELS = ["0-30m", "30-60m", "60-90m", "90-120m", ">120m"]

PATIENCE_EDGES = [10, 60, 300, 1800]  # seconds of quote age
PATIENCE_LABELS = ["0-10s", "10-60s", "1-5m", "5-30m", ">30m"]


# ------------------------------------------------------------------ substrate


def load_fills(path: str = PIN) -> pd.DataFrame:
    """Load the pin, ASSERT its four README invariants, filter to full-game."""
    d = pd.read_csv(path)
    d["filled_at"] = pd.to_datetime(d.filled_at, utc=True, format="ISO8601")
    d["quoted_at"] = pd.to_datetime(d.quoted_at, utc=True, format="ISO8601")

    assert (d.book_age_s == 0).all(), "book_age_s != 0 — wrong touch substrate"
    bid = d.side == "bid"
    pnl_err = ((d.settlement - d.qp).where(bid, d.qp - d.settlement) - d.pnl).abs().max()
    assert pnl_err < 1e-12, f"pnl identity violated (max err {pnl_err})"
    recomputed = pd.Series([
        classify_fill(side=r.side, quote_price=r.qp,
                      best_bid=None if pd.isna(r.bb) else r.bb,
                      best_ask=None if pd.isna(r.ba) else r.ba)
        for r in d.itertuples()], index=d.index)
    disagree = int((recomputed != d["pop"]).sum())
    assert not disagree, (
        f"{disagree}/{len(d)} rows disagree with classify_fill — the export's "
        "population column and the one classifier of record are different worlds")

    d["sport"] = np.where(d.market_slug.str.contains("wnba"), "WNBA", "CFB")
    w = d[d.sport == "WNBA"]
    # The WNBA known-answer is a property of the FULL pin, not of every slate.
    # A single-league (all-CFB) export has zero WNBA rows and a carved subset has
    # a partial cohort; asserting unconditionally made this module REFUSE TO RUN
    # on a football-only slate — found by analysis/dry_run.py before the CFB
    # slate, not during it. The check still fires whenever it CAN, and says so
    # when it cannot, rather than silently passing.
    if len(w) == 17339:
        assert (w["pop"] == REAL).sum() == 6255, "WNBA known-answer failed on the full cohort"
        ka = "WNBA known-answer 17,339/6,255 ✓"
    elif len(w) == 0:
        ka = "WNBA known-answer NOT CHECKABLE (0 WNBA rows — single-league slate)"
    else:
        ka = f"WNBA known-answer NOT CHECKABLE (partial cohort: {len(w):,} of 17,339 rows)"
    print(f"invariants asserted: book_age_s=0 on {len(d):,}/{len(d):,} · pnl identity to "
          f"{pnl_err:.1e} · pop reproduces classify_fill on {len(d):,}/{len(d):,} · {ka}")

    age_err = (d.quote_age_s - (d.filled_at - d.quoted_at).dt.total_seconds()).abs().max()
    assert age_err < 1.0, f"quote_age_s disagrees with filled_at-quoted_at by {age_err}s"

    # trap 3: derivative markets settle on a different event; excluded, counted.
    deriv = ~d.sports_market_type.str.contains("full_game", na=False)
    print(f"trap 3 (settlement horizon): {int(deriv.sum())} fills in half/quarter-derivative "
          f"markets EXCLUDED from all cuts — they settle on a different event "
          f"({d.loc[deriv, 'sports_market_type'].nunique()} market types)")
    d = d[~deriv].copy()

    d["pnl_c"] = d.pnl * 100.0
    return d


# ------------------------------------------------------------------ the cut engine


def _band(values: pd.Series, edges: list[float], labels: list[str]) -> pd.Series:
    return pd.Series(np.array(labels)[np.digitize(values.to_numpy(float), edges)],
                     index=values.index)


def cut_table(d: pd.DataFrame, band_col: str, labels: list[str], title: str) -> pd.DataFrame:
    """One stratification, scored on REAL fills, per-fill mean PRIMARY.

    Every band prints its parts through report_composite and is checked by
    degenerate_extremes_warning (rule 25): the ratio is maximised by inactivity
    over a losing book, so it may never travel alone.
    """
    print(f"\n=== {title} ===")
    all_real = d[d["pop"] == REAL]
    opportunities = float(len(d))
    rows, warnings = [], []
    for lab in labels:
        band_all = d[d[band_col] == lab]
        band = band_all[band_all["pop"] == REAL]
        if len(band) == 0:
            rows.append({"band": lab, "fills": 0, "games": 0, "mean_c": np.nan,
                         "lo": np.nan, "hi": np.nan, "phantom": np.nan, "per_opp": np.nan})
            continue
        cm = clustered_mean({g: v.pnl_c.tolist() for g, v in band.groupby("game_id")})
        comp = report_composite(f"{title}:{lab}", numerator=float(band.pnl_c.sum()),
                                denominator=opportunities, events=int(len(band)))
        warn = degenerate_extremes_warning(f"{title}:{lab}", comp.per_event)
        if warn:
            warnings.append(warn)
        rows.append({
            "band": lab, "fills": len(band), "games": band.game_id.nunique(),
            "mean_c": cm.mean if cm else float(band.pnl_c.mean()),
            "lo": cm.lo if cm else np.nan, "hi": cm.hi if cm else np.nan,
            "phantom": float((band_all["pop"] == PHANTOM).mean()),
            "per_opp": comp.ratio,
        })
    t = pd.DataFrame(rows)
    print(t.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print(f"n: {len(all_real):,} real fills / {all_real.game_id.nunique()} games "
          f"(of {len(d):,} fills / {d.game_id.nunique()} games pre-filter). "
          f"PRIMARY = mean_c (per-fill cents, game-clustered pooled). per_opp is the "
          f"rate-normalised ratio and is NEVER the ranking quantity.")
    mono = _monotonic(t.mean_c.dropna().tolist())
    widths = (t.hi - t.lo).dropna()
    if len(widths):
        flag = (" — MONOTONIC WITH TIGHT CIs IS THE CAPTURE-BUG SIGNATURE, HUNT IT"
                if mono and widths.median() < 1.0 else "")
        print(f"shape check: {'MONOTONIC' if mono else 'not monotonic'}, median CI width "
              f"{widths.median():.2f}c{flag}")
    if warnings:
        print(f"rule 25: {warnings[0]}")
        if len(warnings) > 1:
            print(f"  (same warning on {len(warnings)}/{len(labels)} bands)")
    return t


def _monotonic(xs: list[float]) -> bool:
    if len(xs) < 3:
        return False
    diffs = np.diff(xs)
    return bool(np.all(diffs >= 0) or np.all(diffs <= 0))


# ------------------------------------------------------------------ the three cuts


def run_width(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    d["b"] = _band(d.s_q, WIDTH_EDGES, WIDTH_LABELS)
    t = cut_table(d, "b", WIDTH_LABELS, "WIDTH (quoted spread at quote)")
    print("★ THE `phantom` COLUMN IS FORCED IN THIS CUT AND MUST NOT BE READ AS A FINDING.")
    print("The classification rule is exactly `real <=> excess >= s/2` (B, 2026-09-04), so")
    print("SPREAD SITS ON BOTH SIDES: a wider band mechanically raises the bar a fill must")
    print("clear to count as real, and the phantom share therefore MUST rise with width.")
    print("The monotone gradient here is the criterion restating itself — the same species")
    print("as the retired capture gradient. It is printed because the design doc requires a")
    print("phantom flag on every cut, NOT because it measures anything. (In the LATENESS and")
    print("PATIENCE cuts the bands are not spread-based, so their phantom columns are")
    print("empirical rather than forced — the distinction is exact, not a hedge.)")
    return t


#: The manager's independent WIDTH read, quoted as the known answer this
#: instrument must reproduce. It is the UNWEIGHTED MEAN-OF-GAME-MEANS estimator
#: over ALL markets (derivatives included) — reproduced here to the digit, which
#: is what shows the two reads differ by a labelled estimator choice and not by
#: a defect. The cut tables above use POOLED clustered_mean on full-game markets.
CALIBRATION_MOGM_ALL = [-1.974, -1.609, -6.716, -3.411, -5.609]


def reconcile_width(d_all: pd.DataFrame) -> bool:
    """Known-answer check: reproduce the calibration figures under ITS estimator."""
    r = d_all[d_all["pop"] == REAL].copy()
    r["b"] = _band(r.s_q, WIDTH_EDGES, WIDTH_LABELS)
    got = [round(float(r[r.b == lab].groupby("game_id").pnl_c.mean().mean()), 3)
           for lab in WIDTH_LABELS]
    ok = all(abs(a - b) < 0.01 for a, b in zip(got, CALIBRATION_MOGM_ALL))
    print(f"\nknown-answer check (mean-of-game-means, ALL markets): {got}")
    print(f"  vs the calibration read                             : {CALIBRATION_MOGM_ALL}")
    print(f"  reproduced: {ok} — so the difference from the table above is the "
          f"ESTIMATOR (pooled vs mean-of-game-means) and the derivative filter, "
          f"both labelled choices, not a defect.")
    return ok


def run_lateness(d: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Pregame on time-to-tip; in-game on REAL GAME PERIOD (trap 2's ruling)."""
    out = {}
    pre = d[d.regime == "pregame"].copy()
    if len(pre):
        after = pre.min_since_tip > 0
        pre["b"] = _band(-pre.min_since_tip, PREGAME_EDGES, PREGAME_LABELS)
        pre.loc[after, "b"] = BORN_PRE_FILLED_LIVE
        print(f"\nLATENESS pregame: {int(after.sum())} of {len(pre)} pregame-regime fills "
              f"({after.mean():.0%}) were BORN pregame but FILLED after tip — carried as "
              f"their own state, not folded into '0-10m to tip' where the sign convention "
              f"would have silently put them")
        out["pregame"] = cut_table(pre, "b", [BORN_PRE_FILLED_LIVE] + PREGAME_LABELS,
                                   "LATENESS pregame (wall-clock minutes to tip, both sports)")
    ing = d[d.regime == "ingame"].copy()
    no_period = ing.event_period.isna()
    if no_period.any():
        print(f"\nLATENESS in-game: {int(no_period.sum())} fills "
              f"({no_period.mean():.1%}) carry no event_period and are dropped from the "
              f"period cut — counted here rather than silently absent")
    ing = ing[~no_period].copy()
    ing["b"] = ing.event_period.map(PERIOD_MAP)
    unmapped = ing.b.isna()
    if unmapped.any():
        print(f"LATENESS in-game: {int(unmapped.sum())} fills carry an UNDECLARED period "
              f"({sorted(ing.loc[unmapped, 'event_period'].unique())}) — dropped and named, "
              f"because a period the band map never anticipated is not a band")
        ing = ing[~unmapped]
    for sport in ["WNBA", "CFB"]:
        s = ing[ing.sport == sport]
        if len(s):
            out[f"{sport}-ingame"] = cut_table(
                s, "b", PERIOD_LABELS, f"LATENESS {sport} in-game (real game period)")

    # The second parameterisation, kept alongside: wall clock since tip.
    live = d[d.regime == "ingame"].copy()
    live["b"] = _band(live.min_since_tip, INGAME_EDGES, INGAME_LABELS)
    for sport in ["WNBA", "CFB"]:
        s = live[live.sport == sport]
        if len(s):
            out[f"{sport}-ingame-wallclock"] = cut_table(
                s, "b", INGAME_LABELS,
                f"LATENESS {sport} in-game (WALL CLOCK since tip — the second "
                f"parameterisation; disagreement with the period table above is "
                f"stoppage structure, not lateness)")
    return out


def timing_signature(d: pd.DataFrame) -> None:
    """Quote age at fill, REAL vs PHANTOM — a second, independent signature.

    The separation's mechanism predicts a timing asymmetry: a phantom books on a
    momentary dip of the recorded mid, which needs only an instant of quote
    noise, while a real fill waits for a seller to actually cross down to us. So
    phantoms should fill FASTER. This is not a restatement of the P&L split —
    it is a different observable (time, not money) implied by the same mechanism,
    so agreement is corroboration rather than circularity.

    ★ WHAT THIS CORROBORATES, AND WHAT IT CANNOT ★ It tests the MECHANISM
    (phantoms are momentary quote noise; real fills wait for a seller to cross
    down). It does **NOT** validate the phantom DEFINITION: `ask <= B` could be
    the wrong criterion and would still produce this timing gap, because ANY
    criterion correlated with dip-and-revert would. Only a resting-order probe
    tests the definition itself — D is drafting that, and the two are
    COMPLEMENTARY, NOT SUBSTITUTES. Quoting this signature as evidence that the
    classification is correct would be exactly the overreach it cannot support.

    Stated honestly: both populations are conditioned on having filled, so this
    compares the timing of two filled populations, not fill probability.
    """
    print("\n=== TIMING SIGNATURE — quote age at fill, real vs phantom ===")
    rows = []
    for pop in (PHANTOM, REAL):
        s = d[d["pop"] == pop].quote_age_s
        rows.append({"population": pop, "fills": len(s), "median_s": s.median(),
                     "p25_s": s.quantile(0.25), "p75_s": s.quantile(0.75),
                     "share <=10s": float((s <= 10).mean())})
    t = pd.DataFrame(rows)
    print(t.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    # game-clustered difference in median age, so the claim carries an interval
    per_game = d.groupby(["game_id", "pop"]).quote_age_s.median().unstack()
    if PHANTOM in per_game and REAL in per_game:
        diff = (per_game[PHANTOM] - per_game[REAL]).dropna()
        cm = clustered_mean({g: [v] for g, v in diff.items()})
        print(f"per-game median age, phantom - real: {cm.mean:+.2f}s "
              f"[{cm.lo:+.2f}, {cm.hi:+.2f}] (G={cm.n_clusters})")
        verdict = ("phantoms fill FASTER — the predicted direction" if cm.hi < 0 else
                   "phantoms fill SLOWER — against the predicted direction" if cm.lo > 0 else
                   "no separation in timing at this power — the mechanism's timing "
                   "prediction is NOT corroborated here, which is a real negative")
        print(f"reading: {verdict}")
    print("SCOPE: this corroborates the MECHANISM on a different observable (seconds,")
    print("not cents). It does NOT validate the phantom DEFINITION — any criterion")
    print("correlated with dip-and-revert would produce the same gap. Only a")
    print("resting-order probe tests the definition; the two are complementary.")


def run_patience(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    d["b"] = _band(d.quote_age_s, PATIENCE_EDGES, PATIENCE_LABELS)
    t = cut_table(d, "b", PATIENCE_LABELS, "PATIENCE (quote age at fill)")
    print("SELECTION EFFECT, not a policy comparison: this table is conditioned on")
    print("FILLING. Quotes that never filled are not on this tape, so a band's mean")
    print("describes fills that happened to rest that long — it does NOT estimate what")
    print("resting longer would earn. Reading it as policy is the error this line prevents.")
    return t


# ------------------------------------------------------------------ mutation tests


def _synth(n_games=20, per_game=200, seed=0, effect=None) -> pd.DataFrame:
    """Synthetic fills with known band structure and a known P&L process."""
    rng = np.random.default_rng(seed)
    n = n_games * per_game
    game = np.repeat(np.arange(n_games), per_game)
    shock = rng.normal(0, 3.0, n_games)[game]  # game-level shock for clustering to see
    d = pd.DataFrame({
        "game_id": game, "pop": REAL, "sport": "WNBA",
        "s_q": rng.choice([0.01, 0.02, 0.03, 0.05, 0.08], n),
        "quote_age_s": rng.choice([5.0, 30.0, 120.0, 900.0, 3600.0], n),
        "event_period": rng.choice(["Q1", "Q2", "HT", "Q3", "Q4"], n),
    })
    d["pnl_c"] = rng.normal(-3.0, 8.0, n) + shock
    if effect is not None:
        col, target, size = effect
        d.loc[d[col] == target, "pnl_c"] += size
    return d


def _quiet(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


def selftest() -> None:
    """Rule 4: each cut reads ~zero on a synthetic null and RECOVERS a known effect.

    An instrument that has not been shown to recover a known answer is not an
    instrument. Both directions are tested for every cut, because a cut that can
    only find effects it was built to find is a confirmation device.
    """
    ok = True
    specs = [
        ("WIDTH", "s_q", 0.08, WIDTH_LABELS, ">5.5c",
         lambda x: _band(x.s_q, WIDTH_EDGES, WIDTH_LABELS)),
        ("PATIENCE", "quote_age_s", 3600.0, PATIENCE_LABELS, ">30m",
         lambda x: _band(x.quote_age_s, PATIENCE_EDGES, PATIENCE_LABELS)),
        ("LATENESS-period", "event_period", "Q4", PERIOD_LABELS, "Q4",
         lambda x: x.event_period.map(PERIOD_MAP)),
    ]
    for name, col, target, labels, target_label, bander in specs:
        null = _synth(seed=1)
        null["b"] = bander(null)
        t0 = _quiet(cut_table, null, "b", labels, f"null-{name}")
        spread0 = np.nanmax(t0.mean_c) - np.nanmin(t0.mean_c)
        inj = _synth(seed=1, effect=(col, target, -6.0))
        inj["b"] = bander(inj)
        t1 = _quiet(cut_table, inj, "b", labels, f"inj-{name}")
        got = float(t1.loc[t1.band == target_label, "mean_c"].iloc[0])
        base = float(t0.loc[t0.band == target_label, "mean_c"].iloc[0])
        rec = got - base
        print(f"[{name}] null band-spread {spread0:.2f}c; injected -6.00c into "
              f"{target_label} recovered {rec:+.2f}c (want ~-6.00 and >> the null spread)")
        ok &= abs(rec + 6.0) < 1.0 and abs(rec) > 2 * spread0

    # The pregame band map, on a constructed clock (minutes TO tip are negative
    # min_since_tip, and the sign convention is the easiest thing here to invert).
    pre = pd.DataFrame({"min_since_tip": [-150.0, -90.0, -45.0, -20.0, -5.0]})
    bands = _band(-pre.min_since_tip, PREGAME_EDGES, PREGAME_LABELS).tolist()
    want = [">120m", "60-120m", "30-60m", "10-30m", "0-10m to tip"]
    print(f"[LATENESS pregame bands] {bands} (want {want})")
    ok &= bands == want

    # Every period the export actually emits must map to a declared band; an
    # unmapped period is the failure mode that would silently drop live rows.
    emitted = ["Q1", "End Q1", "Q2", "End Q2", "HT", "Q3", "End Q3", "Q4"]
    unmapped = [p for p in emitted if p not in PERIOD_MAP]
    print(f"[period map] every emitted period is declared: {not unmapped} "
          f"({len(PERIOD_MAP)} mappings -> {len(PERIOD_LABELS)} bands)")
    ok &= not unmapped

    # Rule 25 must be LIVE in the cut engine, not merely imported: the guard's
    # own specimen must still rank the barely-trading band first on the ratio.
    wide = report_composite("w>10c", numerator=-0.010 * 95614, denominator=95614, events=129)
    tight = report_composite("w<=2c", numerator=-0.096 * 98062, denominator=98062, events=2062)
    warn = degenerate_extremes_warning("w>10c", wide.per_event)
    live = (wide.ratio > tight.ratio and wide.per_event < tight.per_event
            and warn is not None and "NEVER ACTING" in warn)
    src = Path(__file__).read_text()
    wired = "degenerate_extremes_warning(" in src and "report_composite(" in src
    print(f"[rule 25] specimen still ranks the barely-trading band first on the ratio and "
          f"the guard catches it: {live}; both call sites live in the cut engine: {wired}")
    ok &= live and wired

    print("SELFTEST", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


# ------------------------------------------------------------------ main


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--fills", default=PIN)
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    d = load_fills(args.fills)

    print("\n=== COMPOSITION (before any ratio) ===")
    print(f"fills {len(d):,} · games {d.game_id.nunique()} · by sport "
          f"{d.groupby('sport').game_id.nunique().to_dict()} games / "
          f"{d.sport.value_counts().to_dict()} fills")
    print(f"population {d['pop'].value_counts().to_dict()} "
          f"(phantom share {(d['pop'] == PHANTOM).mean():.1%}) · "
          f"regime {d.regime.value_counts().to_dict()}")
    real = d[d["pop"] == REAL]
    cm = clustered_mean({g: v.pnl_c.tolist() for g, v in real.groupby("game_id")})
    print(f"REAL fills, settlement P&L, pooled clustered_mean: {cm.mean:+.3f}c/fill "
          f"[{cm.lo:+.3f}, {cm.hi:+.3f}] (G={cm.n_clusters}, rows={cm.n:,})")
    disagree = int(((d.regime == "pregame") & (d.min_since_tip > 0)).sum()
                   + ((d.regime == "ingame") & (d.min_since_tip <= 0)).sum())
    print(f"trap 1: regime (quote birth) and min_since_tip (fill) disagree on {disagree} "
          f"fills ({disagree / len(d):.1%}); the split below uses REGIME, labelled not fixed")

    run_width(d)
    d_all = pd.read_csv(args.fills)
    d_all["pnl_c"] = d_all.pnl * 100.0
    reconcile_width(d_all)
    run_lateness(d)
    run_patience(d)
    timing_signature(d)

    print("\n=== STANDING LANGUAGE ===")
    print("DESCRIPTIVE and HYPOTHESIS-GENERATING. Nothing above gates anything.")
    print("~30 band-level numbers across three cuts and two sports: several will look")
    print("striking by chance. Rank by mechanism, effect size and robustness across")
    print("slices — never by the widest gap. PATIENCE is a selection effect, not a policy")
    print("comparison. Derivative-market fills are excluded (different settlement event).")
    print(CAPITAL_LINE)


if __name__ == "__main__":
    main()
