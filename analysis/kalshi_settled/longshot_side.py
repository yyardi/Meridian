"""Underdog side + two-market vig on settled Kalshi rows (the Bartlett-O'Hara
lottery-premium test). usage: longshot_side.py <cfb_results.json> <nfl_results.json>"""
import json, sys
from collections import defaultdict
def clustered(vals, keys):
    n=len(vals); m=sum(vals)/n; res=defaultdict(float); size=defaultdict(int)
    for v,k in zip(vals,keys): res[k]+=v-m; size[k]+=1
    G=len(res); se=(sum(x*x for x in res.values())**0.5)/n*(G/(G-1))**0.5 if G>1 else 0
    return m,1.96*se,n,G
for lab, path in (("CFB", sys.argv[1]), ("NFL", sys.argv[2])):
    soft=[r for r in json.load(open(path))["soft"] if r["k_spread"]<=0.20 and not (r["dk_pow"]>=0.8 and r["k_mid"]<0.5) and not (r["dk_pow"]<=0.2 and r["k_mid"]>0.5)]
    by_g=defaultdict(dict)
    for r in soft: by_g[r["game"]][r["side"]]=r
    pairs=[g for g in by_g.values() if "home" in g and "away" in g]; keys=[g["home"]["game"] for g in pairs]
    m,h,_,_=clustered([100*(g["home"]["k_mid"]+g["away"]["k_mid"]-1) for g in pairs],keys); print(f"{lab}: (mid+mid)-1 {m:+.2f}c [{m-h:+.2f},{m+h:+.2f}]  n={len(pairs)}")
    dogs=[r for r in soft if r["dk_pow"]<0.5]
    for lo,hi in ((0,.05),(.05,.15),(.15,.3),(.3,.5)):
        s_=[r for r in dogs if lo<=r["k_mid"]+r["k_spread"]/2<hi]
        if len(s_)<8: continue
        a=[r["k_mid"]+r["k_spread"]/2 for r in s_]; w=[r["won"] for r in s_]
        m,h,n,G=clustered([100*(ai-wi)-100*0.07*ai*(1-ai) for ai,wi in zip(a,w)],[r["game"] for r in s_])
        print(f"   dogs ask [{lo:.2f},{hi:.2f}) n={n} ask {sum(a)/n:.3f} won {sum(w)/n:.3f}  EV sell@ask net fee {m:+.2f}c [{m-h:+.2f},{m+h:+.2f}]")
