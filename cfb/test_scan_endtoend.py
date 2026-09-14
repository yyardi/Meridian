"""End-to-end synthetic pass over cfb/run_scan.py. Exits non-zero. Gates the nightly.

WHY THIS EXISTS, BESIDE test_scan_statistic.py. That file extracts
`poisson_binomial_p` by AST and exercises that one function, so it is a correctness
check on the statistic and a LIVENESS CHECK ON NOTHING. The class it cannot catch --
an arity mismatch, a NameError, anything in the surrounding 500 lines -- is exactly
what broke a prod run once (`NameError: binom_rows`, from a half-applied patch that
`ast.parse` accepted) and exactly what a hand-resolved merge conflict in the bet
tuple could reintroduce.

So this runs the WHOLE program against synthetic closes: no database, no venue, no
network. sqlalchemy, core.settlements, core.polymarket.client and core.leagues are
replaced in sys.modules before the source is exec'd, and a deterministic fixture is
fed through the real bucketing, the real degeneracy guard, the real G floor, the real
Poisson-binomial and the real JSON writers.

It asserts the things a defect would break silently rather than loudly:
  * the program runs to completion and writes both JSON artifacts;
  * ROWS_JSON carries the raw INPUTS (bid/ask/y), not our computed pnl, because that
    is the property the permutation null depends on;
  * a planted DEGENERATE cell is excluded from the sandwich and still scored by the
    Poisson-binomial -- the guard and the primary must disagree in that exact way;
  * a planted cell below the G floor does not reach the primary.
"""
import json
import pathlib
import sys
import tempfile
import types

SRC = pathlib.Path(__file__).with_name("run_scan.py")
N_GAMES, FAIL = 40, []


def _fixture():
    """(slug, mtype, game, bid, ask, y) rows. Deterministic, and each block is a probe."""
    rows = []
    for i in range(N_GAMES):                       # ordinary cell: mixed outcomes, mid ~0.55
        rows.append((f"asc-cfb-a{i}-b{i}-2026-09-01-pos-3pt5", "football_team_full_game_spread",
                     f"g{i}", 0.54, 0.56, i % 2))
    for i in range(N_GAMES):                       # a second scorable cell, mid ~0.25, mixed
        rows.append((f"asc-cfb-p{i}-q{i}-2026-09-01-neg-9pt5", "football_team_full_game_total",
                     f"m{i}", 0.24, 0.26, 1 if i % 4 == 0 else 0))
    for i in range(12):                            # DEGENERATE: every bet settles 1, mid ~0.85
        rows.append((f"asc-cfb-c{i}-d{i}-2026-09-01-pos-7pt5", "football_team_first_half_spread",
                     f"h{i}", 0.84, 0.86, 1))
    for i in range(3):                             # BELOW the G floor of 6
        rows.append((f"asc-cfb-e{i}-f{i}-2026-09-01-pos-1pt5", "football_team_second_half_spread",
                     f"k{i}", 0.24, 0.26, 0))
    return rows


def _stub_modules(rows):
    sa = types.ModuleType("sqlalchemy")

    class _Res(list):
        def __init__(self, rs): super().__init__(rs)
        def fetchall(self): return list(self)

    class _Row:
        def __init__(self, d): self._mapping = d

    class _Conn:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, *a, **k):
            return _Res([_Row({"slug": s, "mt": m, "gid": g, "bid": b, "ask": k2})
                         for s, m, g, b, k2, _ in rows])
        def close(self): pass

    class _Eng:
        def connect(self): return _Conn()

    sa.create_engine = lambda *a, **k: _Eng()
    sa.text = lambda q: q
    sa.event = types.SimpleNamespace(listens_for=lambda *a, **k: (lambda f: f))
    sys.modules["sqlalchemy"] = sa

    st = types.ModuleType("core.settlements")
    ymap = {s: y for s, _, _, _, _, y in rows}
    st.load = lambda *a, **k: {}
    st.save = lambda *a, **k: None
    st.settler = lambda client, cache: (lambda slug: ymap.get(slug))
    sys.modules["core.settlements"] = st

    pc = types.ModuleType("core.polymarket.client")
    pc.PolymarketGatewayClient = lambda *a, **k: object()
    sys.modules["core.polymarket.client"] = pc

    lg = types.ModuleType("core.leagues")
    lg.LEAGUES = {"cfb": object()}
    lg.venue_patterns = lambda s: ("%-cfb-%",)
    sys.modules["core.leagues"] = lg

    core = types.ModuleType("core")
    core.settlements = st
    sys.modules["core"] = core


def main():
    rows = _fixture()
    _stub_modules(rows)
    tmp = pathlib.Path(tempfile.mkdtemp())
    import os
    os.environ.update(DATABASE_URL="stub://", CELLS_JSON=str(tmp / "c.json"),
                      ROWS_JSON=str(tmp / "r.json"))
    os.environ.pop("SCAN_SINCE", None)
    ns = {"__name__": "__main__", "__file__": str(SRC)}
    try:
        exec(compile(SRC.read_text(), str(SRC), "exec"), ns)
    except SystemExit as e:
        if e.code not in (0, None): FAIL.append(f"program exited {e.code}")
    except Exception as e:
        FAIL.append(f"{type(e).__name__}: {e}")

    for f in ("c.json", "r.json"):
        if not (tmp / f).exists(): FAIL.append(f"{f} not written")
    if not FAIL:
        cells = json.loads((tmp / "c.json").read_text())
        rws = json.loads((tmp / "r.json").read_text())
        if rws:
            k = set(rws[0])
            if not {"bid", "ask", "y"} <= k:
                FAIL.append(f"ROWS_JSON missing raw inputs, has {sorted(k)}")
            if any(x in k for x in ("pnl", "net")):
                FAIL.append("ROWS_JSON carries computed pnl; the null must recompute")
        why = " ".join(str(e.get("why", "")) for e in cells.get("excluded", []))
        if "no outcome variation" not in why and "DEGENERATE" not in why:
            FAIL.append("planted degenerate cell was NOT excluded from the sandwich")
        print(f"  cells scored {cells.get('m_eff')}   excluded {len(cells.get('excluded', []))}"
              f"   rows {len(rws)}")
    print("\n" + ("END-TO-END OK -- the whole program runs, both artifacts written, "
                  "ROWS_JSON holds inputs" if not FAIL else
                  "*** FAILURE ***\n  " + "\n  ".join(FAIL)))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
