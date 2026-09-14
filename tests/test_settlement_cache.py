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


# --------------------------------------------------------------------------- #
# A corrupt cache must not be silently overwritten by the next run.
# --------------------------------------------------------------------------- #
def test_a_corrupt_cache_is_quarantined_not_overwritten(tmp_path):
    """★ ABSENT AND UNPARSEABLE WERE THE SAME CASE, AND THAT WAS PERMANENT LOSS.
    `load()` returned {} for both, and five programs call `save()` at the end of
    a run -- run_scan, run_scan_live, run_extreme_hold, run_tt_frame_gate. So a
    truncated file was read as empty, the run re-fetched only what it needed,
    and then wrote over it: a 911 KB cache of ~20,000 settlements becomes a few
    hundred, silently, and the next run pays thousands of venue calls again.

    Now a file that exists and does not parse is renamed aside first, so the run
    proceeds cold (correct -- it re-asks the venue) and the bad file survives for
    inspection."""
    from core import settlements as S

    p = tmp_path / "settlements.json"
    p.write_text('{"a-slug": 1, "b-slug": 0, "trunca', encoding="utf-8")  # truncated
    assert S.load(p) == {}
    assert not p.exists(), "the corrupt file is still in place and will be overwritten"
    quarantined = list(tmp_path.glob("settlements.json.corrupt-*"))
    assert len(quarantined) == 1, [q.name for q in tmp_path.iterdir()]
    assert quarantined[0].read_text().endswith("trunca"), "the bad bytes were not kept"

    # and the run's own save now writes a FRESH file beside the quarantined one
    S.save({"c-slug": 1}, p)
    assert json.loads(p.read_text()) == {"c-slug": 1}
    assert len(list(tmp_path.glob("settlements.json.corrupt-*"))) == 1


def test_an_absent_cache_is_still_just_an_empty_cache(tmp_path):
    """The control. A first run has no file and that is not an error.

    ★ THE FIRST VERSION OF THIS COULD NOT FAIL. It asserted only `load() == {}`
    and that no file appeared — both still true if the FileNotFoundError branch
    is removed, because a missing path then reaches the corrupt handler, whose
    `os.replace` raises OSError, which is caught and also returns {} with no
    file created. A mutation removing that branch passed. The distinguishing
    observable is the LOG: a cold start must be silent."""
    from structlog.testing import capture_logs

    from core import settlements as S

    p = tmp_path / "nope.json"
    with capture_logs() as logs:
        assert S.load(p) == {}
    assert not list(tmp_path.iterdir()), "a missing file produced a quarantine artifact"
    assert not [e for e in logs if "corrupt" in e["event"]], (
        f"a cold start logged a corruption error: {[e['event'] for e in logs]}")

    # and the contrast, so this test cannot pass by logging nothing ever
    bad = tmp_path / "bad.json"
    bad.write_text('{"a": 1, "trunc', encoding="utf-8")
    with capture_logs() as logs:
        S.load(bad)
    assert [e["event"] for e in logs] == ["settlement_cache_corrupt"]


def test_a_json_scalar_is_not_a_cache(tmp_path):
    """`json.load` succeeds on `"[]"` and on `"3"`, and the old code then called
    `.items()` on it and raised inside the bare `except`, which looked identical
    to corruption. Parsing is not the same as being a mapping."""
    from core import settlements as S

    for text in ("[]", "3", '"a string"', "null"):
        p = tmp_path / "s.json"
        p.write_text(text, encoding="utf-8")
        assert S.load(p) == {}, text
