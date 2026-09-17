"""Task-owned Grok ACP v1 fake child for MMS Pilot driver tests.

Newline JSON-RPC 2.0, matching grok 1.0.34 initialize + session/new. Prompt
keywords (checked in order):
  crash            exit 3 immediately
  malformed        emit a non-JSON line, then a normal reply
  tool             stream a tool_call then text
  approval-confirm request_permission, wait for the client result
  stream-forever   chunks until session/cancel
  fail             return a JSON-RPC error for the prompt
"""

from __future__ import annotations

import json
import queue
import sys
import threading
import time

_ABORT = object()
SESSION_ID = "sess-fake-grok"


def _out(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _result(req_id, payload=None) -> None:
    _out({"jsonrpc": "2.0", "id": req_id, "result": payload if payload is not None else {}})


def _error(req_id, message: str) -> None:
    _out({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32000, "message": message}})


def _update(kind: str, **fields) -> None:
    _out({
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {"sessionId": SESSION_ID, "update": {"sessionUpdate": kind, **fields}},
    })


def _text_turn(text: str) -> None:
    _update("agent_thought_chunk", content={"type": "text", "text": "thinking "})
    half = max(1, len(text) // 2)
    _update("agent_message_chunk", content={"type": "text", "text": text[:half]})
    _update("agent_message_chunk", content={"type": "text", "text": text[half:]})


class ChildRuntime:
    def __init__(self) -> None:
        self.queue: queue.Queue = queue.Queue()
        self.thinking = "high"
        self.model = "dummy"
        self.stream_deadline = time.monotonic() + 30.0

    def read_stdin(self) -> None:
        for raw_line in sys.stdin.buffer:
            line = raw_line[:-1] if raw_line.endswith(b"\n") else raw_line
            if line.endswith(b"\r"):
                line = line[:-1]
            if not line.strip():
                continue
            try:
                message = json.loads(line.decode("utf-8"))
            except Exception:
                continue
            if isinstance(message, dict):
                self.queue.put(message)
        self.queue.put(_ABORT)

    def next_message(self, timeout: float = 30.0):
        try:
            return self.queue.get(timeout=timeout)
        except queue.Empty:
            return _ABORT

    def handle(self, message: dict) -> str | None:
        method = str(message.get("method") or "")
        req_id = message.get("id")
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        if method == "initialize":
            _result(req_id, {
                "protocolVersion": 1,
                "agentCapabilities": {
                    "loadSession": True,
                    "promptCapabilities": {"image": False, "audio": False, "embeddedContext": True},
                    "sessionCapabilities": {"list": {}, "resume": {}, "close": {}},
                },
                "authMethods": [{"id": "xai.api_key", "name": "xai.api_key"}],
                "_meta": {
                    "modelState": {
                        "currentModelId": self.model,
                        "availableModels": [{
                            "modelId": self.model,
                            "name": "Dummy",
                            "_meta": {
                                "totalContextTokens": 8000,
                                "supportsReasoningEffort": True,
                                "reasoningEffort": "high",
                                "reasoningEfforts": [
                                    {"id": "low", "value": "low"},
                                    {"id": "medium", "value": "medium"},
                                    {"id": "high", "value": "high", "default": True},
                                    {"id": "xhigh", "value": "xhigh"},
                                ],
                            },
                        }],
                    }
                },
            })
            return None
        if method in {"session/new", "session/load", "session/resume"}:
            sid = SESSION_ID if method == "session/new" else str(params.get("sessionId") or SESSION_ID)
            self.loaded = method
            meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
            self.agent_profile = meta.get("agentProfile")
            if method in {"session/load", "session/resume"}:
                _update("agent_message_chunk", content={"type": "text", "text": "REPLAY should not appear"})
            _result(req_id, {
                "sessionId": sid,
                "models": {
                    "currentModelId": self.model,
                    "availableModels": [{"modelId": self.model, "name": "Dummy",
                                         "_meta": {"totalContextTokens": 8000, "reasoningEffort": self.thinking}}],
                },
                "configOptions": [
                    {"id": "model", "category": "model", "currentValue": self.model},
                    {"id": "reasoning_effort", "category": "thought_level", "currentValue": self.thinking},
                ],
            })
            _update("available_commands_update", availableCommands=[
                {"name": "compact", "description": "Compress conversation history"},
                {"name": "context", "description": "Show context window usage"},
            ])
            return None
        if method == "session/set_config_option":
            value = params.get("value")
            if isinstance(value, dict):
                value = value.get("value")
            if params.get("configId") == "reasoning_effort" and isinstance(value, str):
                self.thinking = value
            if params.get("configId") == "model" and isinstance(value, str):
                self.model = value
            _result(req_id, {
                "configOptions": [
                    {"id": "reasoning_effort", "category": "thought_level", "currentValue": self.thinking},
                    {"id": "model", "category": "model", "currentValue": self.model},
                ]
            })
            return None
        if method == "session/cancel":
            self.queue.put(_ABORT)
            _result(req_id, {})
            return None
        if method == "session/close":
            _result(req_id, {})
            return "exit"
        if method == "session/prompt":
            return self.handle_prompt(req_id, params)
        if req_id is not None:
            _error(req_id, f"unknown method {method}")
        return None

    def handle_prompt(self, req_id, params: dict) -> str | None:
        prompt = params.get("prompt") if isinstance(params.get("prompt"), list) else []
        text = "".join(
            str(block.get("text") or "") for block in prompt
            if isinstance(block, dict) and block.get("type") == "text"
        )
        if "slow" in text:
            _update("agent_message_chunk", content={"type": "text", "text": "hold "})
            time.sleep(0.55)
            _text_turn("echo: " + text)
            _result(req_id, {"stopReason": "end_turn"})
            return None
        if "crash" in text:
            sys.exit(3)
        if "malformed" in text:
            sys.stdout.write("not-json\n")
            sys.stdout.flush()
        if "fail" in text:
            _error(req_id, "upstream failed")
            return None
        if "approval-confirm" in text:
            _out({
                "jsonrpc": "2.0",
                "id": 9001,
                "method": "session/request_permission",
                "params": {
                    "sessionId": SESSION_ID,
                    "toolCall": {"title": "Run tests", "kind": "execute"},
                    "options": [
                        {"optionId": "allow-once", "name": "Allow", "kind": "allow_once"},
                        {"optionId": "reject-once", "name": "Reject", "kind": "reject_once"},
                    ],
                },
            })
            while True:
                message = self.next_message()
                if message is _ABORT:
                    _result(req_id, {"stopReason": "cancelled"})
                    return None
                if isinstance(message, dict) and message.get("id") == 9001:
                    break
                if isinstance(message, dict) and message.get("method") == "session/cancel":
                    _result(message.get("id"), {})
                    _result(req_id, {"stopReason": "cancelled"})
                    return None
            _text_turn("approved: " + text)
            _result(req_id, {"stopReason": "end_turn"})
            return None
        if "stream-forever" in text:
            _update("agent_message_chunk", content={"type": "text", "text": "start "})
            while time.monotonic() < self.stream_deadline:
                message = self.next_message(timeout=0.05)
                if message is _ABORT:
                    _result(req_id, {"stopReason": "cancelled"})
                    return None
                if isinstance(message, dict) and message.get("method") == "session/cancel":
                    _result(message.get("id"), {})
                    _result(req_id, {"stopReason": "cancelled"})
                    return None
                if isinstance(message, dict):
                    self.handle(message)
            _result(req_id, {"stopReason": "end_turn"})
            return None
        if "tool" in text:
            _update("tool_call", toolCallId="call1", title="read_file", kind="read",
                    status="in_progress", rawInput={"path": "/tmp/fake.txt"})
            _update("tool_call_update", toolCallId="call1", status="completed",
                    rawOutput={"text": "file body"})
        _text_turn("echo: " + text)
        _result(req_id, {"stopReason": "end_turn"})
        return None


def main() -> None:
    runtime = ChildRuntime()
    threading.Thread(target=runtime.read_stdin, daemon=True).start()
    while True:
        message = runtime.next_message()
        if message is _ABORT:
            break
        if not isinstance(message, dict):
            continue
        if runtime.handle(message) == "exit":
            break


if __name__ == "__main__":
    main()
