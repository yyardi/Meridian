"""PULSE live scorecard: the in-game WNBA model's decisions, scored at settlement.

    docker run --rm --network meridian_default --env-file /opt/meridian/.env \\
      -e DATABASE_URL=postgresql+psycopg://meridian:meridian@postgres:5432/meridian \\
      -v /opt/meridian/core:/app/core -v /opt/meridian/cfb:/app/cfb \\
      -v /opt/meridian/artifacts/reads:/opt/meridian/artifacts/reads \\
      -w /app meridian-api python cfb/run_pulse_live_scorecard.py

Reads `pulse_decisions` (the tape core/pulse/live.py writes; model in
core/pulse/storage.py) and `market_snapshots` on the LOCAL tick database the
engine decides on, both read-only; settles from the venue's own endpoint
through core/settlements.py, whose only write is its cache file under the
reads mount. DAYS (default 45) bounds the read on decided_at. Nothing is
placed, sized or gated.

The PREGAME sibling (`predictions`, core/scorecard.py) was scored for weeks
and reported as PULSE; the live model's own rows had never been scored
against settlement before this file (docs/math/pulse-live-scorecard.md).

What a row is
-------------
One decision of the live loop at one observation of one market. `action` is
'enter' (a maker limit rested at the touch on the side `fair_value` favours),
'exit' (a limit rested against an open position: the profit target, or a stop
at the touch) or 'hold' (a throttled mark while a position rides); there is
no 'none' -- a market the model declined to price leaves no row here (guard
refusals go to pulse_abstentions). Every row carries the model's P(YES) at
that instant (`fair_value`), the touch it saw (`market_bid`, `market_ask`,
YES frame), its resting price (`limit_price`), the desired size
(`contracts`, `stake_usd`, the live-faithful `capped_*` beside them) and the
lifecycle stamps the engine updates in place (`filled_at`, `withdrawn_at`,
`settlement` -- the last only on filled enters). `decided_at` IS the
observation's `captured_at`, which is what makes the fee join below exact.
No order exists behind any row.

Dedupe, deliberate
------------------
`(market_slug, decided_at, action)` is not unique and nothing enforces it: 84
collisions in 19,333 rows on 2026-09-14 -- 24 a YES and a NO enter on one
tick at different prices (two decisions), 60 an exit's profit target and its
stop on one observation (two decisions, correctly sequenced; 7 of them on a
snapshot priced twice, docs/math/one-observation-twice.md). Calibration wants
one (probability, outcome) pair per instant, so it keeps the first-written
row per (market, instant, action). P&L wants one line per bet, so it keeps
one per (market, instant, action, side, limit_price). Both removed counts are
printed beside the tables they apply to.

Settlement
----------
The venue's own label per market, the paper book's route (core/settlements:
0 | 0.5 | 1, memoised). A market the venue has not answered falls back to the
label the engine already stamped on that market's filled enters -- the same
endpoint, asked earlier -- and is counted as such; 0.5 is excluded and
counted; a venue answer that disagrees with a stamped one is counted.

Fee
---
The P&L arm crosses the recorded touch (YES at the ask, NO at 1 - bid) and
holds to settlement, one contract per decision, charging
core.fees.recorded_fee at the coefficient the venue carried on the snapshot
the decision was made on -- joined from market_snapshots on
(market_slug, captured_at = decided_at), because pulse_decisions does not
store it. The venue raised the coefficient at 2026-09-17 04:07Z and this read
spans that instant. A decision whose snapshot is gone (no coefficient) is
excluded from P&L and counted, never charged at today's.

Estimator
---------
A game is one outcome (core/scorecard.py): eighteen markets on one game are
one opinion. Intervals are the cluster-robust sandwich over event_slug with
the G/(G-1) correction and t at df = G-1
(core.quote.adverse_selection.clustered_mean) on the ROW-WEIGHTED mean; the
equal-weight mean of game means is printed beside it with its own t(G-1)
interval, and G_eff = (sum n_g)^2 / sum n_g^2 beside both. Playoffs
(decided_at >= 2026-09-14 UTC) are their own row beside the regular season.

The pure functions are at module level and tested without a database in
tests/test_pulse_live_scorecard.py; the run is under main().
"""
import datetime as dt
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) if "__file__" in globals() else os.getcwd())  # run bare or piped over stdin, like run_paper_book.py
from scipy import stats  # noqa: E402

from core.fees import recorded_fee  # noqa: E402
from core.quote.adverse_selection import clustered_mean  # noqa: E402

UTC = dt.timezone.utc

#: The first playoff day, UTC, on decided_at (the operator's date, 2026-09-14).
PLAYOFFS_FROM = dt.datetime(2026, 9, 14, tzinfo=UTC)
#: Calibration: one (probability, outcome) pair per instant per action.
CALIBRATION_KEY = ("market_slug", "decided_at", "action")
#: P&L: one line per bet -- a side at a price (the 2026-09-14 memory's key).
BET_KEY = ("market_slug", "decided_at", "action", "side", "limit_price")
#: |fair_value - mid| buckets. Fixed here, not fitted to where the mass fell.
#: The first is inside the anchor scorecard's no-bet tolerance (0.02).
GAP_BUCKETS = ((0.00, 0.02), (0.02, 0.05), (0.05, 0.10), (0.10, 0.20), (0.20, 1.01))
#: Log loss clips p into [CLIP, 1 - CLIP]: fair_value is exactly 0 or 1 at
#: minutes_left <= 0 (a step function) and log(0) is not a score. Rows that
#: hit the clip are counted in the `clipped` column.
LOGLOSS_CLIP = 0.001

#: Every decision in the window, with the coefficient of the snapshot it was
#: decided on. The join is an equality on the snapshot table's unique key
#: (market_slug, captured_at): decided_at is copied from captured_at by the
#: engine. The month floor on the snapshot side is what prunes partitions; a
#: mid-month floor alone costs more. Read-only.
DECISIONS_SQL = """
SELECT d.id, d.decided_at, d.event_slug, d.market_slug, d.game_id, d.strategy,
       d.phase, d.action, d.side, d.estimates_version, d.reason, d.binding_constraint,
       d.limit_price::float AS limit_price,
       d.market_bid::float AS bid, d.market_ask::float AS ask,
       d.fair_value::float AS fair_value, d.edge_net::float AS edge_net,
       d.capped_stake_usd::float AS capped_stake_usd,
       d.filled_at, d.mid_at_fill::float AS mid_at_fill, d.withdrawn_at,
       d.settlement AS row_settlement,
       s.fee_coefficient::float AS fee_coefficient
FROM pulse_decisions d
LEFT JOIN market_snapshots s
       ON s.market_slug = d.market_slug AND s.captured_at = d.decided_at
      AND s.captured_at >= :month_floor
WHERE d.decided_at >= :since
ORDER BY d.id
"""


# ---------------------------------------------------------------- populations
def regime(decided_at):
    """'playoffs' from PLAYOFFS_FROM (UTC) on, else 'regular'."""
    return "playoffs" if decided_at >= PLAYOFFS_FROM else "regular"


def dedupe(rows, key):
    """The first-written row (lowest id) per key. Returns (kept, removed)."""
    first = {}
    for r in rows:
        k = tuple(r[c] for c in key)
        if k not in first or r["id"] < first[k]["id"]:
            first[k] = r
    kept = sorted(first.values(), key=lambda r: r["id"])
    return kept, len(rows) - len(kept)


def collisions(rows, key):
    """Groups under `key` holding more than one row, counted by action."""
    groups = defaultdict(list)
    for r in rows:
        groups[tuple(r[c] for c in key)].append(r)
    out = defaultdict(int)
    for g in groups.values():
        if len(g) > 1:
            out[g[0]["action"]] += 1
    return dict(out)


def resolve_settlements(rows, venue_lookup):
    """Per market: the venue's label, else the engine's stamped one, else None.

    `venue_lookup(slug)` -> 0 | 0.5 | 1 | None (core.settlements.settler). The
    stamped label is `settlement` on the market's own filled enters -- the same
    endpoint, asked by the engine earlier. Returns (by_market, counts) where a
    market is scoreable only when by_market[slug] is 0 or 1.
    """
    stamped = defaultdict(set)
    for r in rows:
        if r.get("row_settlement") is not None:
            stamped[r["market_slug"]].add(int(r["row_settlement"]))
    out, counts = {}, dict(venue=0, row=0, half=0, unsettled=0, disagree=0)
    for m in sorted({r["market_slug"] for r in rows}):
        v = venue_lookup(m)
        if v is None:
            s = stamped.get(m)
            if s and len(s) == 1:
                out[m] = next(iter(s))
                counts["row"] += 1
            else:
                out[m] = None
                counts["unsettled"] += 1
            continue
        if v == 0.5:
            out[m] = None
            counts["half"] += 1
            continue
        out[m] = int(v)
        counts["venue"] += 1
        if stamped.get(m) and stamped[m] != {int(v)}:
            counts["disagree"] += 1
    return out, counts


def scoreable(rows, by_market):
    """In-play rows with a model probability, a two-sided touch and a 0/1
    outcome. Everything dropped is counted by reason, never silently."""
    kept, why = [], defaultdict(int)
    for r in rows:
        if r["phase"] != "in_play":
            why["pregame_phase"] += 1
            continue
        y = by_market.get(r["market_slug"])
        if y is None:
            why["unsettled_or_half"] += 1
            continue
        if r["fair_value"] is None:
            why["no_fair_value"] += 1
            continue
        if r["bid"] is None or r["ask"] is None or r["ask"] <= r["bid"]:
            why["no_two_sided_touch"] += 1
            continue
        kept.append({**r, "y": int(y)})
    return kept, dict(why)


# ---------------------------------------------------------------- the arithmetic (pure)
def mid(r):
    return (r["bid"] + r["ask"]) / 2.0


def brier(p, y):
    return (p - y) ** 2


def clipped(p):
    return p < LOGLOSS_CLIP or p > 1.0 - LOGLOSS_CLIP


def logloss(p, y):
    q = min(max(p, LOGLOSS_CLIP), 1.0 - LOGLOSS_CLIP)
    return -math.log(q) if y == 1 else -math.log(1.0 - q)


def bet_side(r):
    """The side the model disagrees toward at this instant, YES frame."""
    return "yes" if r["fair_value"] > mid(r) else "no"


def bet_won(r):
    return (r["y"] == 1) if bet_side(r) == "yes" else (r["y"] == 0)


def gap_bucket(gap):
    for lo, hi in GAP_BUCKETS:
        if lo <= gap < hi:
            return f"[{lo:.2f},{min(hi, 1.0):.2f}{']' if hi > 1.0 else ')'}"
    return None


def taker_stake(side, bid, ask):
    """Dollars at risk on one $1 contract crossing the touch: YES costs the
    ask; NO costs 1 - bid."""
    return ask if side == "yes" else 1.0 - bid


def taker_pnl(side, y, bid, ask, coefficient):
    """Net P&L on one $1 contract crossed at the recorded touch and held to
    settlement y (1 = YES resolved), taker fee charged at `coefficient` --
    the one the venue carried on the snapshot the decision was made on. The
    same arithmetic as run_paper_book.bet_pnl (pinned equal in the tests);
    None is refused by recorded_fee, never charged at today's.

    side 'yes': buy YES at the ask p:      y - p - fee(p)
    side 'no' : buy NO at 1 - bid, p = bid: (1-y) - (1-p) - fee(p)
    """
    if side == "yes":
        p = ask
        return y - p - recorded_fee(p, coefficient)
    p = bid
    return (1 - y) - (1 - p) - recorded_fee(p, coefficient)


def limit_pnl(side, y, limit):
    """The maker arm: one contract AT THE RESTED LIMIT, no fee (the venue
    charges makers nothing), held to settlement. ASSUMES THE FILL -- the row
    joined the touch, so this is taker_pnl plus the spread plus the fee on
    every row, before any fill selection. Printed to show the size of that
    flattery, never as a result."""
    return (y - limit) if side == "yes" else (limit - y)


def lifecycle_arm(r):
    """withdrawn_at, not filled_at IS NULL, names the withdrawn arm: the
    complement merges 'posted and the price left' with 'never posted'."""
    if r["filled_at"] is not None:
        return "filled"
    if r["withdrawn_at"] is not None:
        return "withdrawn"
    return "neither"


def signed_mid_move(r):
    """Mid at fill minus mid at decision, in cents, signed to the position
    (+ = moved in the position's favour). None without a recorded fill mid."""
    if r["mid_at_fill"] is None:
        return None
    move = r["mid_at_fill"] - mid(r)
    return 100.0 * (move if r["side"] == "yes" else -move)


# ---------------------------------------------------------------- the estimator
def cluster_stats(values_by_game):
    """Row-weighted mean with the sandwich interval (CR1, t at df = G-1),
    the equal-weight mean of game means with its own t(G-1) interval, n, G
    and Kish G_eff. Intervals are None below two games."""
    groups = {g: v for g, v in values_by_game.items() if v}
    vals = [x for v in groups.values() for x in v]
    n, G = len(vals), len(groups)
    out = dict(n=n, G=G, g_eff=0.0, mean=None, lo=None, hi=None,
               game_mean=None, game_lo=None, game_hi=None)
    if n == 0:
        return out
    sizes = [len(v) for v in groups.values()]
    out["g_eff"] = n * n / sum(s * s for s in sizes)
    out["mean"] = sum(vals) / n
    cm = clustered_mean(groups)
    if cm is not None:
        out["lo"], out["hi"] = cm.lo, cm.hi
    gm = [sum(v) / len(v) for v in groups.values()]
    out["game_mean"] = sum(gm) / G
    if G >= 2:
        sd = math.sqrt(sum((x - out["game_mean"]) ** 2 for x in gm) / (G - 1))
        h = float(stats.t.ppf(0.975, df=G - 1)) * sd / math.sqrt(G)
        out["game_lo"], out["game_hi"] = out["game_mean"] - h, out["game_mean"] + h
    return out


def calibration_cell(rows):
    """Brier and log loss of the model and of the venue mid at the same
    instants, and the per-row Brier gap (market minus model, positive = the
    model forecast better), game-clustered. Rows here are already deduped
    and scoreable."""
    diff_by_game = defaultdict(list)
    bm = bk = lm = lk = 0.0
    n_clip = 0
    for r in rows:
        p, q, y = r["fair_value"], mid(r), r["y"]
        bm += brier(p, y)
        bk += brier(q, y)
        lm += logloss(p, y)
        lk += logloss(q, y)
        n_clip += clipped(p) or clipped(q)
        diff_by_game[r["event_slug"]].append(brier(q, y) - brier(p, y))
    n = len(rows)
    cs = cluster_stats(diff_by_game)
    return dict(rows=n, markets=len({r["market_slug"] for r in rows}),
                games=cs["G"], g_eff=cs["g_eff"],
                brier_model=bm / n if n else None, brier_market=bk / n if n else None,
                diff=cs["mean"], diff_lo=cs["lo"], diff_hi=cs["hi"],
                logloss_model=lm / n if n else None, logloss_market=lk / n if n else None,
                clipped=n_clip)


def side_win_cell(rows):
    """Win rate of the side the model leans to, game-clustered, row-weighted."""
    by_game = defaultdict(list)
    for r in rows:
        by_game[r["event_slug"]].append(1.0 if bet_won(r) else 0.0)
    return cluster_stats(by_game)


def pnl_cell(rows):
    """The taker arm over enter rows, one contract each, in cents per
    contract; rows without a coefficient are excluded and counted. The limit
    arm's row-weighted mean is beside it, labelled for what it assumes."""
    by_game, limit_by_game = defaultdict(list), defaultdict(list)
    staked = pnl = 0.0
    no_coef = 0
    markets = set()
    for r in rows:
        if r["fee_coefficient"] is None:
            no_coef += 1
            continue
        p = taker_pnl(r["side"], r["y"], r["bid"], r["ask"], r["fee_coefficient"])
        staked += taker_stake(r["side"], r["bid"], r["ask"])
        pnl += p
        markets.add(r["market_slug"])
        by_game[r["event_slug"]].append(100.0 * p)
        limit_by_game[r["event_slug"]].append(100.0 * limit_pnl(r["side"], r["y"], r["limit_price"]))
    cs = cluster_stats(by_game)
    lim = [x for v in limit_by_game.values() for x in v]
    return dict(bets=cs["n"], markets=len(markets), games=cs["G"], g_eff=cs["g_eff"],
                no_coef=no_coef, staked=staked, pnl=pnl,
                net_per_dollar=pnl / staked if staked else None,
                cents=cs["mean"], lo=cs["lo"], hi=cs["hi"],
                game_cents=cs["game_mean"], game_lo=cs["game_lo"], game_hi=cs["game_hi"],
                limit_cents=sum(lim) / len(lim) if lim else None)


def arm_cell(rows):
    c = pnl_cell(rows)
    moves = [m for m in (signed_mid_move(r) for r in rows) if m is not None]
    c["mid_move"] = sum(moves) / len(moves) if moves else None
    c["mid_move_n"] = len(moves)
    return c


# ---------------------------------------------------------------- the tables
CAL_HEADER = (f"{'population':<22}{'group':<10}{'rows':>7}{'markets':>8}{'games':>6}{'G_eff':>7}"
              f"{'brier_model':>12}{'brier_mkt':>10}{'mkt-model_brier [95% CI]':>32}"
              f"{'logloss_model':>14}{'logloss_mkt':>12}{'clipped':>8}")
GAP_HEADER = (f"{'population':<22}{'|fv-mid|':<12}{'rows':>7}{'markets':>8}{'games':>6}{'G_eff':>7}"
              f"{'brier_model':>12}{'brier_mkt':>10}{'mkt-model_brier [95% CI]':>32}"
              f"{'side_win [95% CI]':>28}")
PNL_HEADER = (f"{'population':<22}{'group':<10}{'bets':>6}{'markets':>8}{'games':>6}{'G_eff':>7}"
              f"{'no_coef':>8}{'staked$':>9}{'pnl$':>9}{'net/$1':>8}"
              f"{'c/contract row-wtd [95% CI]':>32}{'c/contract game-mean [95% CI]':>32}"
              f"{'limit_arm c (assumes fill, no fee)':>36}")
ARM_HEADER = (f"{'population':<22}{'arm':<10}{'bets':>6}{'markets':>8}{'games':>6}{'G_eff':>7}"
              f"{'no_coef':>8}{'c/contract row-wtd [95% CI]':>32}"
              f"{'mid_move_to_fill c (signed to position)':>42}")


def _ci(m, lo, hi, fmt):
    if m is None:
        return "n/a"
    if lo is None:
        return f"{m:{fmt}} [no interval: G<2]"
    return f"{m:{fmt}} [{lo:{fmt}}, {hi:{fmt}}]"


def _num(v, fmt):
    return "n/a" if v is None else f"{v:{fmt}}"


def cal_line(pop, group, c):
    return (f"{pop:<22}{group:<10}{c['rows']:>7}{c['markets']:>8}{c['games']:>6}{c['g_eff']:>7.1f}"
            f"{_num(c['brier_model'], '.4f'):>12}{_num(c['brier_market'], '.4f'):>10}"
            f"{_ci(c['diff'], c['diff_lo'], c['diff_hi'], '+.4f'):>32}"
            f"{_num(c['logloss_model'], '.4f'):>14}{_num(c['logloss_market'], '.4f'):>12}{c['clipped']:>8}")


def gap_line(pop, bucket, c, w):
    return (f"{pop:<22}{bucket:<12}{c['rows']:>7}{c['markets']:>8}{c['games']:>6}{c['g_eff']:>7.1f}"
            f"{_num(c['brier_model'], '.4f'):>12}{_num(c['brier_market'], '.4f'):>10}"
            f"{_ci(c['diff'], c['diff_lo'], c['diff_hi'], '+.4f'):>32}"
            f"{_ci(w['mean'], w['lo'], w['hi'], '.3f'):>28}")


def pnl_line(pop, group, c):
    return (f"{pop:<22}{group:<10}{c['bets']:>6}{c['markets']:>8}{c['games']:>6}{c['g_eff']:>7.1f}"
            f"{c['no_coef']:>8}{c['staked']:>9.2f}{c['pnl']:>+9.2f}{_num(c['net_per_dollar'], '+.3f'):>8}"
            f"{_ci(c['cents'], c['lo'], c['hi'], '+.2f'):>32}"
            f"{_ci(c['game_cents'], c['game_lo'], c['game_hi'], '+.2f'):>32}"
            f"{_num(c['limit_cents'], '+.2f'):>36}")


def arm_line(pop, arm, c):
    move = "n/a" if c["mid_move"] is None else f"{c['mid_move']:+.2f} (n={c['mid_move_n']})"
    return (f"{pop:<22}{arm:<10}{c['bets']:>6}{c['markets']:>8}{c['games']:>6}{c['g_eff']:>7.1f}"
            f"{c['no_coef']:>8}{_ci(c['cents'], c['lo'], c['hi'], '+.2f'):>32}{move:>42}")


def _by(rows, fn):
    out = defaultdict(list)
    for r in rows:
        out[fn(r)].append(r)
    return out


def format_report(rows, by_market, settle_counts, *, since, now):
    """The whole printout from the loaded rows and the resolved settlements.
    Pure: a test runs it on fixtures."""
    out = []
    add = out.append
    add(f"PULSE LIVE SCORECARD -- pulse_decisions, decided_at >= {since:%Y-%m-%d %H:%MZ}, read at {now:%Y-%m-%d %H:%MZ}")
    add(f"regimes: regular < {PLAYOFFS_FROM:%Y-%m-%d}Z <= playoffs (UTC, on decided_at)")
    add("")
    add("INVENTORY -- every row in the window, before any filter")
    if rows:
        lo, hi = min(r["decided_at"] for r in rows), max(r["decided_at"] for r in rows)
        add(f"  rows {len(rows):,}  markets {len({r['market_slug'] for r in rows}):,}  "
            f"games {len({r['event_slug'] for r in rows}):,}  "
            f"decided {lo:%Y-%m-%d %H:%MZ} .. {hi:%Y-%m-%d %H:%MZ}")
    else:
        add("  rows 0 -- nothing decided in the window (the engine not running is different from running and finding nothing)")
    by_ap = defaultdict(int)
    for r in rows:
        by_ap[(r["action"], r["phase"])] += 1
    add("  by action x phase: " + ", ".join(f"{a}/{p} {n:,}" for (a, p), n in sorted(by_ap.items())))
    by_v = defaultdict(int)
    for r in rows:
        by_v[r["estimates_version"]] += 1
    add("  by estimates_version: " + ", ".join(f"{v} {n:,}" for v, n in sorted(by_v.items())))
    by_s = defaultdict(int)
    for r in rows:
        by_s[r["strategy"]] += 1
    add("  by strategy: " + ", ".join(f"{s} {n:,}" for s, n in sorted(by_s.items())))
    enters = [r for r in rows if r["action"] == "enter"]
    arms = defaultdict(int)
    for r in enters:
        arms[lifecycle_arm(r)] += 1
    add(f"  enters {len(enters):,}: " + ", ".join(f"{a} {arms[a]:,}" for a in ("filled", "withdrawn", "neither"))
        + f"; cap-blocked intents (capped_stake_usd = 0) {sum(1 for r in enters if r['capped_stake_usd'] == 0):,}")
    coll = collisions(rows, CALIBRATION_KEY)
    add("  (market, instant, action) collisions, groups by action: "
        + (", ".join(f"{a} {n:,}" for a, n in sorted(coll.items())) or "none"))
    add(f"  fee coefficient joined from market_snapshots: {sum(1 for r in rows if r['fee_coefficient'] is not None):,} rows, "
        f"missing {sum(1 for r in rows if r['fee_coefficient'] is None):,}"
        + "; distinct coefficients: " + ", ".join(
            f"{c:.4f}" for c in sorted({r["fee_coefficient"] for r in rows if r["fee_coefficient"] is not None})))
    add("  settlement per market: " + ", ".join(f"{k} {v:,}" for k, v in settle_counts.items())
        + "  (venue = core/settlements answer; row = the engine's own stamp on a filled enter; half = 0.5, excluded)")

    cal_rows, why = scoreable(rows, by_market)
    cal, removed_cal = dedupe(cal_rows, CALIBRATION_KEY)
    add("  scoreable (in_play, settled 0/1, fair_value and a two-sided touch): "
        f"{len(cal_rows):,} of {len(rows):,}; excluded: "
        + (", ".join(f"{k} {v:,}" for k, v in sorted(why.items())) or "none"))
    add("")

    add("CALIBRATION BY ACTION AND REGIME -- one row per (market, instant, action), first-written kept; "
        f"{removed_cal:,} collision rows removed")
    add("  mkt-model_brier: per-row Brier(mid) - Brier(fair_value), row-weighted mean, sandwich CI (CR1, t df=G-1) by game;")
    add("  positive = the model forecast better than the venue mid at the same instants. logloss clips p to "
        f"[{LOGLOSS_CLIP}, {1 - LOGLOSS_CLIP}].")
    add(CAL_HEADER)
    by_regime = _by(cal, lambda r: regime(r["decided_at"]))
    for reg in ("regular", "playoffs", "all"):
        pool = cal if reg == "all" else by_regime.get(reg, [])
        by_action = _by(pool, lambda r: r["action"])
        for action in ("enter", "exit", "hold", "all"):
            sub = pool if action == "all" else by_action.get(action, [])
            add(cal_line(reg, action, calibration_cell(sub)))
    add("")

    add("CALIBRATION BY ESTIMATES VERSION -- all actions, all regimes, same dedupe; model generations never blend")
    add(CAL_HEADER)
    for v, sub in sorted(_by(cal, lambda r: r["estimates_version"]).items()):
        add(cal_line("version", v, calibration_cell(sub)))
    add("")

    add("CALIBRATION BY |fair_value - mid| -- all actions, same dedupe; side_win = win rate of the side the model leans to")
    add("  (the first bucket is inside the anchor scorecard's 0.02 no-bet tolerance; breakeven on a -110 two-way is 0.524)")
    add(GAP_HEADER)
    for reg in ("regular", "playoffs", "all"):
        pool = cal if reg == "all" else by_regime.get(reg, [])
        by_bucket = _by(pool, lambda r: gap_bucket(abs(r["fair_value"] - mid(r))))
        for lo_, hi_ in GAP_BUCKETS:
            label = gap_bucket(lo_)
            sub = by_bucket.get(label, [])
            add(gap_line(reg, label, calibration_cell(sub), side_win_cell(sub)))
    add("")

    bets_all, removed_bets = dedupe([r for r in cal_rows if r["action"] == "enter"], BET_KEY)
    add("PAPER P&L OF ENTER DECISIONS -- taker at the recorded touch, held to settlement, 1 contract per decision,")
    add("  fee at the row's own coefficient (market_snapshots.fee_coefficient at decided_at); one line per")
    add(f"  (market, instant, action, side, limit_price), {removed_bets:,} collision rows removed; no_coef rows excluded, not charged at today's.")
    add("  c/contract row-wtd: sandwich CI (CR1, t df=G-1) by game on the row-weighted mean; game-mean: equal weight per game, t(G-1).")
    add(PNL_HEADER)
    bets_by_regime = _by(bets_all, lambda r: regime(r["decided_at"]))
    for reg in ("regular", "playoffs", "all"):
        pool = bets_all if reg == "all" else bets_by_regime.get(reg, [])
        add(pnl_line(reg, "all", pnl_cell(pool)))
        for strat, sub in sorted(_by(pool, lambda r: r["strategy"]).items()):
            add(pnl_line(reg, strat, pnl_cell(sub)))
    for v, sub in sorted(_by(bets_all, lambda r: r["estimates_version"]).items()):
        add(pnl_line("version", v, pnl_cell(sub)))
    add("")

    add("THE UNFILLED ARM -- the same enter decisions by lifecycle, the same taker P&L. A resting order fills when")
    add("  the market comes TO it and is withdrawn when the model's edge is gone or the price LEFT, so the arms are")
    add("  sorted by price direction before any skill enters: the withdrawn arm always flatters. Decisions are not fills.")
    add(ARM_HEADER)
    by_arm = _by(bets_all, lifecycle_arm)
    for arm in ("filled", "withdrawn", "neither", "all"):
        sub = bets_all if arm == "all" else by_arm.get(arm, [])
        add(arm_line("all regimes", arm, arm_cell(sub)))
    add("")
    add("What the numbers cannot show: the P&L crosses the touch at the decision instant with no depth check and no")
    add("latency, so it is what the model's opinion was worth to a taker, not what a resting limit captured; the")
    add("limit arm assumes every order filled and is an upper bound; a decision in a market with 18 rungs is one")
    add("opinion, and G, not rows, is the sample. Nothing here is sized, gated or armed.")
    return "\n".join(out)


def main():
    from sqlalchemy import create_engine, text

    from core import settlements
    from core.polymarket.client import PolymarketGatewayClient

    days = int(os.environ.get("DAYS", "45"))
    now = dt.datetime.now(UTC)
    since = now - dt.timedelta(days=days)
    month_floor = since.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    eng = create_engine(os.environ["DATABASE_URL"])
    with eng.connect() as c:
        rows = [dict(r._mapping) for r in c.execute(
            text(DECISIONS_SQL), {"since": since, "month_floor": month_floor})]
    eng.dispose()                      # one read; no connection is held while the venue is asked

    cache = settlements.load()
    hits = len(cache)
    with PolymarketGatewayClient() as client:
        by_market, counts = resolve_settlements(rows, settlements.settler(client, cache))
    settlements.save(cache)

    print(format_report(rows, by_market, counts, since=since, now=now))
    print(f"\nsettlement cache {settlements.PATH}: {hits:,} reused, {len(cache) - hits:,} fetched, {len(cache):,} stored")


if __name__ == "__main__":
    main()
