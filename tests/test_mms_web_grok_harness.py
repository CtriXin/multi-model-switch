"""Optional Grok Pilot harness: ACP driver + catalog preset, no real provider."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_CHILD = str(Path(__file__).resolve().parent / "fixtures" / "mms_web" / "grok_fake_child.py")
sys.path.insert(0, str(REPO_ROOT))

from mms_web.drivers import launch_bridge  # noqa: E402
from mms_web.errors import WebError  # noqa: E402
from mms_web.sessions import SessionService  # noqa: E402


class FakeCatalog:
    def resolve_launch(self, preset_id: str, workspace_id: str) -> dict:
        return {
            "harness": "grok",
            "model_info": {"model": "dummy"},
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
        "mms_web.sessions.probe_mms_pi_seam", lambda: {"available": False, "reason": "pi unused"}
    )
    monkeypatch.setattr(
        "mms_web.sessions.probe_mms_grok_seam", lambda: {"available": True, "injected": True}
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


def test_grok_launch_send_stop(service):
    detail = service.launch(
        {
            "requestId": "grok-1",
            "workspaceId": "ws",
            "presetId": "web:grok:prov:dummy",
            "title": "Grok T1",
            "prompt": "hello grok",
        }
    )
    session_id = detail["session"]["id"]
    assert detail["session"]["harness"] == "grok"
    wait_for(
        lambda: service.get_session(session_id)["session"]["state"] == "idle",
        message="grok settle",
    )
    texts = [e["text"] for e in service.get_session(session_id)["events"] if e["kind"] == "assistant"]
    assert texts == ["echo: hello grok"]
    service.send(session_id, {"requestId": "grok-2", "text": "second"})
    wait_for(
        lambda: [e["text"] for e in service.get_session(session_id)["events"] if e["kind"] == "assistant"]
        == ["echo: hello grok", "echo: second"],
        message="second grok turn",
    )
    service.stop(session_id, {"requestId": "grok-3"})
    view = service.get_session(session_id)["session"]
    assert view["state"] in {"idle", "stopped"}


def test_grok_plan_mode_does_not_call_pi_extension(service):
    detail = service.launch(
        {
            "requestId": "grok-plan",
            "workspaceId": "ws",
            "presetId": "web:grok:prov:dummy",
            "prompt": "hello grok",
            "planMode": True,
        }
    )
    notices = [e["text"] for e in detail["events"] if e["kind"] == "notice"]
    assert any("只读规划" in text for text in notices)


def test_grok_approval_confirm(service):
    detail = service.launch(
        {
            "requestId": "grok-appr",
            "workspaceId": "ws",
            "presetId": "web:grok:prov:dummy",
            "prompt": "approval-confirm please",
        }
    )
    session_id = detail["session"]["id"]
    wait_for(
        lambda: service.get_session(session_id)["session"]["state"] == "waiting",
        message="permission prompt",
    )
    approvals = [e for e in service.get_session(session_id)["events"] if e["kind"] == "approval"]
    assert approvals
    service.approve(session_id, approvals[0]["approvalId"], {"requestId": "grok-allow", "decision": "allow"})
    wait_for(
        lambda: any(
            e["kind"] == "assistant" and "approved:" in (e.get("text") or "")
            for e in service.get_session(session_id)["events"]
        ),
        message="approved reply",
    )


def test_non_web_harness_still_rejected(service):
    class CodexCatalog:
        def resolve_launch(self, preset_id: str, workspace_id: str) -> dict:
            return {"harness": "codex", "model_info": {}, "runtime": {"auth_mode": "api_key"}, "cwd": str(REPO_ROOT)}

    service._catalog = CodexCatalog()
    with pytest.raises(WebError) as err:
        service.launch({"requestId": "no-codex", "workspaceId": "ws", "presetId": "x", "prompt": "no"})
    assert err.value.status == 409
    assert "grok" in err.value.message
