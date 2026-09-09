"""MMS Web version reporting and the in-place upgrade.

No test here reaches the network: the GitHub call is always stubbed.
"""

import json
import time
from pathlib import Path

import pytest

from mms_web.upgrade import MIN_CHECK_INTERVAL_SECONDS, UpgradeService


def _service(tmp_path: Path, *, installed: str | None = "v4.2.0", config: bool = True):
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    config_root = tmp_path / "config"
    if config:
        config_root.mkdir(parents=True, exist_ok=True)
        if installed is not None:
            (config_root / "version.json").write_text(
                json.dumps(
                    {
                        "installed_ref": installed,
                        "installed_version": installed if installed.count(".") == 2 else "",
                        "install_channel": "stable",
                        "installed_at": "2026-09-01T00:00:00Z",
                    }
                ),
                encoding="utf-8",
            )
    service = UpgradeService(state_root=state_root, config_root=config_root if config else None)
    service.port = 8765
    return service


def _stub_latest(service, monkeypatch, tag="v4.3.0", error=""):
    monkeypatch.setattr(service, "_fetch_latest", lambda: (tag, error))


def test_status_reports_an_available_update(tmp_path, monkeypatch):
    service = _service(tmp_path)
    _stub_latest(service, monkeypatch)

    status = service.refresh(force=True)

    assert status["installed"]["version"] == "v4.2.0"
    assert status["latest"] == "v4.3.0"
    assert status["updateAvailable"] is True
    assert status["canUpgrade"] is True
    assert status["error"] == ""


def test_status_is_quiet_when_already_current(tmp_path, monkeypatch):
    service = _service(tmp_path, installed="v4.3.0")
    _stub_latest(service, monkeypatch)

    status = service.refresh(force=True)

    assert status["updateAvailable"] is False
    assert status["canUpgrade"] is False


def test_source_checkout_is_never_told_to_upgrade(tmp_path, monkeypatch):
    """A developer's working tree has no comparable version."""
    service = _service(tmp_path, installed="v3.5.0-140-gd5ef85f9")
    _stub_latest(service, monkeypatch)

    status = service.refresh(force=True)

    assert status["comparable"] is False
    assert status["updateAvailable"] is False


def test_status_does_not_touch_the_network(tmp_path, monkeypatch):
    """bootstrap() calls status(); a page load must never wait on GitHub."""
    service = _service(tmp_path)

    def explode():  # pragma: no cover - asserted by not being called
        raise AssertionError("status() must not fetch")

    monkeypatch.setattr(service, "_fetch_latest", explode)
    status = service.status()

    assert status["latest"] == ""
    assert status["updateAvailable"] is False


def test_check_is_rate_limited_between_refreshes(tmp_path, monkeypatch):
    service = _service(tmp_path)
    calls = []

    def counted():
        calls.append(1)
        return "v4.3.0", ""

    monkeypatch.setattr(service, "_fetch_latest", counted)

    service.refresh()
    service.refresh()
    assert len(calls) == 1, "a fresh cache must not be refetched"

    service.refresh(force=True)
    assert len(calls) == 2, "an explicit check always refetches"


def test_a_stale_cache_is_refreshed(tmp_path, monkeypatch):
    service = _service(tmp_path)
    _stub_latest(service, monkeypatch)
    service._write_cache(
        {"latest": "v4.0.0", "checkedAt": time.time() - MIN_CHECK_INTERVAL_SECONDS - 1, "error": ""}
    )

    assert service.refresh()["latest"] == "v4.3.0"


def test_a_failed_check_is_reported_not_raised(tmp_path, monkeypatch):
    service = _service(tmp_path)
    _stub_latest(service, monkeypatch, tag="", error="无法连接到 GitHub，网络恢复后会自动重试。")

    status = service.refresh(force=True)

    assert status["updateAvailable"] is False
    assert "GitHub" in status["error"]


def test_the_check_can_be_switched_off(tmp_path, monkeypatch):
    monkeypatch.setenv("MMS_WEB_UPDATE_CHECK", "0")
    service = _service(tmp_path)

    def explode():  # pragma: no cover - asserted by not being called
        raise AssertionError("the check is disabled")

    monkeypatch.setattr(service, "_fetch_latest", explode)
    status = service.refresh(force=True)

    assert status["checkEnabled"] is False
    assert status["latest"] == ""


def test_upgrade_refuses_while_sessions_are_running(tmp_path, monkeypatch):
    service = _service(tmp_path)
    _stub_latest(service, monkeypatch)
    service.refresh(force=True)

    result = service.start(live_sessions=2)

    assert result["started"] is False
    assert "2" in result["reason"]
    assert not (service._state_root / "upgrade" / "run-upgrade.sh").exists()


def test_upgrade_refuses_when_already_current(tmp_path, monkeypatch):
    service = _service(tmp_path, installed="v4.3.0")
    _stub_latest(service, monkeypatch)
    service.refresh(force=True)

    result = service.start(live_sessions=0)

    assert result["started"] is False
    assert "最新" in result["reason"]


def test_upgrade_refuses_without_a_config_root(tmp_path, monkeypatch):
    service = _service(tmp_path, config=False)
    _stub_latest(service, monkeypatch)
    service.refresh(force=True)

    result = service.start(live_sessions=0)

    assert result["started"] is False


def test_upgrade_script_installs_before_replacing_the_server(tmp_path):
    service = _service(tmp_path)
    script = service._write_upgrade_script("v4.3.0")
    body = script.read_text(encoding="utf-8")

    lines = [line.strip() for line in body.splitlines()]
    install_at = next(i for i, line in enumerate(lines) if "--no-launch-web" in line)
    kill_at = next(i for i, line in enumerate(lines) if line.startswith("kill "))
    restart_at = next(i for i, line in enumerate(lines) if line.startswith("exec "))

    assert install_at < kill_at < restart_at, "the server must not die before the install works"
    # an unattended upgrade must not rewrite the user's shell config
    assert "--no-shell-rc" in body
    # the replacement server comes back on the same port and config root
    assert "--port 8765" in body
    assert f'--config-root "{tmp_path / "config"}"' in body, "paths must stay quoted"
    assert oct(script.stat().st_mode)[-3:] == "700"


def test_upgrade_script_aborts_when_the_install_fails(tmp_path):
    service = _service(tmp_path)
    body = service._write_upgrade_script("v4.3.0").read_text(encoding="utf-8")

    assert 'echo "install failed"; rm -f "$installer"; exit 1' in body
    assert 'echo "download failed"; rm -f "$installer"; exit 1' in body


def test_upgrade_marks_itself_running_and_reports_the_log(tmp_path, monkeypatch):
    service = _service(tmp_path)
    _stub_latest(service, monkeypatch)
    service.refresh(force=True)

    started = {}

    class FakeProcess:
        pid = 4242

    def fake_popen(*args, **kwargs):
        started["args"] = args[0]
        started["session"] = kwargs.get("start_new_session")
        return FakeProcess()

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    result = service.start(live_sessions=0)

    assert result["started"] is True
    assert result["target"] == "v4.3.0"
    assert result["logPath"].endswith("upgrade.log")
    # detached, or it dies with the server it is replacing
    assert started["session"] is True
    assert started["args"][0] == "bash"

    marker = json.loads((service._state_root / "upgrade-running.json").read_text(encoding="utf-8"))
    assert marker["pid"] == 4242


def test_a_dead_upgrade_marker_does_not_block_forever(tmp_path):
    service = _service(tmp_path)
    (service._state_root / "upgrade-running.json").write_text(
        json.dumps({"pid": 999999999, "startedAt": 0}), encoding="utf-8"
    )

    assert service.upgrade_running() is False
