"""One switch decides what reaches the phone; everything else lands on disk.

    pytest --noconftest tests/test_notify_scope.py

The operator was getting five to seven summary pushes a day plus health flaps
on the ticket topic and asked for tickets only. Seven senders each carried
their own POST, so "tickets only" could not be a setting. Now it is one:
MERIDIAN_NTFY_SCOPE, read by `core.notify` (Python senders) and by
`scripts/ntfy_allowed.py` (the cron scripts). These tests pin the default,
the parsing, the mute-to-disk path, the send path, and -- the part a review
cannot see -- that every sender in the inventory actually goes through it.
"""
from __future__ import annotations

import ast
import importlib
import io
import json
import pathlib
import subprocess
import sys
import tokenize

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import notify

#: The inventory (verified 2026-09-18): every process that pushed to the topic.
PYTHON_SENDERS = {
    "cfb/run_ladder_executor.py": "tickets",
    "cfb/run_live_ladder.py": "tickets",
    "core/alerter.py": "health",
    "core/ev_guard.py": "ev",
    "core/api.py": "ev",
    "core/retention.py": "retention",
    "scripts/alarm_v5.py": "alarm",
    "scripts/league_listing_watch.py": "listing",
}
SHELL_SENDERS = [
    "scripts/nightly_scan.sh",
    "scripts/nightly_ladder.sh",
    "scripts/nightly_code_drift.sh",
    "scripts/nightly_tt_elo.sh",
    "scripts/prod_weekend_read.sh",
]
DOORS = {"core/notify.py", "scripts/ntfy_allowed.py"}

#: What a second door would have to name. Before the door (git HEAD of
#: 2026-09-18) the senders used three forms, and a sweep for the literal
#: "https://ntfy.sh/" caught none of them: `'https://ntfy.sh').rstrip("/")`
#: + `httpx.post(base, json={"topic": ...})` (alerter, ev_guard) and
#: f"{server}/{topic}" with server from MERIDIAN_NTFY_SERVER + urlopen
#: (league_listing_watch).
NTFY_NAMES = ("ntfy.sh", "MERIDIAN_NTFY_SERVER", "MERIDIAN_NTFY_TOPIC")
TRANSPORT = ("urlopen(", "httpx.post(", "requests.post(")
#: Non-door files that may name the TOPIC in code, and why: each is a gate
#: ("is there a phone at all?") that reads the variable and sends nothing
#: itself. The alerter also reads MERIDIAN_NTFY_SERVER, only to hand it to
#: the door as `server=`. Anything else that names ntfy is a second door.
NTFY_NAME_ALLOWLIST = {
    "cfb/run_ladder_executor.py": "push() returns False without a topic",
    "cfb/run_live_ladder.py": "alert() returns False without a topic",
    "core/alerter.py": "main() refuses to start without a topic; Notifier passes server= to the door",
    "core/api.py": "the EV guard is not started without a topic",
    "scripts/alarm_v5.py": "main() prints [would page] without a topic",
    "scripts/check_staged_secrets.py": "the secret scanner's regex names the variable in order to catch it",
}
#: The one allowlisted file that also opens a URL: alarm_v5's deadman
#: heartbeat (MERIDIAN_HEARTBEAT_URL), a GET to the monitor, not a push.
TRANSPORT_EXEMPT = {"scripts/alarm_v5.py": "MERIDIAN_HEARTBEAT_URL"}


def code_only(src: str) -> str:
    """The source with comments and docstrings removed, so a sweep reads what
    runs. A docstring that says "the door reads MERIDIAN_NTFY_TOPIC" is not a
    door; `httpx.post(base, json={"topic": topic})` is."""
    tree = ast.parse(src)
    doc_pos = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                doc_pos.add((body[0].value.lineno, body[0].value.col_offset))
    # Blank the dropped tokens in place (by row/col) so every other token
    # keeps its spelling: "urlopen(" must still read "urlopen(".
    lines = src.splitlines(keepends=True)
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT or (tok.type == tokenize.STRING and tok.start in doc_pos):
            (r0, c0), (r1, c1) = tok.start, tok.end
            for r in range(r0, r1 + 1):
                line = lines[r - 1]
                a = c0 if r == r0 else 0
                b = c1 if r == r1 else len(line.rstrip("\r\n"))
                lines[r - 1] = line[:a] + " " * (b - a) + line[b:]
    return "".join(lines)


def ntfy_offence(rel: str, code: str) -> str | None:
    """Why this non-door, non-test file is a second door to the phone, or
    None. `code` is the file after `code_only`."""
    names = [n for n in NTFY_NAMES if n in code]
    if not names:
        return None
    if "ntfy.sh" in code:
        return "holds the server literal ntfy.sh (only the door may)"
    if "MERIDIAN_NTFY_SERVER" in code and rel != "core/alerter.py":
        return "reads MERIDIAN_NTFY_SERVER (only the door builds a URL from it)"
    if rel not in NTFY_NAME_ALLOWLIST:
        return f"names {names} and is not an allowlisted topic gate"
    transport = [t for t in TRANSPORT if t in code]
    if transport and rel not in TRANSPORT_EXEMPT:
        return f"names {names} and calls {transport}"
    return None


@pytest.fixture
def quiet_env(monkeypatch, tmp_path):
    """No scope, no topic, a private muted log, and a network that fails loudly."""
    monkeypatch.delenv("MERIDIAN_NTFY_SCOPE", raising=False)
    monkeypatch.delenv("MERIDIAN_NTFY_TOPIC", raising=False)
    monkeypatch.delenv("MERIDIAN_NTFY_SERVER", raising=False)
    log = tmp_path / "muted.log"
    monkeypatch.setenv("MERIDIAN_NTFY_MUTED_LOG", str(log))

    def no_network(req, timeout=None):
        raise AssertionError("a push reached the network")

    monkeypatch.setattr(notify, "urlopen", no_network)
    return log


# --------------------------------------------------------------------------- #
# The switch
# --------------------------------------------------------------------------- #


def test_default_scope_is_tickets_and_the_schedule(quiet_env):
    assert notify.scope() == frozenset({"tickets", "schedule"})
    assert notify.allowed("tickets") and notify.allowed("schedule")
    # "schedule" joined the default because it is the one message the desk
    # cannot replace: the board shows what is running, not what is on later.
    for kind in notify.KINDS:
        if kind not in ("tickets", "schedule"):
            assert not notify.allowed(kind), kind


def test_all_means_every_kind(monkeypatch):
    monkeypatch.setenv("MERIDIAN_NTFY_SCOPE", "all")
    assert notify.scope() == frozenset(notify.KINDS)
    assert all(notify.allowed(k) for k in notify.KINDS)


@pytest.mark.parametrize("raw", ["tickets,health", " tickets , health ", '"tickets,health"',
                                 "HEALTH,tickets"])
def test_comma_lists_and_whitespace_and_quotes(monkeypatch, raw):
    monkeypatch.setenv("MERIDIAN_NTFY_SCOPE", raw)
    assert notify.allowed("tickets") and notify.allowed("health")
    assert not notify.allowed("nightly") and not notify.allowed("ev")


def test_blank_scope_is_the_default_and_unknown_kinds_never_pass(monkeypatch):
    monkeypatch.setenv("MERIDIAN_NTFY_SCOPE", "   ")
    assert notify.scope() == frozenset({"tickets", "schedule"})
    monkeypatch.setenv("MERIDIAN_NTFY_SCOPE", "all")
    assert not notify.allowed("everything"), "a kind outside KINDS is never allowed"


# --------------------------------------------------------------------------- #
# push(): mute to disk, send when allowed, never raise
# --------------------------------------------------------------------------- #


def test_push_mutes_to_the_log_and_never_raises_without_a_topic(quiet_env):
    log = quiet_env
    assert notify.push("health", "espn DEAD", "x" * 1000, priority=5) == "muted"
    assert notify.push("nightly", "Meridian nightly scan", "0 cells") == "muted"
    lines = [json.loads(ln) for ln in log.read_text(encoding="utf-8").splitlines()]
    assert [ln["kind"] for ln in lines] == ["health", "nightly"]
    assert lines[0]["title"] == "espn DEAD" and len(lines[0]["body"]) == 400
    assert set(lines[0]) == {"ts", "kind", "title", "body"}


def test_muting_happens_before_the_topic_is_consulted(quiet_env, monkeypatch):
    """A muted push is recorded whether or not a topic is configured: the log
    is the record of what WOULD have been pushed."""
    monkeypatch.setenv("MERIDIAN_NTFY_TOPIC", "secret-topic")
    assert notify.push("ev", "EDGE GONE", "body") == "muted"
    text = quiet_env.read_text(encoding="utf-8")
    assert "EDGE GONE" in text and "secret-topic" not in text


def test_allowed_kind_without_a_topic_is_no_topic_not_an_error(quiet_env):
    assert notify.push("tickets", "Meridian order intent", "legs") == "no_topic"
    assert not quiet_env.exists(), "no_topic is not muted; nothing is logged"


def test_push_with_an_allowed_kind_sends(monkeypatch, tmp_path):
    from urllib.parse import parse_qs, urlsplit

    captured = {}

    class Resp:
        def read(self):
            return b"{}"

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["data"] = req.data
        captured["method"] = req.get_method()
        captured["timeout"] = timeout
        return Resp()

    monkeypatch.setattr(notify, "urlopen", fake_urlopen)
    monkeypatch.delenv("MERIDIAN_NTFY_SCOPE", raising=False)
    monkeypatch.setenv("MERIDIAN_NTFY_TOPIC", '"topic-x"')
    monkeypatch.setenv("MERIDIAN_NTFY_SERVER", "https://ntfy.example/")
    monkeypatch.setenv("MERIDIAN_NTFY_MUTED_LOG", str(tmp_path / "muted.log"))
    assert notify.push("tickets", "Meridian order intent — go", "LADDER INTENT ¢",
                       priority=4, tags=["a", "b"], timeout=10) == "sent"
    parts = urlsplit(captured["url"])
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == "https://ntfy.example/topic-x"
    q = parse_qs(parts.query)
    assert q["title"] == ["Meridian order intent — go"]
    assert q["priority"] == ["4"] and q["tags"] == ["a,b"]
    assert captured["data"] == "LADDER INTENT ¢".encode()
    assert captured["method"] == "POST" and captured["timeout"] == 10
    assert not (tmp_path / "muted.log").exists()


def test_a_network_failure_is_failed_not_an_exception(monkeypatch):
    def boom(req, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr(notify, "urlopen", boom)
    monkeypatch.setenv("MERIDIAN_NTFY_SCOPE", "all")
    monkeypatch.setenv("MERIDIAN_NTFY_TOPIC", "t")
    assert notify.push("alarm", "x", "y") == "failed"


def test_an_unwritable_muted_log_does_not_raise(quiet_env, monkeypatch, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv("MERIDIAN_NTFY_MUTED_LOG", str(blocker / "muted.log"))
    assert notify.push("health", "x", "y") == "muted"


# --------------------------------------------------------------------------- #
# scripts/ntfy_allowed.py: the same rule for the host-side cron scripts
# --------------------------------------------------------------------------- #


def _run_allowed(kind: str, env: dict) -> int:
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "ntfy_allowed.py"), kind],
                          env=env, capture_output=True, text=True, check=False).returncode


def test_ntfy_allowed_cli_reads_the_environment_first():
    base = {"PATH": "/usr/bin:/bin"}
    assert _run_allowed("nightly", {**base, "MERIDIAN_NTFY_SCOPE": "tickets"}) == 1
    assert _run_allowed("nightly", {**base, "MERIDIAN_NTFY_SCOPE": "tickets,nightly"}) == 0
    assert _run_allowed("nightly", {**base, "MERIDIAN_NTFY_SCOPE": "all"}) == 0
    assert _run_allowed("tickets", {**base, "MERIDIAN_NTFY_SCOPE": "health"}) == 1
    assert _run_allowed("bogus", {**base, "MERIDIAN_NTFY_SCOPE": "all"}) == 2


def test_ntfy_allowed_falls_back_to_the_env_file_and_only_that_line(tmp_path):
    na = importlib.import_module("scripts.ntfy_allowed")
    env_file = tmp_path / ".env"
    # The decoy line is deliberately NOT a credential name: the staged-secret
    # hook refuses any `MERIDIAN_NTFY_TOPIC=<literal>` in a public repo, and a
    # fixture is not worth an ALLOWED entry.
    env_file.write_text("MERIDIAN_NTFY_SERVER=https://example.invalid\nexport MERIDIAN_NTFY_SCOPE=\"tickets,nightly\"\n",
                        encoding="utf-8")
    assert na.is_allowed("nightly", env={}, env_file=env_file)
    assert not na.is_allowed("health", env={}, env_file=env_file)
    # the environment wins over the file
    assert not na.is_allowed("nightly", env={"MERIDIAN_NTFY_SCOPE": "tickets"}, env_file=env_file)
    # no file, no variable: the default, tickets only
    assert not na.is_allowed("nightly", env={}, env_file=tmp_path / "absent")
    assert na.is_allowed("tickets", env={}, env_file=tmp_path / "absent")


@pytest.mark.parametrize("line, nightly", [
    ("MERIDIAN_NTFY_SCOPE=all # everything", True),
    ("MERIDIAN_NTFY_SCOPE=tickets,nightly\t# widened 09-18", True),
    ('MERIDIAN_NTFY_SCOPE="tickets,nightly" # quoted, then a comment', True),
    ("MERIDIAN_NTFY_SCOPE='all'", True),
    ("MERIDIAN_NTFY_SCOPE=tickets # nightly", False),
    ("MERIDIAN_NTFY_SCOPE=tickets#nightly", False),   # no space: compose keeps it, one unknown kind
])
def test_ntfy_allowed_reads_the_env_file_value_the_way_compose_does(tmp_path, line, nightly):
    """Compose strips an unquoted ` # ...` suffix and ends a quoted value at
    its closing quote. The host gate must read the same value, or one .env
    line opens the containers and mutes the cron scripts."""
    na = importlib.import_module("scripts.ntfy_allowed")
    env_file = tmp_path / ".env"
    env_file.write_text("MERIDIAN_NTFY_SERVER=https://example.invalid\n" + line + "\n", encoding="utf-8")
    assert na.is_allowed("nightly", env={}, env_file=env_file) is nightly


def test_the_default_muted_log_is_absolute_and_ignores_the_cwd(monkeypatch, tmp_path):
    """Both push-carrying containers start in /app and the cron scripts in
    whatever cwd cron gives them; a relative default would scatter the muted
    lines. `MERIDIAN_NTFY_MUTED_LOG` still overrides (compose sets it to the
    host-mounted path)."""
    monkeypatch.delenv("MERIDIAN_NTFY_MUTED_LOG", raising=False)
    here = notify.muted_log_path()
    assert here.is_absolute()
    assert here == ROOT / "artifacts" / "reads" / "ntfy_muted.log"
    monkeypatch.chdir(tmp_path)
    assert notify.muted_log_path() == here
    monkeypatch.setenv("MERIDIAN_NTFY_MUTED_LOG", str(tmp_path / "m.log"))
    assert notify.muted_log_path() == tmp_path / "m.log"


def test_alerter_test_push_fails_when_the_scope_mutes_it(tmp_path):
    """`python -m core.alerter --test` is the channel check the README sends
    the operator to. Under the default scope the push is muted: the phone got
    nothing, so exit 0 would be a false green. It must exit 1 and say why."""
    env = {"PATH": "/usr/bin:/bin", "MERIDIAN_NTFY_TOPIC": "test-topic-never-used",
           "MERIDIAN_NTFY_MUTED_LOG": str(tmp_path / "muted.log"),
           "MERIDIAN_EV_GUARD": "0", "MERIDIAN_FILL_WATCHER": "0"}
    r = subprocess.run([sys.executable, "-m", "core.alerter", "--test"], cwd=ROOT, env=env,
                       capture_output=True, text=True, check=False, timeout=120)
    assert r.returncode == 1, r.stderr[-800:]
    assert "test push: muted" in r.stderr and "MERIDIAN_NTFY_SCOPE" in r.stderr
    assert str(tmp_path / "muted.log") in r.stderr
    lines = (tmp_path / "muted.log").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["kind"] == "health"
    assert "test-topic-never-used" not in r.stdout + r.stderr


# --------------------------------------------------------------------------- #
# The sweep: every sender goes through the door, and no second door exists
# --------------------------------------------------------------------------- #


def test_every_python_sender_routes_through_core_notify():
    for rel, kind in PYTHON_SENDERS.items():
        src = (ROOT / rel).read_text(encoding="utf-8")
        assert "core.notify" in src or "from core import notify" in src, rel
        assert f'"{kind}"' in src, f"{rel} must name its kind {kind!r}"


def test_every_shell_sender_asks_ntfy_allowed_before_curling():
    for rel in SHELL_SENDERS:
        src = (ROOT / rel).read_text(encoding="utf-8")
        gate = src.index('ntfy_allowed.py" nightly')
        assert 0 < gate < src.index("curl "), f"{rel}: the gate must precede the curl"
        assert "ntfy_muted.log" in src, f"{rel}: the muted branch must log the message"
        # rc 1 is "muted by the scope"; rc 2 (bad kind), 127 (no python3) or an
        # ImportError from a stale checkout is a broken gate and must not be
        # written up as the operator's choice.
        assert 'RC_GATE=0; python3 "$(dirname "$0")/ntfy_allowed.py" nightly || RC_GATE=$?' in src, rel
        assert '[ "$RC_GATE" -eq 1 ]' in src and 'ntfy gate failed rc=$RC_GATE' in src, rel
        assert subprocess.run(["bash", "-n", str(ROOT / rel)], check=False).returncode == 0


def test_no_second_door_to_ntfy_in_python_outside_the_doors():
    """The shell scripts keep their curl behind the gate (by design: they run
    on the host without the venv); every PYTHON push goes through the door.
    Swept on code (comments and docstrings stripped) for any ntfy name, with
    the topic gates allowlisted by file -- not for one literal URL spelling,
    which is what the senders never used (see NTFY_NAMES)."""
    from repo_tree import rel, repo_files

    offenders = {}
    for path in list(repo_files(".py")) + [ROOT / "core/notify.py", ROOT / "scripts/ntfy_allowed.py"]:
        r = rel(path)
        if r in DOORS or r.startswith("tests/"):
            continue
        why = ntfy_offence(r, code_only(path.read_text(encoding="utf-8")))
        if why:
            offenders[r] = why
    assert offenders == {}
    # the allowlist is not stale: every entry still names ntfy in code, so a
    # file that stops being a gate is removed here rather than kept open
    for r in NTFY_NAME_ALLOWLIST:
        code = code_only((ROOT / r).read_text(encoding="utf-8"))
        assert any(n in code for n in NTFY_NAMES), f"{r} no longer names ntfy: drop it from the allowlist"
        assert "MERIDIAN_NTFY_TOPIC" in code, f"{r}: an allowlisted file is a topic gate"
    # the transport exemption is exactly the heartbeat, and there is one such call
    alarm = code_only((ROOT / "scripts/alarm_v5.py").read_text(encoding="utf-8"))
    assert "MERIDIAN_HEARTBEAT_URL" in alarm and alarm.count("urlopen(") == 1
    assert "https://ntfy.sh" in (ROOT / "core/notify.py").read_text(encoding="utf-8"), (
        "the sweep is only meaningful if the door itself holds the URL")


@pytest.mark.parametrize("rel_, src", [
    # core/alerter.py and core/ev_guard.py at HEAD before the door
    ("core/ev_guard.py",
     'base = (server or os.environ.get("MERIDIAN_NTFY_SERVER") or "https://ntfy.sh").rstrip("/")\n'
     'r = httpx.post(base, json={"topic": topic, "title": title, "message": body})\n'),
    # scripts/league_listing_watch.py at HEAD before the door
    ("scripts/league_listing_watch.py",
     'topic = os.environ["MERIDIAN_NTFY_TOPIC"]\n'
     'server = os.environ.get("MERIDIAN_NTFY_SERVER", "https://ntfy.sh")\n'
     'req = urllib.request.Request(f"{server}/{topic}", data=body.encode(), method="POST")\n'
     'return urllib.request.urlopen(req, timeout=20).status\n'),
    # the form the old sweep DID catch
    ("core/whatever.py", 'requests.post("https://ntfy.sh/" + topic, data=body)\n'),
    # a new sender that names only the topic and opens a URL
    ("core/newthing.py", 't = os.environ.get("MERIDIAN_NTFY_TOPIC")\nurlopen(Request(u, data=b))\n'),
    # an allowlisted gate that grows a transport
    ("cfb/run_ladder_executor.py", 't = os.environ.get("MERIDIAN_NTFY_TOPIC")\nhttpx.post(u, data=b)\n'),
    # a topic read in a file nobody allowlisted
    ("scripts/new_cron.py", 't = os.environ.get("MERIDIAN_NTFY_TOPIC")\n'),
    # the server named outside the alerter, even with no transport in sight
    ("core/api.py", 's = os.environ.get("MERIDIAN_NTFY_SERVER")\n'),
])
def test_the_sweep_fails_on_every_form_a_sender_used_before_the_door(rel_, src):
    assert ntfy_offence(rel_, code_only(src)), (rel_, src)


def test_the_sweep_passes_a_topic_gate_and_ignores_prose():
    gate = 'topic = os.environ.get("MERIDIAN_NTFY_TOPIC", "").strip()\nif not topic:\n    return False\n'
    assert ntfy_offence("cfb/run_ladder_executor.py", code_only(gate)) is None
    prose = '"""ntfy.sh: the door reads MERIDIAN_NTFY_SERVER and MERIDIAN_NTFY_TOPIC."""\n# https://ntfy.sh/x\nx = 1\n'
    assert code_only(prose).split() == ["x", "=", "1"], code_only(prose)
    assert ntfy_offence("core/anything.py", code_only(prose)) is None


def test_the_door_carries_nothing_the_executor_test_bans():
    """cfb/run_ladder_executor.py imports core.notify, and its test bans these
    strings from the executor's own source; the door must be equally clean."""
    src = (ROOT / "core/notify.py").read_text(encoding="utf-8")
    for bad in ("place_order", "submit_order", "create_order", "MERIDIAN_ORDER_TOKEN",
                "requests.post", "httpx", "/orders", "PolymarketOrderClient", "print("):
        assert bad not in src, bad
    assert "urllib" in src

