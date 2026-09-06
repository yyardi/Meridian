"""Do ESPN abbreviations equal venue slug codes? If not, my null is my matcher.

The map is FUZZY for a reason. If the two sides use different vocabularies,
then exact-segment matching produces false NEGATIVES, and my "0 of 15 present"
measures my own matcher rather than the venue.

Test on games the map DID match: take the ESPN abbreviation and ask whether it
appears verbatim as a segment of the venue slug the map paired it with.
"""
import glob
import json

import pandas as pd

S = ("/private/tmp/claude-501/-Users-yayardia-Documents-Quant-Meridian/"
     "3779e560-5fd2-4c93-8122-5897803b1985/scratchpad")
E = "/Users/yayardia/Documents/Quant/Meridian/backups/exports/"

abbr = {}
for f in sorted(glob.glob(f"{S}/sb_*.json")):
    for ev in (json.load(open(f)).get("events") or []):
        comps = (ev.get("competitions") or [{}])[0]
        abbr[str(ev["id"])] = [
            ((c.get("team") or {}).get("abbreviation") or "").lower()
            for c in (comps.get("competitors") or [])]

m = pd.read_csv(E + "cfb_game_map_computed_20260906T221500Z.csv")
both = miss = 0
shown = 0
print("MATCHED games: does ESPN's abbreviation appear in the venue slug?\n")
for _, r in m.iterrows():
    gid, slug = str(r.espn_game_id), str(r.event_slug)
    ab = [a for a in abbr.get(gid, []) if a]
    if not ab:
        continue
    seg = set(slug.lower().split("-"))
    hit = [a for a in ab if a in seg]
    if len(hit) == len(ab):
        both += 1
    else:
        miss += 1
        if shown < 8:
            print(f"  {gid}  espn={','.join(ab):<12s} venue slug={slug}")
            shown += 1

tot = both + miss
print(f"\n  BOTH ESPN abbreviations present verbatim: {both} of {tot}")
print(f"  at least one absent:                     {miss} of {tot}")
if tot:
    print(f"\n  -> exact-segment matching finds only {both/tot:.0%} of games the")
    print("     map ALREADY matched. My '0 of 15 present' is therefore a")
    print("     property of my matcher, not of the venue.")
