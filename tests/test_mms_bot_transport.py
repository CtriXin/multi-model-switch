from __future__ import annotations

import hashlib
import http.client
import json
import re
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

    def launch_bot(self, payload, bot_id):
        payload = dict(payload)
        payload["owner"] = "bot"
        payload["botId"] = bot_id
        return self.launch(payload)

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
    assert sessions.launched[0]["owner"] == "bot"
    assert sessions.launched[0]["botId"] == bot["id"]
    assert "向其他 Bot 回报时只写一句结论" in prompt
    assert "不在正文贴路径或哈希" in prompt


def test_wait_route_answers_and_dismisses(transport, tmp_path):
    app, server, request = transport
    _, task = make_task(app, tmp_path, prompt="整理报告")
    app.bots.worker(task["id"], {"action": "wait", "question": "要先做哪一项？", "options": ["A", "B"]})
    app.bots._observe(app.bots._tasks[task["id"]], {"state": "idle", "alive": False, "events": [], "artifacts": []})
    assert app.bots.get_task(task["id"])["status"] == "waiting"

    status, _, body = request("POST", f"/api/v1/tasks/{task['id']}/wait",
                              {"action": "answer", "text": "先做 A"}, {"X-MMS-CSRF": app.csrf_token})
    assert status == 200, body
    assert json.loads(body)["status"] == "queued"
    assert app.bots.get_task(task["id"])["waitAnsweredAt"]

    _, second = make_task(app, tmp_path, prompt="等待确认")
    app.bots.worker(second["id"], {"action": "wait", "question": "要现在发布吗？"})
    app.bots._observe(app.bots._tasks[second["id"]], {"state": "idle", "alive": False, "events": [], "artifacts": []})
    status, _, body = request("POST", f"/api/v1/tasks/{second['id']}/wait",
                              {"action": "dismiss"}, {"X-MMS-CSRF": app.csrf_token})
    assert status == 200, body
    closed = json.loads(body)
    assert closed["status"] == "completed" and closed["waitDismissed"] is True

    status, _, body = request("POST", f"/api/v1/tasks/{second['id']}/wait", {"action": "dismiss"})
    assert status == 403


def test_schedule_routes_round_trip_and_errors(transport, tmp_path):
    app, server, request = transport
    worker, _ = make_task(app, tmp_path, prompt="基础任务")
    headers = {"X-MMS-CSRF": app.csrf_token}
    base = f"/api/v1/bots/{worker['id']}/schedules"
    body = {"prompt": "每天查机票", "rule": {"kind": "daily", "atLocalTime": "09:00"},
            "timezone": "Asia/Singapore", "requestId": "sched-route-1"}

    status, _, raw = request("POST", base, body, headers)
    assert status == 200, raw
    schedule = json.loads(raw)
    assert schedule["rule"] == {"kind": "daily", "atLocalTime": "09:00"}
    assert schedule["timezone"] == "Asia/Singapore" and schedule["createdBy"] == "user"

    # The same requestId replays instead of creating a second schedule.
    status, _, raw = request("POST", base, body, headers)
    assert status == 200 and json.loads(raw)["id"] == schedule["id"]
    status, _, raw = request("GET", base)
    assert [row["id"] for row in json.loads(raw)["schedules"]] == [schedule["id"]]

    status, _, raw = request("POST", f"{base}/{schedule['id']}",
                             {"prompt": "改成每三小时", "rule": {"kind": "interval", "everySeconds": 10800},
                              "overlapPolicy": "queue"}, headers)
    assert status == 200, raw
    edited = json.loads(raw)
    assert edited["prompt"] == "改成每三小时" and edited["rule"] == {"kind": "interval", "everySeconds": 10800}
    assert edited["overlapPolicy"] == "queue"

    # Pausing has one entry point only: /enable and /disable.  An edit that
    # carries enabled is refused instead of silently ignored.
    status, _, raw = request("POST", f"{base}/{schedule['id']}", {"prompt": "改说明", "enabled": False}, headers)
    assert status == 400 and json.loads(raw)["error"]["code"] == "INVALID_REQUEST"
    status, _, raw = request("POST", base, {"prompt": "新建带 enabled", "enabled": False,
                                            "rule": {"kind": "interval", "everySeconds": 300}}, headers)
    assert status == 400 and json.loads(raw)["error"]["code"] == "INVALID_REQUEST"
    assert json.loads(request("POST", f"{base}/{schedule['id']}/disable", {}, headers)[2])["enabled"] is False
    assert json.loads(request("POST", f"{base}/{schedule['id']}/enable", {}, headers)[2])["enabled"] is True
    status, _, raw = request("POST", f"{base}/{schedule['id']}/delete", {}, headers)
    assert status == 200 and json.loads(raw) == {"deleted": True, "scheduleId": schedule["id"]}
    assert json.loads(request("GET", base)[2])["schedules"] == []

    for payload, codes in (
        ({"prompt": "太快", "rule": {"kind": "interval", "everySeconds": 60}}, (400, "SCHEDULE_INTERVAL_TOO_SHORT")),
        ({"prompt": "怪规则", "rule": {"kind": "cron"}}, (400, "INVALID_SCHEDULE_RULE")),
        ({"prompt": "怪时区", "rule": {"kind": "daily", "atLocalTime": "09:00"}, "timezone": "Mars/Olympus"},
         (400, "INVALID_TIMEZONE")),
    ):
        status, _, raw = request("POST", base, payload, headers)
        assert (status, json.loads(raw)["error"]["code"]) == codes

    status, _, raw = request("POST", f"{base}/sch_missing", {"prompt": "改"}, headers)
    assert status == 404 and json.loads(raw)["error"]["code"] == "SCHEDULE_NOT_FOUND"

    for index in range(20):
        assert request("POST", base, {"prompt": f"第 {index} 条", "rule": {"kind": "interval", "everySeconds": 300}},
                       headers)[0] == 200
    status, _, raw = request("POST", base, {"prompt": "第 21 条", "rule": {"kind": "interval", "everySeconds": 300}}, headers)
    assert status == 409 and json.loads(raw)["error"]["code"] == "SCHEDULE_LIMIT"

    # A schedule belongs to exactly one Bot; another Bot's id sees nothing.
    other, _ = make_task(app, tmp_path, prompt="另一个任务")
    assert json.loads(request("GET", f"/api/v1/bots/{other['id']}/schedules")[2])["schedules"] == []
    status, _, raw = request("POST", f"/api/v1/bots/{other['id']}/schedules/{schedule['id']}", {"prompt": "越界"}, headers)
    assert status == 404


def test_bot_worker_can_only_manage_its_own_schedules(transport, tmp_path):
    app, server, request = transport
    first_bot, first_task = make_task(app, tmp_path, prompt="第一个")
    second_bot, _ = make_task(app, tmp_path, prompt="第二个")
    foreign = app.bots.create_schedule(second_bot["id"], {"prompt": "别人的定时",
                                                          "rule": {"kind": "interval", "everySeconds": 300}})
    token = app.bots._tasks[first_task["id"]]["token"]
    auth = {"Authorization": f"Bearer {token}"}

    status, _, raw = request("POST", "/api/v1/bot-worker",
                             {"action": "schedule", "op": "create", "prompt": "我自己的定时",
                              "rule": {"kind": "daily", "atLocalTime": "09:00"}, "createdBy": "bot",
                              "requestId": "worker-sched-1"}, auth)
    assert status == 200, raw
    mine = json.loads(raw)["schedule"]
    assert mine["botId"] == first_bot["id"] and mine["createdBy"] == "bot"

    status, _, raw = request("POST", "/api/v1/bot-worker",
                             {"action": "schedule", "op": "list", "requestId": "worker-sched-2"}, auth)
    assert [row["id"] for row in json.loads(raw)["schedules"]] == [mine["id"]]

    status, _, raw = request("POST", "/api/v1/bot-worker",
                             {"action": "schedule", "op": "delete", "scheduleId": foreign["id"],
                              "requestId": "worker-sched-3"}, auth)
    assert status == 404 and json.loads(raw)["error"]["code"] == "SCHEDULE_NOT_FOUND"
    assert app.bots.list_schedules(second_bot["id"]), "the other Bot's schedule must survive"

    status, _, raw = request("POST", "/api/v1/bot-worker",
                             {"action": "schedule", "op": "list", "botId": second_bot["id"],
                              "requestId": "worker-sched-4"}, auth)
    assert status == 403 and json.loads(raw)["error"]["code"] == "BOT_SCOPE"


def _bot_prompt(tmp_path, task=None, bot=None):
    sessions = _Sessions()
    executor = PiBotExecutor(sessions, _Catalog())
    bot = bot or {"id": "bot_1", "name": "worker", "description": "", "systemPrompt": "",
                  "presetId": "pi:test", "workspaceId": "ws-test"}
    task = task or {"id": "task_1", "prompt": "写一个文件", "launchRequestId": "launch-1",
                    "collaborationRequested": False}
    executor.start(task, bot, tmp_path / "context.json")
    return sessions.launched[0]["prompt"]


def test_bot_prompt_lists_every_registered_subcommand(tmp_path):
    from mms_web.bot_client import command_catalog_text, registered_command_names

    prompt = _bot_prompt(tmp_path)
    catalog = command_catalog_text()
    assert catalog in prompt, "the generated command list must be part of the real prompt"
    names = registered_command_names()
    # The parser walk uses argparse internals; if it ever returned nothing the
    # loop below would pass silently, so pin the real registration count.
    assert len(names) >= 20, names
    for name in names:
        assert re.search(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", catalog), name


def test_bot_prompt_covers_schedule_and_memory_and_keeps_handwritten_policy(tmp_path):
    prompt = _bot_prompt(tmp_path)
    assert "schedule create" in prompt and "memory-remember" in prompt
    assert "不要回答做不到" in prompt
    # Converting the command list to generated text must not eat the policy lines.
    assert "不要循环轮询" in prompt
    assert "complete 不是用户验收" in prompt
