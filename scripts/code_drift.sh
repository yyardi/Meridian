#!/usr/bin/env bash
# WHAT IS RUNNING vs WHAT IS ON origin/main, per container.
#
#   sudo -n /opt/meridian/scripts/code_drift.sh            # every container
#   sudo -n /opt/meridian/scripts/code_drift.sh meridian-api
#
# Measured 2026-09-15 and the reason this hashes content rather than reading a
# tag: MERIDIAN_ENGINE_COMMIT is EMPTY in all 21 containers, NO container
# bind-mounts its code (so the checkout at /opt/meridian is never what runs),
# and every image is tagged after its own container with no sha or date. The
# stamp, the mount and the tag all carry nothing, so content is the only
# authority.
#
# UNKNOWN IS NOT A PASS. A container the probe cannot read is reported as
# UNKNOWN and counted separately. An instrument that says "matches" when it did
# not look would be the class of bug it exists to catch.
set -u
cd /opt/meridian || exit 1

PROBE=/tmp/drift_probe_$$.py
cat > "$PROBE" <<'PY'
import hashlib, os
root = "/app"
out = []
for d, dirs, files in os.walk(root):
    dirs[:] = [x for x in dirs if x not in ("__pycache__", ".git", "node_modules")]
    for f in files:
        if f.endswith(".py"):
            p = os.path.join(d, f)
            try:
                b = open(p, "rb").read()
            except OSError:
                continue
            out.append((os.path.relpath(p, root), hashlib.sha256(b).hexdigest()[:16]))
# PATH FIRST, and sorted as the line will be compared. The first version
# emitted "hash path" sorted by PATH while the reference was sorted by the
# whole line (hash first), so `comm` compared two files ordered on different
# keys and reported 210 of 214 files drifted on every container. It also said
# so on stderr -- "file 1 is not in sorted order" -- and the number was
# implausible. Both tells were there to read.
out.sort()
for rel, h in out:
    print(rel, h)
PY
trap 'rm -f "$PROBE"' EXIT

# The reference is origin/main's BLOBS, not the working tree: a dirty checkout
# would otherwise make every container look like it drifted.
git fetch -q origin 2>/dev/null
REF=/tmp/drift_ref_$$.txt
git ls-tree -r origin/main --name-only \
  | grep '\.py$' \
  | while read -r p; do printf '%s %s\n' \
      "$p" "$(git cat-file blob "origin/main:$p" | sha256sum | cut -c1-16)"; done \
  | LC_ALL=C sort > "$REF"
trap 'rm -f "$PROBE" "$REF"' EXIT
# THE REFERENCE MUST BE VERIFIED BEFORE IT IS TRUSTED. Run by a user who
# cannot read this repo -- /opt/meridian is root-owned, so `git` refuses for
# `ubuntu` with "detected dubious ownership" -- `git cat-file` writes NOTHING
# and `sha256sum` cheerfully hashes empty input. Every file then looks drifted
# and the tool reports total drift with complete confidence. That is the exact
# failure this instrument exists to catch, so it checks itself: an empty
# reference, or any entry carrying the sha256 of the empty string, is fatal.
EMPTY_SHA=e3b0c44298fc1c14        # sha256("") -- what a failed cat-file yields
NREF=$(wc -l < "$REF"); NREF=${NREF:-0}
if [ "$NREF" -lt 100 ]; then
  echo "REFERENCE UNUSABLE: only $NREF .py files from origin/main." >&2
  echo "  git cannot read /opt/meridian as $(id -un). Run with sudo." >&2
  exit 2
fi
if grep -q " $EMPTY_SHA\$" "$REF"; then
  echo "REFERENCE UNUSABLE: $(grep -c " $EMPTY_SHA\$" "$REF") entries carry" \
       "the hash of EMPTY input, so git produced nothing for them." >&2
  exit 2
fi
echo "reference: origin/main $(git rev-parse --short origin/main), $NREF .py files"

TARGETS=${*:-$(docker ps --format '{{.Names}}')}
MATCH=0; DIFF=0; UNK=0
for c in $TARGETS; do
  STAMP=$(docker inspect "$c" --format \
    '{{range .Config.Env}}{{if eq (index (split . "=") 0) "MERIDIAN_ENGINE_COMMIT"}}{{index (split . "=") 1}}{{end}}{{end}}' 2>/dev/null)
  GOT=/tmp/drift_got_$$.txt
  # The exec's status, NOT the pipeline's. Sorting inside the `if` made this
  # test `sort`'s exit code, so meridian-postgres -- which has no python and
  # returns an OCI runtime error -- came back as DIFFERS with a file called
  # "OCI" instead of UNKNOWN. A pipeline's status is its LAST command's, and I
  # reintroduced that while fixing the sort-order bug above.
  RAW="$GOT.raw"
  # THE RULE: a probe that could not run must not report agreement. UNKNOWN is
  # not a pass. Read as MATCHES, a container with no python would get a clean
  # bill of health from a tool that never looked at it -- which is the failure
  # this script exists to catch, committed by the script itself.
  if ! docker exec -i "$c" python - < "$PROBE" > "$RAW" 2>/dev/null; then
    printf '%-30s %-8s %s\n' "$c" "UNKNOWN" "no python in the image, or exec refused"
    UNK=$((UNK+1)); rm -f "$GOT" "$RAW"; continue
  fi
  LC_ALL=C sort "$RAW" > "$GOT"; rm -f "$RAW"
  N=$(wc -l < "$GOT"); N=${N:-0}
  if [ "$N" -eq 0 ]; then
    printf '%-30s %-8s %s\n' "$c" "UNKNOWN" "the probe found no .py files"
    UNK=$((UNK+1)); rm -f "$GOT"; continue
  fi
  # A line present in the container and absent-or-different in the reference.
  # comm needs BOTH sides in the same collation; LC_ALL=C on both, and the
  # exit status of the pipeline above is `sort`'s, so a failed exec is caught
  # by the empty-probe branch rather than by the `if`.
  DRIFTED=$(comm -23 "$GOT" "$REF" | awk '{print $1}' | LC_ALL=C sort -u)
  NDRIFT=$(printf '%s' "$DRIFTED" | grep -c . ); NDRIFT=${NDRIFT:-0}
  if [ "$NDRIFT" -eq 0 ]; then
    printf '%-30s %-8s %s\n' "$c" "MATCHES" "$N files, stamp=${STAMP:-<empty>}"
    MATCH=$((MATCH+1))
  else
    printf '%-30s %-8s %s\n' "$c" "DIFFERS" \
      "$NDRIFT of $N files, stamp=${STAMP:-<empty>}"
    printf '%s\n' "$DRIFTED" | head -6 | sed 's/^/      /'
    [ "$NDRIFT" -gt 6 ] && echo "      ... and $((NDRIFT-6)) more"
    DIFF=$((DIFF+1))
  fi
  rm -f "$GOT"
done

echo
# THE OTHER RULE: three counts, never two. "20 of 21 up to date" lets an
# UNKNOWN read as a pass; an unexamined container is its own category and has
# to be printed as one.
echo "$MATCH match, $DIFF DIFFER, $UNK UNKNOWN"
[ "$UNK" -gt 0 ] && echo "UNKNOWN is not a pass: the probe could not read those containers."
exit 0
