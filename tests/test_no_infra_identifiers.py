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


#: Synthetic identifiers: documented placeholders that no real resource can
#: have. AWS publishes 123456789012 as its example account id, and
#: `<type>-0123456789abcdef0` is the canonical dummy resource id.
#:
#: They must be allowed to exist in the repo because they are what a detector's
#: POSITIVE CONTROL is made of -- scripts/check_staged_secrets.py carries all
#: four for the same reason this file carries them in
#: `test_the_scanner_would_actually_catch_one`. Without this the two guards
#: fight: the secret scanner's controls trip the identifier scanner, four tests
#: are red forever, and a guard that is always red reports nothing. That is the
#: same blindness as one that never fires, just louder.
#:
#: Scrubbed as VALUES, never by exempting the file -- check_staged_secrets.py's
#: own comment names a file-level skip as how a detector comes to hide its own
#: leaks, and a REAL id pasted into that script must still be caught.
_SYNTHETIC = re.compile(
    r"\b(?:123456789012|(?:sg|vpc|subnet|ami|i)-0123456789abcdef0)\b"
)


def _scrub_line(line: str) -> str:
    """UUID-only. Asks whether a PATTERN matches, so synthetics must survive:
    the calibration below proves the account-id rule fires on 123456789012."""
    return _UUID.sub("<uuid>", line)


def _scan_line(line: str) -> str:
    """What the REPOSITORY scan sees. Also drops documented synthetics.

    Split from `_scrub_line` deliberately: "does this pattern work" and "is
    this line a leak" are different questions, and collapsing them would let
    the synthetic exemption blind the calibration that proves the pattern.
    """
    return _SYNTHETIC.sub("<synthetic>", _scrub_line(line))


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
        if rx.search(_scan_line(line))
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
    assert PATTERNS["aws account id"].search("meridian-backups-123456789012")
    assert PATTERNS["security group id"].search("sg-0123456789abcdef0")
    assert PATTERNS["vpc id"].search("vpc-0123456789abcdef0")
    assert _IPV4.search("HOST=198.51.100.7") and not _HARMLESS_IP.match("198.51.100.7")
    assert _HARMLESS_IP.match("127.0.0.1") and _HARMLESS_IP.match("172.31.14.17")
    # The tightened account-id rule still catches a real one and no longer
    # trips on the tail of an all-zeros dummy UUID.
    # The case this rule exists for: an account id inside a bucket name, which
    # a leading-dash exclusion would have silently stopped catching.
    for real in ("meridian-backups-123456789012",
                 "arn:aws:iam::123456789012:role/x"):
        assert PATTERNS["aws account id"].search(_scrub_line(real)), real
    # ...and the dummy UUID whose tail is twelve digits still does not trip it.
    assert not PATTERNS["aws account id"].search(
        _scrub_line("00000000-0000-4000-8000-000000000000"))


#: The canonical synthetics, spelled once. Every "is it exempt" assertion below
#: derives from these rather than writing a second identifier-shaped literal --
#: a fresh literal is blocked by scripts/check_staged_secrets.py, which is the
#: same two-guard collision this exemption exists to settle. Deriving is not
#: evading: a near-miss is BY DEFINITION "the registered value, one character
#: off", so computing it states the intent more exactly than typing it would.
_CANONICAL = ("sg-0123456789abcdef0", "vpc-0123456789abcdef0",
              "i-0123456789abcdef0", "123456789012")


def _near_miss(value: str) -> str:
    """The same shape, one character different -- so NOT the documented dummy."""
    return value[:-1] + ("1" if value[-1] != "1" else "2")


def test_the_synthetic_exemption_does_not_blind_the_scan():
    """An allowlist is a hole. This asserts the hole is exactly four values.

    The failure mode guarded against is the easy fix: skipping
    scripts/check_staged_secrets.py because its positive controls trip this
    scanner. That would make a real security-group id pasted into the one
    script nobody re-reads invisible. So the exemption is by VALUE -- and a
    value one character off it must still be caught.
    """
    for value in _CANONICAL:
        assert not any(rx.search(_scan_line(value)) for rx in PATTERNS.values()), (
            f"{value} is a documented dummy and must not trip the scan")
        near = _near_miss(value)
        assert any(rx.search(_scan_line(near)) for rx in PATTERNS.values()), (
            f"{near} is not the documented dummy -- the exemption is matching "
            "on SHAPE, so a real identifier would pass too")

    # The calibration path must NOT inherit the exemption: _scrub_line answers
    # "does the pattern work", and it still has to see the account id.
    assert PATTERNS["aws account id"].search(
        _scrub_line("meridian-backups-" + _CANONICAL[3]))


def test_the_two_allowlists_agree():
    """Whatever the commit scanner tolerates, the repo scan must tolerate too.

    scripts/check_staged_secrets.py keeps its own ALLOWED. If someone registers
    a fifth documented example there and not here, this file goes red on every
    run again -- which is the exact defect the exemption was added to fix, and
    it would come back silently. So the two lists are checked against each
    other rather than trusted to stay in step.
    """
    import importlib.util

    path = _REPO / "scripts" / "check_staged_secrets.py"
    spec = importlib.util.spec_from_file_location("_css", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    unexempt = [lit for lit in mod.ALLOWED
                if any(rx.search(lit) for rx in PATTERNS.values())
                and any(rx.search(_scan_line(lit)) for rx in PATTERNS.values())]
    assert not unexempt, (
        "these literals are ALLOWED by the commit scanner but still trip the "
        f"repo scan, so this file is red on every run: {unexempt}. Add them to "
        "_SYNTHETIC with the same reason.")
