"""Coin Race question 3 (farming fill cost), a SCREEN on the public prints.

A hypothetical resting bid of Q contracts on one side of one market (a YES bid, or a NO bid) is filled
by takers who SELL into that side: a print with taker_side='no' fills resting YES bids at yes_price, a
print with taker_side='yes' fills resting NO bids at no_price (checked on the tape against the book
samples; docs/math/coinrace-research.md). Prices are compared in whole cents.

Placements (per side, per market-window):
  fixed P (1, 2, 3c), FIRST in queue  -- every print at x <= P passes through us first: fills = min(Q, cum V(x<=P))
  fixed P, BEHIND A (=1,000)          -- the farmers' lot ahead absorbs the first A: fills = min(Q, max(0, cum V(x<=P) - A))
  FRONT: one tick in front of the side's best bid at the time (p = b + 1c), first in queue, quoted only
         while p <= cap (10c; our 1,000 at p is then the side's reference, so 'reference <= 10c')
The best bid b is the last book observation at or before the print: the venue's 1-minute candle close
(yes_bid close for YES; 1 - yes_ask close for NO) whose period ENDED at or before the print, or the farm
scorer's once-a-minute sample (`--book-source sample`, 2026-10-03 19:25Z on). No look-ahead.

A fill at our price p settles at v (YES side: the market's settlement value, 1 / 0 / 0.5 in a tie; NO
side: 1 - that): P&L = fills x (v - p). Before anyone responds: our size does not change the takers'
flow, nobody steps in front of us inside a minute, the queue ahead is constant.

    python analysis/coinrace/farm_fill_screen.py --trades DATA/trades.parquet --markets DATA/pricing_markets.parquet \
        --candles DATA/pricing_book_1m.parquet [--book DATA/book_minute.csv] --since 2026-10-02T20:00:00Z
"""
from __future__ import annotations

import argparse
import json
import math

import numpy as np
import pandas as pd

Q = 1000.0
AHEAD = 1000.0


def side_prints(trades: pd.DataFrame) -> pd.DataFrame:
    """One row per print that SELLS into a resting bid: side 'yes' (taker_side='no', price yes_price) or
    side 'no' (taker_side='yes', price no_price). Price in whole cents."""
    y = trades[trades.taker_side == "no"].assign(side="yes", x_c=lambda d: (d.yes_price * 100).round().astype(int))
    n = trades[trades.taker_side == "yes"].assign(side="no", x_c=lambda d: (d.no_price * 100).round().astype(int))
    out = pd.concat([y, n], ignore_index=True)
    return out.sort_values(["ticker", "side", "created_ts", "trade_id"], kind="mergesort").reset_index(drop=True)


def attach_best_bid(pr: pd.DataFrame, book: pd.DataFrame) -> pd.DataFrame:
    """book: ticker, ts (epoch s, the moment the observation is valid), b_yes_c, b_no_c (whole cents, 0 = no
    bid). Attaches the last observation at ts <= print time per ticker (merge_asof, backward)."""
    pr = pr.assign(_ts=pr.created_ts.astype(float)).sort_values("_ts", kind="mergesort")
    bk = book.sort_values("ts", kind="mergesort")
    m = pd.merge_asof(pr, bk, left_on="_ts", right_on="ts", by="ticker", direction="backward")
    m["b_c"] = np.where(m.side == "yes", m.b_yes_c, m.b_no_c)
    if "ref_yes_c" in m:
        m["ref_c"] = np.where(m.side == "yes", m.ref_yes_c, m.ref_no_c)
    m["book_age_s"] = m._ts - m.ts
    m = m.sort_values(["ticker", "side", "_ts", "trade_id"], kind="mergesort").reset_index(drop=True)
    # fallback where no book observation precedes the print (the window's first minute, before any candle
    # closes): the previous print INTO THIS SIDE of this market -- a bid that was there. Tagged.
    prev_x = m.groupby(["ticker", "side"]).x_c.shift(1)
    m["b_src"] = np.where(m.b_c.notna(), "book", np.where(prev_x.notna(), "prev_print", "none"))
    m["b_c"] = m.b_c.where(m.b_c.notna(), prev_x)
    return m


def fills_fixed(pr: pd.DataFrame, p_c: int, ahead: float, q: float = Q) -> pd.Series:
    """Contracts filled to our bid at p_c per print row (time order within ticker/side)."""
    elig = np.where(pr.x_c.values <= p_c, pr["count"].values, 0.0)
    cum = pd.Series(elig, index=pr.index).groupby([pr.ticker, pr.side]).cumsum()
    prev = cum - elig
    return np.clip(cum - ahead, 0, q) - np.clip(prev - ahead, 0, q)


def fills_front(pr: pd.DataFrame, cap_c: int | None, q: float = Q) -> tuple[pd.Series, pd.Series]:
    """One tick in front of the best bid at the time, first in queue. Returns (fills, our price in cents).
    Rows with no book observation are not quoted."""
    b = pr.b_c.fillna(-1).astype(int)
    p = (b + 1).where(b >= 0, -1)
    p = p.where(p <= 98, -1)                                   # a 99c bid disqualifies the side; never quote it
    if cap_c is not None:
        p = p.where(p <= cap_c, -1)
    elig = np.where((p.values > 0) & (pr.x_c.values <= p.values), pr["count"].values, 0.0)
    cum = pd.Series(elig, index=pr.index).groupby([pr.ticker, pr.side]).cumsum()
    prev = cum - elig
    return pd.Series(np.clip(cum, 0, q) - np.clip(prev, 0, q), index=pr.index), p


def fills_front_live(pr: pd.DataFrame, cap_c: int | None, q: float = Q) -> tuple[pd.Series, pd.Series]:
    """One tick in front of the LIVE best bid: a quoter that re-posts on every book change. The best bid just
    before a sell sweep is the sweep's top print price (all prints of one taker order share created_ts), so
    every contract sold into the side fills us first at top + 1c, while top + 1c <= cap. The minute-book
    placement (fills_front) brackets it from the other side: a quote left at b + 1 while the book falls pays
    more per fill."""
    top = pr.groupby(["ticker", "side", "created_ts"]).x_c.transform("max")
    p = top + 1
    p = p.where(p <= 98, -1)
    if cap_c is not None:
        p = p.where(p <= cap_c, -1)
    elig = np.where(p.values > 0, pr["count"].values, 0.0)
    cum = pd.Series(elig, index=pr.index).groupby([pr.ticker, pr.side]).cumsum()
    prev = cum - elig
    return pd.Series(np.clip(cum, 0, q) - np.clip(prev, 0, q), index=pr.index), p


def pnl(pr: pd.DataFrame, fills: pd.Series, p_c) -> pd.Series:
    """Settlement P&L in dollars per print row: fills x (v - p); v = settlement value for YES, 1 - it for NO."""
    v = np.where(pr.side == "yes", pr.settle, 1.0 - pr.settle)
    return fills * (v - np.asarray(p_c) / 100.0)


def per_market_window(pr: pd.DataFrame, cols: list[str], universe: pd.DataFrame) -> pd.DataFrame:
    """Sum cols per ticker over both sides, re-indexed on EVERY market-window of the universe (zeros where
    nothing printed): the denominator is every market-window, not only those with fills."""
    g = pr.groupby("ticker")[cols].sum()
    out = universe.set_index("ticker")[["event_ticker", "close_ts"]].join(g, how="left").fillna({c: 0.0 for c in cols})
    return out


def cluster_ci(values: pd.Series, clusters: pd.Series, reps: int = 2000, seed: int = 7) -> tuple[float, float, float]:
    """Mean per market-window with a cluster bootstrap 95% CI (clusters = windows or days)."""
    df = pd.DataFrame({"v": values.values, "c": clusters.values})
    s = df.groupby("c").v.agg(["sum", "count"])
    sums, cnts = s["sum"].values, s["count"].values
    rng = np.random.default_rng(seed)
    k = len(sums)
    idx = rng.integers(0, k, size=(reps, k))
    boots = sums[idx].sum(1) / cnts[idx].sum(1)
    return float(sums.sum() / cnts.sum()), float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def q(sql: str) -> pd.DataFrame:
    import duckdb
    duckdb.sql("SET threads=2")                      # the operator's laptop: keep it quiet
    return duckdb.sql(sql).df()


def load_book_candles(path: str) -> pd.DataFrame:
    c = q(f"SELECT ticker, end_period_ts, yes_bid_close, yes_ask_close FROM read_parquet('{path}')")
    return pd.DataFrame({"ticker": c.ticker, "ts": c.end_period_ts.astype(float),
                         "b_yes_c": (c.yes_bid_close * 100).round(),
                         "b_no_c": ((1 - c.yes_ask_close) * 100).round()})


def load_book_sample(path: str) -> pd.DataFrame:
    s = pd.read_csv(path)
    return pd.DataFrame({"ticker": s.ticker, "ts": s.t.astype(float), "b_yes_c": (s.yes_best * 100).round(),
                         "b_no_c": (s.no_best * 100).round(), "ref_yes_c": (s.ref_yes * 100).round(),
                         "ref_no_c": (s.ref_no * 100).round()})


def run(trades: pd.DataFrame, markets: pd.DataFrame, book: pd.DataFrame, pull_last_s: float = 0.0) -> dict:
    """All placements on one population. markets: ticker, event_ticker, open_ts, close_ts, settle."""
    pr = side_prints(trades.merge(markets[["ticker", "settle", "open_ts", "close_ts", "event_ticker"]], on="ticker", how="inner"))
    pr = attach_best_bid(pr, book)
    pr["minute"] = ((pr._ts - pr.open_ts) // 60).clip(0, 14).astype(int)
    if pull_last_s > 0:                                        # orders pulled at T - pull_last_s: no fills after
        pr = pr[pr._ts < pr.close_ts - pull_last_s].copy()
    cols = []
    for p_c in (1, 2, 3):
        for tag, ahead in (("first", 0.0), ("behind", AHEAD)):
            f = fills_fixed(pr, p_c, ahead)
            pr[f"f_{p_c}c_{tag}"] = f
            pr[f"pl_{p_c}c_{tag}"] = pnl(pr, f, p_c)
            cols += [f"f_{p_c}c_{tag}", f"pl_{p_c}c_{tag}"]
    f, p = fills_front_live(pr, 10)
    pr["f_front_live_cap10"], pr["pl_front_live_cap10"], pr["p_front_live_cap10"] = f, pnl(pr, f, p.clip(lower=0)), p
    cols += ["f_front_live_cap10", "pl_front_live_cap10"]
    for tag, cap in (("front_cap10", 10), ("front_uncapped", None)):
        f, p = fills_front(pr, cap)
        pr[f"f_{tag}"] = f
        pr[f"pl_{tag}"] = pnl(pr, f, p.clip(lower=0))
        pr[f"p_{tag}"] = p
        cols += [f"f_{tag}", f"pl_{tag}"]
    if "ref_c" in pr:                                          # the scorer's f1000c placement: reference + 1c, quoted
        f, p = fills_front(pr.assign(b_c=pr.ref_c), 11)        # while the reference is <= 10c; first in queue (an upper
        rq = pr.ref_c.fillna(99) <= 10                         # bound: < 200 may rest above the reference)
        f, p = f.where(rq, 0.0), p.where(rq, -1)
        pr["f_front_ref_cap10"], pr["pl_front_ref_cap10"] = f, pnl(pr, f, p.clip(lower=0))
        cols += ["f_front_ref_cap10", "pl_front_ref_cap10"]
    return {"prints": pr, "cols": cols}


def summarise(res: dict, markets: pd.DataFrame, reward_lo: float, reward_hi: float) -> dict:
    pr, cols = res["prints"], res["cols"]
    mw = per_market_window(pr, cols, markets)
    win = mw.event_ticker
    day = (mw.close_ts // 86400).astype(int)
    out = {"n_market_windows": int(len(mw)), "n_windows": int(win.nunique()),
           "n_days": float((mw.close_ts.max() - mw.close_ts.min()) / 86400 + 15 / 1440),
           "book_age_s_p50_p90": [float(x) for x in np.nanpercentile(pr.book_age_s, [50, 90])] if pr.book_age_s.notna().any() else None,
           "prints_without_book_obs": int(pr.b_c.isna().sum()), "policies": {}}
    pols = [c[2:] for c in cols if c.startswith("f_")]
    out["best_bid_source_prints"] = {k: int(v) for k, v in pr.b_src.value_counts().items()}
    for pol in pols:
        f, pl = mw[f"f_{pol}"], mw[f"pl_{pol}"]
        m, lo, hi = cluster_ci(pl, win)
        _, dlo, dhi = cluster_ci(pl, day)
        by_min = pr.groupby("minute")[[f"f_{pol}", f"pl_{pol}"]].sum() / len(mw)
        out["policies"][pol] = {
            "fills_per_mw": float(f.mean()), "frac_mw_any_fill": float((f > 0).mean()),
            "fills_per_mw_p50_p90_p99_max": [float(x) for x in np.percentile(f, [50, 90, 99, 100])],
            "pnl_per_mw": m, "ci95_window_clustered": [lo, hi], "ci95_day_clustered": [dlo, dhi],
            "pnl_per_mw_p1_p10_p50_max": [float(x) for x in np.percentile(pl, [1, 10, 50, 100])],
            "pnl_per_fill_c": float(100 * pl.sum() / f.sum()) if f.sum() > 0 else None,
            "loss_part_per_mw": float(pl.clip(upper=0).mean()), "win_part_per_mw": float(pl.clip(lower=0).mean()),
            "mw_with_pnl_over_100usd": int((pl > 100).sum()),
            "pnl_per_mw_without_those": float(pl[pl <= 100].sum() / len(pl)),
            "pnl_per_day_480mw": float(m * 480),
            "cost_share_of_reward": [float(-m / reward_hi), float(-m / reward_lo)],
            "by_side": {sd: {"fills_per_mw": float(pr.loc[pr.side == sd, f"f_{pol}"].sum() / len(mw)),
                             "pnl_per_mw": float(pr.loc[pr.side == sd, f"pl_{pol}"].sum() / len(mw)),
                             "frac_mw_any_fill": float((pr[pr.side == sd].groupby("ticker")[f"f_{pol}"].sum() > 0).sum() / len(mw))}
                        for sd in ("yes", "no")},
            "by_minute_fills": {int(k): float(v) for k, v in by_min[f"f_{pol}"].items()},
            "by_minute_pnl": {int(k): float(v) for k, v in by_min[f"pl_{pol}"].items()},
        }
    return out


def realised_into_bids(trades: pd.DataFrame, markets: pd.DataFrame, max_c: int = 5) -> pd.DataFrame:
    """The farming doc's estimator (docs/math/kalshi-incentive-farming.md, 80 windows 10-02 23:15Z..10-03 19:00Z):
    the realised settlement P&L of every print into a resting bid at <= max_c, at the PRINTED price, both sides.
    Reproducing its published figures from this tape is the control on the side mapping and the settlement join."""
    pr = side_prints(trades.merge(markets[["ticker", "settle", "event_ticker"]], on="ticker", how="inner"))
    pr = pr[pr.x_c <= max_c].copy()
    pr["pl"] = pnl(pr, pr["count"], pr.x_c)
    return pr


def load_markets(path: str) -> pd.DataFrame:
    return q(f"""SELECT ticker, event_ticker, epoch(open_time) AS open_ts, epoch(close_time) AS close_ts,
                     CAST(settlement_value AS DOUBLE) AS settle, result FROM read_parquet('{path}')""")


def load_trades(path: str) -> pd.DataFrame:
    return q(f"""SELECT ticker, epoch(created_time) AS created_ts, yes_price, no_price, count, taker_side, trade_id
                 FROM read_parquet('{path}')""")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trades", required=True)
    ap.add_argument("--markets", required=True)
    ap.add_argument("--candles", required=True)
    ap.add_argument("--book", default=None, help="book_minute.csv: use the scorer's samples as the best-bid source")
    ap.add_argument("--since", default=None)
    ap.add_argument("--until", default=None)
    ap.add_argument("--pull-last-s", type=float, default=0.0)
    ap.add_argument("--reward-per-day", default="2566,3087", help="paper reward f1000c, $/day over 480 market-windows")
    a = ap.parse_args()
    mk = load_markets(a.markets)
    if a.since:
        mk = mk[mk.close_ts > pd.Timestamp(a.since).timestamp()]
    if a.until:
        mk = mk[mk.close_ts <= pd.Timestamp(a.until).timestamp()]
    tr = load_trades(a.trades)
    # the universe is every market-window the trades file COVERS (a newest-first file covers a suffix of the
    # history; market-windows before it would enter the denominator with zero fills)
    covered_from = float(q(f"SELECT min(epoch(window_end_utc)) AS m FROM read_parquet('{a.trades}')").m.iloc[0])
    mk = mk[mk.close_ts >= covered_from]
    tr = tr[tr.ticker.isin(mk.ticker)]
    book = load_book_sample(a.book) if a.book else load_book_candles(a.candles)
    book = book[book.ticker.isin(mk.ticker)]
    lo, hi = (float(x) / 480 for x in a.reward_per_day.split(","))
    res = run(tr, mk, book, a.pull_last_s)
    s = summarise(res, mk, lo, hi)
    s["reward_per_mw_usd"] = [lo, hi]
    s["trades_file_covers_windows_from_ts"] = covered_from
    s["book_source"] = "farm scorer sample" if a.book else "venue 1-min candles"
    print(json.dumps(s, indent=1))


if __name__ == "__main__":
    main()
