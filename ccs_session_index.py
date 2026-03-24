"""Metadata index for MMS-managed project-scoped CLI sessions."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from ccs_project_store import (
    PRIMARY_CONFIG_DIR,
    claude_raw_entry_path,
    claude_state_sessions_root,
    ensure_claude_project_store,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _slot_state_path(cwd: str, pid: int) -> Path:
    return claude_state_sessions_root(cwd) / f"pid-{pid}.json"


def _session_state_path(cwd: str, session_id: str) -> Path:
    return claude_state_sessions_root(cwd) / f"{session_id}.json"


def record_claude_session_start(*, cwd: str, account_id: str, pid: int, runtime_kind: str, slot_home: str) -> dict:
    store = ensure_claude_project_store(cwd)
    payload = {
        "session_id": None,
        "project_key": store["project_key"],
        "project_path": store["canonical_path"],
        "account_id": account_id or "",
        "started_at": _utc_now(),
        "last_active_at": None,
        "cwd": os.path.realpath(cwd),
        "pid": pid,
        "cli": "claude",
        "runtime_kind": runtime_kind,
        "slot_home": slot_home,
        "exit_code": None,
        "stale_cleanup": False,
    }
    _write_json(_slot_state_path(cwd, pid), payload)
    return payload


def finalize_claude_session(*, cwd: str, pid: int, exit_code: int | None, stale_cleanup: bool = False) -> dict | None:
    slot_state = _slot_state_path(cwd, pid)
    payload = _read_json(slot_state)
    if payload is None:
        return None

    session_file = claude_raw_entry_path("sessions", cwd) / f"{pid}.json"
    session_data = _read_json(session_file) or {}
    session_id = str(session_data.get("sessionId") or "").strip() or payload.get("session_id") or f"pid-{pid}"
    payload["session_id"] = session_id
    payload["cwd"] = session_data.get("cwd") or payload.get("cwd")
    payload["last_active_at"] = _utc_now()
    payload["exit_code"] = exit_code
    payload["stale_cleanup"] = bool(stale_cleanup)
    if session_data.get("startedAt"):
        payload["started_at_ms"] = session_data["startedAt"]

    target = _session_state_path(cwd, session_id)
    _write_json(target, payload)
    try:
        slot_state.unlink()
    except OSError:
        pass
    return payload


def list_indexed_sessions(cli_name: str = "claude") -> list[dict]:
    if cli_name != "claude":
        return []
    root = PRIMARY_CONFIG_DIR / "projects"
    if not root.exists():
        return []

    sessions: list[dict] = []
    for state_dir in root.glob("*/claude/state/sessions"):
        if not state_dir.is_dir():
            continue
        for path in state_dir.glob("*.json"):
            data = _read_json(path)
            if not data or data.get("cli") != "claude":
                continue
            data["_path"] = str(path)
            sessions.append(data)
    sessions.sort(key=lambda item: item.get("last_active_at") or item.get("started_at") or "", reverse=True)
    return sessions


def get_indexed_session(session_id: str, cli_name: str = "claude") -> dict | None:
    session_id = str(session_id or "").strip()
    if not session_id:
        return None
    pid_fallback = session_id[4:] if session_id.startswith("pid-") else session_id
    for item in list_indexed_sessions(cli_name=cli_name):
        if item.get("session_id") == session_id:
            return item
        if str(item.get("pid")) == pid_fallback:
            return item
    return None
