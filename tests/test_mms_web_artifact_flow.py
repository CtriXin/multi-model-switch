"""Real Pi generates, revises and restores local output versions."""
import base64
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shlex
import threading

import pytest

from mms_web.errors import WebError
from mms_web.server import WebApplication
from mms_web.drivers.launch_bridge import probe_mms_pi_seam
from test_mms_web_configuration_flow import connection
from test_mms_web_interactions import PNG, local_app, settle


@contextmanager
def artifact_service():
    records = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(json.dumps({"data": [{"id": m} for m in ("gpt-4.1", "gpt-5", "local-extra-model")]}).encode())

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            records.append(body)
            last = body["messages"][-1]
            text = json.dumps(last, ensure_ascii=False)
            tool = None
            if last["role"] == "user":
                if "artifact-first" in text:
                    tool = ("write", {"path": "result.md", "content": "# Report\n\nOriginal paragraph.\n\nKeep this paragraph.\n"})
                elif "artifact-revise" in text:
                    tool = ("edit", {"path": "result.md", "oldText": "Original paragraph.", "newText": "Revised paragraph."})
                elif "artifact-shell" in text:
                    script = ("from pathlib import Path; import base64; "
                              "Path('summary.csv').write_text('name,value\\nAlpha,42\\nBeta,7\\n'); "
                              "Path('page.html').write_text('<style>body{font-family:system-ui;padding:32px;color:#303048}h1{color:#5850ca}</style><h1>Local result</h1><p>HTML preview ready.</p>'); "
                              f"Path('image.png').write_bytes(base64.b64decode({PNG!r}))")
                    tool = ("bash", {"command": "python3 -c " + shlex.quote(script)})
            if tool:
                chunks = [({"role": "assistant", "tool_calls": [{"index": 0, "id": "artifact-call-" + str(len(records)), "type": "function",
                    "function": {"name": tool[0], "arguments": json.dumps(tool[1])}}]}, None), ({}, "tool_calls")]
            else:
                chunks = [({"role": "assistant", "content": "成果已写入工作文件夹，可以打开查看。"}, None), ({}, "stop")]
            self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
            for delta, finish in chunks:
                event = {"id": "chatcmpl-artifacts", "object": "chat.completion.chunk", "created": 1, "model": "gpt-5",
                         "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
                self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode()); self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", records
    finally:
        server.shutdown(); server.server_close(); thread.join()


@pytest.mark.skipif(not probe_mms_pi_seam()["available"], reason="compatible Pi required")
def test_native_output_selection_revision_restart_and_command_outputs(local_app):
    app, workspace, root = local_app
    with artifact_service() as (url, records):
        connection(app, "Artifact fixture", url, "artifact-fixture-key")
        detail = app.post(["sessions"], {"requestId": "artifact-start", "workspaceId": workspace["id"],
            "presetId": "web:pi:artifact-fixture:gpt-5", "prompt": "artifact-first"})
        sid = detail["session"]["id"]
        detail = settle(app, sid)
        artifact = detail["artifacts"][0]
        assert artifact["revision"] == 1 and artifact["source"] == "tool"
        assert "content" not in artifact
        preview = app.post(["sessions", sid, "artifacts"], {"id": artifact["id"]})
        assert "Original paragraph." in preview["content"]
        selection = {"artifactId": artifact["id"], "revision": 1, "sha256": preview["sha256"], "quote": "Original paragraph."}
        app.post(["sessions", sid, "messages"], {"requestId": "artifact-edit", "text": "artifact-revise: 修改这个段落。", "fileSelections": [selection]})
        detail = settle(app, sid)
        assert detail["artifacts"][0]["revision"] == 2
        assert (root / "result.md").read_text() == "# Report\n\nRevised paragraph.\n\nKeep this paragraph.\n"
        assert any(selection["sha256"] in json.dumps(r, ensure_ascii=False) for r in records)
        assert any(e.get("fileSelections", [{}])[0].get("quote") == "Original paragraph." for e in detail["events"] if e.get("fileSelections"))
        state = app.catalog._state_root
        app.close()
        restored = WebApplication(state_root=state)
        try:
            diff = restored.post(["sessions", sid, "artifacts"], {"id": artifact["id"], "revision": 2, "compare": 1})
            assert "-Original paragraph." in diff["diff"] and "+Revised paragraph." in diff["diff"]
            calls = len(records)
            with pytest.raises(WebError) as error:
                restored.post(["sessions", sid, "messages"], {"requestId": "stale-edit", "text": "Do not send stale selection", "fileSelections": [selection]})
            assert error.value.code == "FILE_CHANGED" and len(records) == calls
            restored.post(["sessions", sid, "messages"], {"requestId": "shell-files", "text": "artifact-shell"})
            detail = settle(restored, sid)
            outputs = {a["path"]: a for a in detail["artifacts"]}
            assert {"result.md", "summary.csv", "page.html", "image.png"} == set(outputs)
            assert all(outputs[p]["source"] == "observed" for p in ("summary.csv", "page.html", "image.png"))
            csv = restored.post(["sessions", sid, "artifacts"], {"id": outputs["summary.csv"]["id"]})
            assert csv["rows"] == [["name", "value"], ["Alpha", "42"], ["Beta", "7"]]
            image = restored.post(["sessions", sid, "artifacts"], {"id": outputs["image.png"]["id"]})
            assert base64.b64decode(image["downloadData"]) == base64.b64decode(PNG)
        finally:
            restored.close()
