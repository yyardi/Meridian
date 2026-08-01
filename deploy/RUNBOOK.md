# Meridian runbook

Operational reference. For architecture see [../docs/infra/architecture.md](../docs/infra/architecture.md).

## Services

| Container | Purpose | Restart |
|---|---|---|
| `meridian-postgres` | Database | `unless-stopped` |
| `meridian-recorder` | Polymarket snapshots, 15–60 min | `unless-stopped` |
| `meridian-scheduler` | Stats, odds, predictions, resolution, 6h | `unless-stopped` |

## Start / stop

```bash
docker compose up -d          # all services; migrations run on boot
docker compose ps
docker compose logs -f recorder
docker compose down           # stop (data survives in the volume)
```

## Health

```bash
./deploy/healthcheck.sh       # exit 0 healthy, 1 stale
python -m core --status       # snapshots, age, and GAPS
```

**The alert that matters is staleness.** Snapshots cannot be backfilled from
anywhere, so a dead recorder is silent data loss. `--status` reports gaps over
90 minutes explicitly — wire `healthcheck.sh` into cron and alert on a
non-zero exit.

## Running on a laptop

macOS sleeps by default and a sleeping laptop stops collection:

```bash
caffeinate -dis               # blocks idle/display/system sleep; Ctrl-C to release
```

Closing the lid still sleeps unless on power with an external display. Gaps
show up in `python -m core --status`.

## Backups

```bash
./deploy/backup.sh            # pg_dump to ./backups, keeps last 14
```

The prediction log and snapshot history are irreplaceable. **Test a restore** —
a backup you have never restored is not a backup:

```bash
gunzip -c backups/meridian-<stamp>.sql.gz | \
  docker compose exec -T postgres psql -U meridian -d meridian_restore_test
```

## Common tasks

```bash
python -m core --once                                  # one recorder cycle
python -m core.feeds.espn_stats --backfill 2020-2026   # rebuild game logs
python -m core.backfill --coverage-only                # data coverage report
python -m core.predictions --run                       # predict latest snapshot
python -m core.resolution --backfill                   # attach outcomes
python -m core.shadow_run --bankroll 35.68             # shadow orders (places nothing)
python -m core.backtest --all-fill-models              # backtest
```

## Migrating off this machine

Everything is stock Postgres and plain Docker, so moving is a config change:

1. Provision Postgres (Supabase **Pro** — the free tier pauses after 7 days
   idle and would silently kill the recorder; or any VPS).
2. Point `DATABASE_URL` at it.
3. Restore the latest dump.
4. `docker compose up -d`.

## Troubleshooting

**Recorder not writing.** `docker compose logs recorder --tail 50`. Check
`board_fetch_failed` (upstream/network) versus a DB connection error.

**Predictions skipped.** `skipped_unknown_team` usually means a new franchise —
update `POLYMARKET_TO_ESPN` in `core/team_mapping.py`. `skipped_insufficient`
is normal early season.

**Resolution finds nothing.** Expected until games finish. It only queries
markets whose game started >3h ago.

**Container exited and did not restart.** `docker kill` counts as manual
intervention and will not auto-restart; `docker compose up -d` brings it back.
Real crashes do restart.

## Safety

- The executor is **SHADOW mode with the kill switch on**. It places nothing.
- There is no market-order code path — limit orders only, by construction.
- `.env` is gitignored. Never commit or log credentials.
- Autonomous execution raises `NotImplementedError` by design.
