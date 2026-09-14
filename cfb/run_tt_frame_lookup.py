"""STEP 1 RESOLVED: a RESOLVED market states its own outcome.

`market.status == MARKET_STATUS_RESOLVED` and each marketSide's `price` becomes
1 or 0. side0 is YES (long=True). So compare the venue's SETTLEMENT label
against side0's RESOLVED PRICE -- two different fields, written by different
parts of the venue. If the frame were inverted these would disagree.

Compared against side0's resolved price, NOT outcomes[]: outcomes[] order is
documented as disagreeing with marketSides[] on a subset of every league.
"""
import os
from sqlalchemy import create_engine, event as sa_event, text
from core import settlements
from core.polymarket.client import PolymarketGatewayClient

PAT = '-(setkameua|setkamemd|setkamecz|setkawoua)-'
eng = create_engine(os.environ["DATABASE_URL"])

@sa_event.listens_for(eng, "connect")
def _np(c, _r):
    cur = c.cursor(); cur.execute("SET max_parallel_workers_per_gather=0"); cur.close(); c.commit()

c = PolymarketGatewayClient()
cache = settlements.load()
settle = settlements.settler(c, cache)
with eng.connect() as conn:
    rows = [dict(r._mapping) for r in conn.execute(text("""
        SELECT DISTINCT ON (market_slug) market_slug, event_slug FROM market_snapshots
        WHERE market_slug ~ :pat AND captured_at < game_start_time
          AND game_start_time < now() - interval '45 minutes'
        ORDER BY market_slug, captured_at DESC"""), {"pat": PAT})]

checked = agree = disagree = unresolved = 0
oc_disagree = 0
for r in rows:
    y = settle(r["market_slug"])
    if y is None:
        continue
    try:
        ev = c._get("/v1/events", params={"slug": r["event_slug"]})
    except Exception:
        continue
    e = (ev.get("events") or [ev])[0] if isinstance(ev, dict) else ev
    m = next((x for x in (e.get("markets") or []) if x.get("slug") == r["market_slug"]), None)
    if not m or m.get("status") != "MARKET_STATUS_RESOLVED":
        unresolved += 1
        continue
    sides = m.get("marketSides") or []
    if len(sides) < 2:
        continue
    s0 = sides[0]
    if not s0.get("long"):
        print("!! side0 is not the long side on", r["market_slug"])
    try:
        p0 = float(s0.get("price"))
    except (TypeError, ValueError):
        unresolved += 1
        continue
    if p0 not in (0.0, 1.0):
        unresolved += 1
        continue
    yes_won_by_price = p0 == 1.0
    yes_won_by_settlement = float(y) >= 0.5
    ok = yes_won_by_price == yes_won_by_settlement
    checked += 1
    agree += ok
    disagree += (not ok)
    # secondary: does outcomes[] order match marketSides[] here?
    import json as _j
    try:
        ocs = _j.loads(m.get("outcomes") or "[]")
        t0 = (s0.get("team") or {}).get("name")
        if ocs and t0 and ocs[0] != t0:
            oc_disagree += 1
    except Exception:
        pass
    if checked <= 8:
        print("%-40s YES=%-22s resolved_price=%s settlement=%s %s"
              % (r["market_slug"], (s0.get("team") or {}).get("name"), p0, y,
                 "AGREE" if ok else "*** DISAGREE ***"))
settlements.save(cache)
print("\nRESOLVED markets compared: %d   agree %d   disagree %d   not resolved yet %d"
      % (checked, agree, disagree, unresolved))
print("outcomes[] order disagreed with marketSides[] on %d of %d" % (oc_disagree, checked))
if checked:
    print("STEP 1 VERDICT:", "FRAME CONSISTENT - settlement follows marketSides[0]"
          if disagree == 0 else "*** FRAME MISMATCH ***")
