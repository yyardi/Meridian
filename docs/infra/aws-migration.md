# Moving the stack to AWS — the operator's click list

Everything below is buildable and reviewable now; **the first execution is the
test.** Every step verifies before the next one starts, and the laptop stack
stays intact and recording until parity is proven across a full slate.

## What already exists (created 2026-08-19, us-east-1)

| | |
|---|---|
| key pair | `meridian` → `~/.ssh/meridian-aws.pem` |
| security group | `sg-0af95dedc2bd41b07` — SSH from the operator's IP /32 only |
| S3 bucket | `meridian-backups-623955527388` |
| VPC | `vpc-06554dfe029f2cf6a` (default) |

## Cost, priced from the AWS Price List API on 2026-08-19

| item | rate | monthly |
|---|---|---|
| **m7i.xlarge** (4 vCPU, 16 GiB) | $0.2016/hr | **$147.17** |
| 100 GB gp3 | $0.08/GB-mo | **$8.00** |
| S3 (a few GB, occasional) | $0.023/GB-mo | pennies |
| | | **≈ $155/mo** |

`t3.xlarge` is $0.1664/hr (**$121.47/mo**) for the same 4 vCPU / 16 GiB and is
tempting. **Take m7i anyway.** t3 is burstable: baseline is 40% of its vCPUs,
and this is a 24/7 workload with a 200ms writer, a postgres, and eight
containers. Burst credits deplete under exactly that profile, and the failure
mode is a recorder that quietly falls behind mid-slate rather than one that
stops — the hardest kind to notice. $26/mo is not the place to economise.

**When the credits run out**, this is a permanently-on instance, which is the
textbook case for a 1-year Compute Savings Plan (~30–40% off on-demand). Worth
revisiting then, not now — committing before the workload has settled is how
you end up paying for a shape you have grown out of.

## Disk: 100 GB is right, and it is not generous

Measured on the laptop, 2026-08-19:

| | |
|---|---|
| database total | **11 GB** |
| `market_snapshots_y2026m08` | 8.9 GB · 15.3M rows |
| `book_levels_y2026m08` | 1.5 GB · 8.3M rows |
| growth | **~10 GB per month** of in-season recording |

So 100 GB is roughly: 11 GB restored + ~15 GB OS/Docker/dumps + **~7 months**
of season-rate headroom. That covers a WNBA season (May–Oct) with room, and it
is not a number to forget about.

Two things make this safe rather than tight:

* **gp3 grows online.** Expanding the volume needs no downtime and no
  re-provision, so getting this slightly wrong is cheap to correct.
* **`core/retention.py` archives-then-deletes** rows older than 72h from the
  three big tables. Worth confirming it is actually running on the instance —
  it was written against the Supabase 500 MB cap, and the 11 GB above suggests
  it is not pruning aggressively on the laptop.

**Set a CloudWatch alarm on disk usage at 80%.** A full disk stops postgres,
which stops the recorder, mid-slate, and unrecorded ticks are unrecoverable.

## Step 1 — launch the instance

| field | value |
|---|---|
| AMI | Ubuntu 22.04 LTS or 24.04 LTS (x86_64) |
| type | **m7i.xlarge** |
| key pair | `meridian` |
| VPC | `vpc-06554dfe029f2cf6a` (default) |
| security group | `sg-0af95dedc2bd41b07` |
| storage | **100 GB gp3**, 3000 IOPS, 125 MB/s (defaults) |
| IAM role | one with `s3:GetObject` on `meridian-backups-623955527388` |

The IAM role is the only item not yet created. Without it, step 4's restore
cannot pull the dump and you would have to scp a multi-GB file over the
laptop's uplink instead.

Confirm SSH before anything else:

```bash
ssh -i ~/.ssh/meridian-aws.pem ubuntu@<instance-ip> 'echo ok'
```

## Step 2 — copy the secrets

`.env` is **never** in the repo and never in a script. It carries
`POLYMARKET_SECRET_KEY` and `MERIDIAN_ORDER_TOKEN`; treat it like the key
material it is.

```bash
scp -i ~/.ssh/meridian-aws.pem \
    ~/Documents/Quant/Meridian/.env \
    ubuntu@<instance-ip>:/tmp/meridian.env

ssh -i ~/.ssh/meridian-aws.pem ubuntu@<instance-ip> \
  'sudo install -D -o meridian -g meridian -m 600 /tmp/meridian.env /opt/meridian/.env && rm /tmp/meridian.env'
```

The `install` runs before the user exists on a first run — do this step
**after** step 3 if it complains, or simply re-run step 3, which is idempotent.

## Step 3 — provision

```bash
scp -i ~/.ssh/meridian-aws.pem deploy/aws/provision.sh ubuntu@<instance-ip>:/tmp/
ssh -i ~/.ssh/meridian-aws.pem ubuntu@<instance-ip> 'sudo bash /tmp/provision.sh'
```

Installs Docker + compose, creates the `meridian` user, clones the repo, checks
`.env` is present with non-empty required keys, creates the artifact root, and
brings the stack up with `--build`.

It **refuses to start without `.env`** rather than coming up half-configured. A
stack that runs without credentials looks healthy — containers up, heartbeats
beating — and records nothing from the authenticated venue. That silent-running
shape has cost this project real data twice (B11, B12).

Verify:

```bash
ssh -i ~/.ssh/meridian-aws.pem ubuntu@<instance-ip> \
  'cd /opt/meridian && docker compose ps && docker compose exec postgres pg_isready -U meridian -d meridian'
```

The database is **empty** at this point. That is expected.

## Step 4 — migrate the data

From the **laptop**, with the local stack running:

```bash
deploy/aws/migrate.sh <instance-ip>
```

1. Preflight — key, container, aws cli, bucket, ssh, and **postgres major
   version parity** (16 both ends; a newer dump is refused by an older server).
2. `pg_dump -Fc -Z6` from **inside** the postgres container — the laptop has no
   postgres client tools, and the container already stages dumps to
   `$MERIDIAN_DATA_DIR/ticks` via the `/backups` mount `core/retention.py` uses.
3. Upload to S3.
4. The instance pulls from S3 itself and `pg_restore --single-transaction` —
   all-or-nothing, so a failure leaves an empty database rather than a
   half-populated one.
5. **Row counts, table by table**, laptop against instance. Any mismatch aborts
   loudly.

Nothing is deleted anywhere. Re-check any time with:

```bash
deploy/aws/migrate.sh <instance-ip> --verify-only
```

## Step 5 — parallel run (this is the real test)

**Do not cut over on matching row counts.** They prove the copy, not the
copier. Let **both** stacks record the same full slate, then compare what each
captured over the same window:

```bash
# laptop
docker exec meridian-postgres psql -U meridian -d meridian -At -c \
  "select count(*) from market_snapshots where captured_at > now() - interval '6 hours'"

# instance
ssh -i ~/.ssh/meridian-aws.pem ubuntu@<instance-ip> \
  "cd /opt/meridian && docker compose exec -T postgres psql -U meridian -d meridian -At -c \
   \"select count(*) from market_snapshots where captured_at > now() - interval '6 hours'\""
```

Counts will not match exactly — two pollers on two networks land on different
200ms boundaries. **Within a few percent is parity; a factor is a problem.**
Also check `/api/status` on the instance shows every writer fresh, over a
tunnel:

```bash
ssh -i ~/.ssh/meridian-aws.pem -N -L 8008:localhost:8008 ubuntu@<instance-ip>
open http://localhost:8008
```

## Step 6 — cutover, and it is smaller than it sounds

The whole stack moves, so there is no `DATABASE_URL` to repoint — every
container already talks to its own local postgres by service name. Cutover is:

1. Stop the laptop stack: `docker compose down` (containers only; **the volume
   stays**).
2. Use the instance from then on, via the SSH tunnel above.

**Rollback is `docker compose up -d` on the laptop.** Nothing was deleted, so
the fallback stays available indefinitely. Do not delete the laptop volume
until the instance has run a full week unattended.

## Ports: keep them shut

The security group allows SSH from one address and nothing else. **Leave it
that way.** The dashboard exposes `/api/orders`, gated by
`MERIDIAN_ORDER_TOKEN` — a token is not a reason to put an order endpoint on
the public internet. The tunnel costs one command and removes the entire class
of problem.

## Two things found by running this, not by writing it

**`docker inspect --format '{{.Mounts}}'` lies on Docker Desktop for Mac.** It
reports the VM-internal source (`/host_mnt/Users/...`), not the macOS path — so
the first draft of `migrate.sh` failed its own "is the dump on the host?" check
against a dump that had written perfectly well. The host path now comes from
`core/paths.py`'s contract (`MERIDIAN_DATA_DIR`, default `<repo>/backups`),
which is the authority anyway. This script runs on the laptop, so this was not
a theoretical platform difference.

**The row-count verification was executed against the live database**, not just
written: all 18 tables in `migrate.sh`'s contract list return counts and none
reports `-1`. That list is deliberately explicit rather than `all tables` — a
table added later should force a deliberate edit here rather than silently not
being checked.

## The morning health check

```bash
deploy/aws/health.sh          # from the laptop, checks the server
```

Same groups, same colours, same `Verdict:` line as running `scripts/health.py`
on the box. Exit code is the script's — 0 for OK or DEGRADED, 1 for DEAD — so
it drops into a cron or a shell prompt unchanged.

### It runs on the host, not in a container — and that was a decision

`scripts/` is deliberately not in the container image, so there were two ways
to run it. The host won, for a reason in the script's own docstring: it exists
to check **what a container cannot see** — `docker compose ps` and the host's
disk. Running it inside a container would need the docker socket mounted in,
which hands root-equivalent host access to a container on a box holding the
venue secret key. Too much privilege for a status command.

So `provision.sh` creates `/opt/meridian/.venv-health`: **63 MB**, five
packages. That dependency list was found by *running* it, not by reading
imports — `healthchecks.py` imports only `httpx` and `sqlalchemy` at the top,
then lazily imports `core.storage` (dotenv) and `core.heartbeat` (structlog)
partway through a run, so the failure arrived three checks in.

### Three things that only showed up when it was run

* **`.env` must be read inside the `sudo`.** It is `0600` and owned by
  `meridian`; the first version grepped it in the invoking shell as `ubuntu`,
  got "Permission denied", and would have run every database check against no
  `DATABASE_URL`.
* **`PYTHONPATH` is required, not defensive.** Python puts the *script's*
  directory on `sys.path` — `scripts/` — never the working directory, so
  `scripts/health.py` cannot see `./core` however you `cd`. Without it the run
  dies on `No module named 'core'` before the first check.
* **`"${EMPTY[@]}"` under `set -u` aborts on bash 3.2**, which is what macOS
  ships and what this wrapper runs on. The ssh options are built as one array
  that is never empty.

### The laptop after cutover

Running `scripts/health.py` on the retired laptop prints one line rather than a
wall of red:

```
local stack retired — production is the server; run deploy/aws/health.sh
Verdict: ALL GOOD — nothing is expected to run here
```

Every container stopped **on the laptop** is a state, not an outage. The same
condition on the server is still an emergency and still exits 1 — the calm path
is deliberately one-sided, and a test pins that asymmetry.

**Known consequence of the cutover, not yet solved:** `tests/conftest.py`
creates a per-run database in a local postgres at `localhost:5433`, so with the
laptop stack down **the test suite cannot run there**. A throwaway
`docker run --rm -p 5433:5432 postgres:16-alpine` with the `meridian` user is
enough, and does not touch the retired stack's volume.

## What is not covered here

* **Backups of the instance's own database.** The laptop was its own backup by
  being the only copy; on EC2 that is no longer true. A nightly `pg_dump` to
  the same S3 bucket is the obvious next step and is not in these scripts.
* **Restart-on-reboot.** Compose services are `restart: unless-stopped`, and
  Docker is enabled at boot, so the stack returns after a reboot — but this has
  not been tested on an instance yet, and the runbook's first execution is the
  place to test it.
