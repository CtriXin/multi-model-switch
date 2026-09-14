"""Native ``/btw`` extension contract tests: BTW_EVENT mapping (T2a).

Covers the host side of the §4.3 data contract before the real extension
exists: the RPC driver parses ``BTW_EVENT:`` notifies (well-formed, malformed
JSON, non-object payload), ``SessionService`` maps the event stream onto
side-question rows (accepted/running/delta/completed/failed/cancelled),
duplicate, late and out-of-order events never reopen or rewind a row, unknown
ids stay inert unless ``accepted`` creates the row, secrets are masked in
every written field, and the main transcript / queue / driver stay untouched
throughout. All drivers are in-process fakes; no subprocess, no real config.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mms_web.sessions import SessionService  # noqa: E402

from test_mms_web_sessions_service import (  # noqa: E402
    FakeDriver,
    launch_ok,
    make_service,
)
from test_mms_web_sessions_pi_driver import make_driver  # noqa: E402  (pytest resolves imported fixtures)

from test_mms_web_btw_backend import wait_btw  # noqa: E402


NATIVE_COMMANDS = [{"name": "btw"}, {"name": "btw:cancel"}]
UPSTREAM_ONLY_COMMANDS = [{"name": "btw"}]  # upstream pi-btw: no headless, no btw:cancel


def btw_event(event: str, btw_id: str = "btw-abc123def456", **fields) -> dict:
    payload = {"v": 1, "event": event, "id": btw_id}
    payload.update(fields)
    return payload


def native_lifecycle(driver: FakeDriver, btw_id: str = "btw-abc123def456", question: str = "这个函数是干什么的？") -> str:
    """accepted -> running -> delta -> delta -> completed, as the extension sends it."""
    driver.emit_side_question_event(btw_event("accepted", btw_id, question=question, at="2026-09-14T10:00:00Z"))
    driver.emit_side_question_event(btw_event("running", btw_id, at="2026-09-14T10:00:01Z"))
    driver.emit_side_question_event(btw_event("delta", btw_id, text="这个函数负责", at="2026-09-14T10:00:02Z"))
    driver.emit_side_question_event(btw_event("delta", btw_id, text="解析配置文件。", at="2026-09-14T10:00:02Z"))
    answer = "这个函数负责解析配置文件。"
    driver.emit_side_question_event(btw_event(
        "completed", btw_id, text=answer, at="2026-09-14T10:00:03Z",
        usage={"input": 120, "output": 8, "cacheRead": 100, "cacheWrite": 0, "cost": None},
        context={"mode": "branch", "entries": 42, "chars": 9000, "truncated": False, "leafId": "e-42"},
    ))
    return answer


def test_native_lifecycle_maps_onto_one_row(tmp_path, monkeypatch):
    service, drivers = make_service(tmp_path, monkeypatch=monkeypatch)
    session_id = launch_ok(service)["session"]["id"]

    answer = native_lifecycle(drivers[0])

    rows = service.list_side_questions(session_id)
    assert [r["btwId"] for r in rows] == ["btw-abc123def456"]
    row = rows[0]
    assert row["status"] == "completed"
    assert row["runner"] == "pi-extension"
    assert row["question"] == "这个函数是干什么的？"
    assert row["answer"] == answer
    assert row["source"] == "completion"
    assert row["usage"] == {"input": 120, "output": 8, "cacheRead": 100, "cacheWrite": 0, "cost": None}
    assert row["contextScope"] == {"mode": "branch", "entries": 42, "chars": 9000, "truncated": False, "leafId": "e-42"}
    assert row["createdAt"] == "2026-09-14T10:00:00Z"
    assert row["completedAt"] == "2026-09-14T10:00:03Z"
    assert row["error"] is None


def test_host_rows_carry_host_runner(tmp_path, monkeypatch):
    service, _ = make_service(tmp_path, monkeypatch=monkeypatch)
    session_id = launch_ok(service)["session"]["id"]

    row = service.ask_side_question(session_id, {"question": "现在进行到哪一步了？"})

    assert row["runner"] == "host"
    assert row["status"] == "completed"
    assert row["source"] == "state"


def test_delta_accumulates_when_completed_has_no_text(tmp_path, monkeypatch):
    service, drivers = make_service(tmp_path, monkeypatch=monkeypatch)
    session_id = launch_ok(service)["session"]["id"]
    driver = drivers[0]

    driver.emit_side_question_event(btw_event("accepted", "btw-delta1", question="q"))
    driver.emit_side_question_event(btw_event("running", "btw-delta1"))
    driver.emit_side_question_event(btw_event("delta", "btw-delta1", text="第一段 "))
    driver.emit_side_question_event(btw_event("delta", "btw-delta1", text="第二段"))
    # A completed without text keeps the accumulated deltas.
    driver.emit_side_question_event(btw_event("completed", "btw-delta1"))

    row = service.get_side_question(session_id, "btw-delta1")
    assert row["status"] == "completed"
    assert row["answer"] == "第一段 第二段"


def test_duplicate_and_late_events_never_rewind(tmp_path, monkeypatch):
    service, drivers = make_service(tmp_path, monkeypatch=monkeypatch)
    session_id = launch_ok(service)["session"]["id"]
    driver = drivers[0]

    native_lifecycle(driver)
    # Everything after the terminal state is dropped, in any order.
    driver.emit_side_question_event(btw_event("delta", text="迟到的增量"))
    driver.emit_side_question_event(btw_event("running"))
    driver.emit_side_question_event(btw_event("accepted", question="改口的问题"))
    driver.emit_side_question_event(btw_event("failed", error="迟到的失败"))
    row = service.get_side_question(session_id, "btw-abc123def456")
    assert row["status"] == "completed"
    assert row["answer"] == "这个函数负责解析配置文件。"
    assert row["question"] == "这个函数是干什么的？"
    assert row["error"] is None

    # Duplicate accepted on a running row is an idempotent no-op.
    driver.emit_side_question_event(btw_event("accepted", "btw-dup1", question="重复确认"))
    driver.emit_side_question_event(btw_event("running", "btw-dup1"))
    driver.emit_side_question_event(btw_event("accepted", "btw-dup1", question="重复确认"))
    row = service.get_side_question(session_id, "btw-dup1")
    assert row["status"] == "running"
    assert row["question"] == "重复确认"


def test_unknown_id_events_are_inert_except_accepted(tmp_path, monkeypatch):
    service, drivers = make_service(tmp_path, monkeypatch=monkeypatch)
    session_id = launch_ok(service)["session"]["id"]
    driver = drivers[0]

    for event in ("running", "delta", "completed", "failed", "cancelled"):
        driver.emit_side_question_event(btw_event(event, "btw-ghost", text="x", error="y"))
    assert service.list_side_questions(session_id) == []

    # Bad ids (empty, or failing the idempotency-key charset) are dropped too.
    driver.emit_side_question_event(btw_event("accepted", "", question="q"))
    driver.emit_side_question_event(btw_event("accepted", "bad id!", question="q"))
    assert service.list_side_questions(session_id) == []


def test_failed_and_cancelled_events_map_to_visible_errors(tmp_path, monkeypatch):
    service, drivers = make_service(tmp_path, monkeypatch=monkeypatch)
    session_id = launch_ok(service)["session"]["id"]
    driver = drivers[0]

    driver.emit_side_question_event(btw_event("accepted", "btw-f1", question="q1"))
    driver.emit_side_question_event(btw_event("failed", "btw-f1", error="模型路由不可用", at="2026-09-14T10:00:05Z"))
    driver.emit_side_question_event(btw_event("accepted", "btw-c1", question="q2"))
    driver.emit_side_question_event(btw_event("cancelled", "btw-c1", at="2026-09-14T10:00:06Z"))

    failed = service.get_side_question(session_id, "btw-f1")
    assert failed["status"] == "failed"
    assert failed["error"] == "模型路由不可用"
    assert failed["runner"] == "pi-extension"
    cancelled = service.get_side_question(session_id, "btw-c1")
    assert cancelled["status"] == "cancelled"
    assert "取消" in cancelled["error"]


def test_history_events_carry_no_row_semantics(tmp_path, monkeypatch):
    service, drivers = make_service(tmp_path, monkeypatch=monkeypatch)
    session_id = launch_ok(service)["session"]["id"]

    drivers[0].emit_side_question_event(btw_event(
        "history", items=[{"id": "btw-old", "question": "旧问题", "status": "completed"}]
    ))
    assert service.list_side_questions(session_id) == []


def test_context_and_usage_whitelisted_not_trusted(tmp_path, monkeypatch):
    service, drivers = make_service(tmp_path, monkeypatch=monkeypatch)
    session_id = launch_ok(service)["session"]["id"]
    driver = drivers[0]

    driver.emit_side_question_event(btw_event("accepted", "btw-w1", question="q"))
    driver.emit_side_question_event(btw_event("completed", "btw-w1", text="a", at="2026-09-14T10:00:09Z",
        context={"mode": "branch", "entries": "many", "chars": -3, "truncated": "yes", "leafId": None, "evil": {"x": 1}},
        usage={"input": 5, "output": 1, "cacheRead": "lots", "cost": "free"}))

    row = service.get_side_question(session_id, "btw-w1")
    assert row["contextScope"] == {"mode": "branch"}
    assert row["usage"] == {"input": 5, "output": 1}  # invalid fields dropped


def test_secrets_masked_in_question_answer_and_error(tmp_path, monkeypatch):
    service, drivers = make_service(tmp_path, monkeypatch=monkeypatch)
    session_id = launch_ok(service)["session"]["id"]
    secret = "sk-secret-token-abcdef"
    session = service._get(session_id)
    session.secrets = [secret]

    drivers[0].emit_side_question_event(btw_event("accepted", "btw-s1", question=f"key 是 {secret} 吗"))
    drivers[0].emit_side_question_event(btw_event("delta", "btw-s1", text=f"是的，key 为 {secret[:4]}"))
    drivers[0].emit_side_question_event(btw_event("delta", "btw-s1", text=secret[4:]))
    drivers[0].emit_side_question_event(btw_event("failed", "btw-s1", error=f"路由失败 {secret}"))

    row = service.get_side_question(session_id, "btw-s1")
    assert secret not in json.dumps(row)
    assert "[已隐藏密钥]" in row["question"]
    assert "[已隐藏密钥]" in row["error"]
    assert row["redactionSummary"]["secretsMasked"] >= 3
    # The split secret never leaked through the accumulated answer either.
    assert row["answer"] is None or secret not in row["answer"]


def test_native_events_never_touch_main_transcript_or_driver(tmp_path, monkeypatch):
    service, drivers = make_service(tmp_path, monkeypatch=monkeypatch)
    detail = launch_ok(service, prompt="主任务")
    session_id = detail["session"]["id"]
    events_before = [dict(e) for e in detail["events"]]
    sequence_before = service._get(session_id).last_sequence
    session = service._get(session_id)
    queue_before = list(session.meta.get("queue") or [])
    pending_before = dict(session.pending_prompts)

    native_lifecycle(drivers[0])

    after = service.get_session(session_id)
    assert [e["id"] for e in after["events"]] == [e["id"] for e in events_before]
    assert service._get(session_id).last_sequence == sequence_before
    assert list(session.meta.get("queue") or []) == queue_before
    assert dict(session.pending_prompts) == pending_before
    # No /btw prompt was sent to the driver by the event path itself.
    assert drivers[0].prompts == ["主任务"]
    assert [r["btwId"] for r in after["sideQuestions"]] == ["btw-abc123def456"]


def test_native_rows_survive_service_restart(tmp_path, monkeypatch):
    service, drivers = make_service(tmp_path, monkeypatch=monkeypatch)
    session_id = launch_ok(service)["session"]["id"]
    native_lifecycle(drivers[0])

    detail = service.stop(session_id, {"requestId": "req-stop"})
    service.close()

    service2, _ = make_service(tmp_path, monkeypatch=monkeypatch)
    rows = service2.list_side_questions(session_id)
    assert [r["btwId"] for r in rows] == ["btw-abc123def456"]
    assert rows[0]["status"] == "completed"
    assert rows[0]["runner"] == "pi-extension"


def test_service_isolation_of_sink_events(tmp_path, monkeypatch):
    """A side-question event for a finalized session is dropped silently."""
    service, drivers = make_service(tmp_path, monkeypatch=monkeypatch)
    session_id = launch_ok(service)["session"]["id"]
    drivers[0].kill()
    service._apply_process_exited(service._get(session_id), 0, "")

    drivers[0].emit_side_question_event(btw_event("accepted", "btw-dead", question="q"))
    assert service.list_side_questions(session_id) == []


# -- RPC driver BTW_EVENT: parsing -------------------------------------


def test_driver_parses_btw_event_notify(make_driver):
    driver, sink = make_driver()
    payload = {"v": 1, "event": "accepted", "id": "btw-123", "question": "q"}
    driver._handle_ui_request({
        "type": "extension_ui_request", "id": "ui-1", "method": "notify",
        "message": "BTW_EVENT:" + json.dumps(payload, ensure_ascii=False),
    })
    assert sink.side_question_events == [payload]


def test_driver_reports_malformed_btw_event_json(make_driver):
    driver, sink = make_driver()
    driver._handle_ui_request({
        "type": "extension_ui_request", "id": "ui-2", "method": "notify",
        "message": "BTW_EVENT:{not json",
    })
    notices = [e for e in sink.events.values() if e.get("kind") == "notice"]
    assert notices and "BTW" in notices[-1]["text"]
    assert sink.side_question_events == []
    assert sink.proto_states == []  # no protocol side effects


def test_driver_rejects_non_object_btw_event_payload(make_driver):
    driver, sink = make_driver()
    driver._handle_ui_request({
        "type": "extension_ui_request", "id": "ui-3", "method": "notify",
        "message": "BTW_EVENT:[1,2,3]",
    })
    notices = [e for e in sink.events.values() if e.get("kind") == "notice"]
    assert notices and "BTW" in notices[-1]["text"]
    assert sink.side_question_events == []


def test_service_maps_payload_from_driver_sink(tmp_path, monkeypatch):
    """Full path: sink.side_question_event -> SessionService row (T2a seam)."""
    service, drivers = make_service(tmp_path, monkeypatch=monkeypatch)
    session_id = launch_ok(service)["session"]["id"]
    assert isinstance(service, SessionService)
    native_lifecycle(drivers[0])
    row = service.get_side_question(session_id, "btw-abc123def456")
    assert row["runner"] == "pi-extension"


# -- T2b: btwNative detection -----------------------------------------


def wait_probe(service: SessionService, session_id: str, timeout: float = 5.0) -> None:
    """The launch-path probe runs off the critical path; wait for its write."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        meta = service._get(session_id).meta
        if "btwNative" in meta:
            return
        time.sleep(0.02)
    raise AssertionError(f"btwNative never probed for {session_id}")


def test_probe_sets_btw_native_only_for_the_fork(tmp_path, monkeypatch):
    service, _ = make_service(tmp_path, monkeypatch=monkeypatch, driver_commands=NATIVE_COMMANDS)
    session_id = launch_ok(service)["session"]["id"]
    wait_probe(service, session_id)
    assert service._get(session_id).meta["btwNative"] is True
    assert service.get_session(session_id)["session"]["btwNative"] is True

    service2, _ = make_service(tmp_path / "b", monkeypatch=monkeypatch, driver_commands=UPSTREAM_ONLY_COMMANDS)
    session_id2 = launch_ok(service2)["session"]["id"]
    wait_probe(service2, session_id2)
    assert service2._get(session_id2).meta["btwNative"] is False

    service3, _ = make_service(tmp_path / "c", monkeypatch=monkeypatch)
    session_id3 = launch_ok(service3)["session"]["id"]
    wait_probe(service3, session_id3)
    assert service3._get(session_id3).meta["btwNative"] is False


def test_probe_failure_never_blocks_launch(tmp_path, monkeypatch):
    service, _ = make_service(tmp_path, monkeypatch=monkeypatch)

    def explode(self, *, timeout=None):
        raise RuntimeError("get_commands exploded")

    monkeypatch.setattr(FakeDriver, "get_commands", explode)
    session_id = launch_ok(service)["session"]["id"]
    wait_probe(service, session_id)
    assert service._get(session_id).meta.get("btwNative") is False


# -- T2b: native-first answering ---------------------------------------


def emit_answer(driver: FakeDriver, btw_id: str, question: str, answer: str = "扩展的回答。") -> None:
    """The event stream the real extension sends for one answered question."""
    driver.emit_side_question_event(btw_event("accepted", btw_id, question=question))
    driver.emit_side_question_event(btw_event("running", btw_id))
    driver.emit_side_question_event(btw_event("delta", btw_id, text=answer[:4]))
    driver.emit_side_question_event(btw_event("delta", btw_id, text=answer[4:]))
    driver.emit_side_question_event(btw_event("completed", btw_id, text=answer,
        context={"mode": "branch", "entries": 7, "chars": 1234, "truncated": True}))


def test_native_answers_via_events_and_only_sends_the_btw_prompt(tmp_path, monkeypatch):
    """A6 core: runner=pi-extension, branch scope, one /btw prompt, no user event."""
    service, drivers = make_service(tmp_path, monkeypatch=monkeypatch, driver_commands=NATIVE_COMMANDS,
                                    sidecar_runner=lambda *a, **k: {"answer": "host"})
    session_id = launch_ok(service, prompt="主任务")["session"]["id"]
    wait_probe(service, session_id)
    session = service._get(session_id)
    events_before = [dict(e) for e in session.events]
    sequence_before = session.last_sequence

    row = service.ask_side_question(session_id, {"question": "现在的分支策略是什么？"})

    # The prompt carried the question to the extension, one command, nothing else.
    assert drivers[0].prompts == ["主任务", "/btw 现在的分支策略是什么？"]
    emit_answer(drivers[0], "btw-native11", "现在的分支策略是什么？", "扩展的回答。")
    final = wait_btw(service, session_id, row["btwId"], {"completed"})
    assert final["runner"] == "pi-extension"
    assert final["answer"] == "扩展的回答。"
    assert final["contextScope"] == {"mode": "branch", "entries": 7, "chars": 1234, "truncated": True}
    assert final["fallbackReason"] is None
    # Invariants: no new user event, no sequence move, no second prompt.
    assert [e["id"] for e in session.events] == [e["id"] for e in events_before]
    assert session.last_sequence == sequence_before
    assert [p for p in drivers[0].prompts if not p.startswith("/btw")] == ["主任务"]
    assert not any(e.get("kind") == "user" for e in session.events[len(events_before):])


def test_native_row_survives_restart_and_keeps_runner(tmp_path, monkeypatch):
    service, drivers = make_service(tmp_path, monkeypatch=monkeypatch, driver_commands=NATIVE_COMMANDS)
    session_id = launch_ok(service)["session"]["id"]
    row = service.ask_side_question(session_id, {"question": "重启后还在吗"})
    emit_answer(drivers[0], "btw-restart1", "重启后还在吗")
    wait_btw(service, session_id, row["btwId"], {"completed"})
    service.stop(session_id, {"requestId": "req-stop"})
    service.close()

    service2, _ = make_service(tmp_path, monkeypatch=monkeypatch)
    rows = service2.list_side_questions(session_id)
    assert [r["btwId"] for r in rows] == [row["btwId"]]
    assert rows[0]["runner"] == "pi-extension"


def test_native_prompt_rejected_falls_back_to_host_once(tmp_path, monkeypatch):
    calls = []

    def runner(context, *, cancel_event, timeout):
        calls.append(context["question"])
        return {"answer": "host 兜底回答。"}

    service, drivers = make_service(tmp_path, monkeypatch=monkeypatch, driver_commands=NATIVE_COMMANDS,
                                    sidecar_runner=runner)
    session_id = launch_ok(service)["session"]["id"]
    drivers[0].fail_next_prompt = {"type": "response", "command": "prompt", "success": False, "error": "no active model"}

    row = service.ask_side_question(session_id, {"question": "被拒的问题"})

    final = wait_btw(service, session_id, row["btwId"], {"completed"})
    assert "extension rejected" in final["fallbackReason"]
    assert final["runner"] == "host"
    assert final["answer"] == "host 兜底回答。"
    assert len(calls) == 1  # exactly one host retry, never a loop
    # The rejection was recorded before the host retry answered.
    assert final["fallbackReason"] == service.get_side_question(session_id, row["btwId"])["fallbackReason"]


def test_native_timeout_falls_back_to_host_once(tmp_path, monkeypatch):
    calls = []

    def runner(context, *, cancel_event, timeout):
        calls.append(1)
        return {"answer": "迟到的 host 回答。"}

    service, drivers = make_service(tmp_path, monkeypatch=monkeypatch, driver_commands=NATIVE_COMMANDS,
                                    sidecar_runner=runner, btw_timeout=0.4)
    session_id = launch_ok(service)["session"]["id"]

    row = service.ask_side_question(session_id, {"question": "慢扩展"})
    # The extension accepted (map established) but never sends a terminal event.
    drivers[0].emit_side_question_event(btw_event("accepted", "btw-slow1", question="慢扩展"))
    drivers[0].emit_side_question_event(btw_event("running", "btw-slow1"))

    final = wait_btw(service, session_id, row["btwId"], {"completed"}, timeout=5.0)
    assert final["runner"] == "host"
    assert final["answer"] == "迟到的 host 回答。"
    assert "超时" in final["fallbackReason"]
    assert len(calls) == 1
    # A late native terminal event after the host retry cannot reopen the row.
    drivers[0].emit_side_question_event(btw_event("completed", "btw-slow1", text="迟到的事件"))
    assert service.get_side_question(session_id, row["btwId"])["answer"] == "迟到的 host 回答。"


def test_native_prompt_timeout_is_treated_as_accepted_then_backed_by_clock(tmp_path, monkeypatch):
    """A slow handler must not block the ask; the fallback clock still fires."""
    calls = []

    def runner(context, *, cancel_event, timeout):
        calls.append(1)
        return {"answer": "慢受理后的 host 回答。"}

    service, drivers = make_service(tmp_path, monkeypatch=monkeypatch, driver_commands=NATIVE_COMMANDS,
                                    sidecar_runner=runner, btw_timeout=0.4)
    session_id = launch_ok(service)["session"]["id"]
    wait_probe(service, session_id)
    drivers[0].timeout_next_prompt = True  # the /btw handler outlives the wait
    import time as _time
    started = _time.monotonic()

    row = service.ask_side_question(session_id, {"question": "慢受理"})

    assert _time.monotonic() - started < 2.0  # the ask returned without the answer
    final = wait_btw(service, session_id, row["btwId"], {"completed"}, timeout=5.0)
    assert final["runner"] == "host"
    assert final["answer"] == "慢受理后的 host 回答。"
    assert len(calls) == 1


def test_cancel_native_question_sends_btw_cancel_and_settles(tmp_path, monkeypatch):
    """A3 seam: /btw:cancel <native id> reaches the driver; the row settles."""
    service, drivers = make_service(tmp_path, monkeypatch=monkeypatch, driver_commands=NATIVE_COMMANDS)
    session_id = launch_ok(service)["session"]["id"]

    row = service.ask_side_question(session_id, {"question": "会被取消的问题"})
    drivers[0].emit_side_question_event(btw_event("accepted", "btw-cxl9", question="会被取消的问题"))
    drivers[0].emit_side_question_event(btw_event("running", "btw-cxl9"))

    cancelled = service.cancel_side_question(session_id, row["btwId"])

    assert cancelled["status"] == "cancelled"
    assert drivers[0].prompts[-1] == "/btw:cancel btw-cxl9"
    # The extension's own cancelled event is absorbed (idempotent terminal).
    drivers[0].emit_side_question_event(btw_event("cancelled", "btw-cxl9"))
    assert service.get_side_question(session_id, row["btwId"])["status"] == "cancelled"


def test_native_unavailable_falls_back_to_host_runner(tmp_path, monkeypatch):
    """A6: extension absent -> host sidecar answers; visible, not faked."""
    def runner(context, *, cancel_event, timeout):
        return {"answer": "host 回答（无扩展）。"}

    service, drivers = make_service(tmp_path, monkeypatch=monkeypatch, sidecar_runner=runner)
    # No commands: probe leaves btwNative unset.
    session_id = launch_ok(service)["session"]["id"]
    wait_probe(service, session_id)

    row = service.ask_side_question(session_id, {"question": "没有扩展时谁回答"})

    assert service._get(session_id).meta.get("btwNative") is False
    final = wait_btw(service, session_id, row["btwId"], {"completed"})
    assert final["runner"] == "host"
    assert final["answer"] == "host 回答（无扩展）。"
    assert final["fallbackReason"] is None  # no native attempt was made or promised
    assert drivers[0].prompts == ["hi"]


def test_native_map_routes_duplicates_of_same_question(tmp_path, monkeypatch):
    """Two identical questions pair FIFO; each row keeps its own lifecycle."""
    service, drivers = make_service(tmp_path, monkeypatch=monkeypatch, driver_commands=NATIVE_COMMANDS)
    session_id = launch_ok(service)["session"]["id"]
    wait_probe(service, session_id)

    first = service.ask_side_question(session_id, {"question": "重复的问题"})
    second = service.ask_side_question(session_id, {"question": "重复的问题"})
    emit_answer(drivers[0], "btw-dup-a", "重复的问题", "第一个回答。")
    emit_answer(drivers[0], "btw-dup-b", "重复的问题", "第二个回答。")

    assert wait_btw(service, session_id, first["btwId"], {"completed"})["answer"] == "第一个回答。"
    assert wait_btw(service, session_id, second["btwId"], {"completed"})["answer"] == "第二个回答。"
