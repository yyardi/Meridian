"""QUOTE v2 — the round-trip ledger and the branch-keyed arm scaffolding.

Manager's ticket (2026-09-02). **OFF THE LIVE PATH. Nothing here deploys.**
The live v1 quoter's policy is FROZEN until A1's gate reads: v2's central
premise (quote only in reverting states) IS the A1 hypothesis, null-favored,
and changing WHICH states get quoted before the read turns the cohort into
selection and kills the non-revert comparison leg. So the arms here are
evaluated by REPLAY over the recorded v1 quote stream (subset-scoring of fills
that already happened) — never by touching what the running engine quotes.

Division of labour (agreed with Quant D, 2026-09-02):
* **D owns the markout core** — `analysis/quote_v2_markout.py`: `markouts()`
  (per-fill side-signed markout at +30s/+2m/+10m, gap-capped, coverage
  counted) and `rule16_gate()` (reproduces v1's ledgered −1.60¢ [−1.69,−1.50]
  net-capture over all 17,032 in-game fills, clustered by game, fails closed).
  This module CONSUMES both; it never reimplements markout, and it never
  re-gates rule 16 — it consumes fills that passed D's gate or calls it.
* **This module owns** the ledger schema, round-trip inventory P&L (settlement
  basis, distinct from D's net-capture markout basis — labelled, never mixed),
  and the arm scaffolding + its selftests.
* **Blessed primitives, imported never reimplemented:** clustering =
  `core.quote.adverse_selection.clustered_mean` (games are the clusters);
  per-fill scoring = `core.quote.report.score_fill` and `net_capture_mark`.
* **Shared classifier:** the A1 vol-character labeller
  (`analysis/a1_oscillation_descriptive.py`, frozen constants BAR=2s,
  WINDOW=120s, k=6, revert<0.8/trend>1.2) is imported here for v2-STATE AND by
  D's M2 post-mortem — one classifier, so the arm cells and the post-mortem
  cells are the SAME cells by construction.

THE ARMS (branch-keyed, NEVER bundled — the research agent's non-negotiable:
a bundle that wins attributes nothing, a bundle that loses kills four ideas at
once). Each arm is one pre-declared lever; the A1 gate's read selects the
branch:

* A1-PASS  -> **v2-STATE**: quote only where char==revert AND guard-clean AND
              uncongested.
* A1-FAIL  -> the other measured levers, each its own arm:
  * **v2-CONGESTION** — do not quote inside B's clustered slow windows.
  * **v2-WIDTH** — quote no tighter than measured adverse selection + margin
    (arithmetic from v1's own ledger; the manager's tight-loses/wide-wins seed
    points here).
  * **v2-GUARD** — refuse to quote in states the PULSE guards flag
    (`core.pulse.guards`, ported to a refuse-to-quote path).

**Arm THRESHOLDS are pinned by the registration (rule 11), not here.** The
constants below are the scaffolding's declared knobs, marked PENDING; they are
set from D's post-mortem cuts + the landed registration before any real read.

The optimism caveat carried from v1 (docs/math/quote-shadow.md): the fill rule
undercounts exactly the fills that hurt, so every capture/P&L number here is an
upper bound — a measured loss is trustworthy, a measured profit authorises
nothing.

FORWARD v2 FILL SCHEMA — required, cheap now, IMPOSSIBLE retroactively
(D's request, 2026-09-02): when the v2 quoter deploys (post-A1-read), each
recorded fill MUST carry, beyond v1's columns:
  * ``game_start_time`` — enables the pregame hours-to-tip partition; D1's
    dead-window fold is undecidable without it.
  * the quoter's STATE SNAPSHOT AT QUOTE TIME — event_period, event_score,
    minutes_left/clock, **clock quality (minutes_left_is_estimate), and the
    fair value if any** — so the lateness/state arms and, critically, the GUARD
    arm become scorable. Guards are on the BUILD LIST (not v1-scorable:
    estimated clock defeats guard 1, guard 2 needs fv); carrying fv +
    clock-quality on every v2 quote row is THE NAMED ENGINEERING TRIGGER that
    returns guards to the arm list (manager). This is this module's build
    obligation for the v2 quoter's storage.
The v1 pin cannot be backfilled with these; they are a build requirement for
the v2 quoter's storage model, to be laid down BEFORE it records its first
forward fill. Documented here so it cannot be forgotten at deploy.

ARM RE-SPEC INPUT from D's calibrated post-mortem (b952c9e) — arm definitions
are the registration's (rule 11); this is the design input feeding it:
  * **Lateness is the loss concentration** (Q4 −3.00c vs −1.3/−1.4 early;
    every spread band worsens late). The strongest measured lever is a
    late-state filter, not character.
  * **Character is FLAT on at-fill capture** (revert −1.70 / trend −1.57 /
    rw −1.52) — at-fill adverse selection does not discriminate on character
    even though trip P&L (A1) does. A character-keyed QUOTING arm has no
    at-fill support; the A1 gate remains the forward test of the trip-P&L claim.
  * **v2-WIDTH folds or is redefined** (see the constant above).
  * **v2-PATIENCE — requote-into-the-dip** (the sharpest input, now LIVE): an
    arm that holds briefly after a fill, or requotes at the pre-fill mid rather
    than chasing the post-fill dip, has ~0.8c/fill of measured not-losing
    available (+10m markout −0.63 [−1.27, +0.02]; ~40% of at-fill loss is
    transient). PRECONDITION MET (D M4 405ef34): v1's requote-into-dip rate is
    82.2% [79.0, 85.3], so the lever is real and the 0.8c is not already in the
    −1.60; and dip-born vs reverted-birth captures OVERLAP (−1.52 vs −1.63), so
    it is a post-fill BEHAVIOUR effect — a requote-replay arm, never a subset.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from core.quote.adverse_selection import ClusteredMean, clustered_mean
from core.quote.report import net_capture_mark, score_fill
from core.quote.storage import ASK, BID

ROOT = Path(__file__).resolve().parent.parent
PIN = "20260902T161223Z"
EXPORTS = Path(os.environ.get("MERIDIAN_EXPORTS_DIR", ROOT / "backups" / "exports"))
FILLS = EXPORTS / f"quote_fills_v1_{PIN}.csv"

#: Maker fills pay theta_maker = 0 (V9/C7); v1 rests and never crosses, so the
#: venue fee on every recorded fill is 0. Carried as a parameter so a future
#: taker-close arm can set it, never hard-zeroed.
FEE_PER_CONTRACT = 0.0

# ---- arm knobs: PENDING the registration (rule 11) ------------------------ #
# v2-WIDTH IS REMOVED (manager, ahead of registration): on the v1 tape width
# was itself state-driven, so width and state are confounded BY THE QUOTING
# POLICY THAT GENERATED THE DATA — no observational read of this tape can
# identify a width effect. A width arm needs EXOGENOUS width variation (a
# policy varying width within state, pre-declared) — a v2.1 design, never a v1
# measurement. Not scaffolded here on purpose.
#
#: v2-STATE / LATENESS (primary): lateness is the measured loss concentration
#: (D b952c9e: Q4 −3.00c vs −1.3/−1.4 early). "Late" = minutes_left at or below
#: this, OR Q4. Threshold PENDING the registration.
LATENESS_MINUTES_LEFT = None            # PENDING registration
#: v2-CONGESTION (second): the arm's object is B's REGISTERED self-clocked
#: causal detector, `analysis/congestion_detector.py` @ d1fb6de — imported, not
#: reinvented. NOT the earlier "≥5s lag / 30s window" lag-statistic (that was a
#: retrospective clustering statistic, in-sample mechanism evidence, never the
#: gate — program doc, B's refutation). The causal rule: trigger move ≥3¢ on a
#: rung, UNRESOLVED by a same-ladder response ≥2¢ within 5s, opens a venue-
#: pooled window [t0+5s, t0+35s). The window OPENS AT CONFIRM (t0+5s), so a
#: predicate keyed at fill time reads no future — keying at TRIGGER time is the
#: lookahead bug B's mutation test exists to catch. `congested` is set in
#: assemble_ledger from B's `windows_from_frame` (same code path as the
#: streaming `CongestionDetector.feed`, so scorer and engine cannot diverge).
#: Detector constants live in congestion_detector.py; nothing to pin here.
#: v2-PATIENCE (third): requote-into-the-dip is a measured cost (post-fill mid
#: reverts +0.76→+0.90c; ~0.8c/fill not-losing available). PRECONDITION MET —
#: D's M4 (quote_v2_markout.py @ 405ef34): v1's requote-into-dip rate is
#: 82.2% [79.0, 85.3] clustered (G=13), so v1 released the lever constantly and
#: the 0.8c is NOT already in the −1.60 — the arm is LIVE, not vacuous. And it
#: is a BEHAVIOUR effect not a selection effect: dip-born vs reverted-birth
#: captures OVERLAP (−1.52 vs −1.63), so a fill-subset scoring would read it as
#: nothing — PATIENCE must be a requote-REPLAY (hold briefly / requote at the
#: pre-fill mid), which is why it is a distinct arm type below, not a predicate.
PATIENCE_ENABLED = True                 # precondition met (D M4 405ef34;
#                                         quote_v2_markout.py landed at 282ab2f)
#: The requote-replay's rule parameters — PENDING the registration (rule 11):
#: how long to hold after a fill before requoting, and whether to requote at the
#: pre-fill mid rather than chasing the post-fill mid.
PATIENCE_HOLD_SECONDS = None            # PENDING registration
PATIENCE_REQUOTE_AT_PREFILL_MID = None  # PENDING registration

REVERT = "revert"


# --------------------------------------------------------------------------- #
# Round-trip inventory P&L — settlement basis (MINE; net-capture is D's basis)
# --------------------------------------------------------------------------- #

@dataclass
class InventoryPnl:
    """Round-trip inventory P&L to settlement, per contract, game-clustered.

    A filled bid is a unit LONG YES opened at quote_price and closed at
    settlement (money at price, C11); a filled ask is a unit SHORT YES. P&L per
    fill = returned − staked − fee. This is the SETTLEMENT basis — the economic
    round trip (open at the quote, close when the market pays) — and is a
    different number from D's net-capture-at-fill markout basis; the two are
    never summed.
    """

    per_fill: ClusteredMean | None      # mean P&L/contract, game-clustered
    total_usd: float                    # summed realised inventory P&L
    n_fills: int
    n_games: int


def inventory_pnl(fills: pd.DataFrame, *, fee: float = FEE_PER_CONTRACT
                  ) -> InventoryPnl:
    """Settlement-basis round-trip P&L over the settled fills in `fills`."""
    df = fills[fills.settlement.isin([0, 1])].copy()
    by_game: dict[str, list[float]] = {}
    total = 0.0
    for r in df.itertuples():
        staked, returned = score_fill(side=r.side, quote_price=float(r.quote_price),
                                      settlement=int(r.settlement))
        pnl = returned - staked - fee
        by_game.setdefault(str(r.game_id), []).append(pnl)
        total += pnl
    return InventoryPnl(
        per_fill=clustered_mean(by_game),
        total_usd=total,
        n_fills=len(df),
        n_games=len(by_game),
    )


def net_capture(fills: pd.DataFrame) -> ClusteredMean | None:
    """v1's net-capture-at-fill mark, game-clustered — the rule-16 anchor's
    basis. Imported computation (`net_capture_mark`), clustered by game. This
    does NOT re-run D's rule16_gate; it is the same quantity for slicing."""
    by_game: dict[str, list[float]] = {}
    for r in fills.itertuples():
        c = net_capture_mark(side=r.side, quote_price=float(r.quote_price),
                             mid_at_fill=float(r.mid_at_fill))
        by_game.setdefault(str(r.game_id), []).append(c)
    return clustered_mean(by_game)


# --------------------------------------------------------------------------- #
# The interpretation matrix — emit BOTH coordinates per character, so the cell
# is a lookup, never an argument constructed after the numbers exist (manager).
# --------------------------------------------------------------------------- #
#
#   A1-PASS x capture-flat          -> revert edge is ROLL economics; v2-STATE
#                                      quotes for the TRIP, not the capture.
#   A1-PASS x capture-discriminates -> full state-conditional maker (strongest).
#   A1-FAIL x capture-flat          -> classifier dead for making; fall to
#                                      CONGESTION / PATIENCE.
#   A1-FAIL x capture-discriminates -> capture-basis quoting only; trip dead.
#
# ROW axis  = A1-PASS/FAIL: the A1 gate's TRIP-economics read per character
#             (forward, on the quote engine's real fills — pending the gate).
# COLUMN axis = capture-flat/discriminates: the AT-FILL capture read per
#             character on the quote fills (computable now; D found it flat:
#             revert −1.70 / trend −1.57 / rw −1.52).
# This module emits the column coordinate; the A1 gate supplies the row.

def matrix_coordinates(ledger: pd.DataFrame) -> dict[str, dict]:
    """Per-character coordinates for the interpretation matrix. `ledger` must
    carry a `character` column (from the A1 classifier at quote time). Emits,
    per character, the at-fill CAPTURE read (net_capture, the column axis) and
    the inventory P&L, both game-clustered. The trip-economics ROW axis is the
    A1 gate's read, joined in when it lands — not manufactured here."""
    if "character" not in ledger.columns:
        raise ValueError("ledger not enriched with `character`; run "
                         "assemble_ledger first")
    out = {}
    for ch in ("revert", "rw", "trend"):
        sub = ledger[ledger.character == ch]
        out[ch] = {
            "n": len(sub),
            "at_fill_capture": net_capture(sub),          # COLUMN coordinate
            "inventory_pnl": inventory_pnl(sub).per_fill,
        }
    return out


# --------------------------------------------------------------------------- #
# The arm scaffolding — branch-keyed replay predicates, never bundled
# --------------------------------------------------------------------------- #

A1_PASS = "A1-PASS"
A1_FAIL = "A1-FAIL"


@dataclass(frozen=True)
class Arm:
    """One pre-declared lever. `keeps(row)` is the replay predicate: given a
    v1 fill enriched with its quote-time state cells, would this arm have rested
    the quote that produced it? Scoring runs on the kept subset ONLY, per arm,
    never bundled."""

    name: str
    branch: str                         # A1_PASS | A1_FAIL
    keeps: "callable"
    detail: str


def _is_late(row) -> bool:
    if getattr(row, "period", None) == "Q4":
        return True
    if LATENESS_MINUTES_LEFT is None:
        return False                    # threshold pending; Q4 is the safe part
    ml = getattr(row, "minutes_left", None)
    return ml is not None and ml <= LATENESS_MINUTES_LEFT


def _state_keeps(row) -> bool:
    # v2-STATE / LATENESS (primary, A1-PASS branch): quote only reverting,
    # guard-clean, uncongested, and NOT late (lateness is the loss
    # concentration, D b952c9e).
    return (row.character == REVERT
            and not row.guard_flagged
            and not row.congested
            and not _is_late(row))


def _congestion_keeps(row) -> bool:
    # v2-CONGESTION (A1-FAIL branch): quote everywhere EXCEPT B's slow windows.
    return not row.congested


# v2-GUARD is NOT an arm on this substrate (manager -> BUILD LIST): the v1 pin
# lacks the state fields the guards need (estimated clock defeats guard 1,
# guard 2 needs fv). It returns as an arm once the v2 quoter RECORDS fv +
# clock-quality per quote row (the named engineering trigger, this module's
# forward-schema requirement). Predicate kept for when that lands.
def _guard_keeps(row) -> bool:
    return not row.guard_flagged


ARMS: dict[str, Arm] = {
    "v2-STATE": Arm("v2-STATE", A1_PASS, _state_keeps,
                    "quote only revert + guard-clean + uncongested + not-late"),
    "v2-CONGESTION": Arm("v2-CONGESTION", A1_FAIL, _congestion_keeps,
                         "skip B's clustered slow windows (>=5s lag / 30s)"),
    # v2-PATIENCE (A1-FAIL) is LIVE (PATIENCE_ENABLED, D M4 405ef34) but a
    # BEHAVIOUR-change arm, not a subset predicate — it is intentionally absent
    # from this subset-predicate registry and scored by requote-replay (below).
}


@dataclass(frozen=True)
class PatienceArm:
    """v2-PATIENCE: a requote-REPLAY arm, not a fill subset. It re-derives what
    v1's fills would have been under a patient requote rule (hold briefly after
    a fill, or requote at the pre-fill mid rather than chasing the post-fill
    dip) and re-scores. The 0.8c/fill lives in post-fill BEHAVIOUR (dip-born
    −1.52 vs reverted-birth −1.63 overlap, D M4), so subset-selection reads it
    as nothing — the replay is the only instrument that sees it. The replay's
    exact rule (hold seconds / pre-fill-mid) is the registration's (rule 11);
    the replay itself needs the tick tape and lands with assemble_ledger's
    requote path."""

    name: str = "v2-PATIENCE"
    branch: str = A1_FAIL
    enabled: bool = bool(PATIENCE_ENABLED)
    detail: str = "requote-replay: hold / requote at pre-fill mid, ~0.8c target"


@dataclass
class ArmScore:
    arm: str
    branch: str
    n_kept: int
    n_games: int
    inventory: InventoryPnl
    net_capture: ClusteredMean | None
    #: markout_{h} clustered means, filled from D's markout columns when the
    #: enriched ledger carries them; empty until then.
    markout: dict[str, ClusteredMean | None]


def score_arm(ledger: pd.DataFrame, arm: Arm) -> ArmScore:
    """Score ONE arm on its kept subset. Never bundles arms. `ledger` is the
    enriched per-fill frame (v1 fills + state cells + optionally D's markout_{h}
    columns)."""
    kept = ledger[ledger.apply(arm.keeps, axis=1)].copy()
    markout = {}
    for col in [c for c in kept.columns if c.startswith("markout_")]:
        by_game: dict[str, list[float]] = {}
        for r in kept.dropna(subset=[col]).itertuples():
            by_game.setdefault(str(r.game_id), []).append(float(getattr(r, col)))
        markout[col] = clustered_mean(by_game)
    return ArmScore(
        arm=arm.name, branch=arm.branch, n_kept=len(kept),
        n_games=kept.game_id.nunique(),
        inventory=inventory_pnl(kept), net_capture=net_capture(kept),
        markout=markout,
    )


# --------------------------------------------------------------------------- #
# Ledger assembly — enrich v1 fills with state cells + D's markouts
# --------------------------------------------------------------------------- #

def assemble_ledger(fills: pd.DataFrame, *, tick_path: Path | None = None
                    ) -> pd.DataFrame:
    """Enrich the pinned v1 fills into the scoring ledger.

    Adds, per fill:
      * `mid_{h}` / `markout_{h}` — D's markouts() (`analysis.quote_v2_markout`,
        side-signed, GAP_CAP_S=120, NaN where a horizon runs past coverage;
        coverage is counted, never dropped);
      * `character` — the A1 vol classifier at QUOTE time (the shared
        `analysis.a1_oscillation_descriptive` at its frozen constants), so the
        v2-STATE cells and D's post-mortem cells are the same cells;
      * `congested` — the GATE flag — is ABSENT in sample (so
        `_congestion_keeps` fail-closes). B's causal detector must run on the
        QUOTER'S OWN observation stream at its own cadence/stamps
        (registration); v1 recorded no such stream, and the recorder tick tape
        (200ms, recorder stamps) is the forbidden cross-process clock AND
        over-fires (90.6% of fills / 75% of game time vs D's ~46%). A labelled
        `congested_recorder_proxy` is recorded for diagnostics only; the gate
        flag awaits the forward v2 quoter's own observation stream.
      * `guard_flagged` — PENDING the forward v2 fill schema (needs fv +
        clock-quality per quote row; not on the v1 pin). Left ABSENT —
        `_guard_keeps` scores only once the v2 quoter records those fields.

    Dependencies imported lazily so the inventory/arm/matrix selftests run
    without loading the tape.
    """
    import duckdb

    from analysis import a1_oscillation_descriptive as a1
    from analysis import quote_v2_markout as mko

    df = fills.copy()
    for col in ("quoted_at", "filled_at"):
        df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")

    tp = Path(tick_path) if tick_path is not None else a1.TICKS
    markets = sorted(df.market_slug.dropna().unique().tolist())

    # 1. markouts (D) — side-signed per-fill markout at +30s/+2m/+10m.
    con = duckdb.connect()
    try:
        con.execute("SET timezone='UTC'")
        mko.load_ticks(con, tp, markets)
        df = mko.markouts(con, df)
    finally:
        con.close()

    # 2. character (A1 classifier at quote time) — the shared labeller.
    bars, slug2game = a1.load_bars()
    df["character"] = [
        a1.character(a1.vr_at(bars[m], t)) if m in bars else "na"
        for m, t in zip(df.market_slug, df.quoted_at)
    ]

    # 3. congestion — the GATE flag (`congested`) is intentionally ABSENT in
    #    sample so `_congestion_keeps` fail-closes. B's causal detector must be
    #    fed the QUOTER'S OWN observation stream at the quoter's cadence with
    #    its own stamps (registration); v1 never recorded that stream, and
    #    feeding the RECORDER tick tape instead (200ms, recorder stamps) is the
    #    cross-process-timestamp usage B's registration explicitly forbids. It
    #    also over-fires badly at 200ms: 90.6% of in-game fills / 75% of game
    #    TIME congested (vs D's ~46% lag-statistic) — a cadence/stamp artifact,
    #    NOT the gate. Recorded ONLY as a labelled proxy for diagnostics; the
    #    real `congested` awaits the forward v2 quoter's own observation stream.
    from analysis import congestion_detector as cg
    raw = pd.read_csv(
        tp, usecols=["event_slug", "market_slug", "sports_market_type",
                     "captured_at", "best_bid", "best_ask"])
    # Hand B's detector tz-NAIVE UTC datetimes: windows_from_frame does its own
    # int64-ns normalization (the ns-hazard note), which requires naive.
    raw["captured_at"] = (pd.to_datetime(raw.captured_at, utc=True,
                                         errors="coerce").dt.tz_localize(None))
    raw = raw.dropna(subset=["captured_at"])
    windows_by_game = {game: cg.windows_from_frame(g)
                       for game, g in raw.groupby("event_slug")}
    fill_game = df.market_slug.map(slug2game)
    fsec = (df.filled_at - pd.Timestamp("1970-01-01", tz="UTC")).dt.total_seconds()
    df["congested_recorder_proxy"] = [
        any(a <= t < b for a, b in windows_by_game.get(gm, []))
        for gm, t in zip(fill_game, fsec)
    ]
    # `congested` (gate) and `guard_flagged` intentionally absent — see docstring.
    return df


# --------------------------------------------------------------------------- #
# Selftests — rule 15 (jitter-null) + arm predicates + inventory known-answer
# --------------------------------------------------------------------------- #

def _synthetic_fills(rng, n_games=8, per_game=40, edge=0.0):
    """Synthetic settled fills. `edge` shifts settlement toward the maker's
    favour per contract (0 = null)."""
    rows = []
    for g in range(n_games):
        for _ in range(per_game):
            side = BID if rng.random() < 0.5 else ASK
            q = float(rng.uniform(0.30, 0.70))
            # null: settlement independent of the quote (fair coin at the mid)
            p_yes = min(max(q + (edge if side == BID else -edge), 0.01), 0.99)
            sett = int(rng.random() < p_yes)
            rows.append({"game_id": f"g{g}", "side": side, "quote_price": q,
                         "mid_at_fill": q + rng.normal(0, 0.01),
                         "settlement": sett})
    return pd.DataFrame(rows)


def _selftest():
    rng = np.random.default_rng(20260902)

    # rule 15 — JITTER-NULL: settlement independent of the quote -> inventory
    # P&L clustered CI includes zero (the instrument does not manufacture edge).
    null = _synthetic_fills(rng, edge=0.0)
    inv = inventory_pnl(null)
    assert inv.per_fill is not None and not inv.per_fill.excludes_zero, \
        f"null inventory P&L excluded zero: {inv.per_fill}"

    # and PERMUTING settlement across fills within game destroys any edge ->
    # still ~0 (the second jitter-null form).
    shuffled = null.copy()
    shuffled["settlement"] = (shuffled.groupby("game_id").settlement
                              .transform(lambda s: rng.permutation(s.values)))
    inv_s = inventory_pnl(shuffled)
    assert not inv_s.per_fill.excludes_zero

    # known-answer (mine, hand-computed): a bid at 0.40 that settles 1 earns
    # +0.60; an ask at 0.40 that settles 0 earns +0.40. Two games so the
    # clustered mean is defined.
    ka = pd.DataFrame([
        {"game_id": "a", "side": BID, "quote_price": 0.40, "mid_at_fill": 0.40,
         "settlement": 1},
        {"game_id": "b", "side": ASK, "quote_price": 0.40, "mid_at_fill": 0.40,
         "settlement": 0},
    ])
    ik = inventory_pnl(ka)
    assert abs(ik.total_usd - (0.60 + 0.40)) < 1e-9, ik.total_usd

    # injected EDGE recovers positive (the needle moves).
    strong = _synthetic_fills(rng, edge=0.08)
    assert inventory_pnl(strong).per_fill.mean > 0

    # arm predicates on synthetic enriched rows — each keeps the right states.
    Row = lambda **k: type("R", (), k)
    base = dict(character="revert", guard_flagged=False, congested=False,
                period="Q2", minutes_left=15.0)
    assert _state_keeps(Row(**base))
    assert not _state_keeps(Row(**{**base, "character": "trend"}))
    assert not _state_keeps(Row(**{**base, "guard_flagged": True}))
    assert not _state_keeps(Row(**{**base, "congested": True}))
    # lateness: Q4 is late even with the threshold unpinned (the safe part).
    assert not _state_keeps(Row(**{**base, "period": "Q4"}))
    assert _congestion_keeps(Row(congested=False))
    assert not _congestion_keeps(Row(congested=True))
    # v2-WIDTH is gone (confounded on this tape); assert it is not an arm.
    assert "v2-WIDTH" not in ARMS and "v2-GUARD" not in ARMS
    assert set(ARMS) == {"v2-STATE", "v2-CONGESTION"}
    # v2-PATIENCE is LIVE but a behaviour-change arm — not in the subset
    # registry, and its precondition is resolved to enabled (D M4).
    assert "v2-PATIENCE" not in ARMS and PatienceArm().enabled is True

    # interpretation matrix: emits per-character coordinates from an enriched
    # ledger; the injected revert-favourable capture shows up as the column.
    enr = null.copy()
    enr["character"] = ["revert", "rw", "trend"] * (len(enr) // 3) + \
        ["revert"] * (len(enr) % 3)
    mx = matrix_coordinates(enr)
    assert set(mx) == {"revert", "rw", "trend"}
    assert all("at_fill_capture" in mx[c] for c in mx)

    # shadow-only, structurally (the v1 guarantee carried into v2): this module
    # has NO import path to the executor or the venue order client.
    import ast
    tree = ast.parse(Path(__file__).read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            imported.update(f"{node.module}.{a.name}" for a in node.names)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    for forbidden in ("core.executor", "core.fill_watcher",
                      "core.polymarket.client.PolymarketOrderClient",
                      "core.polymarket.client.PolymarketAuthedClient"):
        assert forbidden not in imported, f"v2 ledger imports {forbidden}"

    print("selftest: PASSED (rule-15 jitter-null x2; inventory known-answer; "
          "edge recovery; arm predicates incl. lateness; ARMS == "
          "{v2-STATE, v2-CONGESTION} (WIDTH/GUARD removed); matrix coordinates; "
          "shadow-only AST clean)")


def main():
    _selftest()
    if not FILLS.exists():
        print(f"pinned fills not found at {FILLS} — selftests only.")
        return
    fills = pd.read_csv(FILLS)
    ig = fills[fills.regime == "ingame"]
    print(f"v1 pinned fills: {len(fills)} ({len(ig)} ingame / "
          f"{ig.game_id.nunique()} games)")
    inv = inventory_pnl(ig)
    print(f"v1 in-game inventory P&L (settlement basis): "
          f"total ${inv.total_usd:+.2f}, per-fill "
          f"{inv.per_fill.mean:+.4f} [{inv.per_fill.lo:+.4f}, "
          f"{inv.per_fill.hi:+.4f}] over {inv.n_games} games")
    nc = net_capture(ig)
    print(f"v1 in-game net-capture (D's rule-16 basis, sliced here): "
          f"{nc.mean*100:+.2f}c [{nc.lo*100:+.2f}, {nc.hi*100:+.2f}] "
          f"(D's rule16_gate is the authority)")


if __name__ == "__main__":
    main()
