"""Hypothesis #6 — do the tails move most at the start and end of a game?

Origin, from live watching: *"the tail odds move a ton at the start and end."*
The last untested Tier 3 row in
[pulse-hypotheses.md](../../docs/pulse-hypotheses.md).

This is a **descriptive volatility measurement, not a strategy.** It does not
claim a price is wrong; it asks whether the far rungs of the ladder are more
active at the edges of a game than in the middle. That matters for
[ladder-sigma.md](../../docs/math/ladder-sigma.md) (which asks whether the
venue's ~15.9 implied sigma is too narrow) and for QUOTE, which would have to
quote into whatever this finds. It overlaps ladder-sigma deliberately and
**does not touch its gate**: that one is about the *level* of implied sigma
across a whole ladder, this one is about *when* the tails move.

Passing this does not make anything tradable. See correction C12: a measured
effect and a tradable edge are different claims, and #16 passed a gate while
being neither.


THE INSTRUMENT DECIDES THE DESIGN — read this before the gate
--------------------------------------------------------------
The obvious version of this study is "compare deep rungs against near rungs".
**That version is unanswerable with this data**, and measured rather than
assumed (2026-08-07, local mirror):

    book_tier='near'   3,282,678 live obs, median gap   0.20s
    book_tier='deep'      24,019 live obs, median gap  30.11s
    book_tier NULL         2,520 live obs, median gap 641.54s

The live recorder samples the near-money rungs at 200ms and sweeps the deep
ones at 30s ([infra/live-cadence.md](../../docs/infra/live-cadence.md)). A
150x cadence difference makes deep rungs look more volatile **by
construction** — a longer gap contains more movement. That is exactly
correction C1, where "% of frames that differ" was mistaken for a property of
the market when it was a property of the sampling interval.

So the universe here is **`book_tier='near'` only**, which is uniformly
sampled at 0.20s. That is not a workaround; it is the only sub-population
where a volatility comparison means anything.

**The near tier still contains tails.** `book_tier` ranks by |mid - 0.5|
*within each market type*, so the near set spans mid 0.06 to 0.90 at the 5th
and 95th percentiles, and holds **800,759** tail observations across 12 games.
The hypothesis survives the restriction; it is the deep *tier* that is
unmeasurable, not the tail *prices*.

Every excluded row is counted and printed. A silent exclusion is how a study
reports on a population it never had.


PRE-REGISTERED GATE — fixed before any move statistic was computed
-------------------------------------------------------------------
Written 2026-08-07. Sample sizes and cadence above were inspected first (they
decide whether the question is answerable at all); **no |move| number had been
computed when this was written.**

    Phases:  open = Q1     mid = Q2 + Q3     close = Q4

    PASS  requires ALL of:
      (1) mean tail |move| in OPEN  > mean tail |move| in MID, and the 95%
          confidence interval on that difference, clustered by game,
          excludes zero
      (2) the same for CLOSE vs MID
      (3) >= 10 games contributing to both phases of each comparison

    FAIL  if (3) is met but (1) or (2) is not.

    NO DATA  for any comparison whose phases do not both reach 10 games.
      A comparison may report NO DATA while the other reports PASS or FAIL;
      the overall verdict is PASS only if BOTH comparisons pass.

Both directions are required because the hypothesis is specifically about
**both edges**. A close-only effect is the well-known endgame repricing
already recorded as V4, not this claim.

**Interpretation rule, also fixed in advance.** The same statistic is computed
for the *body* rungs as a control. If the body shows the same open/close
elevation, the finding is "the whole board is livelier at the edges of a
game", **not** "the tails specifically" — and the hypothesis as stated is not
supported even if the tail comparison passes on its own. This rule exists
because #16 passed a gate that compared the wrong two things, and the cheapest
protection against repeating that is to name the control before seeing it.


How a move is measured
----------------------
Net absolute mid change over a fixed **30-second** window:

    move = |mid(t + 30s) - mid(t)|

Fixed-horizon and net, not per-tick and not summed travel, because both of
those scale with the number of samples in the window and would reintroduce the
cadence artifact the universe restriction just removed. 30s is
`adverse_selection.DEFAULT_HORIZON_SECONDS`, pre-registered there; no new
constant is invented for this study.

Windows are **non-overlapping** per market, so two observations do not share a
price path — the same rule `overreaction.py` uses, and for the same reason:
overlapping windows inflate n against a gate stated in independent
observations.

A window that **spans a period boundary is dropped**, because its phase would
be ambiguous. HT and OT are excluded entirely: the clock is stopped at
halftime, and overtime is not regulation.

    python -m core.pulse.tail_volatility
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass, field

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.quote.adverse_selection import (
    DEFAULT_HORIZON_SECONDS,
    MAX_MID,
    MIN_MID,
    clustered_mean,
)

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc

#: The window a move is measured over. Inherited from adverse_selection.
WINDOW_SECONDS = DEFAULT_HORIZON_SECONDS

#: Pair `t` with the observation nearest `t + WINDOW` inside this band, so a
#: hole in the stream cannot silently become a 5-minute window reported as 30s.
WINDOW_TOLERANCE = (0.5, 2.0)

#: A rung is a TAIL rung when its mid sits outside the quotable band that
#: adverse_selection, overreaction and first_score all use. Inherited rather
#: than invented: [0.20, 0.80] is the band those studies call tradable, so its
#: complement is the natural definition of "the tails".
TAIL_DISTANCE = 0.5 - MIN_MID           # 0.30

#: Phase mapping. HT and OT are absent on purpose — see the docstring.
PHASE_OF: dict[str, str] = {
    "Q1": "open",
    "Q2": "mid",
    "Q3": "mid",
    "Q4": "close",
}
PHASES = ("open", "mid", "close")

# -- the gate --------------------------------------------------------- #
GATE_MIN_GAMES = 10


@dataclass(frozen=True)
class Move:
    """One non-overlapping window on one market."""

    event_slug: str
    market_slug: str
    phase: str
    is_tail: bool
    mid_start: float
    mid_end: float
    elapsed_seconds: float

    @property
    def move(self) -> float:
        return abs(self.mid_end - self.mid_start)


def band_of(mid: float) -> bool:
    """True when this mid is a tail rung."""
    return abs(mid - 0.5) >= TAIL_DISTANCE


def build_moves(
    series: dict[tuple[str, str], list[tuple[dt.datetime, float, str]]],
    *,
    window_seconds: float = WINDOW_SECONDS,
) -> tuple[list[Move], dict[str, int]]:
    """Per-market observations -> non-overlapping fixed-window moves.

    Each element of a series is `(captured_at, mid, period)`. Returns the moves
    and a tally of why candidates were dropped.
    """
    lo, hi = WINDOW_TOLERANCE
    out: list[Move] = []
    skips: dict[str, int] = defaultdict(int)

    for (event_slug, market_slug), obs in series.items():
        ordered = sorted(obs, key=lambda o: o[0])
        i = 0
        while i < len(ordered):
            t0, mid0, period0 = ordered[i]
            phase = PHASE_OF.get(period0 or "")
            if phase is None:
                skips[f"period not in a phase ({period0 or 'none'})"] += 1
                i += 1
                continue

            # Nearest partner inside the tolerance band.
            best_j = None
            best_gap = float("inf")
            for j in range(i + 1, len(ordered)):
                elapsed = (ordered[j][0] - t0).total_seconds()
                if elapsed > window_seconds * hi:
                    break
                if elapsed < window_seconds * lo:
                    continue
                gap = abs(elapsed - window_seconds)
                if gap < best_gap:
                    best_j, best_gap = j, gap
            if best_j is None:
                skips["no observation inside the window band"] += 1
                i += 1
                continue

            t1, mid1, period1 = ordered[best_j]
            if PHASE_OF.get(period1 or "") != phase:
                # Spans a period boundary: its phase is ambiguous.
                skips["window spans a period boundary"] += 1
                i += 1
                continue

            out.append(Move(
                event_slug=event_slug, market_slug=market_slug, phase=phase,
                is_tail=band_of(mid0), mid_start=mid0, mid_end=mid1,
                elapsed_seconds=(t1 - t0).total_seconds(),
            ))
            # Non-overlapping: resume after the window's far end.
            i = best_j + 1

    return out, dict(skips)


def load_series(
    session: Session,
) -> tuple[dict[tuple[str, str], list[tuple[dt.datetime, float, str]]], dict[str, int]]:
    """Near-tier live mids per (game, market), plus the exclusion tally.

    Exclusions are counted here rather than filtered in SQL and forgotten,
    because "we measured the near tier" and "we measured the board" are
    different claims and the report has to be able to tell them apart.
    """
    skips: dict[str, int] = {}

    counts = session.execute(text("""
        SELECT coalesce(book_tier, 'NULL') AS tier, count(*) AS n
        FROM market_snapshots
        WHERE is_live IS TRUE
          AND best_bid IS NOT NULL AND best_ask IS NOT NULL AND best_ask > best_bid
        GROUP BY 1
    """)).all()
    for r in counts:
        if r.tier != "near":
            skips[f"book_tier={r.tier} (30s+ cadence, not comparable)"] = r.n

    rows = session.execute(text("""
        SELECT event_slug, market_slug, captured_at, event_period,
               (best_bid + best_ask) / 2.0 AS mid
        FROM market_snapshots
        WHERE is_live IS TRUE
          AND book_tier = 'near'
          AND best_bid IS NOT NULL AND best_ask IS NOT NULL AND best_ask > best_bid
          AND event_slug IS NOT NULL
        ORDER BY event_slug, market_slug, captured_at
    """)).all()

    series: dict[tuple[str, str], list[tuple[dt.datetime, float, str]]] = defaultdict(list)
    for r in rows:
        series[(r.event_slug, r.market_slug)].append(
            (r.captured_at, float(r.mid), r.event_period or "")
        )
    return dict(series), skips


# --------------------------------------------------------------------- #
# Statistics
# --------------------------------------------------------------------- #


@dataclass(frozen=True)
class PhaseStat:
    phase: str
    n: int
    n_games: int
    mean: float


@dataclass(frozen=True)
class Contrast:
    """One phase compared against the middle of the game."""

    phase: str
    n_games: int
    diff: float
    lo: float | None
    hi: float | None

    @property
    def excludes_zero(self) -> bool:
        return self.lo is not None and self.lo > 0.0

    @property
    def has_sample(self) -> bool:
        return self.n_games >= GATE_MIN_GAMES


def phase_stats(moves: list[Move], *, tail: bool) -> dict[str, PhaseStat]:
    by_phase: dict[str, list[Move]] = defaultdict(list)
    for m in moves:
        if m.is_tail is tail:
            by_phase[m.phase].append(m)
    out: dict[str, PhaseStat] = {}
    for phase, group in by_phase.items():
        out[phase] = PhaseStat(
            phase=phase, n=len(group),
            n_games=len({m.event_slug for m in group}),
            mean=sum(m.move for m in group) / len(group),
        )
    return out


def contrast_against_mid(moves: list[Move], phase: str, *, tail: bool) -> Contrast:
    """Mean(phase) - mean(mid), with a game-clustered interval.

    **Paired within game.** Each game contributes one difference of its own two
    phase means, so a game that is simply livelier overall cannot push the
    contrast: only its *within-game* shape counts. Clustering is then over
    games, which is the sample unit this project measures in.
    """
    per_game: dict[str, list[float]] = defaultdict(list)
    per_game_mid: dict[str, list[float]] = defaultdict(list)
    for m in moves:
        if m.is_tail is not tail:
            continue
        if m.phase == phase:
            per_game[m.event_slug].append(m.move)
        elif m.phase == "mid":
            per_game_mid[m.event_slug].append(m.move)

    diffs: dict[str, list[float]] = {}
    for game, values in per_game.items():
        mids = per_game_mid.get(game)
        if not mids or not values:
            continue
        diffs[game] = [sum(values) / len(values) - sum(mids) / len(mids)]

    if not diffs:
        return Contrast(phase=phase, n_games=0, diff=float("nan"), lo=None, hi=None)

    flat = [x for v in diffs.values() for x in v]
    cl = clustered_mean(diffs)
    return Contrast(
        phase=phase, n_games=len(diffs), diff=sum(flat) / len(flat),
        lo=cl.lo if cl else None, hi=cl.hi if cl else None,
    )


@dataclass
class Study:
    moves: list[Move]
    skips: dict[str, int]
    tail: dict[str, PhaseStat]
    body: dict[str, PhaseStat]
    tail_open: Contrast
    tail_close: Contrast
    body_open: Contrast
    body_close: Contrast


def run_study(session: Session) -> Study:
    series, load_skips = load_series(session)
    moves, move_skips = build_moves(series)
    skips = {**load_skips, **move_skips}
    return Study(
        moves=moves,
        skips=skips,
        tail=phase_stats(moves, tail=True),
        body=phase_stats(moves, tail=False),
        tail_open=contrast_against_mid(moves, "open", tail=True),
        tail_close=contrast_against_mid(moves, "close", tail=True),
        body_open=contrast_against_mid(moves, "open", tail=False),
        body_close=contrast_against_mid(moves, "close", tail=False),
    )


# --------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------- #


def _verdict_line(c: Contrast) -> str:
    if not c.has_sample:
        return (f"NO DATA — {c.n_games} games against a minimum of "
                f"{GATE_MIN_GAMES}")
    if c.lo is None:
        return "NO DATA — too few clusters for an interval"
    if c.diff > 0 and c.lo > 0:
        return f"passes — {c.diff * 100:+.3f}c, CI [{c.lo * 100:+.3f}, {c.hi * 100:+.3f}]c"
    return f"fails — {c.diff * 100:+.3f}c, CI [{c.lo * 100:+.3f}, {c.hi * 100:+.3f}]c"


def format_report(study: Study) -> str:
    out: list[str] = []
    add = out.append

    add("HYPOTHESIS 6 — tail volatility at the edges of a game")
    add("=" * 78)
    add(f"universe                       : book_tier='near' only "
        f"(uniform 0.20s cadence)")
    add(f"window                         : {WINDOW_SECONDS:.0f}s, non-overlapping, "
        "net |mid move|")
    add(f"tail definition                : |mid - 0.5| >= {TAIL_DISTANCE:.2f} "
        f"(outside [{MIN_MID}, {MAX_MID}])")
    add(f"phases                         : open=Q1  mid=Q2+Q3  close=Q4  "
        "(HT and OT excluded)")
    add(f"windows built                  : {len(study.moves):,}")
    add("")

    add("PRE-REGISTERED GATE (fixed 2026-08-07, before any move was computed)")
    add("-" * 78)
    add("  PASS requires tail |move| higher in BOTH open and close than in mid,")
    add("  each with a 95% CI clustered by game excluding zero, at >= 10 games.")
    add("  Interpretation rule, also fixed in advance: if the BODY rungs show the")
    add("  same pattern, the finding is 'the board is livelier at the edges', not")
    add("  'the tails specifically', and the hypothesis is not supported.")
    add("")

    if study.skips:
        # Two different units, kept apart. Mixing "rows never loaded" with
        # "candidate windows dropped" in one column invites subtracting one
        # from the other, which is meaningless.
        universe = {k: v for k, v in study.skips.items() if k.startswith("book_tier")}
        windows = {k: v for k, v in study.skips.items() if not k.startswith("book_tier")}

        if universe:
            add("Excluded from the universe (OBSERVATIONS never loaded)")
            add("-" * 78)
            for reason, n in sorted(universe.items(), key=lambda kv: -kv[1]):
                add(f"  {reason:<54}: {n:>10,}")
            add("")
        if windows:
            add("Dropped while building windows (CANDIDATE WINDOW STARTS)")
            add("-" * 78)
            add("  Not comparable with the counts above, and not with the window")
            add("  total either: windows are non-overlapping, so one window consumes")
            add("  many observations while one drop consumes a single start point.")
            for reason, n in sorted(windows.items(), key=lambda kv: -kv[1]):
                add(f"  {reason:<54}: {n:>10,}")
            add("")

    if not study.moves:
        add("VERDICT: NO DATA — no window could be built.")
        return "\n".join(out)

    add("Mean |30s move| by phase")
    add("-" * 78)
    add(f"  {'':<8}{'TAIL':>28}{'':>6}{'BODY (control)':>28}")
    add(f"  {'phase':<8}{'n':>10}{'games':>7}{'mean':>11}{'':>6}"
        f"{'n':>10}{'games':>7}{'mean':>11}")
    for phase in PHASES:
        t = study.tail.get(phase)
        b = study.body.get(phase)
        def fmt(s: PhaseStat | None) -> str:
            if s is None:
                return f"{'—':>10}{'—':>7}{'—':>11}"
            return f"{s.n:>10,}{s.n_games:>7}{s.mean * 100:>10.3f}c"
        add(f"  {phase:<8}{fmt(t)}{'':>6}{fmt(b)}")
    add("")

    add("Contrast against mid-game, paired within game then clustered by game")
    add("-" * 78)
    add("  Each game contributes one difference of its own two phase means, so a")
    add("  game that is livelier throughout cannot move the contrast.")
    add(f"  {'comparison':<22}{'games':>7}{'diff':>12}{'95% CI (clustered)':>30}")
    for label, c in (("TAIL  open vs mid", study.tail_open),
                     ("TAIL  close vs mid", study.tail_close),
                     ("body  open vs mid", study.body_open),
                     ("body  close vs mid", study.body_close)):
        ci = (f"[{c.lo * 100:+.3f}, {c.hi * 100:+.3f}]c"
              if c.lo is not None else "n/a")
        diff = f"{c.diff * 100:+.3f}c" if c.n_games else "—"
        add(f"  {label:<22}{c.n_games:>7}{diff:>12}{ci:>30}")
    add("")

    add("VERDICT")
    add("-" * 78)
    add(f"  open vs mid (tail)  : {_verdict_line(study.tail_open)}")
    add(f"  close vs mid (tail) : {_verdict_line(study.tail_close)}")
    add("")

    both_sampled = study.tail_open.has_sample and study.tail_close.has_sample
    both_pass = (
        study.tail_open.has_sample and study.tail_open.diff > 0
        and study.tail_open.excludes_zero
        and study.tail_close.has_sample and study.tail_close.diff > 0
        and study.tail_close.excludes_zero
    )

    if not both_sampled:
        add("  NO DATA — the hypothesis names both edges, and at least one edge")
        add("  does not have the games to test. Not a null result.")
        # An under-powered edge still points somewhere. Say where, labelled as
        # a direction, so the next run is not a surprise — the same way
        # run-overreaction reported its four-cluster number.
        for label, c in (("open", study.tail_open), ("close", study.tail_close)):
            if c.has_sample or c.lo is None or c.n_games < 2:
                continue
            if c.diff < 0 and c.hi < 0:
                add("")
                add(f"  Direction, not a verdict: at {c.n_games} games the {label} edge")
                add(f"  points the OPPOSITE way — {c.diff * 100:+.3f}c, CI "
                    f"[{c.lo * 100:+.3f}, {c.hi * 100:+.3f}]c, entirely below zero.")
                add("  The tails are quieter at the open than mid-game, not livelier.")
                add("  If that holds to 10 games this is a FAIL, not a pass in waiting.")
        # And the control already undercuts the edge that did reach sample.
        if (study.tail_close.has_sample and study.body_close.lo is not None
                and study.body_close.diff > study.tail_close.diff > 0):
            add("")
            add(f"  Also note the control: at the close the BODY rungs gain "
                f"{study.body_close.diff * 100:+.3f}c")
            add(f"  against the tails' {study.tail_close.diff * 100:+.3f}c — the tails move "
                "LESS than the body,")
            add("  not most. The close effect is a whole-board phase effect, which is")
            add("  what the pre-registered interpretation rule was written to catch.")
    elif both_pass:
        # The pre-registered interpretation rule.
        body_same = (
            study.body_open.diff > 0 and study.body_open.excludes_zero
            and study.body_close.diff > 0 and study.body_close.excludes_zero
        )
        if body_same:
            add("  FAIL as stated — the tails do move more at both edges, but SO DOES")
            add("  THE BODY, by the pre-registered control. The effect is a property")
            add("  of the game's phases, not of the tails. Hypothesis #6 claims the")
            add("  tails specifically, and that claim is not supported.")
        else:
            add("  PASS — tail |move| is higher at BOTH edges than in mid-game, both")
            add("  intervals exclude zero, and the body control does not show the")
            add("  same pattern.")
            add("")
            add("  This is a volatility fact, NOT a trade. It says the tails are")
            add("  livelier at the edges; it does not say anyone is mispricing them.")
            add("  Feed it to ladder-sigma and to QUOTE's adverse-selection picture.")
    else:
        add("  FAIL — the hypothesis requires BOTH edges to be livelier than")
        add("  mid-game with intervals excluding zero. At least one does not.")
    add("")

    add("  Standing caveats")
    add("  * Deep-tier rungs are excluded entirely and cannot be recovered: at a")
    add("    30s cadence against the near tier's 0.20s, any volatility comparison")
    add("    between them measures the sampler (correction C1).")
    add("  * Tail membership is itself endogenous late in a game — a rung is a")
    add("    tail rung in Q4 partly BECAUSE the game is decided. The body control")
    add("    is the check on that, not a decoration.")
    add("  * Overlaps [ladder-sigma.md](../../docs/math/ladder-sigma.md), whose")
    add("    gate is untouched: that asks whether implied sigma is too NARROW,")
    add("    this asks WHEN the tails move.")
    return "\n".join(out)


def main() -> int:
    from core.storage import get_engine, get_sessionmaker

    parser = argparse.ArgumentParser(prog="meridian-tail-volatility")
    parser.parse_args()

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.WARNING)
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))

    Session = get_sessionmaker(get_engine())
    with Session() as session:
        study = run_study(session)
    print(format_report(study))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
