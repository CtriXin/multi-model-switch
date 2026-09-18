"""New connection → selected catalog → actual Pi request; task-private providers only."""
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from mms_web.errors import WebError
from test_mms_web_interactions import local_app, settle
from mms_web.drivers.launch_bridge import probe_mms_pi_seam


@contextmanager
def model_service():
    records = []
    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            records.append({"method": "GET", "path": self.path, "authorization": self.headers.get("Authorization")})
            if self.headers.get("Authorization") == "Bearer invalid-fixture-key":
                self.send_response(401); self.end_headers(); return
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(json.dumps({"data": [{"id": m} for m in ["gpt-5", "gpt-4.1", "gpt-5", "local-extra-model"]]}).encode())
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            records.append({"method": "POST", "path": self.path, "authorization": self.headers.get("Authorization"), "body": body})
            self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
            for delta, finish in [({"role": "assistant", "reasoning_content": "Local connection verified."}, None), ({"content": "通道连接验证完成。"}, None), ({}, "stop")]:
                event = {"id": "chatcmpl-local", "object": "chat.completion.chunk", "model": "gpt-5", "created": 1, "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
                self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode()); self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", records
    finally:
        server.shutdown(); server.server_close(); thread.join()


def connection(app, name, url, key):
    found = app.post(["configuration", "discover"], {"service": {"baseUrl": url, "apiKey": key, "protocol": "openai"}})
    assert found["models"] == ["gpt-4.1", "gpt-5", "local-extra-model"]
    assert found["generationVerified"] is False
    preview = app.post(["configuration", "preview"], {"service": {"name": name, "baseUrl": url, "apiKey": key, "protocol": "openai", "models": ["gpt-5"]}})
    assert key not in json.dumps(preview)
    applied = app.post(["configuration", "apply"], {"previewId": preview["previewId"], "revision": preview["revision"]})
    assert applied["applied"] is True
    return applied


def test_discard_preview_erases_temporary_key_and_is_idempotent(local_app):
    app, _, _ = local_app
    preview = app.post(["configuration", "preview"], {"service": {"name": "Discard", "baseUrl": "http://127.0.0.1:1/v1", "apiKey": "discard-fixture-key", "protocol": "openai", "models": ["gpt-5"]}})
    path = app.catalog._previews_dir / (preview["previewId"] + ".json")
    assert "discard-fixture-key" in path.read_text()
    for _ in range(2):
        assert app.post(["configuration", "discard"], {"previewId": preview["previewId"]}) == {"discarded": True}
    assert not path.exists()
    with pytest.raises(WebError) as exc:
        app.post(["configuration", "apply"], {"previewId": preview["previewId"], "revision": preview["revision"]})
    assert exc.value.code == "PREVIEW_NOT_FOUND"
    with pytest.raises(WebError):
        app.post(["configuration", "discard"], {"previewId": "../config"})


def test_same_model_two_channels_reaches_native_pi_with_selected_effort(local_app):
    if not probe_mms_pi_seam()["available"]:
        pytest.skip("compatible Pi required")
    app, workspace, _ = local_app
    with model_service() as (url_a, records_a), model_service() as (url_b, records_b):
        a = connection(app, "Personal", url_a, "personal-fixture-key")
        b = connection(app, "Company", url_b, "company-fixture-key")
        assert a["presetIds"] == ["web:pi:personal:gpt-5"]
        assert b["presetIds"] == ["web:pi:company:gpt-5"]
        catalog = app.get(["bootstrap"])
        assert {p["providerId"] for p in catalog["presets"] if p["name"] == "gpt-5"} == {"personal", "company"}
        assert all(p["name"] != "local-extra-model" for p in catalog["presets"])
        for preset, level, records, key in [(a["presetIds"][0], "low", records_a, "personal-fixture-key"), (b["presetIds"][0], "high", records_b, "company-fixture-key")]:
            options = app.post(["launch-options"], {"presetId": preset, "workspaceId": workspace["id"]})
            assert level in options["supportedThinkingLevels"]
            detail = app.post(["sessions"], {"requestId": preset, "presetId": preset, "workspaceId": workspace["id"], "prompt": "Reply with the connection marker.", "thinkingLevel": level})
            sid = detail["session"]["id"]
            result = settle(app, sid)
            assert any(e.get("text") == "通道连接验证完成。" for e in result["events"])
            posts = [r for r in records if r["method"] == "POST"]
            assert len(posts) == 1
            assert posts[0]["path"] == "/v1/chat/completions"
            assert posts[0]["authorization"] == "Bearer " + key
            assert posts[0]["body"]["model"] == "gpt-5"
            assert posts[0]["body"]["reasoning_effort"] == level
            app.sessions._get(sid).runtime_checked = 0
            assert app.get(["sessions", sid, "runtime"])["thinkingLevel"] == level
        assert len([r for r in records_a if r["method"] == "POST"]) == 1
        assert len([r for r in records_b if r["method"] == "POST"]) == 1
        assert len(app.get(["sessions"])["sessions"]) == 2


@pytest.mark.parametrize('url', ['https://api.example.com/#fragment', 'https://api.example.com:invalid/v1', 'https://api.example.com/has space'])
def test_manual_configuration_rejects_ambiguous_url_before_storing_key(local_app, url):
    app, _, _ = local_app
    with pytest.raises(WebError) as exc:
        app.post(['configuration', 'preview'], {'service': {'name': 'Bad address', 'baseUrl': url, 'apiKey': 'fixture-key', 'models': ['gpt-5']}})
    assert exc.value.code == 'INVALID_SERVICE_URL'
    assert not list(app.catalog._previews_dir.glob('*.json'))


def test_manual_configuration_validates_and_deduplicates_model_ids(local_app):
    app, _, _ = local_app
    service = {'name':'Manual','baseUrl':'http://127.0.0.1:1/v1','apiKey':'fixture-key'}
    for models in ([None], ['bad\nmodel'], ['x'*201]):
        with pytest.raises(WebError) as exc:
            app.post(['configuration', 'preview'], {'service':{**service, 'models':models}})
        assert exc.value.code == 'INVALID_MODEL_LIST'
    preview = app.post(['configuration', 'preview'], {'service':{**service, 'models':['gpt-5','gpt-5']}})
    record = json.loads((app.catalog._previews_dir / (preview['previewId']+'.json')).read_text())
    assert record['service']['models'] == ['gpt-5']


def test_saved_write_is_reported_if_catalog_readback_fails(local_app, monkeypatch):
    app, _, _ = local_app
    preview = app.post(['configuration', 'preview'], {'service': {'name': 'Readback', 'baseUrl':'http://127.0.0.1:1/v1','apiKey':'fixture-key','models':['gpt-5']}})
    def failed_readback():
        raise WebError('INVALID_BUNDLE', '模型目录需要更新。')
    monkeypatch.setattr(app.catalog, 'snapshot', failed_readback)
    result = app.post(['configuration', 'apply'], {'previewId':preview['previewId'],'revision':preview['revision']})
    assert result['applied'] and result['presetIds'] == []
    record = json.loads((app.catalog._previews_dir / (preview['previewId']+'.json')).read_text())
    assert record['consumed'] and not record['service']['apiKey']
