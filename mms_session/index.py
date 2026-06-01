"""Metadata index for MMS-managed project-scoped CLI sessions."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from mms_claude.project_store import (
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
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _slot_state_path(cwd: str, pid: int, account_id: str = "") -> Path:
    return claude_state_sessions_root(cwd, account_id=account_id) / f"pid-{pid}.json"


def _session_state_path(cwd: str, session_id: str, account_id: str = "") -> Path:
    return claude_state_sessions_root(cwd, account_id=account_id) / f"{session_id}.json"


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


def _normalize_resume_model(value: object) -> str:
    return str(value or "").strip()


def _load_matching_raw_session(cwd: str, payload: dict) -> dict | None:
    account_id = str(payload.get("account_id") or "").strip()
    sessions_root = claude_raw_entry_path("sessions", cwd, account_id=account_id)
    if not sessions_root.is_dir():
        return None

    expected_cwd = os.path.realpath(str(payload.get("cwd") or cwd))
    expected_started_at_ms = _payload_started_at_ms(payload)
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
        score = abs(int(started_at_ms) - expected_started_at_ms) if expected_started_at_ms is not None else 0
        candidates.append((score, -int(started_at_ms), data))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[0], item[1]))
    best_score, _neg_started_at, best = candidates[0]
    if expected_started_at_ms is not None and best_score > 10 * 60 * 1000:
        return None
    return best


_CLAUDE_SESSION_ID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _session_id_from_project_jsonl(path: Path) -> str:
    stem = str(path.stem or "").strip()
    if _CLAUDE_SESSION_ID_RE.fullmatch(stem):
        return stem
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for _ in range(5):
                line = handle.readline()
                if not line:
                    break
                try:
                    payload = json.loads(line)
                except Exception:
                    continue
                session_id = str(payload.get("sessionId") or payload.get("session_id") or "").strip()
                if session_id and not session_id.startswith("pid-"):
                    return session_id
    except OSError:
        return ""
    return ""


def _load_latest_project_resume_session(cwd: str, payload: dict) -> dict | None:
    account_id = str(payload.get("account_id") or "").strip()
    projects_root = claude_raw_entry_path("projects", cwd, account_id=account_id)
    if not projects_root.is_dir():
        return None

    expected_started_at_ms = _payload_started_at_ms(payload)
    candidates: list[tuple[int, str, Path]] = []
    for path in projects_root.rglob("*.jsonl"):
        if not path.is_file():
            continue
        session_id = _session_id_from_project_jsonl(path)
        if not session_id:
            continue
        try:
            mtime_ms = int(path.stat().st_mtime * 1000)
        except OSError:
            continue
        if expected_started_at_ms is not None and mtime_ms < expected_started_at_ms - 10 * 60 * 1000:
            continue
        candidates.append((mtime_ms, session_id, path))

    if not candidates:
        return None
    mtime_ms, session_id, source_path = sorted(candidates, reverse=True)[0]
    return {
        "sessionId": session_id,
        "cwd": str(payload.get("cwd") or cwd),
        "startedAt": mtime_ms,
        "pid": payload.get("pid"),
        "_source": str(source_path),
    }


def _reconcile_session_state(path: Path, payload: dict) -> tuple[dict, Path]:
    session_id = str(payload.get("session_id") or "").strip()
    if session_id and session_id != "None" and not session_id.startswith("pid-"):
        return payload, path

    cwd = str(payload.get("cwd") or payload.get("project_path") or "").strip()
    account_id = str(payload.get("account_id") or "").strip()
    if not cwd:
        return payload, path

    session_data = _load_matching_raw_session(cwd, payload)
    if not session_data:
        session_data = _load_latest_project_resume_session(cwd, payload)
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

    target = _session_state_path(cwd, resolved_session_id, account_id=account_id)
    _write_json(target, updated)
    if path != target:
        try:
            path.unlink()
        except OSError:
            pass
    return updated, target


def _synthesize_finalized_session_from_project_jsonl(
    *,
    cwd: str,
    pid: int,
    account_id: str = "",
    exit_code: int | None,
    stale_cleanup: bool = False,
) -> dict | None:
    cwd = os.path.realpath(str(cwd or ""))
    if not cwd:
        return None
    store = ensure_claude_project_store(cwd, account_id=account_id)
    seed_payload = {
        "cwd": cwd,
        "project_path": cwd,
        "account_id": account_id or "",
        "pid": pid,
    }
    session_data = _load_latest_project_resume_session(cwd, seed_payload)
    if not session_data:
        return None
    session_id = str(session_data.get("sessionId") or "").strip()
    if not session_id:
        return None
    started_at_ms = session_data.get("startedAt")
    started_at = _utc_now()
    if isinstance(started_at_ms, (int, float)):
        started_at = datetime.fromtimestamp(float(started_at_ms) / 1000, timezone.utc).isoformat()
    payload = {
        "session_id": session_id,
        "project_key": store["project_key"],
        "project_path": store["canonical_path"],
        "account_id": account_id or "",
        "started_at": started_at,
        "started_at_ms": started_at_ms if isinstance(started_at_ms, (int, float)) else None,
        "last_active_at": _utc_now(),
        "cwd": cwd,
        "pid": pid,
        "session_pid": session_data.get("pid"),
        "cli": "claude",
        "runtime_kind": "",
        "resume_model": "",
        "slot_home": "",
        "exit_code": exit_code,
        "stale_cleanup": bool(stale_cleanup),
        "recovered_from": str(session_data.get("_source") or "project-jsonl"),
    }
    target = _session_state_path(cwd, session_id, account_id=account_id)
    _write_json(target, payload)
    return payload


def record_claude_session_start(
    *,
    cwd: str,
    account_id: str,
    pid: int,
    runtime_kind: str,
    slot_home: str,
    resume_model: str = "",
    runtime_account_id: str = "",
) -> dict:
    store = ensure_claude_project_store(cwd, account_id=account_id)
    payload = {
        "session_id": None,
        "project_key": store["project_key"],
        "project_path": store["canonical_path"],
        "account_id": account_id or "",
        "runtime_account_id": runtime_account_id or "",
        "started_at": _utc_now(),
        "last_active_at": None,
        "cwd": os.path.realpath(cwd),
        "pid": pid,
        "cli": "claude",
        "runtime_kind": runtime_kind,
        "resume_model": _normalize_resume_model(resume_model),
        "slot_home": slot_home,
        "exit_code": None,
        "stale_cleanup": False,
    }
    _write_json(_slot_state_path(cwd, pid, account_id=account_id), payload)
    return payload


def finalize_claude_session(*, cwd: str, pid: int, account_id: str = "", exit_code: int | None, stale_cleanup: bool = False) -> dict | None:
    slot_state = _slot_state_path(cwd, pid, account_id=account_id)
    payload = _read_json(slot_state)
    if payload is None:
        return _synthesize_finalized_session_from_project_jsonl(
            cwd=cwd,
            pid=pid,
            account_id=account_id,
            exit_code=exit_code,
            stale_cleanup=stale_cleanup,
        )

    payload["last_active_at"] = _utc_now()
    payload["exit_code"] = exit_code
    payload["stale_cleanup"] = bool(stale_cleanup)
    payload, target = _reconcile_session_state(slot_state, payload)
    if target == slot_state:
        session_id = str(payload.get("session_id") or "").strip() or f"pid-{pid}"
        target = _session_state_path(cwd, session_id, account_id=account_id)
        _write_json(target, payload)
    try:
        slot_state.unlink()
    except OSError:
        pass
    return payload


def list_indexed_sessions(cli_name: str = "claude") -> list[dict]:
    if cli_name != "claude":
        return []
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
