"""Index the Pi sessions that command-line launches leave behind.

MMS points every Pi launch at one shared session directory through
``PI_CODING_AGENT_SESSION_DIR``, so a session started with ``mmf`` and one
started from Pilot already write their transcripts side by side. Pilot only
ever read its own store, so those sessions were invisible in the browser.

This reads that directory. It never writes to it: the files belong to Pi, and
a session may be mid-write while we look at it.
"""
from __future__ import annotations
import datetime
import json
import os
import re
from pathlib import Path

# Enough lines to pass the header, the model and the first user turn. Reading
# the whole file for a list of 400 sessions would cost far more than it tells.
_HEAD_LINES = 48
_TITLE_LIMIT = 42
# A path or URL longer than this is shortened in the middle before the title
# is measured, so one long path cannot eat the whole line.
_LOCATOR_LIMIT = 24
# Where a title may end. Latin text breaks on the space; Chinese has none, so
# its punctuation is what keeps a cut off the middle of a phrase.
_BREAKS = " \t,;:!?)]}，。；：！？、）】》”’…"
_ROLES = {"user", "assistant", "toolResult"}
_SCHEMES = ("https://", "http://", "file://")
_QUOTES = "'\"`"
# A path or URL anywhere in the line, not only a whole word: people write
# "使用stride完成https://…" with no space in front of the link. Each branch needs
# real structure, so "A/B测试" is text and not a two-segment path.
_LOCATOR_RE = re.compile(
    r"[a-z][a-z0-9+.-]*://[^\s]*"          # scheme://anything
    r"|~?/[^\s/]+(?:/[^\s/]*)+"            # /a/b or ~/a/b, two segments up
    r"|(?:[\w-]+\.)+[a-z]{2,}/[^\s]*",     # host.tld/anything
    re.IGNORECASE)


def session_dir_for(config_root: str | os.PathLike) -> Path:
    """Where MMS points every Pi launch, CLI or Pilot, to keep its sessions.

    Mirrors ``mms_pi_support._pi_session_dir`` without importing it, because
    that resolves the config root from the launch environment and Pilot
    already knows which root it opened.
    """
    return Path(config_root) / "pi-gateway" / "sessions"


def _iso(seconds: float) -> str:
    return datetime.datetime.fromtimestamp(
        seconds, datetime.timezone.utc).isoformat(timespec="milliseconds")


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


def _shorten_locator(word: str, limit: int) -> str:
    """A long path or URL cut in the middle instead of at the end.

    The front of a path is boilerplate shared by every session on the machine
    and the last segments are what someone actually means, so keeping both
    ends says far more in the same width than a trailing ellipsis does. When
    only one end fits, a URL keeps its host and a path keeps its last segment,
    because that is the half a person recognises.
    """
    lead = word[: len(word) - len(word.lstrip(_QUOTES))]
    trail = word[len(word.rstrip(_QUOTES)):]
    body = word[len(lead): len(word) - len(trail)]
    for scheme in _SCHEMES:
        if body.lower().startswith(scheme):
            body = body[len(scheme):]
            break
    if len(body) <= limit:
        return lead + body + trail
    parts = [part for part in body.split("/") if part]
    if not parts:
        return lead + body[: max(1, limit - 1)] + "…" + trail
    absolute = body.startswith("/")
    head = ("/" if absolute else "") + parts[0]
    kept: list[str] = []
    for part in reversed(parts[1:]):
        candidate = "/".join([part, *kept])
        if len(head) + 3 + len(candidate) > limit:
            break
        kept.insert(0, part)
    if kept:
        return lead + head + "/…/" + "/".join(kept) + trail
    if absolute:
        last = parts[-1]
        short = ("…/" + last) if len(last) + 2 <= limit else "…" + last[-(limit - 1):]
    else:
        short = (head + "/…") if len(head) + 2 <= limit else head[: limit - 1] + "…"
    return lead + short + trail


def _clip(line: str) -> str:
    """Cut at the last natural boundary, so no title ends mid-word."""
    cut = line[:_TITLE_LIMIT]
    for index in range(len(cut) - 1, _TITLE_LIMIT // 2, -1):
        if cut[index] in _BREAKS:
            # An ellipsis already there is the cut; never print two in a row.
            return cut[: index + 1].rstrip(" \t…") + "…"
    return cut.rstrip("…") + "…"


def _title_from(text: str) -> str:
    line = " ".join(text.split())
    # A message that is only a path or a URL gets the whole title budget; one
    # inside a sentence gets less, so it cannot crowd out the words around it.
    limit = _TITLE_LIMIT if _LOCATOR_RE.fullmatch(line) else _LOCATOR_LIMIT
    line = _LOCATOR_RE.sub(lambda m: _shorten_locator(m.group(0), limit), line)
    return line if len(line) <= _TITLE_LIMIT else _clip(line)


def _real(path: str) -> str:
    """Resolve for comparison only. macOS reports one directory as both
    ``/tmp`` and ``/private/tmp``, so a raw string compare misses matches."""
    try:
        return os.path.realpath(path)
    except OSError:
        return path


def workspace_for(cwd: str, workspaces: list[dict]) -> str:
    """The registered folder a command-line session ran in, or "".

    Exact path first, then the deepest registered folder that contains it, so
    a session started in a subdirectory still lands in its own project instead
    of one shared bucket.
    """
    if not cwd:
        return ""
    target = _real(cwd)
    best_id = ""
    best_len = -1
    for workspace in workspaces:
        identifier = str(workspace.get("id") or "")
        path = str(workspace.get("path") or "")
        if not identifier or not path:
            continue
        resolved = _real(path).rstrip("/")
        if not resolved:
            continue
        if target == resolved or target.startswith(resolved + "/"):
            if len(resolved) > best_len:
                best_id, best_len = identifier, len(resolved)
    return best_id


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
        # Shaped like a Pilot session so one list can hold both. These were
        # not started here, so nothing about them is actionable in the browser
        # yet; "owner" is what the page keys that difference off.
        "owner": "cli",
        "channel": "",
        "presetId": "",
        "workspaceId": "",
        "state": "stopped",
        "activity": None,
        "archived": False,
        "forkedFrom": None,
        "capabilities": {"send": False, "stop": False, "fork": False, "archive": False},
        "createdAt": str(header.get("timestamp") or ""),
        "updatedAt": _iso(stat.st_mtime),
        "path": str(path),
    }


def index(session_dir: str | os.PathLike, limit: int = 200,
          workspaces: list[dict] | None = None) -> list[dict]:
    """Summaries for the newest transcripts in `session_dir`, newest first.

    `workspaces` places each session in the registered folder it ran in, so
    the sidebar groups these the same way it groups Pilot's own sessions.
    """
    known = list(workspaces or [])
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
            summary["workspaceId"] = workspace_for(summary["cwd"], known)
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
