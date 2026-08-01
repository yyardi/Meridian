"""Cross-market divergence scanner: Polymarket vs sportsbook, over time.

The strategy the evidence supports is fading a thin venue toward book
consensus when they diverge. This module instruments it: for every recorded
snapshot cycle, fit the Polymarket totals ladder, compare its implied mean to
the book line, and report how large the gaps ran and how long the windows
lasted. Pure measurement — no model, no fitting to outcomes.

    python -m core.crossmarket

Caveat noted in output: the book line is the median stored consensus for the
game, not time-matched per cycle. Same-provider book totals move ~0.3-0.6
points pregame, so this smears little; the PM side is fully time-resolved.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict

from sqlalchemy import select

from core.backtest.engine import _is_live_provider
from core.feeds.espn_client import ESPNClient
from core.storage import MarketSnapshot, SportsbookOdds, get_engine, get_sessionmaker
from core.team_mapping import orient_for_slug, orientation_from_scoreboard, parse_event_slug
from strategies.wnba_totals.model.curve_fit import LadderRung, fit_from_rungs

UTC = dt.timezone.utc

#: A gap this large, sustained, is a candidate trading window.
WINDOW_POINTS = 2.0


def scan() -> None:
    Session = get_sessionmaker(get_engine())
    with Session() as s:
        snaps = s.execute(
            select(
                MarketSnapshot.event_slug, MarketSnapshot.captured_at,
                MarketSnapshot.line, MarketSnapshot.best_bid, MarketSnapshot.best_ask,
                MarketSnapshot.game_start_time, MarketSnapshot.is_live,
            ).where(MarketSnapshot.sports_market_type == "basketball_team_full_game_total")
        ).all()

    by_event: dict[str, list] = defaultdict(list)
    for row in snaps:
        by_event[row[0]].append(row)

    espn = ESPNClient()
    dates = set()
    for ev in by_event:
        p = parse_event_slug(ev)
        if p:
            dates.update([p.local_date, p.local_date + dt.timedelta(days=1)])
    omap = orientation_from_scoreboard(espn_client=espn, dates=sorted(dates))

    print("CROSS-MARKET DIVERGENCE SCAN — Polymarket implied total vs book line")
    print("=" * 78)
    print(f"{'event':<26}{'cycles':>7}{'book':>7}{'gap avg':>9}{'gap max':>9}"
          f"{'|gap|>=2':>9}{'PM sigma':>9}")
    print("-" * 78)

    total_cycles = total_windows = 0
    latest: list[tuple[str, dt.datetime, float, float]] = []

    with Session() as s2:
        for ev, rows in sorted(by_event.items()):
            p = parse_event_slug(ev)
            o = orient_for_slug(p, omap) if p else None
            if o is None:
                continue

            brows = [r for r in s2.scalars(
                select(SportsbookOdds).where(SportsbookOdds.espn_game_id == o.espn_game_id)
            ).all() if not _is_live_provider(r.provider_name) and r.over_under is not None]
            if not brows:
                continue
            ous = sorted(float(r.over_under) for r in brows)
            book = ous[len(ous) // 2]

            cycles: dict[dt.datetime, list[LadderRung]] = defaultdict(list)
            for _, cat, line, bid, ask, start, live in rows:
                if live or line is None:
                    continue
                if start and cat >= start - dt.timedelta(minutes=10):
                    continue
                cycles[cat].append(LadderRung(
                    float(line),
                    float(bid) if bid is not None else None,
                    float(ask) if ask is not None else None,
                ))

            gaps, sigmas, last_fit = [], [], None
            for cat in sorted(cycles):
                fit = fit_from_rungs(cycles[cat])
                if not fit.ok:
                    continue
                gaps.append(fit.implied_mean - book)
                sigmas.append(fit.implied_stdev)
                last_fit = (cat, fit.implied_mean)

            if not gaps:
                continue
            windows = sum(1 for g in gaps if abs(g) >= WINDOW_POINTS)
            total_cycles += len(gaps)
            total_windows += windows
            print(f"{ev:<26}{len(gaps):>7}{book:>7.1f}"
                  f"{sum(gaps)/len(gaps):>+9.2f}"
                  f"{max(gaps, key=abs):>+9.2f}{windows:>9}"
                  f"{sum(sigmas)/len(sigmas):>9.1f}")

            if last_fit is not None:
                cat, mean = last_fit
                latest.append((ev, cat, mean, mean - book))

    print("-" * 78)
    pct = (total_windows / total_cycles * 100) if total_cycles else 0.0
    print(f"cycles fit: {total_cycles} · cycles with |gap| >= {WINDOW_POINTS:.0f} pts: "
          f"{total_windows} ({pct:.1f}%)")
    print()
    print("LATEST PREGAME READINGS (the live signal)")
    for ev, cat, mean, gap in sorted(latest, key=lambda x: -abs(x[3])):
        flag = "  <-- DIVERGENT" if abs(gap) >= WINDOW_POINTS else ""
        print(f"  {ev:<26} {cat:%m-%d %H:%M}  PM {mean:6.1f}  gap {gap:+.1f}{flag}")
    print()
    print("Book lines are stored consensus, not time-matched per cycle "
          "(same-provider moves average ~0.3-0.6 pts pregame).")


if __name__ == "__main__":
    scan()
