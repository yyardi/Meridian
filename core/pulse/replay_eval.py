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
    stop_rule: str = "adverse",
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
            # stop management: 'adverse' is the pre-#9 registered rule (kept
            # as the default so historical arm numbers stay comparable);
            # 'ev' is ledger #9 — fire the moment fair value falls to the
            # entry price (docs/math/pulse-ev-stop.md).
            if (not exit_is_stop and fv is not None):
                adverse = (entry_price - fv if entry_side == "yes"
                           else fv - entry_price)
                threshold = 0.0 if stop_rule == "ev" else stop_adverse
                if adverse >= threshold:
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
# v3: the signal-consuming arm (protocol: docs/math/pulse-v3-protocol.md)
# --------------------------------------------------------------------- #
#
# v3a is v1's OWN formulas fed the venue's own clock from the signal-side
# archive — nothing else may differ (the protocol's one-input-per-gate rule).
# The exploratory arms the protocol names (v3b pace-totals, v3c splits-sigma)
# are NOT implemented here: their model forms are not registered, and
# building them from a loose sentence would be exactly the
# "written from hunches" failure the protocol exists to prevent. The report
# says so out loud rather than leaving a silent gap.

#: Protocol floors, fixed in docs/math/pulse-v3-protocol.md before any data.
FLOOR_V3_GAMES = 10
FLOOR_V3_POINTS = 3000
#: A clock reading older than this at the tick falls back to v1's estimator
#: FOR THAT TICK (counted): a dead recorder degrades v3 to v1, never
#: poisons it.
V3_CLOCK_STALENESS_SECONDS = 60.0


@dataclass
class SignalData:
    """One joined game's signal streams, prefetched and time-ordered."""

    espn_game_id: str
    #: Slug's first team is ESPN's home side — the WP frame conversion.
    first_is_home: bool
    #: (first_seen_at, period, clock_seconds), ordered by first_seen_at.
    clock_rows: list
    #: (first_seen_at, home_win_pct), ordered by first_seen_at.
    wp_rows: list


def resolve_signal_games(Session, events: list[EventData]
                         ) -> tuple[dict[str, SignalData], int]:
    """event_slug -> SignalData for unambiguously joined games.

    The join is the registered one: slug team codes -> ESPN abbrevs
    (core.team_mapping), matched against the box snapshots' home/away team
    ids via team_game_logs' id->abbrev map, date within a day. Anything
    ambiguous is EXCLUDED and counted — never guessed. Returns
    (joined, n_excluded)."""
    from core.team_mapping import parse_event_slug

    with Session() as s:
        abbrev_of = dict(s.execute(text("""
            SELECT DISTINCT team_id, team_abbrev FROM team_game_logs
        """)).all())
        games = s.execute(text("""
            SELECT DISTINCT ON (espn_game_id)
                   espn_game_id, home_team_id, away_team_id,
                   min(first_seen_at) OVER (PARTITION BY espn_game_id) AS first_seen
            FROM espn_live_box_snapshots
            WHERE home_team_id IS NOT NULL AND away_team_id IS NOT NULL
            ORDER BY espn_game_id, first_seen_at DESC
        """)).all()

    candidates = []
    for g in games:
        home = abbrev_of.get(g.home_team_id)
        away = abbrev_of.get(g.away_team_id)
        if home and away:
            candidates.append((g.espn_game_id, home, away,
                               (g.first_seen + ET_OFFSET_FOR_JOIN).date()))

    out: dict[str, SignalData] = {}
    excluded = 0
    for data in events:
        abbrevs = event_team_abbrevs(data.event_slug)
        parsed = parse_event_slug(data.event_slug)
        if abbrevs is None or parsed is None:
            continue                   # not a signal-cohort candidate at all
        matches = [
            (gid, home) for gid, home, away, gdate in candidates
            if {home, away} == {abbrevs[0], abbrevs[1]}
            and abs((gdate - parsed.local_date).days) <= 1
        ]
        if not matches:
            continue
        if len(matches) > 1:
            excluded += 1
            log.warning("v3_join_ambiguous", slug=data.event_slug,
                        candidates=[m[0] for m in matches])
            continue
        gid, home_abbrev = matches[0]
        with Session() as s:
            clock_rows = s.execute(text("""
                SELECT first_seen_at, period, clock_seconds
                FROM espn_live_box_snapshots
                WHERE espn_game_id = :g
                  AND period IS NOT NULL AND clock_seconds IS NOT NULL
                ORDER BY first_seen_at
            """), {"g": gid}).all()
            wp_rows = s.execute(text("""
                SELECT first_seen_at, home_win_pct
                FROM espn_live_win_probability
                WHERE espn_game_id = :g AND home_win_pct IS NOT NULL
                ORDER BY first_seen_at
            """), {"g": gid}).all()
        out[data.event_slug] = SignalData(
            espn_game_id=gid,
            first_is_home=(home_abbrev == abbrevs[0]),
            clock_rows=clock_rows,
            wp_rows=wp_rows,
        )
    return out, excluded


#: Scoreboard/box dates are US Eastern; in-season EDT = UTC-4 (the recorder's
#: own convention, restated here for the join only).
ET_OFFSET_FOR_JOIN = dt.timedelta(hours=-4)


class _SeriesPointer:
    """Newest row with first_seen_at <= t, over a time-ordered series —
    the point-in-time bound as a pointer, never a per-tick query."""

    def __init__(self, rows):
        self._rows = rows
        self._i = -1

    def at(self, t):
        while self._i + 1 < len(self._rows) and self._rows[self._i + 1][0] <= t:
            self._i += 1
        return self._rows[self._i] if self._i >= 0 else None


@dataclass
class V3Result:
    n_events_with_signals: int = 0
    n_join_excluded: int = 0
    n_points: int = 0
    brier_v1: float = 0.0
    brier_v3: float = 0.0
    brier_diff_by_game: dict[str, list[float]] = field(default_factory=dict)
    #: Ticks v1 must suppress (clock unusable) but v3a prices.
    coverage_ticks: int = 0
    coverage_brier_sum: float = 0.0
    #: OT ticks neither arm prices (no registered OT model — stated, counted).
    ot_ticks_unpriced: int = 0
    fallback_ticks: int = 0
    #: (estimated − exact) minutes at ticks where both clocks exist.
    clock_disagreement: list[float] = field(default_factory=list)
    #: ESPN's own WP at matched winner-market ticks, and both arms there.
    wp_points: int = 0
    wp_brier_espn: float = 0.0
    wp_brier_v1: float = 0.0
    wp_brier_v3: float = 0.0
    sim: dict[str, SimResult] = field(default_factory=dict)
    roi_by_game: dict[str, dict[str, list[float]]] = field(default_factory=dict)

    @property
    def at_floor(self) -> bool:
        return (len(self.brier_diff_by_game) >= FLOOR_V3_GAMES
                and self.n_points >= FLOOR_V3_POINTS)

    @property
    def trading_diff(self):
        """Paired per-game trading diff (v3a − v1), game means, clustered —
        the registered criterion's SECOND clause ('money-at-price not
        measurably worse'). Games where both arms scored at least one leg."""
        diffs = {}
        for ev in set(self.roi_by_game.get("v1", {})) & set(
                self.roi_by_game.get("v3", {})):
            v1 = self.roi_by_game["v1"][ev]
            v3 = self.roi_by_game["v3"][ev]
            diffs[ev] = [sum(v3) / len(v3) - sum(v1) / len(v1)]
        return clustered_mean(diffs)

    @property
    def verdict(self) -> str:
        """BOTH registered clauses (docs/math/pulse-v3-protocol.md): the
        paired Brier CI excludes zero in v3a's favour, AND money-at-price is
        not measurably worse (the paired trading diff's CI does not sit
        entirely below zero). The first shipped implementation checked only
        the Brier clause — found and fixed at the first at-floor read, with
        the verdict unchanged on that data."""
        if not self.at_floor:
            return "NO DATA"
        cm = clustered_mean(self.brier_diff_by_game)
        if cm is None:
            return "NO DATA"
        if not (cm.mean > 0 and cm.lo > 0):
            return "FAIL"
        td = self.trading_diff
        if td is not None and td.hi < 0:
            return ("FAIL (calibration better, but money-at-price is "
                    "measurably worse — the registration's second clause)")
        return "PASS (go-live question goes to the operator)"


def evaluate_v3(Session, *, limit: int | None = None) -> V3Result:
    """v1 vs v3a over signal-covered games — the registered comparison."""
    from core.pulse.signals import exact_clock
    from strategies.wnba_totals.config import CONFIG

    events = load_events(Session, limit=limit)
    signals, excluded = resolve_signal_games(Session, events)
    r = V3Result(n_join_excluded=excluded)
    r.sim = {"v1": SimResult(), "v3": SimResult()}
    r.roi_by_game = {"v1": defaultdict(list), "v3": defaultdict(list)}

    for data in events:
        sig = signals.get(data.event_slug)
        if sig is None:
            continue
        r.n_events_with_signals += 1
        v1_params, _ = arm_params(data)     # v3a uses v1's constants, only
        ev = data.event_slug                # the clock may differ (protocol)
        game_diffs: list[float] = []

        for mtype, line, ticks in data.markets.values():
            outcome = market_outcome(mtype, line, data.final_score)
            if outcome is None:
                continue
            clock_ptr = _SeriesPointer(sig.clock_rows)
            wp_ptr = _SeriesPointer(sig.wp_rows)
            fvs1: list[float | None] = []
            fvs3: list[float | None] = []
            for tick in ticks:
                pair = parse_score(tick.score)
                started = data.period_starts.get(tick.period or "")
                seconds_in = ((tick.at - started).total_seconds()
                              if started is not None else 0.0)
                v1_clock = minutes_remaining(
                    tick.period, seconds_into_period=max(seconds_in, 0.0))

                clock_row = clock_ptr.at(tick.at)
                exact = None
                if clock_row is not None:
                    staleness = (tick.at - clock_row[0]).total_seconds()
                    if staleness <= V3_CLOCK_STALENESS_SECONDS:
                        exact = exact_clock(int(clock_row[1]),
                                            float(clock_row[2]),
                                            staleness_seconds=staleness)

                if pair is None:
                    fvs1.append(None)
                    fvs3.append(None)
                    continue
                margin, total = pair[0] - pair[1], pair[0] + pair[1]
                common = {"market_type": mtype, "line": line, "margin": margin,
                          "total_so_far": total,
                          "winner_mid": data.winner_mid}

                f1 = (estimate_fv(**common,
                                  minutes_left=v1_clock.minutes_left,
                                  params=v1_params)
                      if v1_clock.usable else None)

                # v3a: the exact clock when fresh and in regulation; v1's
                # estimator otherwise (fallback, counted). OT: no registered
                # model — v3a abstains too, and the count says how much OT
                # pricing would be worth registering.
                if exact is not None and not exact.is_overtime:
                    f3 = estimate_fv(**common,
                                     minutes_left=exact.minutes_left,
                                     params=v1_params)
                elif exact is not None and exact.is_overtime:
                    f3 = None
                    r.ot_ticks_unpriced += 1
                elif v1_clock.usable:
                    f3 = estimate_fv(**common,
                                     minutes_left=v1_clock.minutes_left,
                                     params=v1_params)
                    r.fallback_ticks += 1
                else:
                    f3 = None
                fvs1.append(f1)
                fvs3.append(f3)

                if f1 is not None and f3 is not None:
                    b1 = (f1 - outcome) ** 2
                    b3 = (f3 - outcome) ** 2
                    r.brier_v1 += b1
                    r.brier_v3 += b3
                    r.n_points += 1
                    game_diffs.append(b1 - b3)
                if f1 is None and f3 is not None:
                    r.coverage_ticks += 1
                    r.coverage_brier_sum += (f3 - outcome) ** 2
                if (exact is not None and not exact.is_overtime
                        and v1_clock.usable):
                    r.clock_disagreement.append(
                        v1_clock.minutes_left - exact.minutes_left)
                if (mtype == MARKET_WINNER and f1 is not None
                        and f3 is not None):
                    wp_row = wp_ptr.at(tick.at)
                    if wp_row is not None:
                        p_home = float(wp_row[1])
                        p_first = p_home if sig.first_is_home else 1.0 - p_home
                        r.wp_points += 1
                        r.wp_brier_espn += (p_first - outcome) ** 2
                        r.wp_brier_v1 += (f1 - outcome) ** 2
                        r.wp_brier_v3 += (f3 - outcome) ** 2

            for arm_name, fvs in (("v1", fvs1), ("v3", fvs3)):
                sim = simulate_market(ticks, fvs, outcome,
                                      min_edge=CONFIG.min_edge_threshold)
                agg = r.sim[arm_name]
                agg.n_entries += sim.n_entries
                agg.n_entry_fills += sim.n_entry_fills
                agg.n_round_trips += sim.n_round_trips
                agg.n_rides += sim.n_rides
                agg.rois.extend(sim.rois)
                if sim.rois:
                    r.roi_by_game[arm_name][ev].extend(sim.rois)

        if game_diffs:
            r.brier_diff_by_game[ev] = game_diffs
    return r


def format_v3(r: V3Result) -> str:
    out: list[str] = []
    add = out.append
    add("PULSE v1 vs v3a (exact clock) — signal-covered games only")
    add("=" * 78)
    add("Protocol: docs/math/pulse-v3-protocol.md, registered 2026-08-20 at")
    add(f"n=2 signal games. Floors: >= {FLOOR_V3_GAMES} games AND >= "
        f"{FLOOR_V3_POINTS:,} paired points. Positive diff favours v3a.")
    add("v3b (pace-totals) and v3c (splits-sigma) are NOT implemented: their")
    add("model forms are unregistered, and this eval will not invent them.")
    add("")
    add(f"signal-covered games          : {r.n_events_with_signals}"
        + (f"   (join-excluded: {r.n_join_excluded})" if r.n_join_excluded else ""))
    add(f"paired calibration points     : {r.n_points:,}")
    if r.n_points:
        add(f"Brier v1: {r.brier_v1 / r.n_points:.5f}   "
            f"Brier v3a: {r.brier_v3 / r.n_points:.5f}")
        cm = clustered_mean(r.brier_diff_by_game)
        if cm is not None:
            add(f"paired diff (v1−v3a), clustered: {cm.mean:+.5f}  "
                f"95% CI [{cm.lo:+.5f}, {cm.hi:+.5f}]  (G={cm.n_clusters})")
    add(f"coverage gain (v1 suppressed, v3a priced): {r.coverage_ticks:,} ticks"
        + (f", Brier {r.coverage_brier_sum / r.coverage_ticks:.5f}"
           if r.coverage_ticks else ""))
    add(f"OT ticks unpriced by both (no registered OT model): "
        f"{r.ot_ticks_unpriced:,}")
    add(f"stale-clock fallback ticks    : {r.fallback_ticks:,}")
    if r.clock_disagreement:
        s = sorted(r.clock_disagreement)
        n = len(s)
        add(f"clock disagreement (est−exact minutes): n={n:,}  "
            f"p50={s[n // 2]:+.2f}  p90={s[int(n * 0.9)]:+.2f}  "
            f"max={max(s, key=abs):+.2f}")
    if r.wp_points:
        add(f"ESPN WP reference (matched winner ticks, n={r.wp_points:,}): "
            f"espn {r.wp_brier_espn / r.wp_points:.5f} | "
            f"v1 {r.wp_brier_v1 / r.wp_points:.5f} | "
            f"v3a {r.wp_brier_v3 / r.wp_points:.5f}")
    for arm in ("v1", "v3"):
        s = r.sim[arm]
        n_g = len(r.roi_by_game[arm])
        line = (f"[{arm}] entries {s.n_entries:,} | fills {s.n_entry_fills:,} "
                f"| trips {s.n_round_trips:,} | rides {s.n_rides:,} "
                f"| games {n_g}")
        cm = clustered_mean(r.roi_by_game[arm])
        if cm is not None and r.at_floor:
            line += f" | per-$ {cm.mean:+.4f} [{cm.lo:+.4f}, {cm.hi:+.4f}]"
        elif cm is not None:
            line += " | BELOW FLOORS — counts only"
        add(line)
    td = r.trading_diff
    if td is not None and r.at_floor:
        add(f"paired trading diff (v3a−v1), game means: {td.mean:+.4f}  "
            f"95% CI [{td.lo:+.4f}, {td.hi:+.4f}]  (G={td.n_clusters}) — "
            "the second registered clause")
    add("")
    add(f"VERDICT: {r.verdict}"
        + ("" if r.at_floor else
           f" — floors are {FLOOR_V3_GAMES} games / {FLOOR_V3_POINTS:,} "
           "points. Counts only; accruing is the honest state."))
    return "\n".join(out)


# --------------------------------------------------------------------- #
# The EV stop (ledger #9): paired old-rule vs new-rule trading comparison
# --------------------------------------------------------------------- #

#: The EV-stop registration's timestamp — its floors count only games first
#: recorded after this instant (docs/math/pulse-ev-stop.md).
EV_STOP_REGISTERED_AT = "2026-08-24T23:00:00+00:00"
FLOOR_EV_GAMES = 10
FLOOR_EV_FILLS = 100


def evaluate_ev_stop(Session, *, limit: int | None = None) -> str:
    """Same estimates (the v3a arm — the stop comparison is orthogonal to
    the estimate set by construction), two sims per market differing only
    in the stop rule; paired per-game trading diff. Post-registration games
    gate; earlier games print as a labelled backtest, never gating."""
    from strategies.wnba_totals.config import CONFIG

    events = load_events(Session, limit=limit)
    signals, _ = resolve_signal_games(Session, events)
    reg_at = dt.datetime.fromisoformat(EV_STOP_REGISTERED_AT)

    cohorts = {"gate": {"roi": {"adverse": defaultdict(list),
                                "ev": defaultdict(list)},
                        "fills": {"adverse": 0, "ev": 0}},
               "backtest": {"roi": {"adverse": defaultdict(list),
                                    "ev": defaultdict(list)},
                            "fills": {"adverse": 0, "ev": 0}}}

    for data in events:
        sig_data = signals.get(data.event_slug)
        if sig_data is None:
            continue
        first_seen = (sig_data.clock_rows[0][0]
                      if sig_data.clock_rows else None)
        cohort = cohorts["gate" if (first_seen is not None
                                    and first_seen > reg_at) else "backtest"]
        v1p, _ = arm_params(data)
        for mtype, line, ticks in data.markets.values():
            outcome = market_outcome(mtype, line, data.final_score)
            if outcome is None:
                continue
            clock_ptr = _SeriesPointer(sig_data.clock_rows)
            fvs: list[float | None] = []
            for tick in ticks:
                pair = parse_score(tick.score)
                row = clock_ptr.at(tick.at)
                if pair is None or row is None:
                    fvs.append(None)
                    continue
                from core.pulse.signals import exact_clock
                exact = exact_clock(int(row[1]), float(row[2]))
                if exact.is_overtime or exact.minutes_left <= 0:
                    fvs.append(None)
                    continue
                fvs.append(estimate_fv(
                    market_type=mtype, line=line, margin=pair[0] - pair[1],
                    total_so_far=pair[0] + pair[1],
                    minutes_left=exact.minutes_left,
                    winner_mid=data.winner_mid, params=v1p))
            for rule in ("adverse", "ev"):
                sim = simulate_market(ticks, fvs, outcome,
                                      min_edge=CONFIG.min_edge_threshold,
                                      stop_rule=rule)
                cohort["fills"][rule] += sim.n_entry_fills
                if sim.rois:
                    cohort["roi"][rule][data.event_slug].extend(sim.rois)

    out = ["EV STOP (#9) — paired old-rule vs new-rule, registered gate",
           "=" * 70]
    for label, c in cohorts.items():
        n_games = len(set(c["roi"]["adverse"]) | set(c["roi"]["ev"]))
        diffs = {}
        for ev in set(c["roi"]["adverse"]) & set(c["roi"]["ev"]):
            a = c["roi"]["adverse"][ev]
            e = c["roi"]["ev"][ev]
            diffs[ev] = [sum(e) / len(e) - sum(a) / len(a)]
        cm = clustered_mean(diffs)
        line = (f"[{label}] games {n_games} | fills adverse "
                f"{c['fills']['adverse']:,} / ev {c['fills']['ev']:,}")
        at_floor = (label == "gate"
                    and n_games >= FLOOR_EV_GAMES
                    and c["fills"]["ev"] >= FLOOR_EV_FILLS)
        if cm is not None and (at_floor or label == "backtest"):
            tag = "" if label == "gate" else "  (BACKTEST — never gates)"
            line += (f" | paired diff (ev−adverse) {cm.mean:+.4f} "
                     f"[{cm.lo:+.4f}, {cm.hi:+.4f}] G={cm.n_clusters}{tag}")
        out.append(line)
        if label == "gate" and not at_floor:
            out.append(f"  VERDICT: NO DATA — floors {FLOOR_EV_GAMES} "
                       f"post-registration games / {FLOOR_EV_FILLS} ev fills.")
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
    parser.add_argument("--v3", action="store_true",
                        help="v1 vs v3a (exact clock) over signal-covered "
                             "games — docs/math/pulse-v3-protocol.md")
    parser.add_argument("--ev-stop", dest="ev_stop", action="store_true",
                        help="paired old-stop vs EV-stop trading comparison "
                             "— docs/math/pulse-ev-stop.md")
    parser.add_argument("--json", dest="json_path", default=None)
    args = parser.parse_args()

    Session = _read_only_sessionmaker(args.url)
    if args.league_baseline:
        print(league_baseline(Session))
        return 0
    if args.fit_blend:
        print(fit_blend(Session))
        return 0
    if args.v3:
        print(format_v3(evaluate_v3(Session, limit=args.limit)))
        return 0
    if args.ev_stop:
        print(evaluate_ev_stop(Session, limit=args.limit))
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
