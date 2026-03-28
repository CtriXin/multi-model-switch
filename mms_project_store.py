"""Project-scoped storage helpers for MMS-managed CLI session data."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

PRIMARY_CONFIG_DIR = Path(os.path.expanduser("~/.config/mms"))
PROJECTS_DIR = PRIMARY_CONFIG_DIR / "projects"
CLAUDE_PERSISTENT_ENTRIES = (
    "history.jsonl",
    "sessions",
    "transcripts",
    "file-history",
)
SLOT_MARKER_NAME = ".mms_slot.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_project_path(cwd: str | None = None) -> str:
    cwd = os.path.realpath(cwd or os.getcwd())
    try:
        root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if root:
            return os.path.realpath(root)
    except Exception:
        pass
    return cwd


def project_key(cwd: str | None = None) -> str:
    canonical = canonical_project_path(cwd)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def project_root(cwd: str | None = None) -> Path:
    return PROJECTS_DIR / project_key(cwd)


def claude_project_root(cwd: str | None = None) -> Path:
    return project_root(cwd) / "claude"


def claude_raw_root(cwd: str | None = None) -> Path:
    return claude_project_root(cwd) / "raw"


def claude_state_root(cwd: str | None = None) -> Path:
    return claude_project_root(cwd) / "state"


def claude_state_sessions_root(cwd: str | None = None) -> Path:
    return claude_state_root(cwd) / "sessions"


def claude_raw_entry_path(entry: str, cwd: str | None = None) -> Path:
    return claude_raw_root(cwd) / entry


def claude_project_metadata_path(cwd: str | None = None) -> Path:
    return claude_state_root(cwd) / "metadata.json"


def slot_marker_path(session_home: str | Path) -> Path:
    return Path(session_home) / SLOT_MARKER_NAME


def read_slot_marker(session_home: str | Path) -> dict | None:
    path = slot_marker_path(session_home)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_slot_marker(session_home: str | Path, *, cwd: str, project_key_value: str, account_id: str, runtime_kind: str) -> Path:
    path = slot_marker_path(session_home)
    payload = {
        "cwd": os.path.realpath(cwd),
        "project_key": project_key_value,
        "account_id": account_id or "",
        "runtime_kind": runtime_kind,
        "written_at": _utc_now(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _copy_entry_if_missing(src: Path, dst: Path) -> None:
    if not src.exists() or dst.exists():
        return
    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)


def ensure_claude_project_store(cwd: str | None = None) -> dict:
    canonical = canonical_project_path(cwd)
    key = project_key(canonical)
    root = claude_project_root(canonical)
    raw_root = claude_raw_root(canonical)
    state_root = claude_state_root(canonical)
    state_sessions = claude_state_sessions_root(canonical)

    for path in (PROJECTS_DIR, root, raw_root, state_root, state_sessions):
        path.mkdir(parents=True, exist_ok=True)

    for entry in CLAUDE_PERSISTENT_ENTRIES:
        target = raw_root / entry
        if entry.endswith(".jsonl"):
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.touch()
        else:
            target.mkdir(parents=True, exist_ok=True)

    meta_path = claude_project_metadata_path(canonical)
    if not meta_path.exists():
        payload = {
            "project_key": key,
            "canonical_path": canonical,
            "display_name": os.path.basename(canonical.rstrip(os.sep)) or canonical,
            "created_at": _utc_now(),
        }
        meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    _seed_claude_project_store_from_global(canonical)

    return {
        "project_key": key,
        "canonical_path": canonical,
        "project_root": str(root),
        "raw_root": str(raw_root),
        "state_root": str(state_root),
    }


def _seed_claude_project_store_from_global(cwd: str | None = None) -> None:
    raw_root = claude_raw_root(cwd)
    sentinel = claude_state_root(cwd) / ".seeded"
    if sentinel.exists():
        return

    real_claude_dir = Path(os.path.expanduser("~/.claude"))
    if real_claude_dir.exists():
        for entry in CLAUDE_PERSISTENT_ENTRIES:
            _copy_entry_if_missing(real_claude_dir / entry, raw_root / entry)
    sentinel.write_text(_utc_now() + "\n", encoding="utf-8")
