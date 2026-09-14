"""TABLE TENNIS FRAME GATE (docs/math/tabletennis-preregistration.md, TRAP 1).

No independent settlement source exists for Setka Cup, so a frame error is
unfalsifiable from inside and would present as a large, stable edge. Registered
gate, run BEFORE any edge claim:
  (1) realized YES rate ~= mean YES price
  (2) favourites (YES mid > 0.5) must win MORE than half; a flipped frame shows
      them winning LESS than half.
Counts only. No strategy, no P&L, nothing sized.
"""
import os
from sqlalchemy import create_engine, event, text
from core import settlements
from core.polymarket.client import PolymarketGatewayClient

PAT = '-(setkameua|setkamemd|setkamecz|setkawoua)-'
SQL = """
SELECT DISTINCT ON (market_slug) market_slug, game_id,
       best_bid::float bid, best_ask::float ask, game_start_time
FROM market_snapshots
WHERE market_slug ~ :pat AND best_bid IS NOT NULL AND best_ask IS NOT NULL
  AND captured_at < game_start_time
  AND game_start_time < now() - interval '45 minutes'
ORDER BY market_slug, captured_at DESC
"""

eng = create_engine(os.environ["DATABASE_URL"])

@event.listens_for(eng, "connect")
def _np(c, _r):
    cur = c.cursor()
    cur.execute("SET max_parallel_workers_per_gather = 0")
    cur.close()
    c.commit()

cache = settlements.load()
settle = settlements.settler(PolymarketGatewayClient(), cache)
with eng.connect() as c:
    rows = [dict(r._mapping) for r in c.execute(text(SQL), {"pat": PAT})]
print("markets with a pregame close, started >45 min ago:", len(rows))

n = fav_n = unsettled = 0
fav_win = sum_mid = sum_y = 0.0
for r in rows:
    y = settle(r["market_slug"])
    if y is None:
        unsettled += 1
        continue
    mid = (r["bid"] + r["ask"]) / 2
    n += 1
    sum_mid += mid
    sum_y += float(y)
    if mid > 0.5:
        fav_n += 1
        fav_win += float(y)
settlements.save(cache)
print("settled", n, "unsettled/failed", unsettled)
if n:
    print("mean YES price    %.4f" % (sum_mid / n))
    print("realized YES rate %.4f   gap %+.4f" % (sum_y / n, sum_y / n - sum_mid / n))
if fav_n:
    rate = fav_win / fav_n
    print("favourites (YES mid > 0.5): %d, won %.1f = %.1f%%" % (fav_n, fav_win, 100 * rate))
    print("GATE 2:", "PASS" if rate > 0.5 else "*** FAIL - HALT AND RE-DERIVE THE FRAME ***")
else:
    print("no favourites settled yet; gate 2 not evaluable")
