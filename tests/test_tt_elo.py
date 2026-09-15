"""The table-tennis Elo harness: its controls, before it has a sample.

Zero matches are eligible today — the busiest player has 9 priors against a
floor of 10 — so every test here has to work on a sample that cannot produce a
result. A harness that only works once the data is sufficient is a harness
debugged on the day it matters.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pytest

from core.tt import elo, rule
from core.tt.fit import fit, shuffle_within_price_bucket

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 9, 14, 12, 0, tzinfo=UTC)


def _m(p1, p2, y, i, comp="setkameua", price=None):
    return elo.Match(f"aec-{comp}-{p1}-{p2}-2026-09-14", comp, p1, p2, y,
                     T0 + dt.timedelta(minutes=i), price)


# ----------------------------------------------------- tokens and identity #

def test_a_fixed_width_parser_would_lose_a_player():
    """★ `mars` is 4 characters and `demciva` is 7, against 704 six-character
    appearances. Slicing at six loses one and mangles the other, which is why
    the parser splits on `-` and counts. Pinned rather than tidied: the
    4-character token is the case a naive implementation breaks on.
    """
    got = elo.parse_slug("aec-setkameua-mars-kolole-2026-09-14")
    assert got == ("setkameua", "mars", "kolole")
    assert elo.parse_slug("aec-setkameua-cheart-demciva-2026-09-14") == (
        "setkameua", "cheart", "demciva")

    # What a fixed-width implementation would have produced instead:
    assert "mars"[:6] == "mars"          # survives by luck
    assert "demciva"[:6] == "demciv"     # a token the venue never emitted
    assert "demciv" != "demciva", (
        "truncating to six characters invents a token that could collide with "
        "a real player")


def test_a_slug_that_does_not_yield_two_tokens_returns_none_rather_than_a_guess():
    assert elo.parse_slug("aec-setkameua-onlyone-2026-09-14") is None
    assert elo.parse_slug("aec-setkameua-a-b-c-2026-09-14") is None
    assert elo.parse_slug("aec-setkameua-a-b-not-a-date") is None


def test_identity_is_competition_plus_token_so_a_shared_name_is_two_players():
    """The registered rule ("prior matches in the same competition", "a name in
    two competitions is two entities") implemented as ONE decision, so no code
    path can hold the two definitions apart."""
    ms = [_m("shared", f"o{i}", 1, i, comp="setkameua") for i in range(12)]
    ms += [_m("shared", f"p{i}", 1, 100 + i, comp="setkamecz") for i in range(12)]
    preds = elo.replay(ms)
    # 'shared' accrues separately in each competition, so neither side of the
    # 13th match in either competition can be eligible off the other's history.
    ua = [p for p in preds if p.competition == "setkameua"]
    cz = [p for p in preds if p.competition == "setkamecz"]
    assert ua[-1].prior_p1 == 11 and cz[-1].prior_p1 == 11, (
        "one competition's history leaked into the other's prior count")


def test_a_token_in_two_competitions_is_reported_loudly():
    """0 of 180 today, so the two definitions are indistinguishable now and
    diverge silently the first time one is not. A NOTICE, not a crash."""
    clean = [_m("aaa", "bbb", 1, 0), _m("ccc", "ddd", 0, 1)]
    assert elo.cross_competition_tokens(clean) == {}
    dirty = clean + [_m("aaa", "eee", 1, 2, comp="setkamecz")]
    assert elo.cross_competition_tokens(dirty) == {
        "aaa": ["setkamecz", "setkameua"]}


# ------------------------------------------------------------ the updater #

def test_the_update_is_zero_sum():
    """Whatever the winner gains the loser loses. An updater that is not
    zero-sum drifts the whole pool and every rating with it."""
    a, b = elo.update(1500.0, 1500.0, 1)
    assert a + b == pytest.approx(3000.0)
    assert a > 1500.0 > b
    c, d = elo.update(1700.0, 1300.0, 0)
    assert c + d == pytest.approx(3000.0)
    # The favourite losing costs it rating and pays the underdog the same
    # amount. It does NOT leapfrog: K=24 cannot close a 400-point gap, and the
    # first version of this assertion demanded exactly that.
    assert c < 1700.0 and d > 1300.0
    assert (1700.0 - c) == pytest.approx(d - 1300.0)


def test_an_upset_moves_more_than_an_expected_result():
    fav_win, _ = elo.update(1700.0, 1300.0, 1)
    dog_win, _ = elo.update(1300.0, 1700.0, 1)
    assert (dog_win - 1300.0) > (fav_win - 1700.0) * 3


# --------------------------------------------------- the replay, today's shape #

def test_the_replay_produces_zero_eligible_matches_without_crashing():
    """★ TODAY. Nobody has 10 priors (the busiest player has 9), so the harness
    must run to completion and return an empty eligible set rather than raise,
    divide by zero or quietly filter."""
    ms = [_m(f"a{i}", f"b{i}", i % 2, i) for i in range(9)]
    preds = elo.replay(ms)
    assert len(preds) == 9, "matches went missing instead of being counted"
    assert not any(p.eligible for p in preds)
    assert all("prior" in p.reason for p in preds)


def test_a_match_with_no_start_time_is_refused_and_counted():
    """Ordering is the venue's start instant, not the slug's date, because 94%
    of the settled set falls on one day. A match that cannot be ordered is
    refused with a reason — never silently sorted last."""
    ms = [_m("a", "b", 1, 0),
          elo.Match("aec-setkameua-c-d-2026-09-14", "setkameua", "c", "d", 1,
                    None, None)]
    preds = elo.replay(ms)
    assert len(preds) == 2
    bad = [p for p in preds if not p.eligible and "game_start_time" in p.reason]
    assert len(bad) == 1


def test_a_match_never_informs_its_own_prediction():
    """Predict, then update. If the update came first the fitter would see the
    outcome it is predicting."""
    ms = [_m("a", "b", 1, i) for i in range(3)]
    preds = elo.replay(ms, min_prior=0)
    assert preds[0].elo_p == pytest.approx(0.5), (
        "the first match was predicted from a rating its own result had "
        "already moved")
    assert preds[1].elo_p > 0.5


# ------------------------------------------- the positive control and the null #

def _synthetic(n_players=40, n_matches=1200, seed=7, spread=250.0,
               price_noise=120.0):
    """Matches generated FROM known ratings, with a price that is INFORMATIVE
    but degraded.

    The price has to vary or the design matrix is singular — a constant price
    gives `logit_price` an all-zero column, which is how the first version of
    this control failed. It also has to carry real information, or the
    calibration check on the null becomes vacuous: preserving a flat curve
    proves nothing. So the price is the venue's view of the same two players
    seen through rating noise, and Elo's job is to beat it.
    """
    rng = np.random.default_rng(seed)
    true = {f"p{i}": 1500.0 + spread * rng.standard_normal()
            for i in range(n_players)}
    names = list(true)
    ms = []
    for i in range(n_matches):
        a, b = rng.choice(names, size=2, replace=False)
        p = elo.expected(true[a], true[b])
        y = int(rng.random() < p)
        price = elo.expected(true[a] + price_noise * rng.standard_normal(),
                             true[b] + price_noise * rng.standard_normal())
        ms.append(elo.Match(f"aec-setkameua-{a}-{b}-2026-09-14", "setkameua",
                            a, b, y, T0 + dt.timedelta(seconds=i),
                            float(np.clip(price, 0.02, 0.98))))
    return true, ms


def test_the_positive_control_fires_the_fitter_recovers_known_ratings():
    """★ MUST FIRE. Matches simulated from known ratings; the Elo coefficient
    has to be positive and its interval exclude zero. A fitter that cannot
    recover a signal it was handed cannot be trusted to report its absence."""
    true, ms = _synthetic()
    preds = [p for p in elo.replay(ms) if p.eligible]
    assert len(preds) > 400, f"only {len(preds)} eligible in the control"

    f = fit([p.price_yes for p in preds], [p.elo_p for p in preds],
            [p.y for p in preds], [p.p1 for p in preds], [p.p2 for p in preds])
    assert f.converged
    assert f.beta[2] > 0.3, f"Elo coefficient {f.beta[2]:.3f} did not recover"
    assert f.excludes_zero(2, "game"), "the control's interval included zero"

    # And the ratings themselves correlate with the truth they came from.
    got = elo.ratings_after(ms)
    xs = [true[t] for (_, t) in got]
    ys = [got[(c, t)] for (c, t) in got]
    assert np.corrcoef(xs, ys)[0, 1] > 0.8


def test_the_null_kills_the_elo_coefficient():
    """★ Shuffle outcomes WITHIN a narrow price bucket: the link to the rating
    is severed, so the coefficient must die."""
    _, ms = _synthetic()
    preds = [p for p in elo.replay(ms) if p.eligible]
    rng = np.random.default_rng(11)
    price = [p.price_yes for p in preds]
    y_null = shuffle_within_price_bucket(price, [p.y for p in preds], rng)

    f = fit(price, [p.elo_p for p in preds], y_null,
            [p.p1 for p in preds], [p.p2 for p in preds])
    assert not f.excludes_zero(2, "game"), (
        f"the null still shows an Elo coefficient {f.beta[2]:.3f} — the "
        "permutation is not removing what the primary test measures")


def test_the_null_does_not_destroy_price_calibration():
    """★ THE CHECK ON THE NULL ITSELF. Per `a-null-can-remove-the-wrong-thing`,
    a permutation that destroys PRICE CALIBRATION manufactures an artifact
    instead of removing one — that is how a previous null produced +8c per
    contract of pure fiction. Shuffling inside a price bucket must leave
    realized-vs-price essentially unchanged.
    """
    _, ms = _synthetic()
    preds = [p for p in elo.replay(ms) if p.eligible]
    rng = np.random.default_rng(3)
    price = np.array([p.price_yes for p in preds])
    y = np.array([p.y for p in preds], dtype=float)
    y_null = shuffle_within_price_bucket(price, y, rng)

    assert y_null.sum() == pytest.approx(y.sum()), "the null changed the base rate"
    # Within every bucket the realized rate is invariant by construction; the
    # assertion is that the SHAPE survives, bucket by bucket.
    for lo in (0.0, 0.25, 0.5, 0.75):
        m = (price >= lo) & (price < lo + 0.25)
        if m.sum() > 10:
            assert y[m].mean() == pytest.approx(y_null[m].mean(), abs=1e-9), (
                "the null moved the realized-vs-price curve, so it is "
                "removing calibration rather than the rating signal")


def test_a_large_coefficient_with_no_design_effect_is_visible_as_such():
    """The defect signature, made reportable. deff and G_eff come off the same
    Fit, so a player-linked effect that shows no clustering cannot be quoted
    without the number that contradicts it."""
    _, ms = _synthetic()
    preds = [p for p in elo.replay(ms) if p.eligible]
    f = fit([p.price_yes for p in preds], [p.elo_p for p in preds],
            [p.y for p in preds], [p.p1 for p in preds], [p.p2 for p in preds])
    d, ge = f.deff(2), f.g_eff(2)
    assert d == d and ge == ge, "deff/G_eff not computable"
    assert ge <= f.n, "effective sample larger than the match count"


# ------------------------------------------------- the rule and its image #

def test_the_rule_returns_not_yet_today_and_not_yet_is_not_a_fail():
    v, why = rule.verdict(predicted=0, players=113, interval_excludes_zero=False)
    assert v == rule.NOT_YET and "0 predicted" in why


def test_both_branches_of_the_rule_are_reachable_on_three_competitions():
    assert rule.reachable(max_predicted=5000, max_players=113) == {
        rule.PASS, rule.FAIL, rule.NOT_YET}
    assert rule.verdict(predicted=250, players=113,
                        interval_excludes_zero=True)[0] == rule.PASS
    assert rule.verdict(predicted=250, players=113,
                        interval_excludes_zero=False)[0] == rule.FAIL


def test_setkawoua_can_never_return_pass_or_fail():
    """★ Its whole pool is 6 players against a >=25 floor, so NOT YET is its
    only reachable branch — permanently. Stated now rather than discovered as
    a mysterious silence, and a reason to report it separately instead of
    letting it sit in a table of four looking pending."""
    assert rule.reachable(max_predicted=10_000, max_players=6) == {rule.NOT_YET}


def test_the_nulls_price_coefficient_RISES_and_that_is_collinearity_not_damage():
    """★ The thing that would otherwise look like the null removing the wrong
    thing. Under the null the fitted price coefficient roughly DOUBLES
    (+0.31 -> +0.68 on the control), which reads like calibration being
    disturbed. It is not: the bucket-wise realized-vs-price curve is preserved
    exactly (the test above), and the coefficient moves because price and Elo
    are correlated views of the same ratings — with Elo dead, price collects
    the shared variance it was previously splitting.

    Asserted as a DIRECTION so the reallocation is a checked prediction rather
    than an unexplained surprise the next reader has to talk themselves out of.
    """
    _, ms = _synthetic()
    preds = [p for p in elo.replay(ms) if p.eligible]
    price = [p.price_yes for p in preds]
    args = ([p.p1 for p in preds], [p.p2 for p in preds])

    real = fit(price, [p.elo_p for p in preds], [p.y for p in preds], *args)
    rng = np.random.default_rng(11)
    y_null = shuffle_within_price_bucket(price, [p.y for p in preds], rng)
    null = fit(price, [p.elo_p for p in preds], y_null, *args)

    assert null.beta[1] > real.beta[1], (
        "the price coefficient did not rise when its competing regressor went "
        "dead — check the null is severing Elo and not price")
    assert not null.excludes_zero(2), "the null left an Elo coefficient"


def test_a_small_design_effect_is_not_by_itself_a_defect_signature():
    """★ A CORRECTION TO MY OWN RULE, found by running it on the control.

    I wrote that "a large Elo coefficient with a small design effect is a
    defect signature". On the positive control the coefficient is +1.09 and
    deff is 1.17 — and there the effect is REAL by construction. So the
    heuristic as stated flags its own positive control.

    What deff actually tracks is the IMBALANCE of appearances: with random,
    balanced pairing the player clusters do not concentrate the residuals, so
    deff sits near 1 whether or not the effect is real. The appearance
    distribution has to be reported next to deff, and deff alone must not be
    read as a verdict input.
    """
    _, ms = _synthetic()
    preds = [p for p in elo.replay(ms) if p.eligible]
    f = fit([p.price_yes for p in preds], [p.elo_p for p in preds],
            [p.y for p in preds], [p.p1 for p in preds], [p.p2 for p in preds])

    counts: dict[str, int] = {}
    for p in preds:
        counts[p.p1] = counts.get(p.p1, 0) + 1
        counts[p.p2] = counts.get(p.p2, 0) + 1
    lo, hi = min(counts.values()), max(counts.values())

    assert f.beta[2] > 0.3 and f.deff(2) < 2.0, (
        "the control no longer exhibits the large-coefficient/small-deff "
        "combination this test exists to characterise")
    assert hi / lo < 3.0, (
        "the control's pairing is no longer balanced, so its small deff no "
        "longer demonstrates that balance and not absence-of-effect is what "
        "produces one")
