#!/usr/bin/env python
"""One command that answers "is everything actually working right now?"

Run it before every game night:

    .venv/bin/python scripts/health.py          # wherever the stack lives
    deploy/aws/health.sh                        # from the laptop, checks the server

Two machines, one script
------------------------
Production moved to EC2, and a health surface that still checks the laptop is
worse than none: the operator ran this after cutover and got a wall of red
describing a machine that had been deliberately retired. Red that means
"working as intended" trains people to ignore red.

So the script knows where it is. On the **server** it drops the macOS
sleep-guard check (there is no lid to close), adds uptime, and warns on disk as
a *percentage* — the runbook's 80% promise, which is the number that travels
between a 1 TB laptop and a 100 GB volume. On the **laptop**, if every
container is stopped, it says so in one line instead of eight DEADs.

Detection is `sys.platform` with `--server` / `--laptop` overrides, because a
guess about which machine you are on should be overridable by someone who
knows.

Why this exists: the dashboard reads Supabase only, and the 200ms tick recorder
writes locally. On 2026-08-03 that recorder was dead for 23 hours while the
dashboard looked perfectly healthy, and two games of unrecoverable tick data
were lost. Anything that reports on one database cannot see the other.

The checks themselves live in `core/healthchecks.py`, because the alerter
container evaluates the same set every 5 minutes and pushes to the phone —
two definitions of "healthy" would drift, and the one that pages must not.
This script adds only what a container cannot see: docker ps and pmset.
"""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
import subprocess
import sys

from core.heartbeat import (
    PROVENANCE_OK,
    PROVENANCE_UNKNOWN,
    provenance_verdict,
)
from core.healthchecks import (
    DEAD,
    OK,
    WARN,
    Check,
    check_app_heartbeats,
    check_book_lines,
    check_disk,
    check_disk_headroom,
    check_espn,
    check_fill_watcher,
    check_local_pg_size,
    check_local_ticks,
    check_real_orders,
    check_retention,
    check_primary_db,
    todays_games,
)

UTC = dt.timezone.utc


def check_containers() -> list[Check]:
    expected = {
        "meridian-recorder": "pregame recorder (feeds the dashboard)",
        "meridian-live-recorder": "200ms tick recorder (PULSE)",
        "meridian-live-odds-recorder": "live odds",
        "meridian-kalshi-recorder": "Kalshi recorder (second venue)",
        "meridian-scheduler": "scheduler (predictions)",
        "meridian-api": "dashboard + order path + fill watcher",
        "meridian-alerter": "phone alerts (ntfy)",
        "meridian-postgres": "local Postgres",
        # Overlay engines. Added 2026-09-02 after the health display's silence
        # about them got read as "no PULSE container" by a session that then
        # asked for a redeploy of a running engine — the display could neither
        # confirm nor deny exactly the two processes the research program
        # depends on this month. `espn-live-recorder` rides the same overlay
        # family.
        "meridian-espn-live-recorder": "ESPN live feed (signal side)",
        "meridian-pulse-engine": "PULSE engine (repricing arm + state guards)",
        # Restarted by operator order 2026-09-02 16:04Z; re-bound same day
        # under amendment 10 to the v2 RECORDING engine (quoting policy is
        # v1's, byte-identical — proven on the pinned Aug tape; recording is
        # additive, own-stamp per the B14 fix). Frozen until A1's gate reads
        # (quote-v2-program.md, the freeze-rebind dated line names the
        # commit). MISSING is a real outage: this is the substrate for A1,
        # D1, and the whole v2 program.
        "meridian-quote-engine": "QUOTE engine v2-recording (shadow, frozen; "
                                 "A1/D1/v2 substrate)",
        # GRIDIRON (NFL, 2026-09-02, operator directive — one league, maker
        # only, its own program name; Meridian stays basketball). The venue
        # listed nfl 16 / mlb 50 / cfb 100 events while wnba was dark; the
        # operator's focus ruling cut recording to NFL alone. League-suffixed
        # heartbeat rows (pregame_recorder_nfl / live_recorder_nfl).
        "meridian-nfl-recorder": "GRIDIRON: NFL pregame board",
        "meridian-nfl-live-recorder": "GRIDIRON: NFL live ticks (0.5s)",
        # The NFL quote engine (same engine_v2 as meridian-quote-engine, league
        # nfl). Outside the WNBA freeze; beats as quote_engine_nfl. MISSING
        # before the first slate means nothing quotes NFL and GRIDIRON's
        # descriptive phase accrues zero fills — the whole reason it ships.
        "meridian-gridiron-engine": "GRIDIRON: NFL quote engine (shadow, "
                                    "engine_v2, league=nfl)",
        # Trade-tape trajectory sweepers (hourly, stats only). The WNBA one
        # polls an empty board until listings return — running is correct.
        "meridian-nfl-stats-sweeper": "GRIDIRON: NFL volume trajectory",
        # CFB: recording only, no program, no quoter (2026-09-03) — 100
        # games/Saturday against NFL's 16/week; optionality, not attention.
        "meridian-cfb-recorder": "CFB pregame board (recording only)",
        "meridian-cfb-live-recorder": "CFB live ticks (1s, recording only)",
        "meridian-gridiron-engine": "GRIDIRON quoter — NFL (shadow)",
        "meridian-gridiron-cfb-engine": "GRIDIRON quoter — CFB (shadow)",
        "meridian-wnba-stats-sweeper": "WNBA volume trajectory (empty board "
                                       "until ~Sept 17)",
    }
    try:
        out = subprocess.run(
            ["docker", "compose", "ps", "--format", "{{.Name}} {{.Status}}"],
            capture_output=True, text=True, timeout=30, check=False,
        ).stdout
    except Exception as exc:                                   # pragma: no cover
        return [Check(DEAD, "docker", f"could not query: {exc}")]

    running = {
        line.split(maxsplit=1)[0]: line.split(maxsplit=1)[1]
        for line in out.strip().splitlines() if line.strip()
    }
    #: How many of the expected containers are actually up. main() uses this to
    #: tell "the stack is broken" from "the stack was deliberately stopped".
    check_containers.up_count = sum(
        1 for n in expected if (running.get(n) or "").startswith("Up")
    )
    check_containers.expected_count = len(expected)
    checks = []
    for name, what in expected.items():
        status_text = running.get(name)
        if status_text is None:
            checks.append(Check(DEAD, name.replace("meridian-", ""), f"NOT RUNNING — {what}"))
        elif not status_text.startswith("Up"):
            checks.append(Check(DEAD, name.replace("meridian-", ""), status_text))
        else:
            checks.append(Check(OK, name.replace("meridian-", ""), f"{status_text} — {what}"))
    return checks


def _container_commit(name: str) -> str | None:
    """The MERIDIAN_ENGINE_COMMIT baked into a running container, read from
    docker inspect — the authoritative "what code is this actually running",
    independent of anything the container reports to the DB. None if absent."""
    try:
        out = subprocess.run(
            ["docker", "inspect", "--format",
             "{{range .Config.Env}}{{println .}}{{end}}", name],
            capture_output=True, text=True, timeout=10, check=False).stdout
    except Exception:                                          # pragma: no cover
        return None
    for line in out.splitlines():
        if line.startswith("MERIDIAN_ENGINE_COMMIT="):
            return line.split("=", 1)[1].strip() or None
    return None


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          timeout=10, check=False)


def check_deployed_code() -> list[Check]:
    """Deployed-code audit (the failure class behind three of the night's bugs:
    a container silently running code older than main, the dangerous shape being
    a stale image reporting a false zero — indistinguishable from a quiet venue).

    Compares each RUNNING container's baked commit against the deployed
    checkout's HEAD, BY COMMIT IDENTITY (never grep-for-string):
      * == HEAD                       -> OK
      * ancestor of HEAD, behind by N -> WARN (stale, distance stated)
      * not an ancestor (diverged)    -> DEAD (a finding)
      * commit not in this repo       -> DEAD (unknown ref)
      * NO stamp at all               -> WARN (UNKNOWN PROVENANCE — built without
        the ARG, the exact state we otherwise cannot see; never read as fine)
    Catches both a real stale deploy AND inventing one that isn't there."""
    head = _git("rev-parse", "HEAD")
    if head.returncode != 0:
        return [Check(WARN, "deployed-code",
                      f"cannot read git HEAD: {head.stderr.strip()[:60]}")]
    ref = head.stdout.strip()
    try:
        names = subprocess.run(
            ["docker", "compose", "ps", "--format", "{{.Name}}"],
            capture_output=True, text=True, timeout=30, check=False
        ).stdout.split()
    except Exception as exc:                                   # pragma: no cover
        return [Check(DEAD, "deployed-code", f"could not query docker: {exc}")]
    if not names:
        return [Check(WARN, "deployed-code", "no running containers to audit")]

    checks: list[Check] = []
    for name in sorted(names):
        if name == "meridian-postgres":       # the stock image carries no stamp
            continue
        short = name.replace("meridian-", "")
        commit = _container_commit(name)
        base = provenance_verdict(commit, ref)   # shared identity core
        if base == PROVENANCE_UNKNOWN:
            checks.append(Check(WARN, short,
                                "UNKNOWN PROVENANCE — no commit stamp "
                                "(built without ARG GIT_COMMIT)"))
        elif base == PROVENANCE_OK:
            checks.append(Check(OK, short, f"{commit[:8]} == HEAD"))
        # base == DRIFT: refine with git distance/ancestry (host-only add-on)
        elif _git("merge-base", "--is-ancestor", commit, "HEAD").returncode == 0:
            n = _git("rev-list", "--count", f"{commit}..HEAD").stdout.strip() or "?"
            checks.append(Check(WARN, short,
                                f"STALE — {commit[:8]} is {n} commits behind HEAD"))
        elif _git("cat-file", "-e", commit).returncode == 0:
            checks.append(Check(DEAD, short,
                                f"DIVERGED — {commit[:8]} is not an ancestor of HEAD"))
        else:
            checks.append(Check(DEAD, short,
                                f"UNKNOWN COMMIT — {commit[:8]} is not in this repo"))
    return checks


def check_sleep_guard() -> list[Check]:
    """A sleeping Mac is a hole in an unrecoverable stream.

    Checks the assertions actually held by the OS rather than whether a
    `caffeinate` process exists — a caffeinate started without flags only
    prevents idle sleep, and would look identical in `ps`.
    """
    try:
        out = subprocess.run(
            ["pmset", "-g", "assertions"],
            capture_output=True, text=True, timeout=15, check=False,
        ).stdout
    except Exception as exc:
        return [Check(WARN, "sleep guard", f"could not query pmset: {exc}")]

    def held(name: str) -> bool:
        for line in out.splitlines():
            if name in line and line.strip().split()[-1] != "0":
                return True
        return False

    idle = held("PreventUserIdleSystemSleep")
    if not idle:
        return [Check(WARN, "sleep guard", "NOT running — see step 1 (caffeinate -dims)")]

    on_battery = "Battery Power" in subprocess.run(
        ["pmset", "-g", "batt"], capture_output=True, text=True, timeout=15, check=False,
    ).stdout
    if on_battery:
        # -s is documented as valid only on AC power.
        return [Check(WARN, "sleep guard", "held, but ON BATTERY — plug in before tipoff")]
    return [Check(OK, "sleep guard", "caffeinate active, on AC power")]


def detect_environment(argv_flag: str | None) -> str:
    """'server' or 'laptop'. Explicit flag wins over the guess."""
    if argv_flag:
        return argv_flag
    return "laptop" if sys.platform == "darwin" else "server"


def check_uptime() -> list[Check]:
    """The server replacement for the sleep guard.

    A Mac sleeping is a hole in an unrecoverable stream; an EC2 instance has no
    lid, so the equivalent question is "did this box reboot without anyone
    noticing, and did the stack come back?". Compose services are
    `restart: unless-stopped` and docker is enabled at boot, so a recent reboot
    is not itself a fault — an unexplained one is worth seeing.
    """
    try:
        with open("/proc/uptime") as fh:
            seconds = float(fh.read().split()[0])
    except Exception as exc:
        return [Check(WARN, "uptime", f"could not read /proc/uptime: {str(exc)[:40]}")]
    hours = seconds / 3600.0
    if hours < 1.0:
        return [Check(WARN, "uptime",
                      f"up {seconds / 60:.0f} min — recent reboot; confirm the "
                      "stack came back and no slate was missed")]
    if hours < 24:
        return [Check(OK, "uptime", f"up {hours:.1f} h")]
    return [Check(OK, "uptime", f"up {hours / 24:.1f} days")]


def check_docker_enabled() -> list[Check]:
    """Docker enabled at boot is what makes `restart: unless-stopped` mean
    anything after a reboot. Without it the stack simply does not return."""
    if not shutil.which("systemctl"):
        return []
    out = subprocess.run(["systemctl", "is-enabled", "docker"],
                         capture_output=True, text=True, timeout=15,
                         check=False).stdout.strip()
    if out == "enabled":
        return [Check(OK, "docker at boot", "enabled")]
    return [Check(WARN, "docker at boot",
                  f"{out or 'unknown'} — the stack will NOT return after a reboot")]


RETIRED_NOTE = (
    "local stack retired — production is the server; "
    "run deploy/aws/health.sh"
)


def main() -> int:
    parser = argparse.ArgumentParser(prog="meridian-health")
    env = parser.add_mutually_exclusive_group()
    env.add_argument("--server", dest="env", action="store_const", const="server",
                     help="force the server profile (skip macOS checks)")
    env.add_argument("--laptop", dest="env", action="store_const", const="laptop",
                     help="force the laptop profile")
    args = parser.parse_args()
    where = detect_environment(args.env)

    stamp = dt.datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    print(f"\n\033[1mMERIDIAN HEALTH\033[0m  {stamp}  \033[2m({where})\033[0m")
    print("=" * 72)

    containers = check_containers()
    up = getattr(check_containers, "up_count", None)

    # A deliberately stopped laptop stack is not an outage, and eight DEAD lines
    # saying so is how red stops meaning anything. Nothing is up AND we are on
    # the retired machine: say it once, calmly, and point at the real one.
    if where == "laptop" and up == 0:
        print(f"\n\033[33m{RETIRED_NOTE}\033[0m")
        print("\n" + "=" * 72)
        print("Verdict: \033[32mALL GOOD\033[0m — nothing is expected to run here\n")
        return 0

    games, live = todays_games()
    print("\n\033[1mToday's games\033[0m")
    print("\n".join(games) if games else "  none scheduled")
    if live:
        print("  \033[33m>> A GAME IS LIVE — the tick recorder must be writing.\033[0m")

    if where == "server":
        host = check_uptime() + check_docker_enabled() + check_disk_headroom() + check_disk()
    else:
        host = check_sleep_guard() + check_disk()

    groups: list[tuple[str, list[Check]]] = [
        ("Host", host),
        ("Containers", containers),
        # Deployed-code audit: server-only (needs docker inspect + the deployed
        # git checkout). "in main != in production" made enforceable.
        *([("Deployed code", check_deployed_code())] if where == "server" else []),
        ("Data feeds", check_espn() + check_book_lines()),
        ("Heartbeats", check_app_heartbeats()),
        ("Databases", check_primary_db(live) + check_local_ticks(live)
                      + check_local_pg_size() + check_retention()),
        ("Safety", check_real_orders() + check_fill_watcher()),
    ]

    worst = OK
    for title, checks in groups:
        print(f"\n\033[1m{title}\033[0m")
        for chk in checks:
            print("  " + chk.render())
            if chk.status == DEAD:
                worst = DEAD
            elif chk.status == WARN and worst == OK:
                worst = WARN

    print("\n" + "=" * 72)
    verdict = {OK: "\033[32mALL GOOD\033[0m",
               WARN: "\033[33mDEGRADED — read the WARN lines\033[0m",
               DEAD: "\033[31mSOMETHING IS DOWN — read the DEAD lines\033[0m"}[worst]
    print(f"Verdict: {verdict}\n")
    return 0 if worst != DEAD else 1


if __name__ == "__main__":
    sys.exit(main())
