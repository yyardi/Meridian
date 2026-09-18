#!/usr/bin/env python3
"""Exit 0 if a push of KIND may reach the phone, 1 if it is muted.

    if python3 scripts/ntfy_allowed.py nightly; then curl ...; else <log it>; fi

The cron scripts (nightly_scan.sh and friends) run on the host with the
system python3 and read `.env` themselves -- they are not inside a container
that was handed the environment. So this reads MERIDIAN_NTFY_SCOPE from the
process environment first and, when unset, from the `MERIDIAN_NTFY_SCOPE=`
line of the repo-root `.env`. It never reads or prints the topic.

Same rule as `core.notify.allowed`: default scope is "tickets", "all" means
everything. Exit 2 on a bad argument, so a typo cannot pass as "allowed".
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.notify import KINDS, parse_scope


def scope_from_env_file(path: Path) -> str | None:
    """The value of the LAST `MERIDIAN_NTFY_SCOPE=` line, or None. Only that
    line is looked at; the rest of the file holds secrets and is not parsed."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    value = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if line.startswith("MERIDIAN_NTFY_SCOPE="):
            value = _unquote(line.split("=", 1)[1])
    return value


def _unquote(raw: str) -> str:
    """The value as compose reads it: a quoted value ends at its closing
    quote; an unquoted one ends at the first ` #` (inline comment). Without
    this, `MERIDIAN_NTFY_SCOPE=all # everything` is "all" in the containers
    and the single unknown kind "all # everything" here -- the host gate
    stays muted on the same file that opened the containers."""
    raw = raw.strip()
    if raw[:1] in ('"', "'"):
        end = raw.find(raw[0], 1)
        return raw[1:end] if end > 0 else raw[1:]
    return re.split(r"\s#", raw, maxsplit=1)[0].rstrip()


def is_allowed(kind: str, env: dict | None = None, env_file: Path | None = None) -> bool:
    env = os.environ if env is None else env
    raw = env.get("MERIDIAN_NTFY_SCOPE")
    if raw is None or not raw.strip():
        raw = scope_from_env_file(env_file if env_file is not None else ROOT / ".env")
    return kind in KINDS and kind in parse_scope(raw)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1 or argv[0] not in KINDS:
        print(f"usage: ntfy_allowed.py <{'|'.join(KINDS)}>", file=sys.stderr)
        return 2
    return 0 if is_allowed(argv[0]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
