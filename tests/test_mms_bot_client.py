from __future__ import annotations

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TOKEN = "private-worker-token-123"


class WorkerHandler(BaseHTTPRequestHandler):
    requests: list[dict] = []
    status_code = 200
    response: dict = {"ok": True, "taskId": "task-child"}

    def log_message(self, *_args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length))
        type(self).requests.append(
            {"body": body, "authorization": self.headers.get("Authorization")}
        )
        encoded = json.dumps(self.response, ensure_ascii=False).encode()
        self.send_response(type(self).status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


@pytest.fixture
def worker(tmp_path):
    WorkerHandler.requests = []
    WorkerHandler.status_code = 200
    WorkerHandler.response = {"ok": True, "taskId": "task-child"}
    server = ThreadingHTTPServer(("127.0.0.1", 0), WorkerHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    context = tmp_path / "worker-context.json"
    context.write_text(
        json.dumps(
            {
                "url": f"http://127.0.0.1:{server.server_port}/api/v1/bot-worker",
                "token": TOKEN,
                "taskId": "task-parent",
                "botId": "bot-parent",
            }
        ),
        encoding="utf-8",
    )
    try:
        yield context
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def run_client(context: Path, *args: str):
    return subprocess.run(
        [sys.executable, "-m", "mms_web.bot_client", "--context", str(context), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_dispatch_posts_bounded_payload_and_bearer(worker):
    result = run_client(worker, "dispatch", "bot-child", "检查", "并", "回报", "--request-id", "retry-1")
    assert result.returncode == 0, result.stderr
    request = WorkerHandler.requests[-1]
    assert request["authorization"] == f"Bearer {TOKEN}"
    assert request["body"] == {
        "botId": "bot-child",
        "prompt": "检查 并 回报",
        "parentTaskId": "task-parent",
        "senderBotId": "bot-parent",
        "action": "dispatch",
        "requestId": "retry-1",
    }
    assert json.loads(result.stdout) == {"ok": True, "taskId": "task-child"}
    assert TOKEN not in result.stdout and TOKEN not in result.stderr


@pytest.mark.parametrize(
    ("command", "expected_action", "expected_payload"),
    [
        ("list", "list", {"botId": "bot-parent", "taskId": "task-parent"}),
        ("message bot-child hello there", "message", {
            "recipientBotId": "bot-child", "content": "hello there",
            "taskId": "task-parent", "senderBotId": "bot-parent",
        }),
        ("screenshot --url http://example.test", "screenshot", {
            "taskId": "task-parent", "botId": "bot-parent", "url": "http://example.test",
        }),
        ("browser goto https://example.test", "browser", {
            "taskId": "task-parent", "botId": "bot-parent", "operation": "goto", "target": "https://example.test",
        }),
        ("browser fill loc=css:#name Xin Song", "browser", {
            "taskId": "task-parent", "botId": "bot-parent", "operation": "fill", "target": "loc=css:#name", "value": "Xin Song",
        }),
        ("status", "status", {"taskId": "task-parent", "includeDescendants": True}),
        ("status task-child", "status", {"taskId": "task-child", "includeDescendants": True}),
        ("complete done", "complete", {"taskId": "task-parent", "result": "done"}),
        ("wait child is running", "wait", {"taskId": "task-parent", "reason": "child is running"}),
        ("fail no response", "fail", {"taskId": "task-parent", "error": "no response"}),
    ],
)
def test_commands_map_to_worker_actions(worker, command, expected_action, expected_payload):
    result = run_client(worker, *command.split())
    assert result.returncode == 0, result.stderr
    body = WorkerHandler.requests[-1]["body"]
    assert body["action"] == expected_action
    assert body["requestId"]
    assert {key: value for key, value in body.items() if key not in {"action", "requestId"}} == expected_payload


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8123/api/v1/bot-worker",
        "https://127.0.0.1:8123/api/v1/bot-worker",
        "http://127.0.0.1:8123/api/v1/bot-worker?x=1",
        "http://127.0.0.1:8123/api/v1/bot-worker/extra",
        "http://user:pass@127.0.0.1:8123/api/v1/bot-worker",
    ],
)
def test_context_rejects_non_exact_worker_url(tmp_path, url):
    context = tmp_path / "bad.json"
    context.write_text(
        json.dumps({"url": url, "token": TOKEN, "taskId": "t", "botId": "b"}),
        encoding="utf-8",
    )
    result = run_client(context, "list")
    assert result.returncode == 1
    assert "url" in result.stderr
    assert TOKEN not in result.stdout and TOKEN not in result.stderr


def test_worker_error_is_secret_free(worker):
    WorkerHandler.status_code = 403
    WorkerHandler.response = {
        "error": {"code": "denied", "message": f"bad token {TOKEN}"}
    }
    result = run_client(worker, "list")
    assert result.returncode == 1
    assert "HTTP 403" in result.stderr
    assert TOKEN not in result.stdout and TOKEN not in result.stderr


def test_request_id_can_be_reused(worker):
    first = run_client(worker, "list", "--request-id", "same-request")
    second = run_client(worker, "list", "--request-id", "same-request")
    assert first.returncode == second.returncode == 0
    assert WorkerHandler.requests[-2]["body"]["requestId"] == "same-request"
    assert WorkerHandler.requests[-1]["body"]["requestId"] == "same-request"
