"""Scoring for the QUOTE shadow run. Money at price, games not rows.

    python -m core.quote.report

Reads `shadow_quote_fills`, scores every SETTLED fill to settlement, and
reports per regime behind the pre-registered floors
(docs/math/quote-shadow.md — registered before the engine's first cycle;
the floors and metrics here may not drift from that document).

THE SEPARATION IS THE POINT — 2026-09-04
----------------------------------------
Every number this module printed before today was a blend of two populations
with **opposite signs** (docs/math/adverse-selection-measured.md, the central
empirical result of this program):

    phantom (a fill that could not have happened)   +0.951c / fill
    real    (a seller actually crossed down to us)  -3.376c / fill

A **phantom** is a simulated fill booked while the ask was still ABOVE our bid:
the shadow quoter rests an order against a recorded book **that does not contain
that order**, so the recorded bid is free to fall below our price and drag the
mid onto it while nobody ever offered anywhere near us. The model fills on
`mid <= B`; reality requires `ask <= B`. See WAVE_STANDARD rule 24 — the
counterfactual must contain itself.

The mechanism gives the two populations their opposite signs: a phantom books on
a momentary dip that then REVERTS (the simulator earning mean reversion), while
a real fill is someone who wants out at our price NOW, and that flow does not
revert (informed flow — Glosten-Milgrom from the maker's side).

**So the blend is not a conservative estimate of the real number. It is a
different number, and it has the wrong sign twice over.** This module refuses to
print a verdict on the blend. `population='real'` is the only row that scores.

CAPTURE IS RETIRED — it is an identity, not a measurement
---------------------------------------------------------
`capture = mid_at_fill - quote_price`, and the fill rule only fires once the mid
reaches the quote, so the s/2 terms cancel and **capture identically equals the
negative overshoot of the mid past our price** (corr = +1.0000, mean absolute
residual 0.0000c on 6,146 real fills; zero degrees of freedom). Its ceiling of
-0.50c is half the venue's price increment, not a fee.

`net_capture_mark` therefore no longer appears in this report. The function
stays because five call sites import it, and deleting it would silently change
their arithmetic; its docstring carries the retirement.

The accounting, and the one frame conversion in it
--------------------------------------------------
A filled **bid** is a unit long YES at `quote_price`: staked = price,
returned = settlement (1 or 0). A filled **ask** is a unit short YES — which
on this venue IS the NO side at its complementary price (V14): staked =
`1 - price`, returned = `1 - settlement`. That is C11's money-at-price rule
applied to both sides of a quote; a flat win rate appears nowhere in this
module because most quotes are away from 50c and C11 retired that number.

Clustering is by game (C4): one game's ladder emits hundreds of correlated
fills, and the row-level interval would be wrong by roughly the square root
of that. The clustered machinery is imported from the adverse-selection
study, not reimplemented.

Guards (WAVE_STANDARD rules 22 and 25) are wired here rather than described.
Rule 22: no count in this report can print as a bare zero — a zero from an
instrument that has never returned non-zero on this substrate is an untested
instrument, not evidence of absence, and the classification join is exactly the
kind of instrument that fails to a clean zero. Rule 25: the staked-weighted ROI
is a ratio whose numerator and denominator both move with activity, so it prints
with its parts and with the warning that its argmax ranks activity level rather
than policy quality.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import text

from analysis.guards import (
    assert_age_non_negative,
    degenerate_extremes_warning,
    report_composite,
    report_count,
)
from core.quote.adverse_selection import ClusteredMean, clustered_mean
from core.quote.storage import ASK, BID

#: Pre-registered floors (docs/math/quote-shadow.md, fixed 2026-08-09 before
#: the first cycle). Below either, the report prints NO DATA with counts only.
FLOOR_FILLS = 500
FLOOR_GAMES = 10

#: Populations. A verdict is only ever computed on REAL.
REAL = "real"
PHANTOM = "phantom"
UNMATCHED = "unmatched"

#: How far back the touch may be looked up from a fill instant before the fill
#: is called UNMATCHED. Matches the registered classification in
#: docs/math/adverse-selection-measured.md ("book at the fill instant, <=5s
#: lookback"). Widening this is a change to the registered definition — and on
#: the right substrate it never binds (measured age is 0.0s on every fill), so a
#: run where it DOES bind is reading the wrong table, not a stale market.
BOOK_LOOKBACK_S = 5


def score_fill(*, side: str, quote_price: float, settlement: int) -> tuple[float, float]:
    """(staked, returned) for one settled fill, in dollars per contract."""
    if side == BID:
        return quote_price, float(settlement)
    if side == ASK:
        return 1.0 - quote_price, 1.0 - float(settlement)
    raise ValueError(f"unknown side {side!r}")


def net_capture_mark(*, side: str, quote_price: float, mid_at_fill: float) -> float:
    """RETIRED 2026-09-03 — an identity, not a measurement. Do not rank on it.

    `capture = mid_at_fill - quote_price`, and the fill rule only fires once the
    mid has reached the quote, so this quantity IDENTICALLY EQUALS the negative
    overshoot of the mid past our price: corr +1.0000, mean absolute residual
    0.0000c on 6,146 real fills, zero degrees of freedom. It is a restatement of
    the crossing geometry, so it cannot disagree with itself and any gradient
    read off it is forced. Cross-board comparisons of it carry NO economic
    content — they say only that two boards' mids step different discrete
    distances. Its -0.50c ceiling is half the venue tick, not a fee.

    Kept only because five call sites import it and removing it would silently
    change their arithmetic. **Settlement P&L is primary; markout at pre-named
    horizons is secondary. This is neither.**
    """
    if side == BID:
        return mid_at_fill - quote_price
    if side == ASK:
        return quote_price - mid_at_fill
    raise ValueError(f"unknown side {side!r}")


def classify_fill(*, side: str, quote_price: float,
                  best_bid: float | None, best_ask: float | None) -> str:
    """REAL, PHANTOM or UNMATCHED for one fill against the book at its instant.

    The whole separation turns on this one comparison, so it is a pure function
    with no database in it and the confusion is encoded in its tests.

    Our resting **bid** at price B is only reachable by a real seller if the
    book's best ASK had come down to B or below. Our resting **ask** at A is
    only reachable by a real buyer if the best BID had come up to A or above.
    Anything else is the simulator filling against a book that never contained
    its order.

    UNMATCHED is a third state on purpose. Folding "no book here" into either
    population would let a coverage hole masquerade as an economic finding — and
    the side that matters is the side whose absence is being asked about: a BID
    needs the ASK, so a missing ask is unmatched even when a bid was recorded.
    """
    if side == BID:
        if best_ask is None:
            return UNMATCHED
        return REAL if best_ask <= quote_price else PHANTOM
    if side == ASK:
        if best_bid is None:
            return UNMATCHED
        return REAL if best_bid >= quote_price else PHANTOM
    raise ValueError(f"unknown side {side!r}")


#: The fills, with the touch at each fill instant.
#:
#: SUBSTRATE, AND THE TRAP IN IT. The touch comes from `market_snapshots`
#: (`best_bid`/`best_ask`), NOT from `book_levels`. `book_levels` looks like the
#: obvious source and is the wrong one: it is a SLOW DEPTH LOOP sampled
#: independently of the price loop, and measured against these fills it sits a
#: **median 6.8s and a mean 13.3s behind** the fill instant on the September
#: tape (max 128.6s). Against the registered <=5s lookback that drops **73.6% of
#: all fills and 93.6% of the September ones**, and the survivors are a biased
#: sample — it reported an 84.9% phantom share against the recorded 63.9%.
#: `market_snapshots` is the loop the fill itself was generated from, so the
#: touch is at **age 0.0s on 38,465/38,465 fills, both eras**. The classification
#: reproduces the recorded WNBA result to the digit on it (6,255 real fills,
#: 63.9% phantom, -3.419c clustered) and reproduced nothing on book_levels.
#:
#: The join is BACKWARD (`captured_at <= filled_at`) and the resulting age is
#: asserted non-negative rather than merely capped — a one-sided cap on an age
#: whose join points the other way is vacuous and reads exactly like a freshness
#: gate (rule 23, `assert_age_non_negative`; D shipped a forward join today whose
#: `age <= 5` admitted a book from 25 hours AFTER the fill).
_CLASSIFIED_SQL = """
    SELECT f.regime, f.side, f.game_id, f.market_slug,
           f.quote_price, f.settlement, f.filled_at,
           s.best_bid, s.best_ask,
           EXTRACT(EPOCH FROM (f.filled_at - s.captured_at)) AS book_age_s
    FROM shadow_quote_fills f
    LEFT JOIN LATERAL (
        SELECT ms.best_bid, ms.best_ask, ms.captured_at
        FROM market_snapshots ms
        WHERE ms.market_slug = f.market_slug
          AND ms.captured_at <= f.filled_at
          AND ms.captured_at >= f.filled_at - make_interval(secs => :lookback)
          AND ms.best_bid IS NOT NULL
          AND ms.best_ask IS NOT NULL
        ORDER BY ms.captured_at DESC
        LIMIT 1
    ) s ON true
"""

#: The fallback when the touch substrate is absent. Every fill is UNMATCHED, and
#: rule 22 makes that state loud rather than letting it read as "no phantoms".
_UNCLASSIFIED_SQL = """
    SELECT regime, side, game_id, market_slug, quote_price, settlement,
           filled_at, NULL::numeric AS best_bid, NULL::numeric AS best_ask,
           NULL::double precision AS book_age_s
    FROM shadow_quote_fills
"""


@dataclass
class PopulationReport:
    """One (regime, population) cell. Only `real` is ever given a verdict."""

    regime: str
    population: str
    n_fills: int
    n_settled: int
    n_games: int
    staked: float
    returned: float
    roi_clustered: ClusteredMean | None
    #: Settlement P&L in CENTS per fill, game-clustered. This is the PRIMARY
    #: figure and it must never print without its interval.
    pnl_clustered: ClusteredMean | None = None

    @property
    def at_floor(self) -> bool:
        return self.n_settled >= FLOOR_FILLS and self.n_games >= FLOOR_GAMES

    @property
    def per_fill_cents(self) -> float | None:
        """Mean settlement P&L per fill, in cents. The money, per unit risked."""
        if not self.n_settled:
            return None
        return (self.returned - self.staked) / self.n_settled * 100.0

    @property
    def games_losing(self) -> int | None:
        return None if self.roi_clustered is None else self._losing

    #: filled by build_report; the per-game sign count, which is the one
    #: statistic that does not depend on the mean surviving.
    _losing: int = 0
    _games_scored: int = 0

    @property
    def verdict(self) -> str:
        if self.population != REAL:
            return "NOT SCORED — only the real population can carry a verdict"
        if not self.at_floor:
            return "NO DATA"
        cm = self.roi_clustered
        if cm is None:
            return "NO DATA"
        if cm.mean > 0 and cm.lo > 0:
            return "PASS (upper bound — see the fill-rule caveat)"
        return "FAIL"


@dataclass
class RegimeReport:
    """A regime's three populations, plus the blend it is no longer scored on."""

    regime: str
    populations: dict[str, PopulationReport] = field(default_factory=dict)
    #: Largest touch age the classification join used, in seconds. 0.0 on the
    #: price substrate by construction; anything else names the wrong table.
    max_book_age_s: float | None = None

    @property
    def real(self) -> PopulationReport | None:
        return self.populations.get(REAL)

    @property
    def n_fills(self) -> int:
        return sum(p.n_fills for p in self.populations.values())

    @property
    def n_settled(self) -> int:
        return sum(p.n_settled for p in self.populations.values())

    @property
    def n_games(self) -> int:
        return max((p.n_games for p in self.populations.values()), default=0)

    @property
    def phantom_share(self) -> float | None:
        """Of the CLASSIFIED fills only. Unmatched is a coverage fact, not a
        population, so folding it into the denominator would move this number
        with recorder health rather than with the simulator."""
        classified = sum(self.populations[p].n_fills
                         for p in (REAL, PHANTOM) if p in self.populations)
        if not classified:
            return None
        ph = self.populations[PHANTOM].n_fills if PHANTOM in self.populations else 0
        return ph / classified

    @property
    def at_floor(self) -> bool:
        r = self.real
        return bool(r and r.at_floor)

    @property
    def verdict(self) -> str:
        r = self.real
        return r.verdict if r else "NO DATA"


def _last_nonzero(session, regime: str) -> tuple[dt.datetime | None, int | None]:
    """Provenance for rule 22: when did this regime last record a fill, and how
    many has it ever recorded? A zero from a regime that has NEVER recorded a
    fill is an unproven instrument; a zero from one that recorded 12,000
    yesterday is a live signal that something stopped."""
    row = session.execute(text(
        "SELECT max(filled_at) AS last_at, count(*) AS n "
        "FROM shadow_quote_fills WHERE regime = :r"
    ), {"r": regime}).first()
    if row is None or not row.n:
        return None, None
    return row.last_at, int(row.n)


def build_report(session) -> dict[str, RegimeReport]:
    """Per regime, per population. Classification is attempted; its failure is
    reported as UNMATCHED rather than swallowed."""
    try:
        rows = session.execute(text(_CLASSIFIED_SQL),
                               {"lookback": float(BOOK_LOOKBACK_S)}).all()
    except Exception:  # noqa: BLE001 — the book substrate may be absent
        session.rollback()
        rows = session.execute(text(_UNCLASSIFIED_SQL)).all()

    buckets: dict[tuple[str, str], list] = defaultdict(list)
    for r in rows:
        # Rule 23. Assert BEFORE the lookback cap is trusted: a cap on an age
        # whose join points the other way is vacuous, and it reads like a gate.
        if r.book_age_s is not None:
            assert_age_non_negative(float(r.book_age_s),
                                    f"touch lookup for {r.market_slug}")
        pop = classify_fill(
            side=r.side, quote_price=float(r.quote_price),
            best_bid=None if r.best_bid is None else float(r.best_bid),
            best_ask=None if r.best_ask is None else float(r.best_ask),
        )
        buckets[(r.regime, pop)].append(r)

    out: dict[str, RegimeReport] = {}
    for (regime, pop), fills in buckets.items():
        roi_by_game: dict[str, list[float]] = defaultdict(list)
        cents_by_game: dict[str, list[float]] = defaultdict(list)
        pnl_by_game: dict[str, float] = defaultdict(float)
        staked = returned = 0.0
        n_settled = 0
        for f in fills:
            if f.settlement is None:
                continue
            cost, ret = score_fill(side=f.side, quote_price=float(f.quote_price),
                                   settlement=int(f.settlement))
            if cost <= 0:
                continue
            staked += cost
            returned += ret
            roi_by_game[f.game_id].append(ret / cost - 1.0)
            pnl_by_game[f.game_id] += ret - cost
            cents_by_game[f.game_id].append((ret - cost) * 100.0)
            n_settled += 1
        rep = PopulationReport(
            regime=regime, population=pop,
            n_fills=len(fills), n_settled=n_settled,
            n_games=len({f.game_id for f in fills if f.settlement is not None}),
            staked=staked, returned=returned,
            roi_clustered=clustered_mean(roi_by_game),
            pnl_clustered=clustered_mean(cents_by_game),
        )
        rep._games_scored = len(pnl_by_game)
        rep._losing = sum(1 for v in pnl_by_game.values() if v < 0)
        out.setdefault(regime, RegimeReport(regime=regime)).populations[pop] = rep

    ages: dict[str, float] = defaultdict(float)
    seen_age = False
    for r in rows:
        if r.book_age_s is not None:
            seen_age = True
            ages[r.regime] = max(ages[r.regime], float(r.book_age_s))
    if seen_age:
        for regime, rr in out.items():
            rr.max_book_age_s = ages.get(regime, 0.0)
    return out


def format_report(reports: dict[str, RegimeReport], session=None) -> str:
    out: list[str] = []
    add = out.append
    add("QUOTE SHADOW RUN — settlement-scored, money at price (C11), by game (C4)")
    add("=" * 78)
    add(f"floors (pre-registered): >= {FLOOR_FILLS} settled fills AND "
        f">= {FLOOR_GAMES} games, ON THE REAL POPULATION ONLY")
    add("PRIMARY: settlement P&L.  RETIRED: capture-vs-mid (an identity — see")
    add("docs/math/adverse-selection-measured.md).  ABSENT: markout at pre-named")
    add("horizons, which the metric ruling names SECONDARY and this report does")
    add("not yet compute — stated so its absence is not read as a null result.")
    add("ESTIMATOR, named because two are in circulation and they differ: this is")
    add("`clustered_mean` — the POOLED mean with a game-cluster-robust SE, i.e.")
    add("what a dollar deployed earns. The UNWEIGHTED mean of game means (what a")
    add("TYPICAL GAME looks like) is a different number: on WNBA real fills the")
    add("two read -3.376c [-4.746, -2.007] and -3.419c [-5.062, -1.777] on")
    add("identical rows. Neither is wrong; a comparison that mixes them is.")
    add("REGIME: sign counts and means below are PER REGIME. The in-game and")
    add("mixed-regime counts genuinely differ — on WNBA, six pregame fills flip")
    add("one game, giving 13/13 in-game against 12/13 mixed. Say which you mean.")
    add("")

    if not reports:
        # Rule 22. A bare "no fills" is the least self-validating result there
        # is; the guard makes the empty case carry its own provenance.
        for regime in ("pregame", "ingame"):
            at, n = _last_nonzero(session, regime) if session is not None else (None, None)
            add("  " + str(report_count(f"fills[{regime}]", 0, at, n)))
        add("")
        add("The engine has not written a fill, which is different from running")
        add("and finding nothing — the line above says which.")
        return "\n".join(out)

    for regime in sorted(reports):
        rr = reports[regime]
        add(f"[{regime}]")
        at, n_ever = _last_nonzero(session, regime) if session is not None else (None, None)
        # Rule 22, on the regime's OWN quantity. The provenance must belong to
        # the number it is attached to: printing this regime's fill history
        # beside a POPULATION's zero would make that zero mis-readable, which is
        # worse than a bare zero and is exactly what the guard exists to stop.
        add(f"  {str(report_count(f'{regime} fills, all populations', rr.n_fills, at, n_ever))}")
        for pop in (REAL, PHANTOM, UNMATCHED):
            p = rr.populations.get(pop)
            cnt = p.n_fills if p else 0
            # A population's own provenance is per-run: this run either saw that
            # branch fire or it did not, and there is no stored history of it.
            # So a zero here prints UNPROVEN, which is the honest state — the
            # classifier has not demonstrated that branch can fire on this
            # substrate, and that is a different claim from "it did not happen".
            add(f"  {str(report_count(f'{pop:<9} fills', cnt))}")
        if rr.max_book_age_s is not None:
            add(f"  touch age at fill            : max {rr.max_book_age_s:.1f}s over "
                f"{rr.n_fills:,} fills (lookback cap {BOOK_LOOKBACK_S}s)")
            if rr.max_book_age_s > 1.0:
                add("  ^ NON-ZERO. On the price substrate this is 0.0s by construction;")
                add("    a non-zero age means the join found a SLOWER table, and the")
                add("    UNMATCHED count below is then a substrate fact, not a market one.")
        share = rr.phantom_share
        if share is None:
            add("  phantom share             : NOT COMPUTABLE — nothing classified")
        else:
            add(f"  phantom share (of classified): {share:.1%}")
        um = rr.populations.get(UNMATCHED)
        if um and um.n_fills:
            frac = um.n_fills / rr.n_fills
            add(f"  UNMATCHED is {frac:.1%} of this regime's fills — a COVERAGE hole,")
            add("  not a population. Every figure below is computed on what the book")
            add("  join could reach, and that is a different sample from the tape.")
        add("")

        r = rr.real
        if r is None:
            add("  no REAL fills in this regime. Rule 22: that is either the")
            add("  finding or a broken join, and the counts above say which.")
            add("")
            continue

        add(f"  [{regime}/real] settled {r.n_settled:,} over {r.n_games} games")
        if not r.at_floor:
            add(f"  VERDICT: NO DATA — floors are {FLOOR_FILLS} fills / "
                f"{FLOOR_GAMES} games ON REAL. Counts only; no performance")
            add("  number prints below a floor, and that is the registration.")
            add("")
            continue

        add(f"  staked -> returned           : ${r.staked:,.2f} -> ${r.returned:,.2f}")
        pf = r.per_fill_cents
        pc = r.pnl_clustered
        if pc is not None:
            add(f"  settlement P&L per fill      : {pc.mean:+.3f}c  "
                f"95% CI [{pc.lo:+.3f}, {pc.hi:+.3f}]  (G={pc.n_clusters})  [PRIMARY]")
        elif pf is not None:
            add(f"  settlement P&L per fill      : {pf:+.3f}c   [PRIMARY, no interval]")
        add(f"  games losing money           : {r._losing}/{r._games_scored}"
            f"   (this regime only — see the estimator note)")

        # Rule 25. The staked-weighted ROI is a ratio whose numerator and
        # denominator both move with activity: a policy that barely trades can
        # top it while being the worst cell per fill. It prints with its parts.
        comp = report_composite(f"{regime}/real staked-ROI",
                                numerator=r.returned - r.staked,
                                denominator=max(r.staked, float(r.n_settled)),
                                events=r.n_settled)
        add(f"  {comp}")
        warn = degenerate_extremes_warning(f"{regime}/real staked-ROI",
                                           comp.per_event)
        if warn:
            add(f"  RULE 25: {warn}")

        cm = r.roi_clustered
        if cm is not None:
            add(f"  per-fill ROI, clustered      : {cm.mean:+.4f}  "
                f"95% CI [{cm.lo:+.4f}, {cm.hi:+.4f}]  (G={cm.n_clusters})")
        add(f"  VERDICT: {r.verdict}")

        ph = rr.populations.get(PHANTOM)
        if ph is not None and ph.n_settled:
            add(f"  [{regime}/phantom, NOT SCORED] {ph.n_settled:,} fills, "
                f"{ph.per_fill_cents:+.3f}c/fill — shown because the sign gap")
            add("  between the populations IS the adverse-selection result.")
        add("")

    add("Fill-rule caveat (inherited from the study): transient dips that fill")
    add("and recover are invisible, so losses are trustworthy and profits are")
    add("upper bounds. A PASS here reopens a question; it authorises nothing.")
    add("No in-sample result justifies capital. The forward test is the evidence.")
    return "\n".join(out)


def main() -> int:
    from core.storage import get_engine, get_sessionmaker

    Session = get_sessionmaker(get_engine())
    with Session() as s:
        print(format_report(build_report(s), session=s))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
