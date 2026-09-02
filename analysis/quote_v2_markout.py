"""QUOTE v2 instrumentation — markout, v1 post-mortem, toll map (Quant D).

    .venv/bin/python analysis/quote_v2_markout.py --selftest
    .venv/bin/python analysis/quote_v2_markout.py --fills FILLS.csv
        --ticks TICKS.csv.gz [--rehearsal] [--out DIR]

Measurement side of the QUOTE v2 program (manager brief 2026-09-02): the
engine build is A's; nothing here touches the live quoter. Input is a
shadow_quote_fills-shaped export (columns per core/quote/storage.py:
market_slug, game_id, regime, side, quote_price, mid_at_quote,
spread_at_quote, mid_at_fill, quoted_at, filled_at, settlement) plus the
tick pin for markouts. **THE FILLS PIN DOES NOT EXIST YET as an export** —
flagged to the manager; every real read is blocked on it, which is the
correct order: the instrument exists before the data it must not be tuned
on.

M1 — THE MARKOUT INSTRUMENT. Per fill: capture at fill (EXACTLY report.py's
`net_capture_mark`: bid = mid_at_fill − quote_price, ask = the negative),
plus side-signed markout at +30s / +2m / +10m (bid: mid_h − mid_at_fill;
ask: mid_at_fill − mid_h), from the first two-sided live tick at/after
filled_at + h, gap capped 120s (staleness bound stated — the ffill hazard
entry applies; absent quotes are absent). Net of fee rules: theta_maker = 0
(V9/C7), so maker net = gross; the taker hook exists for any v2 arm that
crosses. Mark-to-market at h = capture + markout_h.

RULE-16 KNOWN-ANSWER GATE: before ANY other module reads real fills, the
instrument must reproduce v1's ledgered in-game verdict from the pinned
substrate — net capture −1.60¢ [−1.69, −1.50] over ALL recorded in-game
fills (17,032; unsettled included, per report.py's own population),
clustered by game_id via the blessed clustered_mean. Mean and both CI ends
must match the ledgered values to the ledger's own 2dp print (±0.005¢).
Mismatch ABORTS. `--rehearsal` downgrades the abort to a loud
UNCALIBRATED banner for schema testing only.

M2 — THE V1 POST-MORTEM BY STATE (only after the gate passes): was the
−1.60¢ uniform, or concentrated where the v2 levers point? Cuts:
  (a) revert/trend character — A's frozen classifier imported from
      analysis/a1_oscillation_descriptive.py (variance_ratio + character
      at their WINDOW_SECONDS, on 1s mid bars ending at quoted_at);
  (b) congestion — B's lags_for_event pooled per event; a fill is
      IN-CONGESTION if filled_at falls within [t0, t0+30s] of a long-lag
      (>=5s) episode in its event (pinned here);
  (c) guard-clean vs would-have-abstained — guard 1 (implausible_state)
      on tape-derived state with an ESTIMATED clock (period + wallclock
      share, labelled estimate); guard 2 needs a fair_value the quote
      substrate does not carry — REPORTED AS NOT COMPUTABLE, never faked;
  (d) the concession decomposition — net capture split into its two
      recorded components, half-spread earned (mid_at_quote − quote_price,
      side-signed) vs move-against-quote (mid_at_fill − mid_at_quote,
      side-signed), by period x mid-band x side.
Every cut: counts first, game-clustered means, share of total loss by
cell. IN-SAMPLE AND SAYS SO — it designs v2 arms, it validates nothing.

M3 — THE TOLL-COLLECTION MAP: per state cell (period x mid band x market
type): what the maker COLLECTS standing there (half-spread at quote, the
toll side of every there-but-tolled-out family) vs what v1's ledger says
the maker PAYS (capture at fill + markout drift) — expected capture minus
adverse selection as a table, emitted to --out. The wave's toll references
(C1's 12c in-window class, the 4.70c concession, B1's 5c family) print as
context rows, never as this table's own measurements.

**No in-sample result justifies capital. The forward test is the evidence.**
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.quote.adverse_selection import clustered_mean  # noqa: E402
from core.quote.report import net_capture_mark, score_fill  # noqa: E402

HORIZONS = [("30s", 30), ("2m", 120), ("10m", 600)]
GAP_CAP_S = 120
LEDGERED = {"mean_c": -1.60, "lo_c": -1.69, "hi_c": -1.50,
            "n_fills": 17032, "n_games": 12}
TOL_C = 0.005
CONGESTION_LONG_S = 5.0
CONGESTION_WINDOW_S = 30.0
REGULATION_MINUTES = 40.0


def hr(t: str) -> None:
    print(f"\n{'=' * 78}\n{t}\n{'=' * 78}")


def cm_str(vals: dict[str, list[float]]) -> str:
    cm = clustered_mean(vals)
    if cm is None:
        return "n/a (<2 games)"
    return (f"{cm.mean * 100:+.2f} [{cm.lo * 100:+.2f}, {cm.hi * 100:+.2f}]c "
            f"(n={cm.n}, G={cm.n_clusters})")


def signed(side: str, later: pd.Series | float, earlier: pd.Series | float):
    """Side-signed move: positive = in the position's favour (bid = long)."""
    d = later - earlier
    return d if side == "bid" else -d


# --------------------------------------------------------------------------- #
# M1 — markout instrument + rule-16 gate
# --------------------------------------------------------------------------- #

def load_fills(path: Path) -> pd.DataFrame:
    f = pd.read_csv(path)
    for c in ("quoted_at", "filled_at"):
        f[c] = pd.to_datetime(f[c], utc=True, format="ISO8601")
    f["capture"] = [net_capture_mark(side=r.side,
                                     quote_price=float(r.quote_price),
                                     mid_at_fill=float(r.mid_at_fill))
                    for r in f.itertuples()]
    return f


def rule16_gate(fills: pd.DataFrame, rehearsal: bool) -> bool:
    hr("RULE-16 KNOWN-ANSWER GATE (v1's ledgered in-game verdict)")
    ing = fills[fills.regime == "ingame"]
    vals = {g: list(v) for g, v in ing.groupby("game_id").capture}
    cm = clustered_mean(vals)
    ok = (cm is not None
          and len(ing) == LEDGERED["n_fills"]
          and abs(cm.mean * 100 - LEDGERED["mean_c"]) <= TOL_C
          and abs(cm.lo * 100 - LEDGERED["lo_c"]) <= TOL_C
          and abs(cm.hi * 100 - LEDGERED["hi_c"]) <= TOL_C)
    got = (f"{cm.mean * 100:+.2f} [{cm.lo * 100:+.2f}, {cm.hi * 100:+.2f}]c "
           f"on {len(ing)} in-game fills" if cm is not None else "no data")
    print(f"ledgered: {LEDGERED['mean_c']:+.2f} [{LEDGERED['lo_c']:+.2f}, "
          f"{LEDGERED['hi_c']:+.2f}]c on {LEDGERED['n_fills']} fills")
    print(f"computed: {got}")
    if ok:
        print("GATE PASSES — the instrument reproduces the ledger; live "
              "reads are permitted")
        return True
    if rehearsal:
        print("GATE FAILS — RUNNING UNCALIBRATED (rehearsal mode): nothing "
              "below is quotable; schema exercise only")
        return True
    print("GATE FAILS — aborting per rule 16: an instrument that cannot "
          "reproduce the known answer must not produce new ones")
    return False


def load_ticks(con: duckdb.DuckDBPyConnection, path: Path,
               markets: list[str]) -> None:
    con.execute("CREATE TEMP TABLE wanted(market_slug VARCHAR)")
    con.executemany("INSERT INTO wanted VALUES (?)", [(m,) for m in markets])
    con.execute(f"""
        CREATE TEMP TABLE tk AS
        SELECT market_slug, event_slug, captured_at, event_period,
               event_score,
               (best_bid + best_ask) / 2.0 AS mid,
               best_ask - best_bid AS spread
        FROM read_csv('{path}')
        WHERE is_live AND best_bid IS NOT NULL AND best_ask IS NOT NULL
          AND market_slug IN (SELECT market_slug FROM wanted)
    """)


def markouts(con: duckdb.DuckDBPyConnection,
             fills: pd.DataFrame) -> pd.DataFrame:
    """Attach mid at filled_at + h per horizon (forward ASOF, gap capped)."""
    out = fills.copy()
    con.register("fills_mk", fills[["market_slug", "filled_at"]]
                 .reset_index(names="fid"))
    for name, secs in HORIZONS:
        rows = con.execute(f"""
            WITH f AS (
              SELECT fid, market_slug,
                     -(epoch(filled_at) + {secs}) AS tneg,
                     filled_at + INTERVAL '{secs} seconds' AS target
              FROM fills_mk
            )
            SELECT f.fid, t.mid,
                   epoch(t.captured_at - f.target) AS gap_s
            FROM f ASOF JOIN (
                 SELECT market_slug, mid, captured_at,
                        -epoch(captured_at) AS neg_t FROM tk) t
              ON f.market_slug = t.market_slug AND t.neg_t <= f.tneg
        """).df()
        rows = rows[rows.gap_s <= GAP_CAP_S].set_index("fid").mid
        out[f"mid_{name}"] = out.index.map(rows)
        out[f"markout_{name}"] = [
            signed(r.side, getattr(r, f"mid_{name}"), r.mid_at_fill)
            if pd.notna(getattr(r, f"mid_{name}")) else np.nan
            for r in out.itertuples()]
    return out


def m1_report(fills: pd.DataFrame) -> None:
    hr("M1. MARKOUT (side-signed; negative = the market kept moving through "
       "the maker; theta_maker = 0 so net = gross)")
    ing = fills[fills.regime == "ingame"]
    print(f"in-game fills: {len(ing)} / {ing.game_id.nunique()} games; "
          f"capture at fill: "
          f"{cm_str({g: list(v) for g, v in ing.groupby('game_id').capture})}")
    for name, _ in HORIZONS:
        sub = ing[ing[f"markout_{name}"].notna()]
        vals = {g: list(v) for g, v in
                sub.groupby("game_id")[f"markout_{name}"]}
        mtm = {g: list(v) for g, v in
               (sub.capture + sub[f"markout_{name}"]).groupby(sub.game_id)}
        print(f"  +{name:>3s}: markout {cm_str(vals)}  |  mark-to-market "
              f"{cm_str(mtm)}  [coverage {len(sub)}/{len(ing)}]")


# --------------------------------------------------------------------------- #
# M2 — post-mortem cuts
# --------------------------------------------------------------------------- #

def cut_report(fills: pd.DataFrame, label: pd.Series, name: str) -> None:
    print(f"\n[{name}] (counts, clustered capture, share of total loss)")
    total_loss = fills.capture.clip(upper=0).sum()
    for val, sub in fills.groupby(label, dropna=False):
        vals = {g: list(v) for g, v in sub.groupby("game_id").capture}
        share = (sub.capture.clip(upper=0).sum() / total_loss
                 if total_loss < 0 else float("nan"))
        print(f"  {str(val):22s}: n={len(sub):6d} G={sub.game_id.nunique():3d}"
              f"  capture {cm_str(vals)}  loss-share {share:5.1%}")


def m2_postmortem(con: duckdb.DuckDBPyConnection,
                  fills: pd.DataFrame) -> None:
    hr("M2. V1 POST-MORTEM BY STATE — uniform, or where the levers point? "
       "(IN-SAMPLE; designs arms, validates nothing)")
    ing = fills[fills.regime == "ingame"].copy()

    # (d) concession decomposition — recorded components, no joins needed.
    ing["half_spread"] = [signed(r.side, r.mid_at_quote, r.quote_price)
                          for r in ing.itertuples()]
    ing["move_against"] = [signed(r.side, r.mid_at_fill, r.mid_at_quote)
                           for r in ing.itertuples()]
    print("(d) capture = half-spread earned + move-against-quote "
          "(identity check on the recorded columns): max residual "
          f"{(ing.capture - ing.half_spread - ing.move_against).abs().max():.6f}")
    print(f"    half-spread earned: "
          f"{cm_str({g: list(v) for g, v in ing.groupby('game_id').half_spread})}")
    print(f"    move against quote: "
          f"{cm_str({g: list(v) for g, v in ing.groupby('game_id').move_against})}")
    ing["mid_band"] = pd.cut(ing.mid_at_quote, [0, .1, .35, .65, .9, 1.0])
    cut_report(ing, ing.mid_band.astype(str), "(d) by mid band at quote")
    cut_report(ing, ing.side, "(d) by side")

    # Manager's seed shapes, clustered and base-labelled. CAPTURE basis
    # (static mark) here; SETTLEMENT basis printed separately below —
    # never mixed (the ledgered -1.60c is capture, the seeds were
    # settlement, and conflating bases is how numbers stop reconciling).
    ing["spread_band"] = pd.cut(ing.spread_at_quote,
                                [0, .02, .05, .10, 1.0],
                                labels=["<=2c", "2-5c", "5-10c", ">10c"])
    cut_report(ing, ing.spread_band.astype(str),
               "seed 1: by SPREAD AT QUOTE (capture basis) — tight-vs-wide")
    roi_rows = ing[ing.settlement.notna()].copy()
    rois = []
    for r in roi_rows.itertuples():
        cost, ret = score_fill(side=r.side, quote_price=float(r.quote_price),
                               settlement=int(r.settlement))
        rois.append(ret / cost - 1.0 if cost > 0 else np.nan)
    roi_rows["roi"] = rois
    print("\nseed 1, SETTLEMENT basis (per-fill ROI, settled fills only, "
          "clustered — the manager's unclustered seed, done properly):")
    for band, sub in roi_rows.groupby(roi_rows.spread_band.astype(str)):
        vals = {g: list(v) for g, v in sub.dropna(subset=["roi"])
                .groupby("game_id").roi}
        print(f"  {band:6s}: n={len(sub):6d}  ROI {cm_str(vals)}")

    # State at fill from the tape (period + score at nearest tick).
    con.register("fills_st", ing[["market_slug", "filled_at"]]
                 .reset_index(names="fid"))
    st = con.execute("""
        SELECT f.fid, t.event_period, t.event_score, t.event_slug
        FROM fills_st f ASOF JOIN tk t
          ON f.market_slug = t.market_slug AND t.captured_at <= f.filled_at
    """).df().set_index("fid")
    ing["period"] = ing.index.map(st.event_period)
    ing["event_slug"] = ing.index.map(st.event_slug)
    cut_report(ing, ing.period, "state: by period at fill")

    # The lever-vs-proxy question: does tight-vs-wide survive holding game
    # state fixed, or is "quote wide" a proxy for "quote late"? (manager's
    # confound caution — if tight losses concentrate late/trending, v2-STATE
    # and v2-WIDTH are one lever wearing two names.)
    ing["late"] = (~ing.period.isin(["Q1", "Q2", "HT"])).map(
        {True: "late", False: "early"})
    cross = (ing.spread_band.astype(str) + " x " + ing.late)
    cut_report(ing, cross, "seed-1 confound cross: spread band x early/late")

    # (a) revert/trend character — A's frozen classifier, their constants.
    try:
        spec = importlib.util.spec_from_file_location(
            "a1", Path(__file__).with_name("a1_oscillation_descriptive.py"))
        a1 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(a1)
        bars = {m: g.set_index("captured_at").mid.resample(a1.BAR).last()
                    .ffill(limit=a1.WINDOW_BARS)
                for m, g in con.execute(
                    "SELECT market_slug, captured_at, mid FROM tk").df()
                .groupby("market_slug")}
        chars = []
        for r in ing.itertuples():
            s = bars.get(r.market_slug)
            if s is None:
                chars.append("no_tape")
                continue
            vr = a1.vr_at(s, r.quoted_at)
            chars.append(a1.character(vr) if np.isfinite(vr) else "no_tape")
        ing["character"] = chars
        cut_report(ing, ing.character,
                   "(a) revert/trend character at quote (A's classifier, "
                   "their WINDOW_SECONDS)")
    except Exception as exc:
        print(f"(a) character cut UNAVAILABLE: {exc} — needs A's "
              f"a1_oscillation_descriptive.py beside this file")

    # (b) congestion — B's lag instrument, pinned window.
    try:
        spec = importlib.util.spec_from_file_location(
            "census", Path(__file__).with_name("cross_market_census.py"))
        census = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(census)
        tkall = con.execute("""
            SELECT market_slug, event_slug, captured_at,
                   mid + spread / 2 AS best_ask, mid - spread / 2 AS best_bid,
                   CASE WHEN market_slug LIKE 'tsc%' OR market_slug LIKE '%total%'
                        THEN 'basketball_team_full_game_total'
                        ELSE 'basketball_team_full_game_spread' END
                   AS sports_market_type
            FROM tk""").df()
        tkall["captured_at"] = tkall.captured_at.dt.tz_localize(None)
        long_starts: dict[str, list[pd.Timestamp]] = {}
        for ev, g in tkall.groupby("event_slug"):
            ts = []
            for kind in ("spread", "total"):
                ts += [t for t, l in census.lags_for_event(g, kind)
                       if l >= CONGESTION_LONG_S]
            long_starts[ev] = sorted(ts)
        def in_congestion(r):
            ts = long_starts.get(r.event_slug, [])
            f = r.filled_at.tz_localize(None)
            return any(0 <= (f - t).total_seconds() <= CONGESTION_WINDOW_S
                       for t in ts)
        ing["congested"] = [in_congestion(r) for r in ing.itertuples()]
        cut_report(ing, ing.congested.map(
            {True: "in-congestion", False: "clear"}),
            f"(b) congestion (fill within {CONGESTION_WINDOW_S:.0f}s after a "
            f">={CONGESTION_LONG_S:.0f}s lag episode; B's instrument)")
    except Exception as exc:
        print(f"(b) congestion cut UNAVAILABLE: {exc}")

    # (c) guard 1 on tape-derived state; clock is an ESTIMATE (period share
    # of wallclock) and says so. Guard 2 (unrepresentable_confidence) needs
    # a fair_value this substrate does not carry: NOT COMPUTABLE, stated.
    try:
        from core.pulse.guards import implausible_state
        per_min = {"Q1": 35.0, "Q2": 25.0, "HT": 20.0, "Q3": 15.0, "Q4": 5.0}
        flags = []
        for r in ing.itertuples():
            try:
                a, b = str(r.event_score).split("-") if pd.notna(
                    getattr(r, "event_score", None)) else (None, None)
                tot, mar = ((int(a) + int(b), int(a) - int(b))
                            if a is not None else (None, None))
            except ValueError:
                tot = mar = None
            ml = per_min.get(str(ing.at[r.Index, "period"]), 20.0)
            flags.append(implausible_state(
                period=ing.at[r.Index, "period"], minutes_left=ml,
                total_so_far=tot, margin=mar) is not None)
        ing["event_score"] = ing.index.map(st.event_score)
        ing["would_abstain"] = flags
        cut_report(ing, ing.would_abstain.map(
            {True: "would-abstain (guard 1)", False: "guard-clean"}),
            "(c) guard 1 on tape state (clock = period-midpoint ESTIMATE); "
            "guard 2 NOT COMPUTABLE here (no fair_value in the substrate)")
    except Exception as exc:
        print(f"(c) guard cut UNAVAILABLE: {exc}")

    print("\nTHE QUESTION, answered by the tables above: if capture is "
          "materially worse in trending / in-congestion / would-abstain "
          "cells, the v2 levers have measured teeth; flat tables mean the "
          "levers are theory. This module states results, the registration "
          "draws the line.")
    m3_toll_map(ing)


# --------------------------------------------------------------------------- #
# M3 — the toll-collection map
# --------------------------------------------------------------------------- #

def m3_toll_map(ing: pd.DataFrame, out: Path | None = None) -> None:
    hr("M3. TOLL-COLLECTION MAP — what the maker collects vs what v1 paid, "
       "by state cell")
    ing = ing.copy()
    if "period" not in ing.columns or "mid_band" not in ing.columns:
        print("state columns unavailable — run after M2")
        return
    tab = ing.groupby(["period", "mid_band"], observed=True).agg(
        fills=("capture", "size"),
        games=("game_id", "nunique"),
        half_spread_c=("half_spread", lambda s: s.mean() * 100),
        capture_c=("capture", lambda s: s.mean() * 100),
        adverse_c=("move_against", lambda s: s.mean() * 100))
    tab["net_c"] = tab.capture_c
    print(tab.round(2).to_string())
    print("\ncontext rows (the wave's toll measurements, NOT this table's): "
          "C1's 12c-class in-window spreads; the 4.70c measured concession; "
          "B1's 5c cross-type family (88 episodes at the >=5s floor, "
          "hand-verification revival condition). The maker's business case "
          "is: cells where half_spread_c exceeds -adverse_c after the v2 "
          "levers; v1's ledger says which cells those were NOT.")
    if out is not None:
        p = out / "toll_map.csv"
        tab.to_csv(p)
        print(f"table -> {p}")


# --------------------------------------------------------------------------- #
# M4 — v1's requote behavior (gates the PATIENCE arm; research ruling 2)
# --------------------------------------------------------------------------- #

REQUOTE_WINDOW_S = 10.0     # a quote born this soon after a same-market fill
                            # is a requote of the fill's own episode


def m4_requote_behavior(fills: pd.DataFrame) -> None:
    """Did v1 requote into dips? THE QUOTE STREAM DOES NOT EXIST — only
    shadow_quote_fills was persisted (core/quote/storage.py has exactly one
    table; unfilled quote updates were never written). But v1's requote rule
    is DETERMINISTIC IN CODE: 'a bid at the best bid and an offer at the
    best ask ... requoted to the touch every cycle' at 5s cadence, no
    damping (core/quote/engine.py:6-7, :68). So the rule's answer is
    always / <=5s / to the current touch, into dips included, BY
    CONSTRUCTION — and this module VERIFIES the coded rule against the
    recorded quote BIRTHS the fills carry (quoted_at, mid_at_quote,
    spread_at_quote), which is verification of a known rule, not a proxy
    for an unrecorded stream."""
    hr("M4. V1 REQUOTE BEHAVIOR (PATIENCE-arm gate; stream absent, rule "
       "deterministic, births verified)")
    ing = fills[fills.regime == "ingame"].sort_values("filled_at")

    # 1. Touch-quoting at birth: quote_price must equal the touch implied by
    # mid_at_quote -/+ spread/2. Verifies 'requoted to the touch'.
    implied = [r.mid_at_quote - r.spread_at_quote / 2 if r.side == "bid"
               else r.mid_at_quote + r.spread_at_quote / 2
               for r in ing.itertuples()]
    at_touch = (np.abs(ing.quote_price.values - np.array(implied)) < 5e-5)
    print(f"quotes born AT the touch: {int(at_touch.sum())}/{len(ing)} = "
          f"{at_touch.mean():.1%} (the coded rule, verified on births)")

    # 2. Requote-into-dip rate: per fill f with a prior same-market fill p
    # within REQUOTE_WINDOW_S of f's BIRTH, was f born at/beyond p's dipped
    # mid (signed vs p's side: <=0 means the market had not reverted before
    # v1 re-centered)?
    rows = []
    for m, g in ing.groupby("market_slug"):
        g = g.sort_values("filled_at")
        prev = None
        for r in g.itertuples():
            if prev is not None:
                gap = (r.quoted_at - prev.filled_at).total_seconds()
                if 0 <= gap <= REQUOTE_WINDOW_S:
                    into_dip = signed(prev.side, r.mid_at_quote,
                                      prev.mid_at_fill) <= 0
                    rows.append(dict(game_id=r.game_id, gap_s=gap,
                                     into_dip=into_dip, capture=r.capture))
            prev = r
    rq = pd.DataFrame(rows)
    if len(rq) == 0:
        print("no fills with a same-market predecessor inside the window — "
              "nothing to verify (counted)")
        return
    print(f"\nfills whose quote was born <= {REQUOTE_WINDOW_S:.0f}s after a "
          f"prior same-market fill: {len(rq)}/{len(ing)} = "
          f"{len(rq) / len(ing):.1%}; birth gap p50 "
          f"{rq.gap_s.median():.1f}s (rule cadence: 5s)")
    dip_vals = {g: [float(v) for v in s]
                for g, s in rq.groupby("game_id").into_dip}
    cmr = clustered_mean(dip_vals)
    ci = (f"{cmr.mean:.1%} [{cmr.lo:.1%}, {cmr.hi:.1%}] "
          f"(n={cmr.n}, G={cmr.n_clusters})" if cmr is not None
          else "n/a (<2 games)")
    print(f"REQUOTE-INTO-DIP RATE (born at/beyond the un-reverted dip): "
          f"{ci}  [raw {rq.into_dip.mean():.1%}]")
    cap_dip = rq[rq.into_dip]
    cap_not = rq[~rq.into_dip]
    print(f"capture of dip-born fills:     "
          f"{cm_str({g: list(v) for g, v in cap_dip.groupby('game_id').capture})}")
    if len(cap_not):
        print(f"capture of reverted-birth fills: "
              f"{cm_str({g: list(v) for g, v in cap_not.groupby('game_id').capture})}")
    print("\nTHE BRANCH (research's pre-written text): a meaningful "
          "into-dip rate means v1 was RELEASING the patience lever "
          "constantly — PATIENCE is a real arm with the measured ~0.8c "
          "target. A negligible rate would demote the reversion to a "
          "measurement-horizon note. The rate above decides; the "
          "registration says which.")


# --------------------------------------------------------------------------- #
# Selftest — rule 15: jitter-null + injected answers, all synthetic
# --------------------------------------------------------------------------- #

def _syn(side, quote, mid_q, mid_f, game="g1", regime="ingame",
         market="m1", t="2026-08-20 01:00:00+00:00"):
    return dict(market_slug=market, game_id=game, regime=regime, side=side,
                quote_price=quote, mid_at_quote=mid_q, spread_at_quote=0.02,
                mid_at_fill=mid_f, quoted_at=pd.Timestamp(t),
                filled_at=pd.Timestamp(t) + pd.Timedelta(seconds=5),
                settlement=1)


def selftest() -> int:
    print("mutation test (rule 15): the markout instrument")
    failures = 0

    def check(name, got, want, tol=1e-9):
        nonlocal failures
        ok = abs(got - want) < tol
        print(f"  {name}: {got:+.4f} (want {want:+.4f}) -> "
              f"{'ok' if ok else 'FAIL'}")
        failures += 0 if ok else 1

    # capture formula matches report.py by construction (imported); verify
    # the sign frame anyway on both sides.
    f = pd.DataFrame([_syn("bid", 0.40, 0.42, 0.39),
                      _syn("ask", 0.60, 0.58, 0.61)])
    f["capture"] = [net_capture_mark(side=r.side,
                                     quote_price=float(r.quote_price),
                                     mid_at_fill=float(r.mid_at_fill))
                    for r in f.itertuples()]
    check("bid capture (mid through quote)", f.capture.iloc[0], -0.01)
    check("ask capture", f.capture.iloc[1], -0.01)

    # markout: flat tape reads exactly 0 at every horizon (jitter-null:
    # shifting fill times on a flat tape must change nothing); injected
    # -2c adverse drift reads -2c on the bid and +2c favourable on the ask.
    con = duckdb.connect()
    con.execute("SET timezone='UTC'")
    base = pd.Timestamp("2026-08-20 01:00:05+00:00")
    ticks = []
    for s in range(0, 700, 10):
        ticks.append(dict(market_slug="mflat", event_slug="g1",
                          captured_at=base + pd.Timedelta(seconds=s),
                          event_period="Q2", event_score="20-18",
                          mid=0.39, spread=0.02))
        ticks.append(dict(market_slug="mdrift", event_slug="g1",
                          captured_at=base + pd.Timedelta(seconds=s),
                          event_period="Q2", event_score="20-18",
                          mid=0.39 - 0.02 * (s >= 30), spread=0.02))
    con.execute("CREATE TEMP TABLE tk AS SELECT * FROM ticks_df",
                ) if False else con.register("ticks_df", pd.DataFrame(ticks))
    con.execute("CREATE TEMP TABLE tk AS SELECT * FROM ticks_df")
    ff = pd.DataFrame([_syn("bid", 0.40, 0.42, 0.39, market="mflat"),
                       _syn("bid", 0.40, 0.42, 0.39, market="mdrift"),
                       _syn("ask", 0.40, 0.38, 0.39, market="mdrift")])
    ff["capture"] = 0.0
    mk = markouts(con, ff)
    check("flat tape markout +30s = 0", mk.markout_30s.iloc[0], 0.0)
    check("jitter-null: flat tape at +10m = 0", mk.markout_10m.iloc[0], 0.0)
    check("injected -2c adverse (bid)", mk.markout_30s.iloc[1], -0.02)
    check("same tape, ask side reads +2c", mk.markout_30s.iloc[2], +0.02)

    # M4 requote classification: fill B born 4s after fill A at the
    # un-reverted dip -> into_dip; fill C born after reversion -> not;
    # fill D born 300s later -> outside the window entirely.
    t0 = pd.Timestamp("2026-08-20 01:00:00+00:00")
    seq = pd.DataFrame([
        dict(_syn("bid", 0.40, 0.42, 0.39, market="mA"),
             quoted_at=t0, filled_at=t0 + pd.Timedelta(seconds=5)),
        dict(_syn("ask", 0.38, 0.39, 0.40, market="mA"),
             quoted_at=t0 + pd.Timedelta(seconds=9),      # 4s after A fills
             filled_at=t0 + pd.Timedelta(seconds=20)),    # born at dip .39
        # C's predecessor is B (an ask filled with mid risen to 0.40); a
        # REVERTED birth for C means mid back BELOW 0.40 at quote time.
        dict(_syn("bid", 0.38, 0.39, 0.37, market="mA"),
             quoted_at=t0 + pd.Timedelta(seconds=28),
             filled_at=t0 + pd.Timedelta(seconds=40)),
        dict(_syn("bid", 0.40, 0.42, 0.39, market="mA"),
             quoted_at=t0 + pd.Timedelta(seconds=400),
             filled_at=t0 + pd.Timedelta(seconds=410)),
    ])
    seq["regime"] = "ingame"
    seq["capture"] = 0.0
    import contextlib, io as _io
    buf = _io.StringIO()
    with contextlib.redirect_stdout(buf):
        m4_requote_behavior(seq)
    out_txt = buf.getvalue()
    ok = ("2/4" in out_txt and "raw 50.0%" in out_txt)
    print(f"  M4 requote classification (2 in-window, 1 into-dip) -> "
          f"{'ok' if ok else 'FAIL'}")
    if not ok:
        print(out_txt)
    failures += 0 if ok else 1

    # rule-16 gate: a synthetic book that does NOT match the ledger must
    # fail closed (and pass only in rehearsal mode).
    import contextlib, io
    fake = pd.DataFrame([_syn("bid", 0.40, 0.42, 0.39, game=f"g{i}")
                         for i in range(12)])
    fake["capture"] = -0.01
    with contextlib.redirect_stdout(io.StringIO()):
        hard = rule16_gate(fake, rehearsal=False)
        soft = rule16_gate(fake, rehearsal=True)
    print(f"  rule-16 gate fails closed / opens in rehearsal -> "
          f"{'ok' if (not hard and soft) else 'FAIL'}")
    failures += 0 if (not hard and soft) else 1

    print(f"mutation test: {'ALL OK' if failures == 0 else f'{failures} FAILURES'}")
    return failures


# --------------------------------------------------------------------------- #

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fills", type=Path)
    ap.add_argument("--ticks", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--rehearsal", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if args.fills is None or args.ticks is None:
        print("need --fills (shadow_quote_fills export — THE PIN DOES NOT "
              "EXIST YET; ask the manager/operator for the export) and "
              "--ticks; --selftest runs without data")
        return 2

    print("QUOTE v2 instrumentation — markout / post-mortem / toll map")
    print(f"fills: {args.fills}  ticks: {args.ticks}")
    if selftest() != 0:
        print("ABORT: mutation test failed")
        return 1

    fills = load_fills(args.fills)
    if not rule16_gate(fills, args.rehearsal):
        return 1
    con = duckdb.connect()
    con.execute("SET timezone='UTC'")
    load_ticks(con, args.ticks, sorted(fills.market_slug.unique()))
    fills = markouts(con, fills)
    m1_report(fills)
    m4_requote_behavior(fills)

    # Seed 2 / D1 fold: the pregame regime on the maker's own ledger
    # (capture AND settlement bases, clustered; n is small and says so).
    hr("SEED 2 / D1 FOLD — the pregame regime (307 fills; D1's dead-window "
       "thesis on the maker's own tape; hours-to-tip partition needs tip "
       "times the fills export lacks — hook stated, finer cut deferred)")
    for regime, sub in fills.groupby("regime"):
        vals = {g: list(v) for g, v in sub.groupby("game_id").capture}
        print(f"  {regime:8s}: n={len(sub):6d} G={sub.game_id.nunique():3d} "
              f" capture {cm_str(vals)}")
        settled = sub[sub.settlement.notna()]
        if len(settled):
            rois = {}
            for g, ss in settled.groupby("game_id"):
                rr = []
                for r in ss.itertuples():
                    cost, ret = score_fill(side=r.side,
                                           quote_price=float(r.quote_price),
                                           settlement=int(r.settlement))
                    if cost > 0:
                        rr.append(ret / cost - 1.0)
                rois[g] = rr
            print(f"            settlement ROI {cm_str(rois)}")

    m2_postmortem(con, fills)

    hr("STANDING STATEMENTS")
    print("All real-fill numbers above are in-sample v1 post-mortem under "
          "the quote engine's own fill model (optimism cuts the known way: "
          "the fill rule undercounts exactly the fills that hurt). They "
          "design v2 arms; the registration and its forward cohort decide.")
    print("\nNo in-sample result justifies capital. The forward test is the "
          "evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
