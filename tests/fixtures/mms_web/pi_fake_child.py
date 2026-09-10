"""Task-owned Pi RPC fake child for MMS Pilot session driver tests.

Protocol: strict JSONL over stdin/stdout (LF framing, optional trailing CR).
Behavior is driven by prompt-message keywords so tests can exercise the real
driver against a real subprocess without any model/provider access.

A background thread reads stdin and pushes parsed commands into a queue; the
main thread processes them. Dialog (extension UI) waits poll the same queue so
answers and aborts are handled while a request is pending.

Prompt keywords (checked in order):
  crash            exit 3 immediately, no response
  exit1            normal reply, then exit code 1
  exit0            normal reply, then exit code 0
  malformed        emit one non-JSON line, then normal reply
  split            emit a JSON line in two chunks (tests client buffering)
  stderr           write to stderr, then normal reply
  fail             respond {"success": false} for the prompt
  tool             normal reply plus tool_execution_* events
  approval-confirm normal reply plus a confirm dialog that blocks until answer
  approval-select  normal reply plus a select dialog that blocks until answer
  approval-notify  normal reply plus a fire-and-forget notify request
  stream-forever   agent_start then endless deltas; abort ends it

Stdin EOF exits 0.
"""

from __future__ import annotations

import json
import queue
import sys
import threading
import time

_ABORT = object()


def _out(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _respond(req_id, command: str, *, success: bool = True, data=None, error=None) -> None:
    payload = {"id": req_id, "type": "response", "command": command, "success": success}
    if data is not None:
        payload["data"] = data
    if error is not None:
        payload["error"] = error
    _out(payload)


def _assistant_text_events(text: str):
    yield {"type": "message_start", "message": {"role": "assistant", "content": []}}
    yield {
        "type": "message_update",
        "usage": {"input": 1, "output": 0, "cacheRead": 0, "cacheWrite": 0},
        "assistantMessageEvent": {"type": "text_start", "contentIndex": 0},
    }
    half = max(1, len(text) // 2)
    for chunk in (text[:half], text[half:]):
        if not chunk:
            continue
        yield {
            "type": "message_update",
            "usage": {"input": 1, "output": 1, "cacheRead": 0, "cacheWrite": 0},
            "assistantMessageEvent": {"type": "text_delta", "contentIndex": 0, "delta": chunk},
        }
    yield {
        "type": "message_update",
        "usage": {"input": 1, "output": 1, "cacheRead": 0, "cacheWrite": 0},
        "assistantMessageEvent": {"type": "text_end", "contentIndex": 0, "content": text},
    }
    message = {
        "role": "assistant",
        "content": [{"type": "text", "text": text}],
        "model": "fake-model",
        "usage": {"input": 1, "output": 1},
        "stopReason": "stop",
    }
    yield {"type": "message_end", "message": message}
    yield {"type": "turn_end", "message": message, "toolResults": []}


def _run_agent(message: str, *, text: str | None = None) -> None:
    _out({"type": "agent_start"})
    _out({"type": "turn_start"})
    reply = text if text is not None else f"echo: {message}"
    for event in _assistant_text_events(reply):
        _out(event)
    _out({"type": "agent_end", "messages": [], "willRetry": False})
    _out({"type": "agent_settled"})


def _run_tool_flow(message: str) -> None:
    _out({"type": "agent_start"})
    _out({"type": "turn_start"})
    call_id = "call_fake_tool_1"
    _out({"type": "tool_execution_start", "toolCallId": call_id, "toolName": "read", "args": {"path": "/tmp/fake.txt"}})
    _out(
        {
            "type": "tool_execution_update",
            "toolCallId": call_id,
            "toolName": "read",
            "args": {"path": "/tmp/fake.txt"},
            "partialResult": {"content": [{"type": "text", "text": "partial line"}]},
        }
    )
    _out(
        {
            "type": "tool_execution_end",
            "toolCallId": call_id,
            "toolName": "read",
            "result": {"content": [{"type": "text", "text": "final tool output"}]},
            "isError": False,
        }
    )
    for event in _assistant_text_events("tool finished for " + message):
        _out(event)
    _out({"type": "agent_end", "messages": [], "willRetry": False})
    _out({"type": "agent_settled"})


class ChildRuntime:
    def __init__(self) -> None:
        self.queue: queue.Queue = queue.Queue()
        self.stream_deadline = time.monotonic() + 30.0
        self.thinking_level = "high"

    # -- stdin ----------------------------------------------------------

    def read_stdin(self) -> None:
        for raw_line in sys.stdin.buffer:
            line = raw_line[:-1] if raw_line.endswith(b"\n") else raw_line
            if line.endswith(b"\r"):
                line = line[:-1]
            if not line.strip():
                continue
            try:
                command = json.loads(line.decode("utf-8"))
                if not isinstance(command, dict):
                    raise ValueError("not an object")
            except Exception:
                _respond(None, "parse", success=False, error="Failed to parse command")
                continue
            self.queue.put(command)
        self.queue.put(None)

    def next_command(self, timeout: float | None = None):
        try:
            return self.queue.get(timeout=timeout)
        except queue.Empty:
            return _ABORT if False else None

    # -- dialog waits -----------------------------------------------------

    def wait_dialog_answer(self, request_id: str, timeout: float = 15.0):
        """Wait for the matching extension_ui_response; handle other commands meanwhile."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                item = self.queue.get(timeout=0.05)
            except queue.Empty:
                continue
            if item is None:
                return None
            if item.get("type") == "extension_ui_response" and str(item.get("id") or "") == request_id:
                return item
            if item.get("type") == "abort":
                self.handle_abort(item)
                return _ABORT
            self.process(item)
        return None

    # -- command processing ----------------------------------------------

    def handle_abort(self, command: dict) -> None:
        _respond(command.get("id"), "abort")
        _out({"type": "agent_settled"})

    def process(self, command: dict) -> None:
        req_id = command.get("id")
        ctype = str(command.get("type") or "")

        if ctype == "extension_ui_response":
            # Late answer with no pending dialog: ignore silently.
            return

        if ctype == "prompt":
            self.handle_prompt(req_id, str(command.get("message") or ""))
            return

        if ctype == "abort":
            self.handle_abort(command)
            return

        if ctype == "set_thinking_level" and "--reasoning" in sys.argv:
            self.thinking_level = command.get("level")
            _respond(req_id, ctype, data={"level": self.thinking_level})
            return

        if ctype == "get_state":
            _respond(
                req_id,
                "get_state",
                # A real Pi reports the model it loaded; the launch path checks
                # for it before treating the session as usable.
                data={"isStreaming": False, "sessionId": "fake", "messageCount": 0,
                      "thinkingLevel": self.thinking_level,
                      "model": {"id": "fake-model", "reasoning": "--reasoning" in sys.argv}},
            )
            return

        _respond(req_id, ctype, success=False, error=f"unsupported command: {ctype}")

    def handle_prompt(self, req_id, message: str) -> None:
        if message == "fail":
            _respond(req_id, "prompt", success=False, error="simulated prompt rejection")
            return
        if message == "never-answered":
            # Deliberately no response: exercises client-side timeouts.
            return
        _respond(req_id, "prompt")
        if message == "crash":
            sys.stdout.flush()
            import os

            os._exit(3)
        if message == "malformed":
            sys.stdout.write("this-line-is-not-json\n")
            sys.stdout.flush()
            _run_agent(message)
            return
        if message == "split":
            blob = json.dumps({"type": "agent_start"}) + "\n"
            half = len(blob) // 2
            sys.stdout.write(blob[:half])
            sys.stdout.flush()
            time.sleep(0.05)
            sys.stdout.write(blob[half:])
            sys.stdout.flush()
            _run_agent(message)
            return
        if message == "stderr":
            sys.stderr.write("fake child stderr diagnostic\n")
            sys.stderr.flush()
            _run_agent(message)
            return
        if message == "exit1":
            _run_agent(message)
            sys.stdout.flush()
            import os

            os._exit(1)
        if message == "exit0":
            _run_agent(message)
            sys.stdout.flush()
            import os

            os._exit(0)
        if message == "tool":
            _run_tool_flow(message)
            return
        if message == "approval-confirm":
            self.run_dialog(req_id, message, method="confirm")
            return
        if message == "approval-select":
            self.run_dialog(req_id, message, method="select")
            return
        if message == "approval-notify":
            _out({"type": "agent_start"})
            _out(
                {
                    "type": "extension_ui_request",
                    "id": "ui-notify-1",
                    "method": "notify",
                    "message": "fake notify text",
                    "notifyType": "warning",
                }
            )
            _run_agent(message, text="notify sent")
            return
        if message == "stream-forever":
            self.run_stream_forever(req_id, message)
            return
        _run_agent(message)

    def run_dialog(self, req_id, message: str, *, method: str) -> None:
        _out({"type": "agent_start"})
        request_id = f"ui-{method}-1"
        request = {
            "type": "extension_ui_request",
            "id": request_id,
            "method": method,
            "title": "Allow fake action?" if method == "confirm" else "Choose fake option",
            "timeout": 30000,
        }
        if method == "confirm":
            request["message"] = "The fake child wants confirmation."
        else:
            request["options"] = ["Allow", "Block"]
        _out(request)
        answer = self.wait_dialog_answer(request_id)
        if answer is _ABORT:
            _out({"type": "agent_end", "messages": [], "willRetry": False})
            return
        if method == "confirm":
            confirmed = "cancelled" not in answer and bool(answer.get("confirmed"))
            for event in _assistant_text_events(f"confirm answered: {confirmed}"):
                _out(event)
        else:
            cancelled = answer is None or bool(answer.get("cancelled"))
            for event in _assistant_text_events(f"select cancelled: {cancelled}"):
                _out(event)
        _out({"type": "agent_end", "messages": [], "willRetry": False})
        _out({"type": "agent_settled"})

    def run_stream_forever(self, req_id, message: str) -> None:
        _out({"type": "agent_start"})
        _out({"type": "turn_start"})
        _out({"type": "message_start", "message": {"role": "assistant", "content": []}})
        piece = 0
        while time.monotonic() < self.stream_deadline:
            try:
                item = self.queue.get(timeout=0.02)
            except queue.Empty:
                item = None
            if item is None:
                _out(
                    {
                        "type": "message_update",
                        "usage": {"input": 1, "output": piece + 1, "cacheRead": 0, "cacheWrite": 0},
                        "assistantMessageEvent": {
                            "type": "text_delta",
                            "contentIndex": 0,
                            "delta": f"chunk{piece} ",
                        },
                    }
                )
                piece += 1
                continue
            if item.get("type") == "abort":
                self.handle_abort(item)
                return
            self.process(item)
        _out({"type": "agent_settled"})


def main() -> int:
    runtime = ChildRuntime()
    reader = threading.Thread(target=runtime.read_stdin, daemon=True)
    reader.start()
    while True:
        command = runtime.queue.get()
        if command is None:
            break
        runtime.process(command)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        raise SystemExit(0)
