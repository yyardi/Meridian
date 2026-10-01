"""Gradient boosting on the 15-minute Bitcoin contract, walk-forward by day, scored against the market.

SIZING / KILL STEP ONLY (operator rule 2026-09-30): nothing here is a result; a model that beats the
market mid out of sample earns a live paper arm, one that does not is closed once.

Data: the research set of analysis/btc15/fetch_kalshi_history.py (Kalshi KXBTC15M per-minute
quotes beside Coinbase 1-minute closes), the same rows backtest_price_aware.build makes: one row
per (window, minute k=1..13) with the quote at that minute and the point-in-time inputs. To the
earlier logistic's inputs this adds the technical set the operator asked for -- RSI 14, MACD
(12/26/9) and its histogram, Bollinger %b (20), EMA 9/21 ratios, realised volatility 15/60,
returns 1/5/15/60 minutes, 1-h and 4-h range position, hour of day, weekday, minute k -- all from
closes at or before the row's instant. Two feature sets: WITH the market's own logit (does the
model add to the price?) and WITHOUT it (can features alone forecast?).

Walk-forward: train on all days before day d (at least 14), predict day d, for every day; models
XGBoost (depth 3, 300 trees, lr 0.05, subsample 0.8) and sklearn HistGradientBoosting. Scored by
Brier against the market mid on the same rows, by minute, and as a taker: buy the side whose
model probability beats the ask plus Kalshi's fee (0.07 p(1-p)) by a margin, first minute per
window, day-clustered mean P&L.

    MERIDIAN_BTC_RESEARCH_DIR=<dir with windows/candles/btc_1m.jsonl> python analysis/btc15/ml_walkforward.py
"""
from __future__ import annotations

import math
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest_price_aware as BP  # noqa: E402  (its load/build/fee/clustered)


def ta(closes: list[float]) -> dict:
    c = np.asarray(closes, dtype=float)
    s = c[-1]
    def ema(x, n):
        a = 2 / (n + 1); e = x[0]
        for v in x[1:]:
            e = a * v + (1 - a) * e
        return e
    out = {}
    d = np.diff(c[-15:]); up = d[d > 0].sum(); dn = -d[d < 0].sum()
    out["rsi14"] = 100.0 if dn == 0 else 100 - 100 / (1 + up / dn)
    e12, e26 = ema(c[-60:], 12), ema(c[-60:], 26)
    macd = e12 - e26
    # signal: EMA9 of the MACD over the last 30 minutes, approximated from rolling EMAs
    macds = []
    for j in range(30, 0, -1):
        seg = c[:len(c) - j + 1][-60:] if len(c) - j + 1 >= 27 else None
        if seg is None:
            break
        macds.append(ema(seg, 12) - ema(seg, 26))
    sig = ema(np.asarray(macds), 9) if len(macds) >= 9 else macd
    out["macd_bp"] = 1e4 * macd / s; out["macd_hist_bp"] = 1e4 * (macd - sig) / s
    w = c[-20:]; mu, sd = w.mean(), w.std()
    out["boll_b"] = 0.5 if sd == 0 else (s - (mu - 2 * sd)) / (4 * sd)
    out["ema9_r"] = 1e4 * (s / ema(c[-30:], 9) - 1); out["ema21_r"] = 1e4 * (s / ema(c[-60:], 21) - 1)
    r = np.diff(np.log(c))
    out["rv15"] = 1e4 * r[-15:].std(); out["rv60"] = 1e4 * r[-60:].std()
    for n in (1, 5, 15, 60):
        out[f"ret{n}"] = 1e4 * math.log(s / c[-1 - n]) if len(c) > n else 0.0
    h1 = c[-60:]; out["pos1h"] = 0.5 if h1.max() == h1.min() else (s - h1.min()) / (h1.max() - h1.min())
    h4 = c[-240:] if len(c) >= 240 else c; out["pos4h"] = 0.5 if h4.max() == h4.min() else (s - h4.min()) / (h4.max() - h4.min())
    return out


def main() -> int:
    W, C, B = BP.load()
    rows = BP.build(W, C, B)
    print(f"rows {len(rows)} over {len({r['ticker'] for r in rows})} windows, {len({r['day'] for r in rows})} days")
    X, Xm, y, meta = [], [], [], []
    for r in rows:
        t = r["open"] + 60 * r["k"]
        closes = [B.get(t - 60 * i) for i in range(241, 0, -1)]
        if any(x is None for x in closes):
            continue
        f = ta(closes)
        qi = r["qi"]
        base = [qi.z, qi.r1, qi.r5, qi.r15, qi.vr, 1e4 * qi.sigma_1m, r["frac"], r["k"], r["hour"], (r["open"] // 86400) % 7,
                f["rsi14"], f["macd_bp"], f["macd_hist_bp"], f["boll_b"], f["ema9_r"], f["ema21_r"], f["rv15"], f["rv60"],
                f["ret1"], f["ret5"], f["ret15"], f["ret60"], f["pos1h"], f["pos4h"], r["ask"] - r["bid"]]
        X.append(base); Xm.append(base + [BP.Q.logit(r["mid"])]); y.append(r["y"]); meta.append(r)
    X, Xm, y = np.asarray(X), np.asarray(Xm), np.asarray(y)
    days = np.asarray([m["day"] for m in meta]); mid = np.asarray([m["mid"] for m in meta])
    uniq = sorted(set(days.tolist()))
    print(f"usable rows {len(y)}; days {len(uniq)}; base rate {y.mean():.3f}; market mid Brier {np.mean((mid - y) ** 2):.4f}")
    import xgboost as xgb
    from sklearn.ensemble import HistGradientBoostingClassifier
    preds = {("xgb", "no_mid"): np.full(len(y), np.nan), ("xgb", "with_mid"): np.full(len(y), np.nan),
             ("hgb", "no_mid"): np.full(len(y), np.nan), ("hgb", "with_mid"): np.full(len(y), np.nan)}
    for i, d in enumerate(uniq):
        if i < 14:
            continue
        tr = days < d; te = days == d
        if te.sum() == 0:
            continue
        for name, feats in (("no_mid", X), ("with_mid", Xm)):
            m1 = xgb.XGBClassifier(n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
                                   reg_lambda=1.0, min_child_weight=20, verbosity=0, n_jobs=4)
            m1.fit(feats[tr], y[tr]); preds[("xgb", name)][te] = m1.predict_proba(feats[te])[:, 1]
            m2 = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=300, min_samples_leaf=40, l2_regularization=1.0)
            m2.fit(feats[tr], y[tr]); preds[("hgb", name)][te] = m2.predict_proba(feats[te])[:, 1]
    ok = ~np.isnan(preds[("xgb", "no_mid")])
    print(f"\nout-of-sample rows {ok.sum()} ({len(set(days[ok].tolist()))} days). Brier (lower is better); market mid {np.mean((mid[ok]-y[ok])**2):.4f}")
    print("model          features    Brier    Brier − mid   by minute k (1,4,7,10,13): model − mid")
    for (mn, fs), p in preds.items():
        b = np.mean((p[ok] - y[ok]) ** 2)
        byk = []
        for k in (1, 4, 7, 10, 13):
            sel = ok & (np.asarray([m["k"] for m in meta]) == k)
            byk.append(np.mean((p[sel] - y[sel]) ** 2) - np.mean((mid[sel] - y[sel]) ** 2))
        print(f"{mn:6s} {fs:12s}  {b:.4f}   {b - np.mean((mid[ok]-y[ok])**2):+.4f}      " + "  ".join(f"{v:+.4f}" for v in byk))
    # taker rule on each model's probability, first minute per window where EV beats the margin
    print("\ntaker: buy the side whose model p beats ask + fee by margin, first minute per window; mean P&L per contract, day-clustered")
    by_w = defaultdict(list)
    for i, m in enumerate(meta):
        if ok[i]:
            by_w[m["ticker"]].append(i)
    for (mn, fs), p in preds.items():
        for margin in (0.0, 0.02, 0.04):
            pnl, dd = [], []
            for tk, idx in by_w.items():
                for i in sorted(idx, key=lambda j: meta[j]["k"]):
                    r = meta[i]; pr = p[i]
                    ev_yes = pr - r["ask"] - BP.fee(r["ask"]); no_px = 1 - r["bid"]; ev_no = (1 - pr) - no_px - BP.fee(no_px)
                    if max(ev_yes, ev_no) > margin:
                        if ev_yes >= ev_no:
                            pnl.append((1 - r["ask"] - BP.fee(r["ask"])) if r["y"] == 1 else -(r["ask"] + BP.fee(r["ask"])))
                        else:
                            pnl.append((1 - no_px - BP.fee(no_px)) if r["y"] == 0 else -(no_px + BP.fee(no_px)))
                        dd.append(r["day"]); break
            if len(pnl) > 5:
                m_, se = BP.clustered(pnl, dd)
                print(f"  {mn:4s} {fs:9s} margin {margin:.2f}: n={len(pnl):4d}  mean {100*m_:+.2f}c  t {m_/se if se else float('nan'):+.2f}")
            else:
                print(f"  {mn:4s} {fs:9s} margin {margin:.2f}: n={len(pnl)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
