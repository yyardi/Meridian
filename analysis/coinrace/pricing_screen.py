"""Coin Race pricing screen — registered question 1 (docs/math/coinrace-research.md).

A SCREEN on recorded data, not a result. Inputs (all under the archive, see pricing_data.py):

  pricing_markets.parquet     settled markets; settlement_value is the truth (1, 0.5 on a tie, 0)
  pricing_candles_1m.parquet  Coinbase 1-minute candles, the PROXY for CF Benchmarks' spot rate
  pricing_book_1m.parquet     Kalshi per-minute candlesticks; yes_ask close = the ask at minute end
  trades.parquet (+ trades.READY), written by the coinrace-microstructure agent: every public
                              Coin Race print; the market's price at minute m is the last print
                              at or before open + 60 m

Walk-forward by UTC day: everything used to price day D (covariances, hour-of-day profile, the
fitted scalars) comes from candles and settled windows strictly before D 00:00Z.

Usage:
  python analysis/coinrace/pricing_screen.py models    # model ladder vs outcomes (no market)
  python analysis/coinrace/pricing_screen.py report    # + market comparison, taker rule, control
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

# This runs on the operator's laptop: one process, single-threaded numerical libraries
# (set before numpy loads), and run it under `nice -n 19`.
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import pricing_model as pm
from pricing_data import DATA_DIR, read_parquet, write_parquet

COINS = pm.COINS
MINUTES = pm.MINUTES
DAY = 86400
LOOKBACK_DAYS = 7          # covariance window
PROFILE_DAYS = 14          # hour-of-day vol profile window
FIT_DAYS = 7               # windows used to fit outcome-fitted scalars
RV_MINUTES = 60            # trailing realised-variance window for M3
FIT_EVERY_DAYS = 7         # the fitted scalars are refit weekly (on the 7 days before the refit)
N_DRAWS_FIT = 256          # scrambled-Sobol draws; `draws_check` measures the error this costs
N_DRAWS_SCORE = 2048

# The ladder: each model adds one thing to the last one KEPT (see `ladder`).
BETA_GRID = (0.0, 0.5, 0.75, 1.0)
K_GRID = (0.7, 0.85, 1.0, 1.2, 1.45)
SIGP_GRID = (0.0, 1e-4, 2e-4)            # proxy noise sd, log-return units (1e-4 = 1 bp)


# ----------------------------------------------------------------------------------- data
def load_events() -> pd.DataFrame:
    m = read_parquet(os.path.join(DATA_DIR, "pricing_markets.parquet"))
    piv = m.pivot(index="event_ticker", columns="coin", values="settlement_value")[list(COINS)]
    ev = m.groupby("event_ticker").agg(open=("open_time", "min"), close=("close_time", "max"),
                                       volume=("volume", "sum"))
    ev = ev.join(piv)
    ev["open_ts"] = np.array([int(t.timestamp()) for t in ev["open"]], dtype=np.int64)
    ev["close_ts"] = ev["open_ts"] + pm.WINDOW_S
    ev["day"] = ev["open"].dt.strftime("%Y-%m-%d")
    ev = ev.sort_values("open_ts")
    ysum = ev[list(COINS)].sum(axis=1)
    bad = ~np.isclose(ysum, 1.0)
    if bad.any():
        print(f"dropping {bad.sum()} events whose settlement values do not sum to 1", file=sys.stderr)
    return ev[~bad]


class Candles:
    """Coinbase 1-minute candles on a dense minute grid (absent minutes carry the last close)."""

    def __init__(self, df: pd.DataFrame):
        self.t0 = int(df["ts"].min())
        n = int((df["ts"].max() - self.t0) // 60) + 1
        self.n = n
        K = len(COINS)
        self.O, self.H, self.L, self.C = (np.full((K, n), np.nan) for _ in range(4))
        self.present = np.zeros((K, n), dtype=bool)
        for k, coin in enumerate(COINS):
            d = df[df["coin"] == coin]
            ix = ((d["ts"].to_numpy() - self.t0) // 60).astype(int)
            self.O[k, ix], self.H[k, ix] = d["open"].to_numpy(), d["high"].to_numpy()
            self.L[k, ix], self.C[k, ix] = d["low"].to_numpy(), d["close"].to_numpy()
            self.present[k, ix] = True
            c = pd.Series(self.C[k]).ffill().to_numpy()
            miss = ~self.present[k]
            self.C[k] = c
            for A in (self.O, self.H, self.L):
                A[k, miss] = c[miss]
        self.logC = np.log(self.C)
        self.r1 = np.diff(self.logC, axis=1, prepend=np.nan)          # r1[:, i] = minute i's return
        self.twa = pm.twa_proxy(self.O, self.H, self.L, self.C)

    def idx(self, ts) -> np.ndarray:
        """Grid index of the minute candle STARTING at ts."""
        return ((np.asarray(ts) - self.t0) // 60).astype(int)

    def valid(self, i) -> np.ndarray:
        i = np.asarray(i)
        return (i >= 1) & (i < self.n)


def load_candles() -> Candles:
    return Candles(read_parquet(os.path.join(DATA_DIR, "pricing_candles_1m.parquet")))


def window_states(ev: pd.DataFrame, cd: Candles) -> dict:
    """Per event: start TWA proxy A, spot S at each scored minute, end TWA proxy B."""
    o = ev["open_ts"].to_numpy()
    iA = cd.idx(o - 60)
    iB = cd.idx(o + pm.WINDOW_S - 60)
    ok = cd.valid(iA) & cd.valid(iB)
    iA_, iB_ = np.where(ok, iA, 1), np.where(ok, iB, 1)
    st = {"ok": ok, "iA": iA_, "iB": iB_,
          "logA": np.log(cd.twa[:, iA_]).T, "logB": np.log(cd.twa[:, iB_]).T,
          "A_present": cd.present[:, iA_].all(axis=0), "B_present": cd.present[:, iB_].all(axis=0)}
    r2 = np.nan_to_num(cd.r1 ** 2)
    cs = np.concatenate([np.zeros((r2.shape[0], 1)), np.cumsum(r2, axis=1)], axis=1)
    for m in MINUTES:
        iS = np.where(ok, cd.idx(o + 60 * (m - 1)), 1)              # the candle closing at open+60m
        st[f"iS{m}"] = iS
        st[f"x{m}"] = cd.logC[:, iS].T - st["logA"]
        # trailing realised 1-minute variance over the RV_MINUTES ending at that candle (causal)
        lo = np.clip(iS + 1 - RV_MINUTES, 0, None)
        st[f"rv{m}"] = ((cs[:, iS + 1] - cs[:, lo]) / np.maximum(iS + 1 - lo, 1)).T
    # alternatives to the OHLC/4 proxy, for the agreement table only
    st["alt"] = {
        "close_to_close (no averaging)": (np.log(cd.C[:, iB_]).T - np.log(cd.C[:, iA_]).T),
        "(open+close)/2": (np.log((cd.O[:, iB_] + cd.C[:, iB_]) / 2).T - np.log((cd.O[:, iA_] + cd.C[:, iA_]) / 2).T),
        "(high+low+close)/3": (np.log((cd.H[:, iB_] + cd.L[:, iB_] + cd.C[:, iB_]) / 3).T
                               - np.log((cd.H[:, iA_] + cd.L[:, iA_] + cd.C[:, iA_]) / 3).T),
        "(open+high+low+close)/4 [used]": st["logB"] - st["logA"],
    }
    return st


def proxy_agreement(ev: pd.DataFrame, st: dict) -> pd.DataFrame:
    Y = ev[list(COINS)].to_numpy()
    rows = []
    for name, R in st["alt"].items():
        ok = st["ok"] & np.isfinite(R).all(axis=1)
        pick = np.argmax(np.where(np.isfinite(R), R, -np.inf), axis=1)
        hit = Y[np.arange(len(Y)), pick] > 0
        single = ok & (Y.max(axis=1) == 1.0)
        both_present = single & st["A_present"] & st["B_present"]
        rows.append({"proxy": name, "windows": int(single.sum()),
                     "agree": float(hit[single].mean()),
                     "windows_all_candles_present": int(both_present.sum()),
                     "agree_all_candles_present": float(hit[both_present].mean())})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------- parameters
def day_params(cd: Candles, D0: int, cov_horizon: int) -> dict | None:
    """Per-minute covariance and hour-of-day variance profile from candles strictly before D0."""
    i1 = cd.idx(D0)                                     # first minute of day D (excluded)
    i0 = max(cd.idx(D0 - LOOKBACK_DAYS * DAY), cov_horizon + 1)
    if i0 >= i1 - 1000:
        return None
    seg = cd.logC[:, i0 - cov_horizon:i1]
    R = seg[:, cov_horizon:] - seg[:, :-cov_horizon]       # overlapping h-minute returns
    R = R[:, np.isfinite(R).all(axis=0)]
    S = (R @ R.T) / R.shape[1] / cov_horizon              # per-minute covariance, zero mean
    # hour-of-day profile of 1-minute variance (UTC hour), relative to the all-hours mean
    p0 = max(cd.idx(D0 - PROFILE_DAYS * DAY), 1)
    r = cd.r1[:, p0:i1]
    hrs = (((cd.t0 + 60 * np.arange(p0, i1)) // 3600) % 24)
    ok = np.isfinite(r).all(axis=0)
    base1 = (r[:, ok] ** 2).mean(axis=1)
    prof = np.ones((24, len(COINS)))
    for h in range(24):
        sel = ok & (hrs == h)
        if sel.sum() > 100:
            prof[h] = (r[:, sel] ** 2).mean(axis=1) / base1
    # 1-minute variance over the trailing week, the denominator of the realised-vol ratio
    rw = cd.r1[:, max(cd.idx(D0 - LOOKBACK_DAYS * DAY), 1):i1]
    base1w = np.nanmean(rw ** 2, axis=1)
    return {"S": S, "prof": prof, "base1": base1w}


def state_covs(ev_open: np.ndarray, rv: np.ndarray, m: int, P: dict, cfg: dict,
               beta: float = 0.0, k: float = 1.0, sigp: float = 0.0) -> np.ndarray:
    """Covariance of the remaining log-return increment for each window at minute m."""
    W = len(ev_open)
    v = pm.remaining_variance_seconds(60 * m) / 60.0      # in minutes (S is per minute)
    cov = np.broadcast_to(P["S"] * v, (W, 5, 5)).copy()
    hrs = (ev_open // 3600) % 24
    prof = P["prof"][hrs] if cfg.get("hour") else np.ones((W, 5))
    if cfg.get("hour"):
        d = np.sqrt(prof)                                  # (W,5)
        cov = cov * d[:, :, None] * d[:, None, :]
    if cfg.get("rv") and beta != 0.0:
        # trailing realised 1-min variance relative to what the (hour-adjusted) week predicts
        ratio = np.clip(rv / (P["base1"][None, :] * prof), 0.05, 20.0)
        d = ratio ** (beta / 2)
        cov = cov * d[:, :, None] * d[:, None, :]
    cov = cov * k
    if sigp > 0:
        cov = cov + (sigp ** 2) * np.eye(5)[None]
    return cov


def probs_for(ev_open, st_rows, P, cfg, z, beta=0.0, k=1.0, sigp=0.0, nu=np.inf) -> dict:
    sc = pm.t_scales(len(z), nu) if cfg.get("tails") else None
    out = {}
    for m in MINUTES:
        cov = state_covs(ev_open, st_rows[f"rv{m}"], m, P, cfg, beta, k, sigp)
        out[m] = pm.win_probs(st_rows[f"x{m}"], cov, z, scales=sc)
    return out


def _subset(st: dict, mask: np.ndarray) -> dict:
    return {k: (v[mask] if isinstance(v, np.ndarray) and len(v) == len(mask) else v)
            for k, v in st.items() if k != "alt"}


def fit_scalars(ev_open, st_rows, Y, P, cfg, z) -> dict:
    """Fit, on PRIOR windows only, one scalar group at a time by pooled log loss over the four
    minutes: beta (vol state), then nu (tails) given beta, then (k, sigp) given both."""
    def ll(**kw):
        pr = probs_for(ev_open, st_rows, P, cfg, z, **kw)
        return float(np.mean([pm.log_loss(pr[m], Y).mean() for m in MINUTES]))
    f = {"beta": 0.0, "k": 1.0, "sigp": 0.0, "nu": np.inf}
    if cfg.get("rv"):
        f["beta"] = min(BETA_GRID, key=lambda b: ll(**{**f, "beta": b}))
    if cfg.get("tails"):
        f["nu"] = min(NU_GRID, key=lambda n: ll(**{**f, "nu": n}))
    if cfg.get("ksig"):
        f["k"], f["sigp"] = min(((a, b) for a in K_GRID for b in SIGP_GRID),
                                key=lambda ab: ll(**{**f, "k": ab[0], "sigp": ab[1]}))
    return f


# ----------------------------------------------------------------------- walk-forward
_G: dict = {}


def _init():
    _G["ev"] = load_events()
    _G["cd"] = load_candles()
    _G["st"] = window_states(_G["ev"], _G["cd"])


def _day0(day: str) -> int:
    return int(dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc).timestamp())


def fit_anchor(D0: int, first_day0: int) -> int:
    """The refit date for day D0: the start of its FIT_EVERY_DAYS block. <= D0 always."""
    return first_day0 + ((D0 - first_day0) // (FIT_EVERY_DAYS * DAY)) * FIT_EVERY_DAYS * DAY


def fitted_for(anchor: int, cfg: dict) -> dict | None:
    """Scalars fitted on settled windows in [anchor - FIT_DAYS, anchor), with the covariance
    estimated from candles before `anchor` — nothing at or after the anchor is read."""
    key = (anchor, json.dumps(cfg, sort_keys=True))
    if key in _G.setdefault("fits", {}):
        return _G["fits"][key]
    ev, cd, st = _G["ev"], _G["cd"], _G["st"]
    o = ev["open_ts"].to_numpy()
    P = day_params(cd, anchor, cfg["horizon"])
    prior = (o + pm.WINDOW_S <= anchor) & (o >= anchor - FIT_DAYS * DAY) & st["ok"]
    f = None
    if P is not None and prior.sum() >= 200:
        Yp = ev[list(COINS)].to_numpy()[prior]
        f = fit_scalars(o[prior], _subset(st, prior), Yp, P, cfg, pm.standard_normals(N_DRAWS_FIT))
    _G["fits"][key] = f
    return f


def score_day(day: str, cfg: dict, first_day: str, n_draws: int = N_DRAWS_SCORE) -> dict | None:
    ev, cd, st = _G["ev"], _G["cd"], _G["st"]
    D0 = _day0(day)
    P = day_params(cd, D0, cfg["horizon"])
    if P is None:
        return None
    o = ev["open_ts"].to_numpy()
    today = (o >= D0) & (o < D0 + DAY) & st["ok"]
    if not today.any():
        return None
    fitted = {"beta": 0.0, "k": 1.0, "sigp": 0.0, "nu": np.inf}
    if cfg.get("rv") or cfg.get("ksig") or cfg.get("tails"):
        fitted = fitted_for(fit_anchor(D0, _day0(first_day)), cfg)
        if fitted is None:
            return None
    pr = probs_for(o[today], _subset(st, today), P, cfg, pm.standard_normals(n_draws), **fitted)
    return {"day": day, "events": ev.index[today].tolist(), "probs": pr, "fitted": fitted}


#: The ladder: start from M0, add ONE thing at a time to the last model KEPT; a step is kept
#: when it lowers the pooled (four-minute) walk-forward log loss. Order fixed before running.
BASE = ("M0 Gaussian, 1-min cov over 7 d", {"horizon": 1})
ADDITIONS = [
    ("5-min-return cov", {"horizon": 5}),
    ("hour-of-day vol profile", {"hour": True}),
    ("trailing-60-min vol state (beta fitted)", {"rv": True}),
    ("variance scale k + proxy noise sigp (fitted)", {"ksig": True}),
    ("fat tails: Student-t scale mixture (nu fitted)", {"tails": True}),
]
NU_GRID = (np.inf, 8.0, 4.0)


def run_model(name: str, cfg: dict, days: list[str]) -> pd.DataFrame:
    """Walk forward day by day in THIS process (no worker pool)."""
    if "ev" not in _G:
        _init()
    rows = []
    for d in days:
        res = score_day(d, cfg, days[0])
        if res is None:
            continue
        for m in MINUTES:
            for e, p in zip(res["events"], res["probs"][m]):
                rows.append((name, e, res["day"], m, *p, json.dumps(res["fitted"])))
    return pd.DataFrame(rows, columns=["model", "event_ticker", "day", "minute",
                                       *[f"p_{c}" for c in COINS], "fitted"])


def draws_check(cfg: dict, days: list[str], n_days: int = 4, seed: int = 0) -> dict:
    """Monte Carlo error of the scoring draws: the same days priced at N_DRAWS_SCORE and at
    4x that many; max |dp| and mean |d log loss| over all their windows and minutes."""
    rng = np.random.default_rng(seed)
    pick = sorted(rng.choice(days[FIT_EVERY_DAYS + 1:], size=n_days, replace=False))
    dps, dll = [], []
    for d in pick:
        a = score_day(d, cfg, days[0], N_DRAWS_SCORE)
        b = score_day(d, cfg, days[0], 4 * N_DRAWS_SCORE)
        if a is None or b is None:
            continue
        Y = _G["ev"].loc[a["events"], list(COINS)].to_numpy()
        for m in MINUTES:
            dps.append(np.abs(a["probs"][m] - b["probs"][m]).max())
            dll.append(np.abs(pm.log_loss(a["probs"][m], Y) - pm.log_loss(b["probs"][m], Y)).mean())
    return {"days": pick, "draws": N_DRAWS_SCORE, "vs_draws": 4 * N_DRAWS_SCORE,
            "max_abs_dp": float(np.max(dps)), "mean_abs_dll": float(np.mean(dll))}


def scored_days(ev: pd.DataFrame, cd: Candles) -> list[str]:
    first = cd.t0 + (LOOKBACK_DAYS + 1) * DAY
    return sorted(d for d in ev["day"].unique()
                  if dt.datetime.fromisoformat(d).replace(tzinfo=dt.timezone.utc).timestamp() >= first)


def per_window_ll(ev: pd.DataFrame, probs: pd.DataFrame, model: str) -> pd.DataFrame:
    """(event, minute) -> log loss and Brier of one model."""
    s = probs[probs["model"] == model]
    P = s[[f"p_{c}" for c in COINS]].to_numpy()
    Y = ev.loc[s["event_ticker"], list(COINS)].to_numpy()
    return pd.DataFrame({"event_ticker": s["event_ticker"].to_numpy(), "minute": s["minute"].to_numpy(),
                         "day": s["day"].to_numpy(), "ll": pm.log_loss(P, Y), "brier": pm.brier(P, Y)})


def compare(ev, probs, a: str, b: str) -> dict:
    """b minus a: per minute and pooled (per-window mean over the four minutes), day-clustered,
    on the windows both models priced."""
    A, B = per_window_ll(ev, probs, a), per_window_ll(ev, probs, b)
    j = A.merge(B, on=["event_ticker", "minute", "day"], suffixes=("_a", "_b"))
    j["d"] = j["ll_b"] - j["ll_a"]
    out = {}
    for m in MINUTES:
        jm = j[j["minute"] == m]
        out[m] = {**pm.clustered_mean_ci(jm["d"], jm["day"]), "ll_a": jm["ll_a"].mean(), "ll_b": jm["ll_b"].mean()}
    w = j.groupby(["event_ticker", "day"])["d"].mean().reset_index()
    out["pooled"] = pm.clustered_mean_ci(w["d"], w["day"])
    return out


def main_models() -> None:
    _init()
    ev, cd, st = _G["ev"], _G["cd"], _G["st"]
    print(proxy_agreement(ev, st).to_string(index=False))
    days = scored_days(ev, cd)
    print(f"scored days {days[0]} .. {days[-1]} ({len(days)})")
    name, cfg = BASE
    frames = [run_model(name, cfg, days)]
    kept_name, kept_cfg = name, cfg
    log = [{"model": name, "parent": "", "kept": True}]
    for i, (what, delta) in enumerate(ADDITIONS, start=1):
        nm = f"M{i} +{what}"
        c = {**kept_cfg, **delta}
        frames.append(run_model(nm, c, days))
        probs = pd.concat(frames, ignore_index=True)
        cmp_ = compare(ev, probs, kept_name, nm)
        keep = cmp_["pooled"]["mean"] < 0
        row = {"model": nm, "parent": kept_name, "kept": keep,
               "pooled_d": cmp_["pooled"]["mean"], "pooled_lo": cmp_["pooled"]["lo"],
               "pooled_hi": cmp_["pooled"]["hi"], "n_windows": cmp_["pooled"]["n"], "G": cmp_["pooled"]["G"]}
        for m in MINUTES:
            row[f"m{m}_d"] = cmp_[m]["mean"]
            row[f"m{m}_ci"] = f"[{cmp_[m]['lo']:+.4f}, {cmp_[m]['hi']:+.4f}]"
            row[f"m{m}_ll"] = cmp_[m]["ll_b"]
        log.append(row)
        print(json.dumps(row, default=str), flush=True)
        if keep:
            kept_name, kept_cfg = nm, c
    probs = pd.concat(frames, ignore_index=True)
    probs["final"] = probs["model"] == kept_name
    write_parquet(probs, os.path.join(DATA_DIR, "pricing_model_probs.parquet"))
    lg = pd.DataFrame(log)
    write_parquet(lg.astype({c: str for c in lg.columns if lg[c].dtype == object}),
                  os.path.join(DATA_DIR, "pricing_ladder.parquet"))
    chk = draws_check(kept_cfg, days)
    print("draws check:", json.dumps(chk))
    with open(os.path.join(DATA_DIR, "pricing_draws_check.json"), "w") as fh:
        json.dump(chk, fh)
    print(f"final model: {kept_name}")
    print(lg.to_string(index=False, float_format=lambda v: f"{v:+.4f}"))


# ---------------------------------------------------------------------- market and taker
TRADES = os.environ.get("COINRACE_TRADES") or os.path.join(DATA_DIR, "trades.parquet")
TRADES_READY = os.path.join(DATA_DIR, "trades.READY")


def load_trades(path: str = TRADES) -> pd.DataFrame:
    """Public Coin Race prints -> ticker, t (epoch s, float), yes_price, count, taker_side."""
    t = read_parquet(path)
    cols = {c.lower(): c for c in t.columns}

    def pick(*names):
        for n in names:
            if n in cols:
                return t[cols[n]]
        raise KeyError(f"none of {names} in {list(t.columns)}")
    tm = pick("created_time", "t", "ts", "time")
    if np.issubdtype(np.asarray(tm).dtype, np.number):
        ts = np.asarray(tm, dtype=float)
    else:
        ts = pd.to_datetime(tm, utc=True).map(lambda x: x.timestamp()).to_numpy(dtype=float)
    out = pd.DataFrame({"ticker": pick("ticker", "market_ticker").astype(str).to_numpy(), "t": ts,
                        "yes_price": pd.to_numeric(pick("yes_price_dollars", "yes_price", "price")).to_numpy(dtype=float),
                        "count": pd.to_numeric(pick("count_fp", "count", "size")).to_numpy(dtype=float),
                        "taker_side": pick("taker_side", "side").astype(str).to_numpy()})
    if out["yes_price"].max() > 1.5:          # cents
        out["yes_price"] = out["yes_price"] / 100.0
    return out.sort_values(["ticker", "t"], kind="stable").reset_index(drop=True)


def _queries(ev: pd.DataFrame) -> pd.DataFrame:
    q = []
    for e, o in zip(ev.index, ev["open_ts"].to_numpy()):
        for c in COINS:
            for m in MINUTES:
                q.append((f"{e}-{c}", e, c, m, float(o + 60 * m), float(o)))
    return pd.DataFrame(q, columns=["ticker", "event_ticker", "coin", "minute", "T", "open_ts"])


def market_prices(ev: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    """Last public print at or before open + 60 m, per market; prints sharing that last
    timestamp (one order sweeping levels) enter at their size-weighted mean price."""
    g = (trades.assign(pc=trades["yes_price"] * trades["count"])
         .groupby(["ticker", "t"], as_index=False).agg(pc=("pc", "sum"), cnt=("count", "sum")))
    g["px"] = g["pc"] / g["cnt"]
    g = g.sort_values("t")
    q = _queries(ev).sort_values("T")
    j = pd.merge_asof(q, g[["ticker", "t", "px"]], left_on="T", right_on="t", by="ticker",
                      direction="backward")
    j.loc[j["t"] < j["open_ts"] - 3600, "px"] = np.nan  # a print from another window cannot leak in
    return j.pivot_table(index=["event_ticker", "minute"], columns="coin", values="px")[list(COINS)]


def book_asks(ev: pd.DataFrame, book: pd.DataFrame) -> pd.DataFrame:
    """yes ask at open + 60 m: the close of Kalshi's 1-minute candle ending then, or of the
    latest earlier candle in the same window when that minute has none."""
    b = book[["ticker", "end_period_ts", "yes_ask_close"]].rename(columns={"end_period_ts": "t"})
    b = b.assign(t=b["t"].astype(float)).sort_values("t")
    q = _queries(ev).sort_values("T")
    j = pd.merge_asof(q, b, left_on="T", right_on="t", by="ticker", direction="backward")
    j.loc[~(j["t"] > j["open_ts"]), "yes_ask_close"] = np.nan
    j["exact"] = j["t"] == j["T"]
    asks = j.pivot_table(index=["event_ticker", "minute"], columns="coin", values="yes_ask_close")[list(COINS)]
    exact = j.groupby(["event_ticker", "minute"])["exact"].mean()
    return asks, exact


def book_mids(ev: pd.DataFrame, book: pd.DataFrame) -> pd.DataFrame:
    """(bid + ask) / 2 at open + 60 m from the same candles (SUPPLEMENTARY market measure, not
    the registered one): a quote that cannot be minutes stale the way a last print can."""
    b = book[["ticker", "end_period_ts", "yes_ask_close", "yes_bid_close"]].rename(columns={"end_period_ts": "t"})
    b = b.assign(t=b["t"].astype(float), mid=(b["yes_ask_close"] + b["yes_bid_close"]) / 2).sort_values("t")
    q = _queries(ev).sort_values("T")
    j = pd.merge_asof(q, b[["ticker", "t", "mid"]], left_on="T", right_on="t", by="ticker", direction="backward")
    j.loc[~(j["t"] > j["open_ts"]), "mid"] = np.nan
    j.loc[j["mid"] <= 0, "mid"] = np.nan
    return j.pivot_table(index=["event_ticker", "minute"], columns="coin", values="mid")[list(COINS)]


def final_probs() -> pd.DataFrame:
    pr = read_parquet(os.path.join(DATA_DIR, "pricing_model_probs.parquet"))
    return pr[pr["final"]].set_index(["event_ticker", "minute"])


def score_vs_market(ev, P: pd.DataFrame, Q: pd.DataFrame, Y: pd.DataFrame | None = None) -> pd.DataFrame:
    """Model vs market (five last prints normalised to sum to 1) on windows where all five
    markets have printed by the minute. Y overrides the outcomes (the shuffled control)."""
    rows = []
    for m in MINUTES:
        qm = Q.xs(m, level="minute").dropna()
        pmm = P.xs(m, level="minute")
        idx = qm.index.intersection(pmm.index)
        q = qm.loc[idx].to_numpy()
        q = q / q.sum(axis=1, keepdims=True)
        p = pmm.loc[idx, [f"p_{c}" for c in COINS]].to_numpy()
        y = (Y if Y is not None else ev[list(COINS)]).loc[idx].to_numpy()
        days = ev.loc[idx, "day"].to_numpy()
        llm, llq = pm.log_loss(p, y), pm.log_loss(q, y)
        brm, brq = pm.brier(p, y), pm.brier(q, y)
        d = pm.clustered_mean_ci(llm - llq, days)
        db = pm.clustered_mean_ci(brm - brq, days)
        uni = np.log(5.0)
        clim = ev.loc[P.index.get_level_values(0).unique(), list(COINS)].mean().to_numpy()
        llc = pm.log_loss(np.broadcast_to(clim, y.shape), y)
        dc = pm.clustered_mean_ci(llm - llc, days)
        rows.append({"minute": m, "n_windows": len(idx), "n_days": len(set(days)),
                     "ll_model": llm.mean(), "ll_market": llq.mean(), "ll_uniform": uni,
                     "ll_climatology": llc.mean(), "d_ll_model_vs_clim": dc["mean"],
                     "d_ll_model_vs_clim_lo": dc["lo"], "d_ll_model_vs_clim_hi": dc["hi"],
                     "d_ll": d["mean"], "d_ll_lo": d["lo"], "d_ll_hi": d["hi"],
                     "brier_model": brm.mean(), "brier_market": brq.mean(),
                     "d_brier": db["mean"], "d_brier_lo": db["lo"], "d_brier_hi": db["hi"]})
    return pd.DataFrame(rows)


def taker_rule(ev, P: pd.DataFrame, A: pd.DataFrame, Y: pd.DataFrame | None = None,
               min_edge: float = 0.0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Buy one YES at the ask when model - ask - fee > min_edge; hold to settlement.
    P&L per contract = settlement value (1, 0.5 on a tie, 0) - ask - fee."""
    Yv = Y if Y is not None else ev[list(COINS)]
    trades = []
    for m in MINUTES:
        am = A.xs(m, level="minute")
        pmm = P.xs(m, level="minute")
        idx = am.index.intersection(pmm.index)
        a = am.loc[idx].to_numpy()
        p = pmm.loc[idx, [f"p_{c}" for c in COINS]].to_numpy()
        y = Yv.loc[idx].to_numpy()
        fee = pm.taker_fee(np.nan_to_num(a, nan=0.5))
        edge = p - a - fee
        ok = np.isfinite(a) & (a > 0) & (a < 1) & (edge > min_edge)
        wi, ci = np.nonzero(ok)
        for w, c in zip(wi, ci):
            trades.append((idx[w], ev.loc[idx[w], "day"], m, COINS[c], p[w, c], a[w, c], fee[w, c],
                           edge[w, c], y[w, c], y[w, c] - a[w, c] - fee[w, c]))
    T = pd.DataFrame(trades, columns=["event_ticker", "day", "minute", "coin", "p_model", "ask",
                                      "fee", "edge", "y", "pnl"])
    rows = []
    for m in [*MINUTES, "all"]:
        s = T if m == "all" else T[T["minute"] == m]
        c = pm.clustered_mean_ci(s["pnl"], s["event_ticker"])
        rows.append({"minute": m, "n_contracts": len(s), "n_windows": s["event_ticker"].nunique(),
                     "n_days": s["day"].nunique(), "mean_ask": s["ask"].mean(),
                     "mean_edge_claimed": s["edge"].mean(), "mean_pnl": c["mean"],
                     "lo": c["lo"], "hi": c["hi"], "win_rate": (s["y"] > 0).mean()})
    return pd.DataFrame(rows), T


def shuffled_outcomes(ev: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Outcome vectors permuted across windows WITHIN each UTC day."""
    rng = np.random.default_rng(seed)
    Y = ev[list(COINS)].copy()
    for ix in ev.groupby("day").groups.values():
        ix = list(ix)
        Y.loc[ix] = Y.loc[ix].to_numpy()[rng.permutation(len(ix))]
    return Y


def passes(sc: pd.DataFrame, tk: pd.DataFrame) -> bool:
    ll_ok = bool((sc["d_ll_hi"] < 0).any())
    tk_all = tk[tk["minute"] == "all"].iloc[0]
    return ll_ok and bool(tk_all["lo"] > 0)


def hand_check(event: str, minute: int = 10) -> dict:
    """Recompute one window's model probabilities from the raw candles, printing every input,
    and compare with the stored walk-forward probability (a second, independent route)."""
    ev, cd = load_events(), load_candles()
    st = window_states(ev, cd)
    i = ev.index.get_loc(event)
    o = int(ev["open_ts"].iloc[i])
    day = ev["day"].iloc[i]
    D0 = int(dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc).timestamp())
    pr = final_probs()
    row = pr.loc[(event, minute)]
    fitted = json.loads(row["fitted"])
    name = row["model"]
    cfg = final_cfg()
    P = day_params(cd, D0, cfg["horizon"])
    ia, isx = st["iA"][i], st[f"iS{minute}"][i]
    out = {"event": event, "open_utc": str(pd.to_datetime(o, unit="s", utc=True)), "day": day,
           "model": name, "cfg": cfg, "fitted": fitted}
    lines = []
    for k, c in enumerate(COINS):
        lines.append({"coin": c,
                      "start_minute_OHLC": [cd.O[k, ia], cd.H[k, ia], cd.L[k, ia], cd.C[k, ia]],
                      "A_twa_proxy": float(np.exp(st["logA"][i, k])),
                      f"S_at_min{minute}": float(cd.C[k, isx]),
                      "x_bp": float(st[f"x{minute}"][i, k] * 1e4),
                      "trailing60_rv_1min_bp": float(np.sqrt(st[f"rv{minute}"][i, k]) * 1e4),
                      "week_1min_sd_bp": float(np.sqrt(P["base1"][k]) * 1e4),
                      "B_twa_proxy_end": float(np.exp(st["logB"][i, k])),
                      "proxy_final_return_bp": float((st["logB"][i, k] - st["logA"][i, k]) * 1e4),
                      "settled": float(ev[c].iloc[i])})
    cov = state_covs(np.array([o]), st[f"rv{minute}"][i:i + 1], minute, P, cfg,
                     fitted["beta"], fitted["k"], fitted["sigp"])
    sc = pm.t_scales(N_DRAWS_SCORE, fitted.get("nu", np.inf)) if cfg.get("tails") else None
    p2 = pm.win_probs(st[f"x{minute}"][i:i + 1], cov, pm.standard_normals(N_DRAWS_SCORE), scales=sc)[0]
    # independent route for the probability step: plain pseudo-random paths, count the argmax
    rng = np.random.default_rng(7)
    nb = 1_000_000
    zz = rng.standard_normal((nb, 5)) @ np.linalg.cholesky(cov[0]).T
    nu = fitted.get("nu", np.inf)
    if cfg.get("tails") and np.isfinite(nu):
        zz *= np.sqrt((nu - 2.0) / rng.chisquare(nu, nb))[:, None]
    brute = np.bincount((st[f"x{minute}"][i] + zz).argmax(axis=1), minlength=5) / nb
    sd = np.sqrt(np.diag(cov[0]))
    out.update({"coins": lines, "remaining_sd_bp": (sd * 1e4).round(2).tolist(),
                "p_bruteforce_1e6_paths": brute.round(4).tolist(),
                "remaining_corr": (cov[0] / np.outer(sd, sd)).round(3).tolist(),
                "p_recomputed": p2.round(4).tolist(),
                "p_stored": [float(row[f"p_{c}"]) for c in COINS]})
    return out


def final_cfg() -> dict:
    """BASE plus every ADDITION the ladder kept."""
    lg = read_parquet(os.path.join(DATA_DIR, "pricing_ladder.parquet"))
    kept = set(lg.loc[lg["kept"].astype(str) == "True", "model"])
    cfg = {**BASE[1]}
    for i, (what, delta) in enumerate(ADDITIONS, start=1):
        if f"M{i} +{what}" in kept:
            cfg.update(delta)
    return cfg


def calibration(ev: pd.DataFrame, P: pd.DataFrame) -> pd.DataFrame:
    """Reliability of the model's per-coin probabilities, pooled over coins, by minute."""
    rows = []
    edges = np.array([0, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9, 1.0001])
    for m in MINUTES:
        pmm = P.xs(m, level="minute")
        p = pmm[[f"p_{c}" for c in COINS]].to_numpy().ravel()
        y = ev.loc[pmm.index, list(COINS)].to_numpy().ravel()
        b = np.digitize(p, edges) - 1
        for k in range(len(edges) - 1):
            sel = b == k
            if sel.sum():
                rows.append({"minute": m, "bin": f"{edges[k]:.2f}-{min(edges[k + 1], 1):.2f}",
                             "n": int(sel.sum()), "mean_p": p[sel].mean(), "freq": y[sel].mean()})
    return pd.DataFrame(rows)


def main_report(n_shuffles: int = 20) -> None:
    ev = load_events()
    P = final_probs()
    trades = load_trades()
    book = read_parquet(os.path.join(DATA_DIR, "pricing_book_1m.parquet"))
    Q = market_prices(ev, trades)
    A, exact = book_asks(ev, book)
    write_parquet(Q.reset_index(), os.path.join(DATA_DIR, "pricing_market_prices.parquet"))
    write_parquet(A.reset_index(), os.path.join(DATA_DIR, "pricing_asks.parquet"))
    cov = {m: int(Q.xs(m, level="minute").notna().all(axis=1).sum()) for m in MINUTES}
    print(f"trades: {len(trades)} prints, {trades['ticker'].nunique()} markets, "
          f"{pd.to_datetime(trades['t'].min(), unit='s', utc=True)} .. {pd.to_datetime(trades['t'].max(), unit='s', utc=True)}")
    print(f"windows with all five markets printed by the minute: {cov}")
    print(f"ask from the exact-minute candle (else carried within the window): {exact.mean():.3f}")
    print(f"model: {P['model'].iloc[0]}")
    cal = calibration(ev, P)
    write_parquet(cal, os.path.join(DATA_DIR, "pricing_calibration.parquet"))
    print(cal.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    sc = score_vs_market(ev, P, Q)
    print(sc.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    M = book_mids(ev, book)
    scm = score_vs_market(ev, P, M)
    print("SUPPLEMENTARY (not registered): market = normalised book mid at the minute")
    print(scm.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    write_parquet(sc, os.path.join(DATA_DIR, "pricing_score_vs_market.parquet"))
    write_parquet(scm, os.path.join(DATA_DIR, "pricing_score_vs_mid.parquet"))
    tk, T = taker_rule(ev, P, A)
    write_parquet(T.drop(columns=["edge_bucket"], errors="ignore"), os.path.join(DATA_DIR, "pricing_taker_trades.parquet"))
    print(tk.to_string(index=False, float_format=lambda v: f"{v:+.4f}"))
    print(f"PASS (registered bar): {passes(sc, tk)}")
    # Shape only (not registered): realised P&L against the edge the model claimed.
    T["edge_bucket"] = pd.cut(T["edge"], [0, 0.02, 0.05, 0.10, 0.20, 1.0])
    rows = []
    for b, g in T.groupby("edge_bucket", observed=True):
        c = pm.clustered_mean_ci(g["pnl"], g["event_ticker"])
        rows.append({"claimed_edge": str(b), "n_contracts": len(g), "mean_claimed": g["edge"].mean(),
                     "mean_pnl": c["mean"], "lo": c["lo"], "hi": c["hi"]})
    by_edge = pd.DataFrame(rows)
    write_parquet(by_edge, os.path.join(DATA_DIR, "pricing_taker_by_edge.parquet"))
    print(by_edge.to_string(index=False, float_format=lambda v: f"{v:+.4f}"))
    write_parquet(tk.astype({"minute": str}), os.path.join(DATA_DIR, "pricing_taker_summary.parquet"))
    # The control that must fail: outcomes shuffled across windows within day.
    ctl = []
    for seed in range(n_shuffles):
        Ys = shuffled_outcomes(ev, seed)
        scs = score_vs_market(ev, P, Q, Ys)
        tks, _ = taker_rule(ev, P, A, Ys)
        row = {"seed": seed, "pass": passes(scs, tks)}
        for _, r in scs.iterrows():
            row[f"m{int(r['minute'])}_d_ll"] = r["d_ll"]
            row[f"m{int(r['minute'])}_ll_model_minus_uniform"] = r["ll_model"] - r["ll_uniform"]
            row[f"m{int(r['minute'])}_ll_market_minus_uniform"] = r["ll_market"] - r["ll_uniform"]
            row[f"m{int(r['minute'])}_excl0_model_better"] = bool(r["d_ll_hi"] < 0)
            row[f"m{int(r['minute'])}_model_vs_clim"] = r["d_ll_model_vs_clim"]
            row[f"m{int(r['minute'])}_model_beats_clim_excl0"] = bool(r["d_ll_model_vs_clim_hi"] < 0)
        a = tks[tks["minute"] == "all"].iloc[0]
        row.update({"taker_mean": a["mean_pnl"], "taker_lo": a["lo"], "taker_hi": a["hi"], "taker_n": a["n_contracts"]})
        ctl.append(row)
    ctl = pd.DataFrame(ctl)
    write_parquet(ctl, os.path.join(DATA_DIR, "pricing_control.parquet"))
    print(ctl.describe().T.to_string(float_format=lambda v: f"{v:+.4f}"))
    print(f"control seeds passing the bar: {int(ctl['pass'].sum())} of {len(ctl)}")


def main_tables() -> None:
    """Markdown tables for the write-up, from the files `models` and `report` saved."""
    def rd(name):
        return read_parquet(os.path.join(DATA_DIR, name))
    ev, cd = load_events(), load_candles()
    pa = proxy_agreement(ev, window_states(ev, cd))
    print("| TWA proxy (Coinbase 1-min candle) | windows | agrees with settled winner | all candles present: windows | agrees |")
    print("|---|---:|---:|---:|---:|")
    for _, r in pa.iterrows():
        print(f"| {r['proxy']} | {r['windows']:,} | {100 * r['agree']:.2f}% | "
              f"{r['windows_all_candles_present']:,} | {100 * r['agree_all_candles_present']:.2f}% |")
    print()
    lg = rd("pricing_ladder.parquet")
    print("| model | vs | pooled d log loss [95% CI] | min 1 | min 5 | min 10 | min 13 | windows / days | kept |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---|")
    for _, r in lg.iterrows():
        if not r["parent"]:
            continue
        print(f"| {r['model']} | {r['parent'].split(' ')[0]} | {r['pooled_d']:+.4f} [{r['pooled_lo']:+.4f}, {r['pooled_hi']:+.4f}] | "
              + " | ".join(f"{r[f'm{m}_d']:+.4f} {r[f'm{m}_ci']}" for m in MINUTES)
              + f" | {int(r['n_windows']):,} / {int(r['G'])} | {'yes' if str(r['kept']) == 'True' else 'no'} |")
    print()
    for name, label in (("pricing_score_vs_market.parquet", "REGISTERED: market = last print, normalised"),
                        ("pricing_score_vs_mid.parquet", "SUPPLEMENTARY: market = book mid, normalised")):
        sc = rd(name)
        print(f"{label}")
        print("| minute | windows / days | log loss model | market | climatology | model - market [95% CI, day-clustered] | Brier model | market | model - market [95% CI] |")
        print("|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for _, r in sc.iterrows():
            print(f"| {int(r['minute'])} | {int(r['n_windows']):,} / {int(r['n_days'])} | {r['ll_model']:.4f} | {r['ll_market']:.4f} | "
                  f"{r['ll_climatology']:.4f} | {r['d_ll']:+.4f} [{r['d_ll_lo']:+.4f}, {r['d_ll_hi']:+.4f}] | "
                  f"{r['brier_model']:.4f} | {r['brier_market']:.4f} | {r['d_brier']:+.4f} [{r['d_brier_lo']:+.4f}, {r['d_brier_hi']:+.4f}] |")
        print()
    tk = rd("pricing_taker_summary.parquet")
    print("| minute | contracts | windows | days | mean ask | mean claimed edge | mean P&L / contract [95% CI, window-clustered] | win rate |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|")
    for _, r in tk.iterrows():
        print(f"| {r['minute']} | {int(r['n_contracts']):,} | {int(r['n_windows']):,} | {int(r['n_days'])} | {r['mean_ask']:.3f} | "
              f"{100 * r['mean_edge_claimed']:+.2f}c | {100 * r['mean_pnl']:+.2f}c [{100 * r['lo']:+.2f}, {100 * r['hi']:+.2f}] | {100 * r['win_rate']:.1f}% |")
    print()
    be = rd("pricing_taker_by_edge.parquet")
    print("| claimed edge (model - ask - fee) | contracts | mean claimed | mean P&L [95% CI] |")
    print("|---|---:|---:|---:|")
    for _, r in be.iterrows():
        print(f"| {r['claimed_edge']} | {int(r['n_contracts']):,} | {100 * r['mean_claimed']:+.2f}c | "
              f"{100 * r['mean_pnl']:+.2f}c [{100 * r['lo']:+.2f}, {100 * r['hi']:+.2f}] |")
    print()
    ctl = rd("pricing_control.parquet")
    print(f"control: {len(ctl)} within-day shuffles; seeds passing the full bar {int(ctl['pass'].sum())}; "
          f"LL leg alone {int(ctl[[f'm{m}_excl0_model_better' for m in MINUTES]].any(axis=1).sum())}; "
          f"model beats climatology (CI excl. 0) at any minute {int(ctl[[f'm{m}_model_beats_clim_excl0' for m in MINUTES]].any(axis=1).sum())}")
    print("| minute | model - market log loss (mean over seeds, min..max) | model - climatology (mean, min..max) |")
    print("|---:|---:|---:|")
    for m in MINUTES:
        a, b = ctl[f"m{m}_d_ll"], ctl[f"m{m}_model_vs_clim"]
        print(f"| {m} | {a.mean():+.3f} ({a.min():+.3f} .. {a.max():+.3f}) | {b.mean():+.3f} ({b.min():+.3f} .. {b.max():+.3f}) |")
    print(f"taker under shuffle: mean {100 * ctl['taker_mean'].mean():+.2f}c, CI upper bound max over seeds "
          f"{100 * ctl['taker_hi'].max():+.2f}c, n {int(ctl['taker_n'].iloc[0]):,}")
    with open(os.path.join(DATA_DIR, "pricing_draws_check.json")) as fh:
        print("draws check:", fh.read())


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "models"
    if cmd == "hand":
        print(json.dumps(hand_check(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 10),
                         indent=1, default=float))
    else:
        {"models": main_models, "report": main_report, "tables": main_tables}[cmd]()
