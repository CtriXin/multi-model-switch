"""
mms_runtime.events — Unified runtime event schema and file-based event emitter.

Provides a minimal event bus for tracking model execution lifecycle
(queued, started, streaming, fallback, retrying, done, failed).
Events are persisted under the selected MMS config root as both an atomically-written
latest.json and daily JSONL append logs, with automatic 7-day cleanup.
"""

import json
import os
import threading
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from tempfile import NamedTemporaryFile

from mms_runtime.state_io import resolve_mms_config_dir


class EventType(str, Enum):
    QUEUED = "queued"
    STARTED = "started"
    STREAMING = "streaming"
    FALLBACK = "fallback"
    RETRYING = "retrying"
    DONE = "done"
    FAILED = "failed"


DEFAULT_EVENT_DIR = Path(resolve_mms_config_dir()) / "events"
EVENT_DIR = DEFAULT_EVENT_DIR
LATEST_PATH = EVENT_DIR / "latest.json"
_RETENTION_DAYS = 7
_LOCK = threading.Lock()


def _event_dir() -> Path:
    configured = Path(EVENT_DIR)
    if configured != DEFAULT_EVENT_DIR:
        return configured
    return Path(resolve_mms_config_dir()) / "events"


def _latest_path() -> Path:
    configured = Path(LATEST_PATH)
    default_path = DEFAULT_EVENT_DIR / "latest.json"
    if configured != default_path:
        return configured
    return _event_dir() / "latest.json"


def _ensure_dir():
    _event_dir().mkdir(parents=True, exist_ok=True)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _daily_path() -> Path:
    return _event_dir() / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.jsonl"


def _atomic_write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = NamedTemporaryFile(
            dir=path.parent, mode="w", suffix=".tmp",
            delete=False, encoding="utf-8",
        )
        json.dump(data, fd, ensure_ascii=False)
        fd.flush()
        os.fsync(fd.fileno())
        tmp_name = fd.name
    finally:
        fd.close()
    os.replace(tmp_name, path)


def _cleanup_old_logs():
    _ensure_dir()
    cutoff = datetime.now(timezone.utc) - timedelta(days=_RETENTION_DAYS)
    for f in _event_dir().glob("*.jsonl"):
        stem = f.stem
        try:
            file_date = datetime.strptime(stem, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if file_date < cutoff:
                f.unlink()
        except (ValueError, OSError):
            pass


def _make_event(type: str, model: str, *, run_id=None, task_id=None, note=None) -> dict:
    return {
        "type": type,
        "model": model,
        "run_id": run_id,
        "task_id": task_id,
        "at": _iso_now(),
        "note": note,
    }


def emit_event(
    type: str,
    model: str,
    *,
    run_id: str | None = None,
    task_id: str | None = None,
    note: str | None = None,
) -> dict:
    if type not in [e.value for e in EventType]:
        raise ValueError(
            f"Unknown event type: {type!r}. "
            f"Valid: {[e.value for e in EventType]}"
        )
    event = _make_event(type, model, run_id=run_id, task_id=task_id, note=note)
    with _LOCK:
        _ensure_dir()
        _atomic_write_json(_latest_path(), event)
        daily = _daily_path()
        with daily.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        _cleanup_old_logs()
    # GBrain memory hook (non-blocking)
    try:
        import gbrain_memory_hook
        gbrain_memory_hook.ingest_mms_event(event)
    except Exception:
        pass
    return event


def get_latest_event() -> dict | None:
    latest_path = _latest_path()
    if not latest_path.is_file():
        return None
    try:
        text = latest_path.read_text(encoding="utf-8").strip()
        if not text:
            return None
        return json.loads(text)
    except (json.JSONDecodeError, OSError):
        return None


def get_recent_events(limit: int = 20) -> list[dict]:
    daily = _daily_path()
    if not daily.is_file():
        return []
    try:
        lines = daily.read_text(encoding="utf-8").strip().split("\n")
    except OSError:
        return []
    events = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
        if len(events) >= limit:
            break
    return list(reversed(events))
