"""PULSE strategy #1 — fade the price lurch on a game's first score.

The hypothesis, and why it is the one worth building first
-----------------------------------------------------------
From live observation: *"IND jumped so much from scoring first it was
ridiculous."* Formally — the opening basket moves the price far more than its
information content justifies, and the move comes back.

This is the cleanest possible form of the overreaction family
([pulse-hypotheses.md](../../docs/pulse-hypotheses.md) #2). Two points out of a
~170-point game is close to zero information. Already measured on 787 games:
each extra Q1 point is worth **1.32** on the final total, not 4.0, and hot
starts regress about 3x. So a first basket is worth roughly 1.3 points of
final total — a rounding error against a residual sd of ~16. If the market
moves the price appreciably on it, the move is almost entirely noise, and
noise is what reverts.

It is also the strongest possible test. A null here is close to fatal for the
whole family (#1 run overreaction, #3 lead-cut, #4 late runs): if the market
does not overshoot on the single least-informative event in a game, it is
unlikely to overshoot on events that actually carry information.

Related: [`overreaction.py`](overreaction.py) asks the same question about
8-point runs and reports **NO DATA**. This is a different trigger, not a
re-test of that one, and it carries its own gate.


PRE-REGISTERED GATE — fixed before any number was computed
----------------------------------------------------------
Written 2026-08-02, prior to running this against any data.

    PASS  requires ALL of:
      (1) mean net P&L per filled trade > 0
      (2) the 95% confidence interval on that mean, clustered by game,
          lies entirely above 0
      (3) n >= 30 filled trades
      (4) those trades spread across >= 10 distinct games

    FAIL  if (3) and (4) are met but (1) or (2) is not.

    NO DATA  if (3) or (4) is not met. Zero triggers is NOT a null result.

**Why the bar is zero here and 6c in `overreaction.py`.** That module measures
raw mid reversion, so the round trip has to be subtracted afterwards and the
bar is the cost. This one measures **P&L**: entry is a maker fill at the touch,
which *earns* the half-spread, and the exit mark *pays* a half-spread. Both
costs are already inside the number, so the bar is zero. This is not a softened
gate — it is the same bar accounted for in a different place, and the exit
charge is applied at the spread observed at exit rather than at a favourable
average.

The +5 min mark is the pre-registered primary, matching `overreaction.py`.
+2 and +10 are reported as secondaries and carry **no gate** — nominating the
best of three after the fact is how a 5% test becomes a 14% one.


The trade
---------
1. Observe the market quoting while the game score is still **0-0**. That last
   quotable mid is the baseline.
2. The score becomes non-zero. Wait `REACTION_SECONDS` for the lurch to land.
3. `lurch = mid(t_score + REACTION) - baseline_mid`. Fade it:

       lurch > 0  ->  rest a limit SELL at the best ask
       lurch < 0  ->  rest a limit BUY  at the best bid

4. The order rests. `replay.py` fills it only when the book later trades
   through it, never on the tick that placed it. Unfilled after
   `ENTRY_PATIENCE_MINUTES`, it is cancelled — an order that never filled is
   not a trade and must not be counted as one.
5. Mark at the horizon:

       long  : pnl = (mid_H - fill) - spread_H / 2
       short : pnl = (fill - mid_H) - spread_H / 2

**Maker-only, structurally.** Entry is a resting limit order resolved by the
replay engine's fill rule. There is no code path here that crosses a spread.


Two honesty constraints, both structural
----------------------------------------
**The fill rule selects for continuation, and the bias is knowable.** The
engine fills a resting sell when the best *bid* rises to it — the whole book
has to come up to you. In reality a taker crosses the spread and lifts your
offer without the bid moving at all, but top-of-book snapshots cannot see a
trade, so the engine uses the conservative proxy. The consequence is specific:
we are recorded as filled mainly when the lurch **kept going**, which is the
worst case for a fade. Therefore

    a PASS from this measurement is trustworthy (real fills include the
    easy ones this proxy discards);
    a FAIL is confounded with the proxy and must not be read as "the
    phenomenon is absent".

This is the mirror image of [`adverse_selection.py`](../quote/adverse_selection.py),
whose fill rule biases the other way. To keep a FAIL diagnosable, the report
also carries an **ungated** signal-only column: the reversion after every
detected lurch whether or not it filled. If signal-only reverts and filled
trades lose, the fill proxy is the story; if neither reverts, the hypothesis is.

**The first score must be *observed*, not assumed.** A game only qualifies if
this process saw a quotable 0-0 tick before the score moved. The live recorder
starts when the board flags a game live, which is some seconds-to-minutes after
tip-off, so games whose opening basket happened before the first snapshot are
**excluded and counted**, never back-filled from the earliest score seen. The
report states how many games were dropped for this reason, because "no trades"
and "never had a first score to trade" demand different responses.


Parameters, and why none of them are fitted
-------------------------------------------
Three free parameters against a 10-game minimum, and every one is inherited
from a constant that was pre-registered elsewhere for a different study, so
none has been tuned on this question:

    REACTION_SECONDS       30s   = adverse_selection.DEFAULT_HORIZON_SECONDS
    ENTRY_PATIENCE_MINUTES 2min  = overreaction.RUN_MINUTES
    PRIMARY_HORIZON        5min  = overreaction.PRIMARY_HORIZON_MINUTES

The quotable band is imported outright rather than restated.

    python -m core.pulse.first_score
    python -m core.pulse.first_score --horizon 5
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass, field

import structlog

from core.pulse.overreaction import RUN_MINUTES
from core.pulse.replay import Order, ReplayContext, Tick, available_games, load_ticks, replay_game
from core.quote.adverse_selection import (
    DEFAULT_HORIZON_SECONDS,
    MAX_SPREAD,
    MAX_MID,
    MIN_MID,
    Cadence,
    cadence,
    clustered_mean,
    naive_mean,
)

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc

# --------------------------------------------------------------------- #
# Pre-registered constants. Every one is inherited; see the docstring.
# --------------------------------------------------------------------- #

#: How long the lurch is given to land before the fade is placed.
REACTION_SECONDS = DEFAULT_HORIZON_SECONDS

#: An entry that has not filled in this long is cancelled, not counted.
ENTRY_PATIENCE_MINUTES = RUN_MINUTES

#: Horizons the fill is marked at. The gate is on the primary only.
PRIMARY_HORIZON_MINUTES = 5.0
HORIZON_MINUTES = (2.0, 5.0, 10.0)

#: Pair a fill with the observation nearest `t+H` inside this band, so a gap in
#: the stream cannot silently become a 20-minute horizon reported as 5.
HORIZON_TOLERANCE = (0.5, 2.0)

# -- the gate --------------------------------------------------------- #
GATE_MIN_TRADES = 30
GATE_MIN_GAMES = 10


def is_quotable(tick: Tick) -> bool:
    """Would anyone rest an order here at all?

    Same band as the adverse-selection and run-overreaction studies, imported
    rather than restated: a 0.95 rung carrying a measured 22-26c spread does
    not have a 'price move', it has quote noise.
    """
    mid, spread = tick.mid, tick.spread
    if mid is None or spread is None:
        return False
    return spread <= MAX_SPREAD and MIN_MID <= mid <= MAX_MID


@dataclass
class Trade:
    """One fade: the signal, the resting order, and what it was worth."""

    game_id: str
    market_slug: str
    market_type: str | None
    baseline_mid: float
    #: How old the 0-0 quote was when the first score landed. Reported, not
    #: filtered on — see `format_report`.
    baseline_age_seconds: float
    signal_mid: float
    signal_at: dt.datetime
    side: str                        # 'buy' | 'sell'
    order: Order
    #: (mid, spread) at each horizon after the *fill*, keyed by minutes.
    after_fill: dict[float, tuple[float, float]] = field(default_factory=dict)
    #: (mid, spread) at each horizon after the *signal*, filled or not. This is
    #: the ungated diagnostic that separates "no phenomenon" from "fill proxy".
    after_signal: dict[float, tuple[float, float]] = field(default_factory=dict)
    #: |observed - target| in seconds for each mark above, so a mark can be
    #: improved as the stream approaches the target and frozen once it passes.
    fill_gap: dict[float, float] = field(default_factory=dict)
    signal_gap: dict[float, float] = field(default_factory=dict)

    @property
    def lurch(self) -> float:
        return self.signal_mid - self.baseline_mid

    @property
    def direction(self) -> float:
        """+1 if the price lurched up, -1 if down."""
        return 1.0 if self.lurch > 0 else -1.0

    @property
    def filled(self) -> bool:
        return self.order.filled_at is not None

    def pnl(self, horizon: float) -> float | None:
        """Net P&L per contract on a filled fade, exit half-spread charged."""
        if not self.filled or self.order.fill_price is None:
            return None
        mark = self.after_fill.get(horizon)
        if mark is None:
            return None
        mid_h, spread_h = mark
        gross = (
            (mid_h - self.order.fill_price)
            if self.side == "buy"
            else (self.order.fill_price - mid_h)
        )
        return gross - spread_h / 2.0

    def signal_reversion(self, horizon: float) -> float | None:
        """Ungated diagnostic: did the lurch come back, fill or no fill?

        Signed so positive always means 'it reverted', matching
        `overreaction.Run.reversion`.
        """
        mark = self.after_signal.get(horizon)
        if mark is None:
            return None
        return -self.direction * (mark[0] - self.signal_mid)


@dataclass
class _MarketState:
    """Per-market bookkeeping inside one game."""

    baseline: Tick | None = None
    trade: Trade | None = None
    done: bool = False


class FadeFirstScore:
    """The strategy. One instance per game — `replay_all` enforces that.

    Holds no state that could survive a game, which is what stops it reading
    game N's outcome out of game N+1.
    """

    def __init__(self) -> None:
        self.markets: dict[str, _MarketState] = defaultdict(_MarketState)
        self.trades: list[Trade] = []
        #: Game-level: we must *see* 0-0 before we believe a first score.
        self.saw_zero_zero = False
        self.first_score_at: dt.datetime | None = None
        self.game_id: str | None = None
        #: Why nothing happened, when nothing happened.
        self.skips: dict[str, int] = defaultdict(int)

    # -- the engine's only entry point -------------------------------- #

    def on_tick(self, tick: Tick, ctx: ReplayContext) -> None:
        if self.game_id is None:
            self.game_id = tick.event_slug

        total = tick.total_points
        if total is None:
            self.skips["tick_without_a_parseable_score"] += 1
        elif total == 0:
            self.saw_zero_zero = True
        elif self.first_score_at is None and self.saw_zero_zero:
            self.first_score_at = tick.captured_at

        state = self.markets[tick.market_slug]

        # Baseline: the last quotable mid while the game was still scoreless.
        if total == 0:
            if is_quotable(tick):
                state.baseline = tick
            return

        self._mark_open_trades(tick, ctx)

        if total is None:
            # No score on this row at all. It still carries a usable quote, so
            # it marks open trades above — but it is not evidence about whether
            # a first score was observed, and counting it as such would inflate
            # `first_score_not_observed` with rows that never had a score to
            # miss. (Measured: it doubled that counter exactly.)
            return
        if state.done or state.trade is not None:
            return
        if self.first_score_at is None:
            # Score is non-zero but we never observed 0-0: the opening basket
            # happened before this recording started. Not tradable, and not
            # silently substituted with 'the earliest score we happened to see'.
            self.skips["first_score_not_observed"] += 1
            return
        if state.baseline is None:
            self.skips["no_quotable_baseline_before_first_score"] += 1
            return

        # Let the lurch land before fading it — and refuse to fade it late.
        #
        # The upper bound is load-bearing. Without it, a rung that was
        # unquotable at tip-off and only tightened up in Q3 would have its
        # first eligible tick 40 minutes after the opening basket, and the
        # strategy would open a "fade the first score" position on a price move
        # that had nothing to do with the first score. The band is
        # `HORIZON_TOLERANCE`'s upper multiple applied to the reaction window,
        # so it introduces no new constant.
        elapsed = (tick.captured_at - self.first_score_at).total_seconds()
        if elapsed < REACTION_SECONDS:
            return
        if elapsed > REACTION_SECONDS * HORIZON_TOLERANCE[1]:
            self.skips["first_quotable_tick_came_too_late_to_be_a_reaction"] += 1
            state.done = True
            return
        if not is_quotable(tick):
            return

        self._open_fade(tick, ctx, state)

    # -- internals ---------------------------------------------------- #

    def _open_fade(self, tick: Tick, ctx: ReplayContext, state: _MarketState) -> None:
        assert state.baseline is not None and tick.mid is not None
        lurch = tick.mid - state.baseline.mid
        if lurch == 0.0:
            # No move to fade. Recorded, not traded.
            self.skips["no_price_move_on_the_first_score"] += 1
            state.done = True
            return

        # Fade: sell into an up-lurch, buy into a down-lurch. Rest at the touch
        # so the fill has to be earned by the book coming to us.
        side = "sell" if lurch > 0 else "buy"
        limit = tick.ask if side == "sell" else tick.bid
        if limit is None:
            return

        order = ctx.place(
            market_slug=tick.market_slug, side=side, limit_price=limit,
            quantity=1.0, note=f"fade-first-score lurch={lurch:+.4f}",
        )
        assert self.first_score_at is not None
        trade = Trade(
            game_id=tick.event_slug, market_slug=tick.market_slug,
            market_type=tick.sports_market_type,
            baseline_mid=state.baseline.mid,
            baseline_age_seconds=(
                self.first_score_at - state.baseline.captured_at
            ).total_seconds(),
            signal_mid=tick.mid,
            signal_at=tick.captured_at, side=side, order=order,
        )
        state.trade = trade
        self.trades.append(trade)

    @staticmethod
    def _mark(
        trade: Trade,
        tick: Tick,
        *,
        origin: dt.datetime,
        marks: dict[float, tuple[float, float]],
        gaps: dict[float, float],
    ) -> None:
        """Record the observation *nearest* `origin + h`, inside the band.

        Taking the first in-band tick instead would report a much shorter
        horizon than it claims: the band is [0.5h, 2h], so at 200ms cadence the
        first tick inside it lands at 2.5 minutes and gets labelled "+5 min".
        Keeping the nearest is still strictly past-only — `elapsed` increases
        monotonically, so the gap falls until the target is passed and then
        rises, and a mark is simply never improved after that. No future tick
        is consulted.
        """
        assert tick.mid is not None and tick.spread is not None
        lo, hi = HORIZON_TOLERANCE
        elapsed = (tick.captured_at - origin).total_seconds() / 60.0
        for h in HORIZON_MINUTES:
            if not (h * lo <= elapsed <= h * hi):
                continue
            gap = abs(elapsed - h)
            if h not in marks or gap < gaps[h]:
                marks[h] = (tick.mid, tick.spread)
                gaps[h] = gap

    def _mark_open_trades(self, tick: Tick, ctx: ReplayContext) -> None:
        """Cancel stale entries, and record the marks each trade still needs."""
        state = self.markets[tick.market_slug]
        trade = state.trade
        if trade is None or tick.mid is None or tick.spread is None:
            return

        # Signal-path marks: recorded whether or not the order ever filled.
        self._mark(trade, tick, origin=trade.signal_at,
                   marks=trade.after_signal, gaps=trade.signal_gap)

        if trade.order.filled_at is not None:
            self._mark(trade, tick, origin=trade.order.filled_at,
                       marks=trade.after_fill, gaps=trade.fill_gap)
            return

        # Still resting: an order that has not filled inside the patience
        # window is cancelled. Leaving it open would let a fill arrive an hour
        # later and be counted as this trade.
        if trade.order.is_open:
            resting = (tick.captured_at - trade.order.placed_at).total_seconds() / 60.0
            if resting > ENTRY_PATIENCE_MINUTES:
                ctx.cancel(trade.order)
                state.done = True


# --------------------------------------------------------------------- #
# Running it
# --------------------------------------------------------------------- #


@dataclass
class StudyResult:
    """Everything the report needs, and nothing that could hide a zero."""

    trades: list[Trade]
    n_games_replayed: int
    n_games_with_first_score: int
    skips: dict[str, int]
    ticks: int
    sampling: Cadence | None
    #: (event_slug, ticks, median gap seconds, signals, fills) per game.
    #: Present so "3 of 9 games produced signals" cannot be reported without
    #: also showing *which* nine and how densely each was sampled.
    per_game: list[tuple[str, int, float | None, int, int]] = field(
        default_factory=list)


def run_study(session, *, min_ticks: int = 100) -> StudyResult:
    """Replay every game with usable tick data, one fresh strategy each."""
    trades: list[Trade] = []
    skips: dict[str, int] = defaultdict(int)
    games = 0
    games_with_first_score = 0
    ticks_total = 0
    series: dict[str, list[Tick]] = defaultdict(list)
    per_game: list[tuple[str, int, float | None, int, int]] = []

    for event_slug, _ in available_games(session, min_ticks=min_ticks):
        # `live_only=False`: the opening basket is the moment the board flips
        # from scoreless to scoring, and the 0-0 side of that transition is
        # often still flagged pregame. Loading only live rows would discard
        # exactly the baseline this study needs.
        ticks = load_ticks(session, event_slug=event_slug, live_only=False)
        if not ticks:
            continue
        games += 1
        ticks_total += len(ticks)
        game_series: dict[str, list[Tick]] = defaultdict(list)
        for t in ticks:
            if t.mid is not None:
                game_series[t.market_slug].append(t)
        for slug, v in game_series.items():
            series[f"{event_slug}:{slug}"] = v

        strategy = FadeFirstScore()
        replay_game(ticks, strategy, event_slug=event_slug)
        if strategy.first_score_at is not None:
            games_with_first_score += 1
        trades.extend(strategy.trades)
        for k, v in strategy.skips.items():
            skips[k] += v

        game_cadence = cadence(game_series)
        per_game.append((
            event_slug,
            len(ticks),
            game_cadence.median if game_cadence else None,
            len(strategy.trades),
            sum(1 for t in strategy.trades if t.filled),
        ))

    return StudyResult(
        trades=trades,
        n_games_replayed=games,
        n_games_with_first_score=games_with_first_score,
        skips=dict(skips),
        ticks=ticks_total,
        sampling=cadence(series),
        per_game=per_game,
    )


# --------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------- #


def format_report(result: StudyResult) -> str:
    out: list[str] = []
    add = out.append

    trades = result.trades
    filled = [t for t in trades if t.filled]
    games_signalled = {t.game_id for t in trades}
    games_filled = {t.game_id for t in filled}

    add("PULSE STRATEGY 1 — fade the first score")
    add("=" * 78)
    add(f"reaction window                : {REACTION_SECONDS:.0f}s after the "
        "first score")
    add(f"entry                          : maker, resting at the touch, "
        f"cancelled after {ENTRY_PATIENCE_MINUTES:.0f} min")
    add(f"exit                           : marked at the mid, charged "
        "half the spread observed there")
    add(f"quotable band                  : mid in [{MIN_MID}, {MAX_MID}], "
        f"spread <= {MAX_SPREAD}")
    add("")
    add(f"games replayed                 : {result.n_games_replayed}")
    add(f"games where 0-0 -> first score was observed : "
        f"{result.n_games_with_first_score}")
    add(f"ticks examined                 : {result.ticks:,}")
    if result.sampling is not None:
        s = result.sampling
        # Sub-second precision, unlike the shared formatter: the difference
        # between 200ms and 1s is the whole reason this data exists, and
        # rounding to whole seconds prints the live recorder's cadence as "0s".
        add(f"snapshot cadence               : median {s.median:.2f}s "
            f"(p10 {s.p10:.2f}s, p90 {s.p90:.2f}s), {s.under_2min:.0%} under 2 min")
    add(f"signals (fades placed)         : {len(trades):,} across "
        f"{len(games_signalled)} games")
    add(f"orders filled                  : {len(filled):,} across "
        f"{len(games_filled)} games"
        + (f"  ({len(filled) / len(trades):.0%} fill rate)" if trades else ""))
    add("")

    add("PRE-REGISTERED GATE (fixed 2026-08-02, before computing)")
    add("-" * 78)
    add(f"  PASS requires mean net P&L per filled trade > 0 at "
        f"+{PRIMARY_HORIZON_MINUTES:.0f} min,")
    add("  with a 95% CI clustered by game lying entirely above zero, at")
    add(f"  n >= {GATE_MIN_TRADES} filled trades across >= {GATE_MIN_GAMES} games.")
    add("  Costs are inside the number: entry earns the half-spread, the exit")
    add("  mark pays one. The bar is therefore zero, not the round trip.")
    add("")

    if result.per_game:
        add("Per game — which games could carry the study at all")
        add("-" * 78)
        add(f"  {'game':<30}{'ticks':>10}{'median gap':>13}{'signals':>9}"
            f"{'fills':>7}")
        for slug, n, med, sig, fil in sorted(result.per_game,
                                             key=lambda r: -r[1]):
            gap = f"{med:.2f}s" if med is not None else "—"
            add(f"  {slug:<30}{n:>10,}{gap:>13}{sig:>9}{fil:>7}")
        add("    A game sampled every ~15 minutes cannot resolve a 30-second")
        add("    reaction window, so it contributes coverage and no signal.")
        add("    Games, not rows, are the sample — and the row counts here")
        add("    differ by three orders of magnitude between the two regimes.")
        add("")

    if result.skips:
        add("Why ticks did not become trades")
        add("-" * 78)
        for reason, n in sorted(result.skips.items(), key=lambda kv: -kv[1]):
            add(f"  {reason:<46}: {n:,}")
        add("")

    if not trades:
        add("VERDICT: NO DATA — the strategy never fired.")
        add("")
        add("  Not a null result. Zero signals means the hypothesis was never")
        add("  tested, which is different from being tested and failing.")
        if result.n_games_with_first_score == 0:
            add("")
            add("  Note: the 0-0 -> first-score transition was never observed in")
            add("  any game. The recorder starts when the board flags a game")
            add("  live, which is after tip-off, so the opening basket falls")
            add("  before the first snapshot. That is a data-coverage problem,")
            add("  not evidence about how prices behave — and no amount of")
            add("  extra games fixes it without recording earlier.")
        return "\n".join(out)

    add("What the lurches looked like")
    add("-" * 78)
    lurches = [abs(t.lurch) for t in trades]
    add(f"  mean |lurch| on first score  : {sum(lurches) / len(lurches):.4f} "
        f"({sum(lurches) / len(lurches) * 100:.2f}c)")
    ups = sum(1 for t in trades if t.lurch > 0)
    add(f"  direction                    : {ups} up, {len(trades) - ups} down")
    by_type: dict[str, int] = defaultdict(int)
    for t in trades:
        by_type[t.market_type or "unknown"] += 1
    add("  by market type               : " + ", ".join(
        f"{k.replace('basketball_team_full_game_', '')}={v}"
        for k, v in sorted(by_type.items())))

    ages = sorted(t.baseline_age_seconds for t in trades)
    med = ages[len(ages) // 2] / 60.0
    p90 = ages[min(len(ages) - 1, int(0.9 * len(ages)))] / 60.0
    add(f"  age of the 0-0 baseline      : median {med:.1f} min, p90 {p90:.1f} min")
    add("    Reported, not filtered on. A stale baseline folds pregame drift")
    add("    into the 'lurch'; pregame travel is a measured 8.5c over the whole")
    add("    pregame window, so it is second-order against the lurch above, but")
    add("    it is a real contaminant and the gate does not correct for it.")
    add("")

    # -- the gated number ------------------------------------------- #
    add("Net P&L per FILLED trade (the gate)")
    add("-" * 78)
    add(f"  {'horizon':<10}{'n':>6}{'mean':>10}{'95% CI (clustered)':>28}"
        f"{'>0':>6}")
    primary = None
    for h in HORIZON_MINUTES:
        by_game: dict[str, list[float]] = defaultdict(list)
        for t in filled:
            p = t.pnl(h)
            if p is not None:
                by_game[t.game_id].append(p)
        values = [x for v in by_game.values() for x in v]
        if not values:
            add(f"  +{h:<9.0f}{'0':>6}{'—':>10}{'—':>28}{'—':>6}")
            continue
        mean = sum(values) / len(values)
        cl = clustered_mean(by_game)
        ci = f"[{cl.lo:+.4f}, {cl.hi:+.4f}]" if cl else "n/a (<2 games)"
        marker = "  <- gate" if h == PRIMARY_HORIZON_MINUTES else ""
        add(f"  +{h:<9.0f}{len(values):>6}{mean:>+10.4f}{ci:>28}"
            f"{'yes' if mean > 0 else 'no':>6}{marker}")
        if h == PRIMARY_HORIZON_MINUTES:
            primary = (mean, cl, len(values), set(by_game))
            naive = naive_mean(values)
            if cl is not None and naive is not None and naive.stderr > 0:
                add(f"  {'':<10}row-level CI would be [{naive.lo:+.4f}, "
                    f"{naive.hi:+.4f}] — clustering widens the SE "
                    f"{cl.stderr / naive.stderr:.1f}x")
    add("")

    # -- the ungated diagnostic ------------------------------------- #
    add("Signal-only reversion, filled or not (UNGATED diagnostic)")
    add("-" * 78)
    add("  Separates 'no phenomenon' from 'the fill proxy discarded it'.")
    add(f"  {'horizon':<10}{'n':>6}{'mean':>10}{'95% CI (clustered)':>28}")
    for h in HORIZON_MINUTES:
        by_game = defaultdict(list)
        for t in trades:
            r = t.signal_reversion(h)
            if r is not None:
                by_game[t.game_id].append(r)
        values = [x for v in by_game.values() for x in v]
        if not values:
            add(f"  +{h:<9.0f}{'0':>6}{'—':>10}{'—':>28}")
            continue
        cl = clustered_mean(by_game)
        ci = f"[{cl.lo:+.4f}, {cl.hi:+.4f}]" if cl else "n/a (<2 games)"
        add(f"  +{h:<9.0f}{len(values):>6}"
            f"{sum(values) / len(values):>+10.4f}{ci:>28}")
    add("")

    # -- per-market-type, ungated ----------------------------------- #
    add("By market type at the primary horizon (UNGATED, descriptive)")
    add("-" * 78)
    add("  `PULSE_MARKETS` in core/executor.py is deliberately empty. This is")
    add("  the table it should eventually be set from — but only once the")
    add("  pooled gate has passed. Splitting an under-powered sample three ways")
    add("  and picking the best arm is how three tests become one finding.")
    add(f"  {'type':<12}{'signals':>9}{'filled':>8}{'games':>7}{'mean P&L':>11}"
        f"{'95% CI (clustered)':>28}")
    types = sorted({(t.market_type or "unknown") for t in trades})
    for mtype in types:
        sig = [t for t in trades if (t.market_type or "unknown") == mtype]
        by_game = defaultdict(list)
        for t in sig:
            p = t.pnl(PRIMARY_HORIZON_MINUTES)
            if p is not None:
                by_game[t.game_id].append(p)
        values = [x for v in by_game.values() for x in v]
        short = mtype.replace("basketball_team_full_game_", "")
        if not values:
            add(f"  {short:<12}{len(sig):>9}{'0':>8}{'0':>7}{'—':>11}{'—':>28}")
            continue
        cl = clustered_mean(by_game)
        ci = f"[{cl.lo:+.4f}, {cl.hi:+.4f}]" if cl else "n/a (<2 games)"
        add(f"  {short:<12}{len(sig):>9}{len(values):>8}{len(by_game):>7}"
            f"{sum(values) / len(values):>+11.4f}{ci:>28}")
    add("")

    add("VERDICT")
    add("-" * 78)
    if primary is None:
        add("  NO DATA — no filled trade could be marked at the primary")
        add(f"  horizon (+{PRIMARY_HORIZON_MINUTES:.0f} min). The strategy fired "
            f"{len(trades)} times and")
        add(f"  {len(filled)} filled, but the tick stream carried no observation")
        add("  inside the horizon band. That is a cadence and coverage")
        add("  statement, not a result.")
    else:
        mean, cl, n, gs = primary
        if n < GATE_MIN_TRADES or len(gs) < GATE_MIN_GAMES:
            add(f"  NO DATA — {n} filled trades across {len(gs)} games, against a")
            add(f"  pre-registered minimum of {GATE_MIN_TRADES} across "
                f"{GATE_MIN_GAMES} games.")
            add("")
            missing = []
            if n < GATE_MIN_TRADES:
                missing.append(f"{GATE_MIN_TRADES - n} more filled trades")
            if len(gs) < GATE_MIN_GAMES:
                missing.append(f"{GATE_MIN_GAMES - len(gs)} more games")
            add(f"  Needs {' and '.join(missing)}. This is NOT a null result:")
            add("  the strategy is built and will accrue. What it needs is games.")
        elif cl is None:
            add("  NO DATA — too few clusters to form an interval.")
        elif mean > 0 and cl.lo > 0:
            add(f"  PASS — net P&L {mean:+.4f}/contract at "
                f"+{PRIMARY_HORIZON_MINUTES:.0f} min,")
            add(f"  95% CI [{cl.lo:+.4f}, {cl.hi:+.4f}] lies entirely above zero")
            add(f"  at n={n} over {len(gs)} games.")
            add("")
            add("  Read with the fill-rule caveat: the proxy discards the easy")
            add("  fills, so this is a lower bound. Next step is out-of-sample")
            add("  games, not size.")
        else:
            add(f"  FAIL — net P&L {mean:+.4f}/contract at "
                f"+{PRIMARY_HORIZON_MINUTES:.0f} min,")
            add(f"  95% CI [{cl.lo:+.4f}, {cl.hi:+.4f}] at n={n} over "
                f"{len(gs)} games.")
            add("")
            add("  Check the signal-only column before concluding. If it")
            add("  reverted and this did not, the fill proxy is the story and")
            add("  the hypothesis is untested rather than refuted.")

    add("")
    add("  Fill-rule caveat: the engine fills a resting sell only when the best")
    add("  bid rises to it, so recorded fills are biased toward the lurch")
    add("  continuing — the worst case for a fade. A PASS is therefore a lower")
    add("  bound and a FAIL is confounded.")
    if result.sampling is not None and not result.sampling.is_fast:
        add("")
        add(f"  Cadence caveat: at a {result.sampling.median:.0f}s median gap "
            "the reaction window and")
        add("  the reversion can land in the same frame. Re-run once a slate")
        add("  has accrued under the 200ms recorder.")
    return "\n".join(out)


def main() -> int:
    from core.storage import get_engine, get_sessionmaker

    parser = argparse.ArgumentParser(prog="meridian-first-score")
    parser.add_argument("--min-ticks", type=int, default=100)
    args = parser.parse_args()

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.WARNING)
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))

    Session = get_sessionmaker(get_engine())
    with Session() as session:
        result = run_study(session, min_ticks=args.min_ticks)
    print(format_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
