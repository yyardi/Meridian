# Why the model-performance page was empty

**Symptom.** `/analytics` showed only *"run `python -m core.analytics` first"*,
including immediately after the operator ran it and watched it print
`wrote .../analytics.json`. Re-running never helped, because re-running was
never the problem.

**Cause.** Writer and reader agreed on the *path* and disagreed on the *disk*.

* `python -m core.analytics` is a host job by construction — it reads the
  standby at `localhost:5433`, which does not exist inside a container. It
  wrote `<repo>/backups/reports/analytics.json`.
* `/api/analytics` runs in `meridian-api`, which had **no mount for the
  artifact root**. `data_dir()` fell back to its default and the endpoint
  looked in `/app/backups/reports/analytics.json` — a path that is not in the
  image and not bound to anything. Verified 2026-08-17:

      $ docker exec meridian-api ls /app/backups
      ls: cannot access '/app/backups': No such file or directory

This was not introduced by the artifact-paths change (PR #3); that change
moved both sides together and left them symbolically identical. It has been
broken since the api became a container on 2026-08-07 — before that the
dashboard was a host `nohup uvicorn` and read the host's own disk. PR #3
changed *which* host path was wrong, not whether it was.

The general shape: **two processes on two filesystems, running identical code,
reading the same environment, resolving to different bytes.** No amount of
agreement in the source can catch that.

## The fix, both halves

`core.paths.analytics_path()` is now the single expression for the file, called
by the writer and the reader — the filename literal appears exactly once in
`core/`, and a test enforces that.

Compose gives the api container **both** halves of the mount contract:

```yaml
    environment:
      MERIDIAN_DATA_DIR: /data          # so reports_dir() points AT the mount
    volumes:
      - ${MERIDIAN_DATA_DIR:-./backups}/reports:/data/reports:ro
```

**`reports/` only, not the root.** The api reads exactly one artifact and
serves every other file from the image's own `static/`. Mounting the whole root
would additionally give an unauthenticated service — bound to all interfaces so
the dashboard is reachable over the tailnet — read access to the database dumps
in `ticks/` and `supabase/`, for no benefit. Inside the container `data_dir()`
is therefore a root with a single subtree in it, and `ticks_dir()` /
`supabase_dir()` resolve to paths that do not exist there. That is correct.

The bind alone is not enough, and this is the trap worth remembering: with the
volume mounted but `MERIDIAN_DATA_DIR` unset inside the container,
`data_dir()` still returns `/app/backups` and the page still fails — with the
data sitting right there at `/data`. `core.paths.DATA_DIR_CONTAINER` and
`tests/test_analytics_path.py` pin the pair together, the same way
`BACKUP_DIR_CONTAINER` pins the postgres staging mount.

Read-only is deliberate: the api serves this artifact and never produces it.

## Takes effect on the next container recreate

A compose change is inert until the api container is recreated — deferred here
because games tip at 02:00Z. Until then the page keeps showing the (now
diagnostic) error. Apply with:

```
docker compose up -d api
```

**That command is not as narrow as it looks.** The api's start command is
`alembic upgrade head && uvicorn ...`, so recreating it migrates the database
to head — including any migration merged since the last recreate, by any
branch. It is a schema change plus a mount change, not a mount change. Check
what is pending (`alembic heads`, `alembic current`) before running it, rather
than reading this section as "restart one container to fix one page".

## The error now names the path

The old message could not distinguish *"never built"* from *"built where I
cannot see it"*, which is exactly why this survived six weeks. It now reports
`looked_in`, `data_dir`, and whether the root exists at all — a missing root
is called out as a mount problem, since that is what it means in a container.
