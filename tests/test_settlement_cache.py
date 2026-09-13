"""core.settlements: only 0/1 is stored, None is re-asked, the file is atomic and plain JSON."""
import json

from core import settlements


class _Venue:
    def __init__(self, answers): self.answers, self.calls = answers, 0
    def get_settlement(self, slug):
        self.calls += 1
        a = self.answers[slug]
        if isinstance(a, Exception): raise a
        return {"slug": slug, "settlement": a}


def test_round_trip_keeps_only_real_labels(tmp_path):
    f = tmp_path / "s.json"
    settlements.save({"a": 1, "b": 0, "c": None, "d": "1", "e": 0.5, "f": True}, f)
    assert settlements.load(f) == {"a": 1, "b": 0, "d": 1, "e": 0.5}   # strings are the venue's; bools are not labels
    assert json.loads(f.read_text()) == {"a": 1, "b": 0, "d": 1, "e": 0.5}


def test_missing_or_corrupt_file_is_an_empty_cache(tmp_path):
    assert settlements.load(tmp_path / "none.json") == {}
    (tmp_path / "bad.json").write_text("{not json")
    assert settlements.load(tmp_path / "bad.json") == {}
    (tmp_path / "list.json").write_text("[1,2]")
    assert settlements.load(tmp_path / "list.json") == {}


def test_save_creates_the_directory_and_leaves_no_debris(tmp_path):
    f = tmp_path / "deep" / "s.json"
    settlements.save({"a": 1}, f)
    assert [p.name for p in f.parent.iterdir()] == ["s.json"]


def test_settler_caches_labels_and_re_asks_none_next_run():
    venue = _Venue({"a": 1, "b": "0", "c": None, "d": RuntimeError("down")})
    cache = {}
    s = settlements.settler(venue, cache)
    assert [s(k) for k in "abcd"] == [1, 0, None, None]
    assert [s(k) for k in "abcd"] == [1, 0, None, None]   # memoised within the run
    assert venue.calls == 4 and cache == {"a": 1, "b": 0}  # c, d never enter the file
    s2 = settlements.settler(venue, cache)
    assert s2("a") == 1 and venue.calls == 4              # a served from cache
    assert s2("c") is None and venue.calls == 5           # c asked again next run
