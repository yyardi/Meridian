"""Row-level check of the manager's classifier against mine, WNBA only.

Their export carries the touch at the fill instant and their pop label.
I have independent tick substrate for WNBA (not for CFB), so WNBA is where
two constructions can actually be compared row by row.

Also tests a specific hypothesis for the 12-of-13 vs 13-of-13 sign-count
disagreement: that it is the PREGAME filter, not marginal noise. Their
6,255 real vs my 6,146 differs by 109; the pregame population is 307.
"""
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

REPO = Path("/Users/yayardia/Documents/Quant/Meridian")
sys.path.insert(0, str(REPO))
from core.quote.adverse_selection import clustered_mean  # noqa: E402

EX = REPO / "backups/exports"
c = pd.read_csv(EX / "quote_fills_classified_20260904T140631Z.csv",
                parse_dates=["filled_at", "quoted_at", "book_at"])
print(f"export rows {len(c):,}  games {c.game_id.nunique()}  "
      f"markets {c.market_slug.nunique()}")
print(f"  pop: {c['pop'].value_counts().to_dict()}")
print(f"  regime: {c.regime.value_counts().to_dict()}")
print(f"  book_age_s == 0 on all rows: {bool((c.book_age_s == 0).all())}")

c["league"] = np.where(c.market_slug.str.contains("-wnba-"), "WNBA",
                       np.where(c.market_slug.str.contains("-cfb-"), "CFB",
                                "other"))
print(f"  leagues: {c.league.value_counts().to_dict()}")

# --- known-answer: their own WNBA headline -----------------------------
w = c[c.league == "WNBA"]
wr = w[w['pop'] == "real"]
cm = clustered_mean({k: list(v) for k, v in wr.groupby("game_id").pnl})
print("\n=== their WNBA headline, recomputed from their own file ===")
print(f"  fills {len(w):,}  real {len(wr):,}  phantom "
      f"{(w['pop']=='phantom').mean():.1%}")
print(f"  real mean {wr.pnl.mean()*100:+.3f}c   clustered "
      f"{cm.mean*100:+.3f} [{cm.lo*100:+.3f}, {cm.hi*100:+.3f}]")
lose = wr.groupby("game_id").pnl.sum() < 0
print(f"  games losing: {int(lose.sum())} of {len(lose)}")

# --- THE PREGAME HYPOTHESIS -------------------------------------------
print("\n=== is the sign-count difference the PREGAME filter? ===")
wi = wr[wr.regime == "ingame"]
li = wi.groupby("game_id").pnl.sum() < 0
print(f"  real, ALL regimes : {len(wr):,} rows, "
      f"{int(lose.sum())} of {len(lose)} games lose")
print(f"  real, INGAME only : {len(wi):,} rows, "
      f"{int(li.sum())} of {len(li)} games lose   <- my filter")
print(f"  difference in real rows: {len(wr)-len(wi)}  "
      f"(pregame real fills)")
g = "13002489"
for lab, sub in (("all regimes", wr), ("ingame only", wi)):
    q = sub[sub.game_id.astype(str) == g]
    print(f"  game {g} {lab:12s}: {len(q):>4d} real fills, total "
          f"{q.pnl.sum():+.2f}, mean {q.pnl.mean()*100:+.3f}c")

# --- row-level: my classification vs theirs, WNBA ----------------------
print("\n=== ROW-LEVEL: my phantom call vs theirs (WNBA) ===")
P = EX / "live_ticks_pulse_games_20260901T195202Z.csv.gz"
SRC = f"""
    SELECT market_slug, captured_at, best_bid, best_ask FROM read_csv('{P}')
    UNION ALL SELECT column00, column05, column06, column07
      FROM read_csv('{EX}/eval_market_snapshots.csv.gz', header=false)
    UNION ALL SELECT column00, column05, column06, column07
      FROM read_csv('{EX}/delta_market_snapshots.csv.gz', header=false)
    UNION ALL SELECT market_slug, captured_at, best_bid, best_ask
      FROM read_csv('{EX}/live_snapshots_since0820.csv.gz')"""
con = duckdb.connect()
con.execute("SET timezone='UTC'")
con.execute(f"CREATE TEMP TABLE tk AS SELECT * FROM ({SRC}) "
            "WHERE best_bid IS NOT NULL AND best_ask IS NOT NULL")
con.register("f", w.reset_index(drop=True).reset_index(names="fid"))
b = con.execute("""
  WITH q AS (SELECT fid, market_slug, epoch(filled_at) t FROM f)
  SELECT q.fid, t.best_bid mfb, t.best_ask mfa, q.t - epoch(t.captured_at) age
  FROM q ASOF JOIN (SELECT market_slug, best_bid, best_ask, captured_at,
                           epoch(captured_at) ct FROM tk) t
    ON q.market_slug = t.market_slug AND t.ct <= q.t
""").df().set_index("fid")
m = w.reset_index(drop=True).join(b)
ok = m[m.mfa.notna()].copy()
ok["mine"] = np.where(ok.side == "bid", ok.mfa > ok.qp + 1e-9,
                      ok.mfb < ok.qp - 1e-9)
ok["theirs"] = ok['pop'] == "phantom"
print(f"  rows I can independently classify: {len(ok):,} of {len(w):,}")
same_book = (((ok.bb - ok.mfb).abs() < 1e-9)
             & ((ok.ba - ok.mfa).abs() < 1e-9))
print(f"  book agrees (their bb/ba == my tick): {same_book.mean():.2%}")
agree = (ok.mine == ok.theirs)
print(f"  CLASSIFICATION AGREES: {agree.sum():,}/{len(ok):,} = {agree.mean():.3%}")
if (~agree).any():
    d = ok[~agree]
    print(f"  disagreements: {len(d)}  "
          f"(mine phantom/theirs real: {int((d.mine & ~d.theirs).sum())}; "
          f"mine real/theirs phantom: {int((~d.mine & d.theirs).sum())})")
    print(f"    their book vs mine differs on "
          f"{int(((d.bb-d.mfb).abs()>1e-9).sum())} of these")
