"""The paper wallet — the operator's $1,000 scoreboard over the shadow fills.

    python -m core.quote.wallet --selftest

Registration: docs/math/paper-wallet-scoreboard.md (c7, operator-ordered,
landed by the manager — the seven load-bearing terms this builds to). AN
INSTRUMENT, NEVER EVIDENCE: a month of paper profit justifies the operator
conversation and nothing else (the capital clause stands).

This module is being built in layers. THIS file is the model-INDEPENDENT
foundation — the per-fill primitives, league routing, concession/fees, and
depth-capped sizing — that the accounting fold uses identically whichever way
the sizing/arms question (Call 1 to c7/manager) resolves. The fold + the
append-only control ledger + settlement + the dashboard panel + the rule-16/18
selftest land on top of these, once the accounting model is confirmed.

The two P&L bases (term 2), always side by side, never one alone:
* OPTIMISTIC shadow-fill basis — fill at quote_price, no concession
  (core/quote/report.py net_capture_mark / score_fill).
* MEASURED-CONCESSION basis — the same fill with the calibrated maker-fill
  concession added to the entry cost (C13: 4.70c in-game, 2.10c pregame). The
  gap between the arms IS that concession, and the dashboard never hides it.
"""

from __future__ import annotations

import argparse
import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field
from math import floor

from core.leagues import League, league_of_slug
from core.quote.report import net_capture_mark, score_fill
from core.quote.storage import ASK, BID

try:  # reuse the venue fee coefficients, don't restate them
    from core.backtest.fills import fee_per_contract
except Exception:  # noqa: BLE001 — keep the primitives importable without backtest
    def fee_per_contract(price: float, *, is_maker: bool,
                         assume_rebate: bool = False) -> float:
        return 0.0 if is_maker else 0.06 * price * (1.0 - price)

# --- registration constants (docs/math/paper-wallet-scoreboard.md) ---------- #
SEED_PER_LEAGUE = 500.0          # $500 each at birth; $1,000 total
DAILY_BAR = 3.29                 # the daily P&L bar ($100/month / 30.4)
MONTHLY_BAR = 100.0              # month-to-date bar
#: C13 measured maker-fill concession, added to the entry cost on the
#: concession arm. Same pins as roundtrip_ledger.py / scorecard.py / fills.py.
CONCESSION_IN_GAME = 0.047
CONCESSION_PREGAME = 0.021
#: Depth-at-fill-time staleness bound (D's ffill-hazard rule). Depth samples on
#: a slower loop than price and its own stamp (book_levels.captured_at, NOT the
#: parent snapshot's) is the authority; a level older than this before the fill,
#: or NULL-stamped (Supabase-era rows), is counted OUT — never inherited/ffill'd.
#: A too-tight bound simply raises the clip-to-zero rate, which is printed, so
#: the artifact is measurable rather than hidden.
DEPTH_STALENESS_S = 120.0
#: Bankruptcy halt = OPERATIONAL ruin, not literal ruin (manager ruling,
#: registered; supersedes the epsilon-at-zero version). Under reservation the
#: book can never realize a loss larger than its equity, so concession equity
#: asymptotes to zero rather than crossing it — an epsilon-at-zero halt would
#: essentially never fire. The halt instead trips at 20% of seed remaining
#: ($100 on a $500 ledger): at that point a single game's normal quoting
#: (~tens of contracts at ~40c cost) consumes the whole available balance, so
#: the book can no longer run the registered strategy at any density; and an
#: 80% drawdown on a maker book whose edge is measured in cents is the strategy
#: refuted on this bankroll, not a variance excursion. The two CONTINUOUS
#: meters (concession-equity drawdown + capital-clip rate) are what the operator
#: watches between halts; the clip-rate meter doubles as the "$1,000 binds"
#: answer.
HALT_DRAWDOWN_FRACTION = 0.20


def route_league(market_slug: str | None) -> League | None:
    """The league a fill belongs to, or None = REFUSE (term 1). Never guesses:
    routing is the explicit prefix table (core/leagues.py). An unknown-league
    fill is refused loudly and recorded, never defaulted into a ledger."""
    return league_of_slug(market_slug)


def concession_for(regime: str) -> float:
    """The measured concession for a fill's regime (fixed at quote birth)."""
    if regime == "ingame":
        return CONCESSION_IN_GAME
    if regime == "pregame":
        return CONCESSION_PREGAME
    raise ValueError(f"unknown regime {regime!r} — cannot pick a concession")


def stake_per_contract(*, side: str, quote_price: float) -> float:
    """Dollars staked to hold one contract: a bid stakes the YES price, an ask
    stakes the complementary NO price (V14). Same frame as report.score_fill."""
    if side == BID:
        return quote_price
    if side == ASK:
        return 1.0 - quote_price
    raise ValueError(f"unknown side {side!r}")


def realized_per_contract(*, side: str, quote_price: float, settlement: int,
                          concession: float) -> float:
    """Realized $/contract at settlement on ONE arm. concession=0 is the
    optimistic arm; concession>0 is the measured-concession arm (the entry cost
    carries the concession, the payout does not)."""
    staked, returned = score_fill(side=side, quote_price=quote_price,
                                  settlement=settlement)
    return (returned - staked) - concession


def mark_per_contract(*, side: str, quote_price: float, mid_now: float,
                      concession: float) -> float:
    """UNREALIZED $/contract for an open position, marked at the recorded mid
    (term 4). Never summed into realized by the caller — labelled UNREALIZED."""
    return net_capture_mark(side=side, quote_price=quote_price,
                            mid_at_fill=mid_now) - concession


def maker_fee_per_contract(quote_price: float) -> float:
    """Maker fee per contract — theta_maker=0 (V9/C7), so ~0. The taker hook
    exists in fee_per_contract for any future arm that crosses; the frozen v1
    maker policy never does."""
    return fee_per_contract(quote_price, is_maker=True)


def size_fill(*, available: float, cost_basis: float,
              depth: float) -> tuple[int, str]:
    """Honest sizing (term 3): whole contracts capped by BOTH the free capital
    (available / cost_basis) AND the recorded book depth at the quoted level.
    Returns (size, cap) where cap names the binding constraint for the clipped
    ledger line: 'depth' = the venue bound it, 'capital' = the $1,000 bound it
    (the Sunday scoreboard signal), 'none' = neither clipped, 'zero' = nothing
    takeable. `available` is the reservation-adjusted cash (realized equity minus
    open cost basis); `cost_basis` is per-contract entry cost (stake, plus the
    concession on the concession arm)."""
    depth_cap = int(floor(max(depth, 0.0)))
    affordable = (int(floor(max(available, 0.0) / cost_basis))
                  if cost_basis > 0 else 0)
    size = max(min(depth_cap, affordable), 0)
    if size == 0:
        return 0, "zero"
    if depth_cap < affordable:
        return size, "depth"
    if affordable < depth_cap:
        return size, "capital"
    return size, "none"


# --------------------------------------------------------------------------- #
#  The fold — the accounting core (model (a), pessimistic-sized: manager 51a4103,
#  research-ratified "hope may value the book, it may never buy contracts").
# --------------------------------------------------------------------------- #

@dataclass
class Fill:
    """One shadow fill as the wallet consumes it. `depth` is the recorded book
    depth at the quoted level at fill time (resolved from book_levels by the DB
    gather; set directly in tests). settlement/settled_at are None until the
    market resolves."""
    market_slug: str
    regime: str                      # 'pregame' | 'ingame'
    side: str                        # 'bid' | 'ask'
    quote_price: float
    mid_at_fill: float
    filled_at: dt.datetime
    depth: float
    settlement: int | None = None
    settled_at: dt.datetime | None = None


@dataclass
class LedgerLine:
    """An append-only control/scoreboard event (seed / halt / reset). Persisted
    in paper_wallet_control; the halt line is emitted by the fold."""
    league: str
    kind: str                        # 'seed' | 'halt' | 'reset' | 'resplit'
    at: dt.datetime
    amount: float | None = None
    note: str = ""


@dataclass
class LeagueBook:
    slug: str
    seed: float
    optimistic: float                # realized balance, optimistic arm (seed + settled P&L)
    concession: float                # realized balance, concession arm (governs sizing)
    toll: float                      # cumulative $ divergence = optimistic - concession
    reserved_conc: float             # open cost basis still tied up (concession arm)
    available_to_size: float         # concession realized equity - reserved_conc
    halted: bool
    halt_line: LedgerLine | None
    n_fills: int                     # sized > 0
    n_clipped_depth: int             # book depth bound the size (venue was the cap)
    n_clipped_reservation: int       # capital bound the size ($1,000 was the cap)
    n_zero: int                      # sized 0 (no depth / no free capital)
    n_skipped_halt: int              # entries refused because the book had halted
    unrealized_opt: float
    unrealized_conc: float
    n_open_marked: int
    n_open_unmarkable: int           # open, no current mid (coverage gap, counted)
    #: Realized P&L per settlement DATE (ISO) per arm — term 5's daily line
    #: (P&L vs $3.29/day). {date: delta}; today's + month-to-date derive from it.
    daily_opt: dict = field(default_factory=dict)
    daily_conc: dict = field(default_factory=dict)
    #: Concurrency (D's 51c252e, the binding constraint): the peak and
    #: time-weighted count of simultaneously-OPEN markets and contracts in this
    #: ledger. Peak contracts is the arithmetic worst-case dollar exposure at
    #: unit size (per-contract loss <= $1 on a binary); it is what sizes the
    #: bankroll need, and nobody had it until now. The reservation rule already
    #: CLIPS aggregate exposure to the ledger's equity — so the capital-clip rate
    #: reads as "how much bankroll the strategy actually needs", and any explicit
    #: cap is picked by arithmetic from THIS worst case, never from a transferred
    #: WNBA number.
    peak_open_markets: int = 0
    peak_open_contracts: int = 0
    tw_open_markets: float = 0.0      # time-weighted mean over the ledger's span
    tw_open_contracts: float = 0.0


@dataclass
class WalletResult:
    books: dict[str, LeagueBook]
    refused: list[Fill] = field(default_factory=list)   # unknown-league (term 1)


def _concurrency(intervals: list[tuple], now: dt.datetime):
    """Peak and time-weighted concurrent open MARKETS and CONTRACTS from a list
    of (open_at, close_at, size, market_slug) — a sweep line over the open
    intervals. close_at is the settlement instant, or `now` for a still-open
    position. Contracts sum size; markets count distinct slugs currently open
    (ref-counted, so overlapping positions in one market count the market once).
    Time-weighted = the integral over the ledger's active span / that span."""
    if not intervals:
        return 0, 0, 0.0, 0.0
    events: list[tuple] = []
    for (a, b, sz, mkt) in intervals:
        b = b or now
        if b < a:
            b = a
        events.append((a, +1, sz, mkt))
        events.append((b, -1, sz, mkt))
    events.sort(key=lambda e: (e[0], e[1]))          # close (-1) before open (+1) at ties
    cur_contracts = 0
    mkt_refs: dict[str, int] = {}
    peak_c = peak_m = 0
    area_c = area_m = 0.0
    prev_t = events[0][0]
    span = (events[-1][0] - events[0][0]).total_seconds()
    for (t, delta, sz, mkt) in events:
        dt_s = (t - prev_t).total_seconds()
        if dt_s > 0:
            area_c += cur_contracts * dt_s
            area_m += len([m for m, c in mkt_refs.items() if c > 0]) * dt_s
        prev_t = t
        if delta > 0:
            cur_contracts += sz
            mkt_refs[mkt] = mkt_refs.get(mkt, 0) + 1
        else:
            cur_contracts -= sz
            mkt_refs[mkt] = mkt_refs.get(mkt, 0) - 1
        open_m = len([m for m, c in mkt_refs.items() if c > 0])
        peak_c = max(peak_c, cur_contracts)
        peak_m = max(peak_m, open_m)
    tw_c = (area_c / span) if span > 0 else float(peak_c)
    tw_m = (area_m / span) if span > 0 else float(peak_m)
    return peak_m, peak_c, tw_m, tw_c


def _fold_league(slug: str, fills: list[Fill], seed: float,
                 mids: dict[str, float], now: dt.datetime) -> LeagueBook:
    """Cash-flow fold with OPEN-EXPOSURE RESERVATION (manager ruling, registered
    tonight; the real venue's rule = min(cash, buyingPower), cash consumed at
    fill). available-to-size = concession realized equity − Σ(open cost basis);
    cost is reserved at entry and freed at settlement. So the paper book can
    never carry exposure a real $1,000 could not afford — the structural
    optimism leak, closed. Both arms reserve their own cost basis, but SIZING is
    governed by the concession (pessimistic) arm's available.

    event-ordered so an entry sees every settlement that resolved before it."""
    events: list[tuple] = []
    for i, f in enumerate(fills):
        events.append((f.filled_at, 1, "entry", i, f))
        if f.settlement is not None and f.settled_at is not None:
            events.append((f.settled_at, 0, "settle", i, f))
    events.sort(key=lambda e: (e[0], e[1]))          # settle (0) before entry (1) at ties

    eq_opt = eq_conc = float(seed)                    # realized equity (seed + settled P&L)
    res_opt = res_conc = 0.0                          # reserved open cost basis
    toll = 0.0
    daily_opt: dict[str, float] = {}
    daily_conc: dict[str, float] = {}
    halted = False
    halt_line: LedgerLine | None = None
    size: dict[int, int] = {}
    n_fills = n_clip_depth = n_clip_res = n_zero = n_skipped = 0
    open_idx: list[int] = []

    for (t, _k, kind, i, f) in events:
        if kind == "entry":
            if halted:
                n_skipped += 1
                continue
            stake = stake_per_contract(side=f.side, quote_price=f.quote_price)
            cc = concession_for(f.regime)
            cost_conc = stake + cc                    # concession-arm cost basis
            available = eq_conc - res_conc            # reservation-adjusted cash
            sz, cap = size_fill(available=available, cost_basis=cost_conc,
                                depth=f.depth)
            size[i] = sz
            if sz == 0:
                n_zero += 1
            else:
                n_fills += 1
                if cap == "depth":
                    n_clip_depth += 1                 # the venue was the constraint
                elif cap == "capital":
                    n_clip_res += 1                   # $1,000 was the constraint
                res_conc += sz * cost_conc
                res_opt += sz * stake
                if f.settlement is None:
                    open_idx.append(i)
        else:  # settle: free the reservation, book realized P&L on both arms
            sz = size.get(i, 0)
            if sz == 0:
                continue
            stake = stake_per_contract(side=f.side, quote_price=f.quote_price)
            cc = concession_for(f.regime)
            res_conc -= sz * (stake + cc)
            res_opt -= sz * stake
            r_opt = sz * realized_per_contract(
                side=f.side, quote_price=f.quote_price,
                settlement=f.settlement, concession=0.0)
            r_conc = sz * realized_per_contract(
                side=f.side, quote_price=f.quote_price,
                settlement=f.settlement, concession=cc)
            eq_opt += r_opt
            eq_conc += r_conc
            toll += (r_opt - r_conc)
            d = f.settled_at.date().isoformat()       # term-5 daily line
            daily_opt[d] = daily_opt.get(d, 0.0) + r_opt
            daily_conc[d] = daily_conc.get(d, 0.0) + r_conc
            # BANKRUPTCY HALT (51a4103): the concession bankroll gone (realized
            # equity <= 0) stops trading even while optimism shows profit — the
            # book that survives only on the optimistic valuation, made visible.
            if eq_conc < HALT_DRAWDOWN_FRACTION * seed and not halted:
                halted = True
                halt_line = LedgerLine(
                    league=slug, kind="halt", at=t,
                    note=(f"concession-arm equity ${eq_conc:.2f} fell below "
                          f"{HALT_DRAWDOWN_FRACTION:.0%} of ${seed:.2f} seed "
                          f"(operational ruin) — wallet HALTS trading (optimistic "
                          f"line ${eq_opt:.2f}: a book surviving only on optimism)"))

    un_opt = un_conc = 0.0
    n_marked = n_unmarkable = 0
    for i in open_idx:
        f = fills[i]
        mid = mids.get(f.market_slug)
        if mid is None:
            n_unmarkable += 1
            continue
        cc = concession_for(f.regime)
        sz = size[i]
        un_opt += sz * mark_per_contract(side=f.side, quote_price=f.quote_price,
                                         mid_now=mid, concession=0.0)
        un_conc += sz * mark_per_contract(side=f.side, quote_price=f.quote_price,
                                          mid_now=mid, concession=cc)
        n_marked += 1

    # concurrency (D's binding constraint): open intervals of every sized
    # position — settled ones close at settled_at, open ones at `now`.
    intervals = [
        (fills[i].filled_at, fills[i].settled_at, size[i], fills[i].market_slug)
        for i in range(len(fills)) if size.get(i, 0) > 0
    ]
    peak_m, peak_c, tw_m, tw_c = _concurrency(intervals, now)

    return LeagueBook(
        slug=slug, seed=float(seed), optimistic=eq_opt, concession=eq_conc,
        toll=toll, reserved_conc=res_conc, available_to_size=eq_conc - res_conc,
        halted=halted, halt_line=halt_line, n_fills=n_fills,
        n_clipped_depth=n_clip_depth, n_clipped_reservation=n_clip_res,
        n_zero=n_zero, n_skipped_halt=n_skipped, unrealized_opt=un_opt,
        unrealized_conc=un_conc, n_open_marked=n_marked,
        n_open_unmarkable=n_unmarkable,
        daily_opt=daily_opt, daily_conc=daily_conc,
        peak_open_markets=peak_m, peak_open_contracts=peak_c,
        tw_open_markets=tw_m, tw_open_contracts=tw_c)


def fold(fills: list[Fill], *, seeds: dict[str, float] | None = None,
         mids: dict[str, float] | None = None,
         now: dt.datetime | None = None) -> WalletResult:
    """Fold shadow fills into the paper wallet: route by league (unknown =
    REFUSE, recorded), size each fill pessimistically (concession-arm balance),
    settle realized P&L on both arms, mark open positions UNREALIZED, and measure
    open-exposure concurrency. Pure over its inputs — the DB gather builds the
    Fill list (depth from book_levels, mids from the latest snapshot), the seeds
    from the control ledger, and `now` (open positions close there for the
    concurrency sweep; defaults to the latest timestamp in the fills)."""
    seeds = seeds or {}
    mids = mids or {}
    if now is None:
        stamps = [f.settled_at or f.filled_at for f in fills]
        now = max(stamps) if stamps else dt.datetime.now(dt.timezone.utc)
    refused: list[Fill] = []
    by_league: dict[str, list[Fill]] = defaultdict(list)
    for f in fills:
        lg = route_league(f.market_slug)
        if lg is None:
            refused.append(f)
            continue
        by_league[lg.slug].append(f)
    books = {
        slug: _fold_league(slug, lg_fills,
                           seeds.get(slug, SEED_PER_LEAGUE), mids, now)
        for slug, lg_fills in by_league.items()
    }
    return WalletResult(books=books, refused=refused)


# --------------------------------------------------------------------------- #
#  DB gather — build the Fill list from the live tables and fold (the --db path)
# --------------------------------------------------------------------------- #

def _effective_seeds(session) -> dict[str, float]:
    """Per-league seed = the amount of the most recent control line (birth seed
    or operator reset/resplit). Append-only, so 'most recent' is the effective
    bankroll basis; leagues with no line fall back to SEED_PER_LEAGUE."""
    from sqlalchemy import text
    rows = session.execute(text("""
        SELECT DISTINCT ON (league) league, amount
        FROM paper_wallet_control
        WHERE kind IN ('seed','reset','resplit')
        ORDER BY league, effective_at DESC
    """)).all()
    return {r.league: float(r.amount) for r in rows}


def _load_fills_with_depth(
    session, *, staleness_s: float = DEPTH_STALENESS_S,
) -> tuple[list[Fill], int, int]:
    """shadow_quote_fills + the recorded book depth at each fill's quoted level.

    Depth-join (D's ruling, registered 6d4ce04): book_levels is ONE YES-frame
    book, so a BID quote joins side='bid' and an ASK joins side='offer', both at
    price == quote_price (4dp exact; conservative-zero otherwise). Keyed on
    book_levels.captured_at — depth samples on a slower loop and its own stamp is
    the authority — with the staleness bound; NULL-stamped rows are counted OUT,
    never inheriting the parent snapshot's stamp. Returns (fills, n_depth_absent,
    n_total); depth absent (exact level not recorded fresh) -> depth 0 -> the
    fill clips to zero, and that RATE is printed so the tick-neighbor artifact is
    measurable (never a silent merge)."""
    import bisect
    from collections import defaultdict

    from sqlalchemy import text

    rows = session.execute(text("""
        SELECT market_slug, game_id, regime, side, quote_price, mid_at_fill,
               filled_at, settlement, settled_at
        FROM shadow_quote_fills ORDER BY filled_at
    """)).all()
    if not rows:
        return [], 0, 0

    markets = sorted({r.market_slug for r in rows})
    tmin = min(r.filled_at for r in rows) - dt.timedelta(seconds=staleness_s)
    tmax = max(r.filled_at for r in rows)
    lvls = session.execute(text("""
        SELECT ms.market_slug AS market_slug, bl.side AS side,
               bl.price AS price, bl.quantity AS quantity,
               bl.captured_at AS captured_at
        FROM book_levels bl
        JOIN market_snapshots ms ON ms.id = bl.snapshot_id
        WHERE ms.market_slug = ANY(:markets)
          AND bl.side IN ('bid','offer')
          AND bl.captured_at IS NOT NULL          -- never inherit the parent stamp
          AND bl.captured_at >= :tmin AND bl.captured_at <= :tmax
    """), {"markets": markets, "tmin": tmin, "tmax": tmax}).all()

    series: dict[tuple, list] = defaultdict(list)
    for lv in lvls:
        series[(lv.market_slug, lv.side, round(float(lv.price), 4))].append(
            (lv.captured_at, float(lv.quantity)))
    index: dict[tuple, tuple] = {}
    for k, s in series.items():
        s.sort()
        index[k] = ([t for t, _ in s], [q for _, q in s])

    fills: list[Fill] = []
    n_absent = 0
    for r in rows:
        book_side = "bid" if r.side == "bid" else "offer"
        key = (r.market_slug, book_side, round(float(r.quote_price), 4))
        depth = 0.0
        hit = index.get(key)
        if hit is not None:
            times, qtys = hit
            pos = bisect.bisect_right(times, r.filled_at) - 1  # newest <= fill
            if pos >= 0 and times[pos] >= r.filled_at - dt.timedelta(
                    seconds=staleness_s):
                depth = qtys[pos]
        if depth <= 0:
            n_absent += 1
        fills.append(Fill(
            market_slug=r.market_slug, regime=r.regime, side=r.side,
            quote_price=float(r.quote_price), mid_at_fill=float(r.mid_at_fill),
            filled_at=r.filled_at, depth=depth,
            settlement=(None if r.settlement is None else int(r.settlement)),
            settled_at=r.settled_at))
    return fills, n_absent, len(rows)


def _load_mids(session, markets) -> dict[str, float]:
    """Latest recorded mid per market — for marking OPEN positions (term 4)."""
    from sqlalchemy import text
    markets = list(markets)
    if not markets:
        return {}
    rows = session.execute(text("""
        SELECT DISTINCT ON (market_slug) market_slug, best_bid, best_ask
        FROM market_snapshots
        WHERE market_slug = ANY(:m)
          AND best_bid IS NOT NULL AND best_ask IS NOT NULL
        ORDER BY market_slug, captured_at DESC
    """), {"m": markets}).all()
    return {r.market_slug: (float(r.best_bid) + float(r.best_ask)) / 2.0
            for r in rows}


def gather(session, *, staleness_s: float = DEPTH_STALENESS_S):
    """Fold the live tables into the wallet. Returns (WalletResult, meta) where
    meta carries the clip-to-zero (depth-absent) count/rate D requires printed."""
    seeds = _effective_seeds(session)
    fills, n_absent, n_total = _load_fills_with_depth(
        session, staleness_s=staleness_s)
    open_markets = {f.market_slug for f in fills if f.settlement is None}
    mids = _load_mids(session, open_markets)
    result = fold(fills, seeds=seeds, mids=mids,
                  now=dt.datetime.now(dt.timezone.utc))

    # Depth-absent fills as their OWN LINE (D's remedy): count, share, and the
    # capture they WOULD have carried at unit size — the suppression cost.
    # exact-match clip-to-zero is capacity-conservative but P&L-SIGN-DEPENDENT:
    # an absent fill contributes nothing, so on a NEGATIVE-capture book it
    # FLATTERS the loss. This line says how much of the outcome is "we didn't
    # trade" vs "we traded well". 10%-of-ingame is the pre-data trigger for the
    # within-one-min_tick revisit (its own labelled column, never replacing
    # exact-match).
    absent = [f for f in fills if f.depth <= 0]
    ingame = [f for f in fills if f.regime == "ingame"]
    ingame_absent = [f for f in absent if f.regime == "ingame"]

    def _wouldbe(f: Fill, conc: float) -> float:
        return net_capture_mark(side=f.side, quote_price=f.quote_price,
                                mid_at_fill=f.mid_at_fill) - conc

    wb_opt = [_wouldbe(f, 0.0) for f in absent]
    wb_conc = [_wouldbe(f, concession_for(f.regime)) for f in absent]
    ing_rate = (len(ingame_absent) / len(ingame)) if ingame else 0.0
    meta = {
        "n_fills": n_total,
        "depth_absent": n_absent,
        "depth_absent_rate": (n_absent / n_total) if n_total else 0.0,
        "n_ingame": len(ingame),
        "ingame_absent": len(ingame_absent),
        "ingame_absent_rate": ing_rate,
        "absent_wouldbe_opt_sum": sum(wb_opt),
        "absent_wouldbe_conc_sum": sum(wb_conc),
        "absent_wouldbe_opt_mean_c": (sum(wb_opt) / len(wb_opt) * 100) if wb_opt else 0.0,
        "absent_wouldbe_conc_mean_c": (sum(wb_conc) / len(wb_conc) * 100) if wb_conc else 0.0,
        "trigger_10pct_ingame": ing_rate > 0.10,
        "staleness_s": staleness_s,
        "seeds": seeds,
    }
    return result, meta


def run_db() -> int:
    from core.storage.base import get_engine
    from core.storage import get_sessionmaker
    try:
        with get_sessionmaker(get_engine())() as s:
            result, meta = gather(s)
    except Exception as exc:  # noqa: BLE001 — DB may be unreachable from here
        msg = str(exc).lower()
        if ("does not exist" in msg or "could not connect" in msg
                or "connection refused" in msg):
            print("wallet tables not present / DB unreachable from here — the "
                  "wallet runs where shadow_quote_fills + book_levels live "
                  "(main checkout / prod).")
            return 0
        raise
    print(f"paper wallet — {meta['n_fills']:,} fills")
    # depth-absent as its own line (D): count, share, and would-be capture.
    print(f"depth-absent (clip-to-zero): {meta['depth_absent']:,} "
          f"({meta['depth_absent_rate']:.1%} of all, "
          f"{meta['ingame_absent_rate']:.1%} of ingame) | would-be capture at "
          f"unit size: opt ${meta['absent_wouldbe_opt_sum']:+.2f} "
          f"({meta['absent_wouldbe_opt_mean_c']:+.2f}c/fill), conc "
          f"${meta['absent_wouldbe_conc_sum']:+.2f} "
          f"({meta['absent_wouldbe_conc_mean_c']:+.2f}c/fill) — the suppression "
          f"cost we did not trade")
    print("  NOTE: exact-4dp match is capacity-conservative but P&L "
          "sign-dependent — an absent fill contributes nothing, so on a "
          "negative-capture book it FLATTERS the loss (the would-be line above "
          "is how much).")
    if meta["trigger_10pct_ingame"]:
        print("  *** TRIGGER: ingame depth-absent > 10% — build the "
              "within-one-min_tick snap as its own labelled column (never "
              "replacing exact-match). ***")
    if result.refused:
        print(f"REFUSED (unknown league, not folded): {len(result.refused)} fills")
    for slug, b in sorted(result.books.items()):
        drawdown = 1.0 - (b.concession / b.seed) if b.seed else 0.0
        clip_rate = (b.n_clipped_reservation / b.n_fills) if b.n_fills else 0.0
        print(f"\n[{slug}] seed ${b.seed:.2f}   fills {b.n_fills} "
              f"(depth-clip {b.n_clipped_depth}, capital-clip "
              f"{b.n_clipped_reservation}, zero {b.n_zero})"
              + ("   *** HALTED ***" if b.halted else ""))
        print(f"  optimistic  ${b.optimistic:10.2f}   P&L ${b.optimistic - b.seed:+.2f}"
              f"   (MTD bar ${MONTHLY_BAR:.0f})")
        print(f"  concession  ${b.concession:10.2f}   P&L ${b.concession - b.seed:+.2f}"
              f"   drawdown {drawdown:.1%}   capital-clip rate {clip_rate:.1%}")
        print(f"  toll (cumulative concession cost) ${b.toll:.2f}   "
              f"reserved ${max(b.reserved_conc, 0.0):.2f}   "
              f"available ${b.available_to_size:.2f}")
        print(f"  UNREALIZED (open, not in realized): optimistic "
              f"${b.unrealized_opt:+.2f} / concession ${b.unrealized_conc:+.2f} "
              f"({b.n_open_marked} marked, {b.n_open_unmarkable} no-mid)")
        print(f"  CONCURRENCY (sizes the bankroll need): peak "
              f"{b.peak_open_contracts} open contracts across "
              f"{b.peak_open_markets} markets (~${b.peak_open_contracts} "
              f"worst-case at unit size vs ${b.seed:.0f} seed); time-weighted "
              f"{b.tw_open_contracts:.1f} contracts / {b.tw_open_markets:.1f} "
              f"markets")
        if b.halt_line is not None:
            print(f"  HALT: {b.halt_line.note}")
    return 0


# --------------------------------------------------------------------------- #
#  --selftest: the primitives, pure (the fold's rule-16 known-answer on the Aug
#  pin lands with the DB gather). These must hold before any dollar is folded.
# --------------------------------------------------------------------------- #

def _selftest_primitives() -> int:
    ok = True

    def check(label, got, want, tol=1e-9):
        nonlocal ok
        c = abs(got - want) <= tol if isinstance(want, float) else got == want
        print(f"{label:52} {'OK' if c else f'FAIL got={got!r} want={want!r}'}")
        ok &= c

    # realized, both arms, both sides (YES-frame)
    check("bid@0.40 settle=1 optimistic",
          realized_per_contract(side=BID, quote_price=0.40, settlement=1,
                                concession=0.0), 0.60)
    check("bid@0.40 settle=1 concession(ingame)",
          realized_per_contract(side=BID, quote_price=0.40, settlement=1,
                                concession=CONCESSION_IN_GAME), 0.60 - 0.047)
    check("bid@0.40 settle=0 optimistic",
          realized_per_contract(side=BID, quote_price=0.40, settlement=0,
                                concession=0.0), -0.40)
    check("ask@0.60 settle=0 optimistic (NO side wins)",
          realized_per_contract(side=ASK, quote_price=0.60, settlement=0,
                                concession=0.0), 0.60)

    # the arm gap on any single leg IS the concession (term 2's lesson)
    gap = (realized_per_contract(side=BID, quote_price=0.40, settlement=1,
                                 concession=0.0)
           - realized_per_contract(side=BID, quote_price=0.40, settlement=1,
                                   concession=CONCESSION_IN_GAME))
    check("arm gap == concession (ingame)", gap, CONCESSION_IN_GAME)

    # unrealized mark
    check("mark bid@0.40 mid=0.43 optimistic",
          mark_per_contract(side=BID, quote_price=0.40, mid_now=0.43,
                            concession=0.0), 0.03)
    check("mark ask@0.60 mid=0.55 optimistic",
          mark_per_contract(side=ASK, quote_price=0.60, mid_now=0.55,
                            concession=0.0), 0.05)

    # sizing: depth binds -> cap 'depth'; capital binds -> cap 'capital'
    check("size: avail 100 / cost 0.40, depth 100 -> 100",
          size_fill(available=100.0, cost_basis=0.40, depth=100)[0], 100)
    check("size: depth 100 < affordable 250 -> cap 'depth'",
          size_fill(available=100.0, cost_basis=0.40, depth=100)[1], "depth")
    check("size: depth 1000 >= affordable 250 -> cap 'capital'",
          size_fill(available=100.0, cost_basis=0.40, depth=1000)[1], "capital")
    check("size: affordable 100/0.40=250",
          size_fill(available=100.0, cost_basis=0.40, depth=1000)[0], 250)
    check("size: no capital -> (0,'zero')",
          size_fill(available=0.0, cost_basis=0.40, depth=1000), (0, "zero"))

    # maker fee is ~0 (theta_maker=0)
    check("maker fee @0.50 == 0", maker_fee_per_contract(0.50), 0.0)

    # routing: real prod NFL slug format (aec-/asc-/tsc- families, -nfl- infix,
    # verified at the artifact 2026-09-02) routes; a Kalshi ticker can never
    # reach shadow_quote_fills but is refused if seen; unknown refuses.
    check("route aec-nfl-... (prod format)",
          route_league("aec-nfl-ari-lac-2026-09-13").slug, "nfl")
    check("route tsc-nfl-... market slug",
          route_league("tsc-nfl-buf-nyj-2026-09-11-3pt5").slug, "nfl")
    check("route wnba market slug",
          route_league("tsc-wnba-ny-chi-2026-08-18-191pt5").slug, "wnba")
    check("route kxnfl ticker -> REFUSE (never reaches fills, net anyway)",
          route_league("kxnflgame-25sep11bufnyj") is None, True)
    check("route unknown -> REFUSE", route_league("mlb-lad-sf") is None, True)

    # concession_for
    check("concession ingame", concession_for("ingame"), CONCESSION_IN_GAME)
    check("concession pregame", concession_for("pregame"), CONCESSION_PREGAME)

    print("\nPRIMITIVES SELFTEST:",
          "PASS — both arms, the arm-gap==concession identity, honest "
          "depth/balance clipping, maker fee 0, and loud league routing all "
          "hold. (The fold's rule-16/18 selftest lands with the fold.)"
          if ok else "FAIL")
    return 0 if ok else 1


def _selftest_fold() -> int:
    ok = True

    def chk(label, cond):
        nonlocal ok
        print(f"{label:56} {'OK' if cond else 'FAIL'}")
        ok &= cond

    t0 = dt.datetime(2026, 8, 18, 19, 0, tzinfo=dt.timezone.utc)

    def T(sec):
        return t0 + dt.timedelta(seconds=sec)

    # 1. clean winning bid, depth-clipped: hand-computed both arms + toll
    f1 = Fill("tsc-wnba-ny-chi-1", "ingame", "bid", 0.40, 0.43, T(0),
              depth=10, settlement=1, settled_at=T(3600))
    b = fold([f1], seeds={"wnba": 500.0}).books["wnba"]
    chk("clean: optimistic 506.00", abs(b.optimistic - 506.0) < 1e-9)
    chk("clean: concession 505.53", abs(b.concession - 505.53) < 1e-9)
    chk("clean: toll 0.47 == opt-conc",
        abs(b.toll - 0.47) < 1e-9 and abs(b.toll - (b.optimistic - b.concession)) < 1e-9)
    chk("clean: depth 10 bound the size (cap 'depth')",
        b.n_clipped_depth == 1 and b.n_clipped_reservation == 0 and b.n_fills == 1)

    # 2. rule-18 fabricated-fill plant: a known extra fill moves the ledger by
    #    EXACTLY the computed amount (5 contracts x $0.70 = $3.50 optimistic).
    f2 = Fill("tsc-wnba-ny-chi-2", "ingame", "bid", 0.30, 0.35, T(1),
              depth=5, settlement=1, settled_at=T(3600))
    b2 = fold([f1, f2], seeds={"wnba": 500.0}).books["wnba"]
    chk("plant fabricated: ledger moves by EXACTLY 3.50",
        abs((b2.optimistic - b.optimistic) - 3.50) < 1e-9)

    # 3. rule-18 depth-clip plant: book depth binds -> size = depth, cap 'depth'
    f3 = Fill("tsc-wnba-x-3", "ingame", "bid", 0.40, 0.43, T(0),
              depth=3, settlement=1, settled_at=T(3600))
    b3 = fold([f3], seeds={"wnba": 500.0}).books["wnba"]
    chk("plant depth-clip: size=depth=3 -> opt 501.80, cap 'depth'",
        abs(b3.optimistic - 501.8) < 1e-9 and b3.n_clipped_depth == 1)

    # 3b. RESERVATION-clip plant (the Sunday signal): capital binds below depth.
    #     seed 1.0, cost 0.547 -> affordable 1 << depth 100 -> cap 'capital'.
    frc = Fill("tsc-wnba-rc-1", "ingame", "bid", 0.50, 0.50, T(0),
               depth=100, settlement=None, settled_at=None)
    brc = fold([frc], seeds={"wnba": 1.0}).books["wnba"]
    chk("plant reservation-clip: capital bound size to 1 (cap 'capital')",
        brc.n_clipped_reservation == 1 and brc.n_clipped_depth == 0
        and brc.reserved_conc > 0)

    # 4. bankruptcy plant (registered): a loss drops concession equity below 20%
    #    of seed (operational ruin) -> HALT line prints, next entry does not fold.
    #    seed 10, one bid@0.50 loss sized to depth 100: 18 contracts x $0.547 cost
    #    -> equity 10 - 9.846 = $0.154 < $2.00 (20% of $10) -> halt.
    fa = Fill("tsc-wnba-a-1", "ingame", "bid", 0.50, 0.50, T(0),
              depth=100, settlement=0, settled_at=T(3600))
    fb = Fill("tsc-wnba-a-2", "ingame", "bid", 0.50, 0.50, T(7200),
              depth=100, settlement=1, settled_at=T(10800))
    bk = fold([fa, fb], seeds={"wnba": 10.0}).books["wnba"]
    chk("plant bankruptcy: halted with a visible line",
        bk.halted and bk.halt_line is not None and bk.halt_line.kind == "halt")
    chk("plant bankruptcy: concession equity < 20% of seed",
        bk.concession < 0.20 * 10.0)
    chk("plant bankruptcy: post-halt entry did NOT fold",
        bk.n_skipped_halt == 1)

    # 5. refusal (term 1): unknown-league fill refused and recorded, never folded
    fu = Fill("mlb-lad-sf-1", "ingame", "bid", 0.40, 0.43, T(0),
              depth=10, settlement=1, settled_at=T(3600))
    ru = fold([fu])
    chk("refusal: unknown league refused, no book created",
        len(ru.refused) == 1 and not ru.books)

    # 6. unrealized (term 4): open position marked at mid, NOT in realized balance
    fo = Fill("tsc-wnba-o-1", "ingame", "bid", 0.40, 0.43, T(0),
              depth=10, settlement=None, settled_at=None)
    bo = fold([fo], seeds={"wnba": 500.0},
              mids={"tsc-wnba-o-1": 0.46}).books["wnba"]
    chk("unrealized: realized balance unchanged at seed",
        abs(bo.optimistic - 500.0) < 1e-9 and abs(bo.concession - 500.0) < 1e-9)
    chk("unrealized: marked 10*(0.46-0.40)=0.60, labelled separate",
        abs(bo.unrealized_opt - 0.60) < 1e-9 and bo.n_open_marked == 1)

    # CONCURRENCY (D's binding constraint): 3 distinct markets, overlapping open
    # intervals [0,30] [10,40] [20,50] -> all three open over [20,30] -> peak =
    # 5+3+2=10 contracts across 3 markets. Depth caps each size to its depth.
    fc = [
        Fill("tsc-wnba-c-1", "ingame", "bid", 0.40, 0.43, T(0),
             depth=5, settlement=1, settled_at=T(30)),
        Fill("tsc-wnba-c-2", "ingame", "bid", 0.40, 0.43, T(10),
             depth=3, settlement=1, settled_at=T(40)),
        Fill("tsc-wnba-c-3", "ingame", "bid", 0.40, 0.43, T(20),
             depth=2, settlement=1, settled_at=T(50)),
    ]
    bc = fold(fc, seeds={"wnba": 500.0}).books["wnba"]
    chk("concurrency: peak 10 contracts across 3 markets (overlap [20,30])",
        bc.peak_open_contracts == 10 and bc.peak_open_markets == 3)
    chk("concurrency: time-weighted within (0, peak]",
        0 < bc.tw_open_contracts <= 10 and 0 < bc.tw_open_markets <= 3)

    print("\nFOLD SELFTEST:", "PASS — both arms hand-reconciled, the toll meter "
          "is exactly opt-conc, a fabricated fill moves the ledger by the "
          "computed amount, an over-depth fill clips-and-logs, a loss halts the "
          "bankrupt book with a visible line, an unknown league is refused, and "
          "open positions mark UNREALIZED without touching realized. Can fail."
          if ok else "FAIL")
    return 0 if ok else 1


# The immutable Aug fills pin (manager-confirmed) and its ledgered known-answer.
# The pin never carried a recorded checksum, so this selftest is its checksum of
# record (manager). Repo-relative; a gitignored data artifact, so the check
# skips where it is absent (worktrees) and runs where it is present (main
# checkout / prod).
_PIN_REL = "backups/exports/quote_fills_v1_20260902T161223Z.csv"
_PIN_MD5 = "2083a93153d51738d7d472345548a08c"
_LEDGER_INGAME_FILLS = 17032
_LEDGER_CAPTURE_CENTS = -1.60            # optimistic net-capture mean, ledgered
_LEDGER_CI_CENTS = (-1.69, -1.50)        # the ledgered clustered CI (containment)


def _selftest_rule16() -> int:
    """rule-16 KNOWN-ANSWER: reproduce the capture ledger's totals on both arms
    from the immutable Aug pin.

    Folded at the LEDGER'S basis — size = 1 contract, NO depth-cap, NO
    reservation — because the pin carries no depth columns and the ledger's
    -1.60c was computed per-contract. Depth-capping and reservation are FORWARD
    behaviors; the rule-18 plants in _selftest_fold already prove they fire.
    This check proves the ARITHMETIC CORE (both-arm capture, the YES-frame, the
    ingame filter) matches the ledger. md5-gated: refuses on a changed pin.
    """
    import csv
    import hashlib
    from pathlib import Path

    pin = Path(__file__).resolve().parents[2] / _PIN_REL
    if not pin.exists():
        print(f"rule-16 (Aug pin): SKIPPED — pin absent here ({_PIN_REL}); runs "
              "where backups/exports/ is populated (main checkout / prod).")
        return 0
    md5 = hashlib.md5(pin.read_bytes()).hexdigest()
    if md5 != _PIN_MD5:
        print(f"rule-16 (Aug pin): REFUSED — md5 {md5} != pinned {_PIN_MD5}; the "
              "pin changed and this selftest is its checksum of record.")
        return 1

    with open(pin) as f:
        ing = [r for r in csv.DictReader(f) if r["regime"] == "ingame"]
    n = len(ing)

    def cap(r, concession):                # size=1, ledger basis (mark at fill)
        return mark_per_contract(side=r["side"],
                                 quote_price=float(r["quote_price"]),
                                 mid_now=float(r["mid_at_fill"]),
                                 concession=concession)

    mean_opt = sum(cap(r, 0.0) for r in ing) / n
    mean_conc = sum(cap(r, concession_for(r["regime"])) for r in ing) / n
    lo, hi = _LEDGER_CI_CENTS
    c1 = n == _LEDGER_INGAME_FILLS
    c2 = (round(mean_opt * 100, 2) == _LEDGER_CAPTURE_CENTS
          and lo <= mean_opt * 100 <= hi)
    c3 = abs((mean_opt - mean_conc) - CONCESSION_IN_GAME) < 1e-9

    print(f"rule-16: ingame fills {n} (ledger {_LEDGER_INGAME_FILLS}) "
          f"-> {'OK' if c1 else 'FAIL'}")
    print(f"rule-16: optimistic capture {mean_opt * 100:.4f}c "
          f"(ledger {_LEDGER_CAPTURE_CENTS}c, CI {lo}..{hi}c) "
          f"-> {'OK' if c2 else 'FAIL'}")
    print(f"rule-16: concession capture {mean_conc * 100:.4f}c "
          f"(= optimistic - 4.70c) -> {'OK' if c3 else 'FAIL'}")
    ok = c1 and c2 and c3
    print("RULE-16:", "PASS — the wallet reproduces the capture ledger's totals "
          "on both arms from the pinned Aug fills; the arithmetic core is the "
          "ledger's." if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--db", action="store_true",
                    help="fold the live tables and print the scoreboard")
    args = ap.parse_args()
    if args.selftest:
        rc = _selftest_primitives()
        print()
        rc |= _selftest_fold()
        print()
        rc |= _selftest_rule16()
        return rc
    if args.db:
        return run_db()
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
