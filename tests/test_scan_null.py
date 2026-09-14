"""The permutation null, and the control that says it can see anything.

A 400-600 cell scan produces a best cell whatever the truth is. These test the
machinery that says what that best cell looks like with the edge removed and
everything else left alone.
"""
from __future__ import annotations

import importlib.util
import pathlib
import random
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
    rows = _rows(n_games=120, seed=21)
    null = N.null_distribution(rows, reps=150, seed=555)
    planted = N.plant_edge(rows, lo=0.60, hi=0.80, cents=40.0, seed=7)
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
    rows = _rows(n_games=120, seed=21)
    null = N.null_distribution(rows, reps=150, seed=555)
    floor = N.min_detectable_edge(rows, null, lo=0.60, hi=0.80)
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
    assert hc == hc, "HC is NaN"


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
