"""Read-only session catalog for MMS-managed CLI resume history.

The catalog intentionally stores no new state.  It scans existing Claude and
Codex resume files and normalizes them into one shape so UI/CLI surfaces can
search by CLI, project, title, or session id.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from mms_project_store import get_projects_dir
from mms_state_io import resolve_mms_config_dir


_CLAUDE_SESSION_ID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _real_user_home() -> Path:
    for key in ("MMS_REAL_HOME", "REAL_HOME", "ORIGINAL_HOME"):
        value = str(os.environ.get(key) or "").strip()
        if value:
            return Path(os.path.abspath(os.path.expanduser(value)))
    return Path.home()


def _dedupe_paths(paths: Iterable[Path | str]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for item in paths:
        raw = str(item or "").strip()
        if not raw:
            continue
        path = Path(os.path.abspath(os.path.expanduser(raw)))
        key = os.path.realpath(str(path))
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def claude_project_roots() -> list[Path]:
    home = _real_user_home()
    roots: list[Path] = []
    try:
        roots.append(get_projects_dir())
    except Exception:
        pass
    try:
        roots.append(Path(resolve_mms_config_dir()) / "projects")
    except Exception:
        pass
    roots.extend(
        [
            home / ".config" / "mms-next" / "projects",
            home / ".config" / "mms" / "projects",
        ]
    )
    return [path for path in _dedupe_paths(roots) if path.exists()]


def codex_roots() -> list[Path]:
    home = _real_user_home()
    roots: list[Path] = []
    for env_name in ("MMS_CODEX_RESUME_WRITEBACK_ROOT", "CODEX_HOME"):
        value = str(os.environ.get(env_name) or "").strip()
        if value:
            roots.append(Path(value))
    roots.extend(
        [
            home / ".config" / "mms" / "codex-gateway" / ".codex",
            home / ".codex",
        ]
    )
    roots.extend((home / ".config" / "mms" / "codex-gateway" / "s").glob("*/.codex"))
    roots.extend((home / ".config" / "mms" / "accounts").glob("*/.codex"))
    roots.extend((home / ".config" / "mms" / "accounts").glob("*/s/*/.codex"))
    return [path for path in _dedupe_paths(roots) if path.exists()]


def _read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _mtime_iso(path: Path) -> str:
    try:
        ts = path.stat().st_mtime
    except OSError:
        ts = 0
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def _iso_sort_value(value: object) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return 0.0


def _short_text(value: object, limit: int = 120) -> str:
    if isinstance(value, list):
        parts = [_short_text(item, limit=limit) for item in value]
        text = " ".join(part for part in parts if part)
    elif isinstance(value, dict):
        if "text" in value:
            text = str(value.get("text") or "")
        elif "content" in value:
            text = _short_text(value.get("content"), limit=limit)
        else:
            text = ""
    else:
        text = str(value or "")
    text = " ".join(text.split())
    return text[:limit]


def _title_candidate(value: object, limit: int = 120) -> str:
    text = _short_text(value, limit=limit)
    lowered = text.lower()
    if not text:
        return ""
    boilerplate_prefixes = (
        "# agents.md instructions",
        "<environment_context>",
        "<permissions instructions>",
        "you are codex",
        "you are claude",
        "another language model started",
    )
    if any(lowered.startswith(prefix) for prefix in boilerplate_prefixes):
        return ""
    return text


def _record_key(record: dict) -> tuple[str, str]:
    return str(record.get("cli") or ""), str(record.get("session_id") or "")


def _record_priority(record: dict) -> int:
    kind = str(record.get("source_kind") or "")
    return {
        "mms-index": 4,
        "codex-index": 3,
        "claude-jsonl": 2,
        "codex-jsonl": 2,
    }.get(kind, 1)


def _merge_records(records: Iterable[dict]) -> list[dict]:
    merged: dict[tuple[str, str], dict] = {}
    for raw in records:
        if not isinstance(raw, dict):
            continue
        key = _record_key(raw)
        if not key[0] or not key[1]:
            continue
        current = merged.get(key)
        next_record = dict(raw)
        next_record.setdefault("source_paths", [])
        source_path = str(next_record.get("source_path") or "").strip()
        if source_path and source_path not in next_record["source_paths"]:
            next_record["source_paths"].append(source_path)
        if current is None:
            merged[key] = next_record
            continue
        for path in next_record.get("source_paths") or []:
            if path and path not in current.setdefault("source_paths", []):
                current["source_paths"].append(path)
        for field in ("title", "cwd", "project_path", "project_name", "updated_at", "created_at"):
            if not current.get(field) and next_record.get(field):
                current[field] = next_record[field]
        replace = (
            _record_priority(next_record),
            _iso_sort_value(next_record.get("updated_at") or next_record.get("created_at")),
        ) > (
            _record_priority(current),
            _iso_sort_value(current.get("updated_at") or current.get("created_at")),
        )
        if replace:
            source_paths = current.get("source_paths") or []
            for field, value in current.items():
                if field not in next_record and value:
                    next_record[field] = value
            next_record["source_paths"] = source_paths
            merged[key] = next_record
    return list(merged.values())


def _project_name(path: object) -> str:
    text = str(path or "").rstrip(os.sep)
    return os.path.basename(text) if text else ""


def _claude_state_records(projects_root: Path) -> Iterable[dict]:
    for session_path in projects_root.glob("*/claude/state/sessions/*.json"):
        payload = _read_json(session_path)
        session_id = str(payload.get("session_id") or "").strip()
        if not session_id or session_id.startswith("pid-"):
            continue
        metadata = _read_json(session_path.parents[1] / "metadata.json")
        project_path = str(payload.get("project_path") or metadata.get("canonical_path") or payload.get("cwd") or "")
        yield {
            "cli": "claude",
            "session_id": session_id,
            "project_path": project_path,
            "project_name": _project_name(project_path),
            "cwd": str(payload.get("cwd") or project_path),
            "account_id": str(payload.get("account_id") or metadata.get("account_id") or ""),
            "runtime_kind": str(payload.get("runtime_kind") or ""),
            "model": str(payload.get("resume_model") or ""),
            "created_at": str(payload.get("started_at") or ""),
            "updated_at": str(payload.get("last_active_at") or payload.get("started_at") or ""),
            "status": "active" if payload.get("exit_code") is None else f"exit:{payload.get('exit_code')}",
            "source_kind": "mms-index",
            "source_path": str(session_path),
        }


def _claude_jsonl_summary(path: Path) -> dict:
    session_id = path.stem if _CLAUDE_SESSION_ID_RE.match(path.stem) else ""
    cwd = ""
    created_at = ""
    updated_at = _mtime_iso(path)
    title = ""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for index, line in enumerate(handle):
                if index >= 240:
                    break
                try:
                    payload = json.loads(line)
                except Exception:
                    continue
                if not isinstance(payload, dict):
                    continue
                session_id = session_id or str(payload.get("sessionId") or payload.get("session_id") or "").strip()
                cwd = cwd or str(payload.get("cwd") or "").strip()
                timestamp = str(payload.get("timestamp") or "").strip()
                if timestamp:
                    created_at = created_at or timestamp
                    updated_at = timestamp
                if not title and payload.get("type") == "user":
                    message = payload.get("message") if isinstance(payload.get("message"), dict) else payload
                    title = _title_candidate(message.get("content"), limit=120)
    except OSError:
        pass
    return {
        "session_id": session_id,
        "cwd": cwd,
        "created_at": created_at or updated_at,
        "updated_at": updated_at,
        "title": title,
    }


def _claude_raw_records(projects_root: Path) -> Iterable[dict]:
    for metadata_path in projects_root.glob("*/claude/state/metadata.json"):
        metadata = _read_json(metadata_path)
        project_path = str(metadata.get("canonical_path") or "")
        account_id = str(metadata.get("account_id") or "")
        raw_projects = metadata_path.parents[1] / "raw" / "projects"
        if not raw_projects.is_dir():
            continue
        for jsonl_path in raw_projects.rglob("*.jsonl"):
            if "subagents" in jsonl_path.parts or jsonl_path.stem.startswith("agent-"):
                continue
            summary = _claude_jsonl_summary(jsonl_path)
            session_id = str(summary.get("session_id") or "").strip()
            if not session_id:
                continue
            cwd = str(summary.get("cwd") or project_path)
            yield {
                "cli": "claude",
                "session_id": session_id,
                "project_path": project_path or cwd,
                "project_name": _project_name(project_path or cwd),
                "cwd": cwd,
                "account_id": account_id,
                "runtime_kind": "api_key" if account_id else "",
                "model": "",
                "created_at": str(summary.get("created_at") or ""),
                "updated_at": str(summary.get("updated_at") or ""),
                "title": str(summary.get("title") or ""),
                "status": "raw",
                "source_kind": "claude-jsonl",
                "source_path": str(jsonl_path),
            }


def _codex_index_records(root: Path) -> Iterable[dict]:
    index_path = root / "session_index.jsonl"
    if not index_path.is_file():
        return
    try:
        handle = index_path.open("r", encoding="utf-8", errors="replace")
    except OSError:
        return
    with handle:
        for line in handle:
            try:
                payload = json.loads(line)
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            session_id = str(payload.get("id") or "").strip()
            if not session_id:
                continue
            yield {
                "cli": "codex",
                "session_id": session_id,
                "project_path": str(payload.get("cwd") or ""),
                "project_name": _project_name(payload.get("cwd")),
                "cwd": str(payload.get("cwd") or ""),
                "model": str(payload.get("model") or ""),
                "created_at": str(payload.get("created_at") or payload.get("timestamp") or ""),
                "updated_at": str(payload.get("updated_at") or payload.get("created_at") or ""),
                "title": _short_text(payload.get("thread_name") or payload.get("title"), limit=120),
                "status": "indexed",
                "source_kind": "codex-index",
                "source_path": str(index_path),
                "_root": str(root),
            }


def _codex_jsonl_summary(path: Path) -> dict:
    session_id = ""
    cwd = ""
    title = ""
    created_at = ""
    updated_at = _mtime_iso(path)
    model = ""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for index, line in enumerate(handle):
                if index >= 1000:
                    break
                try:
                    payload = json.loads(line)
                except Exception:
                    continue
                if not isinstance(payload, dict):
                    continue
                timestamp = str(payload.get("timestamp") or "").strip()
                if timestamp:
                    created_at = created_at or timestamp
                    updated_at = timestamp
                kind = payload.get("type")
                body = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
                if kind == "session_meta":
                    session_id = session_id or str(body.get("id") or "").strip()
                    cwd = cwd or str(body.get("cwd") or "").strip()
                    model = model or str(body.get("model") or body.get("model_provider") or "").strip()
                    created_at = created_at or str(body.get("timestamp") or "")
                if not title and kind == "response_item":
                    role = str(body.get("role") or "").strip()
                    if role == "user":
                        title = _title_candidate(body.get("content"), limit=120)
    except OSError:
        pass
    if not session_id:
        match = re.search(r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})", path.name)
        session_id = match.group(1) if match else ""
    return {
        "session_id": session_id,
        "cwd": cwd,
        "title": title,
        "created_at": created_at or updated_at,
        "updated_at": updated_at,
        "model": model,
    }


def _codex_jsonl_records(root: Path) -> Iterable[dict]:
    for sessions_dir_name in ("sessions", "archived_sessions"):
        sessions_dir = root / sessions_dir_name
        if not sessions_dir.is_dir():
            continue
        for jsonl_path in sessions_dir.rglob("*.jsonl"):
            summary = _codex_jsonl_summary(jsonl_path)
            session_id = str(summary.get("session_id") or "").strip()
            if not session_id:
                continue
            cwd = str(summary.get("cwd") or "")
            yield {
                "cli": "codex",
                "session_id": session_id,
                "project_path": cwd,
                "project_name": _project_name(cwd),
                "cwd": cwd,
                "model": str(summary.get("model") or ""),
                "created_at": str(summary.get("created_at") or ""),
                "updated_at": str(summary.get("updated_at") or ""),
                "title": str(summary.get("title") or ""),
                "status": "raw",
                "source_kind": "codex-jsonl",
                "source_path": str(jsonl_path),
                "_root": str(root),
            }


def list_session_records(cli: str = "all", query: str = "", limit: int | None = None) -> list[dict]:
    cli = str(cli or "all").strip().lower()
    query = " ".join(str(query or "").lower().split())
    records: list[dict] = []
    if cli in {"all", "claude"}:
        for root in claude_project_roots():
            records.extend(_claude_state_records(root))
            records.extend(_claude_raw_records(root))
    if cli in {"all", "codex"}:
        for root in codex_roots():
            records.extend(_codex_index_records(root))
            records.extend(_codex_jsonl_records(root))
    merged = _merge_records(records)
    if query:
        tokens = query.split()
        merged = [
            record
            for record in merged
            if all(
                token
                in " ".join(
                    str(record.get(field) or "").lower()
                    for field in ("cli", "session_id", "project_path", "project_name", "cwd", "title", "model")
                )
                for token in tokens
            )
        ]
    merged.sort(
        key=lambda item: (
            _iso_sort_value(item.get("updated_at") or item.get("created_at")),
            str(item.get("session_id") or ""),
        ),
        reverse=True,
    )
    if limit is not None and int(limit) > 0:
        return merged[: int(limit)]
    return merged


def resolve_catalog_ref(session_ref: str, cli: str = "all") -> tuple[str | None, dict | None, str | None]:
    ref = str(session_ref or "").strip()
    if not ref:
        return None, None, "session id 不能为空"
    records = list_session_records(cli=cli, limit=None)
    exact = [item for item in records if str(item.get("session_id") or "") == ref]
    if exact:
        return str(exact[0].get("session_id") or ""), exact[0], None
    matches = [item for item in records if str(item.get("session_id") or "").startswith(ref)]
    if len(matches) == 1:
        return str(matches[0].get("session_id") or ""), matches[0], None
    if len(matches) > 1:
        return None, None, f"session 前缀不唯一: {ref}"
    return None, None, f"找不到 session: {ref}"
