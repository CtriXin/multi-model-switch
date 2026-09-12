from __future__ import annotations

import hashlib
import http.client
import json
import subprocess
import sys
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from mms_web.bot_executor import PiBotExecutor
from mms_web.bots import BotRuntime
from mms_web.server import WebApplication, create_server


ROOT = Path(__file__).resolve().parents[1]


class FakeExecutor:
    def available(self):
        return True

    def validate(self, bot):
        return {"model": "fake", "capabilities": ["dispatch"]}

    def start(self, task, bot, context_path):
        return {
            "sessionId": f"session-{task['id']}",
            "baseline": 0,
            "artifactBaseline": {},
            "model": "fake",
        }

    def snapshot(self, task):
        return {"state": "running", "events": [], "artifacts": [], "alive": True}

    def cancel(self, task):
        return None

    def artifact(self, session_id, artifact_id, revision):
        return {"content": "", "mimeType": "text/plain"}


@pytest.fixture
def transport(tmp_path):
    public = tmp_path / "public"
    public.mkdir()
    (public / "index.html").write_text("<h1>test</h1>", encoding="utf-8")

    # Keep the real HTTP handler and create_server path, while preventing any
    # catalog/session adapter from reading user configuration or launching Pi.
    with patch("mms_web.server._adapter", return_value=None):
        app = WebApplication(state_root=tmp_path / "state")
    app.bots.close()
    app.bots = BotRuntime(state_root=tmp_path / "state", executor=FakeExecutor())
    server = create_server(app, public, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def request(method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        encoded = None if body is None else json.dumps(body).encode()
        request_headers = dict(headers or {})
        if encoded is not None:
            request_headers.setdefault("Content-Type", "application/json")
        connection.request(method, path, body=encoded, headers=request_headers)
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    try:
        yield app, server, request
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        app.close()


def make_task(app, tmp_path, *, prompt="任务"):
    bot = app.bots.create_bot(
        {
            "name": "test-bot",
            "description": "",
            "systemPrompt": "",
            "workspaceId": "ws-test",
            "presetId": "pi:fake",
            "wakeEnabled": False,
        }
    )
    task = app.bots.create_task(
        {"botId": bot["id"], "prompt": prompt, "wake": False}
    )
    app.bots._tasks[task["id"]]["token"] = f"token-{task['id']}"
    app.bots._persist()
    return bot, task


def run_client(url: str, token: str, task_id: str, bot_id: str, *args: str):
    context = Path("/tmp") / f"mms-bot-transport-{task_id}.json"
    context.write_text(
        json.dumps({"url": url, "token": token, "taskId": task_id, "botId": bot_id}),
        encoding="utf-8",
    )
    try:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "mms_web.bot_client",
                "--context",
                str(context),
                *args,
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    finally:
        context.unlink(missing_ok=True)


def test_worker_token_binds_mutation_to_authorized_task(transport, tmp_path):
    app, server, request = transport
    _, first = make_task(app, tmp_path, prompt="first")
    _, second = make_task(app, tmp_path, prompt="second")
    first_token = app.bots._tasks[first["id"]]["token"]

    status, _, body = request(
        "POST",
        "/api/v1/bot-worker",
        {
            "action": "complete",
            "requestId": "complete-cross-task",
            "taskId": second["id"],
            "text": "only first may change",
        },
        {"Authorization": f"Bearer {first_token}"},
    )

    assert status == 200, body
    assert app.bots._tasks[first["id"]]["declaredResult"] == "only first may change"
    assert app.bots._tasks[second["id"]].get("declaredResult") is None


def test_ordinary_post_requires_csrf(transport):
    app, _, request = transport
    status, _, body = request(
        "POST",
        "/api/v1/bots",
        {"name": "blocked"},
    )
    assert status == 403
    assert json.loads(body)["error"]["code"] == "INVALID_CSRF"


def test_worker_origin_is_rejected_even_with_valid_token(transport, tmp_path):
    app, server, request = transport
    bot, task = make_task(app, tmp_path)
    token = app.bots._tasks[task["id"]]["token"]
    status, _, body = request(
        "POST",
        "/api/v1/bot-worker",
        {"action": "list", "requestId": "origin-check"},
        {
            "Authorization": f"Bearer {token}",
            "Origin": f"http://127.0.0.1:{server.server_port}",
        },
    )
    assert status == 403
    assert json.loads(body)["error"]["code"] == "INVALID_WORKER"


def test_get_artifact_returns_real_bytes_and_non_image_as_text(transport, tmp_path):
    app, _, request = transport
    _, task = make_task(app, tmp_path)
    artifact_root = tmp_path / "state" / "bots" / "screenshots"
    artifact_root.mkdir(parents=True, exist_ok=True)

    image = b"\x89PNG\r\nreal-test-bytes"
    image_path = artifact_root / "capture.png"
    image_path.write_bytes(image)
    html = b"<script>alert('kept as text')</script>"
    html_path = artifact_root / "report.html"
    html_path.write_bytes(html)

    for artifact_id, name, kind, path, content in (
        ("a-image", "capture.png", "screenshot", image_path, image),
        ("a-html", "report.html", "file", html_path, html),
    ):
        app.bots._artifacts[task["id"]].append(
            {
                "id": artifact_id,
                "name": name,
                "kind": kind,
                "path": str(path),
                "sha256": hashlib.sha256(content).hexdigest(),
                "size": len(content),
            }
        )
    app.bots._persist()

    image_status, image_headers, image_body = request(
        "GET", f"/api/v1/tasks/{task['id']}/artifacts/a-image/content"
    )
    html_status, html_headers, html_body = request(
        "GET", f"/api/v1/tasks/{task['id']}/artifacts/a-html/content"
    )
    preview_status, preview_headers, preview_body = request(
        "GET", f"/api/v1/tasks/{task['id']}/artifacts/a-html/preview"
    )
    assert image_status == 200
    assert image_body == image
    assert image_headers["Content-Type"].startswith("image/png")
    assert html_status == 200
    assert html_body == html
    assert html_headers["Content-Type"].startswith("text/plain")
    assert preview_status == 200
    assert preview_headers["Content-Type"].startswith("text/html")
    assert b"<script" not in preview_body
    assert b"<!doctype html>" in preview_body


@pytest.mark.parametrize(
    ("command", "field", "value"),
    [
        ("complete done from client", "declaredResult", "done from client"),
        ("fail failure from client", "declaredError", "failure from client"),
    ],
)
def test_client_payload_matches_worker_runtime_contract(
    transport, tmp_path, command, field, value
):
    app, server, _ = transport
    bot, task = make_task(app, tmp_path)
    token = app.bots._tasks[task["id"]]["token"]
    result = run_client(
        f"http://127.0.0.1:{server.server_port}/api/v1/bot-worker",
        token,
        task["id"],
        bot["id"],
        *command.split(),
    )
    assert result.returncode == 0, result.stderr
    assert app.bots._tasks[task["id"]][field] == value


class _Catalog:
    def snapshot(self):
        return {"presets": [{"id": "pi:test", "name": "test-model", "channel": "test", "harness": "pi", "available": True}],
                "workspaces": [{"id": "ws-test"}]}


class _Sessions:
    def __init__(self):
        self.launched = []

    def capabilities(self):
        return {"launch": True}

    def launch(self, payload):
        self.launched.append(payload)
        return {"session": {"id": "session-1", "state": "idle", "modelName": "test-model"}}

    def get_session(self, session_id):
        return {"session": {"id": session_id, "state": "idle"}, "events": [], "artifacts": []}

    def diagnostics(self, session_id):
        return {}


def test_bot_prompt_asks_for_one_line_peer_reports_without_paths_or_hashes(tmp_path):
    sessions = _Sessions()
    executor = PiBotExecutor(sessions, _Catalog())
    bot = {"id": "bot_1", "name": "worker", "description": "", "systemPrompt": "",
           "presetId": "pi:test", "workspaceId": "ws-test"}
    task = {"id": "task_1", "prompt": "写一个文件", "launchRequestId": "launch-1", "collaborationRequested": False}
    executor.start(task, bot, tmp_path / "context.json")
    prompt = sessions.launched[0]["prompt"]
    assert "向其他 Bot 回报时只写一句结论" in prompt
    assert "不在正文贴路径或哈希" in prompt
