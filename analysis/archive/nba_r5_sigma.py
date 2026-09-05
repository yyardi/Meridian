"""R5 — pregame totals sigma (sigma_T0). Registered harness.

Registration: docs/math/nba-r5-pregame-totals-sigma.md (amendments 1-7 landed;
this harness implements the amended text and NOTHING not in it).

ESTIMAND: sigma_T0 = SD(final total INCLUDING OT - closing total line), NBA.
Two arms, walk-forward, first eval after ONE fit season (amendment 4):
  T (points):   sigma = expanding-window SD of r_i = final_i - line_i
  L (relative): cv = expanding-window SD of r_i / line_i; per-game
                sigma_i = cv * line_i (amendment 1: per-game, never season-mean)
PRIMARY: one-season-ahead Gaussian log-score paired diff (L - T), season-
clustered t-CI over eval-season means. Decision rule (pre-registered):
L > T outside CI -> relative form; T > L outside CI -> points form;
straddle -> points on parsimony. The winner is adopted as the better GAUSSIAN
APPROXIMATION only (amendment 5a); A3's shape analysis retains authority.

ADOPTED CONSTANT (amendment 2 units): terminal expanding-window estimate in
the winning form - points value if T, DIMENSIONLESS CV if L.

STRUCTURE: the mutation suite runs FIRST and the process aborts non-zero on
any failure; the real read only executes after every mutation passes, in the
same invocation. There is no flag to skip mutations and no flag to run the
read alone. Author-runner: research agent (disclosed per #20 precedent).

FORBIDDEN FORMS (refused in code, not prose):
  - anchor other than closing_total (opening lines don't exist in the pin;
    the column name is asserted);
  - any fit season >= its eval season (look-ahead guard asserted per fold);
  - winsorizing/trimming: no clipping function appears; the no-trim rule is
    load-bearing for A3 (named consumer dependency);
  - regulation-only sigma ported to OT-inclusive settlement (the estimand is
    OT-inclusive; regulation appears ONLY inside mutation 3's direction check);
  - rows-not-games floors (evaluability is counted in games).

COVERAGE (rule 10, print-before-fit duty): the per-season lined-games table
prints before any fit; evaluable = >=900 lined games (a-priori round ~73% of
1,230, chosen blind - amendment 7); floor >=5 of 6 evals. Known from the pin
and disclosed: 2025 is partial (979/1,235 lined); the 2025 eval's fit jumps
the 2023-24 unlined hole (two-year drift gap, noted on that fold).
"""
import sys
import numpy as np
import pandas as pd
from scipy import stats

GAMES_PIN = "backups/exports/nba_games_20260901T225326Z.csv"
PLAYS_PIN = "backups/exports/nba_plays_20260901T225326Z.csv.gz"
LINED_BAR = 900          # amendment 7: a-priori, blind; re-barring = new registration
EVAL_FLOOR = 5           # of 6 expected evals (amendment 4)
SEED = 20260902          # mutation determinism; the real read uses no randomness

RNG = np.random.default_rng(SEED)


def load_games():
    g = pd.read_csv(GAMES_PIN)
    assert "closing_total" in g.columns, "anchor column missing: closing_total"
    g["final_total"] = g.team0_score + g.team1_score       # OT-inclusive by construction
    g["is_ot"] = g.max_period > 4
    g = g[g.closing_total.notna()].copy()
    g["r"] = g.final_total - g.closing_total
    return g


def coverage_table(g_all):
    cov = (g_all.groupby("season")
           .agg(games=("game_id", "count"),
                lined=("closing_total", lambda s: s.notna().sum()))
           .reset_index())
    cov["evaluable"] = cov.lined >= LINED_BAR
    print("== COVERAGE (print-before-fit duty, rule 10) ==")
    print(cov.to_string(index=False))
    return sorted(cov.loc[cov.evaluable, "season"].tolist())


def fold_stats(fit, ev):
    """Returns per-game paired log-score diff (L - T) and the fitted params."""
    sigma_T = fit.r.std(ddof=1)
    cv = (fit.r / fit.closing_total).std(ddof=1)
    ll_T = stats.norm.logpdf(ev.r, scale=sigma_T)
    ll_L = stats.norm.logpdf(ev.r, scale=cv * ev.closing_total)
    return ll_L - ll_T, sigma_T, cv


def clustered_ci(season_means, label):
    m, se = np.mean(season_means), stats.sem(season_means)
    tcrit = stats.t.ppf(0.975, len(season_means) - 1)
    lo, hi = m - tcrit * se, m + tcrit * se
    print(f"  {label}: mean {m:+.6f} [{lo:+.6f}, {hi:+.6f}] over {len(season_means)} seasons")
    return m, lo, hi


def walk_forward(g, seasons, quiet=False, splits=False):
    """Runs the registered protocol on frame g restricted to `seasons`.
    Returns (season_mean_diffs, fold_rows, terminal sigma_T, terminal cv)."""
    diffs, rows = [], []
    for k, ev_season in enumerate(seasons[1:], start=1):
        fit = g[g.season.isin(seasons[:k])]
        ev = g[g.season == ev_season]
        assert fit.season.max() < ev_season, "look-ahead guard"
        d, sigma_T, cv = fold_stats(fit, ev)
        diffs.append(d.mean())
        rows.append(dict(eval_season=ev_season, n=len(ev), sigma_T=round(sigma_T, 4),
                         cv=round(cv, 6), mean_diff_LminusT=round(d.mean(), 6),
                         note=("fit jumps 2023-24 hole" if ev_season == 2025 else "")))
        if splits:
            rows[-1]["diff_no_OT"] = round(d[~ev.is_ot.values].mean(), 6)
            dev = (ev.closing_total - ev.closing_total.median()).abs()
            inner = dev <= dev.median()
            rows[-1]["diff_inner_q"] = round(d[inner.values].mean(), 6)
            rows[-1]["diff_outer_q"] = round(d[~inner.values].mean(), 6)
    term_fit = g[g.season.isin(seasons)]
    term_sigma = term_fit.r.std(ddof=1)
    term_cv = (term_fit.r / term_fit.closing_total).std(ddof=1)
    if not quiet:
        print(pd.DataFrame(rows).to_string(index=False))
    return diffs, rows, term_sigma, term_cv


# ---------------- MUTATION SUITE (runs first; abort on any failure) ----------------

def mutation_shuffle_null(g, seasons):
    """Permute finals across games within season: L must NOT beat T outside CI;
    recovered sigma printed beside the unconditional within-season SD."""
    gs = g.copy()
    gs["final_total"] = gs.groupby("season")["final_total"].transform(
        lambda s: RNG.permutation(s.values))
    gs["r"] = gs.final_total - gs.closing_total
    diffs, _, term_sigma, _ = walk_forward(gs, seasons, quiet=True)
    m, lo, hi = clustered_ci(diffs, "shuffle-null L-T")
    uncond = gs.groupby("season").r.std(ddof=1).mean()
    print(f"  recovered terminal sigma {term_sigma:.4f} vs mean within-season SD {uncond:.4f}")
    assert not (lo > 0), "MUTATION FAIL: L beats T under shuffle (level-dependence should die)"
    print("  PASS: L does not beat T once the line-final pairing is destroyed")


def mutation_generator_recovery(g, seasons):
    """Synthetic finals ~ N(line, sigma_inj), two levels; recovery within 3*SE."""
    for sigma_inj in (14.0, 22.0):
        gs = g.copy()
        gs["final_total"] = gs.closing_total + RNG.normal(0, sigma_inj, len(gs))
        gs["r"] = gs.final_total - gs.closing_total
        _, _, term_sigma, _ = walk_forward(gs, seasons, quiet=True)
        se = sigma_inj / np.sqrt(2 * len(gs))
        print(f"  inject {sigma_inj}: recovered {term_sigma:.4f} (3*SE band +/-{3*se:.4f})")
        assert abs(term_sigma - sigma_inj) < 3 * se, f"MUTATION FAIL: {sigma_inj} not recovered"
    print("  PASS: both injected levels recovered - the needle moves")


def mutation_ot_direction(g, seasons):
    """OT inclusion must RAISE sigma vs regulation-only recompute. Regulation-end
    totals come from the cumulative-score maximum within period 4 (scores are
    non-decreasing; no clock parsing - ESPN junk-clock lesson)."""
    plays = pd.read_csv(PLAYS_PIN)
    p4 = plays[plays.period == 4].copy()
    p4["running_total"] = p4.home_score + p4.away_score
    reg_end = p4.groupby("game_id").running_total.max()
    gs = g.copy()
    gs["reg_total"] = gs.game_id.map(reg_end)
    usable = gs[gs.reg_total.notna() | ~gs.is_ot].copy()
    dropped = len(gs) - len(usable)
    usable["reg_total"] = np.where(usable.is_ot, usable.reg_total, usable.final_total)
    sigma_full = (usable.final_total - usable.closing_total).std(ddof=1)
    sigma_reg = (usable.reg_total - usable.closing_total).std(ddof=1)
    ot_share = 1 - (sigma_reg ** 2 / sigma_full ** 2)
    print(f"  sigma OT-inclusive {sigma_full:.4f} vs regulation-only {sigma_reg:.4f} "
          f"(OT variance share {ot_share:.4%}; {int(usable.is_ot.sum())} OT games; "
          f"{dropped} games lacked period-4 plays and are counted, not hidden)")
    assert sigma_full > sigma_reg, "MUTATION FAIL: OT inclusion did not raise sigma - instrument flag"
    print("  PASS: artifact direction as asserted (OT raises sigma)")


# ---------------- MAIN ----------------

def main():
    g_all = pd.read_csv(GAMES_PIN)
    seasons = coverage_table(g_all)
    g = load_games()
    g = g[g.season.isin(seasons)]
    n_evals = len(seasons) - 1
    print(f"\nevaluable seasons: {seasons} -> {n_evals} evals (floor >= {EVAL_FLOOR})")
    if n_evals < EVAL_FLOOR:
        print("INFEASIBLE-AS-REGISTERED: floors re-derive from the printed table")
        sys.exit(2)

    print("\n== MUTATION SUITE (strictly before the read) ==")
    print("[1] shuffle-null")
    mutation_shuffle_null(g, seasons)
    print("[2] generator recovery")
    mutation_generator_recovery(g, seasons)
    print("[3] OT artifact direction")
    mutation_ot_direction(g, seasons)
    print("== SUITE PASSED - proceeding to the registered read ==\n")

    print("== R5 READ (single-shot on the pin) ==")
    diffs, rows, term_sigma, term_cv = walk_forward(g, seasons, splits=True)
    m, lo, hi = clustered_ci(diffs, "PRIMARY paired log-score L-T")

    if lo > 0:
        verdict, form = "L WINS OUTSIDE CI", "relative"
    elif hi < 0:
        verdict, form = "T WINS OUTSIDE CI", "points"
    else:
        verdict, form = "STRADDLE -> POINTS ON PARSIMONY (tie-break, loser recorded)", "points"
    print(f"\nVERDICT: {verdict}")
    print("(the winner is the better GAUSSIAN APPROXIMATION only - amendment 5a;"
          " A3's skew/kurtosis authority is untouched)")

    df = pd.DataFrame(rows)
    print("\n== AMENDMENT 5b: OT robustness (descriptive, never gated) ==")
    no_ot = clustered_ci(df.diff_no_OT.tolist(), "paired L-T excluding OT games")
    flip = (no_ot[1] > 0) != (lo > 0) or (no_ot[2] < 0) != (hi < 0)
    print(f"  form choice {'FLIPS' if flip else 'does not flip'} on the OT split"
          f"{' - adoption append must say so' if flip else ''}")

    print("\n== AMENDMENT 6: L-mechanism decomposition (descriptive, never gated) ==")
    clustered_ci(df.diff_inner_q.tolist(), "inner quartiles |line - season median|")
    clustered_ci(df.diff_outer_q.tolist(), "outer quartiles |line - season median|")

    print("\n== ADOPTED CONSTANT (amendment 2 units) ==")
    n = len(g)
    if form == "points":
        se = term_sigma / np.sqrt(2 * n)
        print(f"  sigma_T0 = {term_sigma:.4f} points (SE {se:.4f}, n={n} games,"
              f" terminal expanding window over {seasons})")
    else:
        se = term_cv / np.sqrt(2 * n)
        print(f"  cv_T0 = {term_cv:.6f} dimensionless (SE {se:.6f}, n={n} games);"
              f" per-game sigma_i = cv_T0 * line_i")
    print("\nCalibration work, never edge work. No capital implication of any branch.")


if __name__ == "__main__":
    main()
