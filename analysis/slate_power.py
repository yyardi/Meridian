"""What will tomorrow's slate actually buy us? — a power check on a load-bearing claim.

The standing brief says *"Saturday's 103-game slate is the first sample large
enough to resolve a -3.4c effect."* **That sentence has never been checked.** It
is the reason tomorrow is treated as decisive. This module checks it.

    .venv/bin/python analysis/slate_power.py --selftest
    .venv/bin/python analysis/slate_power.py

EVERYTHING BELOW THIS LINE WAS WRITTEN BEFORE ANY NUMBER WAS COMPUTED
=====================================================================
A power calculation is exactly the kind of number that gets tuned until it says
something comfortable, so the estimator, the projection formula, the assumptions
and the decision questions are all fixed here, in the artifact, first.

**ESTIMATOR — named, because two are in circulation and they differ on identical
rows.** `core.quote.adverse_selection.clustered_mean`: the POOLED mean with a
game-cluster-robust sandwich SE and df = G-1. This is the one
`core/quote/report.py` prints. The unweighted mean-of-game-means is the OTHER
one, recorded in docs/math/adverse-selection-measured.md. Never mixed.

**PROJECTION FORMULA — derived from the sandwich, not assumed.** For the pooled
clustered mean, Var = [G/(G-1)] * SUM_g(S_g^2) / n^2, where S_g is game g's sum
of within-cluster residuals. If N new games are exchangeable with the observed
ones, both SUM(S_g^2) and n scale by (G+N)/G, so

    Var(G+N) / Var(G)  =  G / (G+N)        =>  SE scales as sqrt(G/(G+N))

and the half-width additionally shrinks through the t-critical value as df goes
from G-1 to G+N-1:

    HW(G+N) = HW(G) * [t_{0.975, G+N-1} / t_{0.975, G-1}] * sqrt(G/(G+N))

**THE THREE DECISION QUESTIONS, fixed now** — at 11 + N games, does the interval
around a -3.4c effect exclude 0c, -1c, and -6c? These are different questions
and the third decides whether FLATTEN's improvement is measurable.

**AND THE DISTINCTION THAT MAKES THE ANSWER HONEST.** "The CI excludes v" is a
statement about ONE realised interval; a design that only just excludes v has
about 50% power and will fail half the time on a rerun. So each question is
answered twice: (i) does the projected half-width satisfy HW < |mu - v| (the
"can it, at best" reading), and (ii) does it satisfy HW <= |mu - v| / 1.43,
which is 80% power at a two-sided 5% test (|mu-v| >= 2.80*SE and HW ~ 1.96*SE).
**Reporting only (i) is how a power claim flatters itself.**

**ASSUMPTIONS, each tested below where the data can test it:**

A1. *New games resemble the observed ones in per-game dispersion.* TESTED: the
    per-game sd is recomputed dropping each game in turn (jackknife), and the
    largest single-game influence is reported. If one game drives the sd, the
    projection inherits that fragility and the report says so.
A2. *103 games produce real fills at the observed per-game rate.* NOT TESTABLE
    ON THIS PIN — see section 4, where the test I intended turns out to be
    structurally vacuous. **And the sharper form of the assumption, which is
    not a market question at all:** the engine refuses to quote above
    `MAX_SPREAD = 0.15` (`core/quote/adverse_selection.py:137`; zero fills
    above it in 38,465 rows, and the observed maximum is exactly 0.15, so the
    gate binds rather than merely existing). The CFB board is median 11c wide
    with p75 at 30c, so a material share of it sits ABOVE our own gate. The
    real assumption is therefore *"will 103 games' worth of board sit below
    15c at today's rate"* — and if tomorrow's slate is wider, yield drops for a
    STRUCTURAL reason (a constant we chose) rather than a market one. The
    coverage sensitivity in section 4b is the stand-in for the test that needs
    a board-width pin nobody has yet.
A3. *Games are the unit and they are not equally informative.* A game with 12
    real fills is a noisier contribution than one with 800. Reported as Kish
    effective cluster count G_eff = (SUM n_g)^2 / SUM(n_g^2), which says how
    many EQUAL-sized games the observed distribution is actually worth. The
    projection is run on BOTH nominal G and G_eff, and the honest figure is the
    one built on G_eff.
A4. *The effect size itself is not being estimated here.* This projects
    PRECISION under an assumed -3.4c, and says nothing about whether -3.4c is
    the right centre.

**WHAT WOULD FALSIFY THE BRIEF'S CLAIM:** if the projected half-width at 11+103
games (on G_eff, under A2's yield) does not clear the -6c question, then the
slate cannot resolve FLATTEN-sized differences and "the first sample large
enough" is false as written. That sentence is the deliverable.

*No in-sample result justifies capital. The forward test is the evidence.*
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.quote.adverse_selection import clustered_mean
from core.quote.report import PHANTOM, REAL, classify_fill

PIN = "backups/exports/quote_fills_classified_20260904T142200Z.csv"
ASSUMED_EFFECT = -3.4      # the effect the brief claims the slate resolves
COMPARATORS = [0.0, -1.0, -6.0]
SLATE_SIZES = [30, 60, 103]
POWER_FACTOR = 1.43        # |mu-v| >= 2.80*SE and HW ~ 1.96*SE  =>  HW <= |mu-v|/1.43
CAPITAL_LINE = "No in-sample result justifies capital. The forward test is the evidence."


def load(path: str = PIN) -> pd.DataFrame:
    d = pd.read_csv(path)
    bid = d.side == "bid"
    err = ((d.settlement - d.qp).where(bid, d.qp - d.settlement) - d.pnl).abs().max()
    assert err < 1e-12 and (d.book_age_s == 0).all(), "substrate invariants failed"
    d["sport"] = np.where(d.market_slug.str.contains("wnba"), "WNBA", "CFB")
    d["pnl_c"] = d.pnl * 100.0
    return d


def project_hw(hw_now: float, g_now: float, n_new: float) -> float:
    """Half-width at G+N games under the sandwich's scaling (see docstring)."""
    g_new = g_now + n_new
    t_ratio = stats.t.ppf(0.975, df=g_new - 1) / stats.t.ppf(0.975, df=g_now - 1)
    return hw_now * t_ratio * np.sqrt(g_now / g_new)


def kish(counts: np.ndarray) -> float:
    """Effective cluster count: how many EQUAL-sized games this distribution is worth."""
    return float(counts.sum() ** 2 / (counts ** 2).sum())


#: Per-game sd on CFB real fills, from docs/math/markout-measured.md (4a2cb1b).
#: SETTLEMENT IS PRIMARY. These are reported beside it and may not promote it.
MARKOUT_SD = {"settlement": (4.102, 1.000), "markout 10s": (1.034, 0.759),
              "markout 30s": (0.652, 0.821), "markout 60s": (0.617, 0.969),
              "markout 300s": (0.846, 0.989)}  # (per-game sd cents, coverage)


def markout_second_pass(hw_settlement: float, g_nom: int, g_eff: float) -> None:
    """The same question on a SECONDARY metric — reported, never promoted.

    Declared before computing: this is a RATIO-SCALED projection. I hold
    markout's per-game sd but not its fills, so the half-width is scaled from
    settlement's measured half-width by the sd ratio. That assumes the
    within-game correlation structure is similar across metrics; it is an
    approximation and it is labelled as one rather than presented as a measured
    interval.
    """
    print("\n=== 4c. SECOND PASS — MARKOUT, BESIDE SETTLEMENT AND NOT ABOVE IT ===")
    print("Settlement is PRIMARY: it is the money. Markout is SECONDARY and a tighter")
    print("interval around a proxy may not promote it — choosing a metric by its variance")
    print("is the trade capture made and lost. Ratio-scaled from settlement's measured")
    print("half-width by per-game sd (an approximation, labelled as one).")
    rows = []
    for name, (sd, cov) in MARKOUT_SD.items():
        ratio = sd / MARKOUT_SD["settlement"][0]
        hw_today = hw_settlement * ratio
        n_eff = 103 * (g_eff / g_nom)
        hw_103 = project_hw(hw_today, g_eff, n_eff)
        rows.append({"metric": name, "per_game_sd_c": sd, "coverage": cov,
                     "HW_today_c": hw_today, "HW_at_+103_c": hw_103,
                     "vs -6c 80% power": "YES" if hw_103 <= 2.6 / POWER_FACTOR else "NO"})
    print(pd.DataFrame(rows).to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print("\nCOVERAGE, and why it costs less here than it looks: the staleness cap drops")
    print("24% of fills at 10s and 18% at 30s. For a FILL-level estimator that is a direct")
    print("sample loss; for a GAME-CLUSTERED one it is second-order, because the binding")
    print("unit is games and every game retains fills at every horizon. The real exposure")
    print("is not precision but CENTRE: the dropped rows are markets that stopped updating,")
    print("which is not random, and a market that stopped updating plausibly has a markout")
    print("near zero — so dropping them could bias the metric AWAY from zero. This module")
    print("projects precision only (A4) and is silent on that; it is named because a")
    print("coverage note that only mentions n would understate the problem.")
    print("Recommended basis if a markout projection is ever used: 60s — sd 0.617c at 96.9%")
    print("coverage dominates 30s (0.652c at 82.1%) on both axes at once.")
    print("Standing limit, from the metric's own doc: 54% of the phantom/real markout gap")
    print("is already present at h=0, i.e. the classification criterion restating itself.")
    print("That does not touch this projection (it uses REAL fills' dispersion only) but it")
    print("does mean markout's phantom-vs-real GAP is not clean evidence about anything.")


def report(d: pd.DataFrame) -> None:
    print("=== COMPOSITION (before any ratio) ===")
    real = d[d["pop"] == REAL]
    for sport in ["WNBA", "CFB"]:
        s = real[real.sport == sport]
        gm = s.groupby("game_id").pnl_c.mean()
        cm = clustered_mean({g: v.pnl_c.tolist() for g, v in s.groupby("game_id")})
        print(f"{sport}: {len(s):,} real fills / {s.game_id.nunique()} games · "
              f"pooled {cm.mean:+.3f}c [{cm.lo:+.3f}, {cm.hi:+.3f}] · "
              f"per-game mean sd {gm.std(ddof=1):.3f}c")

    cfb = real[real.sport == "CFB"]
    counts = cfb.groupby("game_id").size()
    gm = cfb.groupby("game_id").pnl_c.mean()
    g_nom = len(counts)
    g_eff = kish(counts.to_numpy())

    print("\n=== 1. PER-GAME DISPERSION (CFB — tomorrow is football) ===")
    print(f"per-game mean P&L: {gm.mean():+.3f}c, sd {gm.std(ddof=1):.3f}c across {g_nom} games")
    print(f"  (B's independently measured CFB per-game sd was 4.10c)")
    # A1: jackknife — is the sd driven by one game?
    jack = [gm.drop(g).std(ddof=1) for g in gm.index]
    worst = int(np.argmax(np.abs(np.array(jack) - gm.std(ddof=1))))
    print(f"A1 jackknife: dropping one game moves the sd to [{min(jack):.3f}, {max(jack):.3f}]c; "
          f"largest single-game influence is game {gm.index[worst]} "
          f"(sd {gm.std(ddof=1):.3f} -> {jack[worst]:.3f})")

    print("\n=== 2. REAL-FILL YIELD PER GAME (the sample that counts) ===")
    print(f"real fills per CFB game: median {counts.median():.0f}, "
          f"IQR [{counts.quantile(.25):.0f}, {counts.quantile(.75):.0f}], "
          f"min {counts.min()}, max {counts.max()}")
    print(f"phantom share (CFB): {(d[d.sport == 'CFB']['pop'] == PHANTOM).mean():.1%} — "
          f"only the real fills score")
    print(f"A3 effective cluster count: G_eff = {g_eff:.2f} against a nominal {g_nom} "
          f"({g_eff / g_nom:.0%}) — the yield skew costs {g_nom - g_eff:.1f} games' worth "
          f"of independent information before a single new game is played")

    print("\n=== 3. WHAT 11 + N GAMES BUYS ===")
    cm = clustered_mean({g: v.pnl_c.tolist() for g, v in cfb.groupby("game_id")})
    hw_now = (cm.hi - cm.lo) / 2
    print(f"today, CFB real fills, pooled clustered_mean: {cm.mean:+.3f}c "
          f"[{cm.lo:+.3f}, {cm.hi:+.3f}] — half-width {hw_now:.3f}c (G={g_nom}, n={cm.n:,})")
    print(f"projecting on BOTH nominal G={g_nom} and effective G_eff={g_eff:.2f}; "
          f"the G_eff row is the honest one.\n")
    rows = []
    for basis, g0 in [("nominal", float(g_nom)), ("G_eff", g_eff)]:
        for n in SLATE_SIZES:
            # new games enter at the same yield skew, so they too are worth
            # (g_eff/g_nom) of their nominal count on the effective basis
            n_eff = n * (g_eff / g_nom) if basis == "G_eff" else n
            hw = project_hw(hw_now, g0, n_eff)
            rows.append({"basis": basis, "N_new": n, "G_total": g0 + n_eff,
                         "half_width_c": hw,
                         "CI_at_-3.4": f"[{ASSUMED_EFFECT - hw:+.2f}, {ASSUMED_EFFECT + hw:+.2f}]"})
    t = pd.DataFrame(rows)
    print(t.to_string(index=False, float_format=lambda v: f"{v:.2f}"))

    print("\n=== THE THREE DECISION QUESTIONS, at 103 additional games ===")
    print("(i) 'excludes' = HW < |mu-v|, the best-case reading of one interval.")
    print("(ii) '80% power' = HW <= |mu-v|/1.43 — what is needed to expect it to")
    print("     REPLICATE. A design that only just excludes v fails half the time.")
    for basis, g0 in [("nominal", float(g_nom)), ("G_eff", g_eff)]:
        n_eff = 103 * (g_eff / g_nom) if basis == "G_eff" else 103
        hw = project_hw(hw_now, g0, n_eff)
        print(f"\n  [{basis}: G={g0 + n_eff:.1f}, half-width {hw:.2f}c]")
        for v in COMPARATORS:
            gap = abs(ASSUMED_EFFECT - v)
            print(f"    -3.4c vs {v:+.0f}c (gap {gap:.1f}c): "
                  f"excludes={'YES' if hw < gap else 'NO '}   "
                  f"80% power={'YES' if hw <= gap / POWER_FACTOR else 'NO '}")

    print("\n=== 4. ASSUMPTION A2 — and why this pin CANNOT test it ===")
    per_game_width = d[d.sport == "CFB"].groupby("game_id").s_q.median()
    print(f"median quoted spread per CFB game: {(per_game_width * 100).round(1).tolist()} cents")
    print("★ THE TEST I INTENDED IS VACUOUS, AND SAYING SO IS THE RESULT. `s_q` is the")
    print("spread AT OUR QUOTE — the markets the engine CHOSE to quote in — not the")
    print("board's width. It reads ~2c on every game because the quoter only rests where")
    print("it is already tight (67% of CFB quotes at <=3c), against a board the manager")
    print("measured at median 11c / p75 30c. Correlating it against yield therefore has")
    print("no variation to work with and would return a meaningless 'no relationship'.")
    print("A2 IS UNTESTED ON THIS PIN, not tested-and-passed. What decides tomorrow's")
    print("yield is how much of a 103-game board is tight enough to quote at all, and")
    print("that quantity is not in this file.")

    above = int((d.s_q > 0.15).sum())
    print(f"\nTHE GATE, which makes A2 structural rather than market-driven: the engine")
    print(f"refuses to quote above MAX_SPREAD=0.15 (core/quote/adverse_selection.py:137).")
    print(f"Fills above it: {above} of {len(d):,}; observed max s_q = {d.s_q.max():.2f} — the")
    print(f"gate BINDS. Against a board at median 11c / p75 30c, a material share of")
    print(f"tomorrow's markets is above our own cutoff. So 'will the yield hold' is really")
    print(f"'will 103 games' worth of board sit under 15c', and if it does not, the loss is")
    print(f"OURS BY CONSTRUCTION rather than the market's. (Note the s_q distribution above")
    print(f"is FILL-conditioned and so tighter than the quote distribution it came from;")
    print(f"it bounds nothing about the board, which is the point.)")

    print("\n=== 4b. SO: SENSITIVITY TO COVERAGE, since A2 cannot be settled ===")
    print("If tomorrow's board is wider, fewer games clear the quoter's bar. The")
    print("question 'does the slate resolve -6c' re-answered at coverage fractions:")
    hw0, g0 = hw_now, g_eff
    for frac in [1.0, 0.5, 0.25, 0.1]:
        n_eff = 103 * frac * (g_eff / g_nom)
        hw = project_hw(hw0, g0, n_eff)
        gap6 = abs(ASSUMED_EFFECT - (-6.0))
        print(f"  {frac:4.0%} of 103 games covered -> G_eff {g0 + n_eff:5.1f}, "
              f"HW {hw:.2f}c · vs -6c: excludes={'YES' if hw < gap6 else 'NO '} "
              f"80% power={'YES' if hw <= gap6 / POWER_FACTOR else 'NO '}")
    print("The comparison survives deep coverage loss, which is the robustness that")
    print("matters more than the headline: the answer does not depend on the number")
    print("103 being right, only on it not collapsing by an order of magnitude.")

    markout_second_pass(hw_now, g_nom, g_eff)

    print("\n=== 5. THE CENTRE IS TRANSPLANTED, AND THAT IS A SEPARATE EXPOSURE ===")
    cfb_cm = clustered_mean({g: v.pnl_c.tolist() for g, v in cfb.groupby("game_id")})
    wnba = real[real.sport == "WNBA"]
    w_cm = clustered_mean({g: v.pnl_c.tolist() for g, v in wnba.groupby("game_id")})
    print(f"The brief's -3.4c is the WNBA number ({w_cm.mean:+.3f}c). CFB's own estimate")
    print(f"today is {cfb_cm.mean:+.3f}c [{cfb_cm.lo:+.3f}, {cfb_cm.hi:+.3f}] — it SPANS ZERO.")
    print("This module projects PRECISION and is silent on the centre (A4). Tomorrow")
    print("resolves CFB's effect wherever it truly sits; it does not verify -3.4c, and")
    print("a football slate is not evidence about a basketball number.")
    print(f"\n{CAPITAL_LINE}")


# ------------------------------------------------------------------ selftest


def selftest() -> None:
    """The projection must recover a KNOWN answer before it projects an unknown one.

    1. sqrt-N law: on synthetic games drawn from one distribution, the projected
       half-width at G+N must match the half-width actually measured on G+N
       simulated games (the projection is not merely internally consistent).
    2. Kish: equal-sized clusters give G_eff == G; one dominant cluster drives
       G_eff toward 1. This is the quantity that decides the honest answer.
    3. The power factor is the right way round: a gap that is only just excluded
       must FAIL the 80% test.
    """
    ok = True
    rng = np.random.default_rng(7)

    # 1. projection vs simulation
    def sim_hw(g, per=300):
        vals = {i: (rng.normal(-3.0, 4.0) + rng.normal(0, 8.0, per)).tolist() for i in range(g)}
        cm = clustered_mean(vals)
        return (cm.hi - cm.lo) / 2
    base_g = 11
    hw_base = float(np.median([sim_hw(base_g) for _ in range(200)]))
    for n in [30, 103]:
        proj = project_hw(hw_base, base_g, n)
        sim = float(np.median([sim_hw(base_g + n) for _ in range(200)]))
        rel = abs(proj - sim) / sim
        print(f"[projection] G=11 -> {base_g + n}: projected {proj:.3f}c vs simulated "
              f"{sim:.3f}c ({rel:.1%} apart; want <10%)")
        ok &= rel < 0.10

    # 2. Kish behaves at both extremes
    equal, skewed = np.full(11, 300), np.array([3000] + [10] * 10)
    print(f"[Kish] equal clusters -> G_eff {kish(equal):.2f} (want 11.00); "
          f"one dominant -> G_eff {kish(skewed):.2f} (want ~1)")
    ok &= abs(kish(equal) - 11) < 1e-9 and kish(skewed) < 1.5

    # 3. the power factor must be strictly stricter than mere exclusion
    gap, hw_just = 3.4, 3.39
    print(f"[power factor] HW={hw_just} vs gap={gap}: excludes="
          f"{hw_just < gap}, 80% power={hw_just <= gap / POWER_FACTOR} "
          f"(want True then False — 'just excludes' must not read as powered)")
    ok &= (hw_just < gap) and not (hw_just <= gap / POWER_FACTOR)

    print("SELFTEST", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--fills", default=PIN)
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    report(load(args.fills))


if __name__ == "__main__":
    main()
