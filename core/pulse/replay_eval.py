"""Offline v1-vs-v2 estimate evaluation against the recorded tick archive.

    python -m core.pulse.replay_eval                  # the comparison
    python -m core.pulse.replay_eval --fit-blend      # refit W_BLEND (prints)
    python -m core.pulse.replay_eval --league-baseline  # refit LEAGUE_SIGMA_SQ

Why this exists
---------------
PULSE v2 (docs/math/pulse-v2-inputs.md) may replace v1's estimates ONLY if a
replay over the archive says it prices games better. This module is that
replay: both estimate sets walk the same recorded ticks of every finished
game with live coverage, and the differences are attributable to the
estimates alone — same clock model, same anchors where shared, same decision
rule, same fill rule, same games.

Two measurements, both clustered by game (C4)
---------------------------------------------
**Calibration** — at every sampled tick with a usable clock and a two-sided
book, each arm's P(YES) is scored against the market's actual settlement
frame outcome (winner: first team won; total rung: final total over the
line; spread rung: first margin + line > 0 — the 196/196-verified frame) as
a Brier contribution. The paired per-game mean difference (v1 − v2, positive
favours v2) gets a game-clustered CI.

**Money at price** — each arm trades the registered PULSE rule on the same
ticks: maker entry at the touch when the net edge clears the strategy
config's threshold, profit-target exit resting on fill, FV-adverse stop to
the touch, endpoint fills, UNIT contracts (sizing is not what is being
compared), unexited fills scored at the game's known settlement (C11). The
registered floors (live_report's) are reported against each arm's counts.

Honesty constraints, stated
---------------------------
* **Read-only, structurally**: the evaluation connection opens with
  ``default_transaction_read_only=on`` — this module cannot write to the
  database it reads, whatever its code does (the mirror fixture's trick).
* **Point-in-time**: form is computed as of each game's first live tick;
  the blend refit is leave-one-game-out for the eval's own numbers.
* **The stale cohort is labelled.** Games whose form was older than
  ``MAX_FORM_STALENESS_DAYS`` at tip are exactly the games the live v2
  guard would refuse — the eval runs them anyway (guard disabled,
  deliberately) to measure degraded-form v2, and reports the two cohorts
  separately. Blending them would average a model with its own absence.
* Sampling is one tick per ``BUCKET_SECONDS`` per market; sub-bucket touches
  are invisible to BOTH arms, so fill optimism cancels in the comparison but
  absolute numbers remain upper bounds (the usual caveat, doubled for round
  trips).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass, field

import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from core.kelly_sizing import net_edge
from core.live_fv import (
    DEFAULT_SIGMA,
    REGULATION_MINUTES,
    fair_value,
    minutes_remaining,
    parse_score,
)
from core.live_totals_fv import over_probability, project_total, remaining_sigma
from core.pulse.live import (
    DEFAULT_PROFIT_TARGET,
    DEFAULT_STOP_ADVERSE,
    MARKET_SPREAD,
    MARKET_TOTAL,
    MARKET_WINNER,
    spread_fair_value,
)
from core.pulse.live_report import FLOOR_ENTRY_FILLS, FLOOR_GAMES
from core.pulse.team_form import (
    MAX_FORM_STALENESS_DAYS,
    MatchupForm,
    blended_total_anchor,
    event_team_abbrevs,
    matchup_form,
)
from core.quote.adverse_selection import clustered_mean

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc

#: The analysis mirror — read-only enforced at connection time below.
DEFAULT_URL = "postgresql+psycopg://meridian:meridian@localhost:5433/meridian"

#: One tick per market per bucket. 15s keeps a 2.5h game near 600 points per
#: market — enough for endpoint fills to mean something, small enough to walk
#: 50 games in minutes.
BUCKET_SECONDS = 15

#: The registered entry threshold is the strategy config's own; imported at
#: call time so the eval and the engine cannot disagree about it.


def _read_only_sessionmaker(url: str):
    engine = create_engine(
        url, pool_size=2, max_overflow=2,
        connect_args={"options": "-c default_transaction_read_only=on"},
    )
    return sessionmaker(bind=engine)


# --------------------------------------------------------------------- #
# Archive loading
# --------------------------------------------------------------------- #


@dataclass(frozen=True)
class Tick:
    at: dt.datetime
    bid: float
    ask: float
    score: str | None
    period: str | None

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0


@dataclass
class EventData:
    event_slug: str
    final_score: tuple[int, int]
    winner_mid: float | None
    mu_v4: float | None
    form: MatchupForm | None          # staleness guard DISABLED here, labelled
    form_fresh: bool
    period_starts: dict[str, dt.datetime] = field(default_factory=dict)
    #: market_slug -> (market_type, line, ticks)
    markets: dict[str, tuple[str, float | None, list[Tick]]] = field(default_factory=dict)


def load_events(Session, *, limit: int | None = None) -> list[EventData]:
    with Session() as s:
        finals = {r.event_slug: r.event_score for r in s.execute(text("""
            SELECT DISTINCT ON (event_slug) event_slug, event_score
            FROM market_snapshots
            WHERE event_period = 'FT' AND event_score IS NOT NULL
            ORDER BY event_slug, captured_at DESC"""))}
        events = sorted(finals)
        if limit:
            events = events[:limit]

        out: list[EventData] = []
        for ev in events:
            pair = parse_score(finals[ev])
            if pair is None:
                continue
            data = EventData(event_slug=ev, final_score=pair,
                             winner_mid=None, mu_v4=None,
                             form=None, form_fresh=False)

            first_live = s.execute(text("""
                SELECT min(captured_at) FROM market_snapshots
                WHERE is_live IS TRUE AND event_slug = :ev"""),
                {"ev": ev}).scalar()
            if first_live is None:
                continue

            for r in s.execute(text("""
                SELECT event_period, min(captured_at) AS first_seen
                FROM market_snapshots
                WHERE is_live IS TRUE AND event_slug = :ev
                  AND event_period IS NOT NULL
                GROUP BY event_period"""), {"ev": ev}):
                data.period_starts[r.event_period] = r.first_seen

            row = s.execute(text("""
                SELECT best_bid, best_ask FROM market_snapshots
                WHERE sports_market_type = :w AND event_slug = :ev
                  AND is_live IS FALSE AND event_score = '0-0'
                  AND best_bid IS NOT NULL AND best_ask IS NOT NULL
                  AND best_ask > best_bid
                ORDER BY captured_at DESC LIMIT 1"""),
                {"w": MARKET_WINNER, "ev": ev}).first()
            if row is not None:
                data.winner_mid = (float(row.best_bid) + float(row.best_ask)) / 2.0

            ladder = [(float(r.line), float(r.model_probability))
                      for r in s.execute(text("""
                SELECT DISTINCT ON (market_slug) line, model_probability
                FROM predictions
                WHERE sports_market_type = :t AND event_slug = :ev
                  AND line IS NOT NULL AND model_probability IS NOT NULL
                ORDER BY market_slug, predicted_at DESC"""),
                {"t": MARKET_TOTAL, "ev": ev})]
            if len(ladder) >= 3:
                from strategies.wnba_totals.model.curve_fit import fit_ladder
                fit = fit_ladder(sorted(ladder))
                if fit.ok and fit.implied_mean is not None:
                    data.mu_v4 = float(fit.implied_mean)

            abbrevs = event_team_abbrevs(ev)
            if abbrevs is not None:
                form = matchup_form(
                    s, first_abbrev=abbrevs[0], second_abbrev=abbrevs[1],
                    as_of=first_live, max_staleness_days=None)
                data.form = form
                data.form_fresh = (
                    form is not None
                    and form.staleness_days <= MAX_FORM_STALENESS_DAYS)

            for r in s.execute(text("""
                SELECT DISTINCT ON (market_slug) market_slug,
                       sports_market_type, line
                FROM market_snapshots
                WHERE event_slug = :ev AND is_live IS TRUE
                  AND sports_market_type IN (:w, :t, :sp)
                ORDER BY market_slug, captured_at DESC"""),
                {"ev": ev, "w": MARKET_WINNER, "t": MARKET_TOTAL,
                 "sp": MARKET_SPREAD}):
                ticks = [Tick(at=x.captured_at, bid=float(x.best_bid),
                              ask=float(x.best_ask), score=x.event_score,
                              period=x.event_period)
                         for x in s.execute(text("""
                    SELECT DISTINCT ON (bucket)
                           to_timestamp(floor(extract(epoch FROM captured_at)
                                        / :b) * :b) AS bucket,
                           captured_at, best_bid, best_ask, event_score,
                           event_period
                    FROM market_snapshots
                    WHERE market_slug = :m AND is_live IS TRUE
                      AND best_bid IS NOT NULL AND best_ask IS NOT NULL
                    ORDER BY bucket, captured_at DESC"""),
                    {"m": r.market_slug, "b": BUCKET_SECONDS})
                    if float(x.best_ask) > float(x.best_bid)]
                if ticks:
                    data.markets[r.market_slug] = (
                        r.sports_market_type,
                        None if r.line is None else float(r.line),
                        sorted(ticks, key=lambda t: t.at),
                    )
            if data.markets:
                out.append(data)
        return out


# --------------------------------------------------------------------- #
# Estimates, both arms, one code path
# --------------------------------------------------------------------- #


@dataclass(frozen=True)
class ArmParams:
    """Everything that differs between the arms — nothing else may."""

    name: str
    sigma: float
    totals_mu: float | None


def arm_params(data: EventData) -> tuple[ArmParams, ArmParams]:
    v1 = ArmParams(name="v1", sigma=DEFAULT_SIGMA, totals_mu=data.mu_v4)
    if data.form is not None:
        v2 = ArmParams(
            name="v2", sigma=data.form.sigma,
            totals_mu=blended_total_anchor(data.mu_v4, data.form))
    else:
        v2 = ArmParams(name="v2", sigma=DEFAULT_SIGMA, totals_mu=data.mu_v4)
    return v1, v2


def estimate_fv(
    *, market_type: str, line: float | None, margin: int, total_so_far: int,
    minutes_left: float, winner_mid: float | None, params: ArmParams,
) -> float | None:
    """One arm's P(YES) — the engine's own math with the arm's constants."""
    if market_type == MARKET_WINNER:
        return fair_value(margin=margin, minutes_left=minutes_left,
                          pregame_price=winner_mid, sigma=params.sigma)
    if market_type == MARKET_TOTAL:
        if line is None or params.totals_mu is None:
            return None
        elapsed = REGULATION_MINUTES - minutes_left
        projected = project_total(pregame_mu=params.totals_mu,
                                  total_so_far=total_so_far,
                                  elapsed_minutes=elapsed)
        return over_probability(projected_total=projected, line=line,
                                sigma=remaining_sigma(elapsed))
    if market_type == MARKET_SPREAD:
        if line is None:
            return None
        return spread_fair_value(margin=margin, minutes_left=minutes_left,
                                 line=line, pregame_price=winner_mid,
                                 sigma=params.sigma)
    return None


def market_outcome(market_type: str, line: float | None,
                   final: tuple[int, int]) -> int | None:
    """YES settlement under the verified frames. None = unscorable."""
    margin = final[0] - final[1]
    total = final[0] + final[1]
    if market_type == MARKET_WINNER:
        return None if margin == 0 else int(margin > 0)
    if market_type == MARKET_TOTAL:
        if line is None or total == line:
            return None
        return int(total > line)
    if market_type == MARKET_SPREAD:
        if line is None or float(line) == int(line) or margin + line == 0:
            return None                # whole lines: push semantics unverified
        return int(margin + line > 0)
    return None


# --------------------------------------------------------------------- #
# The trading simulation — the registered rule, unit size
# --------------------------------------------------------------------- #


@dataclass
class SimResult:
    n_entries: int = 0
    n_entry_fills: int = 0
    n_round_trips: int = 0
    n_rides: int = 0
    rois: list[float] = field(default_factory=list)   # per-$ per scored leg


def simulate_market(
    ticks: list[Tick], fvs: list[float | None], outcome: int,
    *, min_edge: float, profit_target: float = DEFAULT_PROFIT_TARGET,
    stop_adverse: float = DEFAULT_STOP_ADVERSE,
) -> SimResult:
    """The engine's registered decision rule on one market's tick tape.

    `fvs[i]` is the arm's estimate at `ticks[i]` (None = suppressed). Unit
    contracts. Kept deliberately parallel to `core/pulse/live.py` — if the
    rules there change, this must change with them (the registration pins
    both).
    """
    r = SimResult()
    entry_price: float | None = None
    entry_side: str | None = None
    entry_idx = -1
    exit_price: float | None = None
    exit_is_stop = False

    def edge_at(fv: float, side: str, limit: float) -> float:
        if side == "yes":
            return net_edge(fv, limit, is_maker=True)
        return net_edge(1.0 - fv, 1.0 - limit, is_maker=True)

    position_open = False
    for i, (tick, fv) in enumerate(zip(ticks, fvs)):
        mid = tick.mid
        if position_open:
            # exit fill first (endpoint rule, never the birth tick)
            if exit_price is not None and i > entry_idx:
                filled = (mid >= exit_price if entry_side == "yes"
                          else mid <= exit_price)
                if filled:
                    cost = entry_price if entry_side == "yes" else 1.0 - entry_price
                    cap = (exit_price - entry_price if entry_side == "yes"
                           else entry_price - exit_price)
                    r.n_round_trips += 1
                    r.rois.append(cap / cost)
                    position_open = False
                    entry_price = entry_side = exit_price = None
                    continue
            # stop management
            if (not exit_is_stop and fv is not None):
                adverse = (entry_price - fv if entry_side == "yes"
                           else fv - entry_price)
                if adverse >= stop_adverse:
                    exit_price = tick.ask if entry_side == "yes" else tick.bid
                    exit_price = min(max(exit_price, 0.01), 0.99)
                    exit_is_stop = True
            continue

        if entry_price is not None:
            # resting, unfilled entry: fill or withdraw (edge gone)
            if i > entry_idx:
                filled = (mid <= entry_price if entry_side == "yes"
                          else mid >= entry_price)
                if filled:
                    r.n_entry_fills += 1
                    position_open = True
                    exit_price = (entry_price + profit_target
                                  if entry_side == "yes"
                                  else entry_price - profit_target)
                    exit_price = min(max(exit_price, 0.01), 0.99)
                    exit_is_stop = False
                    continue
            if fv is None or edge_at(fv, entry_side, entry_price) <= 0:
                entry_price = entry_side = None
            continue

        # flat: consider entering
        if fv is None:
            continue
        if not (0.05 <= mid <= 0.95) or (tick.ask - tick.bid) > 0.15:
            continue
        side = "yes" if fv > mid else "no"
        limit = tick.bid if side == "yes" else tick.ask
        cost = limit if side == "yes" else 1.0 - limit
        if not (0.01 <= cost <= 0.99):
            continue
        if edge_at(fv, side, limit) < min_edge:
            continue
        entry_price, entry_side, entry_idx = limit, side, i
        r.n_entries += 1

    # game over: an open position (or one that filled and never exited) rides
    if position_open and entry_price is not None:
        cost = entry_price if entry_side == "yes" else 1.0 - entry_price
        ret = float(outcome) if entry_side == "yes" else 1.0 - float(outcome)
        r.n_rides += 1
        r.rois.append(ret / cost - 1.0)
    return r


# --------------------------------------------------------------------- #
# The comparison
# --------------------------------------------------------------------- #


@dataclass
class CohortResult:
    label: str
    n_games: int = 0
    n_calibration_points: int = 0
    brier_v1: float = 0.0
    brier_v2: float = 0.0
    brier_diff_by_game: dict[str, list[float]] = field(default_factory=dict)
    sim: dict[str, SimResult] = field(default_factory=dict)      # arm -> totals
    roi_by_game: dict[str, dict[str, list[float]]] = field(default_factory=dict)


def evaluate(Session, *, limit: int | None = None) -> dict[str, CohortResult]:
    from strategies.wnba_totals.config import CONFIG

    events = load_events(Session, limit=limit)
    cohorts = {
        "fresh-form": CohortResult("fresh-form"),
        "stale-form": CohortResult("stale-form"),
    }
    for c in cohorts.values():
        c.sim = {"v1": SimResult(), "v2": SimResult()}
        c.roi_by_game = {"v1": defaultdict(list), "v2": defaultdict(list)}

    for data in events:
        cohort = cohorts["fresh-form" if data.form_fresh else "stale-form"]
        v1, v2 = arm_params(data)
        ev = data.event_slug
        game_diffs: list[float] = []
        b1_sum = b2_sum = 0.0
        n_pts = 0

        for mtype, line, ticks in data.markets.values():
            outcome = market_outcome(mtype, line, data.final_score)
            if outcome is None:
                continue
            fvs1: list[float | None] = []
            fvs2: list[float | None] = []
            for tick in ticks:
                pair = parse_score(tick.score)
                started = data.period_starts.get(tick.period or "")
                seconds_in = ((tick.at - started).total_seconds()
                              if started is not None else 0.0)
                clock = minutes_remaining(tick.period,
                                          seconds_into_period=max(seconds_in, 0.0))
                if pair is None or not clock.usable:
                    fvs1.append(None)
                    fvs2.append(None)
                    continue
                margin, total = pair[0] - pair[1], pair[0] + pair[1]
                common = {"market_type": mtype, "line": line, "margin": margin,
                          "total_so_far": total,
                          "minutes_left": clock.minutes_left,
                          "winner_mid": data.winner_mid}
                f1 = estimate_fv(**common, params=v1)
                f2 = estimate_fv(**common, params=v2)
                fvs1.append(f1)
                fvs2.append(f2)
                if f1 is not None and f2 is not None:
                    b1 = (f1 - outcome) ** 2
                    b2 = (f2 - outcome) ** 2
                    b1_sum += b1
                    b2_sum += b2
                    n_pts += 1
                    game_diffs.append(b1 - b2)

            for arm_name, fvs in (("v1", fvs1), ("v2", fvs2)):
                sim = simulate_market(ticks, fvs, outcome,
                                      min_edge=CONFIG.min_edge_threshold)
                agg = cohort.sim[arm_name]
                agg.n_entries += sim.n_entries
                agg.n_entry_fills += sim.n_entry_fills
                agg.n_round_trips += sim.n_round_trips
                agg.n_rides += sim.n_rides
                agg.rois.extend(sim.rois)
                if sim.rois:
                    cohort.roi_by_game[arm_name][ev].extend(sim.rois)

        if n_pts:
            cohort.n_games += 1
            cohort.n_calibration_points += n_pts
            cohort.brier_v1 += b1_sum
            cohort.brier_v2 += b2_sum
            cohort.brier_diff_by_game[ev] = game_diffs
    return cohorts


def format_comparison(cohorts: dict[str, CohortResult]) -> str:
    out: list[str] = []
    add = out.append
    add("PULSE v1 vs v2 — replay over the recorded tick archive")
    add("=" * 78)
    add("Positive Brier diff favours v2. Trading is the registered rule, unit")
    add("size, endpoint fills — losses trustworthy, profits upper bounds.")
    add(f"Floors framework (per arm): >= {FLOOR_ENTRY_FILLS} filled entries "
        f"AND >= {FLOOR_GAMES} games.")
    for label in ("fresh-form", "stale-form"):
        c = cohorts[label]
        add("")
        add(f"[{label}]  games: {c.n_games}   calibration points: "
            f"{c.n_calibration_points:,}")
        if c.n_games == 0:
            add("  (empty cohort)")
            continue
        if c.n_calibration_points:
            add(f"  Brier v1: {c.brier_v1 / c.n_calibration_points:.5f}   "
                f"Brier v2: {c.brier_v2 / c.n_calibration_points:.5f}")
            cm = clustered_mean(c.brier_diff_by_game)
            if cm is not None:
                verdict = ("v2 better" if cm.lo > 0
                           else ("v1 better" if cm.hi < 0 else "no separation"))
                add(f"  paired diff (v1−v2), clustered: {cm.mean:+.5f}  "
                    f"95% CI [{cm.lo:+.5f}, {cm.hi:+.5f}]  (G={cm.n_clusters})"
                    f"  -> {verdict}")
        for arm in ("v1", "v2"):
            s = c.sim[arm]
            n_g = len(c.roi_by_game[arm])
            at_floor = (s.n_entry_fills >= FLOOR_ENTRY_FILLS
                        and n_g >= FLOOR_GAMES)
            line = (f"  [{arm}] entries {s.n_entries:,} | fills "
                    f"{s.n_entry_fills:,} | trips {s.n_round_trips:,} | rides "
                    f"{s.n_rides:,} | games {n_g}")
            cm = clustered_mean(c.roi_by_game[arm])
            if cm is not None and at_floor:
                line += (f" | per-$ {cm.mean:+.4f} [{cm.lo:+.4f}, {cm.hi:+.4f}]")
            elif cm is not None:
                line += " | BELOW FLOORS — counts only"
            add(line)
    return "\n".join(out)


# --------------------------------------------------------------------- #
# Refit modes (print; constants move only by hand, with the doc)
# --------------------------------------------------------------------- #


def fit_blend(Session) -> str:
    events = load_events(Session)
    triples = [(d.event_slug, d.mu_v4, d.form.form_total,
                d.final_score[0] + d.final_score[1])
               for d in events
               if d.mu_v4 is not None and d.form is not None and d.form_fresh]
    if len(triples) < 2:
        return f"fit-blend: only {len(triples)} fresh-form events — NO DATA"
    num = sum((m4 - ft) * (fin - ft) for _, m4, ft, fin in triples)
    den = sum((m4 - ft) ** 2 for _, m4, ft, fin in triples)
    w = max(0.0, min(1.0, num / den)) if den > 0 else 1.0

    def rmse(wx: float) -> float:
        return math.sqrt(sum(
            (fin - (wx * m4 + (1 - wx) * ft)) ** 2
            for _, m4, ft, fin in triples) / len(triples))

    return (f"fit-blend: n={len(triples)} fresh-form events | w*={w:.3f} | "
            f"rmse v4-only {rmse(1.0):.2f}, form-only {rmse(0.0):.2f}, "
            f"blend {rmse(w):.2f}\n"
            "Update team_form.W_BLEND and docs/math/pulse-v2-inputs.md "
            "TOGETHER, or not at all.")


def league_baseline(Session) -> str:
    with Session() as s:
        rows = s.execute(text("""
            SELECT t.q1-o.q1 s1, t.q2-o.q2 s2, t.q3-o.q3 s3, t.q4-o.q4 s4
            FROM team_game_logs t
            JOIN team_game_logs o
              ON o.espn_game_id = t.espn_game_id AND o.team_id <> t.team_id
            WHERE t.is_completed
              AND t.q1 IS NOT NULL AND t.q2 IS NOT NULL
              AND t.q3 IS NOT NULL AND t.q4 IS NOT NULL
              AND o.q1 IS NOT NULL AND o.q2 IS NOT NULL
              AND o.q3 IS NOT NULL AND o.q4 IS NOT NULL
              AND t.team_id < o.team_id
        """)).all()
    if not rows:
        return "league-baseline: no completed games with quarters — NO DATA"
    variances = []
    for r in rows:
        s = [float(r.s1), float(r.s2), float(r.s3), float(r.s4)]
        m = sum(s) / 4.0
        variances.append(sum((x - m) ** 2 for x in s) / 3.0 / 10.0)
    v = sum(variances) / len(variances)
    return (f"league-baseline: {len(rows)} games | sigma_sq_per_min = {v:.3f} "
            f"| implied moment sigma {v ** 0.5:.3f}/sqrt-min\n"
            "Update team_form.LEAGUE_SIGMA_SQ_PER_MIN and the doc TOGETHER.")


def main() -> int:
    parser = argparse.ArgumentParser(prog="pulse-replay-eval")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--limit", type=int, default=None,
                        help="cap the number of events (smoke runs)")
    parser.add_argument("--fit-blend", action="store_true")
    parser.add_argument("--league-baseline", action="store_true")
    parser.add_argument("--json", dest="json_path", default=None)
    args = parser.parse_args()

    Session = _read_only_sessionmaker(args.url)
    if args.league_baseline:
        print(league_baseline(Session))
        return 0
    if args.fit_blend:
        print(fit_blend(Session))
        return 0

    cohorts = evaluate(Session, limit=args.limit)
    print(format_comparison(cohorts))
    if args.json_path:
        payload = {}
        for label, c in cohorts.items():
            cm = clustered_mean(c.brier_diff_by_game)
            payload[label] = {
                "n_games": c.n_games,
                "n_calibration_points": c.n_calibration_points,
                "brier_v1": (c.brier_v1 / c.n_calibration_points
                             if c.n_calibration_points else None),
                "brier_v2": (c.brier_v2 / c.n_calibration_points
                             if c.n_calibration_points else None),
                "brier_diff_clustered": (
                    None if cm is None else
                    {"mean": cm.mean, "lo": cm.lo, "hi": cm.hi,
                     "n_clusters": cm.n_clusters}),
                "arms": {
                    arm: {
                        "entries": c.sim[arm].n_entries,
                        "entry_fills": c.sim[arm].n_entry_fills,
                        "round_trips": c.sim[arm].n_round_trips,
                        "rides": c.sim[arm].n_rides,
                        "games": len(c.roi_by_game[arm]),
                    } for arm in ("v1", "v2")
                },
            }
        with open(args.json_path, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"\nwrote {args.json_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
