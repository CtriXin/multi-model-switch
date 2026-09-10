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


def _run(args, *, home: Path, timeout=90):
    env = {k: v for k, v in os.environ.items()
           if k not in ("MMS_CONFIG_ROOT", "MMS_CONFIG_DIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME",
                        "MMS_REAL_HOME", "REAL_HOME", "ORIGINAL_HOME", "MMS_WEB_PORT_BASE")}
    env.update({"HOME": str(home), "MMS_REAL_HOME": str(home), "PYTHONPATH": str(ROOT)})
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
