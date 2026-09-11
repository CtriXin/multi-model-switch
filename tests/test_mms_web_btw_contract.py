"""Pilot ``/btw`` side-question contract tests (fixtures + regression + negative).

The real Pilot backend now implements side questions (``mms_web/side_questions.py``
+ server routes; see also ``test_mms_web_btw_backend.py``).
This suite keeps two layers:

- The task-owned fixture (tests/fixtures/mms_web/btw_side_questions.py)
  still pins the minimal behavior contract from MESSAGE-CONTROL-SPEC.md /
  HANDOFF-BTW.md as a reference implementation.
- The "real surface" tests below assert the REAL SessionService and
  WebApplication: the backend exists, routes end-to-end, reports its
  capabilities from real sources only, and never fakes a success.

Contract coverage:
1. A running main task is never interrupted by a BTW.
2. BTW never enters the main transcript, event sequence, or follow-up queue.
3. Multiple BTWs stay independent (ids, statuses, order, idempotency).
4. A pending approval is observable but never resolved by a BTW.
5. Sidecar failures/timeouts are visible and never affect the main task.
6. After reload/restart, completed BTWs survive verbatim and unfinished ones
   become ``uncertain`` — never fabricated success.
7. Unsupported capabilities report ``supported:false`` + reason at the
   fixture layer, and the real service/server only advertise what has a
   real source — nothing fakes a successful answer.

No production code is modified by this suite.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "mms_web"))

from btw_side_questions import (  # noqa: E402
    BTW_FINAL_STATES,
    BTW_TRANSITIONS,
    SIDECAR_CONTEXT_FIELDS,
    FakeBtwSidecar,
    SideQuestionStore,
)
from mms_web.errors import WebError  # noqa: E402
from mms_web.sessions import SessionService  # noqa: E402

QUESTION = "现在进行到哪一步了？"
ANALYTIC = "这两个方案的架构取舍分别是什么？"


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
    """In-process driver double; records every main-channel interaction."""

    def __init__(self, sink=None) -> None:
        self.lock = threading.Lock()
        self._alive = True
        self._sink = sink
        self.prompts: list[str] = []
        self.aborts = 0
        self.ui_responses: list[tuple[str, str]] = []

    def alive(self) -> bool:
        return self._alive

    def send_prompt(self, text: str) -> dict:
        with self.lock:
            self.prompts.append(text)
        return {"type": "response", "command": "prompt", "success": True}

    def abort(self) -> dict:
        with self.lock:
            self.aborts += 1
        return {"type": "response", "command": "abort", "success": True}

    def respond_ui(self, approval_id: str, decision: str) -> None:
        with self.lock:
            self.ui_responses.append((approval_id, decision))
        if self._sink is not None:
            self._sink.upsert_event(
                {"id": f"a-{approval_id}", "kind": "approval", "approvalId": approval_id, "decision": decision}
            )
            self._sink.approval_resolved(approval_id, decision)

    def close(self, *, graceful_timeout: float = 5.0) -> None:
        self._alive = False

    def kill(self) -> None:
        self._alive = False


@pytest.fixture()
def seeded_seam(monkeypatch):
    monkeypatch.setattr(
        "mms_web.sessions.probe_mms_pi_seam", lambda: {"available": True, "injected": True}
    )


def make_service(tmp_path: Path, *, sidecar_runner=None, btw_timeout=None) -> tuple[SessionService, list[FakeDriver]]:
    drivers: list[FakeDriver] = []

    def driver_factory(plan, sink):
        driver = FakeDriver(sink=sink)
        drivers.append(driver)
        return driver

    def plan_builder(harness, model_info, runtime, cwd):
        from mms_web.drivers.launch_bridge import LaunchPlan

        return LaunchPlan(cmd=["true"], env={}, cwd=cwd, harness=harness)

    kwargs = {}
    if sidecar_runner is not None:
        kwargs["sidecar_runner"] = sidecar_runner
    if btw_timeout is not None:
        kwargs["btw_timeout"] = btw_timeout
    service = SessionService(
        config_root=tmp_path / "config",
        state_root=tmp_path / "state",
        catalog=FakeCatalog(),
        driver_factory=driver_factory,
        launch_plan_builder=plan_builder,
        real_launch=True,
        **kwargs,
    )
    return service, drivers


def launch_ok(service, request_id="req-1", prompt="主任务目标"):
    return service.launch(
        {"requestId": request_id, "workspaceId": "ws-1", "presetId": "p-1", "prompt": prompt}
    )


def session_detail(service, session_id) -> dict:
    """Real session detail plus the queue truth (session.meta['queue'], the
    single place queue_update writes to; runtime view reads the same)."""
    detail = service.get_session(session_id)
    detail["queue"] = list(service._sessions[session_id].meta.get("queue") or [])
    return detail


def make_store(service, tmp_path, sidecar=None) -> SideQuestionStore:
    return SideQuestionStore(
        tmp_path / "state", sidecar=sidecar,
        state_reader=lambda session_id: session_detail(service, session_id),
    )


def transcript_snapshot(service, session_id) -> tuple[list[dict], int]:
    detail = service.get_session(session_id)
    return detail["events"], detail["session"]["updatedAt"]


# ---------------------------------------------------------------------------
# 1. A running main task is never interrupted by a BTW.
# ---------------------------------------------------------------------------

def test_btw_while_running_never_touches_main_driver_or_state(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service, prompt="长任务主目标")
    session_id = detail["session"]["id"]
    driver = drivers[0]
    events_before, _ = transcript_snapshot(service, session_id)
    prompts_before = list(driver.prompts)

    store = make_store(service, tmp_path, sidecar=FakeBtwSidecar(mode="answer"))
    for question in (QUESTION, ANALYTIC, "/btw 当前是不是在等我审批？"):
        record = store.ask(session_id, {"question": question})
        assert record["status"] in BTW_FINAL_STATES

    assert driver.prompts == prompts_before, "BTW must never send a main-channel prompt"
    assert driver.aborts == 0, "BTW must never abort the main task"
    assert driver.ui_responses == []
    assert driver.alive()
    events_after, _ = transcript_snapshot(service, session_id)
    assert events_after == events_before, "main transcript must be untouched"
    assert service.get_session(session_id)["session"]["state"] == "running"


def test_btw_while_sidecar_hangs_keeps_main_task_running(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service)
    session_id = detail["session"]["id"]
    store = make_store(service, tmp_path, sidecar=FakeBtwSidecar(mode="hang"))
    record = store.ask(session_id, {"question": ANALYTIC})
    assert record["status"] == "running"
    assert service.get_session(session_id)["session"]["state"] == "running"
    assert drivers[0].alive()


# ---------------------------------------------------------------------------
# 2. BTW never enters the main transcript, event sequence, or queue.
# ---------------------------------------------------------------------------

def test_btw_never_enters_main_transcript_or_queue(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    detail = launch_ok(service, prompt="主任务目标XYZ")
    session_id = detail["session"]["id"]
    live = service._sessions[session_id]

    # A follow-up queue exists with one pending supplement (the real queue
    # surface BTW must not join).
    service._apply_driver_event(
        live,
        {"id": "n-queue", "kind": "notice", "title": "待发送消息",
         "text": "还有 1 条补充消息等待执行", "queue": ["补充说明A"]},
    )
    events_before, _ = transcript_snapshot(service, session_id)

    marker = "旁问独有标记ABC123"
    sidecar = FakeBtwSidecar(mode="answer", answer=f"关于{marker}的回答")
    store = make_store(service, tmp_path, sidecar=sidecar)
    store.ask(session_id, {"question": f"{ANALYTIC}（{marker}）"})
    store.ask(session_id, {"question": QUESTION})

    # Main transcript: no BTW question, no BTW answer, sequence unchanged.
    events_after, _ = transcript_snapshot(service, session_id)
    assert events_after == events_before
    dumped = json.dumps(events_after, ensure_ascii=False)
    assert marker not in dumped and QUESTION not in dumped

    # The driver never saw the question (no prompt, no queue join).
    assert all(marker not in p and QUESTION not in p for p in drivers[0].prompts)
    queue_notices = [e for e in events_after if e.get("id") == "n-queue"]
    assert queue_notices, "precondition: queue notice exists"
    # Queue truth lives in session.meta['queue'] (written by queue_update and
    # read by the runtime view); the BTW must not have joined it.
    assert live.meta["queue"] == ["补充说明A"], "BTW must not enter the follow-up queue"

    # Session persistence file has no BTW content either.
    session_file = tmp_path / "state" / "sessions" / f"{session_id}.json"
    assert marker not in session_file.read_text(encoding="utf-8")

    # Contrast: a normal send DOES append a user event to the transcript.
    service.send(session_id, {"requestId": "send-1", "text": "正常补充消息"})
    events_sent, _ = transcript_snapshot(service, session_id)
    assert any(e.get("kind") == "user" and e.get("text") == "正常补充消息" for e in events_sent)
    assert len(events_sent) > len(events_after)


# ---------------------------------------------------------------------------
# 3. Multiple BTWs stay independent.
# ---------------------------------------------------------------------------

def test_multiple_btws_have_independent_ids_and_statuses(tmp_path, seeded_seam):
    service, _ = make_service(tmp_path)
    session_id = launch_ok(service)["session"]["id"]
    sidecar = FakeBtwSidecar(mode="answer")
    store = make_store(service, tmp_path, sidecar=sidecar)

    first = store.ask(session_id, {"question": QUESTION})  # state answer
    sidecar.mode = "error"
    second = store.ask(session_id, {"question": f"{ANALYTIC}-失败"})  # completion fails
    sidecar.mode = "hang"
    third = store.ask(session_id, {"question": f"{ANALYTIC}-挂起"})  # never finishes

    ids = {first["btwId"], second["btwId"], third["btwId"]}
    assert len(ids) == 3, "each BTW needs its own id"
    assert first["source"] == "state" and first["status"] == "completed" and first["answer"]
    assert second["source"] == "completion" and second["status"] == "failed"
    assert second["error"] and not second["answer"]
    assert third["status"] == "running" and not third["answer"] and not third["completedAt"]

    listed = store.list(session_id)
    assert [r["btwId"] for r in listed] == [first["btwId"], second["btwId"], third["btwId"]], \
        "BTW order is preserved and never overwritten"
    assert [r["status"] for r in listed] == ["completed", "failed", "running"]


def test_idempotency_key_replays_original_btw(tmp_path, seeded_seam):
    service, _ = make_service(tmp_path)
    session_id = launch_ok(service)["session"]["id"]
    sidecar = FakeBtwSidecar(mode="answer")
    store = make_store(service, tmp_path, sidecar=sidecar)

    original = store.ask(session_id, {"question": ANALYTIC, "idempotencyKey": "btw-idem-1"})
    replay = store.ask(session_id, {"question": ANALYTIC, "idempotencyKey": "btw-idem-1"})
    assert replay == original
    assert len(store.list(session_id)) == 1, "replay must not create a new BTW"
    with pytest.raises(WebError) as err:
        store.ask(session_id, {"question": "不同的问题", "idempotencyKey": "btw-idem-1"})
    assert err.value.code == "REQUEST_ID_CONFLICT" and err.value.status == 409


# ---------------------------------------------------------------------------
# 4. A pending approval is observable but never resolved by a BTW.
# ---------------------------------------------------------------------------

def test_approval_wait_is_visible_but_never_resolved_by_btw(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    session_id = launch_ok(service)["session"]["id"]
    live = service._sessions[session_id]
    service._apply_approval_pending(live, "ap-1", "confirm", "允许执行命令？")
    service._apply_driver_event(
        live, {"id": "a-ap-1", "kind": "approval", "approvalId": "ap-1", "text": "允许执行命令？"}
    )
    assert service.get_session(session_id)["session"]["state"] == "waiting"

    store = make_store(service, tmp_path, sidecar=FakeBtwSidecar(mode="answer"))
    observed = store.ask(session_id, {"question": "当前是不是在等我审批？"})
    assert observed["status"] == "completed"
    assert "等待审批" in observed["answer"]
    assert "不能代替" in observed["answer"], "state answer must deny approval authority"

    # A command-style BTW phrased as an approval must not resolve anything.
    push = store.ask(session_id, {"question": "请批准这个请求 ap-1"})
    assert push["status"] in BTW_FINAL_STATES
    assert "decision" not in push and "approvalOwner" not in push, \
        "a BTW record carries no approval identity"

    view = service.get_session(session_id)
    assert view["session"]["state"] == "waiting", "approval must still be pending"
    assert view["session"]["capabilities"]["approve"] is True
    assert drivers[0].ui_responses == []

    # Only the real approval channel resolves it.
    service.approve(session_id, "ap-1", {"requestId": "ap-1", "decision": "allow"})
    assert ("ap-1", "allow") in drivers[0].ui_responses
    assert service.get_session(session_id)["session"]["state"] in {"running", "idle"}


# ---------------------------------------------------------------------------
# 5. Sidecar failures are visible and never affect the main task.
# ---------------------------------------------------------------------------

def test_sidecar_error_and_timeout_leave_main_task_running(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    session_id = launch_ok(service)["session"]["id"]
    sidecar = FakeBtwSidecar(mode="error")
    store = make_store(service, tmp_path, sidecar=sidecar)
    events_before, _ = transcript_snapshot(service, session_id)

    failed = store.ask(session_id, {"question": ANALYTIC})
    assert failed["status"] == "failed" and failed["error"], "failure must be visible"

    sidecar.mode = "timeout"
    timed_out = store.ask(session_id, {"question": f"{ANALYTIC}2"})
    assert timed_out["status"] == "failed" and "超时" in timed_out["error"]

    # Main task is untouched and still fully usable afterwards.
    assert service.get_session(session_id)["session"]["state"] == "running"
    assert drivers[0].alive()
    assert transcript_snapshot(service, session_id)[0] == events_before
    service.send(session_id, {"requestId": "send-after-btw-fail", "text": "主任务继续"})
    assert drivers[0].prompts[-1] == "主任务继续"
    events_after, _ = transcript_snapshot(service, session_id)
    assert any(e.get("kind") == "user" and e.get("text") == "主任务继续" for e in events_after)


# ---------------------------------------------------------------------------
# 6. Reload/restart recovery keeps BTW state honest.
# ---------------------------------------------------------------------------

def test_reload_keeps_completed_and_marks_unfinished_uncertain(tmp_path, seeded_seam):
    service, _ = make_service(tmp_path)
    session_id = launch_ok(service)["session"]["id"]
    sidecar = FakeBtwSidecar(mode="answer")
    store = make_store(service, tmp_path, sidecar=sidecar)
    done = store.ask(session_id, {"question": ANALYTIC, "idempotencyKey": "btw-done"})
    sidecar.mode = "hang"
    hanging = store.ask(session_id, {"question": f"{ANALYTIC}-挂起"})
    cancelled = store.ask(session_id, {"question": f"{ANALYTIC}-取消"})
    store.cancel(session_id, cancelled["btwId"])

    reloaded = make_store(service, tmp_path, sidecar=FakeBtwSidecar(mode="answer"))
    records = {r["btwId"]: r for r in reloaded.list(session_id)}
    assert set(records) == {done["btwId"], hanging["btwId"], cancelled["btwId"]}

    recovered_done = records[done["btwId"]]
    assert recovered_done["status"] == "completed"
    assert recovered_done["answer"] == done["answer"]
    assert recovered_done["question"] == done["question"]

    recovered_hanging = records[hanging["btwId"]]
    assert recovered_hanging["status"] == "uncertain", "unfinished must not fake success"
    assert recovered_hanging["recoveredFrom"] == "running"
    assert not recovered_hanging["answer"] and not recovered_hanging["completedAt"]
    assert recovered_hanging["error"], "uncertainty must be explained"

    assert records[cancelled["btwId"]]["status"] == "cancelled"

    # A finished BTW stays immutable across another reload.
    again = make_store(service, tmp_path, sidecar=None)
    assert again.get(session_id, done["btwId"])["status"] == "completed"


def test_main_session_and_btws_readable_separately_after_restart(tmp_path, seeded_seam):
    service, _ = make_service(tmp_path)
    session_id = launch_ok(service, request_id="req-restart", prompt="重启前主任务")["session"]["id"]
    store = make_store(service, tmp_path, sidecar=FakeBtwSidecar(mode="answer"))
    done = store.ask(session_id, {"question": QUESTION})
    service.close()

    service2, _ = make_service(tmp_path)  # fresh service, same state root
    assert service2.get_session(session_id)["session"]["state"] == "stopped", \
        "restart must not pretend the child runs"

    store2 = make_store(service2, tmp_path, sidecar=FakeBtwSidecar(mode="answer"))
    recovered = store2.get(session_id, done["btwId"])
    assert recovered["status"] == "completed" and recovered["answer"] == done["answer"]
    assert [e.get("text") for e in service2.get_session(session_id)["events"]
            if e.get("kind") == "user"] == ["重启前主任务"]

    # The main task is finished now: a new BTW has no bypass target.
    with pytest.raises(WebError) as err:
        store2.ask(session_id, {"question": QUESTION})
    assert err.value.code == "CAPABILITY_UNAVAILABLE" and err.value.status == 409


# ---------------------------------------------------------------------------
# 7. Unsupported capabilities never fake success.
# ---------------------------------------------------------------------------

def test_real_session_service_reports_btw_capabilities_honestly(tmp_path, seeded_seam, monkeypatch):
    """Positive + negative capability contract on the REAL service.

    The backend exists now, so the contract flips: state answers are a real,
    session-owned capability and are advertised; model-backed answers are
    advertised only when a real source exists (an injected read-only runner
    or a usable route transport). No fabricated ``True``."""
    service, _ = make_service(tmp_path)
    caps = service.capabilities()
    # State answers are always real: they read the session snapshot only.
    assert caps["sideQuestions"] is True

    # No injected runner + no usable route transport -> not advertised.
    monkeypatch.setattr("mms_web.sessions._route_completion_build", lambda: False)
    bare, _ = make_service(tmp_path / "bare")
    assert bare.capabilities()["sidecarCompletion"] is False

    # An injected read-only runner is a real source and is advertised again.
    def idle_runner(context, *, cancel_event, timeout):
        return {"answer": "fixture"}  # pragma: no cover - never called here

    injected, _ = make_service(tmp_path / "injected", sidecar_runner=idle_runner)
    assert injected.capabilities()["sidecarCompletion"] is True

    # The real rows surface on the session detail, beside the transcript.
    session_id = launch_ok(service)["session"]["id"]
    row = service.ask_side_question(session_id, {"question": QUESTION})
    assert row["status"] == "completed" and row["source"] == "state"
    detail = service.get_session(session_id)
    assert [r["btwId"] for r in detail["sideQuestions"]] == [row["btwId"]]
    # Session-level caps stay about the main turn (send/stop/approve);
    # /btw is a service-level capability and is not re-claimed per session.
    assert set(detail["session"]["capabilities"]) == {"send", "stop", "approve"}


def test_real_server_routes_side_questions_end_to_end(tmp_path, seeded_seam, monkeypatch):
    """The real HTTP app now owns the side-question routes. End-to-end over
    a real SessionService: asking through the route answers from state,
    never touches the main transcript or driver, settled rows are never
    rewritten by a late cancel, and every failure path stays honest (404
    for a missing session/row/unknown variant — never a faked success)."""
    from mms_web.server import WebApplication

    def adapter(module, name, **kwargs):
        if module == "mms_web.catalog":
            return FakeCatalog()
        return None  # sessions is injected below

    monkeypatch.setattr("mms_web.server._adapter", adapter)
    app = WebApplication(state_root=tmp_path / "app-state")
    service, drivers = make_service(tmp_path)
    app.sessions = service
    try:
        detail = launch_ok(service, prompt="端到端主任务")
        session_id = detail["session"]["id"]
        events_before = [e["id"] for e in detail["events"]]

        row = app.post(["sessions", session_id, "side-questions"],
                       {"question": "现在进行到哪一步了？"})
        assert row["status"] == "completed" and row["source"] == "state"
        assert row["mainSessionId"] == session_id

        listed = app.get(["sessions", session_id, "side-questions"])
        assert [r["btwId"] for r in listed["sideQuestions"]] == [row["btwId"]]
        fetched = app.get(["sessions", session_id, "side-questions", row["btwId"]])
        assert fetched["btwId"] == row["btwId"]
        assert "idempotencyKey" not in fetched, "keys never leave the service"

        # Isolation holds through the real HTTP surface too.
        after = service.get_session(session_id)
        assert [e["id"] for e in after["events"]] == events_before
        assert drivers[0].prompts == ["端到端主任务"]
        assert row["btwId"] not in {e["id"] for e in after["events"]}

        # Cancelling a settled row is an idempotent no-op: history is never
        # rewritten into a fake cancellation.
        again = app.post(["sessions", session_id, "side-questions", row["btwId"], "cancel"], {})
        assert again["status"] == "completed" and again["answer"] == row["answer"]

        # Failure paths stay honest: 404, never a fabricated success.
        with pytest.raises(WebError) as err:
            app.post(["sessions", "s-missing", "side-questions"], {"question": "状态？"})
        assert err.value.status == 404
        with pytest.raises(WebError) as err:
            app.get(["sessions", session_id, "side-questions", "btw-missing"])
        assert err.value.status == 404 and err.value.code == "BTW_NOT_FOUND"
        with pytest.raises(WebError) as err:
            app.get(["sessions", session_id, "side-questions", row["btwId"], "extra"])
        assert err.value.status == 404 and err.value.code == "NOT_FOUND"
    finally:
        app.close()


def test_no_sidecar_analytic_question_fails_closed(tmp_path, seeded_seam):
    service, _ = make_service(tmp_path)
    session_id = launch_ok(service)["session"]["id"]
    store = make_store(service, tmp_path, sidecar=None)
    assert store.capability()["sideQuestions"]["supported"] is False
    with pytest.raises(WebError) as err:
        store.ask(session_id, {"question": ANALYTIC})
    assert err.value.code == "CAPABILITY_UNAVAILABLE" and err.value.status == 409
    assert store.list(session_id) == [], "fail-closed must leave no phantom record"


def test_no_sidecar_state_question_answers_from_state_only(tmp_path, seeded_seam):
    service, _ = make_service(tmp_path)
    session_id = launch_ok(service)["session"]["id"]
    store = make_store(service, tmp_path, sidecar=None)
    record = store.ask(session_id, {"question": QUESTION})
    assert record["status"] == "completed" and record["source"] == "state"
    assert record["answer"] and record["routeSnapshot"] == {"source": "state"}
    assert store.capability()["sideQuestions"]["stateOnly"] is True


def test_unsupported_sidecar_never_fakes_success(tmp_path, seeded_seam):
    service, _ = make_service(tmp_path)
    session_id = launch_ok(service)["session"]["id"]
    sidecar = FakeBtwSidecar(mode="answer")
    sidecar.supported = False
    sidecar.unsupported_reason = "fixture：旁问模型未配置"
    store = make_store(service, tmp_path, sidecar=sidecar)
    cap = store.capability()["sideQuestions"]
    assert cap["supported"] is False and cap["reason"] == "fixture：旁问模型未配置"
    with pytest.raises(WebError) as err:
        store.ask(session_id, {"question": ANALYTIC})
    assert err.value.code == "CAPABILITY_UNAVAILABLE"
    assert sidecar.calls == [], "an unsupported sidecar must not even be called"
    assert store.list(session_id) == []


# ---------------------------------------------------------------------------
# State machine and input validation (negative).
# ---------------------------------------------------------------------------

def test_state_machine_rejects_illegal_transitions():
    record = {"status": "prepared"}
    for illegal in ("completed", "failed", "running"):
        with pytest.raises(AssertionError):
            SideQuestionStore._transition(dict(record), illegal)
    for terminal in BTW_FINAL_STATES:
        with pytest.raises(AssertionError):
            SideQuestionStore._transition({"status": terminal}, "running")
    # The legal graph matches MESSAGE-CONTROL-SPEC §4 exactly.
    assert BTW_TRANSITIONS["prepared"] == {"accepted", "cancelled", "uncertain"}
    assert "completed" in BTW_TRANSITIONS["running"]
    assert "uncertain" in BTW_TRANSITIONS["running"]


def test_cancel_rejects_finished_btw(tmp_path, seeded_seam):
    service, _ = make_service(tmp_path)
    session_id = launch_ok(service)["session"]["id"]
    store = make_store(service, tmp_path, sidecar=FakeBtwSidecar(mode="answer"))
    done = store.ask(session_id, {"question": QUESTION})
    with pytest.raises(WebError) as err:
        store.cancel(session_id, done["btwId"])
    assert err.value.code == "BTW_ALREADY_FINISHED" and err.value.status == 409
    with pytest.raises(WebError) as err:
        store.cancel(session_id, "btw-missing")
    assert err.value.code == "BTW_NOT_FOUND" and err.value.status == 404


def test_ask_validates_payload_and_missing_session(tmp_path, seeded_seam):
    service, _ = make_service(tmp_path)
    session_id = launch_ok(service)["session"]["id"]
    store = make_store(service, tmp_path, sidecar=FakeBtwSidecar(mode="answer"))
    for bad in ({}, {"question": ""}, {"question": "   "}, {"question": 5}, {"question": QUESTION, "idempotencyKey": "bad key!"}):
        with pytest.raises(WebError) as err:
            store.ask(session_id, bad)
        assert err.value.code == "INVALID_REQUEST" and err.value.status == 400
    with pytest.raises(WebError) as err:
        store.ask("missing-session", {"question": QUESTION})
    assert err.value.status == 404

    blind = SideQuestionStore(tmp_path / "other-state", sidecar=FakeBtwSidecar())
    with pytest.raises(WebError) as err:
        blind.ask(session_id, {"question": QUESTION})
    assert err.value.code == "CAPABILITY_UNAVAILABLE" and err.value.status == 409


# ---------------------------------------------------------------------------
# Sidecar context is allowlisted and secret-free.
# ---------------------------------------------------------------------------

def test_sidecar_context_is_allowlisted_and_secret_free(tmp_path, seeded_seam):
    service, _ = make_service(tmp_path)
    session_id = launch_ok(service)["session"]["id"]
    live = service._sessions[session_id]
    secret = "sk-fixture-secret-987654321"
    service._apply_driver_event(
        live,
        {"id": "m-secret", "kind": "assistant",
         "text": f"内部推理正文，包含密钥 {secret} 和完整思路",
         "thinking": "完整 thinking 不应外传"},
    )
    service._apply_driver_event(
        live, {"id": "t-1", "kind": "tool", "title": "read_file", "status": "finished"}
    )

    sidecar = FakeBtwSidecar(mode="answer")
    store = make_store(service, tmp_path, sidecar=sidecar)
    record = store.ask(session_id, {"question": ANALYTIC})
    assert record["status"] == "completed"

    assert len(sidecar.calls) == 1
    context = sidecar.calls[0]["context"]
    assert set(context) <= set(SIDECAR_CONTEXT_FIELDS), "context must be allowlisted"
    dumped = json.dumps(context, ensure_ascii=False)
    assert secret not in dumped
    assert "内部推理正文" not in dumped and "thinking 不应外传" not in dumped
    assert context["lastToolTitle"] == "read_file"
    assert context["mainState"] == "running"
    # The persisted BTW record carries no transcript bodies either.
    btw_files = list((tmp_path / "state" / "side-questions" / session_id).glob("*.json"))
    assert len(btw_files) == 1
    persisted = btw_files[0].read_text(encoding="utf-8")
    assert secret not in persisted and "内部推理正文" not in persisted
