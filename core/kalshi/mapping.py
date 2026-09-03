"""Kalshi ticker parsing and the Kalshi -> ESPN team mapping.

Kalshi's WNBA event tickers look like ``KXWNBAGAME-26AUG05PHXATL``: a series
ticker, then ``yyMONdd`` and **two team codes concatenated with no
delimiter**. The shared suffix (``26AUG05PHXATL``) is the same across the
moneyline, spread, and total series for one game, so it serves as the game
key.

Two hazards, both the same species as the Polymarket ones in
`core.team_mapping`:

1. **Kalshi's codes are a third abbreviation space.** Two differ from ESPN:
   ``CONN`` -> ``CON`` and ``PDX`` -> ``POR``. The table below is explicit and
   complete for the same reason POLYMARKET_TO_ESPN is: an explicit table fails
   loudly on a new franchise, a transform fails silently.

2. **The concatenated pair has no delimiter**, so parsing tries every split
   point and demands exactly one where both halves are known codes.
   `tests/test_kalshi.py` proves that property holds for every franchise pair,
   so a future code addition that introduces ambiguity breaks a test instead
   of silently mis-parsing (e.g. all-star exhibition codes like ``SPNCOO``
   simply fail to parse, which is correct — those are not games we compare).

Ticker order is stored verbatim but treated as **positional only**, never
home/away. Polymarket's slug order flipped convention mid-season; Kalshi's
order earns the same distrust until measured. Orientation, when needed, comes
from ESPN via the existing `core.team_mapping` machinery on the unordered
pair.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

from core.team_mapping import UnknownTeamError

#: Kalshi code -> ESPN abbreviation. Codes observed on the venue 2026-08-05
#: across every open KXWNBAGAME event.
KALSHI_TO_ESPN: dict[str, str] = {
    "ATL": "ATL",
    "CHI": "CHI",
    "CONN": "CON",   # <- differs
    "DAL": "DAL",
    "GS": "GS",
    "IND": "IND",
    "LA": "LA",
    "LV": "LV",
    "MIN": "MIN",
    "NY": "NY",
    "PDX": "POR",    # <- differs
    "PHX": "PHX",
    "SEA": "SEA",
    "TOR": "TOR",
    "WSH": "WSH",
}

#: Kalshi NFL code -> ESPN abbreviation. Codes harvested from the venue
#: 2026-09-02 via each open KXNFLGAME event's own market-ticker suffixes
#: (the two per-team markets name the codes exactly — no split-guessing),
#: with yes_sub_title confirming the franchise. Two differ from ESPN,
#: the same species as CONN/PDX above.
KALSHI_TO_ESPN_NFL: dict[str, str] = {
    "ARI": "ARI", "ATL": "ATL", "BAL": "BAL", "BUF": "BUF", "CAR": "CAR",
    "CHI": "CHI", "CIN": "CIN", "CLE": "CLE", "DAL": "DAL", "DEN": "DEN",
    "DET": "DET", "GB": "GB", "HOU": "HOU", "IND": "IND",
    "JAC": "JAX",    # <- differs
    "KC": "KC", "LAC": "LAC", "LAR": "LAR", "LV": "LV", "MIA": "MIA",
    "MIN": "MIN", "NE": "NE", "NO": "NO", "NYG": "NYG", "NYJ": "NYJ",
    "PHI": "PHI", "PIT": "PIT", "SEA": "SEA", "SF": "SF", "TB": "TB",
    "TEN": "TEN",
    "WAS": "WSH",    # <- differs
}

#: Kalshi NCAAF code -> ESPN abbreviation. Every value is None ON PURPOSE.
#: The KEYS are harvested from the venue (2026-09-03, all 468 open NCAAF
#: events across the three series) and exist so a game key can be split;
#: the VALUES are None because Kalshi's college code space is NOT ESPN's
#: and cannot be derived: measured against ESPN's own 2026-09-03 slate,
#: 4 of 11 games use a different code on each side (ESPN BCU / Kalshi
#: COOK, ALB / ALBY, MIZ / MIZZ, WES / UWGA) -- a 36-in-100 divergence,
#: the CONN/PDX hazard at scale. Guessing would manufacture confident
#: wrong identities, so first_espn stays NULL for college games and the
#: Polymarket link is skipped rather than faked. The venue's own `title`
#: and `sub_title` are stored verbatim, so an ESPN mapping can be built
#: later from data we already hold.
KALSHI_TO_ESPN_NCAAF: dict[str, str | None] = {
    "AAMU": None,     # Alabama A&M
    "AC": None,       # Abilene Christian
    "AFA": None,      # Air Force
    "AKR": None,      # Akron
    "ALA": None,      # Alabama
    "ALBY": None,     # University at Albany
    "ALCN": None,     # Alcorn St.
    "ALST": None,     # Alabama St.
    "APP": None,      # Appalachian St.
    "ARIZ": None,     # Arizona
    "ARK": None,      # Arkansas
    "ARMY": None,     # Army
    "ARPB": None,     # Arkansas-Pine Bluff
    "ARST": None,     # Arkansas St.
    "ASU": None,      # Arizona St.
    "AUB": None,      # Auburn
    "BALL": None,     # Ball St.
    "BAY": None,      # Baylor
    "BC": None,       # Boston College
    "BGSU": None,     # Bowling Green
    "BRWN": None,     # Brown
    "BRY": None,      # Bryant
    "BSU": None,      # Boise St.
    "BUCK": None,     # Bucknell
    "BUFF": None,     # Buffalo
    "BUT": None,      # Butler
    "BYU": None,      # BYU
    "CAL": None,      # California
    "CAMP": None,     # Campbell
    "CARK": None,     # Central Arkansas
    "CCAR": None,     # Coastal Carolina
    "CCSU": None,     # Central Connecticut St.
    "CHAR": None,     # Charlotte
    "CHAT": None,     # Chattanooga
    "CHS": None,      # Chicago State Cougars
    "CHSO": None,     # Charleston Southern
    "CIN": None,      # Cincinnati
    "CIT": None,      # The Citadel
    "CLEM": None,     # Clemson
    "CLMB": None,     # Columbia
    "CMU": None,      # Central Michigan
    "COLG": None,     # Colgate
    "COLO": None,     # Colorado
    "CONN": None,     # UConn
    "COOK": None,     # Bethune-Cookman
    "COR": None,      # Cornell
    "CP": None,       # Cal Poly
    "CSU": None,      # Central State (OH) Marauders
    "CWU": None,      # Central Washington Wildcats
    "DART": None,     # Dartmouth
    "DAV": None,      # Davidson
    "DEL": None,      # Delaware
    "DRKE": None,     # Drake
    "DSU": None,      # Delaware St.
    "DUKE": None,     # Duke
    "DUQ": None,      # Duquesne
    "ECSU": None,     # Elizabeth City State Vikings
    "ECU": None,      # East Carolina
    "EIU": None,      # Eastern Illinois
    "EKY": None,      # Eastern Kentucky
    "ELON": None,     # Elon
    "EMU": None,      # Eastern Michigan
    "ETAM": None,     # East Texas A&M
    "ETSU": None,     # East Tennessee St.
    "EWC": None,      # Edward Waters Tigers
    "EWU": None,      # Eastern Washington
    "FAMU": None,     # Florida A&M
    "FAU": None,      # Florida Atlantic
    "FIU": None,      # Florida International
    "FLA": None,      # Florida
    "FOR": None,      # Fordham
    "FPU": None,      # Franklin Pierce Ravens
    "FRES": None,     # Fresno St.
    "FSU": None,      # Florida St.
    "FUR": None,      # Furman
    "GASO": None,     # Georgia Southern
    "GAST": None,     # Georgia St.
    "GRAM": None,     # Grambling St.
    "GT": None,       # Georgia Tech
    "GTWN": None,     # Georgetown
    "HAMP": None,     # Hampton
    "HARV": None,     # Harvard
    "HAW": None,      # Hawai'i
    "HC": None,       # Holy Cross
    "HCU": None,      # Houston Christian
    "HOU": None,      # Houston
    "HOW": None,      # Howard
    "IDHO": None,     # Idaho
    "IDST": None,     # Idaho St.
    "ILL": None,      # Illinois
    "ILST": None,     # Illinois St.
    "IND": None,      # Indiana
    "INST": None,     # Indiana St.
    "IOWA": None,     # Iowa
    "ISU": None,      # Iowa St.
    "IW": None,       # Incarnate Word
    "JKST": None,     # Jackson St.
    "JMU": None,      # James Madison
    "JVST": None,     # Jacksonville St.
    "KCU": None,      # Kentucky Christian Knights
    "KENN": None,     # Kennesaw St.
    "KENT": None,     # Kent St.
    "KSU": None,      # Kansas St.
    "KU": None,       # Kansas
    "LAF": None,      # Lafayette
    "LAM": None,      # Lamar
    "LC": None,       # Lane Dragons
    "LEH": None,      # Lehigh
    "LIB": None,      # Liberty
    "LINW": None,     # Lindenwood
    "LIU": None,      # LIU
    "LOU": None,      # Louisville
    "LSU": None,      # LSU
    "LT": None,       # Louisiana Tech
    "MASS": None,     # UMass
    "MCNS": None,     # McNeese
    "MD": None,       # Maryland
    "ME": None,       # Maine
    "MEM": None,      # Memphis
    "MER": None,      # Mercer
    "MHU": None,      # Mercyhurst
    "MIA": None,      # Miami (FL)
    "MICH": None,     # Michigan
    "MILES": None,    # Miles Golden Bears
    "MINN": None,     # Minnesota
    "MISS": None,     # Ole Miss
    "MIZZ": None,     # Missouri
    "MOH": None,      # Miami (OH)
    "MONM": None,     # Monmouth
    "MONT": None,     # Montana
    "MORE": None,     # Morehead St.
    "MORG": None,     # Morgan St.
    "MOSU": None,     # Missouri St.
    "MRMK": None,     # Merrimack
    "MRSH": None,     # Marshall
    "MRST": None,     # Marist
    "MSST": None,     # Mississippi St.
    "MSU": None,      # Michigan St.
    "MTST": None,     # Montana St.
    "MTU": None,      # Middle Tennessee
    "MURR": None,     # Murray St.
    "MVSU": None,     # Mississippi Valley St.
    "NAU": None,      # Northern Arizona
    "NAVY": None,     # Navy
    "NCAT": None,     # North Carolina A&T
    "NCCU": None,     # North Carolina Central
    "NCST": None,     # North Carolina St.
    "ND": None,       # Notre Dame
    "NDSU": None,     # North Dakota St.
    "NEB": None,      # Nebraska
    "NEV": None,      # Nevada
    "NHC": None,      # New Haven
    "NICH": None,     # Nicholls St.
    "NIU": None,      # Northern Illinois
    "NMSU": None,     # New Mexico St.
    "NORF": None,     # Norfolk St.
    "NW": None,       # Northwestern
    "NWST": None,     # Northwestern St.
    "ODU": None,      # Old Dominion
    "OHIO": None,     # Ohio
    "OKLA": None,     # Oklahoma
    "OKST": None,     # Oklahoma St.
    "ORE": None,      # Oregon
    "ORST": None,     # Oregon St.
    "OSU": None,      # Ohio St.
    "PEAY": None,     # Austin Peay
    "PENN": None,     # Penn
    "PITT": None,     # Pittsburgh
    "PRE": None,      # Presbyterian
    "PRIN": None,     # Princeton
    "PRST": None,     # Portland St.
    "PSU": None,      # Penn St.
    "PUR": None,      # Purdue
    "PV": None,       # Prairie View A&M
    "RICE": None,     # Rice
    "RICH": None,     # Richmond
    "RMU": None,      # Robert Morris
    "RUTG": None,     # Rutgers
    "SAC": None,      # Sacramento St.
    "SAM": None,      # Samford
    "SCAR": None,     # South Carolina
    "SCST": None,     # South Carolina St.
    "SCSU": None,     # Southern Connecticut State O
    "SDAK": None,     # South Dakota
    "SDST": None,     # South Dakota St.
    "SDSU": None,     # San Diego St.
    "SELA": None,     # Southeastern Louisiana
    "SEMO": None,     # Southeast Missouri St.
    "SFA": None,      # Stephen F. Austin
    "SHSU": None,     # Sam Houston
    "SHU": None,      # Sacred Heart
    "SIU": None,      # Southern Illinois
    "SJSU": None,     # San Jose St.
    "SMU": None,      # SMU
    "SOU": None,      # Southern University
    "STAN": None,     # Stanford
    "STET": None,     # Stetson
    "STNH": None,     # Stonehill
    "STON": None,     # Stony Brook
    "SUU": None,      # Southern Utah
    "SYR": None,      # Syracuse
    "TARL": None,     # Tarleton St.
    "TC": None,       # Tusculum Pioneers
    "TCU": None,      # TCU
    "TEM": None,      # Temple
    "TENN": None,     # Tennessee
    "TEX": None,      # Texas
    "TLSA": None,     # Tulsa
    "TNST": None,     # Tennessee St.
    "TNTC": None,     # Tennessee Tech
    "TOL": None,      # Toledo
    "TOWS": None,     # Towson
    "TROY": None,     # Troy
    "TTU": None,      # Texas Tech
    "TULN": None,     # Tulane
    "TWU": None,      # Texas Wesleyan Rams
    "TXAM": None,     # Texas A&M
    "TXSO": None,     # Texas Southern
    "TXST": None,     # Texas St.
    "UAB": None,      # UAB
    "UCD": None,      # UC Davis
    "UCF": None,      # UCF
    "UCLA": None,     # UCLA
    "UGA": None,      # Georgia
    "UK": None,       # Kentucky
    "ULL": None,      # Louisiana
    "ULM": None,      # Louisiana-Monroe
    "UNA": None,      # North Alabama
    "UNC": None,      # North Carolina
    "UNCO": None,     # Northern Colorado
    "UND": None,      # North Dakota
    "UNH": None,      # New Hampshire
    "UNI": None,      # Northern Iowa
    "UNLV": None,     # UNLV
    "UNM": None,      # New Mexico
    "UNT": None,      # North Texas
    "URI": None,      # Rhode Island
    "USA": None,      # South Alabama
    "USC": None,      # USC
    "USD": None,      # San Diego
    "USF": None,      # South Florida
    "USM": None,      # Southern Miss
    "UST": None,      # St. Thomas
    "USU": None,      # Utah St.
    "UTAH": None,     # Utah
    "UTEP": None,     # UTEP
    "UTM": None,      # Tennessee-Martin
    "UTRGV": None,    # UT Rio Grande Valley
    "UTSA": None,     # UTSA
    "UTU": None,      # Utah Tech
    "UVA": None,      # Virginia
    "UWFL": None,     # West Florida Argonauts
    "UWGA": None,     # West Georgia
    "VALP": None,     # Valparaiso
    "VAN": None,      # Vanderbilt
    "VILL": None,     # Villanova
    "VMI": None,      # VMI
    "VT": None,       # Virginia Tech
    "WAG": None,      # Wagner
    "WAKE": None,     # Wake Forest
    "WASH": None,     # Washington
    "WCU": None,      # Western Carolina
    "WEB": None,      # Webber International Warrior
    "WEBB": None,     # Gardner-Webb
    "WIS": None,      # Wisconsin
    "WIU": None,      # Western Illinois
    "WKU": None,      # Western Kentucky
    "WM": None,       # William & Mary
    "WMU": None,      # Western Michigan
    "WOF": None,      # Wofford
    "WSU": None,      # Washington St.
    "WVSU": None,     # West Virginia State Yellow J
    "WVU": None,      # West Virginia
    "WYO": None,      # Wyoming
    "YALE": None,     # Yale
    "YSU": None,      # Youngstown St.
}

LEAGUE_WNBA = "wnba"
LEAGUE_NFL = "nfl"
LEAGUE_CFB = "cfb"

#: One explicit table per league. Seven codes exist in BOTH tables (ATL,
#: CHI, DAL, IND, LV, MIN, SEA), so a game key alone does not identify a
#: league — parsing takes the league, and kalshi_games keys on
#: (league, game_key). A same-date cross-league pair (SEA/ATL in both
#: leagues on one Sunday) is a real collision, not a hypothetical.
LEAGUE_TABLES: dict[str, dict[str, str | None]] = {
    LEAGUE_WNBA: KALSHI_TO_ESPN,
    LEAGUE_NFL: KALSHI_TO_ESPN_NFL,
    LEAGUE_CFB: KALSHI_TO_ESPN_NCAAF,
}

#: The three full-game series the pre-registered comparison runs on.
SERIES_MONEYLINE = "KXWNBAGAME"
SERIES_SPREAD = "KXWNBASPREAD"
SERIES_TOTAL = "KXWNBATOTAL"

#: The NFL full-game series (GRIDIRON) — venue-verified 2026-09-02: same
#: event-ticker shape, ~25 team-directional spread rungs and ~19 total
#: rungs per game, no start time on events (the standing WNBA gap).
SERIES_MONEYLINE_NFL = "KXNFLGAME"
SERIES_SPREAD_NFL = "KXNFLSPREAD"
SERIES_TOTAL_NFL = "KXNFLTOTAL"

#: The NCAAF full-game series — venue-verified 2026-09-03, same
#: SERIES-yyMONdd<CODE><CODE> shape, all three sharing the game key.
SERIES_MONEYLINE_NCAAF = "KXNCAAFGAME"
SERIES_SPREAD_NCAAF = "KXNCAAFSPREAD"
SERIES_TOTAL_NCAAF = "KXNCAAFTOTAL"

SERIES_TO_MARKET_TYPE: dict[str, str] = {
    SERIES_MONEYLINE: "winner",
    SERIES_SPREAD: "spread",
    SERIES_TOTAL: "total",
    SERIES_MONEYLINE_NFL: "winner",
    SERIES_SPREAD_NFL: "spread",
    SERIES_TOTAL_NFL: "total",
    SERIES_MONEYLINE_NCAAF: "winner",
    SERIES_SPREAD_NCAAF: "spread",
    SERIES_TOTAL_NCAAF: "total",
}

SERIES_TO_LEAGUE: dict[str, str] = {
    SERIES_MONEYLINE: LEAGUE_WNBA,
    SERIES_SPREAD: LEAGUE_WNBA,
    SERIES_TOTAL: LEAGUE_WNBA,
    SERIES_MONEYLINE_NFL: LEAGUE_NFL,
    SERIES_SPREAD_NFL: LEAGUE_NFL,
    SERIES_TOTAL_NFL: LEAGUE_NFL,
    SERIES_MONEYLINE_NCAAF: LEAGUE_CFB,
    SERIES_SPREAD_NCAAF: LEAGUE_CFB,
    SERIES_TOTAL_NCAAF: LEAGUE_CFB,
}

LEAGUE_SERIES: dict[str, tuple[str, ...]] = {
    LEAGUE_WNBA: (SERIES_MONEYLINE, SERIES_SPREAD, SERIES_TOTAL),
    LEAGUE_NFL: (SERIES_MONEYLINE_NFL, SERIES_SPREAD_NFL, SERIES_TOTAL_NFL),
    LEAGUE_CFB: (SERIES_MONEYLINE_NCAAF, SERIES_SPREAD_NCAAF,
                 SERIES_TOTAL_NCAAF),
}

_MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


@dataclass(frozen=True)
class ParsedGameKey:
    """Date and team codes recovered from a Kalshi game key.

    ``first_code``/``second_code`` are positional ONLY — see module docstring.
    ``league`` names which code table parsed it (shared codes make the key
    alone league-ambiguous).
    """

    game_key: str
    local_date: dt.date
    first_code: str
    second_code: str
    league: str = LEAGUE_WNBA

    @property
    def first_espn(self) -> str:
        return _to_espn(self.first_code, self.league)

    @property
    def second_espn(self) -> str:
        return _to_espn(self.second_code, self.league)

    @property
    def espn_pair(self) -> frozenset[str]:
        """Unordered ESPN team pair — the only safe cross-venue join key."""
        return frozenset({self.first_espn, self.second_espn})


def _to_espn(code: str, league: str = LEAGUE_WNBA) -> str:
    table = LEAGUE_TABLES[league]
    key = (code or "").strip().upper()
    if key not in table:
        raise UnknownTeamError(
            f"no ESPN mapping for Kalshi {league} team {code!r}. A franchise "
            "was probably added — update the league's table."
        )
    mapped = table[key]
    if mapped is None:
        raise UnknownTeamError(
            f"Kalshi {league} code {code!r} has no ESPN identity: the college "
            "code space diverges from ESPN's and is not derivable (4 of 11 "
            "games measured divergent, 2026-09-03). Stored verbatim instead."
        )
    return mapped


def local_date_from_game_key(game_key: str) -> dt.date | None:
    """``26SEP03MASSRUTG`` -> 2026-09-03, independent of the team codes.

    Split out so a pairing taken from the venue's own sub_title (the
    ground truth) can still get its date without round-tripping through
    code-splitting, which is the part that can be wrong.
    """
    key = (game_key or "").strip().upper()
    if len(key) < 9:
        return None
    yy, mon, dd = key[:2], key[2:5], key[5:7]
    if mon not in _MONTHS or not yy.isdigit() or not dd.isdigit():
        return None
    try:
        return dt.date(2000 + int(yy), _MONTHS[mon], int(dd))
    except ValueError:
        return None


def parse_game_key(game_key: str, league: str = LEAGUE_WNBA) -> ParsedGameKey | None:
    """Parse ``26AUG05PHXATL`` -> (2026-08-05, PHX, ATL), or None.

    Returns None when the date is malformed, when no split of the team blob
    yields two known codes (all-star exhibitions), or when more than one split
    does (ambiguity — refusing is safer than guessing, same rule as
    `resolve_orientation`).
    """
    key = (game_key or "").strip().upper()
    if len(key) < 9:
        return None
    yy, mon, dd, teams = key[:2], key[2:5], key[5:7], key[7:]
    if mon not in _MONTHS or not yy.isdigit() or not dd.isdigit():
        return None
    try:
        local_date = dt.date(2000 + int(yy), _MONTHS[mon], int(dd))
    except ValueError:
        return None

    table = LEAGUE_TABLES[league]
    splits = [
        (teams[:i], teams[i:])
        for i in range(1, len(teams))
        if teams[:i] in table and teams[i:] in table
    ]
    if len(splits) != 1:
        return None
    first, second = splits[0]
    return ParsedGameKey(
        game_key=key, local_date=local_date, first_code=first,
        second_code=second, league=league,
    )


_SUB_TITLE_CODES = re.compile(r"^\s*([A-Z0-9&'.]+)\s+vs\s+([A-Z0-9&'.]+)")


def codes_from_sub_title(sub_title: str | None) -> tuple[str, str] | None:
    """``'KCU vs MORE (Sep 3)'`` -> ``('KCU', 'MORE')``.

    THE VENUE'S OWN PAIRING, and the reason college coverage is safe: with
    130+ variable-length codes and no delimiter, splitting a game key is a
    guess, and a wrong guess yields a CONFIDENT row for a game that does
    not exist — a failure no drop-counter can see. The event payload
    states both codes outright, so we read them instead of inferring.
    Measured 2026-09-03: present and parseable on 468/468 open NCAAF
    events, and the two codes concatenate to the ticker blob 468/468 —
    the venue agrees with itself.

    Split-parsing survives only as a CROSS-CHECK (`parse_game_key`): it
    agreed everywhere on those 468, but 10 of the 75,900 hypothetical code
    pairs are genuinely ambiguous (MEM+ORE vs ME+MORE — Memphis/Oregon is
    indistinguishable from Maine/Morehead St. by splitting alone), so the
    ground truth leads and the split follows.
    """
    m = _SUB_TITLE_CODES.match(sub_title or "")
    return (m.group(1), m.group(2)) if m else None


def game_key_from_event_ticker(event_ticker: str) -> str | None:
    """``KXWNBAGAME-26AUG05PHXATL`` -> ``26AUG05PHXATL``."""
    parts = (event_ticker or "").split("-", 1)
    return parts[1] if len(parts) == 2 and parts[1] else None
