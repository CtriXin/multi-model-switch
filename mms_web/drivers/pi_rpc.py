"""Pi ``--mode rpc`` rich driver for MMS Pilot sessions.

Protocol source: official ``pi --mode rpc`` JSONL protocol
(docs/rpc.md of the installed pi-coding-agent), verified against the installed
dist sources. Framing is strict LF JSONL; a trailing CR is stripped.

Approvals map only to real protocol requests: extension UI dialog methods
(``select`` / ``confirm`` / ``input`` / ``editor``). This driver never invents
approvals and never answers shell prompts itself. ``confirm`` supports
allow/deny directly; ``select`` requires an explicit option, while
``input``/``editor`` accept user-entered values. No dialog is auto-answered.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import uuid
from typing import Callable

from ..errors import WebError
from .base import DriverClosedError, DriverWriteUnconfirmedError, RpcTimeoutError

_DIALOG_METHODS = {"select", "confirm", "input", "editor"}
_FIRE_AND_FORGET_METHODS = {"notify", "setStatus", "setWidget", "setTitle", "set_editor_text"}
_TEXT_SNIPPET_LIMIT = 200000
_NOTICE_TEXT_LIMIT = 1000
_STDERR_TAIL_BYTES = 2048


def _clip(text: str, limit: int) -> str:
    text = str(text or "")
    if len(text) <= limit:
        return text
    keep = limit // 2
    return text[:keep] + f"\n…[{len(text) - limit} chars omitted]…\n" + text[-keep:]


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
    return "\n".join(parts)


def _summarize_args(args) -> str:
    if isinstance(args, dict):
        return json.dumps(args, ensure_ascii=False, sort_keys=True)
    return str(args)


class _PendingRequest:
    __slots__ = ("event", "response")

    def __init__(self) -> None:
        self.event = threading.Event()
        self.response: dict | None = None


class PiRpcDriver:
    """Owns one pi child process and normalizes its protocol events.

    The sink is called from reader threads and must be thread-safe:

    - ``upsert_event(fields)``: merge an API Event by stable ``id``.
    - ``set_proto_state(state)``: one of ``running`` / ``idle`` / ``waiting``.
    - ``set_activity(phase, **details)``: observed operation, independent of lifecycle.
    - ``approval_pending(approval_id, method, title)`` / ``approval_resolved(approval_id, decision)``.
    - ``process_exited(exit_code, stderr_tail)``: exactly once after the child died.
    """

    def __init__(
        self,
        process,
        sink,
        *,
        response_timeout: float = 30.0,
        abort_timeout: float = 15.0,
        name: str = "pi",
    ) -> None:
        self._proc = process
        self._sink = sink
        self._response_timeout = response_timeout
        self._abort_timeout = abort_timeout
        self._name = name

        self._write_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._next_request_id = 1
        self._pending: dict[str, _PendingRequest] = {}
        self._ui_pending: dict[str, dict] = {}
        self._streaming = False
        self._open_assistant_id: str | None = None
        self._active_tools: dict[str, str] = {}
        self._turn_outcome = "idle"
        self._exit_code: int | None = None
        self._stderr_tail = ""
        self._exit_notified = False

        self._reader = threading.Thread(target=self._stdout_loop, name=f"{name}-rpc-stdout", daemon=True)
        self._stderr_reader = threading.Thread(target=self._stderr_loop, name=f"{name}-rpc-stderr", daemon=True)
        self._reader.start()
        self._stderr_reader.start()

    # -- lifecycle -----------------------------------------------------

    def alive(self) -> bool:
        return self._proc.poll() is None

    @property
    def exit_code(self) -> int | None:
        return self._exit_code

    def wait(self, timeout: float | None = None) -> bool:
        """Wait for process exit; True when exited."""
        try:
            self._proc.wait(timeout=timeout)
            return True
        except subprocess.TimeoutExpired:
            return False

    def _terminate_group(self, sig) -> None:
        try:
            if os.getpgid(self._proc.pid) == self._proc.pid:
                os.killpg(self._proc.pid, sig)
            else:
                self._proc.send_signal(sig)
        except (OSError, AttributeError):
            pass

    def close_for_update(self, *, timeout: float = 10.0) -> bool:
        """Request an explicitly approved idle restart; never escalate to SIGKILL.

        Keep stdin open if the child ignores termination, so a failed update
        does not itself break the original RPC transport.
        """
        if self.alive():
            self._terminate_group(signal.SIGTERM)
        if not self.wait(timeout=timeout):
            return False
        self._notify_exit()
        return True

    def close(self, *, graceful_timeout: float = 5.0) -> None:
        """Stop the child: stdin EOF first, then terminate, then kill.

        Never leaves an orphan behind. Blocks until the child is reaped.
        """
        if self._exit_code is not None:
            self.wait(timeout=5)
            self._notify_exit()
            return
        try:
            if self._proc.stdin and not self._proc.stdin.closed:
                self._proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass
        if not self.wait(timeout=graceful_timeout):
            try:
                self._terminate_group(signal.SIGTERM)
            except OSError:
                pass
            if not self.wait(timeout=3.0):
                try:
                    self._terminate_group(signal.SIGKILL)
                except OSError:
                    pass
                self.wait(timeout=5.0)
        self._notify_exit()

    # -- commands ------------------------------------------------------

    def request(self, command: dict, *, timeout: float | None = None) -> dict:
        with self._state_lock:
            if self._exit_code is not None:
                raise DriverClosedError("pi process exited")
            request_id = f"r{self._next_request_id}"
            self._next_request_id += 1
            pending = _PendingRequest()
            self._pending[request_id] = pending
        payload = {"id": request_id, **command}
        try:
            self._write_line(payload)
        except (BrokenPipeError, OSError) as exc:
            with self._state_lock:
                self._pending.pop(request_id, None)
            raise DriverWriteUnconfirmedError(f"pi stdin write failed: {exc.__class__.__name__}") from exc
        wait_seconds = self._response_timeout if timeout is None else timeout
        if not pending.event.wait(wait_seconds):
            with self._state_lock:
                self._pending.pop(request_id, None)
            raise RpcTimeoutError(f"pi rpc response timeout after {wait_seconds}s")
        response = pending.response or {}
        if not isinstance(response, dict):
            raise RpcTimeoutError("pi rpc returned a malformed response")
        return response

    def send_prompt(self, text: str, *, images=None, timeout: float | None = None) -> dict:
        command: dict = {"type": "prompt", "message": str(text)}
        if images:
            command["images"] = images
        if self._streaming:
            command["streamingBehavior"] = "followUp"
        return self.request(command, timeout=timeout)

    def abort(self, *, timeout: float | None = None) -> dict:
        for approval_id in self.pending_approvals():
            try:
                self.respond_ui(approval_id, "deny")
            except WebError:
                pass
        self.request({"type": "clear_queue"}, timeout=self._abort_timeout)
        return self.request({"type": "abort"}, timeout=self._abort_timeout if timeout is None else timeout)

    def get_state(self) -> dict:
        response = self.request({"type": "get_state"})
        return response.get("data") if isinstance(response.get("data"), dict) else {}

    # -- approvals -----------------------------------------------------

    def pending_approvals(self) -> dict:
        with self._state_lock:
            return {k: dict(v) for k, v in self._ui_pending.items()}

    def respond_ui(self, approval_id: str, decision: str, value: str | None = None) -> None:
        with self._state_lock:
            entry = self._ui_pending.get(approval_id)
        if entry is None:
            raise WebError("APPROVAL_NOT_FOUND", "该问题不存在或已处理。", 404)
        method = entry.get("method")
        payload = {"type": "extension_ui_response", "id": approval_id}
        if decision == "deny":
            payload.update({"confirmed": False} if method == "confirm" else {"cancelled": True})
        elif method == "confirm":
            payload["confirmed"] = True
        elif method in {"select", "input", "editor"}:
            if not isinstance(value, str) or (method == "select" and value not in entry.get("options", [])):
                raise WebError("INTERACTION_VALUE_REQUIRED", "请选择有效选项或填写回答。", 400)
            payload["value"] = value
        else:
            raise WebError("APPROVAL_KIND_UNSUPPORTED", "当前交互类型不受支持。", 409)
        self._write_line(payload)
        with self._state_lock:
            self._ui_pending.pop(approval_id, None)
        self._upsert({"id": f"a-{approval_id}", "kind": "approval", "approvalId": approval_id,
                      "decision": decision, "answer": value})
        self._sink.approval_resolved(approval_id, decision)

    # -- IO plumbing ---------------------------------------------------

    def _write_line(self, payload: dict) -> None:
        line = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        with self._write_lock:
            stdin = self._proc.stdin
            if stdin is None or stdin.closed:
                raise DriverClosedError("pi stdin closed")
            stdin.write(line)
            stdin.flush()

    def _stdout_loop(self) -> None:
        stream = self._proc.stdout
        try:
            while True:
                raw = stream.readline()
                if not raw:
                    break
                line = raw[:-1] if raw.endswith(b"\n") else raw
                if line.endswith(b"\r"):
                    line = line[:-1]
                if not line.strip():
                    continue
                self._handle_line(line.decode("utf-8", "replace"))
        except Exception:
            pass
        finally:
            self._on_stdout_eof()

    def _stderr_loop(self) -> None:
        stream = self._proc.stderr
        try:
            while True:
                raw = stream.readline()
                if not raw:
                    break
                text = raw.decode("utf-8", "replace").rstrip("\n")
                if text:
                    self._stderr_tail = (self._stderr_tail + "\n" + text)[-_STDERR_TAIL_BYTES:]
        except Exception:
            pass

    def _on_stdout_eof(self) -> None:
        with self._state_lock:
            pending = list(self._pending.values())
            self._pending.clear()
        for item in pending:
            item.response = {"type": "response", "success": False, "error": "process exited", "deliveryUnconfirmed": True}
            item.event.set()
        try:
            exit_code = self._proc.wait(timeout=5)
        except Exception:
            exit_code = self._proc.poll()
            if exit_code is None:
                exit_code = -1
        with self._state_lock:
            self._exit_code = exit_code
        self._streaming = False
        self._notify_exit()

    def _notify_exit(self) -> None:
        with self._state_lock:
            if self._exit_notified:
                return
            exit_code = self._exit_code
            if exit_code is None:
                try:
                    exit_code = self._proc.poll()
                except Exception:
                    exit_code = -1
                self._exit_code = exit_code
            stderr_tail = self._stderr_tail
            self._exit_notified = True
        self._sink.process_exited(exit_code if exit_code is not None else -1, stderr_tail)

    # -- event normalization -------------------------------------------

    def _upsert(self, fields: dict) -> None:
        self._sink.upsert_event(fields)

    def _notice(self, text: str, *, title: str | None = None) -> None:
        self._upsert({"id": f"n-{uuid.uuid4().hex[:12]}", "kind": "notice", "text": _clip(text, _NOTICE_TEXT_LIMIT), "title": title})

    def _handle_line(self, line: str) -> None:
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            self._notice("收到非 RPC 输出，已跳过。", title="协议异常")
            return
        if not isinstance(message, dict):
            self._notice("收到非对象的 RPC 消息", title="协议异常")
            return
        mtype = message.get("type")
        if mtype == "response":
            self._handle_response(message)
        elif mtype == "extension_ui_request":
            self._handle_ui_request(message)
        else:
            self._handle_event(message)

    def _handle_response(self, message: dict) -> None:
        request_id = str(message.get("id") or "")
        with self._state_lock:
            pending = self._pending.pop(request_id, None)
        if pending is None:
            return
        pending.response = message
        pending.event.set()
        if message.get("success") is False:
            error = str(message.get("error") or "unknown error")
            self._notice(f"命令 {message.get('command') or '?'} 失败: {_clip(error, 400)}", title="命令错误")

    def _handle_ui_request(self, message: dict) -> None:
        request_id = str(message.get("id") or "")
        method = str(message.get("method") or "")
        title = str(message.get("title") or "")
        if method in _DIALOG_METHODS:
            detail_parts = [title]
            if message.get("message"):
                detail_parts.append(str(message.get("message")))
            options = message.get("options")
            if isinstance(options, list) and options:
                detail_parts.append(" / ".join(str(o) for o in options))
            with self._state_lock:
                self._ui_pending[request_id] = {"method": method, "title": title, "options": options or []}
            # Event first, then the pending capability flip: the snapshot must
            # never advertise an approve action whose event is still missing.
            self._upsert(
                {
                    "id": f"a-{request_id}",
                    "kind": "approval",
                    "approvalId": request_id,
                    "method": method, "options": options or [],
                    "placeholder": message.get("placeholder", ""),
                    "prefill": message.get("prefill") or message.get("text") or "",
                    "title": title or "等待确认",
                    "text": "\n".join(p for p in detail_parts if p),
                }
            )
            self._sink.approval_pending(request_id, method, title)
            return
        if method == "notify" and str(message.get("message", "")).startswith("MMS_WEB_STATE:"):
            try:
                state = json.loads(message["message"].split(":", 1)[1])
                if isinstance(state.get("planning"), bool):
                    self._upsert({"id": "n-web-mode", "kind": "notice", "planning": state["planning"], "text": "只读规划已开启，当前只允许读取文件。" if state["planning"] else "当前为执行模式。"})
                    return
            except (ValueError, TypeError):
                pass
        if method in _FIRE_AND_FORGET_METHODS:
            text = message.get("message") or message.get("statusText") or message.get("title") or ""
            label = {"set_editor_text": "setEditorText"}.get(method, method)
            self._notice(f"[{label}] {text}" if text else f"[{label}]", title="扩展通知")
            return
        self._notice(f"未处理的扩展 UI 请求: {method}", title="协议异常")

    def _handle_event(self, message: dict) -> None:
        etype = message.get("type")
        if etype == "agent_start":
            self._streaming = True
            self._turn_outcome = "idle"
            self._active_tools.clear()
            self._sink.set_proto_state("running")
            self._activity("running")
        elif etype == "agent_settled":
            self._streaming = False
            with self._state_lock:
                waiting = bool(self._ui_pending)
            self._sink.set_proto_state("waiting" if waiting else "idle")
            self._active_tools.clear()
            self._open_assistant_id = None
            self._activity(self._turn_outcome)
        elif etype == "message_start" and (message.get("message") or {}).get("role") == "user":
            self._sink.upsert_event({"consumedPrompt": _content_text(message["message"].get("content"))})
        elif etype == "message_start" and (message.get("message") or {}).get("role") == "assistant":
            self._open_assistant_id = f"m-{uuid.uuid4().hex[:12]}"
            self._upsert({"id": self._open_assistant_id, "kind": "assistant", "text": ""})
            self._activity("running", eventId=self._open_assistant_id)
        elif etype == "message_update":
            self._handle_message_update(message)
        elif etype == "message_end":
            self._handle_message_end(message)
        elif etype in {"tool_execution_start", "tool_execution_update", "tool_execution_end"}:
            self._handle_tool_execution(message)
        elif etype == "compaction_start":
            self._activity("compacting")
            self._notice("上下文压缩已开始", title="compaction")
        elif etype == "compaction_end":
            self._activity("running" if self._streaming else "idle")
            self._notice("上下文压缩已结束", title="compaction")
        elif etype in {"auto_retry_start", "auto_retry_end", "summarization_retry_scheduled", "summarization_retry_finished"}:
            self._activity("retrying" if etype in {"auto_retry_start", "summarization_retry_scheduled"} else "running" if self._streaming else "idle")
            self._notice(f"自动重试事件: {etype}", title="retry")
        elif etype == "queue_update":
            queue = [str(text) for text in [*(message.get("steering") or []), *(message.get("followUp") or [])]]
            self._upsert({"id": "n-queue", "kind": "notice", "title": "待发送消息", "text": f"还有 {len(queue)} 条补充消息等待执行" if queue else "待发送队列已清空", "queue": queue})
        elif etype == "extension_error":
            self._notice(_clip(str(message.get("error") or "extension error"), 400), title="扩展错误")
        # turn_start / turn_end / agent_end / bash_execution_update and
        # unknown future event types are intentionally ignored here.

    def _handle_message_update(self, message: dict) -> None:
        delta = message.get("assistantMessageEvent")
        if not isinstance(delta, dict):
            return
        dtype = delta.get("type")
        if self._open_assistant_id:
            if dtype in {"thinking_start", "thinking_delta"}:
                self._activity("thinking", eventId=self._open_assistant_id)
            elif dtype in {"text_start", "text_delta"}:
                self._activity("responding", eventId=self._open_assistant_id)
            elif dtype in {"thinking_end", "text_end", "toolcall_start"}:
                self._activity("running", eventId=self._open_assistant_id)
        if dtype in {"text_delta", "thinking_delta"} and self._open_assistant_id:
            self._upsert(
                {
                    "id": self._open_assistant_id,
                    "kind": "assistant",
                    "textAppend" if dtype == "text_delta" else "thinkingAppend": str(delta.get("delta") or ""),
                }
            )

    def _handle_message_end(self, message: dict) -> None:
        msg = message.get("message")
        if not isinstance(msg, dict):
            self._open_assistant_id = None
            return
        if msg.get("role") != "assistant":
            return
        text = _content_text(msg.get("content"))
        if msg.get("errorMessage"):
            text += "\n\n" + str(msg["errorMessage"])
        event_id = self._open_assistant_id or f"m-{uuid.uuid4().hex[:12]}"
        self._open_assistant_id = None
        self._turn_outcome = "stopped" if msg.get("stopReason") == "aborted" else "error" if msg.get("errorMessage") or msg.get("stopReason") == "error" else "idle"
        self._activity("running")
        thinking = "\n".join(b.get("thinking", "") for b in msg.get("content", []) if isinstance(b, dict) and b.get("type") == "thinking")
        self._upsert({"id": event_id, "kind": "assistant", "text": text, "thinking": thinking, "nativeTimestamp": msg.get("timestamp"), "usage": msg.get("usage", {})})

    def _handle_tool_execution(self, message: dict) -> None:
        etype = message.get("type")
        call_id = str(message.get("toolCallId") or uuid.uuid4().hex[:8])
        tool_name = str(message.get("toolName") or "tool")
        fields: dict = {"id": f"t-{call_id}", "kind": "tool", "title": tool_name}
        if etype == "tool_execution_start":
            self._active_tools[call_id] = tool_name
            self._activity("tool", eventId=fields["id"], toolName=tool_name)
            fields["status"] = "running"
            fields["text"] = _summarize_args(message.get("args"))
            fields["arguments"] = message.get("args") or {}
        elif etype == "tool_execution_update":
            partial = message.get("partialResult")
            fields["status"] = "running"
            fields["text"] = _clip(_content_text(partial.get("content")) if isinstance(partial, dict) else "", _TEXT_SNIPPET_LIMIT)
        elif etype == "tool_execution_end":
            self._active_tools.pop(call_id, None)
            if self._active_tools:
                active_id, active_name = next(iter(self._active_tools.items()))
                self._activity("tool", eventId=f"t-{active_id}", toolName=active_name)
            else:
                self._activity("running")
            result = message.get("result")
            fields["status"] = "error" if message.get("isError") else "done"
            fields["text"] = _clip(_content_text(result.get("content")) if isinstance(result, dict) else "", _TEXT_SNIPPET_LIMIT)
            if isinstance(result, dict):
                fields["media"] = [b for b in result.get("content", []) if isinstance(b, dict) and b.get("type") == "image"]
        self._upsert(fields)

    def _activity(self, phase: str, **details) -> None:
        self._sink.set_activity(phase, **details)
