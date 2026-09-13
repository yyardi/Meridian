"""The settlement cache. A settled market is 0/1 forever; anything else must re-ask."""
from __future__ import annotations

import json

import pytest

from cfb.run_paper_book import cache_put, load_settle_cache, save_settle_cache


def test_a_round_trip_keeps_the_labels(tmp_path):
    p = tmp_path / "s.json"
    save_settle_cache({"a": 1, "b": 0}, p)
    assert load_settle_cache(p) == {"a": 1, "b": 0}


@pytest.mark.parametrize("bad", [None, "", "pending", -1, 2, 0.5, True, [1]])
def test_only_zero_and_one_are_ever_stored(bad):
    """The one error nobody would see: caching None freezes a market as
    permanently unsettled, so the book skips it on every future run and the
    `unsettled` count looks stable instead of falling."""
    c = {}
    stored = cache_put(c, "slug", bad)
    if bad is True:          # bool is an int subclass; 1 is a legitimate label
        assert stored and c == {"slug": 1}
    else:
        assert not stored and c == {}


def test_a_none_left_out_is_re_asked_not_remembered(tmp_path):
    p = tmp_path / "s.json"
    c = {}
    cache_put(c, "settled", 1)
    cache_put(c, "pending", None)
    save_settle_cache(c, p)
    back = load_settle_cache(p)
    assert "settled" in back and "pending" not in back


@pytest.mark.parametrize("content", ["", "not json", "[]", '"x"', '{"a": null}',
                                     '{"a": "pending"}', '{"a": 7}'])
def test_a_corrupt_cache_costs_a_slow_run_not_a_failed_one(tmp_path, content):
    p = tmp_path / "s.json"
    p.write_text(content, encoding="utf-8")
    assert load_settle_cache(p) == {}


def test_a_missing_file_is_an_empty_cache(tmp_path):
    assert load_settle_cache(tmp_path / "nope" / "s.json") == {}


def test_it_creates_its_directory(tmp_path):
    p = tmp_path / "made" / "up" / "s.json"
    save_settle_cache({"a": 1}, p)
    assert load_settle_cache(p) == {"a": 1}


def test_the_write_is_atomic_and_leaves_no_debris(tmp_path):
    p = tmp_path / "s.json"
    save_settle_cache({"a": 1}, p)
    save_settle_cache({"a": 1, "b": 0}, p)
    assert load_settle_cache(p) == {"a": 1, "b": 0}
    assert [f.name for f in tmp_path.iterdir()] == ["s.json"]


def test_a_stored_label_is_never_silently_rewritten(tmp_path):
    """Settlement is final. If the venue ever disagrees with the cache that is a
    finding, not something to paper over -- so the cache is keyed by slug and a
    hit short-circuits before any request."""
    p = tmp_path / "s.json"
    save_settle_cache({"a": 1}, p)
    c = load_settle_cache(p)
    assert c["a"] == 1
    cache_put(c, "a", 0)          # a caller CAN overwrite; nothing in main does
    assert c["a"] == 0


def test_the_file_is_plain_json_an_operator_can_read(tmp_path):
    p = tmp_path / "s.json"
    save_settle_cache({"z": 1, "a": 0}, p)
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert raw == {"a": 0, "z": 1}
    assert list(raw) == ["a", "z"], "sorted, so diffs between runs are readable"
