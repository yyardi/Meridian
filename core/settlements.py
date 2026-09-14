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
import time

import structlog

log = structlog.get_logger(__name__)

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
    """A missing cache is an empty cache. A CORRUPT one is quarantined first.

    Absent and unparseable were the same case here, and returning `{}` for both
    was silent PERMANENT LOSS rather than tolerance: five programs call `save()`
    at the end of a run -- `cfb/run_scan.py`, `run_scan_live.py`,
    `run_extreme_hold.py`, `run_tt_frame_gate.py` -- so a truncated file was read
    as empty, the run re-fetched only what it needed, and then overwrote the
    file. A 911 KB cache of ~20,000 settlements becomes a few hundred, and
    nothing says so; the next run pays thousands of venue calls it had already
    paid for.

    So a file that EXISTS and does not parse is renamed aside before `{}` is
    returned. The run proceeds on a cold cache (correct -- it re-asks the venue,
    and `label` means nothing can be frozen as never-settled), `save()` writes a
    fresh file, and the bad one is kept for inspection instead of being
    overwritten. That is what quarantining it by hand looked like on 2026-09-14;
    doing it here means nobody has to be watching.
    """
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as exc:
        try:
            bad = f"{path}.corrupt-{int(time.time())}"
            os.replace(path, bad)
            log.error("settlement_cache_corrupt", path=str(path), moved_to=bad,
                      error=str(exc)[:200], note="cache rebuilt from the venue; "
                      "the unreadable file was kept, not overwritten")
        except OSError:
            log.error("settlement_cache_corrupt_and_unmovable", path=str(path),
                      error=str(exc)[:200])
        return {}
    if not isinstance(raw, dict):
        return {}
    return {k: label(v) for k, v in raw.items() if label(v) is not None}


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
