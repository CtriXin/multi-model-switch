"""Real Pi requests against a task-local provider; workspace and UI protocol checks."""
import base64
import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from mms_web.server import WebApplication
from mms_web.errors import WebError
from mms_web.drivers.launch_bridge import probe_mms_pi_seam

PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAoAAAAKCAIAAAACUFjqAAAAEklEQVR4nGPQzfXCgxhGpbEhAOWtWRHbuRuwAAAAAElFTkSuQmCC'


@pytest.fixture
def local_app(tmp_path, monkeypatch):
    for key in ("HOME", "MMS_REAL_HOME", "REAL_HOME", "ORIGINAL_HOME"):
        monkeypatch.setenv(key, str(tmp_path / "home"))
    app = WebApplication(state_root=tmp_path / "state")
    folder = tmp_path / "project"
    folder.mkdir()
    (folder / "notes.md").write_text("# Reference\nworkspace marker")
    workspace = app.post(["workspaces"], {"path": str(folder)})
    yield app, workspace, folder
    app.close()


def test_workspace_reads_attachments_and_boundaries(local_app, tmp_path):
    app, workspace, root = local_app
    wid = workspace["id"]
    (root / "sub").mkdir()
    (root / ".env").write_text("private")
    (root / "credentials.sh").write_text("private")
    (tmp_path / "outside.txt").write_text("private outside")
    (root / "link").symlink_to(tmp_path / "outside.txt")
    tree = app.post(["files", "tree"], {"workspaceId": wid})
    assert {e["name"] for e in tree["entries"]} == {"sub", "notes.md"}
    for path in ("../outside.txt", ".env", "credentials.sh", "link", str(root / "notes.md")):
        with pytest.raises(WebError):
            app.post(["files", "read"], {"workspaceId": wid, "path": path})
    image = app.post(["attachments"], {"name": "image.png", "data": PNG})
    assert app.get(["attachments", image["id"]])["dataUrl"].startswith("data:image/png;base64,")
    assert app.sessions.files.root.joinpath(image["id"], "content").stat().st_mode & 0o777 == 0o600
    with pytest.raises(WebError):
        app.post(["attachments"], {"name": "binary.exe", "data": base64.b64encode(b"MZ\0\0").decode()})
    with pytest.raises(WebError):
        app.get(["attachments", "../../outside.txt"])


def test_git_diff_in_subdirectory_does_not_expose_siblings(local_app):
    app, workspace, root = local_app
    # Git initialization is confined to this test's fresh temporary directory.
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    sub = root / "sub"; sub.mkdir()
    (sub / "new.md").write_text("new content\n")
    (root / "sibling.txt").write_text("not in selected workspace")
    ws = app.post(["workspaces"], {"path": str(sub)})
    changes = app.post(["files", "git"], {"workspaceId": ws["id"]})
    assert changes["changes"] == [{"path": "new.md", "status": "??"}]
    assert "+new content" in app.post(["files", "git"], {"workspaceId": ws["id"], "path": "new.md"})["diff"]


@pytest.fixture
def native(local_app):
    if not probe_mms_pi_seam()["available"]:
        pytest.skip("compatible Pi required")
    app, workspace, root = local_app
    records = []
    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            records.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            records[-1]["_testAuthorization"] = self.headers.get("Authorization")
            self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
            last = records[-1]["messages"][-1]
            if last["role"] == "user" and "slow-queue-marker" in json.dumps(last):
                time.sleep(1.5)
            if last["role"] == "user" and "write-tool-marker" in json.dumps(last):
                chunks = [({"role":"assistant", "tool_calls":[{"index":0,"id":"call-write-" + str(len(records)),"type":"function","function":{"name":"write","arguments":json.dumps({"path":"native-plan-probe.txt","content":"written after execute enabled"})}}]},None), ({},"tool_calls")]
            elif last["role"] == "user" and "read-image-marker" in json.dumps(last):
                chunks = [({"role":"assistant", "tool_calls":[{"index":0,"id":"call-read-image","type":"function","function":{"name":"read","arguments":json.dumps({"path":"pixel.png"})}}]},None), ({},"tool_calls")]
            else:
                chunks = [({"role": "assistant", "reasoning_content": "Fixture thinking marker."}, None), ({"content": "Native interaction works."}, None), ({}, "stop")]
            for delta, finish in chunks:
                event = {"id":"chatcmpl-test", "object":"chat.completion.chunk", "created":1, "model":"gpt-5", "choices":[{"index":0,"delta":delta,"finish_reason":finish}]}
                if finish:
                    event["usage"] = {"prompt_tokens":42,"completion_tokens":9,"total_tokens":51,"prompt_tokens_details":{"cached_tokens":12}}
                self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode()); self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
    server = ThreadingHTTPServer(("127.0.0.1",0),Provider)
    thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    preview = app.post(["configuration", "preview"], {"service":{"name":"Local vision", "baseUrl":f"http://127.0.0.1:{server.server_port}/v1", "apiKey":"test-owned-key", "models":["gpt-5"], "protocol":"openai"}})
    app.post(["configuration", "apply"], {"previewId":preview["previewId"],"revision":preview["revision"]})
    yield app, workspace, records
    server.shutdown(); server.server_close(); thread.join()


def settle(app, sid):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        detail = app.get(["sessions",sid])
        if detail["session"]["state"] in {"idle","error","completed"}:
            return detail
        time.sleep(.05)
    raise AssertionError("Pi did not settle")


def test_native_images_thinking_stats_controls_fork_archive(native):
    app, workspace, records = native
    image = app.post(["attachments"], {"name":"pixel.png", "data":PNG})
    text = app.post(["attachments"], {"name":"memo.txt", "data":base64.b64encode(b"attachment text marker").decode()})
    detail = app.post(["sessions"], {"requestId":"image-start","workspaceId":workspace["id"],"presetId":"web:pi:local-vision:gpt-5","prompt":"image-history-marker", "attachments":[image["id"],text["id"]],"references":["notes.md"]})
    sid = detail["session"]["id"]
    detail = settle(app,sid)
    sent = json.dumps(records[-1])
    assert "data:image/png;base64," in sent and "attachment text marker" in sent and "notes.md" in sent
    assert any(e.get("thinking") == "Fixture thinking marker." for e in detail["events"])
    app.sessions._get(sid).runtime_checked = 0
    runtime = app.get(["sessions",sid,"runtime"])
    assert runtime["stats"]["tokens"]["output"] == 9
    assert runtime["stats"]["tokens"]["cacheRead"] == 12
    app.post(["sessions",sid,"control"], {"requestId":"thinking-high","action":"thinking","value":"high"})
    assert app.get(["sessions",sid,"runtime"])["thinkingLevel"] == "high"
    app.post(["sessions",sid,"manage"], {"title":"Renamed"})
    assistant = next(e for e in detail["events"] if e["kind"] == "assistant" and e["text"])
    branch = app.post(["sessions",sid,"fork"], {"requestId":"branch-1","eventId":assistant["id"]})
    bid = branch["session"]["id"]
    assert bid != sid
    app.post(["sessions",bid,"messages"], {"requestId":"branch-send","text":"branch only"})
    settle(app,bid)
    assert "image-history-marker" in json.dumps(records[-1]["messages"])
    assert not any(e.get("text") == "branch only" for e in app.get(["sessions",sid])["events"])
    assert app.post(["sessions",sid,"fork"], {"requestId":"branch-1","eventId":assistant["id"]})["session"]["id"] == bid
    app.post(["sessions",sid,"manage"], {"archived":True})
    assert next(s for s in app.bootstrap()["sessions"] if s["id"] == sid)["archived"]
    app.post(["sessions",sid,"manage"], {"archived":False})
    assert app.get(["sessions",sid])["session"]["title"] == "Renamed"


def test_native_readonly_plan_blocks_write_then_execute_restores_tools(native):
    app, workspace, records = native
    root = Path(workspace["path"])
    detail = app.post(["sessions"], {"requestId":"plan-start","workspaceId":workspace["id"],"presetId":"web:pi:local-vision:gpt-5","prompt":"write-tool-marker", "planMode":True})
    sid = detail["session"]["id"]
    detail = settle(app,sid)
    assert app.get(["sessions",sid,"runtime"])["planning"] is True
    assert not (root / "native-plan-probe.txt").exists()
    assert any(e["kind"] == "tool" and e.get("status") == "error" and "只读规划" in e["text"] for e in detail["events"])
    calls = len(records)
    app.post(["sessions",sid,"control"], {"requestId":"plan-off","action":"plan","value":False})
    assert len(records) == calls, "UI mode command must never call the model"
    app.post(["sessions",sid,"messages"], {"requestId":"execute-write","text":"write-tool-marker"})
    settle(app,sid)
    assert (root / "native-plan-probe.txt").read_text() == "written after execute enabled"
    assert app.get(["sessions",sid,"runtime"])["planning"] is False
    (root / "pixel.png").write_bytes(base64.b64decode(PNG))
    app.post(["sessions",sid,"messages"], {"requestId":"tool-image","text":"read-image-marker"})
    detail = settle(app,sid)
    media = [a for e in detail["events"] if e["kind"] == "tool" for a in e.get("attachments", [])]
    assert media and app.get(["attachments",media[0]["id"]])["dataUrl"].startswith("data:image/png;base64,")


def test_native_queue_controls_and_restored_planning(native):
    app, workspace, records = native
    detail = app.post(["sessions"], {"requestId":"queue-start","workspaceId":workspace["id"],"presetId":"web:pi:local-vision:gpt-5","prompt":"slow-queue-marker"})
    sid = detail["session"]["id"]
    app.post(["sessions",sid,"messages"], {"requestId":"queue-message","text":"queued-only-marker"})
    app.sessions._get(sid).runtime_checked = 0
    assert app.get(["sessions",sid,"runtime"])["pendingMessageCount"] == 1
    with pytest.raises(WebError) as error:
        app.post(["sessions",sid,"control"], {"requestId":"busy-plan","action":"plan","value":True})
    assert error.value.code == "SESSION_BUSY"
    app.post(["sessions",sid,"control"], {"requestId":"queue-clear","action":"clearQueue"})
    settle(app,sid)
    assert not any("queued-only-marker" in json.dumps(request["messages"]) for request in records)
    assert next(e for e in app.get(["sessions",sid])["events"] if e.get("text") == "queued-only-marker")["status"] == "cancelled"
    app.post(["sessions",sid,"control"], {"requestId":"retry-on","action":"autoRetry","value":True})
    assert app.get(["sessions",sid,"runtime"])["autoRetryEnabled"] is True
    app.post(["sessions",sid,"control"], {"requestId":"plan-before-restart","action":"plan","value":True})
    app.sessions._get(sid).driver.close()
    app.post(["sessions",sid,"messages"], {"requestId":"restored-plan","text":"write-tool-marker"})
    settle(app,sid)
    assert app.get(["sessions",sid,"runtime"])["planning"] is True
    assert not (Path(workspace["path"]) / "native-plan-probe.txt").exists()


def test_native_queued_prompt_begins_after_previous_answer(native):
    app, workspace, records = native
    first = app.post(["sessions"], {"requestId":"queue-order-start", "workspaceId":workspace["id"], "presetId":"web:pi:local-vision:gpt-5", "prompt":"slow-queue-marker"})
    sid = first["session"]["id"]
    app.post(["sessions",sid,"messages"], {"requestId":"queue-order-next", "text":"second-execution-marker"})
    detail = settle(app,sid)
    assert len(records) == 2
    events = detail["events"]
    index = next(i for i,e in enumerate(events) if e.get("text") == "second-execution-marker")
    assert events[index].get("status") == "delivered"
    assert any(e["kind"] == "assistant" and e["text"] for e in events[:index])
    assert any(e["kind"] == "assistant" and e["text"] for e in events[index+1:])
