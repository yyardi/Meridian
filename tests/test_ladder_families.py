"""The cross-family consistency scanner, pinned on the ways it can be wrong.

Three kinds of test here and the middle one is the point.

1. ARITHMETIC: every basket's edge is netted of every leg's fee, sized by its
   smallest leg, and guarded by the stale-rung cap -- the same four defects
   `test_ladder_scan.py` pins for the two-leg spread pair.
2. THE MATH ITSELF: the Frechet bounds are checked against enumerated joint
   distributions, including one that breaks the upper bound and leaves the
   lower one standing. A bound that is merely coded correctly is worth nothing
   if the bound is false, and no amount of quote fixtures can tell.
3. ORIENTATION: a CORRECT totals ladder fed to the spread scanner produces a
   phantom violation. That is the defect this module exists to prevent and it
   is asserted as a positive fact about the wrong function, not as a comment.
"""
from __future__ import annotations

import itertools
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core.ladder import families, scan  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _q(bid, ask, bid_size=100.0, ask_size=100.0):
    return (bid, ask, bid_size, ask_size)


def _c(key, bid, ask, bid_size=100.0, ask_size=100.0):
    return families.Claim(key, bid, ask, bid_size, ask_size)


# --------------------------------------------------------------------------- #
# 1. the two-leg dominance, which is every ladder and every containment
# --------------------------------------------------------------------------- #

def test_a_correctly_ordered_totals_ladder_yields_nothing():
    """Over 48.5 must be dearer than Over 52.5: the higher line is harder."""
    rungs = {48.5: _c("48.5", 0.60, 0.61), 52.5: _c("52.5", 0.40, 0.41)}
    pairs = families.totals_ladder_pairs(rungs)
    found = [families.dominance("g", rungs[a], rungs[b], "totals_ladder")
             for a, b in pairs]
    assert [v for v in found if v is not None] == []


def test_an_inverted_totals_ladder_is_found_and_priced_net_of_BOTH_fees():
    rungs = {48.5: _c("48.5", 0.40, 0.41), 52.5: _c("52.5", 0.50, 0.51)}
    (sub, sup), = families.totals_ladder_pairs(rungs)
    assert sub == 52.5 and sup == 48.5, "the HIGHER line is the subset"
    v = families.dominance("g", rungs[sub], rungs[sup], "totals_ladder")
    gross = 0.50 - 0.41
    assert v is not None
    assert abs(v.edge - (gross - scan.fee(0.50) - scan.fee(0.41))) < 1e-12
    assert v.edge < gross, "two fees must come off"


def test_the_spread_scanner_on_a_CORRECT_totals_ladder_manufactures_a_violation():
    """THE ORIENTATION TRAP, asserted rather than described.

    These two rungs are a perfectly ordered Over ladder. `scan.scan_ladder`
    hard-codes the spread ordering -- higher line is EASIER -- so it reads the
    same board as an arbitrage. A totals scan that reuses it reports the honest
    board as broken and stays silent on the broken one.
    """
    ordered_over_ladder = {48.5: _q(0.50, 0.51), 52.5: _q(0.40, 0.41)}
    assert scan.scan_ladder("g", ordered_over_ladder), (
        "if this ever stops firing, scan.scan_ladder's ordering changed and "
        "families.totals_ladder_pairs must be re-derived against it")


def test_the_winner_identity_is_scanned_in_both_directions():
    """An equality is two implications. A winner market quoted BELOW the 0-line
    spread is as impossible as one quoted above, and a one-directional scan
    sees half the board."""
    winner = _c("winner", 0.62, 0.63)
    zero = _c("spread+0.0", 0.40, 0.41)
    assert families.dominance("g", winner, zero, "winner_is_line_zero") is None
    assert families.dominance("g", zero, winner, "winner_is_line_zero") is None
    flipped_winner = _c("winner", 0.40, 0.41)
    flipped_zero = _c("spread+0.0", 0.50, 0.51)
    assert families.dominance("g", flipped_zero, flipped_winner,
                              "winner_is_line_zero") is not None


def test_a_stale_rung_is_excluded_rather_than_counted():
    """The same guard and the same reason as the spread scan: an 88c 'edge' is
    a rung nobody updated, not a market."""
    sub, sup = _c("52.5", 0.93, 0.94), _c("48.5", 0.03, 0.04)
    assert families.dominance("g", sub, sup, "totals_ladder") is None
    wide = families.dominance("g", sub, sup, "totals_ladder", max_edge=1.0)
    assert wide is not None and wide.edge > families.MAX_PLAUSIBLE_EDGE


def test_size_is_the_smallest_leg_and_is_capped():
    sub = _c("52.5", 0.50, 0.51, bid_size=4.0, ask_size=900.0)
    sup = _c("48.5", 0.40, 0.41, bid_size=900.0, ask_size=900.0)
    assert families.dominance("g", sub, sup, "totals_ladder").size == 4.0
    huge_sub = _c("52.5", 0.50, 0.51, bid_size=9e6, ask_size=9e6)
    huge_sup = _c("48.5", 0.40, 0.41, bid_size=9e6, ask_size=9e6)
    v = families.dominance("g", huge_sub, huge_sup, "totals_ladder")
    assert v.size == families.MAX_PLAUSIBLE_SIZE


# --------------------------------------------------------------------------- #
# 2. the three-leg baskets
# --------------------------------------------------------------------------- #

def test_the_frechet_upper_basket_pays_three_fees_not_two():
    """Three legs, three fees. This is why a three-leg family needs materially
    more gross disorder than a pair to clear zero."""
    whole = _c("total 45.5", 0.70, 0.71)
    parts = (_c("tt-a 20.5", 0.25, 0.26), _c("tt-b 24.5", 0.30, 0.31))
    v = families.frechet_upper("g", whole, parts)
    gross = 0.70 - 0.26 - 0.31
    fees = scan.fee(0.70) + scan.fee(0.26) + scan.fee(0.31)
    assert v is not None and abs(v.edge - (gross - fees)) < 1e-12
    assert len(v.legs) == 3


def test_the_frechet_lower_basket_subtracts_k_minus_one():
    """P(X>N) >= P(U>u) + P(V>v) - 1: the '- 1' is the whole content of the
    bound and dropping it turns every ordinary board into an arbitrage."""
    whole = _c("total 44.5", 0.40, 0.41)
    parts = (_c("tt-a 20.5", 0.80, 0.81), _c("tt-b 24.5", 0.75, 0.76))
    v = families.frechet_lower("g", whole, parts)
    gross = 0.80 + 0.75 - 1.0 - 0.41
    fees = scan.fee(0.80) + scan.fee(0.75) + scan.fee(0.41)
    assert v is not None and abs(v.edge - (gross - fees)) < 1e-12
    without_the_minus_one = 0.80 + 0.75 - 0.41
    assert v.edge < without_the_minus_one


def test_a_three_leg_basket_is_sized_by_its_smallest_of_three():
    whole = _c("total 45.5", 0.70, 0.71, bid_size=500.0)
    parts = (_c("tt-a 20.5", 0.25, 0.26, ask_size=7.0),
             _c("tt-b 24.5", 0.30, 0.31, ask_size=500.0))
    assert families.frechet_upper("g", whole, parts).size == 7.0


def test_the_legs_name_the_button_the_operator_presses():
    """The protocol's only non-price loss state is clicking the wrong side, so
    a basket carries buy-NO prices already translated."""
    whole = _c("total 45.5", 0.70, 0.71)
    parts = (_c("tt-a 20.5", 0.25, 0.26), _c("tt-b 24.5", 0.30, 0.31))
    legs = families.frechet_upper("g", whole, parts).legs
    assert legs[0].side == "buy_no" and abs(legs[0].price - 0.30) < 1e-12
    assert all(leg.side == "buy_yes" for leg in legs[1:])


# --------------------------------------------------------------------------- #
# 3. the bounds themselves, against enumerated distributions
# --------------------------------------------------------------------------- #

def _joint_grid(support):
    """Every deterministic-per-atom joint over a 3-point sample space.

    Enumerating joints rather than sampling means the bound is checked against
    dependence structures no simulation would draw -- perfectly correlated,
    perfectly anti-correlated and everything between -- which is the only kind
    of counterexample a Frechet bound can have.
    """
    atoms = list(itertools.product(support, repeat=3))
    for u in atoms:
        for v in atoms:
            yield u, v


def test_the_frechet_bounds_hold_for_every_enumerated_joint_without_a_residual():
    """X = U + V exactly. Both bounds must hold for EVERY dependence."""
    support = (0, 1, 2)
    for nu, nv in itertools.product((0, 1), repeat=2):
        big_n = nu + nv
        for u, v in _joint_grid(support):
            p_u = sum(1 for x in u if x > nu) / 3.0
            p_v = sum(1 for x in v if x > nv) / 3.0
            p_x = sum(1 for a, b in zip(u, v) if a + b > big_n) / 3.0
            assert p_x <= p_u + p_v + 1e-12
            assert p_x >= p_u + p_v - 1.0 - 1e-12


def test_an_unquoted_residual_breaks_the_UPPER_bound_and_spares_the_LOWER():
    """The asymmetry the runner's --allow-upper-frechet flag exists for.

    U and V are the two quoted halves; W is overtime, non-negative and unpriced.
    Everyone clears zero on W alone, so the whole is over its line while neither
    part is over its own -- the upper bound is false. The lower bound only ever
    said 'both parts over implies the whole over', which W cannot disturb.
    """
    u = v = (0, 0, 0)
    w = (10, 10, 10)
    nu = nv = 0.0
    big_n = nu + nv
    p_u = sum(1 for x in u if x > nu) / 3.0
    p_v = sum(1 for x in v if x > nv) / 3.0
    p_x = sum(1 for a, b, c in zip(u, v, w) if a + b + c > big_n) / 3.0
    assert p_x > p_u + p_v, "upper bound is NOT implied once a residual exists"
    assert p_x >= p_u + p_v - 1.0, "lower bound survives the residual"


# --------------------------------------------------------------------------- #
# 4. the generators, and the coverage claim that goes in the doc
# --------------------------------------------------------------------------- #

def test_containment_has_almost_no_coverage_at_the_venues_real_lines():
    """The relation P(1H Over n) <= P(FG Over n) is EXACT and nearly useless:
    half lines sit near half the full-game line, so the `whole line <= segment
    line` condition is met by no listed pair. Pinned because the doc claims it
    and a reader is entitled to see it fail."""
    half_lines = [20.5, 24.5, 27.5]
    full_lines = [44.5, 48.5, 52.5]
    assert families.containment_pairs(half_lines, full_lines) == []
    assert families.containment_pairs([50.5], full_lines) == [
        (50.5, 44.5), (50.5, 48.5)]


def test_an_exact_split_licenses_both_bounds_and_a_strict_one_licenses_one():
    both = families.frechet_splits([45.0], [[20.5], [24.5]])
    assert sorted(w for _, _, w in both) == ["frechet_lower", "frechet_upper"]
    only_upper = families.frechet_splits([48.5], [[20.5], [24.5]])
    assert [w for _, _, w in only_upper] == ["frechet_upper"]
    only_lower = families.frechet_splits([40.5], [[20.5], [24.5]])
    assert [w for _, _, w in only_lower] == ["frechet_lower"]


def test_every_scanned_relation_is_exact_and_the_expected_ones_are_named():
    """Nothing merely EXPECTED may be scanned: a violation of a modelled
    relation has a loss state, which is the opposite of the claim."""
    exact = {k for k, (_, ok, _) in families.RELATIONS.items() if ok}
    assert "segment_spread_in_whole" not in exact
    assert "quarter_additivity_of_price" not in exact
    assert {"totals_ladder", "frechet_upper", "frechet_lower"} <= exact


# --------------------------------------------------------------------------- #
# 5. the double-count one level up, and the caller
# --------------------------------------------------------------------------- #

def test_best_per_game_must_be_taken_JOINTLY_across_relations():
    """One mispriced total rung contradicts its own ladder AND every Frechet
    split it appears in. Those baskets share a leg and compete for the same
    depth, so per-relation totals may not be added -- the same defect that
    overstated CFB 2.5x one level down (STATUS 0bi)."""
    ladder = families.Basket("g", "totals_ladder", (), 0.03, 100.0)
    basket = families.Basket("g", "frechet_upper", (), 0.02, 100.0)
    per_relation = (sum(scan.best_per_game([ladder]).values())
                    + sum(scan.best_per_game([basket]).values()))
    joint = sum(scan.best_per_game([ladder, basket]).values())
    assert joint == 3.0
    assert per_relation == 5.0, "adding per-relation totals double-counts"


def test_the_module_has_a_caller_and_places_nothing():
    src = (ROOT / "core" / "ladder" / "families.py").read_text(encoding="utf-8")
    for bad in ("PolymarketGateway", "requests.post", "MERIDIAN_ORDER_TOKEN",
                "DATABASE_URL"):
        assert bad not in src
    outside = [p for p in ROOT.rglob("*.py")
               if "core/ladder" not in str(p) and not p.name.startswith("test_")]
    callers = [p for p in outside
               if "families" in p.read_text(encoding="utf-8", errors="ignore")
               and "core.ladder" in p.read_text(encoding="utf-8", errors="ignore")]
    assert callers, "core.ladder.families has no caller outside its own package"


def test_the_runner_reports_rather_than_crashing_and_defaults_to_inplay():
    run = ROOT / "cfb" / "run_family_scan.py"
    r = subprocess.run([sys.executable, str(run), "--help"],
                       capture_output=True, text=True)
    assert r.returncode == 0 and "--census" in r.stdout
    src = run.read_text(encoding="utf-8")
    assert 'ap.add_argument("--phase", default="inplay"' in src
    assert "board[(gid, ts)]" in src, "legs must come from ONE sweep"
    assert src.count("SELECT max(quantity)") == 2


# --------------------------------------------------------------------------- #
# 6. the venue's line grid, and the two relations it leaves with no denominator
# --------------------------------------------------------------------------- #

VENUE_TOTALS = [41.5, 45.5, 48.5, 52.5]
VENUE_SPREADS = [-10.5, -3.5, -0.5, 0.5, 3.5, 10.5]
VENUE_HALVES = [20.5, 24.5, 27.5]


def _families_module_lines():
    return {"tot": VENUE_TOTALS, "spr": VENUE_SPREADS, "win": [0.0],
            "h1": VENUE_HALVES, "h2": VENUE_HALVES}


def test_every_line_this_repo_has_ever_recorded_is_a_half_point():
    """The premise the next two tests rest on, measured rather than assumed.

    Grep the whole tree for rung slugs and check the decimal. If the venue ever
    starts quoting an integer line this fails, and it SHOULD -- the vacuity of
    the winner identity and the unreachability of the exact Frechet split are
    both consequences of the grid, not facts about the relations.
    """
    slugs = set()
    for path in ROOT.rglob("*"):
        if path.is_dir() or path.suffix not in (".py", ".md", ".csv", ".out"):
            continue
        # Anchored on the slug's date so a Python identifier that happens to end
        # `pt2` cannot enter the census; a rung slug always carries one.
        for m in re.finditer(
                r"\d{4}-\d{2}-\d{2}-[a-z-]*?(\d+)pt(\d)\b",
                path.read_text(encoding="utf-8", errors="ignore")):
            slugs.add((m.group(1), m.group(2)))
    assert slugs, "no rung slugs found in the tree -- the premise is unmeasured"
    decimals = {d for _, d in slugs}
    assert decimals == {"5"}, f"an integer or non-half line appeared: {decimals}"


def test_the_winner_identity_has_no_denominator_on_a_half_point_grid():
    """Candidate (b) is EXACT and VACUOUS. The moneyline is the spread at line
    0 and the venue lists no 0.0 spread rung, so there is no second price to
    disagree with it. A scan reporting "0 violations" here is reporting that it
    had nothing to scan."""
    cov = families.coverage(_families_module_lines(),
                            totals="tot", spread="spr", winner="win")
    assert cov["winner_is_line_zero"] == 0
    # ... and the relation is not broken, only unreachable: put a 0.0 rung on
    # the board and both directions become scannable.
    with_zero = dict(_families_module_lines(), spr=VENUE_SPREADS + [0.0])
    cov2 = families.coverage(with_zero, totals="tot", spread="spr", winner="win")
    assert cov2["winner_is_line_zero"] == 2


def test_an_exact_frechet_split_cannot_occur_on_the_venues_real_lines():
    """Two half-point part lines sum to an INTEGER; the whole is a half-point.
    So `sum(parts) == N` never holds and every split is strict one way.

    `test_an_exact_split_licenses_both_bounds_and_a_strict_one_licenses_one`
    exercises the equality branch at whole=45.0, which is a line this venue has
    never quoted. That test pins the arithmetic; this one pins that the branch
    is unreachable from the board, so nobody reads its coverage as real.
    """
    splits = families.frechet_splits(VENUE_TOTALS, [VENUE_HALVES, VENUE_HALVES])
    both = [(n, c) for n, c, _ in splits
            if sum(c) == n]
    assert both == [], f"an exact split appeared on a half-point grid: {both}"
    # Coverage is nonetheless ample in each single direction -- unlike (b),
    # this relation has a denominator.
    cov = families.coverage(_families_module_lines(), totals="tot", spread="spr",
                            winner="win", segments=[("h1", "h2", "tot")])
    assert cov["frechet_upper:tot"] > 0 and cov["frechet_lower:tot"] > 0


def test_coverage_separates_a_clean_board_from_an_unscannable_one():
    """The whole point of the denominator: containment (c) and the winner
    identity (b) both print zero violations, and only one of them was scanned."""
    cov = families.coverage(_families_module_lines(), totals="tot", spread="spr",
                            winner="win", segments=[("h1", "h2", "tot")])
    assert cov["segment_in_whole:tot"] == 0, "half lines sit under full lines"
    assert cov["totals_ladder"] == len(VENUE_TOTALS) * (len(VENUE_TOTALS) - 1) // 2


def test_a_spread_slugs_sign_token_survives_the_runners_fallback_parse():
    """The recorded `line` column is preferred, but when it is NULL the slug is
    parsed -- and `neg-10pt5` and `pos-10pt5` are both listed for the same game.
    A parse that drops the token maps both to +10.5, collides them on one dict
    key and prices a rung as its own mirror image."""
    sys.path.insert(0, str(ROOT / "cfb"))
    import run_family_scan as runner

    assert runner.line_of("asc-cfb-akron-wake-2026-09-03-neg-10pt5", None) == -10.5
    assert runner.line_of("asc-cfb-akron-wake-2026-09-03-pos-10pt5", None) == 10.5
    assert runner.line_of("tsc-cfb-akron-wake-2026-09-03-total-29pt5", None) == 29.5
    # the recorded column still wins, sign and all
    assert runner.line_of("asc-cfb-akron-wake-2026-09-03-neg-10pt5", -10.5) == -10.5


# --------------------------------------------------------------------------- #
# 7. the archived measurement, which is the only one that has actually been run
# --------------------------------------------------------------------------- #

def _archive():
    sys.path.insert(0, str(ROOT / "cfb"))
    import run_family_scan_archive as arch
    return arch, arch.load(str(ROOT / arch.DEFAULT))


def test_the_archive_dump_parses_into_the_families_the_doc_reports_on():
    """The obs counts in docs/math/consistency-families.md, pinned. If the file
    is re-cut or the CSV gains a column these move, and the doc is then stale
    rather than quietly wrong."""
    _, board = _archive()
    assert len(board) == 62, "60 CFB + 2 NFL settled games"
    rungs = sum(len(v) for f in board.values() for v in f.values())
    assert rungs == 4456
    fams = {k.split("|")[0] for f in board.values() for k in f}
    assert fams == {"winner", "spread", "total", "team_tot"}
    # (c) and (e) are NOT measurable here and the doc says so: no segment totals
    assert not any(k.startswith("football_game_") for k in fams)


def test_the_shipped_scanner_and_hand_arithmetic_agree_on_every_archived_pair():
    """A duplicate measurement, not a review. `two_leg` prices each pair twice
    -- once through `families.dominance` and once by writing the fee-netted
    edge out longhand -- and the runner prints `!!` when they disagree. This
    asserts they never do, which is what licenses quoting either."""
    arch, board = _archive()
    for family, higher_is_subset in (("total", True), ("spread", False)):
        recs = arch.two_leg(board, family, higher_is_subset, "r")
        assert recs, f"no {family} pairs parsed"
        scanner = sum(1 for x in recs if x[2] is not None)
        hand = sum(1 for x in recs
                   if 0.0 < x[3] <= scan.MAX_PLAUSIBLE_EDGE)
        assert scanner == hand, f"{family}: scanner {scanner} vs hand {hand}"


def test_the_totals_ladder_is_measurably_cleaner_than_the_spread_control():
    """The headline of (a), and the reason the control is in the runner.

    Same games, same instrument, same fee, same pregame close. If the spread
    control also came back clean the totals zero would say nothing -- it would
    be an instrument that cannot detect disorder. It is not: the spread ladder
    shows more than twice the pair-weighted disorder on the same board.
    """
    arch, board = _archive()
    tot = arch.two_leg(board, "total", True, "r")
    spr = arch.two_leg(board, "spread", False, "r")
    tot_ordered = sum(x[5] for x in tot) / len(tot)
    spr_ordered = sum(x[5] for x in spr) / len(spr)
    assert tot_ordered > spr_ordered, "the control must be the dirtier board"
    assert tot_ordered > 0.99 and spr_ordered < 0.98


def test_the_frechet_bounds_are_mostly_VACUOUS_on_the_real_board():
    """Why (d) returns zero, and why that zero is NOT evidence of a tight board.

    A dependence-free bound is wide. On roughly three quarters of the archived
    splits it is implied by `0 <= P <= 1` alone and observes nothing about the
    prices at all; even where it does bind, the board never comes within 20c of
    it against a three-leg fee near 4.5c. Zero violations here means the bound
    is slack, not that the market is exact.
    """
    arch, board = _archive()
    up, low = arch.three_leg(board)
    for name, recs in (("upper", up), ("lower", low)):
        assert recs, f"no {name} splits"
        binding = sum(x[5] for x in recs) / len(recs)
        assert 0.15 < binding < 0.45, f"{name} non-vacuous share {binding:.2%}"
        assert max(x[3] for x in recs) < -0.15, (
            f"{name}: board came within 15c of a Frechet bound")
    assert 3 * scan.fee(0.5) < 0.05, "three-leg fee near 4.5c at even money"
