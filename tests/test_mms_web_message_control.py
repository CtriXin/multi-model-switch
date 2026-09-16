"""Pilot T2 message-control contract tests (SessionService + driver seam).

Semantics under test:
- default send while busy is a Pi follow-up (queued behind current work);
- ``mode: "steer"`` is Pi native steering, delivered after the in-flight tool
  calls finish; it never ends the current turn;
- a pending approval is part of the turn and must never be bypassed by steer;
- only stop/interrupt (abort) ends the current turn; partial results survive;
- delivery status distinguishes queued / delivered / failed / interrupted;
- a failed steer is reported, never silently degraded into a follow-up;
- status survives service restart; resume/restart invalidates stale queued rows.

No subprocess, no MMS modules, no real config.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
import sys

sys.path.insert(0, str(REPO_ROOT))

from mms_web.drivers.base import DriverClosedError, RpcTimeoutError  # noqa: E402
from mms_web.errors import WebError  # noqa: E402
from mms_web.sessions import SessionService  # noqa: E402


class FakeCatalog:
    def __init__(self, launch_result=None) -> None:
        self.launch_result = launch_result or {
            "harness": "pi",
            "model_info": {"model": "fake-sonnet"},
            "runtime": {"id": "prov-1", "name": "Fake Provider", "channel": "chat"},
            "cwd": "/tmp/fake-ws",
        }

    def resolve_launch(self, preset_id: str, workspace_id: str) -> dict:
        return self.launch_result


class FakeDriver:
    """In-process driver double with steer/follow-up/abort instrumentation."""

    def __init__(self, sink=None) -> None:
        self.lock = threading.Lock()
        self._alive = True
        self._sink = sink
        self.prompts: list[str] = []
        self.steers: list[str] = []
        self.aborts = 0
        self.ui_responses: list[tuple[str, str]] = []
        self.pending: dict[str, dict] = {}
        self.fail_next_prompt: dict | None = None
        self.fail_next_steer: dict | None = None
        self.timeout_next_steer = False
        # What Pi would still be holding, by lane. Rewriting the queue reads
        # this back through clear_queue, so the double has to model it.
        self.queued_steering: list[str] = []
        self.queued_followup: list[str] = []
        self.follow_ups: list[str] = []
        self.fail_next_follow_up = False

    def alive(self) -> bool:
        return self._alive

    def send_prompt(self, text: str, *, images=None) -> dict:
        if self.fail_next_prompt is not None:
            failure, self.fail_next_prompt = self.fail_next_prompt, None
            return failure
        with self.lock:
            self.prompts.append(text)
            self.queued_followup.append(text)
        return {"type": "response", "command": "prompt", "success": True}

    def steer(self, text: str, *, images=None) -> dict:
        if self.timeout_next_steer:
            self.timeout_next_steer = False
            raise RpcTimeoutError("timeout")
        if self.fail_next_steer is not None:
            failure, self.fail_next_steer = self.fail_next_steer, None
            return failure
        with self.lock:
            self.steers.append(text)
            self.queued_steering.append(text)
        return {"type": "response", "command": "steer", "success": True}

    def follow_up(self, text: str, *, images=None) -> dict:
        if self.fail_next_follow_up:
            self.fail_next_follow_up = False
            raise DriverClosedError("pi exited")
        with self.lock:
            self.follow_ups.append(text)
            self.queued_followup.append(text)
        return {"type": "response", "command": "follow_up", "success": True}

    def clear_queue(self, *, timeout=None) -> dict:
        with self.lock:
            cleared = {"steering": list(self.queued_steering), "followUp": list(self.queued_followup)}
            self.queued_steering.clear()
            self.queued_followup.clear()
        return cleared

    def abort(self) -> dict:
        with self.lock:
            self.aborts += 1
        return {"type": "response", "command": "abort", "success": True}

    def request(self, command: dict, timeout=None) -> dict:
        ctype = command.get("type")
        if ctype == "get_state":
            return {"success": True, "data": {"model": {"id": "fake-sonnet", "input": []}}}
        if ctype == "get_session_stats":
            return {"success": True, "data": {"tokens": {}, "totalMessages": 0}}
        if ctype == "clear_queue":
            return {"success": True, "data": {"steering": [], "followUp": []}}
        return {"success": True, "data": {}}

    def get_state(self) -> dict:
        return {"model": {"id": "fake-sonnet", "input": []}}

    def respond_ui(self, approval_id: str, decision: str, value=None) -> None:
        with self.lock:
            self.ui_responses.append((approval_id, decision))
            self.pending.pop(approval_id, None)
        if self._sink is not None:
            self._sink.upsert_event(
                {"id": f"a-{approval_id}", "kind": "approval", "approvalId": approval_id, "decision": decision}
            )
            self._sink.approval_resolved(approval_id, decision)

    def close(self, *, graceful_timeout: float = 5.0) -> None:
        self._alive = False

    def kill(self) -> None:
        self._alive = False


def make_service(tmp_path: Path, catalog=None, **kwargs):
    catalog = catalog or FakeCatalog()
    drivers: list[FakeDriver] = []

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
        real_launch=True,
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


def user_events(detail):
    return [e for e in detail["events"] if e["kind"] == "user"]


def deliver(service, session, text):
    """Simulate Pi consuming the message: user message_start observed."""
    driver = getattr(session, "driver", None)
    if driver is not None:
        # Pi takes a delivered message out of its own queue.
        for lane in (driver.queued_steering, driver.queued_followup):
            if text in lane:
                lane.remove(text)
                break
    service._apply_driver_event(session, {"consumedPrompt": text})


# -- default send stays follow-up -------------------------------------------


def test_default_send_while_running_is_followup_then_delivered(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    sid = detail["session"]["id"]
    session = service._get(sid)

    sent = service.send(sid, {"requestId": "s-1", "text": "排队补充"})
    queued = next(e for e in user_events(sent) if e["text"] == "排队补充")
    assert queued["status"] == "queued"
    assert drivers[0].prompts[-1] == "排队补充"
    assert drivers[0].steers == [], "default send must not use the steer command"

    deliver(service, session, drivers[0].prompts[-1])
    detail = service.get_session(sid)
    delivered = next(e for e in user_events(detail) if e["text"] == "排队补充")
    assert delivered["status"] == "delivered"
    assert delivered["sequence"] == max(e["sequence"] for e in detail["events"])


# -- steer: immediate guidance after tool calls ------------------------------


def test_steer_uses_steer_command_and_keeps_turn_running(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    sid = detail["session"]["id"]
    session = service._get(sid)

    sent = service.send(sid, {"requestId": "st-1", "text": "换个方向", "mode": "steer"})
    assert drivers[0].steers == ["换个方向"]
    assert drivers[0].aborts == 0, "steer must never abort the current turn"
    event = next(e for e in user_events(sent) if e["text"] == "换个方向")
    assert event["status"] == "queued"
    assert sent["session"]["state"] == "running"

    deliver(service, session, drivers[0].steers[-1])
    detail = service.get_session(sid)
    event = next(e for e in user_events(detail) if e["text"] == "换个方向")
    assert event["status"] == "delivered"
    assert detail["session"]["state"] == "running", "steer delivery does not settle the turn"


def test_steer_on_idle_session_sends_as_new_prompt(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service, prompt="")
    sid = detail["session"]["id"]
    assert detail["session"]["state"] == "idle"
    service.send(sid, {"requestId": "st-idle", "text": "开始吧", "mode": "steer"})
    assert drivers[0].prompts == ["开始吧"], "idle steer is just a new prompt"
    assert drivers[0].steers == []


def test_invalid_mode_rejected(tmp_path, seeded_seam):
    service, _ = make_service(tmp_path)
    detail = launch_ok(service)
    with pytest.raises(WebError) as err:
        service.send(detail["session"]["id"], {"requestId": "m-bad", "text": "x", "mode": "interrupt"})
    assert err.value.code == "INVALID_PARAMETER"


def test_mode_is_part_of_request_fingerprint(tmp_path, seeded_seam):
    service, _ = make_service(tmp_path)
    detail = launch_ok(service)
    sid = detail["session"]["id"]
    service.send(sid, {"requestId": "m-fp", "text": "x"})
    with pytest.raises(WebError) as err:
        service.send(sid, {"requestId": "m-fp", "text": "x", "mode": "steer"})
    assert err.value.code == "REQUEST_ID_CONFLICT"


# -- approval waiting must not be bypassed -----------------------------------


def test_steer_blocked_while_approval_pending(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    sid = detail["session"]["id"]
    session = service._get(sid)
    service._apply_approval_pending(session, "ap-1", "confirm", "允许执行?")
    assert service.get_session(sid)["session"]["state"] == "waiting"

    with pytest.raises(WebError) as err:
        service.send(sid, {"requestId": "st-blocked", "text": "绕过审批", "mode": "steer"})
    assert err.value.code == "APPROVAL_PENDING"
    assert err.value.status == 409
    assert drivers[0].steers == [] and drivers[0].prompts == ["hi"]
    assert "ap-1" in session.approvals, "rejected steer must not touch the pending approval"

    # The default follow-up still queues behind the approval instead.
    queued = service.send(sid, {"requestId": "fu-wait", "text": "之后处理"})
    event = next(e for e in user_events(queued) if e["text"] == "之后处理")
    assert event["status"] == "queued"

    # Resolve the approval; steering is available again.
    service.approve(sid, "ap-1", {"requestId": "ap-ok", "decision": "allow"})
    assert service.get_session(sid)["session"]["state"] == "running"
    service.send(sid, {"requestId": "st-after", "text": "现在引导", "mode": "steer"})
    assert drivers[0].steers == ["现在引导"]


# -- failure never degrades silently -----------------------------------------


def test_failed_steer_is_reported_and_never_resent_as_followup(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    sid = detail["session"]["id"]

    drivers[0].fail_next_steer = {"type": "response", "success": False, "error": "no steering"}
    with pytest.raises(WebError) as err:
        service.send(sid, {"requestId": "st-fail", "text": "引导", "mode": "steer"})
    assert err.value.code == "STEER_FAILED"
    assert drivers[0].prompts == ["hi"], "a failed steer must not fall back to follow-up"
    event = next(e for e in user_events(service.get_session(sid)) if e["text"] == "引导")
    assert event["status"] == "failed"


def test_timed_out_steer_is_uncertain_and_replay_never_resends(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    sid = detail["session"]["id"]

    drivers[0].timeout_next_steer = True
    with pytest.raises(WebError) as err:
        service.send(sid, {"requestId": "st-timeout", "text": "引导", "mode": "steer"})
    assert err.value.code == "RPC_TIMEOUT"
    event = next(e for e in user_events(service.get_session(sid)) if e["text"] == "引导")
    assert event["status"] == "failed"
    assert event["contextUsage"]["state"] == "uncertain"

    replay = service.send(sid, {"requestId": "st-timeout", "text": "引导", "mode": "steer"})
    assert drivers[0].steers == [], "a possibly accepted steer must never be sent twice"
    assert [e["id"] for e in replay["events"]] == [e["id"] for e in service.get_session(sid)["events"]]


# -- stop interrupts; partial results survive ---------------------------------


def test_stop_interrupts_queued_and_preserves_partial_results(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    sid = detail["session"]["id"]
    session = service._get(sid)

    service._apply_driver_event(session, {"id": "m-partial", "kind": "assistant", "text": "半截回答"})
    service.send(sid, {"requestId": "q-1", "text": "排队一"})
    service.send(sid, {"requestId": "q-2", "text": "排队二", "mode": "steer"})

    stopped = service.stop(sid, {"requestId": "stop-1"})
    assert drivers[0].aborts == 1
    statuses = {e["text"]: e.get("status") for e in user_events(stopped)}
    assert statuses["排队一"] == "interrupted"
    assert statuses["排队二"] == "interrupted"
    partial = next(e for e in stopped["events"] if e["id"] == "m-partial")
    assert partial["text"] == "半截回答", "existing events and partial results survive interrupt"

    replay = service.stop(sid, {"requestId": "stop-1"})
    assert drivers[0].aborts == 1, "stop replay must not abort twice"
    assert [e["id"] for e in replay["events"]] == [e["id"] for e in stopped["events"]]


def test_clear_queue_marks_cancelled_not_interrupted(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    sid = detail["session"]["id"]
    service.send(sid, {"requestId": "q-c", "text": "排队"})
    service.control(sid, {"requestId": "cq-1", "action": "clearQueue"})
    event = next(e for e in user_events(service.get_session(sid)) if e["text"] == "排队")
    assert event["status"] == "cancelled"


def test_process_exit_strands_queued_messages(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    sid = detail["session"]["id"]
    session = service._get(sid)
    service.send(sid, {"requestId": "q-x", "text": "排队"})

    service._apply_process_exited(session, 1, "boom")
    event = next(e for e in user_events(service.get_session(sid)) if e["text"] == "排队")
    assert event["status"] == "failed", "unexpected exit: queued delivery is impossible"
    assert service.get_session(sid)["session"]["state"] == "error"


# -- queue state ---------------------------------------------------------------


def test_queue_state_split_and_cleared_on_stop(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    sid = detail["session"]["id"]
    session = service._get(sid)
    service._apply_driver_event(session, {
        "id": "n-queue", "kind": "notice",
        "queue": ["引导", "跟进"], "queueSteering": ["引导"], "queueFollowUp": ["跟进"],
    })
    session.runtime_checked = 0
    runtime = service.runtime_view(sid)
    assert runtime["queueSteering"] == ["引导"]
    assert runtime["queueFollowUp"] == ["跟进"]
    assert runtime["queue"] == ["引导", "跟进"]

    service.stop(sid, {"requestId": "stop-q"})
    session.runtime_checked = 0
    runtime = service.runtime_view(sid)
    assert runtime["queue"] == [] and runtime["queueSteering"] == [] and runtime["queueFollowUp"] == []


# -- recovery ------------------------------------------------------------------


def make_resumable_service(tmp_path):
    runtime_root = tmp_path / "state" / "runtimes" / "rt-1"
    runtime_root.mkdir(parents=True)
    catalog = FakeCatalog({
        "harness": "pi",
        "model_info": {"model": "fake-sonnet"},
        "runtime": {"id": "prov-1", "name": "Fake", "channel": "chat", "_webConfigRoot": str(runtime_root)},
        "cwd": str(tmp_path),
    })
    return make_service(tmp_path, catalog=catalog)


def test_resume_invalidates_stale_queued_messages(tmp_path, seeded_seam):
    service, drivers = make_resumable_service(tmp_path)
    detail = launch_ok(service)
    sid = detail["session"]["id"]
    session = service._get(sid)
    runtime_root = Path(session.meta["runtimeRoot"])
    (runtime_root / "conversation.jsonl").write_text("")

    service.send(sid, {"requestId": "q-r", "text": "旧排队"})
    drivers[0].kill()  # process died without an exit callback: queue lost

    sent = service.send(sid, {"requestId": "q-r2", "text": "恢复后继续"})
    stale = next(e for e in user_events(sent) if e["text"] == "旧排队")
    assert stale["status"] == "cancelled", "resume must invalidate the dead process queue"
    assert len(drivers) == 2 and drivers[1].prompts == ["恢复后继续"]


def test_statuses_survive_service_restart(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    sid = detail["session"]["id"]
    session = service._get(sid)

    service.send(sid, {"requestId": "p-1", "text": "已送达"})
    deliver(service, session, drivers[0].prompts[-1])
    drivers[0].fail_next_steer = {"type": "response", "success": False, "error": "no"}
    with pytest.raises(WebError):
        service.send(sid, {"requestId": "p-2", "text": "已失败", "mode": "steer"})
    service.send(sid, {"requestId": "p-3", "text": "被打断"})
    service.stop(sid, {"requestId": "p-4"})
    service.send(sid, {"requestId": "p-5", "text": "还排着"})
    service.close()

    restored, _ = make_service(tmp_path)
    detail = restored.get_session(sid)
    statuses = {e["text"]: e.get("status") for e in user_events(detail)}
    assert statuses["已送达"] == "delivered"
    assert statuses["已失败"] == "failed"
    assert statuses["被打断"] == "interrupted"
    assert statuses["还排着"] == "cancelled", "restart invalidates an undelivered queue entry"
    runtime = detail["runtime"]
    assert runtime.get("queue", []) == [] and "pendingMessageCount" not in runtime


# -- acting on one queued message ------------------------------------------
#
# Pi has no per-message delete, promote or reorder: the only primitive is
# clear_queue. Each of these actions is the service clearing both lanes and
# putting back what should stay, in the order it should go.


def queue_two(service, drivers, tmp_path):
    """A running session with two follow-ups waiting behind the current work."""
    detail = launch_ok(service)
    sid = detail["session"]["id"]
    session = service._get(sid)
    driver = drivers[0]
    # The launch prompt is the work in flight, not something still queued.
    driver.queued_followup.clear()
    service.send(sid, {"requestId": "q-a", "text": "先补一段说明"})
    service.send(sid, {"requestId": "q-b", "text": "最后再总结一次"})
    return sid, session, driver


def queued_ids(service, sid):
    return [item["id"] for item in service._get(sid).pending_view()]


def test_queue_exposes_addressable_ids_and_lanes(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    sid, session, driver = queue_two(service, drivers, tmp_path)
    pending = session.pending_view()
    assert [item["text"] for item in pending] == ["先补一段说明", "最后再总结一次"]
    assert {item["mode"] for item in pending} == {"followUp"}
    assert all(item["id"] for item in pending)
    assert service.get_session(sid)["runtime"]["pending"] == pending
    # Every mutation response carries the queue the caller just acted on, not
    # the runtime snapshot's older copy.
    assert service.queue(sid, {"requestId": "q-z", "action": "move",
                               "id": pending[0]["id"], "toIndex": 0})["runtime"]["pending"] == pending
    assert service.get_session(sid)["session"]["capabilities"]["queueControl"] is True


def test_promoting_a_queued_message_moves_it_into_the_steering_lane(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    sid, session, driver = queue_two(service, drivers, tmp_path)
    second = queued_ids(service, sid)[1]
    service.queue(sid, {"requestId": "q-1", "action": "steer", "id": second})
    pending = session.pending_view()
    # Steering is delivered first, so the promoted message leads.
    assert [(item["text"], item["mode"]) for item in pending] == [
        ("最后再总结一次", "steer"),
        ("先补一段说明", "followUp"),
    ]
    assert driver.steers == ["最后再总结一次"]
    assert driver.follow_ups == ["先补一段说明"]
    assert driver.queued_steering == ["最后再总结一次"]
    assert driver.queued_followup == ["先补一段说明"]


def test_removing_one_queued_message_keeps_the_rest_in_order(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    sid, session, driver = queue_two(service, drivers, tmp_path)
    first = queued_ids(service, sid)[0]
    detail = service.queue(sid, {"requestId": "q-1", "action": "remove", "id": first})
    assert [item["text"] for item in session.pending_view()] == ["最后再总结一次"]
    assert driver.follow_ups == ["最后再总结一次"]
    dropped = next(e for e in user_events(detail) if e["id"] == first)
    assert dropped["status"] == "cancelled"


def test_reordering_puts_the_queue_back_in_the_new_order(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    sid, session, driver = queue_two(service, drivers, tmp_path)
    second = queued_ids(service, sid)[1]
    service.queue(sid, {"requestId": "q-1", "action": "move", "id": second, "toIndex": 0})
    assert [item["text"] for item in session.pending_view()] == ["最后再总结一次", "先补一段说明"]
    assert driver.follow_ups == ["最后再总结一次", "先补一段说明"]


def test_moving_a_message_onto_itself_leaves_the_queue_alone(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    sid, session, driver = queue_two(service, drivers, tmp_path)
    before = session.pending_view()
    service.queue(sid, {"requestId": "q-1", "action": "move", "id": before[0]["id"], "toIndex": 0})
    assert session.pending_view() == before


def test_a_promoted_message_says_it_is_steering_now(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    sid, session, driver = queue_two(service, drivers, tmp_path)
    first = queued_ids(service, sid)[0]
    detail = service.queue(sid, {"requestId": "q-1", "action": "steer", "id": first})
    # The page labels a queued message by this, so it has to follow the lane.
    assert next(e for e in user_events(detail) if e["id"] == first)["mode"] == "steer"


def test_a_message_delivered_during_the_rewrite_is_not_sent_twice(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    sid, session, driver = queue_two(service, drivers, tmp_path)
    first, second = queued_ids(service, sid)
    # Pi took the first one while the user was still deciding: it is gone from
    # Pi's queue, so clear_queue never hands it back.
    driver.queued_followup.remove("先补一段说明")
    service.queue(sid, {"requestId": "q-1", "action": "steer", "id": second})
    assert "先补一段说明" not in driver.follow_ups
    assert [item["id"] for item in session.pending_view()] == [second]
    assert session.event_index[first]["status"] == "delivered"


def test_queue_refuses_a_message_that_is_no_longer_waiting(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    sid, session, driver = queue_two(service, drivers, tmp_path)
    first = queued_ids(service, sid)[0]
    deliver(service, session, "先补一段说明")
    with pytest.raises(WebError) as excinfo:
        service.queue(sid, {"requestId": "q-1", "action": "remove", "id": first})
    assert excinfo.value.code == "QUEUE_ITEM_GONE"


def test_queue_refuses_a_move_across_delivery_lanes(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    sid, session, driver = queue_two(service, drivers, tmp_path)
    first, second = queued_ids(service, sid)
    service.queue(sid, {"requestId": "q-1", "action": "steer", "id": second})
    with pytest.raises(WebError) as excinfo:
        # Index 0 is now the steering lane; a follow-up cannot be moved into it,
        # because Pi delivers every steer before any follow-up regardless.
        service.queue(sid, {"requestId": "q-2", "action": "move", "id": first, "toIndex": 0})
    assert excinfo.value.code == "INVALID_PARAMETER"


def test_queue_refuses_unknown_actions_and_dead_sessions(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    sid, session, driver = queue_two(service, drivers, tmp_path)
    first = queued_ids(service, sid)[0]
    with pytest.raises(WebError) as unknown:
        service.queue(sid, {"requestId": "q-1", "action": "shuffle", "id": first})
    assert unknown.value.code == "UNKNOWN_COMMAND"
    driver.close()
    with pytest.raises(WebError) as dead:
        service.queue(sid, {"requestId": "q-2", "action": "remove", "id": first})
    assert dead.value.code == "SESSION_NOT_ACTIVE"


def test_a_queue_rewrite_that_cannot_be_written_back_reports_the_loss(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    sid, session, driver = queue_two(service, drivers, tmp_path)
    first = queued_ids(service, sid)[0]
    driver.fail_next_follow_up = True
    with pytest.raises(WebError) as excinfo:
        service.queue(sid, {"requestId": "q-1", "action": "remove", "id": first})
    assert excinfo.value.code == "QUEUE_REWRITE_FAILED"
    # Nothing is left claiming to be waiting when it is not.
    assert session.pending_view() == []
    assert session.event_index[queued_ids_before(session, first)]["status"] == "failed"


def queued_ids_before(session, removed):
    return next(e["id"] for e in session.events
                if e["kind"] == "user" and e["id"] != removed and e.get("status") == "failed")


def test_a_delivered_steer_is_credited_to_the_answer_it_shapes(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    sid = detail["session"]["id"]
    session = service._get(sid)
    drivers[0].queued_followup.clear()
    service._apply_driver_event(session, {"id": "a-1", "kind": "assistant", "text": "写文档中"})
    service.send(sid, {"requestId": "q-1", "text": "改成看注册页", "mode": "steer"})
    steer_id = queued_ids(service, sid)[0]
    deliver(service, session, "改成看注册页")
    # The steer reaches the next request, so the answer already written is not
    # the one it changed.
    assert "steeredBy" not in session.event_index["a-1"]
    service._apply_driver_event(session, {"id": "a-2", "kind": "assistant", "text": "在看注册页"})
    assert session.event_index["a-2"]["steeredBy"] == [steer_id]
    # Credited once, not to every answer that follows.
    service._apply_driver_event(session, {"id": "a-3", "kind": "assistant", "text": "继续"})
    assert "steeredBy" not in session.event_index["a-3"]


def test_a_sent_message_records_how_it_was_delivered(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    sid = detail["session"]["id"]
    assert user_events(detail)[0]["mode"] == "direct"
    drivers[0].queued_followup.clear()
    queued = service.send(sid, {"requestId": "q-1", "text": "补一句"})
    assert user_events(queued)[-1]["mode"] == "followUp"
    steered = service.send(sid, {"requestId": "q-2", "text": "换个方向", "mode": "steer"})
    assert user_events(steered)[-1]["mode"] == "steer"
