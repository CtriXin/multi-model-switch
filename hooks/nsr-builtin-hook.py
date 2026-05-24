#!/usr/bin/env python3
"""Built-in NSR hook fallback for MMS session-local hooks.

This keeps NSR hook support usable even when the external Non-Stop-Run repo is
not installed. If a full NSR runtime is installed, the shell wrappers prefer it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _clean(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _real_home() -> Path:
    for key in ("MMS_REAL_HOME", "REAL_HOME", "ORIGINAL_HOME"):
        raw = _clean(os.environ.get(key))
        if raw:
            path = Path(raw).expanduser()
            if path.is_dir():
                return path
    home = Path(os.environ.get("HOME", str(Path.home()))).expanduser()
    match = re.match(r"^(/(?:Users|home)/[^/]+)/\.config/mms/", str(home))
    if match:
        return Path(match.group(1))
    return home


def _state_root() -> Path:
    for key in ("MMS_NSR_STATE_HOME", "NSR_STATE_HOME"):
        raw = _clean(os.environ.get(key))
        if raw:
            return Path(raw).expanduser().resolve()
    nsr_home = _clean(os.environ.get("NSR_HOME"))
    if nsr_home:
        root = Path(nsr_home).expanduser().resolve()
        # Historically NSR_HOME was sometimes used as the tool root. Avoid
        # treating that checkout as the state directory when scripts/ exists.
        if not (root / "scripts" / "controller.py").exists():
            return root
    return (_real_home() / ".nsr").resolve()


def _load_request() -> dict[str, Any]:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _project_root_from(request: dict[str, Any]) -> str:
    for key in ("cwd", "project_root", "workspace", "workspace_dir"):
        value = _clean(request.get(key))
        if value:
            return value
    for key in ("MMS_PROJECT_ROOT", "CLAUDE_PROJECT_DIR", "PWD"):
        value = _clean(os.environ.get(key))
        if value:
            return value
    try:
        return str(Path.cwd().resolve())
    except Exception:
        return ""


def _session_id_from(request: dict[str, Any], project_root: str) -> str:
    for key in ("session_id", "sessionId", "conversation_id", "thread_id"):
        value = _clean(request.get(key))
        if value:
            return value
    for key in ("NSR_SESSION_ID", "CODEX_THREAD_ID", "CLAUDE_SESSION_ID"):
        value = _clean(os.environ.get(key))
        if value:
            return value
    digest = hashlib.sha1((project_root or "local").encode("utf-8")).hexdigest()[:12]
    return f"local-{digest}"


def _event_name_from(request: dict[str, Any]) -> str:
    for key in ("hook_event_name", "hookEventName", "event"):
        value = _clean(request.get(key))
        if value:
            return value
    return ""


def _session_dir(session_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", session_id)[:180] or "local"
    return _state_root() / "sessions" / safe


def _state_path(session_id: str) -> Path:
    return _session_dir(session_id) / "state.json"


def _load_state(session_id: str) -> dict[str, Any] | None:
    path = _state_path(session_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _save_state(session_id: str, state: dict[str, Any]) -> None:
    path = _state_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _append_event(session_id: str, state: dict[str, Any], kind: str, summary: str, detail: str = "") -> None:
    session_dir = _session_dir(session_id)
    session_dir.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": _now_iso(),
        "kind": _clean(kind),
        "summary": _clean(summary),
        "detail": _clean(detail)[:1000],
        "source": "mms-builtin-nsr-hook",
    }
    with (session_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
    trace = state.setdefault("trace", {})
    if isinstance(trace, dict):
        trace["latest_event"] = entry["summary"]
        try:
            trace["event_count"] = int(trace.get("event_count", 0) or 0) + 1
        except Exception:
            trace["event_count"] = 1
    runtime = state.setdefault("runtime", {})
    if isinstance(runtime, dict):
        runtime["updated_at"] = _now_iso()
        runtime.setdefault("schema_version", SCHEMA_VERSION)
    _save_state(session_id, state)


def _active(state: dict[str, Any] | None) -> bool:
    if not isinstance(state, dict):
        return False
    runtime = state.get("runtime") if isinstance(state.get("runtime"), dict) else {}
    return _clean(runtime.get("mode", "disabled")).lower() == "active"


def _brief(value: object, limit: int = 180) -> str:
    text = " ".join(_clean(value).split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _context_message(state: dict[str, Any], *, event: str = "") -> str:
    goal = state.get("goal") if isinstance(state.get("goal"), dict) else {}
    loop = state.get("loop") if isinstance(state.get("loop"), dict) else {}
    quality = state.get("quality") if isinstance(state.get("quality"), dict) else {}
    parts = ["[nsr] active execution loop"]
    objective = _brief(goal.get("objective"), 160)
    if objective:
        parts.append(f"objective: {objective}")
    current_slice = _brief(loop.get("current_slice"), 140)
    if current_slice:
        parts.append(f"slice: {current_slice}")
    next_action = _brief(loop.get("next_action"), 180)
    if next_action:
        parts.append(f"next_action: {next_action}")
    validation = _brief(quality.get("validation_summary"), 160)
    if validation:
        parts.append(f"validation: {validation}")
    if event:
        parts.append(f"event: {event}")
    return "\n".join(parts)


def _json_response(payload: dict[str, Any], *, host: str) -> None:
    if host == "codex" and payload == {"continue": True}:
        return
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def _output_context(event_name: str, message: str) -> dict[str, Any]:
    return {
        "continue": True,
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": message,
        },
    }


def _handle(host: str, request: dict[str, Any]) -> dict[str, Any]:
    project_root = _project_root_from(request)
    session_id = _session_id_from(request, project_root)
    event_name = _event_name_from(request)
    state = _load_state(session_id)
    if not _active(state):
        return {"continue": True}

    assert state is not None
    if event_name == "SessionStart":
        _append_event(session_id, state, "session_start", f"{host} SessionStart")
        refreshed = _load_state(session_id) or state
        return _output_context(event_name, _context_message(refreshed, event="session_start"))
    if event_name == "UserPromptSubmit":
        return _output_context(event_name, _context_message(state, event="user_prompt"))
    if event_name == "PreCompact":
        _append_event(session_id, state, "precompact", f"{host} PreCompact")
        return {"continue": True}
    if event_name == "PostCompact":
        _append_event(session_id, state, "postcompact", f"{host} PostCompact")
        return {"continue": True}
    if event_name in {"PreToolUse", "PostToolUse"}:
        tool_name = _clean(request.get("tool_name")) or _clean(request.get("tool")) or "tool"
        _append_event(session_id, state, event_name.lower(), tool_name)
        return {"continue": True}
    if event_name == "PermissionRequest":
        tool_name = _clean(request.get("tool_name")) or "permission_request"
        reason = _clean(request.get("reason"))
        _append_event(session_id, state, "permission_request", tool_name, reason)
        return {"hookSpecificOutput": {"hookEventName": event_name}}
    if event_name == "Stop":
        loop = state.get("loop") if isinstance(state.get("loop"), dict) else {}
        status = _clean(loop.get("status", "running")).lower()
        next_action = _clean(loop.get("next_action"))
        if status not in {"blocked", "complete"} and next_action:
            return {"decision": "block", "reason": _context_message(state, event="stop")}
        return {"continue": True}
    return {"continue": True}


def main(argv: list[str]) -> int:
    host = _clean(argv[1] if len(argv) > 1 else "") or _clean(os.environ.get("MMS_NSR_HOST")) or "unknown"
    _json_response(_handle(host, _load_request()), host=host)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
