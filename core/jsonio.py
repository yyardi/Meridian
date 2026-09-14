"""One guarded JSON writer, because three modules learned this separately today.

2026-09-14, in one morning, three artifact writers died on `json.dump`:

    05:28Z  cfb/run_scan.py        numpy int64   truncated CELLS_JSON, 225 bytes
    09:52Z  cfb/run_scan_live.py   inherited by copy from the same file
    10:16Z  cfb/run_paper_book.py  datetime      exit 1, no paper book for the day

The scan was fixed in place and the paper book was not, which is the recurring
shape in this codebase: an argument gets carried down into one module and not
its neighbour. So the guard lives here now and the callers import it.

Two properties, and they are separate:

`_plain` converts the types that turn up in analysis output -- numpy and scipy
scalars, and datetimes -- and raises on anything else. It is deliberately NOT a
`default=str`. A silent stringify would have written the datetime as a quoted
string and the paper book would have "worked", producing a document whose
`generated_at` and row timestamps had different types than the reader expects.
A writer that cannot serialise something should say so.

`write_json` writes to a temp file in the destination directory and renames, so
a reader never observes a half-written artifact and a crash leaves the previous
one intact. The scan's truncated CELLS_JSON had a plausible size and a fresh
mtime, which is worse than no file: `core/settlements.py` read exactly that
shape as an empty cache and would have overwritten 20,000 settlements with a
few hundred. The temp file is removed on failure rather than left beside the
real one, because a stray `.tmp` with a fresh mtime is the same trap again.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from typing import Any


def _plain(o: Any) -> Any:
    if isinstance(o, (dt.datetime, dt.date, dt.time)):
        return o.isoformat()
    if hasattr(o, "item"):                      # numpy / scipy scalars
        return o.item()
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


def write_json(path: str, payload: Any, *, separators=None) -> str:
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, default=_plain, separators=separators)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path
