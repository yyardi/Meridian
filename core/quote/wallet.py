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
#: The instant depth split onto its own slower loop, so every book_level written
#: from here on carries its OWN captured_at (models.py BookLevel.captured_at:
#: "Stamped by EVERY writer since 2026-08-07"; the local partitioned table's PK
#: forbids NULL). BEFORE this, depth was fetched TOGETHER with its snapshot, so a
#: NULL own-stamp there means the parent snapshot's captured_at is the exact
#: time — safe to inherit. AFTER this, a NULL own-stamp is an ANOMALY (broken
#: invariant, e.g. a bad Supabase import via scripts/import_supabase_export.py),
#: NOT a fetched-together row, and inheriting the parent stamp would BACKDATE it
#: — so post-epoch NULLs are counted OUT and flagged loudly, never inherited.
#:
#: RULE-20 LABEL (read this before inferring a bug from the fix below): this is
#: DEFENSIVE HARDENING, and it FIRES ON ZERO CURRENT ROWS. As of 2026-09-03
#: production holds 15,254,061 book_levels rows, all stamped, with ZERO NULL
#: captured_at (checked) — so the parent-stamp-inherit branch and the anomaly
#: counter guard a state that does not exist in the data today. It is NOT a
#: bugfix for an observed defect; do not read the COALESCE below as evidence that
#: rows were being dropped. It exists so that IF a recorder change or a bad
#: Supabase import (scripts/import_supabase_export.py) reintroduces fetched-
#: together NULL-stamp rows, they are recovered rather than silently dropped —
#: which would read as a thin book, P&L-FLATTERING on a losing book (silent AND
#: biased). Inert-and-self-reporting beats silent-and-biased. (Rule 20: a zero
#: count forbids the CLAIM, not the build — it sets this label, in the code.)
DEPTH_OWNSTAMP_EPOCH = dt.datetime(2026, 8, 7, tzinfo=dt.timezone.utc)
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
              depth: float, quote_size: float) -> tuple[int, str]:
    """Honest sizing (term 3): the STRATEGY's intended quote size, then CAPPED by
    BOTH the recorded book depth at the quoted level AND the free capital. Depth
    is a CAP on the strategy's size (term 7: "a fill exceeding recorded depth
    clips and logs"), NEVER the size itself — sizing to `min(depth, capital)`
    simulates a maker who takes the whole displayed book every fill, a strategy
    nobody ran and no ledger funds (median recorded depth ~1,000 contracts would
    consume a $500 ledger in one fill). v1 quoted ONE contract: shadow_quote_fills
    records no size, so each fill is a unit event (Fill.quote_size defaults 1.0);
    forward, the quoter's own size is the input and depth returns to the cap it
    was registered as.

    Returns (size, cap): 'none' = the full intended size was takeable; 'depth' =
    the venue clipped below intent; 'capital' = the $1,000 clipped below intent;
    'zero_depth'/'zero_capital'/'zero_both' = sized 0, SPLIT by which bound was
    empty. That split is deliberate: one blended 'zero' counter conflated "no book
    at our price" with "no free capital", and reading the blend as a depth
    failure cost an evening — they are different facts and get different lines.
    `available` is reservation-adjusted cash; `cost_basis` is per-contract entry
    cost (stake, plus the concession on the concession arm)."""
    want = int(floor(max(quote_size, 0.0)))
    depth_cap = int(floor(max(depth, 0.0)))
    affordable = (int(floor(max(available, 0.0) / cost_basis))
                  if cost_basis > 0 else 0)
    size = max(min(want, depth_cap, affordable), 0)
    if size == 0:
        no_depth = depth_cap <= 0
        no_capital = affordable <= 0
        if no_depth and not no_capital:
            return 0, "zero_depth"
        if no_capital and not no_depth:
            return 0, "zero_capital"
        return 0, "zero_both"        # both empty, or want==0 (quoted nothing)
    if size < want:
        return size, ("depth" if depth_cap <= affordable else "capital")
    return size, "none"              # full intended size takeable


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
    #: The STRATEGY's intended quote size for this fill — what depth and capital
    #: then CAP. v1 quoted one contract and shadow_quote_fills records no size,
    #: so a v1 fill is a unit event: default 1.0. A forward strategy that records
    #: its own size sets this; depth stays the cap it was registered as, never the
    #: size. (Sizing to full depth was the bug that voided the first wallet run.)
    quote_size: float = 1.0
    #: Provenance of the matched depth level (set by the DB gather; defaults for
    #: direct-construction tests). `depth_parent_stamped` is True when the level
    #: was matched via its parent snapshot's stamp because its OWN stamp was NULL
    #: — a pre-08-07 fetched-together row, where the parent stamp is exact (no
    #: slower loop to backdate). `depth_staleness_s` is the chosen level's age at
    #: fill time, so the parent-stamp relaxation is measured, never free.
    depth_parent_stamped: bool = False
    depth_staleness_s: float | None = None


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
    peak_concurrent_markets: int = 0
    peak_concurrent_contracts: int = 0
    tw_concurrent_markets: float = 0.0      # time-weighted mean over the ledger's span
    tw_concurrent_contracts: float = 0.0
    #: n_zero SPLIT by reason (they sum to n_zero). Kept apart because a blended
    #: zero counter read as a depth failure cost an evening: "no book at our
    #: price" and "no free capital" are different facts. no_capital rising is the
    #: money-runs-out signal (term 3's Sunday scoreboard); no_depth is the
    #: depth-absent artifact (its own line already, _absent_meta).
    n_zero_no_depth: int = 0
    n_zero_no_capital: int = 0
    n_zero_both: int = 0


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
    n_zero_depth = n_zero_cap = n_zero_both = 0
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
                                depth=f.depth, quote_size=f.quote_size)
            size[i] = sz
            if sz == 0:
                n_zero += 1
                if cap == "zero_depth":
                    n_zero_depth += 1                 # no book at our price
                elif cap == "zero_capital":
                    n_zero_cap += 1                   # money ran out (the signal)
                else:
                    n_zero_both += 1
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
        peak_concurrent_markets=peak_m, peak_concurrent_contracts=peak_c,
        tw_concurrent_markets=tw_m, tw_concurrent_contracts=tw_c,
        n_zero_no_depth=n_zero_depth, n_zero_no_capital=n_zero_cap,
        n_zero_both=n_zero_both)


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

def _effective_seeds(session) -> dict[str, dict]:
    """Per-league seed = the most recent control line (birth seed or operator
    reset/resplit): its amount AND its effective instant. The effective instant
    is the COHORT BOUNDARY (ruling ab8be48) — the LIVE wallet folds only fills at
    or after it; the August tape is a separately-labelled historical print, not
    the live balance. A league with NO control line has NO live wallet: it is
    REFUSED, never defaulted (an unseeded wallet reporting a number is the
    empty-verdict over-claim in another slot). Returns {league: {amount,
    effective_at}}; empty means nothing is seeded."""
    from sqlalchemy import text
    rows = session.execute(text("""
        SELECT DISTINCT ON (league) league, amount, effective_at
        FROM paper_wallet_control
        WHERE kind IN ('seed','reset','resplit')
        ORDER BY league, effective_at DESC
    """)).all()
    return {r.league: {"amount": float(r.amount), "effective_at": r.effective_at}
            for r in rows}


def _load_fills_with_depth(
    session, *, staleness_s: float = DEPTH_STALENESS_S,
) -> tuple[list[Fill], int, int, int]:
    """shadow_quote_fills + the recorded book depth at each fill's quoted level.

    Depth-join (D's ruling, registered 6d4ce04): book_levels is ONE YES-frame
    book, so a BID quote joins side='bid' and an ASK joins side='offer', both at
    price == quote_price (4dp exact; conservative-zero otherwise), within the
    staleness bound.

    Time source (amended, D-approved + gated): the level's OWN stamp
    (book_levels.captured_at) is the authority whenever present — depth samples
    on a slower loop than price since DEPTH_OWNSTAMP_EPOCH, so its own stamp is
    the only one that answers the ordering question, and the parent snapshot's
    stamp is NEVER allowed to backdate a slow-loop row. A NULL own-stamp is
    handled by EPOCH, not blanket: before DEPTH_OWNSTAMP_EPOCH depth was fetched
    TOGETHER with the snapshot, so the own stamp is genuinely NULL and the
    parent's captured_at IS the exact time (safe to inherit); at/after the epoch
    a NULL own-stamp is a broken-invariant ANOMALY (not fetched-together) whose
    parent stamp WOULD backdate it, so it is counted OUT and flagged loudly (D's
    ruling — the staleness counter is blind to a backdated row, which reads
    healthy precisely because it was backdated).

    DEFENSIVE HARDENING, INERT TODAY: production holds zero NULL-stamped rows
    (see DEPTH_OWNSTAMP_EPOCH), so the inherit branch fires on nothing now. It is
    NOT the fix for the ~200x n_zero gap (that gap is on fully-stamped rows and
    is still under investigation via --depth-debug); it prevents a FUTURE silent,
    P&L-flattering drop of imported fetched-together rows.

    Returns (fills, n_depth_absent, n_total, n_post_epoch_null_levels); the last
    is the anomaly count (should be 0). depth absent -> depth 0 -> the fill clips
    to zero, and that RATE is printed so the artifact is measurable."""
    import bisect
    from collections import defaultdict

    from sqlalchemy import text

    rows = session.execute(text("""
        SELECT market_slug, game_id, regime, side, quote_price, mid_at_fill,
               filled_at, settlement, settled_at
        FROM shadow_quote_fills ORDER BY filled_at
    """)).all()
    if not rows:
        return [], 0, 0, 0

    markets = sorted({r.market_slug for r in rows})
    tmin = min(r.filled_at for r in rows) - dt.timedelta(seconds=staleness_s)
    tmax = max(r.filled_at for r in rows)
    # Effective stamp = own stamp when present; the parent snapshot's stamp only
    # for a NULL own-stamp BEFORE the epoch (fetched-together, parent exact). A
    # NULL own-stamp at/after the epoch fails the gate below -> excluded from the
    # match (counted out) and tallied as an anomaly, never inherited/backdated.
    epoch = DEPTH_OWNSTAMP_EPOCH
    lvls = session.execute(text("""
        SELECT ms.market_slug AS market_slug, bl.side AS side,
               bl.price AS price, bl.quantity AS quantity,
               COALESCE(bl.captured_at, ms.captured_at) AS captured_at,
               (bl.captured_at IS NULL) AS parent_stamped
        FROM book_levels bl
        JOIN market_snapshots ms ON ms.id = bl.snapshot_id
        WHERE ms.market_slug = ANY(:markets)
          AND bl.side IN ('bid','offer')
          AND (bl.captured_at IS NOT NULL OR ms.captured_at < :epoch)
          AND COALESCE(bl.captured_at, ms.captured_at) >= :tmin
          AND COALESCE(bl.captured_at, ms.captured_at) <= :tmax
    """), {"markets": markets, "tmin": tmin, "tmax": tmax, "epoch": epoch}).all()

    # Anomaly: NULL own-stamp AT/AFTER the epoch (invariant broken) — counted
    # out above, tallied here so it is LOUD rather than a silent coverage dip.
    n_post_epoch_null = session.execute(text("""
        SELECT count(*) FROM book_levels bl
        JOIN market_snapshots ms ON ms.id = bl.snapshot_id
        WHERE ms.market_slug = ANY(:markets)
          AND bl.side IN ('bid','offer')
          AND bl.captured_at IS NULL AND ms.captured_at >= :epoch
          AND ms.captured_at >= :tmin AND ms.captured_at <= :tmax
    """), {"markets": markets, "tmin": tmin, "tmax": tmax, "epoch": epoch}).scalar()

    series: dict[tuple, list] = defaultdict(list)
    for lv in lvls:
        series[(lv.market_slug, lv.side, round(float(lv.price), 4))].append(
            (lv.captured_at, float(lv.quantity), bool(lv.parent_stamped)))
    index: dict[tuple, tuple] = {}
    for k, s in series.items():
        s.sort(key=lambda x: x[0])
        index[k] = ([t for t, _, _ in s], [q for _, q, _ in s],
                    [p for _, _, p in s])

    fills: list[Fill] = []
    n_absent = 0
    for r in rows:
        book_side = "bid" if r.side == "bid" else "offer"
        key = (r.market_slug, book_side, round(float(r.quote_price), 4))
        depth = 0.0
        parent_stamped = False
        staleness = None
        hit = index.get(key)
        if hit is not None:
            times, qtys, parents = hit
            pos = bisect.bisect_right(times, r.filled_at) - 1  # newest <= fill
            if pos >= 0 and times[pos] >= r.filled_at - dt.timedelta(
                    seconds=staleness_s):
                depth = qtys[pos]
                parent_stamped = parents[pos]
                staleness = (r.filled_at - times[pos]).total_seconds()
        if depth <= 0:
            n_absent += 1
        fills.append(Fill(
            market_slug=r.market_slug, regime=r.regime, side=r.side,
            quote_price=float(r.quote_price), mid_at_fill=float(r.mid_at_fill),
            filled_at=r.filled_at, depth=depth,
            settlement=(None if r.settlement is None else int(r.settlement)),
            settled_at=r.settled_at,
            depth_parent_stamped=(parent_stamped if depth > 0 else False),
            depth_staleness_s=(staleness if depth > 0 else None)))
    return fills, n_absent, len(rows), int(n_post_epoch_null or 0)


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


def _absent_meta(fills: list[Fill]) -> dict:
    """Depth-absent as its OWN line (D's remedy): count, share, and the capture
    the absent fills WOULD have carried at unit size — the suppression cost.
    exact-match clip-to-zero is capacity-conservative but P&L-SIGN-DEPENDENT: an
    absent fill contributes nothing, so on a negative-capture book it FLATTERS
    the loss. 10%-of-ingame is the pre-data trigger for the within-one-min_tick
    revisit (its own labelled column, never replacing exact-match)."""
    n_total = len(fills)
    absent = [f for f in fills if f.depth <= 0]
    ingame = [f for f in fills if f.regime == "ingame"]
    ingame_absent = [f for f in absent if f.regime == "ingame"]

    def _wouldbe(f: Fill, conc: float) -> float:
        return net_capture_mark(side=f.side, quote_price=f.quote_price,
                                mid_at_fill=f.mid_at_fill) - conc

    wb_opt = [_wouldbe(f, 0.0) for f in absent]
    wb_conc = [_wouldbe(f, concession_for(f.regime)) for f in absent]
    ing_rate = (len(ingame_absent) / len(ingame)) if ingame else 0.0
    # The parent-stamp relaxation, MEASURED: how many depth matches leaned on a
    # fetched-together parent stamp (own stamp NULL), and how stale those chosen
    # levels were. If this is a large share, the historical print is resting on
    # the pre-08-07 tape — visible, not free.
    ps = [f for f in fills if f.depth > 0 and f.depth_parent_stamped]
    ps_stale = [f.depth_staleness_s for f in ps if f.depth_staleness_s is not None]
    sized = [f for f in fills if f.depth > 0]
    return {
        "n_fills": n_total,
        "depth_absent": len(absent),
        "depth_absent_rate": (len(absent) / n_total) if n_total else 0.0,
        "n_ingame": len(ingame),
        "ingame_absent": len(ingame_absent),
        "ingame_absent_rate": ing_rate,
        "absent_wouldbe_opt_sum": sum(wb_opt),
        "absent_wouldbe_conc_sum": sum(wb_conc),
        "absent_wouldbe_opt_mean_c": (sum(wb_opt) / len(wb_opt) * 100) if wb_opt else 0.0,
        "absent_wouldbe_conc_mean_c": (sum(wb_conc) / len(wb_conc) * 100) if wb_conc else 0.0,
        "trigger_10pct_ingame": ing_rate > 0.10,
        "n_depth_sized": len(sized),
        "n_depth_parent_stamped": len(ps),
        "depth_parent_stamped_rate": (len(ps) / len(sized)) if sized else 0.0,
        "parent_stamped_staleness_max_s": max(ps_stale) if ps_stale else 0.0,
        "parent_stamped_staleness_mean_s": (sum(ps_stale) / len(ps_stale)) if ps_stale else 0.0,
    }


def _live_cohort(fills: list[Fill], seeds: dict[str, dict]):
    """Partition fills into the LIVE cohort — forward-only from each league's
    seed instant, seeded leagues ONLY — and the list of UNSEEDED leagues (which
    have fills but no seed line: refused, never defaulted). Pure (ruling
    ab8be48). Returns (live_fills, unseeded)."""
    by_league: dict[str, list[Fill]] = defaultdict(list)
    for f in fills:
        lg = route_league(f.market_slug)
        if lg is not None:
            by_league[lg.slug].append(f)
    live: list[Fill] = []
    for lg, s in seeds.items():
        live.extend([f for f in by_league.get(lg, [])
                     if f.filled_at >= s["effective_at"]])
    unseeded = sorted(lg for lg in by_league if lg not in seeds)
    return live, unseeded


def gather(session, *, staleness_s: float = DEPTH_STALENESS_S, now=None):
    """Fold the live tables into the wallet, with the COHORT BOUNDARY enforced
    (ruling ab8be48). Returns (live, historical, meta):

    * live: the operator's wallet — FORWARD-ONLY from each league's seed
      instant, and ONLY for seeded leagues. A league with no control line is
      REFUSED (listed in meta['unseeded']), never defaulted — an unseeded wallet
      reporting a number is an over-claim.
    * historical: the full-cohort fold (default seeds), a separately-LABELLED
      print — e.g. v1's August tape driven to operational ruin. Never the live
      balance.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    seeds = _effective_seeds(session)                       # {lg: {amount, effective_at}}
    fills, _n_absent, _n_total, n_post_epoch_null = _load_fills_with_depth(
        session, staleness_s=staleness_s)
    mids = _load_mids(session, {f.market_slug for f in fills
                                if f.settlement is None})

    # LIVE: forward-from-seed, seeded leagues only (pure, regression-tested)
    seed_amounts = {lg: s["amount"] for lg, s in seeds.items()}
    live_fills, unseeded = _live_cohort(fills, seeds)
    live = fold(live_fills, seeds=seed_amounts, mids=mids, now=now)

    # HISTORICAL: the full cohort, labelled (default seeds)
    historical = fold(fills, mids=mids, now=now)

    meta = {
        "seeded": bool(seeds),
        "unseeded": unseeded,
        "seeds": {lg: {"amount": s["amount"],
                       "effective_at": s["effective_at"].isoformat()}
                  for lg, s in seeds.items()},
        "staleness_s": staleness_s,
        "live_absent": _absent_meta(live_fills),
        "historical_absent": _absent_meta(fills),
        # Anomaly (should be 0): NULL own-stamp at/after DEPTH_OWNSTAMP_EPOCH —
        # a broken invariant, counted out of the join, surfaced loudly here.
        "post_epoch_null_levels": n_post_epoch_null,
    }
    return live, historical, meta


def run_db() -> int:
    from core.storage.base import get_engine
    from core.storage import get_sessionmaker
    try:
        with get_sessionmaker(get_engine())() as s:
            live, historical, meta = gather(s)
    except Exception as exc:  # noqa: BLE001 — DB may be unreachable from here
        msg = str(exc).lower()
        if ("does not exist" in msg or "could not connect" in msg
                or "connection refused" in msg):
            print("wallet tables not present / DB unreachable from here — the "
                  "wallet runs where shadow_quote_fills + book_levels live "
                  "(main checkout / prod).")
            return 0
        raise

    def _absent_line(am):
        print(f"depth-absent (clip-to-zero): {am['depth_absent']:,} "
              f"({am['depth_absent_rate']:.1%} of all, "
              f"{am['ingame_absent_rate']:.1%} of ingame) | would-be capture at "
              f"unit size: opt ${am['absent_wouldbe_opt_sum']:+.2f} "
              f"({am['absent_wouldbe_opt_mean_c']:+.2f}c/fill), conc "
              f"${am['absent_wouldbe_conc_sum']:+.2f} "
              f"({am['absent_wouldbe_conc_mean_c']:+.2f}c/fill) — suppression cost")
        if am["trigger_10pct_ingame"]:
            print("  *** TRIGGER: ingame depth-absent > 10% — build the "
                  "within-one-min_tick snap (its own column, never replacing "
                  "exact-match). ***")
        if am["n_depth_parent_stamped"]:
            print(f"  depth via fetched-together parent stamp: "
                  f"{am['n_depth_parent_stamped']:,} of {am['n_depth_sized']:,} "
                  f"sized ({am['depth_parent_stamped_rate']:.1%}) | staleness "
                  f"mean {am['parent_stamped_staleness_mean_s']:.0f}s, max "
                  f"{am['parent_stamped_staleness_max_s']:.0f}s — the pre-08-07 "
                  f"relaxation (own stamp NULL, parent exact), measured not free")

    def _book(b):
        drawdown = 1.0 - (b.concession / b.seed) if b.seed else 0.0
        clip_rate = (b.n_clipped_reservation / b.n_fills) if b.n_fills else 0.0
        print(f"\n  [{b.slug}] seed ${b.seed:.2f}   fills {b.n_fills} "
              f"(depth-clip {b.n_clipped_depth}, capital-clip "
              f"{b.n_clipped_reservation}, zero {b.n_zero} "
              f"[no-depth {b.n_zero_no_depth}, no-capital {b.n_zero_no_capital}, "
              f"both {b.n_zero_both}])"
              + ("   *** HALTED ***" if b.halted else ""))
        print(f"    optimistic ${b.optimistic:10.2f}  P&L ${b.optimistic - b.seed:+.2f}")
        print(f"    concession ${b.concession:10.2f}  P&L ${b.concession - b.seed:+.2f}"
              f"   drawdown {drawdown:.1%}   capital-clip {clip_rate:.1%}")
        print(f"    toll ${b.toll:.2f}   unrealized opt ${b.unrealized_opt:+.2f} / "
              f"conc ${b.unrealized_conc:+.2f}")
        print(f"    concurrency: peak {b.peak_concurrent_contracts} contracts / "
              f"{b.peak_concurrent_markets} markets (~${b.peak_concurrent_contracts}"
              f" worst-case at unit size vs ${b.seed:.0f}); time-weighted "
              f"{b.tw_concurrent_contracts:.1f}/{b.tw_concurrent_markets:.1f}")
        if b.halt_line is not None:
            print(f"    HALT: {b.halt_line.note}")

    if meta.get("post_epoch_null_levels"):
        print(f"*** ANOMALY: {meta['post_epoch_null_levels']:,} book_levels with "
              f"NULL captured_at AT/AFTER {DEPTH_OWNSTAMP_EPOCH.date()} — the "
              f"own-stamp invariant is broken (bad import?). These are counted "
              f"OUT of the depth join, never inherited. Investigate. ***\n")

    print("=== LIVE WALLET (forward-only from each seed line; bars "
          f"${DAILY_BAR}/day, ${MONTHLY_BAR:.0f}/mo) ===")
    if not meta["seeded"]:
        print("  UNSEEDED — no live balance. Refusing to report rather than "
              "default: write a seed line (paper_wallet_control) to begin. The "
              "August tape is a historical print below, never the live balance.")
    else:
        if meta["unseeded"]:
            print(f"  REFUSED (no seed line, not in the live wallet): "
                  f"{', '.join(meta['unseeded'])}")
        _absent_line(meta["live_absent"])
        for b in sorted(live.books.values(), key=lambda x: x.slug):
            _book(b)

    print("\n=== HISTORICAL PRINT (full cohort — NOT the live balance; e.g. v1's "
          "August tape) ===")
    _absent_line(meta["historical_absent"])
    for b in sorted(historical.books.values(), key=lambda x: x.slug):
        _book(b)
    return 0


def _depth_debug(n: int = 20, staleness_s: float = DEPTH_STALENESS_S) -> int:
    """Instrument the depth-join predicate funnel for the first N zero-depth
    fills — names which predicate collapses coverage, MEASURED on real data
    rather than hypothesised (the 200x n_zero gap). Run against prod:

        python -m core.quote.wallet --depth-debug [N]

    Replicates _load_fills_with_depth's exact matcher (same float-4dp key, same
    bisect + staleness), then for each zero-depth fill shows the count surviving
    each successive predicate. The column that drops to 0 IS the cause:
      * +side=0            -> side value / mapping
      * +price[numeric]=0  -> the exact price is not in the book (tick/frame);
                              'book prices present' shows what IS there vs quote
      * +price[round4] != +price[numeric] -> float-4dp rounding (the price-repr
                              hypothesis) diverges from NUMERIC equality
      * +window=0 (price>0) -> staleness/time: the level exists but not near fill
      * python_index_has_key=False while +price[numeric]>0 -> a Python-matcher
                              bug (the float key), the smoking gun
    The fill's quote_price is compared as NUMERIC (bound as its Decimal), never
    via a float CAST that would itself inject the error we are testing for."""
    import bisect
    from collections import defaultdict

    from sqlalchemy import text

    from core.storage import get_sessionmaker
    from core.storage.base import get_engine

    with get_sessionmaker(get_engine())() as s:
        rows = s.execute(text(
            "SELECT market_slug, side, quote_price, filled_at, regime "
            "FROM shadow_quote_fills ORDER BY filled_at")).all()
        if not rows:
            print("no shadow_quote_fills here.")
            return 0
        markets = sorted({r.market_slug for r in rows})
        tmin = min(r.filled_at for r in rows) - dt.timedelta(seconds=staleness_s)
        tmax = max(r.filled_at for r in rows)
        lvls = s.execute(text("""
            SELECT ms.market_slug AS market_slug, bl.side AS side,
                   bl.price AS price, bl.quantity AS quantity,
                   COALESCE(bl.captured_at, ms.captured_at) AS captured_at
            FROM book_levels bl JOIN market_snapshots ms ON ms.id = bl.snapshot_id
            WHERE ms.market_slug = ANY(:markets) AND bl.side IN ('bid','offer')
              AND COALESCE(bl.captured_at, ms.captured_at) >= :tmin
              AND COALESCE(bl.captured_at, ms.captured_at) <= :tmax
        """), {"markets": markets, "tmin": tmin, "tmax": tmax}).all()
        series: dict[tuple, list] = defaultdict(list)
        for lv in lvls:
            series[(lv.market_slug, lv.side, round(float(lv.price), 4))].append(
                (lv.captured_at, float(lv.quantity)))
        index: dict[tuple, tuple] = {}
        for k, v in series.items():
            v.sort(key=lambda x: x[0])
            index[k] = ([t for t, _ in v], [q for _, q in v])

        zeros = []
        for r in rows:
            bs = "bid" if r.side == "bid" else "offer"
            key = (r.market_slug, bs, round(float(r.quote_price), 4))
            depth = 0.0
            hit = index.get(key)
            if hit is not None:
                times, qtys = hit
                pos = bisect.bisect_right(times, r.filled_at) - 1
                if pos >= 0 and times[pos] >= r.filled_at - dt.timedelta(
                        seconds=staleness_s):
                    depth = qtys[pos]
            if depth <= 0:
                zeros.append(r)

        print(f"book_levels loaded in window: {len(lvls):,}  |  "
              f"zero-depth fills: {len(zeros):,}/{len(rows):,} "
              f"({(len(zeros) / len(rows) if rows else 0):.1%})  |  "
              f"staleness {staleness_s:.0f}s  |  first {min(n, len(zeros))}:")

        for i, r in enumerate(zeros[:n]):
            bs = "bid" if r.side == "bid" else "offer"
            qpk = round(float(r.quote_price), 4)
            p = {"m": r.market_slug, "bs": bs, "qp": r.quote_price, "qpk": qpk,
                 "lo": r.filled_at - dt.timedelta(seconds=staleness_s),
                 "hi": r.filled_at}

            def cnt(where, _p=p):
                return s.execute(text(
                    "SELECT count(*) FROM book_levels bl "
                    "JOIN market_snapshots ms ON ms.id = bl.snapshot_id "
                    "WHERE ms.market_slug = :m " + where), _p).scalar()

            c_m = cnt("")
            c_s = cnt("AND bl.side = :bs")
            c_p = cnt("AND bl.side = :bs AND bl.price = :qp")
            c_pk = cnt("AND bl.side = :bs AND round(bl.price, 4) = :qpk")
            c_w = cnt("AND bl.side = :bs AND bl.price = :qp "
                      "AND COALESCE(bl.captured_at, ms.captured_at) "
                      "BETWEEN :lo AND :hi")
            in_index = (r.market_slug, bs, qpk) in index
            near = s.execute(text(
                "SELECT bl.price AS price, count(*) AS c FROM book_levels bl "
                "JOIN market_snapshots ms ON ms.id = bl.snapshot_id "
                "WHERE ms.market_slug = :m AND bl.side = :bs "
                "AND COALESCE(bl.captured_at, ms.captured_at) BETWEEN :lo AND :hi "
                "GROUP BY bl.price ORDER BY c DESC LIMIT 8"), p).all()

            print(f"\n[{i}] {r.market_slug} side={r.side}->{bs} "
                  f"quote_price={r.quote_price} (float key {qpk}) "
                  f"filled_at={r.filled_at.isoformat()}")
            print(f"    funnel: market={c_m:,}  +side={c_s:,}  "
                  f"+price[numeric]={c_p:,}  +price[round4]={c_pk:,}  "
                  f"+window={c_w:,}  |  python_index_has_key={in_index}")
            pr = ", ".join(f"{float(x.price):.4f}x{x.c}" for x in near) or "NONE"
            print(f"    book prices present (this mkt+side, in window): {pr}")
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

    # sizing: intended quote_size, then CAPPED by depth and by capital.
    # v1 unit: want 1, plenty of depth+capital -> size 1, nothing clipped.
    check("size: want 1, depth 100, afford 250 -> 1, cap 'none'",
          size_fill(available=100.0, cost_basis=0.40, depth=100, quote_size=1),
          (1, "none"))
    # depth binds: want 1000 > depth 100 (< affordable 250) -> 100, cap 'depth'
    check("size: want 1000 > depth 100 -> 100, cap 'depth'",
          size_fill(available=100.0, cost_basis=0.40, depth=100, quote_size=1000),
          (100, "depth"))
    # capital binds: want 1000 > affordable 250 (< depth 1000) -> 250, 'capital'
    check("size: want 1000, depth 1000, afford 250 -> 250, cap 'capital'",
          size_fill(available=100.0, cost_basis=0.40, depth=1000, quote_size=1000),
          (250, "capital"))
    # depth is a CAP, never the target: want 1 with depth 1000 is still 1
    check("size: want 1 with depth 1000 stays 1 (depth is a CAP, not target)",
          size_fill(available=100.0, cost_basis=0.40, depth=1000, quote_size=1)[0],
          1)
    # zero split by reason
    check("size: no capital -> (0,'zero_capital')",
          size_fill(available=0.0, cost_basis=0.40, depth=1000, quote_size=1),
          (0, "zero_capital"))
    check("size: no depth -> (0,'zero_depth')",
          size_fill(available=100.0, cost_basis=0.40, depth=0, quote_size=1),
          (0, "zero_depth"))
    check("size: no depth AND no capital -> (0,'zero_both')",
          size_fill(available=0.0, cost_basis=0.40, depth=0, quote_size=1),
          (0, "zero_both"))

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

    # 1. clean winning bid, depth-clipped: hand-computed both arms + toll.
    #    quote_size 1000 > depth 10 -> depth is the cap (the clip under test).
    f1 = Fill("tsc-wnba-ny-chi-1", "ingame", "bid", 0.40, 0.43, T(0),
              depth=10, settlement=1, settled_at=T(3600), quote_size=1000)
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
              depth=5, settlement=1, settled_at=T(3600), quote_size=1000)
    b2 = fold([f1, f2], seeds={"wnba": 500.0}).books["wnba"]
    chk("plant fabricated: ledger moves by EXACTLY 3.50",
        abs((b2.optimistic - b.optimistic) - 3.50) < 1e-9)

    # 3. rule-18 depth-clip plant: book depth binds -> size = depth, cap 'depth'
    f3 = Fill("tsc-wnba-x-3", "ingame", "bid", 0.40, 0.43, T(0),
              depth=3, settlement=1, settled_at=T(3600), quote_size=1000)
    b3 = fold([f3], seeds={"wnba": 500.0}).books["wnba"]
    chk("plant depth-clip: size=depth=3 -> opt 501.80, cap 'depth'",
        abs(b3.optimistic - 501.8) < 1e-9 and b3.n_clipped_depth == 1)

    # 3b. RESERVATION-clip plant (the Sunday signal): capital binds below depth.
    #     seed 1.0, cost 0.547 -> affordable 1 << depth 100 -> cap 'capital'.
    frc = Fill("tsc-wnba-rc-1", "ingame", "bid", 0.50, 0.50, T(0),
               depth=100, settlement=None, settled_at=None, quote_size=1000)
    brc = fold([frc], seeds={"wnba": 1.0}).books["wnba"]
    chk("plant reservation-clip: capital bound size to 1 (cap 'capital')",
        brc.n_clipped_reservation == 1 and brc.n_clipped_depth == 0
        and brc.reserved_conc > 0)

    # 4. bankruptcy plant (registered): a loss drops concession equity below 20%
    #    of seed (operational ruin) -> HALT line prints, next entry does not fold.
    #    seed 10, one bid@0.50 loss sized to depth 100: 18 contracts x $0.547 cost
    #    -> equity 10 - 9.846 = $0.154 < $2.00 (20% of $10) -> halt.
    fa = Fill("tsc-wnba-a-1", "ingame", "bid", 0.50, 0.50, T(0),
              depth=100, settlement=0, settled_at=T(3600), quote_size=1000)
    fb = Fill("tsc-wnba-a-2", "ingame", "bid", 0.50, 0.50, T(7200),
              depth=100, settlement=1, settled_at=T(10800), quote_size=1000)
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
              depth=10, settlement=None, settled_at=None, quote_size=1000)
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
             depth=5, settlement=1, settled_at=T(30), quote_size=1000),
        Fill("tsc-wnba-c-2", "ingame", "bid", 0.40, 0.43, T(10),
             depth=3, settlement=1, settled_at=T(40), quote_size=1000),
        Fill("tsc-wnba-c-3", "ingame", "bid", 0.40, 0.43, T(20),
             depth=2, settlement=1, settled_at=T(50), quote_size=1000),
    ]
    bc = fold(fc, seeds={"wnba": 500.0}).books["wnba"]
    chk("concurrency: peak 10 contracts across 3 markets (overlap [20,30])",
        bc.peak_concurrent_contracts == 10 and bc.peak_concurrent_markets == 3)
    chk("concurrency: time-weighted within (0, peak]",
        0 < bc.tw_concurrent_contracts <= 10 and 0 < bc.tw_concurrent_markets <= 3)

    # 7. THE SIZING FIX (v1 quoted ONE contract; depth is a CAP, not the target).
    #    A unit fill (quote_size default 1.0) on a 1,000-deep book sizes to 1, and
    #    its P&L is +0.60 (one contract), NOT +600 (the whole book).
    fv = Fill("tsc-wnba-v-1", "ingame", "bid", 0.40, 0.43, T(0),
              depth=1000, settlement=1, settled_at=T(3600))   # quote_size = 1.0
    bv = fold([fv], seeds={"wnba": 500.0}).books["wnba"]
    chk("sizing fix: unit fill on depth 1000 -> size 1, opt +0.60 (not +600)",
        bv.n_fills == 1 and abs(bv.optimistic - 500.60) < 1e-9
        and bv.n_clipped_depth == 0)
    #    and the money does NOT run out after a handful of unit fills — the halt
    #    was an artifact of taking the whole book, not v1's exposure.
    many = [Fill(f"tsc-wnba-m-{i}", "ingame", "bid", 0.50, 0.50, T(i),
                 depth=1000, settlement=None, settled_at=None) for i in range(20)]
    bm = fold(many, seeds={"wnba": 500.0}).books["wnba"]
    chk("sizing fix: 20 unit fills on $500 do NOT halt (was ~25 over-sized -> halt)",
        not bm.halted and bm.n_fills == 20)

    # 8. n_zero SPLIT by reason: depth-absent (no book) vs capital-starved (no
    #    money) zero for DIFFERENT reasons and are counted apart — the conflated
    #    counter is what read as a depth failure and cost an evening.
    fzd = Fill("tsc-wnba-zd-1", "ingame", "bid", 0.40, 0.43, T(0),
               depth=0, settlement=None, settled_at=None)      # no depth
    bzd = fold([fzd], seeds={"wnba": 500.0}).books["wnba"]
    chk("n_zero split: depth-absent -> n_zero_no_depth (not no_capital)",
        bzd.n_zero == 1 and bzd.n_zero_no_depth == 1 and bzd.n_zero_no_capital == 0)
    fzc = Fill("tsc-wnba-zc-1", "ingame", "bid", 0.90, 0.90, T(0),
               depth=1000, settlement=None, settled_at=None)   # deep book, no money
    bzc = fold([fzc], seeds={"wnba": 0.50}).books["wnba"]       # seed < one contract
    chk("n_zero split: capital-starved -> n_zero_no_capital (not no_depth)",
        bzc.n_zero == 1 and bzc.n_zero_no_capital == 1 and bzc.n_zero_no_depth == 0)

    # COHORT BOUNDARY (ruling ab8be48): live is forward-only from the seed, and
    # a league with no seed line is REFUSED (never defaulted) — the over-claim
    # fix. Pure test of the partition.
    aug = Fill("tsc-wnba-h-1", "ingame", "bid", 0.40, 0.43,
               dt.datetime(2026, 8, 20, tzinfo=dt.timezone.utc), depth=5,
               settlement=1, settled_at=dt.datetime(2026, 8, 20, 20,
                                                     tzinfo=dt.timezone.utc))
    sep = Fill("tsc-wnba-h-2", "ingame", "bid", 0.40, 0.43,
               dt.datetime(2026, 9, 4, tzinfo=dt.timezone.utc), depth=5,
               settlement=1, settled_at=dt.datetime(2026, 9, 4, 20,
                                                     tzinfo=dt.timezone.utc))
    live_u, unseeded_u = _live_cohort([aug, sep], {})
    chk("cohort: unseeded -> live empty, league refused",
        live_u == [] and unseeded_u == ["wnba"])
    seed = {"wnba": {"amount": 500.0,
                     "effective_at": dt.datetime(2026, 9, 3,
                                                 tzinfo=dt.timezone.utc)}}
    live_s, unseeded_s = _live_cohort([aug, sep], seed)
    chk("cohort: seeded -> forward-only (drops the August fill)",
        live_s == [sep] and unseeded_s == [])

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
    ap.add_argument("--depth-debug", nargs="?", type=int, const=20, default=None,
                    metavar="N",
                    help="instrument the depth-join predicate funnel for the "
                         "first N zero-depth fills (default 20) — names the "
                         "predicate that collapses coverage, on real data")
    args = ap.parse_args()
    if args.selftest:
        rc = _selftest_primitives()
        print()
        rc |= _selftest_fold()
        print()
        rc |= _selftest_rule16()
        return rc
    if args.depth_debug is not None:
        return _depth_debug(n=args.depth_debug)
    if args.db:
        return run_db()
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
