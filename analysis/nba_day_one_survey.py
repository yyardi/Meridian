"""NBA day-one market-quality survey — the launch policy's clause-2 gate.

    .venv/bin/python analysis/nba_day_one_survey.py --snapshots CSV[.gz]
        [--out DIR] [--selftest]

Built BEFORE listings exist (docs/math/nba-launch-policy.md: the survey runs
first; "a listing is not a book" (V29) is resolved by measurement) so that
opening night cannot be recorded retroactively. Input is a market_snapshots-
shaped export (the live_ticks pin schema, plus the columns the full snapshot
table carries: fee_coefficient, min_tick_size, min_trade_qty, book_tier,
raw). EVERY module degrades LOUDLY when a column is missing — the missing-
column report is itself a pre-launch deliverable: it says what the export
path must add before the first tip. Composition before ratios everywhere.

Modules (owners credited; reuse per the round's rule 15):

  M0 composition + V29 structural checks — slug families (aec/asc/tsc/tec),
     half-point *ptX slug/line agreement, recorder cadence vs the 200ms
     assumption, column availability.
  M1 spread distribution by type x period x band — B's
     `spread_distribution` (analysis/cross_market_census.py, commit b9c380f)
     — plus THE PRE-COMMITTED TOLL COMPARISON, pinned here before any NBA
     row exists: C1's WNBA reference is the 12c-class in-window median;
     "materially tighter" is PINNED as in-play spread+totals p50 <= 8c —
     at or above 12c-class the tolled-out families stay closed; <= 8c
     reopens C1 with ONLY the toll term changed. Routing language, no gate.
  M2 top-of-book depth at rung level — book_tier-sampled rows, levels
     parsed from `raw`; emits the rung-level table; V1 (WNBA) is the prior.
  M3 fee coefficients — verify venue-stated 0.06 everywhere (V9);
     deviations are loud and per-market.
  M4 update cadence + cross-rung response lags — B's `lags_for_event` with
     their censoring header carried, their `validate_lag_instrument()` wired
     into THIS file's selftest (validates the import at our constants), and
     the congestion clustering share vs a deterministic circular-shift null.
  M5 ladder sigma vs fitted constants — probit fit of ladder mids at period
     boundaries; totals vs `nba_constants_v1.json` r3b sigma (36/24/12
     minutes remaining), spreads vs r1b per-sqrt-min phase table. PREGAME
     totals sigma is FITTED AND REPORTED but the comparison line is GATED:
     no sigma_T0 estimand exists until R5 registers (the hook is the
     commitment; the read waits).
  M6 ladder coherence invariant — persistent executable violations net of
     both taker fees. Coherence is a measured invariant of the venue's
     engine (1 sub-cent violation / 4.69M WNBA rows); persistent violations
     on a new board mean a SICK BOARD OR ENGINE CHANGE, never opportunity.
     (The wall cites survey/ladder_coherence.py; that file is NOT in the
     repo — flagged to the manager; this module is a fresh, mutation-tested
     implementation of the same invariant.)
  M7 C3's day-one record artifacts (--out DIR): first-appearance ladder
     snapshots WITH rung coverage relative to the at-the-money line (B's
     seeded-ladder gap finding: 18/34 WNBA boards had no rung near even
     margin — coverage decides which games any cross-type check can run
     on); first two-sided time per rung; book death/revival events with
     game state; halftime last-Q2/first-Q3 mids (D2's fields). The ESPN
     join at listing is recorder-side plumbing, NOT this instrument —
     stated so its absence here is a decision, not an oversight.

Rule 15 stands: the FIRST real episode of anything (lag, violation, depth
whale, book death) gets hand-verified against the raw rows before any
number from its module is quoted.

**No in-sample result justifies capital. The forward test is the evidence.**
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
from scipy import stats

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.quote.adverse_selection import clustered_mean  # noqa: E402

CONSTANTS = REPO / "analysis" / "nba_constants_v1.json"
FEE_EXPECTED = 0.06                      # V9, venue-published
TOLL_TIGHTER_P50_C = 8.0                 # pinned: "materially tighter" bar
TOLL_REFERENCE_C = 12.0                  # C1's WNBA in-window median class
CADENCE_EXPECT_MS = 200
COHERENCE_PERSIST_S = 20.0
SIGMA_MIN_RUNGS = 4
SIGMA_MIN_SPAN = 6.0                     # points of line span for a fit
NBA_BOUNDARY_MIN_LEFT = {"Q2": 36.0, "Q3": 24.0, "Q4": 12.0}
R1B_PHASE_AT_BOUNDARY = {"Q2": "(24.0,36.0]", "Q3": "(12.0,24.0]",
                         "Q4": "(0.0,12.0]"}

_census_spec = importlib.util.spec_from_file_location(
    "cross_market_census", Path(__file__).with_name("cross_market_census.py"))
census = importlib.util.module_from_spec(_census_spec)
try:
    _census_spec.loader.exec_module(census)
    CENSUS_OK = all(hasattr(census, f) for f in
                    ("lags_for_event", "spread_distribution",
                     "validate_lag_instrument"))
except Exception:                                        # pragma: no cover
    census, CENSUS_OK = None, False


def hr(t: str) -> None:
    print(f"\n{'=' * 78}\n{t}\n{'=' * 78}")


def need(df: pd.DataFrame, cols: list[str], module: str) -> bool:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        print(f"[{module}] DEGRADED — export is missing columns {missing}; "
              f"fix the export path before listing day")
        return False
    return True


# --------------------------------------------------------------------------- #
# M0 — composition and V29 structural checks
# --------------------------------------------------------------------------- #

def m0_composition(df: pd.DataFrame,
                   resolved: pd.DataFrame | None = None) -> dict:
    """Composition, and THE CONVENTION GATE: the survey's assumptions about
    the venue (half-point ptX slug encoding, first-team score frame, ~200ms
    cadence) were measured on WNBA/resolved markets (V29) — on a live NBA
    board they are inferences until asserted here. Returns {check: bool};
    any False makes the whole run exit nonzero, loudly, per the manager's
    module-zero requirement. The frame check needs settlements: it runs when
    --resolved is given (settlement == [first-team margin + line > 0], the
    196/196 method) and reports UNVERIFIED otherwise."""
    hr("M0. COMPOSITION + V29 CONVENTION GATE (counts before ratios)")
    gate: dict[str, bool] = {}
    print(f"rows {len(df)} | markets {df.market_slug.nunique()} | events "
          f"{df.event_slug.nunique() if 'event_slug' in df else '?'} | "
          f"window {df.captured_at.min()} -> {df.captured_at.max()}")
    fam = df.market_slug.str.split("-").str[0]
    print("slug families (V29 expects aec/asc/tsc, tec extra):")
    print(fam.value_counts().to_string())

    # Half-point discipline: slugs ending ptX must agree with the line column.
    if "line" in df.columns:
        per = df.drop_duplicates("market_slug")
        slugline = per.market_slug.str.extract(
            r"(?:pos|neg)?-?(\d+)pt(\d)$", expand=True)
        have = slugline[0].notna()
        parsed = (pd.to_numeric(slugline.loc[have, 0])
                  + pd.to_numeric(slugline.loc[have, 1]) / 10.0)
        neg = per.loc[have, "market_slug"].str.contains("-neg-")
        parsed = parsed.where(~neg.values, -parsed)
        line_abs = per.loc[have, "line"].astype(float)
        agree = (parsed.values == line_abs.values)
        n_half = int((pd.to_numeric(slugline.loc[have, 1]) == 5).sum())
        gate["slug_line_encoding"] = bool(agree.all()) and n_half == int(
            have.sum())
        print(f"\nladder slugs with ptX suffix: {int(have.sum())} "
              f"({n_half} half-point); slug<->line agreement "
              f"{int(agree.sum())}/{len(agree)}"
              + ("" if gate["slug_line_encoding"] else
                 "  <- CONVENTION GATE FAILS: encoding drifted from V29; "
                 "triangle math and line parsing are both unsafe"))

    # Recorder cadence: median inter-row gap per market, busiest decile.
    g = df.sort_values("captured_at").groupby("market_slug").captured_at
    gaps = g.diff().dt.total_seconds().dropna() * 1000
    if len(gaps):
        gate["cadence"] = bool(gaps.median() <= 5 * CADENCE_EXPECT_MS)
        print(f"\nrecorder cadence: inter-row gap p50 {gaps.median():.0f}ms, "
              f"p90 {gaps.quantile(.9):.0f}ms (assumption: "
              f"~{CADENCE_EXPECT_MS}ms"
              + ("" if gate["cadence"] else
                 " — CONVENTION GATE FAILS: >5x slower; every latency "
                 "number downstream is wrong") + ")")

    # First-team score frame: needs settlements (the 196/196 method).
    if (resolved is not None and "event_score" in df.columns
            and "line" in df.columns):
        settle = resolved.dropna(subset=["settlement"]).drop_duplicates(
            "market_slug").set_index("market_slug").settlement
        # Final score is an EVENT-level fact: a market whose book died
        # mid-Q4 has a stale last score of its own; use the event's very
        # last scored row instead (any market — scores ride on every row).
        finals = (df[df.event_score.notna()].sort_values("captured_at")
                  .groupby("event_slug").event_score.last())
        spr = df[df.sports_market_type.astype(str).str.endswith("spread")]
        per = spr.drop_duplicates("market_slug")[
            ["market_slug", "event_slug", "line"]].set_index("market_slug")
        per["S"] = per.index.map(settle)
        per["final"] = per.event_slug.map(finals)
        per = per[per.S.notna() & per.final.notna()]
        n_ok = n_all = n_boundary = 0
        bad_slugs = []
        for r in per.itertuples():
            try:
                a, b = str(r.final).split("-")
                margin = int(a) - int(b)
                pred = 1 if (margin + float(r.line)) > 0 else 0
            except (ValueError, TypeError):
                continue
            n_all += 1
            if pred == int(r.S):
                n_ok += 1
            elif abs(margin + float(r.line)) <= 2.5:
                # The tape can end BEFORE the final points (hand-verified,
                # rule 15: tor-wsh 08-19 tape ends 82-91, resolved final
                # 82-93; the +10.5 rung sits in that gap and settled
                # correctly). A single rung within one basket of the
                # boundary is tape truncation, not a frame flip.
                n_boundary += 1
            else:
                bad_slugs.append(r.Index)
        if n_all:
            gate["score_frame"] = len(bad_slugs) == 0
            print(f"first-team score frame vs settlements: {n_ok}/{n_all} "
                  f"agree, {n_boundary} boundary rungs where the tape ended "
                  f"early (excluded, counted)"
                  + ("" if gate["score_frame"] else
                     f"  <- CONVENTION GATE FAILS: {len(bad_slugs)} clear "
                     f"flips (the 33-of-85 pattern); hand-verify (rule 15): "
                     f"{bad_slugs[:5]}"))
        else:
            print("score-frame check: no resolvable spread markets yet — "
                  "UNVERIFIED (reruns as settlements land)")
    else:
        print("score-frame check: UNVERIFIED until --resolved is provided "
              "(first settlements) — stated, not skipped")

    cols = ["fee_coefficient", "min_tick_size", "min_trade_qty", "book_tier",
            "raw", "event_period", "event_score", "is_live", "line"]
    avail = {c: ("yes" if c in df.columns else "MISSING") for c in cols}
    print(f"\ncolumn availability: {avail}")
    return gate


# --------------------------------------------------------------------------- #
# M1 — spreads and the pre-committed toll comparison
# --------------------------------------------------------------------------- #

def m1_spreads(df: pd.DataFrame) -> None:
    hr("M1. SPREAD DISTRIBUTION (B's census module) + THE TOLL COMPARISON")
    if not CENSUS_OK:
        print("DEGRADED: analysis/cross_market_census.py (b9c380f) not "
              "importable — land B's commit; no fallback implementation on "
              "purpose (one instrument, rule 15).")
        return
    table = census.spread_distribution(df)
    print(table.to_string(index=False))
    live = df[df["is_live"]] if "is_live" in df.columns else df
    lad = live[live.sports_market_type.astype(str)
               .str.endswith(("spread", "total"))]
    two = lad[lad.best_bid.notna() & lad.best_ask.notna()]
    if len(two) == 0:
        print("\n(no in-play ladder rows yet — toll comparison pending)")
        return
    p50 = float((two.best_ask - two.best_bid).median()) * 100
    print(f"\nTHE TOLL NUMBER: in-play ladder spread p50 = {p50:.1f}c "
          f"(n={len(two)} rows / {two.market_slug.nunique()} markets / "
          f"{two.event_slug.nunique() if 'event_slug' in two else '?'} events)")
    if p50 <= TOLL_TIGHTER_P50_C:
        print(f"  <= {TOLL_TIGHTER_P50_C:.0f}c: MATERIALLY TIGHTER than the "
              f"WNBA {TOLL_REFERENCE_C:.0f}c-class — C1 REOPENS with only "
              f"the toll term changed (pre-committed routing, not a gate)")
    else:
        print(f"  {TOLL_REFERENCE_C:.0f}c-class or wider — the tolled-out "
              f"families stay closed; same doors, new board")


# --------------------------------------------------------------------------- #
# M2 — top-of-book depth at rung level
# --------------------------------------------------------------------------- #

def parse_book_raw(raw: str | dict) -> tuple[float | None, float | None]:
    """(size at best bid, size at best ask) from a stored book payload.

    Tolerant to the two shapes seen from this venue family: lists of
    {price,size} dicts or [price, size] pairs, under bids/asks or
    buys/sells. Returns (None, None) when nothing parses — counted, never
    guessed."""
    try:
        book = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(book, dict):
            return None, None
        out = []
        for side, best in (("bids", max), ("asks", min)):
            levels = book.get(side) or book.get(
                {"bids": "buys", "asks": "sells"}[side]) or []
            parsed = []
            for lv in levels:
                if isinstance(lv, dict) and "price" in lv and "size" in lv:
                    parsed.append((float(lv["price"]), float(lv["size"])))
                elif isinstance(lv, (list, tuple)) and len(lv) >= 2:
                    parsed.append((float(lv[0]), float(lv[1])))
            if not parsed:
                out.append(None)
                continue
            px = best(p for p, _ in parsed)
            out.append(sum(s for p, s in parsed if p == px))
        return out[0], out[1]
    except Exception:
        return None, None


def m2_depth(df: pd.DataFrame, out: Path | None) -> None:
    hr("M2. TOP-OF-BOOK DEPTH AT RUNG LEVEL (V1's WNBA numbers are the prior)")
    if not need(df, ["book_tier"], "M2"):
        return
    sampled = df[df.book_tier.notna()].copy()
    print(f"book-tier-sampled rows: {len(sampled)} "
          f"({sampled.market_slug.nunique()} markets); tiers: "
          f"{sampled.book_tier.value_counts().to_dict()}")
    if len(sampled) == 0:
        return
    if "raw" not in sampled.columns or sampled.raw.isna().all():
        print("DEGRADED: no raw payloads in the export — depth cannot be "
              "read; the export must carry raw for book_tier rows")
        return
    parsed = sampled.raw.map(parse_book_raw)
    sampled["bid_depth"] = parsed.str[0]
    sampled["ask_depth"] = parsed.str[1]
    n_bad = int(sampled.bid_depth.isna().sum())
    print(f"parsed {len(sampled) - n_bad}/{len(sampled)} payloads "
          f"({n_bad} unparsed — {'INVESTIGATE' if n_bad else 'ok'})")
    ok = sampled[sampled.bid_depth.notna()].copy()
    if len(ok) == 0:
        return
    ok["mid_band"] = pd.cut((ok.best_bid + ok.best_ask) / 2,
                            [0, .1, .35, .65, .9, 1.0])
    tab = ok.groupby([ok.sports_market_type.astype(str)
                      .str.rsplit("_", n=1).str[-1], "mid_band"],
                     observed=True).agg(
        rows=("market_slug", "size"),
        bid_depth_p50=("bid_depth", "median"),
        ask_depth_p50=("ask_depth", "median"))
    print(tab.to_string())
    if out is not None:
        p = out / "rung_depth.csv"
        ok[["market_slug", "captured_at", "line", "book_tier",
            "best_bid", "best_ask", "bid_depth", "ask_depth"]].to_csv(
            p, index=False)
        print(f"rung-level depth table -> {p}")
    print("(rule 15: hand-verify the first real depth row against the venue "
          "before quoting any capture number)")


# --------------------------------------------------------------------------- #
# M3 — fee coefficients
# --------------------------------------------------------------------------- #

def m3_fees(df: pd.DataFrame) -> None:
    hr("M3. FEE COEFFICIENTS (V9: 0.060000 everywhere on the WNBA board)")
    if not need(df, ["fee_coefficient"], "M3"):
        return
    per = df.dropna(subset=["fee_coefficient"]).drop_duplicates("market_slug")
    counts = per.fee_coefficient.astype(float).value_counts()
    print(f"distinct fee coefficients across {len(per)} markets:")
    print(counts.to_string())
    odd = per[per.fee_coefficient.astype(float).round(6) != FEE_EXPECTED]
    if len(odd):
        print(f"\nLOUD: {len(odd)} markets deviate from {FEE_EXPECTED} — "
              f"every cost model in the repo assumes V9; list:")
        print(odd[["market_slug", "fee_coefficient"]]
              .head(20).to_string(index=False))
    else:
        print(f"all {FEE_EXPECTED} — V9 transfers to the NBA board")


# --------------------------------------------------------------------------- #
# M4 — cadence + cross-rung response lags (B's instrument)
# --------------------------------------------------------------------------- #

def m4_lags(df: pd.DataFrame) -> None:
    hr("M4. CROSS-RUNG RESPONSE LAGS (B's lags_for_event; censoring header "
       "carried: the pin cannot order updates faster than one poll — the "
       "observable population is the >=400ms tail; attribution, no capture "
       "economics)")
    if not CENSUS_OK:
        print("DEGRADED: census module unavailable (see M1)")
        return
    if not need(df, ["event_slug", "event_period"], "M4"):
        return
    episodes: list[tuple] = []
    d = df.copy()
    d["captured_at"] = pd.to_datetime(d.captured_at, utc=True).dt.tz_localize(None)
    for _, ev in d.groupby("event_slug"):
        for kind in ("spread", "total"):
            try:
                episodes += census.lags_for_event(ev, kind)
            except Exception as exc:
                print(f"  lags_for_event failed on one event/kind: {exc}")
    if not episodes:
        print("no response episodes yet (thin board or no co-moves) — "
              "counted, not invented")
        return
    s = pd.Series([l for _, l in episodes])
    print(f"episodes {len(s)}: lag p50 {s.median():.2f}s, p90 "
          f"{s.quantile(.9):.2f}s")
    # Congestion clustering with B's OWN null (census.congestion_clustering,
    # aedced3): one instrument, one copy of the null — a reimplementation
    # here already produced null == statistic once and is why the callable
    # exists (its docstring says so).
    if hasattr(census, "congestion_clustering"):
        cc = census.congestion_clustering(episodes)
        if cc is None:
            print("congestion clustering: <10 long-lag episodes — "
                  "no verdict (counted, not invented)")
        else:
            print(f"congestion clustering (B's nulled instrument): "
                  f"share_near {cc['share_near']:.1%} vs null "
                  f"{cc['null_share']:.1%} -> "
                  f"{'CLUSTERED' if cc['clustered'] else 'not clustered'} "
                  f"(WNBA reference 55-70% vs 7-12%); rule 15 on the first "
                  f"NBA episode")
    else:
        print("DEGRADED: census.congestion_clustering missing — land B's "
              "aedced3; no local null on purpose")


# --------------------------------------------------------------------------- #
# M5 — ladder sigma vs the fitted constants
# --------------------------------------------------------------------------- #

def probit_fit(lines: pd.Series, mids: pd.Series) -> tuple[float, float] | None:
    """(mu, sigma) from ladder mids: P(X > L) = 1 - Phi((L-mu)/sigma).

    Least squares on z = Phi^-1(1 - mid) vs L; needs >= SIGMA_MIN_RUNGS rungs
    with mids in (0.01, 0.99) spanning >= SIGMA_MIN_SPAN points."""
    m = (mids > 0.01) & (mids < 0.99)
    L, y = lines[m].astype(float), mids[m].astype(float)
    if len(L) < SIGMA_MIN_RUNGS or L.max() - L.min() < SIGMA_MIN_SPAN:
        return None
    z = stats.norm.ppf(1.0 - y)
    slope, intercept = ((z - z.mean()) * (L - L.mean())).sum() / \
        ((L - L.mean()) ** 2).sum(), 0.0
    intercept = z.mean() - slope * L.mean()
    if slope <= 0:
        return None
    sigma = 1.0 / slope
    mu = -intercept * sigma
    return float(mu), float(sigma)


def m5_sigma(df: pd.DataFrame) -> None:
    hr("M5. LADDER SIGMA vs FITTED CONSTANTS (queue candidate 2's machinery; "
       "R1b/R3b from nba_constants_v1.json)")
    if not need(df, ["event_slug", "event_period", "line"], "M5"):
        return
    consts = json.loads(CONSTANTS.read_text())
    r3b = {float(k): v for k, v in consts["r3b_totals"]["sigma"].items()}
    r1b = consts["r1b_sigma"]["phase_table"]
    two = df[df.best_bid.notna() & df.best_ask.notna()].copy()
    two["mid"] = (two.best_bid + two.best_ask) / 2

    def ladder_at(ev_rows: pd.DataFrame, period: str | None) -> pd.DataFrame:
        sub = (ev_rows[ev_rows.event_period == period] if period
               else ev_rows[~ev_rows.get("is_live", True).fillna(False)])
        if len(sub) == 0:
            return sub
        t0 = sub.captured_at.min()
        first = (sub[sub.captured_at <= t0 + pd.Timedelta(seconds=60)]
                 .sort_values("captured_at").groupby("line").first())
        return first.reset_index()

    for mtype, ref_kind in (("total", "r3b"), ("spread", "r1b")):
        rows = two[two.sports_market_type.astype(str).str.endswith(mtype)]
        print(f"\n[{mtype} ladders]")
        devs: dict[str, dict[str, list[float]]] = {}
        for period, min_left in [(None, None)] + list(
                NBA_BOUNDARY_MIN_LEFT.items()):
            fits = []
            for ev, ev_rows in rows.groupby("event_slug"):
                lad = ladder_at(ev_rows, period)
                if len(lad) == 0:
                    continue
                if mtype == "spread":
                    # P(margin + line > 0): mid rises with line; flip to the
                    # survivor frame the probit fit expects.
                    fit = probit_fit(-lad.line, 1.0 - lad.mid)
                else:
                    fit = probit_fit(lad.line, lad.mid)
                if fit is not None:
                    fits.append((ev, fit))
            label = period or "PREGAME/LISTING"
            if not fits:
                print(f"  {label}: no fittable ladders yet")
                continue
            sig = pd.Series([s for _, (mu, s) in fits])
            print(f"  {label}: {len(fits)} ladders fitted; implied sigma "
                  f"p50 {sig.median():.2f} (p25 {sig.quantile(.25):.2f}, "
                  f"p75 {sig.quantile(.75):.2f})")
            if period is None:
                if mtype == "total":
                    print("    comparison GATED: no pregame totals-sigma "
                          "estimand until R5 registers — fitted values "
                          "reported, the hook is the commitment")
                continue
            if mtype == "total":
                ref = r3b[NBA_BOUNDARY_MIN_LEFT[period]]
            else:
                minutes = NBA_BOUNDARY_MIN_LEFT[period]
                ref = r1b[R1B_PHASE_AT_BOUNDARY[period]] * (minutes ** 0.5)
            dv = {e: [s - ref] for e, (mu, s) in fits}
            cm = clustered_mean(dv)
            line = (f"    vs constant {ref:.2f}: deviation "
                    f"{sig.median() - ref:+.2f} (median)")
            if cm is not None:
                line += (f"; clustered {cm.mean:+.2f} "
                         f"[{cm.lo:+.2f}, {cm.hi:+.2f}] "
                         f"({cm.n_clusters} games)")
            print(line + " — persistent one-direction deviation beyond the "
                  "WNBA dispersion (+/-1.4) is queue candidate 2's trigger")


# --------------------------------------------------------------------------- #
# M6 — the coherence invariant
# --------------------------------------------------------------------------- #

def coherence_violations(df: pd.DataFrame) -> pd.DataFrame:
    """Persistent executable dominance violations on one ladder type.

    Survivor-frame monotonicity: P(X > L) must be NON-INCREASING in L, so a
    violation is the HIGHER threshold's bid crossing the LOWER threshold's
    ask. Then buy X>L_lo at ask_lo and sell X>L_hi at bid_hi: the payoff is
    0 or +1 in every state (the higher claim implies the lower), so
    bid_hi - ask_lo - fee(bid_hi) - fee(ask_lo) > 0 is free money.
    (The opposite comparison, bid_lo - ask_ hi > 0, is a STRANGLE — normal
    band pricing, not an arb — the first draft of this function flagged
    6,963 of those on the WNBA pin against c7's measured invariant of ~1,
    which is what a sign error looks like.) Episodes persisting >=
    COHERENCE_PERSIST_S are returned. Spread ladders are passed in with
    line NEGATED ONLY (YES at line L is the survivor claim margin > -L at
    its own price; no price transform)."""
    out = []
    two = df[df.best_bid.notna() & df.best_ask.notna()].copy()
    # Evaluate on the closed methodology's 10s grid with per-bucket
    # freshness: each rung contributes its last two-sided quote WITHIN the
    # bucket, and a pair is only comparable where both rungs quoted in the
    # same bucket. Raw-tick ffill manufactures simultaneity from stale
    # quotes (first draft: 11 extra episodes, most of them one stale side).
    two["bucket"] = two.captured_at.dt.floor("10s")
    for (ev, mt), g in two.groupby(["event_slug", "sports_market_type"]):
        wide = g.pivot_table(index="bucket", columns="line",
                             values=["best_bid", "best_ask"], aggfunc="last")
        lines = sorted({c[1] for c in wide.columns})
        for lo, hi in zip(lines, lines[1:]):
            try:
                bid_hi = wide[("best_bid", hi)]
                ask_lo = wide[("best_ask", lo)]
            except KeyError:
                continue
            edge = (bid_hi - ask_lo
                    - 0.06 * bid_hi * (1 - bid_hi)
                    - 0.06 * ask_lo * (1 - ask_lo))
            viol = edge > 0                       # NaN buckets compare False
            if not viol.any():
                continue
            grp = (viol != viol.shift()).cumsum()
            for _, run in edge[viol].groupby(grp[viol]):
                # split at absent buckets: continuity means CONSECUTIVE
                # fresh buckets, not adjacency in a gappy index
                gaps = (pd.Series(run.index).diff().dt.total_seconds()
                        .gt(10.01).cumsum().values)
                for _, r2 in run.groupby(gaps):
                    dur = ((r2.index[-1] - r2.index[0]).total_seconds()
                           + 10.0)
                    if dur >= COHERENCE_PERSIST_S:
                        out.append(dict(event_slug=ev, mtype=mt, lo=lo,
                                        hi=hi, start=r2.index[0],
                                        seconds=dur,
                                        max_edge=float(r2.max())))
    return pd.DataFrame(out)


def m6_coherence(df: pd.DataFrame) -> None:
    hr("M6. LADDER COHERENCE INVARIANT (persistent executable violations = "
       "sick board or engine change, NEVER opportunity)")
    if not need(df, ["event_slug", "line"], "M6"):
        return
    frames = []
    tot = df[df.sports_market_type.astype(str).str.endswith("total")]
    if len(tot):
        frames.append(tot)
    spr = df[df.sports_market_type.astype(str).str.endswith("spread")].copy()
    if len(spr):
        # YES at line L = survivor claim (margin > -L) at its OWN price:
        # negate the line only, prices untouched.
        spr["line"] = -spr.line
        frames.append(spr)
    eps = pd.concat([coherence_violations(f) for f in frames],
                    ignore_index=True) if frames else pd.DataFrame()
    if len(eps) == 0:
        print("invariant HOLDS: zero persistent executable violations "
              f"(persistence bar {COHERENCE_PERSIST_S:.0f}s, both fees "
              "charged) — matches the WNBA invariant")
    else:
        print(f"VIOLATIONS: {len(eps)} persistent episodes — hand-verify the "
              f"first against raw rows (rule 15), then treat as VENUE ENGINE "
              f"CHANGE OR SICK BOARD; do not route to any candidate:")
        print(eps.head(20).to_string(index=False))


# --------------------------------------------------------------------------- #
# M7 — C3's record artifacts
# --------------------------------------------------------------------------- #

def m7_artifacts(df: pd.DataFrame, out: Path) -> None:
    hr(f"M7. DAY-ONE RECORD ARTIFACTS -> {out} (C3's list; ESPN join is "
       "recorder-side plumbing, deliberately not here)")
    out.mkdir(parents=True, exist_ok=True)
    two = df[df.best_bid.notna() & df.best_ask.notna()]

    first = (df.sort_values("captured_at").groupby("market_slug").first()
             .reset_index())
    if "line" in df.columns:
        lad = first[first.line.notna()].copy()
        lad["abs_line"] = lad.line.abs()
        cov = lad.groupby(["event_slug", "sports_market_type"]).agg(
            rungs=("line", "nunique"), lo=("line", "min"), hi=("line", "max"),
            min_abs_line=("abs_line", "min"))
        cov.to_csv(out / "ladder_coverage_at_listing.csv")
        print(f"ladder coverage at listing (B's seeded-gap check: WNBA had "
              f"18/34 boards with no rung near even) -> "
              f"ladder_coverage_at_listing.csv ({len(cov)} ladders)")
    first.to_csv(out / "first_appearance.csv", index=False)
    print(f"first appearance per market -> first_appearance.csv "
          f"({len(first)} markets)")

    fts = (two.sort_values("captured_at").groupby("market_slug")
           .captured_at.first().rename("first_two_sided_at"))
    fts.to_csv(out / "first_two_sided.csv")
    print(f"first two-sided time per rung -> first_two_sided.csv")

    d = df.sort_values(["market_slug", "captured_at"]).copy()
    d["two"] = d.best_bid.notna() & d.best_ask.notna()
    flip = d.two != d.groupby("market_slug").two.shift()
    events = d[flip & d.groupby("market_slug").cumcount().gt(0)]
    keep = [c for c in ("market_slug", "captured_at", "two", "event_period",
                        "event_score", "is_live") if c in d.columns]
    events[keep].to_csv(out / "book_events.csv", index=False)
    print(f"book death/revival transitions -> book_events.csv "
          f"({len(events)} events; rule 15 on the first one)")

    if "event_period" in df.columns:
        q2 = (two[two.event_period == "Q2"].sort_values("captured_at")
              .groupby("market_slug").last())
        q3 = (two[two.event_period == "Q3"].sort_values("captured_at")
              .groupby("market_slug").first())
        ht = pd.DataFrame({
            "q2_close_mid": (q2.best_bid + q2.best_ask) / 2,
            "q3_open_mid": (q3.best_bid + q3.best_ask) / 2}).dropna()
        ht.to_csv(out / "halftime_mids.csv")
        print(f"halftime boundary mids (D2's fields) -> halftime_mids.csv "
              f"({len(ht)} markets)")


# --------------------------------------------------------------------------- #
# Selftest — synthetic NBA-shaped listings (V29 slugs, half-point lines)
# --------------------------------------------------------------------------- #

def _syn_rows():
    base = pd.Timestamp("2026-10-20 23:00:00+00:00")
    rows = []
    mu, sigma = 222.5, 14.0
    for i, line in enumerate([200.5 + 4 * k for k in range(12)]):
        mid = 1.0 - stats.norm.cdf((line - mu) / sigma)
        for tick in range(3):
            rows.append(dict(
                market_slug=f"tsc-nba-det-bkn-2026-10-20-{line:g}".replace(
                    ".5", "pt5"),
                event_slug="nba-det-bkn-2026-10-20",
                sports_market_type="basketball_team_full_game_total",
                line=line, captured_at=base + pd.Timedelta(seconds=tick),
                best_bid=round(mid - 0.01, 4), best_ask=round(mid + 0.01, 4),
                event_period="Q2", event_score="30-28", is_live=True,
                fee_coefficient=0.06, book_tier="near" if i < 3 else None,
                raw=json.dumps({"bids": [{"price": round(mid - 0.01, 4),
                                          "size": 120.0}],
                                "asks": [[round(mid + 0.01, 4), 80.0]]})
                if i < 3 else None))
    return pd.DataFrame(rows)


def selftest() -> int:
    print("mutation test: every module on synthetic NBA-shaped listings")
    failures = 0

    def check(name, ok):
        nonlocal failures
        print(f"  {name} -> {'ok' if ok else 'FAIL'}")
        failures += 0 if not ok else 0
        failures += 0 if ok else 1

    df = _syn_rows()
    df["captured_at"] = pd.to_datetime(df.captured_at, utc=True)

    # M5: probit fit must recover the injected (mu, sigma) near-exactly.
    lad = df[df.captured_at == df.captured_at.min()]
    fit = probit_fit(lad.line, (lad.best_bid + lad.best_ask) / 2)
    check("sigma fit recovers mu=222.5 sigma=14",
          fit is not None and abs(fit[0] - 222.5) < 0.1
          and abs(fit[1] - 14.0) < 0.1)

    # M2: both raw shapes parse.
    b, a = parse_book_raw(df.raw.dropna().iloc[0])
    check("depth parser (dict + pair shapes)", b == 120.0 and a == 80.0)

    # M6: clean board holds; injected persistent executable violation fires;
    # a transient (< persistence bar) one does not. All three frames get
    # their ticks stretched to 0/15/30s so persistence is actually testable
    # (a 2s span passes ANY board vacuously — the first draft's clean and
    # transient cases were vacuous and masked a dominance-direction error).
    stretch = lambda d: d.assign(captured_at=d.captured_at + pd.to_timedelta(
        d.groupby("market_slug").cumcount() * 14, unit="s"))
    clean = coherence_violations(stretch(df))
    check("coherence: clean monotone board holds over 30s", len(clean) == 0)
    bad = stretch(df.copy())
    lines_sorted = sorted(bad.line.unique())
    lo, hi = lines_sorted[0], lines_sorted[1]
    # true violation: the HIGHER threshold's bid above the LOWER's ask
    bad.loc[bad.line == hi, "best_bid"] = 0.99
    bad.loc[bad.line == hi, "best_ask"] = 1.00
    viol = coherence_violations(bad)
    check("coherence: injected persistent violation detected",
          len(viol) >= 1)
    strangle = stretch(df.copy())
    # NORMAL band pricing (bid_lo far above ask_hi) must NOT be flagged —
    # the exact pattern the sign error mistook for 6,963 arbs
    check("coherence: a strangle is not an arb",
          len(coherence_violations(strangle)) == 0)
    trans = stretch(df.copy())
    first_tick = trans.groupby("market_slug").cumcount() == 0
    trans.loc[(trans.line == hi) & first_tick, "best_bid"] = 0.99
    check("coherence: transient violation NOT flagged",
          len(coherence_violations(trans)) == 0)

    # M3: fee deviation is caught.
    odd = df.copy()
    odd.loc[odd.index[:3], "fee_coefficient"] = 0.05
    per = odd.drop_duplicates("market_slug")
    check("fee deviation detected",
          (per.fee_coefficient.astype(float).round(6) != FEE_EXPECTED).any())

    # M0: slug<->line agreement machinery on V29-shaped slugs.
    slugline = df.market_slug.str.extract(r"(\d+)pt(\d)$")
    check("V29 slug parse (ptX)", slugline[0].notna().all())

    # M0 convention gate: a drifted line column must fail the gate; the
    # score-frame check must catch a flipped settlement.
    import contextlib
    import io
    drift = df.copy()
    drift["line"] = drift.line + 1.0            # slug says 200pt5, line 201.5
    with contextlib.redirect_stdout(io.StringIO()):
        g1 = m0_composition(drift)
    check("convention gate: slug/line drift fails",
          g1.get("slug_line_encoding") is False)
    spread_rows = pd.DataFrame([dict(
        market_slug="asc-nba-was-mia-2026-10-20-pos-3pt5",
        event_slug="nba-was-mia-2026-10-20",
        sports_market_type="basketball_team_full_game_spread", line=3.5,
        captured_at=df.captured_at.max(), best_bid=0.5, best_ask=0.52,
        event_period="Q4", event_score="100-98", is_live=True,
        fee_coefficient=0.06, book_tier=None, raw=None)])
    both = pd.concat([df, spread_rows], ignore_index=True)
    good = pd.DataFrame([dict(
        market_slug="asc-nba-was-mia-2026-10-20-pos-3pt5", settlement=1)])
    flipped = good.assign(settlement=0)
    with contextlib.redirect_stdout(io.StringIO()):
        g_ok = m0_composition(both, good)
        g_bad = m0_composition(both, flipped)
    check("convention gate: score frame verified on agreeing settlement",
          g_ok.get("score_frame") is True)
    check("convention gate: flipped settlement caught",
          g_bad.get("score_frame") is False)

    # M4: B's own instrument validation runs at our import (their rule-15
    # pair: planted co-move recovered, jitter null invents nothing).
    if CENSUS_OK:
        try:
            check("B's validate_lag_instrument()",
                  bool(census.validate_lag_instrument()))
        except Exception as exc:
            check(f"B's validate_lag_instrument() raised: {exc}", False)
        # Wiring check for the congestion callable: a tightly clustered
        # synthetic pool must read CLUSTERED through MY call path.
        if hasattr(census, "congestion_clustering"):
            base_t = pd.Timestamp("2026-10-20 23:00:00")
            clustered_pool = ([(base_t + pd.Timedelta(seconds=i), 6.0)
                               for i in range(12)]
                              + [(base_t + pd.Timedelta(hours=3), 0.5)])
            cc = census.congestion_clustering(clustered_pool)
            check("congestion wiring: clustered pool reads clustered",
                  cc is not None and cc["clustered"] is True)
        else:
            print("  congestion_clustering absent — M4 will run DEGRADED "
                  "(land B's aedced3)")
    else:
        print("  census module unavailable — lag validation SKIPPED "
              "(M1/M4 degraded); land B's b9c380f")

    print(f"mutation test: "
          f"{'ALL OK' if failures == 0 else f'{failures} FAILURES'}")
    return failures


# --------------------------------------------------------------------------- #

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshots", type=Path)
    ap.add_argument("--resolved", type=Path, default=None,
                    help="resolved-outcomes CSV; activates the score-frame "
                         "convention check as settlements land")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if args.snapshots is None:
        print("need --snapshots (market_snapshots-shaped CSV/CSV.GZ export); "
              "--selftest runs without data")
        return 2

    print("NBA day-one market-quality survey (launch policy clause 2)")
    print(f"input: {args.snapshots}")
    print("reproduce: .venv/bin/python analysis/nba_day_one_survey.py "
          "--snapshots <export> [--out DIR]")
    if selftest() != 0:
        print("ABORT: mutation test failed; the survey must not read a real "
              "board through a broken instrument")
        return 1

    df = pd.read_csv(args.snapshots)
    df["captured_at"] = pd.to_datetime(df.captured_at, utc=True,
                                       format="ISO8601")
    if "is_live" in df.columns and df.is_live.dtype != bool:
        df["is_live"] = (df.is_live.astype(str).str.lower()
                         .map({"t": True, "true": True, "1": True,
                               "f": False, "false": False, "0": False})
                         .fillna(False))
    resolved = pd.read_csv(args.resolved) if args.resolved else None

    gate = m0_composition(df, resolved)
    m1_spreads(df)
    m2_depth(df, args.out)
    m3_fees(df)
    m4_lags(df)
    m5_sigma(df)
    m6_coherence(df)
    if args.out is not None:
        m7_artifacts(df, args.out)
    else:
        print("\n(--out not given: C3 record artifacts NOT written — on "
              "listing day this is not optional)")

    hr("STANDING STATEMENTS")
    print("Shadow only (launch policy clause 1). Rule 15: the first real "
          "episode of anything above gets hand-verified against raw rows "
          "before its module's numbers are quoted. WNBA verdicts port as "
          "registrations, never as evidence (clause 3).")
    print("\nNo in-sample result justifies capital. The forward test is the "
          "evidence.")
    failed = [k for k, v in gate.items() if not v]
    if failed:
        print(f"\nCONVENTION GATE FAILED: {failed} — the venue's live NBA "
              f"conventions drifted from the assumptions this survey (and "
              f"B's triangle math) were built on. NOTHING above is safe to "
              f"quote until the mismatch is resolved in daylight.")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
