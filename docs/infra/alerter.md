# The alerter — how the machine reports while nobody is looking

Built 2026-08-07 for a two-week unattended stretch. Every outage this project
has had was caught by a human happening to look; the alerter is the looking,
containerized (`meridian-alerter`), evaluating **the same checks as
`scripts/health.py`** every 5 minutes and pushing to the phone via
[ntfy.sh](https://ntfy.sh) (`MERIDIAN_NTFY_TOPIC` in `.env` — the topic is the
auth, treat it like a password).

## When it pushes

| trigger | timing | priority |
|---|---|---|
| any check transitions to DEAD | immediately | urgent |
| a DEAD check recovers | immediately | default |
| a WARN persists 30 minutes | once | high |
| disk free < 20 GB · Supabase > 400 MB | on arrival (slow burns that end in data loss) | high |
| a pending exit enters FAILED | immediately, **per row** | urgent |
| daily digest | 9:00 CT, **always — green or not** | default/high |
| container start | immediately (doubles as the reboot notification) | default |

Transitions only, never states: a check that stays DEAD does not re-push every
5 minutes. An alarm that spams gets muted, and a muted alarm is worse than none.

## The digest is the alerter's own heartbeat

B11's lesson applied to the alarm itself: a watchdog whose death is silent
re-creates the exact ambiguity it exists to remove. The 9:00 CT digest always
sends — verdict, per-service heartbeat ages, games with live ticks in 24h, the
Kalshi gate count (matched games vs the 10-game gate), order/exit state — so
**no digest by ~9:05 CT means the alerter (or the machine) is down**, and a
green digest is a daily proof of life. If it was down at 9:00 it sends on
recovery: a late digest beats a missing one. It also beats `service_heartbeats`
every cycle, so `health.py` and `/api/status` judge it like any writer.

## One definition of healthy

The checks live in [`core/healthchecks.py`](../../core/healthchecks.py),
imported by both `scripts/health.py` (which adds the host-only checks: docker
ps, pmset) and the alerter. Two implementations would drift, and the copy that
pages the phone is the one that must not.

Container specifics: the alerter reads local Postgres at `postgres:5432` (not
the host's `localhost:5433`) via `MERIDIAN_LOCAL_DATABASE_URL`, and measures
**host** disk via a bind-mounted directory (`MERIDIAN_DISK_PATH=/hostdisk`) —
statvfs inside the Docker VM would report the VM's overlay, not the disk that
actually fills.

## Operator notes

* **Testing restart-resilience:** `docker kill`/`docker stop` do NOT exercise
  `restart: unless-stopped` — Docker treats CLI stops as operator intent and
  leaves the container down (measured 2026-08-07). A real crash does restart
  it: kill the process *inside* the container and it is back in ~10 s, with
  the startup push as the receipt.

* Test the channel: `docker compose exec alerter python -m core.alerter --test`
* The alerter **refuses to start** without `MERIDIAN_NTFY_TOPIC` (crash-loop,
  visible in `docker compose ps` and health.py) — running silently while
  looking covered would be worse.
* Push failures are logged and swallowed; the loop keeps evaluating. The
  missed digest is what reveals a broken channel.
* No retention, no cleanup, no automatic action of any kind is taken on any
  alert — tick data is unrecoverable and deletion is a human decision.
