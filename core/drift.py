"""Is the code that is RUNNING the code that is on origin/main?

Every failure this exists to catch looked correct from the outside: an api
image eight days stale that silently broke a Monday paper book, a PULSE image
from 2026-09-06 that did not contain the watermark merged that morning, six
fixes written and inert, and two rounds of "staged means deployed". None of
them were visible from the image tag or from the checkout on disk.

THREE FACTS ABOUT THIS FLEET, measured 2026-09-15, which force the design:

1. `MERIDIAN_ENGINE_COMMIT` is EMPTY IN ALL 21 CONTAINERS, not just the scalp
   image. The intended stamp carries nothing anywhere, so it cannot be the
   answer -- only a reported observation.
2. NO container bind-mounts the code. The only binds are data directories, so
   every service runs its IMAGE's copy and the checkout at /opt/meridian is
   never what runs. That is exactly why "the checkout looked right" was
   misleading rather than merely unhelpful.
3. Image tags carry no version: each container's image is named after the
   container (`meridian-scalp-nfl`), with no sha or date to compare.

So content is the only authority: hash the .py files INSIDE the container and
compare them to the same files at origin/main.

THE ONE RULE THAT MATTERS: an absent stamp, an unreadable container, or a
container with no Python is **UNKNOWN**, never MATCHES. An instrument that
reports agreement when it has not looked would be this entire class of bug one
more time, inside the tool built to detect it.
"""

from __future__ import annotations

UNKNOWN = "UNKNOWN"
MATCHES = "MATCHES"
DIFFERS = "DIFFERS"


def classify(container: dict[str, str] | None, reference: dict[str, str]
             ) -> tuple[str, list[str]]:
    """(verdict, differing paths).

    `container` is path -> content hash for the files the CONTAINER holds, or
    None when the probe could not run. `reference` is the same mapping at
    origin/main.

    A file the reference LACKS counts as differing, not as agreement: it means
    the running image carries code that main has deleted, which is drift in
    the direction nobody checks.

    Files the reference has and the container lacks are NOT drift — images
    legitimately exclude tests/ and the analysis runners — so the comparison
    is one-directional by design, and the docstring says so because the
    asymmetry is a choice rather than an oversight.
    """
    if container is None:
        return UNKNOWN, []
    if not container:
        # An image with zero Python files is not agreement. It is a probe that
        # found nothing, which is the same epistemic state as a failed probe.
        return UNKNOWN, []
    differing = sorted(p for p, h in container.items() if reference.get(p) != h)
    return (DIFFERS, differing) if differing else (MATCHES, [])


def summarise(rows: list[tuple[str, str, list[str]]]) -> str:
    """One line per container plus a total that cannot hide an UNKNOWN.

    `rows` is (name, verdict, differing). The counts are printed separately
    rather than as "N of M up to date", because a single number would let an
    UNKNOWN read as a pass.
    """
    n_match = sum(1 for _, v, _ in rows if v == MATCHES)
    n_diff = sum(1 for _, v, _ in rows if v == DIFFERS)
    n_unk = sum(1 for _, v, _ in rows if v == UNKNOWN)
    out = [f"{n_match} match, {n_diff} DIFFER, {n_unk} UNKNOWN "
           f"(of {len(rows)} containers)"]
    if n_unk:
        out.append("  UNKNOWN is not a pass: the probe could not read those "
                   "containers, so nothing is known about their code.")
    return "\n".join(out)
