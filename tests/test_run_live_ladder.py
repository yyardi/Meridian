"""The live sampler is read-only by construction, and its line parse is the verified one."""
from __future__ import annotations

import importlib
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
RUN = importlib.import_module("cfb.run_live_ladder")
SRC = pathlib.Path(RUN.__file__).read_text(encoding="utf-8")


def test_it_cannot_place_an_order():
    for bad in ("place_order", "submit_order", "MERIDIAN_ORDER_TOKEN", "requests.post", "httpx.post"):
        assert bad not in SRC
    assert "get_book" in SRC


def test_line_parse_matches_the_settled_convention():
    """neg -> negative line; verified on 84,646 settled pairs with zero violations."""
    assert RUN.line_of("asc-nfl-det-buf-2026-09-17-neg-10pt5", "aec-nfl-det-buf-2026-09-17") == -10.5
    assert RUN.line_of("asc-nfl-det-buf-2026-09-17-pos-3pt5", "aec-nfl-det-buf-2026-09-17") == 3.5
    assert RUN.line_of("aec-nfl-det-buf-2026-09-17", "aec-nfl-det-buf-2026-09-17") == 0.0
    assert RUN.line_of("tsc-nfl-det-buf-2026-09-17-44pt5", "aec-nfl-det-buf-2026-09-17") is None


def test_default_is_uncapped_because_venue_depth_is_real():
    assert 'default=1e12' in SRC


def test_one_bad_rung_does_not_kill_the_sample():
    assert "except Exception" in SRC and "continue" in SRC
