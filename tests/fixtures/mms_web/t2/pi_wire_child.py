"""Scenario-scripted fake Pi RPC child for T2 message-control tests.

Independent of ``pi_fake_child.py``: instead of hardcoded prompt keywords, this
child is driven by a JSONL scenario file and records a bidirectional wire log,
so tests can prove what MMS actually wrote to the Pi protocol (and in which
order the fake service answered) without any model or provider access.

Invocation::

    python3 pi_wire_child.py <scenario.jsonl> <wire-log.jsonl>

* Every command read from stdin is appended to the wire log as
  ``{"dir": "in", "line": {...}}`` at the moment it is processed.
* Every line this child writes to stdout is appended as
  ``{"dir": "out", "line": {...}}``. The log therefore preserves the causal
  order between what MMS sent and what the fake service did next.

Scenario file: one JSON object per line, each a rule::

    {
      "when":  {"type": "steer"},          # subset-match against the command
      "if":    {"dialog_open": "ui-1"},    # optional extra condition
      "reply": {"success": true},          # response envelope (id echoed)
      "emit":  [ {...}, ... ],             # protocol events written to stdout
      "wait_dialog": "ui-1",               # block until the dialog is answered
      "on_answer": [ ... ],                # emitted after the dialog resolves
      "sticky": false                      # rule fires once unless sticky
    }

A rule that never emits ``agent_end``/``agent_settled`` leaves the fake run
open, which is how scenarios stage "a turn is still in flight".

Any string value ``"$msg"`` inside reply/emit/on_answer is replaced with the
matched command's ``message`` field, so scenarios can echo the exact text MMS
sent. Commands that match no rule fall back to protocol-shaped defaults
(prompt echoes an assistant run without consuming the prompt, steer succeeds,
abort settles, get_state reports a usable model), which keeps scenario files
limited to the behavior under test.

Stdin EOF exits 0.
"""

from __future__ import annotations

import json
import queue
import sys
import threading
import time


def _assistant_run(text: str) -> list[dict]:
    """A complete assistant message: start, one delta, end, turn end."""
    return [
        {"type": "message_start", "message": {"role": "assistant", "content": []}},
        {
            "type": "message_update",
            "usage": {"input": 10, "output": 1, "cacheRead": 0, "cacheWrite": 0},
            "assistantMessageEvent": {"type": "text_delta", "contentIndex": 0, "delta": text},
        },
        {
            "type": "message_update",
            "usage": {"input": 10, "output": 1, "cacheRead": 0, "cacheWrite": 0},
            "assistantMessageEvent": {"type": "text_end", "contentIndex": 0, "content": text},
        },
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": text}],
                "model": "t2-fake-model",
                "usage": {"input": 10, "output": 1},
                "stopReason": "stop",
            },
        },
        {"type": "turn_end", "message": {}, "toolResults": []},
    ]


def _substitute(value, message: str):
    if isinstance(value, str):
        return message if value == "$msg" else value
    if isinstance(value, list):
        return [_substitute(item, message) for item in value]
    if isinstance(value, dict):
        return {key: _substitute(item, message) for key, item in value.items()}
    return value


class WireChild:
    def __init__(self, rules: list[dict], wire_path: str) -> None:
        self.rules = rules
        self.wire_path = wire_path
        self.wire: list[dict] = []
        self.commands: queue.Queue = queue.Queue()
        self.dialogs_open: set[str] = set()
        self._wire_lock = threading.Lock()

    # -- logging ---------------------------------------------------------

    def _flush_wire(self, obj: dict) -> None:
        with self._wire_lock:
            self.wire.append(obj)
            with open(self.wire_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(obj, ensure_ascii=False) + "\n")

    def log_out(self, obj: dict) -> None:
        self._flush_wire({"dir": "out", "line": obj})
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    def respond(self, req_id, command: str, *, success: bool = True, data=None, error=None) -> None:
        payload = {"id": req_id, "type": "response", "command": command, "success": success}
        if data is not None:
            payload["data"] = data
        if error is not None:
            payload["error"] = error
        self.log_out(payload)

    # -- stdin -----------------------------------------------------------

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
                self.log_out({"id": None, "type": "response", "command": "parse", "success": False,
                              "error": "Failed to parse command"})
                continue
            self.commands.put(command)
        self.commands.put(None)

    # -- rule matching -----------------------------------------------------

    def match_rule(self, command: dict) -> dict | None:
        message = str(command.get("message") or "")
        for index, rule in enumerate(self.rules):
            when = rule.get("when") or {}
            if any(command.get(key) != value for key, value in when.items()):
                continue
            extra = rule.get("if") or {}
            dialog = extra.get("dialog_open")
            if dialog is not None and dialog not in self.dialogs_open:
                continue
            if not rule.get("sticky"):
                self.rules.pop(index)
            return _substitute(rule, message)
        return None

    # -- command processing -------------------------------------------------

    def process(self, command: dict) -> None:
        self._flush_wire({"dir": "in", "line": command})
        req_id = command.get("id")
        ctype = str(command.get("type") or "")
        message = str(command.get("message") or "")

        if ctype == "extension_ui_response":
            # Handled inside dialog waits; a late answer without a dialog is
            # ignored, exactly like a real extension host would.
            return

        rule = self.match_rule(command)
        if rule is not None:
            self.run_rule(req_id, ctype, rule)
            return
        self.run_default(req_id, ctype, message, command)

    def run_rule(self, req_id, ctype: str, rule: dict) -> None:
        reply = rule.get("reply")
        if reply is None:
            reply = {"success": True}
        error = reply.get("error")
        self.respond(req_id, ctype, success=bool(reply.get("success", True)),
                     data=reply.get("data"), error=error)
        for event in rule.get("emit") or []:
            self.log_out(event)
        dialog = rule.get("wait_dialog")
        if dialog is None:
            return
        answer = self.wait_dialog(dialog)
        if answer != "answered":
            # aborted/eof/timeout: the run is over or the host is gone;
            # pretending the dialog was answered would be a fake outcome.
            return
        for event in rule.get("on_answer") or []:
            self.log_out(event)

    def wait_dialog(self, dialog_id: str, timeout: float = 20.0) -> str:
        """Wait for the dialog answer; abort settles the fake run."""
        self.dialogs_open.add(dialog_id)
        deadline = time.monotonic() + timeout
        try:
            while time.monotonic() < deadline:
                try:
                    item = self.commands.get(timeout=0.05)
                except queue.Empty:
                    continue
                if item is None:
                    return "eof"
                if item.get("type") == "extension_ui_response" and str(item.get("id") or "") == dialog_id:
                    self._flush_wire({"dir": "in", "line": item})
                    self.dialogs_open.discard(dialog_id)
                    return "answered"
                if item.get("type") == "abort":
                    self._flush_wire({"dir": "in", "line": item})
                    self.respond(item.get("id"), "abort")
                    self.log_out({"type": "agent_settled"})
                    self.dialogs_open.discard(dialog_id)
                    return "aborted"
                # Anything else (a steer attempting to bypass the dialog, a
                # queued follow-up) is logged and answered by the normal path.
                self.process(item)
        finally:
            self.dialogs_open.discard(dialog_id)
        return "timeout"

    def run_default(self, req_id, ctype: str, message: str, command: dict) -> None:
        if ctype == "prompt":
            self.respond(req_id, "prompt")
            self.log_out({"type": "agent_start"})
            self.log_out({"type": "turn_start"})
            for event in _assistant_run(f"echo: {message}"):
                self.log_out(event)
            self.log_out({"type": "agent_end", "messages": [], "willRetry": False})
            self.log_out({"type": "agent_settled"})
            return
        if ctype == "steer":
            # Real Pi only accepts steering mid-run; succeeding here keeps the
            # default harmless for scenarios that never steer.
            self.respond(req_id, "steer")
            return
        if ctype == "abort":
            self.respond(req_id, "abort")
            self.log_out({"type": "agent_settled"})
            return
        if ctype == "clear_queue":
            self.respond(req_id, "clear_queue", data={"steering": [], "followUp": []})
            return
        if ctype == "get_state":
            self.respond(req_id, "get_state", data={
                "isStreaming": False, "sessionId": "t2-fake", "messageCount": 0,
                "model": {"id": "t2-fake-model", "reasoning": True, "input": []},
            })
            return
        if ctype == "get_session_stats":
            self.respond(req_id, "get_session_stats", data={"tokens": {}, "totalMessages": 0})
            return
        self.respond(req_id, ctype, success=False, error=f"unsupported command: {ctype}")

    # -- main loop -----------------------------------------------------------

    def main(self) -> int:
        while True:
            command = self.commands.get()
            if command is None:
                return 0
            self.process(command)


def main() -> int:
    scenario_path, wire_path = sys.argv[1], sys.argv[2]
    with open(scenario_path, encoding="utf-8") as handle:
        rules = [json.loads(line) for line in handle if line.strip()]
    open(wire_path, "w").close()
    child = WireChild(rules, wire_path)
    reader = threading.Thread(target=child.read_stdin, daemon=True)
    reader.start()
    try:
        return child.main()
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
