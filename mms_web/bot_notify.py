"""Delivery of Bot task results away from the page.

Two surfaces share one event record: local notifications polled by the Web UI
and optional signed webhooks for external receivers such as a Feishu bot.
Delivery never blocks the task; a webhook is attempted once more after a
failure and is dropped afterwards.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import queue
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request
from uuid import uuid4

from .errors import WebError
from .runtime import private_json

EVENT_TYPES = ("task.completed", "task.failed", "task.waiting", "task.retrying")
MAX_EVENTS = 500
MAX_WEBHOOKS = 10
DEFAULT_TIMEOUT = 5.0


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def one_line(value, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def sign(body: bytes, secret: str) -> str:
    digest = hmac.new(str(secret or "").encode("utf-8"), body, hashlib.sha256).hexdigest()
    return "sha256=" + digest


class Notifier:
    """Durable local event log plus best-effort webhook fan-out."""

    def __init__(self, root: Path, *, timeout: float = DEFAULT_TIMEOUT, retry_delay: float = 1.0,
                 poster=None, sleeper=None):
        self.root = Path(root)
        self.events_path = self.root / "notifications.json"
        self.config_path = self.root / "notify.json"
        self.timeout = max(1.0, float(timeout))
        self.retry_delay = max(0.0, float(retry_delay))
        self._poster = poster or self._post
        self._sleep = sleeper or time.sleep
        self._lock = threading.RLock()
        self._events = self._load_events()
        self._config = self._load_config()
        self._queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None

    # ---------------------------------------------------------------- events
    def _load_events(self):
        try:
            data = json.loads(self.events_path.read_text())
        except (OSError, ValueError):
            return []
        rows = data.get("events") if isinstance(data, dict) else None
        return [row for row in rows or [] if isinstance(row, dict) and row.get("type") in EVENT_TYPES]

    def _persist_events(self):
        try:
            private_json(self.events_path, {"schema": 1, "events": self._events[-MAX_EVENTS:]})
        except OSError:
            # A read-only state root must not stop the task itself.
            pass

    def emit(self, event: dict) -> dict:
        """Append one event and queue webhook delivery without blocking."""
        record = {
            "id": "notif_" + uuid4().hex[:16],
            "at": now(),
            "type": str(event.get("type") or ""),
            "botId": str(event.get("botId") or ""),
            "botName": one_line(event.get("botName"), 80),
            "taskId": str(event.get("taskId") or ""),
            "title": one_line(event.get("title"), 120),
            "summary": one_line(event.get("summary"), 200),
            "waitReason": event.get("waitReason") or None,
            "link": str(event.get("link") or ""),
        }
        if record["type"] not in EVENT_TYPES:
            raise WebError("INVALID_REQUEST", "不支持这个通知类型。", 400)
        with self._lock:
            self._events.append(record)
            del self._events[:-MAX_EVENTS]
            self._persist_events()
            hooks = self._hooks_for(record["type"])
        if hooks:
            self._ensure_worker()
            self._queue.put(record)
        return record

    def emit_task(self, bot: dict, task: dict, event_type: str, wait_reason=None, note: str = "") -> dict:
        """Build an event from a Bot task and hand it to :meth:`emit`."""
        outcome = task.get("outcome") if isinstance(task.get("outcome"), dict) else {}
        summary = outcome.get("summary") if event_type == "task.completed" else None
        if not summary:
            summary = note or task.get("result") or task.get("error") or ""
        bot_id, task_id = task.get("botId") or "", task.get("id") or ""
        return self.emit({
            "type": event_type, "botId": bot_id, "botName": (bot or {}).get("name") or "",
            "taskId": task_id, "title": task.get("prompt"), "summary": summary,
            "waitReason": wait_reason, "link": f"#page=bots&bot={bot_id}&task={task_id}",
        })

    def list_events(self, since=None, limit: int = 200):
        """Return events after ``since``; the Web UI keeps its own read cursor."""
        with self._lock:
            events = [dict(row) for row in self._events]
        if since:
            events = [row for row in events if _parse_time(row.get("at")) > _parse_time(since)]
        return events[-max(1, min(int(limit), MAX_EVENTS)):]

    # ---------------------------------------------------------------- config
    def _load_config(self):
        try:
            data = json.loads(self.config_path.read_text())
        except (OSError, ValueError):
            return []
        rows = data.get("webhooks") if isinstance(data, dict) else None
        valid = []
        for row in rows or []:
            try:
                valid.append(self._webhook(row))
            except WebError:
                continue
        return valid

    @staticmethod
    def _webhook(row) -> dict:
        if not isinstance(row, dict):
            raise WebError("INVALID_REQUEST", "webhook 必须是对象。", 400)
        url = str(row.get("url") or "").strip()
        if not url.startswith(("http://", "https://")) or len(url) > 1000:
            raise WebError("INVALID_REQUEST", "webhook 地址必须是 http(s) URL。", 400)
        events = row.get("events")
        if events in (None, "", []):
            events = list(EVENT_TYPES)
        if not isinstance(events, list) or any(item not in EVENT_TYPES for item in events):
            raise WebError("INVALID_REQUEST", "webhook 事件必须是 task.completed / task.failed / task.waiting / task.retrying。", 400)
        secret = row.get("secret", "")
        if not isinstance(secret, str) or len(secret) > 200:
            raise WebError("INVALID_REQUEST", "webhook secret 必须是 200 字以内的文本。", 400)
        return {"url": url, "events": events, "secret": secret}

    def config(self) -> dict:
        with self._lock:
            webhooks = [dict(row) for row in self._config]
        return {"webhooks": webhooks, "events": list(EVENT_TYPES), "timeoutSeconds": self.timeout}

    def update_config(self, payload) -> dict:
        if not isinstance(payload, dict) or not isinstance(payload.get("webhooks"), list):
            raise WebError("INVALID_REQUEST", "请提交 webhooks 列表。", 400)
        rows = payload["webhooks"]
        if len(rows) > MAX_WEBHOOKS:
            raise WebError("INVALID_REQUEST", f"最多配置 {MAX_WEBHOOKS} 个 webhook。", 400)
        webhooks = [self._webhook(row) for row in rows]
        with self._lock:
            self._config = webhooks
            try:
                private_json(self.config_path, {"schema": 1, "webhooks": webhooks})
            except OSError as exc:
                raise WebError("NOTIFY_STORE_INVALID", "通知配置无法写入本地状态。", 409) from exc
        return self.config()

    # -------------------------------------------------------------- delivery
    def _hooks_for(self, event_type: str):
        with self._lock:
            hooks = [dict(row) for row in self._config]
        return [row for row in hooks if not row.get("events") or event_type in row["events"]]

    def _ensure_worker(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._deliver_loop, daemon=True, name="mms-bot-notify")
            self._thread.start()

    def _deliver_loop(self):
        while True:
            record = self._queue.get()
            try:
                if record is None:
                    return
                for hook in self._hooks_for(record.get("type") or ""):
                    self._deliver(hook, record)
            except Exception:
                # Delivery is best effort; a broken receiver must never stop
                # the scheduler thread or the task it reports on.
                continue

    def _deliver(self, hook: dict, record: dict) -> bool:
        body = json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8")
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "X-MMS-Event": str(record.get("type") or ""),
            "X-MMS-Signature": sign(body, hook.get("secret") or ""),
        }
        for attempt in (0, 1):
            try:
                status, _ = self._poster(hook["url"], body, headers)
                if 200 <= int(status) < 300:
                    return True
            except Exception:
                pass
            if attempt == 0:
                self._sleep(self.retry_delay)
        return False

    def _post(self, url: str, body: bytes, headers: dict):
        req = urllib_request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib_request.urlopen(req, timeout=self.timeout) as response:
                return response.status, response.read(2048)
        except urllib_error.HTTPError as exc:
            return exc.code, b""

    def close(self, timeout: float = 2.0):
        with self._lock:
            thread = self._thread
        if not thread:
            return
        self._queue.put(None)
        thread.join(timeout=timeout)


def _parse_time(value) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed
    except (TypeError, ValueError):
        raise WebError("INVALID_REQUEST", "since 需要包含时区的日期时间。", 400) from None
