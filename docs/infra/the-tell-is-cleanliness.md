# The tell is cleanliness

Nineteen instances from one night, across two sessions. Not one announced
itself as an error. Every one produced a tidy, well-formed, confident output —
a count, a mean, a hash, a "passed", a "still running" — and that is the
common feature. **A broken instrument does not usually return garbage. It
returns something clean.**

Written because the failures kept arriving in different costumes and we kept
diagnosing each one locally. They are five mechanisms, and naming them is
cheaper than re-deriving the diagnosis nineteen times.

## 1. The instrument appears in its own measurement

| instance | what it actually measured | what caught it |
|---|---|---|
| `pgrep -f nightly_scan` | its own command line | an implausible duration: "still running at 2h21m" when the true time was 9m15s |
| `pgrep -f nightly_scan` (again, other session, same night) | its own command line | the scan's artifact already existed |

The cheap handle for a process is a string, and the searching process is also
a string. Nothing about the output says which one you matched.

## 2. The instrument's failure produces a valid-looking value

| instance | the failure | the clean output | what caught it |
|---|---|---|---|
| `git cat-file blob` where git refuses ("dubious ownership") | writes NOTHING | `sha256sum` hashes empty input, so 414 reference entries all became `e3b0c44298fc…`, under a header reading "reference: origin/main 7e57c8d, 414 .py files" | an independent grep for a known marker returned the empty hash |
| `grep -v " Up "` on `docker ps` | the separator is a TAB, so nothing matched | matching nothing returns everything, which looks like a full survey of down containers | there were no down containers to find |
| a container OOM-killed at exit 137 | the wrapper's own status was 0 | "exit=0" with an empty output file | zero rows where ~1M were expected |
| `random.Random(1)` constructed INSIDE a comprehension | 2,000 identical draws | a degenerate sample computes a mean and an sd without complaint; a test then failed for the wrong reason | the SECOND copy of the same bug, where a single-valued sample made a tail function return None and the TypeError was unmissable |
| `grep -c` on wrapped prose | counts lines, not occurrences | a plausible integer | whitespace normalisation; `grep -o \| wc -l` does NOT fix it |

This is the largest group and the most dangerous: the failure mode has a
*type-correct* output.

## 3. A proxy stands in for the thing

| the proxy | the thing | what it cost |
|---|---|---|
| a constant's VALUE | the constant's identity | 383 "duplicated threshold" pairs, almost all unrelated constants that both happen to be 30. Re-keyed on NAME: 4 pairs, one a real drift |
| `git rev-list --count` (reachability) | whether the content is on main | one apparently-unmerged commit; every file was byte-identical on main and the one that "differed" had moved on for unrelated reasons |
| a filename from `grep -rln` | a code path | escalated to the operator as "worse than data loss, an availability problem". The only hit under `core/` was a COMMENT, written by the other session that morning |
| a grep for one's own summary | the amendment's actual wording | a rescued file reported missing when it was present |
| an image tag, a commit stamp, a checkout on disk | the code inside the container | five separate confusions in one day. All three carry nothing on this fleet: the stamp is empty in all 28 containers, no container bind-mounts its code, and every image is tagged after its own container |

## 4. The status measured is not the status that matters

| instance | what was tested | what mattered |
|---|---|---|
| `if ! docker exec … \| sort > f` | `sort`'s exit status | `docker`'s. A container with no Python returned an OCI error and was classified DIFFERS with a file named "OCI" instead of UNKNOWN |
| `pytest \| tail && push` | `tail`'s status | `pytest`'s. Pushed red twice in a night |
| `bash script \| tail -4; echo $?` | `tail`'s status | the script's `exit 2` |
| "my command timed out" | the client's patience | the query's life. A 62M-row unbounded scan ran to completion on prod after the requester stopped waiting, and could not be cancelled by its own author |

A pipeline's exit status is its last command's. This one recurred **three
times in one night** in two sessions, including inside the tool built to catch
the class.

## 5. The control tests something adjacent to its name

| instance | what it asserted | why it passed anyway |
|---|---|---|
| a precedence test reading `LIVE_FINALS_SQL` | that a post row beats a backfill row | the precedence between the two SOURCES lives in `GAMES_SQL`; the post row was the only live row in the fixture, so it passed with the precedence REVERTED |
| a guard grepping a docker-run block for the literal `/opt/meridian` | that host paths are not used inside a container | the defect was the VARIABLE `$OUT`. The second version then failed on a legitimate shell redirect — so it failed on the fix rather than the bug |
| a clamp on a returned value, with a test for it | that the value cannot exceed the segment | the bound held by construction; removing the clamp broke nothing |
| a source-grep asserting `'g["src"] == "proxy"' in inspect.getsource(...)` | that a policy is implemented | a contract on TEXT, not behaviour |
| a batched mutation runner | that the tests catch a mutation | the mutation was never applied; "18 passed" meant nothing. Grepping the file flipped it to 5 failures |

## What actually caught them

Tallied, because it decides where to spend effort:

* **an implausible number** — 5
* **an independent second route** (a different table, a grep, a recompute) — 5
* **stderr that was already printed** — 2 (`comm: file 1 is not in sorted order`; git's ownership refusal)
* **mutating in both directions** — 3
* **verifying the intervention LANDED** — 2
* **reading the code** — **0**

Nothing here was found by review. That is the practical content of the note.

## The four habits that follow

1. **Ask what the instrument would say if it were measuring itself.** If the
   answer is "the same thing", the instrument cannot answer the question.
2. **Verify the intervention landed, not that the output looks right.** Grep
   the mutated file. `ps` the pid you think you killed. Print the separator.
   Check `n_distinct` on the sample. A clean result from an intervention you
   did not confirm is a result about your plumbing.
3. **Mutate in both directions.** One direction proves the test CAN fail; the
   other proves it fails for the RIGHT REASON. A test that fails on both the
   bug and the fix is worse than no test, because it trains you to ignore it.
4. **Suspect the tidy answer.** Zero hits, all passed, 383 matches, "still
   running", a reference of 414 entries, a mean over 2,000 draws. Friction is
   evidence that something real was touched.

## And the corollary that is harder to act on

A conclusion that does not move is not evidence that the description is sound.
Three times in one night a pooled statistic produced a false description
behind a correct headline — which is precisely why nobody looks. The
instrument being wrong and the answer being right are independent events, and
only one of them is visible.
