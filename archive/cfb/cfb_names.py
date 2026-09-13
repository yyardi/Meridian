"""cfb_names.py -- the CFBD<->ESPN school-name bridge, with a uniqueness guard.

CFBD gives SCHOOL ONLY ("Iowa", "Miami"); ESPN gives SCHOOL + MASCOT
("Iowa Hawkeyes", "Miami Hurricanes"). Exact matching yields 0/19; prefix
matching yields 19/19 (meridian-a1, 2026-09-05).

★ WHY PREFIX MATCHING NEEDS A GUARD ★
College football has genuine name collisions where one CFBD school name is a
prefix of MULTIPLE ESPN names:
    "Miami"          -> "Miami Hurricanes" (FL) AND "Miami RedHawks" (OH)
    "Louisiana"      -> "Louisiana Ragin' Cajuns" AND "Louisiana Tech Bulldogs"
    "Texas"          -> "Texas Longhorns" AND "Texas Tech Red Raiders" ...
A prefix match that silently picks the first is a WRONG GAME PAIRING: the model
would train on one game's state against another game's outcome, and every
validation would pass. 19/19 on a 19-game sample does not establish safety at
9,000 games -- it establishes that no collision happened to appear in 19 games.

So: match must be UNIQUE or the row is REFUSED and counted. Same shape as the
+/-1 day date join -- a fuzzy bridge that works on a sample and mismatches
silently at scale.
"""
from __future__ import annotations


def _norm(s: str) -> str:
    return " ".join(str(s).replace("&", "and").replace("'", "").split()).casefold()


def bridge(cfbd_name: str, espn_names) -> tuple[str | None, str]:
    """Returns (espn_name | None, reason). Refuses on ambiguity, never guesses."""
    c = _norm(cfbd_name)
    exact = [e for e in espn_names if _norm(e) == c]
    if len(exact) == 1:
        return exact[0], "exact"
    if len(exact) > 1:
        return None, f"AMBIGUOUS exact: {exact}"
    pref = [e for e in espn_names if _norm(e).startswith(c + " ")]
    if len(pref) == 1:
        return pref[0], "unique-prefix"
    if len(pref) > 1:
        return None, f"AMBIGUOUS prefix ({len(pref)}): {sorted(pref)} -- REFUSED, not guessed"
    return None, "no match"


def build_map(cfbd_names, espn_names):
    out, refused = {}, []
    for c in cfbd_names:
        e, why = bridge(c, espn_names)
        (out.__setitem__(c, e) if e else refused.append((c, why)))
    return out, refused


def _selftest():
    espn = ["Iowa Hawkeyes", "Duke Blue Devils", "Miami Hurricanes", "Miami RedHawks",
            "Texas Longhorns", "Texas Tech Red Raiders", "Louisiana Ragin Cajuns",
            "Louisiana Tech Bulldogs", "Purdue Boilermakers"]
    assert bridge("Iowa", espn)[0] == "Iowa Hawkeyes"
    assert bridge("Purdue", espn)[1] == "unique-prefix"
    # ★ the collisions must REFUSE, not pick the first
    for coll in ("Miami", "Texas", "Louisiana"):
        got, why = bridge(coll, espn)
        assert got is None and "AMBIGUOUS" in why, f"{coll} silently resolved to {got}"
    # a longer name that is unambiguous still matches
    assert bridge("Texas Tech", espn)[0] == "Texas Tech Red Raiders"
    assert bridge("Nowhere State", espn) == (None, "no match")
    m, refused = build_map(["Iowa", "Miami", "Purdue"], espn)
    assert set(m) == {"Iowa", "Purdue"} and len(refused) == 1
    print(f"selftest OK -- unique matches bridge, {len(refused)} collision refused not guessed "
          f"(Miami FL/OH, Texas/Texas Tech, Louisiana/La Tech all caught)")


if __name__ == "__main__":
    _selftest()


# --------------------------------------------------------------------------
# PROVIDER identity -- the same fuzzy-key family as the school-name bridge.
#
# CFBD carries BOTH "Draft Kings" AND "DraftKings" as separate provider strings
# on the SAME game (meridian-a1, 2026-09-05). Keying a dict on the raw string
# silently keeps whichever arrived last -- and if the two entries ever disagree,
# the survivor is arbitrary. Normalise, then REFUSE on a genuine conflict.
#
# AND ASSERT THE PROVIDER PER GAME, not once for the dataset. If ESPN's
# pickcenter serves DraftKings for most games and another book for some, a
# value-only comparison certifies parity while the model trains on one book and
# serves on another for that subset -- the exact asymmetry the check exists to
# catch, hiding inside a passing check.
PROVIDER_ALIASES = {"draftkings": "draftkings", "draft kings": "draftkings",
                    "bovada": "bovada", "espn bet": "espnbet", "espnbet": "espnbet",
                    "consensus": "consensus", "teamrankings": "teamrankings"}


def norm_provider(p: str) -> str:
    k = " ".join(str(p).split()).casefold()
    return PROVIDER_ALIASES.get(k, k.replace(" ", ""))


def pick_provider_line(entries, want="DraftKings"):
    """entries: [(provider, spread)]. Returns (spread, reason). Refuses on conflict."""
    w = norm_provider(want)
    hits = {}
    for prov, spread in entries:
        hits.setdefault(norm_provider(prov), []).append(spread)
    if w not in hits:
        return None, f"provider {want!r} absent (have: {sorted(hits)})"
    vals = {v for v in hits[w] if v is not None}
    if len(vals) > 1:
        return None, f"CONFLICT: {want!r} appears {len(hits[w])}x with different lines {sorted(vals)} -- REFUSED"
    return next(iter(vals)), "unique after normalisation"


def assert_same_provider(ours_provider, cfbd_provider):
    a, b = norm_provider(ours_provider), norm_provider(cfbd_provider)
    return (a == b), f"serve={a} train={b}" + ("" if a == b else "  <-- TRAIN/SERVE BOOK MISMATCH")


def _selftest_providers():
    # the real case: same book, two spellings, same value -> collapses cleanly
    e = [("Bovada", -40.5), ("Draft Kings", -38.5), ("DraftKings", -38.5)]
    v, why = pick_provider_line(e)
    assert v == -38.5 and "unique" in why, why
    # ★ two spellings with DIFFERENT lines must REFUSE, not pick the last
    e2 = [("Draft Kings", -38.5), ("DraftKings", -37.0)]
    v2, why2 = pick_provider_line(e2)
    assert v2 is None and "CONFLICT" in why2, why2
    # absent provider is named, not defaulted to another book
    v3, why3 = pick_provider_line([("Bovada", -40.5)])
    assert v3 is None and "absent" in why3
    # ★ per-game provider identity
    ok, _ = assert_same_provider("DraftKings", "Draft Kings"); assert ok
    bad, msg = assert_same_provider("DraftKings", "Bovada")
    assert not bad and "MISMATCH" in msg
    print("selftest OK -- provider aliases collapse, conflicting duplicates refused, "
          "absent provider named, per-game book identity asserted")


if __name__ == "__main__":
    _selftest_providers()
