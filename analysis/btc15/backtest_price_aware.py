"""Which price-aware rules would have made money on the 15-minute Bitcoin contract?

Point-in-time: at minute k after the open (t = open + 60k) the rule sees Kalshi's
last yes bid/ask of that minute, Coinbase's BTC close of the minute ending at t,
and volatility from the 60 minutes before t. Nothing after t.

Entry: the first minute k (1..13, so at least 2 min left) where the rule's
probability beats the price by more than the fee plus a margin; one contract per
window, held to settlement. Fee: the Polymarket US taker fee 0.0695*p*(1-p),
rounded up to the cent (the harness's conservative reading).

Split: chronological, the first 60% of days fit anything that is fitted; every
number below the line is on the last 40%, which nothing was fitted on.
Interval: mean P&L per contract with a day-clustered standard error.
"""
from __future__ import annotations

import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

#: The data directory fetch_kalshi_history.py wrote (windows.jsonl, candles.jsonl, btc_1m.jsonl).
HERE = os.environ.get("MERIDIAN_BTC_RESEARCH_DIR") or os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, REPO)
from core.fees import POLYMARKET_TAKER as FEE  # noqa: E402  -- the venue's taker coefficient for this period


def fee(p: float) -> float:
    return math.ceil(FEE * p * (1 - p) * 100 - 1e-9) / 100      # identical to core.btc15.quant.fee


def phi(z: np.ndarray) -> np.ndarray:
    from scipy.special import ndtr
    return ndtr(z)


def load():
    W = [json.loads(l) for l in open(os.path.join(HERE, "windows.jsonl"))]
    C = {}
    for l in open(os.path.join(HERE, "candles.jsonl")):
        d = json.loads(l)
        C[d["ticker"]] = {r["t"]: r for r in d["rows"]}
    B = {}
    for l in open(os.path.join(HERE, "btc_1m.jsonl")):
        d = json.loads(l)
        B[d["t"]] = d["close"]          # candle START -> close at start+60
    return W, C, B


from core.btc15 import quant as Q  # noqa: E402  -- the SAME feature code the live harness runs


def build(W, C, B):
    rows = []
    for w in W:
        if w["result"] not in ("yes", "no") or w["strike"] is None:
            continue
        y = 1.0 if w["result"] == "yes" else 0.0
        K = float(w["strike"])
        c = C.get(w["ticker"]) or {}
        length = w["close"] - w["open"]
        for k in range(1, 14):
            t = w["open"] + 60 * k
            q = c.get(t)
            if not q or q["bid"] is None or q["ask"] is None:
                continue
            bid, ask = float(q["bid"]), float(q["ask"])
            if not (0.01 <= bid < ask <= 0.99):
                continue
            # 1-minute closes ending AT t (Coinbase candle starting t-60 closes at t), oldest first
            closes = [B.get(t - 60 * i) for i in range(241, 0, -1)]
            if any(x is None for x in closes[-61:]):
                continue
            if any(x is None for x in closes):
                closes = closes[-61:]                    # no volatility ratio without 4 h of history
            s = closes[-1]
            tau = w["close"] - t
            qi = Q.inputs(s, K, tau, closes)
            if qi is None:
                continue
            rows.append({"lo": None if q.get("lo") is None else float(q["lo"]),
                         "hi": None if q.get("hi") is None else float(q["hi"]),
                         "ticker": w["ticker"], "day": w["open"] // 86400, "open": w["open"], "k": k, "tau": tau,
                         "frac": (t - w["open"]) / length,
                         "bid": bid, "ask": ask, "mid": (bid + ask) / 2, "qi": qi, "z": qi.z, "y": y,
                         "hour": (w["open"] % 86400) // 3600})
    return rows


def clustered(pnl, day):
    pnl, day = np.asarray(pnl), np.asarray(day)
    n = len(pnl)
    if n < 2:
        return float("nan"), float("nan")
    m = pnl.mean()
    G = len(set(day.tolist()))
    s = defaultdict(float)
    for p, d in zip(pnl, day):
        s[d] += p - m
    var = sum(v * v for v in s.values()) / n ** 2 * (G / max(G - 1, 1))
    return m, math.sqrt(var)


def trade(rows_by_w, prob, margin, kmin=1, kmax=13):
    """First minute per window where prob beats the price + fee + margin."""
    out = []
    for tk, rs in rows_by_w.items():
        for r in rs:
            if not (kmin <= r["k"] <= kmax):
                continue
            p = prob(r)
            if p is None:
                continue
            ev_yes = p - r["ask"] - fee(r["ask"])
            no_price = 1 - r["bid"]
            ev_no = (1 - p) - no_price - fee(no_price)
            if ev_yes > margin and ev_yes >= ev_no:
                pnl = r["y"] - r["ask"] - fee(r["ask"])
                out.append((pnl, r["day"], r["ask"] + fee(r["ask"]), r["k"], "YES", ev_yes))
                break
            if ev_no > margin:
                pnl = (1 - r["y"]) - no_price - fee(no_price)
                out.append((pnl, r["day"], no_price + fee(no_price), r["k"], "NO", ev_no))
                break
    return out


def make(rows_by_w, prob, margin, k_post=1, through=True):
    """Post ONE resting order at minute k_post on the side the probability favours over the
    mid, at (fair - margin) rounded down to the cent; it rests until 2 min before the close.
    Filled if a later minute's trade goes THROUGH the price (through=True) or touches it.
    Maker fee 0 on this venue. Held to settlement."""
    out = []
    for tk, rs in rows_by_w.items():
        r0 = next((x for x in rs if x["k"] == k_post), None)
        if r0 is None:
            continue
        p = prob(r0)
        if p is None:
            continue
        later = [x for x in rs if x["k"] > k_post]
        if p >= r0["mid"]:
            b = math.floor((p - margin) * 100 + 1e-9) / 100
            if not (0.01 <= b < r0["ask"]):
                continue
            hit = any(x["lo"] is not None and (x["lo"] < b - 1e-9 if through else x["lo"] <= b + 1e-9) for x in later)
            if hit:
                out.append((r0["y"] - b, r0["day"], b, k_post, "YES", p - b))
        else:
            q = math.floor(((1 - p) - margin) * 100 + 1e-9) / 100
            a = 1 - q                      # a NO bid at q is a YES offer at 1 - q
            if not (0.01 <= q and a > r0["bid"]):
                continue
            hit = any(x["hi"] is not None and (x["hi"] > a + 1e-9 if through else x["hi"] >= a - 1e-9) for x in later)
            if hit:
                out.append(((1 - r0["y"]) - q, r0["day"], q, k_post, "NO", (1 - p) - q))
    return out


def report(name, tr):
    if not tr:
        print(f"  {name:44s}  n=   0")
        return
    pnl = [x[0] for x in tr]
    m, se = clustered(pnl, [x[1] for x in tr])
    staked = sum(x[2] for x in tr)
    hit = np.mean([x[0] > 0 for x in tr])
    print(f"  {name:44s}  n={len(tr):5d}  hit={hit:.3f}  mean={m*100:+6.2f}c  se={se*100:5.2f}c  "
          f"t={m/se if se else float('nan'):+5.2f}  total=${sum(pnl):+8.2f}  roi={sum(pnl)/staked*100:+6.2f}%")


def logit(p):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def main():
    W, C, B = load()
    rows = build(W, C, B)
    days = sorted({r["day"] for r in rows})
    cut = days[int(len(days) * 0.6)]
    train = [r for r in rows if r["day"] < cut]
    test = [r for r in rows if r["day"] >= cut]
    print(f"rows {len(rows)}  windows {len({r['ticker'] for r in rows})}  days {len(days)}  "
          f"train days {sum(d < cut for d in days)}  test days {sum(d >= cut for d in days)}")

    # ---- calibration: Brier by minute, market mid vs random walk
    print("\nBrier by minute k (test): market mid | random walk | n")
    for k in (1, 3, 5, 8, 10, 12, 13):
        rs = [r for r in test if r["k"] == k]
        if not rs:
            continue
        y = np.array([r["y"] for r in rs])
        bm = np.mean((np.array([r["mid"] for r in rs]) - y) ** 2)
        br = np.mean((phi(np.array([r["z"] for r in rs])) - y) ** 2)
        print(f"  k={k:2d}  {bm:.4f} | {br:.4f} | {len(rs)}")

    # ---- a logistic model fitted on train: market logit + random-walk z + momentum + vol ratio
    from sklearn.linear_model import LogisticRegression
    def X(r):
        return Q.vector(r["qi"], r["mid"], r["frac"])
    Xtr = np.array([X(r) for r in train]); ytr = np.array([r["y"] for r in train])
    lr = LogisticRegression(C=1.0, max_iter=2000).fit(Xtr, ytr)
    print("\nlogistic coefficients [logit(mid), z, r1, r5, r15, vol ratio, frac]:",
          np.round(lr.coef_[0], 3).tolist(), "intercept", round(float(lr.intercept_[0]), 3))
    Xte = np.array([X(r) for r in test]); yte = np.array([r["y"] for r in test])
    pte = lr.predict_proba(Xte)[:, 1]
    print(f"test Brier: logistic {np.mean((pte - yte) ** 2):.4f}  market {np.mean((np.array([r['mid'] for r in test]) - yte) ** 2):.4f}")
    phat = {id(r): p for r, p in zip(test, pte)}

    by_w = defaultdict(list)
    for r in test:
        by_w[r["ticker"]].append(r)
    for rs in by_w.values():
        rs.sort(key=lambda r: r["k"])

    print("\nTEST SET strategies (one contract per window, held to settlement):")
    # controls
    fav = []
    for rs in by_w.values():
        r = next((x for x in rs if x["k"] == 1), None)
        if r is None:
            continue
        if r["mid"] >= 0.5:
            fav.append((r["y"] - r["ask"] - fee(r["ask"]), r["day"], r["ask"] + fee(r["ask"]), 1, "YES", 0))
        else:
            np_ = 1 - r["bid"]
            fav.append(((1 - r["y"]) - np_ - fee(np_), r["day"], np_ + fee(np_), 1, "NO", 0))
    report("CONTROL always-the-favourite at minute 1", fav)
    report("CONTROL market mid as the probability (m=0)", trade(by_w, lambda r: r["mid"], 0.0))
    for m in (0.0, 0.02, 0.04, 0.06, 0.10):
        report(f"random walk, margin {m:.2f}", trade(by_w, lambda r: float(phi(np.array([r["z"]]))[0]), m))
    for m in (0.0, 0.02, 0.04, 0.06):
        report(f"logistic (fitted on train), margin {m:.2f}", trade(by_w, lambda r: phat[id(r)], m))
    for kmin in (8, 10, 12):
        report(f"random walk, margin 0.04, only k>={kmin}",
               trade(by_w, lambda r: float(phi(np.array([r["z"]]))[0]), 0.04, kmin=kmin))
        report(f"logistic, margin 0.02, only k>={kmin}", trade(by_w, lambda r: phat[id(r)], 0.02, kmin=kmin))

    print("\nTEST SET maker orders (rest at fair - margin, fee 0; 'through' = a trade crossed our price):")
    rw = lambda r: float(phi(np.array([r["z"]]))[0])
    lg = lambda r: phat[id(r)]
    for name, pr in (("CONTROL market mid", lambda r: r["mid"]), ("random walk", rw), ("logistic", lg)):
        for m in (0.01, 0.02, 0.04):
            for kp in (1, 5):
                report(f"{name}, margin {m:.2f}, post k={kp}, through", make(by_w, pr, m, kp, True))
        report(f"{name}, margin 0.02, post k=1, touch (optimistic)", make(by_w, pr, 0.02, 1, False))

    # ---- SELECTION ON TRAIN ONLY, then the selected configurations read once on TEST
    by_tr = defaultdict(list)
    for r in train:
        by_tr[r["ticker"]].append(r)
    for rs in by_tr.values():
        rs.sort(key=lambda r: r["k"])
    phat_tr = {id(r): pp for r, pp in zip(train, lr.predict_proba(Xtr)[:, 1])}
    rw = lambda r: float(phi(np.array([r["z"]]))[0])
    probs_tr = {"walk": rw, "logistic": lambda r: phat_tr[id(r)], "mid": lambda r: r["mid"]}
    probs_te = {"walk": rw, "logistic": lambda r: phat[id(r)], "mid": lambda r: r["mid"]}
    grid = []
    for pn in ("walk", "logistic"):
        for mg in (0.0, 0.02, 0.04, 0.06):
            for km in (1, 5, 8, 10):
                grid.append(("taker", pn, mg, km))
        for mg in (0.01, 0.02, 0.03, 0.04, 0.06):
            for kp in (1, 3, 5, 8):
                grid.append(("maker", pn, mg, kp))
    def run(cfg, bw, probs):
        kind, pn, mg, kk = cfg
        return trade(bw, probs[pn], mg, kmin=kk) if kind == "taker" else make(bw, probs[pn], mg, kk, True)
    scored = []
    for cfg in grid:
        tr = run(cfg, by_tr, probs_tr)
        if len(tr) < 100:
            continue
        m_, se_ = clustered([x[0] for x in tr], [x[1] for x in tr])
        scored.append((m_ / se_ if se_ else 0, m_, len(tr), cfg))
    scored.sort(reverse=True)
    print(f"\nSELECTION: {len(grid)} configurations, {len(scored)} with >= 100 train trades; top 5 by train t, then TEST once:")
    for t_, m_, n_, cfg in scored[:5]:
        print(f"  train {cfg}: n={n_} mean={m_*100:+.2f}c t={t_:+.2f}")
        report(f"    TEST {cfg[0]} {cfg[1]} m={cfg[2]} k={cfg[3]}", run(cfg, by_w, probs_te))
    for kind in ("taker", "maker"):
        cfg = (kind, "mid", 0.02, 5)
        report(f"    TEST CONTROL {kind} on the market mid, m=0.02 k=5", run(cfg, by_w, probs_te))

    if "--save" in sys.argv:
        Xall = np.array([X(r) for r in rows]); yall = np.array([r["y"] for r in rows])
        full = LogisticRegression(C=1.0, max_iter=2000).fit(Xall, yall)
        import datetime as _dt
        prov = {"intercept": float(full.intercept_[0]), "coef": [float(c) for c in full.coef_[0]],
                "features": ["logit(mid)", "z", "r1", "r5", "r15", "vol_ratio", "frac"],
                "fitted_on": "Kalshi KXBTC15M settled windows with per-minute quotes, Coinbase BTC-USD 1m",
                "from": str(_dt.datetime.fromtimestamp(min(r["open"] for r in rows), _dt.timezone.utc)),
                "to": str(_dt.datetime.fromtimestamp(max(r["open"] for r in rows), _dt.timezone.utc)),
                "rows": len(rows), "windows": len({r["ticker"] for r in rows}),
                "out_of_sample_brier": {"logistic": float(np.mean((pte - yte) ** 2)),
                                        "market_mid": float(np.mean((np.array([r["mid"] for r in test]) - yte) ** 2))},
                "fitted_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")}
        out = os.path.join(REPO, "core", "btc15", "quant_coef.json")
        json.dump(prov, open(out, "w"), indent=1)
        print("saved", out)

    # same rules on TRAIN, for the in-sample picture (not evidence)
    by_tr = defaultdict(list)
    for r in train:
        by_tr[r["ticker"]].append(r)
    for rs in by_tr.values():
        rs.sort(key=lambda r: r["k"])
    print("\nTRAIN (in-sample, for reference only):")
    report("random walk, margin 0.04", trade(by_tr, lambda r: float(phi(np.array([r["z"]]))[0]), 0.04))


if __name__ == "__main__":
    main()
