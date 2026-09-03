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
#: Bankruptcy floor. Under open-exposure reservation the book can never realize
#: a loss larger than its equity (it never reserves more than it has), so the
#: concession balance asymptotes to zero rather than crossing it — true
#: insolvency is the knife-edge of total ruin. The halt fires within this
#: epsilon of zero; the CONTINUOUS drawdown + capital-clip meters are the
#: operative "book bleeding / $1,000 binds" signals (flagged to the manager).
HALT_FLOOR = 1e-9


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


@dataclass
class WalletResult:
    books: dict[str, LeagueBook]
    refused: list[Fill] = field(default_factory=list)   # unknown-league (term 1)


def _fold_league(slug: str, fills: list[Fill], seed: float,
                 mids: dict[str, float]) -> LeagueBook:
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
            # BANKRUPTCY HALT (51a4103): the concession bankroll gone (realized
            # equity <= 0) stops trading even while optimism shows profit — the
            # book that survives only on the optimistic valuation, made visible.
            if eq_conc <= HALT_FLOOR and not halted:
                halted = True
                halt_line = LedgerLine(
                    league=slug, kind="halt", at=t,
                    note=(f"concession-arm realized equity reached ${eq_conc:.2f}"
                          f" — wallet HALTS trading (optimistic line ${eq_opt:.2f}"
                          f": a book surviving only on optimism)"))

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

    return LeagueBook(
        slug=slug, seed=float(seed), optimistic=eq_opt, concession=eq_conc,
        toll=toll, reserved_conc=res_conc, available_to_size=eq_conc - res_conc,
        halted=halted, halt_line=halt_line, n_fills=n_fills,
        n_clipped_depth=n_clip_depth, n_clipped_reservation=n_clip_res,
        n_zero=n_zero, n_skipped_halt=n_skipped, unrealized_opt=un_opt,
        unrealized_conc=un_conc, n_open_marked=n_marked,
        n_open_unmarkable=n_unmarkable)


def fold(fills: list[Fill], *, seeds: dict[str, float] | None = None,
         mids: dict[str, float] | None = None) -> WalletResult:
    """Fold shadow fills into the paper wallet: route by league (unknown =
    REFUSE, recorded), size each fill pessimistically (concession-arm balance),
    settle realized P&L on both arms, mark open positions UNREALIZED. Pure over
    its inputs — the DB gather builds the Fill list (depth from book_levels,
    mids from the latest snapshot) and the seeds from the control ledger."""
    seeds = seeds or {}
    mids = mids or {}
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
                           seeds.get(slug, SEED_PER_LEAGUE), mids)
        for slug, lg_fills in by_league.items()
    }
    return WalletResult(books=books, refused=refused)


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

    # 4. bankruptcy plant (51a4103): total ruin drives concession equity to ~0 ->
    #    HALT line prints and the next entry does not fold. Under reservation the
    #    book cannot lose more than it holds, so this is the knife-edge terminal
    #    case: seed = one contract's cost basis, that contract totally lost.
    seed_ruin = 0.50 + CONCESSION_IN_GAME          # = one bid@0.50 concession cost
    fa = Fill("tsc-wnba-a-1", "ingame", "bid", 0.50, 0.50, T(0),
              depth=1, settlement=0, settled_at=T(3600))
    fb = Fill("tsc-wnba-a-2", "ingame", "bid", 0.50, 0.50, T(7200),
              depth=1, settlement=1, settled_at=T(10800))
    bk = fold([fa, fb], seeds={"wnba": seed_ruin}).books["wnba"]
    chk("plant bankruptcy: halted with a visible line",
        bk.halted and bk.halt_line is not None and bk.halt_line.kind == "halt")
    chk("plant bankruptcy: concession equity ~0", bk.concession <= HALT_FLOOR)
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

    print("\nFOLD SELFTEST:", "PASS — both arms hand-reconciled, the toll meter "
          "is exactly opt-conc, a fabricated fill moves the ledger by the "
          "computed amount, an over-depth fill clips-and-logs, a loss halts the "
          "bankrupt book with a visible line, an unknown league is refused, and "
          "open positions mark UNREALIZED without touching realized. Can fail."
          if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        rc = _selftest_primitives()
        print()
        rc |= _selftest_fold()
        return rc
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
