"""Durable, local Bot orchestration over real Pi sessions.

A completed model turn and user acceptance remain separate. No live mock
executor, retry-after-uncertain-launch, or arbitrary local-file serving.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import re
import threading
import time
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from .file_lock import LOCK_EX, LOCK_NB, flock

from .errors import WebError
from . import bot_schedules
from .bot_schedules import (MAX_SCHEDULES_PER_BOT, RECENT_TASK_LIMIT, advance, apply_update,
                            build_schedule, defer_once, is_due)
from .bot_executor import _context_percent
from .runtime import private_json
from .bot_memory import BotMemoryStore, BotMemoryError
from .bot_communications import BotCommunications
from .bot_coordinator import (plan_for, direct_plan, build_planner_prompt, parse_model_plan, sanitize_plan,
                              looks_multi_goal, set_plan_status, transition_plan, transition_step,
                              normalize_step_status)
from . import bot_retry
from .bot_notify import Notifier

TERMINAL = {"completed", "failed", "cancelled", "interrupted"}
PLAN_UNDO_SECONDS = 30
PLANNER_MODES = {"model", "keywords", "off"}
ORCHESTRATION_POLICIES = {"direct-first", "plan-approve", "off"}
MAX_TASKS = 2000
MAX_MESSAGES = 500
PIXEL_AVATAR_IDS = ("round", "cat", "puff", "cube", "leaf", "ghost", "rocket", "star", "bean", "bot",
                    "diamond", "hex", "ticket", "wave", "shield", "gem", "orbit", "sun")
PIXEL_AVATAR_COLORS = ("#b9a5ff", "#ff9f91", "#73dfc7", "#ffd77d", "#8bb8ff", "#f18bd5")
_COLLABORATION_HINTS = (
    "找", "派给", "分派", "协作", "并行", "让.*bot", "让.*同事", "请.*检查",
    r"让\s+(?!我|你|他|它|我们|自己)[A-Za-z0-9_-]{1,40}\s",
    r"让\s*(?!我|你|他|它|我们|自己)[\u4e00-\u9fff]{1,8}(?:帮|写|检查|处理|做|整理|核对|各)",
)


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


PEER_SYSTEM_STATES = {"interrupted", "cancelled"}


def peer_report(*, state, message, bot_name, outcome, system_failure=False):
    """What the other Bot sees when a dispatched task ends.

    A result is the Bot's one-line conclusion (``outcome.summary``, else the
    first 200 characters) plus an artifact index supplied by the caller. A
    runtime state — interrupted, cancelled, or Pi stopping before a result —
    is delivered as a system event, never dressed up as a deliverable.
    """
    if state in PEER_SYSTEM_STATES or (state == "failed" and system_failure):
        return "system", f"{bot_name} 的任务已中断，未产生结果"
    summary = (outcome or {}).get("summary") if isinstance(outcome, dict) else None
    return "result", str(summary or message or "")[:200]


# A waiting task must own a real question: a bare "waiting" status with
# nothing to answer is what left the sidebar pointing at an empty chat.
_QUESTION_ENDINGS = ("吗", "么", "呢", "对不对", "好不好", "有没有", "是不是")
_QUESTION_MARKERS = (
    # Question words may be followed by a noun (“哪些章节”), so they are
    # matched inside the tail rather than only at its end.
    "哪", "什么", "怎么", "怎样", "如何", "是否", "要不要", "能不能", "可不可以",
    "为什么", "多少", "多久",
    "请确认", "请提供", "请补充", "请说明", "请选择", "请告诉我", "请回复",
    # A second-person request also tells the user what to answer;
    # "需要你确认预算" is a question-shaped wait even without "？".
    "需要你", "需要您", "请你", "请您", "等你确认", "由你决定", "由你确认",
    "你确认", "你提供", "你补充", "你决定",
)
_TRIVIAL_TOKENS = ("收到", "明白", "已发送", "沟通完毕", "无待办", "先候着")
_WAIT_OPTIONS = re.compile(r"^\s*(?:选项|可选项)\s*[:：]\s*(.+)$")
MAX_WAIT_OPTIONS = 4
TRIVIAL_RESULT_CHARS = 120


def looks_like_question(text) -> bool:
    """Whether a Bot turn actually asks the user something.

    Used before entering ``waiting/user`` and when folding unreadable legacy
    records: a question mark anywhere, a question-shaped ending, or an
    explicit question form such as “是否…” / “请确认…”.
    """
    raw = str(text or "")
    if not raw.strip():
        return False
    if "?" in raw or "？" in raw:
        return True
    # A real model often asks first and explains afterwards, so every line and
    # sentence is checked, not only the tail of the whole message.
    for segment in re.split(r"[\n。!！.]+", raw):
        tail = " ".join(segment.split()).rstrip("~～ ")[-60:]
        if not tail:
            continue
        if tail.endswith(_QUESTION_ENDINGS):
            return True
        if any(marker in tail for marker in _QUESTION_MARKERS):
            return True
    return False


def is_trivial_result(text) -> bool:
    """A short acknowledgement or greeting is not worth a memory digest."""
    value = " ".join(str(text or "").split())
    if len(value) < TRIVIAL_RESULT_CHARS:
        return True
    return any(token in value for token in _TRIVIAL_TOKENS)


def parse_wait_text(text) -> tuple[str, list[str]]:
    """Split a wait message into (question, quick options).

    ``选项：A | B`` becomes quick replies; every other line stays the question.
    """
    question_lines: list[str] = []
    options: list[str] = []
    for line in str(text or "").splitlines():
        match = _WAIT_OPTIONS.match(line)
        if match and not options:
            options = [part.strip()[:200] for part in re.split(r"[|｜、,，]", match.group(1)) if part.strip()][:MAX_WAIT_OPTIONS]
            continue
        question_lines.append(line)
    return "\n".join(question_lines).strip(), options


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
        self._schedules, self._communications = {}, {}
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
            self._schedules = bot_schedules.sanitize_schedules(data.get("schedules"))
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
                bot.setdefault("planner", "model")
            self._migrate_wait_contracts()
            self._migrate_scheduled_tasks()
        except (OSError, ValueError, KeyError, TypeError):
            self._load_error = "Bot 记录无法读取，原文件已保留；请检查记录后再写入。"

    def _persist(self):
        if self._load_error:
            raise WebError("BOT_STORE_INVALID", self._load_error, 409)
        if not self._file_lock:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            handle = (self.root / "owner.lock").open("a+")
            try:
                flock(handle, LOCK_EX | LOCK_NB)
            except OSError:
                handle.close()
                raise WebError("BOT_STORE_BUSY", "另一个 Pilot 正在管理这份 Bot 记录。", 409) from None
            self._file_lock = handle
        private_json(self.root / "state.json", {"schema": 2, "bots": self._bots, "tasks": self._tasks,
                    "messages": self._messages, "artifacts": self._artifacts, "requests": self._requests,
                    "schedules": self._schedules, "communications": self._communications})
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
                        "orchestrationPolicy": payload.get("orchestrationPolicy", "direct-first"),
                        "planner": payload.get("planner", "model")})
            if bot["orchestrationPolicy"] not in ORCHESTRATION_POLICIES:
                raise WebError("INVALID_REQUEST", "orchestrationPolicy 必须是 direct-first、plan-approve 或 off。", 400)
            if bot["planner"] not in PLANNER_MODES:
                raise WebError("INVALID_REQUEST", "planner 必须是 model、keywords 或 off。", 400)
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
            bots = deepcopy(list(self._bots.values()))
            for bot in bots:
                bot["pendingQuestion"] = self._pending_question(bot["id"])
            return bots

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
            if "planner" in payload:
                if payload["planner"] not in PLANNER_MODES:
                    raise WebError("INVALID_REQUEST", "planner 必须是 model、keywords 或 off。", 400)
                updated["planner"] = payload["planner"]
            if "orchestrationPolicy" in payload:
                if payload["orchestrationPolicy"] not in ORCHESTRATION_POLICIES:
                    raise WebError("INVALID_REQUEST", "orchestrationPolicy 必须是 direct-first、plan-approve 或 off。", 400)
                updated["orchestrationPolicy"] = payload["orchestrationPolicy"]
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
            removed_schedules = {key for key, row in self._schedules.items() if row["botId"] == bot_id}
            self._schedules = {key: row for key, row in self._schedules.items() if key not in removed_schedules}
            removed_resources = task_ids | (old_communication_ids - set(self._communications)) | removed_schedules | {bot_id}
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
                if value in self._schedules:
                    return {**deepcopy(self._schedules[value]), "kind": "schedule"}
                return {**self.get_task(value), "kind": "task"}
            bot = self._bot(str(payload.get("botId") or ""))
            self.executor.validate(bot)
            if len(self._tasks) >= MAX_TASKS:
                raise WebError("TASK_LIMIT", "本地已保存 2,000 个任务，请归档后继续。", 409)
            parent_id = payload.get("parentTaskId")
            if parent_id and payload.get("runAt"):
                raise WebError("INVALID_REQUEST", "子任务不能定时执行。", 400)
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
            if run_at:
                # A one-off time is no longer a task state; it is its own
                # schedule entity, so the timer survives restarts and can be
                # listed, paused or deleted.
                schedule = self.create_schedule(bot["id"], {"prompt": prompt, "rule": {"kind": "once", "at": run_at}})
                self._remember(key, value, schedule["id"])
                return {**schedule, "kind": "schedule"}
            coordinator_plan = plan_for(prompt, bot, list(self._bots.values()))
            task = {"id": "task_" + uuid4().hex[:16], "botId": bot["id"],
                    "prompt": prompt, "parentTaskId": parent_id,
                    "status": "queued", "runAt": None, "children": [],
                    "result": None, "error": None, "acceptedAt": None, "sessionId": None, "waitReason": None,
                    "turn": 0, "createdAt": now(), "updatedAt": now(), "token": "", "seenEvents": {},
                    "priority": task_priority(payload), "queueReason": "等待调度",
                    "coordinatorPlan": coordinator_plan}
            task["executionMode"] = coordinator_plan["mode"]
            task["collaborationRequested"] = collaboration_requested(task["prompt"])
            task["outcome"] = None
            if payload.get("wake") is False:
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
            return {**self._view(task), "kind": "task"}

    def create_schedule(self, bot_id, payload):
        with self._lock:
            key, value = self._replay("schedule", payload)
            if key in self._requests:
                return deepcopy(self._schedule(bot_id, value))
            self._bot(bot_id)
            count = sum(1 for item in self._schedules.values() if item["botId"] == bot_id)
            schedule = build_schedule(bot_id, payload, existing_count=count,
                                      now=datetime.now(timezone.utc), created_by=payload.get("createdBy"))
            self._schedules[schedule["id"]] = schedule
            self._remember(key, value, schedule["id"])
            self._persist()
            return deepcopy(schedule)

    def list_schedules(self, bot_id):
        with self._lock:
            self._bot(bot_id)
            rows = [deepcopy(item) for item in self._schedules.values() if item["botId"] == bot_id]
            return sorted(rows, key=lambda item: str(item.get("createdAt") or ""))

    def update_schedule(self, bot_id, schedule_id, payload):
        with self._lock:
            updated = apply_update(self._schedule(bot_id, schedule_id), payload, now=datetime.now(timezone.utc))
            self._schedules[schedule_id] = updated
            self._persist()
            return deepcopy(updated)

    def delete_schedule(self, bot_id, schedule_id):
        with self._lock:
            self._schedule(bot_id, schedule_id)
            self._schedules.pop(schedule_id, None)
            self._persist()
            return {"deleted": True, "scheduleId": schedule_id}

    def set_schedule_enabled(self, bot_id, schedule_id, enabled):
        with self._lock:
            schedule = self._schedule(bot_id, schedule_id)
            schedule["enabled"] = bool(enabled)
            schedule["updatedAt"] = now()
            self._persist()
            return deepcopy(schedule)

    def _schedule(self, bot_id, schedule_id):
        schedule = self._schedules.get(schedule_id)
        if not schedule or schedule["botId"] != bot_id:
            raise WebError("SCHEDULE_NOT_FOUND", "找不到这条定时。", 404)
        return schedule

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
                    used_percent = _context_percent(usage)
                    context_window = usage.get("contextWindow")
                context_window = context_window or model.get("contextWindow")
                if used_percent is None and used_tokens is not None and context_window:
                    used_percent = round(float(used_tokens) / float(context_window) * 100, 1)
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

    def _pending_question(self, bot_id):
        """The latest answered-question contract for a Bot, or None.

        A ``waiting/user`` row without a question is legacy dirty data; it
        stays out so the sidebar never points at an empty chat.
        """
        rows = [task for task in self._tasks.values()
                if task["botId"] == bot_id and task["status"] == "waiting"
                and task.get("waitReason") == "user" and str(task.get("waitQuestion") or "").strip()]
        if not rows:
            return None
        task = max(rows, key=lambda item: str(item.get("waitSince") or item.get("updatedAt") or ""))
        return {"taskId": task["id"], "question": str(task["waitQuestion"]).strip(),
                "options": list(task.get("waitOptions") or []),
                "since": task.get("waitSince") or task.get("updatedAt")}

    def _migrate_wait_contracts(self):
        """Backfill older ``waiting/user`` rows so dirty data stops lighting up."""
        for task in self._tasks.values():
            if task["status"] != "waiting" or task.get("waitReason") != "user":
                continue
            task.setdefault("waitSince", task.get("updatedAt") or task.get("createdAt") or now())
            task.setdefault("waitOptions", [])
            if task.get("waitQuestion"):
                continue
            question, options = parse_wait_text(self._last_wait_text(task))
            if question and looks_like_question(question):
                task["waitQuestion"] = question[:2000]
                if options and not task["waitOptions"]:
                    task["waitOptions"] = options
            else:
                task["waitQuestion"] = ""

    def _migrate_scheduled_tasks(self):
        """Release legacy ``scheduled`` tasks into independent once-schedules.

        The schedule id is derived from the task id so a load that has not been
        persisted yet cannot create a second copy of the same migration.
        """
        stamp = datetime.now(timezone.utc)
        for task in self._tasks.values():
            if task.get("status") != "scheduled":
                continue
            note = "原来的定时时间无效，没有迁移；本任务改为等待手动唤醒。"
            try:
                run_at = parse_time(task.get("runAt"))
                count = sum(1 for item in self._schedules.values() if item["botId"] == task["botId"])
                if not run_at:
                    pass
                elif count >= MAX_SCHEDULES_PER_BOT:
                    note = "原来的定时没有迁移：这个 Bot 已达 20 条定时上限；本任务改为等待手动唤醒。"
                else:
                    schedule = build_schedule(task["botId"], {"prompt": task["prompt"], "rule": {"kind": "once", "at": run_at}},
                                              existing_count=count, now=stamp, created_by="user",
                                              schedule_id="sch_" + hashlib.sha256(task["id"].encode()).hexdigest()[:16])
                    self._schedules[schedule["id"]] = schedule
                    task["scheduleId"] = schedule["id"]
                    note = "原来的定时已迁移成独立的定时；本任务改为等待手动唤醒。"
            except Exception:
                # A broken legacy row must not stop the whole record loading.
                note = "原来的定时记录无法读取，没有迁移；本任务改为等待手动唤醒。"
            task.update(status="waiting", waitReason="manual", runAt=None, token="", updatedAt=now())
            self._message(task["id"], "system", note)

    def _last_wait_text(self, task):
        """The most recent user-facing text, used when no explicit question came."""
        rows = [row for row in self._messages.get(task["id"], [])
                if row.get("type") in {"progress", "message"} and str(row.get("content") or "").strip()]
        # Prefer this turn, so a question asked two rounds ago cannot be reused
        # as if the Bot had just asked it again.
        rows = [row for row in rows if row.get("turn") == task.get("turn")] or rows
        return str(rows[-1]["content"]).strip() if rows else ""

    def _record_wait_request(self, task, payload):
        """Explicit question/options from the wait tool; text stays the fallback."""
        # Every round starts from scratch: a stale question from an earlier
        # wait must never be shown as the one the Bot is asking now.
        question = str(payload.get("question") or "").strip()
        task["waitQuestion"] = question[:2000] if question else ""
        options = payload.get("options")
        task["waitOptions"] = ([str(item).strip()[:200] for item in options if str(item).strip()][:MAX_WAIT_OPTIONS]
                               if isinstance(options, list) else [])
        task["waitRequested"] = True

    def _enter_user_wait(self, task):
        """Enter ``waiting/user`` only with a real question.

        Without one the turn is closed as completed and ``waitDeclined`` is
        recorded for diagnosis, so the sidebar never points at an empty chat.
        """
        text = str(task.get("waitQuestion") or "").strip() or self._last_wait_text(task)
        question, options = parse_wait_text(text)
        if not question or not looks_like_question(question):
            task["waitDeclined"] = True
            task["waitRequested"] = False
            self._finish(task, "completed", question or text or "本轮没有需要用户补充的问题。")
            return False
        task.update(status="waiting", waitReason="user", token="", waitQuestion=question[:2000],
                    waitOptions=(list(task.get("waitOptions") or []) or options)[:MAX_WAIT_OPTIONS],
                    waitSince=now())
        self._bot(task["botId"])["status"] = "idle"
        self._notify(task, "task.waiting", "input", question)
        return True

    def wait_action(self, task_id, payload):
        """Answer or dismiss a ``waiting/user`` task from the Web UI.

        ``answer`` reuses the ordinary message path, so the reply resumes the
        same task; ``dismiss`` closes it as completed without a session turn.
        """
        with self._lock:
            task = self._task(task_id)
            if task["status"] != "waiting" or task.get("waitReason") != "user":
                raise WebError("TASK_NOT_WAITING", "这条任务现在不在等用户回复。", 409)
            action = str((payload or {}).get("action") or "").strip()
            if action == "answer":
                text = text_field(payload, "text", 32000, True)
                task["waitAnsweredAt"] = now()
                task.update(waitQuestion="", waitOptions=[], waitSince=None)
                return self.add_message(task_id, {"content": text})
            if action == "dismiss":
                task["waitDismissed"] = True
                self._finish(task, "completed", "等待已结束。")
                self._persist()
                return self._view(task)
            raise WebError("INVALID_REQUEST", "action 必须是 answer 或 dismiss。", 400)

    def _should_remember_task(self, task, message):
        """Only a task with a durable outcome is worth a memory digest."""
        outcome = task.get("outcome") if isinstance(task.get("outcome"), dict) else {}
        summary = str(outcome.get("summary") or "").strip()
        # ``summary`` falls back to the raw text; only an explicit 结论 section
        # counts as a structured conclusion here.
        structured = (bool(summary) and summary != str(outcome.get("raw") or "").strip()) \
            or bool(str(outcome.get("changes") or "").strip())
        artifacts = bool(self._artifacts.get(task["id"]))
        if task.get("deliveryMessageIds") and not artifacts and not structured:
            return False
        return structured or artifacts or not is_trivial_result(message)

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
            if task["status"] in {"scheduled", "interrupted", "failed", "waiting"} and task.get("waitReason") not in {"approval", "connection", "stopping", "plan-approval"}:
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

    def _finish(self, task, state, message, *, error_code="", error_detail="", error_status=None, system_failure=False):
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
                system_failure = True
        task.pop("retry", None)
        task.update(status=state, updatedAt=now(), completedAt=now(), token="", waitReason=None,
                    waitQuestion="", waitOptions=[], waitSince=None)
        plan = task.get("coordinatorPlan")
        if plan and plan.get("status") in {"auto", "approved", "running", "merging"}:
            self._settle_plan_on_finish(plan, state)
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
                if bot.get("memoryEnabled", True) and self._should_remember_task(task, message):
                    digest = f"任务 {task['id']}：{task.get('prompt','')[:600]}\n结果：{message[:1200]}"
                    self.memory.remember(task["botId"], digest, kind="task", source="task", task_id=task["id"])
            except Exception:
                pass
        if task.get("parentTaskId"):
            parent = self._task(task["parentTaskId"])
            # The peer gets a structured conclusion plus an artifact index; the
            # model's raw report and runtime status text stay in the task log.
            report_type, report_text = peer_report(
                state=state, message=message, bot_name=self._bot(task["botId"])["name"],
                outcome=task.get("outcome"), system_failure=system_failure)
            self._message(parent["id"], report_type, report_text, task["botId"], childTaskId=task["id"],
                          artifacts=self._peer_artifacts(task) if state == "completed" else [])
            parent["childrenChanged"] = True
            parent_plan = parent.get("coordinatorPlan") or {}
            if parent_plan.get("mode") == "delegate" and parent_plan.get("steps"):
                if self._sync_plan_steps(parent, parent_plan) and parent_plan.get("status") in {"done", "failed", "cancelled"}:
                    parent["childResults"] = self._child_results(parent, parent_plan)
        if state in {"completed", "failed"}:
            self._notify(task, "task.completed" if state == "completed" else "task.failed")

    def _notify(self, task, event_type, wait_reason=None, note=""):
        """Best-effort delivery; a broken receiver never fails the task."""
        try:
            self.notifier.emit_task(self._bot(task["botId"]), task, event_type, wait_reason, note)
        except Exception:
            pass

    def _peer_artifacts(self, task):
        """Artifact index for a peer report; local paths and hashes stay out."""
        return [{"id": item["id"], "name": item.get("name", ""), "kind": item.get("kind", "file"),
                 "taskId": task["id"]} for item in self._artifacts.get(task["id"], [])]

    def _resume_children(self, task):
        if not task.get("childrenChanged") or not task.get("children"):
            return False
        children = [self._task(t) for t in task["children"]]
        if any(c["status"] not in TERMINAL for c in children):
            return False
        plan = task.get("coordinatorPlan") or {}
        if plan.get("mode") == "delegate" and plan.get("status") in {"done", "failed", "cancelled", "rejected"}:
            return False
        if task.get("planResolved") and plan.get("mode") == "delegate":
            # A step that is still pending/ready/running has work left; the
            # parent resumes only when the plan has nothing more to dispatch.
            if any(normalize_step_status(step.get("status")) in {"pending", "ready", "running"}
                   for step in plan.get("steps", [])):
                return False
        self._queue_parent_merge(task, plan)
        return True

    def _step_result(self, step, child):
        """Structured per-step result: summary plus whatever the child has."""
        outcome = child.get("outcome") or {}
        summary = str(outcome.get("summary") or child.get("result") or child.get("error") or "")[:600]
        result = {"summary": summary}
        if outcome.get("summary"):
            result["conclusion"] = str(outcome["summary"])[:4000]
        if outcome.get("evidence"):
            result["evidence"] = str(outcome["evidence"])[:4000]
        artifacts = [{"taskId": child["id"], "url": item.get("url"), "label": item.get("name", "")}
                     for item in self._artifacts.get(child["id"], []) if item.get("url")][:20]
        if artifacts:
            result["artifacts"] = artifacts
        return result

    def _child_results(self, task, plan):
        """Task-level mirror of steps[].result so the frontend reads it once."""
        rows = []
        seen = set()
        if plan.get("mode") == "delegate":
            for step in plan.get("steps", []):
                task_id = step.get("taskId")
                if task_id:
                    seen.add(task_id)
                result = step.get("result") or {}
                row = {"stepId": step.get("id"), "botId": step.get("botId"), "taskId": task_id,
                       "status": normalize_step_status(step.get("status")),
                       "summary": str(result.get("summary") or step.get("error") or "")[:600]}
                if result.get("evidence"):
                    row["evidence"] = result["evidence"]
                if result.get("artifacts"):
                    row["artifacts"] = result["artifacts"]
                rows.append(row)
        for child_id in task.get("children", []):
            if child_id in seen or child_id not in self._tasks:
                continue
            child = self._tasks[child_id]
            outcome = child.get("outcome") or {}
            rows.append({"taskId": child_id, "botId": child.get("botId"), "status": child.get("status"),
                         "summary": str(outcome.get("summary") or child.get("result") or child.get("error") or "")[:600]})
        return rows

    def _queue_parent_merge(self, task, plan):
        """Queue the owner's merge turn with per-step summaries. Runs once per
        generation of children; planExecutedAt/resumedAt/childrenChanged and
        the plan-terminal guard keep restarts from resuming twice."""
        child_results = self._child_results(task, plan)
        lines = []
        for index, row in enumerate(child_results, 1):
            name = str((self._bots.get(row.get("botId") or "") or {}).get("name") or row.get("botId") or "")
            label = row.get("stepId") or row.get("taskId")
            lines.append(f"{index}. [{label} · {name} · {row.get('status')}] {row.get('summary') or '（无摘要）'}")
        if task.get("planResolved") and plan.get("mode") == "delegate":
            transition_plan(plan, "merging", by="system")
            task["coordinatorPlan"] = plan
        task["childResults"] = child_results
        task["resumedAt"] = now()
        task.update(status="queued", waitReason=None, childrenChanged=False,
                    resumeText="子任务均已回传，请检查成果并总结。\n" + "\n".join(lines))
        self._message(task["id"], "system", "子任务已回传，自动唤醒发起 Bot。")

    def plan_task(self, task, bot):
        """Decide and persist the durable plan before a task's session starts.

        planner=model (default) makes one short throwaway call on the task
        Bot's own preset with a hard 20s budget; parse failure, unavailability
        or timeout falls back to the deterministic keyword plan. The decision
        is persisted exactly once (planResolved) and never replanned.
        """
        with self._lock:
            live = self._task(task["id"])
            if live.get("planResolved"):
                return deepcopy(live.get("coordinatorPlan"))
            prompt = live["prompt"]
            planner = bot.get("planner", "model")
            policy = bot.get("orchestrationPolicy", "direct-first")
            bots_snapshot = deepcopy(list(self._bots.values()))
            # direct-first stays cheap: only an explicit collaboration signal
            # or a multi-goal shape pays for the throwaway model planner.
            wants_plan = bool(live.get("collaborationRequested")) or looks_multi_goal(
                prompt, bots_snapshot, owner_id=bot.get("id"))
        memory_summary = ""
        if planner == "model" and policy != "off" and wants_plan and bot.get("memoryEnabled", True):
            try:
                notes = self.memory.get(bot["id"], query=prompt).get("notes", [])
                memory_summary = "\n".join(str(note.get("content") or "") for note in notes[:5])[:2000]
            except Exception:
                memory_summary = ""
        if planner == "off" or policy == "off":
            plan = direct_plan(bot, "已按设置关闭自动分工，由当前 Bot 直接完成。", "off")
        elif not wants_plan:
            plan = direct_plan(bot, "普通任务由当前 Bot 直接完成。", "direct-first")
        elif planner == "keywords" or not hasattr(self.executor, "plan"):
            plan = plan_for(prompt, bot, bots_snapshot)
            plan["source"] = "keywords"
        else:
            plan = None
            try:
                history = self._recent_task_titles(bots_snapshot, exclude=bot.get("id"))
                reply = self.executor.plan(build_planner_prompt(prompt, bot, bots_snapshot, memory_summary, history), bot)
                if reply:
                    plan = parse_model_plan(reply, bot, bots_snapshot)
            except Exception:
                plan = None
            if plan is None:
                plan = plan_for(prompt, bot, bots_snapshot)
                plan["source"] = "fallback"
        set_plan_status(plan, "proposed" if plan["mode"] == "delegate" and policy == "plan-approve" else "auto")
        with self._lock:
            live = self._task(task["id"])
            if live.get("planResolved"):
                return deepcopy(live.get("coordinatorPlan"))
            live.update(coordinatorPlan=plan, executionMode=plan["mode"], planResolved=True,
                        planDecidedAt=now(), orchestrationPolicy=policy, updatedAt=now())
            self._persist()
            return deepcopy(plan)

    def _recent_task_titles(self, bots, exclude=None):
        """Up to three recent completed task titles per Bot, for the planner."""
        wanted = {bot.get("id") for bot in bots if bot.get("id") and bot.get("id") != exclude}
        history = {bot_id: [] for bot_id in wanted}
        with self._lock:
            completed = [t for t in self._tasks.values()
                         if t.get("botId") in wanted and t.get("status") == "completed"]
        completed.sort(key=lambda t: str(t.get("completedAt") or ""), reverse=True)
        for task in completed:
            titles = history[task["botId"]]
            if len(titles) >= 3:
                continue
            title = str(task.get("prompt") or "").strip().splitlines()[0][:60] if task.get("prompt") else ""
            if title:
                titles.append(title)
        return history

    def _advance_plan(self, task):
        """Dispatch plan steps whose dependencies are done. Never recreates a
        step that already has a taskId; reconciles by (parentTaskId, step.id)
        so a restart cannot duplicate a dispatched step. Returns changed."""
        plan = task.get("coordinatorPlan") or {}
        if plan.get("mode") != "delegate" or not task.get("planResolved"):
            return False
        steps = plan.get("steps") or []
        by_id = {step.get("id"): step for step in steps}
        changed = self._sync_plan_steps(task, plan)
        # Phase 2: per-step failure policy while the plan is still active.
        if plan.get("status") in {"auto", "approved", "running"}:
            for step in steps:
                if step.get("status") != "failed" or step.get("policyApplied"):
                    continue
                step["policyApplied"] = True
                policy = step.get("onFailure") or "retry"
                changed = True
                if policy == "skip":
                    step["status"] = "skipped"
                    self._skip_dependents(steps, by_id, step["id"])
                    continue
                # retry: the child already spent its T3 retry budget before
                # reaching a terminal state, so an exhausted retry is abort.
                for other in steps:
                    if other is not step and other.get("status") in {"pending", "ready"}:
                        other["status"] = "skipped"
                        other["result"] = {"summary": "计划中止，本步骤未执行。"}
                transition_plan(plan, "failed", by=f"step:{step['id']}")
                self._resume_plan_failure(task, plan, step)
                return True
        # Phase 3: a step whose dependency was skipped can never run.
        for step in steps:
            if step.get("status") == "pending" and any(
                    by_id.get(dep, {}).get("status") == "skipped" for dep in step.get("dependsOn", [])):
                step["status"] = "skipped"
                step["result"] = {"summary": "前置步骤被跳过，本步骤未执行。"}
                changed = True
        # Phase 4: dispatch ready steps (pending -> ready -> running).
        if plan.get("status") == "running":
            for step in steps:
                if step.get("status") not in {"pending", "ready"}:
                    continue
                # A skipped prerequisite is settled, not pending: otherwise a
                # dependent step waits forever after skip-step.
                if any(normalize_step_status(by_id.get(dep, {}).get("status")) not in {"done", "skipped"}
                       for dep in step.get("dependsOn", [])):
                    continue
                step["status"] = "ready"
                attempt = step.get("attempts", 1)
                try:
                    child = self.create_task({"botId": step["botId"], "prompt": step["goal"], "parentTaskId": task["id"],
                                              "requestId": f"plan:{task['id']}:{step['id']}:{attempt}"})
                except WebError as exc:
                    step["status"] = "failed"
                    step["error"] = exc.message
                    changed = True
                    continue
                step["taskId"] = child["id"]
                step["status"] = "running"
                self._tasks[child["id"]]["planStepId"] = step["id"]
                if step.get("presetId"):
                    self._tasks[child["id"]]["presetIdOverride"] = step["presetId"]
                changed = True
        if changed:
            task["updatedAt"] = now()
        return changed

    def _sync_plan_steps(self, task, plan):
        """Phase 1 of plan advance: normalize legacy statuses, link steps to
        children, and sync terminal child outcomes into step status +
        structured result. Also called from _finish so a child that finishes
        after an abort/cancel still updates the result graph."""
        steps = plan.get("steps") or []
        changed = False
        children = [self._tasks[c] for c in task.get("children", []) if c in self._tasks]
        for step in steps:
            normalized = normalize_step_status(step.get("status"))
            if normalized != step.get("status"):
                step["status"] = normalized
                changed = True
            child = self._tasks.get(step.get("taskId") or "")
            if child is None:
                # Reconcile by (parentTaskId, step.id): a live child always
                # links back; a terminal one only explains a step already
                # recorded as running, so a retried step gets a fresh child.
                match = next((c for c in children
                              if c.get("planStepId") == step.get("id") and c["status"] not in TERMINAL), None)
                if match is None and step["status"] == "running":
                    match = next((c for c in children if c.get("planStepId") == step.get("id")), None) or \
                            next((c for c in children if c["botId"] == step.get("botId") and c.get("prompt") == step.get("goal")), None)
                if match:
                    step["taskId"] = match["id"]
                    child = match
                    changed = True
            if child is None:
                continue
            if child["status"] not in TERMINAL:
                if step["status"] in {"pending", "ready"}:
                    step["status"] = "running"
                    changed = True
                continue
            if step["status"] in {"done", "failed", "skipped"}:
                continue
            if child["status"] == "completed":
                step["status"] = "done"
                step["result"] = self._step_result(step, child)
                changed = True
            elif child["status"] == "interrupted":
                # A restart or stop interrupted the child. It is not a plan
                # failure: the step waits for an explicit wake, skip or retry.
                step["status"] = "running"
                changed = True
            else:
                step["status"] = "failed"
                step["error"] = str(child.get("error") or "子任务未成功结束。")[:500]
                step["result"] = self._step_result(step, child)
                changed = True
        return changed

    def _skip_dependents(self, steps, by_id, skipped_id):
        """Cascade: pending steps depending on a skipped step never run."""
        frontier = {skipped_id}
        while frontier:
            newly = set()
            for step in steps:
                if step.get("status") in {"pending", "ready"} and frontier & set(step.get("dependsOn", [])):
                    step["status"] = "skipped"
                    step["result"] = {"summary": "前置步骤被跳过，本步骤未执行。"}
                    newly.add(step["id"])
            frontier = newly

    def _resume_plan_failure(self, task, plan, failed_step):
        """abort: wake the owner once to report which step failed."""
        name = str((self._bots.get(failed_step.get("botId") or "") or {}).get("name") or failed_step.get("botId") or "")
        reason = str(failed_step.get("error") or "")
        task["childResults"] = self._child_results(task, plan)
        task["resumedAt"] = now()
        task.update(status="queued", waitReason=None, childrenChanged=False,
                    resumeText=f"分工计划已中止：步骤 {failed_step['id']}（{name}）失败。{reason} "
                               "请用一两句话告诉用户哪一步失败、可能原因，并询问要不要换模型或换人重试；"
                               "不要重复创建已失败的子任务。")
        self._message(task["id"], "system", f"分工计划中止：{name} 执行的步骤失败。")

    def _settle_plan_on_finish(self, plan, state):
        """Plan mirror of the owner task's own terminal state."""
        steps = plan.get("steps") or []
        if plan.get("mode") == "direct" and steps:
            # The owner does a direct plan's only step itself, so nothing else
            # would ever move it off "pending".
            if state == "completed":
                steps[0]["status"] = "done"
            elif state in {"failed", "interrupted"}:
                steps[0]["status"] = "failed"
        if plan.get("mode") == "delegate" and any(
                normalize_step_status(step.get("status")) in {"pending", "ready", "running"} for step in steps):
            return  # Children still active; the plan settles at the merge turn.
        if state == "completed":
            for target in ("running", "merging", "done"):
                if plan.get("status") == target:
                    continue
                transition_plan(plan, target, by="system")
        elif state in {"failed", "interrupted"}:
            for target in ("running", "failed"):
                if plan.get("status") == target:
                    continue
                transition_plan(plan, target, by="system")
        elif state == "cancelled":
            transition_plan(plan, "cancelled", by="user")

    def _settle_plan_after_action(self, task, plan):
        """After retry-step/skip-step: wait for active steps or resume merge."""
        steps = plan.get("steps") or []
        active = any(normalize_step_status(step.get("status")) in {"pending", "ready", "running"}
                     for step in steps)
        if active:
            if task["status"] in TERMINAL:
                task.update(status="waiting", waitReason="children", completedAt=None,
                            acceptedAt=None, error=None, updatedAt=now())
            return
        task["childrenChanged"] = True
        if self._resume_children(task):
            return
        # Nothing left to wait for (all steps done/skipped without children):
        # queue the merge turn directly.
        self._queue_parent_merge(task, plan)

    def plan_action(self, task_id, payload):
        """User decision on a visible plan: approve, reject, replace, cancel,
        or per-step retry-step/skip-step."""
        action = payload.get("action")
        if action not in {"approve", "reject", "replace", "cancel", "retry-step", "skip-step"}:
            raise WebError("INVALID_REQUEST", "计划操作必须是 approve、reject、replace、cancel、retry-step 或 skip-step。", 400)
        with self._lock:
            task = self._task(task_id)
            plan = task.get("coordinatorPlan") or {}
            if not task.get("planResolved") or plan.get("mode") != "delegate":
                raise WebError("PLAN_NOT_ACTIONABLE", "这个任务没有可操作的协作计划。", 409)
            status = plan.get("status")
            if status in {"rejected", "done", "cancelled"}:
                raise WebError("PLAN_NOT_ACTIONABLE", "计划已处理，不能重复操作。", 409)
            if action == "retry-step":
                return self._plan_retry_step(task, plan, payload)
            if action == "skip-step":
                return self._plan_skip_step(task, plan, payload)
            if action == "cancel":
                return self._plan_cancel(task, plan)
            if status == "failed" and action != "reject":
                raise WebError("PLAN_NOT_ACTIONABLE", "计划已中止，只能用 retry-step 或 skip-step 处理失败步骤。", 409)
            if action == "replace":
                candidate = sanitize_plan(payload.get("plan"), self._bot(task["botId"]), list(self._bots.values()), "user")
                if not candidate:
                    raise WebError("INVALID_PLAN", "替换计划无效：子任务必须指向其它已存在的 Bot 并带有明确目标。", 400)
                if status != "proposed":
                    raise WebError("PLAN_NOT_ACTIONABLE", "计划已开始执行，请先撤回再替换。", 409)
                set_plan_status(candidate, "proposed", by="user")
                task["coordinatorPlan"] = candidate
                plan = candidate
            if action == "reject":
                if status == "proposed":
                    pass
                elif status in {"auto", "approved", "running"}:
                    decided = parse_time(task.get("planExecutedAt") or task.get("planDecidedAt"))
                    elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(decided)).total_seconds() if decided else PLAN_UNDO_SECONDS + 1
                    if elapsed > PLAN_UNDO_SECONDS:
                        raise WebError("PLAN_UNDO_EXPIRED", "计划已开始执行超过 30 秒，不能再撤回；可在任务里取消子任务。", 409)
                    for child_id in list(task.get("children", [])):
                        if self._tasks.get(child_id) and self._tasks[child_id]["status"] not in TERMINAL:
                            self.cancel_task(child_id)
                    task.update(children=[], childrenChanged=False)
                else:
                    raise WebError("PLAN_NOT_ACTIONABLE", "当前状态不能撤回计划。", 409)
                transition_plan(plan, "rejected", by="user")
                plan["mode"] = "direct"
                task.update(coordinatorPlan=plan, executionMode="direct", status="queued", waitReason=None,
                            acceptedAt=None, updatedAt=now(),
                            resumeText="用户拒绝了分工计划，请由你自己直接完成任务；不要重复创建已取消的子任务。")
                self._message(task_id, "system", "已拒绝分工计划，由当前 Bot 直接执行。")
                self._persist()
                return self._view(task)
            transition_plan(plan, "approved", by="user")
            transition_plan(plan, "running", by="system")
            task["coordinatorPlan"] = plan
            self._advance_plan(task)
            task["planExecutedAt"] = now()
            if task.get("children"):
                task.update(status="waiting", waitReason="children", updatedAt=now())
                self._bot(task["botId"])["status"] = "idle"
                self._message(task_id, "system", "分工计划已确认，子任务开始执行。")
            else:
                task.update(coordinatorPlan={**plan, "mode": "direct"}, executionMode="direct",
                            status="queued", waitReason=None, updatedAt=now(),
                            resumeText="计划中没有可执行的子任务，请由你自己直接完成任务。")
            self._persist()
            return self._view(task)

    def _plan_step(self, plan, payload):
        step_id = str(payload.get("stepId") or "")
        step = next((s for s in plan.get("steps", []) if s.get("id") == step_id), None)
        if not step:
            raise WebError("INVALID_REQUEST", "找不到这个计划步骤。", 400)
        step["status"] = normalize_step_status(step.get("status"))
        return step

    def _plan_retry_step(self, task, plan, payload):
        """Re-dispatch a failed step: failed -> ready -> running, plan reopens."""
        step = self._plan_step(plan, payload)
        if step.get("status") != "failed":
            raise WebError("PLAN_NOT_ACTIONABLE", "只有失败的步骤可以重试。", 409)
        if plan.get("status") == "failed":
            transition_plan(plan, "running", by="user")
        if plan.get("status") != "running":
            raise WebError("PLAN_NOT_ACTIONABLE", "当前状态不能重试步骤。", 409)
        transition_step(step, "ready")
        step["taskId"] = None
        step["attempts"] = step.get("attempts", 1) + 1
        step.pop("error", None)
        step.pop("result", None)
        step.pop("policyApplied", None)
        task["coordinatorPlan"] = plan
        self._advance_plan(task)
        task["planExecutedAt"] = task.get("planExecutedAt") or now()
        self._settle_plan_after_action(task, plan)
        self._message(task["id"], "system", f"已重新派发步骤 {step['id']}。")
        self._persist()
        return self._view(task)

    def _plan_skip_step(self, task, plan, payload):
        """Mark a step skipped and let the rest of the plan move on."""
        step = self._plan_step(plan, payload)
        if step.get("status") not in {"pending", "ready", "failed"}:
            raise WebError("PLAN_NOT_ACTIONABLE", "只有未开始或失败的步骤可以跳过。", 409)
        if plan.get("status") not in {"running", "failed"}:
            raise WebError("PLAN_NOT_ACTIONABLE", "当前状态不能跳过步骤。", 409)
        transition_step(step, "skipped")
        step["policyApplied"] = True
        step["result"] = {"summary": "用户跳过了这个步骤。"}
        by_id = {s.get("id"): s for s in plan.get("steps", [])}
        self._skip_dependents(plan.get("steps", []), by_id, step["id"])
        if plan.get("status") == "failed" and not any(
                normalize_step_status(s.get("status")) in {"pending", "ready", "running"} for s in plan.get("steps", [])):
            transition_plan(plan, "running", by="user")
        task["coordinatorPlan"] = plan
        self._settle_plan_after_action(task, plan)
        self._message(task["id"], "system", f"已跳过步骤 {step['id']}。")
        self._persist()
        return self._view(task)

    def _plan_cancel(self, task, plan):
        """Cancel the whole plan: stop running children, wake the owner once."""
        if plan.get("status") not in {"proposed", "auto", "approved", "running"}:
            raise WebError("PLAN_NOT_ACTIONABLE", "当前状态不能取消计划。", 409)
        transition_plan(plan, "cancelled", by="user")
        for step in plan.get("steps", []):
            if normalize_step_status(step.get("status")) in {"pending", "ready"}:
                step["status"] = "skipped"
                step["result"] = {"summary": "计划已取消，本步骤未执行。"}
        for child_id in list(task.get("children", [])):
            if self._tasks.get(child_id) and self._tasks[child_id]["status"] not in TERMINAL:
                self.cancel_task(child_id)
        task["childResults"] = self._child_results(task, plan)
        task["resumedAt"] = now()
        task.update(coordinatorPlan=plan, status="queued", waitReason=None, childrenChanged=False,
                    acceptedAt=None, updatedAt=now(),
                    resumeText="用户取消了分工计划；进行中的子任务已停止。请直接告诉用户计划已取消，"
                               "不要重复创建已取消的子任务。")
        self._message(task["id"], "system", "分工计划已取消。")
        self._persist()
        return self._view(task)

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
            # _advance_plan may create child tasks; iterate over a snapshot.
            for task in list(self._tasks.values()):
                if task.get("orphanAlive") and not self.executor.orphan_alive(task):
                    task["orphanAlive"] = False
                    changed = True
                if task["status"] == "waiting" and task.get("waitReason") == "user" and task.get("waitSince"):
                    # A question nobody answered for a week is not a pending
                    # conversation any more; close it instead of glowing forever.
                    try:
                        stale = datetime.fromisoformat(task["waitSince"]) <= datetime.now(timezone.utc) - timedelta(days=7)
                    except (TypeError, ValueError):
                        stale = False
                    if stale:
                        task["waitDismissed"] = True
                        self._message(task["id"], "system", "等待超过 7 天，已自动结束。")
                        self._finish(task, "completed", "等待超时，已结束")
                        changed = True
                        continue
                if task["status"] == "waiting" and task.get("waitReason") == "children":
                    changed = self._advance_plan(task) or changed
                    changed = self._resume_children(task) or changed
            busy = [t for t in self._tasks.values() if t.get("orphanAlive") or t["status"] in {"starting", "running"} or (t["status"] == "waiting" and t.get("waitReason") not in {"children", "manual", "user", "plan-approval"})]
            busy_bots = {t["botId"] for t in busy}
            busy_workspaces = {self._bot(t["botId"])["workspaceId"] for t in busy}
            now_dt = datetime.now(timezone.utc)
            for schedule in list(self._schedules.values()):
                if not is_due(schedule, now_dt):
                    continue
                bot = self._bots.get(schedule["botId"])
                armed = bool(bot and bot.get("wakeEnabled", True) and schedule["enabled"])
                holding = bool(bot and bot["id"] in busy_bots and schedule.get("overlapPolicy", "skip") == "skip")
                due_at = schedule.get("nextRunAt")
                if schedule["rule"]["kind"] == "once" and (not armed or holding):
                    # A one-shot gets exactly one chance: keep its due time and
                    # record why it waits instead of silently consuming it.
                    parked = defer_once(schedule, stamp=now(), reason="paused" if not armed else "busy")
                    if parked:
                        self._schedules[parked["id"]] = parked
                        changed = True
                    continue
                updated, skipped = advance(schedule, now=now_dt)
                reason = "" if not armed else ("上一轮仍在运行" if holding else (f"错过了 {skipped} 次触发" if skipped else ""))
                fired = None
                try:
                    fired = self.create_task({"botId": bot["id"], "prompt": updated["prompt"]}) if armed and not holding and not skipped else None
                except Exception:
                    fired, reason = None, "创建任务失败"
                if fired:
                    self._tasks[fired["id"]]["scheduleId"] = updated["id"]
                    if (schedule.get("lastSkip") or {}).get("reason") in {"paused", "busy"}:
                        self._message(fired["id"], "system", f"这条定时原定 {due_at} 触发，因暂停或上一轮未结束而延后，现在补触发。")
                    updated.update(lastRunAt=now(), lastTaskId=fired["id"], lastSkip=None,
                                   recentTaskIds=(updated.get("recentTaskIds") or [])[-(RECENT_TASK_LIMIT - 1):] + [fired["id"]])
                elif reason:
                    updated["lastSkip"] = {"at": now(), "reason": "busy" if holding else ("missed" if skipped else "error"), "skipped": skipped}
                    if updated.get("lastTaskId"):
                        self._message(updated["lastTaskId"], "system", f"定时没有执行（{reason}），已按规则跳过。")
                updated["updatedAt"] = now()
                self._schedules[updated["id"]] = updated
                changed = True
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
            # The plan gate runs in this worker thread (never inside the
            # scheduler lock) and is bounded by the planner timeout; a
            # planning failure must never block the task itself.
            if not task.get("planResolved"):
                try:
                    # Keep direct-first lightweight: a normal request should
                    # use the Bot's persistent session immediately. The
                    # throwaway model planner is reserved for an explicit
                    # collaboration request, a multi-goal shaped prompt, or an
                    # opt-in approval policy.
                    with self._lock:
                        peek = self._task(task["id"])
                        multi_goal = looks_multi_goal(peek["prompt"], list(self._bots.values()), owner_id=bot.get("id"))
                    if (bot.get("planner", "model") == "model"
                            and bot.get("orchestrationPolicy", "direct-first") == "direct-first"
                            and not task.get("collaborationRequested")
                            and not multi_goal):
                        with self._lock:
                            live = self._task(task["id"])
                            if not live.get("planResolved"):
                                plan = direct_plan(bot, "普通任务由当前 Bot 直接完成。", "direct-first")
                                set_plan_status(plan, "auto")
                                live.update(coordinatorPlan=plan, executionMode="direct",
                                            planResolved=True, planDecidedAt=now(), updatedAt=now())
                                self._persist()
                    else:
                        self.plan_task(task, bot)
                except Exception:
                    with self._lock:
                        live = self._task(task["id"])
                        if not live.get("planResolved"):
                            plan = direct_plan(bot, "计划判定失败，由当前 Bot 直接完成。", "fallback")
                            set_plan_status(plan, "auto")
                            live.update(coordinatorPlan=plan, executionMode="direct",
                                        planResolved=True, planDecidedAt=now())
                            self._persist()
            with self._lock:
                live = self._task(task["id"])
                if live["status"] != "starting":
                    return
                plan = deepcopy(live.get("coordinatorPlan") or {})
                if (plan.get("mode") == "delegate" and not live.get("planExecutedAt")
                        and live.get("orchestrationPolicy", "direct-first") != "off"):
                    if plan.get("status") == "proposed":
                        live.update(status="waiting", waitReason="plan-approval", updatedAt=now())
                        self._bot(bot["id"])["status"] = "idle"
                        self._message(live["id"], "system", "分工计划已生成，等待你确认后开始。")
                        self._persist()
                        return
                    live_plan = live["coordinatorPlan"]
                    transition_plan(live_plan, "running", by="system")
                    self._advance_plan(live)
                    live["planExecutedAt"] = now()
                    if live.get("children"):
                        live.update(status="waiting", waitReason="children", updatedAt=now())
                        self._bot(bot["id"])["status"] = "idle"
                        self._persist()
                        return
                    # No step could be dispatched: the owner carries on directly.
                    live_plan["mode"] = "direct"
                    live["executionMode"] = "direct"
                    self._persist()
                task = deepcopy(live)
                if task.get("presetIdOverride"):
                    bot = {**bot, "presetId": task["presetIdOverride"]}
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
                live_plan = live.get("coordinatorPlan")
                if live_plan and live_plan.get("mode") == "direct" and live_plan.get("status") == "auto":
                    transition_plan(live_plan, "running", by="system")
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
                self._finish(task, "failed" if state == "error" else "interrupted",
                             "Pi 执行失败。" if state == "error" else "Pi 已停止，任务尚未完成。",
                             system_failure=True)
            elif task.get("declaredError"):
                self._finish(task, "failed", task["declaredError"])
            elif task.get("inbox"):
                task.update(status="queued", waitReason=None, resumeText="\n".join(task.pop("inbox")))
                self._bot(task["botId"])["status"] = "idle"
            else:
                plan = task.get("coordinatorPlan") or {}
                plan_settled = plan.get("mode") == "delegate" and plan.get("status") in {"done", "failed", "cancelled", "rejected"}
                if not plan_settled and any(self._task(c)["status"] not in TERMINAL for c in task.get("children", [])):
                    task.update(status="waiting", waitReason="children")
                    self._bot(task["botId"])["status"] = "idle"
                elif self._resume_children(task):
                    self._bot(task["botId"])["status"] = "idle"
                elif task.get("waitRequested"):
                    self._enter_user_wait(task)
                else:
                    bad = any(e.get("status") == "error" for e in snapshot.get("events", []) if e.get("kind") == "user")
                    if bad:
                        self._finish(task, "failed", "Pi 未确认接收任务，请查看会话。", system_failure=True)
                    else:
                        answers = [e["text"] for e in snapshot.get("events", []) if e.get("kind") == "assistant" and e.get("text")]
                        if task.get("declaredResult") or answers:
                            self._finish(task, "completed", task.get("declaredResult") or answers[-1])
                        else:
                            self._finish(task, "failed", "本轮结束但没有收到结果。", system_failure=True)
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
        if action == "schedule":
            if payload.get("botId") and payload["botId"] != task["botId"]:
                raise WebError("BOT_SCOPE", "只能管理当前 Bot 自己的定时。", 403)
            op = str(payload.get("op") or "")
            if op == "create":
                spec = {key: payload[key] for key in ("prompt", "rule", "timezone", "overlapPolicy", "createdBy", "requestId") if key in payload}
                return {"schedule": self.create_schedule(task["botId"], spec)}
            if op == "list":
                return {"schedules": self.list_schedules(task["botId"])}
            if op in {"pause", "resume"}:
                return {"schedule": self.set_schedule_enabled(task["botId"], str(payload.get("scheduleId") or ""), op == "resume")}
            if op == "delete":
                return self.delete_schedule(task["botId"], str(payload.get("scheduleId") or ""))
            raise WebError("INVALID_REQUEST", "schedule 操作必须是 create、list、pause、resume 或 delete。", 400)
        if action in {"complete", "fail", "wait"}:
            content = str(payload.get("result") or payload.get("error") or payload.get("text") or payload.get("content") or payload.get("reason") or "")[:32000]
            with self._lock:
                live = self._task(task_id)
                if action == "complete":
                    live.update(declaredResult=content, waitRequested=False)
                elif action == "fail":
                    live["declaredError"] = content or "Bot 报告执行失败。"
                else:
                    self._record_wait_request(live, payload)
                self._message(task_id, "progress", content or "等待后续结果。", task["botId"])
                self._persist()
            return {"ok": True, "taskId": task_id, "message": "已记录，最终状态以 Pi 本轮结束为准。"}
        raise WebError("BOT_ACTION_UNKNOWN", "不支持这个 Bot 工具。", 400)
