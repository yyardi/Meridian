"""Cross-venue gap analysis: Polymarket vs Kalshi.

Pre-registered gate (fixed 2026-08-05, before any matched data existed)
-----------------------------------------------------------------------
No conclusion about the venue gap may be drawn until **at least 10 matched
games** have same-minute pregame snapshots on both venues. When the gate is
met, report exactly two statistics, computed on matched contracts and
clustered by game:

1. **Median |mid gap|** — |Polymarket mid − Kalshi mid| on contracts matched
   by market type and identical line (a Kalshi ``floor_strike`` of 15.5 on
   team X matches a Polymarket spread line of 15.5 quoted from team X, and
   nothing else — a half-point off is basis, not a match). Mids are paired at
   the same minute: snapshots whose ``captured_at`` differ by more than 60s do
   not pair.
2. **Sign persistence** — of matched pairs where the gap is nonzero, the
   fraction of games whose *game-level median* gap keeps one sign across the
   pregame window. Clustering by game is mandatory: 360 pregame minutes of one
   game are one observation of the venue relationship, not 360.

The 10-game minimum is the same lesson as PULSE (837k rows was still a 3-game
sample): rows are not games, and per-minute snapshots are wildly dependent
within a game.

Deliberately NOT reported: anything resembling a tradable edge, fee-adjusted
or otherwise. That is a later, separately registered question. This module's
only job when the gate is met is to say how far apart two transactable prices
sit and whether the sign is stable.


IMPLEMENTATION NOTES (added 2026-08-07; the spec above is unchanged)
====================================================================

The gate function was weaker than the gate it implements
--------------------------------------------------------
The pre-registration requires 10 matched games with same-minute pregame
snapshots **on both venues**. The original `count_matched_games` counted games
with a Polymarket *slug* and at least one **Kalshi** snapshot — it never
checked that any Polymarket snapshot existed, let alone a same-minute one.

Measured 2026-08-07 against the local mirror: that proxy read **10** and the
gate it stands for read **7**, because three games had Kalshi data and no
Polymarket data *locally*. That was mirror staleness, not absence — the
Polymarket *pregame* recorder writes to the primary while `market_snapshots` is
locally authored for the live stream, and `sync_local` **refuses** `--stream`
(an id-keyed upsert would destroy local ticks that cannot be refetched).

**So the full-sample run reads the primary, read-only.** Against it the gate is
met: **10 comparable games, 773 pairs, 61 contracts**. Running this module
against the local mirror will report fewer games and is not wrong — it is a
different, smaller sample. The gate number depends on which database you ask.

So `count_matched_games` is kept as what it actually measures — discovery
coverage — and the gate now runs on `count_comparable_games`, which requires a
real same-minute pair on a line-identical contract. Both are reported, because
a proxy that disagrees with its own gate should be visible rather than quietly
replaced.

Line-identical, and why so little matches
------------------------------------------
The spec is strict on purpose: "a half-point off is basis, not a match".
Measured across the 10 discovered games:

* **Totals** — both venues list 9 rungs on every game at 3-point spacing, and
  in **7 of 10 games the two ladders are offset by exactly 1.0 point** (Kalshi
  180.5/183.5/..., Polymarket 181.5/184.5/...). Three games coincide.
  **26 line-identical totals out of 90 Kalshi strikes against 90 Polymarket.**
* **Spreads** — 29 line-identical out of 74 Kalshi against 60 Polymarket.
* **Moneyline** — matches by construction: one team-wins contract per side,
  no line to disagree about.

That is a fact about the two boards, not about the gap, and it is reported
below the gate because it is a precondition for the comparison rather than a
conclusion from it.

Frames, in the YES direction, per V14/V15/V20
---------------------------------------------
Every mid is converted to the probability of the SAME outcome before
differencing. Getting one of these backwards inverts a gap while leaving it in
[0, 1], which is the failure mode V15 exists to name.

* **Totals** — Polymarket YES = OVER the line (V14); Kalshi "Over X points
  scored" YES = the same event when line == strike. Direct.
* **Spreads** — Polymarket `-neg-X` quoted from team T means T *gives* X, i.e.
  T wins by more than X, which is exactly Kalshi's "T wins by over X". Direct.
  Polymarket `-pos-X` from T means T *gets* X, i.e. T loses by less than X or
  wins — the **complement** of "the opponent wins by over X", so it pairs with
  the opponent's Kalshi contract as `1 - kalshi_mid`.
* **Moneyline** — Polymarket YES = the slug's first team wins (V20); Kalshi's
  ticker suffix names the team. Paired on the same team.

Pairing tolerance is **60 seconds and is pinned by the spec above**, not chosen
here. Kalshi records at 60s and Polymarket's pregame sweep is far slower, so
the binding constraint is Polymarket's cadence, and the report states the
achieved gap distribution rather than assuming it.
"""

from __future__ import annotations

import datetime as dt
import statistics
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import distinct, func, select, text

from core.storage import KalshiGame, KalshiSnapshot

#: The pre-registered minimum. Do not lower it; a smaller n means "wait".
MIN_MATCHED_GAMES = 10


def count_matched_games(session) -> int:
    """Games linked to a Polymarket event that actually have Kalshi snapshots.

    **This is discovery coverage, not the gate.** It says a Kalshi game was
    mapped to a Polymarket event and that Kalshi recorded it — nothing about
    whether Polymarket did. Kept because it is the recorder's own progress
    metric; `count_comparable_games` is what the pre-registration asks for.
    """
    return session.scalar(
        select(func.count(distinct(KalshiGame.game_key)))
        .select_from(KalshiGame)
        .join(KalshiSnapshot, KalshiSnapshot.game_key == KalshiGame.game_key)
        .where(KalshiGame.polymarket_event_slug.is_not(None))
    ) or 0


def count_comparable_games(session) -> int:
    """Games with a real same-minute pregame pair on a line-identical contract.

    The gate as the pre-registration states it: "at least 10 matched games have
    same-minute pregame snapshots **on both venues**". Computed by actually
    building the pairs rather than by counting rows on one side.
    """
    return len({p.game_key for p in build_pairs(session)})


def gate_status(session) -> dict:
    """Where the sample stands against the pre-registered gate.

    Reports the proxy alongside the real gate. They disagreed on 2026-08-07
    (10 vs 7) and a silent substitution would have hidden that.
    """
    discovered = count_matched_games(session)
    comparable = count_comparable_games(session)
    return {
        "discovered_games": discovered,
        "comparable_games": comparable,
        "required": MIN_MATCHED_GAMES,
        "gate_met": comparable >= MIN_MATCHED_GAMES,
        "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


# --------------------------------------------------------------------- #
# Matching — the part the whole result rests on
# --------------------------------------------------------------------- #

#: Pinned by the spec above: "snapshots whose captured_at differ by more than
#: 60s do not pair". Not a tunable.
PAIR_TOLERANCE_SECONDS = 60.0

_PM_TYPE = {
    "total": "basketball_team_full_game_total",
    "spread": "basketball_team_full_game_spread",
    "winner": "basketball_team_full_game_winner",
}


@dataclass(frozen=True)
class Contract:
    """One venue's contract, reduced to what matching needs."""

    game_key: str
    market_type: str            # 'total' | 'spread' | 'winner'
    #: The line both venues must agree on exactly. None for moneylines.
    line: float | None
    #: ESPN code of the team the YES side belongs to. None for totals.
    team: str | None
    #: True when this venue's YES is the COMPLEMENT of the paired outcome.
    invert: bool = False


@dataclass(frozen=True)
class Pair:
    """One line-identical contract, priced on both venues at the same minute."""

    game_key: str
    market_type: str
    line: float | None
    team: str | None
    captured_pm: dt.datetime
    captured_kalshi: dt.datetime
    pm_mid: float               # YES frame of the shared outcome
    kalshi_mid: float           # YES frame of the SAME outcome
    hours_to_tipoff: float | None

    @property
    def lag_seconds(self) -> float:
        return abs((self.captured_pm - self.captured_kalshi).total_seconds())

    @property
    def gap(self) -> float:
        """Polymarket minus Kalshi, same outcome, same frame."""
        return self.pm_mid - self.kalshi_mid


def kalshi_team_from_ticker(ticker: str) -> str | None:
    """ESPN code from a Kalshi ticker suffix.

    `KXWNBAGAME-26AUG05DALWSH-DAL` -> DAL;
    `KXWNBASPREAD-26AUG06LVIND-IND10` -> IND (digits are the strike marker).
    """
    from core.kalshi.mapping import KALSHI_TO_ESPN

    tail = (ticker or "").rsplit("-", 1)[-1]
    code = "".join(ch for ch in tail if ch.isalpha()).upper()
    return KALSHI_TO_ESPN.get(code)


def pm_spread_team_and_invert(
    market_slug: str, line: float, first_espn: str, second_espn: str
) -> tuple[str, float, bool] | None:
    """(team the Kalshi contract must name, strike, invert) for a PM spread.

    `-neg-X` from team T is "T wins by more than X" — Kalshi's own wording, so
    it pairs with T's contract directly. `-pos-X` from T is "T loses by less
    than X, or wins", which is the complement of "the opponent wins by over X",
    so it pairs with the OPPONENT's contract and inverts.
    """
    if "-neg-" in market_slug:
        return first_espn, abs(line), False
    if "-pos-" in market_slug:
        return second_espn, abs(line), True
    return None


def build_pairs(session) -> list[Pair]:
    """Every line-identical contract priced within 60s on both venues.

    Pregame only, per the spec ("same-minute *pregame* snapshots"). Each
    Polymarket snapshot is paired with the NEAREST Kalshi snapshot of the
    matched contract, and dropped if that nearest one is more than 60s away.

    **One pair per (contract, Kalshi observation).** Kalshi records every 60s;
    Polymarket's pregame sweep is denser and, critically, *uneven across
    contracts*. Without this rule a single Kalshi row is reused by every
    Polymarket snapshot near it, and the pair count per contract becomes a fact
    about Polymarket's cadence rather than about the market.

    Measured on 26AUG05PHXATL totals before the rule: four contracts produced
    17 pairs each and four produced 2,398 — a 140x imbalance inside one game.
    The mean signed gap read +0.30c, of which essentially all came from one
    dense contract; deduplicated it is **-0.01c**. The pre-registered *median*
    was unaffected (0.00c either way), which is exactly why the spec asks for a
    median — but every mean computed on these pairs inherits the bias, so the
    rule is applied at construction rather than left to each statistic.
    """
    games = session.execute(text("""
        SELECT game_key, polymarket_event_slug, first_espn, second_espn
        FROM kalshi_games WHERE polymarket_event_slug IS NOT NULL
    """)).all()

    pairs: list[Pair] = []
    for g in games:
        if not (g.first_espn and g.second_espn):
            continue

        # Kalshi side: strike + team per ticker, then its price series.
        terms = {
            r.ticker: r for r in session.execute(text("""
                SELECT DISTINCT ON (ticker) ticker, market_type, floor_strike
                FROM kalshi_contracts WHERE game_key = :g
                ORDER BY ticker, captured_at DESC
            """), {"g": g.game_key}).all()
        }
        kseries: dict[str, list[tuple[dt.datetime, float]]] = defaultdict(list)
        for r in session.execute(text("""
            SELECT ticker, captured_at, yes_bid, yes_ask FROM kalshi_snapshots
            WHERE game_key = :g AND yes_bid IS NOT NULL AND yes_ask IS NOT NULL
            ORDER BY ticker, captured_at
        """), {"g": g.game_key}).all():
            b, a = float(r.yes_bid), float(r.yes_ask)
            if a > b:
                kseries[r.ticker].append((r.captured_at, (a + b) / 2.0))

        # Index Kalshi contracts by (market_type, line, team).
        kindex: dict[tuple, str] = {}
        for ticker, t in terms.items():
            team = kalshi_team_from_ticker(ticker)
            line = float(t.floor_strike) if t.floor_strike is not None else None
            if t.market_type == "total":
                kindex[("total", line, None)] = ticker
            elif t.market_type in ("spread", "winner") and team:
                kindex[(t.market_type, line, team)] = ticker

        # Kalshi is the coarser side (60s); Polymarket's pregame sweep is
        # denser and uneven. Claiming each Kalshi observation at most once —
        # by the PM snapshot closest to it — stops one Kalshi row being reused
        # hundreds of times.
        claimed: dict[tuple, tuple[float, int]] = {}

        # Polymarket side, pregame only.
        for r in session.execute(text("""
            SELECT market_slug, sports_market_type, line, captured_at,
                   best_bid, best_ask, game_start_time
            FROM market_snapshots
            WHERE event_slug = :e AND is_live IS FALSE
              AND best_bid IS NOT NULL AND best_ask IS NOT NULL
            ORDER BY captured_at
        """), {"e": g.polymarket_event_slug}).all():
            b, a = float(r.best_bid), float(r.best_ask)
            if a <= b:
                continue
            pm_mid = (a + b) / 2.0
            mt = {v: k for k, v in _PM_TYPE.items()}.get(r.sports_market_type)
            if mt is None:
                continue

            invert = False
            if mt == "total":
                if r.line is None:
                    continue
                key = ("total", float(r.line), None)
                team = None
            elif mt == "spread":
                if r.line is None:
                    continue
                resolved = pm_spread_team_and_invert(
                    r.market_slug, float(r.line), g.first_espn, g.second_espn)
                if resolved is None:
                    continue
                team, strike, invert = resolved
                key = ("spread", strike, team)
            else:                                   # winner
                team = g.first_espn                 # PM YES = slug's first team (V20)
                key = ("winner", None, team)

            ticker = kindex.get(key)
            if ticker is None or not kseries.get(ticker):
                continue

            # Nearest Kalshi observation, dropped beyond the pinned tolerance.
            best = min(kseries[ticker],
                       key=lambda kv: abs((kv[0] - r.captured_at).total_seconds()))
            if abs((best[0] - r.captured_at).total_seconds()) > PAIR_TOLERANCE_SECONDS:
                continue

            kmid = 1.0 - best[1] if invert else best[1]
            hours = (
                (r.game_start_time - r.captured_at).total_seconds() / 3600.0
                if r.game_start_time is not None else None
            )
            # One pair per (contract, KALSHI observation) — see `build_pairs`.
            slot = (ticker, best[0])
            prior = claimed.get(slot)
            lag = abs((best[0] - r.captured_at).total_seconds())
            if prior is not None and prior[0] <= lag:
                continue
            claimed[slot] = (lag, len(pairs) if prior is None else prior[1])
            if prior is not None:
                pairs[prior[1]] = Pair(
                    game_key=g.game_key, market_type=mt,
                    line=float(r.line) if r.line is not None else None,
                    team=team, captured_pm=r.captured_at, captured_kalshi=best[0],
                    pm_mid=pm_mid, kalshi_mid=kmid, hours_to_tipoff=hours,
                )
                continue
            pairs.append(Pair(
                game_key=g.game_key, market_type=mt,
                line=float(r.line) if r.line is not None else None,
                team=team, captured_pm=r.captured_at, captured_kalshi=best[0],
                pm_mid=pm_mid, kalshi_mid=kmid, hours_to_tipoff=hours,
            ))
    return pairs


# --------------------------------------------------------------------- #
# The two pre-registered statistics
# --------------------------------------------------------------------- #


def game_medians(pairs: list[Pair]) -> dict[str, float]:
    """Per-game median SIGNED gap. One number per game — the sample unit."""
    by_game: dict[str, list[float]] = defaultdict(list)
    for p in pairs:
        by_game[p.game_key].append(p.gap)
    return {g: statistics.median(v) for g, v in by_game.items()}


def median_abs_gap(pairs: list[Pair]) -> float | None:
    """Statistic 1: median |mid gap|, as a median of per-game medians.

    Median-of-medians rather than a pooled median: one game contributes
    thousands of correlated per-minute rows, and pooling would weight games by
    how long each happened to be recorded.
    """
    by_game: dict[str, list[float]] = defaultdict(list)
    for p in pairs:
        by_game[p.game_key].append(abs(p.gap))
    if not by_game:
        return None
    return statistics.median(statistics.median(v) for v in by_game.values())


#: Below this, a "gap" is floating-point residue, not a price difference. Both
#: venues tick at 1 cent, so the smallest representable real gap is 0.005 (a
#: half-tick of mid). Measured on the 2026-08-10 full-sample run: one game's
#: median came out +5.55e-17 — arithmetic dust from (bid+ask)/2 — and without
#: this guard it would have counted as a "signed" game in statistic 2. This
#: implements the registered "nonzero" wording; it does not change it.
SIGN_EPSILON = 1e-9


def sign_persistence(pairs: list[Pair]) -> tuple[float | None, int, int]:
    """Statistic 2: fraction of games whose game-level median gap shares a sign.

    Games whose median gap is zero (within SIGN_EPSILON — see above) carry no
    sign and are excluded from the denominator — the spec asks about pairs
    "where the gap is nonzero". Returns (fraction, games_with_a_sign,
    games_total).
    """
    medians = game_medians(pairs)
    signed = {g: m for g, m in medians.items() if abs(m) > SIGN_EPSILON}
    if not signed:
        return None, 0, len(medians)
    positives = sum(1 for m in signed.values() if m > 0)
    fraction = max(positives, len(signed) - positives) / len(signed)
    return fraction, len(signed), len(medians)


def clustered_mean_abs_gap(pairs: list[Pair]):
    """Game-clustered mean |gap| with a 95% interval. Supporting, not gated."""
    from core.quote.adverse_selection import clustered_mean

    by_game: dict[str, list[float]] = defaultdict(list)
    for p in pairs:
        by_game[p.game_key].append(abs(p.gap))
    return clustered_mean(by_game)


def matchability(session) -> dict:
    """How many contracts could be compared at all — a precondition, not a gap.

    Reported below the gate because "the ladders barely overlap" is a fact
    about the two boards rather than a conclusion about their prices.
    """
    rows = session.execute(text("""
        SELECT g.game_key, g.polymarket_event_slug ev FROM kalshi_games g
        JOIN kalshi_snapshots k ON k.game_key = g.game_key
        WHERE g.polymarket_event_slug IS NOT NULL GROUP BY 1, 2
    """)).all()
    out = {"total": [0, 0, 0], "spread": [0, 0, 0]}
    for r in rows:
        for mt, pm_type in (("total", _PM_TYPE["total"]), ("spread", _PM_TYPE["spread"])):
            ks = {float(x[0]) for x in session.execute(text("""
                SELECT DISTINCT floor_strike FROM kalshi_contracts
                WHERE game_key=:g AND market_type=:m AND floor_strike IS NOT NULL
            """), {"g": r.game_key, "m": mt}).all()}
            ps = {abs(float(x[0])) for x in session.execute(text("""
                SELECT DISTINCT line FROM market_snapshots
                WHERE event_slug=:e AND sports_market_type=:m AND line IS NOT NULL
            """), {"e": r.ev, "m": pm_type}).all()}
            out[mt][0] += len(ks)
            out[mt][1] += len(ps)
            out[mt][2] += len(ks & ps)
    return {k: {"kalshi_strikes": v[0], "polymarket_lines": v[1], "line_identical": v[2]}
            for k, v in out.items()}


#: Hours-to-tip-off buckets for the V22 secondary. A headline gap computed
#: mostly far from tip-off is a clock artifact, not a venue fact.
HORIZON_BUCKETS: tuple[tuple[str, float, float], ...] = (
    ("0-1h", 0.0, 1.0),
    ("1-3h", 1.0, 3.0),
    ("3-6h", 3.0, 6.0),
    ("6-12h", 6.0, 12.0),
    (">12h", 12.0, 1e9),
)


def gap_by_horizon(pairs: list[Pair]) -> dict[str, tuple[int, float | None]]:
    """Median |gap| per hours-to-tip bucket. Secondary, per V22."""
    buckets: dict[str, list[float]] = defaultdict(list)
    for p in pairs:
        h = p.hours_to_tipoff
        if h is None:
            continue
        for label, lo, hi in HORIZON_BUCKETS:
            if lo <= h < hi:
                buckets[label].append(abs(p.gap))
                break
    return {k: (len(v), statistics.median(v)) for k, v in buckets.items()}


def report(session) -> dict:
    """The two pre-registered statistics — refuses to run before the gate.

    Below the gate this returns the gate status, the matchability counts and
    the pairing diagnostics, and **no price statistics at all**: a partial
    median is exactly the premature verdict the pre-registration exists to
    prevent. Matchability is a precondition (can these boards be compared?),
    not a conclusion (how far apart are they?), so it is safe to show.
    """
    status = gate_status(session)
    pairs = build_pairs(session)
    status["matched_pairs"] = len(pairs)
    status["pair_games"] = len({p.game_key for p in pairs})
    status["matchability"] = matchability(session)
    if pairs:
        lags = sorted(p.lag_seconds for p in pairs)
        status["pair_lag_seconds"] = {
            "median": lags[len(lags) // 2],
            "p90": lags[int(0.9 * (len(lags) - 1))],
            "max": lags[-1],
            "tolerance": PAIR_TOLERANCE_SECONDS,
        }

    if not status["gate_met"]:
        status["statistics"] = None
        status["note"] = (
            f"Gate NOT met: {status['comparable_games']} comparable games "
            f"against a pre-registered minimum of {MIN_MATCHED_GAMES}. No "
            "price statistics are reported. (The discovery proxy reads "
            f"{status['discovered_games']} — see the module docstring.)"
        )
        return status

    cl = clustered_mean_abs_gap(pairs)
    fraction, signed_games, total_games = sign_persistence(pairs)
    status["statistics"] = {
        "median_abs_gap": median_abs_gap(pairs),
        "sign_persistence": fraction,
        "games_with_a_signed_median": signed_games,
        "games_total": total_games,
        "per_game_median_signed_gap": game_medians(pairs),
        "mean_abs_gap_clustered": None if cl is None else {
            "mean": cl.mean, "lo": cl.lo, "hi": cl.hi, "games": cl.n_clusters,
        },
        "gap_by_hours_to_tipoff": gap_by_horizon(pairs),
    }
    return status
