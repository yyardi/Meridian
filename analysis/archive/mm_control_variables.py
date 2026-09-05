"""The unstudied market-maker control variables — inventory skew, placement,
toxicity — measured on the v1 fills tape. (Quant D, 2026-09-02.)

    .venv/bin/python analysis/mm_control_variables.py --selftest
    .venv/bin/python analysis/mm_control_variables.py
        --fills FILLS.csv --ticks TICKS.csv.gz [--out DIR]

v1 fixed all four MM control variables (placement, size, skew,
participation); the registered arms study participation and a corner of
placement. These three reads cover the rest, on data we already own, inside
the lever wave's DESIGN-NOT-EVIDENCE framing: they shape which arms
GRIDIRON prioritises and what magnitude to expect. The forward gates stay
the only evidence.

M1 — MARKOUT CONDITIONAL ON INVENTORY AT FILL (the skew question).
Per market, v1's position path is the signed cumulative sum of its own
fills (bid +1, ask −1, unit size; the quote engine has no exit — positions
ride to settlement, so inventory ACCUMULATES over a market's life). Each
fill is classified by the inventory it was taken INTO:
    flat        inv_before == 0
    adding      sign(fill) == sign(inv_before)   (exposure grows)
    reducing    sign(fill) != sign(inv_before)   (exposure shrinks)
plus |inv_before| as a magnitude ladder. Hypothesis under test: fills taken
while already long are systematically worse — one-sided flow arrives in
bursts and v1's symmetric requote kept standing in front of it. That is
Avellaneda–Stoikov's inventory penalty (q·γ·σ²·(T−t)) tested rather than
assumed. A FLAT result is equally valuable: it says the loss is pure
per-fill adverse selection with no inventory dimension, skew is dead here,
and PATIENCE's measured effect is standalone rather than skew wearing a
time costume.

M2 — THE PLACEMENT CURVE (fill rate × capture, by spread width).
THE DENOMINATOR PROBLEM, STATED: fill RATE needs quotes PLACED, and the
quote stream was never persisted (shadow_quote_fills is the only quote
table). v1's rule is deterministic — both sides requoted to the touch every
5s cycle whenever a two-sided book existed (engine.py:6-7, :68), verified
100% at-touch on 17,032 births in the M4 read — so the denominator is
DERIVED: 5s buckets in which the market had a two-sided live tick, from the
tick pin, banded by that bucket's own spread. Rate = fills / cycles (each
cycle places TWO quotes, one per side — stated, not divided away).
The economic quantity is CAPTURE PER CYCLE QUOTED (rate × capture/fill),
not capture per fill: a band that fills rarely but richly and a band that
fills constantly but thinly are only comparable per unit of time quoted.
Markets outside the tick pin have no denominator and are excluded, counted.

M3 — TOXICITY PROXY: SAME-SIDE FILL RUNS.
Consecutive fills on the same side within a short window per market
(RUN_GAP_S), cut by run length. If long runs mark out much worse, that is
order-flow toxicity in its crudest measurable form — the mechanism behind
both M1 and PATIENCE — and it says whether a RUN-LENGTH trigger would beat
a fixed time-based hold-off.

All reads: in-game, league=WNBA (export rule 37e5f0d, re-asserted here),
game-clustered, BOTH fill arms (optimistic modelled capture and the
measured-concession floor, labelled, never mixed), rule-16 gated on the
fills tape before anything is scored.

**No in-sample result justifies capital. The forward test is the evidence.**
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.quote.adverse_selection import clustered_mean  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "quote_v2_markout", Path(__file__).with_name("quote_v2_markout.py"))
qvm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(qvm)

CYCLE_S = 5.0                    # v1's requote cadence (engine.py:68)
QUOTES_PER_CYCLE = 2             # both sides, every cycle
RUN_GAP_S = 30.0                 # fills this close continue a run
MEASURED_CONCESSION = 0.0470     # static-study, per filled quote
SPREAD_BANDS = [(0.0, 0.02, "<=2c"), (0.02, 0.05, "2-5c"),
                (0.05, 0.10, "5-10c"), (0.10, 1.01, ">10c")]
LEAGUE = "wnba"


def hr(t: str) -> None:
    print(f"\n{'=' * 78}\n{t}\n{'=' * 78}")


def cm_str(vals: dict[str, list[float]], unit: str = "c") -> str:
    c = clustered_mean(vals)
    if c is None:
        return "n/a"
    return (f"{c.mean * 100:+.2f} [{c.lo * 100:+.2f}, {c.hi * 100:+.2f}]{unit}"
            f" (n={c.n}, G={c.n_clusters})")


def by_game(df: pd.DataFrame, col: str) -> dict[str, list[float]]:
    sub = df[df[col].notna()]
    return {g: list(v) for g, v in sub.groupby("game_id")[col]}


def band_of(spread: float) -> str:
    for lo, hi, name in SPREAD_BANDS:
        if lo <= spread < hi:
            return name
    return ">10c"


# --------------------------------------------------------------------------- #
# M1 — inventory
# --------------------------------------------------------------------------- #

def add_inventory(fills: pd.DataFrame) -> pd.DataFrame:
    """Signed position path per market. bid = +1 (long YES), ask = −1.

    inv_before is the position carried INTO each fill; the class describes
    what the fill did to exposure. Unit size throughout (v1 quoted one
    contract per side), so the path is a cumulative count, not a notional.
    """
    f = fills.sort_values(["market_slug", "filled_at"]).copy()
    f["signed"] = np.where(f.side == "bid", 1.0, -1.0)
    f["inv_before"] = (f.groupby("market_slug")["signed"]
                       .cumsum() - f["signed"])

    def klass(row) -> str:
        if row.inv_before == 0:
            return "flat"
        return ("adding" if np.sign(row.signed) == np.sign(row.inv_before)
                else "reducing")

    f["inv_class"] = [klass(r) for r in f.itertuples()]
    f["inv_abs"] = f.inv_before.abs()
    f["inv_mag"] = pd.cut(f.inv_abs, [-0.1, 0.1, 1.1, 3.1, 1e9],
                          labels=["0", "1", "2-3", "4+"])
    return f


def m0_inventory_path(con, fills: pd.DataFrame) -> None:
    """Does the Avellaneda-Stoikov inventory penalty APPLY to v1 at all?

    RECONSTRUCTABILITY, stated first (c7's condition): the quote engine has
    NO EXIT MECHANISM — it rests a bid and an offer each cycle and holds
    whatever fills to settlement (core/quote/engine.py; ShadowQuoteFill
    carries settlement, never an exit). So the position path is the signed
    cumsum of a market's own fills and NOTHING ELSE: no exit rows to match,
    no orphan-exit problem, no re-linked rows, no cap-semantics eras — those
    are PULSE-ledger artifacts and none of them touch this tape. Flattening
    happens only two ways: the opposite side of our own two-sided quote gets
    hit, or the market settles. This is cleanly reconstructable, which is
    why the answer below can be trusted at face value.

    Time weighting: each fill starts a segment that ends at the next fill in
    that market, and the LAST segment ends at the market's last two-sided
    live tick in the pin (its observable end). Markets with no tick coverage
    contribute to the fill-instant distribution but not the time-weighted
    one — counted, not stitched."""
    hr("M0. THE INVENTORY PATH — is the A-S inventory penalty operative "
       "here at all? (gates the skew arm's priority)")
    print("reconstruction: signed cumsum of each market's own fills; the "
          "quote engine has NO exits (positions ride to settlement), so "
          "there is nothing to match and nothing unreconstructable — the "
          "PULSE ledger's orphan/re-link/cap-era problems do not exist on "
          "this tape.\n")

    f = fills.copy()
    f["inv_after"] = f.inv_before + f.signed

    # --- distribution of |q| at every fill instant -----------------------
    at_fill = f.inv_before.abs()
    print(f"|q| carried INTO each fill (n={len(f)}): mean {at_fill.mean():.2f}"
          f", p50 {at_fill.median():.0f}, p90 {at_fill.quantile(.9):.0f}, "
          f"max {at_fill.max():.0f}")
    dist = at_fill.value_counts(normalize=True).sort_index()
    shown = {int(k): f"{v:.1%}" for k, v in list(dist.items())[:6]}
    print(f"  distribution: {shown}"
          + (" ..." if len(dist) > 6 else ""))
    print(f"  share of fills taken at |q| >= 2: "
          f"{(at_fill >= 2).mean():.1%}  (|q| >= 4: "
          f"{(at_fill >= 4).mean():.1%})")

    # --- time-weighted |q| and time at nonzero ---------------------------
    ends = con.execute("""
        SELECT market_slug, max(captured_at) AS t_end FROM tk
        GROUP BY 1
    """).df().set_index("market_slug").t_end
    segs = []
    for m, g in f.sort_values("filled_at").groupby("market_slug"):
        t_end = ends.get(m)
        if pd.isna(t_end):
            continue
        times = list(g.filled_at) + [pd.Timestamp(t_end).tz_convert("UTC")]
        held = list(g.inv_after)
        for i, q in enumerate(held):
            dt_s = (times[i + 1] - times[i]).total_seconds()
            if dt_s > 0:
                segs.append((m, g.game_id.iloc[0], abs(q), dt_s))
    if not segs:
        print("\nno tick-covered markets — time weighting unavailable")
    else:
        sd = pd.DataFrame(segs, columns=["market_slug", "game_id", "absq",
                                         "seconds"])
        tw = (sd.absq * sd.seconds).sum() / sd.seconds.sum()
        nonzero = sd[sd.absq > 0].seconds.sum() / sd.seconds.sum()
        ge2 = sd[sd.absq >= 2].seconds.sum() / sd.seconds.sum()
        print(f"\nTIME-WEIGHTED |q| = {tw:.2f} over "
              f"{sd.seconds.sum() / 3600:.1f} market-hours "
              f"({sd.market_slug.nunique()} tick-covered markets)")
        print(f"  share of quoted TIME at q != 0: {nonzero:.1%}; "
              f"at |q| >= 2: {ge2:.1%}")
        holds = sd[sd.absq > 0].seconds
        if len(holds):
            print(f"  holding duration while q != 0: p50 "
                  f"{holds.median():.0f}s, p90 {holds.quantile(.9):.0f}s, "
                  f"max {holds.max() / 60:.1f}min")

    # --- the late cut -----------------------------------------------------
    if "period" in f.columns:
        late = f[~f.period.isin(["Q1", "Q2", "HT"])]
        early = f[f.period.isin(["Q1", "Q2", "HT"])]
        for name, sub in (("late (Q3/Q4/OT)", late), ("early (Q1/Q2/HT)",
                                                      early)):
            if len(sub) == 0:
                continue
            a = sub.inv_before.abs()
            print(f"\n{name}: n={len(sub)}, |q| mean {a.mean():.2f}, "
                  f"p90 {a.quantile(.9):.0f}, share |q|>=2 {(a >= 2).mean():.1%}")

    print("\nTHE RULING THIS SUPPORTS: if v1 sat at |q| in {0,1} with short "
          "holds, the A-S inventory penalty was never operative — skew "
          "would fix a risk we do not carry, and placement/participation "
          "stay the live levers. If v1 carried real inventory, "
          "concentrated late, A-S earns its priority. The numbers above "
          "answer it; the ranking is c7's.")


def m1_inventory(fills: pd.DataFrame) -> None:
    hr("M1. MARKOUT x INVENTORY AT FILL — is there a skew dimension? "
       "(A-S inventory penalty, tested not assumed)")
    print("position path = signed cumsum of a market's OWN fills (bid +1, "
          "ask −1, unit size); the quote engine has no exit, so inventory "
          "accumulates to settlement. inv_before = position carried INTO "
          "the fill.\n")
    print(f"{'class':10s} {'n':>7s} {'G':>3s}  {'capture (opt)':>28s} "
          f"{'pess':>8s}  {'markout +2m':>28s}")
    for k in ("flat", "adding", "reducing"):
        sub = fills[fills.inv_class == k]
        if len(sub) == 0:
            continue
        pess = sub.half_spread.mean() - MEASURED_CONCESSION
        print(f"{k:10s} {len(sub):>7d} {sub.game_id.nunique():>3d}  "
              f"{cm_str(by_game(sub, 'capture')):>28s} "
              f"{pess * 100:>+7.2f}c  "
              f"{cm_str(by_game(sub, 'markout_2m')):>28s}")

    print("\nby |inventory| carried in (the magnitude ladder):")
    for mag, sub in fills.groupby("inv_mag", observed=True):
        if len(sub) == 0:
            continue
        print(f"  |inv|={str(mag):4s}: n={len(sub):>6d} "
              f"capture {cm_str(by_game(sub, 'capture')):>26s}  "
              f"markout+2m {cm_str(by_game(sub, 'markout_2m'))}")

    # The directional form of the hypothesis: fills taken while ALREADY LONG
    # vs already SHORT, so a one-sided-flow story is separable from a
    # generic "big inventory is bad" story.
    print("\ndirectional (sign of inventory carried in):")
    for name, mask in (("already long  (inv>0)", fills.inv_before > 0),
                       ("already short (inv<0)", fills.inv_before < 0),
                       ("flat          (inv=0)", fills.inv_before == 0)):
        sub = fills[mask]
        if len(sub) == 0:
            continue
        print(f"  {name}: n={len(sub):>6d} "
              f"capture {cm_str(by_game(sub, 'capture')):>26s}  "
              f"markout+2m {cm_str(by_game(sub, 'markout_2m'))}")

    print("\nthe paired form (adding − flat, per game — the cleanest read of "
          "the skew claim, game-clustered on differences):")
    for col in ("capture", "markout_2m"):
        diffs = {}
        for g, gs in fills.groupby("game_id"):
            a = gs.loc[gs.inv_class == "adding", col].dropna()
            fl = gs.loc[gs.inv_class == "flat", col].dropna()
            if len(a) and len(fl):
                diffs[g] = [a.mean() - fl.mean()]
        print(f"  {col:11s}: {cm_str(diffs)}")
    print("\nreading: a materially worse 'adding' row (and a paired diff "
          "whose CI excludes zero) says inventory ORDERS outcomes and skew "
          "is a real lever — and that PATIENCE may be partly crediting "
          "skew's effect. Flat rows say the loss is pure per-fill adverse "
          "selection, skew is dead here, and PATIENCE stands alone.")


# --------------------------------------------------------------------------- #
# M2 — placement curve
# --------------------------------------------------------------------------- #

def cycle_denominator(con, markets: list[str]) -> pd.DataFrame:
    """5s buckets with a two-sided live book, per market x spread band.

    DERIVED, not recorded: v1 quoted both sides to the touch every 5s cycle
    whenever a two-sided book existed. Each bucket = one cycle = two quotes
    placed. The bucket's spread is its LAST two-sided tick's spread (the
    quote the cycle would have joined)."""
    df = con.execute("""
        WITH b AS (
          SELECT market_slug,
                 time_bucket(INTERVAL '5 seconds', captured_at) AS bucket,
                 arg_max(spread, captured_at) AS spread
          FROM tk
          GROUP BY 1, 2
        )
        SELECT market_slug, bucket, spread FROM b
    """).df()
    df["band"] = df.spread.map(band_of)
    return df


def m2_placement(con, fills: pd.DataFrame) -> None:
    hr("M2. THE PLACEMENT CURVE — fill rate x capture by spread width "
       "(denominator DERIVED from the deterministic 5s cycle; the quote "
       "stream was never persisted)")
    cyc = cycle_denominator(con, sorted(fills.market_slug.unique()))
    if len(cyc) == 0:
        print("no tick coverage — no denominator; nothing to report")
        return
    covered = set(cyc.market_slug)
    inpin = fills[fills.market_slug.isin(covered)]
    print(f"markets with tick coverage: {len(covered)}; fills inside the "
          f"pin: {len(inpin)}/{len(fills)} "
          f"({len(fills) - len(inpin)} excluded, counted — the known "
          f"4-of-13-game pin gap)")

    fills2 = inpin.copy()
    fills2["band"] = fills2.spread_at_quote.map(band_of)
    cyc_n = cyc.groupby("band").size()
    print(f"\n{'band':7s} {'cycles':>9s} {'fills':>7s} {'fills/cycle':>12s} "
          f"{'capture/fill':>26s} {'capture/cycle':>14s} {'pess/cycle':>11s}")
    for _, _, band in SPREAD_BANDS:
        n_cyc = int(cyc_n.get(band, 0))
        sub = fills2[fills2.band == band]
        if n_cyc == 0 and len(sub) == 0:
            continue
        rate = len(sub) / n_cyc if n_cyc else np.nan
        capf = sub.capture.mean() if len(sub) else np.nan
        pessf = (sub.half_spread.mean() - MEASURED_CONCESSION
                 if len(sub) else np.nan)
        print(f"{band:7s} {n_cyc:>9d} {len(sub):>7d} {rate:>12.4f} "
              f"{cm_str(by_game(sub, 'capture')):>26s} "
              f"{rate * capf * 100:>+13.3f}c {rate * pessf * 100:>+10.3f}c")
    print(f"\n(each cycle places {QUOTES_PER_CYCLE} quotes — one per side — "
          f"so fills/cycle is per two-sided placement, not per quote. "
          f"CAPTURE PER CYCLE is the comparable quantity: a band that fills "
          f"rarely and richly vs one that fills constantly and thinly are "
          f"only comparable per unit of time quoted.)")
    print("SHAPE is the transferable output, not the level: WNBA's ~4c "
          "in-play books left nowhere to stand but the touch. NFL quarter "
          "totals quote ~30c wide, where joining the touch may never fill "
          "and stepping inside makes the market — the question GRIDIRON's "
          "placement arm inherits is whether capture/fill falls FASTER than "
          "fill-rate rises as you cross bands.")


# --------------------------------------------------------------------------- #
# M3 — toxicity: same-side runs
# --------------------------------------------------------------------------- #

def add_runs(fills: pd.DataFrame) -> pd.DataFrame:
    """Run index: consecutive same-side fills within RUN_GAP_S, per market."""
    f = fills.sort_values(["market_slug", "filled_at"]).copy()
    gap = f.groupby("market_slug").filled_at.diff().dt.total_seconds()
    same = f.side.eq(f.groupby("market_slug").side.shift())
    cont = same & (gap <= RUN_GAP_S)
    f["run_id"] = (~cont.fillna(False)).cumsum()
    f["run_pos"] = f.groupby("run_id").cumcount() + 1
    lengths = f.groupby("run_id").size().rename("run_len")
    f = f.join(lengths, on="run_id")
    f["run_band"] = pd.cut(f.run_len, [0, 1, 2, 4, 1e9],
                           labels=["1 (isolated)", "2", "3-4", "5+"])
    return f


def m3_runs(fills: pd.DataFrame) -> None:
    hr(f"M3. TOXICITY PROXY — same-side fill runs (consecutive same-side "
       f"fills within {RUN_GAP_S:.0f}s, per market)")
    print(f"{'run length':14s} {'fills':>7s} {'runs':>6s} "
          f"{'capture':>28s} {'markout +2m':>28s}")
    for band, sub in fills.groupby("run_band", observed=True):
        if len(sub) == 0:
            continue
        print(f"{str(band):14s} {len(sub):>7d} {sub.run_id.nunique():>6d} "
              f"{cm_str(by_game(sub, 'capture')):>28s} "
              f"{cm_str(by_game(sub, 'markout_2m')):>28s}")
    print("\nby position WITHIN the run (is it the run, or just the tail?):")
    for pos in (1, 2, 3):
        sub = fills[fills.run_pos == pos]
        if len(sub) == 0:
            continue
        print(f"  fill #{pos} of its run: n={len(sub):>6d} "
              f"capture {cm_str(by_game(sub, 'capture')):>26s}  "
              f"markout+2m {cm_str(by_game(sub, 'markout_2m'))}")
    deep = fills[fills.run_pos >= 4]
    if len(deep):
        print(f"  fill #4+ of its run:  n={len(deep):>6d} "
              f"capture {cm_str(by_game(deep, 'capture')):>26s}  "
              f"markout+2m {cm_str(by_game(deep, 'markout_2m'))}")
    print("\nreading: if markout degrades with run length AND with position "
          "inside the run, the flow is toxic in bursts and a RUN-LENGTH "
          "trigger (stand down after k same-side fills) is the natural "
          "hold-off — testable against PATIENCE's fixed time-based form. "
          "If only long runs are bad but position within them is flat, the "
          "run length is a state marker, not a live trigger.")

    # c7's second question: SIGNED PERSISTENCE — repeatedly hit on one side
    # while the price trends away. This is the sequence-level adverse
    # selection that skew fixes even in a world of informed flow, i.e. the
    # case for skew that does NOT depend on the A-S penalty being operative.
    hr("M3b. SIGNED PERSISTENCE — was v1 repeatedly hit on one side while "
       "the price trended away? (the skew case that survives even if the "
       "A-S inventory penalty is inoperative)")
    rows = []
    for rid, g in fills[fills.run_len >= 2].groupby("run_id"):
        g = g.sort_values("filled_at")
        first, last = g.iloc[0], g.iloc[-1]
        # mid travel across the run, signed AGAINST the side being hit:
        # a bid run with the mid falling is adverse (we kept buying into a
        # fall); positive = the market moved against the whole run.
        adverse = qvm.signed(first.side, first.mid_at_fill, last.mid_at_fill)
        rows.append(dict(game_id=first.game_id, run_len=len(g),
                         side=first.side, adverse_travel=adverse,
                         span_s=(last.filled_at
                                 - first.filled_at).total_seconds(),
                         end_markout=last.markout_2m))
    if not rows:
        print("no multi-fill runs — nothing to report")
        return
    rr = pd.DataFrame(rows)
    print(f"multi-fill same-side runs: {len(rr)} across "
          f"{rr.game_id.nunique()} games; span p50 {rr.span_s.median():.0f}s")
    print(f"  MID TRAVEL AGAINST the run (>0 = the market kept moving away "
          f"through the whole run): "
          f"{cm_str({g: list(v) for g, v in rr.groupby('game_id').adverse_travel})}")
    print(f"  share of runs where the market moved against us end-to-end: "
          f"{(rr.adverse_travel > 0).mean():.1%}")
    for band, sub in rr.groupby(pd.cut(rr.run_len, [1, 2, 4, 1e9],
                                       labels=["2", "3-4", "5+"]),
                                observed=True):
        if len(sub) == 0:
            continue
        print(f"  run length {str(band):4s}: n={len(sub):>5d} adverse travel "
              f"{cm_str({g: list(v) for g, v in sub.groupby('game_id').adverse_travel})}")
    print("\nreading: persistent adverse travel through same-side runs is "
          "sequence-level adverse selection — the thing a skew rule fixes "
          "directly (lean the quote away after being hit) regardless of "
          "whether we ever CARRY enough inventory for the A-S penalty to "
          "bind. Travel near zero says the runs are just clustering, and "
          "the skew case rests entirely on M0's inventory answer.")


# --------------------------------------------------------------------------- #
# Mutation tests
# --------------------------------------------------------------------------- #

def m4_terminal_dispersion(fills: pd.DataFrame) -> None:
    """c7's ruling 2: A-S's inventory penalty is a RISK-AVERSION term about
    the dispersion of TERMINAL wealth. M1 measured the MEAN of per-fill
    capture by |q| and found it flat — which is fully consistent with
    "inventory doesn't move the average and fattens the tail." This tests
    AS on its own object: per-MARKET settlement P&L, cut by the peak |q|
    that market carried.

    Per contract: a bid long at p returns S − p; an ask short at p returns
    p − S (unit size, maker both ways, theta_maker = 0). Per market = the
    sum over its fills. Markets with any unsettled fill are EXCLUDED and
    counted — a partial book has no terminal wealth."""
    hr("M4. TERMINAL DISPERSION BY INVENTORY — testing A-S on its own "
       "object (mean was flat; the penalty is about the TAIL)")
    f = fills.copy()
    f["pnl"] = np.where(f.side == "bid", f.settlement - f.quote_price,
                        f.quote_price - f.settlement)
    unsettled = f.groupby("market_slug").settlement.apply(
        lambda s: s.isna().any())
    drop = set(unsettled[unsettled].index)
    print(f"markets excluded for any unsettled fill: {len(drop)} of "
          f"{f.market_slug.nunique()} (counted, not stitched)")
    f = f[~f.market_slug.isin(drop)]
    if f.empty:
        print("no fully-settled markets — nothing to report")
        return

    per = f.groupby("market_slug").agg(
        pnl=("pnl", "sum"), fills=("pnl", "size"),
        game_id=("game_id", "first"),
        peak_absq=("inv_abs", "max"))
    per["peak_band"] = pd.cut(per.peak_absq, [-0.1, 1.1, 3.1, 9.1, 1e9],
                              labels=["<=1", "2-3", "4-9", "10+"])
    print(f"\nfully-settled markets: {len(per)} across "
          f"{per.game_id.nunique()} games; total P&L "
          f"${per.pnl.sum():+,.2f} (unit size)")
    print(f"\n{'peak |q|':9s} {'mkts':>5s} {'mean':>8s} {'SD':>8s} "
          f"{'worst':>9s} {'p10':>8s} {'p90':>8s} {'sum':>10s}")
    for band, sub in per.groupby("peak_band", observed=True):
        if len(sub) == 0:
            continue
        print(f"{str(band):9s} {len(sub):>5d} {sub.pnl.mean():>+8.2f} "
              f"{sub.pnl.std():>8.2f} {sub.pnl.min():>+9.2f} "
              f"{sub.pnl.quantile(.1):>+8.2f} {sub.pnl.quantile(.9):>+8.2f} "
              f"{sub.pnl.sum():>+10.2f}")
    print("\nthe five largest single-market losses, with the peak |q| each "
          "carried (the ruin question in its rawest form):")
    for r in per.nsmallest(5, "pnl").itertuples():
        print(f"  {r.Index[:52]:52s} ${r.pnl:+8.2f} on {r.fills:>4d} fills, "
              f"peak |q| {r.peak_absq:.0f}")
    worst_decile = per.nsmallest(max(1, len(per) // 10), "pnl")
    print(f"\nworst decile: mean peak |q| {worst_decile.peak_absq.mean():.1f} "
          f"vs {per.peak_absq.mean():.1f} overall — the NON-CIRCULAR form "
          f"of the tail claim (an association with an ex-ante observable).")
    print("NOT REPORTED, deliberately: 'the worst decile carries more than "
          "the net total, so the rest is profitable.' That decile is "
          "selected ON THE DEPENDENT VARIABLE and the statement is close to "
          "a tautology for any right-skewed loss distribution — it would "
          "read as 'remove the tail and we have a business', which the "
          "bucket means above refute: NO peak-|q| bucket has a positive "
          "mean. The book is not profitable-except-for-a-tail; it is "
          "flat-to-negative everywhere WITH a catastrophic tail "
          "concentrated in high inventory. Only the second claim is "
          "supported, and only the prospective cap (M6) can test it.")


def m7_concurrent_exposure(con, fills: pd.DataFrame) -> None:
    """A per-market cap does not bound the BOOK (c7's gap, measured rather
    than flagged). Ruin comes from TOTAL exposure across CONCURRENT
    markets: K per market x N simultaneous markets is the number that
    touches a $1,000 wallet, and N was never measured — the 147/209 market
    counts elsewhere in this file are CUMULATIVE, not concurrent.

    Method: every fill is an event changing one market's q; every market
    also ends (its last two-sided live tick — same convention as M0, so a
    position stops counting when the market stops being observable rather
    than riding forever). Walking that event stream globally gives, at each
    instant, total |q| across all open markets and how many markets are
    non-flat. Time weighting is by the interval each state was held.

    The dollar reading is exact because of the bounded-loss property: total
    |q| contracts can lose at most $1 each, so PEAK TOTAL |q| IS THE
    ARITHMETIC WORST CASE FOR THE WHOLE BOOK in dollars."""
    hr("M7. CONCURRENT BOOK EXPOSURE — what a $1,000 wallet actually faces "
       "(a per-market cap bounds a market, not the book)")
    f = fills.sort_values("filled_at").copy()
    f["sgn"] = np.where(f.side == "bid", 1.0, -1.0)
    ends = con.execute("SELECT market_slug, max(captured_at) t_end "
                       "FROM tk GROUP BY 1").df().set_index(
                           "market_slug").t_end
    events: list[tuple] = []
    for m, g in f.groupby("market_slug"):
        q = 0.0
        for t, s in zip(g.filled_at, g.sgn):
            q += s
            events.append((t, m, q))
        t_end = ends.get(m)
        if pd.notna(t_end):
            te = pd.Timestamp(t_end)
            te = te.tz_convert("UTC") if te.tzinfo else te.tz_localize("UTC")
            events.append((te, m, 0.0))
    if not events:
        print("no events")
        return
    events.sort(key=lambda e: e[0])
    live: dict[str, float] = {}
    peak_abs = peak_n = 0.0
    wsum = wn = wt = 0.0
    prev_t = events[0][0]
    peak_at = None
    for t, m, q in events:
        dt_s = (t - prev_t).total_seconds()
        if dt_s > 0:
            tot = sum(abs(v) for v in live.values())
            n = sum(1 for v in live.values() if v != 0)
            wsum += tot * dt_s
            wn += n * dt_s
            wt += dt_s
        live[m] = q
        tot = sum(abs(v) for v in live.values())
        n = sum(1 for v in live.values() if v != 0)
        if tot > peak_abs:
            peak_abs, peak_at = tot, t
        peak_n = max(peak_n, n)
        prev_t = t
    print(f"observed span {wt / 3600:.1f} hours across "
          f"{f.market_slug.nunique()} markets / {f.game_id.nunique()} games")
    print(f"  PEAK total |q| across all open markets: {peak_abs:.0f} "
          f"contracts (at {peak_at})")
    print(f"  peak concurrent NON-FLAT markets: {peak_n:.0f}")
    print(f"  time-weighted total |q|: {wsum / wt:.1f} contracts; "
          f"time-weighted non-flat markets: {wn / wt:.1f}")
    print(f"\nTHE ARITHMETIC WALLET NUMBER: at most $1 of loss per contract, "
          f"so this book's PEAK worst case was ~${peak_abs:.0f} and its "
          f"time-weighted worst case ~${wsum / wt:.0f} — against a $1,000 "
          f"wallet, at UNIT size.")
    print("  scaling is the operator's decision and the arithmetic is "
          "linear: at size S per fill the peak worst case is "
          f"~${peak_abs:.0f} x S. A wallet that must survive its own worst "
          "observed night sets S from that, not from a per-market K.")
    print("\nHOW CONSERVATIVE THAT BOUND IS, stated so it is usable: it "
          "assumes EVERY open contract settles against us at once. Real "
          "books hold both directions across uncorrelated games, so the "
          "realised figure is far smaller — this tape's entire cumulative "
          "settled P&L over 13 games was about −$133 against a peak bound "
          "of ~$702. The bound is the RUIN object (what cannot be exceeded) "
          "and the realised distribution is the P&L object; a wallet sizes "
          "on the first and forecasts on the second.")
    print("\nCAVEATS: (1) unit size — v1 quoted one contract; (2) the span "
          "is the tick pin's, so the 4 games outside it are absent and this "
          "is a LOWER bound on true concurrency; (3) markets stop counting "
          "at their last observable tick, so genuinely-held-to-settlement "
          "exposure past the pin is not counted; (4) WNBA slates are small "
          "— an NFL Sunday lists far more concurrent games, so this number "
          "does not transfer and must be re-measured on the NFL board "
          "before it sizes anything.")


def m6_inventory_cap(fills: pd.DataFrame) -> None:
    """PROSPECTIVE inventory cap — the run that decides whether the tail
    finding means anything (c7's item 3, highest-value remaining).

    A hard cap refuses any fill that would take |q| beyond K, walking each
    market's fills IN TIME ORDER so the refusal changes the path exactly as
    it would live. The whole book is then re-scored on the ACCEPTED fills
    only — the foregone fills included by their absence, which is where
    hindsight caps usually die: 110 of 209 markets reach peak |q| >= 10, so
    a cap at 10 also refuses the money the non-worst of those markets
    earned.

    Prior from our own record, stated before the numbers: B's loss-cap
    surface found no surviving cell, and the ride work's durable heuristic
    is that on this venue wins and tails COHABIT the same states because
    risk is priced through the contract price. A cap that survives here
    would be the program's biggest result; a cap that dies teaches the same
    lesson in a new place and narrows skew's justification to the
    flattening form alone."""
    hr("M6. PROSPECTIVE INVENTORY CAP — does refusing high-|q| fills "
       "actually help, once the foregone fills are counted?")
    f = fills[fills.settlement.notna()].copy()
    f["pnl"] = np.where(f.side == "bid", f.settlement - f.quote_price,
                        f.quote_price - f.settlement)
    f["sgn"] = np.where(f.side == "bid", 1.0, -1.0)
    f = f.sort_values(["market_slug", "filled_at"])

    def run_cap(K: float) -> pd.DataFrame:
        keep = []
        for _, g in f.groupby("market_slug", sort=False):
            q = 0.0
            for idx, s in zip(g.index, g.sgn):
                if abs(q + s) > K:
                    continue            # the quote is not there; no fill
                q += s
                keep.append(idx)
        return f.loc[keep]

    base_per = f.groupby("market_slug").pnl.sum()
    print(f"{'cap K':>7s} {'fills kept':>11s} {'refused':>9s} "
          f"{'total P&L':>11s} {'delta':>9s} {'per-mkt SD':>11s} "
          f"{'worst mkt':>10s}")
    print(f"{'none':>7s} {len(f):>11d} {0:>9d} {f.pnl.sum():>+11.2f} "
          f"{0.0:>+9.2f} {base_per.std():>11.2f} {base_per.min():>+10.2f}")
    for K in (3, 5, 10, 20):
        kept = run_cap(K)
        per_k = kept.groupby("market_slug").pnl.sum()
        # markets that vanish entirely score 0, not NaN — the cap's own
        # consequence, counted
        per_k = per_k.reindex(base_per.index).fillna(0.0)
        print(f"{K:>7d} {len(kept):>11d} {len(f) - len(kept):>9d} "
              f"{kept.pnl.sum():>+11.2f} "
              f"{kept.pnl.sum() - f.pnl.sum():>+9.2f} "
              f"{per_k.std():>11.2f} {per_k.min():>+10.2f}")
    # Is the improvement MECHANISM or SAMPLE LUCK? A total delta can come
    # from one game. Per-game deltas, game-clustered, are what separate
    # "capping avoids adding to losers" from "capping happened to skip the
    # markets that lost in these 13 games".
    print("\nper-GAME delta (capped − uncapped), game-clustered — the check "
          "that separates mechanism from sample luck:")
    base_g = f.groupby("game_id").pnl.sum()
    for K in (3, 5, 10, 20):
        kept = run_cap(K)
        gd = (kept.groupby("game_id").pnl.sum()
              .reindex(base_g.index).fillna(0.0) - base_g)
        c = clustered_mean({g: [v] for g, v in gd.items()})
        n_pos = int((gd > 0).sum())
        print(f"  K={K:<3d}: {n_pos}/{len(gd)} games improved; per-game "
              f"delta {c.mean:+.2f} [{c.lo:+.2f}, {c.hi:+.2f}] $ (G="
              f"{c.n_clusters})" if c else f"  K={K}: n/a")

    print("\nreading: the cap earns its place only if TOTAL P&L improves — "
          "SD falling alone is not a win, because refusing fills trivially "
          "shrinks variance toward zero (a book that never trades has none). "
          "The honest pairing is delta-P&L WITH per-market SD: variance "
          "bought at an acceptable price in mean is the ruin-control case; "
          "variance bought by giving up the book is not.")
    # POWER: a bare "not supported" invites re-litigation every month. The
    # useful form is "not supported, here is the n that would settle it,
    # and here is the league where that n exists."
    print("\npower of this null (why the interval is wide, and what would "
          "close it):")
    for K in (5, 10):
        kept = run_cap(K)
        gd = (kept.groupby("game_id").pnl.sum()
              .reindex(base_g.index).fillna(0.0) - base_g)
        sd_g, mean_g = gd.std(ddof=1), gd.mean()
        se = sd_g / np.sqrt(len(gd))
        # two-sided alpha 0.05, power 0.80 -> (1.96 + 0.8416)^2 = 7.849
        n_need = (7.849 * sd_g ** 2 / mean_g ** 2) if mean_g else np.inf
        print(f"  K={K:<3d}: per-game delta {mean_g:+.2f}, SD {sd_g:.2f}, "
              f"SE {se:.2f} on G={len(gd)} -> resolving an effect this size "
              f"at 80% power needs ~{n_need:.0f} GAMES")
    print("  what that means operationally, and it is WORSE than a "
          "one-season wait: an NFL regular season is ~272 games (+13 "
          "playoff), so ~295 at K=10 is MORE THAN A FULL SEASON and ~835 "
          "at K=5 is roughly three. This effect is not resolvable on any "
          "calendar that precedes the decisions it would inform — on WNBA "
          "it is unreachable outright. CONSEQUENCE: the cap's P&L question "
          "cannot be settled empirically in time, which is precisely why "
          "the risk-limit justification below is not a fallback but the "
          "ONLY available route. Nobody should re-litigate the P&L form on "
          "any n we will have.")

    print("\n=== DISPOSITION, three parts (c7's ruling; a risk limit and a "
          "P&L lever are different objects and must not share a verdict) "
          "===")
    print("(a) CAP AS P&L LEVER — DEAD. Clustered null above, power stated. "
          "It is not expected to make money and the evidence does not say "
          "it does.")
    print("(b) CAP AS RISK LIMIT — LIVE, and justified ARITHMETICALLY, not "
          "statistically. 'Worst market -18.85 -> -4.28 at K=3' is a "
          "GUARANTEE ABOUT THE SHAPE OF THE LOSS DISTRIBUTION, not an "
          "estimate, and needs no CI; applying a significance test to a "
          "bound is a category error (mine, corrected). Every desk runs "
          "position limits that are not expected to earn — they exist to "
          "make the worst case computable rather than hoped-for. Its "
          "expected P&L COST is unmeasured, and the clustered CI above is "
          "the honest bound ON THAT COST.")
    print("(c) FLATTENING — the live P&L lever (M5), rates as upper "
          "bounds. Convert the position; do not refuse the fill.")
    print("\nWHY THE BOUND ROUTE IS STRONGER HERE THAN ANYWHERE ELSE (c7; a "
          "structural property of this venue our record had never stated): "
          "ON A BINARY MARKET THE PER-CONTRACT LOSS IS BOUNDED. A long at p "
          "loses at most p; a short at p loses at most (1−p); either way at "
          "most $1 per contract at settlement. So a per-market cap of K "
          "bounds that market's loss at ~$K ARITHMETICALLY — not in "
          "expectation, not within a CI. In equities a position limit is a "
          "heuristic against unbounded loss; here it is a hard guarantee. "
          "That is why the risk-limit route works precisely where the "
          "statistics cannot reach.")

    print("\nAND THE CLUSTERED VERDICT GOVERNS: a total delta is a sum over "
          "a handful of games. If the per-game row above shows a coin-flip "
          "improvement count and a CI spanning zero, the cap is NOT "
          "supported at the standard every other number in this program is "
          "held to — whatever the total says. That is the same failure mode "
          "as the worst-decile framing this file refuses to print: a "
          "headline carried by a few observations. Report the total and the "
          "clustered row TOGETHER or neither.")


def m5_flattening_lean(con, fills: pd.DataFrame) -> None:
    """c7's ruling 4, run first: were round trips AVAILABLE and refused?

    v1 never leans to get flat. After a BID fill its standing ask stayed at
    the touch (mid_at_quote + spread_at_quote/2 — both sides are born in
    the same cycle, so the fills tape recovers the ask exactly). The
    counterfactual: rest the offer k cents INSIDE that ask and ask whether
    the engine's OWN fill rule (a newer observation's mid >= the offer)
    would have crossed it within N seconds.

    Cycle-resolution scan, deliberately: the engine fill-checks once per 5s
    cycle against the newest observation, so scanning every 200ms tick
    would flatter the counterfactual. Buckets are 5s and use the bucket's
    last mid — exactly what a cycle would have seen.

    Round-trip capture if flattened = lean_price − quote_price (maker both
    sides, theta_maker = 0), against the actual outcome of that contract,
    which was to ride to settlement."""
    hr("M5. THE FLATTENING LEAN — were round trips available and refused? "
       "(c7 ruling 4; cycle-resolution so the counterfactual can't flatter)")
    f = fills[fills.settlement.notna()].copy()
    if f.empty:
        print("no settled fills — nothing to report")
        return
    # the standing quote's OTHER side at the moment of this fill
    f["ask_at_quote"] = f.mid_at_quote + f.spread_at_quote / 2
    f["bid_at_quote"] = f.mid_at_quote - f.spread_at_quote / 2
    f["ride_pnl"] = np.where(f.side == "bid", f.settlement - f.quote_price,
                             f.quote_price - f.settlement)

    con.register("lean_fills", f[["market_slug", "filled_at", "side",
                                  "quote_price", "ask_at_quote",
                                  "bid_at_quote"]].reset_index(names="fid"))
    for horizon in (30, 120):
        print(f"\n--- flatten within {horizon}s "
              f"(5s cycle resolution) ---")
        print(f"{'lean':>6s} {'side':>4s} {'n':>7s} {'flattened':>10s} "
              f"{'round-trip if flat':>22s} {'actual ride P&L':>22s}")
        for k in (0.01, 0.02, 0.03, 0.05):
            got = con.execute(f"""
                WITH b AS (
                  SELECT market_slug,
                         time_bucket(INTERVAL '5 seconds', captured_at) bk,
                         arg_max(mid, captured_at) AS mid
                  FROM tk GROUP BY 1, 2
                )
                SELECT l.fid,
                       max(CASE
                         WHEN l.side = 'bid' AND b.mid >= l.ask_at_quote - {k}
                           THEN 1
                         WHEN l.side = 'ask' AND b.mid <= l.bid_at_quote + {k}
                           THEN 1 ELSE 0 END) AS flattened
                FROM lean_fills l JOIN b
                  ON b.market_slug = l.market_slug
                 AND b.bk > l.filled_at
                 AND b.bk <= l.filled_at + INTERVAL '{horizon} seconds'
                GROUP BY l.fid
            """).df().set_index("fid").flattened
            sub = f.copy()
            sub["flat"] = sub.index.map(got).fillna(0).astype(bool)
            for side in ("bid", "ask"):
                ss = sub[sub.side == side]
                if len(ss) == 0:
                    continue
                fl = ss[ss.flat]
                if side == "bid":
                    rt = (fl.ask_at_quote - k) - fl.quote_price
                else:
                    rt = fl.quote_price - (fl.bid_at_quote + k)
                rt_by_g = {g: list(v) for g, v in rt.groupby(fl.game_id)}
                ride_by_g = {g: list(v) for g, v
                             in fl.ride_pnl.groupby(fl.game_id)}
                print(f"{k * 100:>5.0f}c {side:>4s} {len(ss):>7d} "
                      f"<={ss.flat.mean():>8.1%} "
                      f"{cm_str(rt_by_g):>22s} {cm_str(ride_by_g):>22s}")
    print("\nRATES ARE UPPER BOUNDS ('<='), c7's trace of the optimism one "
          "step further than my own caveat: the mid-cross rule fills on "
          "excursions a real resting order often would not get — the same "
          "artifact that books ~1.5c/leg and then reverts — so it inflates "
          "the flatten RATE as well as the price. Apples-to-apples against "
          "the engine's own fills (which inherit the identical rule); "
          "optimistic the moment it is projected onto real forward fills.")
    print("\nreading: a high flatten rate with a round-trip capture better "
          "than the ride says round trips WERE available and the no-exit "
          "architecture — not adverse selection — is the primary cap on "
          "this book's earnings. A low rate says the offsetting flow simply "
          "was not there, and one-sided accumulation was structural rather "
          "than chosen. Both columns are on the same fills, so they are "
          "directly comparable; the ride column is real settled money and "
          "the round-trip column is a counterfactual under the engine's own "
          "fill rule.")


def _f(mkt, side, t, game="g1", q=0.40, mq=0.42, sp=0.04, mf=0.39, s=1):
    return dict(market_slug=mkt, game_id=game, regime="ingame", side=side,
                quote_price=q, mid_at_quote=mq, spread_at_quote=sp,
                mid_at_fill=mf, quoted_at=pd.Timestamp(t),
                filled_at=pd.Timestamp(t) + pd.Timedelta(seconds=1),
                settlement=s)


def selftest() -> int:
    print("mutation test: the three control-variable instruments")
    failures = 0

    def check(name, ok):
        nonlocal failures
        print(f"  {name} -> {'ok' if ok else 'FAIL'}")
        failures += 0 if ok else 1

    base = "2026-08-20 01:00:00+00:00"
    T = lambda s: pd.Timestamp(base) + pd.Timedelta(seconds=s)

    # M1: known path bid,bid,ask,ask on one market ->
    # inv_before 0,+1,+2,+1 ; classes flat,adding,reducing,reducing
    seq = pd.DataFrame([
        _f("m1", "bid", T(0)), _f("m1", "bid", T(10)),
        _f("m1", "ask", T(20)), _f("m1", "ask", T(30))])
    inv = add_inventory(seq)
    check("inventory path 0,+1,+2,+1",
          list(inv.inv_before) == [0.0, 1.0, 2.0, 1.0])
    check("inventory classes flat/adding/reducing/reducing",
          list(inv.inv_class) == ["flat", "adding", "reducing", "reducing"])

    # inventory is PER MARKET — a second market restarts at flat
    two = pd.DataFrame([_f("m1", "bid", T(0)), _f("m2", "bid", T(5))])
    check("inventory is per-market (m2 starts flat)",
          list(add_inventory(two).inv_before) == [0.0, 0.0])

    # M3: runs — 3 same-side inside the gap, then a side flip, then a
    # same-side fill outside the gap (new run)
    runs = add_runs(pd.DataFrame([
        _f("m1", "bid", T(0)), _f("m1", "bid", T(10)), _f("m1", "bid", T(20)),
        _f("m1", "ask", T(25)),
        _f("m1", "ask", T(300))]))
    check("run lengths 3,3,3,1,1", list(runs.run_len) == [3, 3, 3, 1, 1])
    check("run positions 1,2,3,1,1", list(runs.run_pos) == [1, 2, 3, 1, 1])

    # M2 denominator: 60s of 1s ticks -> 12 five-second buckets
    import duckdb
    con = duckdb.connect()
    con.execute("SET timezone='UTC'")
    ticks = pd.DataFrame([
        dict(market_slug="m1", captured_at=T(i), spread=0.04, mid=0.40)
        for i in range(60)])
    ticks["event_period"] = "Q2"
    con.register("ticks_df", ticks)
    con.execute("CREATE TEMP TABLE tk AS SELECT * FROM ticks_df")
    cyc = cycle_denominator(con, ["m1"])
    check("cycle denominator: 60s of ticks -> 12 five-second buckets",
          len(cyc) == 12)
    check("buckets banded by their own spread (4c -> 2-5c)",
          set(cyc.band) == {"2-5c"})

    # band boundaries are half-open and exhaustive
    check("band boundaries", [band_of(x) for x in (0.01, 0.02, 0.05, 0.10,
                                                   0.50)]
          == ["<=2c", "2-5c", "5-10c", ">10c", ">10c"])

    # M0 time-weighting: a market that sits at |q|=1 for 30s then flat for
    # 30s must read time-weighted |q| = 0.5 and 50% of time at q != 0.
    import contextlib, io as _io
    tw_fills = add_inventory(pd.DataFrame([
        _f("m1", "bid", T(0)), _f("m1", "ask", T(30))]))
    tw_fills["markout_2m"] = np.nan
    tw_fills["half_spread"] = 0.02
    tw_fills["capture"] = -0.01
    buf = _io.StringIO()
    with contextlib.redirect_stdout(buf):
        m0_inventory_path(con, tw_fills)
    txt = buf.getvalue()
    # segments: |q|=1 from fill1 (T+1) to fill2 (T+31) = 30s, then |q|=0
    # from T+31 to the market's last tick (T+59) = 28s -> 30/58 = 0.517
    check("M0 time-weighting = 30s at |q|=1 of 58s observable (0.52)",
          "TIME-WEIGHTED |q| = 0.52" in txt and "at q != 0: 51.7%" in txt)

    # M5: a bid filled at 0.40 with the ask at 0.44 leans to 0.42 at k=2c.
    # Tape rises to mid 0.43 at +10s -> flattened (0.43 >= 0.42), round
    # trip = 0.42 − 0.40 = +2c. A tape that never reaches 0.42 must NOT
    # flatten (the counterfactual cannot invent liquidity).
    rise = pd.DataFrame([dict(market_slug="mR", captured_at=T(i),
                              spread=0.04, event_period="Q2",
                              mid=0.40 if i < 10 else 0.43)
                         for i in range(60)])
    flat_tape = rise.assign(mid=0.40, market_slug="mF")
    con.register("tick2", pd.concat([rise, flat_tape]))
    con.execute("DROP TABLE IF EXISTS tk")
    con.execute("CREATE TEMP TABLE tk AS SELECT * FROM tick2")
    lean_fills = pd.DataFrame([
        _f("mR", "bid", T(0), q=0.40, mq=0.42, sp=0.04),
        _f("mF", "bid", T(0), q=0.40, mq=0.42, sp=0.04)])
    lean_fills["capture"] = -0.01
    lean_fills["half_spread"] = 0.02
    buf3 = _io.StringIO()
    with contextlib.redirect_stdout(buf3):
        m5_flattening_lean(con, lean_fills)
    t3 = buf3.getvalue()
    check("M5 flattens the rising tape and not the flat one (50%)",
          "50.0%" in t3)
    # restore the earlier tk for the remaining checks
    con.execute("DROP TABLE IF EXISTS tk")
    con.execute("CREATE TEMP TABLE tk AS SELECT * FROM ticks_df")

    # M4: two markets, known settlement P&L and peak |q|
    m4 = add_inventory(pd.DataFrame([
        _f("mA", "bid", T(0), q=0.40, s=1), _f("mA", "bid", T(10), q=0.40, s=1),
        _f("mB", "ask", T(0), q=0.60, s=1)]))
    buf4 = _io.StringIO()
    with contextlib.redirect_stdout(buf4):
        m4_terminal_dispersion(m4)
    t4 = buf4.getvalue()
    # mA: two bids at .40 settling 1 -> +1.20 ; mB: ask .60 settling 1 -> -0.40
    check("M4 settlement P&L arithmetic (+1.20 / -0.40, peak |q| 1 vs 0)",
          "+0.80" in t4 and "-0.40" in t4)

    # M6: a cap at 1 on three same-side fills must keep exactly the first
    # (|q| would exceed 1 on the second), and its P&L must be that fill's
    # alone — the foregone fills counted by absence, not by hindsight.
    cap_f = add_inventory(pd.DataFrame([
        _f("mC", "bid", T(0), q=0.40, s=1),
        _f("mC", "bid", T(10), q=0.40, s=1),
        _f("mC", "bid", T(20), q=0.40, s=1)]))
    buf5 = _io.StringIO()
    with contextlib.redirect_stdout(buf5):
        m6_inventory_cap(cap_f)
    t5 = buf5.getvalue()
    # uncapped: 3 fills x (1 - 0.40) = +1.80 ; K=3 keeps all (|q| max 3)
    check("M6 uncapped total is +1.80 on 3 fills", "+1.80" in t5)
    # K=3 keeps 3, K=5/10/20 keep 3 too -> refused 0 in every printed row
    check("M6 cap K=3 keeps all three (|q| never exceeds 3)",
          t5.count("+1.80") >= 2)

    # M7: two markets each reaching |q|=1 at overlapping times must peak at
    # total 2, not 1 — the whole point of concurrency.
    conc = pd.DataFrame([_f("mX", "bid", T(0)), _f("mY", "bid", T(2))])
    con.execute("DROP TABLE IF EXISTS tk")
    con.execute("""CREATE TEMP TABLE tk AS
        SELECT 'mX' AS market_slug, ticks_df.captured_at, 0.4 AS mid,
               0.04 AS spread, 'Q2' AS event_period FROM ticks_df
        UNION ALL SELECT 'mY', ticks_df.captured_at, 0.4, 0.04, 'Q2'
        FROM ticks_df""")
    buf6 = _io.StringIO()
    with contextlib.redirect_stdout(buf6):
        m7_concurrent_exposure(con, conc)
    t6 = buf6.getvalue()
    check("M7 peaks at 2 concurrent contracts across 2 markets",
          "PEAK total |q| across all open markets: 2" in t6
          and "peak concurrent NON-FLAT markets: 2" in t6)
    con.execute("DROP TABLE IF EXISTS tk")
    con.execute("CREATE TEMP TABLE tk AS SELECT * FROM ticks_df")

    # M0 must not stitch: a market with no tick coverage contributes to the
    # fill-instant distribution but not the time-weighted one.
    nocov = add_inventory(pd.DataFrame([_f("mZZ", "bid", T(0))]))
    nocov["markout_2m"] = np.nan
    nocov["half_spread"] = 0.02
    nocov["capture"] = -0.01
    buf2 = _io.StringIO()
    with contextlib.redirect_stdout(buf2):
        m0_inventory_path(con, nocov)
    check("M0 excludes uncovered markets from time weighting (no stitching)",
          "time weighting unavailable" in buf2.getvalue())

    print(f"mutation test: "
          f"{'ALL OK' if failures == 0 else f'{failures} FAILURES'}")
    return failures


# --------------------------------------------------------------------------- #

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fills", type=Path)
    ap.add_argument("--ticks", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if args.fills is None or args.ticks is None:
        print("need --fills and --ticks; --selftest runs without data")
        return 2

    print("MM control variables — inventory / placement / toxicity")
    print("design-not-evidence: shapes GRIDIRON's arm priorities and "
          "expected magnitudes; the forward gates are the only evidence")
    if selftest() != 0:
        print("ABORT: mutation test failed")
        return 1

    fills = qvm.load_fills(args.fills)
    if not qvm.rule16_gate(fills, rehearsal=False):
        return 1

    ing = fills[fills.regime == "ingame"].copy()
    bad = ing[~ing.market_slug.str.contains(f"-{LEAGUE}-")]
    if len(bad):
        print(f"LOUD: {len(bad)} non-{LEAGUE} fills excluded (export pin "
              f"37e5f0d violated)")
        ing = ing[ing.market_slug.str.contains(f"-{LEAGUE}-")]

    ing["half_spread"] = [qvm.signed(r.side, r.mid_at_quote, r.quote_price)
                          for r in ing.itertuples()]
    import duckdb
    con = duckdb.connect()
    con.execute("SET timezone='UTC'")
    qvm.load_ticks(con, args.ticks, sorted(ing.market_slug.unique()))
    ing = qvm.markouts(con, ing)
    ing = add_inventory(ing)
    ing = add_runs(ing)

    # period at fill (for M0's late cut and any state read), from the tape
    con.register("fills_st", ing[["market_slug", "filled_at"]]
                 .reset_index(names="fid"))
    st = con.execute("""
        SELECT f.fid, t.event_period
        FROM fills_st f ASOF JOIN tk t
          ON f.market_slug = t.market_slug AND t.captured_at <= f.filled_at
    """).df().set_index("fid")
    ing["period"] = ing.index.map(st.event_period)

    m7_concurrent_exposure(con, ing)  # c7: the aggregate the wallet faces
    m6_inventory_cap(ing)             # c7 item 3: the deciding run
    m5_flattening_lean(con, ing)
    m4_terminal_dispersion(ing)
    m0_inventory_path(con, ing)
    m1_inventory(ing)
    m2_placement(con, ing)
    m3_runs(ing)

    hr("SYNTHESIS — one mechanism, seen from four ends")
    print("""
v1 IS NOT A MARKET MAKER; IT IS A PASSIVE POSITION ACCUMULATOR WITH
SLIGHTLY BETTER ENTRY PRICES THAN MID. It quotes two-sided, realises
one-sided flow, and has no mechanism to close — so the round trip that IS
market making almost never happens, "capture" is an intermediate valuation
of a position whose real P&L is settlement, and the −1.60c/fill is entry
adverse selection on a book that then rides to the buzzer.

Everything measured here is a consequence of that one architectural fact:

  M0/M1  it accumulates (time-weighted |q| 7.24, 94% of time non-flat) —
         and the accumulation does not order the per-fill MEAN.
  M4     but it orders the TAIL: per-market settlement SD 0.35 -> 6.45
         across the peak-|q| ladder, an ex-ante observable.
  M5     round trips were AVAILABLE (up to 27-42% at a 1c lean) and
         refused, at a round-trip capture of +1.44c against rides of
         -15.09c with CIs an order of magnitude wider.
  M7     and the un-closed positions aggregate: peak 702 contracts across
         91 concurrent markets = a ~$702 arithmetic worst case against a
         $1,000 wallet AT UNIT SIZE.

THE ONE MISSING CAPABILITY ANSWERS ALL THREE PROBLEMS. Flattening —
converting the position rather than refusing the fill — now carries three
independent arguments:
  1. ECONOMIC: it turns high-variance rides into tight positive scalps.
  2. RISK: it shrinks the inventory that orders the tail.
  3. CAPITAL EFFICIENCY: closing lowers peak concurrent exposure, which
     frees wallet capacity, which permits size, which multiplies earnings
     per fill. At unit size the book already ran ~70% wallet utilisation;
     exposure is linear in size, so size 2 exceeds the wallet outright.
     "How big should we quote" is now an ARITHMETIC question, not an
     open one.

AND THE TWO NUMBERS MUST NOT BE CONFLATED: a wallet SIZES on the bound
(~$702, what cannot be exceeded) and FORECASTS on the realised
distribution (~-$133 cumulative over 13 games). A reader who merges them
will either panic or dismiss; both are printed, both are labelled.

What did NOT survive, stated with equal prominence: the inventory CAP as a
P&L lever (clustered null, and no calendar can resolve it), and any reading
of the tail decomposition that implies "remove the tail and we have a
business" — no peak-|q| bucket has a positive mean.
""")

    hr("STANDING STATEMENTS")
    print("In-sample on the v1 WNBA fills pin, under the quote engine's own "
          "fill model (optimism cuts the known way: it undercounts exactly "
          "the fills that hurt). Both arms printed, never mixed. The M2 "
          "denominator is DERIVED from a deterministic rule, not recorded — "
          "its assumption is stated at the module head and inherits M4's "
          "100%-at-touch verification.")
    print("Multiple comparisons: three instruments x several cuts each; "
          "rank by mechanism plausibility and effect size, never p-value.")
    print("\nNo in-sample result justifies capital. The forward test is the "
          "evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
