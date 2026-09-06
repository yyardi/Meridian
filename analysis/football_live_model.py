"""Football live model: market mid as a FEATURE, not an opponent.

Architecture per d5's survey — nflfastR and CFBD both take the market as an
input. PULSE was built the other way, as a rival estimate diffed against the
price, and that is why its disagreements are stale rather than informed. Here
the model predicts the OUTCOME given the mid *and* the state, and the edge is
wherever it moves the mid after seeing state the market has not repriced.

    features = market mid  +  game state
    target   = settlement
    edge     = model_p − mid, on the fills the model would actually take

## ★ THE TRAINING SET IS EMPTY TODAY, AND THAT IS MEASURED NOT ASSUMED

    espn_cfb_game_state   50 games   2026-09-05 22:08Z -> 09-06 16:08Z
    CFB price tape        48 games   2026-09-03 21:51Z -> 09-05 20:51Z

    games sharing an id via cfb_game_map        12
    games with ANY TEMPORAL OVERLAP              0

The price recorder died 09-05 22:08Z — 77 minutes after its tape ends — and the
state recorder started at that same instant. **They have never been live
together.** Twelve games match by id and none of them share a single second, so
there is no (market, time) carrying both a price and a state.

**The venue tape was restored 2026-09-06 20:43Z. Tonight's 23:30Z slate is the
first moment both recorders run simultaneously in this programme's history.**
This file is the harness, written now so the fit is push-button when that data
lands rather than started from scratch on Saturday.

## ★ POWER, STATED BEFORE ANY FIT

Money half-width was **6.216pp at G=34** on the existing scorer. Scaling
1/sqrt(G):

    G= 50   half-width ~5.13pp
    G=100   half-width ~3.62pp
    G=282   half-width ~2.16pp   <- first point it resolves the 2.69pp taker bar

**At 50 games only an effect above ~5pp is resolvable.** The measured PULSE
filled-arm effect was +4.76pp and did not clear zero at G=34; it would not clear
at G=50 either. **So a single slate cannot establish this model earns money.**
What a single slate CAN do is falsify it — a large negative is detectable — and
establish the pipeline end to end.

That is stated here so a null on Saturday is read as underpowered rather than as
a verdict, and a positive is read as needing replication.

## The benchmark, which is the first external one this programme has had

`espn_cfb_game_state.espn_home_win_pct` is on the same rows, 96.7% present.
**If the model cannot beat ESPN's public number on ESPN's own data, that is the
result** and it should be reported as such rather than tuned away.

## Scoring

**Money, not Brier** — money is linear in edge where Brier squares it, so the
same target costs ~182 games rather than ~15,400. Uses the committed
`analysis/pulse_money_scorer.py` convention: side-signed price difference,
filled rows only, cluster-robust sandwich with t at df=G-1 and the G/(G-1)
correction, clusters are games, row-weighted.

## Held out BY GAME, never by row

`GroupKFold(groups=game_id)`. A row-level split puts the same game on both
sides and every score is leakage — the outcome is shared by every row in a game.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import GroupKFold

from core.quote.adverse_selection import clustered_mean

STATE = "backups/exports/espn_cfb_game_state_20260906T174104Z.csv.gz"
GAMEMAP = "backups/exports/cfb_game_map_20260906T174104Z.csv.gz"

#: Available today. possession / down / distance / yard_line are NOT stored —
#: they are the core of every public football WP model, they are in the ESPN
#: summary we already fetch, and D is adding them. The spec below is written so
#: they slot in without restructuring.
FEATURES_NOW = ["mid", "period", "clock_seconds", "margin", "total_so_far",
                "home_timeouts_used", "away_timeouts_used",
                "live_spread", "live_over_under"]
FEATURES_PENDING = ["possession_is_home", "down", "distance", "yard_line"]


def clock_seconds(display_clock: str, period) -> float | None:
    """ESPN gives 'MM:SS' within a period. Returns seconds left in the GAME."""
    try:
        m, s = str(display_clock).split(":")
        left_in_period = int(m) * 60 + float(s)
    except Exception:
        return None
    try:
        p = int(period)
    except Exception:
        return None
    return left_in_period + max(4 - p, 0) * 15 * 60


def load_joined(price_csv: str) -> pd.DataFrame:
    """Join the venue price tape to ESPN state through cfb_game_map.

    Returns an empty frame when the two recorders never overlapped, which is
    the state of the world before 2026-09-06 20:43Z.
    """
    S = pd.read_csv(STATE)
    M = pd.read_csv(GAMEMAP)
    P = pd.read_csv(price_csv)
    S["t"] = pd.to_datetime(S.first_seen_at, utc=True, format="ISO8601", errors="coerce")
    P["t"] = pd.to_datetime(P.captured_at, utc=True, format="ISO8601", errors="coerce")
    vm = dict(zip(M.venue_game_id.astype(str), M.espn_game_id.astype(str)))
    P["espn"] = P.game_id.astype(str).map(vm) if "game_id" in P else None
    S["clock_seconds"] = [clock_seconds(c, p) for c, p in zip(S.display_clock, S.period)]
    S["margin"] = S.home_score - S.away_score
    S["total_so_far"] = S.home_score + S.away_score
    # BACKWARD JOIN ONLY: nearest state at or before the price stamp. A forward
    # join imports the future, which is the look-ahead defect diagnosed on the
    # horizon ladder.
    out = []
    for espn, px in P.dropna(subset=["espn"]).groupby("espn"):
        st = S[S.game_id.astype(str) == str(espn)].sort_values("t")
        if st.empty:
            continue
        j = pd.merge_asof(px.sort_values("t"), st, on="t", direction="backward")
        out.append(j)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def fit_and_score(d: pd.DataFrame, features: list[str], n_splits: int = 5):
    """Out-of-fold model probability, held out by game. Returns d with `model_p`."""
    d = d.dropna(subset=features + ["y"]).copy()
    if d.game_id.nunique() < n_splits:
        raise ValueError(f"{d.game_id.nunique()} games, need >= {n_splits}")
    X, y, g = d[features].to_numpy(), d.y.to_numpy(), d.game_id.to_numpy()
    oof = np.full(len(d), np.nan)
    for tr, te in GroupKFold(n_splits=n_splits).split(X, y, g):
        m = HistGradientBoostingClassifier(
            max_depth=3, max_iter=250, learning_rate=0.05,
            min_samples_leaf=100, l2_regularization=1.0, random_state=0)
        m.fit(X[tr], y[tr])
        oof[te] = m.predict_proba(X[te])[:, 1]
    d["model_p"] = oof
    return d


def money(d: pd.DataFrame, p_col: str, edge_min: float = 0.03):
    """Money on the bets this probability would take, game-clustered.

    Takes the side the estimate favours when it disagrees with the mid by more
    than `edge_min`; P&L is the side-signed settlement minus the entry price.
    """
    b = d[(d[p_col] - d["mid"]).abs() >= edge_min].copy()
    if b.empty:
        return None, 0
    long_yes = b[p_col] > b["mid"]
    b["pnl"] = np.where(long_yes, b.y - b["mid"], b["mid"] - b.y)
    r = clustered_mean({k: v.tolist() for k, v in b.groupby("game_id").pnl})
    return r, len(b)


def main() -> int:
    print(__doc__.split("## ★ POWER")[0])
    print("Run with a price export once both recorders have been live together.")
    print("As of 2026-09-06 that is tonight's 23:30Z slate and no earlier data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
