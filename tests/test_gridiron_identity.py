"""The spread-sited identity. Zero fitted parameters given sigma."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

from core.gridiron.identity import (espn_margin_delta, identity_cover_probability,
                                    identity_z, kickoff_wp, ladder_fit_quality)
from core.gridiron.scale import MarginScale

SCALE = MarginScale(13.19, 0.1182, line_range=(7.9, 49.7), n_games=14, corr=0.948)


def test_the_update_does_not_involve_sigma():
    """The property that chose margin space over logit space."""
    d = espn_margin_delta(0.83, 0.62)
    for sigma in (10.0, 15.65, 25.0):
        s = MarginScale(sigma, 0.0, line_range=(0, 60), n_games=9, corr=0.0)
        z = identity_z(-14.0, 18.0, 0.83, 0.62, s)
        assert z - (18.0 - 14.0) / sigma == pytest.approx(d)


def test_no_news_leaves_the_anchor_untouched():
    """WP unchanged since kickoff must reprice nothing."""
    z = identity_z(-18.0, 18.0, 0.62, 0.62, SCALE)
    assert z == pytest.approx(0.0)
    assert identity_cover_probability(-18.0, 18.0, 0.62, 0.62, SCALE) == pytest.approx(0.5)


def test_good_news_moves_the_whole_ladder_the_same_way():
    lines = np.array([-24.0, -20.0, -16.0, -12.0])
    flat = identity_cover_probability(lines, 18.0, 0.62, 0.62, SCALE)
    good = identity_cover_probability(lines, 18.0, 0.85, 0.62, SCALE)
    assert np.all(good > flat)
    assert np.all(np.diff(good) > 0)          # still monotone in the line


def test_the_frame_is_pinned_z_rises_with_the_handicap():
    """`L` is ADDED to the margin. A ladder that falls with L is inverted."""
    z = identity_z(np.array([-30.0, -20.0, -10.0]), 18.0, 0.7, 0.6, SCALE)
    assert z[0] < z[1] < z[2]


@pytest.mark.parametrize("line", [-30.0, -24.0, -12.0, -6.0])
def test_a_pregame_sigma_underweights_the_anchor_on_both_wings(line):
    """The signed direction of assumption 1, and NOT the obvious one.

    A too-large sigma shrinks the anchor term only -- the update is sigma-free
    -- so z moves TOWARD the pure-update value on every rung. It does not move
    toward 0.5: `mu_anchor + L` changes sign across the crossing, so a
    toward-0.5 claim is wrong on one wing. This test failed the first version
    of that claim, which is why the docstring says what it says.
    """
    pure = espn_margin_delta(0.85, 0.62)
    live = identity_z(line, 18.0, 0.85, 0.62, SCALE, sigma_t=11.5)
    preg = identity_z(line, 18.0, 0.85, 0.62, SCALE)
    assert abs(preg - pure) < abs(live - pure)


def test_sigma_has_exactly_zero_effect_at_the_crossing():
    """Why a shape test near the money has no power on sigma, whatever n is.

    At `L = -mu_anchor` the anchor term is 0/sigma = 0 for every sigma, so the
    two agree to the bit. Sensitivity peaks about one sigma out, which is where
    the board is thinnest -- 40.3% of interior rungs sit >=15 points from their
    own crossing and 7.7% sit >=25.
    """
    at = [identity_z(-18.0, 18.0, 0.85, 0.62, SCALE, sigma_t=s)
          for s in (8.0, 11.5, 15.65, 25.0)]
    assert at[0] == at[1] == at[2] == at[3] == pytest.approx(espn_margin_delta(0.85, 0.62))
    # and one sigma out it is emphatically not zero
    out = [identity_z(-18.0 - 15.7, 18.0, 0.85, 0.62, SCALE, sigma_t=s)
           for s in (11.5, 25.0)]
    assert abs(out[0] - out[1]) > 0.5


def test_sigma_t_defaults_to_pregame_so_adding_it_later_changes_nothing():
    a = identity_z(-20.0, 18.0, 0.8, 0.6, SCALE)
    b = identity_z(-20.0, 18.0, 0.8, 0.6, SCALE, sigma_t=SCALE.sigma(18.0))
    assert a == pytest.approx(b)


def _state(rows):
    return pd.DataFrame([
        {"game_id": g, "state": "in", "period": p, "display_clock": c,
         "home_score": h, "away_score": a, "espn_home_win_pct": w,
         "first_seen_at": pd.Timestamp("2026-09-05 23:00:00+00:00")
         + pd.Timedelta(minutes=i)}
        for i, (g, p, c, h, a, w) in enumerate(rows)])


def test_the_kickoff_row_is_gated_on_score_not_on_the_clock():
    """`display_clock` reads 15:00 in period 1 on rows already scoring 21-0, and
    reg_left jumps backwards. Only 0-0 in period 1 is a kickoff."""
    s = _state([
        (1, 1, "15:00", 21, 0, 0.99),      # the liar: clock says kickoff, score does not
        (1, 1, "14:52", 0, 0, 0.55),       # the real one
        (1, 2, "15:00", 0, 0, 0.60),       # period 2, not a kickoff
    ])
    assert kickoff_wp(s).loc[1] == pytest.approx(0.55)


def test_a_game_never_seen_at_0_0_has_no_kickoff_row_rather_than_a_guess():
    s = _state([(2, 2, "5:04", 14, 0, 0.90), (2, 4, "15:00", 49, 3, 0.999)])
    assert 2 not in kickoff_wp(s).index


def _ladder(mu, sigma, lines=range(-34, 3, 2)):
    lines = np.array(list(lines), dtype=float)
    return pd.DataFrame({"line": lines, "mid": norm.cdf((mu + lines) / sigma)})


def test_a_correct_identity_matches_the_venues_own_free_fit():
    sigma = SCALE.sigma(18.0)
    q = ladder_fit_quality(_ladder(18.0, sigma), 18.0, 0.62, 0.62, SCALE)
    assert q["r2_identity"] == pytest.approx(q["r2_venue"], abs=1e-6)
    assert q["rmse_z"] < 1e-9


def test_a_wrong_update_is_caught_by_the_ladder():
    """The falsification. The identity claims a shift the traded ladder denies."""
    sigma = SCALE.sigma(18.0)
    truth = _ladder(18.0, sigma)                       # market says: no news
    q = ladder_fit_quality(truth, 18.0, 0.95, 0.62, SCALE)   # identity says: big news
    assert q["r2_venue"] > 0.999
    assert q["r2_identity"] < 0.9, "a bogus update must degrade the fit"
    assert q["rmse_z"] > 0.5


def test_a_wrong_sigma_shows_up_as_a_slope_error_not_a_shift():
    """Attribution B depends on: sigma moves the ladder's slope."""
    q = ladder_fit_quality(_ladder(18.0, 9.0), 18.0, 0.62, 0.62, SCALE)
    assert q["r2_identity"] < q["r2_venue"]
    assert q["r2_venue"] > 0.999          # the ladder itself is a clean line


def test_true_kickoff_refuses_a_recorder_start():
    """The 09-05 defect: 14 games returned the SAME 'kickoff' minute, because
    that was when the recorder started. Every one was already in progress."""
    from core.gridiron.fit import true_kickoff
    t = pd.Timestamp("2026-09-05 22:08:30+00:00")
    s = pd.DataFrame([
        # three games the recorder first saw in the same minute, all mid-game
        {"game_id": 1, "state": "in", "period": 2, "home_score": 14, "away_score": 0,
         "first_seen_at": t},
        {"game_id": 2, "state": "in", "period": 4, "home_score": 49, "away_score": 3,
         "first_seen_at": t},
        # and one seen from an actual kickoff
        {"game_id": 3, "state": "in", "period": 1, "home_score": 0, "away_score": 0,
         "first_seen_at": t},
    ])
    k = true_kickoff(s)
    assert list(k.index) == [3], "a recorder start is not a kickoff"


def _srow(gid, per, clock, h, a, st="in", t=0):
    return {"game_id": gid, "state": st, "period": per, "display_clock": clock,
            "home_score": h, "away_score": a,
            "first_seen_at": pd.Timestamp("2026-09-05 22:00:00+00:00")
            + pd.Timedelta(minutes=t)}


def test_the_clock_branch_still_carries_a_real_regulation_finish():
    """It supplies 14 of 42 games on the 09-05 tape. Guarding must not kill it."""
    from core.gridiron.fit import outcome_cohort
    s = pd.DataFrame([_srow(1, 1, "15:00", 0, 0, t=0),
                      _srow(1, 4, "0:00", 34, 18, t=180)])
    c = outcome_cohort(s)
    assert list(c.game_id) == [1] and c.margin.iloc[0] == 16


def test_a_p4_zero_clock_row_with_the_game_still_running_is_refused():
    """ESPN reports P4 0:00 on rows that are not final -- on game 401858428 the
    margin went -5 to +1 ACROSS such a row, a sign flip. Today `tail(1)` saves
    us by accident; this makes the predicate itself refuse."""
    from core.gridiron.fit import outcome_cohort
    s = pd.DataFrame([_srow(1, 4, "0:00", 20, 25, t=100),
                      _srow(1, 4, "3:12", 26, 25, t=110),      # still playing
                      _srow(1, 4, "0:00", 26, 25, t=120, st="in")])
    c = outcome_cohort(s)
    # the LAST row is a genuine regulation end, so it qualifies -- with the
    # right margin, not the -5 the earlier liar row carried
    assert c.margin.iloc[0] == 1


def test_a_game_that_went_to_overtime_is_not_settled_at_regulation_end():
    from core.gridiron.fit import outcome_cohort
    s = pd.DataFrame([_srow(1, 4, "0:00", 21, 20, t=100),
                      _srow(1, 5, "0:00", 21, 20, t=110)])
    assert outcome_cohort(s).empty


def test_a_recorder_that_stopped_mid_game_yields_no_outcome():
    from core.gridiron.fit import outcome_cohort
    s = pd.DataFrame([_srow(1, 2, "5:04", 14, 0, t=0)])
    assert outcome_cohort(s).empty


def test_espn_un_posts_and_the_first_post_row_can_name_the_wrong_winner():
    """Real shape from game 401858428: ESPN called it final at 7-12, reverted to
    live, the home team scored, and it finalled again at 13-12. Taking the FIRST
    post row names the losing team. 2 of 28 games change margin after a post."""
    from core.gridiron.fit import outcome_cohort
    s = pd.DataFrame([
        _srow(1, 4, "0:00", 7, 12, t=100),
        _srow(1, None, None, 7, 12, st="post", t=101),     # premature final
        _srow(1, 4, "0:00", 13, 12, t=102),                # un-posted, home scores
        _srow(1, None, None, 13, 12, st="post", t=103),    # the real final
    ])
    c = outcome_cohort(s)
    assert c.margin.iloc[0] == 1, "must take the LAST post row, not the first"


def test_settlement_hazard_reports_the_phenomenon_not_todays_labels():
    """B's design: assert the DISAGREEMENT exists and name the game, so a mutant
    hardcoding observed labels fails and a substrate that stops exercising the
    hazard is visible as an empty result rather than a silent pass."""
    from core.gridiron.fit import settlement_hazard
    s = pd.DataFrame([
        _srow(1, 4, "0:00", 7, 12, t=100),
        _srow(1, None, None, 7, 12, st="post", t=101),
        _srow(1, None, None, 13, 12, st="post", t=103),   # winner changes
        _srow(2, None, None, 16, 3, st="post", t=100),
        _srow(2, None, None, 19, 9, st="post", t=101),    # margin moves, winner does not
        _srow(3, None, None, 21, 7, st="post", t=100),    # clean
    ])
    h = settlement_hazard(s).set_index("game_id")
    assert list(h.index) == [1, 2], "game 3 is clean and must not be reported"
    assert h.loc[1, "winner_changes"] is True or h.loc[1, "winner_changes"] == True
    assert not h.loc[2, "winner_changes"]


def test_settlement_hazard_is_empty_when_the_substrate_stops_exercising_it():
    from core.gridiron.fit import settlement_hazard
    s = pd.DataFrame([_srow(1, 4, "0:00", 21, 7, t=100),
                      _srow(1, None, None, 21, 7, st="post", t=101)])
    assert settlement_hazard(s).empty
