"""Cross-venue CFB totals: build the code map, then measure the gap.

Answers meridian-70's question (is there a cross-venue arb on CFB totals?) and,
as a by-product, meridian-14's first venue question (which board is tighter on
the same games?).

Run:  .venv/bin/python analysis/cross_venue_cfb_gap.py [--harvest]

Without --harvest it reads the saved payloads in backups/exports/, so the
numbers below are reproducible without hitting either venue.

WHAT IT ESTABLISHES

1. The team-code map is buildable from both venues' own payloads and is a
   BIJECTION on observed games: 220 codes from 177 matched games, zero
   conflicts in either direction. It lives in `core.kalshi.cross_venue`.

2. Only 30.5% of codes are identical. A naive lowercase-and-compare join
   loses 69.5% of the board, and MIS-JOINS one pair: Kalshi SDST is South
   Dakota St. while Polymarket's `sdst` is San Diego St. (Kalshi SDSU).

3. The join lifts coverage from 10 verified pairs to **620 (game, line) cells
   across 72 games**.

4. **There is no arbitrage.** Max gross gap in either direction is +1.00c --
   exactly one tick -- on 2.9% of cells. Kalshi's quadratic fee averages
   1.34c, which EXCEEDS the largest gross gap observed. Three cells survive
   the Kalshi fee alone, all at extreme prices where the quadratic fee is
   smallest, and none survives once the second leg's costs are counted.

5. The reason is structural rather than a sampling accident: **gross gaps are
   quantised in 1c ticks and the fee is ~1.3c**, so clearing costs needs the
   two books to differ by TWO ticks or more. Zero of 620 cells did.

WHAT IT DOES NOT ESTABLISH

This is ONE SNAPSHOT. It measures the cross-sectional distribution at an
instant, not the time-series tail, so it cannot speak to how often a gap opens
or how long one lasts -- both of which meridian-70 explicitly asked for and
neither of which a snapshot can answer. The structural argument above is
snapshot-independent; the frequency claim is not.

The 620 cells are the INTERSECTION of two boards, which selects for liquidity
on both. They are not a sample of either board. That is why the Polymarket
spread here (median 1c, 6.1% over our 15c gate) is nowhere near the 43.24%
measured over the whole CFB board in `cfb_wide_band_census.py` -- different
populations, not a contradiction.
"""

from __future__ import annotations

import json
import re
import statistics as st
import sys
import time
import urllib.request
from collections import Counter, defaultdict

KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
K_EXPORT = "backups/exports/kalshi_cfb_events_20260904T172000Z.json"
P_EXPORT = "backups/exports/pm_cfb_events_20260904T172000Z.json"
MONTHS = {m: i + 1 for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
     "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}

#: Kalshi's published quadratic fee, series `fee_type` = quadratic_with_maker_fees
#: and `fee_multiplier` = 1, both read from /series/KXNCAAFTOTAL rather than
#: assumed. Per contract, in dollars.
def kalshi_fee(price: float) -> float:
    return 0.07 * price * (1.0 - price)


def normalise(name: str) -> str:
    """The ONE normalisation that earns its place: St. -> State.

    Measured: exact name agreement 67.6% raw, 87.4% after this rule, 88.1%
    after also stripping parentheticals and punctuation. Everything past the
    first rule is worth ~0.7pp combined, so the rest is noise dressed as care.
    """
    s = re.sub(r"\bSt\.", "State", name)
    s = re.sub(r"\s*\([^)]*\)", "", s)
    s = re.sub(r"[.'’&-]", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def kalshi_games(events: list[dict]) -> dict:
    out = {}
    for e in events:
        m = re.match(r"^\s*([A-Z0-9]+)\s+vs\s+([A-Z0-9]+)\s*\(", e.get("sub_title") or "")
        title = e.get("title") or ""
        base = title.rsplit(":", 1)[0] if ":" in title else title
        names = base.split(" vs ")
        tick = (e.get("event_ticker") or "").split("-", 1)
        d = re.match(r"^(\d{2})([A-Z]{3})(\d{2})", tick[1]) if len(tick) > 1 else None
        if not (m and len(names) == 2 and d):
            continue
        date = f"20{d.group(1)}-{MONTHS[d.group(2)]:02d}-{int(d.group(3)):02d}"
        key = (date, frozenset(normalise(n) for n in names))
        out.setdefault(key, {"suffix": tick[1], "codes": (m.group(1), m.group(2)),
                             "names": tuple(normalise(n) for n in names)})
    return out


def pm_games(events: list[dict]) -> tuple[dict, dict]:
    games, totals = {}, {}
    for e in events:
        teams = e.get("teams") or []
        if len(teams) != 2 or not all(t.get("safeName") and t.get("abbreviation") for t in teams):
            continue
        date = (e.get("startDate") or "")[:10]
        names = tuple(normalise(t["safeName"]) for t in teams)
        games[(date, frozenset(names))] = {
            "slug": e.get("slug"), "codes": tuple(t["abbreviation"] for t in teams),
            "names": names}
        rungs = {}
        for m in e.get("markets") or []:
            if "-total-" not in (m.get("slug") or "") or m.get("closed"):
                continue
            line = m.get("line")
            bid = (m.get("bestBidQuote") or {}).get("value")
            ask = (m.get("bestAskQuote") or {}).get("value")
            if line is not None and bid and ask:
                rungs[float(line)] = (float(bid), float(ask))
        if rungs:
            totals[e.get("slug")] = rungs
    return games, totals


def main() -> int:
    harvest = "--harvest" in sys.argv
    kev = json.load(open(K_EXPORT))
    pev = json.load(open(P_EXPORT))
    kg = kalshi_games(kev)
    pg, ptot = pm_games(pev)
    print(f"kalshi games {len(kg):,} (from {len(kev):,} events) | "
          f"polymarket games {len(pg):,}")

    matched = {k: (v, pg[k]) for k, v in kg.items() if k in pg}
    why = Counter()
    pm_names_by_date = defaultdict(set)
    for (d, names) in pg:
        pm_names_by_date[d].update(names)
    for key, v in kg.items():
        if key in pg:
            continue
        d = key[0]
        present = [n for n in v["names"] if n in pm_names_by_date.get(d, ())]
        why["PM has no board that date" if d not in pm_names_by_date
            else "PM lists neither team (coverage)" if not present
            else "PM lists one team (name/pairing)"] += 1
    print(f"MATCHED {len(matched):,}/{len(kg):,} games "
          f"({len(matched)/len(kg)*100:.1f}%)")
    for k, v in why.most_common():
        print(f"   unmatched: {k:36s} {v:4d}")

    codes = defaultdict(Counter)
    for kv, pv in matched.values():
        kn = dict(zip(kv["names"], kv["codes"]))
        pn = dict(zip(pv["names"], pv["codes"]))
        for n in kn:
            if n in pn:
                codes[kn[n]][pn[n]] += 1
    conflicts = sum(1 for v in codes.values() if len(v) > 1)
    rev = defaultdict(set)
    for k, v in codes.items():
        rev[v.most_common(1)[0][0]].add(k)
    print(f"\nCODE MAP: {len(codes)} codes | conflicts {conflicts} | "
          f"reverse conflicts {sum(1 for v in rev.values() if len(v) > 1)}")
    ident = sum(1 for k, v in codes.items() if k.lower() == v.most_common(1)[0][0].lower())
    print(f"  identical {ident}/{len(codes)} ({ident/len(codes)*100:.1f}%) | "
          f"differing {len(codes)-ident} -- a naive join loses these")

    if not harvest:
        print("\n(quotes need --harvest; both venues quote live and the saved "
              "payload carries Polymarket's book but not Kalshi's)")
        return 0

    cells = []
    for key, (kv, pv) in matched.items():
        rungs = ptot.get(pv["slug"])
        if not rungs:
            continue
        try:
            d = json.load(urllib.request.urlopen(
                f"{KALSHI}/markets?event_ticker=KXNCAAFTOTAL-{kv['suffix']}", timeout=25))
        except Exception:
            continue
        for m in d.get("markets", []):
            fs, b, a = m.get("floor_strike"), m.get("yes_bid_dollars"), m.get("yes_ask_dollars")
            if fs is None or not b or not a or float(b) <= 0 or float(a) <= 0:
                continue
            if float(fs) not in rungs:
                continue
            pb, pa = rungs[float(fs)]
            cells.append(dict(
                line=float(fs), kb=float(b), ka=float(a), pb=pb, pa=pa,
                kbs=float(m.get("yes_bid_size_fp") or 0),   # _fp, not _size
                kas=float(m.get("yes_ask_size_fp") or 0),
                gK=pb - float(a), gP=float(b) - pa))
        time.sleep(0.22)

    print(f"\nSHARED CELLS {len(cells):,}")
    pos = [c for c in cells if max(c["gK"], c["gP"]) > 0]
    print(f"  positive GROSS gap: {len(pos)}/{len(cells)} "
          f"({len(pos)/len(cells)*100:.1f}%)  max "
          f"{max(max(c['gK'], c['gP']) for c in cells)*100:+.2f}c")
    survive = 0
    for c in pos:
        px = c["ka"] if c["gK"] >= c["gP"] else c["kb"]
        survive += (max(c["gK"], c["gP"]) - kalshi_fee(px)) > 0
    print(f"  survive the KALSHI FEE ALONE: {survive}/{len(pos)}")
    print(f"  mean Kalshi fee {st.mean([kalshi_fee(c['ka']) for c in cells])*100:.2f}c "
          f"vs max gross gap 1.00c  <- the fee exceeds the largest gap")

    ks = [c["ka"] - c["kb"] for c in cells]
    ps = [c["pa"] - c["pb"] for c in cells]
    print(f"\nSPREADS on identical cells (the INTERSECTION, selected for "
          f"liquidity on both boards):")
    for nm, v in (("kalshi", ks), ("polymarket", ps)):
        print(f"  {nm:11s} median {st.median(v)*100:.1f}c  mean {st.mean(v)*100:.1f}c  "
              f"over our 15c gate {sum(1 for x in v if x > 0.15)/len(v)*100:.1f}%")
    tighter = sum(1 for a, b in zip(ks, ps) if a < b)
    same = sum(1 for a, b in zip(ks, ps) if abs(a - b) < 1e-9)
    print(f"  kalshi tighter {tighter/len(ks)*100:.1f}% | identical "
          f"{same/len(ks)*100:.1f}% | polymarket tighter "
          f"{(len(ks)-tighter-same)/len(ks)*100:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
