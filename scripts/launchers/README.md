# Launchers

The host-side scripts cron runs to start a game's instruments, and the
nightly verdict. Until 2026-09-21 these lived only in
`/opt/meridian/artifacts/reads/` on the box, written by hand over ssh; a
retired launcher there kept a `--budget-usd 2 --cooldown 10` pair alive for
a night after the code had dropped both, and a wrapper grepped its database
URL out of a sibling script and broke when that sibling was retired. They
are versioned here so a test can pin what they pass.

| script | what it starts | costs REST budget |
|---|---|---|
| `launch_stream_exec.sh <slug> <min> [floor] [fresh_s]` | the stream detector: one ticket per fresh crossing over the floor | no |
| `launch_stream_slate.sh <league> <min> <tag>` | the stream recorder for a kickoff window, into `reads/stream/<tag>/` | no |
| `launch_ladder.sh <slug> <min> [ws]` | the REST executor for the desk; `ws` adds the REST-vs-stream comparator | yes (two with `ws`) |
| `launch_sampler.sh <slug> <min>` | read-only REST sampler, no tickets (basketball, baseball) | yes |
| `slate_verdict.sh` | nightly: instants table, settlement P&L, edge ledger; pushes the headline | no |
| `schedule_ping.sh --hours 24` / `--starting-within 15` | the day's slate to the phone; tipoff pings | no |
| `slate_fast.py`, `slate_pnl.py` | run inside the api image by `slate_verdict.sh` | no |

`scripts/schedule_slate.py` writes the cron lines that call these; the
constant `RECORDER_LOOKAHEAD_H` there must equal `--lookahead-hours` in
`launch_stream_slate.sh`, and `tests/test_schedule_slate.py` checks it.
Deploy: `install -m 755` each into `/opt/meridian/scripts/launchers/` on the
box; the copies under `artifacts/reads/` are what tonight's already-installed
cron lines call and stay until those have fired.
