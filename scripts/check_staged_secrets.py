#!/usr/bin/env python3
"""Block a commit that would publish infra identifiers or credentials.

    scripts/check_staged_secrets.py            # scan the STAGED diff (hook mode)
    scripts/check_staged_secrets.py --all      # scan every tracked file
    scripts/check_staged_secrets.py --install  # install as .git/hooks/pre-commit

WHY THIS EXISTS AND WHY THE TEST WAS NOT ENOUGH
================================================
`tests/test_no_infra_identifiers.py` already encoded these rules, and on
2026-09-05 the repo still published — to a PUBLIC remote — the AWS account id
in README.md across 811 commits, the security group and VPC ids across 814,
and the production server's IP across 127.

Three distinct failures, and a hook is the answer to all three:

1. **The test ran after the fact.** A test tells you the secret is committed;
   a hook stops it being committed. By the time a red suite is noticed the
   value is already published, and publishing is the irreversible step.
2. **The test had been red on main for two days and nobody acted.** A signal
   nobody blocks on is a signal nobody reads. This hook refuses the commit,
   which is not ignorable.
3. **The test file itself carried the real account id, VPC id, security group
   id and a public IP as its own fixtures** — and the scanner skips its own
   file, so the leak detector was the single largest source of leaked
   identifiers and structurally could not flag itself. THAT is why the
   allowlist below is a set of literal exemptions with a stated reason each,
   never a whole-file skip.

The patterns are IMPORTED from the test module rather than restated, so the
hook and the suite cannot drift into disagreeing about what a secret is.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

# --- one source of truth for what an identifier looks like ----------------- #
# Loaded BY PATH, not by `import tests.…`: there is no tests/__init__.py, so a
# package import silently fails and a hand-copied fallback substitutes itself.
# The first version of this file did exactly that — and it LOOKED fine, because
# the fallback caught the leak. A duplicated rule set that nobody knows is
# duplicated is worse than an honest copy: it drifts, and the drift is silent.
# So: load the real module, and if that is impossible SAY SO on stderr rather
# than quietly degrading.
def _load_patterns():
    import importlib.util
    f = os.path.join(_ROOT, "tests", "test_no_infra_identifiers.py")
    spec = importlib.util.spec_from_file_location("_infra_patterns", f)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {f}")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.PATTERNS, m._HARMLESS_IP, m._IPV4, getattr(m, "_THIRD_PARTY_IPS", set())


try:
    PATTERNS, _HARMLESS_IP, _IPV4, _THIRD_PARTY_IPS = _load_patterns()
    _PATTERN_SOURCE = "tests/test_no_infra_identifiers.py"
except Exception as _exc:                                    # pragma: no cover
    print(f"check_staged_secrets: WARNING — could not load the suite's "
          f"patterns ({type(_exc).__name__}: {_exc}); falling back to a COPY "
          f"that may have drifted. Fix the import rather than trusting this.",
          file=sys.stderr)
    _PATTERN_SOURCE = "built-in fallback copy (DRIFT RISK)"
    _THIRD_PARTY_IPS = set()
    PATTERNS = {
        "aws account id": re.compile(r"\b\d{12}\b"),
        "security group id": re.compile(r"\bsg-[0-9a-f]{8,17}\b"),
        "vpc id": re.compile(r"\bvpc-[0-9a-f]{8,17}\b"),
        "subnet id": re.compile(r"\bsubnet-[0-9a-f]{8,17}\b"),
        "ec2 instance id": re.compile(r"\bi-[0-9a-f]{17}\b"),
        "ami id": re.compile(r"\bami-[0-9a-f]{8,17}\b"),
    }
    _HARMLESS_IP = re.compile(
        r"^(127\.|0\.0\.0\.0|255\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|169\.254\.)")
    _IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

#: Live credential material. These are FATAL and have no allowlist: a private
#: key or an access key in a diff is never a documentation example.
CREDENTIALS = {
    "aws access key id": re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"),
    "private key block": re.compile(r"BEGIN (RSA |EC |OPENSSH |PGP )?PRIVATE KEY"),
    "aws secret access key": re.compile(r"aws_secret_access_key\s*=\s*\S+"),
    "bearer token literal": re.compile(r"Bearer\s+[A-Za-z0-9_\-]{24,}"),
}

#: A non-empty assignment to a name that should only ever hold a real secret.
#: `FOO=`, `FOO=...`, `FOO=<placeholder>` and `FOO="${FOO}"` are all fine.
_SECRET_NAMES = (r"POLYMARKET_SECRET_KEY|POLYMARKET_KEY_ID|MERIDIAN_ORDER_TOKEN"
                 r"|MERIDIAN_NTFY_TOPIC|CFBD_API_KEY|AWS_SECRET_ACCESS_KEY")
ASSIGNED_SECRET = re.compile(
    rf"\b({_SECRET_NAMES})\s*=\s*(?!$|\s|#|\.\.\.|<|\"?\$)[^\s#]{{6,}}")

#: RFC 5737 documentation ranges plus the synthetic ids the suite uses as
#: positive controls. EXPLICIT LITERALS WITH A REASON — never a file-level
#: skip, which is exactly how the detector came to hide its own leaks.
ALLOWED = {
    "192.0.2.": "RFC 5737 TEST-NET-1, reserved for documentation",
    "198.51.100.": "RFC 5737 TEST-NET-2, reserved for documentation",
    "203.0.113.": "RFC 5737 TEST-NET-3, reserved for documentation",
    "123456789012": "AWS docs' canonical example account id",
    "sg-0123456789abcdef0": "synthetic positive control",
    "vpc-0123456789abcdef0": "synthetic positive control",
    "i-0123456789abcdef0": "synthetic positive control",
}

_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")


def _scrub(line: str) -> str:
    """Strip UUIDs — their 12-hex tail otherwise reads as an account id."""
    return _UUID.sub("<uuid>", line)


def _allowed(text: str) -> bool:
    return any(a in text for a in ALLOWED)


def scan_text(text: str, where: str) -> list[str]:
    hits: list[str] = []
    for n, raw in enumerate(text.splitlines(), 1):
        line = _scrub(raw)

        for name, pat in CREDENTIALS.items():
            if pat.search(line):
                hits.append(f"{where}:{n}  CREDENTIAL — {name}")

        m = ASSIGNED_SECRET.search(line)
        if m:
            hits.append(f"{where}:{n}  CREDENTIAL — {m.group(1)} assigned a real-looking value")

        if _allowed(line):
            continue

        for name, pat in PATTERNS.items():
            if pat.search(line):
                hits.append(f"{where}:{n}  infra identifier — {name}")

        for ip in _IPV4.findall(line):
            # `_THIRD_PARTY_IPS` is the suite's own reasoned allowlist —
            # imported, not restated, so the hook and the test cannot drift
            # into disagreeing about what counts as exposure.
            if ip in _THIRD_PARTY_IPS:
                continue
            if not _HARMLESS_IP.match(ip) and not _allowed(ip):
                hits.append(f"{where}:{n}  public IP address")
    return hits


def _staged_diff() -> str:
    """ADDED lines only — an existing hit must not block unrelated work."""
    out = subprocess.run(["git", "diff", "--cached", "--unified=0"],
                         capture_output=True, text=True).stdout
    return "\n".join(l[1:] for l in out.splitlines()
                     if l.startswith("+") and not l.startswith("+++"))


def _install() -> int:
    d = subprocess.run(["git", "rev-parse", "--git-dir"],
                       capture_output=True, text=True).stdout.strip()
    hook = os.path.join(d, "hooks", "pre-commit")
    os.makedirs(os.path.dirname(hook), exist_ok=True)
    # The hook must work from a WORKTREE CHECKED OUT ON AN OLDER BRANCH, where
    # this script does not exist in the tree. Resolving it from
    # --show-toplevel crashes there; the commit is still blocked (fail-closed
    # is right) but the error is cryptic and every such worktree breaks.
    # So: try this worktree, then the main checkout beside the common git dir,
    # and only then refuse with an explanation.
    body = """#!/bin/sh
# Installed by scripts/check_staged_secrets.py --install
top=$(git rev-parse --show-toplevel 2>/dev/null)
common=$(git rev-parse --git-common-dir 2>/dev/null)
main=$(cd "$common/.." 2>/dev/null && pwd)
for c in "$top/scripts/check_staged_secrets.py" "$main/scripts/check_staged_secrets.py"; do
  if [ -f "$c" ]; then exec python3 "$c"; fi
done
echo "pre-commit: check_staged_secrets.py not found in this worktree or in" >&2
echo "  $main -- refusing the commit (fail closed)." >&2
echo "  This worktree is probably on a branch predating the guard." >&2
echo "  Rebase onto main, or run with --no-verify only if you are certain" >&2
echo "  the diff contains no infra identifiers or credentials." >&2
exit 1
"""
    with open(hook, "w") as f:
        f.write(body)
    os.chmod(hook, 0o755)
    print(f"installed {hook}")
    print("Every clone needs this once — a hook is not itself committed.")
    return 0


def main() -> int:
    if "--install" in sys.argv:
        return _install()

    if "--all" in sys.argv:
        files = subprocess.run(["git", "ls-files"], capture_output=True,
                               text=True).stdout.split()
        hits: list[str] = []
        for f in files:
            try:
                with open(os.path.join(_ROOT, f), encoding="utf-8") as fh:
                    hits += scan_text(fh.read(), f)
            except (OSError, UnicodeDecodeError):
                continue
    else:
        hits = scan_text(_staged_diff(), "staged")

    if not hits:
        print("secret check: clean")
        return 0

    print("\n*** COMMIT BLOCKED — this would publish infrastructure identifiers "
          "or credentials ***\n", file=sys.stderr)
    for h in hits[:40]:
        print(f"  {h}", file=sys.stderr)
    if len(hits) > 40:
        print(f"  ... and {len(hits) - 40} more", file=sys.stderr)
    print("\nThis repository is PUBLIC. Pushing is irreversible: rewriting "
          "history afterwards does not remove the value from forks, clones, or "
          "GitHub's cache.\n"
          "Use an environment variable with a loud default:\n"
          '  SG="${MERIDIAN_SG:?set MERIDIAN_SG}"\n'
          "and keep the value in ~/.meridian-aws, which is not tracked.\n"
          "If a hit is genuinely a documentation example, add the literal to "
          "ALLOWED in this file WITH ITS REASON — never skip a whole file, "
          "which is how the previous detector came to hide its own leaks.",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
