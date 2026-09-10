"""Full-chain launch tests: SessionService + PiRpcDriver + real subprocess.

The child is the task-owned fixture (tests/fixtures/mms_web/pi_fake_child.py),
wired in through the same launch_plan_builder seam the lead's HTTP server will
use for real MMS launches. Also covers the MMS seam probe/plan builder with a
stubbed support module (no real gateway dirs are written).
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_CHILD = str(Path(__file__).resolve().parent / "fixtures" / "mms_web" / "pi_fake_child.py")
sys.path.insert(0, str(REPO_ROOT))

from mms_web.drivers import launch_bridge  # noqa: E402
from mms_web.drivers.base import LaunchSeamUnavailable  # noqa: E402
from mms_web.errors import WebError  # noqa: E402
from mms_web.sessions import SessionService  # noqa: E402


class FakeCatalog:
    def resolve_launch(self, preset_id: str, workspace_id: str) -> dict:
        return {
            "harness": "pi",
            "model_info": {"model": "fake-model"},
            "runtime": {"id": "prov", "name": "Fixture Provider", "channel": "chat", "auth_mode": "api_key"},
            "cwd": str(REPO_ROOT),
        }


def wait_for(predicate, timeout: float = 10.0, message: str = "condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError(f"timeout waiting for {message}")


@pytest.fixture()
def service(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "mms_web.sessions.probe_mms_pi_seam", lambda: {"available": True, "injected": True}
    )
    svc = SessionService(
        config_root=tmp_path / "config",
        state_root=tmp_path / "state",
        catalog=FakeCatalog(),
        launch_plan_builder=launch_bridge.fixed_command_plan_builder(
            [sys.executable, FIXTURE_CHILD]
        ),
        real_launch=True,
    )
    yield svc
    svc.close()


def test_full_chain_launch_send_snapshot_stop(service):
    detail = service.launch(
        {
            "requestId": "chain-1",
            "workspaceId": "ws",
            "presetId": "preset",
            "title": "集成验证",
            "prompt": "hello chain",
        }
    )
    session_id = detail["session"]["id"]
    assert detail["session"]["state"] == "running"
    wait_for(
        lambda: service.get_session(session_id)["session"]["state"] == "idle",
        message="agent settle",
    )
    snapshot = service.get_session(session_id)
    texts = [e["text"] for e in snapshot["events"] if e["kind"] == "assistant"]
    assert texts == ["echo: hello chain"]
    # deltas must not duplicate the finalized text
    assistant_events = [e for e in snapshot["events"] if e["kind"] == "assistant"]
    assert len(assistant_events) == 1

    detail = service.send(session_id, {"requestId": "chain-2", "text": "second turn"})
    wait_for(
        lambda: [e["text"] for e in service.get_session(session_id)["events"] if e["kind"] == "assistant"]
        == ["echo: hello chain", "echo: second turn"],
        message="second turn",
    )
    user_texts = [e["text"] for e in detail["events"] if e["kind"] == "user"]
    assert user_texts == ["hello chain", "second turn"]

    service.stop(session_id, {"requestId": "chain-3"})
    view = service.get_session(session_id)["session"]
    assert view["state"] in {"idle", "stopped"}
    # close() must not leave the fixture child alive.
    service.close()
    driver = service._sessions[session_id].driver
    wait_for(lambda: driver._proc.poll() is not None, message="child reaped")
    assert service.get_session(session_id)["session"]["state"] == "stopped"


def test_full_chain_approval_confirm_flow(service):
    detail = service.launch(
        {
            "requestId": "ap-chain",
            "workspaceId": "ws",
            "presetId": "preset",
            "prompt": "approval-confirm",
        }
    )
    session_id = detail["session"]["id"]
    wait_for(
        lambda: service.get_session(session_id)["session"]["capabilities"]["approve"],
        message="approval pending",
    )
    view = service.get_session(session_id)["session"]
    assert view["state"] == "waiting"
    approval_events = [e for e in service.get_session(session_id)["events"] if e["kind"] == "approval"]
    assert approval_events[0]["approvalId"] == "ui-confirm-1"
    result = service.approve(session_id, "ui-confirm-1", {"requestId": "ap-allow", "decision": "allow"})
    assert any(
        e.get("decision") == "allow" for e in result["events"] if e["kind"] == "approval"
    )
    wait_for(
        lambda: service.get_session(session_id)["session"]["state"] == "idle",
        message="resume after approval",
    )
    texts = [e["text"] for e in service.get_session(session_id)["events"] if e["kind"] == "assistant"]
    assert texts == ["confirm answered: True"]


def test_full_chain_child_exit_error_state(service):
    detail = service.launch(
        {
            "requestId": "exit-chain",
            "workspaceId": "ws",
            "presetId": "preset",
            "prompt": "stderr",
        }
    )
    session_id = detail["session"]["id"]
    wait_for(
        lambda: service.get_session(session_id)["session"]["state"] == "idle",
        message="first turn settle",
    )
    service.send(session_id, {"requestId": "exit-chain-2", "text": "exit1"})
    wait_for(
        lambda: service.get_session(session_id)["session"]["state"] == "error",
        message="error state",
    )
    view = service.get_session(session_id)["session"]
    assert view["capabilities"] == {"send": False, "stop": False, "approve": False}
    events = service.get_session(session_id)["events"]
    exit_notices = [e["text"] for e in events if "Pi 进程已退出" in e.get("text", "")]
    assert exit_notices and "fake child stderr diagnostic" not in exit_notices[0]
    with pytest.raises(WebError) as err:
        service.send(session_id, {"requestId": "after-exit", "text": "x"})
    assert err.value.code == "SESSION_NOT_ACTIVE"


def test_full_chain_parallel_snapshots_keep_ordering(service):
    detail = service.launch(
        {
            "requestId": "par-1",
            "workspaceId": "ws",
            "presetId": "preset",
            "prompt": "hello",
        }
    )
    session_id = detail["session"]["id"]
    stop = threading.Event()
    problems: list[str] = []

    def poller():
        try:
            while not stop.is_set():
                events = service.get_session(session_id)["events"]
                sequences = [e["sequence"] for e in events]
                if sequences != sorted(sequences):
                    problems.append("out of order")
                if len({e["id"] for e in events}) != len(events):
                    problems.append("duplicate ids")
        except Exception as exc:  # pragma: no cover
            problems.append(repr(exc))

    threads = [threading.Thread(target=poller) for _ in range(4)]
    for thread in threads:
        thread.start()
    try:
        for index in range(5):
            service.send(session_id, {"requestId": f"par-s{index}", "text": f"msg {index}"})
            wait_for(
                lambda idx=index: len(
                    [e for e in service.get_session(session_id)["events"] if e["kind"] == "assistant"]
                )
                >= idx + 1,
                message=f"assistant {index}",
            )
    finally:
        stop.set()
        for thread in threads:
            thread.join(timeout=5)
    assert not problems


# -- worker launch boundary ---------------------------------------------


def test_seam_probe_does_not_import_mms_core(monkeypatch):
    monkeypatch.setattr(launch_bridge, "pi_runtime", lambda: ("/bin/pi", "/bin/node"))
    before = set(sys.modules)
    report = launch_bridge.probe_mms_pi_seam()
    assert report["available"]
    assert "mms_core" not in set(sys.modules) - before
    assert report["launcher"] == "mms_launchers.launch_cli"


def test_plan_builder_requires_private_snapshot(tmp_path):
    with pytest.raises(LaunchSeamUnavailable):
        launch_bridge.build_pi_launch_plan({"model": "m"}, {"auth_mode": "api_key"}, str(tmp_path))


def test_plan_keeps_secrets_out_of_argv_and_parent_env(tmp_path, monkeypatch):
    import json
    (tmp_path / "config.toml").write_text("")
    monkeypatch.setattr(launch_bridge, "pi_runtime", lambda: ("/bin/pi", "/bin/node"))
    parent = dict(os.environ)
    plan = launch_bridge.build_pi_launch_plan({"model": "m"},
        {"auth_mode": "api_key", "api_key": "PRIVATE-TEST-SECRET", "_webConfigRoot": str(tmp_path)}, str(tmp_path))
    assert "PRIVATE-TEST-SECRET" not in str(plan.cmd)
    assert os.environ == parent
    assert plan.env["MMS_CONFIG_ROOT"] == str(tmp_path.resolve())
    payload_file = Path(plan.cmd[-1])
    assert payload_file.stat().st_mode & 0o777 == 0o600
    payload = json.loads(payload_file.read_text())
    assert payload["runtime"]["api_key"] == "PRIVATE-TEST-SECRET"
    assert payload["extraArgs"][:2] == ["--mode", "rpc"]
    assert "--session" in payload["extraArgs"]


def test_plan_rejects_global_config_even_with_valid_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("MMS_REAL_HOME", str(tmp_path))
    root = tmp_path / ".config/mms-next"
    root.mkdir(parents=True)
    (root / "config.toml").write_text("")
    with pytest.raises(WebError, match="独立目录"):
        launch_bridge.build_pi_launch_plan({}, {"auth_mode": "api_key", "_webConfigRoot": str(root)}, str(tmp_path))


def test_plan_rejects_oauth(tmp_path):
    with pytest.raises(LaunchSeamUnavailable):
        launch_bridge.build_pi_launch_plan({}, {"auth_mode": "oauth"}, str(tmp_path))
