"""H4 -- score the pregame-softness snapshots against settlement.

Registered in docs/math/e8-nfl-preregistration.md (H4): Brier of the venue mid
against Brier of DraftKings' POWER-devigged probability, favourite side, one
observation per game, venues scored separately (different quoting engines).

Which snapshot: the LAST one taken before kickoff (PRIMARY -- lines move and
the nearest snapshot is fairest to both sides), and the FIRST one (secondary,
the 2026-09-07 registration snapshot). Both are printed, labelled.

DK power devig is RECOMPUTED here from the two moneylines of each game rather
than read from the CSV: the Kalshi file has no power column, and recomputing
gives the Polymarket file's dk_pow a second route to disagree with.

Settlement: ESPN's public summary endpoint, keyless, no prod.

    python3 analysis/pregame_softness/score_softness.py
"""
import csv
import datetime as dt
import json
import os
import sys
import urllib.request
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = {
    "polymarket_us": (os.path.join(HERE, "pregame_softness_polymarket_snapshots.csv"), "v_mid"),
    "kalshi":        (os.path.join(HERE, "pregame_softness_snapshots.csv"),            "k_mid"),
}
SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={}"


def implied(ml: float) -> float:
    ml = float(ml)
    return (-ml) / (-ml + 100.0) if ml < 0 else 100.0 / (ml + 100.0)


def power_devig(p_a: float, p_b: float) -> tuple[float, float]:
    """Solve p_a**k + p_b**k = 1 for k >= 1 by bisection; return (q_a, q_b)."""
    lo, hi = 1.0, 20.0
    for _ in range(80):
        k = (lo + hi) / 2
        if p_a ** k + p_b ** k > 1.0:
            lo = k
        else:
            hi = k
    k = (lo + hi) / 2
    return p_a ** k, p_b ** k


_settle = {}
def settlement(event: str):
    """(completed, home_won, tie) from ESPN. Cached per event."""
    if event in _settle:
        return _settle[event]
    try:
        with urllib.request.urlopen(SUMMARY.format(event), timeout=20) as r:
            j = json.load(r)
        comp = j["header"]["competitions"][0]
        done = bool(comp["status"]["type"].get("completed"))
        sc = {c["homeAway"]: float(c.get("score") or 0) for c in comp["competitors"]}
        out = (done, sc["home"] > sc["away"], sc["home"] == sc["away"])
    except Exception as e:  # noqa: BLE001 -- a fetch failure is "unsettled", printed
        print(f"  settlement fetch failed for {event}: {e}", file=sys.stderr)
        out = (False, None, None)
    _settle[event] = out
    return out


def load(venue: str):
    path, midcol = FILES[venue]
    by_game = defaultdict(lambda: defaultdict(dict))   # event -> ts -> side -> row
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            by_game[r["espn_event"]][r["ts"]][r["side"]] = r
    return by_game, midcol


def pick(ts_rows: dict, kickoff: dt.datetime, which: str):
    before = sorted(ts for ts in ts_rows if dt.datetime.fromisoformat(ts) < kickoff)
    if not before:
        return None
    return ts_rows[before[-1] if which == "last" else before[0]]


def ci(vals):
    n = len(vals)
    m = sum(vals) / n
    if n < 2:
        return m, float("inf"), n
    se = (sum((v - m) ** 2 for v in vals) / (n - 1)) ** 0.5 / n ** 0.5
    return m, 1.96 * se, n


def score(venue: str, which: str):
    by_game, midcol = load(venue)
    diffs, closer, unsettled, ties, pow_gap = [], 0, 0, 0, 0.0
    rows_out = []
    for event, ts_rows in by_game.items():
        any_ts = next(iter(ts_rows))
        any_row = next(iter(ts_rows[any_ts].values()))
        k = any_row["kickoff"].replace("Z", "+00:00")
        kickoff = dt.datetime.fromisoformat(k)
        pair = pick(ts_rows, kickoff, which)
        if not pair or "home" not in pair or "away" not in pair:
            continue
        done, home_won, tie = settlement(event)
        if not done:
            unsettled += 1
            continue
        if tie:
            ties += 1
            continue
        q_home, q_away = power_devig(implied(pair["home"]["dk_ml"]), implied(pair["away"]["dk_ml"]))
        if "dk_pow" in pair["home"]:
            pow_gap = max(pow_gap, abs(q_home - float(pair["home"]["dk_pow"])))
        fav = "home" if q_home >= 0.5 else "away"
        q = q_home if fav == "home" else q_away
        v = float(pair[fav][midcol])
        y = 1.0 if (home_won if fav == "home" else not home_won) else 0.0
        d = (v - y) ** 2 - (q - y) ** 2          # venue Brier minus DK Brier; negative = venue closer
        diffs.append(d)
        closer += d < 0
        rows_out.append((event, pair[fav]["team"], fav, q, v, int(y), d))
    return diffs, closer, unsettled, ties, pow_gap, rows_out


if __name__ == "__main__":
    print("H4 -- venue mid vs DK power-devigged prob, FAVOURITE side, one obs per game.")
    print("Brier difference (venue - DK): NEGATIVE means the venue was closer to the outcome.\n")
    for which, label in (("last", "PRIMARY: last snapshot before kickoff"),
                         ("first", "secondary: first (registration) snapshot")):
        print(f"=== {label} ===")
        for venue in FILES:
            diffs, closer, unsettled, ties, pow_gap, rows = score(venue, which)
            if not diffs:
                print(f"  {venue:<14} no settled games  (unsettled {unsettled}, ties {ties})")
                continue
            m, h, n = ci(diffs)
            verdict = ("NO INTERVAL (G=1)" if n < 2 else
                       "venue CLOSER" if m + h < 0 else "DK closer" if m - h > 0 else "spans zero")
            print(f"  {venue:<14} games {n:>3}  mean diff {m:+.4f}  [{m-h:+.4f}, {m+h:+.4f}]  "
                  f"venue closer in {closer}/{n}  {verdict}   (unsettled {unsettled}, ties {ties})")
            if pow_gap:
                print(f"  {'':<14} recomputed power devig vs CSV dk_pow: max |gap| {pow_gap:.4f}")
            for ev, team, side, q, v, y, d in rows:
                print(f"  {'':<14}   {ev} {team:<14}{side:<5} dk_pow {q:.4f} venue {v:.4f} won {y}  diff {d:+.4f}")
        print()
    print("A Brier gap is registered as the H4 metric. It says nothing about a maker's P&L.")
    print("One game per venue is NOT a measurement; the read is after Sunday's slate settles (G >= 13).")
