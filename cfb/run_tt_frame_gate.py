"""TT frame gate, arm B (oriented calibration) + the registered n formula.

Arm B = mean(y_f - p_f) where p_f is the FAVOURITE side's price and y_f whether
the favourite won. It dominates arm A (favourite win rate) for free: subtracting
p_f removes Var(p_f). Arm C (unoriented mean(y)-mean(p) in the YES frame) has
zero power when the venue assigns YES without regard to strength, so it is
reported as a secondary and never gates.

Registered: n >= z^2 * E[p_f(1-p_f)] / (pbar_f - 0.5)^2 * deff, deff = 1.3.
"""
import os
from sqlalchemy import create_engine, event, text
from core import settlements
from core.polymarket.client import PolymarketGatewayClient

PAT = '-(setkameua|setkamemd|setkamecz|setkawoua)-'
SQL = """
SELECT DISTINCT ON (market_slug) market_slug, game_id,
       best_bid::float bid, best_ask::float ask, game_start_time,
       EXTRACT(EPOCH FROM (game_start_time - captured_at))/60 AS mins_before
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
settled = []
for r in rows:
    y = settle(r["market_slug"])
    if y is None:
        continue
    mid = (r["bid"] + r["ask"]) / 2
    pf = max(mid, 1 - mid)                    # the favourite side's price
    yf = float(y) if mid >= 0.5 else 1 - float(y)   # did the favourite win
    settled.append((pf, yf, mid, float(y), float(r["mins_before"] or 0)))
settlements.save(cache)

n = len(settled)
print("settled matches with a pregame close:", n, "of", len(rows))
if not n:
    raise SystemExit
pbar_f = sum(p for p, *_ in settled) / n
armB = sum(y - p for p, y, *_ in settled) / n
armA = sum(y for _, y, *_ in settled) / n
var = sum(p * (1 - p) for p, *_ in settled) / n
print("pbar_f (mean FAVOURITE price)  %.4f" % pbar_f)
print("arm A  favourite win rate      %.4f" % armA)
print("arm B  mean(y_f - p_f)         %+.4f   <- the one to watch" % armB)
d = pbar_f - 0.5
for z, lab in ((1.645, "5%"), (2.326, "1%")):
    need = z * z * var / (d * d) * 1.3 if d > 0 else float("inf")
    print(f"n needed for a {lab} wrong-call rate: {need:.0f}   (have {n})")
ms = sorted(x[4] for x in settled)
print("mins_before: min %.1f  median %.1f  p90 %.1f  max %.1f" % (
    ms[0], ms[n // 2], ms[int(n * 0.9)], ms[-1]))
beyond = sum(1 for m in ms if m > 8)
print("closes staler than 8 min: %d of %d  (mass here = genuine drops, not staleness)" % (beyond, n))

# The split that decides whether a wrong-sign arm A is a FRAME problem or noise:
# if YES-favourites and NO-favourites disagree, the asymmetry is about the frame.
yf_n = [x for x in settled if x[2] >= 0.5]
nf_n = [x for x in settled if x[2] < 0.5]
for lab, grp in (("YES is favourite", yf_n), ("NO is favourite", nf_n)):
    if grp:
        w = sum(y for _, y, *_ in grp)
        print("  %-18s n=%2d  favourite won %.1f = %.1f%%  mean p_f %.3f"
              % (lab, len(grp), w, 100 * w / len(grp), sum(p for p, *_ in grp) / len(grp)))
