"""Index the Pi sessions that command-line launches leave behind.

MMS points every Pi launch at one shared session directory through
``PI_CODING_AGENT_SESSION_DIR``, so a session started with ``mmf`` and one
started from Pilot already write their transcripts side by side. Pilot only
ever read its own store, so those sessions were invisible in the browser.

This reads that directory. It never writes to it: the files belong to Pi, and
a session may be mid-write while we look at it.
"""
from __future__ import annotations
import json
import os
from pathlib import Path

# Enough lines to pass the header, the model and the first user turn. Reading
# the whole file for a list of 400 sessions would cost far more than it tells.
_HEAD_LINES = 48
_TITLE_LIMIT = 42
_ROLES = {"user", "assistant", "toolResult"}


def _text_of(message: dict) -> str:
    """Flatten a Pi message's content blocks into plain text."""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if isinstance(block, dict) and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "\n".join(parts).strip()


def _title_from(text: str) -> str:
    line = " ".join(text.split())
    if len(line) <= _TITLE_LIMIT:
        return line
    return line[:_TITLE_LIMIT] + "…"


def summarize(path: Path) -> dict | None:
    """Read a transcript's head into a session summary, or None if unusable."""
    header: dict = {}
    model = ""
    provider = ""
    title = ""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for index, line in enumerate(handle):
                if index >= _HEAD_LINES:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    # A session being written can end mid-line; skip it.
                    continue
                if not isinstance(event, dict):
                    continue
                kind = event.get("type")
                if kind == "session" and not header:
                    header = event
                elif kind == "model_change":
                    model = str(event.get("model") or event.get("modelId") or model)
                    provider = str(event.get("provider") or provider)
                elif kind == "message" and not title:
                    message = event.get("message")
                    if isinstance(message, dict) and message.get("role") == "user":
                        title = _title_from(_text_of(message))
        stat = path.stat()
    except OSError:
        return None
    session_id = str(header.get("id") or "").strip()
    if not session_id:
        return None
    return {
        "id": f"cli:{session_id}",
        "piSessionId": session_id,
        "title": title or "命令行会话",
        "cwd": str(header.get("cwd") or ""),
        "harness": "pi",
        "modelName": model,
        "providerName": provider,
        # These sessions were not started here, so nothing about them is
        # editable from the browser until one is resumed.
        "owner": "cli",
        "createdAt": str(header.get("timestamp") or ""),
        "updatedAt": stat.st_mtime,
        "path": str(path),
    }


def index(session_dir: str | os.PathLike, limit: int = 200) -> list[dict]:
    """Summaries for the newest transcripts in `session_dir`, newest first."""
    root = Path(session_dir)
    if not root.is_dir():
        return []
    try:
        files = [p for p in root.iterdir() if p.suffix == ".jsonl" and p.is_file()]
    except OSError:
        return []
    # Order by mtime before reading anything, so a large directory only pays
    # the parse cost for the page being shown.
    files.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    summaries = []
    for path in files[: max(0, limit)]:
        summary = summarize(path)
        if summary:
            summaries.append(summary)
    return summaries


def transcript(path: str | os.PathLike, limit: int = 2000) -> list[dict]:
    """Normalized events for rendering one transcript."""
    events: list[dict] = []
    try:
        with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(event, dict) or event.get("type") != "message":
                    continue
                message = event.get("message")
                if not isinstance(message, dict):
                    continue
                role = str(message.get("role") or "")
                if role not in _ROLES:
                    continue
                events.append({
                    "id": str(event.get("id") or ""),
                    "role": role,
                    "text": _text_of(message),
                    "at": str(event.get("timestamp") or ""),
                })
    except OSError:
        return []
    # Keep the tail: the end of a long session is what someone wants to see.
    return events[-max(1, limit):]
