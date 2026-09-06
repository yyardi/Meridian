#!/usr/bin/env python
"""Three checks over every `docker-compose*.yml`, none of which fail loudly on their own.

    python scripts/audit_compose_names.py            # report
    python scripts/audit_compose_names.py --running  # also compare against `docker ps`

Written after the CFB venue tape died silently on 2026-09-05: two files each
declared a service `cfb-live-recorder` with container_name
`meridian-cfb-live-recorder`, one running the ESPN feed and one the venue
recorder. Bringing up one destroyed the other and nothing errored.

Derived independently by builder-d5 and Debugger, same answer; the third check
is Debugger's.

WHY EACH CHECK EXISTS — each catches a failure that produces no error:

1. DUPLICATE container_name. Two definitions competing for one Docker name.
   Whichever is created last wins and silently replaces the other's container.

2. DUPLICATE SERVICE KEY. Subtler and worth its own check: when both files are
   passed to one `-f` invocation, Compose MERGES same-named services field by
   field rather than erroring, so the second definition's `command` can override
   the first's while the name looks untouched.

   NOTE, and this is a genuine ambiguity rather than a hedge: with only one of
   the two files in the invocation there is no merge — Docker simply replaces
   the container of that name. Both routes end with a dead recorder and both are
   fixed by renaming. Which one actually happened on 09-05 is not recoverable
   without shell history, so this file does not claim one.

3. DEFINED BUT NOT RUNNING (--running). A feed that is defined and absent looks
   exactly like a feed that is defined and healthy, unless something compares
   the two lists. This is the check that catches the NEXT silent death rather
   than explaining the last one.
"""
from __future__ import annotations

import argparse
import collections
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SERVICE = re.compile(r"^  ([a-z0-9][a-z0-9._-]*):\s*$")
CNAME = re.compile(r"^\s+container_name:\s*(\S+)\s*$")
ONEOFF = re.compile(r'restart:\s*["\']?no["\']?')


def scan() -> tuple[dict, dict, dict]:
    """(container_name -> [where]), (service key -> [where]), (cname -> one-off?)"""
    cnames, services, oneoff = (collections.defaultdict(list),
                                collections.defaultdict(list), {})
    for path in sorted(ROOT.glob("docker-compose*.yml")):
        current, body = None, []
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if m := SERVICE.match(line):
                if current:
                    oneoff[current] = any(ONEOFF.search(b) for b in body)
                current, body = m.group(1), []
                services[current].append(f"{path.name}:{n}")
            elif current:
                body.append(line)
                if c := CNAME.match(line):
                    cnames[c.group(1)].append(f"{path.name}:{n}")
        if current:
            oneoff[current] = any(ONEOFF.search(b) for b in body)
    return cnames, services, oneoff


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--running", action="store_true",
                    help="also compare definitions against `docker ps`")
    args = ap.parse_args()
    cnames, services, oneoff = scan()
    bad = 0

    print(f"{len(cnames)} distinct container_names over "
          f"{sum(len(v) for v in cnames.values())} definitions\n")

    for label, table in (("container_name", cnames), ("service key", services)):
        dupes = {k: v for k, v in table.items() if len(v) > 1}
        if dupes:
            bad += 1
            print(f"!! DUPLICATE {label}:")
            for k, where in sorted(dupes.items()):
                print(f"     {k}  <-  {', '.join(where)}")
        else:
            print(f"ok  no duplicate {label}")

    if args.running:
        try:
            out = subprocess.run(["docker", "ps", "--format", "{{.Names}}"],
                                 capture_output=True, text=True, timeout=20).stdout
        except Exception as exc:                                   # noqa: BLE001
            print(f"\n?? could not read `docker ps`: {exc}")
            return 1 if bad else 0
        live = {n for n in out.split() if n}
        # One-off runners are SUPPOSED to be absent; excluding them keeps the
        # check quiet enough that a real absence is visible.
        missing = sorted(c for c, w in cnames.items()
                         if c not in live
                         and not oneoff.get(w[0].split(":")[0].replace(".yml", ""), False))
        undefined = sorted(n for n in live
                           if n.startswith("meridian-") and n not in cnames)
        print()
        print(f"!! DEFINED BUT NOT RUNNING: {missing}" if missing
              else "ok  every defined service is running")
        print(f"!! RUNNING BUT NOT DEFINED: {undefined}" if undefined
              else "ok  nothing running is undefined")
        bad += bool(missing) + bool(undefined)

    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
