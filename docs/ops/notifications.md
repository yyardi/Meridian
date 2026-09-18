# Notifications: what reaches the phone

Everything Meridian pushes goes to one ntfy topic (`MERIDIAN_NTFY_TOPIC` in
`.env`; the topic is the auth, never print it). By 2026-09-18 seven senders
shared it and the operator was getting five to seven summaries a day plus
health flaps. The fix is one switch, not seven edits.

## The senders and their kinds

| kind | sender | what it is |
|---|---|---|
| `tickets` | `cfb/run_ladder_executor.py push()`, `cfb/run_live_ladder.py alert()` | the two-leg order ticket a person places |
| `health` | `core/alerter.py` | the 5-minute health checks: DEAD / recovered / 30-min WARN / daily digest |
| `ev` | `core/ev_guard.py` (started by `core/api.py`) | EDGE-GONE transitions on open button positions |
| `retention` | `core/retention.py` | rolling-archive verification failures |
| `alarm` | `scripts/alarm_v5.py` | recorder silent / venue price freeze |
| `listing` | `scripts/league_listing_watch.py` | a watched league first lists on the venue |
| `nightly` | `scripts/nightly_scan.sh`, `nightly_ladder.sh`, `nightly_code_drift.sh`, `nightly_tt_elo.sh`, `prod_weekend_read.sh` | cron summaries |

Python senders call `core.notify.push(kind, title, body)`; the shell scripts
ask `python3 scripts/ntfy_allowed.py nightly` before their `curl`. Nothing
else in the repo POSTs to ntfy (`tests/test_notify_scope.py` sweeps for it).

## The switch

```
MERIDIAN_NTFY_SCOPE=tickets          # default when unset: order tickets only
MERIDIAN_NTFY_SCOPE=tickets,health   # comma list of kinds
MERIDIAN_NTFY_SCOPE=all              # everything (the pre-switch behaviour)
```

Containers read it from their environment (`.env` via compose); the cron
scripts run on the host and read the `MERIDIAN_NTFY_SCOPE=` line of
`/opt/meridian/.env` themselves. Changing the line takes effect on the next
push for the cron scripts and after a restart for the containers.

## Where muted pushes go

A push outside the scope is not dropped. Python senders append one JSON line
`{ts, kind, title, body}` to `<repo>/artifacts/reads/ntfy_muted.log`
(absolute, resolved from `core/notify.py`, so the working directory never
decides; `MERIDIAN_NTFY_MUTED_LOG` overrides the path, and docker-compose.yml
sets it on the `api` and `alerter` services to the host-mounted
`/opt/meridian/artifacts/reads/ntfy_muted.log` — without that the line would
land in the image's `/app` and vanish on recreate); the cron scripts append a
tab-separated `timestamp  nightly  message` line to
`/opt/meridian/artifacts/reads/ntfy_muted.log`. The topic is never written
there. So "did the retention job try to page me while I had it muted?" is a
`grep retention` away, and widening the scope later loses nothing already
recorded.

Muted counts as handled for the alerter's state machine: a muted digest is
marked sent (it is on disk), and a DEAD transition is still a transition.
The alerter still refuses to start without a topic; the scope decides what
the topic receives, not whether the alerter runs.

## How to widen

1. Set `MERIDIAN_NTFY_SCOPE=tickets,health` (or `all`) in `/opt/meridian/.env`.
2. Restart the containers that push (`alerter`, `api`) so they re-read it;
   the cron scripts pick it up on their next run.
3. `tail artifacts/reads/ntfy_muted.log` to see what you were not getting.
