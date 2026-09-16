"""Windows seams of `mms web start|status|url|stop|restart` (T3 Preview).

None of these need a Windows host: each one drives the exact branch the
service takes when ``os.name == "nt"``, including the Windows-only subprocess
constants, which are injected so the branch can be exercised on POSIX.
"""
import os
import signal
import subprocess
from pathlib import Path

import pytest

from mms_web import service

WINDOWS_STATE_ROOT = r"C:\Users\xin\AppData\Local\MMS\mms-web"


def _entry(port=8765, state=WINDOWS_STATE_ROOT, pid=4242):
    return {"port": port, "pid": pid, "version": "0.0.0", "identity": "i",
            "stateRoot": state, "configRoot": "", "source": "",
            "url": f"http://127.0.0.1:{port}", "mine": True}


def test_a_windows_command_line_keeps_its_drive_separators(monkeypatch):
    """Win32_Process reports `--state-root C:\\Users\\...` unquoted."""
    monkeypatch.setattr(service, "_is_windows", lambda: True)
    command = subprocess.list2cmdline(
        [r"C:\Python311\python.exe", "-P", "-m", "mms_web",
         "--state-root", WINDOWS_STATE_ROOT, "--port", "8765"])
    argv = service._split_command_line(command)
    assert service._option(argv, "--state-root") == WINDOWS_STATE_ROOT
    assert argv[0] == r"C:\Python311\python.exe"


def test_a_quoted_windows_path_with_spaces_also_survives(monkeypatch):
    monkeypatch.setattr(service, "_is_windows", lambda: True)
    spaced = r"C:\Users\Zhang Wei\AppData\Local\MMS\mms-web"
    command = subprocess.list2cmdline([r"C:\py\python.exe", "-m", "mms_web", "--state-root", spaced])
    assert service._option(service._split_command_line(command), "--state-root") == spaced


def test_mine_comes_from_the_state_fingerprint_not_the_process_list(monkeypatch, tmp_path):
    """Discovery must not depend on netstat or CIM being readable."""
    state = tmp_path / "state"
    monkeypatch.setattr(service, "_probe", lambda port, timeout=0.4: None if port != 8765 else {
        "identity": "i", "version": "9.9.9", "stateIdentity": service.state_identity(state)})
    monkeypatch.setattr(service, "_listening_pids", lambda port: [])
    monkeypatch.setattr(service, "_command_line", lambda pid: [])
    found = service.discover(8765, 1, state)
    assert [entry["mine"] for entry in found] == [True]
    assert found[0]["url"] == "http://127.0.0.1:8765"


def test_a_foreign_state_root_is_not_mine(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "_probe", lambda port, timeout=0.4: {
        "identity": "i", "version": "9.9.9", "stateIdentity": service.state_identity(tmp_path / "theirs")})
    monkeypatch.setattr(service, "_listening_pids", lambda port: [7])
    monkeypatch.setattr(service, "_command_line", lambda pid: [])
    assert service.discover(8765, 1, tmp_path / "mine")[0]["mine"] is False


def test_start_detaches_the_background_pilot_from_the_console(monkeypatch, tmp_path):
    """start_new_session is ignored on Windows; the flags are what detach."""
    monkeypatch.setattr(service, "_is_windows", lambda: True)
    monkeypatch.setattr(service.subprocess, "DETACHED_PROCESS", 0x00000008, raising=False)
    monkeypatch.setattr(service.subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200, raising=False)
    monkeypatch.setattr(service, "discover", lambda *a, **k: [])
    monkeypatch.setattr(service, "_free_port", lambda base, limit: 8765)
    monkeypatch.setattr(service, "START_TIMEOUT", 0)
    seen = {}

    def fake_popen(command, **kwargs):
        seen.update(kwargs)
        return object()

    monkeypatch.setattr(service.subprocess, "Popen", fake_popen)
    with pytest.raises(SystemExit):           # never becomes ready: only the spawn matters
        service.start(state_root=tmp_path, port_base=8765, limit=1, open_browser=False, quiet=True)
    assert seen["creationflags"] == 0x00000208


def test_stop_requests_a_windows_exit_and_never_force_kills(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "_is_windows", lambda: True)
    monkeypatch.setattr(service, "STOP_TIMEOUT", 5)
    monkeypatch.setattr(service.time, "sleep", lambda _: None)
    monkeypatch.setattr(service, "discover", lambda *a, **k: [_entry(state=str(tmp_path))])
    commands = []
    monkeypatch.setattr(service.subprocess, "run",
                        lambda *a, **k: commands.append(a[0]) or subprocess.CompletedProcess(a[0], 0, "", ""))
    request = tmp_path / service.STOP_REQUEST
    # The Pilot answers until it has seen the request, like the real watcher.
    monkeypatch.setattr(service, "_probe",
                        lambda port, timeout=0.4: None if request.exists() else {"identity": "i", "version": "1"})
    stopped = service.stop(state_root=tmp_path, port_base=8765, limit=1, everyone=False, quiet=True)
    assert [entry["pid"] for entry in stopped] == [4242]
    assert request.read_text(encoding="utf-8") == "8765"
    assert commands == [], commands           # no taskkill, no CloseMainWindow


def test_a_stop_that_times_out_leaves_no_request_for_the_next_start(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "_is_windows", lambda: True)
    monkeypatch.setattr(service, "STOP_TIMEOUT", 0.2)
    monkeypatch.setattr(service.time, "sleep", lambda _: None)
    monkeypatch.setattr(service, "discover", lambda *a, **k: [_entry(state=str(tmp_path))])
    monkeypatch.setattr(service, "_probe", lambda port, timeout=0.4: {"identity": "i", "version": "1"})
    assert service.stop(state_root=tmp_path, port_base=8765, limit=1, everyone=False, quiet=True) == []
    assert not (tmp_path / service.STOP_REQUEST).exists()


def test_the_fingerprint_ignores_case_the_way_windows_paths_do(tmp_path):
    lower = tmp_path / "state"
    lower.mkdir()
    assert service.state_identity(lower) == service.state_identity(Path(str(lower)))


def test_close_for_update_never_force_kills_an_idle_pi_on_windows(monkeypatch):
    from mms_web.drivers import pi_rpc

    calls = []

    class Child(pi_rpc.PiRpcDriver):
        def __init__(self):
            self._exit_code = None
            self._proc = type("P", (), {
                "stdin": None, "pid": 1,
                "terminate": lambda s: calls.append("terminate"),
                "kill": lambda s: calls.append("kill")})()

        def alive(self):
            return True

        def wait(self, timeout=None):
            return False

        def _notify_exit(self):
            return None

    monkeypatch.setattr(pi_rpc, "_is_windows", lambda: True)
    # The Windows signal module has no SIGKILL, so the module falls back to a
    # sentinel that is not SIGTERM; a graceful request must stay distinguishable.
    monkeypatch.setattr(pi_rpc, "FORCE_SIGNAL", "force")
    child = Child()
    assert child.close_for_update(timeout=0) is False
    assert calls == []                        # the update aborts; the session lives
    child.close(graceful_timeout=0)           # must not raise where SIGKILL is absent
    assert calls == ["kill"]                  # only the explicit stop ladder forces


def test_a_live_pilot_publishes_the_fingerprint_the_cli_compares(tmp_path):
    """End to end: the header exists, and it is the one `mine` is decided by."""
    import json
    import socket
    import sys

    root = Path(__file__).resolve().parents[1]
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    state = tmp_path / "state"
    environment = {key: value for key, value in os.environ.items()
                   if key not in ("MMS_CONFIG_ROOT", "MMS_CONFIG_DIR", "XDG_CONFIG_HOME",
                                  "XDG_DATA_HOME", "MMS_REAL_HOME", "REAL_HOME",
                                  "ORIGINAL_HOME", "MMS_WEB_PORT_BASE", "MMS_COMMAND_NAME")}
    environment.update({"HOME": str(tmp_path), "MMS_REAL_HOME": str(tmp_path), "PYTHONPATH": str(root)})

    def run(*args):
        return subprocess.run([sys.executable, "-P", "-m", "mms_web", *args], cwd=root,
                              env=environment, capture_output=True, text=True, timeout=90)

    started = run("start", "--port", str(port), "--state-root", str(state), "--json")
    assert started.returncode == 0, started.stdout + started.stderr
    try:
        assert json.loads(started.stdout)["mine"] is True
        probed = service._probe(port)
        assert probed["stateIdentity"] == service.state_identity(state)
    finally:
        run("stop", "--all", "--port", str(port), "--state-root", str(state), "--json")
