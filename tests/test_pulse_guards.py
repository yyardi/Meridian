"""The PULSE state guards: refuse garbage in, refuse fake certainty out.

Mutation-tested against the RECORDED states from Track C's six extreme-miss
games (`analysis/fv-calibration-report.md`, CORRECTION section) — every
fixture below is a literal row from the pinned wave tape
(`pulse_decisions_full_20260901T195202Z.csv`), its id in the comment. The
sea-dal P=1.0000 row is the regression: remove the guard and its test goes
red. Healthy states from the same games prove the guards stay quiet on real
basketball.

Pure tests — no database. The wiring tests drive `PulseEngine._estimate`
directly on synthetic observations; `_estimate` touches no session.
"""

from __future__ import annotations

import datetime as dt

from core.pulse import guards
from core.pulse.live import EventAnchors, Observation, PulseEngine
from core.pulse.storage import STRAT_TOTAL

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 9, 1, 1, 0, 0, tzinfo=UTC)


# --------------------------------------------------------------------------- #
# Guard 1 — jointly-impossible clock/score states, on the recorded rows
# --------------------------------------------------------------------------- #

def test_sea_dal_certainty_from_corrupt_state_is_refused():
    # Row 3281 (v3, UNFLAGGED — the reason the guard must not read a flag):
    # 91 points at "Q2, 30:00 left" priced P(over 171.5) = 1.0000 against a
    # market at 0.62; the game finaled 162. Elapsed is 10 minutes; 91 points
    # in 10 minutes is not basketball. THIS TEST MUST GO RED IF THE GUARD IS
    # REMOVED.
    reason = guards.implausible_state(
        period="Q2", minutes_left=30.0, total_so_far=91, margin=1)
    assert reason is not None and reason.startswith("score_too_high_for_elapsed")


def test_conn_la_period_seam_score_is_refused():
    # Row 1707: 11 points on the board with the Q1 clock still at 40:00 —
    # points cannot precede elapsed time.
    reason = guards.implausible_state(
        period="Q1", minutes_left=40.0, total_so_far=11, margin=3)
    assert reason is not None and reason.startswith("score_too_high_for_elapsed")


def test_period_and_clock_must_agree():
    # No recorded instance (v1's constructed clock respects bounds and the
    # venue clock happened not to disagree this window) — the check exists
    # for the corruption class, not one incident: a Q4 label with 25 minutes
    # remaining is impossible whatever the score says.
    reason = guards.implausible_state(
        period="Q4", minutes_left=25.0, total_so_far=120, margin=4)
    assert reason is not None and reason.startswith("period_clock_mismatch")


def test_stale_score_under_running_clock_is_refused():
    # The converse corruption: 20 points at 35 elapsed minutes (floor is
    # 1.5/min − 10 = 42.5). Zero tape rows trip this; a dead score feed
    # riding a live clock would.
    reason = guards.implausible_state(
        period="Q4", minutes_left=5.0, total_so_far=20, margin=2)
    assert reason is not None and reason.startswith("score_too_low_for_elapsed")


def test_healthy_states_from_the_same_games_pass():
    # sea-dal's own plausible neighbourhood (46 points at ~10 elapsed), the
    # HT seam with its recorded 19.42–20.16 drift, and a normal endgame.
    for period, minutes, total, margin in [
        ("Q2", 30.0, 46, 4),           # plausible Q2 boundary state
        ("HT", 19.42, 105, 7),         # recorded seam drift, conn-dal
        ("HT", 20.16, 105, 7),
        ("Q1", 39.86, 2, 2),           # first bucket of a real game
        ("Q4", 0.15, 181, 3),          # por-atl's real endgame state
    ]:
        assert guards.implausible_state(
            period=period, minutes_left=minutes, total_so_far=total,
            margin=margin) is None, (period, minutes, total)


# --------------------------------------------------------------------------- #
# Guard 2 — unrepresentable confidence, on the recorded rows (totals only)
# --------------------------------------------------------------------------- #

def test_por_atl_foul_game_zero_is_refused():
    # Row 12921 (v4): P(over 183.5) = 0.0 with 0:09 left, 181 on the board —
    # needing 2.5 points. The foul game produced 3 and the over won while
    # the market bid 0.63.
    reason = guards.unrepresentable_confidence(
        fair_value=0.0, minutes_left=0.15, line=183.5, total_so_far=181)
    assert reason is not None and reason.startswith("endgame_tail")


def test_ind_ny_overtime_zero_is_refused():
    # Rows 1668/1670: P(over 200.5) = 0.0004 → 0.0000 in the last two
    # minutes at 184 — the projection converges to total_so_far at the
    # buzzer, so P(OT points) is structurally zero. The game went to OT and
    # the over won against a market bid of 0.82.
    for minutes, fv in [(2.09, 0.0004), (1.08, 0.0000)]:
        reason = guards.unrepresentable_confidence(
            fair_value=fv, minutes_left=minutes, line=200.5, total_so_far=184)
        assert reason is not None and reason.startswith("endgame_tail")


def test_conn_dal_halftime_098_is_refused():
    # Rows 19080/19092 (v4): 105 at the half, P(over 173.5) = 0.98 held for
    # nineteen consecutive minutes; the second half scored 63. A half-length
    # extrapolation's sigma cannot justify 98%.
    for minutes, fv in [(20.64, 0.9842), (20.0, 0.9811)]:
        reason = guards.unrepresentable_confidence(
            fair_value=fv, minutes_left=minutes, line=173.5, total_so_far=105)
        assert reason is not None and reason.startswith("extrapolation_tail")


def test_ind_ny_early_under_certainty_is_refused():
    # Row 1296 (v1): P(over 200.5) = 0.008 with 20.8 minutes left at 75 —
    # asserting sub-1% about half a game that (via OT) reached 211.
    reason = guards.unrepresentable_confidence(
        fair_value=0.008, minutes_left=20.8, line=200.5, total_so_far=75)
    assert reason is not None and reason.startswith("extrapolation_tail")


def test_clinched_over_passes_at_any_confidence():
    # Points never come off the board: 185 > 183.5 makes P(over) = 1
    # arithmetic, not a tail claim — at the buzzer or the half alike.
    for minutes in (0.1, 2.9, 18.0, 20.0):
        assert guards.unrepresentable_confidence(
            fair_value=1.0, minutes_left=minutes, line=183.5,
            total_so_far=185) is None


def test_unclinched_endgame_certainty_is_refused_even_when_plausible():
    # The documented conservative footprint: needing 30 points in two
    # minutes, fv≈0 is PROBABLY right — and is refused anyway, because the
    # Gaussian's zero carries no foul-game/OT mass. Half the tape's 229
    # endgame refusals are such agreement states; they cost nothing because
    # fv≈mid fires no entry. This test pins the choice as intentional.
    reason = guards.unrepresentable_confidence(
        fair_value=0.001, minutes_left=2.0, line=210.5, total_so_far=180)
    assert reason is not None and reason.startswith("endgame_tail")


def test_midgame_and_moderate_confidence_pass():
    # Between the bands (3 < minutes < 15) nothing fires at any fv, and
    # inside the bands moderate confidence passes.
    assert guards.unrepresentable_confidence(
        fair_value=0.999, minutes_left=8.0, line=183.5, total_so_far=140) is None
    assert guards.unrepresentable_confidence(
        fair_value=0.90, minutes_left=20.0, line=173.5, total_so_far=105) is None
    assert guards.unrepresentable_confidence(
        fair_value=0.10, minutes_left=1.0, line=183.5, total_so_far=178) is None


# --------------------------------------------------------------------------- #
# Wiring — the engine abstains: no fair value, the reason carried
# --------------------------------------------------------------------------- #

def _engine() -> PulseEngine:
    # _estimate never touches the session; the sessionmaker is inert here.
    return PulseEngine(sessionmaker=None)


def _ob(*, mtype, line=None, score, period, slug="guard-test-market",
        event="guard-test-event") -> Observation:
    return Observation(
        market_slug=slug, event_slug=event, game_id="g1",
        sports_market_type=mtype, line=line, captured_at=NOW,
        bid=0.45, ask=0.50, is_live=True, event_score=score,
        event_period=period, min_trade_qty=0.01)


def test_engine_abstains_on_corrupt_state_and_carries_the_reason():
    from core.pulse.live import MARKET_WINNER
    eng = _engine()
    # Period start == capture time → 30:00 left in Q2 with 91 points: the
    # sea-dal shape, arriving through the engine's own clock path.
    eng._period_starts[("guard-test-event", "Q2")] = NOW
    est = eng._estimate(_ob(mtype=MARKET_WINNER, score="46-45", period="Q2"))
    assert est.fair_value is None
    assert est.abstain_guard == guards.GUARD_STATE
    assert est.abstain_reason.startswith("score_too_high_for_elapsed")
    assert not est.clock.usable          # nothing downstream prices or stops
    assert est.abstained_fair_value is None   # refused BEFORE pricing


def test_engine_abstains_on_endgame_certainty_and_keeps_the_evidence():
    from core.pulse.live import MARKET_TOTAL
    eng = _engine()
    eng._anchors["guard-test-event"] = EventAnchors(totals_mu=165.0)
    # Q4 with 2 minutes left, 181 on the board, line 182.5: the projection
    # runs far past the line and the Gaussian asserts near-certainty about
    # 1.5 points that still require future scoring.
    eng._period_starts[("guard-test-event", "Q4")] = NOW - dt.timedelta(minutes=8)
    est = eng._estimate(_ob(mtype=MARKET_TOTAL, line=182.5,
                            score="92-89", period="Q4"))
    assert est.strategy == STRAT_TOTAL
    assert est.fair_value is None
    assert est.abstain_guard == guards.GUARD_CONFIDENCE
    assert est.abstain_reason.startswith("endgame_tail")
    # The refused assertion is kept as evidence for the abstention row.
    assert est.abstained_fair_value is not None
    assert est.abstained_fair_value > 1.0 - guards.ENDGAME_BAND


def test_engine_prices_normally_when_no_guard_fires():
    from core.pulse.live import MARKET_TOTAL
    eng = _engine()
    eng._anchors["guard-test-event"] = EventAnchors(totals_mu=165.0)
    eng._period_starts[("guard-test-event", "Q4")] = NOW - dt.timedelta(minutes=8)
    # Same state, line at the projection: mid-band probability, no guard.
    est = eng._estimate(_ob(mtype=MARKET_TOTAL, line=189.5,
                            score="92-89", period="Q4"))
    assert est.abstain_guard is None
    assert est.fair_value is not None
    assert guards.ENDGAME_BAND < est.fair_value < 1.0 - guards.ENDGAME_BAND


def test_abstentions_are_recorded_once_per_throttle_window():
    # The binding_constraint principle: the refusal lands as a row with the
    # refused state and the would-have-been assertion; the second call
    # inside the throttle window writes nothing.
    from core.pulse.live import MARKET_TOTAL
    from core.pulse.storage import PulseAbstention
    from core.storage import get_engine, get_sessionmaker
    from sqlalchemy import text

    Session = get_sessionmaker(get_engine())
    eng = _engine()
    eng._anchors["guard-test-event"] = EventAnchors(totals_mu=165.0)
    eng._period_starts[("guard-test-event", "Q4")] = NOW - dt.timedelta(minutes=8)
    ob = _ob(mtype=MARKET_TOTAL, line=182.5, score="92-89", period="Q4")
    est = eng._estimate(ob)
    assert est.abstain_guard == guards.GUARD_CONFIDENCE
    try:
        with Session() as s:
            eng._record_abstention(s, ob, est)
            eng._record_abstention(s, ob, est)      # throttled
            s.commit()
        with Session() as s:
            rows = s.query(PulseAbstention).filter(
                PulseAbstention.market_slug == "guard-test-market").all()
            assert len(rows) == 1
            row = rows[0]
            assert row.guard == guards.GUARD_CONFIDENCE
            assert row.reason.startswith("endgame_tail")
            assert row.total_so_far == 181
            assert float(row.line) == 182.5
            assert row.fair_value_raw is not None   # the refused assertion
            assert row.estimates_version == est.version
    finally:
        with Session() as s:
            s.execute(text("delete from pulse_abstentions "
                           "where market_slug = 'guard-test-market'"))
            s.commit()
