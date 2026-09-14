"""The permutation null, and the control that says it can see anything.

A 400-600 cell scan produces a best cell whatever the truth is. These test the
machinery that says what that best cell looks like with the edge removed and
everything else left alone.
"""
from __future__ import annotations

import importlib.util
import pathlib
import math
import random
import statistics
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / "cfb" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


N = _load("run_scan_null")
MTYPE = "baseball_team_full_game_winner"


def _rows(n_games=60, *, seed=1, rungs=1, league="mlb", mtype=MTYPE):
    """Synthetic winner markets: one row per game unless `rungs` says more."""
    rng = random.Random(seed)
    out = []
    for g in range(n_games):
        mid = rng.choice([0.25, 0.35, 0.50, 0.65, 0.75])
        # One outcome per GAME, shared by its rungs. Drawing each rung
        # independently would leave no within-game dependence for block
        # permutation to preserve, and the clustering test below would then
        # pass or fail on nothing.
        game_y = 1 if rng.random() < mid else 0
        for k in range(rungs):
            out.append({
                "market_slug": f"aec-{league}-g{g}-r{k}", "game_id": f"g{g}",
                "league": league, "mtype": mtype,
                "bid": mid - 0.01, "ask": mid + 0.01,
                "y": game_y,
            })
    return out


def _rows_every_cell(n_games=70, seed=77):
    """Rows across every (league, type) the registry scores, so m is not
    artificially small. A 1-row-per-game single-league fixture scores TWO cells
    of 29 and cannot support a control at all — which is how a planted-edge
    test came to fail for want of cells rather than want of signal."""
    from strategies.ladder import STRATEGIES
    pairs = sorted({(st["league"], ty) for st in STRATEGIES.values()
                    for ty in st["types"]})
    rng = random.Random(seed)
    out = []
    for lg, ty in pairs:
        for g in range(n_games):
            mid = rng.choice([0.18, 0.26, 0.34, 0.45, 0.55, 0.63, 0.72, 0.85])
            y = 1 if rng.random() < mid else 0
            for k in range(2):
                out.append({"market_slug": f"aec-{lg}-{ty}-{g}-{k}",
                            "game_id": f"{lg}-g{g}", "league": lg,
                            "mtype": f"x_{ty}", "bid": round(mid - 0.01, 3),
                            "ask": round(mid + 0.01, 3), "y": y})
    return out


# ------------------------------------------------------------ the permutation
def test_the_marginal_win_rate_is_preserved_exactly():
    """The null must destroy the price-outcome PAIRING and nothing else. A
    permutation that changes how often YES resolves is changing the world, not
    the pairing."""
    rows = _rows()
    ys, _ = N.permute_settlements(rows, random.Random(3))
    assert sum(ys) == sum(r["y"] for r in rows)


def test_prices_are_never_touched():
    rows = _rows()
    before = [(r["bid"], r["ask"]) for r in rows]
    N.permute_settlements(rows, random.Random(4))
    assert [(r["bid"], r["ask"]) for r in rows] == before


def test_whole_games_move_together():
    """★ The clustering requirement. Each game here is internally homogeneous —
    all outcomes 1 or all 0 — so if blocks travel intact every game stays
    homogeneous afterwards. Row-level shuffling would mix them."""
    rows = []
    for g in range(40):
        y = g % 2
        for k in range(3):
            rows.append({"market_slug": f"m-{g}-{k}", "game_id": f"g{g}",
                         "league": "mlb", "mtype": MTYPE,
                         "bid": 0.49, "ask": 0.51, "y": y})
    ys, _ = N.permute_settlements(rows, random.Random(5))
    by_game = {}
    for r, y in zip(rows, ys):
        by_game.setdefault(r["game_id"], set()).add(y)
    assert all(len(v) == 1 for v in by_game.values()), (
        "a game ended up with mixed outcomes — blocks were split and the null "
        "will be too narrow")


def test_a_stratum_with_one_game_is_counted_as_frozen():
    """Rows that cannot move contribute no null variance. Silently leaving
    them in place narrows the distribution, which is the failure direction
    that makes everything look significant."""
    rows = _rows(n_games=20) + [{
        "market_slug": "aec-cricket-solo", "game_id": "solo",
        "league": "cricket", "mtype": "match_winner",
        "bid": 0.4, "ask": 0.42, "y": 1}]
    _, frozen = N.permute_settlements(rows, random.Random(6))
    assert frozen >= 1


def test_row_shuffling_breaks_the_null_and_the_direction_is_not_the_obvious_one():
    """★ PERMUTING WHOLE GAMES IS LOAD-BEARING — and the brief had the sign
    backwards, which I only know because I measured it instead of asserting it.

    Expected: free row shuffling destroys within-game dependence, so the null
    comes out TOO NARROW and every cell clears it. Measured, the opposite:

        rows/game   block p95   free p95   ratio
            1          3.45       3.45      1.00
            2          3.45       4.41      1.28
            4          3.45       6.11      1.77      (3 seeds each, same shape)

    The mechanism is that `clustered()` builds the standard error from
    game-level residual SUMS. Block permutation keeps a game's outcomes
    aligned, so its residuals add — large sums, large SE, small t. A free
    shuffle mixes outcomes inside a game so the residuals partly cancel, the
    SE collapses and t inflates. The null therefore comes out WIDER, the scan
    becomes too conservative, and real edges are HIDDEN rather than
    manufactured.

    Either way the fix is the same and the reason is unchanged: a null has to
    reproduce the dependence the data actually has. Recording the direction
    because "too narrow, everything looks significant" is the intuition
    everyone reaches for, and here it is wrong.
    """
    correlated = _rows(n_games=50, rungs=4, seed=11)
    single = _rows(n_games=50, rungs=1, seed=11)

    def p95_of(rows, shuffler, seed=99, reps=150):
        chosen = N.select(rows)
        rng = random.Random(seed)
        ts = [N.summarise(N.score_cells(rows, shuffler(rows, rng), chosen))["max_abs_t"]
              for _ in range(reps)]
        return sorted(ts)[int(0.95 * (len(ts) - 1))]

    def free(rs, rng):
        ys = [r["y"] for r in rs]
        rng.shuffle(ys)
        return ys

    block = lambda rs, rng: N.permute_settlements(rs, rng)[0]   # noqa: E731

    assert p95_of(correlated, free) > p95_of(correlated, block), (
        "row shuffling did not change the null on correlated rungs — the "
        "clustering argument needs re-deriving before this harness is trusted")

    # CONTROL: with one row per game there is no within-game dependence to
    # destroy, so the two must agree exactly. Without this, the assertion
    # above would also pass for a shuffler that is simply broken.
    assert p95_of(single, free) == p95_of(single, block), (
        "the two permutations disagree even with one row per game, so the "
        "difference above is not about clustering")


# ------------------------------------------------------------ reproducibility
def test_the_null_is_seeded_and_reproducible():
    """A threshold nobody can reproduce is not a threshold."""
    rows = _rows(n_games=40, seed=2)
    a = N.null_distribution(rows, reps=40, seed=123)["quantiles"]
    b = N.null_distribution(rows, reps=40, seed=123)["quantiles"]
    c = N.null_distribution(rows, reps=40, seed=124)["quantiles"]
    assert a == b
    assert a != c, "different seeds gave identical draws — the seed is ignored"


# --------------------------------------------------- the control on the control
def test_the_monte_carlo_detects_a_planted_edge():
    """★ NEITHER NUMBER MEANS ANYTHING ALONE. Quantiles say what noise looks
    like; this says the instrument can tell signal from it. A null that flags
    nothing prints exactly the same quantiles as one that works."""
    rows = _rows_every_cell()
    null = N.null_distribution(rows, reps=120, seed=555)
    planted = N.plant_edge(rows, lo=0.60, hi=0.90, cents=25.0, seed=7)
    observed = N.summarise(N.score_cells(rows, planted))
    assert observed["max_abs_t"] > null["quantiles"]["max_abs_t"]["p95"], (
        f"the Monte Carlo did not see a planted 40c edge: observed "
        f"{observed['max_abs_t']:.2f} vs null p95 "
        f"{null['quantiles']['max_abs_t']['p95']:.2f} — it cannot distinguish "
        "signal from noise and its quantiles mean nothing")


def test_the_control_reports_the_smallest_edge_it_could_have_seen():
    """★ The pass/fail above is the weaker half. What a reader needs is the
    SMALLEST edge this sample could have detected — a scan whose floor is 20c
    cannot support a 5c claim, not because the claim is false but because the
    instrument could not have seen it either way.

    On synthetic data a +5c edge over ~48 games gives t ~ 0.7 against a
    max-|t| null near 4: undetectable, and that is a fact about the sample
    size rather than a defect. Asserted loosely because the exact floor moves
    with the fixture; what is pinned is that a floor EXISTS and is reported.
    """
    rows = _rows_every_cell()
    null = N.null_distribution(rows, reps=120, seed=555)
    floor = N.min_detectable_edge(rows, null, lo=0.60, hi=0.90, trials=20)
    assert floor is not None, "no candidate edge was detectable at all"
    assert floor >= 5, (
        "a 2c edge cleared a max-|t| null over many cells, which would mean "
        "the null is far too narrow")


def test_unplanted_data_does_not_clear_its_own_null():
    """The other direction, and the one that catches a null that flags
    EVERYTHING: data with no edge must sit inside its own distribution."""
    rows = _rows(n_games=120, seed=22)
    null = N.null_distribution(rows, reps=150, seed=556)
    observed = N.summarise(N.score_cells(rows, [r["y"] for r in rows]))
    assert observed["max_abs_t"] <= null["quantiles"]["max_abs_t"]["max"], (
        "unplanted data exceeded every one of its own null draws")


# ------------------------------------------------- the three statistics
def test_var_t_is_about_one_under_an_independent_null():
    rng = random.Random(4)
    v = N.var_t([rng.gauss(0, 1) for _ in range(4000)])
    assert 0.9 < v < 1.1, v


def test_the_pool_sees_what_the_best_cell_cannot():
    """★ WHY max|t| ALONE WOULD HIDE THE CASE THE SCAN EXISTS TO FIND.

    Ten cells at a true t of 3 among 490 null cells. Multiplicity demands
    roughly 3.89 of a single cell at m=500, so NOT ONE of the ten clears —
    max|t| reports nothing. Var(t) and Higher Criticism both move, because
    they read the pool rather than its maximum.
    """
    rng = random.Random(7)
    null_ts = [rng.gauss(0, 1) for _ in range(500)]
    diffuse = [rng.gauss(0, 1) for _ in range(490)] + [3.0] * 10

    assert max(abs(t) for t in diffuse) < 3.89, (
        "the planted cells individually clear the multiplicity threshold, so "
        "this fixture does not demonstrate the diffuse case")
    assert N.var_t(diffuse) > N.var_t(null_ts)
    assert N.higher_criticism(diffuse) > N.higher_criticism(null_ts)


def test_higher_criticism_is_not_just_a_restatement_of_the_maximum():
    """HC must respond to COUNT, not only to the largest value. Two vectors
    with the same maximum and different numbers of modest effects must not
    score the same, or it adds nothing to max|t|."""
    rng = random.Random(11)
    base = [rng.gauss(0, 1) for _ in range(480)]
    one = base + [3.0] + [0.0] * 19
    many = base + [3.0] * 20
    assert max(map(abs, one)) == max(map(abs, many))
    assert N.higher_criticism(many) > N.higher_criticism(one)


def test_the_independent_calibration_pins_both_conventions():
    """★ THE REGISTERED PAIR MIXES ONE-SIDED AND TWO-SIDED, and the harness has
    to pin both or the clustering gap gets measured against the wrong yardstick.

    Exact at m=500: median max|t| two-sided 3.198; median max t one-sided
    2.992; asymptotic MEAN of the one-sided max 2.907 — which is the
    registered 2.9. P(max|t| > 3) two-sided 0.741 — the registered 0.74.
    Both registered numbers are correct on their own terms and cannot both
    describe one statistic.

    This harness is two-sided throughout, so 3.198/0.741 is the pair to read
    against; comparing the permutation p50 to 2.9 would book the convention
    difference as clustering.
    """
    c = N.calibration_independent(500, trials=1500, seed=5)
    assert 3.05 <= c["median_best_abs_t"] <= 3.35, c
    assert 0.66 <= c["p_any_abs_exceeds_3"] <= 0.82, c
    assert 2.85 <= c["median_best_signed_t"] <= 3.15, c
    assert c["median_best_abs_t"] > c["median_best_signed_t"], (
        "two-sided max must exceed one-sided; the conventions are swapped")


# --------------------------------------------- the two-sided control bands
def test_the_control_band_rejects_a_leaking_harness():
    """★ ONLY THE UPPER BOUND CATCHES LEAKAGE. An edge planted AT the detection
    floor must be missed about half the time — that is what being at the floor
    means. Recovering it almost always means the harness is seeing the
    planting rather than the edge."""
    ok, why = N.control_verdict(0.98, 1.00)
    assert not ok and "LEAK" in why


def test_the_control_band_rejects_a_blunt_harness():
    ok, why = N.control_verdict(0.50, 0.40)
    assert not ok and "BLUNT" in why


def test_the_control_band_accepts_the_designed_shape():
    ok, why = N.control_verdict(0.50, 0.93)
    assert ok, why


def test_recovery_is_a_rate_not_a_single_trial():
    """One planted trial is a coin flip. A bigger edge must recover at least as
    often as a smaller one, which a single trial cannot guarantee."""
    rows = _rows(n_games=120, seed=31)
    null = N.null_distribution(rows, reps=60, seed=777)
    small = N.recovery_rate(rows, null, lo=0.60, hi=0.80, cents=5, trials=25)
    big = N.recovery_rate(rows, null, lo=0.60, hi=0.80, cents=60, trials=25)
    assert 0.0 <= small <= 1.0 and 0.0 <= big <= 1.0
    assert big >= small, (small, big)


def test_higher_criticism_does_not_explode_on_a_tiny_p_value():
    """★ HC+ , and the + is load-bearing. Plain HC divides by sqrt(p(1-p)), so
    one extreme cell sends it to infinity — the unstabilised version returned
    p99 2,864 and max 10,626 on synthetic NULL data, which is a division by
    almost zero wearing the clothes of a heavy tail. Below 1/m a p-value is an
    extrapolation of the normal tail rather than something the sample
    measured."""
    rng = random.Random(3)
    ts = [rng.gauss(0, 1) for _ in range(199)] + [12.0]
    hc = N.higher_criticism(ts)
    assert hc < 50.0, f"HC exploded to {hc:.1f} on one extreme cell"
    assert not math.isnan(hc), "HC is NaN"


def test_higher_criticism_still_moves_when_it_should():
    """The stabilisation must not have flattened it: the diffuse case still
    has to score above a pure null, or HC+ is just a constant."""
    rng = random.Random(9)
    null_ts = [rng.gauss(0, 1) for _ in range(500)]
    diffuse = [rng.gauss(0, 1) for _ in range(490)] + [3.0] * 10
    assert N.higher_criticism(diffuse) > N.higher_criticism(null_ts)


def test_higher_criticism_is_not_dead_on_ordinary_null_data():
    """★ THE OTHER WAY TO GET STABILISATION WRONG, and I shipped it first. A
    strict HC+ that SKIPS every p below 1/m returned 0.00 for all 400 null
    replicates and for the observed value — a statistic with no variance
    reports exactly as much as one that explodes. It must MOVE across null
    draws, or it cannot separate anything from anything."""
    rng = random.Random(17)
    vals = {N.higher_criticism([rng.gauss(0, 1) for _ in range(29)])
            for _ in range(60)}
    assert len(vals) > 5, f"HC took only {len(vals)} distinct values: {vals}"
    assert max(vals) > 0.0, "HC is identically zero on null data"


# --------------------------------------------------------------------- #
# The m that every statistic is read against.
# --------------------------------------------------------------------- #
def test_the_reported_m_is_the_m_actually_scored():
    """★ THE BUG THAT COST A STATISTIC ITS PROMOTION.

    `score_cells` drops any cell with fewer than two bets, so on a tape
    covering one league most of the registry never scores. The header reported
    `len(select(rows))` — 29 — while the statistics were computed on 7. At
    m=7, `int(0.25 * m) == 1`, so HC examined a SINGLE term, barely moved, and
    I reported it as a dead statistic and asked for its promotion to be
    stopped. The statistic was fine. The m was a fiction.

    Every number in the report is read against m, so m has to be the one that
    was used.
    """
    rows = _rows(n_games=60, seed=41)           # mlb only: most cells cannot score
    null = N.null_distribution(rows, reps=20, seed=1)
    assert null["cells_scored"] <= null["cells_selected"]
    assert null["cells_scored"] == len(N.score_cells(rows, [r["y"] for r in rows])), (
        "the reported m is not the number of cells actually scored")
    assert not null["cells_scored_varied"], (
        "the scored cell count moved between replicates, so a single m does "
        "not describe this run")


def test_higher_criticism_examines_more_than_one_term_at_small_m():
    """int() truncation left exactly one term below m=8, which is how HC came
    to look like a point mass. With one term it cannot respond to the COUNT of
    small p-values, which is the only thing it is for."""
    strong = [4.0, 3.5] + [0.1] * 5            # m=7, two clearly small p's
    weak = [4.0] + [0.1] * 6                   # m=7, one
    assert N.higher_criticism(strong) > N.higher_criticism(weak), (
        "HC did not respond to a second small p-value at m=7 — it is still "
        "reading a single term")


def test_empirical_hc_has_no_ceiling_to_sit_on():
    """★ The whole failure family, removed at the source. Empirical p-values
    are bounded below by 1/(reps+1) BY CONSTRUCTION, so nothing explodes,
    nothing is skipped, and no denominator is clamped — which is what gave the
    clamped version a ceiling at alpha0*m that the permutation sat on."""
    rows = _rows(n_games=120, seed=42)
    null = N.null_distribution(rows, reps=60, seed=9)
    observed = N.score_cells(rows, [r["y"] for r in rows])
    hc = N.empirical_hc(observed, null)
    m = null["cells_scored"]
    ceiling = (m ** 0.5) * (max(2, int(0.25 * m)) / m) / ((1 / m) * (1 - 1 / m)) ** 0.5
    assert hc < ceiling, f"empirical HC {hc:.2f} reached the clamped ceiling {ceiling:.2f}"
    assert not math.isnan(hc)


def test_empirical_hc_moves_across_null_draws():
    """A statistic with no spread cannot separate anything; that is the tell I
    had on screen twice before computing the ceiling."""
    rows = _rows(n_games=120, seed=43)
    null = N.null_distribution(rows, reps=80, seed=10)
    rng = random.Random(3)
    chosen = N.select(rows)
    vals = set()
    for _ in range(30):
        ys, _ = N.permute_settlements(rows, rng)
        vals.add(round(N.empirical_hc(N.score_cells(rows, ys, chosen), null), 6))
    assert len(vals) > 5, f"empirical HC took only {len(vals)} distinct values"


# --------------------------------------------------------------------- #
# Degeneracy, judged inside every replicate.
# --------------------------------------------------------------------- #
def test_a_cell_with_no_outcome_variation_is_excluded():
    """★ 40 bets all settling YES, prices over 40 ticks: t = 67.14. The same
    prices with outcomes varying: t = 1.94. The sandwich has no risk to measure
    so it measures PRICE DISPERSION, the interval collapses and the mean stays
    large. On the real scan 16 such cells were all twelve of the top twelve."""
    from strategies.base import Bet

    rows = [{"market_slug": f"m{g}", "game_id": f"g{g}", "league": "mlb",
             "mtype": "baseball_team_full_game_winner",
             "bid": round(0.40 + 0.004 * g - 0.01, 4),
             "ask": round(0.40 + 0.004 * g + 0.01, 4), "y": 1} for g in range(40)]
    chosen = {"deg": [Bet(market_slug=r["market_slug"], side="yes",
                          price=r["ask"], stake=r["ask"],
                          game_id=r["game_id"]) for r in rows]}
    drop = {}
    cells = N.score_cells(rows, [1] * 40, chosen, dropped=drop)
    assert cells == {}, "a cell with no outcome variation was scored"
    assert drop["degenerate"] == 1

    varied = [1 if g % 2 else 0 for g in range(40)]
    drop2 = {}
    assert N.score_cells(rows, varied, chosen, dropped=drop2) != {}
    assert drop2["degenerate"] == 0


def test_the_guard_runs_inside_the_replicate_not_once():
    """★ Permutation CREATES and DESTROYS degeneracy, so m varies by replicate.
    A null filtered on the observed degeneracy set would reproduce the artifact
    in the reference and then agree with the observed value for the wrong
    reason."""
    rows = _rows_every_cell(n_games=12, seed=5)     # thin: degeneracy will occur
    null = N.null_distribution(rows, reps=40, seed=3)
    assert "degenerate_per_rep" in null and "reps_with_degenerate" in null
    assert null["cells_scored_min"] <= null["cells_scored"] <= null["cells_scored_max"]
    assert null["reps_with_degenerate"] >= 0


def test_the_scan_floors_are_matched_not_chosen():
    r"""G_FLOOR is the scan's, so the reference is filtered like the instrument
    it calibrates.

    Read by AST, not by regex: the scan declares it as a TUPLE,
    `FEE_PM, G_FLOOR = 0.06, 6`, and `G_FLOOR\s*=\s*(\d+)` matched
    "G_FLOOR = 0" out of the 0.06. Importing the module is not an option — it
    runs the scan at import.
    """
    import ast

    tree = ast.parse((REPO / "cfb" / "run_scan.py").read_text())
    found = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            names = (tgt.elts if isinstance(tgt, ast.Tuple) else [tgt])
            vals = (node.value.elts if isinstance(node.value, ast.Tuple)
                    else [node.value])
            if len(names) != len(vals):
                continue
            for nm, vl in zip(names, vals):
                if isinstance(nm, ast.Name) and isinstance(vl, ast.Constant):
                    found[nm.id] = vl.value
    assert "G_FLOOR" in found, "could not read G_FLOOR from the scan"
    assert N.G_FLOOR == found["G_FLOOR"], (
        f"null uses G_FLOOR={N.G_FLOOR}, the scan uses {found['G_FLOOR']} — "
        "the reference would be over a different population")


def test_p_values_use_the_scans_t_distribution_not_the_normal():
    """At G=6 the scan's df is 5 and t(5).sf(3)=0.01505 against the normal
    0.00135 — an 11x gap at a t the scan sees routinely. HC reads the SMALLEST
    p-values, so the convention has to match."""
    assert N._p_two_sided(3.0, 5) > 8 * N._p_two_sided(3.0, None)
    assert N._p_two_sided(3.0, None) < 0.01


# --------------------------------------------------------------------- #
# The binomial branch: exact on the win count, honest about clustering.
# --------------------------------------------------------------------- #
def test_the_poisson_binomial_reduces_to_the_binomial_when_prices_agree():
    """The control on the exact test. If every break-even is the same, the
    Poisson-binomial must BE the binomial — otherwise the convolution is wrong
    and every p downstream of it is wrong."""
    pmf = N.poisson_binomial_pmf([0.3] * 12)
    assert abs(sum(pmf) - 1.0) < 1e-12
    assert abs(pmf[0] - 0.7 ** 12) < 1e-12
    from math import comb
    assert abs(pmf[4] - comb(12, 4) * 0.3 ** 4 * 0.7 ** 8) < 1e-12


def test_a_decile_band_makes_the_single_p_binomial_wrong():
    """★ A decile spans a 0.1 PRICE BAND, so break-even varies within the cell
    and the exact null is Poisson-binomial. Collapsing to one p mis-states the
    tail — the same class of approximation as the sandwich it replaces, milder
    but not free."""
    spread = [0.20 + 0.01 * i for i in range(11)]      # 0.20 .. 0.30
    flat = [sum(spread) / len(spread)] * len(spread)
    assert N.poisson_binomial_pmf(spread)[0] != N.poisson_binomial_pmf(flat)[0]
    # and the exact version is not merely different, it is the one that sums
    assert abs(sum(N.poisson_binomial_pmf(spread)) - 1.0) < 1e-12


def test_break_even_includes_the_fee():
    """EV = p - ask - fee = 0, so break-even is ABOVE the ask. A break-even
    that forgot the fee would make every cell look better than it is."""
    assert N.break_even(0.50) > 0.50
    assert abs(N.break_even(0.50) - (0.50 + 0.06 * 0.25)) < 1e-12
    assert N.break_even(1.0) == 1.0          # no fee at the boundary


def test_clustering_the_win_count_is_not_optional():
    """★ A BINOMIAL ASSUMES INDEPENDENT BETS AND BETS IN ONE GAME ARE NOT —
    which is the entire reason the sandwich clustered. Replacing one with the
    other trades a homogeneity failure for a clustering failure.

    Measured on the real tape, nfl first-quarter spread decile 0: 68 bets over
    15 games, n/G = 4.5. Per-bet Poisson-binomial p = 5.11e-02; collapsed to
    one observation per game it is p = 1.00. The cell is not evidence at all,
    and the per-bet test said borderline.
    """
    from strategies.base import Bet

    rows, ys = [], []
    for g in range(15):
        for k in range(4):                    # 4 bets per game, all agreeing
            rows.append({"market_slug": f"m{g}-{k}", "game_id": f"g{g}",
                         "league": "nfl", "mtype": "x_spread",
                         "bid": 0.04, "ask": 0.06, "y": 0.0})
            ys.append(0.0)
    chosen = {"cell": [Bet(market_slug=r["market_slug"], side="yes",
                           price=r["ask"], stake=r["ask"],
                           game_id=r["game_id"]) for r in rows]}
    per_bet = N.binomial_cells(rows, ys, chosen, cluster=False)["cell"]
    per_game = N.binomial_cells(rows, ys, chosen, cluster=True)["cell"]
    assert per_bet["unit_n"] == 60 and per_game["unit_n"] == 15
    assert abs(per_bet["n_over_g"] - 4.0) < 1e-9
    assert per_game["p"] > per_bet["p"], (
        "clustering did not weaken the evidence — the reduction is not being "
        "applied and the p is overstated by roughly sqrt(n/G)")


def test_min_p_is_the_across_cell_statistic_not_the_per_cell_one():
    """Per cell the binomial is exact and needs no permutation — and the
    permutation would ABSORB it, since shuffling existing settlements holds the
    marginal win count fixed, which is what that hypothesis is about. What needs
    a reference is the minimum over correlated cells."""
    assert N.min_p({"a": {"p": 0.3}, "b": {"p": 0.02}, "c": {"p": 0.9}}) == 0.02
    assert N.min_p({}) == 1.0


def test_the_cached_price_table_is_the_same_test_it_replaces():
    """★ THE CONTROL ON THE OPTIMISATION, AND IT HAD TO BE REWRITTEN. My first
    version compared `binomial_cells(table=tbl)` against `binomial_cells(table=None)`
    — but table=None just calls `cell_price_table` itself, so both sides shared
    the premise under test and the check could not fail. The reference has to be
    built in the test, from the definition: group by game, mean break-even per
    game, majority outcome, exact Poisson-binomial p.
    """
    from strategies.base import Bet
    rows, ys = [], []
    for g in range(9):
        for j in range(2):
            rows.append({"market_slug": f"m{g}-{j}", "game_id": f"g{g}",
                         "league": "cfb", "mtype": "full_game_winner",
                         "bid": 0.30 + 0.01 * j, "ask": 0.32 + 0.01 * j,
                         "y": float((g + j) % 3 == 0)})
            ys.append(rows[-1]["y"])
    chosen = {"c": [Bet(market_slug=r["market_slug"], side="yes", price=r["ask"],
                        stake=r["ask"], game_id=r["game_id"]) for r in rows]}
    got = N.binomial_cells(rows, ys, chosen, cluster=True,
                           table=N.cell_price_table(rows, chosen, cluster=True))["c"]

    # --- the independent reference, written out longhand ---
    ref_ps, ref_k = [], 0
    for g in range(9):
        mem = [i for i, r in enumerate(rows) if r["game_id"] == f"g{g}"]
        ref_ps.append(sum(N.break_even(rows[i]["ask"]) for i in mem) / len(mem))
        ref_k += int(sum(ys[i] for i in mem) / len(mem) >= 0.5)
    assert got["k"] == ref_k
    assert got["unit_n"] == 9
    assert abs(got["p"] - N.poisson_binomial_p(ref_k, ref_ps)) < 1e-12
    # the table answers for EVERY achievable k, not only the observed one
    tbl = N.cell_price_table(rows, chosen, cluster=True)["c"]
    assert len(tbl["pval"]) == 10
    for k in range(10):
        assert abs(tbl["pval"][k] - N.poisson_binomial_p(k, ref_ps)) < 1e-12


def test_games_per_cell_do_not_move_under_permutation():
    """★ WHY MIXED GAMES ARE KEPT BY MAJORITY. G is a property of the price/game
    structure, so it must be identical in every replicate. Dropping disagreeing
    games would shrink G in the NULL only — the permutation manufactures
    disagreement — and a smaller-G null cannot reach as far into the tail, which
    biases toward my own hypothesis."""
    rows = _rows_every_cell()
    chosen = N.select(rows)
    tbl = N.cell_price_table(rows, chosen, cluster=True)
    rng = random.Random(5)
    seen = set()
    for _ in range(25):
        ys, _f = N.permute_settlements(rows, rng)
        bc = N.binomial_cells(rows, ys, chosen, cluster=True, rng=rng, table=tbl)
        seen.add(tuple(sorted((k, v["unit_n"]) for k, v in bc.items())))
    assert len(seen) == 1, "G moved under permutation — the null is not comparable"


def test_an_exact_tie_is_not_silently_a_win():
    """A 1-1 game has no direction. A fixed `>= 0.5` would call every such game a
    win and lift the null's k on both tails, which is a bias with no argument
    behind it."""
    from strategies.base import Bet
    rows = [{"market_slug": f"m{j}", "game_id": "g0", "league": "cfb",
             "mtype": "full_game_winner", "bid": 0.48, "ask": 0.50,
             "y": float(j == 0)} for j in range(2)]
    rows.append({"market_slug": "m2", "game_id": "g1", "league": "cfb",
                 "mtype": "full_game_winner", "bid": 0.48, "ask": 0.50, "y": 0.0})
    ys = [r["y"] for r in rows]
    chosen = {"c": [Bet(market_slug=r["market_slug"], side="yes", price=r["ask"],
                        stake=r["ask"], game_id=r["game_id"]) for r in rows]}
    tbl = N.cell_price_table(rows, chosen, cluster=True)
    ks = {N.binomial_cells(rows, ys, chosen, cluster=True,
                           rng=random.Random(s), table=tbl)["c"]["k"]
          for s in range(40)}
    assert ks == {0, 1}, f"tie-break is deterministic, saw k in {ks}"
    assert N.binomial_cells(rows, ys, chosen, cluster=True,
                            table=tbl)["c"]["mixed_games"] == 1


def test_min_p_is_drawn_in_the_null_and_has_a_spread():
    """A null with no spread is not a null. min-p must vary across replicates —
    if it were constant the multiplicity reference would be a single number
    dressed as a distribution."""
    rows = _rows_every_cell()
    null = N.null_distribution(rows, reps=40, seed=3)
    assert "min_p" in null["draws"]
    assert len(null["draws"]["min_p"]) == 40
    assert len(set(null["draws"]["min_p"])) > 1, "min-p is degenerate"
    assert null["binomial_cells"] > 0
    assert null["mixed_games_per_rep"] is not None


# --------------------------------------------------------------------------- #
# The null is PARAMETRIC now, and the control took three tries to become real.
# --------------------------------------------------------------------------- #
def test_the_h0_draw_reproduces_the_prices_it_was_built_from():
    """★ THE PROPERTY THE PERMUTATION DESTROYED. Permutation strata were
    (league, market type), which span every price decile, so a shuffle handed a
    5c longshot's cell the outcome of a favourite: decile 0's win rate went
    0.039 -> 0.140 and decile 9's 0.935 -> 0.766, everything flattened toward
    the pooled 0.439. That is roughly +8c/contract of artifact at the cheap end.

    Under the parametric draw each bet's win probability IS its break-even, so
    calibration holds by construction. Checked per price band, because a pooled
    win rate cannot see this -- the permutation preserved the pooled rate
    exactly and that is what made it look sound."""
    rows = _rows_every_cell()
    rng = random.Random(4)
    bands = [(0.0, 0.2), (0.4, 0.6), (0.8, 1.0)]
    tot = {b: [0.0, 0] for b in bands}
    for _ in range(60):
        ys = N.draw_under_h0(rows, rng)
        for r, y in zip(rows, ys):
            for b in bands:
                if b[0] <= r["ask"] < b[1]:
                    tot[b][0] += y
                    tot[b][1] += 1
    for b in bands:
        got = tot[b][0] / tot[b][1]
        want = statistics.fmean(N.break_even(r["ask"]) for r in rows
                                if b[0] <= r["ask"] < b[1])
        assert abs(got - want) < 0.06, (
            f"band {b}: drew {got:.3f} where break-even is {want:.3f} — the "
            "null is not reproducing the prices it claims to hold fixed")


def test_the_draw_keeps_a_games_bets_together():
    """One uniform per GAME, not per bet. Independent draws give a null too
    narrow by roughly sqrt(n/G) -- the same factor, in the same direction, as an
    independent binomial overstating a cell."""
    rows = [{"market_slug": f"m{i}", "game_id": f"g{i // 4}", "league": "cfb",
             "mtype": "full_game_winner", "bid": 0.49, "ask": 0.50, "y": 0.0}
            for i in range(40)]
    rng = random.Random(9)
    agreed = sum(len({*ys[i:i + 4]}) == 1
                 for _ in range(40)
                 for ys in [N.draw_under_h0(rows, rng)]
                 for i in range(0, 40, 4))
    # every game's four bets must agree, every time
    assert agreed == 40 * 10, f"{agreed} of 400 game blocks agreed internally"


def test_the_control_does_not_fire_when_nothing_is_planted():
    """★★ THE TEST THAT BROKE THE CONTROL TWICE, AND THE ONLY ONE THAT COULD.
    Ask what the instrument does at ZERO effect.

    First version: `plant_edge` redrew each bet INDEPENDENTLY while the null
    draws one uniform per game, so min-p "recovered" at 0.70 with a zero-cent
    plant -- firing on the redraw, not on any edge.

    Second version: it kept OBSERVED settlements outside the bucket, so min-p,
    being a MINIMUM over all cells, picked up the real tape's own most extreme
    cell (third_quarter_total/dec7, p=1.17e-04) which the plant never touches.
    Zero-cent recovery 0.97 against a nominal 0.05. The sandwich statistics
    escaped that one only by magnitude -- observed max|t| 3.99 against a p95 of
    9.21 -- which is being right for the wrong reason.

    Third version draws every row under H0 with one uniform per game and adds
    the edge only inside the bucket. Measured on the canonical artifact, 120
    trials: 0c gives max|t| 0.07, Var(t) 0.04, HC 0.04, min-p 0.07."""
    rows = _rows_every_cell()
    zero = N.plant_edge(rows, lo=0.60, hi=0.80, cents=0.0, seed=11)
    big = N.plant_edge(rows, lo=0.60, hi=0.80, cents=25.0, seed=11)
    assert zero != big, "the plant is ignoring `cents`"

    # a zero plant is a pure H0 draw: its win rate in the bucket is break-even
    idx = [i for i, r in enumerate(rows) if 0.60 <= (r["bid"] + r["ask"]) / 2 < 0.80]
    assert idx, "fixture has no rows in the control bucket"
    be = statistics.fmean(N.break_even(rows[i]["ask"]) for i in idx)
    got = statistics.fmean(
        statistics.fmean(N.plant_edge(rows, lo=0.60, hi=0.80, cents=0.0,
                                      seed=200 + k)[i] for i in idx)
        for k in range(40))
    assert abs(got - be) < 0.08, (
        f"a ZERO-cent plant won {got:.3f} of the time where break-even is "
        f"{be:.3f} — the control is not at H0 and its recovery rates are not "
        "power")
    # and outside the bucket it is H0 too, not the observed tape
    out = [i for i in range(len(rows)) if i not in set(idx)]
    if out:
        assert any(N.plant_edge(rows, lo=0.60, hi=0.80, cents=0.0, seed=s)[i]
                   != rows[i]["y"] for s in range(6) for i in out), (
            "outside the bucket the plant reproduced the observed settlements — "
            "min-p then reports the real tape's extremes as a recovery")


def test_the_permutation_is_no_longer_the_null():
    """It stays in the file because its failure is the lesson, but it must not
    be what `null_distribution` uses. Asserted at the source: a default that
    silently went back to permuting would reproduce the whole defect."""
    src = pathlib.Path(N.__file__).read_text()
    fn = src[src.index("def null_distribution("):src.index("def empirical_hc(")]
    assert "draw = draw_under_h0 if draw is None else draw" in fn
    assert "permute_settlements(" not in fn, (
        "null_distribution is permuting again — that removes calibration, not "
        "the edge")
