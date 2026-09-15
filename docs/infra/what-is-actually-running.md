# Is the running code the code on main? Measured, and the answer surprised us

Built 2026-09-15 to catch a class that cost us four times in a day: an api
image eight days stale that broke a Monday paper book, a PULSE image believed
to predate the watermark merged that morning, "six fixes written and inert",
and two rounds of staged-means-deployed. **Every one of those looked correct
from the image tag and from the checkout on disk.**

## Three facts that force the design

1. **`MERIDIAN_ENGINE_COMMIT` is EMPTY in all 28 containers**, not just the
   scalp image. The intended stamp carries nothing anywhere.
2. **No container bind-mounts its code.** The only binds are data directories,
   so every service runs its IMAGE's copy and `/opt/meridian` is never what
   runs. That is why "the checkout looked right" was actively misleading.
3. **Image tags carry no version**: each container's image is named after the
   container, with no sha or date.

Stamp, mount and tag all carry nothing, so **content is the only authority**:
hash the `.py` files inside the container and compare them to the same files at
`origin/main`.

**UNKNOWN is never MATCHES.** An unreadable container, a container with no
Python, or an absent stamp is UNKNOWN and counted separately. An instrument
that reports agreement without looking would be this whole class of bug again,
inside the tool built to detect it.

## The first real run, and it retires its own premise

```
28 containers DIFFER by exactly 1 of 214 files -- core/quote/adverse_selection.py
 1 UNKNOWN  meridian-postgres (no python in the image)
 0 match
```

That single file changed on main in **22635d8 at 05:36Z**; the images were
built at **00:25Z**, five hours and eleven minutes earlier. So the fleet is
uniformly current as of its build, with one file's worth of drift since.

**And the four fixes we believed were inert are all running**, verified by
independent greps rather than by this tool:

| fix | marker | in the running container |
|---|---|---|
| PULSE watermark | `acted_captured_at` | 4 occurrences |
| scalp future timestamps | `age < -1.0` | 1 |
| ESPN confirming poll | `SETTLE_CONFIRM_SECONDS` | 5 |
| recorder markets_seen | `markets_seen` | 4 |

The fleet was rebuilt at 2026-09-15T00:25Z, after the day's merges. "Six fixes
written and inert" was true when it was said and had expired by the time the
detector ran. **The instrument's first output contradicted the belief that
justified building it**, which is the most useful thing a new instrument can do.

## Three bugs in the instrument, all caught before it shipped

Each was a defect I keep a note about, reintroduced while building the thing
meant to catch defects.

**1. Two files sorted on different keys.** The probe emitted `hash path` sorted
by PATH; the reference was sorted by the whole line, so by HASH. `comm` then
compared two files ordered differently and reported **210 of 214 files
drifted on every container**. Two tells were present and both were readable:
`comm` printed "file 1 is not in sorted order" on stderr, and the number was
implausible for images built from this repo. Fixed by emitting `path hash` and
sorting both sides under `LC_ALL=C`.

**2. A garbage reference, produced with total confidence.** `/opt/meridian` is
root-owned, so `git` refuses for `ubuntu` with "detected dubious ownership" —
and then `git cat-file blob` writes NOTHING while `sha256sum` cheerfully
hashes empty input. Every file gets the sha256 of the empty string, every
container looks 100% drifted, and the header still says "reference:
origin/main <sha>". The script now verifies its own reference before using it:
fewer than 100 files, or any entry carrying `e3b0c44298fc1c14`, is fatal with
exit 2 and a message naming the cause.

**3. A pipeline's exit status is its last command's.** Fixing bug 1 moved the
`docker exec` into `... | LC_ALL=C sort > "$GOT"`, so the `if !` test measured
`sort` rather than `docker`. `meridian-postgres`, which has no Python and
returns an OCI runtime error, came back as **DIFFERS, 1 of 1 files, named
"OCI"** instead of UNKNOWN. The exec's status is now tested on its own.

All three produced clean, confident, wrong output. None of them would have been
caught by reading the code.

## Using it

```
sudo -n /opt/meridian/scripts/code_drift.sh                 # every container
sudo -n /opt/meridian/scripts/code_drift.sh meridian-api    # one
```

`sudo` is not optional: without it the reference cannot be built and the script
exits 2 rather than guessing.

**CORRECTED 09-15: this paragraph credited `core/drift.py` with tests for
pinning "UNKNOWN is not a pass". It never ran.** The script carries its own
complete classification — the two UNKNOWN branches, `comm -23` for the
asymmetry, and three separate counts — and nothing imported the Python module,
so the tested implementation and the running one were different code and the
guarantee belonged to the one that never executed. The duplicate is deleted;
the two rules are now comments at the branches that implement them. **Pinning
them with a test that drives THIS script (stubbing `docker exec`) is the open
option, and it is the only version of that test worth having — a test of a
parallel implementation asserts a guarantee about code that does not run.**
