"""Activity is observed, scoped to the current turn, and never restored as busy."""
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from test_mms_web_interactions import local_app, settle
from test_mms_web_sessions_pi_driver import make_driver
from test_mms_web_sessions_service import make_service
from mms_web.drivers.launch_bridge import probe_mms_pi_seam


def test_protocol_phases_use_settled_not_agent_end(make_driver):
    driver, sink = make_driver()
    def event(kind, **fields):
        driver._handle_event({"type": kind, **fields})
    event("agent_start")
    assert sink.activities[-1]["phase"] == "running"  # No invented thinking.
    event("message_start", message={"role": "assistant"})
    event("message_update", assistantMessageEvent={"type": "thinking_delta", "delta": "reason"})
    thinking_id = sink.activities[-1]["eventId"]
    assert sink.activities[-1]["phase"] == "thinking"
    event("message_update", assistantMessageEvent={"type": "text_delta", "delta": "answer"})
    assert sink.activities[-1] == {"phase": "responding", "eventId": thinking_id}
    event("message_end", message={"role": "assistant", "content": []})
    event("tool_execution_start", toolCallId="one", toolName="read")
    event("tool_execution_start", toolCallId="two", toolName="bash")
    event("tool_execution_end", toolCallId="two")
    assert sink.activities[-1] == {"phase": "tool", "toolName": "read", "eventId": "t-one"}
    event("tool_execution_end", toolCallId="one")
    event("agent_end", willRetry=True)
    assert sink.proto_states[-1] == "running"
    event("auto_retry_start")
    assert sink.activities[-1]["phase"] == "retrying"
    event("auto_retry_end")
    event("compaction_start")
    assert sink.activities[-1]["phase"] == "compacting"
    event("compaction_end")
    assert sink.activities[-1]["phase"] == "running"
    event("agent_settled")
    assert sink.proto_states[-1] == "idle" and sink.activities[-1]["phase"] == "idle"
    event("compaction_start")  # User-initiated compact while no turn is running.
    event("compaction_end")
    assert sink.activities[-1]["phase"] == "idle"


@pytest.mark.parametrize("stop_reason,error,phase", [("error", "upstream failed", "error"), ("aborted", "aborted", "stopped")])
def test_failed_or_aborted_turn_does_not_look_successful(make_driver, stop_reason, error, phase):
    driver, sink = make_driver()
    driver._handle_event({"type": "agent_start"})
    driver._handle_event({"type": "message_end", "message": {"role": "assistant", "content": [], "stopReason": stop_reason, "errorMessage": error}})
    driver._handle_event({"type": "agent_settled"})
    assert sink.proto_states[-1] == "idle"  # Still able to send another prompt.
    assert sink.activities[-1]["phase"] == phase
    driver._handle_event({"type": "agent_start"})
    assert sink.activities[-1]["phase"] == "running"
    driver._handle_event({"type": "agent_settled"})
    assert sink.activities[-1]["phase"] == "idle"


def test_waiting_precedence_terminal_cleanup_and_restart(tmp_path, monkeypatch):
    service, drivers = make_service(tmp_path, monkeypatch=monkeypatch)
    try:
        detail = service.launch({"requestId":"status-service", "presetId":"p", "workspaceId":"w", "prompt":"work"})
        sid = detail["session"]["id"]
        session = service._get(sid)
        sink = drivers[0]._sink
        sink.set_proto_state("running")
        sink.set_activity("thinking", eventId="old")
        first = session.session_view()["activity"]
        sink.set_activity("thinking", eventId="old")
        assert session.session_view()["activity"]["since"] == first["since"]
        sink.approval_pending("ask", "input", "Question")
        sink.set_activity("tool", eventId="t-tool", toolName="read")
        assert session.session_view()["activity"] == {"phase":"waiting", "method":"input"}
        sink.approval_resolved("ask", "allow")
        assert session.session_view()["activity"]["phase"] == "tool"
        sink.upsert_event({"id":"t-tool", "kind":"tool", "status":"running", "text":"partial"})
        sink.set_proto_state("idle")
        assert session.session_view()["activity"] is None
        assert session.event_index["t-tool"]["status"] == "error"
        sink.set_proto_state("running")
        sink.set_activity("thinking", eventId="new")
        assert session.session_view()["activity"]["eventId"] == "new"
        sink.upsert_event({"id":"t-interrupted", "kind":"tool", "status":"running", "text":"unfinished before restart"})
        restarted, _ = make_service(tmp_path)
        assert restarted.get_session(sid)["session"]["state"] == "stopped"
        assert restarted.get_session(sid)["session"]["activity"] is None
        assert restarted._get(sid).event_index["t-interrupted"]["status"] == "error"
        restarted.close()
        sink.process_exited(1, "failure")
        sink.set_activity("thinking", eventId="late")
        assert session.session_view()["state"] == "error"
        assert session.session_view()["activity"] is None
    finally:
        service.close()


@pytest.fixture
def staged_native(local_app):
    if not probe_mms_pi_seam()["available"]:
        pytest.skip("compatible Pi required")
    app, workspace, root = local_app
    gates = [threading.Event() for _ in range(3)]
    received = threading.Event()
    records = []
    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            records.append(request)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            def chunk(delta, finish=None):
                payload = {"id":"native-status", "object":"chat.completion.chunk", "created":1, "model":"gpt-5", "choices":[{"index":0, "delta":delta, "finish_reason":finish}]}
                self.wfile.write(("data: " + json.dumps(payload) + "\n\n").encode())
                self.wfile.flush()
            try:
                if request["messages"][-1]["role"] == "user":
                    received.set()
                    gates[0].wait(15)
                    chunk({"role":"assistant", "reasoning_content":"Native thinking marker."})
                    gates[1].wait(15)
                    chunk({"content":"I will read the local task result."})
                    gates[2].wait(15)
                    chunk({"tool_calls":[{"index":0,"id":"call-status","type":"function","function":{"name":"bash","arguments":json.dumps({"command":"while [ ! -f status-release ]; do sleep 0.05; done; printf 'native tool finished'", "timeout":10})}}]})
                    chunk({}, "tool_calls")
                else:
                    chunk({"role":"assistant", "content":"Native status finished."})
                    chunk({}, "stop")
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
    server = ThreadingHTTPServer(("127.0.0.1",0), Provider)
    thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    preview = app.post(["configuration","preview"], {"service":{"name":"Status fixture", "baseUrl":f"http://127.0.0.1:{server.server_port}/v1", "apiKey":"test-owned-key", "models":["gpt-5"], "protocol":"openai"}})
    app.post(["configuration","apply"], {"previewId":preview["previewId"],"revision":preview["revision"]})
    yield app, workspace, root, gates, received, records
    for gate in gates: gate.set()
    (root / "status-release").touch()
    server.shutdown(); server.server_close(); thread.join()


@pytest.mark.xfail(
    os.name == "nt",
    reason="hosted Windows Server Pi native bootstrap does not load the configured model yet",
    strict=False,
)
def test_actual_pi_activity_and_session_list(staged_native):
    app, workspace, root, gates, received, records = staged_native
    detail = app.post(["sessions"], {"requestId":"native-status", "presetId":"web:pi:status-fixture:gpt-5", "workspaceId":workspace["id"], "prompt":"status-flow", "thinkingLevel":"medium"})
    sid = detail["session"]["id"]
    def wait_phase(phase):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            row = next(s for s in app.get(["sessions"])["sessions"] if s["id"] == sid)
            if (row.get("activity") or {}).get("phase") == phase:
                return row
            time.sleep(.02)
        raise AssertionError(f"never observed {phase}: {row}")
    assert received.wait(10)
    wait_phase("running")
    gates[0].set()
    thinking = wait_phase("thinking")
    assert thinking["state"] == "running"
    gates[1].set()
    responding = wait_phase("responding")
    assert responding["activity"]["eventId"] == thinking["activity"]["eventId"]
    gates[2].set()
    tool = wait_phase("tool")
    assert tool["activity"]["toolName"] == "bash"
    assert tool["activity"]["turnStartedAt"] == thinking["activity"]["turnStartedAt"]
    (root / "status-release").touch()
    detail = settle(app, sid)
    assert detail["session"]["state"] == "idle" and detail["session"]["activity"] is None
    assert any(e.get("thinking") == "Native thinking marker." for e in detail["events"])
    assert any(e.get("kind") == "tool" and e.get("status") == "done" for e in detail["events"])
    assert records[-1]["messages"][-1]["role"] == "tool"
