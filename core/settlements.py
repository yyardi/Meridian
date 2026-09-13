"""Venue settlement cache: slug -> 0|1. Only real settlements are stored; an
unsettled market or a failed request is None and is asked again next run, so
nothing can be frozen as "never settled". Lives under the reads dir the api
mounts (docker-compose.yml) so the file survives rebuilds; SETTLE_CACHE moves it."""
import json
import os
import tempfile

PATH = os.environ.get("SETTLE_CACHE", "/opt/meridian/artifacts/reads/settlements.json")


def load(path=PATH):
    """A missing, unreadable or malformed file is an empty cache, never an error."""
    try:
        return {k: int(v) for k, v in json.load(open(path, encoding="utf-8")).items() if v in (0, 1)}
    except Exception:
        return {}


def save(cache, path=PATH):
    """Atomic write: a crash mid-run leaves the old file, not half of a new one."""
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump({k: v for k, v in cache.items() if v in (0, 1)}, fh, sort_keys=True, separators=(",", ":"))
    os.replace(tmp, path)


def settler(client, cache):
    """settlement(slug) -> 0|1|None over the venue, memoised for this run; only 0/1 enter `cache`."""
    miss = set()
    def settlement(slug):
        if slug in cache: return cache[slug]
        if slug in miss: return None
        try:
            s = client.get_settlement(slug).get("settlement"); v = int(s) if s in (0, 1, "0", "1") else None
        except Exception:
            v = None
        (miss.add(slug) if v is None else cache.__setitem__(slug, v))
        return v
    return settlement
