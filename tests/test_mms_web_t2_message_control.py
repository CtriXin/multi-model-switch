"""T2 message-control contract tests: fixtures, regression and negative angles.

Independently written against the T2 contract (branch base ``origin/dev`` plus
the T2 backend change), covering the eight invariants the feature promises:

1. followUp 排队 — a busy session queues behind the current work, at the wire
   ``streamingBehavior: "followUp"``, and is delivered (``delivered``) in FIFO
   order once the service actually consumes it.
2. steer 安全边界与送达时机 — steering rides the native ``steer`` command, is
   delivered only after the in-flight tool call finishes and before the next
   LLM call, and never aborts the running turn.
3. interrupt 停止语义 — only stop (deny approvals → clear_queue → abort) ends
   the turn; queued messages become ``interrupted``.
4. queue 删除/恢复 — explicit clear marks ``cancelled``; restart/resume
   invalidates what the new process can no longer deliver; exit strands
   ``failed`` (or ``interrupted`` after a requested stop).
5. approval waiting 不可绕过 — a pending approval blocks steer before the
   driver is ever touched; follow-up still queues behind it.
6. 重复提交幂等 — one requestId, one wire command; mode is part of the
   request fingerprint.
7. 主任务已有结果保留 — interrupt keeps delivered messages, partial answers
   and event history intact.
8. fail closed — no steer support means 409/502 and a ``failed`` event, never
   a silent follow-up and never a fake success.

Part A drives the service with in-process driver doubles. Part B drives the
real ``PiRpcDriver`` against ``fixtures/mms_web/t2/pi_wire_child.py`` and
asserts on the recorded bidirectional wire log, so the proofs are about the
actual protocol writes, not the doubles.

On plain ``origin/dev`` (without the T2 backend) the tests that pin T2-only
behavior intentionally fail: the point of this file is to hold the contract
the backend change must satisfy. See the regression report for the exact
expected-failure list.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from mms_web.drivers.base import PipedProcessLauncher, RpcTimeoutError  # noqa: E402
from mms_web.drivers.launch_bridge import LaunchPlan  # noqa: E402
from mms_web.drivers.pi_rpc import PiRpcDriver  # noqa: E402
from mms_web.errors import WebError  # noqa: E402
from mms_web.sessions import SessionService  # noqa: E402

T2_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "mms_web" / "t2"
WIRE_CHILD = T2_FIXTURES / "pi_wire_child.py"


# -- shared harness -----------------------------------------------------------


class FakeCatalog:
    def __init__(self, launch_result=None) -> None:
        self.launch_result = launch_result or {
            "harness": "pi",
            "model_info": {"model": "t2-fake-model"},
            "runtime": {"id": "prov-1", "name": "Fake Provider", "channel": "chat"},
            "cwd": "/tmp/t2-fake-ws",
        }

    def resolve_launch(self, preset_id: str, workspace_id: str) -> dict:
        return self.launch_result


class T2Driver:
    """In-process driver double recording every command as a wire entry."""

    def __init__(self, sink=None) -> None:
        self.lock = threading.Lock()
        self._alive = True
        self._sink = sink
        self.wire: list[dict] = []
        self.fail_next_steer: dict | None = None
        self.timeout_next_steer = False

    def alive(self) -> bool:
        return self._alive

    def get_state(self) -> dict:
        return {"model": {"id": "t2-fake-model", "input": []}}

    def send_prompt(self, text: str, *, images=None) -> dict:
        with self.lock:
            self.wire.append({"type": "prompt", "message": text})
        return {"type": "response", "command": "prompt", "success": True}

    def steer(self, text: str, *, images=None) -> dict:
        with self.lock:
            self.wire.append({"type": "steer", "message": text})
        if self.timeout_next_steer:
            self.timeout_next_steer = False
            raise RpcTimeoutError("simulated steer timeout")
        if self.fail_next_steer is not None:
            failure, self.fail_next_steer = self.fail_next_steer, None
            return failure
        return {"type": "response", "command": "steer", "success": True}

    def abort(self) -> dict:
        with self.lock:
            self.wire.append({"type": "abort"})
        return {"type": "response", "command": "abort", "success": True}

    def pending_approvals(self) -> dict:
        return {}

    def respond_ui(self, approval_id: str, decision: str, value: str | None = None) -> None:
        with self.lock:
            self.wire.append({"type": "extension_ui_response", "id": approval_id,
                              "decision": decision, "value": value})
        if self._sink is not None:
            # A real driver reports the decision back through the sink.
            self._sink.upsert_event({"id": f"a-{approval_id}", "kind": "approval",
                                     "approvalId": approval_id, "decision": decision, "answer": value})
            self._sink.approval_resolved(approval_id, decision)

    def request(self, command: dict, timeout: float | None = None) -> dict:
        with self.lock:
            self.wire.append(dict(command))
        ctype = command.get("type")
        if ctype == "get_state":
            return {"success": True, "data": {"model": {"id": "t2-fake-model", "input": []}}}
        if ctype == "get_session_stats":
            return {"success": True, "data": {"tokens": {}, "totalMessages": 0}}
        return {"success": True, "data": {}}

    def close(self, *, graceful_timeout: float = 5.0) -> None:
        self._alive = False

    def kill(self) -> None:
        self._alive = False


class LegacyDriver(T2Driver):
    """A driver from before steer existed: no callable ``steer`` at all."""

    steer = None


def make_service(tmp_path: Path, driver_cls=T2Driver):
    catalog = FakeCatalog()
    drivers: list[T2Driver] = []

    def driver_factory(plan, sink):
        driver = driver_cls(sink=sink)
        drivers.append(driver)
        return driver

    def plan_builder(harness, model_info, runtime, cwd):
        return LaunchPlan(cmd=["true"], env={}, cwd=cwd, harness=harness)

    service = SessionService(
        config_root=tmp_path / "config",
        state_root=tmp_path / "state",
        catalog=catalog,
        driver_factory=driver_factory,
        launch_plan_builder=plan_builder,
        real_launch=True,
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


def user_events(detail):
    return [e for e in detail["events"] if e.get("kind") == "user"]


def user_status(detail, text):
    return next(e for e in user_events(detail) if e["text"] == text).get("status")


def deliver(service, session, text):
    """Simulate the service consuming a queued message (user message_start)."""
    service._apply_driver_event(session, {"consumedPrompt": text})


def wait_until(predicate, timeout: float = 8.0, what: str = "condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError(f"{what} not reached in {timeout}s")


# -- Part A: service contract with driver doubles ----------------------------


# 1. followUp 排队


def test_mode_contract_rejects_unknown_values(tmp_path, seeded_seam):
    """mode is a closed vocabulary; anything else fails before a send."""
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    sid = detail["session"]["id"]

    with pytest.raises(WebError) as err:
        service.send(sid, {"requestId": "m-1", "text": "x", "mode": "interrupt"})
    assert err.value.code == "INVALID_PARAMETER"
    assert err.value.status == 400
    with pytest.raises(WebError) as err:
        service.send(sid, {"requestId": "m-2", "text": "x", "mode": 7})
    assert err.value.code == "INVALID_PARAMETER"

    # A missing or null mode is the default follow-up, not an error.
    service.send(sid, {"requestId": "m-3", "text": "默认排队"})
    assert [w["type"] for w in drivers[0].wire[-1:]] == ["prompt"]
    explicit = service.send(sid, {"requestId": "m-4", "text": "显式排队", "mode": "followUp"})
    assert user_status(explicit, "显式排队") == "queued"


def test_followup_delivered_fifo_and_resequenced(tmp_path, seeded_seam):
    """Queued follow-ups are delivered in send order and move to the end."""
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    sid = detail["session"]["id"]
    session = service._get(sid)

    first = service.send(sid, {"requestId": "f-1", "text": "排队一"})
    second = service.send(sid, {"requestId": "f-2", "text": "排队二"})
    assert user_status(first, "排队一") == "queued"
    assert user_status(second, "排队二") == "queued"

    deliver(service, session, "排队一")
    deliver(service, session, "排队二")
    detail = service.get_session(sid)
    assert user_status(detail, "排队一") == "delivered"
    assert user_status(detail, "排队二") == "delivered"
    sequences = [e["sequence"] for e in user_events(detail) if e["text"] in {"排队一", "排队二"}]
    assert sequences == sorted(sequences), "delivery order must follow queue order"
    assert sequences[-1] == max(e["sequence"] for e in detail["events"])
    assert not session.pending_prompts, "pending map drains as messages land"


def test_queue_view_splits_lanes_and_follows_updates(tmp_path, seeded_seam):
    """The runtime view reports steering and follow-up lanes separately."""
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    sid = detail["session"]["id"]
    session = service._get(sid)

    service._apply_driver_event(session, {
        "id": "n-queue", "kind": "notice", "title": "待发送消息",
        "queue": ["改方向", "补充A", "补充B"],
        "queueSteering": ["改方向"], "queueFollowUp": ["补充A", "补充B"],
    })
    session.runtime_checked = 0
    runtime = service.runtime_view(sid)
    assert runtime["queueSteering"] == ["改方向"]
    assert runtime["queueFollowUp"] == ["补充A", "补充B"]
    assert runtime["queue"] == ["改方向", "补充A", "补充B"]

    service._apply_driver_event(session, {
        "id": "n-queue", "kind": "notice", "queue": [], "queueSteering": [], "queueFollowUp": [],
    })
    session.runtime_checked = 0
    runtime = service.runtime_view(sid)
    assert runtime["queue"] == [] and runtime["queueSteering"] == [] and runtime["queueFollowUp"] == []


# 2. steer 安全边界（service 层的部分；送达时机见 Part B）


def test_steer_on_idle_session_is_just_a_new_prompt(tmp_path, seeded_seam):
    """Nothing to steer into: the message starts a turn instead of erroring."""
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service, prompt="")
    sid = detail["session"]["id"]
    assert detail["session"]["state"] == "idle"

    service.send(sid, {"requestId": "st-idle", "text": "开始吧", "mode": "steer"})
    wire_types = [w["type"] for w in drivers[0].wire]
    assert wire_types.count("prompt") == 1
    assert "steer" not in wire_types, "idle steer must not write a steer command"


# 3. interrupt 停止语义


def test_stop_marks_queued_interrupted_not_cancelled(tmp_path, seeded_seam):
    """`interrupted` is reserved for the stop path; clearQueue keeps `cancelled`."""
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    sid = detail["session"]["id"]
    service.send(sid, {"requestId": "q-1", "text": "排队"})
    service.send(sid, {"requestId": "q-2", "text": "引导", "mode": "steer"})

    stopped = service.stop(sid, {"requestId": "stop-1"})
    assert [w["type"] for w in drivers[0].wire].count("abort") == 1
    assert user_status(stopped, "排队") == "interrupted"
    assert user_status(stopped, "引导") == "interrupted"


def test_stop_replay_aborts_once(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    sid = detail["session"]["id"]
    service.send(sid, {"requestId": "q-1", "text": "排队"})

    first = service.stop(sid, {"requestId": "stop-1"})
    second = service.stop(sid, {"requestId": "stop-1"})
    assert [w["type"] for w in drivers[0].wire].count("abort") == 1
    assert [e["id"] for e in second["events"]] == [e["id"] for e in first["events"]]


# 4. queue 删除/恢复


def test_clear_queue_cancels_and_leaves_approvals_alone(tmp_path, seeded_seam):
    """Explicit deletion cancels queued rows but never resolves approvals."""
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    sid = detail["session"]["id"]
    session = service._get(sid)
    service._apply_approval_pending(session, "ap-1", "confirm", "允许执行?")
    service.send(sid, {"requestId": "q-1", "text": "排队"})

    service.control(sid, {"requestId": "cq-1", "action": "clearQueue"})
    detail = service.get_session(sid)
    assert user_status(detail, "排队") == "cancelled"
    assert detail["session"]["state"] == "waiting", "the approval still waits"
    assert "ap-1" in service._get(sid).approvals, "clearQueue must not answer the dialog"


def test_exit_strands_queue_failed_and_stop_exit_keeps_interrupted(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)  # prompt "hi" leaves the session running
    sid = detail["session"]["id"]

    service.send(sid, {"requestId": "a-1", "text": "意外退出前的排队"})
    service._apply_process_exited(service._get(sid), 1, "boom")
    detail = service.get_session(sid)
    assert user_status(detail, "意外退出前的排队") == "failed", "queue died with the process"
    assert detail["session"]["state"] == "error"

    detail2 = launch_ok(service, request_id="req-2", prompt="第二轮")
    sid2 = detail2["session"]["id"]
    service.send(sid2, {"requestId": "a-2", "text": "停止前的排队"})
    service.stop(sid2, {"requestId": "stop-2"})
    service._apply_process_exited(service._get(sid2), 0, "")
    detail2 = service.get_session(sid2)
    assert user_status(detail2, "停止前的排队") == "interrupted", "user asked for the stop"
    assert detail2["session"]["state"] == "stopped"


def test_restart_invalidates_queue_and_keeps_final_statuses(tmp_path, seeded_seam):
    """A fresh service never advertises a dead process's queue."""
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    sid = detail["session"]["id"]
    session = service._get(sid)

    service.send(sid, {"requestId": "p-1", "text": "已送达"})
    deliver(service, session, "已送达")
    drivers[0].fail_next_steer = {"type": "response", "success": False, "error": "no"}
    with pytest.raises(WebError):
        service.send(sid, {"requestId": "p-2", "text": "已失败", "mode": "steer"})
    service.send(sid, {"requestId": "p-3", "text": "被打断"})
    service.stop(sid, {"requestId": "p-4"})
    detail = launch_ok(service, request_id="req-2")
    other = detail["session"]["id"]
    service.send(other, {"requestId": "p-5", "text": "还排着"})
    # Advertise a non-empty queue; the restart below must retract it.
    service._apply_driver_event(service._get(other), {
        "id": "n-queue", "kind": "notice", "queue": ["还排着"],
        "queueSteering": [], "queueFollowUp": ["还排着"],
    })
    service._get(other).runtime_checked = 0
    service.runtime_view(other)
    service.close()

    restored, _ = make_service(tmp_path)
    detail = restored.get_session(sid)
    assert user_status(detail, "已送达") == "delivered"
    assert user_status(detail, "已失败") == "failed"
    assert user_status(detail, "被打断") == "interrupted"
    other_detail = restored.get_session(other)
    assert user_status(other_detail, "还排着") == "cancelled", "restart invalidates the stale queue"
    runtime = other_detail["runtime"]
    for key in ("queue", "queueSteering", "queueFollowUp"):
        assert not runtime.get(key), "a fresh service must not advertise a dead queue"
    assert not runtime.get("pendingMessageCount")


# 5. approval waiting 不可绕过


def test_pending_approval_blocks_steer_before_the_driver(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    sid = detail["session"]["id"]
    session = service._get(sid)
    service._apply_approval_pending(session, "ap-1", "confirm", "允许执行?")
    wire_before = len(drivers[0].wire)

    with pytest.raises(WebError) as err:
        service.send(sid, {"requestId": "st-1", "text": "绕过审批", "mode": "steer"})
    assert err.value.code == "APPROVAL_PENDING"
    assert err.value.status == 409
    assert len(drivers[0].wire) == wire_before, "no command may reach the driver"
    assert "ap-1" in session.approvals, "the dialog itself is untouched"

    # The follow-up lane stays open: it queues behind the approval.
    queued = service.send(sid, {"requestId": "fu-1", "text": "之后处理"})
    assert user_status(queued, "之后处理") == "queued"

    # Resolve, and steering becomes deliverable again.
    service.approve(sid, "ap-1", {"requestId": "ap-ok", "decision": "allow"})
    service.send(sid, {"requestId": "st-2", "text": "现在引导", "mode": "steer"})
    assert any(w["type"] == "steer" and w["message"] == "现在引导" for w in drivers[0].wire)


# 6. 重复提交幂等


def test_duplicate_request_sends_once_and_mode_joins_the_fingerprint(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    sid = detail["session"]["id"]

    first = service.send(sid, {"requestId": "dup-1", "text": "只发一次"})
    again = service.send(sid, {"requestId": "dup-1", "text": "只发一次"})
    prompts = [w for w in drivers[0].wire if w["type"] == "prompt" and w["message"] == "只发一次"]
    assert prompts == [{"type": "prompt", "message": "只发一次"}]
    assert [e["id"] for e in again["events"]] == [e["id"] for e in first["events"]]

    # The same requestId promising a different delivery mode is a conflict,
    # not a silent replay of the first semantics.
    with pytest.raises(WebError) as err:
        service.send(sid, {"requestId": "dup-1", "text": "只发一次", "mode": "steer"})
    assert err.value.code == "REQUEST_ID_CONFLICT"


# 7. 主任务已有结果保留


def test_interrupt_preserves_history_and_finished_work(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    sid = detail["session"]["id"]
    session = service._get(sid)

    service._apply_driver_event(session, {"id": "m-done", "kind": "assistant", "text": "完整回答"})
    service._apply_driver_event(session, {"id": "m-part", "kind": "assistant", "text": "半截回答"})
    service._apply_driver_event(session, {"id": "t-1", "kind": "tool", "title": "read", "text": "执行中", "status": "running"})
    service.send(sid, {"requestId": "d-1", "text": "已送达"})
    deliver(service, session, "已送达")
    before = service.get_session(sid)
    old_sequences = {e["id"]: e["sequence"] for e in before["events"]}
    service.send(sid, {"requestId": "q-1", "text": "排队"})

    stopped = service.stop(sid, {"requestId": "stop-1"})
    # The aborted run settles (agent_settled) and unfinished tools close out.
    service._apply_proto_state(session, "idle")
    stopped = service.get_session(sid)
    events = {e["id"]: e for e in stopped["events"]}
    assert events["m-done"]["text"] == "完整回答"
    assert events["m-part"]["text"] == "半截回答", "partial answers survive verbatim"
    assert "未收到此工具的完成回报" in events["t-1"]["text"]
    assert user_status(stopped, "已送达") == "delivered", "finished work is not retroactively queued"
    assert user_status(stopped, "排队") == "interrupted"
    for event_id, sequence in old_sequences.items():
        assert events[event_id]["sequence"] == sequence, "history must not be renumbered"


# 8. fail closed：不支持 steer / steer 被拒绝 / 超时


def test_legacy_driver_fails_closed_without_silent_followup(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path, driver_cls=LegacyDriver)
    detail = launch_ok(service)
    sid = detail["session"]["id"]

    with pytest.raises(WebError) as err:
        service.send(sid, {"requestId": "st-1", "text": "引导", "mode": "steer"})
    assert err.value.code == "CAPABILITY_UNAVAILABLE"
    assert err.value.status == 409
    prompts = [w for w in drivers[0].wire if w["type"] == "prompt"]
    assert prompts == [{"type": "prompt", "message": "hi"}], \
        "a refused steer must not fall back to a queued prompt"
    assert user_status(service.get_session(sid), "引导") == "failed"


def test_rejected_steer_is_reported_and_never_resent(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    sid = detail["session"]["id"]

    drivers[0].fail_next_steer = {"type": "response", "command": "steer", "success": False, "error": "rejected"}
    with pytest.raises(WebError) as err:
        service.send(sid, {"requestId": "st-1", "text": "引导", "mode": "steer"})
    assert err.value.code == "STEER_FAILED"
    assert err.value.status == 502
    wire_types = [w["type"] for w in drivers[0].wire]
    assert wire_types.count("steer") == 1 and wire_types.count("prompt") == 1
    assert user_status(service.get_session(sid), "引导") == "failed"


def test_timed_out_steer_replays_without_resending(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    sid = detail["session"]["id"]

    drivers[0].timeout_next_steer = True
    with pytest.raises(WebError) as err:
        service.send(sid, {"requestId": "st-1", "text": "引导", "mode": "steer"})
    assert err.value.code == "RPC_TIMEOUT"
    detail = service.get_session(sid)
    event = next(e for e in user_events(detail) if e["text"] == "引导")
    assert event["status"] == "failed"
    assert event["contextUsage"]["state"] == "uncertain"

    replay = service.send(sid, {"requestId": "st-1", "text": "引导", "mode": "steer"})
    assert [w["type"] for w in drivers[0].wire].count("steer") == 1, \
        "a possibly accepted steer must never be written twice"
    assert [e["id"] for e in replay["events"]] == [e["id"] for e in service.get_session(sid)["events"]]


# -- Part B: protocol contract over the real driver + wire child ---------------


def read_wire(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def wire_in(wire: list[dict]) -> list[dict]:
    return [entry["line"] for entry in wire if entry["dir"] == "in"]


def wire_out(wire: list[dict]) -> list[dict]:
    return [entry["line"] for entry in wire if entry["dir"] == "out"]


def make_wire_service(tmp_path: Path, scenario: str):
    wire_path = tmp_path / f"wire-{scenario}-{time.monotonic_ns()}.jsonl"
    drivers: list[PiRpcDriver] = []

    def driver_factory(plan, sink):
        process = PipedProcessLauncher().popen(
            [sys.executable, str(WIRE_CHILD),
             str(T2_FIXTURES / "scenarios" / f"{scenario}.jsonl"), str(wire_path)],
            env=dict(os.environ), cwd=str(REPO_ROOT),
        )
        driver = PiRpcDriver(process, sink, name=f"t2-{scenario}")
        drivers.append(driver)
        return driver

    def plan_builder(harness, model_info, runtime, cwd):
        return LaunchPlan(cmd=["true"], env={}, cwd=cwd, harness=harness)

    service = SessionService(
        config_root=tmp_path / "config",
        state_root=tmp_path / "state",
        catalog=FakeCatalog(),
        driver_factory=driver_factory,
        launch_plan_builder=plan_builder,
        real_launch=True,
    )

    def snapshot() -> list[dict]:
        """Read the wire log without disturbing the live child."""
        return read_wire(wire_path)

    def teardown() -> None:
        for driver in drivers:
            try:
                driver.close(graceful_timeout=2.0)
            except Exception:
                pass

    return service, snapshot, teardown


def session_event(detail, **match):
    for event in detail["events"]:
        if all(event.get(key) == value for key, value in match.items()):
            return event
    return None


# 1. followUp 排队（wire 层）


def test_wire_busy_send_is_streaming_behavior_followup(tmp_path, seeded_seam):
    """A busy session's send must carry streamingBehavior=followUp at the wire."""
    service, snapshot, teardown = make_wire_service(tmp_path, "steer-tool-flow")
    try:
        detail = launch_ok(service, prompt="start-tool-run")
        sid = detail["session"]["id"]
        wait_until(lambda: session_event(service.get_session(sid), kind="tool", status="running") is not None,
                   what="in-flight tool observed")

        service.send(sid, {"requestId": "w-fu", "text": "排队到工具之后"})
        wire = snapshot()
        prompts = [c for c in wire_in(wire) if c.get("type") == "prompt"]
        assert prompts and prompts[-1]["message"] == "排队到工具之后"
        assert prompts[-1].get("streamingBehavior") == "followUp", \
            "a running session must queue, not interrupt"
        assert all(c.get("type") != "steer" for c in wire_in(wire)), \
            "the default mode never writes a steer command"
    finally:
        teardown()


def test_wire_idle_launch_prompt_is_direct(tmp_path, seeded_seam):
    """The launch prompt runs immediately: no streamingBehavior is written."""
    service, snapshot, teardown = make_wire_service(tmp_path, "steer-tool-flow")
    try:
        detail = launch_ok(service, prompt="你好")
        sid = detail["session"]["id"]
        wait_until(lambda: service.get_session(sid)["session"]["state"] == "idle",
                   what="first turn settles")
        wire = snapshot()
        first_prompt = next(c for c in wire_in(wire) if c.get("type") == "prompt")
        assert first_prompt["message"] == "你好"
        assert "streamingBehavior" not in first_prompt, "idle sends are direct"
    finally:
        teardown()


# 2. steer 安全边界与送达时机（wire 层）


def test_wire_steer_waits_for_inflight_tool_before_next_llm(tmp_path, seeded_seam):
    """Steer lands after the in-flight tool call, before the next LLM call."""
    service, snapshot, teardown = make_wire_service(tmp_path, "steer-tool-flow")
    try:
        detail = launch_ok(service, prompt="start-tool-run")
        sid = detail["session"]["id"]
        wait_until(lambda: session_event(service.get_session(sid), kind="tool", status="running") is not None,
                   what="in-flight tool observed")

        sent = service.send(sid, {"requestId": "w-st", "text": "改用另一个文件", "mode": "steer"})
        assert user_status(sent, "改用另一个文件") == "queued"
        wait_until(lambda: user_status(service.get_session(sid), "改用另一个文件") == "delivered",
                   what="steering message delivered")
        wait_until(lambda: session_event(service.get_session(sid), kind="assistant", text="已按引导调整方向") is not None,
                   what="steered reply lands")
        wire = snapshot()

        incoming = wire_in(wire)
        steers = [c for c in incoming if c.get("type") == "steer"]
        assert len(steers) == 1 and steers[0]["message"] == "改用另一个文件"
        assert all(c.get("type") != "abort" for c in incoming), \
            "steering must never end the turn"

        outgoing = wire_out(wire)

        def first_index(predicate):
            return next(i for i, o in enumerate(outgoing) if predicate(o))

        tool_end = first_index(lambda o: o.get("type") == "tool_execution_end")
        consumed = first_index(lambda o: o.get("type") == "message_start"
                               and (o.get("message") or {}).get("role") == "user")
        llm_reply = first_index(lambda o: o.get("type") == "message_start"
                                and (o.get("message") or {}).get("role") == "assistant")
        assert tool_end < consumed < llm_reply, \
            "tool result first, then the steering text, then the next LLM call"

        detail = service.get_session(sid)
        tool = session_event(detail, kind="tool", status="done")
        assert tool is not None and "工具完整输出" in tool.get("text", "")
        partial = [e for e in detail["events"] if e.get("kind") == "assistant"]
        assert any(e.get("text") == "已按引导调整方向" for e in partial)
    finally:
        teardown()


def test_wire_duplicate_steer_request_writes_one_command(tmp_path, seeded_seam):
    service, snapshot, teardown = make_wire_service(tmp_path, "steer-tool-flow")
    try:
        detail = launch_ok(service, prompt="start-tool-run")
        sid = detail["session"]["id"]
        wait_until(lambda: session_event(service.get_session(sid), kind="tool", status="running") is not None,
                   what="in-flight tool observed")

        first = service.send(sid, {"requestId": "w-dup", "text": "只引导一次", "mode": "steer"})
        replay = service.send(sid, {"requestId": "w-dup", "text": "只引导一次", "mode": "steer"})
        current = service.get_session(sid)
        assert [e["id"] for e in replay["events"]] == [e["id"] for e in current["events"]], \
            "a replay must return the live session view, not a stale snapshot"
        assert user_status(first, "只引导一次") == user_status(replay, "只引导一次")
        wire = snapshot()
        steers = [c for c in wire_in(wire) if c.get("type") == "steer"]
        assert len(steers) == 1, "a replayed steer must not hit the wire twice"
    finally:
        teardown()


# 3+5. interrupt 停止语义 + approval 不可绕过（wire 层）


def test_wire_approval_gate_blocks_steer_and_queues_followup_behind(tmp_path, seeded_seam):
    """A pending approval is part of the turn: steer may not jump it."""
    service, snapshot, teardown = make_wire_service(tmp_path, "approval-gate")
    try:
        detail = launch_ok(service, prompt="ask-for-approval")
        sid = detail["session"]["id"]
        wait_until(lambda: service.get_session(sid)["session"]["state"] == "waiting",
                   what="approval observed")

        with pytest.raises(WebError) as err:
            service.send(sid, {"requestId": "w-gate", "text": "绕过审批", "mode": "steer"})
        assert err.value.code == "APPROVAL_PENDING"
        wire = snapshot()
        incoming = wire_in(wire)
        assert all(c.get("type") != "steer" for c in incoming), \
            "the service gate must stop the steer before the protocol write"
        steer_rejections = [o for o in wire_out(wire)
                            if o.get("type") == "response" and o.get("command") == "steer"]
        assert not steer_rejections, "no steer response may exist either"

        service.send(sid, {"requestId": "w-fu", "text": "排队到审批之后"})
        wire = snapshot()
        followup = [c for c in wire_in(wire) if c.get("type") == "prompt"][-1]
        assert followup["message"] == "排队到审批之后"
        assert followup.get("streamingBehavior") == "followUp", \
            "the default lane queues behind the approval"
        assert user_status(service.get_session(sid), "排队到审批之后") == "queued"

        service.approve(sid, "ui-t2-confirm", {"requestId": "w-ap", "decision": "allow"})
        wait_until(lambda: service.get_session(sid)["session"]["state"] == "idle",
                   what="dialog resolved and turn finished")
        wire = snapshot()
        answer = [c for c in wire_in(wire) if c.get("type") == "extension_ui_response"]
        assert answer and answer[-1]["id"] == "ui-t2-confirm" and answer[-1].get("confirmed") is True
    finally:
        teardown()


def test_wire_stop_denies_approval_clears_queue_then_aborts(tmp_path, seeded_seam):
    """Stop is the only interrupt: deny dialog, clear queue, abort — in order."""
    service, snapshot, teardown = make_wire_service(tmp_path, "approval-gate")
    try:
        detail = launch_ok(service, prompt="ask-for-approval")
        sid = detail["session"]["id"]
        wait_until(lambda: service.get_session(sid)["session"]["state"] == "waiting",
                   what="approval observed")
        service.send(sid, {"requestId": "w-fu", "text": "停止前的排队"})

        stopped = service.stop(sid, {"requestId": "w-stop"})
        assert user_status(stopped, "停止前的排队") == "interrupted"
        wire = snapshot()
        incoming = wire_in(wire)
        kinds = [c.get("type") for c in incoming]
        assert "extension_ui_response" in kinds and "clear_queue" in kinds and "abort" in kinds
        assert kinds.index("extension_ui_response") < kinds.index("clear_queue") < kinds.index("abort")
        deny = next(c for c in incoming if c.get("type") == "extension_ui_response")
        assert deny.get("confirmed") is False, "stop denies the open dialog"

        detail = service.get_session(sid)
        approval = session_event(detail, kind="approval")
        assert approval is not None and approval.get("decision") == "deny"
    finally:
        teardown()
