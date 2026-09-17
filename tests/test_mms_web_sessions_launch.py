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


def test_bot_owned_launch_is_kept_out_of_pilot_session_list(service):
    detail = service.launch_bot(
        {
            "requestId": "bot-owner-1",
            "workspaceId": "ws",
            "presetId": "preset",
            "title": "日程员",
            "prompt": "整理今天的安排",
        },
        "bot_schedule",
    )
    session_id = detail["session"]["id"]
    view = service.get_session(session_id)["session"]
    assert view["owner"] == "bot"
    assert view["botId"] == "bot_schedule"
    assert any(row["id"] == session_id for row in service.list_sessions())


def test_read_only_bot_launch_requires_enforced_plan(service):
    with pytest.raises(WebError, match="只读工具限制"):
        service.launch_bot({"requestId": "unsafe-adapter", "workspaceId": "ws",
                            "presetId": "preset", "prompt": "review"}, "owner", read_only=True)
    assert service.list_sessions() == []


def test_read_only_bot_flag_reaches_plan_and_cannot_replay_as_executor(service):
    original = service._launch_plan_builder
    received = []

    def build(harness, model, runtime, cwd):
        received.append(dict(runtime))
        plan = original(harness, model, runtime, cwd)
        # This controlled test child only echoes and never runs a model/tool.
        plan.read_only = runtime.get("_webReadOnly") is True
        return plan

    service._launch_plan_builder = build
    payload = {"requestId": "readonly-bot", "workspaceId": "ws", "presetId": "preset", "prompt": "review"}
    detail = service.launch_bot(payload, "owner", read_only=True)
    session_id = detail["session"]["id"]
    assert detail["session"]["readOnly"] is True
    assert received[-1]["_webReadOnly"] is True
    assert detail["session"]["capabilities"]["send"] is False
    for action, body in [(service.switch_model, {"presetId": "another"}),
                         (service.fork, {}), (service.send, {"text": "continue"}),
                         (service.control, {"action": "plan", "value": False}),
                         (service.ask_side_question, {"question": "extra"})]:
        with pytest.raises(WebError) as blocked:
            action(session_id, {"requestId": "blocked", **body})
        assert blocked.value.code == "BOT_REVIEW_IMMUTABLE"
    with pytest.raises(WebError) as error:
        service.launch_bot(payload, "owner")
    assert error.value.code == "REQUEST_ID_CONFLICT"
    wait_for(lambda: service.get_session(session_id)["session"]["state"] == "idle")
    service.retire_bot_session(session_id)
    assert service._sessions[session_id].driver._proc.poll() is not None
    assert service.get_session(session_id)["session"]["archived"] is True


def test_public_launch_cannot_claim_read_only_mode(service):
    detail = service.launch({"requestId": "public-readonly", "workspaceId": "ws",
                             "presetId": "preset", "prompt": "normal", "readOnly": True})
    assert not detail["session"].get("readOnly")


@pytest.mark.parametrize("failed_reader", [False, True])
def test_fleet_full_chain_preserves_main_and_reaps_both_readers(service, tmp_path, failed_reader):
    from mms_web.bot_executor import PiBotExecutor
    from mms_web.bots import BotRuntime

    class FleetCatalog(FakeCatalog):
        def snapshot(self):
            return {"presets": [
                {"id": name, "name": name, "family": family, "harness": "pi", "available": True}
                for name, family in [("owner-model", "GPT"), ("review-a", "Kimi"), ("review-b", "GLM")]
            ], "workspaces": [{"id": "ws"}]}

        def resolve_launch(self, preset_id, workspace_id):
            resolved = super().resolve_launch(preset_id, workspace_id)
            resolved["model_info"] = {"model": preset_id}
            resolved["cwd"] = str(tmp_path)
            return resolved

    original = service._launch_plan_builder

    def build(harness, model, runtime, cwd):
        if failed_reader and model["model"] == "review-a":
            raise WebError("BOT_REVIEW_UNAVAILABLE", "fixture readonly launch refused", 409)
        plan = original(harness, model, runtime, cwd)
        # Controlled echo subprocess: no model or filesystem tools execute.
        plan.read_only = runtime.get("_webReadOnly") is True
        return plan

    service._launch_plan_builder = build
    service._catalog = FleetCatalog()
    rt = BotRuntime(state_root=tmp_path / "bots", executor=PiBotExecutor(service, service._catalog))
    rt.configure_endpoint("http://127.0.0.1:8765/api/v1/bot-worker")

    def complete(task):
        def tick_done():
            rt.tick()
            for worker in list(rt._workers):
                worker.join(timeout=0.05)
            return rt.get_task(task["id"])["status"] == "completed"
        wait_for(tick_done, message="Fleet lifecycle completion")
        rt.tick()

    try:
        owner = rt.create_bot({"name": "Owner", "workspaceId": "ws", "presetId": "owner-model",
                               "wakeEnabled": True})
        ordinary = rt.create_task({"botId": owner["id"], "prompt": "摘要", "fleetDispatch": False})
        complete(ordinary)
        main = rt.get_bot(owner["id"])["sessionId"]
        rt.update_bot(owner["id"], {"fleetPolicy": {"families": ["Kimi", "GLM"],
                         "models": {"Kimi": "review-a", "GLM": "review-b"}}})
        fleet = rt.create_task({"botId": owner["id"], "prompt": "请评价方案", "fleetDispatch": True})
        complete(fleet)
        children = [rt.get_task(cid) for cid in rt.get_task(fleet["id"])["children"]]
        assert len(children) == 2
        readers = [child for child in children if child["sessionId"]]
        if failed_reader:
            assert {child["status"] for child in children} == {"completed", "failed"}
        else:
            assert {child["model"] for child in readers} == {"review-a", "review-b"}
        assert len({child["sessionId"] for child in readers} | {main}) == len(readers) + 1
        for child in readers:
            live = service._sessions[child["sessionId"]]
            assert live.session_view()["readOnly"] is True
            assert live.meta["archived"] is True
            assert live.driver._proc.poll() is not None
        assert rt.get_bot(owner["id"])["sessionId"] == main
        assert service._sessions[main].alive()
        assert not service._sessions[main].meta.get("archived")
        assert rt.get_task(fleet["id"])["sessionId"] == main
    finally:
        rt.close()


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
    assert view["capabilities"] == {"send": False, "stop": False, "approve": False, "steer": False, "queueControl": False}
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


def test_plan_accepts_registry_snapshot_without_legacy_config(tmp_path, monkeypatch):
    bundle = tmp_path / "generated/model-registry.latest-approved.json"
    bundle.parent.mkdir()
    bundle.write_text('{}')
    monkeypatch.setattr(launch_bridge, "pi_runtime", lambda: ("/bin/pi", "/bin/node"))
    plan = launch_bridge.build_pi_launch_plan({"model": "m"},
        {"auth_mode": "api_key", "_webConfigRoot": str(tmp_path)}, str(tmp_path))
    assert plan.env["MMS_CONFIG_ROOT"] == str(tmp_path.resolve())
    assert not (tmp_path / "config.toml").exists()


def test_plan_rejects_snapshot_without_any_config(tmp_path, monkeypatch):
    monkeypatch.setattr(launch_bridge, "pi_runtime", lambda: ("/bin/pi", "/bin/node"))
    with pytest.raises(LaunchSeamUnavailable, match="配置"):
        launch_bridge.build_pi_launch_plan({},
            {"auth_mode": "api_key", "_webConfigRoot": str(tmp_path)}, str(tmp_path))


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


def test_windows_plan_uses_powershell_when_bash_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(launch_bridge.sys, "platform", "win32")
    monkeypatch.delenv("ProgramFiles", raising=False)
    monkeypatch.delenv("ProgramFiles(x86)", raising=False)
    monkeypatch.setattr(launch_bridge.shutil, "which", lambda name: "C:/Windows/powershell.exe" if name == "powershell.exe" else None)

    args = launch_bridge._windows_shell_tool_args()
    assert args[args.index("--tools") + 1] == "read,powershell,edit,write"
    assert "bash" not in args[args.index("--tools") + 1]


def test_windows_plan_keeps_bash_when_git_bash_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(launch_bridge.sys, "platform", "win32")
    monkeypatch.setenv("ProgramFiles", "C:/Program Files")
    monkeypatch.setattr(launch_bridge.Path, "is_file", lambda path: str(path).endswith("Git/bin/bash.exe"))
    monkeypatch.setattr(launch_bridge.shutil, "which", lambda _name: None)

    assert launch_bridge._windows_shell_tool_args() == []


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
