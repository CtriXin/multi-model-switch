"""Metadata index for MMC-managed Claude sessions."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from mms_state_io import atomic_write_json, locked_state_file
from mmc_project_store import (
    claude_raw_entry_path,
    claude_state_sessions_root,
    ensure_claude_project_store,
    get_projects_dir,
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
    with locked_state_file(path):
        atomic_write_json(str(path), payload, mode=0o600)


def _slot_state_path(cwd: str, pid: int) -> Path:
    return claude_state_sessions_root(cwd) / f"pid-{pid}.json"


def _session_state_path(cwd: str, session_id: str) -> Path:
    return claude_state_sessions_root(cwd) / f"{session_id}.json"


def _payload_started_at_ms(payload: dict) -> int | None:
    raw = payload.get("started_at_ms")
    if isinstance(raw, (int, float)):
        return int(raw)
    started_at = str(payload.get("started_at") or "").strip()
    if not started_at:
        return None
    try:
        return int(datetime.fromisoformat(started_at).timestamp() * 1000)
    except ValueError:
        return None


def _load_matching_raw_session(cwd: str, payload: dict) -> dict | None:
    sessions_root = claude_raw_entry_path("sessions", cwd)
    if not sessions_root.is_dir():
        return None

    expected_cwd = os.path.realpath(str(payload.get("cwd") or cwd))
    expected_started_at_ms = _payload_started_at_ms(payload)
    expected_child_pid = payload.get("child_pid")
    expected_nonce = str(payload.get("launch_nonce") or "").strip()
    if not (isinstance(expected_child_pid, int) and expected_child_pid > 0) and not expected_nonce:
        return None
    candidates: list[tuple[int, int, dict]] = []

    for path in sessions_root.glob("*.json"):
        data = _read_json(path)
        if not data:
            continue
        session_id = str(data.get("sessionId") or "").strip()
        started_at_ms = data.get("startedAt")
        if not session_id or not isinstance(started_at_ms, (int, float)):
            continue
        session_cwd = os.path.realpath(str(data.get("cwd") or cwd))
        if expected_cwd and session_cwd and expected_cwd != session_cwd:
            continue
        raw_pid = data.get("pid")
        if isinstance(expected_child_pid, int) and expected_child_pid > 0:
            if raw_pid != expected_child_pid:
                continue
            score = 0
            candidates.append((score, -int(started_at_ms), data))
            continue
        raw_nonce = str(data.get("launchNonce") or data.get("launch_nonce") or "").strip()
        if expected_nonce and raw_nonce:
            if raw_nonce != expected_nonce:
                continue
            score = 0
            candidates.append((score, -int(started_at_ms), data))
            continue
        continue

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[0], item[1]))
    best_score, _neg_started_at, best = candidates[0]
    if isinstance(expected_child_pid, int) and expected_child_pid > 0:
        return best
    if expected_nonce:
        return best
    return None


def _reconcile_session_state(path: Path, payload: dict) -> tuple[dict, Path]:
    session_id = str(payload.get("session_id") or "").strip()
    if session_id and not session_id.startswith("pid-"):
        return payload, path

    cwd = str(payload.get("cwd") or payload.get("project_path") or "").strip()
    if not cwd:
        return payload, path

    session_data = _load_matching_raw_session(cwd, payload)
    if not session_data:
        return payload, path

    resolved_session_id = str(session_data.get("sessionId") or "").strip()
    if not resolved_session_id:
        return payload, path

    updated = dict(payload)
    updated["session_id"] = resolved_session_id
    updated["cwd"] = session_data.get("cwd") or updated.get("cwd")
    updated["started_at_ms"] = session_data.get("startedAt") or updated.get("started_at_ms")
    updated["session_pid"] = session_data.get("pid")

    target = _session_state_path(cwd, resolved_session_id)
    _write_json(target, updated)
    if path != target:
        try:
            path.unlink()
        except OSError:
            pass
    return updated, target


def record_claude_session_start(*, cwd: str, pid: int, slot_home: str) -> dict:
    store = ensure_claude_project_store(cwd)
    payload = {
        "session_id": None,
        "project_key": store["project_key"],
        "project_path": store["canonical_path"],
        "started_at": _utc_now(),
        "last_active_at": None,
        "cwd": os.path.realpath(cwd),
        "pid": pid,
        "child_pid": None,
        "launch_nonce": None,
        "cli": "claude",
        "runtime_kind": "oauth",
        "slot_home": slot_home,
        "exit_code": None,
        "stale_cleanup": False,
    }
    _write_json(_slot_state_path(cwd, pid), payload)
    return payload


def bind_claude_session_process(*, cwd: str, pid: int, child_pid: int | None = None, launch_nonce: str = "") -> dict | None:
    slot_state = _slot_state_path(cwd, pid)
    payload = _read_json(slot_state)
    if payload is None:
        return None
    if isinstance(child_pid, int) and child_pid > 0:
        payload["child_pid"] = child_pid
    if str(launch_nonce or "").strip():
        payload["launch_nonce"] = str(launch_nonce).strip()
    _write_json(slot_state, payload)
    return payload


def finalize_claude_session(*, cwd: str, pid: int, exit_code: int | None, stale_cleanup: bool = False) -> dict | None:
    slot_state = _slot_state_path(cwd, pid)
    payload = _read_json(slot_state)
    if payload is None:
        return None

    payload["last_active_at"] = _utc_now()
    payload["exit_code"] = exit_code
    payload["stale_cleanup"] = bool(stale_cleanup)
    payload, target = _reconcile_session_state(slot_state, payload)
    if target == slot_state:
        session_id = str(payload.get("session_id") or "").strip() or f"pid-{pid}"
        target = _session_state_path(cwd, session_id)
        _write_json(target, payload)
    try:
        slot_state.unlink()
    except OSError:
        pass
    return payload


def list_indexed_sessions() -> list[dict]:
    root = get_projects_dir()
    if not root.exists():
        return []

    sessions: list[dict] = []
    seen_keys: set[str] = set()
    for state_dir in root.glob("*/claude/state/sessions"):
        if not state_dir.is_dir():
            continue
        for path in state_dir.glob("*.json"):
            data = _read_json(path)
            if not data or data.get("cli") != "claude":
                continue
            data, resolved_path = _reconcile_session_state(path, data)
            dedupe_key = str(data.get("session_id") or resolved_path)
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            data["_path"] = str(resolved_path)
            sessions.append(data)
    sessions.sort(key=lambda item: item.get("last_active_at") or item.get("started_at") or "", reverse=True)
    return sessions


def resolve_session_ref(session_ref: str) -> tuple[str | None, str | None]:
    ref = str(session_ref or "").strip()
    if not ref:
        return None, "session_ref 不能为空"
    sessions = list_indexed_sessions()
    if not sessions:
        return None, "暂无可恢复 session"

    if ref.isdigit():
        index = int(ref)
        if 1 <= index <= len(sessions):
            return str(sessions[index - 1].get("session_id") or "").strip() or None, None
        return None, f"找不到第 {index} 条 session"

    exact = [item for item in sessions if str(item.get("session_id") or "").strip() == ref]
    if exact:
        return ref, None

    matches = [
        str(item.get("session_id") or "").strip()
        for item in sessions
        if str(item.get("session_id") or "").strip().startswith(ref)
    ]
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        return None, f"session 前缀不唯一: {ref}"
    return None, f"找不到 session: {ref}"
