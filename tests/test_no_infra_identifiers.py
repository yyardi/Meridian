"""The public repo carries the SHAPE of the infrastructure, never its addresses.

Why a test and not a review habit
---------------------------------
Account-specific identifiers arrive by the most natural route there is: someone
writes a runbook while looking at the console, and the real value is what is in
front of them. It reads as helpful. It is only a leak in aggregate, and only
once the repo is public — which it is.

So the rule is mechanical. A bucket name embeds an AWS account id; a security
group or VPC id names the network; a server address plus a public SSH port is
the pair that actually matters. None of them belong in git, and none of them
are the kind of thing a reviewer reliably notices at the end of a long diff.

Comments and prose are scanned too, unlike the bankroll scanner — an address in
a comment is exactly as public as one in code.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent

_SCANNED_SUFFIXES = {".py", ".sh", ".md", ".yml", ".yaml", ".toml", ".json",
                     ".html", ".js", ".cfg", ".ini", ".txt"}
_SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache",
              "node_modules", "backups"}

PATTERNS = {
    # 12 consecutive digits is an AWS account id, and `meridian-backups-<id>`
    # is the shape that matters most — so the pattern must NOT exclude a
    # leading dash. UUID tails are handled by stripping UUIDs from the line
    # first (see `_scrub_line`); an earlier attempt to solve it with a
    # lookbehind killed the bucket-name case, which is the one this exists for.
    "aws account id": re.compile(r"\b\d{12}\b"),
    "security group id": re.compile(r"\bsg-[0-9a-f]{8,17}\b"),
    "vpc id": re.compile(r"\bvpc-[0-9a-f]{8,17}\b"),
    "subnet id": re.compile(r"\bsubnet-[0-9a-f]{8,17}\b"),
    "ec2 instance id": re.compile(r"\bi-[0-9a-f]{17}\b"),
    "ami id": re.compile(r"\bami-[0-9a-f]{8,17}\b"),
}

#: Addresses that are not addresses: loopback, bind-all, RFC5737 doc ranges,
#: and the private ranges a compose file legitimately names.
_HARMLESS_IP = re.compile(
    r"^(127\.|0\.0\.0\.0|255\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|169\.254\.)"
)
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

#: Third-party public addresses that are evidence, not exposure. The rule is
#: about OUR infrastructure; deleting a measured fact to satisfy a scanner is
#: the tail wagging the dog. Each entry states whose address it is and why the
#: value earns its place — an allowlist without that becomes a dumping ground.
_THIRD_PARTY_IPS = {
    # Cloudflare anycast edge. docs/math/write-latency.md cites it as the
    # evidence that the authenticated host and the public gateway resolve to
    # the SAME edge — so the auth host is not further away, it just does more.
    # Discoverable by anyone with `dig`; naming it exposes nothing of ours.
    "172.64.149.216",
}


#: 8-4-4-4-12 hex. A dummy UUID's final group is twelve digits and is not an
#: account id; stripping them beats trying to describe them in the main rule.
_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)


def _scrub_line(line: str) -> str:
    return _UUID.sub("<uuid>", line)


def _files():
    for path in sorted(_REPO.rglob("*")):
        if not path.is_file() or path.suffix not in _SCANNED_SUFFIXES:
            continue
        if set(path.parts) & _SKIP_DIRS:
            continue
        if path.name == Path(__file__).name:          # this file names patterns
            continue
        yield path, path.relative_to(_REPO).as_posix()


@pytest.mark.parametrize("label", sorted(PATTERNS))
def test_no_aws_identifiers(label):
    rx = PATTERNS[label]
    hits = [
        f"{rel}:{i}: {line.strip()[:90]}"
        for path, rel in _files()
        for i, line in enumerate(path.read_text(errors="ignore").splitlines(), 1)
        if rx.search(_scrub_line(line))
    ]
    assert not hits, (
        f"{label} found in a public repository. Real values live in the AWS "
        "console and the operator's local notes; docs use <placeholders> and "
        "scripts read env vars.\n  " + "\n  ".join(hits)
    )


def test_no_public_ip_addresses():
    """Public IPv4 only. Loopback, bind-all and private ranges are structure,
    not addresses, and compose files legitimately contain them."""
    hits = []
    for path, rel in _files():
        for i, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
            for ip in _IPV4.findall(line):
                octets = ip.split(".")
                if any(int(o) > 255 for o in octets):     # a version, not an IP
                    continue
                if _HARMLESS_IP.match(ip) or ip in _THIRD_PARTY_IPS:
                    continue
                hits.append(f"{rel}:{i}: {ip}")
    assert not hits, (
        "public IP address in a public repository — a server address plus an "
        "open SSH port is the pair that matters. Use <server-ip> in docs and "
        "MERIDIAN_SERVER / ~/.meridian-server in scripts.\n  " + "\n  ".join(hits)
    )


def test_the_scanner_would_actually_catch_one():
    """A guard nobody has watched fail is a guard nobody has tested."""
    assert PATTERNS["aws account id"].search("meridian-backups-623955527388")
    assert PATTERNS["security group id"].search("sg-0af95dedc2bd41b07")
    assert PATTERNS["vpc id"].search("vpc-06554dfe029f2cf6a")
    assert _IPV4.search("HOST=100.60.80.165") and not _HARMLESS_IP.match("100.60.80.165")
    assert _HARMLESS_IP.match("127.0.0.1") and _HARMLESS_IP.match("172.31.14.17")
    # The tightened account-id rule still catches a real one and no longer
    # trips on the tail of an all-zeros dummy UUID.
    # The case this rule exists for: an account id inside a bucket name, which
    # a leading-dash exclusion would have silently stopped catching.
    for real in ("meridian-backups-623955527388",
                 "arn:aws:iam::623955527388:role/x"):
        assert PATTERNS["aws account id"].search(_scrub_line(real)), real
    # ...and the dummy UUID whose tail is twelve digits still does not trip it.
    assert not PATTERNS["aws account id"].search(
        _scrub_line("00000000-0000-4000-8000-000000000000"))
