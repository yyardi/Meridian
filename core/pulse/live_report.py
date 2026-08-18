"""Scoring for the PULSE live run. Money at price, games not rows.

    python -m core.pulse.live_report

Reads ``pulse_decisions``, scores what can honestly be scored, and reports
behind the pre-registered floors (docs/math/pulse-live.md — registered before
the engine's first cycle; the floors and metrics here may not drift from that
document).

Two scoring legs, kept separate because their evidence differs
--------------------------------------------------------------
**Round trips** — entry filled AND its exit filled. Capture per contract is
the price difference in the position's own direction; dollars are capture ×
contracts against the entry stake. This is the strategy the operator actually
described (capitalize repeatedly in-game), and it inherits the fill rule's
optimism TWICE (once per leg), so its profits are upper bounds of upper
bounds. Losses remain trustworthy.

**Ride to settlement** — entry filled, exit never filled, market settled.
Money at price (C11): a `yes` position staked `entry`, returned `settlement`;
a `no` position staked `1 − entry`, returned `1 − settlement` (V14 frame).
This leg is the honest fallback, not the plan, and it is reported separately
so a good exit engine cannot hide a bad entry engine or vice versa.

Clustering is by event (C4): one game's ladder emits correlated decisions,
and the row-level interval would be wrong by roughly the square root of the
per-game count. The clustered machinery is the adverse-selection study's own.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import text

from core.pulse.storage import NO, YES
from core.quote.adverse_selection import ClusteredMean, clustered_mean

#: Pre-registered floors (docs/math/pulse-live.md, fixed before the first
#: cycle). Below either, the report prints NO DATA with counts only.
FLOOR_GAMES = 10
FLOOR_ENTRY_FILLS = 100


def round_trip_capture(*, side: str, entry_price: float, exit_price: float) -> float:
    """Per-contract capture of a completed round trip, in dollars (YES frame
    prices; the sign conversion is the direction, nothing else)."""
    if side == YES:
        return exit_price - entry_price
    if side == NO:
        return entry_price - exit_price
    raise ValueError(f"unknown side {side!r}")


def settlement_score(*, side: str, entry_price: float, settlement: int) -> tuple[float, float]:
    """(staked, returned) per contract for a ride-to-settlement leg (C11/V14)."""
    if side == YES:
        return entry_price, float(settlement)
    if side == NO:
        return 1.0 - entry_price, 1.0 - float(settlement)
    raise ValueError(f"unknown side {side!r}")


@dataclass
class LiveReport:
    version: str
    n_decisions: int
    n_entries: int
    n_entry_fills: int
    n_round_trips: int
    n_rides_settled: int
    n_games: int                      # distinct events with at least one entry fill
    trip_staked: float
    trip_pnl: float
    ride_staked: float
    ride_returned: float
    trip_roi_clustered: ClusteredMean | None
    ride_roi_clustered: ClusteredMean | None

    @property
    def at_floor(self) -> bool:
        return self.n_entry_fills >= FLOOR_ENTRY_FILLS and self.n_games >= FLOOR_GAMES

    @property
    def verdict(self) -> str:
        if not self.at_floor:
            return "NO DATA"
        cm = self.trip_roi_clustered
        if cm is None:
            return "NO DATA"
        if cm.mean > 0 and cm.lo > 0:
            return "PASS (upper bound — the fill rule is optimistic on both legs)"
        return "FAIL"


def build_report(session) -> dict[str, LiveReport]:
    """One report PER ESTIMATES VERSION. Never a combined number: v1 and v2
    are different models, and blending model generations in one performance
    figure is the exact bug the era-separation work (PR #23) deleted."""
    entries = session.execute(text("""
        SELECT e.id, e.event_slug, e.side, e.limit_price, e.contracts,
               e.stake_usd, e.filled_at, e.settlement, e.estimates_version,
               x.limit_price AS exit_price, x.filled_at AS exit_filled_at
        FROM pulse_decisions e
        LEFT JOIN LATERAL (
              SELECT limit_price, filled_at FROM pulse_decisions
              WHERE entry_id = e.id AND action = 'exit'
                AND filled_at IS NOT NULL
              ORDER BY filled_at LIMIT 1
        ) x ON TRUE
        WHERE e.action = 'enter'
    """)).all()
    counts = dict(session.execute(text("""
        SELECT estimates_version, count(*) FROM pulse_decisions
        GROUP BY estimates_version
    """)).all())

    by_version: dict[str, list] = defaultdict(list)
    for e in entries:
        by_version[e.estimates_version].append(e)

    out: dict[str, LiveReport] = {}
    for version, version_entries in by_version.items():
        trip_roi_by_game: dict[str, list[float]] = defaultdict(list)
        ride_roi_by_game: dict[str, list[float]] = defaultdict(list)
        n_entry_fills = n_round_trips = n_rides_settled = 0
        trip_staked = trip_pnl = ride_staked = ride_returned = 0.0
        games: set[str] = set()

        for e in version_entries:
            if e.filled_at is None:
                continue
            n_entry_fills += 1
            games.add(e.event_slug)
            entry_price = float(e.limit_price)
            contracts = float(e.contracts)
            side = e.side
            cost_per_contract = entry_price if side == YES else 1.0 - entry_price
            if cost_per_contract <= 0 or contracts <= 0:
                continue
            if e.exit_filled_at is not None:
                capture = round_trip_capture(
                    side=side, entry_price=entry_price, exit_price=float(e.exit_price))
                n_round_trips += 1
                trip_staked += cost_per_contract * contracts
                trip_pnl += capture * contracts
                trip_roi_by_game[e.event_slug].append(capture / cost_per_contract)
            elif e.settlement is not None:
                staked, returned = settlement_score(
                    side=side, entry_price=entry_price, settlement=int(e.settlement))
                n_rides_settled += 1
                ride_staked += staked * contracts
                ride_returned += returned * contracts
                ride_roi_by_game[e.event_slug].append(returned / staked - 1.0)

        out[version] = LiveReport(
            version=version,
            n_decisions=int(counts.get(version, 0)),
            n_entries=len(version_entries),
            n_entry_fills=n_entry_fills,
            n_round_trips=n_round_trips,
            n_rides_settled=n_rides_settled,
            n_games=len(games),
            trip_staked=trip_staked,
            trip_pnl=trip_pnl,
            ride_staked=ride_staked,
            ride_returned=ride_returned,
            trip_roi_clustered=clustered_mean(trip_roi_by_game),
            ride_roi_clustered=clustered_mean(ride_roi_by_game),
        )
    return out


def format_report(reports: dict[str, LiveReport]) -> str:
    out: list[str] = []
    add = out.append
    add("PULSE LIVE RUN — shadow decisions, money at price (C11), by game (C4)")
    add("=" * 78)
    add(f"floors (pre-registered): >= {FLOOR_ENTRY_FILLS} filled entries AND "
        f">= {FLOOR_GAMES} games — applied PER ESTIMATES VERSION")
    if not reports:
        add("")
        add("NO DATA — no decisions recorded. The engine has not run against a")
        add("live stream, which is different from running and finding nothing.")
        return "\n".join(out)
    for version in sorted(reports):
        add("")
        add(_format_one(reports[version]))
    return "\n".join(out)


def _format_one(r: LiveReport) -> str:
    out: list[str] = []
    add = out.append
    add(f"[estimates {r.version}]")
    add(f"decisions recorded            : {r.n_decisions:,}")
    add(f"entries decided / filled      : {r.n_entries:,} / {r.n_entry_fills:,}")
    add(f"round trips completed         : {r.n_round_trips:,}")
    add(f"rides settled                 : {r.n_rides_settled:,}")
    add(f"distinct games with a fill    : {r.n_games}")
    if not r.at_floor:
        add("")
        add(f"VERDICT: NO DATA — floors are {FLOOR_ENTRY_FILLS} filled entries / "
            f"{FLOOR_GAMES} games. Counts only; no performance number is printed")
        add("below a floor, and that is the registration, not shyness.")
        return "\n".join(out)
    add("")
    add(f"[round trips]  staked ${r.trip_staked:,.2f}  pnl ${r.trip_pnl:+,.2f}")
    cm = r.trip_roi_clustered
    if cm is not None:
        add(f"  per-$ capture, clustered    : {cm.mean:+.4f}  "
            f"95% CI [{cm.lo:+.4f}, {cm.hi:+.4f}]  (G={cm.n_clusters})")
    add(f"[rides]        staked ${r.ride_staked:,.2f} -> returned ${r.ride_returned:,.2f}")
    cm = r.ride_roi_clustered
    if cm is not None:
        add(f"  ROI, clustered              : {cm.mean:+.4f}  "
            f"95% CI [{cm.lo:+.4f}, {cm.hi:+.4f}]  (G={cm.n_clusters})")
    add("")
    add(f"VERDICT: {r.verdict}")
    add("")
    add("Fill-rule caveat, doubled: a round trip needed TWO optimistic fills.")
    add("Losses are trustworthy; profits are upper bounds and authorise nothing.")
    return "\n".join(out)


def main() -> int:
    from core.storage import get_engine, get_sessionmaker

    Session = get_sessionmaker(get_engine())
    with Session() as s:
        print(format_report(build_report(s)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
