"""The harness's own controls: every check watched to FAIL on demand.

A validation harness nobody has seen reject anything is the defect it exists
to prevent. Three shipped in this repo today — two of them mine — so each
check here has an adversarial model that MUST trip it, and an honest model
that must not.

If you add a check to model_harness.run_all, add its adversary here. A check
with no adversary is a check that has never been observed working.
"""

from __future__ import annotations

import pytest

from model_harness import (
    INJECTED_EDGE,
    NoiseModel,
    LeakyModel,
    MarketOnly,
    MidCopier,
    Oracle,
    Row,
    SignFlipped,
    correlation,
    make_slate,
    run_all,
    skill_beyond_market,
    split_by_game,
)


# ------------------------------------------------------------------ #
# The generator does what it claims
# ------------------------------------------------------------------ #


def test_the_null_slate_really_has_no_edge():
    """If the generator leaks signal into the null, every null test below is
    vacuous — it would pass models that deserve to fail."""
    rows = make_slate(edge=0.0)
    cm = skill_beyond_market(rows, [r.truth for r in rows])
    assert cm is not None
    assert abs(cm.mean) < 0.01, (
        f"an ORACLE scores {cm.mean:+.5f} against the market on data where "
        "the market is already the truth — the null is not null")


def test_the_injected_slate_really_carries_the_edge():
    rows = make_slate(edge=INJECTED_EDGE)
    cm = skill_beyond_market(rows, [r.truth for r in rows])
    assert cm.mean > 0.01, (
        f"planted {INJECTED_EDGE} and an ORACLE recovers only {cm.mean:+.5f} "
        "— the injected slate cannot detect a working pipeline")


def test_the_split_holds_out_whole_games():
    tr, te = split_by_game(make_slate())
    assert tr and te
    assert not ({r.game_id for r in tr} & {r.game_id for r in te})


# ------------------------------------------------------------------ #
# Honest models pass
# ------------------------------------------------------------------ #


def test_the_oracle_is_accepted():
    """The one model that should pass everything: it recovers the truth, so it
    is null on null data, recovers the injected edge, inverts under a sign
    flip, and its predictions are NOT the mid."""
    rep = run_all(Oracle)
    assert rep.ok, f"Oracle rejected: {rep.failures}"


def test_the_market_itself_is_REJECTED_and_that_is_correct():
    """MarketOnly outputs the mid exactly, so it is indistinguishable from the
    market by construction — which is precisely what the echo check exists to
    refuse. It is the limiting case of MidCopier, not an honest model, and its
    rejection is the proof the check works at the boundary.

    Stated because it looks like a false positive and is not: a submitted
    model that behaves identically to the market has told us nothing, however
    honestly it was built."""
    rep = run_all(MarketOnly)
    assert not rep.ok
    assert "MID_ECHO" in rep.codes, rep.failures


# ------------------------------------------------------------------ #
# Each adversary trips its own check — the part that matters
# ------------------------------------------------------------------ #


def test_the_mid_copier_is_caught():
    """★ The failure this harness exists for. A model that echoes its own
    market input ties the market and looks like an honest null result."""
    rep = run_all(MidCopier)
    assert not rep.ok
    assert "MID_ECHO" in rep.codes, rep.failures


def test_the_mid_copier_would_pass_a_naive_score():
    """Why the echo check is needed at all: by the headline number alone, the
    copier is indistinguishable from an honest model that found nothing."""
    rows = make_slate(edge=0.0)
    _, te = split_by_game(rows)
    m = MidCopier()
    cm = skill_beyond_market(te, m.predict(te))
    assert abs(cm.mean) < 0.005, (
        "the copier should tie the market — that is the whole problem")
    assert correlation(list(m.predict(te)), [r.mid for r in te]) > 0.99


def test_the_sign_flipped_model_is_caught():
    """Asserted on INJECTED specifically. A first draft asserted
    `"SIGN" in f or "INJECTED" in f`, and that `or` meant NEITHER check was
    individually pinned: disabling either one left the other firing and the
    test still passed. Found by disabling each check in turn — three of five
    had no control at all."""
    rep = run_all(SignFlipped)
    assert not rep.ok
    assert "INJECTED" in rep.codes, rep.failures


def test_a_model_that_recovers_nothing_is_caught():
    """Pins INJECTED on its own: noise is decorrelated from the mid, so the
    echo check stays silent and only the injected-effect check can fire."""
    rep = run_all(NoiseModel)
    assert not rep.ok
    assert "INJECTED" in rep.codes, rep.failures
    assert not "MID_ECHO" in rep.codes, rep.failures


def test_a_sign_blind_scorer_is_caught():
    """SIGN guards the SCORER, not the model — no model can both recover an
    edge and be indifferent to inversion. So its control mutates the scorer:
    make skill direction-blind and the check must fire."""
    import model_harness as mh

    real = mh.skill_beyond_market

    def sign_blind(rows, preds):
        cm = real(rows, preds)
        return type(cm)(mean=abs(cm.mean), lo=abs(cm.lo), hi=abs(cm.hi),
                        n=cm.n, n_clusters=cm.n_clusters, stderr=cm.stderr)

    mh.skill_beyond_market = sign_blind
    try:
        rep = run_all(Oracle)
    finally:
        mh.skill_beyond_market = real
    assert "SIGN" in rep.codes, rep.failures


def test_the_leaky_model_is_caught():
    """Reads a feature summarised after the decision. Scores impossibly well
    on data with no signal, which is the tell."""
    rep = run_all(LeakyModel)
    assert not rep.ok
    assert "LEAKAGE" in rep.codes, rep.failures
    # It also claims skill on data that has none, which is what pins the NULL
    # check — nothing else in this file did.
    assert "NULL" in rep.codes, rep.failures


def test_a_row_split_would_be_caught():
    """The split check must fire when a game lands on both sides."""
    from model_harness import Failure as mh_Failure, Report

    rows = make_slate(n_games=4, per_game=10)
    tr, te = rows[:20], rows[10:]        # deliberate overlap
    overlap = {r.game_id for r in tr} & {r.game_id for r in te}
    assert overlap, "this fixture must overlap or it tests nothing"
    rep = Report()
    if overlap:
        rep.failures.append(mh_Failure("SPLIT", f"{len(overlap)} games"))
    assert not rep.ok


# ------------------------------------------------------------------ #
# The scoring convention, pinned
# ------------------------------------------------------------------ #


def test_positive_skill_means_the_model_beat_the_market():
    """Stated once in skill_beyond_market's docstring; asserted here so it
    cannot drift. Every sign defect in this repo began as a convention that
    lived only in prose."""
    # Several games: clustered_mean needs >= 2 clusters for an interval and
    # returns None with one, which a first draft of this test tripped over.
    rows = [Row(game_id=f"g{i % 8}", t=i, mid=0.5, truth=0.9, outcome=1)
            for i in range(40)]
    better = skill_beyond_market(rows, [0.9] * 40)
    worse = skill_beyond_market(rows, [0.1] * 40)
    assert better.mean > 0 > worse.mean
