"""Point-in-time team form for PULSE v2: fitted volatility and tempo priors.

What v1 lacks, by design
------------------------
The v1 live estimates run on exactly three inputs: the pregame price, the
live score/clock, and ONE league constant — ``DEFAULT_SIGMA = 2.628`` margin
points per √minute, fitted once across 787 games. Every matchup gets the same
volatility and every totals anchor is v4's pregame number untouched by recent
form. This module supplies the missing cross-section:

* **Per-matchup margin volatility** — some pairings genuinely swing more per
  minute than others (pace is the dominant driver, which is why a per-matchup
  moment estimate captures "per-matchup-pace" without a separate pace model).
* **A recent-form tempo prior for the total** — where the two teams' last
  games say this one ends, blended with v4's anchor.

Everything here is **point-in-time by construction**: a query for a game on
date D reads only completed games strictly before D. Feeding a same-day log
row into a same-day estimate would be lookahead — the exact error
docs/math/point-in-time.md exists to prevent.

The volatility estimator (a moment, not a refit)
------------------------------------------------
For one completed game, the four quarter margin-changes ``s_k`` (team quarter
points minus opponent quarter points) are draws whose variance over a
10-minute quarter is ``sigma² · 10`` plus a drift term. The within-game
variance around the game's own mean removes that game's drift:

    var_g = Σ (s_k − s̄)² / 3          sigma²_g = var_g / 10

A team's estimate averages ``sigma²_g`` over its recent completed games; a
matchup averages its two teams; and the result is SHRUNK toward the league
moment with ``K_SHRINK`` pseudo-games — 10 games of one team is not much
evidence against 787:

    sigma²_shrunk = (n·sigma²_team + K·sigma²_league) / (n + K)

What v2 actually uses is the **ratio**, applied to v1's own fitted constant:

    sigma_v2 = DEFAULT_SIGMA · sqrt(sigma²_shrunk / LEAGUE_SIGMA_SQ_PER_MIN)

so the probit calibration of the 2.628 stays, and only the cross-sectional
information moves it. The league baseline is frozen below (measured from the
mirror on 2026-08-18, 213 completed 2026 games) rather than re-derived per
call: it moves glacially and freezing it makes the multiplier auditable.

The tempo prior
---------------
    form_total(A, B) = (A.for + A.against + B.for + B.against) / 2

over each team's last ``N_RECENT`` completed games. The v2 totals anchor is

    mu_v2 = W_BLEND · mu_v4 + (1 − W_BLEND) · form_total

``W_BLEND`` is frozen from an offline fit (docs/math/pulse-v2-inputs.md; the
replay eval refits it leave-one-game-out to keep its own numbers honest).
Runtime fitting was rejected deliberately: a weight that drifts silently
under a live engine is the decayed-bankroll bug wearing a new coat.

Freshness is a refusal, not a caveat
------------------------------------
``matchup_form`` returns None when either team's newest completed game is
older than ``MAX_FORM_STALENESS_DAYS`` before the as-of instant. Stale form
silently feeding a live model is exactly the failure the operator's
"verify max(game_date) is current" instruction names — the caller (the v2
engine) falls back to the v1 constants and says so. The offline eval may
disable the guard to measure degraded-form value, but it must LABEL the
cohort (see replay_eval).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import structlog
from sqlalchemy import text

from core.live_fv import DEFAULT_SIGMA

log = structlog.get_logger(__name__)

#: Recent-form window, in completed games per team.
N_RECENT = 10
#: Shrinkage weight: pseudo-games of league prior mixed into a team's moment.
K_SHRINK = 8.0
#: League per-minute margin-swing variance. Frozen 2026-08-18 from the local
#: mirror: within-game quarter-swing variance / 10, averaged over the same
#: 787 completed games with quarter scores that fitted the win curve. The
#: implied moment sigma (2.386/√min) deliberately does NOT match the probit
#: 2.628 — the probit carries model misspecification the moment cannot see,
#: which is exactly why v2 applies the RATIO to 2.628 rather than using the
#: moment directly. Recompute with
#: ``python -m core.pulse.replay_eval --league-baseline`` when the season's
#: history grows, and bump this constant plus the doc together.
LEAGUE_SIGMA_SQ_PER_MIN = 5.694
#: Form older than this refuses to feed a live estimate.
MAX_FORM_STALENESS_DAYS = 5.0
#: Frozen blend weight for the v2 totals anchor. **Fitted 2026-08-18 and the
#: fit said 1.0** — on the only honest sample available (6 fresh-form events;
#: the other 36 archived events sit behind the July-31 log staleness the
#: ESPN fix #25 will repair), the constrained least-squares weight clamps to
#: 1.0 and form-only RMSE (21.9) loses to v4-only (19.6). So the blend is
#: currently a NO-OP by measurement, not by design: the machinery ships, the
#: weight stays 1.0, and it may move only when a refit on the restored logs
#: (``python -m core.pulse.replay_eval --fit-blend``) says so — updated here
#: and in docs/math/pulse-v2-inputs.md together, never silently at runtime.
W_BLEND = 1.0


@dataclass(frozen=True)
class TeamForm:
    """One team's recent completed games, as of an instant. Point-in-time."""

    abbrev: str
    as_of: dt.datetime
    n_games: int
    points_for: float                 # per game, recent window
    points_against: float
    sigma_sq_per_min: float           # within-game quarter-swing moment
    possessions: float | None         # pace proxy per game, when stats allow
    last_game_at: dt.datetime

    @property
    def staleness_days(self) -> float:
        return (self.as_of - self.last_game_at).total_seconds() / 86400.0


@dataclass(frozen=True)
class MatchupForm:
    """What recent form says about one matchup. All point-in-time."""

    first: TeamForm
    second: TeamForm
    #: Recent-form expected total for this pairing.
    form_total: float
    #: sqrt(shrunk matchup variance / league variance) — multiplies 2.628.
    sigma_multiplier: float
    #: DEFAULT_SIGMA · sigma_multiplier: the number the v2 curve actually uses.
    sigma: float

    @property
    def staleness_days(self) -> float:
        return max(self.first.staleness_days, self.second.staleness_days)


_FORM_SQL = text("""
    SELECT game_date, points_scored, points_allowed, q1, q2, q3, q4,
           fga, fta, oreb, turnovers,
           oq1, oq2, oq3, oq4
    FROM (
        SELECT t.game_date, t.points_scored, t.points_allowed,
               t.q1, t.q2, t.q3, t.q4, t.fga, t.fta, t.oreb, t.turnovers,
               o.q1 AS oq1, o.q2 AS oq2, o.q3 AS oq3, o.q4 AS oq4
        FROM team_game_logs t
        JOIN team_game_logs o
          ON o.espn_game_id = t.espn_game_id AND o.team_id <> t.team_id
        WHERE t.team_abbrev = :abbrev
          AND t.is_completed
          AND t.game_date < :as_of
        ORDER BY t.game_date DESC
        LIMIT :n
    ) recent
""")


def team_form(
    session, abbrev: str, *, as_of: dt.datetime, n_recent: int = N_RECENT
) -> TeamForm | None:
    """A team's recent form strictly BEFORE ``as_of``. None when it has no
    completed history there — a team without a past gets no prior, not a
    made-up one."""
    rows = session.execute(
        _FORM_SQL, {"abbrev": abbrev, "as_of": as_of, "n": n_recent}
    ).all()
    if not rows:
        return None

    pf = pa = 0.0
    poss_vals: list[float] = []
    swing_vars: list[float] = []
    last: dt.datetime | None = None
    for r in rows:
        pf += float(r.points_scored)
        pa += float(r.points_allowed)
        if last is None or r.game_date > last:
            last = r.game_date
        if None not in (r.fga, r.fta, r.oreb, r.turnovers):
            poss_vals.append(
                float(r.fga) - float(r.oreb) + float(r.turnovers)
                + 0.44 * float(r.fta))
        quarters = (r.q1, r.q2, r.q3, r.q4, r.oq1, r.oq2, r.oq3, r.oq4)
        if None not in quarters:
            swings = [float(r.q1) - float(r.oq1), float(r.q2) - float(r.oq2),
                      float(r.q3) - float(r.oq3), float(r.q4) - float(r.oq4)]
            mean = sum(swings) / 4.0
            swing_vars.append(sum((s - mean) ** 2 for s in swings) / 3.0 / 10.0)

    n = len(rows)
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=dt.timezone.utc)
    return TeamForm(
        abbrev=abbrev,
        as_of=as_of,
        n_games=n,
        points_for=pf / n,
        points_against=pa / n,
        sigma_sq_per_min=(sum(swing_vars) / len(swing_vars)
                          if swing_vars else LEAGUE_SIGMA_SQ_PER_MIN),
        possessions=sum(poss_vals) / len(poss_vals) if poss_vals else None,
        last_game_at=last,
    )


def matchup_form(
    session,
    *,
    first_abbrev: str,
    second_abbrev: str,
    as_of: dt.datetime,
    max_staleness_days: float | None = MAX_FORM_STALENESS_DAYS,
    n_recent: int = N_RECENT,
) -> MatchupForm | None:
    """Both teams' form combined, or None — missing history or stale form
    refuse rather than degrade silently. Pass ``max_staleness_days=None``
    ONLY from the offline eval, which labels its stale cohort.
    """
    a = team_form(session, first_abbrev, as_of=as_of, n_recent=n_recent)
    b = team_form(session, second_abbrev, as_of=as_of, n_recent=n_recent)
    if a is None or b is None:
        return None

    combined_sq = (a.sigma_sq_per_min + b.sigma_sq_per_min) / 2.0
    n_eff = (a.n_games + b.n_games) / 2.0
    shrunk = ((n_eff * combined_sq + K_SHRINK * LEAGUE_SIGMA_SQ_PER_MIN)
              / (n_eff + K_SHRINK))
    multiplier = (shrunk / LEAGUE_SIGMA_SQ_PER_MIN) ** 0.5

    form = MatchupForm(
        first=a, second=b,
        form_total=(a.points_for + a.points_against
                    + b.points_for + b.points_against) / 2.0,
        sigma_multiplier=multiplier,
        sigma=DEFAULT_SIGMA * multiplier,
    )
    if max_staleness_days is not None and form.staleness_days > max_staleness_days:
        log.info("pulse_form_stale",
                 first=first_abbrev, second=second_abbrev,
                 staleness_days=round(form.staleness_days, 1),
                 note="v2 refuses stale form; the caller falls back to v1")
        return None
    return form


def blended_total_anchor(mu_v4: float | None, form: MatchupForm | None) -> float | None:
    """The v2 totals anchor. Both inputs present: the frozen blend. Only v4:
    v4 alone (v1's own anchor — no information lost). Only form: None — the
    form total alone has not earned anchor status and v1 would have refused
    this market too, so refusing keeps the arms comparable."""
    if mu_v4 is None:
        return None
    if form is None:
        return mu_v4
    return W_BLEND * mu_v4 + (1.0 - W_BLEND) * form.form_total


def event_team_abbrevs(event_slug: str) -> tuple[str, str] | None:
    """Slug team codes -> ESPN abbrevs, or None for an unparseable slug.

    The mapping hazard is real (CONN vs CON, PDX vs POR) and lives in
    `core.team_mapping`, which is the one place it is maintained.
    """
    from core.team_mapping import UnknownTeamError, parse_event_slug, to_espn_abbrev

    parsed = parse_event_slug(event_slug)
    if parsed is None:
        return None
    try:
        return (to_espn_abbrev(parsed.first_polymarket),
                to_espn_abbrev(parsed.second_polymarket))
    except UnknownTeamError:
        # NOTE: structlog's first positional IS `event` — passing an `event=`
        # kwarg raises TypeError inside the handler (found by test, 2026-08-20).
        log.warning("pulse_form_unknown_team", slug=event_slug)
        return None
