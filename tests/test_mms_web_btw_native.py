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
