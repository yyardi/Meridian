"""Experiment 5 — adverse selection against a resting quote.

The thesis, and why it is the whole question for QUOTE
-----------------------------------------------------
The at-the-money spread on this venue is ~3c live and ~6c pregame — 6-12% of
contract value, against ~0.01% in equities. A spread that wide means nobody is
making this market, and you do not need microsecond infrastructure to compete
with nobody.

That argument is only half of one. A market maker does not earn the spread; it
earns the spread **minus adverse selection**. Your resting bid is filled
precisely when someone wants to sell, and the reason they want to sell is
usually that the price is about to fall. Get filled often enough at the wrong
moment and a 3c spread is a 3c invitation to lose money slowly.

So this module asks one question and answers it from recorded snapshots alone:

    If you had a resting quote at the best bid (or offer), how far does the
    mid move against you within 30 seconds, and does the half-spread you
    captured cover it?

No orders. No model. No fill simulator beyond the one stated below.


PRE-REGISTERED GATE — fixed before any number was computed
----------------------------------------------------------
Written 2026-08-02, prior to running this against any data.

    PASS  requires ALL of:
      (1) mean net capture per filled quote > 0
      (2) the 95% confidence interval on that mean excludes zero
      (3) n >= 500 quote-windows
      (4) those windows spread across >= 10 distinct games

    FAIL  if (3) and (4) are met but (1) or (2) is not.

    NO DATA  if (3) or (4) is not met. Zero or few windows is not a null
      result — it means the experiment has not run.

The confidence interval is **clustered by game**, not by row. One game emits
~130 correlated ladder rows sampled every second; treating those as
independent would shrink the interval by roughly sqrt(rows-per-game) and
manufacture significance out of autocorrelation. The row-level interval is
reported alongside purely to show how large that lie would have been.

Condition (4) is the one that usually binds, and it is deliberate: sample size
in this project is games, not rows.


How a quote window is built
---------------------------
For each market snapshot at time `t` with a two-sided quote:

    b = best bid,  a = best ask,  m = (a+b)/2,  s = a-b

Two hypothetical resting quotes are considered, a bid at `b` and an offer at
`a`. At the end of the horizon we observe `m_H`, the mid at `t+H`.

**Fill rule.** The resting bid is treated as filled if `m_H <= b` — the mid
came down to meet it. The offer is filled if `m_H >= a`. This is the weakest
assumption the data supports, and its direction matters (see the caveat).

**P&L.** A filled bid leaves you long one contract at `b`, marked at `m_H`:

    net_bid  = m_H - b  =  (m - b)  +  (m_H - m)  =  s/2  +  dmid
    net_ask  = a - m_H  =  (a - m)  -  (m_H - m)  =  s/2  -  dmid

which is the decomposition the whole question is about: **half-spread captured,
plus the mid move you were run over by.** Positive means the spread covered the
adverse selection; negative means it did not.

Fees are taken as zero rather than as a maker rebate. A rebate would only make
the result look better, and a gate that can be passed by an accounting
assumption is not a gate.


Two honesty constraints, both structural
----------------------------------------
**The fill rule is biased toward optimism, and by a known sign.** Between two
snapshots we see no path — only endpoints. A mid that dipped below `b` and
recovered inside the window filled you and is invisible here, so this
undercounts exactly the fills that hurt. Therefore:

    a FAIL from this measurement is trustworthy (real losses are worse);
    a PASS is NOT (real fills include the transient dips we cannot see).

This asymmetry is why a PASS here would still not authorise building QUOTE on
its own.

**Cadence bounds what is observable.** Snapshots recorded before 2026-08-02
were sampled every ~30s, so a 30s horizon is a single hop with no interior at
all. From 2026-08-02 the live recorder samples at ~1s, and the same code then
sees ~30 interior points per window. The report states which regime the data
came from, because the same number means different things in each.

    python -m core.quote.adverse_selection
    python -m core.quote.adverse_selection --horizon 30 --days 7
"""

from __future__ import annotations

import argparse
import datetime as dt
import math
from collections import defaultdict
from dataclasses import dataclass

from scipy import stats
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.storage import MarketSnapshot

UTC = dt.timezone.utc

# --------------------------------------------------------------------- #
# Pre-registered constants. Changing any of these after seeing a result is
# how a gate becomes a rubber stamp.
# --------------------------------------------------------------------- #

#: How long a quote is assumed to rest before being marked.
DEFAULT_HORIZON_SECONDS = 30.0

#: Pair a snapshot with the observation nearest `t+H`, but only inside this
#: multiplicative band. At 30s cadence the only candidate is the next row; at
#: 1s cadence this stops a gap in the stream from silently becoming a 5-minute
#: horizon that gets reported as 30 seconds.
HORIZON_TOLERANCE = (0.5, 2.0)

#: Only rungs a market maker would actually quote. Deep rungs carry measured
#: 22-26c spreads and do not trade; including them would let untradable prices
#: dominate the average in whichever direction they happened to drift.
MIN_MID, MAX_MID = 0.20, 0.80

#: A spread wider than this is not a market-making opportunity, it is an empty
#: book with two stale orders in it.
MAX_SPREAD = 0.15

#: Below this there is no spread to capture and the tick dominates.
MIN_SPREAD = 0.01

#: Maker fee. Zero, not a rebate: see the module docstring.
DEFAULT_FEE = 0.0

# -- the gate --------------------------------------------------------- #
GATE_MIN_WINDOWS = 500
GATE_MIN_GAMES = 10
GATE_CONFIDENCE = 0.95


@dataclass(frozen=True)
class Quote:
    """One observed two-sided quote."""

    game_id: str
    market_slug: str
    captured_at: dt.datetime
    bid: float
    ask: float

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    @property
    def is_quotable(self) -> bool:
        """Would a market maker post here at all?"""
        return (
            MIN_SPREAD <= self.spread <= MAX_SPREAD
            and MIN_MID <= self.mid <= MAX_MID
        )


@dataclass(frozen=True)
class QuoteWindow:
    """A resting quote and what the mid did to it."""

    quote: Quote
    horizon_seconds: float
    mid_at_horizon: float

    @property
    def dmid(self) -> float:
        return self.mid_at_horizon - self.quote.mid

    @property
    def half_spread(self) -> float:
        return self.quote.spread / 2.0

    # -- the two hypothetical resting orders -------------------------- #

    @property
    def bid_filled(self) -> bool:
        return self.mid_at_horizon <= self.quote.bid

    @property
    def ask_filled(self) -> bool:
        return self.mid_at_horizon >= self.quote.ask

    def net_bid(self, fee: float = DEFAULT_FEE) -> float:
        """P&L per contract on a filled resting bid."""
        return (self.mid_at_horizon - self.quote.bid) - fee

    def net_ask(self, fee: float = DEFAULT_FEE) -> float:
        """P&L per contract on a filled resting offer."""
        return (self.quote.ask - self.mid_at_horizon) - fee

    def fills(self, fee: float = DEFAULT_FEE) -> list[float]:
        """Realised P&L for whichever side(s) the mid came to meet."""
        out: list[float] = []
        if self.bid_filled:
            out.append(self.net_bid(fee))
        if self.ask_filled:
            out.append(self.net_ask(fee))
        return out


# --------------------------------------------------------------------- #
# Window construction — pure, so the logic is testable without a database
# --------------------------------------------------------------------- #


def build_windows(
    series: dict[str, list[Quote]],
    *,
    horizon_seconds: float = DEFAULT_HORIZON_SECONDS,
) -> list[QuoteWindow]:
    """Per-market quote series -> the windows that can be marked.

    A quote is paired with the observation nearest `t + horizon`, provided that
    observation falls inside `HORIZON_TOLERANCE`. Quotes with no such partner
    are dropped rather than stretched: a 6-minute gap marked as a 30-second
    horizon would be a different experiment reported under this one's name.
    """
    lo, hi = HORIZON_TOLERANCE
    windows: list[QuoteWindow] = []

    for quotes in series.values():
        ordered = sorted(quotes, key=lambda q: q.captured_at)
        times = [q.captured_at for q in ordered]

        for i, quote in enumerate(ordered):
            if not quote.is_quotable:
                continue
            target = quote.captured_at + dt.timedelta(seconds=horizon_seconds)

            best: Quote | None = None
            best_gap = float("inf")
            for j in range(i + 1, len(ordered)):
                elapsed = (times[j] - quote.captured_at).total_seconds()
                if elapsed > horizon_seconds * hi:
                    break
                if elapsed < horizon_seconds * lo:
                    continue
                gap = abs((times[j] - target).total_seconds())
                if gap < best_gap:
                    best, best_gap = ordered[j], gap
            if best is None:
                continue

            windows.append(
                QuoteWindow(
                    quote=quote,
                    horizon_seconds=(best.captured_at - quote.captured_at).total_seconds(),
                    mid_at_horizon=best.mid,
                )
            )
    return windows


# --------------------------------------------------------------------- #
# Statistics — clustered by game, because rows are not independent
# --------------------------------------------------------------------- #


@dataclass(frozen=True)
class ClusteredMean:
    mean: float
    lo: float
    hi: float
    n: int
    n_clusters: int
    stderr: float

    @property
    def excludes_zero(self) -> bool:
        return (self.lo > 0.0) or (self.hi < 0.0)


def clustered_mean(
    values_by_cluster: dict[str, list[float]], *, confidence: float = GATE_CONFIDENCE
) -> ClusteredMean | None:
    """Mean with a cluster-robust CI, clusters being games.

    One game emits ~130 ladder rows a second, all responding to the same score.
    The row-level standard error treats them as ~130 independent observations
    per second and is wrong by roughly sqrt(rows per game) — enough to turn
    noise into a publishable result. This uses the standard cluster-robust
    sandwich estimator for a mean, with the usual small-sample correction, and
    takes df = G-1 so that few clusters produce an honestly wide interval.
    """
    clusters = {k: v for k, v in values_by_cluster.items() if v}
    n_clusters = len(clusters)
    values = [x for v in clusters.values() for x in v]
    n = len(values)
    if n == 0 or n_clusters < 2:
        return None

    mean = sum(values) / n
    # sandwich: sum over clusters of (sum of within-cluster residuals)^2
    meat = sum((sum(x - mean for x in v)) ** 2 for v in clusters.values())
    correction = n_clusters / (n_clusters - 1)
    variance = correction * meat / (n * n)
    stderr = math.sqrt(variance) if variance > 0 else 0.0

    tcrit = float(stats.t.ppf(0.5 + confidence / 2.0, df=n_clusters - 1))
    return ClusteredMean(
        mean=mean,
        lo=mean - tcrit * stderr,
        hi=mean + tcrit * stderr,
        n=n,
        n_clusters=n_clusters,
        stderr=stderr,
    )


def naive_mean(values: list[float], *, confidence: float = GATE_CONFIDENCE) -> ClusteredMean | None:
    """The row-level interval. Reported only to show how wrong it would be."""
    n = len(values)
    if n < 2:
        return None
    mean = sum(values) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in values) / (n - 1))
    stderr = sd / math.sqrt(n)
    tcrit = float(stats.t.ppf(0.5 + confidence / 2.0, df=n - 1))
    return ClusteredMean(
        mean=mean, lo=mean - tcrit * stderr, hi=mean + tcrit * stderr,
        n=n, n_clusters=n, stderr=stderr,
    )


# --------------------------------------------------------------------- #
# Database
# --------------------------------------------------------------------- #


def load_quotes(
    session: Session,
    *,
    as_of: dt.datetime | None,
    since: dt.datetime | None = None,
    live_only: bool = True,
) -> dict[str, list[Quote]]:
    """Two-sided quotes per market.

    `as_of` is keyword-only with no default, per the project's point-in-time
    rule: this is a retrospective measurement, but nothing stops it being run
    as of a past instant, and making the bound explicit keeps it from being
    forgotten when it does matter.
    """
    stmt = select(
        MarketSnapshot.game_id,
        MarketSnapshot.market_slug,
        MarketSnapshot.captured_at,
        MarketSnapshot.best_bid,
        MarketSnapshot.best_ask,
    ).where(
        MarketSnapshot.best_bid.is_not(None),
        MarketSnapshot.best_ask.is_not(None),
        MarketSnapshot.game_id.is_not(None),
    )
    if live_only:
        stmt = stmt.where(MarketSnapshot.is_live.is_(True))
    if as_of is not None:
        stmt = stmt.where(MarketSnapshot.captured_at < as_of)
    if since is not None:
        stmt = stmt.where(MarketSnapshot.captured_at >= since)

    out: dict[str, list[Quote]] = defaultdict(list)
    for game_id, slug, captured_at, bid, ask in session.execute(stmt).all():
        b, a = float(bid), float(ask)
        if a <= b:
            # Crossed or locked: not a quote anyone could rest inside.
            continue
        out[slug].append(
            Quote(
                game_id=str(game_id),
                market_slug=slug,
                captured_at=captured_at,
                bid=b,
                ask=a,
            )
        )
    return dict(out)


#: Gaps longer than this are treated as separate recording sessions rather
#: than as cadence — an overnight hole is not a poll interval.
MAX_CADENCE_GAP_SECONDS = 3600.0


@dataclass(frozen=True)
class Cadence:
    """How densely the stream was actually sampled.

    Reported as a distribution, not a single median, because the live snapshot
    stream is **bimodal** and a median hides it. Two processes write rows
    flagged `is_live`: the live recorder (~1s since 2026-08-02, ~35s before it)
    and the pregame recorder, which sweeps the whole board every 15 minutes and
    marks whatever is live at the time. So a market's series interleaves
    second-scale and quarter-hour-scale observations, and quoting only the
    median invites reading a 15-minute gap as a 60-second one.
    """

    median: float
    p10: float
    p90: float
    under_2min: float
    n_gaps: int

    @property
    def is_fast(self) -> bool:
        return self.median <= 5.0


def cadence(series: dict[str, list]) -> Cadence | None:
    """Gap distribution between consecutive observations of the same market.

    Accepts any series whose elements carry `captured_at`.
    """
    gaps: list[float] = []
    for items in series.values():
        ordered = sorted(x.captured_at for x in items)
        gaps.extend(
            (b - a).total_seconds()
            for a, b in zip(ordered, ordered[1:])
            if 0 < (b - a).total_seconds() <= MAX_CADENCE_GAP_SECONDS
        )
    if not gaps:
        return None
    gaps.sort()

    def pct(p: float) -> float:
        return gaps[min(len(gaps) - 1, int(p * len(gaps)))]

    return Cadence(
        median=pct(0.50),
        p10=pct(0.10),
        p90=pct(0.90),
        under_2min=sum(1 for g in gaps if g <= 120) / len(gaps),
        n_gaps=len(gaps),
    )


# --------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------- #


def format_report(
    windows: list[QuoteWindow],
    *,
    horizon_seconds: float,
    fee: float = DEFAULT_FEE,
    quotes_examined: int = 0,
    sampling: Cadence | None = None,
) -> str:
    out: list[str] = []
    add = out.append

    add("EXPERIMENT 5 — adverse selection against a resting quote")
    add("=" * 78)
    add(f"horizon                        : {horizon_seconds:.0f}s")
    add(f"quotable band                  : mid in [{MIN_MID}, {MAX_MID}], "
        f"spread in [{MIN_SPREAD}, {MAX_SPREAD}]")
    add(f"maker fee assumed              : {fee:.4f} (zero, not a rebate)")
    add(f"two-sided quotes examined      : {quotes_examined:,}")
    add(f"quote-windows built            : {len(windows):,}")
    if sampling is not None:
        add(f"snapshot cadence               : median {sampling.median:.0f}s "
            f"(p10 {sampling.p10:.0f}s, p90 {sampling.p90:.0f}s), "
            f"{sampling.under_2min:.0%} under 2 min")
    add("")

    add("PRE-REGISTERED GATE (fixed 2026-08-02, before computing)")
    add("-" * 78)
    add("  PASS requires mean net capture > 0, 95% CI (clustered by game)")
    add(f"  excluding zero, n >= {GATE_MIN_WINDOWS} windows across "
        f">= {GATE_MIN_GAMES} games.")
    add("")

    fills_by_game: dict[str, list[float]] = defaultdict(list)
    dmid_by_game: dict[str, list[float]] = defaultdict(list)
    half_spreads: list[float] = []
    n_fills = 0
    for w in windows:
        half_spreads.append(w.half_spread)
        dmid_by_game[w.quote.game_id].append(w.dmid)
        for pnl in w.fills(fee):
            fills_by_game[w.quote.game_id].append(pnl)
            n_fills += 1

    games = {w.quote.game_id for w in windows}

    if not windows:
        add("VERDICT: NO DATA — the experiment has not run.")
        add("")
        add("  Not a null result. Zero quote-windows means the hypothesis was")
        add("  never tested, which is different from being tested and failing.")
        return "\n".join(out)

    add("What the quotes looked like")
    add("-" * 78)
    mean_half = sum(half_spreads) / len(half_spreads)
    add(f"  mean half-spread available   : {mean_half:+.4f}  "
        f"({mean_half * 100:.2f}c per contract)")
    add(f"  windows with a fill          : {n_fills:,} "
        f"({n_fills / max(1, len(windows)):.1%} of quote-sides observed)")
    add(f"  distinct games               : {len(games)}")
    add("")

    all_dmid = [x for v in dmid_by_game.values() for x in v]
    if all_dmid:
        adverse = sum(1 for x in all_dmid if abs(x) > 0)
        add(f"  mid moved at all             : {adverse:,}/{len(all_dmid):,} windows")
        add(f"  mean |mid move| over horizon : "
            f"{sum(abs(x) for x in all_dmid) / len(all_dmid):.4f}")
        add("")

    if not n_fills:
        add("VERDICT: NO DATA — quotes were built, but none were filled.")
        add("")
        add("  The mid never came to meet a resting quote within the horizon in")
        add("  any observed window. That is a statement about cadence and")
        add("  sample, not about adverse selection.")
        return "\n".join(out)

    clustered = clustered_mean(fills_by_game)
    naive = naive_mean([x for v in fills_by_game.values() for x in v])

    add("Net capture per filled quote (half-spread + adverse mid move)")
    add("-" * 78)
    all_fills = [x for v in fills_by_game.values() for x in v]
    add(f"  mean                         : {sum(all_fills) / len(all_fills):+.4f} "
        f"({sum(all_fills) / len(all_fills) * 100:+.2f}c)")
    if clustered is not None:
        add(f"  95% CI, clustered by game    : "
            f"[{clustered.lo:+.4f}, {clustered.hi:+.4f}]   "
            f"(G={clustered.n_clusters}, df={clustered.n_clusters - 1})")
    else:
        add("  95% CI, clustered by game    : n/a — fewer than 2 games, and a "
            "one-game")
        add("                                 interval would be a within-game "
            "interval.")
    if naive is not None:
        add(f"  95% CI, row-level (WRONG)    : "
            f"[{naive.lo:+.4f}, {naive.hi:+.4f}]   (n={naive.n:,})")
        if clustered is not None and naive.stderr > 0:
            add(f"  clustering widens the SE by  : "
                f"{clustered.stderr / naive.stderr:.1f}x")
    add("")

    add("VERDICT")
    add("-" * 78)
    if len(windows) < GATE_MIN_WINDOWS or len(games) < GATE_MIN_GAMES:
        add(f"  NO DATA — {len(windows):,} windows across {len(games)} games, "
            f"against a")
        add(f"  pre-registered minimum of {GATE_MIN_WINDOWS:,} windows across "
            f"{GATE_MIN_GAMES} games.")
        add("")
        missing = []
        if len(windows) < GATE_MIN_WINDOWS:
            missing.append(f"{GATE_MIN_WINDOWS - len(windows):,} more windows")
        if len(games) < GATE_MIN_GAMES:
            missing.append(f"{GATE_MIN_GAMES - len(games)} more games")
        add(f"  Needs {' and '.join(missing)}. This is NOT a null result: the")
        add("  experiment is built and will accrue. What it needs is games.")
    elif clustered is None:
        add("  NO DATA — too few clusters to form an interval.")
    elif clustered.mean > 0 and clustered.excludes_zero and clustered.lo > 0:
        add(f"  PASS — net capture {clustered.mean:+.4f} per filled quote, "
            f"95% CI")
        add(f"  [{clustered.lo:+.4f}, {clustered.hi:+.4f}] excludes zero at "
            f"n={clustered.n:,} over {len(games)} games.")
        add("")
        add("  Read this with the fill-rule caveat below. A PASS here is the")
        add("  optimistic bound, not the expected result.")
    else:
        add(f"  FAIL — net capture {clustered.mean:+.4f} per filled quote, "
            f"95% CI")
        add(f"  [{clustered.lo:+.4f}, {clustered.hi:+.4f}].")
        add("")
        add("  Adverse selection ate the spread. QUOTE stays unbuilt.")

    add("")
    add("  Fill-rule caveat: fills are inferred from the mid meeting the quote")
    add("  at the horizon, so transient dips that filled you and recovered are")
    add("  invisible. That undercounts exactly the fills that hurt, so a FAIL")
    add("  is trustworthy and a PASS is an upper bound.")
    if sampling is not None and not sampling.is_fast:
        add("")
        add(f"  Cadence caveat: at a {sampling.median:.0f}s median gap this "
            "horizon has no")
        add("  interior — it is a single hop. The 1s recorder shipped")
        add("  2026-08-02; re-run once a slate has accrued under it.")
    return "\n".join(out)


def run(
    session: Session,
    *,
    as_of: dt.datetime | None = None,
    horizon_seconds: float = DEFAULT_HORIZON_SECONDS,
    since: dt.datetime | None = None,
    fee: float = DEFAULT_FEE,
    live_only: bool = True,
) -> str:
    series = load_quotes(session, as_of=as_of, since=since, live_only=live_only)
    quotes_examined = sum(len(v) for v in series.values())
    windows = build_windows(series, horizon_seconds=horizon_seconds)
    return format_report(
        windows,
        horizon_seconds=horizon_seconds,
        fee=fee,
        quotes_examined=quotes_examined,
        sampling=cadence(series),
    )


def main() -> int:
    from core.storage import get_engine, get_sessionmaker

    parser = argparse.ArgumentParser(prog="meridian-adverse-selection")
    parser.add_argument("--horizon", type=float, default=DEFAULT_HORIZON_SECONDS)
    parser.add_argument("--days", type=int, default=None,
                        help="only look this many days back")
    parser.add_argument("--fee", type=float, default=DEFAULT_FEE)
    parser.add_argument("--include-pregame", action="store_true",
                        help="also use snapshots from before tip-off")
    args = parser.parse_args()

    since = dt.datetime.now(UTC) - dt.timedelta(days=args.days) if args.days else None
    Session = get_sessionmaker(get_engine())
    with Session() as session:
        print(
            run(
                session,
                horizon_seconds=args.horizon,
                since=since,
                fee=args.fee,
                live_only=not args.include_pregame,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
