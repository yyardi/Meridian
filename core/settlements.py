"""Venue settlement cache: slug -> 0 | 0.5 | 1. Only real settlements are
stored; an unsettled market or a failed request is None and is asked again next
run, so nothing can be frozen as "never settled". Lives under the reads dir the
api mounts (docker-compose.yml) so the file survives rebuilds; SETTLE_CACHE
moves it.

**0.5 IS A REAL SETTLEMENT, not a missing one.** First-class cricket (the
venue's `county`) can be drawn, and the venue settles a draw at a half. Every
consumer that wrote `v in (0, 1)` would have discarded those rows as
unsettled -- silently, and forever, since an unsettled market is re-asked but
never stored. One rule, here, so there is one place that decides."""
import json
import os
import tempfile

PATH = os.environ.get("SETTLE_CACHE", "/opt/meridian/artifacts/reads/settlements.json")
#: The three the venue can return. A draw is 0.5; anything else is not a label.
LABELS = (0, 0.5, 1)


def label(v):
    """`v` as a stored settlement, or None. The ONLY definition of "settled".

    Accepts the venue's strings as well as its numbers ("0.5", "1"). Rejects
    bools explicitly: `True == 1` in Python, and a client returning a boolean
    has told us something different from a settlement of 1.
    """
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f in (0.0, 1.0):
        return int(f)
    return 0.5 if f == 0.5 else None


def load(path=PATH):
    """A missing, unreadable or malformed file is an empty cache, never an error."""
    try:
        raw = json.load(open(path, encoding="utf-8"))
        return {k: label(v) for k, v in raw.items() if label(v) is not None}
    except Exception:
        return {}


def save(cache, path=PATH):
    """Atomic write: a crash mid-run leaves the old file, not half of a new one."""
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump({k: label(v) for k, v in cache.items() if label(v) is not None},
                  fh, sort_keys=True, separators=(",", ":"))
    os.replace(tmp, path)


def settler(client, cache):
    """settlement(slug) -> 0|0.5|1|None over the venue, memoised for this run."""
    miss = set()
    def settlement(slug):
        if slug in cache: return cache[slug]
        if slug in miss: return None
        try:
            v = label(client.get_settlement(slug).get("settlement"))
        except Exception:
            v = None
        (miss.add(slug) if v is None else cache.__setitem__(slug, v))
        return v
    return settlement
