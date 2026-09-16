from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote
from unittest.mock import patch

import pytest

from mms_web.bot_notify import EVENT_TYPES, Notifier, sign
from mms_web.bots import BotRuntime
from mms_web.errors import WebError
from mms_web.server import WebApplication, create_server


class Receiver:
    """Local HTTP receiver that records signed POST bodies."""

    def __init__(self, *, fail_first=False, delay=0.0):
        self.requests: list[tuple[dict, bytes]] = []
        self.fail_first = fail_first
        self.delay = delay
        self._lock = threading.Lock()
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                size = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(size)
                with receiver._lock:
                    receiver.requests.append((dict(self.headers), body))
                    first = len(receiver.requests) == 1
                if receiver.delay:
                    time.sleep(receiver.delay)
                self.send_response(500 if receiver.fail_first and first else 200)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_port}/hook"

    def count(self):
        with self._lock:
            return len(self.requests)

    def wait(self, count, timeout=3.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.count() >= count:
                return True
            time.sleep(0.02)
        return False

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def test_emit_persists_events_and_filters_since(tmp_path):
    notifier = Notifier(tmp_path)
    older = notifier.emit({"type": "task.completed", "botId": "bot_1", "botName": "同事",
                           "taskId": "task_1", "title": "整理需求", "summary": "完成",
                           "link": "#page=bots&bot=bot_1&task=task_1"})
    time.sleep(0.01)
    newer = notifier.emit({"type": "task.failed", "botId": "bot_1", "botName": "同事",
                           "taskId": "task_2", "title": "抓取页面", "summary": "失败",
                           "link": "#page=bots&bot=bot_1&task=task_2"})
    assert [row["id"] for row in notifier.list_events()] == [older["id"], newer["id"]]
    assert [row["id"] for row in notifier.list_events(since=older["at"])] == [newer["id"]]

    reloaded = Notifier(tmp_path)
    assert [row["id"] for row in reloaded.list_events()] == [older["id"], newer["id"]]
    with pytest.raises(WebError) as failure:
        notifier.list_events(since="not-a-time")
    assert failure.value.code == "INVALID_REQUEST"


def test_emit_rejects_unknown_event_type(tmp_path):
    notifier = Notifier(tmp_path)
    with pytest.raises(WebError):
        notifier.emit({"type": "task.whatever"})


def test_webhook_signs_payload_and_retries_once(tmp_path):
    receiver = Receiver(fail_first=True)
    notifier = Notifier(tmp_path, timeout=2, retry_delay=0.01)
    try:
        saved = notifier.update_config({"webhooks": [{"url": receiver.url, "events": ["task.completed"], "secret": "s3cret"}]})
        assert saved["webhooks"][0]["url"] == receiver.url
        notifier.emit({"type": "task.completed", "botId": "bot_1", "botName": "同事", "taskId": "task_1",
                       "title": "整理需求", "summary": "完成", "link": "#page=bots"})
        assert receiver.wait(2)
        raw_headers, body = receiver.requests[-1]
        headers = {key.casefold(): value for key, value in raw_headers.items()}
        assert headers["x-mms-event"] == "task.completed"
        assert headers["x-mms-signature"] == sign(body, "s3cret")
        assert hmac.new(b"s3cret", body, hashlib.sha256).hexdigest() == headers["x-mms-signature"].removeprefix("sha256=")
        payload = json.loads(body)
        assert payload["botId"] == "bot_1" and payload["summary"] == "完成"

        # The receiver now answers 200, so the next event needs one attempt.
        notifier.emit({"type": "task.completed", "botId": "bot_1", "taskId": "task_2", "summary": "第二件"})
        assert receiver.wait(3)
        time.sleep(0.05)
        assert receiver.count() == 3
    finally:
        receiver.close()
        notifier.close()


def test_webhook_event_filter(tmp_path):
    matching = Receiver()
    other = Receiver()
    notifier = Notifier(tmp_path, timeout=2, retry_delay=0.01)
    try:
        notifier.update_config({"webhooks": [
            {"url": matching.url, "events": ["task.failed"], "secret": "a"},
            {"url": other.url, "events": ["task.waiting"], "secret": "b"},
        ]})
        notifier.emit({"type": "task.failed", "botId": "bot_1", "taskId": "task_1", "summary": "失败"})
        assert matching.wait(1)
        time.sleep(0.05)
        assert other.count() == 0
    finally:
        matching.close()
        other.close()
        notifier.close()


def test_slow_webhook_does_not_block_emit(tmp_path):
    receiver = Receiver(delay=0.8)
    notifier = Notifier(tmp_path, timeout=0.2, retry_delay=0)
    try:
        notifier.update_config({"webhooks": [{"url": receiver.url, "events": [], "secret": "s"}]})
        started = time.monotonic()
        notifier.emit({"type": "task.completed", "botId": "bot_1", "taskId": "task_1", "summary": "完成"})
        assert time.monotonic() - started < 0.3
    finally:
        receiver.close()
        notifier.close()


def test_config_validation_and_round_trip(tmp_path):
    notifier = Notifier(tmp_path)
    with pytest.raises(WebError) as failure:
        notifier.update_config({"webhooks": [{"url": "ftp://example.com/hook", "events": [], "secret": "x"}]})
    assert failure.value.code == "INVALID_REQUEST"
    with pytest.raises(WebError):
        notifier.update_config({"webhooks": [{"url": "http://example.com/hook", "events": ["task.bogus"]}]})
    with pytest.raises(WebError):
        notifier.update_config({"webhooks": [{"url": "http://example.com/hook"}] * 11})
    with pytest.raises(WebError):
        notifier.update_config({"config": []})

    saved = notifier.update_config({"webhooks": [{"url": "http://127.0.0.1:9/hook", "events": ["task.failed"], "secret": "s"}]})
    assert saved["events"] == list(EVENT_TYPES)
    assert saved["webhooks"][0]["events"] == ["task.failed"]
    stored = json.loads((tmp_path / "notify.json").read_text())
    assert stored["webhooks"][0]["url"] == "http://127.0.0.1:9/hook"


class CompletingExecutor:
    def __init__(self):
        self.state = "running"
        self.starts = []

    def available(self):
        return True

    def validate(self, bot):
        return {"model": "fake"}

    def start(self, task, bot, context_path):
        self.starts.append(task["id"])
        return {"sessionId": f"session-{len(self.starts)}", "baseline": 0,
                "artifactBaseline": {}, "model": "fake"}

    def snapshot(self, task):
        if self.state == "completed":
            return {"state": "completed", "alive": False, "artifacts": [], "events": [
                {"id": "answer", "kind": "assistant", "status": "done",
                 "text": "# 结论\n区域 A 的发布状态已确认。\n# 证据\n- ./evidence.log"}]}
        return {"state": self.state, "alive": self.state == "running", "artifacts": [], "events": []}

    def cancel(self, task):
        pass

    def artifact(self, session_id, artifact_id, revision):
        return {"content": "", "mimeType": "text/plain"}


class FailingExecutor(CompletingExecutor):
    def start(self, task, bot, context_path):
        self.starts.append(task["id"])
        raise WebError("BOT_SESSION_BUSY", "Bot 的会话仍在执行或等待确认。", 409)


def drain(rt):
    for worker in list(rt._workers):
        worker.join(timeout=1)


def make_bot(rt, name="通知 Bot"):
    return rt.create_bot({"name": name, "description": "", "systemPrompt": "",
                          "workspaceId": "ws-1", "presetId": "pi:fake", "wakeEnabled": True})


def test_runtime_notifies_completed_waiting_and_retrying(tmp_path):
    executor = CompletingExecutor()
    rt = BotRuntime(state_root=tmp_path, executor=executor)
    rt.configure_endpoint("http://127.0.0.1:9/api/v1/bot-worker")
    try:
        bot = make_bot(rt)
        done = rt.create_task({"botId": bot["id"], "prompt": "检查区域 A 的发布状态"})
        rt.tick(); drain(rt)
        assert rt.get_task(done["id"])["status"] == "running"
        executor.state = "completed"
        rt.tick()
        events = rt.list_notifications()["events"]
        assert events[-1]["type"] == "task.completed"
        assert events[-1]["botName"] == bot["name"]
        assert events[-1]["title"] == "检查区域 A 的发布状态"
        assert events[-1]["summary"] == "区域 A 的发布状态已确认。"
        assert events[-1]["link"] == f"#page=bots&bot={bot['id']}&task={done['id']}"

        executor.state = "running"
        waiting = rt.create_task({"botId": bot["id"], "prompt": "先确认预算再继续"})
        rt.tick(); drain(rt)
        assert rt.worker(waiting["id"], {"action": "wait", "reason": "需要你确认预算"})["ok"] is True
        executor.state = "idle"
        rt.tick()
        events = rt.list_notifications()["events"]
        assert events[-1]["type"] == "task.waiting"
        assert events[-1]["waitReason"] == "input"
        assert "需要你确认预算" in events[-1]["summary"]
        assert rt.get_task(waiting["id"])["status"] == "waiting"
    finally:
        rt.close()

    failing = FailingExecutor()
    retry_rt = BotRuntime(state_root=tmp_path / "retry", executor=failing)
    retry_rt.configure_endpoint("http://127.0.0.1:9/api/v1/bot-worker")
    try:
        retry_bot = make_bot(retry_rt)
        task = retry_rt.create_task({"botId": retry_bot["id"], "prompt": "等待基础设施恢复"})
        retry_rt.tick(); drain(retry_rt)
        assert retry_rt.list_notifications()["events"][-1]["type"] == "task.retrying"
    finally:
        retry_rt.close()


@pytest.fixture
def app_client(tmp_path):
    public = tmp_path / "public"
    public.mkdir()
    (public / "index.html").write_text("<h1>test</h1>", encoding="utf-8")
    with patch("mms_web.server._adapter", return_value=None):
        app = WebApplication(state_root=tmp_path / "state")
    app.bots.close()
    app.bots = BotRuntime(state_root=tmp_path / "state", executor=CompletingExecutor())
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
        yield app, request
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        app.close()


def test_notification_routes_pull_events_and_round_trip_config(app_client):
    app, request = app_client
    app.bots.notifier.emit({"type": "task.completed", "botId": "bot_x", "botName": "同事",
                            "taskId": "task_x", "title": "整理", "summary": "完成",
                            "link": "#page=bots&bot=bot_x&task=task_x"})
    status, _, body = request("GET", "/api/v1/bots/notifications")
    assert status == 200, body
    first = json.loads(body)["events"][0]
    assert first["type"] == "task.completed" and first["botId"] == "bot_x"

    time.sleep(0.01)
    app.bots.notifier.emit({"type": "task.failed", "botId": "bot_x", "botName": "同事",
                            "taskId": "task_y", "title": "抓取", "summary": "失败", "link": "#page=bots"})
    status, _, body = request("GET", f"/api/v1/bots/notifications?since={quote(first['at'], safe='')}")
    assert status == 200, body
    remaining = json.loads(body)["events"]
    assert [row["taskId"] for row in remaining] == ["task_y"]

    status, _, body = request("POST", "/api/v1/bots/notifications/config",
                              {"webhooks": [{"url": "http://127.0.0.1:9/hook", "events": ["task.failed"], "secret": "s"}]},
                              {"X-MMS-CSRF": app.csrf_token})
    assert status == 200, body
    assert json.loads(body)["webhooks"][0]["events"] == ["task.failed"]
    status, _, body = request("GET", "/api/v1/bots/notifications/config")
    assert status == 200
    assert json.loads(body)["webhooks"][0]["url"] == "http://127.0.0.1:9/hook"

    status, _, body = request("POST", "/api/v1/bots/notifications/config", {"webhooks": []})
    assert status == 403 and json.loads(body)["error"]["code"] == "INVALID_CSRF"
