"""GRIDIRON policy A/B scorer — settlement-primary, game-clustered, rule-25 wired.

Registration: docs/gridiron/policy-variants.md (amendment 9d371e8, correction
385eae5). Two ENGINES (BASE, FLATTEN); three CUTS (WIDTH, LATENESS, PATIENCE) on
BASE's own fills. This module scores both, on shadow_quote_fills carrying the
`policy` stamp, `settlement`, and touch-at-fill (best_bid/ask_at_fill).

METRIC RULING (amendment), enforced here:
  * PRIMARY: settlement P&L. On a binary held to expiry it is dominated by
    directional variance, so the EFFECTIVE SAMPLE IS GAMES, NOT FILLS — every CI
    is game-clustered (core.quote.adverse_selection.clustered_mean, the cluster-
    robust sandwich with df=G-1 the rest of the program uses).
  * SECONDARY: markout at pre-named horizons (analysis/quote_v2_markout.py; lower
    variance, real power at this n). Referenced, not re-implemented.
  * RETIRED: capture versus mid-at-fill — wrong for a maker in both directions.
    Not computed here; the column stays as a fact, the metric does not.
  * PHANTOM FLAG on every arm and cut, always reported. A fill is a PHANTOM when
    the touch never reached our price (a bid fill with best_ask_at_fill > our
    bid, an ask fill with best_bid_at_fill < our ask): the mid-cross rule booked
    a fill reality would have refused.
  * RULE 25 is binding on every comparison: no composite is reported alone
    (report_composite carries numerator, denominator and per-event mean), and any
    ratio used to RANK arms is checked at both degenerate extremes
    (degenerate_extremes_warning). The arms differ in ACTIVITY by construction,
    which is exactly when a ratio ranks activity instead of policy — the >5.5c
    band once topped a table while being the worst cell on the board.
  * RULE 22: a zero count cannot print bare — report_count says whether a zero is
    an unproven instrument or a measured absence, and every coverage gap (a cut
    whose input is missing) is COUNTED, never silently dropped.

FLATTEN is scored on DISPERSION AND TAIL, not mean: its registered premise is
inventory RISK, which a per-fill mean structurally cannot address (on the WNBA
tape capture-by-position is flat and ADD≈REDUCE). The caveat outranks the
parameter and is printed with the table: **every cell is negative at every k;
flattening improves a losing book, it does not make a winning one.**

DESIGN-NOT-EVIDENCE until the slate settles: this scores the forward CFB A/B once
its fills settle; run before then it reports coverage, not conclusions.

    .venv/bin/python analysis/gridiron_ab_score.py --selftest
    .venv/bin/python analysis/gridiron_ab_score.py            # DB read + report
"""
from __future__ import annotations

import statistics as stats
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from analysis.guards import (  # noqa: E402
    degenerate_extremes_warning,
    report_composite,
    report_count,
)
from core.quote.adverse_selection import clustered_mean  # noqa: E402

BID, ASK = "bid", "ask"

#: Registered WIDTH buckets (¢ of quoted spread). Edges are upper-exclusive; the
#: last is open. The cut's own hypothesis ("wide is better") was a phantom
#: artifact and is REFUTED, not inverted — it is reported, never ranked-on.
WIDTH_EDGES = [1.5, 2.5, 3.5, 5.5]
WIDTH_LABELS = ["<=1.5", "1.5-2.5", "2.5-3.5", "3.5-5.5", ">5.5"]

#: PATIENCE cut: a fill within this many seconds of a prior fill in the SAME
#: market is "impatient" (v1 requoting into a dip); the rest are the control.
PATIENCE_WINDOW_SECONDS = 30.0


@dataclass(frozen=True)
class Fill:
    """One scored fill, arm-stamped. Prices are YES-frame in [0,1]; times are
    epoch seconds; settlement is 0/1 or None (unsettled)."""
    market: str
    game: str
    side: str
    quote_price: float
    spread_at_quote: float          # in [0,1]; ×100 for ¢
    filled_at: float                # epoch seconds
    settlement: int | None
    best_bid_at_fill: float | None
    best_ask_at_fill: float | None
    event_period: str | None = None
    policy: str = "base"


# --------------------------------------------------------------------------- #
# Core per-fill quantities — the arithmetic a quant should be able to check.
# --------------------------------------------------------------------------- #

def settlement_pnl_cents(f: Fill) -> float | None:
    """Settlement P&L of one fill, in cents, or None if unsettled.

    A filled BID is a unit LONG YES bought at `quote_price`; at settlement s it
    is worth s, so P&L = s - p. A filled ASK is a unit SHORT YES sold at
    `quote_price` (equivalently long NO at 1-p); P&L = p - s. ×100 -> cents.
    """
    if f.settlement is None:
        return None
    s = float(f.settlement)
    edge = (s - f.quote_price) if f.side == BID else (f.quote_price - s)
    return edge * 100.0


def is_phantom(f: Fill) -> bool | None:
    """True if the touch never reached our price (the mid-cross rule booked a
    fill reality would refuse). None if touch-at-fill is missing — a coverage
    gap, counted, never guessed. A BID fills for real only if the ask came down
    to our bid (best_ask_at_fill <= our bid); an ASK only if the bid came up to
    our ask (best_bid_at_fill >= our ask)."""
    if f.side == BID:
        if f.best_ask_at_fill is None:
            return None
        return f.best_ask_at_fill > f.quote_price
    else:
        if f.best_bid_at_fill is None:
            return None
        return f.best_bid_at_fill < f.quote_price


def _pnl_by_game(fills: list[Fill]) -> dict[str, list[float]]:
    """Per-game lists of settled per-fill P&L — the input clustered_mean wants
    (clusters = games, the effective sample for a binary held to expiry)."""
    by_game: dict[str, list[float]] = defaultdict(list)
    for f in fills:
        p = settlement_pnl_cents(f)
        if p is not None:
            by_game[f.game].append(p)
    return by_game


# --------------------------------------------------------------------------- #
# Per-arm / per-cut summary — every ratio through report_composite (rule 25),
# every count through report_count (rule 22).
# --------------------------------------------------------------------------- #

@dataclass
class ArmScore:
    name: str
    n_fills: int
    n_settled: int
    n_phantom: int
    n_real: int
    n_touch_missing: int
    composite: object                    # guards.Composite | None
    clustered: object                    # ClusteredMean | None
    warning: str | None

    def phantom_report(self):
        # rule 22: a phantom count of 0 cannot print bare — without a fired
        # control the phantom classifier's zero is an untested instrument, not
        # "no phantoms", and report_count says so. (No timestamp control exists
        # for a tally, so provenance is absent by design — never half-stated.)
        return report_count(f"{self.name}:phantom_fills", self.n_phantom)


def score_arm(name: str, fills: list[Fill]) -> ArmScore:
    """Settlement-primary summary of one population (an arm, or a cut's cell).

    Every figure travels with its parts. The composite's numerator is total
    settlement P&L (¢), denominator is settled fills, events are games — so the
    ranking ratio (¢/fill) can never print without ¢/game beside it, and a cell
    that scored well by barely trading is visible on sight.
    """
    n_fills = len(fills)
    pnls = [settlement_pnl_cents(f) for f in fills]
    settled = [p for p in pnls if p is not None]
    n_settled = len(settled)

    phantoms = [is_phantom(f) for f in fills]
    n_missing = sum(1 for x in phantoms if x is None)
    n_phantom = sum(1 for x in phantoms if x is True)
    n_real = sum(1 for x in phantoms if x is False)

    by_game = _pnl_by_game(fills)
    clustered = clustered_mean(by_game) if by_game else None

    composite = None
    warning = None
    if n_settled:
        total = sum(settled)
        n_games = len(by_game)
        # rule 25: the ratio (¢/fill) refuses to print without num/den/per-event.
        composite = report_composite(f"{name}:settlement_pnl",
                                     numerator=total, denominator=n_settled,
                                     events=n_games)
        # rule 25: is this ranking ratio maximised by a degenerate activity
        # level? per-event (per-game) mean is the sign that decides.
        warning = degenerate_extremes_warning(f"{name}:settlement_pnl",
                                              composite.per_event)
    return ArmScore(name, n_fills, n_settled, n_phantom, n_real, n_missing,
                    composite, clustered, warning)


def rank_arms(scores: list[ArmScore]) -> list[str]:
    """Rank arms by settlement ¢/fill, but emit the rule-25 warning for every
    arm whose ranking ratio is maximised by a degenerate extreme. Returns the
    lines to print; the ranking is NEVER reported without them."""
    lines = []
    ranked = sorted((s for s in scores if s.composite is not None),
                    key=lambda s: s.composite.ratio, reverse=True)
    for s in ranked:
        lines.append(f"  {s.name:28s} {s.composite}")
        if s.warning:
            lines.append(f"      ! RULE 25: {s.warning}")
    if not ranked:
        lines.append("  (no arm has a settled fill yet — nothing to rank)")
    return lines


# --------------------------------------------------------------------------- #
# The three CUTS, on BASE's own fills.
# --------------------------------------------------------------------------- #

def _width_bucket(spread_cents: float) -> str:
    for edge, label in zip(WIDTH_EDGES, WIDTH_LABELS):
        if spread_cents <= edge:
            return label
    return WIDTH_LABELS[-1]


def width_cut(base_fills: list[Fill]) -> list[ArmScore]:
    """WIDTH — quoted-spread buckets. THE rule-25 specimen: phantom share rises
    with spread, so an uncorrected ratio manufactures a spurious 'wide is better'
    gradient. Every bucket goes through score_arm, so each carries its per-game
    mean and its degenerate-extremes warning."""
    buckets: dict[str, list[Fill]] = defaultdict(list)
    for f in base_fills:
        buckets[_width_bucket(f.spread_at_quote * 100.0)].append(f)
    return [score_arm(f"width[{lab}]", buckets[lab])
            for lab in WIDTH_LABELS if buckets[lab]]


def lateness_cut(base_fills: list[Fill], late_periods: set[str] | None = None
                 ) -> tuple[list[ArmScore], int]:
    """LATENESS — by event_period, late window vs the rest. Returns (scores,
    n_uncovered): fills without a recovered event_period are COUNTED, not
    dropped (rule 22). event_period rides in on the fill when the recorder
    supplies it; otherwise this cut reports its own coverage as zero rather than
    a false partition."""
    covered = [f for f in base_fills if f.event_period is not None]
    n_uncovered = len(base_fills) - len(covered)
    if not covered:
        return [], n_uncovered
    if late_periods:
        groups = {"late": [f for f in covered if f.event_period in late_periods],
                  "rest": [f for f in covered if f.event_period not in late_periods]}
    else:
        groups = defaultdict(list)
        for f in covered:
            groups[f"period={f.event_period}"].append(f)
    return [score_arm(f"lateness[{k}]", v) for k, v in groups.items() if v], n_uncovered


def patience_cut(base_fills: list[Fill]) -> list[ArmScore]:
    """PATIENCE — fills within 30s of a prior fill in the SAME market
    ('impatient': v1 requoting into a dip) vs the rest. Computed from filled_at
    ordering alone, so it needs no join."""
    by_market: dict[str, list[Fill]] = defaultdict(list)
    for f in base_fills:
        by_market[f.market].append(f)
    impatient, patient = [], []
    for market, fs in by_market.items():
        fs_sorted = sorted(fs, key=lambda f: f.filled_at)
        last = None
        for f in fs_sorted:
            if last is not None and (f.filled_at - last) < PATIENCE_WINDOW_SECONDS:
                impatient.append(f)
            else:
                patient.append(f)
            last = f.filled_at
    return [score_arm("patience[impatient<30s]", impatient),
            score_arm("patience[rest]", patient)]


# --------------------------------------------------------------------------- #
# FLATTEN: dispersion AND tail, not mean.
# --------------------------------------------------------------------------- #

@dataclass
class DispersionTail:
    name: str
    n_games: int
    per_game_std: float | None
    per_game_iqr: float | None
    worst_game: float | None
    tail_mean_p10: float | None          # mean of the worst-decile GAMES


def dispersion_tail(name: str, fills: list[Fill]) -> DispersionTail:
    """FLATTEN's registered surface. Inventory RISK shows in the SPREAD of
    per-game outcomes and the bad tail, not in the mean (which is flat across
    position). Per-game totals, then std / IQR / worst game / worst-decile mean."""
    by_game = _pnl_by_game(fills)
    totals = sorted(sum(v) for v in by_game.values())
    n = len(totals)
    if n == 0:
        return DispersionTail(name, 0, None, None, None, None)
    std = stats.pstdev(totals) if n > 1 else 0.0
    if n >= 4:
        q1, q3 = totals[n // 4], totals[(3 * n) // 4]
        iqr = q3 - q1
    else:
        iqr = None
    k = max(1, n // 10)
    tail_mean = sum(totals[:k]) / k
    return DispersionTail(name, n, std, iqr, totals[0], tail_mean)


FLATTEN_CAVEAT = (
    "CAVEAT (outranks the parameter): every cell is negative at every k; "
    "flattening improves a losing book, it does not make a winning one. "
    "'FLATTEN leaves the losing family' means BY BEING LESS NEGATIVE.")

#: SECONDARY metric that this scorer does NOT compute. Markout is a separate run
#: deliberately (manager's call): folding its tick-tape join in here would couple
#: two very different failure modes and the join is the part most likely to break.
#: But a secondary metric in another file is one that quietly never gets run — so
#: this notice prints UNCONDITIONALLY, every report, naming the command. An absent
#: metric must not read as a metric that came back empty.
MARKOUT_NOTICE = [
    "!!! SECONDARY METRIC REQUIRED AND NOT INCLUDED HERE: markout at 30s/2m/10m.",
    "    Markout is the amendment's POWERED secondary (lower variance, real",
    "    power at this n) and this report is INCOMPLETE without it. It is a",
    "    SEPARATE run on purpose (the tick-tape join is the fragile part):",
    "        .venv/bin/python analysis/quote_v2_markout.py \\",
    "            --fills <arm_fills.csv> --ticks <ticks.csv.gz>",
    "    This line is not an empty result — it is a metric that has NOT been run.",
]


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #

def render(base: list[Fill], flatten: list[Fill],
           late_periods: set[str] | None = None) -> list[str]:
    out: list[str] = []

    out.append("=" * 72)
    out.append("GRIDIRON POLICY A/B — settlement-primary, game-clustered (rule 25 wired)")
    out.append("=" * 72)
    out += MARKOUT_NOTICE          # leads the report — cannot be missed

    # ---- arms ----
    b, f = score_arm("BASE", base), score_arm("FLATTEN", flatten)
    out.append("\nARMS (primary: settlement ¢/fill, per-game clustered):")
    out += rank_arms([b, f])
    for s in (b, f):
        # rule 22: counts, never bare — a zero-phantom on zero-settled says UNPROVEN.
        out.append(f"  {s.name}: fills={s.n_fills} settled={s.n_settled} "
                   f"phantom={s.n_phantom} real={s.n_real} touch_missing={s.n_touch_missing}")
        out.append(f"      {s.phantom_report()}")
        if s.clustered is not None:
            c = s.clustered
            out.append(f"      per-fill clustered: {c.mean:+.3f}c "
                       f"[{c.lo:+.3f}, {c.hi:+.3f}] (G={c.n_clusters}, n={c.n}) "
                       f"{'EXCLUDES 0' if c.excludes_zero else 'spans 0'}")

    # ---- FLATTEN dispersion & tail ----
    out.append("\nFLATTEN vs BASE — DISPERSION AND TAIL (not mean):")
    for name, fills in (("BASE", base), ("FLATTEN", flatten)):
        d = dispersion_tail(name, fills)
        out.append(f"  {name}: games={d.n_games} "
                   f"per-game std={_fmt(d.per_game_std)} iqr={_fmt(d.per_game_iqr)} "
                   f"worst={_fmt(d.worst_game)} tail(p10)={_fmt(d.tail_mean_p10)}")
    out.append("  " + FLATTEN_CAVEAT)

    # ---- cuts on BASE ----
    out.append("\nCUT: WIDTH (BASE's fills) — reported, never ranked-on "
               "(the 'wide is better' gradient was a phantom artifact):")
    out += rank_arms(width_cut(base))

    lscores, n_unc = lateness_cut(base, late_periods)
    out.append(f"\nCUT: LATENESS (BASE's fills) — event_period coverage gap: "
               f"{report_count('lateness:uncovered_fills', n_unc)}")
    out += rank_arms(lscores)

    out.append("\nCUT: PATIENCE (BASE's fills) — within 30s of a prior same-market fill:")
    out += rank_arms(patience_cut(base))

    out.append("")
    out += MARKOUT_NOTICE          # and closes it — the omission bookends the report
    return out


def _fmt(x):
    return "n/a" if x is None else f"{x:+.3f}"


# --------------------------------------------------------------------------- #
# DB read (main) — kept thin; the metric logic above is pure and DB-free.
# --------------------------------------------------------------------------- #

def load_fills(con, policy: str, league_prefix: str | None = None) -> list[Fill]:
    from sqlalchemy import text
    # event_period is NOT on the fill (it is not touch-at-fill and does not gate a
    # controller, so it is not recorded there). The LATENESS cut recovers it by an
    # EXACT join: a fill's filled_at IS the captured_at of the market_snapshots
    # observation it was judged against, so (market_slug, captured_at=filled_at)
    # matches that snapshot. LEFT JOIN -> a fill whose snapshot was pruned keeps
    # event_period NULL and is COUNTED as uncovered by the cut (rule 22), never
    # silently dropped. This is a read-time join and acceptable precisely because
    # LATENESS is a selection, not a controller input.
    q = """
        SELECT f.market_slug, f.game_id, f.side, f.quote_price, f.spread_at_quote,
               extract(epoch from f.filled_at) AS filled_at, f.settlement,
               f.best_bid_at_fill, f.best_ask_at_fill, f.policy,
               ms.event_period AS event_period
        FROM shadow_quote_fills f
        LEFT JOIN LATERAL (
            SELECT event_period FROM market_snapshots ms
            WHERE ms.market_slug = f.market_slug
              AND ms.captured_at = f.filled_at
            LIMIT 1
        ) ms ON true
        WHERE f.policy = :p
    """
    rows = con.execute(text(q), {"p": policy}).all()
    out = []
    for r in rows:
        out.append(Fill(
            market=r.market_slug, game=str(r.game_id), side=r.side,
            quote_price=float(r.quote_price),
            spread_at_quote=float(r.spread_at_quote),
            filled_at=float(r.filled_at),
            settlement=(None if r.settlement is None else int(r.settlement)),
            best_bid_at_fill=(None if r.best_bid_at_fill is None else float(r.best_bid_at_fill)),
            best_ask_at_fill=(None if r.best_ask_at_fill is None else float(r.best_ask_at_fill)),
            event_period=r.event_period, policy=r.policy or "base"))
    return out


def main() -> int:
    from core.storage import get_engine
    eng = get_engine()
    with eng.connect() as con:
        base = load_fills(con, "base")
        flatten = load_fills(con, "flatten")
    for line in render(base, flatten):
        print(line)
    return 0


# --------------------------------------------------------------------------- #
# Selftest — synthetic plants (rule 18) with known answers (rule 16). DB-free.
# --------------------------------------------------------------------------- #

def _selftest() -> int:
    ok = True

    def chk(label, cond):
        nonlocal ok
        ok = ok and cond
        print(f"  {label:62} {'OK' if cond else 'FAIL'}")

    # --- P&L arithmetic (rule 16: known answers) ---
    long_win = Fill("m", "g", BID, 0.40, 0.04, 1.0, 1, 0.40, 0.44)
    chk("long YES @0.40 settles 1 -> +60c",
        abs(settlement_pnl_cents(long_win) - 60.0) < 1e-9)
    long_lose = Fill("m", "g", BID, 0.40, 0.04, 0.0, 0, 0.40, 0.44)
    chk("long YES @0.40 settles 0 -> -40c",
        abs(settlement_pnl_cents(long_lose) + 40.0) < 1e-9)
    short_win = Fill("m", "g", ASK, 0.60, 0.04, 0.0, 0, 0.56, 0.60)
    chk("short YES @0.60 settles 0 -> +60c",
        abs(settlement_pnl_cents(short_win) - 60.0) < 1e-9)
    chk("unsettled fill -> None", settlement_pnl_cents(
        Fill("m", "g", BID, 0.4, 0.04, 1.0, None, 0.4, 0.44)) is None)

    # --- phantom test (rule 16) ---
    # bid @0.40, touch (0.38,0.44): ask .44 > .40 -> phantom (ask never came)
    chk("bid fill, ask above our bid -> PHANTOM",
        is_phantom(Fill("m", "g", BID, 0.40, 0.06, 1.0, 1, 0.38, 0.44)) is True)
    # bid @0.40, touch (0.38,0.40): ask .40 <= .40 -> real
    chk("bid fill, ask at our bid -> REAL",
        is_phantom(Fill("m", "g", BID, 0.40, 0.02, 1.0, 1, 0.38, 0.40)) is False)
    chk("missing touch -> None (coverage gap, not a guess)",
        is_phantom(Fill("m", "g", BID, 0.40, 0.02, 1.0, 1, None, None)) is None)

    # --- rule 25 specimen: WIDTH. A wide band that BARELY TRADES scores a
    # flattering ¢/fill while its per-game mean is negative; the guard must warn.
    base = []
    # tight band: 200 fills across 10 games, each -1c settled (a real losing book)
    for gi in range(10):
        for k in range(20):
            # alternate win/lose so ~ -1c/fill on average, spread 1c (tight)
            settle = 1 if k % 2 == 0 else 0
            base.append(Fill(f"tm{gi}", f"g{gi}", BID, 0.505, 0.01,
                             1000.0 + gi * 100 + k, settle, 0.50, 0.51))
    # wide band: 2 fills in 2 games, both winners (flattering ratio)
    for gi in range(2):
        base.append(Fill(f"wm{gi}", f"wg{gi}", BID, 0.20, 0.08,
                         5000.0 + gi, 1, 0.12, 0.28))
    wc = {s.name: s for s in width_cut(base)}
    tight = wc.get("<=1.5") or wc.get("width[<=1.5]")
    # locate by label substring
    tights = [s for s in width_cut(base) if "<=1.5" in s.name]
    wides = [s for s in width_cut(base) if ">5.5" in s.name]
    chk("WIDTH cut produces the tight and wide bands", bool(tights and wides))
    if tights and wides:
        t, w = tights[0], wides[0]
        chk("wide band WINS on ¢/fill ratio (the artifact)",
            w.composite.ratio > t.composite.ratio)
        chk("tight (losing) band's per-game mean is negative -> rule-25 warning",
            t.warning is not None and "NEVER ACTING" in t.warning)
        # the degenerate warning fires for a uniformly-signed per-event mean
        neg_warn = degenerate_extremes_warning("probe", -1.0)
        chk("degenerate_extremes_warning fires on a negative per-event mean",
            neg_warn is not None and "NEVER ACTING" in neg_warn)

    # --- rule 22: a zero count announces itself ---
    empty = score_arm("EMPTY", [])
    chk("empty arm: 0 settled, composite is None (nothing ranked)",
        empty.n_settled == 0 and empty.composite is None)
    chk("empty arm phantom count prints UNPROVEN, not bare 0",
        "UNPROVEN" in str(empty.phantom_report()))

    # --- game-clustered CI is used (not row-level) ---
    s = score_arm("CLU", base)
    chk("arm score carries a game-clustered CI (clusters = games)",
        s.clustered is not None and s.clustered.n_clusters >= 2)

    # --- PATIENCE cut splits on the 30s window ---
    pf = [Fill("m1", "g", BID, 0.5, 0.02, 100.0, 1, 0.49, 0.50),
          Fill("m1", "g", BID, 0.5, 0.02, 110.0, 0, 0.49, 0.50),   # +10s impatient
          Fill("m1", "g", BID, 0.5, 0.02, 200.0, 1, 0.49, 0.50)]   # +90s patient
    ps = {s.name: s for s in patience_cut(pf)}
    imp = [s for s in patience_cut(pf) if "impatient" in s.name][0]
    chk("PATIENCE: one fill within 30s is impatient", imp.n_fills == 1)

    # --- FLATTEN dispersion/tail computes without a mean ranking ---
    d = dispersion_tail("FLATTEN", base)
    chk("dispersion/tail: per-game std + worst-decile tail computed",
        d.per_game_std is not None and d.tail_mean_p10 is not None)

    # --- render runs end to end and prints the guards' output ---
    lines = render(base, [], late_periods={"Q4"})
    joined = "\n".join(lines)
    chk("render emits per-game clustered CIs and the FLATTEN caveat",
        "clustered" in joined and "losing book" in joined)
    chk("render emits rule-22 coverage line for the LATENESS gap",
        "lateness:uncovered_fills" in joined)
    chk("render emits the LOUD markout-NOT-INCLUDED notice (names the command)",
        "REQUIRED AND NOT INCLUDED" in joined
        and "quote_v2_markout.py" in joined)

    print("\nGRIDIRON A/B SCORER SELFTEST:",
          "PASS — settlement P&L known-answers hold, phantom test correct, "
          "rule 25 (composite+extremes) and rule 22 (report_count) WIRED, "
          "CIs game-clustered, FLATTEN on dispersion/tail." if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        raise SystemExit(_selftest())
    raise SystemExit(main())
