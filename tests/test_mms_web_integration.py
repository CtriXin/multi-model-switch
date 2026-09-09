"""Local HTTP provider + actual installed Pi + original MMS launcher acceptance.

No network provider, host credentials, host config writes, or global auth.
"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from mms_web.drivers.launch_bridge import probe_mms_pi_seam
from mms_web.runtime import snapshot_config
from mms_web.server import WebApplication


def test_first_run_is_configurable_without_touching_real_mms(tmp_path, monkeypatch):
    monkeypatch.setenv("MMS_REAL_HOME", str(tmp_path / "home"))
    app = WebApplication(state_root=tmp_path / "state")
    assert app.bootstrap()["capabilities"]["configure"]
    preview = app.post(["configuration", "preview"], {"service": {
        "name": "My service", "baseUrl": "http://127.0.0.1:12345/v1",
        "apiKey": "test-owned-key", "models": ["test-model"], "protocol": "openai"}})
    app.post(["configuration", "apply"], {"previewId": preview["previewId"], "revision": preview["revision"]})
    model = app.bootstrap()["models"][0]
    assert model["available"] and not model["verified"]
    assert "pi" in model["harnesses"]
    result = app.catalog.resolve_launch("web:pi:my-service:test-model", "default")
    assert result["runtime"]["api_key"] == "test-owned-key"
    assert result["runtime"]["protocols"] == ["openai_chat_completions"]
    assert not (tmp_path / "home/.config/mms").exists()
    assert not (tmp_path / "home/.config/mms-next").exists()
    app.close()


def test_snapshot_excludes_auth_and_history_and_preserves_source(tmp_path, monkeypatch):
    monkeypatch.setenv("MMS_REAL_HOME", str(tmp_path / "home"))
    source = tmp_path / "source"
    source.mkdir()
    (source / "config.toml").write_text("[provider]\ndefault = 'p'\n")
    (source / "credentials.sh").write_text("export MMS_PROVIDER_P_API_KEY='test-key'\n")
    (source / "accounts").mkdir()
    (source / "accounts/auth.json").write_text("global-auth-must-not-copy")
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in source.iterdir() if p.is_file()}
    a = snapshot_config(source, tmp_path / "state")
    b = snapshot_config(source, tmp_path / "state")
    assert a != b
    assert not (a / "accounts").exists()
    assert (a / "credentials.sh").stat().st_mode & 0o777 == 0o600
    assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in source.iterdir() if p.is_file()}


def test_real_pi_launch_from_web_setup_and_native_resume(tmp_path, monkeypatch):
    if not probe_mms_pi_seam()["available"]:
        pytest.skip("A compatible local Pi installation is required")
    monkeypatch.setenv("MMS_REAL_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("REAL_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ORIGINAL_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    records = []

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            records.append({"path": self.path, "auth": self.headers.get("Authorization"), "payload": payload})
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for delta, finish in [({"role": "assistant", "content": "Local connection works."}, None), ({}, "stop")]:
                event = {"id": "chatcmpl-local", "object": "chat.completion.chunk", "created": 1,
                         "model": "test-model", "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
                self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode())
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")

    provider = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    thread = threading.Thread(target=provider.serve_forever, daemon=True)
    thread.start()
    app = WebApplication(state_root=tmp_path / "state")
    folder = tmp_path / "project"
    folder.mkdir()
    try:
        workspace = app.post(["workspaces"], {"path": str(folder)})
        preview = app.post(["configuration", "preview"], {"service": {
            "name": "Local fixture", "baseUrl": f"http://127.0.0.1:{provider.server_port}/v1",
            "apiKey": "test-owned-key", "models": ["test-model"], "protocol": "openai"}})
        app.post(["configuration", "apply"], {"previewId": preview["previewId"], "revision": preview["revision"]})
        result = app.post(["sessions"], {"requestId": "native-start", "workspaceId": workspace["id"],
            "presetId": "web:pi:local-fixture:test-model", "prompt": "native-history-marker"})
        sid = result["session"]["id"]

        def settled():
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                detail = app.get(["sessions", sid])
                if detail["session"]["state"] in {"idle", "error", "completed"}:
                    return detail
                time.sleep(.05)
            raise AssertionError("native Pi did not settle")

        detail = settled()
        assert any(e["text"] == "Local connection works." for e in detail["events"])
        assert records[0]["path"] == "/v1/chat/completions"
        assert records[0]["auth"] == "Bearer test-owned-key"
        assert records[0]["payload"]["model"] == "test-model"
        app.close()
        app = WebApplication(state_root=tmp_path / "state")
        assert app.get(["sessions", sid])["session"]["capabilities"]["send"]
        app.post(["sessions", sid, "messages"], {"requestId": "native-resume", "text": "second turn"})
        detail = settled()
        assert len([e for e in detail["events"] if e["kind"] == "assistant" and e["text"]]) == 2
        assert "native-history-marker" in json.dumps(records[-1]["payload"]["messages"])
        assert not (tmp_path / "home/.config/mms").exists()
    finally:
        app.close()
        provider.shutdown()
        provider.server_close()
        thread.join()


def test_artifacts_only_expose_successful_workspace_outputs(tmp_path):
    from mms_web.artifacts import collect_artifacts
    workspace = tmp_path / "project"
    workspace.mkdir()
    (workspace / "report.md").write_text("# Actual result")
    (tmp_path / "outside.txt").write_text("private outside")
    (workspace / "link.txt").symlink_to(tmp_path / "outside.txt")
    (workspace / ".env").write_text("TOKEN=private")
    events = [{"kind": "tool", "title": "write", "status": "done", "arguments": {"path": p}}
              for p in ("report.md", "../outside.txt", "link.txt", ".env")]
    result = collect_artifacts({"cwd": str(workspace)}, events)
    assert len(result) == 1 and result[0]["content"] == "# Actual result"
    events[0]["status"] = "error"
    assert collect_artifacts({"cwd": str(workspace)}, events) == []
