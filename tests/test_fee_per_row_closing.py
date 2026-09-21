"""The closing-price family charges each row at the coefficient the venue carried on it.

    pytest tests/test_fee_per_row_closing.py      (the SELECT tests need the suite's DB)

Polymarket US raised its taker coefficient at 2026-09-17 04:07Z. The recorder
stores the venue's value on every row (market_snapshots.fee_coefficient: 0.06 on
63.5M rows to 04:00Z that day, 0.0695 on every row since, no NULLs), and each
runner here reads a window that spans that instant -- the paper book 60 days,
the decomposition 90, the shadow replay any DATE, the two scans the whole tape
-- so one constant across the window overcharged every pre-change row by 16 %.

Each runner now selects fee_coefficient beside the book and passes the row's
value to the fee; a row without one is refused, never charged at today's. Every
expectation below is an expression in the row's coefficient, never pinned
cents, so the venue's next move cannot break a test that is right.

Five runners, three shapes of test each: two rows in ONE run charged at their
own coefficients, a row without one refused, and the SELECT executed against
postgres with the column in its result. The two scans run at import, so they
are exec'd whole against synthetic closes with the database and the venue
stubbed and core.fees left real -- the harness cfb/test_scan_endtoend.py was
meant to do, and cannot since it replaces `core` itself.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import pathlib
import sys
import types

import pytest

from core import fees

ROOT = pathlib.Path(__file__).resolve().parents[1]
CFB = ROOT / "cfb"

#: The venue's coefficient before and after it raised the fee at 2026-09-17
#: 04:07Z. Spelled here and not imported: they are HISTORY, and core/fees.py
#: holds only the current one.
PRE, POST = 0.06, 0.0695


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


book = _load("paper_book_fee_rows", CFB / "run_paper_book.py")
decomp = _load("longshot_decomp_fee_rows", CFB / "run_longshot_decomp.py")
shadow = _load("longshot_shadow_fee_rows", CFB / "run_longshot_shadow.py")


# ------------------------------------------------------------------ the paper book
def _close(coef, game="g", bid=0.49, ask=0.50):
    return {"bid": bid, "ask": ask, "game_id": game, "fee_coefficient": coef}


def test_paper_book_charges_two_closes_in_one_run_at_their_own_coefficients():
    """A 60-day read taken on 2026-09-21 holds closes from both sides of 09-17."""
    pre, post = book.bet_row("yes", 1, _close(PRE, "g1")), book.bet_row("yes", 1, _close(POST, "g2"))
    assert pre[0] == pytest.approx(1 - 0.50 - PRE * 0.50 * 0.50)
    assert post[0] == pytest.approx(1 - 0.50 - POST * 0.50 * 0.50)
    assert pre[0] - post[0] == pytest.approx((POST - PRE) * 0.50 * 0.50)     # the old fee was cheaper
    assert pre[1:] == (0.50, "g1") and post[1:] == (0.50, "g2")
    # the NO side reads the SAME row's coefficient, on the bid
    pre_no, post_no = book.bet_row("no", 0, _close(PRE)), book.bet_row("no", 0, _close(POST))
    assert pre_no[0] == pytest.approx(1 - (1 - 0.49) - PRE * 0.49 * 0.51)
    assert pre_no[0] - post_no[0] == pytest.approx((POST - PRE) * 0.49 * 0.51)


def test_paper_book_refuses_a_close_without_a_coefficient():
    """NULL from the venue is an error, not today's fee; a SELECT that lost the column is too."""
    with pytest.raises(ValueError):
        book.bet_row("yes", 1, _close(None))
    with pytest.raises(KeyError):
        book.bet_row("yes", 1, {"bid": 0.49, "ask": 0.50, "game_id": "g"})
    with pytest.raises(ValueError):
        book.bet_pnl("no", 0, 0.49, 0.50, fee=None)


def test_paper_book_has_no_default_fee_and_no_constant():
    """bet_pnl takes the fee it charges; a call without one is a TypeError, not
    today's coefficient. The permutation null passes each row's (run_scan_null)."""
    with pytest.raises(TypeError):
        book.bet_pnl("yes", 1, 0.49, 0.50)
    assert not hasattr(book, "FEE")
    assert book.bet_pnl("yes", 1, 0.49, 0.50, PRE) != book.bet_pnl("yes", 1, 0.49, 0.50, POST)


# ------------------------------------------------------------------ the decomposition
def _rung(coef, slug, game="g", bid=0.25, ask=0.27):
    return {"market_slug": slug, "game_id": game, "bid": bid, "ask": ask, "fee_coefficient": coef}


def test_decomp_charges_two_rungs_in_one_run_at_their_own_coefficients():
    rows = [_rung(PRE, "pre", "g1"), _rung(POST, "post", "g2")]
    bets, uns = decomp.bets_for(rows, "no", lambda slug: 0)         # both settle NO: the longshot lost
    assert uns == 0 and [b[2] for b in bets] == ["g1", "g2"]
    assert bets[0][0] == pytest.approx(1 - (1 - 0.25) - PRE * 0.25 * 0.75)
    assert bets[1][0] == pytest.approx(1 - (1 - 0.25) - POST * 0.25 * 0.75)
    assert bets[0][0] - bets[1][0] == pytest.approx((POST - PRE) * 0.25 * 0.75)


def test_decomp_refuses_a_rung_without_a_coefficient():
    with pytest.raises(ValueError):
        decomp.bets_for([_rung(None, "s")], "no", lambda slug: 0)
    with pytest.raises(KeyError):
        decomp.bets_for([{"market_slug": "s", "game_id": "g", "bid": 0.25, "ask": 0.27}], "no", lambda slug: 0)
    with pytest.raises(TypeError):                                    # no today's-value default to fall back on
        decomp.bet_pnl("no", 0, 0.25, 0.27)


# ------------------------------------------------------------------ the shadow replay
def test_shadow_replay_charges_two_rungs_in_one_run_at_their_own_coefficients():
    pre = shadow.rung_pnl_c({"bid": 0.25, "ask": 0.27, "fee_coefficient": PRE}, 0)
    post = shadow.rung_pnl_c({"bid": 0.25, "ask": 0.27, "fee_coefficient": POST}, 0)
    assert pre == pytest.approx(100 * (0.25 - PRE * 0.25 * 0.75))
    assert post == pytest.approx(100 * (0.25 - POST * 0.25 * 0.75))
    assert pre - post == pytest.approx(100 * (POST - PRE) * 0.25 * 0.75)


def test_shadow_refuses_a_rung_without_a_coefficient():
    with pytest.raises(ValueError):
        shadow.rung_pnl_c({"bid": 0.25, "fee_coefficient": None}, 0)
    with pytest.raises(KeyError):
        shadow.rung_pnl_c({"bid": 0.25}, 0)
    with pytest.raises(TypeError):
        shadow.buy_no_pnl_c(0.25, 0)
    assert not hasattr(shadow, "FEE"), "the lister carries no fee constant; every fee is the row's"

def _bootstraps_then_imports(src: str) -> bool:
    """Run bare (the trainer image mounts cfb/ alone) the script puts the repo
    root on sys.path itself and then imports core.fees -- one function, never
    a copy of it and never a constant. The guarded-import-with-fallback shape
    it replaces is refused by name."""
    import ast
    boot = src.find("sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))")
    imp = src.find("from core.fees import")
    guarded = [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Try)
               and any(isinstance(m, ast.ImportFrom) and m.module == "core.fees" for m in ast.walk(n))]
    # nightly_scan.sh pipes run_scan.py over stdin (`python - < cfb/run_scan.py`),
    # where __file__ does not exist: the bootstrap must not touch it there.
    piped_safe = '"__file__" in globals()' in src[boot:imp]
    return 0 <= boot < imp and not guarded and piped_safe


@pytest.mark.parametrize("path", ["run_longshot_decomp.py", "run_longshot_shadow.py", "run_paper_book.py",
                                  "run_scan.py", "run_scan_live.py"])
def test_run_bare_the_script_bootstraps_the_repo_root_and_imports_one_recorded_fee(path):
    """Both scripts also run where core/ is not on sys.path (the trainer image mounts
    cfb/ only). They no longer carry a fallback copy of recorded_fee: they put the
    repo root on sys.path and import the one in core/fees.py, so there is exactly
    one function to be right or wrong."""
    src = (CFB / path).read_text()
    assert "from core.fees import" in src, path
    assert _bootstraps_then_imports(src), path


# ------------------------------------------------------------------ the SELECTs (needs the suite's DB)
_NOW = dt.datetime(2026, 9, 21, tzinfo=dt.timezone.utc)


def _scan_close(path):
    """The scan's CLOSE, built exactly as the script builds it, with no floor."""
    src = (CFB / path).read_text()
    ns = {"SINCE": None}
    exec(src[src.index('_FLOOR = "'):src.index("def partition_floors")], ns)   # noqa: S102 - the shipped source
    return ns["CLOSE"]


@pytest.mark.parametrize("label, sql, params", [
    ("paper book", book.CLOSE_SQL, {"pats": ["%-cfb-%"], "since": _NOW}),
    ("decomposition", decomp.CLOSE_SQL, {"pat": "%-cfb-%", "since": _NOW}),
    ("shadow replay", shadow.SNAPS_SQL, {"gids": ["g"], "t": shadow.SPREAD, "lo": _NOW, "hi": _NOW}),
    ("pregame scan", _scan_close("run_scan.py"), {"pats": ["%-cfb-%"]}),
    ("in-game scan", _scan_close("run_scan_live.py"), {"pats": ["%-cfb-%"], "smin": 10, "liveh": 4.5}),
])
def test_every_select_carries_fee_coefficient_beside_the_book(label, sql, params):
    """Executed against postgres, not grepped: the column must come back WITH the
    prices. Zero rows is fine -- keys() is the SELECT list, and the test database
    is empty."""
    from sqlalchemy import text
    from core.storage import get_engine
    with get_engine().connect() as c:
        keys = set(c.execute(text(sql), params).keys())
    assert {"bid", "ask", "fee_coefficient"} <= keys, (label, sorted(keys))


# ------------------------------------------------------------------ the two scans, run whole
def _stub_venue_and_db(monkeypatch, rows):
    """The scans build an engine and run at import; give them synthetic closes and no
    venue. Only the database and venue modules are replaced -- core.fees stays real,
    which is the point."""
    import core

    class _Res(list):
        def all(self): return list(self)
        def fetchall(self): return list(self)

    class _Row:
        def __init__(self, d): self._mapping = d

    class _Conn:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, q, *a, **k):
            if "first_play" in q:                                    # START_LAG: no observed play here
                return _Res([])
            return _Res([_Row({k2: v for k2, v in r.items() if k2 != "y"}) for r in rows])

    sa = types.ModuleType("sqlalchemy")
    sa.create_engine = lambda *a, **k: types.SimpleNamespace(connect=lambda: _Conn())
    sa.text = lambda q: q
    sa.event = types.SimpleNamespace(listens_for=lambda *a, **k: (lambda f: f))
    monkeypatch.setitem(sys.modules, "sqlalchemy", sa)

    st = types.ModuleType("core.settlements")
    ymap = {r["slug"]: r["y"] for r in rows}
    st.load = lambda *a, **k: {}
    st.save = lambda *a, **k: None
    st.settler = lambda client, cache: (lambda slug: ymap.get(slug))
    monkeypatch.setitem(sys.modules, "core.settlements", st)
    monkeypatch.setattr(core, "settlements", st, raising=False)     # `from core import X` reads the attribute first

    pc = types.ModuleType("core.polymarket.client")
    pc.PolymarketGatewayClient = lambda *a, **k: object()
    monkeypatch.setitem(sys.modules, "core.polymarket.client", pc)

    lg = types.ModuleType("core.leagues")
    lg.LEAGUES = {"cfb": object()}
    lg.venue_patterns = lambda s: ("%-cfb-%",)
    monkeypatch.setitem(sys.modules, "core.leagues", lg)


def _run_scan(path, rows, tmp_path, monkeypatch):
    _stub_venue_and_db(monkeypatch, rows)
    cells, rj = tmp_path / "cells.json", tmp_path / "rows.json"
    monkeypatch.setenv("DATABASE_URL", "stub://")
    monkeypatch.setenv("CELLS_JSON", str(cells))
    monkeypatch.setenv("ROWS_JSON", str(rj))
    for v in ("SCAN_SINCE", "SCAN_EXPECT", "MAXCALLS"):
        monkeypatch.delenv(v, raising=False)
    src = CFB / path
    exec(compile(src.read_text(), str(src), "exec"),                 # noqa: S102 - the shipped source
         {"__name__": f"scan_under_test_{path[:-3]}", "__file__": str(src)})
    return json.loads(cells.read_text()), json.loads(rj.read_text())


def _closes(coef_a, coef_b, n=12):
    """Two cells with IDENTICAL prices and settlements and different coefficients: the
    only thing that can separate their means is the fee. Twelve games each clears the G
    floor of 6 and mixes outcomes, so both reach the sandwich and the Poisson-binomial."""
    rows = []
    for i in range(n):
        rows.append(dict(slug=f"asc-cfb-a{i}-b{i}-2026-09-01-pos-3pt5", mt="football_team_full_game_spread",
                         gid=f"g{i}", bid=0.54, ask=0.56, fee_coefficient=coef_a, y=i % 2))
        rows.append(dict(slug=f"asc-cfb-c{i}-d{i}-2026-09-01-pos-3pt5", mt="football_team_full_game_total",
                         gid=f"t{i}", bid=0.54, ask=0.56, fee_coefficient=coef_b, y=i % 2))
    return rows


@pytest.mark.parametrize("path", ["run_scan.py", "run_scan_live.py"])
def test_the_scan_charges_two_cells_in_one_run_at_their_own_coefficients(path, tmp_path, monkeypatch):
    cells, rows = _run_scan(path, _closes(PRE, POST), tmp_path, monkeypatch)
    by_mt = {c["mt"]: c["mean_cents"] for c in cells["cells"]}
    assert set(by_mt) == {"football_team_full_game_spread", "football_team_full_game_total"}
    # same prices, same settlements: the means differ by exactly the fee difference on the ask
    assert by_mt["football_team_full_game_spread"] - by_mt["football_team_full_game_total"] == \
        pytest.approx(100 * (POST - PRE) * 0.56 * 0.44)
    assert by_mt["football_team_full_game_spread"] == pytest.approx(100 * (0.5 - 0.56 - PRE * 0.56 * 0.44))
    # and the inputs the permutation null consumes carry the coefficient each row was charged at
    seen = {(r["mt"], r["fee_coefficient"]) for r in rows}
    assert seen == {("football_team_full_game_spread", PRE), ("football_team_full_game_total", POST)}


@pytest.mark.parametrize("path", ["run_scan.py", "run_scan_live.py"])
def test_the_scan_refuses_a_close_without_a_coefficient(path, tmp_path, monkeypatch):
    """The nightly dies rather than charging today's fee to a row the venue priced differently."""
    with pytest.raises(ValueError):
        _run_scan(path, _closes(PRE, None), tmp_path, monkeypatch)
    rows = _closes(PRE, POST)
    for r in rows:
        r.pop("fee_coefficient")
    with pytest.raises(KeyError):
        _run_scan(path, rows, tmp_path, monkeypatch)
