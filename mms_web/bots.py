"""Durable, local Bot orchestration over real Pi sessions.

A completed model turn and user acceptance remain separate. No live mock
executor, retry-after-uncertain-launch, or arbitrary local-file serving.
"""
from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import secrets
import re
import threading
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .errors import WebError
from .runtime import private_json
from .bot_memory import BotMemoryStore, BotMemoryError
from .bot_communications import BotCommunications
from .bot_coordinator import plan_for
from . import bot_retry
from .bot_notify import Notifier

TERMINAL = {"completed", "failed", "cancelled", "interrupted"}
MAX_TASKS = 2000
MAX_MESSAGES = 500
PIXEL_AVATAR_IDS = ("round", "cat", "puff", "cube", "leaf", "ghost", "rocket", "star", "bean", "bot")
PIXEL_AVATAR_COLORS = ("#b9a5ff", "#ff9f91", "#73dfc7", "#ffd77d", "#8bb8ff", "#f18bd5")
_COLLABORATION_HINTS = ("找", "派给", "分派", "协作", "并行", "让.*bot", "让.*同事", "请.*检查")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def parse_time(value):
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        raise WebError("INVALID_TIME", "请提供包含时区的日期和时间。", 400) from None


def text_field(payload, key, limit, required=False):
    value = payload.get(key, "")
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise WebError("INVALID_REQUEST", f"{key} 不能为空且长度须在 {limit} 字以内。", 400)
    return value.strip()


def task_priority(payload):
    value = payload.get("priority", 50)
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
        raise WebError("INVALID_PRIORITY", "priority 必须是 0 到 100 的整数。", 400)
    return value


def avatar_field(payload, key, allowed, fallback):
    value = payload.get(key, fallback)
    if not isinstance(value, str) or value not in allowed:
        raise WebError("INVALID_REQUEST", f"{key} 不是可用的预设值。", 400)
    return value


def collaboration_requested(prompt: str) -> bool:
    """Detect an explicit request for Bot collaboration without planning a team."""
    return any(re.search(pattern, prompt, re.IGNORECASE) for pattern in _COLLABORATION_HINTS)


def parse_outcome(text: str) -> dict[str, str | None]:
    """Extract an optional v2 outcome envelope from Bot Markdown."""
    raw = str(text or "").strip()[:32000]
    labels = {"结论": "summary", "证据": "evidence", "改动": "changes",
              "未完成事项": "pending", "下一步": "next"}
    sections: dict[str, str] = {}
    current: str | None = None
    for line in raw.splitlines():
        match = re.match(r"^\s{0,3}#{1,3}\s*(结论|证据|改动|未完成事项|下一步)\s*:?[ \t]*$", line)
        if match:
            current = labels[match.group(1)]
            sections[current] = ""
        elif current:
            sections[current] = (sections[current] + "\n" + line).strip()
    return {"summary": sections.get("summary") or raw, "evidence": sections.get("evidence"),
            "changes": sections.get("changes"), "pending": sections.get("pending"),
            "next": sections.get("next"), "raw": raw}


class BotRuntime(BotCommunications):
    def __init__(self, *, state_root: Path, executor, computer=None, max_concurrent=3):
        self.root = Path(state_root) / "bots"
        self.executor, self.computer = executor, computer
        self.memory = BotMemoryStore(Path(state_root))
        self.max_concurrent = max(1, min(int(max_concurrent), 8))
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._changed = threading.Event()
        self._bots, self._tasks, self._messages, self._artifacts, self._requests = {}, {}, {}, {}, {}
        self._communications = {}
        self._launching = set()
        self._workers = set()
        self._thread = None
        self._file_lock = None
        self._endpoint = ""
        self._load_error = ""
        self.notifier = Notifier(self.root)
        self.can_dispatch = lambda: True
        self._load()

    def _load(self):
        path = self.root / "state.json"
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text())
            if data.get("schema") != 2:
                raise ValueError("Unsupported bot record")
            self._bots = data["bots"]
            self._tasks = data["tasks"]
            self._messages = data["messages"]
            self._artifacts = data["artifacts"]
            self._requests = data.get("requests", {})
            self._communications = data.get("communications", {})
            for task in self._tasks.values():
                # The old Pi process is not ours after restart. Preserve its
                # transcript and require an explicit resume, never replay work.
                if task["status"] in {"starting", "running"} or task.get("waitReason") in {"approval", "stopping", "connection"}:
                    task.update(status="interrupted", error="服务重启，原执行已中断。查看记录后可继续。", token="")
                    task["orphanAlive"] = bool(hasattr(self.executor, "orphan_alive") and self.executor.orphan_alive(task))
                    self._mailbox_receipt(task, "failed")
            for bot in self._bots.values():
                bot["status"] = "idle"
                bot.setdefault("memoryEnabled", True)
                bot.setdefault("memoryBudgetTokens", 2000)
                bot.setdefault("autoCompact", True)
                bot.setdefault("compactAtPercent", 70)
                bot.setdefault("orchestrationPolicy", "direct-first")
        except (OSError, ValueError, KeyError, TypeError):
            self._load_error = "Bot 记录无法读取，原文件已保留；请检查记录后再写入。"

    def _persist(self):
        if self._load_error:
            raise WebError("BOT_STORE_INVALID", self._load_error, 409)
        if not self._file_lock:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            handle = (self.root / "owner.lock").open("a+")
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                handle.close()
                raise WebError("BOT_STORE_BUSY", "另一个 Pilot 正在管理这份 Bot 记录。", 409) from None
            self._file_lock = handle
        private_json(self.root / "state.json", {"schema": 2, "bots": self._bots, "tasks": self._tasks,
                    "messages": self._messages, "artifacts": self._artifacts, "requests": self._requests,
                    "communications": self._communications})
        self._changed.set()

    def configure_endpoint(self, url):
        self._endpoint = url

    def start(self):
        if self._thread:
            return
        self._thread = threading.Thread(target=self._loop, daemon=True, name="mms-bot-scheduler")
        self._thread.start()

    def close(self):
        self._stop.set()
        self._changed.set()
        if self._thread:
            self._thread.join(timeout=5)
        with self._lock:
            active = [deepcopy(t) for t in self._tasks.values() if t["status"] in {"starting", "running"} or t.get("waitReason") in {"approval", "stopping", "connection"}]
        for task in active:
            try:
                self.executor.cancel(task)
            except Exception:
                pass
        for thread in list(self._workers):
            thread.join(timeout=3)
        with self._lock:
            for item in active:
                task = self._tasks[item["id"]]
                if task["status"] not in TERMINAL:
                    task.update(status="interrupted", token="", error="服务已停止，可查看记录后继续。", updatedAt=now())
                    self._mailbox_receipt(task, "failed")
            if self._file_lock:
                self._persist()
                self._file_lock.close()
                self._file_lock = None
        self.notifier.close()

    def capabilities(self):
        available = bool(self.executor and self.executor.available() and not self._load_error)
        browser_provider = self.computer.capabilities() if self.computer and hasattr(self.computer, "capabilities") else None
        return {"executor": "pi", "available": available, "reason": self._load_error or ("" if available else "Pi 或 MMS 模型尚未连接。"),
                "maxConcurrent": self.max_concurrent, "autoWake": True,
                "screenshot": bool(self.computer),
                "browser": bool(self.computer and self.computer.available()),
                "browserProvider": browser_provider,
                "version": "2.2"}

    def _bot(self, bot_id):
        if bot_id not in self._bots:
            raise WebError("BOT_NOT_FOUND", "找不到这个 Bot。", 404)
        return self._bots[bot_id]

    def _task(self, task_id):
        if task_id not in self._tasks:
            raise WebError("TASK_NOT_FOUND", "找不到这个 Bot 任务。", 404)
        return self._tasks[task_id]

    def _view(self, task):
        return deepcopy({k: v for k, v in task.items() if k not in {"token", "baseline", "artifactBaseline", "launchRequestId", "declaredResult", "declaredError", "seenEvents", "resumeText"}})

    def _replay(self, operation, payload):
        rid = payload.get("requestId")
        if not rid:
            return None, None
        if not isinstance(rid, str) or len(rid) > 128:
            raise WebError("INVALID_REQUEST", "requestId 无效。", 400)
        key = operation + ":" + rid
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        old = self._requests.get(key)
        if old:
            if old["fingerprint"] != fingerprint:
                raise WebError("REQUEST_ID_CONFLICT", "同一请求编号对应了不同操作。", 409)
            return key, old["resource"]
        return key, fingerprint

    def _remember(self, key, fingerprint, resource):
        if key:
            self._requests[key] = {"fingerprint": fingerprint, "resource": resource}

    def create_bot(self, payload):
        with self._lock:
            key, value = self._replay("bot", payload)
            if key in self._requests:
                return self.get_bot(value)
            if len(self._bots) >= 50:
                raise WebError("BOT_LIMIT", "最多创建 50 个 Bot。", 409)
            # Bot work is scoped by Bot identity and its durable Pi session.
            # The computer is shared; workspaceId is an internal launch hint,
            # defaulting to the catalog's global workspace rather than a user
            # facing per-Bot folder assignment.
            requested_preset = payload.get("presetId")
            if requested_preset in (None, ""):
                requested_preset = ""
            elif not isinstance(requested_preset, str):
                raise WebError("INVALID_REQUEST", "presetId 必须是文本。", 400)
            elif len(requested_preset) > 500:
                raise WebError("INVALID_REQUEST", "presetId 过长。", 400)
            bot = {"id": "bot_" + uuid4().hex[:16], "name": text_field(payload, "name", 80, True),
                   "description": text_field(payload, "description", 1000), "systemPrompt": text_field(payload, "systemPrompt", 12000),
                   "workspaceId": text_field(payload, "workspaceId", 500) or "default", "presetId": requested_preset.strip(),
                   "wakeEnabled": payload.get("wakeEnabled", True), "status": "idle", "sessionId": None,
                   "avatarId": avatar_field(payload, "avatarId", PIXEL_AVATAR_IDS, secrets.choice(PIXEL_AVATAR_IDS)),
                   "avatarColor": avatar_field(payload, "avatarColor", PIXEL_AVATAR_COLORS, secrets.choice(PIXEL_AVATAR_COLORS)),
                   "createdAt": now(), "updatedAt": now()}
            bot.update({"memoryEnabled": True, "memoryBudgetTokens": 2000,
                        "autoCompact": True, "compactAtPercent": 70,
                        "orchestrationPolicy": "direct-first"})
            if type(bot["wakeEnabled"]) is not bool:
                raise WebError("INVALID_REQUEST", "wakeEnabled 必须是布尔值。", 400)
            bot.update(self.executor.validate(bot))
            self._bots[bot["id"]] = bot
            self.memory.update_settings(bot["id"], **{k: bot[k] for k in ("memoryEnabled", "memoryBudgetTokens", "autoCompact", "compactAtPercent")})
            self._remember(key, value, bot["id"])
            self._persist()
            return deepcopy(bot)

    def get_bot(self, bot_id):
        with self._lock:
            return deepcopy(self._bot(bot_id))

    def list_bots(self):
        with self._lock:
            return deepcopy(list(self._bots.values()))

    def update_bot(self, bot_id, payload):
        with self._lock:
            bot = self._bot(bot_id)
            active = any(t["botId"] == bot_id and (t["status"] not in TERMINAL | {"scheduled", "queued"} or t.get("orphanAlive")) for t in self._tasks.values())
            if active and "presetId" in payload and payload.get("presetId") not in (None, "", bot.get("presetId")):
                raise WebError("BOT_BUSY", "Bot 正在执行当前任务，模型将在本轮结束后才能切换。", 409)
            updated = deepcopy(bot)
            for key, limit in (("name", 80), ("description", 1000), ("systemPrompt", 12000), ("workspaceId", 500), ("presetId", 500)):
                if key in payload:
                    if key == "workspaceId" and payload[key] in (None, ""):
                        updated[key] = "default"
                    elif key == "presetId" and payload[key] in (None, ""):
                        updated[key] = ""
                    else:
                        updated[key] = text_field(payload, key, limit, key in {"name", "presetId"})
            for key, allowed in (("avatarId", PIXEL_AVATAR_IDS), ("avatarColor", PIXEL_AVATAR_COLORS)):
                if key in payload:
                    updated[key] = avatar_field(payload, key, allowed, updated.get(key, allowed[0]))
            if "wakeEnabled" in payload:
                if type(payload["wakeEnabled"]) is not bool:
                    raise WebError("INVALID_REQUEST", "wakeEnabled 必须是布尔值。", 400)
                updated["wakeEnabled"] = payload["wakeEnabled"]
            for key, low, high in (("memoryBudgetTokens", 500, 8000), ("compactAtPercent", 50, 90)):
                if key in payload:
                    value = payload[key]
                    if type(value) is not int or not low <= value <= high:
                        raise WebError("INVALID_REQUEST", f"{key} 必须是 {low} 到 {high} 之间的整数。", 400)
                    updated[key] = value
            if "memoryEnabled" in payload or "autoCompact" in payload:
                for key in ("memoryEnabled", "autoCompact"):
                    if key in payload:
                        if type(payload[key]) is not bool:
                            raise WebError("INVALID_REQUEST", f"{key} 必须是布尔值。", 400)
                        updated[key] = payload[key]
            updated.update(self.executor.validate(updated))
            if updated["workspaceId"] != bot["workspaceId"] or updated["presetId"] != bot["presetId"]:
                updated["sessionId"] = None
            updated["updatedAt"] = now()
            self._bots[bot_id] = updated
            try:
                self.memory.update_settings(bot_id, **{k: updated[k] for k in ("memoryEnabled", "memoryBudgetTokens", "autoCompact", "compactAtPercent")})
            except BotMemoryError as exc:
                raise WebError("MEMORY_STORE_INVALID", "Bot 记忆记录无法更新，请检查本地状态。", 409) from exc
            self._persist()
            return deepcopy(updated)

    def delete_bot(self, bot_id):
        """Delete a Bot and its private transcript, artifacts, memory and mailbox rows."""
        with self._lock:
            if bot_id not in self._bots:
                return {"deleted": True, "botId": bot_id, "taskIds": []}
            task_ids = {t["id"] for t in self._tasks.values() if t["botId"] == bot_id}
            related = [t for t in self._tasks.values() if t["id"] in task_ids
                       or t.get("parentTaskId") in task_ids or any(c in task_ids for c in t.get("children", []))]
            if any(t["status"] not in TERMINAL | {"queued", "scheduled"} or t.get("orphanAlive") or t["id"] in self._launching for t in related):
                raise WebError("BOT_BUSY", "请先结束这个 Bot 及其协作中的任务，再删除它。", 409)
            screenshot_paths = []
            for task_id in task_ids:
                for artifact in self._artifacts.get(task_id, []):
                    path = Path(artifact.get("path") or "").resolve()
                    screenshots = (self.root / "screenshots").resolve()
                    if path.is_relative_to(screenshots) and path.is_file():
                        screenshot_paths.append(path)
                self._tasks.pop(task_id, None)
                self._messages.pop(task_id, None)
                self._artifacts.pop(task_id, None)
            for task in self._tasks.values():
                task["children"] = [child for child in task.get("children", []) if child not in task_ids]
                if task.get("parentTaskId") in task_ids:
                    task["parentTaskId"] = None
            old_communication_ids = set(self._communications)
            self._communications = {key: row for key, row in self._communications.items()
                                    if row.get("senderBotId") != bot_id and row.get("recipientBotId") != bot_id
                                    and row.get("taskId") not in task_ids and row.get("deliveryTaskId") not in task_ids}
            removed_resources = task_ids | (old_communication_ids - set(self._communications)) | {bot_id}
            self._requests = {key: value for key, value in self._requests.items()
                              if value.get("resource") not in removed_resources}
            self._bots.pop(bot_id, None)
            self._persist()
            self.memory.delete(bot_id)
            for path in screenshot_paths:
                path.unlink(missing_ok=True)
            return {"deleted": True, "botId": bot_id, "taskIds": sorted(task_ids)}

    def _message(self, task_id, kind, content, sender=None, **extra):
        rows = self._messages.setdefault(task_id, [])
        message = {"id": "msg_" + uuid4().hex[:16], "taskId": task_id, "type": kind,
                   "content": content[:32000], "senderBotId": sender, "createdAt": now(), **extra}
        rows.append(message)
        if len(rows) > MAX_MESSAGES:
            del rows[:-MAX_MESSAGES]
        return message

    def create_task(self, payload):
        with self._lock:
            key, value = self._replay("task", payload)
            if key in self._requests:
                return self.get_task(value)
            bot = self._bot(str(payload.get("botId") or ""))
            self.executor.validate(bot)
            if len(self._tasks) >= MAX_TASKS:
                raise WebError("TASK_LIMIT", "本地已保存 2,000 个任务，请归档后继续。", 409)
            parent_id = payload.get("parentTaskId")
            if parent_id:
                parent = self._task(parent_id)
                ancestor, depth = parent, 0
                while ancestor:
                    depth += 1
                    if ancestor["botId"] == bot["id"] or depth > 5:
                        raise WebError("BOT_DISPATCH_CYCLE", "不能沿同一分发链再次调用同一个 Bot，最多五层。", 409)
                    ancestor = self._tasks.get(ancestor.get("parentTaskId"))
                if len(parent.get("children", [])) >= 20:
                    raise WebError("BOT_CHILD_LIMIT", "一个任务最多分发 20 个子任务。", 409)
            run_at = parse_time(payload.get("runAt"))
            prompt = text_field(payload, "prompt", 32000, True)
            coordinator_plan = plan_for(prompt, bot, list(self._bots.values()))
            task = {"id": "task_" + uuid4().hex[:16], "botId": bot["id"],
                    "prompt": prompt, "parentTaskId": parent_id,
                    "status": "scheduled" if run_at else "queued", "runAt": run_at, "children": [],
                    "result": None, "error": None, "acceptedAt": None, "sessionId": None, "waitReason": None,
                    "turn": 0, "createdAt": now(), "updatedAt": now(), "token": "", "seenEvents": {},
                    "priority": task_priority(payload), "queueReason": "等待调度" if not run_at else None,
                    "coordinatorPlan": coordinator_plan}
            task["executionMode"] = coordinator_plan["mode"]
            task["collaborationRequested"] = collaboration_requested(task["prompt"])
            task["outcome"] = None
            if payload.get("wake") is False and not run_at:
                task.update(status="waiting", waitReason="manual")
            self._tasks[task["id"]] = task
            self._artifacts[task["id"]] = []
            self._message(task["id"], "instruction", task["prompt"])
            if parent_id:
                parent = self._task(parent_id)
                parent.setdefault("children", []).append(task["id"])
                self._message(parent_id, "handoff", f"已分发给 {bot['name']}：{task['prompt']}", bot["id"], childTaskId=task["id"])
                if parent["status"] in TERMINAL:
                    parent.update(status="waiting", waitReason="children", acceptedAt=None)
            self._remember(key, value, task["id"])
            self._persist()
            return self._view(task)

    def auto_task(self, payload):
        """Route a natural-language request to the best Bot.

        This is intentionally deterministic and inspectable for v2.0: Bot
        identity metadata provides the routing signal, while the selected Bot
        still performs the real work in its Pi session. A future Router Bot can
        replace this scorer without changing the task contract.
        """
        prompt = text_field(payload, "prompt", 32000, True)
        with self._lock:
            bots = list(self._bots.values())
        if not bots:
            raise WebError("BOT_REQUIRED", "请先创建至少一个 Bot。", 409)
        # An explicit Bot name in the user's sentence is stronger than any
        # metadata score. Longest match wins, so a specialized name beats a
        # shorter generic one. This is recognition, not multi-agent planning.
        explicit = [bot for bot in bots if len(str(bot.get("name") or "").strip()) >= 2 and
                    str(bot["name"]).casefold() in prompt.casefold()]
        if explicit:
            bot = max(explicit, key=lambda item: len(str(item["name"])))
            routing = "explicit-bot-name"
        else:
            words = [w.lower() for w in re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", prompt)]
            scored = []
            for index, candidate in enumerate(bots):
                corpus = " ".join(str(candidate.get(key) or "") for key in ("name", "description", "systemPrompt")).lower()
                score = sum(3 if word in str(candidate.get("name") or "").lower() else 1 for word in words if word in corpus)
                # Preserve list order as the stable tie-breaker.
                scored.append((score, -index, candidate))
            _, _, bot = max(scored, key=lambda item: (item[0], item[1]))
            routing = "metadata-score"
        task = self.create_task({k: v for k, v in payload.items() if k not in {"botId", "prompt"}} | {"botId": bot["id"], "prompt": prompt})
        return {"task": task, "bot": deepcopy(bot), "routing": routing}

    def get_task(self, task_id):
        with self._lock:
            return self._view(self._task(task_id))

    def list_tasks(self, *, bot_id=None, status=None):
        with self._lock:
            return [self._view(t) for t in reversed(list(self._tasks.values())) if (not bot_id or t["botId"] == bot_id) and (not status or t["status"] == status)]

    @staticmethod
    def _message_view(message):
        """Return a read-only compatible view of a persisted message.

        Older records stored Pi notices and tool events as ``message``.  The
        source id prefixes are emitted by the session layer and are the only
        unambiguous signal available for correcting those records.  Keep the
        persisted event untouched; only the API view gets the richer shape.
        """
        view = deepcopy(message)
        source_id = view.get("sourceEventId")
        if isinstance(source_id, str):
            if source_id.startswith("n-"):
                view["sourceKind"] = "notice"
                view["type"] = "progress"
            elif source_id.startswith("t-"):
                view["sourceKind"] = "tool"
                view["type"] = "progress"
        return view

    def list_messages(self, task_id):
        with self._lock:
            self._task(task_id)
            return [self._message_view(message) for message in self._messages.get(task_id, [])]

    def list_bot_messages(self, bot_id):
        with self._lock:
            self._bot(bot_id)
            return [self._message_view(message) for task in self._tasks.values() if task["botId"] == bot_id
                    for message in self._messages.get(task["id"], [])]

    def memory_view(self, bot_id, query=""):
        with self._lock:
            bot = self._bot(bot_id)
            settings = {k: bot.get(k, v) for k, v in (("memoryEnabled", True), ("memoryBudgetTokens", 2000), ("autoCompact", True), ("compactAtPercent", 70))}
        view = self.memory.get(bot_id, query=query)
        view["settings"] = settings
        session_id = bot.get("sessionId")
        if session_id and getattr(self.executor, "sessions", None):
            try:
                runtime = self.executor.sessions.runtime_view(session_id)
                model = runtime.get("model") or {}
                stats = runtime.get("stats") or {}
                usage = stats.get("contextUsage") if isinstance(stats, dict) else None
                used_tokens = context_window = used_percent = None
                if isinstance(usage, dict):
                    used_tokens = usage.get("usedTokens", usage.get("tokens"))
                    used_percent = usage.get("usedPercent", usage.get("percent"))
                    context_window = usage.get("contextWindow")
                context_window = context_window or model.get("contextWindow")
                if used_percent is None and used_tokens is not None and context_window:
                    used_percent = round(float(used_tokens) / float(context_window) * 100, 1)
                elif used_percent is not None and float(used_percent) <= 1:
                    used_percent = round(float(used_percent) * 100, 1)
                source = "live" if runtime.get("alive") and not runtime.get("cached") else "cached"
                view["context"] = {**view.get("context", {}), "contextWindow": context_window, "usedTokens": used_tokens, "usedPercent": used_percent,
                                    "source": source}
                self.memory.update_context(bot_id, contextWindow=context_window, usedTokens=used_tokens, usedPercent=used_percent, source=source)
            except Exception:
                pass
        return view

    def list_notifications(self, since=None):
        """Events the page has not acknowledged yet; the client keeps the cursor."""
        with self._lock:
            return {"events": self.notifier.list_events(since)}

    def notify_config(self):
        with self._lock:
            return self.notifier.config()

    def update_notify_config(self, payload):
        with self._lock:
            return self.notifier.update_config(payload)

    def memory_mutate(self, bot_id, payload):
        with self._lock:
            bot = self._bot(bot_id)
            settings = {k: bot.get(k, v) for k, v in (("memoryEnabled", True), ("memoryBudgetTokens", 2000), ("autoCompact", True), ("compactAtPercent", 70))}
        action = payload.get("action")
        if action == "remember":
            content = text_field(payload, "content", 2000, True)
            try:
                if payload.get("id"):
                    self.memory.update(bot_id, str(payload["id"]), content)
                else:
                    self.memory.remember(bot_id, content, kind="fact", source="user")
            except BotMemoryError as exc:
                raise WebError("INVALID_REQUEST", "记忆内容或记录编号无效。", 400) from exc
        elif action == "forget":
            try:
                self.memory.forget(bot_id, str(payload.get("id") or ""))
            except BotMemoryError as exc:
                raise WebError("MEMORY_NOT_FOUND", "找不到这条记忆。", 404) from exc
        else:
            raise WebError("INVALID_REQUEST", "记忆操作必须是 remember 或 forget。", 400)
        view = self.memory.get(bot_id)
        view["settings"] = settings
        return view

    def wake_task(self, task_id, payload=None):
        with self._lock:
            task = self._task(task_id)
            if task.get("orphanAlive"):
                raise WebError("BOT_PREVIOUS_PROCESS_ALIVE", "上次执行进程仍存在，先检查该会话；不会重复启动或终止不明进程。", 409)
            if task.get("retry"):
                # An explicit wake skips the remaining backoff instead of
                # silently waiting for the timer.
                task.pop("retry", None)
                task.update(status="queued", queueReason="已唤醒，等待调度", updatedAt=now())
                self._message(task_id, "system", "已跳过等待重试，立即重新排队。")
                self._persist()
                return self._view(task)
            if task["status"] in {"scheduled", "interrupted", "failed", "waiting"} and task.get("waitReason") not in {"approval", "connection", "stopping"}:
                if task.get("waitReason") == "children" and any(self._task(c)["status"] not in TERMINAL for c in task["children"]):
                    return self._view(task)
                task.update(status="queued", waitReason=None, runAt=None, error=None, acceptedAt=None,
                            resumeText="继续本任务。先检查已有记录和成果，避免重复副作用。")
                task.pop("retry", None)
                self._message(task_id, "system", "已唤醒，等待执行。")
                self._persist()
            return self._view(task)

    def wake_bot(self, bot_id, payload=None):
        with self._lock:
            self._bot(bot_id)
            ids = [t["id"] for t in self._tasks.values() if t["botId"] == bot_id and t["status"] in {"scheduled", "waiting", "interrupted"}]
        for tid in ids:
            self.wake_task(tid, payload)
        return {"bot": self.get_bot(bot_id), "wokenTaskIds": ids}

    def accept_task(self, task_id):
        with self._lock:
            task = self._task(task_id)
            if task["status"] != "completed":
                raise WebError("TASK_NOT_COMPLETE", "任务尚未完成，不能验收。", 409)
            if not task.get("acceptedAt"):
                task.update(acceptedAt=now(), updatedAt=now())
                self._message(task_id, "system", "用户已接受此结果。")
                self._persist()
            return self._view(task)

    def add_message(self, task_id, payload):
        with self._lock:
            key, value = self._replay("message:" + task_id, payload)
            if key in self._requests:
                return self.get_task(value)
            task = self._task(task_id)
            content = text_field(payload, "content", 32000, True)
            if task.get("orphanAlive"):
                raise WebError("BOT_PREVIOUS_PROCESS_ALIVE", "上次执行进程仍存在，请先检查该会话。", 409)
            self._message(task_id, "instruction", content)
            if task["status"] in {"running", "starting"} or task.get("waitReason") in {"approval", "stopping", "connection"}:
                task.setdefault("inbox", []).append(content)
            else:
                task.update(status="queued", waitReason=None, acceptedAt=None, error=None,
                            resumeText=content, runAt=None)
                task.pop("retry", None)
            self._remember(key, value, task_id)
            self._persist()
            return self._view(task)

    def cancel_task(self, task_id):
        targets = []
        with self._lock:
            def visit(tid):
                task = self._task(tid)
                for child in task.get("children", []):
                    visit(child)
                if task["status"] in TERMINAL:
                    return
                task["token"] = ""
                if task.get("sessionId") and task["status"] in {"running", "waiting"} and task.get("waitReason") != "children":
                    task.update(cancelRequested=True, cancelAt=now(), waitReason="stopping")
                    targets.append(deepcopy(task))
                elif task["status"] == "starting":
                    task["cancelRequested"] = True
                    task["cancelAt"] = now()
                else:
                    self._finish(task, "cancelled", "任务已取消。")
            visit(task_id)
            self._persist()
        for task in targets:
            try:
                self.executor.cancel(task)
            except Exception:
                with self._lock:
                    self._message(task["id"], "error", "停止请求尚未确认，请查看对应会话。")
        return self.get_task(task_id)

    def _finish(self, task, state, message, *, error_code="", error_detail="", error_status=None):
        # Only a task that never reached execution may be replayed. Anything
        # after that is reported to the user, because the first attempt may
        # already have changed something a silent retry would duplicate.
        if state in {"failed", "interrupted"} and task.get("status") == "starting":
            if bot_retry.classify(error_code, message, error_detail, status=error_status) == "transient":
                retry = bot_retry.schedule(task, message, error_code=error_code, detail=error_detail)
                if retry:
                    task["error"] = message
                    self._bot(task["botId"])["status"] = "idle"
                    self._message(task["id"], "system", f"基础设施暂时不可用：{message}"
                                  f" 将在 {retry['nextAt']} 自动重试（第 {retry['count']} 次）。")
                    self._notify(task, "task.retrying")
                    return
                # The whole budget is spent: this is a real failure now, not
                # an uncertain launch, and the message lists every attempt.
                message = bot_retry.exhausted_message(task, message)
                state = "failed"
        task.pop("retry", None)
        task.update(status=state, updatedAt=now(), completedAt=now(), token="", waitReason=None)
        self._mailbox_receipt(task, "processed" if state == "completed" else "failed")
        if state == "completed":
            task["result"] = message
            task["outcome"] = parse_outcome(message)
            task["error"] = None
        elif state in {"failed", "interrupted"}:
            task["error"] = message
        self._bot(task["botId"])["status"] = "idle"
        self._message(task["id"], "result" if state == "completed" else "error" if state == "failed" else "system", message, task["botId"])
        if state == "completed":
            try:
                bot = self._bot(task["botId"])
                if bot.get("memoryEnabled", True):
                    digest = f"任务 {task['id']}：{task.get('prompt','')[:600]}\n结果：{message[:1200]}"
                    self.memory.remember(task["botId"], digest, kind="task", source="task", task_id=task["id"])
            except Exception:
                pass
        if task.get("parentTaskId"):
            parent = self._task(task["parentTaskId"])
            self._message(parent["id"], "result", f"子任务 {task['id']} ({state})：{message}", task["botId"], childTaskId=task["id"])
            parent["childrenChanged"] = True
        if state in {"completed", "failed"}:
            self._notify(task, "task.completed" if state == "completed" else "task.failed")

    def _notify(self, task, event_type, wait_reason=None, note=""):
        """Best-effort delivery; a broken receiver never fails the task."""
        try:
            self.notifier.emit_task(self._bot(task["botId"]), task, event_type, wait_reason, note)
        except Exception:
            pass

    def _resume_children(self, task):
        if not task.get("childrenChanged") or not task.get("children"):
            return False
        children = [self._task(t) for t in task["children"]]
        if any(c["status"] not in TERMINAL for c in children):
            return False
        replies = "\n\n".join(f"{c['id']} [{c['status']}] {c.get('result') or c.get('error') or ''}" for c in children)
        task.update(status="queued", waitReason=None, childrenChanged=False, resumeText="子任务均已回传，请检查成果并总结。\n" + replies)
        self._message(task["id"], "system", "子任务已回传，自动唤醒发起 Bot。")
        return True

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                # Preserve evidence and pause dispatch after a scheduler/store
                # failure rather than endlessly rerunning uncertain actions.
                with self._lock:
                    self._load_error = "Bot 调度器发生错误；记录已保留，请检查本地服务。"
            self._changed.wait(0.5)
            self._changed.clear()

    def tick(self):
        if self._load_error or self._stop.is_set():
            return
        with self._lock:
            polling = [deepcopy(t) for t in self._tasks.values() if t.get("sessionId") and (t["status"] == "running" or (t["status"] == "waiting" and t.get("waitReason") in {"approval", "stopping", "connection"}))]
        for task in polling:
            try:
                if task.get("cancelRequested") and task.get("cancelAt") and not task.get("forceStopSent"):
                    elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(task["cancelAt"])).total_seconds()
                    if elapsed >= 15 and hasattr(self.executor, "force_stop"):
                        self.executor.force_stop(task)
                        with self._lock:
                            self._task(task["id"])["forceStopSent"] = True
                snapshot = self.executor.snapshot(task)
                with self._lock:
                    live = self._task(task["id"])
                    self._observe(live, snapshot)
            except Exception:
                with self._lock:
                    task = self._task(task["id"])
                    # The process may still be doing work. Keep its resource
                    # reservation until the existing session is observable.
                    task.update(status="waiting", waitReason="connection", error="暂时无法确认执行状态，正在恢复连接；工作目录仍被保留。", updatedAt=now())
                    self._persist()
        launches = []
        with self._lock:
            if not self.can_dispatch():
                return
            changed = self._deliver_mailbox()
            for task in self._tasks.values():
                if task.get("orphanAlive") and not self.executor.orphan_alive(task):
                    task["orphanAlive"] = False
                    changed = True
                if task["status"] == "scheduled" and task.get("runAt") and self._bot(task["botId"])["wakeEnabled"]:
                    if datetime.fromisoformat(task["runAt"]) <= datetime.now(timezone.utc):
                        task.update(status="queued", runAt=None)
                        self._message(task["id"], "system", "到达计划时间，自动唤醒。")
                        changed = True
                if task["status"] == "waiting" and task.get("waitReason") == "children":
                    changed = self._resume_children(task) or changed
            busy = [t for t in self._tasks.values() if t.get("orphanAlive") or t["status"] in {"starting", "running"} or (t["status"] == "waiting" and t.get("waitReason") not in {"children", "manual", "user"})]
            busy_bots = {t["botId"] for t in busy}
            busy_workspaces = {self._bot(t["botId"])["workspaceId"] for t in busy}
            queued = sorted(
                (task for task in self._tasks.values() if task["status"] == "queued"),
                # Python's sort is stable: omitting the random task id keeps
                # insertion order when two requests share the same timestamp.
                key=lambda task: (-int(task.get("priority", 50)), task.get("createdAt", "")),
            )
            for task in queued:
                retry = task.get("retry") or {}
                if retry.get("nextAt"):
                    if datetime.fromisoformat(retry["nextAt"]) > datetime.now(timezone.utc):
                        continue
                    retry.pop("nextAt", None)
                    task["queueReason"] = "等待重试"
                    changed = True
                if len(busy) + len(launches) >= self.max_concurrent:
                    if task.get("queueReason") != "等待并发资源":
                        task["queueReason"] = "等待并发资源"
                        changed = True
                    continue
                bot = self._bot(task["botId"])
                if bot["id"] in busy_bots or bot["workspaceId"] in busy_workspaces:
                    if task.get("queueReason") != "等待 Bot 或工作环境空闲":
                        task["queueReason"] = "等待 Bot 或工作环境空闲"
                        changed = True
                    continue
                task.update(status="starting", updatedAt=now(), startedAt=now(), turn=task["turn"] + 1,
                            launchRequestId=f"bot-{task['id']}-{task['turn'] + 1}", token=secrets.token_urlsafe(32),
                            seenEvents={}, cancelRequested=False, declaredResult=None, declaredError=None,
                            waitRequested=False, waitReason=None, forceStopSent=False, cancelAt=None,
                            result=None, error=None, completedAt=None, acceptedAt=None, outcome=None, queueReason=None)
                bot["status"] = "busy"
                busy_bots.add(bot["id"])
                busy_workspaces.add(bot["workspaceId"])
                launches.append((deepcopy(task), deepcopy(bot)))
                changed = True
            if changed:
                self._persist()
        for task, bot in launches:
            thread = threading.Thread(target=self._launch, args=(task, bot), daemon=True, name=f"mms-{task['id']}")
            self._workers.add(thread)
            thread.start()

    def _launch(self, task, bot):
        try:
            if not self._endpoint:
                raise WebError("BOT_ENDPOINT_UNAVAILABLE", "Bot 服务尚未开始监听。", 409)
            context = self.root / "contexts" / f"{task['id']}.json"
            private_json(context, {"url": self._endpoint, "token": task["token"], "taskId": task["id"], "botId": bot["id"]})
            with self._lock:
                task["mailboxContext"] = self._mailbox_prompt(task)
            if bot.get("memoryEnabled", True):
                memory_view = self.memory.get(bot["id"], query=task["prompt"])
                notes = memory_view.get("notes", [])
                budget = max(500, min(8000, int(bot.get("memoryBudgetTokens", 2000))))
                selected, used = [], 0
                for note in notes:
                    text = str(note.get("content") or "")
                    cost = max(1, len(text) // 4)
                    if used + cost > budget:
                        continue
                    selected.append(f"[{note.get('source')}/{note.get('kind')}] {text}")
                    used += cost
                task["memoryContext"] = "\n".join(selected)
            outcome = self.executor.start(task, bot, context)
            with self._lock:
                live = self._task(task["id"])
                live.update(outcome)
                live.pop("retry", None)
                live["status"] = "running"
                self._mailbox_receipt(live, "delivered")
                self._bot(bot["id"])["sessionId"] = outcome["sessionId"]
                self._message(task["id"], "progress", "Pi 已接收任务。", bot["id"])
                cancelled = live.get("cancelRequested") or self._stop.is_set()
                self._persist()
            if cancelled:
                self.executor.cancel(live)
        except Exception as exc:
            with self._lock:
                live = self._task(task["id"])
                message = exc.message if isinstance(exc, WebError) else "Pi 启动结果待检查，请查看本地会话诊断。"
                # This is the only replayable seam; `_finish` retries a
                # transient reason and otherwise keeps the prompt unmodified
                # for an explicit human resume.
                self._finish(live, "interrupted", message, error_code=getattr(exc, "code", ""),
                             error_detail=str(exc), error_status=getattr(exc, "status", None))
                self._persist()
        finally:
            self._workers.discard(threading.current_thread())

    def _observe(self, task, snapshot):
        if task["status"] in TERMINAL:
            return
        changed = False
        for event in snapshot.get("events", []):
            identity = event.get("id")
            if not identity:
                # Session events normally always carry an id.  Keep a stable
                # fallback for old/custom executors without turning every poll
                # into another message.
                identity = "e-" + hashlib.sha256(
                    json.dumps(event, sort_keys=True, ensure_ascii=False, default=str).encode()
                ).hexdigest()[:16]
            identity = str(identity)
            signature = json.dumps(
                {key: value for key, value in event.items() if key not in {"createdAt", "updatedAt"}},
                sort_keys=True,
                ensure_ascii=False,
                default=str,
            )
            if task.setdefault("seenEvents", {}).get(identity) == signature:
                continue
            task["seenEvents"][identity] = signature
            kind = str(event.get("kind") or "")
            message_type = {
                "assistant": "message",
                "tool": "progress",
                "notice": "progress",
                "approval": "approval",
                "error": "error",
                "wait": "wait",
                "waiting": "wait",
            }.get(kind)
            if not message_type:
                changed = True
                continue

            text = str(event.get("text") or "").strip()
            # Pi creates an empty assistant event at stream start.  It is a
            # lifecycle marker, not a Bot reply.  Do not persist it or let an
            # empty later update erase an already visible answer.
            if kind == "assistant" and not text:
                changed = True
                continue
            content = (str(event.get("title") or "") + "\n" + text).strip()[:32000]
            if not content:
                # Preserve explicit approval/wait/error events even when a
                # driver omitted their text, so actionable states stay visible.
                content = {"approval": "等待确认", "wait": "等待继续", "error": "执行错误"}.get(message_type, "")
            if not content:
                changed = True
                continue

            metadata = {
                key: deepcopy(value)
                for key, value in event.items()
                if key not in {"id", "kind", "text", "textAppend", "thinkingAppend", "createdAt", "updatedAt"}
            }
            metadata.update(sourceEventId=identity, sourceKind=kind, turn=task["turn"], type=message_type)
            existing = next((m for m in self._messages.get(task["id"], [])
                             if m.get("sourceEventId") == identity and m.get("turn") == task["turn"]), None)
            if existing:
                existing.update(content=content, **metadata, updatedAt=now())
            else:
                self._message(task["id"], message_type, content, task["botId"], **metadata)
            changed = True
        state = snapshot.get("state")
        if state == "waiting":
            if task["status"] != "waiting" or task.get("waitReason") != "approval":
                task.update(status="waiting", waitReason="approval", updatedAt=now())
                self._notify(task, "task.waiting", "approval", "Bot 在执行中等待你的确认。")
            changed = True
        elif state == "running":
            if task["status"] != "running":
                task.update(status="running", waitReason=None, error=None)
                changed = True
        elif state in {"idle", "completed", "error", "stopped"}:
            if state in {"idle", "completed"}:
                self._mailbox_receipt(task, "processed")
            self._capture_session_artifacts(task, snapshot.get("artifacts", []))
            if task.get("cancelRequested"):
                self._finish(task, "cancelled", "Pi 已停止本任务。")
            elif state in {"error", "stopped"}:
                self._finish(task, "failed" if state == "error" else "interrupted", "Pi 执行失败。" if state == "error" else "Pi 已停止，任务尚未完成。")
            elif task.get("declaredError"):
                self._finish(task, "failed", task["declaredError"])
            elif task.get("inbox"):
                task.update(status="queued", waitReason=None, resumeText="\n".join(task.pop("inbox")))
                self._bot(task["botId"])["status"] = "idle"
            elif any(self._task(c)["status"] not in TERMINAL for c in task.get("children", [])):
                task.update(status="waiting", waitReason="children")
                self._bot(task["botId"])["status"] = "idle"
            elif self._resume_children(task):
                self._bot(task["botId"])["status"] = "idle"
            elif task.get("waitRequested"):
                task.update(status="waiting", waitReason="user", token="")
                self._bot(task["botId"])["status"] = "idle"
                reason = next((m.get("content") for m in reversed(self._messages.get(task["id"], []))
                               if m.get("type") == "progress"), "")
                self._notify(task, "task.waiting", "input", reason or "Bot 在等你的输入。")
            else:
                bad = any(e.get("status") == "error" for e in snapshot.get("events", []) if e.get("kind") == "user")
                if bad:
                    self._finish(task, "failed", "Pi 未确认接收任务，请查看会话。")
                else:
                    answers = [e["text"] for e in snapshot.get("events", []) if e.get("kind") == "assistant" and e.get("text")]
                    if task.get("declaredResult") or answers:
                        self._finish(task, "completed", task.get("declaredResult") or answers[-1])
                    else:
                        self._finish(task, "failed", "本轮结束但没有收到结果。")
            changed = True
        if changed:
            task["updatedAt"] = now()
            self._persist()

    def _capture_session_artifacts(self, task, artifacts):
        for item in artifacts:
            if task.get("artifactBaseline", {}).get(item["id"]) == item.get("sha256"):
                continue
            rows = self._artifacts[task["id"]]
            if any(r.get("sessionArtifactId") == item["id"] and r.get("sha256") == item.get("sha256") for r in rows):
                continue
            aid = "artifact_" + uuid4().hex[:16]
            rows.append({"id": aid, "name": item["name"], "kind": "screenshot" if item["kind"] == "image" else "file",
                         "sha256": item.get("sha256"), "sessionArtifactId": item["id"], "sessionId": task["sessionId"],
                         "revision": item.get("revision", 1), "url": f"/api/v1/tasks/{task['id']}/artifacts/{aid}/content"})

    def list_artifacts(self, task_id):
        with self._lock:
            self._task(task_id)
            return [{k: v for k, v in deepcopy(a).items() if k not in {"path", "sessionArtifactId", "sessionId"}} for a in self._artifacts.get(task_id, [])]

    def screenshot(self, task_id, url=None):
        with self._lock:
            self._task(task_id)
        if not self.computer:
            raise WebError("SCREENSHOT_UNAVAILABLE", "Ego 截图组件尚未连接。", 409)
        item = self.computer.capture(task_id, url)
        with self._lock:
            aid = "artifact_" + uuid4().hex[:16]
            item.update(id=aid, url=f"/api/v1/tasks/{task_id}/artifacts/{aid}/content")
            self._artifacts[task_id].append(item)
            self._message(task_id, "progress", "已保存真实截图：" + item["name"], self._task(task_id)["botId"])
            self._persist()
            return {k: v for k, v in item.items() if k != "path"}

    def artifact_content(self, task_id, artifact_id):
        with self._lock:
            self._task(task_id)
            item = next((deepcopy(a) for a in self._artifacts.get(task_id, []) if a["id"] == artifact_id), None)
        if not item:
            raise WebError("ARTIFACT_NOT_FOUND", "找不到这个成果。", 404)
        if item.get("sessionArtifactId"):
            data = self.executor.artifact(item["sessionId"], item["sessionArtifactId"], item["revision"])
            content = base64.b64decode(data["downloadData"], validate=True) if data.get("downloadData") else base64.b64decode(data["content"], validate=True) if data.get("encoding") == "base64" else data.get("content", "").encode()
            return content, data.get("mimeType") or ("image/png" if data.get("kind") == "image" else "text/plain; charset=utf-8")
        path = Path(item.get("path") or "").resolve()
        if not path.is_relative_to((self.root / "screenshots").resolve()) or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
            raise WebError("ARTIFACT_FORBIDDEN", "成果路径不可读取。", 403)
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != item["sha256"]:
            raise WebError("ARTIFACT_CHANGED", "截图已改变，请重新生成。", 409)
        return content, "image/png" if item.get("kind") == "screenshot" else "text/plain; charset=utf-8"

    def artifact_html_preview(self, task_id, artifact_id):
        # Reuse Pilot's offline renderer and the same revision/hash-checked read.
        from .artifact_preview import offline_html
        with self._lock:
            self._task(task_id)
            item = next((a for a in self._artifacts.get(task_id, []) if a["id"] == artifact_id), None)
            if not item:
                raise WebError("ARTIFACT_NOT_FOUND", "找不到这个成果。", 404)
            if Path(item.get("name", "")).suffix.lower() not in {".html", ".htm"}:
                raise WebError("PREVIEW_UNAVAILABLE", "这个成果不是 HTML。", 400)
        content, _ = self.artifact_content(task_id, artifact_id)
        if len(content) > 1024 * 1024:
            raise WebError("PREVIEW_UNAVAILABLE", "HTML 预览最多支持 1 MB，请下载查看完整文件。", 400)
        try:
            return offline_html(content.decode("utf-8-sig"))
        except UnicodeError as exc:
            raise WebError("PREVIEW_UNAVAILABLE", "此文件不是 UTF-8 文本，请下载查看。", 400) from exc

    def authorize_worker(self, token):
        with self._lock:
            for task in self._tasks.values():
                if task.get("token") and secrets.compare_digest(token, task["token"]) and task["status"] in {"starting", "running", "waiting"}:
                    return task["id"]
        raise WebError("BOT_WORKER_UNAUTHORIZED", "Bot 工具凭据无效或任务已结束。", 403)

    def worker(self, task_id, payload):
        with self._lock:
            task = deepcopy(self._task(task_id))
        action = payload.get("action")
        if action == "list":
            return {"bots": [{k: b.get(k) for k in ("id", "name", "description", "model", "status")} for b in self.list_bots()]}
        if action in {"memory_list", "memory_search"}:
            query = str(payload.get("query") or payload.get("text") or "") if action == "memory_search" else ""
            with self._lock:
                bot = self._bot(task["botId"])
                settings = {k: bot.get(k, v) for k, v in (("memoryEnabled", True), ("memoryBudgetTokens", 2000), ("autoCompact", True), ("compactAtPercent", 70))}
            view = self.memory.get(task["botId"], query=query)
            view["settings"] = settings
            return view
        if action == "memory_remember":
            content = str(payload.get("content") or payload.get("text") or "").strip()
            if not content or len(content) > 2000:
                raise WebError("INVALID_REQUEST", "记忆内容不能为空且不超过 2,000 字。", 400)
            with self._lock:
                bot = self._bot(task["botId"])
                if not bot.get("memoryEnabled", True):
                    raise WebError("MEMORY_DISABLED", "这个 Bot 已关闭记忆。", 409)
            self.memory.remember(task["botId"], content, kind="fact", source="bot")
            return self.memory.get(task["botId"])
        if action == "memory_forget":
            self.memory.forget(task["botId"], str(payload.get("id") or ""))
            return self.memory.get(task["botId"])
        if action in {"message", "reply"}:
            return self.send_bot_message(task_id, {**payload, "content": payload.get("content") or payload.get("text") or ""})
        if action == "inbox":
            rows = self.list_communications(task["botId"])
            return {"messages": [r for r in rows if r["recipientBotId"] == task["botId"]][-50:]}
        if action == "dispatch":
            return self.create_task({"botId": payload.get("botId"), "prompt": payload.get("prompt") or payload.get("content") or payload.get("text"), "parentTaskId": task_id,
                                     "requestId": f"{task_id}:{payload.get('requestId') or uuid4().hex}"})
        if action == "screenshot":
            return self.screenshot(task_id, payload.get("url"))
        if action == "browser":
            if not self.computer:
                raise WebError("EGO_UNAVAILABLE", "当前没有可用的 Ego 浏览器。", 409)
            return self.computer.interact(task_id, str(payload.get("operation") or ""),
                                          payload.get("target"), payload.get("value"))
        if action == "status":
            target = str(payload.get("taskId") or task_id)
            with self._lock:
                ancestor = self._task(target)
                while ancestor["id"] != task_id and ancestor.get("parentTaskId"):
                    ancestor = self._task(ancestor["parentTaskId"])
                if ancestor["id"] != task_id:
                    raise WebError("BOT_SCOPE", "只能读取当前任务及其子任务。", 403)
            return self.get_task(target)
        if action in {"complete", "fail", "wait"}:
            content = str(payload.get("result") or payload.get("error") or payload.get("text") or payload.get("content") or payload.get("reason") or "")[:32000]
            with self._lock:
                live = self._task(task_id)
                if action == "complete":
                    live.update(declaredResult=content, waitRequested=False)
                elif action == "fail":
                    live["declaredError"] = content or "Bot 报告执行失败。"
                else:
                    live["waitRequested"] = True
                self._message(task_id, "progress", content or "等待后续结果。", task["botId"])
                self._persist()
            return {"ok": True, "taskId": task_id, "message": "已记录，最终状态以 Pi 本轮结束为准。"}
        raise WebError("BOT_ACTION_UNKNOWN", "不支持这个 Bot 工具。", 400)
