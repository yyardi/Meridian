# The tell is cleanliness

Twenty-seven rows below: 21 from one night across two sessions, six added on
2026-09-15. Not one announced itself as an error. Almost every one produced a
tidy, well-formed, confident output — a count, a mean, a hash, a "passed", a
"still running" — and that is the common feature. **A broken instrument does
not usually return garbage. It returns something clean.** Mechanism 6 is the
limiting case and was added last: it returns nothing at all, and a suite of
2,326 passing tests could not tell.

*(That sentence said "every one" until mechanism 6 was written into the
document beneath it — the sixth mechanism contradicted the intro's universal
claim, in the file about claims that survive because nobody re-reads them.)*

Written because the failures kept arriving in different costumes and we kept
diagnosing each one locally. They are six mechanisms, and naming them is
cheaper than re-deriving the diagnosis twenty-seven times.

The count in this paragraph said "nineteen" in the file's first commit, when
its own tables already carried 21 rows, and the row added on 2026-09-15 was
labelled "instance 20" by incrementing that number rather than counting the
tables. Both were corrected, and every count since has been produced by
counting the rows. The unit is table rows, which is checkable
by eye; note that section 1's first two rows are one instrument in two
sessions, so an "instruments" count would be lower and would require a
judgement about what collapses. That judgement is why the original number was
unverifiable in the first place.

## 1. The instrument appears in its own measurement

| instance | what it actually measured | what caught it |
|---|---|---|
| `pgrep -f nightly_scan` | its own command line | an implausible duration: "still running at 2h21m" when the true time was 9m15s |
| `pgrep -f nightly_scan` (again, other session, same night) | its own command line | the scan's artifact already existed |
| a caller sweep's second pass, grepping non-Python files | `.pytest_cache/v/cache/nodeids`, whose contents are the names of the things under test | three modules were cleared of being callerless by the test cache's own leftovers. The sweep built for mechanism 6, failing by mechanism 1 |
| that sweep's first regex, `tt import money` | a spelling, not the import | it misses `from core.tt import elo, money, rule`, which is how the real caller is written, so it reported the arm unwired AFTER it had been wired. The matcher was narrower than the measurement |

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
| "141 files changed, 141 insertions" read as one line per file | the per-file distribution | I called a stale branch's additions "about one line per file, a whitespace artefact". Measured: only 29 files have ANY insertion, the top ten carry 105 of the 141, three carry 14 each, and 8 land in the retracted rebate document. The gloss made a branch carrying 141 lines of old prose sound harmless. **Caught by a peer re-measuring a number I had glossed rather than counted.** TWICE-CORRECTED, both wrong before this: (1) the gloss; (2) my correction of it, which said git "never printed two equal numbers" — it did, against `022eed3`, the tip the gloss was read on. *Files changed* moves with main (140/141/142 across three successive tips); *insertions* is fixed at 141. So the two numbers were equal, transiently, and the mechanism is a moving denominator over a fixed numerator. Stable: 141 insertions, 29 files gaining any, mean 4.86. Unstable: any count of files changed. Full account in habit 5 |
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

## 6. The instrument is not connected to anything

Every mechanism above produces a WRONG answer that looks clean. This one
produces NO answer and looks cleanest of all.

| instance | what looked clean | what caught it |
|---|---|---|
| `core/tt/money.py` | 20 passing tests, a registered criterion in a pre-registration doc, and a commit message describing it working | nothing imported it outside its own test file; `PRICE_SQL` selected only the mid, so it had neither an entry point nor the bid/ask it needs. **A peer asking what calls it** |
| `rule.money_verdict` | 28 passing tests on the registered decision rule | the runner decided inline instead — and its expression returned **PASS on an interval entirely below zero**, a strategy that reliably loses. The registered rule was callerless one level down, and the tests protected the copy that never ran |
| `core/drift.py` | a tested classification, and a doc crediting it with pinning "UNKNOWN is not a pass" | the nightly cron runs `scripts/code_drift.sh`, which carries its own complete classification. The Python duplicate was never imported, so the guarantee belonged to the implementation that never executed |

**The suite cannot see this class.** A green suite is consistent with every
module in it being inert, because the tests import what they test. Nothing in
2,326 passing tests distinguishes *runs and is correct* from *is correct and
never runs* — only the import graph does, and no test asks it by default.

Swept across `core/`: **22 of 111 modules have no caller in code, compose,
shell or cron.** Most are legitimately run by hand, which is why the registered
guard is scoped to `core/tt/` — the package that has to fire unattended at
09:00Z with nobody watching. A repo-wide version would be 22 lines of noise,
and a guard its reader learns to skip is worse than none.

**The sweep built for this mechanism failed twice by mechanism 1**, and both
are filed there rather than here: a regex that missed the three-name import
form and so called the arm unwired after it was wired, and a pass that counted
`.pytest_cache` node ids as callers. Classification matters because the fix
differs — one needs a parser, the other needs an exclusion.

## What actually caught them

Tallied, because it decides where to spend effort:

* **an implausible number** — 5
* **a peer asking what calls it** — 3 (an uncalled module, an uncalled decision rule, and a doc crediting the uncalled copy — no test in 2,326 could see any of them)
* **driving the thing rather than reading it** — 2 (the inline verdict that returned PASS on three of four cases including a confident loss; and the zero-width interval, found only by feeding the runner 40 identical bets)
* **a peer re-measuring a number that was glossed rather than counted** — 1
* **re-reading the source string a correction was built on** — 2 (the correction above said git never printed two equal numbers; against the tip it was written on, it did — the count moves with main, the insertions do not)
* **an independent second route** (a different table, a grep, a recompute) — 5
* **stderr that was already printed** — 2 (`comm: file 1 is not in sorted order`; git's ownership refusal)
* **mutating in both directions** — 3
* **verifying the intervention LANDED** — 2
* **reading the code** — **0**

Nothing here was found by review. That is the practical content of the note.

## The six habits that follow

1. **Ask what the instrument would say if it were measuring itself.** If the
   answer is "the same thing", the instrument cannot answer the question.
2. **Verify the intervention landed, not that the output looks right.** Grep
   the mutated file. `ps` the pid you think you killed. Print the separator.
   Check `n_distinct` on the sample. A clean result from an intervention you
   did not confirm is a result about your plumbing.
3. **Mutate in both directions.** One direction proves the test CAN fail; the
   other proves it fails for the RIGHT REASON. A test that fails on both the
   bug and the fix is worse than no test, because it trains you to ignore it.
4. **Ask what calls it.** A module, a test file, green tests and a commit
   message describing it working are all properties of code that may never
   execute. The question no suite asks is which non-test file imports this,
   and the answer took one AST sweep.
5. **Suspect the tidy answer.** Zero hits, all passed, 383 matches, "still
   running", a reference of 414 entries, a mean over 2,000 draws. Friction is
   evidence that something real was touched.
6. **Ask which members of the denominator could have entered the numerator.**
   Git printed `141 files changed, 141 insertions(+), 20840 deletions(-)` at the
   tip the gloss was read on, and against today's main the same diff reads
   `142 files changed, 141 insertions(+), 20985 deletions(-)`. I read it as
   "about one line per file". 113 of the 142 files contain
   only deletions — structurally incapable of carrying an insertion — so the
   mean over files that gained anything is 4.86, and ten files carry 105 of
   the 141. I then corrected this instance by saying the two
   numbers were never equal. **They were** — against main at `022eed3`, the tip
   when the gloss was written, git printed `141 files changed, 141
   insertions(+)`. The count reads 140, 141, then 142 against three successive
   tips, because *files changed* grows as main advances while *insertions* is a
   fixed property of the branch. So the coincidence was real and **transient**,
   which makes the habit stronger rather than weaker: the ratio was near 1.0 by
   an accident of timing that will never reproduce, and **dividing a moving
   number by a fixed one is worse than dividing two unrelated fixed ones.**

   Three revisions of one number, by two people, each locally sound: 141 lines
   → "one line per file, whitespace" → "never equal". Per
   `three-revisions-is-the-signal`, the honest output is the range and its
   breaking bound, not the latest point. **The stable facts are: 141 insertions,
   29 files gaining any, mean 4.86, ten files carrying 105. The unstable one is
   any count of *files changed*, which is a property of when you looked.**

## The guard I tried to write, and why it is not here

The heading above said "four habits" over a list of five for one commit — my
own. The obvious guard is: a heading claiming a count, immediately above an
ordered list, must match the list. Written and run over `docs/`, it finds
exactly 9 qualifying headings and reports 1 mismatch — `## What the two days
say`, above a four-item list, where "two" counts DAYS OF DATA and not list
items. A 1-in-9 false positive rate, semantic and not fixable by tightening
the regex, on a check nobody would investigate twice. So it is not registered.
The class stays on the reading list instead: **a numeral in a heading binds to
some noun, and only sometimes to the list beneath it.**

## And the corollary that is harder to act on

A conclusion that does not move is not evidence that the description is sound.
Three times in one night a pooled statistic produced a false description
behind a correct headline — which is precisely why nobody looks. The
instrument being wrong and the answer being right are independent events, and
only one of them is visible.
