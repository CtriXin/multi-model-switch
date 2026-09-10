"""PiRpcDriver protocol tests against the real fixture child subprocess.

Covers: strict LF framing with split chunks, malformed lines, stderr capture,
EOF/exit codes, cancel without orphans, approval scope, message ordering, and
streaming text assembly. No models, providers, or real config are touched.
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
FIXTURE_CHILD = str(Path(__file__).resolve().parent / "fixtures" / "mms_web" / "pi_fake_child.py")

sys.path.insert(0, str(REPO_ROOT))

from mms_web.drivers.base import PipedProcessLauncher, RpcTimeoutError  # noqa: E402
from mms_web.drivers.pi_rpc import PiRpcDriver  # noqa: E402
from mms_web.errors import WebError  # noqa: E402


class RecordingSink:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.events: dict[str, dict] = {}
        self.order: list[str] = []
        self.proto_states: list[str] = []
        self.activities: list[dict] = []
        self.approvals_pending: dict[str, dict] = {}
        self.approvals_resolved: list[tuple[str, str]]
        self.approvals_resolved = []
        self.exited: list[tuple[int, str]] = []
        self.exit_event = threading.Event()

    def upsert_event(self, fields: dict) -> None:
        with self.lock:
            event_id = str(fields.get("id") or f"?{len(self.order)}")
            if event_id in self.events and fields.get("textAppend") is not None:
                self.events[event_id]["text"] = self.events[event_id].get("text", "") + str(
                    fields.get("textAppend")
                )
            else:
                stored = dict(self.events.get(event_id) or {})
                stored.update({k: v for k, v in fields.items() if k != "textAppend"})
                self.events[event_id] = stored
                if event_id not in self.order:
                    self.order.append(event_id)

    def set_proto_state(self, state: str) -> None:
        with self.lock:
            self.proto_states.append(state)

    def set_activity(self, phase: str, **details) -> None:
        with self.lock:
            self.activities.append({"phase": phase, **details})

    def approval_pending(self, approval_id: str, method: str, title: str) -> None:
        with self.lock:
            self.approvals_pending[approval_id] = {"method": method, "title": title}

    def approval_resolved(self, approval_id: str, decision: str) -> None:
        with self.lock:
            self.approvals_resolved.append((approval_id, decision))
            self.approvals_pending.pop(approval_id, None)

    def process_exited(self, exit_code: int, stderr_tail: str) -> None:
        with self.lock:
            self.exited.append((exit_code, stderr_tail))
        self.exit_event.set()

    # helpers

    def wait_for(self, predicate, timeout: float = 8.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.lock:
                if predicate():
                    return
            time.sleep(0.02)
        raise AssertionError("condition not reached in time")

    def text_of(self, event_id: str) -> str:
        with self.lock:
            return self.events.get(event_id, {}).get("text", "")


@pytest.fixture()
def make_driver():
    made: list[PiRpcDriver] = []

    def _make() -> tuple[PiRpcDriver, RecordingSink]:
        sink = RecordingSink()
        process = PipedProcessLauncher().popen(
            [sys.executable, FIXTURE_CHILD], env=dict(os.environ), cwd=str(REPO_ROOT)
        )
        driver = PiRpcDriver(process, sink, name="fake-pi")
        made.append(driver)
        return driver, sink

    yield _make
    for driver in made:
        try:
            driver.close(graceful_timeout=2.0)
        except Exception:
            pass


def test_prompt_streams_text_in_order(make_driver):
    driver, sink = make_driver()
    response = driver.send_prompt("hello world")
    assert response["success"] is True
    sink.wait_for(lambda: "idle" in sink.proto_states)
    assistant_ids = [i for i in sink.order if i.startswith("m-")]
    assert len(assistant_ids) == 1
    assert sink.text_of(assistant_ids[0]) == "echo: hello world"
    # Proto state must come from protocol events only: running then idle.
    assert sink.proto_states[0] == "running"
    assert sink.proto_states[-1] == "idle"


def test_split_json_line_is_buffered(make_driver):
    driver, sink = make_driver()
    assert driver.send_prompt("split")["success"] is True
    sink.wait_for(lambda: "idle" in sink.proto_states)
    assert sink.text_of([i for i in sink.order if i.startswith("m-")][0]) == "echo: split"


def test_malformed_line_becomes_notice_and_flow_continues(make_driver):
    driver, sink = make_driver()
    assert driver.send_prompt("malformed")["success"] is True
    sink.wait_for(lambda: any(e.get("title") == "协议异常" for e in sink.events.values()))
    sink.wait_for(lambda: "idle" in sink.proto_states)
    assert sink.text_of([i for i in sink.order if i.startswith("m-")][0]) == "echo: malformed"


def test_stderr_is_captured_and_reported_on_error_exit(make_driver):
    driver, sink = make_driver()
    driver.send_prompt("stderr")
    sink.wait_for(lambda: "idle" in sink.proto_states)
    driver.send_prompt("exit1")
    assert sink.exit_event.wait(timeout=8)
    code, tail = sink.exited[-1]
    assert code == 1
    assert "fake child stderr diagnostic" in tail
    assert driver.exit_code == 1


def test_exit0_reports_completed_context(make_driver):
    driver, sink = make_driver()
    driver.send_prompt("exit0")
    assert sink.exit_event.wait(timeout=8)
    assert driver.exit_code == 0
    assert sink.exited[-1][0] == 0


def test_crash_drains_pending_requests(make_driver):
    driver, sink = make_driver()
    driver.send_prompt("crash")
    assert sink.exit_event.wait(timeout=8)
    assert sink.exited[-1][0] == 3
    from mms_web.drivers.base import DriverClosedError

    with pytest.raises(DriverClosedError):
        driver.send_prompt("after crash")


def test_tool_lifecycle_maps_to_tool_events(make_driver):
    driver, sink = make_driver()
    assert driver.send_prompt("tool")["success"] is True
    sink.wait_for(lambda: "idle" in sink.proto_states)
    tool_events = [sink.events[i] for i in sink.order if i.startswith("t-")]
    assert len(tool_events) == 1
    tool = tool_events[0]
    assert tool["title"] == "read"
    assert tool["status"] == "done"
    assert "final tool output" in tool["text"]
    # Intermediate partial replaced, not appended.
    assert "partial line" not in tool["text"]


def test_confirm_approval_allow_and_deny(make_driver):
    driver, sink = make_driver()
    assert driver.send_prompt("approval-confirm")["success"] is True
    sink.wait_for(lambda: "ui-confirm-1" in sink.approvals_pending)
    assert sink.approvals_pending["ui-confirm-1"]["method"] == "confirm"
    driver.respond_ui("ui-confirm-1", "allow")
    sink.wait_for(lambda: any(d == "allow" for _, d in sink.approvals_resolved))
    sink.wait_for(lambda: "idle" in sink.proto_states)
    assert sink.text_of([i for i in sink.order if i.startswith("m-")][0]) == "confirm answered: True"

    assert driver.send_prompt("approval-confirm")["success"] is True
    sink.wait_for(lambda: "ui-confirm-1" in sink.approvals_pending)
    driver.respond_ui("ui-confirm-1", "deny")
    sink.wait_for(
        lambda: any(
            sink.text_of(i) == "confirm answered: False" for i in sink.order if i.startswith("m-")
        )
    )
    sink.wait_for(lambda: sink.proto_states[-1:] == ["idle"])


def test_select_requires_an_explicit_value_or_cancel(make_driver):
    driver, sink = make_driver()
    assert driver.send_prompt("approval-select")["success"] is True
    sink.wait_for(lambda: "ui-select-1" in sink.approvals_pending)
    # An approval without an actual selected value must never guess.
    with pytest.raises(WebError) as err:
        driver.respond_ui("ui-select-1", "allow")
    assert err.value.status == 400
    assert err.value.code == "INTERACTION_VALUE_REQUIRED"
    driver.respond_ui("ui-select-1", "deny")
    sink.wait_for(
        lambda: any(
            sink.text_of(i) == "select cancelled: True" for i in sink.order if i.startswith("m-")
        )
    )
    sink.wait_for(lambda: sink.proto_states[-1:] == ["idle"])


def test_unknown_approval_rejected(make_driver):
    driver, sink = make_driver()
    with pytest.raises(WebError) as err:
        driver.respond_ui("does-not-exist", "allow")
    assert err.value.status == 404


def test_notify_is_notice_not_approval(make_driver):
    driver, sink = make_driver()
    assert driver.send_prompt("approval-notify")["success"] is True
    sink.wait_for(lambda: any("fake notify text" in e.get("text", "") for e in sink.events.values()))
    sink.wait_for(lambda: "idle" in sink.proto_states)
    assert all(e.get("kind") != "approval" for e in sink.events.values())
    assert sink.approvals_pending == {}


def test_failed_prompt_reports_error(make_driver):
    driver, sink = make_driver()
    response = driver.send_prompt("fail")
    assert response["success"] is False
    assert "simulated prompt rejection" in response["error"]
    sink.wait_for(lambda: any(e.get("title") == "命令错误" for e in sink.events.values()))


def test_abort_stops_streaming_without_orphan(make_driver):
    driver, sink = make_driver()
    driver.send_prompt("stream-forever")
    sink.wait_for(lambda: len([i for i in sink.order if i.startswith("m-")]) == 1)
    response = driver.abort()
    assert response["success"] is True
    sink.wait_for(lambda: "idle" in sink.proto_states)
    driver.close(graceful_timeout=2.0)
    assert sink.exit_event.wait(timeout=8)
    assert driver._proc.poll() is not None, "child must be reaped, no orphan"


def test_close_reaps_child_via_stdin_eof(make_driver):
    driver, sink = make_driver()
    driver.send_prompt("hello")
    sink.wait_for(lambda: "idle" in sink.proto_states)
    driver.close(graceful_timeout=3.0)
    assert sink.exit_event.wait(timeout=8)
    assert driver._proc.poll() is not None


def test_get_state_roundtrip(make_driver):
    driver, sink = make_driver()
    state = driver.get_state()
    assert state.get("isStreaming") is False


def test_response_timeout_raises(make_driver):
    driver, sink = make_driver()
    with pytest.raises(RpcTimeoutError):
        driver.request({"type": "prompt", "message": "never-answered"}, timeout=0.2)


def test_crlf_line_is_accepted():
    import subprocess

    sink = RecordingSink()
    code = (
        "import json,sys\n"
        "msg={\"type\":\"agent_start\"}\n"
        "sys.stdout.write(json.dumps(msg)+\"\\r\\n\")\n"
        "sys.stdout.flush()\n"
        "sys.stdin.readline()\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    driver = PiRpcDriver(proc, sink, name="crlf")
    try:
        sink.wait_for(lambda: "running" in sink.proto_states)
        assert sink.proto_states == ["running"]
    finally:
        driver.close(graceful_timeout=2.0)


def test_explicit_select_input_and_editor_answers(make_driver):
    driver, sink = make_driver()
    for method in ("select", "input", "editor"):
        request_id = "ui-" + method
        driver._handle_ui_request({"type": "extension_ui_request", "id": request_id,
            "method": method, "title": "Your choice", "options": ["A", "B"], "prefill": "initial"})
        value = "B" if method == "select" else "Typed answer"
        driver.respond_ui(request_id, "allow", value)
        assert request_id not in driver.pending_approvals()
        event = sink.events["a-" + request_id]
        assert event["answer"] == value and event["decision"] == "allow"
        assert event["method"] == method
