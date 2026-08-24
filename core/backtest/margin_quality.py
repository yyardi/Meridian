"""Where the margin-quality gap lives — a diagnostic, not a gate.

    python -m core.backtest.margin_quality

The headline number behind the moneyline exclusion was a margin MAE comparison:
ours 10.19, the market's 9.65. That number was cited as if it were about the
moneyline. It is not, and cannot be.

**The moneyline and the spread come from the same projection.** ANCHOR prices
the moneyline as `prob_home_win(projected_margin, sigma)` and the spread as
`prob_cover(projected_margin, threshold, sigma)` — the moneyline is the spread
at line 0. A margin estimate worse than the market's indicts both markets by
exactly the same amount. Since the spread sat in `ANCHOR_MARKETS` throughout,
the MAE could never have been the reason the moneyline alone was barred. (The
inconsistency was caught by the operator, not by this codebase.)

So the honest question is not "is our margin worse" — it is, on average — but
**where**. A model whose margin is competitive in close games and hopeless in
blowouts is a different animal from one uniformly behind, and only the first
kind is worth trading in the regime it is good at.

Two splits, and the distinction between them matters:

* **Ex-ante, by what the market expected** (|market margin| buckets). Known
  before tip, so a policy may condition on it.
* **Post-hoc, by what actually happened** (|actual margin| buckets). Reported
  because it is diagnostic, but it conditions on the outcome and **no policy
  may gate on it** — you do not know at tip time whether a game will be close.

Uncertainty is bootstrapped over games on the PAIRED difference
(ours − market's) per game, because the two errors on one game are strongly
correlated and differencing first is what removes the shared game difficulty.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.backtest.engine import _is_live_provider, _game_rows
from core.backtest.moneyline import _final_scores
from core.storage import SportsbookOdds
from strategies.wnba_totals.config import CONFIG, WNBATotalsConfig
from strategies.wnba_totals.model.fair_value import (
    estimate_totals_distribution,
    project,
)
from strategies.wnba_totals.model.features import build_matchup_features


@dataclass
class GameMargin:
    espn_game_id: str
    season: int
    month: int
    market_margin: float      # what the market expected, = -handicap
    model_margin: float
    actual_margin: float

    @property
    def model_err(self) -> float:
        return abs(self.model_margin - self.actual_margin)

    @property
    def market_err(self) -> float:
        return abs(self.market_margin - self.actual_margin)

    @property
    def delta(self) -> float:
        """Ours minus theirs. Positive = we are worse on this game."""
        return self.model_err - self.market_err


@dataclass
class Bucket:
    label: str
    games: list[GameMargin] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.games)

    @property
    def model_mae(self) -> float | None:
        return None if not self.games else sum(g.model_err for g in self.games) / self.n

    @property
    def market_mae(self) -> float | None:
        return None if not self.games else sum(g.market_err for g in self.games) / self.n

    @property
    def mean_delta(self) -> float | None:
        return None if not self.games else sum(g.delta for g in self.games) / self.n

    def delta_interval(self, *, resamples: int = 4000, seed: int = 42
                       ) -> tuple[float, float] | None:
        """Bootstrap CI on the PAIRED per-game difference."""
        if self.n < 2:
            return None
        deltas = [g.delta for g in self.games]
        rng = random.Random(seed)
        out = []
        for _ in range(resamples):
            s = sum(rng.choice(deltas) for _ in deltas)
            out.append(s / len(deltas))
        out.sort()
        return out[int(0.025 * len(out))], out[int(0.975 * len(out))]

    def as_dict(self) -> dict:
        ci = self.delta_interval()
        return {
            "bucket": self.label,
            "games": self.n,
            "model_mae": None if self.model_mae is None else round(self.model_mae, 3),
            "market_mae": None if self.market_mae is None else round(self.market_mae, 3),
            "mean_delta": None if self.mean_delta is None else round(self.mean_delta, 3),
            "delta_ci95": None if ci is None else [round(ci[0], 3), round(ci[1], 3)],
            "delta_ci_crosses_zero": None if ci is None else bool(ci[0] < 0 < ci[1]),
        }


def _market_margin(session: Session, espn_game_id: str) -> float | None:
    """Consensus expected home margin. `spread` is the home HANDICAP, so the
    expected margin is its negation — the sign error that nearly shipped once
    already (see moneyline-spread-baseline.md)."""
    rows = [
        r for r in session.execute(
            select(SportsbookOdds.provider_name, SportsbookOdds.spread)
            .where(SportsbookOdds.espn_game_id == espn_game_id)
        ).all()
        if not _is_live_provider(r.provider_name) and r.spread is not None
    ]
    if not rows:
        return None
    spreads = sorted(float(r.spread) for r in rows)
    return -spreads[len(spreads) // 2]


def collect(
    *, session: Session, start_season: int = 2024, end_season: int = 2026,
    model_config: WNBATotalsConfig | None = None,
) -> list[GameMargin]:
    mcfg = model_config or CONFIG
    out: list[GameMargin] = []
    for row in _game_rows(session, start_season, end_season, True):
        market_margin = _market_margin(session, row.espn_game_id)
        if market_margin is None:
            continue
        features = build_matchup_features(
            session=session, home_team_id=row.team_id,
            away_team_id=row.opponent_id, as_of=row.game_date, config=mcfg,
        )
        if features is None or not features.sufficient_data:
            continue
        dist = estimate_totals_distribution(
            as_of=row.game_date, session=session, season=row.season
        )
        projection = project(features, config=mcfg, sigma=dist.sigma)
        if projection is None:
            continue
        home_pts, away_pts = _final_scores(session, row.espn_game_id)
        if home_pts is None or away_pts is None:
            continue
        out.append(GameMargin(
            espn_game_id=row.espn_game_id, season=row.season,
            month=row.game_date.month,
            market_margin=market_margin,
            model_margin=projection.projected_margin,
            actual_margin=float(home_pts - away_pts),
        ))
    return out


def bucket_by_expected(games: list[GameMargin]) -> list[Bucket]:
    """Ex-ante: what the MARKET expected. Known before tip; policy may use it."""
    edges = [(0.0, 3.0), (3.0, 7.0), (7.0, 12.0), (12.0, 999.0)]
    labels = ["expected close (0-3)", "expected 3-7", "expected 7-12", "expected 12+"]
    buckets = [Bucket(label=l) for l in labels]
    for g in games:
        a = abs(g.market_margin)
        for b, (lo, hi) in zip(buckets, edges):
            if lo <= a < hi:
                b.games.append(g)
                break
    return buckets


def bucket_by_actual(games: list[GameMargin]) -> list[Bucket]:
    """Post-hoc: what actually happened. DIAGNOSTIC ONLY — conditions on the
    outcome, so no policy may gate on it."""
    edges = [(0.0, 4.0), (4.0, 10.0), (10.0, 20.0), (20.0, 999.0)]
    labels = ["actual close (0-3)", "actual 4-9", "actual 10-19", "actual 20+"]
    buckets = [Bucket(label=l) for l in labels]
    for g in games:
        a = abs(g.actual_margin)
        for b, (lo, hi) in zip(buckets, edges):
            if lo <= a < hi:
                b.games.append(g)
                break
    return buckets


def bucket_difference(a: Bucket, b: Bucket, *, resamples: int = 4000,
                      seed: int = 7) -> dict:
    """Bootstrap the difference between two buckets' mean deltas.

    **This is the test that answers "is the gap concentrated?", and it is not
    the same as reading whether each bucket's own CI crosses zero.** One bucket
    clearing zero while another does not is compatible with the two being
    identical — small buckets have wide intervals, so "not significant" often
    means "not enough games", not "no gap". Concentration is a claim about the
    DIFFERENCE, so the difference is what gets resampled.
    """
    da = [g.delta for g in a.games]
    db = [g.delta for g in b.games]
    if len(da) < 2 or len(db) < 2:
        return {"comparison": f"{a.label} -> {b.label}", "difference": None}
    rng = random.Random(seed)
    out = []
    for _ in range(resamples):
        ma = sum(rng.choice(da) for _ in da) / len(da)
        mb = sum(rng.choice(db) for _ in db) / len(db)
        out.append(mb - ma)
    out.sort()
    lo, hi = out[int(0.025 * len(out))], out[int(0.975 * len(out))]
    point = (sum(db) / len(db)) - (sum(da) / len(da))
    return {
        "comparison": f"{a.label} -> {b.label}",
        "difference": round(point, 3),
        "ci95": [round(lo, 3), round(hi, 3)],
        "distinguishable_from_zero": not (lo < 0 < hi),
    }


def bucket_by_month(games: list[GameMargin]) -> list[Bucket]:
    by: dict[int, Bucket] = {}
    for g in games:
        by.setdefault(g.month, Bucket(label=f"month {g.month:02d}")).games.append(g)
    return [by[k] for k in sorted(by)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", type=int, default=2024)
    ap.add_argument("--end", type=int, default=2026)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    from core.storage import get_sessionmaker

    Session = get_sessionmaker()
    with Session() as session:
        games = collect(session=session, start_season=args.start, end_season=args.end)

    overall = Bucket(label="ALL", games=games)
    groups = {
        "overall": [overall],
        "ex_ante_expected_margin": bucket_by_expected(games),
        "post_hoc_actual_margin": bucket_by_actual(games),
        "by_month": bucket_by_month(games),
    }
    if args.json:
        print(json.dumps(
            {k: [b.as_dict() for b in v] for k, v in groups.items()}, indent=2
        ))
        return 0

    for name, buckets in groups.items():
        print(f"\n=== {name} ===")
        print(f"{'bucket':>22} {'n':>5} {'ours':>7} {'market':>7} {'delta':>7}  CI95 (paired)")
        for b in buckets:
            d = b.as_dict()
            if d["games"] == 0:
                continue
            ci = d["delta_ci95"]
            ci_s = "n/a" if ci is None else f"[{ci[0]:+.2f}, {ci[1]:+.2f}]"
            star = "" if (ci is None or d["delta_ci_crosses_zero"]) else "  *"
            print(f"{d['bucket']:>22} {d['games']:>5} {d['model_mae']:>7} "
                  f"{d['market_mae']:>7} {d['mean_delta']:>+7} {ci_s:>18}{star}")
    print("\n  * = paired CI excludes zero (a real gap, not noise)")
    print("  Positive delta = OUR margin estimate is worse on that bucket.")

    # The concentration question, tested properly.
    ex, ac = groups["ex_ante_expected_margin"], groups["post_hoc_actual_margin"]
    print("\n=== is the gap CONCENTRATED? (difference between buckets) ===")
    print("  Reading the table above for this is a mistake: one bucket clearing")
    print("  zero while another does not is compatible with them being equal.")
    for a, b in ((ex[0], ex[1]), (ex[0], ex[2]), (ex[0], ex[3]),
                 (ac[0], ac[2]), (ac[0], ac[3])):
        d = bucket_difference(a, b)
        if d["difference"] is None:
            continue
        verdict = ("DISTINGUISHABLE" if d["distinguishable_from_zero"]
                   else "not distinguishable")
        print(f"  {d['comparison']:<48} {d['difference']:+.3f} "
              f"[{d['ci95'][0]:+.2f}, {d['ci95'][1]:+.2f}]  {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
