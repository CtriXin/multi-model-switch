"""Small, durable per-Bot memory store.

Memory is deliberately independent from the Pi transcript.  A Bot may change
model, resume a different session, or restart the service without losing its
bounded notes.  The store does not call a model: task summaries supplied by
the caller are retained as ``kind=task`` notes and are clearly labelled.
"""
from __future__ import annotations

import fcntl
import json
import re
import shutil
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .runtime import private_json

SCHEMA = 1
MAX_FACTS = 100
MAX_TASKS = 200
MAX_CONTENT_CHARS = 2000
DEFAULT_SETTINGS = {
    "memoryEnabled": True,
    "memoryBudgetTokens": 2000,
    "autoCompact": True,
    "compactAtPercent": 70,
}
DEFAULT_CONTEXT = {
    "contextWindow": None,
    "usedTokens": None,
    "usedPercent": None,
    "source": "unknown",
    "lastCompactedAt": None,
    "compactionError": None,
}
_BOT_ID = re.compile(r"^bot_[A-Za-z0-9_-]{1,100}$")
_WORD = re.compile(r"[a-z0-9_]+|[\u4e00-\u9fff]", re.I)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _tokens(value: str) -> list[str]:
    """Return stable lexical tokens, including Chinese unigrams and latin words."""
    return [part.lower() for part in _WORD.findall(value or "")]


def _sort_key(note: dict) -> tuple[str, str]:
    return (str(note.get("updatedAt") or note.get("createdAt") or ""), str(note.get("id") or ""))


class BotMemoryError(ValueError):
    """Invalid or unreadable memory data (the HTTP layer can map this to 400/409)."""


class BotMemoryStore:
    """Per-Bot memory persisted below ``state_root/bots/memory``.

    The public methods return a complete view suitable for the Web API.  Writes
    are atomic and protected by both a process lock and a per-Bot flock, so two
    Pilot processes cannot interleave JSON updates.
    """

    def __init__(self, state_root: Path):
        self.root = Path(state_root).resolve() / "bots" / "memory"
        self._lock = threading.RLock()

    def _validate_bot(self, bot_id: str) -> str:
        if not isinstance(bot_id, str) or not _BOT_ID.fullmatch(bot_id):
            raise BotMemoryError("invalid bot id")
        return bot_id

    def _paths(self, bot_id: str) -> tuple[Path, Path]:
        bot_id = self._validate_bot(bot_id)
        directory = self.root / bot_id
        return directory / "memory.json", directory / "owner.lock"

    @staticmethod
    def _empty() -> dict:
        return {
            "schema": SCHEMA,
            "facts": [],
            "tasks": [],
            "settings": dict(DEFAULT_SETTINGS),
            "context": dict(DEFAULT_CONTEXT),
        }

    def _read(self, path: Path) -> dict:
        if not path.exists():
            return self._empty()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise BotMemoryError("memory record cannot be read") from exc
        if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
            raise BotMemoryError("unsupported memory record")
        data = self._empty()
        for key in ("facts", "tasks"):
            values = payload.get(key, [])
            if not isinstance(values, list):
                raise BotMemoryError("invalid memory notes")
            data[key] = [self._clean_note(v) for v in values if isinstance(v, dict)]
        data["settings"].update(self._clean_settings(payload.get("settings", {})))
        context = payload.get("context", {})
        if isinstance(context, dict):
            for key in DEFAULT_CONTEXT:
                if key in context:
                    data["context"][key] = context[key]
        return data

    @staticmethod
    def _clean_note(note: dict) -> dict:
        content = note.get("content", "")
        if not isinstance(content, str):
            content = str(content)
        content = content.strip()[:MAX_CONTENT_CHARS]
        kind = note.get("kind", "fact") if note.get("kind") in {"fact", "task"} else "fact"
        source = note.get("source", "user") if note.get("source") in {"user", "bot", "task"} else "user"
        created = str(note.get("createdAt") or _now())
        updated = str(note.get("updatedAt") or created)
        item = {
            "id": str(note.get("id") or "mem_" + uuid4().hex[:16]),
            "content": content,
            "kind": kind,
            "source": source,
            "createdAt": created,
            "updatedAt": updated,
        }
        if note.get("taskId") is not None:
            item["taskId"] = str(note["taskId"])
        return item

    @staticmethod
    def _clean_settings(settings: dict) -> dict:
        if not isinstance(settings, dict):
            return {}
        result = {}
        for key in DEFAULT_SETTINGS:
            if key in settings:
                result[key] = settings[key]
        return result

    @contextmanager
    def _file_guard(self, bot_id: str, *, write: bool):
        path, lock_path = self._paths(bot_id)
        lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        handle = lock_path.open("a+")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX if write else fcntl.LOCK_SH)
            yield path
        finally:
            try:
                fcntl.flock(handle, fcntl.LOCK_UN)
            finally:
                handle.close()

    @staticmethod
    def _view(data: dict, query: str = "") -> dict:
        all_notes = list(data["facts"]) + list(data["tasks"])
        query_tokens = _tokens(query)
        if query_tokens:
            scored = []
            qset = set(query_tokens)
            for note in all_notes:
                ntokens = _tokens(note["content"])
                counts = {token: ntokens.count(token) for token in qset}
                score = sum(counts.values())
                if score:
                    # Exact phrase and full-query matches get a deterministic boost.
                    if query.strip().lower() in note["content"].lower():
                        score += 5
                    if qset.issubset(set(ntokens)):
                        score += 2
                    scored.append((score, note))
            # Stable tie-breaking: relevance, newest update, then id.
            scored.sort(key=lambda x: x[1].get("id", ""))
            scored.sort(key=lambda x: x[1].get("updatedAt", ""), reverse=True)
            scored.sort(key=lambda x: x[0], reverse=True)
            all_notes = [note for _, note in scored]
        else:
            all_notes.sort(key=_sort_key, reverse=True)
        # Return copies so callers cannot mutate in-memory state.
        return {
            "notes": [dict(note) for note in all_notes],
            "limits": {"maxFacts": MAX_FACTS, "maxTasks": MAX_TASKS, "maxContentChars": MAX_CONTENT_CHARS},
            "settings": dict(data["settings"]),
            "context": dict(data["context"]),
        }

    def get(self, bot_id: str, query: str = "") -> dict:
        with self._lock, self._file_guard(bot_id, write=False) as path:
            return self._view(self._read(path), query if isinstance(query, str) else "")

    list = get

    def search(self, bot_id: str, query: str) -> dict:
        return self.get(bot_id, query)

    def _write(self, bot_id: str, data: dict) -> dict:
        path, _ = self._paths(bot_id)
        data["facts"] = sorted(data["facts"], key=_sort_key, reverse=True)[:MAX_FACTS]
        data["tasks"] = sorted(data["tasks"], key=_sort_key, reverse=True)[:MAX_TASKS]
        private_json(path, data)
        return data

    def remember(self, bot_id: str, content: str, *, kind: str = "fact", source: str = "user", task_id: str | None = None, note_id: str | None = None) -> dict:
        if not isinstance(content, str) or not content.strip():
            raise BotMemoryError("content is required")
        if kind not in {"fact", "task"} or source not in {"user", "bot", "task"}:
            raise BotMemoryError("invalid note kind or source")
        if kind == "task" and source != "task":
            source = "task"
        with self._lock, self._file_guard(bot_id, write=True) as path:
            data = self._read(path)
            now = _now()
            existing = next((n for n in data["facts"] + data["tasks"] if note_id and n["id"] == note_id), None)
            if existing:
                existing.update(content=content.strip()[:MAX_CONTENT_CHARS], updatedAt=now)
                if task_id is not None:
                    existing["taskId"] = str(task_id)
            else:
                item = {"id": note_id or "mem_" + uuid4().hex[:16], "content": content.strip()[:MAX_CONTENT_CHARS], "kind": kind, "source": source, "createdAt": now, "updatedAt": now}
                if task_id is not None:
                    item["taskId"] = str(task_id)
                data["tasks" if kind == "task" else "facts"].append(item)
            return self._view(self._write(bot_id, data))

    def update(self, bot_id: str, note_id: str, content: str, **kwargs) -> dict:
        """Update an existing note while preserving its kind/source."""
        if not isinstance(note_id, str) or not note_id or not isinstance(content, str) or not content.strip():
            raise BotMemoryError("note id and content are required")
        with self._lock, self._file_guard(bot_id, write=True) as path:
            data = self._read(path)
            existing = next((n for n in data["facts"] + data["tasks"] if n.get("id") == note_id), None)
            if existing is None:
                raise BotMemoryError("note not found")
            existing["content"] = content.strip()[:MAX_CONTENT_CHARS]
            existing["updatedAt"] = _now()
            if kwargs.get("task_id") is not None:
                existing["taskId"] = str(kwargs["task_id"])
            return self._view(self._write(bot_id, data))

    def forget(self, bot_id: str, note_id: str) -> dict:
        if not isinstance(note_id, str) or not note_id:
            raise BotMemoryError("note id is required")
        with self._lock, self._file_guard(bot_id, write=True) as path:
            data = self._read(path)
            before = len(data["facts"]) + len(data["tasks"])
            data["facts"] = [n for n in data["facts"] if n["id"] != note_id]
            data["tasks"] = [n for n in data["tasks"] if n["id"] != note_id]
            if before == len(data["facts"]) + len(data["tasks"]):
                raise BotMemoryError("note not found")
            return self._view(self._write(bot_id, data))

    def update_settings(self, bot_id: str, **changes) -> dict:
        allowed = set(DEFAULT_SETTINGS)
        if set(changes) - allowed:
            raise BotMemoryError("unknown memory setting")
        with self._lock, self._file_guard(bot_id, write=True) as path:
            data = self._read(path)
            settings = data["settings"]
            for key, value in changes.items():
                if key in {"memoryEnabled", "autoCompact"}:
                    if type(value) is not bool:
                        raise BotMemoryError(f"{key} must be boolean")
                elif key == "memoryBudgetTokens":
                    if type(value) is not int or not 500 <= value <= 8000:
                        raise BotMemoryError("memoryBudgetTokens must be 500..8000")
                elif key == "compactAtPercent":
                    if type(value) is not int or not 50 <= value <= 90:
                        raise BotMemoryError("compactAtPercent must be 50..90")
                settings[key] = value
            return self._view(self._write(bot_id, data))

    def update_context(self, bot_id: str, **changes) -> dict:
        allowed = set(DEFAULT_CONTEXT)
        if set(changes) - allowed:
            raise BotMemoryError("unknown context field")
        with self._lock, self._file_guard(bot_id, write=True) as path:
            data = self._read(path)
            data["context"].update(changes)
            return self._view(self._write(bot_id, data))

    def delete(self, bot_id: str) -> None:
        """Remove all durable memory for a Bot after its runtime record is gone."""
        with self._lock:
            bot_id = self._validate_bot(bot_id)
            directory = self.root / bot_id
            if not directory.exists():
                return
            lock_path = directory / "owner.lock"
            handle = lock_path.open("a+")
            try:
                fcntl.flock(handle, fcntl.LOCK_EX)
            finally:
                try:
                    fcntl.flock(handle, fcntl.LOCK_UN)
                finally:
                    handle.close()
            shutil.rmtree(directory)

# Short aliases keep integration code readable while retaining the explicit API.
MemoryStore = BotMemoryStore
BotMemory = BotMemoryStore
