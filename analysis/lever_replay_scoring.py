"""LEVER REPLAY scoring — which composition flips v1's −1.60¢, on the tape
we own. (Quant D; A's policy-variant harness emits the fills tapes.)

    .venv/bin/python analysis/lever_replay_scoring.py --selftest
    .venv/bin/python analysis/lever_replay_scoring.py
        --baseline FILLS.csv --ticks TICKS.csv.gz
        --variants lever_replay_*.csv [--out DIR]

DESIGN-NOT-EVIDENCE (c7's framing, printed with every table): this shapes
which arms GRIDIRON prioritizes Sept 9 and the magnitudes to expect; the
forward gates stay the only evidence. Everything here is an in-sample
replay on the August WNBA pin.

CONSUMPTION CONTRACT with A's harness (agreed interface):
- one CSV per variant, shadow_quote_fills columns exactly (market_slug,
  game_id, regime, side, quote_price, mid_at_quote, spread_at_quote,
  mid_at_fill, quoted_at, filled_at, settlement), variant name = filename
  stem after 'lever_replay_';
- the baseline tape is the ALL-LEVERS-OFF emission, and RULE 16 applies to
  it: it must reproduce the ledgered −1.60¢ [−1.69, −1.50] on 17,032
  in-game fills (quote_v2_markout.rule16_gate, the one authority) before
  any variant is scored. A harness whose levers-off tape does not
  reproduce the ledger is broken, not interesting.
- league=WNBA is pinned AT THE EXPORT (checklist rule, 37e5f0d); this
  scorer re-asserts it (slug prefix) and counts violations loudly —
  belt to the export's suspenders.

THREE BASES per variant, labelled, never mixed (the standing lesson):
- OPTIMISTIC (modelled): capture at fill exactly as recorded by the replay
  fill model — net_capture_mark. Losses trustworthy, gains upper bounds.
- MEASURED-CONCESSION: same fills, the modelled move-against replaced by
  the measured 4.70¢/fill static-study concession:
  pess = half_spread_earned − 4.70¢. The honest floor for maker fills.
- SETTLEMENT: report.score_fill ROI on settled fills (money at price).
Markout horizons (+30s/+2m/+10m) and mark-to-market ride along from
quote_v2_markout.markouts() — one markout core, imported.

SUPPRESSION COST is first-class: a lever that wins by not trading says so —
fills forgone vs baseline, forgone share, and the per-game distribution of
suppression. The lever × capture table is the deliverable.

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
from core.quote.report import score_fill  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "quote_v2_markout", Path(__file__).with_name("quote_v2_markout.py"))
qvm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(qvm)

MEASURED_CONCESSION_C = 4.70          # static-study, per filled quote
LEAGUE_PREFIX = "wnba"                # event slugs must carry it


def hr(t: str) -> None:
    print(f"\n{'=' * 78}\n{t}\n{'=' * 78}")


def cm(vals: dict[str, list[float]]):
    return clustered_mean(vals)


def cm_str(vals: dict[str, list[float]]) -> str:
    c = clustered_mean(vals)
    if c is None:
        return "n/a"
    return (f"{c.mean * 100:+.2f} [{c.lo * 100:+.2f}, {c.hi * 100:+.2f}]c "
            f"(G={c.n_clusters})")


def league_check(fills: pd.DataFrame, name: str) -> None:
    bad = fills[~fills.market_slug.str.contains(f"-{LEAGUE_PREFIX}-")]
    if len(bad):
        print(f"  LOUD [{name}]: {len(bad)} fills are not {LEAGUE_PREFIX} "
              f"(export pin violated — e.g. {bad.market_slug.iloc[0]}); "
              f"they are EXCLUDED and this needs the export fixed")


def enrich(fills: pd.DataFrame) -> pd.DataFrame:
    f = fills.copy()
    if "capture" not in f.columns:
        from core.quote.report import net_capture_mark
        f["capture"] = [net_capture_mark(side=r.side,
                                         quote_price=float(r.quote_price),
                                         mid_at_fill=float(r.mid_at_fill))
                        for r in f.itertuples()]
    f["half_spread"] = [qvm.signed(r.side, r.mid_at_quote, r.quote_price)
                        for r in f.itertuples()]
    f["pess_capture"] = f.half_spread - MEASURED_CONCESSION_C / 100.0
    rois = []
    for r in f.itertuples():
        if pd.isna(r.settlement):
            rois.append(np.nan)
            continue
        cost, ret = score_fill(side=r.side, quote_price=float(r.quote_price),
                               settlement=int(r.settlement))
        rois.append(ret / cost - 1.0 if cost > 0 else np.nan)
    f["roi"] = rois
    return f


def score_variant(con, name: str, fills: pd.DataFrame,
                  baseline: pd.DataFrame) -> dict:
    ing = fills[fills.regime == "ingame"].copy()
    league_check(ing, name)
    ing = ing[ing.market_slug.str.contains(f"-{LEAGUE_PREFIX}-")]
    ing = enrich(ing)
    ing = qvm.markouts(con, ing)

    base_n = len(baseline[baseline.regime == "ingame"])
    forgone = base_n - len(ing)
    by_g = lambda col: {g: list(v) for g, v in ing.groupby("game_id")[col]}
    mtm = (ing.capture + ing.markout_10m)
    out = dict(
        variant=name,
        n_fills=len(ing),
        forgone=forgone,
        forgone_share=forgone / base_n if base_n else np.nan,
        games=ing.game_id.nunique(),
        capture_opt=cm(by_g("capture")),
        capture_pess=cm(by_g("pess_capture")),
        mtm_10m=cm({g: list(v) for g, v in mtm.groupby(ing.game_id)}),
        roi_settle=cm({g: list(v.dropna())
                       for g, v in ing.groupby("game_id").roi}),
        markout_cov=int(ing.markout_10m.notna().sum()),
    )
    return out


def render_table(rows: list[dict]) -> None:
    hr("THE LEVER x CAPTURE TABLE (design-not-evidence: shapes GRIDIRON's "
       "Sept-9 arm priorities and expected magnitudes; forward gates are "
       "the only evidence)")
    print(f"{'variant':28s} {'fills':>7s} {'forgone':>8s} "
          f"{'capture opt (clustered)':>26s} {'pess (hs-4.70c)':>16s} "
          f"{'mtm +10m':>10s} {'ROI settle':>11s}")
    for r in rows:
        co, cp, mm, ro = (r["capture_opt"], r["capture_pess"],
                          r["mtm_10m"], r["roi_settle"])
        fco = (f"{co.mean * 100:+.2f} [{co.lo * 100:+.2f},{co.hi * 100:+.2f}]"
               if co else "n/a")
        fcp = f"{cp.mean * 100:+.2f}" if cp else "n/a"
        fmm = f"{mm.mean * 100:+.2f}" if mm else "n/a"
        fro = f"{ro.mean * 100:+.1f}%" if ro else "n/a"
        flip = (" <- FLIPS SIGN (optimistic basis; CI excludes 0)"
                if co and co.lo > 0 else "")
        print(f"{r['variant']:28s} {r['n_fills']:>7d} "
              f"{r['forgone']:>5d} ({r['forgone_share']:>5.1%}) "
              f"{fco:>26s} {fcp:>16s} {fmm:>10s} {fro:>11s}{flip}")
    print("\nreading rules: a positive optimistic capture with a deeply "
          "negative pessimistic column is a fill-model artifact until the "
          "forward gate says otherwise; a variant whose win is mostly "
          "'forgone' is a suppression lever and must be priced as trading "
          "less, not trading better. Bases are never averaged.")


def selftest() -> int:
    print("mutation test: lever scoring arithmetic")
    failures = 0

    def check(name, got, want, tol=1e-9):
        nonlocal failures
        ok = abs(got - want) < tol
        print(f"  {name}: {got:+.4f} (want {want:+.4f}) -> "
              f"{'ok' if ok else 'FAIL'}")
        failures += 0 if ok else 1

    f = pd.DataFrame([
        dict(market_slug="asc-wnba-a-b-2026-08-20-pos-3pt5", game_id="g1",
             regime="ingame", side="bid", quote_price=0.40, mid_at_quote=0.42,
             spread_at_quote=0.04, mid_at_fill=0.39,
             quoted_at=pd.Timestamp("2026-08-20 01:00:00+00:00"),
             filled_at=pd.Timestamp("2026-08-20 01:00:05+00:00"),
             settlement=1),
        dict(market_slug="asc-wnba-a-b-2026-08-20-pos-4pt5", game_id="g2",
             regime="ingame", side="ask", quote_price=0.60, mid_at_quote=0.58,
             spread_at_quote=0.04, mid_at_fill=0.61,
             quoted_at=pd.Timestamp("2026-08-20 01:00:00+00:00"),
             filled_at=pd.Timestamp("2026-08-20 01:00:05+00:00"),
             settlement=0),
    ])
    e = enrich(f)
    # half-spread earned: bid 0.42-0.40 = +2c; ask 0.60-0.58 = +2c
    check("half-spread bid", e.half_spread.iloc[0], 0.02)
    check("half-spread ask", e.half_spread.iloc[1], 0.02)
    # pessimistic = half_spread - 4.70c exactly
    check("pessimistic swap", e.pess_capture.iloc[0], 0.02 - 0.047)
    # settlement ROI: bid long at .40 settles 1 -> +150%; ask short at .60
    # (cost .40) settles 0 -> +150%
    check("ROI bid settle-1", e.roi.iloc[0], 1.0 / 0.40 - 1.0)
    check("ROI ask settle-0", e.roi.iloc[1], 1.0 / 0.40 - 1.0)

    # suppression accounting: a variant with 1 of 2 baseline fills forgone
    import duckdb
    con = duckdb.connect()
    con.execute("SET timezone='UTC'")
    ticks = pd.DataFrame([
        dict(market_slug=m, event_slug="e", captured_at=t, mid=0.40,
             spread=0.02)
        for m in f.market_slug
        for t in pd.date_range("2026-08-20 01:00:00+00:00", periods=80,
                               freq="10s")])
    con.execute("CREATE TEMP TABLE tk AS SELECT * FROM ticks_df",
                ) if False else con.register("ticks_df", ticks)
    con.execute("CREATE TEMP TABLE tk AS SELECT * FROM ticks_df")
    r = score_variant(con, "half", f.iloc[:1], f)
    ok = r["n_fills"] == 1 and r["forgone"] == 1 and \
        abs(r["forgone_share"] - 0.5) < 1e-9
    print(f"  suppression accounting (1 of 2 forgone) -> "
          f"{'ok' if ok else 'FAIL'}")
    failures += 0 if ok else 1

    # league pin: an NFL row is excluded and shouted about
    mixed = pd.concat([f, f.iloc[:1].assign(
        market_slug="asc-nfl-ne-sea-2026-09-09-pos-20pt5")],
        ignore_index=True)
    r2 = score_variant(con, "mixed", mixed, mixed)
    ok = r2["n_fills"] == 2      # the nfl row dropped
    print(f"  league pin re-assert (nfl row excluded) -> "
          f"{'ok' if ok else 'FAIL'}")
    failures += 0 if ok else 1

    print(f"mutation test: "
          f"{'ALL OK' if failures == 0 else f'{failures} FAILURES'}")
    return failures


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", type=Path)
    ap.add_argument("--ticks", type=Path)
    ap.add_argument("--variants", type=Path, nargs="*", default=[])
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if args.baseline is None or args.ticks is None:
        print("need --baseline (all-levers-off fills tape) and --ticks; "
              "--selftest runs without data")
        return 2

    print("LEVER REPLAY scoring (design-not-evidence)")
    if selftest() != 0:
        print("ABORT: mutation test failed")
        return 1

    baseline = qvm.load_fills(args.baseline)
    # Rule 16: the levers-off tape must BE v1 — the one gate, A's harness
    # licensed by it.
    if not qvm.rule16_gate(baseline, rehearsal=False):
        print("the all-levers-off tape does not reproduce the ledger — "
              "A's harness (or the export) is broken; scoring nothing")
        return 1

    import duckdb
    con = duckdb.connect()
    con.execute("SET timezone='UTC'")
    qvm.load_ticks(con, args.ticks, sorted(baseline.market_slug.unique()))

    rows = [score_variant(con, "v1-baseline (levers off)",
                          baseline, baseline)]
    for vp in args.variants:
        name = vp.stem.replace("lever_replay_", "")
        vf = qvm.load_fills(vp)
        rows.append(score_variant(con, name, vf, baseline))
    render_table(rows)
    if args.out is not None:
        args.out.mkdir(parents=True, exist_ok=True)
        flat = [{k: (f"{v.mean:+.4f}" if hasattr(v, "mean") else v)
                 for k, v in r.items()} for r in rows]
        pd.DataFrame(flat).to_csv(args.out / "lever_capture_table.csv",
                                  index=False)
        print(f"table -> {args.out / 'lever_capture_table.csv'}")

    hr("STANDING STATEMENTS")
    print("In-sample replay on the August WNBA pin under the replay fill "
          "model; optimistic gains are upper bounds; the pessimistic column "
          "is the measured-concession floor; suppression is a cost, counted. "
          "This table designs GRIDIRON's arms; it validates none of them.")
    print("\nNo in-sample result justifies capital. The forward test is the "
          "evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
