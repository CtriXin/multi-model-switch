"""Grok Build ACP v1 driver for optional MMS Pilot sessions.

Wire format was probed against grok 1.0.34: newline JSON-RPC 2.0, initialize
``protocolVersion: 1``, then ``session/new``. This is not Pi RPC and not ACP v2.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import uuid

from ..errors import WebError
from .base import DriverClosedError, DriverWriteUnconfirmedError, RpcTimeoutError

_TEXT_SNIPPET_LIMIT = 200000
_NOTICE_TEXT_LIMIT = 1000
_STDERR_TAIL_BYTES = 2048
_FORCE_SIGNAL = getattr(signal, "SIGKILL", signal.SIGTERM)


def _clip(text: str, limit: int) -> str:
    text = str(text or "")
    if len(text) <= limit:
        return text
    keep = limit // 2
    return text[:keep] + f"\n…[{len(text) - limit} chars omitted]…\n" + text[-keep:]


class _Pending:
    __slots__ = ("event", "response", "error")

    def __init__(self) -> None:
        self.event = threading.Event()
        self.response: dict | None = None
        self.error: str | None = None


class GrokAcpDriver:
    """Owns one ``grok agent stdio`` child and maps ACP updates onto Pilot events."""

    def __init__(
        self,
        process,
        sink,
        *,
        cwd: str = "",
        resume_session_id: str | None = None,
        plan_mode: bool = False,
        response_timeout: float = 30.0,
        abort_timeout: float = 15.0,
        handshake_timeout: float = 20.0,
        name: str = "grok",
    ) -> None:
        self._proc = process
        self._sink = sink
        self._cwd = str(cwd or os.getcwd())
        self._resume_session_id = str(resume_session_id or "").strip() or None
        self._plan_mode = bool(plan_mode)
        self._response_timeout = response_timeout
        self._abort_timeout = abort_timeout
        self._name = name

        self._write_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._next_request_id = 1
        self._pending: dict[int, _Pending] = {}
        self._ui_pending: dict[str, dict] = {}
        self._session_id = ""
        self._streaming = False
        self._open_assistant_id: str | None = None
        self._active_tools: dict[str, str] = {}
        self._commands: list[dict] = []
        self._model = {
            "id": "",
            "name": "",
            "input": ["text"],
            "reasoning": True,
            "contextWindow": 0,
            "thinkingLevelMap": {"low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh"},
        }
        self._thinking_level = "high"
        self._usage: dict = {}
        self._follow_up: list[str] = []
        self._steering: list[str] = []
        self._steer_notice_sent = False
        self._prompt_ids: set[int] = set()
        self._replay = False
        self._exit_code: int | None = None
        self._stderr_tail = ""
        self._exit_notified = False
        self._native_session_id = ""

        self._reader = threading.Thread(target=self._stdout_loop, name=f"{name}-acp-stdout", daemon=True)
        self._stderr_reader = threading.Thread(target=self._stderr_loop, name=f"{name}-acp-stderr", daemon=True)
        self._reader.start()
        self._stderr_reader.start()
        self._handshake(handshake_timeout)

    @property
    def native_session_id(self) -> str:
        return self._native_session_id

    def alive(self) -> bool:
        return self._proc.poll() is None

    @property
    def exit_code(self) -> int | None:
        return self._exit_code

    def wait(self, timeout: float | None = None) -> bool:
        try:
            self._proc.wait(timeout=timeout)
            return True
        except subprocess.TimeoutExpired:
            return False

    def close_for_update(self, *, timeout: float = 10.0) -> bool:
        if self.alive():
            try:
                if self._session_id:
                    self._rpc("session/close", {"sessionId": self._session_id}, timeout=min(3.0, timeout), quiet=True)
            except Exception:
                pass
            self._terminate_group(signal.SIGTERM)
        if not self.wait(timeout=timeout):
            return False
        self._notify_exit()
        return True

    def close(self, *, graceful_timeout: float = 5.0) -> None:
        if self._exit_code is not None:
            self.wait(timeout=5)
            self._notify_exit()
            return
        try:
            if self._session_id and self.alive():
                self._rpc("session/close", {"sessionId": self._session_id}, timeout=min(2.0, graceful_timeout), quiet=True)
        except Exception:
            pass
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
                    self._terminate_group(_FORCE_SIGNAL)
                except OSError:
                    pass
                self.wait(timeout=5.0)
        self._notify_exit()

    def request(self, command: dict, *, timeout: float | None = None, quiet: bool = False) -> dict:
        ctype = str(command.get("type") or "")
        try:
            data = self._dispatch(ctype, command, timeout=timeout)
        except RpcTimeoutError:
            raise
        except DriverClosedError:
            raise
        except WebError as exc:
            if quiet:
                return {"type": "response", "success": False, "error": exc.message}
            raise
        except Exception as exc:
            if quiet:
                return {"type": "response", "success": False, "error": str(exc)}
            raise WebError("COMMAND_FAILED", str(exc)[:800], 409) from exc
        return {"type": "response", "success": True, "data": data}

    def send_prompt(self, text: str, *, images=None, timeout: float | None = None) -> dict:
        if self._streaming:
            return self.follow_up(text, images=images, timeout=timeout)
        return self._prompt(text, images=images, timeout=timeout)

    def steer(self, text: str, *, images=None, timeout: float | None = None) -> dict:
        # Grok ACP has no Pi-style steer. Queue until idle rather than interrupt.
        if images:
            raise WebError("IMAGE_UNSUPPORTED", "Grok 排队补充暂不支持图片，请等本轮结束后发送。", 409)
        with self._state_lock:
            self._steering.append(str(text))
        if not self._steer_notice_sent:
            self._steer_notice_sent = True
            self._notice("Grok 没有立即引导，这条消息会在当前轮结束后发送。", title="排队")
        self._emit_queue()
        return {"type": "response", "success": True, "data": {}}

    def follow_up(self, text: str, *, images=None, timeout: float | None = None) -> dict:
        if images:
            raise WebError("IMAGE_UNSUPPORTED", "Grok 排队补充暂不支持图片，请等本轮结束后发送。", 409)
        with self._state_lock:
            self._follow_up.append(str(text))
        self._emit_queue()
        return {"type": "response", "success": True, "data": {}}

    def clear_queue(self, *, timeout: float | None = None) -> dict:
        with self._state_lock:
            steering = list(self._steering)
            follow_up = list(self._follow_up)
            self._steering.clear()
            self._follow_up.clear()
        self._emit_queue()
        return {"steering": steering, "followUp": follow_up}

    def abort(self, *, timeout: float | None = None) -> dict:
        for approval_id in self.pending_approvals():
            try:
                self.respond_ui(approval_id, "deny")
            except WebError:
                pass
        self.clear_queue()
        if self._session_id:
            try:
                self._rpc(
                    "session/cancel",
                    {"sessionId": self._session_id},
                    timeout=self._abort_timeout if timeout is None else timeout,
                    quiet=True,
                )
            except (DriverClosedError, RpcTimeoutError):
                pass
        self._streaming = False
        self._sink.set_proto_state("idle")
        return {"type": "response", "success": True, "data": {}}

    def get_state(self) -> dict:
        with self._state_lock:
            model = dict(self._model)
            level = self._thinking_level
            pending = len(self._follow_up) + len(self._steering)
        return {
            "model": model,
            "thinkingLevel": level,
            "autoCompactionEnabled": True,
            "autoRetryEnabled": False,
            "isCompacting": False,
            "pendingMessageCount": pending,
            "supportedThinkingLevels": [k for k in ("low", "medium", "high", "xhigh") if k in (model.get("thinkingLevelMap") or {})],
            "planning": self._plan_mode,
        }

    def get_commands(self, *, timeout: float | None = None) -> list:
        with self._state_lock:
            return [dict(item) for item in self._commands]

    def pending_approvals(self) -> dict:
        with self._state_lock:
            return {k: dict(v) for k, v in self._ui_pending.items()}

    def respond_ui(self, approval_id: str, decision: str, value: str | None = None) -> None:
        with self._state_lock:
            entry = self._ui_pending.get(approval_id)
        if entry is None:
            raise WebError("APPROVAL_NOT_FOUND", "该问题不存在或已处理。", 404)
        option_id = value
        if decision == "deny":
            option_id = entry.get("rejectId")
            outcome = {"outcome": "cancelled"} if not option_id else {"outcome": "selected", "optionId": option_id}
        elif entry.get("method") == "confirm":
            option_id = entry.get("allowId") or option_id
            if not option_id:
                raise WebError("INTERACTION_VALUE_REQUIRED", "请选择有效选项或填写回答。", 400)
            outcome = {"outcome": "selected", "optionId": option_id}
        elif entry.get("method") == "select":
            options = entry.get("options") or []
            if not isinstance(value, str) or value not in options:
                raise WebError("INTERACTION_VALUE_REQUIRED", "请选择有效选项或填写回答。", 400)
            outcome = {"outcome": "selected", "optionId": value}
        else:
            raise WebError("APPROVAL_KIND_UNSUPPORTED", "当前交互类型不受支持。", 409)
        self._write({"jsonrpc": "2.0", "id": entry["rpcId"], "result": {"outcome": outcome}})
        with self._state_lock:
            self._ui_pending.pop(approval_id, None)
        self._upsert({"id": f"a-{approval_id}", "kind": "approval", "approvalId": approval_id,
                      "decision": decision, "answer": value})
        self._sink.approval_resolved(approval_id, decision)
        waiting = bool(self.pending_approvals())
        self._sink.set_proto_state("waiting" if waiting else ("running" if self._streaming else "idle"))

    # -- handshake / RPC ------------------------------------------------

    def _handshake(self, timeout: float) -> None:
        init = self._rpc(
            "initialize",
            {
                "protocolVersion": 1,
                "clientCapabilities": {},
                "clientInfo": {"name": "mms-pilot", "title": "MMS Pilot", "version": "0"},
            },
            timeout=timeout,
        )
        caps = init.get("agentCapabilities") if isinstance(init, dict) else {}
        prompt_caps = (caps or {}).get("promptCapabilities") if isinstance(caps, dict) else {}
        if isinstance(prompt_caps, dict) and prompt_caps.get("image"):
            self._model["input"] = ["text", "image"]
        meta = init.get("_meta") if isinstance(init, dict) else {}
        self._apply_model_state((meta or {}).get("modelState") if isinstance(meta, dict) else None)
        session = None
        if self._resume_session_id:
            self._replay = True
            params = {"sessionId": self._resume_session_id, "cwd": self._cwd, "mcpServers": []}
            for method in ("session/load", "session/resume"):
                try:
                    session = self._rpc(method, params, timeout=timeout)
                except (WebError, RpcTimeoutError, DriverClosedError):
                    session = None
                if isinstance(session, dict) and session.get("sessionId"):
                    break
            self._replay = False
        if not isinstance(session, dict) or not session.get("sessionId"):
            new_params: dict = {"cwd": self._cwd, "mcpServers": []}
            if self._plan_mode:
                new_params["_meta"] = {"agentProfile": "plan"}
            session = self._rpc("session/new", new_params, timeout=timeout)
        if not isinstance(session, dict) or not session.get("sessionId"):
            raise DriverClosedError("grok ACP session/new failed")
        self._session_id = str(session["sessionId"])
        self._native_session_id = self._session_id
        self._apply_session_result(session)
        if self._plan_mode:
            self._upsert({"planning": True})
        self._sink.set_proto_state("idle")

    def _dispatch(self, ctype: str, command: dict, *, timeout: float | None) -> dict:
        if ctype in {"", "get_state"}:
            return self.get_state()
        if ctype == "get_commands":
            return {"commands": self.get_commands()}
        if ctype == "get_session_stats":
            with self._state_lock:
                return dict(self._usage)
        if ctype == "get_available_models":
            return {"models": [{"id": self._model.get("id"), "name": self._model.get("name")}]}
        if ctype == "set_thinking_level":
            self._set_thinking(str(command.get("level") or ""))
            return self.get_state()
        if ctype == "set_model":
            model = str(command.get("modelId") or command.get("model") or "")
            self._set_config("model", model)
            return self.get_state()
        if ctype == "set_session_name":
            return {}
        if ctype == "set_plan_mode":
            enabled = bool(command.get("enabled"))
            self._plan_mode = enabled
            if enabled:
                self._prompt("/plan", wait=False)
            self._upsert({"planning": enabled})
            return self.get_state()
        if ctype in {"set_auto_compaction", "set_auto_retry"}:
            return self.get_state()
        if ctype == "compact":
            note = str(command.get("customInstructions") or "").strip()
            message = "/compact " + note if note else "/compact"
            self._prompt(message, timeout=timeout if timeout is not None else 120, wait=True)
            return {}
        if ctype == "clear_queue":
            return self.clear_queue()
        if ctype == "abort":
            return self.abort(timeout=timeout)
        if ctype == "prompt":
            return self.send_prompt(str(command.get("message") or ""), images=command.get("images"), timeout=timeout)
        raise WebError("UNKNOWN_COMMAND", "此命令未接入，请从命令菜单选择。", 400)

    def _prompt(self, text: str, *, images=None, timeout: float | None = None, wait: bool = False) -> dict:
        if not self._session_id:
            raise DriverClosedError("grok session is not ready")
        blocks: list[dict] = [{"type": "text", "text": str(text)}]
        for image in images or []:
            if not isinstance(image, dict):
                continue
            data = str(image.get("data") or "")
            mime = str(image.get("mimeType") or "image/png")
            if data:
                blocks.append({"type": "image", "data": data, "mimeType": mime})
        self._streaming = True
        self._turn_begin()
        request_id, pending = self._begin_rpc(
            "session/prompt",
            {"sessionId": self._session_id, "prompt": blocks},
        )
        with self._state_lock:
            self._prompt_ids.add(request_id)
        wait_seconds = self._response_timeout if timeout is None else timeout
        if wait:
            return self._await_rpc(request_id, pending, wait_seconds)
        # Grok 1.0.34 keeps session/prompt open until the turn ends. Pilot
        # must return after the write is accepted, then finish on the result.
        if pending.event.wait(0.4):
            return self._finish_rpc(request_id, pending)
        return {}

    def _set_thinking(self, level: str) -> None:
        if level in {"off", "none", "minimal"}:
            level = "low"
        if level not in {"low", "medium", "high", "xhigh", "max"}:
            raise WebError("EFFORT_UNSUPPORTED", "这条模型通道不支持所选 effort，请重新选择。", 409)
        if level == "max":
            level = "xhigh"
        try:
            self._set_config("reasoning_effort", level)
        except WebError:
            # Some grok builds only expose effort as a model picker suffix.
            self._thinking_level = level
            return
        self._thinking_level = level

    def _set_config(self, config_id: str, value: str) -> None:
        if not self._session_id:
            raise DriverClosedError("grok session is not ready")
        result = self._rpc(
            "session/set_config_option",
            {"sessionId": self._session_id, "configId": config_id, "value": {"value": value}},
        )
        if isinstance(result, dict):
            self._apply_session_result(result)

    def _begin_rpc(self, method: str, params=None) -> tuple[int, _Pending]:
        with self._state_lock:
            if self._exit_code is not None:
                raise DriverClosedError("grok process exited")
            request_id = self._next_request_id
            self._next_request_id += 1
            pending = _Pending()
            self._pending[request_id] = pending
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            payload["params"] = params
        try:
            self._write(payload)
        except (BrokenPipeError, OSError) as exc:
            with self._state_lock:
                self._pending.pop(request_id, None)
            raise DriverWriteUnconfirmedError(f"grok stdin write failed: {exc.__class__.__name__}") from exc
        return request_id, pending

    def _await_rpc(self, request_id: int, pending: _Pending, wait_seconds: float) -> dict:
        if not pending.event.wait(wait_seconds):
            with self._state_lock:
                self._pending.pop(request_id, None)
                self._prompt_ids.discard(request_id)
            raise RpcTimeoutError(f"grok ACP timeout after {wait_seconds}s")
        return self._finish_rpc(request_id, pending)

    def _finish_rpc(self, request_id: int, pending: _Pending, *, quiet: bool = False) -> dict:
        with self._state_lock:
            self._prompt_ids.discard(request_id)
        if pending.error:
            if quiet:
                return {}
            raise WebError("COMMAND_FAILED", _clip(pending.error, 800), 409)
        return pending.response if isinstance(pending.response, dict) else {}

    def _rpc(self, method: str, params=None, *, timeout: float | None = None, quiet: bool = False) -> dict:
        request_id, pending = self._begin_rpc(method, params)
        wait_seconds = self._response_timeout if timeout is None else timeout
        try:
            return self._await_rpc(request_id, pending, wait_seconds)
        except WebError:
            if quiet:
                return {}
            raise

    def _write(self, payload: dict) -> None:
        line = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        with self._write_lock:
            stdin = self._proc.stdin
            if stdin is None or stdin.closed:
                raise DriverClosedError("grok stdin closed")
            stdin.write(line)
            stdin.flush()

    def _terminate_group(self, sig) -> None:
        try:
            if os.getpgid(self._proc.pid) == self._proc.pid:
                os.killpg(self._proc.pid, sig)
            else:
                self._proc.send_signal(sig)
        except (OSError, AttributeError):
            pass

    # -- IO -------------------------------------------------------------

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
                try:
                    self._handle_line(line.decode("utf-8", "replace"))
                except Exception as exc:
                    self._record_event_error(exc)
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
            item.error = "process exited"
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

    def _record_event_error(self, exc: Exception) -> None:
        detail = f"{type(exc).__name__}: {_clip(str(exc), 400)}"
        self._stderr_tail = (self._stderr_tail + "\nACP event handling error: " + detail)[-_STDERR_TAIL_BYTES:]
        try:
            self._sink.upsert_event(
                {
                    "id": f"n-rpc-{uuid.uuid4().hex[:12]}",
                    "kind": "notice",
                    "title": "RPC 事件处理异常",
                    "text": "Grok 仍在运行，但有一条事件未能写入会话；后续事件会继续接收。",
                }
            )
        except Exception:
            pass

    def _handle_line(self, line: str) -> None:
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            self._notice("收到非 RPC 输出，已跳过。", title="协议异常")
            return
        if not isinstance(message, dict):
            self._notice("收到非对象的 RPC 消息", title="协议异常")
            return
        if "id" in message and ("result" in message or "error" in message):
            self._handle_response(message)
            return
        method = str(message.get("method") or "")
        if method == "session/request_permission" and "id" in message:
            self._handle_permission(message)
            return
        if method == "session/update":
            params = message.get("params") if isinstance(message.get("params"), dict) else {}
            update = params.get("update") if isinstance(params.get("update"), dict) else {}
            self._handle_update(update)
            return
        if method == "_x.ai/queue/changed":
            self._handle_native_queue(message.get("params") if isinstance(message.get("params"), dict) else {})
            return
        if method == "_x.ai/session_notification":
            params = message.get("params") if isinstance(message.get("params"), dict) else {}
            update = params.get("update") if isinstance(params.get("update"), dict) else {}
            if update.get("sessionUpdate") == "retry_state" and update.get("type") == "retrying":
                self._activity("retrying")
            return

    def _handle_response(self, message: dict) -> None:
        try:
            request_id = int(message.get("id"))
        except (TypeError, ValueError):
            return
        with self._state_lock:
            pending = self._pending.pop(request_id, None)
        if pending is None:
            return
        if "error" in message:
            error = message.get("error")
            pending.error = str((error or {}).get("message") if isinstance(error, dict) else error or "unknown error")
            pending.response = {}
        else:
            result = message.get("result")
            pending.response = result if isinstance(result, dict) else {}
            pending.error = None
        pending.event.set()
        with self._state_lock:
            in_flight = request_id in self._prompt_ids
        if in_flight:
            try:
                result = self._finish_rpc(request_id, pending, quiet=True)
            except WebError as exc:
                self._notice(exc.message, title="命令错误")
                result = {}
            self._turn_end(result)

    def _handle_permission(self, message: dict) -> None:
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        options = params.get("options") if isinstance(params.get("options"), list) else []
        tool = params.get("toolCall") if isinstance(params.get("toolCall"), dict) else {}
        title = str(tool.get("title") or tool.get("kind") or "等待确认")
        allow_id = ""
        reject_id = ""
        names = []
        for option in options:
            if not isinstance(option, dict):
                continue
            option_id = str(option.get("optionId") or option.get("option_id") or "")
            kind = str(option.get("kind") or "")
            names.append(str(option.get("name") or option_id))
            if kind.startswith("allow") and not allow_id:
                allow_id = option_id
            if kind.startswith("reject") and not reject_id:
                reject_id = option_id
        approval_id = f"g{message.get('id')}"
        with self._state_lock:
            self._ui_pending[approval_id] = {
                "method": "confirm",
                "title": title,
                "options": names,
                "allowId": allow_id,
                "rejectId": reject_id,
                "rpcId": message.get("id"),
            }
        self._upsert(
            {
                "id": f"a-{approval_id}",
                "kind": "approval",
                "approvalId": approval_id,
                "method": "confirm",
                "options": names,
                "title": title,
                "text": title + (("\n" + " / ".join(names)) if names else ""),
            }
        )
        self._sink.approval_pending(approval_id, "confirm", title)
        self._sink.set_proto_state("waiting")

    def _handle_update(self, update: dict) -> None:
        kind = str(update.get("sessionUpdate") or "")
        if self._replay and kind in {
            "agent_message_chunk",
            "agent_message",
            "agent_thought_chunk",
            "agent_thought",
            "tool_call",
            "tool_call_update",
        }:
            return
        if kind in {"agent_message_chunk", "agent_message"}:
            self._ensure_assistant()
            text = _content_text(update.get("content") if "content" in update else update)
            if text:
                self._activity("responding", eventId=self._open_assistant_id)
                self._upsert({"id": self._open_assistant_id, "kind": "assistant", "textAppend": text})
        elif kind in {"agent_thought_chunk", "agent_thought"}:
            self._ensure_assistant()
            text = _content_text(update.get("content") if "content" in update else update)
            if text:
                self._activity("thinking", eventId=self._open_assistant_id)
                self._upsert({"id": self._open_assistant_id, "kind": "assistant", "thinkingAppend": text})
        elif kind == "tool_call":
            self._handle_tool_call(update, starting=True)
        elif kind == "tool_call_update":
            self._handle_tool_call(update, starting=False)
        elif kind == "available_commands_update":
            commands = update.get("availableCommands") or update.get("available_commands") or []
            if isinstance(commands, list):
                with self._state_lock:
                    self._commands = [item for item in commands if isinstance(item, dict)]
        elif kind in {"current_mode_update", "plan"}:
            return
        elif kind == "usage_update":
            usage = update.get("usage") if isinstance(update.get("usage"), dict) else {}
            if usage:
                with self._state_lock:
                    self._usage = {"tokens": usage, "contextUsage": usage}

    def _handle_tool_call(self, update: dict, *, starting: bool) -> None:
        call_id = str(update.get("toolCallId") or update.get("toolCallID") or uuid.uuid4().hex[:8])
        name = str(update.get("title") or update.get("toolName") or update.get("kind") or "tool")
        status = str(update.get("status") or ("in_progress" if starting else "completed"))
        fields = {"id": f"t-{call_id}", "kind": "tool", "title": name}
        if status in {"pending", "in_progress", "running"}:
            self._active_tools[call_id] = name
            self._activity("tool", eventId=fields["id"], toolName=name)
            fields["status"] = "running"
            raw = update.get("rawInput") or update.get("raw_input") or update.get("content")
            fields["text"] = _clip(json.dumps(raw, ensure_ascii=False) if isinstance(raw, (dict, list)) else str(raw or ""), _TEXT_SNIPPET_LIMIT)
            fields["arguments"] = raw if isinstance(raw, dict) else {}
        else:
            self._active_tools.pop(call_id, None)
            if self._active_tools:
                active_id, active_name = next(iter(self._active_tools.items()))
                self._activity("tool", eventId=f"t-{active_id}", toolName=active_name)
            else:
                self._activity("running")
            fields["status"] = "error" if status in {"failed", "error"} else "done"
            raw = update.get("rawOutput") or update.get("raw_output") or update.get("content")
            fields["text"] = _clip(
                json.dumps(raw, ensure_ascii=False) if isinstance(raw, (dict, list)) else str(raw or ""),
                _TEXT_SNIPPET_LIMIT,
            )
        self._upsert(fields)

    def _ensure_assistant(self) -> None:
        if self._open_assistant_id:
            return
        self._open_assistant_id = f"m-{uuid.uuid4().hex[:12]}"
        self._upsert({"id": self._open_assistant_id, "kind": "assistant", "text": ""})

    def _turn_begin(self) -> None:
        self._open_assistant_id = None
        self._active_tools.clear()
        self._sink.set_proto_state("running")
        self._activity("running")

    def _turn_end(self, result) -> None:
        self._streaming = False
        if self._open_assistant_id:
            self._activity("idle")
        self._open_assistant_id = None
        waiting = bool(self.pending_approvals())
        self._sink.set_proto_state("waiting" if waiting else "idle")
        self._flush_queue()
        if isinstance(result, dict) and result.get("stopReason") in {"cancelled", "canceled"}:
            self._activity("stopped")

    def _flush_queue(self) -> None:
        with self._state_lock:
            next_text = self._steering.pop(0) if self._steering else (self._follow_up.pop(0) if self._follow_up else "")
        self._emit_queue()
        if next_text:
            self._upsert({"consumedPrompt": next_text})
            threading.Thread(target=self._prompt, args=(next_text,), daemon=True, name="grok-queue-flush").start()

    def _handle_native_queue(self, params: dict) -> None:
        entries = params.get("entries") if isinstance(params.get("entries"), list) else []
        texts = [str(item.get("text") or "") for item in entries if isinstance(item, dict)]
        running = str(params.get("runningText") or "").strip()
        if running:
            self._streaming = True
            self._sink.set_proto_state("running")
        self._upsert({
            "id": "n-queue",
            "kind": "notice",
            "title": "待发送消息",
            "text": f"还有 {len(texts)} 条补充消息等待执行" if texts else "待发送队列已清空",
            "queue": texts,
            "queueSteering": [],
            "queueFollowUp": texts,
        })

    def _emit_queue(self) -> None:
        with self._state_lock:
            steering = list(self._steering)
            follow_up = list(self._follow_up)
        queue = [*steering, *follow_up]
        self._upsert({
            "id": "n-queue",
            "kind": "notice",
            "title": "待发送消息",
            "text": f"还有 {len(queue)} 条补充消息等待执行" if queue else "待发送队列已清空",
            "queue": queue,
            "queueSteering": steering,
            "queueFollowUp": follow_up,
        })

    def _apply_session_result(self, result: dict) -> None:
        models = result.get("models") if isinstance(result.get("models"), dict) else {}
        self._apply_model_state(models)
        options = result.get("configOptions") if isinstance(result.get("configOptions"), list) else []
        for option in options:
            if not isinstance(option, dict):
                continue
            if option.get("id") == "reasoning_effort" or option.get("category") == "thought_level":
                current = option.get("currentValue")
                if isinstance(current, str) and current:
                    self._thinking_level = current

    def _apply_model_state(self, state) -> None:
        if not isinstance(state, dict):
            return
        current = str(state.get("currentModelId") or self._model.get("id") or "")
        available = state.get("availableModels") if isinstance(state.get("availableModels"), list) else []
        match = next((item for item in available if isinstance(item, dict) and str(item.get("modelId") or "") == current), None)
        if current:
            self._model["id"] = current
            self._model["name"] = str((match or {}).get("name") or current)
        meta = (match or {}).get("_meta") if isinstance(match, dict) else {}
        if isinstance(meta, dict):
            window = int(meta.get("totalContextTokens") or 0)
            if window:
                self._model["contextWindow"] = window
            efforts = meta.get("reasoningEfforts") if isinstance(meta.get("reasoningEfforts"), list) else []
            mapping = {}
            for item in efforts:
                if isinstance(item, dict) and item.get("id"):
                    mapping[str(item["id"])] = str(item.get("value") or item["id"])
                    if item.get("default"):
                        self._thinking_level = str(item.get("value") or item["id"])
            if mapping:
                self._model["thinkingLevelMap"] = mapping
                self._model["reasoning"] = True
            current_effort = meta.get("reasoningEffort")
            if isinstance(current_effort, str) and current_effort:
                self._thinking_level = current_effort

    def _upsert(self, fields: dict) -> None:
        self._sink.upsert_event(fields)

    def _notice(self, text: str, *, title: str | None = None) -> None:
        self._upsert({"id": f"n-{uuid.uuid4().hex[:12]}", "kind": "notice", "text": _clip(text, _NOTICE_TEXT_LIMIT), "title": title})

    def _activity(self, phase: str, **details) -> None:
        self._sink.set_activity(phase, **details)


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        if content.get("type") == "text":
            return str(content.get("text") or "")
        if "text" in content:
            return str(content.get("text") or "")
        if "data" in content and content.get("type") in {None, "text"}:
            return str(content.get("data") or "")
        inner = content.get("content")
        if inner is not None and inner is not content:
            return _content_text(inner)
        return ""
    if isinstance(content, list):
        return "".join(_content_text(item) for item in content)
    return ""
