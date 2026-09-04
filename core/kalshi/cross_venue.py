"""Kalshi CFB team code -> Polymarket US CFB team code.

Built 2026-09-04 from **both venues' own payloads**, not by inference, for the
same reason `codes_from_sub_title` exists: with 200+ variable-length codes a
guessed correspondence yields a CONFIDENT row for a game that does not exist,
and no drop-counter can see it.

**Harvest.** Kalshi ``/events?series_ticker=KXNCAAF{GAME,TOTAL,SPREAD}`` states
its codes in ``sub_title`` ("SJSU vs EMU (Sep 4)") and its display names in
``title`` ("San Jose St. vs Eastern Michigan: Total Points"). Polymarket US
``/v2/leagues/cfb/events`` states both in ``teams[]``: ``abbreviation`` ("sjst")
and ``safeName`` ("San Jose State"). Games were matched on **date + unordered
normalised name pair** (461 Kalshi events -> 250 distinct games; 241 Polymarket
games; **177 matched**), and the code correspondence read off each matched game.

**The map is over-determined, which is the positive control.** 220 codes derived
from 177 games with **zero conflicts in either direction** — no Kalshi code maps
to two Polymarket codes and no Polymarket code to two Kalshi codes. A wrong name
match would have shown up as a conflict; none did.

**Only 30.5% of codes are identical (67/220).** A naive lowercase-and-compare
join silently loses 69.5% of the board, which is why the earlier cross-venue
census matched 10 pairs out of 57 contracts.

**And one code COLLIDES, which is the dangerous case rather than the lossy one.**
Kalshi ``SDST`` is South Dakota St. and maps to ``sdkst``; Polymarket's ``sdst``
is San Diego St., which Kalshi calls ``SDSU``. A naive join does not merely miss
that pair, it silently joins **two different games**. This is the CONN/PDX
hazard from `core.kalshi.mapping`, now across venues.

**Coverage, stated separately from mapping.** 73 of 250 Kalshi games did not
match, and the reason is mostly NOT the code space: 39 are games where
Polymarket lists neither team that day and 12 fall on dates Polymarket has no
CFB board at all -- 51 of 73 are Polymarket simply not carrying the game
(largely FCS/small-college). 22 are single-team matches needing more work. So
the join ceiling is set by Polymarket's narrower board, not only by codes.

**Names are the bridge and they are not authoritative** — the one normalisation
that earns its place is ``St.`` -> ``State``, which lifts exact name agreement
from 67.6% to 87.4%. Everything after that is worth ~0.7pp combined. The map,
once derived, should be used in preference to name matching.
"""

from __future__ import annotations

#: Kalshi CFB code -> Polymarket US CFB code. Comments carry Kalshi's own
#: display name so a wrong row is legible without re-fetching either venue.
KALSHI_TO_POLYMARKET_CFB: dict[str, str] = {
    "AAMU":  "alaam",               # Alabama A&M
    "AC":    "abchr",               # Abilene Christian
    "AFA":   "airf",                # Air Force
    "AKR":   "akron",               # Akron
    "ALA":   "ala",                 # Alabama (identical)
    "ALCN":  "alcst",               # Alcorn St.
    "ALST":  "alast",               # Alabama St.
    "APP":   "applst",              # Appalachian St.
    "ARIZ":  "arz",                 # Arizona
    "ARK":   "ark",                 # Arkansas (identical)
    "ARMY":  "army",                # Army (identical)
    "ARPB":  "arpb",                # Arkansas-Pine Bluff (identical)
    "ARST":  "arkst",               # Arkansas St.
    "ASU":   "arzst",               # Arizona St.
    "AUB":   "aubrn",               # Auburn
    "BALL":  "ballst",              # Ball St.
    "BAY":   "bayl",                # Baylor
    "BC":    "boscol",              # Boston College
    "BGSU":  "bowlgr",              # Bowling Green
    "BRY":   "bryant",              # Bryant
    "BSU":   "boise",               # Boise St.
    "BUCK":  "buck",                # Bucknell (identical)
    "BUFF":  "buf",                 # Buffalo
    "BYU":   "byu",                 # BYU (identical)
    "CAL":   "cah",                 # California
    "CAMP":  "camp",                # Campbell (identical)
    "CCAR":  "coast",               # Coastal Carolina
    "CCSU":  "cencon",              # Central Connecticut St.
    "CHAR":  "charlt",              # Charlotte
    "CHAT":  "chat",                # Chattanooga (identical)
    "CHSO":  "chsou",               # Charleston Southern
    "CIN":   "cin",                 # Cincinnati (identical)
    "CIT":   "cita",                # The Citadel
    "CLEM":  "clmsn",               # Clemson
    "CMU":   "cmich",               # Central Michigan
    "COLG":  "colg",                # Colgate (identical)
    "COLO":  "col",                 # Colorado
    "COOK":  "bcook",               # Bethune-Cookman
    "CSU":   "colst",               # Colorado St.
    "DAV":   "dav",                 # Davidson (identical)
    "DEL":   "del",                 # Delaware (identical)
    "DRKE":  "drake",               # Drake
    "DSU":   "delst",               # Delaware St.
    "DUKE":  "duke",                # Duke (identical)
    "DUQ":   "duq",                 # Duquesne (identical)
    "ECU":   "ecar",                # East Carolina
    "EIU":   "eill",                # Eastern Illinois
    "EKY":   "ekent",               # Eastern Kentucky
    "ELON":  "elon",                # Elon (identical)
    "EMU":   "emich",               # Eastern Michigan
    "ETAM":  "txamc",               # East Texas A&M
    "ETSU":  "etnst",               # East Tennessee St.
    "EWU":   "ewash",               # Eastern Washington
    "FAMU":  "flam",                # Florida A&M
    "FAU":   "flatl",               # Florida Atlantic
    "FIU":   "flint",               # Florida International
    "FLA":   "fl",                  # Florida
    "FOR":   "fordm",               # Fordham
    "FSU":   "flst",                # Florida St.
    "FUR":   "furman",              # Furman
    "GASO":  "gas",                 # Georgia Southern
    "GAST":  "gast",                # Georgia St. (identical)
    "GT":    "gtech",               # Georgia Tech
    "GTWN":  "gtwn",                # Georgetown (identical)
    "HAMP":  "hamp",                # Hampton (identical)
    "HC":    "holy",                # Holy Cross
    "HCU":   "houbap",              # Houston Christian
    "HOU":   "hou",                 # Houston (identical)
    "HOW":   "howrd",               # Howard
    "IDHO":  "idaho",               # Idaho
    "IDST":  "idhst",               # Idaho St.
    "ILL":   "ill",                 # Illinois (identical)
    "ILST":  "illst",               # Illinois St.
    "IND":   "ind",                 # Indiana (identical)
    "INST":  "indst",               # Indiana St.
    "IOWA":  "iowa",                # Iowa (identical)
    "ISU":   "iowast",              # Iowa St.
    "IW":    "incar",               # Incarnate Word
    "JMU":   "jmad",                # James Madison
    "JVST":  "jaxst",               # Jacksonville St.
    "KENN":  "kenest",              # Kennesaw St.
    "KENT":  "kentst",              # Kent St.
    "KSU":   "kanst",               # Kentucky State Thorobreds
    "LAF":   "lafay",               # Lafayette
    "LAM":   "lamar",               # Lamar
    "LEH":   "lehi",                # Lehigh
    "LIB":   "librty",              # Liberty
    "LINW":  "jac",                 # Lindenwood
    "LOU":   "lou",                 # Louisville (identical)
    "LSU":   "lsu",                 # LSU (identical)
    "LT":    "loutch",              # Louisiana Tech
    "ME":    "maine",               # Maine
    "MEM":   "mphs",                # Memphis
    "MER":   "merc",                # Mercer
    "MHU":   "mrcy",                # Mercyhurst
    "MICH":  "mich",                # Michigan (identical)
    "MINN":  "minnst",              # Minnesota
    "MISS":  "miss",                # Ole Miss (identical)
    "MOH":   "miaoh",               # Miami (OH)
    "MONM":  "monm",                # Monmouth (identical)
    "MONT":  "mont",                # Montana (identical)
    "MORE":  "more",                # Morehead St. (identical)
    "MOSU":  "msrst",               # Missouri St.
    "MRSH":  "marsh",               # Marshall
    "MRST":  "mrst",                # Marist (identical)
    "MSST":  "mspst",               # Mississippi St.
    "MSU":   "mst",                 # Michigan St.
    "MTU":   "mtnst",               # Middle Tennessee
    "MURR":  "murst",               # Murray St.
    "NAU":   "narz",                # Northern Arizona
    "NAVY":  "navy",                # Navy (identical)
    "NCAT":  "ncat",                # North Carolina A&T (identical)
    "NCCU":  "ncc",                 # North Carolina Central
    "NCST":  "ncst",                # North Carolina St. (identical)
    "ND":    "nd",                  # Notre Dame (identical)
    "NDSU":  "ndkst",               # North Dakota St.
    "NEB":   "nebr",                # Nebraska
    "NHC":   "nhc",                 # New Haven (identical)
    "NIU":   "nill",                # Northern Illinois
    "NORF":  "norfst",              # Norfolk St.
    "NWST":  "nwst",                # Northwestern St. (identical)
    "ODU":   "old",                 # Old Dominion
    "OHIO":  "ohio",                # Ohio (identical)
    "OKLA":  "okl",                 # Oklahoma
    "OKST":  "okst",                # Oklahoma St. (identical)
    "ORE":   "ore",                 # Oregon (identical)
    "ORST":  "oregst",              # Oregon St.
    "OSU":   "ohiost",              # Ohio St.
    "PEAY":  "ausp",                # Austin Peay
    "PITT":  "pitt",                # Pittsburgh (identical)
    "PRE":   "presb",               # Presbyterian
    "PSU":   "pennst",              # Penn St.
    "PUR":   "pur",                 # Purdue (identical)
    "PV":    "pvam",                # Prairie View A&M
    "RICE":  "rice",                # Rice (identical)
    "RICH":  "rich",                # Richmond (identical)
    "RMU":   "robms",               # Robert Morris
    "RUTG":  "rutger",              # Rutgers
    "SAM":   "samf",                # Samford
    "SCAR":  "sc",                  # South Carolina
    "SCST":  "scarst",              # South Carolina St.
    "SDAK":  "sdak",                # South Dakota (identical)
    "SDST":  "sdkst",               # South Dakota St. -- 'sdst' is PM's code for SDSU (San Diego St.)
    "SDSU":  "sdst",                # San Diego St.
    "SELA":  "selou",               # Southeastern Louisiana
    "SEMO":  "semst",               # Southeast Missouri St.
    "SHSU":  "smho",                # Sam Houston
    "SHU":   "sacred",              # Sacred Heart
    "SIU":   "sill",                # Southern Illinois
    "SJSU":  "sjst",                # San Jose St.
    "SMU":   "smu",                 # SMU (identical)
    "STET":  "stet",                # Stetson (identical)
    "STNH":  "stnh",                # Stonehill (identical)
    "STON":  "stbr",                # Stony Brook
    "SUU":   "sutah",               # Southern Utah
    "SYR":   "syra",                # Syracuse
    "TARL":  "tarl",                # Tarleton St. (identical)
    "TEM":   "templ",               # Temple
    "TENN":  "tenn",                # Tennessee (identical)
    "TEX":   "tx",                  # Texas
    "TLSA":  "tulsa",               # Tulsa
    "TNST":  "tenst",               # Tennessee St.
    "TNTC":  "tentch",              # Tennessee Tech
    "TOL":   "toledo",              # Toledo
    "TOWS":  "tows",                # Towson (identical)
    "TROY":  "troy",                # Troy (identical)
    "TTU":   "txtech",              # Texas Tech
    "TULN":  "tulane",              # Tulane
    "TXAM":  "txam",                # Texas A&M (identical)
    "TXSO":  "txs",                 # Texas Southern
    "TXST":  "txst",                # Texas St. (identical)
    "UAB":   "uab",                 # UAB (identical)
    "UCD":   "ucdv",                # UC Davis
    "UCF":   "ucf",                 # UCF (identical)
    "UCLA":  "ucla",                # UCLA (identical)
    "UGA":   "ga",                  # Georgia
    "UK":    "uk",                  # Kentucky (identical)
    "ULM":   "lamon",               # Louisiana-Monroe
    "UNA":   "nal",                 # North Alabama
    "UNC":   "ncar",                # North Carolina
    "UNCO":  "ncol",                # Northern Colorado
    "UND":   "ndak",                # North Dakota
    "UNH":   "nhamp",               # New Hampshire
    "UNI":   "niowa",               # Northern Iowa
    "UNLV":  "unlv",                # UNLV (identical)
    "UNM":   "nmx",                 # New Mexico
    "UNT":   "ntx",                 # North Texas
    "URI":   "ri",                  # Rhode Island
    "USA":   "sala",                # South Alabama
    "USD":   "usd",                 # San Diego (identical)
    "USF":   "sfl",                 # South Florida
    "USM":   "soumis",              # Southern Miss
    "UST":   "stmn",                # St. Thomas
    "USU":   "utahst",              # Utah St.
    "UTRGV": "utrgv",               # UT Rio Grande Valley (identical)
    "UTSA":  "utsa",                # UTSA (identical)
    "UTU":   "dxst",                # Utah Tech
    "UVA":   "vir",                 # Virginia
    "UWGA":  "uwg",                 # West Georgia
    "VALP":  "valp",                # Valparaiso (identical)
    "VAN":   "vand",                # Vanderbilt
    "VILL":  "vill",                # Villanova (identical)
    "VMI":   "vamil",               # VMI
    "VT":    "vtech",               # Virginia Tech
    "WAG":   "wag",                 # Wagner (identical)
    "WAKE":  "wake",                # Wake Forest (identical)
    "WASH":  "wash",                # Washington (identical)
    "WCU":   "wcar",                # Western Carolina
    "WEB":   "webst",               # Webber International Warriors
    "WEBB":  "gardwb",              # Gardner-Webb
    "WIS":   "wisc",                # Wisconsin
    "WIU":   "will",                # Western Illinois
    "WKU":   "wkent",               # Western Kentucky
    "WM":    "wm",                  # William & Mary (identical)
    "WMU":   "wmich",               # Western Michigan
    "WOF":   "woff",                # Wofford
    "WSU":   "washst",              # Washington St.
    "WVU":   "wvir",                # West Virginia
    "WYO":   "wyom",                # Wyoming
    "YSU":   "yngst",               # Youngstown St.
}

#: Reverse direction. Built rather than written so the two cannot drift.
POLYMARKET_TO_KALSHI_CFB: dict[str, str] = {
    v: k for k, v in KALSHI_TO_POLYMARKET_CFB.items()
}

#: Kalshi codes whose lowercase form is a VALID Polymarket code for a
#: DIFFERENT team. A naive equality join mis-joins these rather than
#: missing them, so they are named explicitly.
COLLIDING_CODES: frozenset[str] = frozenset({"SDST"})


class UnknownCrossVenueCode(KeyError):
    """Raised rather than guessing, per this module's whole point."""


def kalshi_to_polymarket(code: str) -> str:
    """Kalshi CFB code -> Polymarket code, or raise.

    Explicit failure is the requirement: a silent fallback to the lowercased
    Kalshi code is wrong for 69.5% of the board and mis-joins SDST.
    """
    key = (code or "").strip().upper()
    if key not in KALSHI_TO_POLYMARKET_CFB:
        raise UnknownCrossVenueCode(
            f"No Polymarket CFB code known for Kalshi {code!r}. "
            "Re-harvest both boards rather than lowercasing the Kalshi code."
        )
    return KALSHI_TO_POLYMARKET_CFB[key]
