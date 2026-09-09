"""User-facing session controls backed by Pi RPC and native history."""
import copy
import json
import time
import uuid
from pathlib import Path

from .errors import WebError
from .drivers.base import DriverClosedError, RpcTimeoutError
from .runtime import private_json, snapshot_config


def redact(value, secrets):
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, "[已隐藏密钥]")
        return value
    if isinstance(value, list):
        return [redact(item, secrets) for item in value]
    if isinstance(value, dict):
        return {key: redact(item, secrets) for key, item in value.items()}
    return value


def history(path):
    if not path or not Path(path).is_file():
        return []
    entries = []
    for line in Path(path).read_text().splitlines():
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
    return entries


def backfill_history(session):
    root = session.meta.get("runtimeRoot")
    if not root:
        return
    rows = [e for e in history(Path(root) / "conversation.jsonl") if (e.get("message") or {}).get("role") == "assistant"]
    events = [e for e in session.events if e.get("kind") == "assistant"]
    # Attach only to a matching message, never invent or reorder transcript text.
    cursor = 0
    for event in events:
        for index in range(cursor, len(rows)):
            message = rows[index]["message"]
            blocks = message.get("content") or []
            text = "\n".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            if message.get("errorMessage"):
                text += "\n\n" + message["errorMessage"]
            if redact(text, session.secrets) != event.get("text", ""):
                continue
            event.setdefault("thinking", redact("\n".join(b.get("thinking", "") for b in blocks if b.get("type") == "thinking"), session.secrets))
            event.setdefault("nativeTimestamp", message.get("timestamp"))
            event.setdefault("nativeEntryId", rows[index].get("id"))
            cursor = index + 1
            break


class SessionActions:
    def _rpc(self, session, command, timeout=8):
        if not session.alive():
            self._resume(session)
        try:
            response = session.driver.request(command, timeout=timeout)
        except (RpcTimeoutError, DriverClosedError) as exc:
            raise WebError("RPC_TIMEOUT", "执行工具尚未确认操作，请稍后查看状态。", 504) from exc
        if not response.get("success"):
            message = redact(str(response.get("error") or "当前执行工具不支持此操作。"), session.secrets)
            raise WebError("COMMAND_FAILED", message[:800], 409)
        return response.get("data") or {}

    def runtime_view(self, session_id):
        session = self._get(session_id)
        cached = session.meta.get("runtimeView", {})
        if not session.alive() or time.monotonic() - getattr(session, "runtime_checked", 0) < 4:
            return {**cached, "alive": session.alive(), "cwd": session.meta.get("cwd"), "cached": not session.alive(), "planning": session.meta.get("planning", False)}
        session.runtime_checked = time.monotonic()
        try:
            state = self._rpc(session, {"type": "get_state"}, 2)
            model = state.get("model") or {}
            stats = self._rpc(session, {"type": "get_session_stats"}, 2)
            view = {key: state[key] for key in ("thinkingLevel", "autoCompactionEnabled", "autoRetryEnabled", "isCompacting", "pendingMessageCount", "supportedThinkingLevels") if key in state}
            if "autoRetry" in session.meta.get("controlSettings", {}):
                view["autoRetryEnabled"] = session.meta["controlSettings"]["autoRetry"]
            from .launch_options import supported_levels
            view["supportedThinkingLevels"] = supported_levels(model)
            view["planning"] = session.meta.get("planning", False)
            view["queue"] = session.meta.get("queue", [])
            view.update({"model": {key: model[key] for key in ("id", "name", "provider", "api", "reasoning", "input", "contextWindow", "maxTokens") if key in model},
                         "stats": {key: stats[key] for key in ("tokens", "cost", "contextUsage", "toolCalls", "totalMessages") if key in stats},
                         "cwd": session.meta.get("cwd"), "alive": True, "cached": False})
            session.meta["runtimeView"] = redact(view, session.secrets)
            session.persist(self._state_dir)
            return session.meta["runtimeView"]
        except WebError:
            return {**cached, "alive": session.alive(), "cwd": session.meta.get("cwd"), "stale": True}

    def diagnostics(self, session_id):
        session = self._get(session_id)
        driver = session.driver
        return redact({"state": session.state, "alive": session.alive(), "pid": getattr(getattr(driver, "_proc", None), "pid", None), "exitCode": getattr(driver, "exit_code", None), "mode": "Pi RPC (--mode rpc)", "cwd": session.meta.get("cwd"), "stderr": str(getattr(driver, "_stderr_tail", ""))[-8000:], "notices": [e["text"] for e in session.events if e["kind"] == "notice"][-12:]}, session.secrets)

    def command_catalog(self, session_id):
        session = self._get(session_id)
        if not session.alive():
            return {"commands": [], "message": "继续会话后加载执行工具的扩展命令。"}
        data = self._rpc(session, {"type": "get_commands"})
        return {"commands": [{k: c[k] for k in ("name", "description", "source") if k in c}
                             for c in data.get("commands", []) if isinstance(c, dict) and not c.get("name", "").startswith("mms-web-")]}

    def _require_plan_control(self, session):
        available = self._rpc(session, {"type": "get_commands"})
        if not any(c.get("name") == "mms-web-plan" for c in available.get("commands", [])):
            raise WebError("CAPABILITY_UNAVAILABLE", "当前进程未加载 Web 模式控制，重新启动会话后可用。", 409)

    def control(self, session_id, payload):
        session = self._get(session_id)
        action = payload.get("action")
        value = payload.get("value")
        command = None
        if action == "plan":
            if not isinstance(value, bool):
                raise WebError("INVALID_PARAMETER", "请选择规划或执行模式。", 400)
            command = {"type": "prompt", "message": "/mms-web-plan " + ("on" if value else "off")}
        elif action == "thinking":
            if value not in {"off", "minimal", "low", "medium", "high", "xhigh", "max"}:
                raise WebError("INVALID_PARAMETER", "请选择有效的 Thinking 等级。", 400)
            command = {"type": "set_thinking_level", "level": value}
        elif action in {"autoCompaction", "autoRetry"}:
            if not isinstance(value, bool):
                raise WebError("INVALID_PARAMETER", "此设置需要开启或关闭。", 400)
            command = {"type": "set_auto_compaction" if action == "autoCompaction" else "set_auto_retry", "enabled": value}
        elif action == "compact":
            command = {"type": "compact", "customInstructions": str(value or "")[:4000]}
        elif action == "clearQueue":
            command = {"type": "clear_queue"}
        else:
            raise WebError("UNKNOWN_COMMAND", "此命令未接入，请从命令菜单选择。", 400)
        with session.mutation_lock, self._request_scope(self._validate_request_id(payload.get("requestId")), {"op": "control", "action": action, "value": value}, session) as replay:
            if replay is None:
                if session.state in {"running", "waiting"} and action != "clearQueue":
                    raise WebError("SESSION_BUSY", "请等待当前执行结束，再调整运行参数。", 409)
                if action == "plan":
                    self._require_plan_control(session)
                if action == "thinking":
                    from .launch_options import set_thinking
                    set_thinking(self, session, value)
                else:
                    self._rpc(session, command, 120 if action == "compact" else 8)
                session.meta.setdefault("controlSettings", {})[action] = value
                session.runtime_checked = 0
                session.append_event({"kind": "notice", "title": "设置", "text": {"plan": "工作模式已切换", "thinking": f"Thinking 已设置为 {value}", "autoCompaction": "自动压缩设置已更新", "autoRetry": "自动重试设置已更新", "compact": "上下文压缩完成", "clearQueue": "待发送队列已清空"}[action]}, self._now)
                session.persist(self._state_dir)
        return self.get_session(session_id)

    def switch_model(self, session_id, payload):
        from .model_switch import switch_model
        return switch_model(self, session_id, payload)

    def manage(self, session_id, payload):
        session = self._get(session_id)
        with session.mutation_lock:
            if "title" in payload:
                title = str(payload["title"]).strip()[:100]
                if not title:
                    raise WebError("INVALID_TITLE", "会话名称不能为空。", 400)
                if session.alive():
                    self._rpc(session, {"type": "set_session_name", "name": title})
                session.meta["title"] = title
            if "archived" in payload:
                if not isinstance(payload["archived"], bool):
                    raise WebError("INVALID_PARAMETER", "归档参数无效。", 400)
                if session.state in {"running", "waiting"}:
                    raise WebError("SESSION_BUSY", "运行中的会话请先停止，再归档。", 409)
                session.meta["archived"] = payload["archived"]
            session.persist(self._state_dir)
            return session.detail_view()

    def fork(self, session_id, payload):
        session = self._get(session_id)
        with session.mutation_lock, self._request_scope(self._validate_request_id(payload.get("requestId")), {"op": "fork", "sessionId": session_id, "eventId": payload.get("eventId")}) as replay:
            if replay is not None:
                return replay.detail_view()
            if session.state in {"running", "waiting"} or not session.can_resume():
                raise WebError("SESSION_BUSY", "请等待会话停止或回复完成后再创建分支。", 409)
            backfill_history(session)
            selected = next((e for e in session.events if e["id"] == payload.get("eventId") and e["kind"] == "assistant"), None)
            if payload.get("eventId") and (not selected or not selected.get("nativeEntryId")):
                raise WebError("FORK_UNAVAILABLE", "这条回复的原生历史尚未写入，请稍后重试。", 409)
            old_root = Path(session.meta["runtimeRoot"])
            rows = history(old_root / "conversation.jsonl")
            if selected:
                end = next(i for i, row in enumerate(rows) if row.get("id") == selected["nativeEntryId"])
                rows = rows[:end + 1]
            new_root = snapshot_config(old_root, self._state_root)
            saved = json.loads((old_root / "resume.json").read_text())
            saved["runtime"]["_webConfigRoot"] = str(new_root)
            private_json(new_root / "resume.json", saved)
            if rows and rows[0].get("type") == "session":
                rows[0]["id"] = str(uuid.uuid4())
            with (new_root / "conversation.jsonl").open("w") as stream:
                (new_root / "conversation.jsonl").chmod(0o600)
                for row in rows:
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            meta = copy.deepcopy(session.meta)
            meta.update(id="s-" + uuid.uuid4().hex[:12], title=session.meta["title"] + " · 分支", runtimeRoot=str(new_root), archived=False, updatedAt=self._now(), forkedFrom=session_id)
            branch = type(session)(meta)
            branch.state = "stopped"
            end_index = session.events.index(selected) + 1 if selected else len(session.events)
            branch.events = copy.deepcopy(session.events[:end_index])
            branch.event_index = {e["id"]: e for e in branch.events}
            branch.last_sequence = max((e["sequence"] for e in branch.events), default=0)
            branch.append_event({"kind": "notice", "text": "已创建独立会话分支，后续对话不会改变原会话。工作文件夹仍与原会话共用。"}, self._now)
            with self._lock:
                self._sessions[meta["id"]] = branch
                self._requests[payload["requestId"]]["sessionId"] = meta["id"]
            branch.persist(self._state_dir)
            return branch.detail_view()
