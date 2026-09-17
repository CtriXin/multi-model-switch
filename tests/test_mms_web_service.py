"""`mms web status|url|start|stop|restart` manage the detached Pilot (issue #188)."""
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _free_port_base() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _run(args, *, home: Path, timeout=90, extra_env=None):
    env = {k: v for k, v in os.environ.items()
           if k not in ("MMS_CONFIG_ROOT", "MMS_CONFIG_DIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME",
                        "MMS_REAL_HOME", "REAL_HOME", "ORIGINAL_HOME", "MMS_WEB_PORT_BASE",
                        "MMS_COMMAND_NAME")}
    env.update({"HOME": str(home), "MMS_REAL_HOME": str(home), "PYTHONPATH": str(ROOT)})
    env.update(extra_env or {})
    return subprocess.run([sys.executable, "-P", "-m", "mms_web", *args], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=timeout)


@pytest.fixture
def home(tmp_path):
    (tmp_path / "config").mkdir()
    return tmp_path


def _stop_everything(home: Path, port: int):
    _run(["stop", "--all", "--port", str(port), "--json"], home=home)


def test_status_and_url_report_nothing_on_an_unused_port_range(home):
    port = _free_port_base()
    status = _run(["status", "--port", str(port), "--json"], home=home)
    assert status.returncode == 1, status.stderr
    assert json.loads(status.stdout)["instances"] == []
    url = _run(["url", "--port", str(port)], home=home)
    assert url.returncode == 1
    assert "mms web start" in url.stderr


def test_start_status_url_stop_cycle(home):
    port = _free_port_base()
    state = home / "state"
    config = home / "config"
    try:
        started = _run(["start", "--port", str(port), "--state-root", str(state), "--config-root", str(config), "--json"], home=home)
        assert started.returncode == 0, started.stdout + started.stderr
        instance = json.loads(started.stdout)
        assert instance["mine"] is True and instance["port"] == port
        assert instance["url"] == f"http://127.0.0.1:{port}"
        assert (state / "logs" / "mms-web.log").is_file()

        # A second start does not spawn another server: same pid, same port.
        again = _run(["start", "--port", str(port), "--state-root", str(state), "--json"], home=home)
        assert json.loads(again.stdout)["pid"] == instance["pid"]

        status = _run(["status", "--port", str(port), "--state-root", str(state), "--json"], home=home)
        assert status.returncode == 0
        rows = json.loads(status.stdout)["instances"]
        assert [r["port"] for r in rows] == [port]
        assert rows[0]["mine"] is True
        assert rows[0]["stateRoot"] == str(state.resolve())
        assert rows[0]["configRoot"] == str(config)
        from mms_version import VERSION
        assert rows[0]["version"] == VERSION

        # Another state root sees the same server but not as its own.
        other = _run(["status", "--port", str(port), "--state-root", str(home / "elsewhere"), "--json"], home=home)
        assert other.returncode == 1
        assert json.loads(other.stdout)["instances"][0]["mine"] is False

        url = _run(["url", "--port", str(port), "--state-root", str(state)], home=home)
        assert url.stdout.strip() == f"http://127.0.0.1:{port}"

        stopped = _run(["stop", "--port", str(port), "--state-root", str(state), "--json"], home=home)
        assert stopped.returncode == 0, stopped.stderr
        assert [r["pid"] for r in json.loads(stopped.stdout)] == [instance["pid"]]
        after = _run(["status", "--port", str(port), "--state-root", str(state), "--json"], home=home)
        assert after.returncode == 1 and json.loads(after.stdout)["instances"] == []
    finally:
        _stop_everything(home, port)


@pytest.mark.skipif(os.name == "nt", reason="Windows binds one Pilot per selected port range")
def test_stop_only_touches_its_own_state_root_unless_all(home):
    port = _free_port_base()
    a, b = home / "a", home / "b"
    config = home / "config"
    try:
        for state in (a, b):
            started = _run(["start", "--port", str(port), "--state-root", str(state), "--config-root", str(config), "--json"], home=home)
            assert started.returncode == 0, started.stdout + started.stderr
        # Stopping b leaves a alone.
        assert _run(["stop", "--port", str(port), "--state-root", str(b), "--json"], home=home).returncode == 0
        rows = json.loads(_run(["status", "--port", str(port), "--state-root", str(a), "--json"], home=home).stdout)["instances"]
        assert len(rows) == 1 and rows[0]["stateRoot"] == str(a.resolve())
        # --all from an unrelated root stops what is left.
        assert _run(["stop", "--all", "--port", str(port), "--state-root", str(home / "none"), "--json"], home=home).returncode == 0
        rows = json.loads(_run(["status", "--port", str(port), "--json"], home=home).stdout)["instances"]
        assert rows == []
    finally:
        _stop_everything(home, port)


def test_the_verb_may_follow_options_that_mms_core_prepends(home):
    """`mms web status` arrives here as `--config-root <root> status` when
    MMS_CONFIG_ROOT is set, and `mms web --open` must keep serving as before."""
    port = _free_port_base()
    result = _run(["--config-root", str(home / "config"), "status", "--port", str(port), "--json"], home=home)
    assert result.returncode == 1, result.stderr
    assert json.loads(result.stdout)["instances"] == []
    # An unknown positional is still an argparse error from the server parser.
    bogus = _run(["frobnicate"], home=home)
    assert bogus.returncode == 2 and "unrecognized arguments" in bogus.stderr


def test_bare_web_prints_help_instead_of_occupying_the_terminal(home):
    """`mms web` with nothing to do says what can be appended (issue #191)."""
    bare = _run([], home=home)
    assert bare.returncode == 0, bare.stderr
    assert bare.stdout.startswith("MMS Pilot ")
    for verb in ("start", "status", "url", "stop", "restart"):
        assert f"\n  {verb}" in bare.stdout, verb
    # mms_core prepends the selected root, so that is still a bare call.
    prepended = _run(["--config-root", str(home / "config")], home=home)
    assert prepended.stdout == bare.stdout
    for flag in ("help", "-h", "--help"):
        assert _run([flag], home=home).stdout == bare.stdout, flag


def test_help_examples_are_spelled_like_the_entry_point_that_printed_them(home):
    env_named = _run([], home=home, extra_env={"MMS_COMMAND_NAME": "mmf"})
    assert "mmf web start --open" in env_named.stdout
    assert "mms web start --open" not in env_named.stdout
    default = _run([], home=home)
    assert "mms web start --open" in default.stdout


def test_options_that_ask_for_a_server_are_not_a_help_request():
    from mms_web.service import wants_help

    assert wants_help([]) is True
    assert wants_help(["--config-root", "/tmp/root"]) is True
    assert wants_help(["--config-root=/tmp/root"]) is True
    assert wants_help(["--help"]) is True
    # Anything that asks for a server keeps serving, including the launcher
    # invocations: `MMS Pilot.command` passes --open, the installer passes
    # --state-root/--port/--open.
    for argv in (["--open"], ["--port", "8080"], ["--listen", "lan"], ["--version"],
                 ["--state-root", "/tmp/state", "--port", "8080", "--open"],
                 ["--config-root", "/tmp/root", "--open"]):
        assert wants_help(argv) is False, argv


def test_the_help_lists_every_verb_that_can_be_dispatched():
    from mms_web.service import VERBS, help_text

    text = help_text("mms web")
    for verb in VERBS:
        assert f"\n  {verb}" in text, verb
    assert "logs/mms-web.log" in text


def test_doctor_restart_reuses_the_current_pilot_port(monkeypatch, tmp_path):
    from mms_web import service

    current = {"port": 8766, "pid": 42, "mine": True}
    calls = []
    mine_calls = []

    def find_mine(_rows):
        mine_calls.append(True)
        return current if len(mine_calls) == 1 else None

    monkeypatch.setattr(service, "_mine", find_mine)
    monkeypatch.setattr(service, "discover", lambda *args: calls.append(("discover", args)) or [current])
    monkeypatch.setattr(service, "stop", lambda **kwargs: calls.append(("stop", kwargs)))
    monkeypatch.setattr(service, "start", lambda **kwargs: calls.append(("start", kwargs)) or {**current, "version": "test"})
    def fake_request(base, path, timeout=8.0):
        if path == "/api/v1/bootstrap":
            return True, {"version": "1", "capabilities": {"launch": True}}
        if path == "/api/v1/sessions":
            return True, {"sessions": []}
        return True, {"session": {"id": "session/1"}}

    monkeypatch.setattr(service, "_doctor_request", fake_request)
    assert service.doctor(state_root=tmp_path, port_base=8765, limit=20, restart=True) == 0
    start_call = next(item for item in calls if item[0] == "start")
    assert start_call[1]["port_base"] == 8766


def test_restart_reuses_the_current_pilot_port(monkeypatch, tmp_path):
    from mms_web import service

    current = {"port": 8766, "pid": 42, "mine": True}
    calls = []
    monkeypatch.setattr(service, "_mine", lambda rows: current)
    monkeypatch.setattr(service, "discover", lambda *args: [current])
    monkeypatch.setattr(service, "stop", lambda **kwargs: calls.append(("stop", kwargs)))
    monkeypatch.setattr(service, "start", lambda **kwargs: calls.append(("start", kwargs)) or current)
    monkeypatch.setattr(service, "default_state_root", lambda: tmp_path)

    assert service.run("restart", ["--state-root", str(tmp_path), "--port", "8765", "--json"]) == 0
    start_call = next(item for item in calls if item[0] == "start")
    assert start_call[1]["port_base"] == 8766


def test_doctor_checks_bootstrap_sessions_and_detail_without_network(home, monkeypatch, capsys):
    from mms_web import service

    instance = {"port": 9876, "version": "test", "pid": 1, "url": "http://127.0.0.1:9876"}
    monkeypatch.setattr(service, "_mine", lambda rows: instance)
    monkeypatch.setattr(service, "discover", lambda *args: [instance])
    calls = []

    def fake_request(base, path, timeout=8.0):
        calls.append(path)
        if path == "/api/v1/bootstrap":
            return True, {"version": "1", "capabilities": {"launch": True}}
        if path == "/api/v1/sessions":
            return True, {"sessions": [{"id": "session/1"}]}
        return True, {"session": {"id": "session/1"}}

    monkeypatch.setattr(service, "_doctor_request", fake_request)
    assert service.doctor(state_root=home / "state", port_base=9876, limit=1) == 0
    assert calls == ["/api/v1/bootstrap", "/api/v1/sessions", "/api/v1/sessions/session%2F1"]
    assert "MMS doctor：PASS" in capsys.readouterr().out


def test_fingerprint_discovery_never_reads_a_different_default_roots_token(monkeypatch, tmp_path):
    from mms_web import service
    state, default = tmp_path / "selected", tmp_path / "default"
    default.mkdir()
    (default / "remote-access.json").write_text('{"mode":"lan"}')
    (default / "remote-access-token").write_text('foreign-fixture-token')
    monkeypatch.setattr(service, 'default_state_root', lambda: default)
    monkeypatch.setattr(service, '_probe', lambda port: {
        'identity': 'fixture', 'version': '9.9.9', 'stateIdentity': service.state_identity(state)})
    monkeypatch.setattr(service, '_listening_pids', lambda port: [])
    found = service.discover(8765, 1, state)[0]
    assert found['mine'] is True and found['stateRoot'] == str(state.resolve())
    assert found['url'] == 'http://127.0.0.1:8765'
    state.mkdir()
    (state / "remote-access.json").write_text('{"mode":"lan"}')
    (state / "remote-access-token").write_text('selected-fixture-token')
    assert service.discover(8765, 1, state)[0]['url'] == 'http://127.0.0.1:8765/?k=selected-fixture-token'
