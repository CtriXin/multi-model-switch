"""Pilot ``/btw`` backend contract tests: session-owned side questions.

Covers the API surface, the isolation invariants (no main transcript, queue,
model or effort mutation), idempotency, redaction, failure/cancel/timeout
semantics, restart persistence, fail-closed completion, and HTTP routing.
All drivers and sidecars are in-process fakes; no subprocess, no real config.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from mms_web.errors import WebError  # noqa: E402
from mms_web.sessions import SessionService  # noqa: E402

from test_mms_web_sessions_service import (  # noqa: E402
    FakeCatalog,
    FakeDriver,
    launch_ok,
    make_service,
)


def wait_btw(service: SessionService, session_id: str, btw_id: str, want: set[str], timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = service.get_side_question(session_id, btw_id)
        if row["status"] in want:
            return row
        time.sleep(0.02)
    raise AssertionError(f"btw {btw_id} stayed {row['status']}, wanted {want}")


def blocking_runner(release: threading.Event):
    def runner(context, *, cancel_event, timeout):
        while not cancel_event.is_set() and not release.is_set():
            time.sleep(0.01)
        return {"answer": "迟到的旁问回答。"}
    return runner


def test_capabilities_expose_btw_and_model_backed_answers(tmp_path, monkeypatch):
    """`sidecarCompletion` says the build can attempt a model answer.

    Whether one session actually can is a property of that session's route,
    not of the service, so it is reported on the question's own row instead.
    """
    service, _ = make_service(tmp_path, monkeypatch=monkeypatch)
    caps = service.capabilities()
    assert caps["sideQuestions"] is True
    assert caps["sidecarCompletion"] is True
    monkeypatch.setattr("mms_web.sessions._route_completion_build", lambda: False)
    service3, _ = make_service(tmp_path / "c", monkeypatch=monkeypatch)
    assert service3.capabilities()["sidecarCompletion"] is False
    service2, _ = make_service(tmp_path / "b", monkeypatch=monkeypatch,
                               sidecar_runner=blocking_runner(threading.Event()))
    assert service2.capabilities()["sidecarCompletion"] is True


def test_state_question_completes_without_touching_main(tmp_path, monkeypatch):
    service, drivers = make_service(tmp_path, monkeypatch=monkeypatch)
    detail = launch_ok(service, prompt="帮我修复这个 bug")
    session_id = detail["session"]["id"]
    events_before = [dict(e) for e in detail["events"]]
    sequence_before = service._get(session_id).last_sequence

    row = service.ask_side_question(session_id, {"question": "现在进行到哪一步了？"})

    assert row["status"] == "completed"
    assert row["owner"] == "sidecar"
    assert row["source"] == "state"
    assert row["mainSessionId"] == session_id
    assert "当前状态" in row["answer"]
    assert row["contextRevision"] == f"r-{sequence_before}"
    # Main transcript, sequence, queue and driver are untouched.
    after = service.get_session(session_id)
    assert [e["id"] for e in after["events"]] == [e["id"] for e in events_before]
    assert service._get(session_id).last_sequence == sequence_before
    assert drivers[0].prompts == ["帮我修复这个 bug"]
    assert row["btwId"] not in {e["id"] for e in after["events"]}
    assert [r["btwId"] for r in after["sideQuestions"]] == [row["btwId"]]


def test_btw_does_not_enter_pending_queue(tmp_path, monkeypatch):
    service, drivers = make_service(tmp_path, monkeypatch=monkeypatch)
    detail = launch_ok(service, prompt="第一轮")
    session_id = detail["session"]["id"]
    # Session is still "running": a second send lands in the follow-up queue.
    service.send(session_id, {"requestId": "req-2", "text": "补充一点"})
    session = service._get(session_id)
    queued_before = dict(session.pending_prompts)
    queue_meta_before = list(session.meta.get("queue") or [])

    service.ask_side_question(session_id, {"question": "队列里有几条？"})

    assert dict(session.pending_prompts) == queued_before
    assert list(session.meta.get("queue") or []) == queue_meta_before
    assert drivers[0].prompts == ["第一轮", "补充一点"]  # btw never reached the driver


def test_multiple_btw_keep_independent_ids_and_order(tmp_path, monkeypatch):
    service, _ = make_service(tmp_path, monkeypatch=monkeypatch)
    session_id = launch_ok(service)["session"]["id"]
    first = service.ask_side_question(session_id, {"question": "状态如何？"})
    second = service.ask_side_question(session_id, {"question": "刚才在做什么？"})
    assert first["btwId"] != second["btwId"]
    rows = service.list_side_questions(session_id)
    assert [r["btwId"] for r in rows] == [first["btwId"], second["btwId"]]
    assert rows[0]["question"] != rows[1]["question"]


def test_idempotency_key_replays_original_row(tmp_path, monkeypatch):
    service, _ = make_service(tmp_path, monkeypatch=monkeypatch)
    session_id = launch_ok(service)["session"]["id"]
    payload = {"question": "进度如何？", "idempotencyKey": "btw-req-1"}
    first = service.ask_side_question(session_id, payload)
    replay = service.ask_side_question(session_id, dict(payload))
    assert replay["btwId"] == first["btwId"]
    assert len(service.list_side_questions(session_id)) == 1
    # The key never leaves the service.
    assert "idempotencyKey" not in replay


def test_approval_wait_observable_but_not_bypassable(tmp_path, monkeypatch):
    service, drivers = make_service(tmp_path, monkeypatch=monkeypatch)
    session_id = launch_ok(service)["session"]["id"]
    session = service._get(session_id)
    drivers[0].emit_approval(service, session, approval_id="ap-1", method="confirm")
    assert service.get_session(session_id)["session"]["state"] == "waiting"

    row = service.ask_side_question(session_id, {"question": "当前是不是在等我审批？"})

    assert row["status"] == "completed"
    assert "审批" in row["answer"]
    assert "ap-1" in session.approvals  # still pending
    assert drivers[0].ui_responses == []  # btw never answered the approval


def test_completion_without_runner_fails_closed(tmp_path, monkeypatch):
    service, drivers = make_service(tmp_path, monkeypatch=monkeypatch)
    session_id = launch_ok(service)["session"]["id"]
    row = service.ask_side_question(
        session_id, {"question": "帮我分析这个设计是否合理", "sourceHint": "completion"})
    assert row["status"] == "failed"
    assert "只读旁问模型" in row["error"]
    assert row["answer"] is None
    assert service.get_session(session_id)["session"]["state"] == "running"
    assert drivers[0].prompts == ["hi"]


def test_completion_runner_answers_without_driver(tmp_path, monkeypatch):
    seen = {}

    def runner(context, *, cancel_event, timeout):
        seen.update(context)
        return {"answer": "只读回答：主任务在跑测试。", "usage": {"inputTokens": 12}}

    service, drivers = make_service(tmp_path, monkeypatch=monkeypatch, sidecar_runner=runner)
    session_id = launch_ok(service)["session"]["id"]
    row = service.ask_side_question(session_id, {"question": "分析一下目前的进展"})
    assert row["source"] == "completion"
    final = wait_btw(service, session_id, row["btwId"], {"completed"})
    assert final["answer"] == "只读回答：主任务在跑测试。"
    assert final["usage"] == {"inputTokens": 12}
    # The sidecar saw only the budgeted context snapshot, never the driver.
    assert seen["kind"] == "mms-web-btw-context/v1"
    assert seen["state"] == "running"
    assert drivers[0].prompts == ["hi"]
    assert service._get(session_id).last_sequence == 2  # notice + user only


def test_completion_cancel_discards_late_answer(tmp_path, monkeypatch):
    release = threading.Event()
    service, _ = make_service(tmp_path, monkeypatch=monkeypatch,
                              sidecar_runner=blocking_runner(release))
    session_id = launch_ok(service)["session"]["id"]
    row = service.ask_side_question(session_id, {"question": "分析一下", "sourceHint": "completion"})
    assert row["status"] == "running"
    cancelled = service.cancel_side_question(session_id, row["btwId"])
    assert cancelled["status"] == "cancelled"
    release.set()  # the sidecar returns after cancellation
    time.sleep(0.2)
    assert service.get_side_question(session_id, row["btwId"])["status"] == "cancelled"
    assert service.get_side_question(session_id, row["btwId"])["answer"] is None
    # Cancelling an already-settled row is an idempotent no-op.
    assert service.cancel_side_question(session_id, row["btwId"])["status"] == "cancelled"


def test_completion_timeout_marks_failed_and_main_continues(tmp_path, monkeypatch):
    def slow_runner(context, *, cancel_event, timeout):
        cancel_event.wait(30)  # released by the watchdog's cancel signal
        return {"answer": "太迟了"}

    service, _ = make_service(tmp_path, monkeypatch=monkeypatch,
                              sidecar_runner=slow_runner, btw_timeout=0.2)
    session_id = launch_ok(service)["session"]["id"]
    row = service.ask_side_question(session_id, {"question": "分析一下", "sourceHint": "completion"})
    final = wait_btw(service, session_id, row["btwId"], {"failed"})
    assert "超时" in final["error"]
    assert service.get_session(session_id)["session"]["state"] == "running"


def test_completion_exception_is_visible_and_redacted(tmp_path, monkeypatch):
    def broken(context, *, cancel_event, timeout):
        raise RuntimeError("sk-testsecret123 exploded")

    service, _ = make_service(tmp_path, monkeypatch=monkeypatch, sidecar_runner=broken)
    session_id = launch_ok(service)["session"]["id"]
    service._get(session_id).secrets.append("sk-testsecret123")
    row = service.ask_side_question(session_id, {"question": "分析一下", "sourceHint": "completion"})
    final = wait_btw(service, session_id, row["btwId"], {"failed"})
    assert final["error"]
    assert "sk-testsecret123" not in json.dumps(final, ensure_ascii=False)


def test_secrets_masked_in_question_answer_and_summary(tmp_path, monkeypatch):
    def echo_runner(context, *, cancel_event, timeout):
        return {"answer": f"回答 {context['question']}，泄露 sk-testsecret123"}

    service, _ = make_service(tmp_path, monkeypatch=monkeypatch, sidecar_runner=echo_runner)
    session_id = launch_ok(service)["session"]["id"]
    service._get(session_id).secrets.append("sk-testsecret123")
    row = service.ask_side_question(
        session_id, {"question": "sk-testsecret123 是什么", "sourceHint": "completion"})
    final = wait_btw(service, session_id, row["btwId"], {"completed"})
    payload = json.dumps(final, ensure_ascii=False)
    assert "sk-testsecret123" not in payload
    assert "[已隐藏密钥]" in payload
    assert final["redactionSummary"]["secretsMasked"] >= 2


def test_main_stop_does_not_cancel_running_btw(tmp_path, monkeypatch):
    gate = threading.Event()

    def runner(context, *, cancel_event, timeout):
        gate.wait(5)
        return {"answer": "主任务停了，旁问照样答完。"}

    service, drivers = make_service(tmp_path, monkeypatch=monkeypatch, sidecar_runner=runner)
    session_id = launch_ok(service)["session"]["id"]
    row = service.ask_side_question(session_id, {"question": "分析一下", "sourceHint": "completion"})
    service.stop(session_id, {"requestId": "req-stop"})
    assert drivers[0].aborts == 1
    gate.set()
    final = wait_btw(service, session_id, row["btwId"], {"completed"})
    assert final["answer"] == "主任务停了，旁问照样答完。"


def test_restart_preserves_finished_and_cancels_in_flight(tmp_path, monkeypatch):
    release = threading.Event()
    service, _ = make_service(tmp_path, monkeypatch=monkeypatch,
                              sidecar_runner=blocking_runner(release), btw_timeout=60)
    session_id = launch_ok(service)["session"]["id"]
    done = service.ask_side_question(session_id, {"question": "状态如何？"})
    pending = service.ask_side_question(session_id, {"question": "分析一下", "sourceHint": "completion"})
    assert pending["status"] == "running"

    # A second service over the same state dir is a restart: the worker thread
    # is gone, so the in-flight row is cancelled, never faked as done.
    reloaded, _ = make_service(tmp_path, monkeypatch=monkeypatch, sidecar_runner=blocking_runner(threading.Event()))
    rows = {r["btwId"]: r for r in reloaded.list_side_questions(session_id)}
    assert rows[done["btwId"]]["status"] == "completed"
    assert rows[done["btwId"]]["answer"] == done["answer"]
    assert rows[pending["btwId"]]["status"] == "cancelled"
    assert "重启" in rows[pending["btwId"]]["error"]

    release.set()
    service.close()
    reloaded.close()


def test_close_marks_in_flight_uncertain(tmp_path, monkeypatch):
    release = threading.Event()
    service, _ = make_service(tmp_path, monkeypatch=monkeypatch,
                              sidecar_runner=blocking_runner(release), btw_timeout=60)
    session_id = launch_ok(service)["session"]["id"]
    row = service.ask_side_question(session_id, {"question": "分析一下", "sourceHint": "completion"})
    service.close()
    final = service.get_side_question(session_id, row["btwId"])
    assert final["status"] == "uncertain"
    assert final["answer"] is None
    release.set()


def test_fork_carries_only_settled_btw(tmp_path, monkeypatch):
    service, _ = make_service(tmp_path, monkeypatch=monkeypatch)
    session_id = launch_ok(service)["session"]["id"]
    session = service._get(session_id)
    root = tmp_path / "state" / "runtimes" / "rt-1"
    root.mkdir(parents=True)
    (root / "resume.json").write_text(json.dumps(
        {"modelInfo": {"model": "fake-sonnet"}, "runtime": {"id": "prov-1"}, "cwd": "/tmp/fake-ws"}))
    (root / "conversation.jsonl").write_text("")
    session.meta["runtimeRoot"] = str(root)
    service._apply_proto_state(session, "idle")
    settled = service.ask_side_question(session_id, {"question": "状态如何？"})

    branch = service.fork(session_id, {"requestId": "req-fork"})

    branch_id = branch["session"]["id"]
    assert [r["btwId"] for r in branch["sideQuestions"]] == [settled["btwId"]]
    assert branch["sideQuestions"][0]["mainSessionId"] == session_id  # history, unrewritten
    assert service.list_side_questions(session_id)[0]["status"] == "completed"


def test_validation_fail_closed(tmp_path, monkeypatch):
    service, _ = make_service(tmp_path, monkeypatch=monkeypatch)
    session_id = launch_ok(service)["session"]["id"]
    for payload, code in [
        ({}, "INVALID_REQUEST"),
        ({"question": "   "}, "INVALID_REQUEST"),
        ({"question": "状态？", "sourceHint": "magic"}, "INVALID_PARAMETER"),
        ({"question": "状态？", "idempotencyKey": "bad key!"}, "INVALID_REQUEST"),
    ]:
        with pytest.raises(WebError) as err:
            service.ask_side_question(session_id, payload)
        assert err.value.code == code
        assert err.value.status == 400
    assert service.list_side_questions(session_id) == []  # nothing half-recorded
    with pytest.raises(WebError) as err:
        service.ask_side_question("s-missing", {"question": "状态？"})
    assert err.value.code == "SESSION_NOT_FOUND"
    with pytest.raises(WebError) as err:
        service.get_side_question(session_id, "btw-missing")
    assert err.value.code == "BTW_NOT_FOUND"
    with pytest.raises(WebError) as err:
        service.cancel_side_question(session_id, "btw-missing")
    assert err.value.code == "BTW_NOT_FOUND"


def test_http_routing_for_side_questions(tmp_path, monkeypatch):
    """The WebApplication route shape, without a real session service."""
    from mms_web.server import WebApplication

    calls = []

    class StubSessions:
        def list_side_questions(self, session_id):
            calls.append(("list", session_id))
            return []
        def get_side_question(self, session_id, btw_id):
            calls.append(("get", session_id, btw_id))
            return {"btwId": btw_id, "status": "completed"}
        def ask_side_question(self, session_id, payload):
            calls.append(("ask", session_id, payload.get("question")))
            return {"btwId": "btw-1", "status": "accepted"}
        def cancel_side_question(self, session_id, btw_id):
            calls.append(("cancel", session_id, btw_id))
            return {"btwId": btw_id, "status": "cancelled"}
        def close(self):
            pass

    class StubCatalog:
        pass

    def adapter(module, name, **kwargs):
        if module == "mms_web.catalog":
            return StubCatalog()
        return StubSessions()

    monkeypatch.setattr("mms_web.server._adapter", adapter)
    app = WebApplication(state_root=tmp_path / "state")
    try:
        assert app.get(["sessions", "s-1", "side-questions"]) == {"sideQuestions": []}
        assert app.get(["sessions", "s-1", "side-questions", "btw-9"])["btwId"] == "btw-9"
        assert app.post(["sessions", "s-1", "side-questions"], {"question": "状态？"})["status"] == "accepted"
        assert app.post(["sessions", "s-1", "side-questions", "btw-9", "cancel"], {})["status"] == "cancelled"
        assert calls == [
            ("list", "s-1"), ("get", "s-1", "btw-9"), ("ask", "s-1", "状态？"), ("cancel", "s-1", "btw-9"),
        ]
        with pytest.raises(WebError):
            app.get(["sessions", "s-1", "side-questions", "btw-9", "extra"])
    finally:
        app.close()
