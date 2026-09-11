"""SessionService contract tests with a fake catalog and fake driver.

Covers requestId idempotency, persistence/restart snapshots, capability
fail-closed behavior, approval scope, error mapping, and state-from-protocol
guarantees. No subprocess, no MMS modules, no real config.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from mms_web.drivers.base import DriverClosedError, RpcTimeoutError  # noqa: E402
from mms_web.errors import WebError  # noqa: E402
from mms_web.sessions import SessionService  # noqa: E402


class FakeCatalog:
    def __init__(self, launch_result=None, error: Exception | None = None) -> None:
        self.launch_result = launch_result or {
            "harness": "pi",
            "model_info": {"model": "fake-sonnet"},
            "runtime": {"id": "prov-1", "name": "Fake Provider", "channel": "chat"},
            "cwd": "/tmp/fake-ws",
        }
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def resolve_launch(self, preset_id: str, workspace_id: str) -> dict:
        self.calls.append((preset_id, workspace_id))
        if self.error is not None:
            raise self.error
        return self.launch_result


class FakeDriver:
    """In-process driver double; protocol state is set explicitly by tests."""

    def __init__(self, sink=None) -> None:
        self.lock = threading.Lock()
        self._alive = True
        self._sink = sink
        self.prompts: list[str] = []
        self.aborts = 0
        self.ui_responses: list[tuple[str, str]] = []
        self.pending: dict[str, dict] = {}
        self.fail_next_prompt: dict | None = None
        self.timeout_next_prompt = False
        self.reject_ui: WebError | None = None

    # driver API used by SessionService

    def alive(self) -> bool:
        return self._alive

    def send_prompt(self, text: str) -> dict:
        if self.timeout_next_prompt:
            self.timeout_next_prompt = False
            raise RpcTimeoutError("timeout")
        if self.fail_next_prompt is not None:
            failure, self.fail_next_prompt = self.fail_next_prompt, None
            return failure
        with self.lock:
            self.prompts.append(text)
        return {"type": "response", "command": "prompt", "success": True}

    def abort(self) -> dict:
        with self.lock:
            self.aborts += 1
        return {"type": "response", "command": "abort", "success": True}

    def respond_ui(self, approval_id: str, decision: str) -> None:
        if self.reject_ui is not None:
            raise self.reject_ui
        with self.lock:
            self.ui_responses.append((approval_id, decision))
            self.pending.pop(approval_id, None)
        if self._sink is not None:
            # Mirrors PiRpcDriver: record the decision event before resolving.
            self._sink.upsert_event(
                {"id": f"a-{approval_id}", "kind": "approval", "approvalId": approval_id, "decision": decision}
            )
            self._sink.approval_resolved(approval_id, decision)

    def close(self, *, graceful_timeout: float = 5.0) -> None:
        self._alive = False

    # test controls

    def kill(self) -> None:
        self._alive = False

    def emit_approval(self, service, session, approval_id="ap-1", method="confirm"):
        service._apply_approval_pending(session, approval_id, method, "title")


def make_service(tmp_path: Path, catalog=None, real_launch: bool = True, monkeypatch=None, **kwargs) -> tuple[SessionService, list[FakeDriver]]:
    catalog = catalog or FakeCatalog()
    drivers: list[FakeDriver] = []
    if monkeypatch is not None:
        monkeypatch.setattr(
            "mms_web.sessions.probe_mms_pi_seam", lambda: {"available": True, "injected": True}
        )

    def driver_factory(plan, sink):
        driver = FakeDriver(sink=sink)
        drivers.append(driver)
        return driver

    def plan_builder(harness, model_info, runtime, cwd):
        from mms_web.drivers.launch_bridge import LaunchPlan

        return LaunchPlan(cmd=["true"], env={}, cwd=cwd, harness=harness)

    service = SessionService(
        config_root=tmp_path / "config",
        state_root=tmp_path / "state",
        catalog=catalog,
        driver_factory=driver_factory,
        launch_plan_builder=plan_builder,
        real_launch=real_launch,
        **kwargs,
    )
    return service, drivers


@pytest.fixture()
def seeded_seam(monkeypatch):
    monkeypatch.setattr(
        "mms_web.sessions.probe_mms_pi_seam", lambda: {"available": True, "injected": True}
    )
    return None


def launch_ok(service, request_id="req-1", prompt="hi", **extra):
    payload = {"requestId": request_id, "workspaceId": "ws-1", "presetId": "p-1", "prompt": prompt}
    payload.update(extra)
    return service.launch(payload)


def test_capabilities_require_real_launch_and_seam(tmp_path, seeded_seam):
    service, _ = make_service(tmp_path, real_launch=True)
    assert service.capabilities()["launch"] is True
    service2, _ = make_service(tmp_path, real_launch=False)
    assert service2.capabilities()["launch"] is False


def test_launch_disabled_without_real_launch(tmp_path, seeded_seam):
    service, _ = make_service(tmp_path, real_launch=False)
    # The blocker travels with the flag now: a page full of unavailable models
    # has to be able to say what is missing.
    assert service.capabilities() == {"launch": False,
                                      "launchReason": "没有选定 MMS 配置根，无法启动会话。",
                                      "sideQuestions": True,
                                      "sidecarCompletion": False}
    with pytest.raises(WebError) as err:
        launch_ok(service)
    assert err.value.status == 409
    assert err.value.code == "CAPABILITY_UNAVAILABLE"


def test_launch_success_shape(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service, prompt="帮我看一下这个问题")
    session = detail["session"]
    assert session["harness"] == "pi"
    assert session["owner"] == "web"
    assert session["modelName"] == "fake-sonnet"
    assert session["providerName"] == "Fake Provider"
    assert session["state"] == "running"
    assert session["capabilities"] == {"send": True, "stop": True, "approve": False}
    assert session["title"] == "帮我看一下这个问题"
    kinds = [event["kind"] for event in detail["events"]]
    assert kinds.count("user") == 1
    assert drivers[0].prompts == ["帮我看一下这个问题"]
    sequences = [event["sequence"] for event in detail["events"]]
    assert sequences == sorted(sequences)


def test_launch_request_id_idempotent(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    first = launch_ok(service, request_id="req-a")
    second = launch_ok(service, request_id="req-a")
    assert first["session"]["id"] == second["session"]["id"]
    assert len(drivers) == 1, "replayed launch must not spawn again"
    # different payload with same requestId conflicts
    with pytest.raises(WebError) as err:
        launch_ok(service, request_id="req-a", prompt="different")
    assert err.value.code == "REQUEST_ID_CONFLICT"
    assert err.value.status == 409


def test_failed_launch_releases_request_id(tmp_path, seeded_seam):
    catalog = FakeCatalog(error=RuntimeError("preset missing"))
    service, _ = make_service(tmp_path, catalog=catalog)
    with pytest.raises(WebError) as err:
        launch_ok(service, request_id="req-b")
    assert err.value.code == "LAUNCH_RESOLVE_FAILED"
    # Same requestId can be retried after the failure.
    service._catalog.error = None
    detail = launch_ok(service, request_id="req-b")
    assert detail["session"]["id"]


def test_non_pi_harness_fail_closed(tmp_path, seeded_seam):
    catalog = FakeCatalog(launch_result={"harness": "codex", "model_info": {}, "runtime": {}, "cwd": "/tmp"})
    service, _ = make_service(tmp_path, catalog=catalog)
    with pytest.raises(WebError) as err:
        launch_ok(service)
    assert err.value.status == 409
    assert err.value.code == "CAPABILITY_UNAVAILABLE"
    assert "codex" in err.value.message


def test_send_and_idempotency(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    session_id = detail["session"]["id"]
    sent = service.send(session_id, {"requestId": "send-1", "text": "继续"})
    assert sent["session"]["state"] == "running"
    assert drivers[0].prompts[-1] == "继续"
    replay = service.send(session_id, {"requestId": "send-1", "text": "继续"})
    assert [e["sequence"] for e in replay["events"]] == [e["sequence"] for e in sent["events"]]
    assert drivers[0].prompts.count("继续") == 1
    with pytest.raises(WebError) as err:
        service.send(session_id, {"requestId": "send-1", "text": "other"})
    assert err.value.code == "REQUEST_ID_CONFLICT"


def test_send_rejected_for_invalid_payload(tmp_path, seeded_seam):
    service, _ = make_service(tmp_path)
    detail = launch_ok(service)
    session_id = detail["session"]["id"]
    for payload in ({}, {"requestId": "x1"}, {"requestId": "x2", "text": ""}, {"requestId": "x3", "text": 5}):
        with pytest.raises(WebError):
            service.send(session_id, payload)


def test_send_failure_maps_to_weberror(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    session_id = detail["session"]["id"]
    drivers[0].fail_next_prompt = {"type": "response", "success": False, "error": "no"}
    with pytest.raises(WebError) as err:
        service.send(session_id, {"requestId": "send-f", "text": "x"})
    assert err.value.code == "SEND_FAILED"
    assert err.value.status == 502
    drivers[0].timeout_next_prompt = True
    with pytest.raises(WebError) as err:
        service.send(session_id, {"requestId": "send-t", "text": "x"})
    assert err.value.code == "RPC_TIMEOUT"


def test_send_after_exit_fail_closed(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    session_id = detail["session"]["id"]
    drivers[0].kill()
    with pytest.raises(WebError) as err:
        service.send(session_id, {"requestId": "send-2", "text": "x"})
    assert err.value.code == "SESSION_NOT_ACTIVE"


def test_stop_is_abort_and_idempotent(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    session_id = detail["session"]["id"]
    stopped = service.stop(session_id, {"requestId": "stop-1"})
    assert stopped["session"]["state"] in {"running", "idle"}
    assert drivers[0].aborts == 1
    service.stop(session_id, {"requestId": "stop-1"})
    assert drivers[0].aborts == 1, "replay must not abort twice"
    drivers[0].kill()
    service.stop(session_id, {"requestId": "stop-2"})  # dead process: idempotent success


def test_approve_scope_and_not_found(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    session_id = detail["session"]["id"]
    live = service._sessions[session_id]
    with pytest.raises(WebError) as err:
        service.approve(session_id, "nope", {"requestId": "ap-0", "decision": "allow"})
    assert err.value.code == "APPROVAL_NOT_FOUND"
    service._apply_approval_pending(live, "ap-1", "confirm", "Allow?")
    # A real driver also emits the approval Event when the request arrives.
    service._apply_driver_event(
        live, {"id": "a-ap-1", "kind": "approval", "approvalId": "ap-1", "text": "Allow?"}
    )
    with pytest.raises(WebError) as err:
        service.approve(session_id, "ap-1", {"requestId": "ap-1b", "decision": "maybe"})
    assert err.value.code == "INVALID_REQUEST"
    result = service.approve(session_id, "ap-1", {"requestId": "ap-1", "decision": "allow"})
    assert ("ap-1", "allow") in drivers[0].ui_responses
    approval_events = [e for e in result["events"] if e["kind"] == "approval"]
    assert approval_events[-1].get("decision") == "allow"
    # Second decision for the same approval is gone.
    with pytest.raises(WebError) as err:
        service.approve(session_id, "ap-1", {"requestId": "ap-2", "decision": "deny"})
    assert err.value.code == "APPROVAL_NOT_FOUND"


def test_unsupported_approval_kind_propagates(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    session_id = detail["session"]["id"]
    live = service._sessions[session_id]
    service._apply_approval_pending(live, "sel-1", "select", "Choose")
    drivers[0].reject_ui = WebError("APPROVAL_KIND_UNSUPPORTED", "不支持", status=409)
    with pytest.raises(WebError) as err:
        service.approve(session_id, "sel-1", {"requestId": "sel-1", "decision": "allow"})
    assert err.value.status == 409


def test_session_not_found(tmp_path, seeded_seam):
    service, _ = make_service(tmp_path)
    with pytest.raises(WebError) as err:
        service.get_session("missing")
    assert err.value.status == 404
    with pytest.raises(WebError):
        service.send("missing", {"requestId": "r", "text": "x"})


def test_process_exit_states(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    session_id = detail["session"]["id"]
    live = service._sessions[session_id]
    service._apply_process_exited(live, 0, "")
    assert service.get_session(session_id)["session"]["state"] == "completed"
    assert service.get_session(session_id)["session"]["capabilities"]["send"] is False

    detail2 = launch_ok(service, request_id="req-c")
    live2 = service._sessions[detail2["session"]["id"]]
    service._apply_process_exited(live2, 7, "boom\nTypeError: x")
    view = service.get_session(detail2["session"]["id"])["session"]
    assert view["state"] == "error"
    assert all("TypeError: x" not in e["text"] for e in service.get_session(detail2["session"]["id"])["events"])

    detail3 = launch_ok(service, request_id="req-d")
    live3 = service._sessions[detail3["session"]["id"]]
    live3.stop_requested = True
    service._apply_process_exited(live3, 1, "")
    assert service.get_session(detail3["session"]["id"])["session"]["state"] == "stopped"


def test_waiting_state_with_pending_approval(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    session_id = detail["session"]["id"]
    live = service._sessions[session_id]
    service._apply_proto_state(live, "idle")
    assert service.get_session(session_id)["session"]["state"] == "idle"
    service._apply_approval_pending(live, "ap-9", "confirm", "?")
    assert service.get_session(session_id)["session"]["state"] == "waiting"
    assert service.get_session(session_id)["session"]["capabilities"]["approve"] is True
    service._apply_approval_resolved(live, "ap-9", "allow")
    assert service.get_session(session_id)["session"]["state"] == "running"
    assert service.get_session(session_id)["session"]["capabilities"]["approve"] is False


def test_persistence_and_restart_snapshot(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service, request_id="req-p", prompt="第一轮")
    session_id = detail["session"]["id"]
    service.send(session_id, {"requestId": "send-p", "text": "第二轮"})
    service.close()
    drivers[0].kill()

    catalog2 = FakeCatalog()
    service2, _ = make_service(tmp_path, catalog=catalog2)
    listed = service2.list_sessions()
    assert len(listed) == 1
    assert listed[0]["state"] == "stopped", "restart must not pretend the child runs"
    assert listed[0]["capabilities"] == {"send": False, "stop": False, "approve": False}
    detail2 = service2.get_session(session_id)
    texts = [e["text"] for e in detail2["events"] if e["kind"] == "user"]
    assert texts == ["第一轮", "第二轮"]
    sequences = [e["sequence"] for e in detail2["events"]]
    assert sequences == sorted(sequences)
    # requestId idempotency survives restart; conflicting reuse rejected.
    replay = service2.launch({"requestId": "req-p", "workspaceId": "ws-1", "presetId": "p-1", "prompt": "第一轮"})
    assert replay["session"]["id"] == session_id
    with pytest.raises(WebError):
        service2.launch({"requestId": "send-p", "workspaceId": "ws-1", "presetId": "p-1", "prompt": "x"})


def test_snapshot_thread_safety_under_concurrent_reads(tmp_path, seeded_seam):
    service, _ = make_service(tmp_path)
    detail = launch_ok(service)
    session_id = detail["session"]["id"]
    live = service._sessions[session_id]
    stop = threading.Event()
    errors: list[Exception] = []

    def reader():
        try:
            while not stop.is_set():
                snapshot = service.get_session(session_id)
                sequences = [e["sequence"] for e in snapshot["events"]]
                assert sequences == sorted(sequences)
        except Exception as exc:  # pragma: no cover - failure reporting
            errors.append(exc)

    threads = [threading.Thread(target=reader) for _ in range(3)]
    for thread in threads:
        thread.start()
    for index in range(40):
        service._apply_driver_event(live, {"id": f"m-{index}", "kind": "assistant", "text": f"t{index}"})
    stop.set()
    for thread in threads:
        thread.join(timeout=5)
    assert not errors


def test_closed_service_rejects_mutations(tmp_path, seeded_seam):
    service, _ = make_service(tmp_path)
    service.close()
    with pytest.raises(WebError) as err:
        launch_ok(service, request_id="after-close")
    assert err.value.status == 503


def test_state_file_has_no_secrets_and_is_task_scoped(tmp_path, seeded_seam):
    service, _ = make_service(tmp_path)
    detail = launch_ok(service)
    session_id = detail["session"]["id"]
    payload = json.loads((tmp_path / "state" / "sessions" / f"{session_id}.json").read_text())
    assert payload["schema"] == 1
    assert payload["session"]["owner"] == "web"
    assert "apiKey" not in json.dumps(payload)
    assert str(tmp_path) in str(service._state_root.resolve())


def test_timeout_replay_never_resends_a_possibly_accepted_message(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    sid = detail["session"]["id"]
    drivers[0].timeout_next_prompt = True
    with pytest.raises(WebError, match="超时"):
        service.send(sid, {"requestId": "uncertain-send", "text": "only-once"})
    before = list(drivers[0].prompts)
    replay = service.send(sid, {"requestId": "uncertain-send", "text": "only-once"})
    assert drivers[0].prompts == before
    assert len([e for e in replay["events"] if e["kind"] == "user" and e["text"] == "only-once"]) == 1
    service.close()
