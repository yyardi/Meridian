"""The PULSE live engine: the in-game shadow decision loop.

What it is
----------
Everything this system has shadow-traded so far was decided PREGAME by the
anchor model; the deep-dive page proves it (11,273 of 11,283 decisions before
tip). This engine is the missing half: it consumes the local 200ms tick
stream **during** games and emits shadow decisions — limit entries, limit
exits, throttled holds — with the full game state attached to every one.
Rows land in ``pulse_decisions`` (`core/pulse/storage.py`), keyed the same
way as the game tape, so "decided in-play" is a join, not an aspiration.

**No order exists anywhere in this module and none can.** There is no import
path to ``core.executor`` or any venue-writing client — pinned by an
AST-level test, the same structural guarantee the quote engine carries. The
only network touch is the public settlement endpoint, explicit answers only.
Sizing reads the venue's real balance from ``account_balances`` (PR #11) and
**never fetches**: a missing or stale reading refuses entries rather than
inventing a bankroll.

The three live estimates
------------------------
Computed fresh from each market's newest tick, every cycle:

* **Winner** — the anchored win curve (`core/pulse/win_curve.py`, rendered by
  `core/live_fv.py`): ``Phi((margin + E·t/40) / (sigma·sqrt(t)))`` with the
  pregame price carried forward. The formula the live-FV strip shows; here it
  is finally wired to a decision loop.
* **Total** — the tempo projection (`core/live_totals_fv.py`): the pregame v4
  ladder anchor moved by a *fraction* of the scoring surprise, never raw pace,
  with the fitted per-period residual sd. Positioned against every recorded
  rung of the ladder.
* **Spread** — the win curve's own margin model evaluated at the rung:
  ``P(final margin + line > 0)``. The YES frame was verified against the
  recorded stream itself (2026-08-18): taking each event's true final score
  from its FT ticks and each spread market's last decisively-priced Q4 book,
  **196/196** markets agree that YES settles 1 iff the first team's final
  margin plus the stored line is positive; the same method reproduces the
  V19 winner frame 37/37. Every spread line in the data is a half-point;
  whole-number lines (push semantics unverified) are refused, not guessed.

Position management, the operator's model
-----------------------------------------
"Capitalize repeatedly during the game, don't hold to settlement." Entries
are maker limits joining the touch on the side the estimate favours, sized by
fractional Kelly against the real bankroll with the game/day exposure caps.
The moment an entry fills, an exit limit rests at the profit target; when the
exit fills the position is closed and the market may be re-entered — that is
the roll. If the model's own estimate crosses back through the entry by the
stop buffer, the exit reprices to the touch instead (cut, still a limit). A
position whose exit never fills rides to settlement and is scored
money-at-price there (C11) — the honest fallback, not the plan.

The fill rule and its signed bias (inherited, stated)
-----------------------------------------------------
A resting order fills when a NEWER observation's mid crosses it — the
adverse-selection study's endpoint rule, same as the quote engine. Between
observations there is no path, so transient touches that would have filled
are invisible, and the invisible fills skew favourable-at-entry: measured
losses are trustworthy, measured profits are upper bounds and authorise
nothing. The loop reads the latest tick per market per cycle (default 1s), so
sub-cycle round trips are additionally invisible.

Scoring is not done here. `core/pulse/live_report.py` scores round trips and
ride-to-settlement legs behind the pre-registered floors
(docs/math/pulse-live.md): counts only until the floors are met. No gate is
changed by any of this.
"""

from __future__ import annotations

import datetime as dt
import math
import os
import threading
import time
from dataclasses import dataclass, field

import structlog
from scipy import stats
from sqlalchemy import text

from core import heartbeat as hb
from core.bankroll import BankrollUnavailable
from core.kelly_sizing import Constraint, size_position
from core.live_fv import DEFAULT_SIGMA, Clock, fair_value, minutes_remaining, parse_score
from core.live_totals_fv import over_probability, project_total, remaining_sigma
from core.pulse.storage import (
    ENTER,
    EXIT,
    HOLD,
    IN_PLAY,
    NO,
    PREGAME,
    STRAT_SPREAD,
    STRAT_TOTAL,
    STRAT_WINNER,
    YES,
    PulseDecision,
)
from core.pulse.win_curve import REGULATION_MINUTES, pregame_margin_from_price

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc

#: Heartbeat service name. Defined here rather than in core/heartbeat.py's
#: APP_DB_SERVICES, deliberately (the quote engine's precedent): a service in
#: the roster reads DEAD on every host where it is not deployed, and this
#: deploy is operator-gated between slates. Add to the roster when the
#: overlay actually runs (docs/math/pulse-live.md, ops notes).
SERVICE_PULSE = "pulse_engine"

#: Venue market-type strings, restated (the other modules that define them —
#: core/executor.py among others — are exactly what this module must not
#: import).
MARKET_WINNER = "basketball_team_full_game_winner"
MARKET_TOTAL = "basketball_team_full_game_total"
MARKET_SPREAD = "basketball_team_full_game_spread"

#: Which estimate set prices decisions. 'v1' is the informationally-thin
#: baseline (pregame price + score/clock + the league constant sigma); 'v2'
#: adds the point-in-time inputs from `core/pulse/team_form.py` — per-matchup
#: fitted volatility and the (currently weight-1.0, by measurement) blended
#: totals anchor. v2 components REFUSE stale form and fall back to the v1
#: values; every decision row records which set actually priced it, so the
#: two model generations never blend in a performance query (the
#: era-separation lesson).
ESTIMATES_V1 = "v1"
ESTIMATES_V2 = "v2"
DEFAULT_ESTIMATES_VERSION = os.environ.get("MERIDIAN_PULSE_ESTIMATES", ESTIMATES_V1)

#: Cycle cadence. The tick stream is 200ms; 1s reads every market's newest
#: tick without re-walking the stream, and the fill rule is endpoint-based
#: either way (sub-cycle touches are invisible, see the module docstring).
DEFAULT_INTERVAL_SECONDS = float(os.environ.get("MERIDIAN_PULSE_INTERVAL_SECONDS", "1"))
DEFAULT_SETTLE_EVERY_SECONDS = float(
    os.environ.get("MERIDIAN_PULSE_SETTLE_EVERY_SECONDS", "600"))
#: Profit target, in YES-frame cents, for the exit that rests the moment an
#: entry fills. In-game moneylines travel ~37c peak-to-trough; 5c is a target
#: a tight game crosses many times (the roll), not a hold-to-settlement bet.
DEFAULT_PROFIT_TARGET = float(os.environ.get("MERIDIAN_PULSE_PROFIT_TARGET", "0.05"))
#: If the model's own estimate moves against the position by this much from
#: the entry price, the exit reprices to the touch (a cut, still a limit).
DEFAULT_STOP_ADVERSE = float(os.environ.get("MERIDIAN_PULSE_STOP_ADVERSE", "0.10"))
#: While a position is open, a hold row is emitted at most this often — the
#: in-game trail on the tape without a row per tick.
DEFAULT_HOLD_LOG_SECONDS = float(os.environ.get("MERIDIAN_PULSE_HOLD_LOG_SECONDS", "60"))
#: At most this many open positions (or resting entries) per event. The
#: dollar correlation is Kelly's game cap; this keeps the count sane on a
#: 9-rung ladder where every rung can show the same edge.
DEFAULT_MAX_OPEN_PER_EVENT = int(os.environ.get("MERIDIAN_PULSE_MAX_OPEN_PER_EVENT", "3"))

#: Only observations this fresh may trigger fills or decisions. The stream
#: writes 5/s per market in-game; 60s of silence means the recorder is not
#: recording, and a "fill" against a dead stream is fiction.
MAX_OBSERVATION_AGE_SECONDS = 60.0
#: A resting ENTRY in a market that left the live set is withdrawn after this
#: long unseen. Short: an entry decision belongs to a stream that exists.
ENTRY_UNSEEN_WITHDRAW_SECONDS = 120.0
#: A POSITION in a market unseen this long stops being managed: its exit is
#: withdrawn and the entry rides to settlement (scored there, C11). Longer
#: than the entry grace so a stream hiccup does not orphan a live position.
POSITION_UNSEEN_RIDE_SECONDS = 900.0
#: Filled entries younger than this are not asked about at settlement.
MIN_SETTLE_AGE_HOURS = 4.0
#: How often the pregame anchors (winner mid, v4 totals mu) are re-read for
#: events that do not have one yet. Anchors are pregame quantities; once
#: found they are pinned for the life of the process.
ANCHOR_REFRESH_SECONDS = 300.0
#: Sizing band: no entry whose YES mid sits outside it (a book at 0.97 has
#: nothing left to capture before the price ceiling), and no entry into a
#: spread wider than the quotable band's own cap.
MIN_MID, MAX_MID = 0.05, 0.95
MAX_SPREAD = 0.15
#: Bankroll readings older than this refuse entries (the scheduler's poller
#: writes every ~20 minutes; see core/bankroll.py).
BANKROLL_MAX_AGE_SECONDS = 1800.0
#: A live market whose edge sizes to ZERO warns at most this often per
#: market — the 2026-08-20 starvation was invisible precisely because this
#: skip was silent.
SIZED_ZERO_LOG_SECONDS = 300.0
#: Shadow sizing semantics (operator decision, 2026-08-21): exposure caps
#: ANNOTATE, never bind — see _maybe_enter. "1" restores live-faithful
#: enforcement (the future live mode; release-on-return still governs the
#: committed-money counter either way).
DEFAULT_ENFORCE_CAPS = os.environ.get("MERIDIAN_PULSE_ENFORCE_CAPS", "0") == "1"
#: The exposure caps — the constraints that annotate rather than bind in
#: shadow. Model-intent gates (no edge / under threshold) and venue realities
#: (min bankroll, min trade qty on the DESIRED size) are deliberately absent.
_EXPOSURE_CAPS = frozenset({
    Constraint.MAX_POSITION_PCT,
    Constraint.MAX_GAME_PCT,
    Constraint.MAX_DAILY_PCT,
    Constraint.MAX_DOLLARS,
})


def spread_fair_value(
    *,
    margin: int,
    minutes_left: float,
    line: float,
    pregame_price: float | None,
    sigma: float = DEFAULT_SIGMA,
) -> float | None:
    """P(first team's final margin + line > 0) — the YES side of a spread rung.

    The winner curve's own margin model evaluated away from zero: expected
    final margin is the current margin plus the pregame edge decayed by time
    remaining, and the remaining-margin sd is ``sigma * sqrt(minutes_left)``
    (a MARGIN sigma — correct here, unlike for totals, see
    core/live_totals_fv.py).

    Frame verified 2026-08-18 against the recorded stream: 196/196 decisively
    priced spread books agree with the venue's own FT finals under this rule
    (module docstring). Whole-number lines are refused — every observed line
    is a half-point, so ``margin + line == 0`` has never been observable and
    push semantics would be a guess.

    Returns None without a pregame price, for the same reason the winner FV
    does: a 50/50 prior between unequal teams is a wrong prior, not a neutral
    one.
    """
    if pregame_price is None:
        return None
    if float(line) == int(line):
        return None                    # whole-number line: push semantics unverified
    edge = pregame_margin_from_price(pregame_price, sigma)
    expected = margin + edge * (minutes_left / REGULATION_MINUTES) + line
    if minutes_left <= 0:
        return 1.0 if expected > 0 else (0.0 if expected < 0 else 0.5)
    return float(stats.norm.cdf(expected / (sigma * math.sqrt(minutes_left))))


# --------------------------------------------------------------------- #
# In-memory state
# --------------------------------------------------------------------- #


@dataclass(frozen=True)
class Observation:
    """One live market's newest tick."""

    market_slug: str
    event_slug: str
    game_id: str | None
    sports_market_type: str
    line: float | None
    captured_at: dt.datetime
    bid: float
    ask: float
    is_live: bool
    event_score: str | None
    event_period: str | None
    min_trade_qty: float | None

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread(self) -> float:
        return self.ask - self.bid


@dataclass(frozen=True)
class Estimate:
    """The live model state for one market at one observation."""

    strategy: str
    fair_value: float | None          # P(YES), or None when unpriceable
    clock: Clock
    score: str | None
    margin: int | None
    total_so_far: int | None
    projected_total: float | None
    total_sigma: float | None
    note: str | None = None
    #: Which estimate set actually priced this — 'v2' only when a v2 input
    #: (matchup sigma, blended anchor) fed the number; a v2-mode engine whose
    #: form refused still prices with v1 values and says so.
    version: str = ESTIMATES_V1


@dataclass
class RestingOrder:
    """A simulated limit order. YES frame; `buys_yes` decides the fill sign."""

    decision_id: int
    limit_price: float
    contracts: float
    buys_yes: bool                    # True: fills when mid <= limit; else mid >= limit
    placed_at: dt.datetime            # the observation it was born from

    def fills_at(self, ob: Observation) -> bool:
        if ob.captured_at <= self.placed_at:
            return False              # never filled by the tick it was born from
        return ob.mid <= self.limit_price if self.buys_yes else ob.mid >= self.limit_price


@dataclass
class OpenPosition:
    entry_decision_id: int
    side: str                         # 'yes' | 'no'
    strategy: str
    entry_price: float                # YES frame
    contracts: float
    stake_usd: float
    opened_at: dt.datetime
    exit_order: RestingOrder | None = None
    exit_is_stop: bool = False
    last_hold_monotonic: float = field(default_factory=time.monotonic)


@dataclass
class MarketState:
    event_slug: str | None = None
    entry_order: RestingOrder | None = None
    entry_side: str | None = None
    entry_strategy: str | None = None
    entry_stake: float = 0.0
    position: OpenPosition | None = None
    last_seen_monotonic: float = field(default_factory=time.monotonic)


@dataclass
class CycleResult:
    observed: int = 0
    decisions: int = 0
    entries: int = 0
    entry_fills: int = 0
    exit_fills: int = 0
    withdrawals: int = 0
    settled: int = 0


@dataclass(frozen=True)
class EventAnchors:
    winner_mid: float | None = None   # pregame moneyline mid, YES frame
    totals_mu: float | None = None    # v4 ladder-fitted pregame projected total
    #: v2 inputs (core/pulse/team_form.py), None when form refused or v1 mode.
    matchup_sigma: float | None = None
    totals_mu_v2: float | None = None


# --------------------------------------------------------------------- #
# The engine
# --------------------------------------------------------------------- #


class PulseEngine:
    """The loop. Reads the tick stream; writes `pulse_decisions` rows and one
    heartbeat, all into its own database. Nothing else, structurally."""

    def __init__(
        self,
        sessionmaker,
        *,
        interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
        settle_every_seconds: float = DEFAULT_SETTLE_EVERY_SECONDS,
        profit_target: float = DEFAULT_PROFIT_TARGET,
        stop_adverse: float = DEFAULT_STOP_ADVERSE,
        hold_log_seconds: float = DEFAULT_HOLD_LOG_SECONDS,
        max_open_per_event: int = DEFAULT_MAX_OPEN_PER_EVENT,
        sigma: float = DEFAULT_SIGMA,
        estimates_version: str = DEFAULT_ESTIMATES_VERSION,
        enforce_caps: bool = DEFAULT_ENFORCE_CAPS,
        settlement_lookup=None,
        bankroll_reader=None,
    ) -> None:
        self._Session = sessionmaker
        self.interval_seconds = interval_seconds
        self.settle_every_seconds = settle_every_seconds
        self.profit_target = profit_target
        self.stop_adverse = stop_adverse
        self.hold_log_seconds = hold_log_seconds
        self.max_open_per_event = max_open_per_event
        self.sigma = sigma
        self.estimates_version = estimates_version
        self.enforce_caps = enforce_caps
        from strategies.wnba_totals.config import CONFIG
        #: The fractional-Kelly haircut the desired size uses — the config's
        #: own, so shadow intent and live sizing share one definition.
        self._kelly_fraction = CONFIG.kelly_fraction
        #: slug -> 0|1|None. Production asks the PUBLIC gateway; tests inject.
        self._settlement_lookup = settlement_lookup or self._venue_settlement
        #: () -> float|None. Production reads stored account_balances rows and
        #: NEVER fetches; tests inject. None refuses entries.
        self._bankroll_reader = bankroll_reader or self._stored_bankroll
        self._markets: dict[str, MarketState] = {}
        self._anchors: dict[str, EventAnchors] = {}
        self._period_starts: dict[tuple[str, str], dt.datetime] = {}
        self._period_starts_loaded = False
        self._last_anchor_refresh = float("-inf")
        self._last_settle = float("-inf")
        self._daily_day: dt.date | None = None
        self._daily_staked = 0.0
        #: market -> monotonic instant of the last sized-to-zero warning.
        self._sized_zero_logged: dict[str, float] = {}
        self._heartbeat = hb.Heartbeat(sessionmaker, SERVICE_PULSE)
        self._stop = threading.Event()

    # ---- data in ---------------------------------------------------------- #

    def _observations(self, session) -> list[Observation]:
        rows = session.execute(text("""
            SELECT DISTINCT ON (market_slug)
                   market_slug, event_slug, game_id, sports_market_type, line,
                   captured_at, best_bid, best_ask, is_live, event_score,
                   event_period, min_trade_qty
            FROM market_snapshots
            WHERE is_live IS TRUE
              AND event_slug IS NOT NULL
              AND sports_market_type IN (:w, :t, :s)
              AND best_bid IS NOT NULL AND best_ask IS NOT NULL
              AND captured_at > now() - make_interval(secs => :age)
            ORDER BY market_slug, captured_at DESC
        """), {
            "w": MARKET_WINNER, "t": MARKET_TOTAL, "s": MARKET_SPREAD,
            "age": MAX_OBSERVATION_AGE_SECONDS,
        }).all()
        out = []
        for r in rows:
            bid, ask = float(r.best_bid), float(r.best_ask)
            if ask <= bid:
                continue                       # crossed/locked book
            out.append(Observation(
                market_slug=r.market_slug, event_slug=r.event_slug,
                game_id=None if r.game_id is None else str(r.game_id),
                sports_market_type=r.sports_market_type,
                line=None if r.line is None else float(r.line),
                captured_at=r.captured_at, bid=bid, ask=ask,
                is_live=bool(r.is_live),
                event_score=r.event_score, event_period=r.event_period,
                min_trade_qty=None if r.min_trade_qty is None else float(r.min_trade_qty),
            ))
        return out

    def _load_period_starts(self, session) -> None:
        """First sighting of each (event, period), across engine restarts.

        Without this, a restart mid-Q3 would reset the period clock to zero
        and overstate minutes remaining by up to a whole quarter.
        """
        rows = session.execute(text("""
            SELECT event_slug, event_period, min(captured_at) AS first_seen
            FROM market_snapshots
            WHERE is_live IS TRUE AND event_period IS NOT NULL
              AND captured_at > now() - make_interval(hours => 12)
            GROUP BY event_slug, event_period
        """)).all()
        for r in rows:
            self._period_starts[(r.event_slug, r.event_period)] = r.first_seen
        self._period_starts_loaded = True

    def _refresh_anchors(self, session, events: set[str]) -> None:
        """Pregame anchors per event: winner mid and v4 totals mu.

        Pregame quantities — pinned once found. Only events still missing one
        are re-queried, at most every ANCHOR_REFRESH_SECONDS.
        """
        want_v2 = self.estimates_version == ESTIMATES_V2
        missing = [e for e in events
                   if e not in self._anchors
                   or self._anchors[e].winner_mid is None
                   or self._anchors[e].totals_mu is None
                   or (want_v2 and self._anchors[e].matchup_sigma is None)]
        if not missing:
            return
        if time.monotonic() - self._last_anchor_refresh < ANCHOR_REFRESH_SECONDS:
            return
        self._last_anchor_refresh = time.monotonic()

        winner: dict[str, float] = {
            r.event_slug: (float(r.best_bid) + float(r.best_ask)) / 2.0
            for r in session.execute(text("""
                SELECT DISTINCT ON (event_slug) event_slug, best_bid, best_ask
                FROM market_snapshots
                WHERE sports_market_type = :w
                  AND is_live IS FALSE AND event_score = '0-0'
                  AND best_bid IS NOT NULL AND best_ask IS NOT NULL
                  AND best_ask > best_bid
                  AND event_slug = ANY(:slugs)
                ORDER BY event_slug, captured_at DESC
            """), {"w": MARKET_WINNER, "slugs": missing}).all()
        }
        try:
            from core.live_totals_fv import pregame_totals_anchor
            totals = {e: mu for e, mu in pregame_totals_anchor(session).items()
                      if e in set(missing)}
        except Exception as exc:       # a broken ladder fit must not stop winners
            log.warning("pulse_totals_anchor_failed", error=str(exc)[:200])
            totals = {}
        for e in missing:
            prior = self._anchors.get(e, EventAnchors())
            winner_mid = prior.winner_mid or winner.get(e)
            totals_mu = prior.totals_mu or totals.get(e)
            matchup_sigma = prior.matchup_sigma
            totals_mu_v2 = prior.totals_mu_v2
            if want_v2 and matchup_sigma is None:
                # Point-in-time trivially: the logs hold only completed past
                # games. Stale form returns None and the estimate stays v1 —
                # a refusal with a log line, never a silent degrade.
                from core.pulse.team_form import (
                    blended_total_anchor,
                    event_team_abbrevs,
                    matchup_form,
                )
                abbrevs = event_team_abbrevs(e)
                if abbrevs is not None:
                    form = matchup_form(
                        session, first_abbrev=abbrevs[0],
                        second_abbrev=abbrevs[1],
                        as_of=dt.datetime.now(UTC))
                    if form is not None:
                        matchup_sigma = form.sigma
                        totals_mu_v2 = blended_total_anchor(totals_mu, form)
                        log.info("pulse_v2_form", event_slug=e,
                                 sigma=round(form.sigma, 3),
                                 sigma_multiplier=round(form.sigma_multiplier, 3),
                                 form_total=round(form.form_total, 1),
                                 staleness_days=round(form.staleness_days, 1))
            self._anchors[e] = EventAnchors(
                winner_mid=winner_mid,
                totals_mu=totals_mu,
                matchup_sigma=matchup_sigma,
                totals_mu_v2=totals_mu_v2,
            )

    def _stored_bankroll(self) -> float | None:
        """The newest stored account reading, never a fetch, never a default.

        `allow_fetch=False` is the structural half: this loop must not hold
        credentials and must not touch the venue for sizing. A missing or
        stale reading returns None and the loop refuses entries.
        """
        from core import bankroll
        try:
            snapshot = bankroll.current(
                allow_fetch=False, max_age_seconds=BANKROLL_MAX_AGE_SECONDS,
                Session=self._Session)
            return float(snapshot.bankroll)
        except BankrollUnavailable as exc:
            log.warning("pulse_bankroll_unavailable", error=str(exc)[:150])
            return None

    # ---- estimates -------------------------------------------------------- #

    def _clock_for(self, ob: Observation) -> Clock:
        started = self._period_starts.get((ob.event_slug, ob.event_period or ""))
        seconds_in = (
            (ob.captured_at - started).total_seconds() if started is not None else 0.0
        )
        return minutes_remaining(ob.event_period, seconds_into_period=max(seconds_in, 0.0))

    def _estimate(self, ob: Observation) -> Estimate:
        anchors = self._anchors.get(ob.event_slug, EventAnchors())
        clock = self._clock_for(ob)
        pair = parse_score(ob.event_score)
        margin = None if pair is None else pair[0] - pair[1]
        total_so_far = None if pair is None else pair[0] + pair[1]

        strategy = {MARKET_WINNER: STRAT_WINNER, MARKET_TOTAL: STRAT_TOTAL,
                    MARKET_SPREAD: STRAT_SPREAD}[ob.sports_market_type]
        fv = projected = sigma_t = None
        note = clock.note

        # v2 inputs, where the form allowed them; the version label records
        # what actually priced the number, not what mode the engine ran in.
        version = ESTIMATES_V1
        sigma = self.sigma
        totals_mu = anchors.totals_mu
        if self.estimates_version == ESTIMATES_V2:
            if (strategy in (STRAT_WINNER, STRAT_SPREAD)
                    and anchors.matchup_sigma is not None):
                sigma = anchors.matchup_sigma
                version = ESTIMATES_V2
            elif strategy == STRAT_TOTAL and anchors.totals_mu_v2 is not None:
                totals_mu = anchors.totals_mu_v2
                version = ESTIMATES_V2

        if pair is None:
            note = "no score on the tick — no estimate"
        elif not clock.usable:
            pass                       # suppressed, not approximated (live_fv's rule)
        elif strategy == STRAT_WINNER:
            fv = fair_value(margin=margin, minutes_left=clock.minutes_left,
                            pregame_price=anchors.winner_mid, sigma=sigma)
            if anchors.winner_mid is None:
                note = "no pregame quote — no fair value"
        elif strategy == STRAT_TOTAL:
            if ob.line is None or totals_mu is None:
                note = "no v4 pregame ladder — no anchor" if ob.line is not None else note
            else:
                elapsed = REGULATION_MINUTES - clock.minutes_left
                projected = project_total(
                    pregame_mu=totals_mu, total_so_far=total_so_far,
                    elapsed_minutes=elapsed)
                sigma_t = remaining_sigma(elapsed)
                fv = over_probability(projected_total=projected,
                                      line=ob.line, sigma=sigma_t)
        elif strategy == STRAT_SPREAD:
            if ob.line is None:
                note = "spread market without a line"
            else:
                fv = spread_fair_value(
                    margin=margin, minutes_left=clock.minutes_left, line=ob.line,
                    pregame_price=anchors.winner_mid, sigma=sigma)
                if anchors.winner_mid is None:
                    note = "no pregame quote — no fair value"
                elif fv is None:
                    note = "whole-number spread line — push semantics unverified"

        return Estimate(
            strategy=strategy, fair_value=fv, clock=clock,
            score=ob.event_score, margin=margin, total_so_far=total_so_far,
            projected_total=projected, total_sigma=sigma_t, note=note,
            version=version,
        )

    # ---- decision rows ---------------------------------------------------- #

    def _decision_row(
        self, ob: Observation, est: Estimate, *,
        action: str, side: str, limit_price: float, contracts: float,
        stake_usd: float, bankroll: float | None, binding: str | None,
        reason: str | None, entry_id: int | None, edge_net: float | None,
        capped_stake: float | None = None, capped_contracts: float | None = None,
    ) -> PulseDecision:
        from decimal import Decimal as D

        def dec(v, q="0.0001"):
            return None if v is None else D(str(round(float(v), 4)))

        return PulseDecision(
            decided_at=ob.captured_at,
            event_slug=ob.event_slug,
            market_slug=ob.market_slug,
            game_id=ob.game_id,
            sports_market_type=ob.sports_market_type,
            line=dec(ob.line),
            strategy=est.strategy,
            phase=IN_PLAY if ob.is_live else PREGAME,
            action=action,
            side=side,
            limit_price=dec(limit_price),
            contracts=dec(contracts) or 0,
            stake_usd=dec(stake_usd) or 0,
            bankroll_usd=dec(bankroll),
            binding_constraint=binding,
            reason=reason,
            entry_id=entry_id,
            score=est.score,
            margin=est.margin,
            period=ob.event_period,
            minutes_left=dec(round(est.clock.minutes_left, 2)),
            minutes_left_is_estimate=est.clock.is_estimate,
            total_so_far=est.total_so_far,
            projected_total=dec(est.projected_total),
            total_sigma=dec(est.total_sigma),
            market_bid=dec(ob.bid),
            market_ask=dec(ob.ask),
            fair_value=dec(est.fair_value),
            edge_net=dec(edge_net),
            estimates_version=est.version,
            capped_stake_usd=dec(capped_stake),
            capped_contracts=dec(capped_contracts),
        )

    def _withdraw(self, session, decision_id: int, at: dt.datetime | None = None) -> None:
        session.execute(text("""
            UPDATE pulse_decisions SET withdrawn_at = coalesce(:at, now())
            WHERE id = :id AND withdrawn_at IS NULL
        """), {"id": decision_id, "at": at})

    def _mark_filled(self, session, decision_id: int, ob: Observation) -> None:
        session.execute(text("""
            UPDATE pulse_decisions SET filled_at = :at, mid_at_fill = :mid
            WHERE id = :id AND filled_at IS NULL
        """), {"id": decision_id, "at": ob.captured_at,
               "mid": round(ob.mid, 4)})

    # ---- exposure --------------------------------------------------------- #

    def _event_exposure(self, event_slug: str) -> tuple[int, float]:
        """(open count, dollars committed) across this event's markets —
        resting entries count as committed: the decision to risk the money
        was made when the limit was rested, not when it filled."""
        n = 0
        dollars = 0.0
        for state in self._markets.values():
            if state.event_slug != event_slug:
                continue
            pos = state.position
            if pos is not None:
                n += 1
                dollars += pos.stake_usd
            elif state.entry_order is not None:
                n += 1
                dollars += state.entry_stake
        return n, dollars

    def _note_daily_stake(self, stake: float, now: dt.datetime) -> None:
        if self._daily_day != now.date():
            self._daily_day = now.date()
            self._daily_staked = 0.0
        self._daily_staked += stake

    def _release_daily_stake(self, stake: float) -> None:
        """Money came back — an unfilled entry stood down, or a position
        closed. The daily brake meters COMMITTED money, not money-ever;
        without this release the day's FIRST game permanently exhausts the
        budget (20% of a ~$19 bankroll is ~$3.84) and every later same-UTC-day
        game sizes to zero in silence — measured on the 2026-08-20 slate,
        where ind-dal's nine entries starved the 02:00Z pair to ZERO rows.
        Rides to settlement are deliberately never released: that money is
        gone until the market pays."""
        self._daily_staked = max(self._daily_staked - stake, 0.0)

    def _daily_exposure(self, now: dt.datetime) -> float:
        if self._daily_day != now.date():
            return 0.0
        return self._daily_staked

    # ---- one market, one cycle -------------------------------------------- #

    def _check_entry_fill(self, session, state: MarketState, ob: Observation,
                          est: Estimate, result: CycleResult) -> None:
        order = state.entry_order
        if order is None or not order.fills_at(ob):
            return
        self._mark_filled(session, order.decision_id, ob)
        result.entry_fills += 1
        position = OpenPosition(
            entry_decision_id=order.decision_id,
            side=state.entry_side or (YES if order.buys_yes else NO),
            strategy=state.entry_strategy or est.strategy,
            entry_price=order.limit_price,
            contracts=order.contracts,
            stake_usd=state.entry_stake,
            opened_at=ob.captured_at,
        )
        state.entry_order = None
        state.position = position
        log.info("pulse_entry_filled", market=ob.market_slug, side=position.side,
                 price=position.entry_price, contracts=position.contracts,
                 mid_at_fill=round(ob.mid, 4))
        # The exit rests the moment the entry exists — that IS the strategy.
        self._place_exit(session, state, ob, est,
                         reason="profit_target", stop=False, result=result)

    def _place_exit(self, session, state: MarketState, ob: Observation,
                    est: Estimate, *, reason: str, stop: bool,
                    result: CycleResult) -> None:
        pos = state.position
        if pos is None:
            return
        if stop:
            # Cut at the touch on our exit side — still a limit, never a cross.
            limit = ob.ask if pos.side == YES else ob.bid
        else:
            limit = (pos.entry_price + self.profit_target if pos.side == YES
                     else pos.entry_price - self.profit_target)
        limit = min(max(limit, 0.01), 0.99)
        row = self._decision_row(
            ob, est, action=EXIT, side=pos.side, limit_price=limit,
            contracts=pos.contracts, stake_usd=0.0, bankroll=None,
            binding=None, reason=reason, entry_id=pos.entry_decision_id,
            edge_net=None,
        )
        session.add(row)
        session.flush()
        result.decisions += 1
        pos.exit_order = RestingOrder(
            decision_id=row.id, limit_price=limit, contracts=pos.contracts,
            buys_yes=(pos.side == NO),        # a NO position exits by buying YES back
            placed_at=ob.captured_at,
        )
        pos.exit_is_stop = stop
        log.info("pulse_exit_rested", market=ob.market_slug, side=pos.side,
                 limit=limit, reason=reason)

    def _check_exit_fill(self, session, state: MarketState, ob: Observation,
                         result: CycleResult) -> None:
        pos = state.position
        if pos is None or pos.exit_order is None or not pos.exit_order.fills_at(ob):
            return
        self._mark_filled(session, pos.exit_order.decision_id, ob)
        result.exit_fills += 1
        capture = (pos.exit_order.limit_price - pos.entry_price
                   if pos.side == YES else
                   pos.entry_price - pos.exit_order.limit_price)
        log.info("pulse_round_trip", market=ob.market_slug, side=pos.side,
                 entry=pos.entry_price, exit=pos.exit_order.limit_price,
                 capture_per_contract=round(capture, 4),
                 held_seconds=round((ob.captured_at - pos.opened_at).total_seconds(), 1))
        self._release_daily_stake(pos.stake_usd)   # position closed, money back
        state.position = None          # flat again — the market may be re-entered

    def _manage_position(self, session, state: MarketState, ob: Observation,
                         est: Estimate, result: CycleResult) -> None:
        pos = state.position
        if pos is None:
            return
        # Stop: the model's own estimate crossed back through the entry by the
        # buffer. Only when the estimate is currently trustworthy — a dead
        # clock does not get to panic a position (fills stay price-based).
        if (not pos.exit_is_stop and est.fair_value is not None
                and est.clock.usable):
            adverse = (pos.entry_price - est.fair_value if pos.side == YES
                       else est.fair_value - pos.entry_price)
            if adverse >= self.stop_adverse:
                if pos.exit_order is not None:
                    self._withdraw(session, pos.exit_order.decision_id,
                                   at=ob.captured_at)
                    result.withdrawals += 1
                self._place_exit(session, state, ob, est,
                                 reason="fv_adverse", stop=True, result=result)
                return
        # Throttled hold trail.
        if time.monotonic() - pos.last_hold_monotonic >= self.hold_log_seconds:
            pos.last_hold_monotonic = time.monotonic()
            exit_limit = pos.exit_order.limit_price if pos.exit_order else pos.entry_price
            row = self._decision_row(
                ob, est, action=HOLD, side=pos.side, limit_price=exit_limit,
                contracts=pos.contracts, stake_usd=0.0, bankroll=None,
                binding=None, reason="position_open",
                entry_id=pos.entry_decision_id, edge_net=None,
            )
            session.add(row)
            result.decisions += 1

    def _manage_entry(self, session, state: MarketState, ob: Observation,
                      est: Estimate, result: CycleResult) -> None:
        """A resting, unfilled entry either still has its edge or stands down.

        Registered behaviour: the limit rests where it was born — no chasing
        the touch — and is withdrawn the moment the CURRENT estimate no longer
        clears zero at that price. Withdrawn rows keep their decision context;
        `withdrawn_at` is what distinguishes "stood down" from "never filled".
        """
        order = state.entry_order
        if order is None:
            return
        fv = est.fair_value
        edge = None
        if fv is not None and est.clock.usable:
            edge = (fv - order.limit_price if state.entry_side == YES
                    else (1.0 - fv) - (1.0 - order.limit_price))
        if fv is None or not est.clock.usable or edge <= 0:
            self._withdraw(session, order.decision_id, at=ob.captured_at)
            result.withdrawals += 1
            self._release_daily_stake(state.entry_stake)   # money never left
            state.entry_order = None
            state.entry_stake = 0.0
            log.info("pulse_entry_withdrawn", market=ob.market_slug,
                     reason="estimate gone" if fv is None else "edge gone")

    def _maybe_enter(self, session, state: MarketState, ob: Observation,
                     est: Estimate, bankroll: float | None,
                     result: CycleResult) -> None:
        if state.position is not None or state.entry_order is not None:
            return
        fv = est.fair_value
        if fv is None or not est.clock.usable:
            return
        if bankroll is None:
            return                     # no real balance, no entry — never a guess
        mid = ob.mid
        if not (MIN_MID <= mid <= MAX_MID) or ob.spread > MAX_SPREAD:
            return
        n_open, dollars_open = self._event_exposure(ob.event_slug)
        # The per-event count cap: in live mode it blocks outright (before
        # sizing, as always). In shadow mode it ANNOTATES like the dollar
        # caps (operator follow-up, 2026-08-22): the entry lands at full
        # desired size with 'max_open_per_event' as the label and capped
        # size 0 — live would not have entered at all. Full intent within
        # games too: on a 9-rung ladder the 4th in-band market is exactly
        # the intent the tape used to discard.
        count_capped = n_open >= self.max_open_per_event
        if count_capped and self.enforce_caps:
            return

        side = YES if fv > mid else NO
        limit = ob.bid if side == YES else ob.ask     # join the touch, maker
        if side == YES:
            probability, cost = fv, limit
        else:
            probability, cost = 1.0 - fv, 1.0 - limit
        if not (0.01 <= cost <= 0.99):
            return

        min_qty = ob.min_trade_qty or 0.01
        sized = size_position(
            probability=probability,
            price=cost,
            bankroll=bankroll,
            is_maker=True,
            game_exposure_used=dollars_open / bankroll if bankroll > 0 else 1.0,
            daily_exposure_used=self._daily_exposure(ob.captured_at) / bankroll
            if bankroll > 0 else 1.0,
            minimum_trade_qty=min_qty,
        )

        # SHADOW SIZING SEMANTICS (operator decision, 2026-08-21): with zero
        # real dollars at stake, the shadow tape's whole purpose is the
        # complete record of the model's intent — and on 2026-08-20 the
        # daily cap silently discarded two entire games of exactly that.
        # In shadow mode (enforce_caps=False, the default), exposure caps
        # ANNOTATE instead of bind: the row carries the full desired
        # fractional-Kelly size, plus the live-faithful capped size in
        # capped_* when a cap would have bound (0 = would have blocked).
        # Model-intent gates (no edge, edge under threshold) and venue
        # realities (min bankroll, min trade qty on the DESIRED size) still
        # refuse — a cap is not a model opinion, but those are.
        entry_contracts = sized.contracts
        entry_stake = sized.dollars
        capped_stake = capped_contracts = None
        binding_label = sized.binding_constraint.value

        if not self.enforce_caps:
            binding = sized.binding_constraint
            if binding in (Constraint.NEGATIVE_EDGE, Constraint.MIN_EDGE):
                return                 # the model does not want this trade
            desired_stake = sized.kelly_fraction_raw * self._kelly_fraction * bankroll
            desired_contracts = desired_stake / cost if cost > 0 else 0.0
            if binding == Constraint.MIN_BANKROLL or desired_contracts < min_qty:
                pass                   # venue reality: fall through to the loud log
            elif count_capped:
                # The strongest statement wins: live blocks BEFORE sizing on
                # the count cap, so whatever the dollar caps said, the
                # live-faithful size is zero.
                entry_contracts, entry_stake = desired_contracts, desired_stake
                capped_stake, capped_contracts = 0.0, 0.0
                binding_label = "max_open_per_event"
            elif binding in _EXPOSURE_CAPS:
                entry_contracts, entry_stake = desired_contracts, desired_stake
                capped_stake, capped_contracts = sized.dollars, sized.contracts
            elif binding == Constraint.BELOW_MIN_TRADE_QTY:
                # The CAPPED size fell under the venue minimum but the
                # desired size did not — a cap block in disguise (the exact
                # 2026-08-20 shape once day_room hit zero).
                entry_contracts, entry_stake = desired_contracts, desired_stake
                capped_stake, capped_contracts = 0.0, 0.0
            else:                      # KELLY: caps did not bind; sizes agree
                entry_contracts, entry_stake = desired_contracts, desired_stake

        if entry_contracts < min_qty or entry_stake <= 0:
            # The 2026-08-20 lesson: a live market with real edge sized to
            # zero used to skip in total silence, and a whole slate produced
            # zero rows before anyone knew where to look. Loud, throttled.
            last = self._sized_zero_logged.get(ob.market_slug, float("-inf"))
            if time.monotonic() - last >= SIZED_ZERO_LOG_SECONDS:
                self._sized_zero_logged[ob.market_slug] = time.monotonic()
                log.warning(
                    "pulse_entry_sized_zero", market=ob.market_slug,
                    constraint=binding_label,
                    edge_net=round(sized.edge_net, 4),
                    daily_staked=round(self._daily_staked, 2),
                    bankroll=round(bankroll, 2))
            return

        row = self._decision_row(
            ob, est, action=ENTER, side=side, limit_price=limit,
            contracts=entry_contracts, stake_usd=entry_stake,
            bankroll=bankroll, binding=binding_label,
            reason=None, entry_id=None, edge_net=sized.edge_net,
            capped_stake=capped_stake, capped_contracts=capped_contracts,
        )
        session.add(row)
        session.flush()
        result.decisions += 1
        result.entries += 1
        state.entry_order = RestingOrder(
            decision_id=row.id, limit_price=limit, contracts=entry_contracts,
            buys_yes=(side == YES), placed_at=ob.captured_at,
        )
        state.entry_side = side
        state.entry_strategy = est.strategy
        state.entry_stake = entry_stake
        self._note_daily_stake(entry_stake, ob.captured_at)
        log.info("pulse_entry_rested", market=ob.market_slug, side=side,
                 limit=limit, contracts=round(entry_contracts, 2),
                 stake=round(entry_stake, 2), fv=round(fv, 4),
                 edge_net=round(sized.edge_net, 4), strategy=est.strategy,
                 capped_stake=None if capped_stake is None else round(capped_stake, 2))

    # ---- one cycle -------------------------------------------------------- #

    def cycle(self) -> CycleResult:
        """One pass over every live market. Public so tests drive it."""
        result = CycleResult()
        with self._Session() as session:
            if not self._period_starts_loaded:
                self._load_period_starts(session)
            observations = self._observations(session)
            result.observed = len(observations)

            for ob in observations:
                self._period_starts.setdefault(
                    (ob.event_slug, ob.event_period or ""), ob.captured_at)

            self._refresh_anchors(session, {ob.event_slug for ob in observations})
            bankroll = self._bankroll_reader() if observations else None

            seen: set[str] = set()
            for ob in observations:
                seen.add(ob.market_slug)
                state = self._markets.setdefault(ob.market_slug, MarketState())
                state.event_slug = ob.event_slug
                state.last_seen_monotonic = time.monotonic()
                est = self._estimate(ob)

                # Fills first, against orders that were ALREADY resting — an
                # order is never filled by the observation it was born from.
                self._check_entry_fill(session, state, ob, est, result)
                self._check_exit_fill(session, state, ob, result)

                if state.position is not None:
                    self._manage_position(session, state, ob, est, result)
                elif state.entry_order is not None:
                    self._manage_entry(session, state, ob, est, result)
                else:
                    self._maybe_enter(session, state, ob, est, bankroll, result)

            self._sweep_unseen(session, seen, result)
            session.commit()

        if time.monotonic() - self._last_settle >= self.settle_every_seconds:
            self._last_settle = time.monotonic()
            result.settled = self._settle_filled_entries()
        return result

    def _sweep_unseen(self, session, seen: set[str], result: CycleResult) -> None:
        """Markets that left the live set: withdraw entries quickly; let
        positions ride to settlement after a longer grace (game over, or the
        stream died — either way there is nothing left to manage against)."""
        now = time.monotonic()
        for slug in list(self._markets):
            if slug in seen:
                continue
            state = self._markets[slug]
            unseen = now - state.last_seen_monotonic
            if state.entry_order is not None and unseen > ENTRY_UNSEEN_WITHDRAW_SECONDS:
                self._withdraw(session, state.entry_order.decision_id)
                result.withdrawals += 1
                self._release_daily_stake(state.entry_stake)   # money never left
                state.entry_order = None
                state.entry_stake = 0.0
                log.info("pulse_entry_withdrawn", market=slug, reason="stream gone")
            if state.position is not None and unseen > POSITION_UNSEEN_RIDE_SECONDS:
                if state.position.exit_order is not None:
                    self._withdraw(session, state.position.exit_order.decision_id)
                    result.withdrawals += 1
                log.info("pulse_position_rides_to_settlement", market=slug,
                         entry_decision_id=state.position.entry_decision_id)
                state.position = None
            if state.position is None and state.entry_order is None:
                del self._markets[slug]

    # ---- settlement ------------------------------------------------------- #

    def _venue_settlement(self, market_slug: str) -> int | None:
        """The public gateway's answer, or None. Never a guess."""
        from core.polymarket.client import PolymarketGatewayClient

        try:
            with PolymarketGatewayClient() as gw:
                body = gw.get_settlement(market_slug)
            value = body.get("settlement")
            return value if value in (0, 1) else None
        except Exception as exc:
            log.warning("pulse_settlement_check_failed",
                        market=market_slug, error=str(exc)[:150])
            return None

    def _settle_filled_entries(self) -> int:
        """Mark settlement on old filled entries — the scoring basis for
        positions that never exited, and a free cross-check for those that did."""
        cutoff = dt.datetime.now(UTC) - dt.timedelta(hours=MIN_SETTLE_AGE_HOURS)
        with self._Session() as s:
            slugs = [r[0] for r in s.execute(text("""
                SELECT DISTINCT market_slug FROM pulse_decisions
                WHERE action = 'enter' AND filled_at IS NOT NULL
                  AND settlement IS NULL AND filled_at < :cutoff
            """), {"cutoff": cutoff}).all()]
        settled = 0
        for slug in slugs:
            answer = self._settlement_lookup(slug)
            if answer not in (0, 1):
                continue
            with self._Session() as s:
                s.execute(text("""
                    UPDATE pulse_decisions
                    SET settlement = :v, settled_at = now()
                    WHERE market_slug = :m AND action = 'enter'
                      AND filled_at IS NOT NULL AND settlement IS NULL
                """), {"v": answer, "m": slug})
                s.commit()
            settled += 1
            log.info("pulse_entries_settled", market=slug, settlement=answer)
        return settled

    # ---- lifecycle -------------------------------------------------------- #

    def stop(self) -> None:
        self._stop.set()

    def run_forever(self) -> None:
        log.info("pulse_engine_started",
                 interval_seconds=self.interval_seconds,
                 profit_target=self.profit_target,
                 note="shadow only — no order exists behind anything this writes")
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                result = self.cycle()
                any_live = result.observed > 0
            except Exception as exc:   # one bad cycle must not kill the run
                log.error("pulse_engine_cycle_failed", error=str(exc)[:300])
                result, any_live = CycleResult(), None
            self._heartbeat.beat(
                interval_seconds=self.interval_seconds,
                rows_written=result.decisions,
                cycle_seconds=time.monotonic() - started,
                game_live=any_live,
            )
            self._stop.wait(self.interval_seconds)


def main() -> int:
    from core.storage import get_engine, get_sessionmaker

    PulseEngine(get_sessionmaker(get_engine())).run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
