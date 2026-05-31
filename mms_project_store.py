"""Project-scoped storage helpers for MMS-managed CLI session data."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from mms_state_io import resolve_mms_config_dir

DEFAULT_PRIMARY_CONFIG_DIR = Path(os.path.expanduser("~/.config/mms"))
PRIMARY_CONFIG_DIR = DEFAULT_PRIMARY_CONFIG_DIR
DEFAULT_PROJECTS_DIR = DEFAULT_PRIMARY_CONFIG_DIR / "projects"
PROJECTS_DIR = DEFAULT_PROJECTS_DIR
CLAUDE_PERSISTENT_ENTRIES = (
    "history.jsonl",
    "projects",
    "sessions",
    "transcripts",
    "file-history",
)
SLOT_MARKER_NAME = ".mms_slot.json"


def _real_user_home() -> Path:
    for key in ("MMS_REAL_HOME", "REAL_HOME", "ORIGINAL_HOME"):
        value = str(os.environ.get(key) or "").strip()
        if value:
            return Path(os.path.abspath(os.path.expanduser(value)))

    home = os.path.abspath(os.path.expanduser("~"))
    gateway_markers = (
        f"{os.sep}.config{os.sep}mms{os.sep}codex-gateway{os.sep}",
        f"{os.sep}.config{os.sep}mms{os.sep}claude-gateway{os.sep}",
    )
    for marker in gateway_markers:
        if marker in home:
            return Path(home.split(marker, 1)[0])
    return Path(home)


def get_primary_config_dir() -> Path:
    if PRIMARY_CONFIG_DIR != DEFAULT_PRIMARY_CONFIG_DIR:
        return PRIMARY_CONFIG_DIR
    return Path(resolve_mms_config_dir())


def get_projects_dir() -> Path:
    if PROJECTS_DIR != DEFAULT_PROJECTS_DIR:
        return PROJECTS_DIR
    if PRIMARY_CONFIG_DIR != DEFAULT_PRIMARY_CONFIG_DIR:
        return PRIMARY_CONFIG_DIR / "projects"
    return get_primary_config_dir() / "projects"


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


def _normalize_account_id(account_id: str | None = None) -> str:
    value = str(account_id or "").strip().lower()
    if not value:
        return "shared"
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value)


def project_key(cwd: str | None = None, account_id: str | None = None) -> str:
    canonical = canonical_project_path(cwd)
    scope = f"{_normalize_account_id(account_id)}::{canonical}"
    return hashlib.sha256(scope.encode("utf-8")).hexdigest()[:16]


def project_root(cwd: str | None = None, account_id: str | None = None) -> Path:
    return get_projects_dir() / project_key(cwd, account_id=account_id)


def claude_project_root(cwd: str | None = None, account_id: str | None = None) -> Path:
    return project_root(cwd, account_id=account_id) / "claude"


def claude_raw_root(cwd: str | None = None, account_id: str | None = None) -> Path:
    return claude_project_root(cwd, account_id=account_id) / "raw"


def claude_state_root(cwd: str | None = None, account_id: str | None = None) -> Path:
    return claude_project_root(cwd, account_id=account_id) / "state"


def claude_state_sessions_root(cwd: str | None = None, account_id: str | None = None) -> Path:
    return claude_state_root(cwd, account_id=account_id) / "sessions"


def claude_raw_entry_path(entry: str, cwd: str | None = None, account_id: str | None = None) -> Path:
    return claude_raw_root(cwd, account_id=account_id) / entry


def claude_project_metadata_path(cwd: str | None = None, account_id: str | None = None) -> Path:
    return claude_state_root(cwd, account_id=account_id) / "metadata.json"


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


def write_slot_marker(
    session_home: str | Path,
    *,
    cwd: str,
    project_key_value: str,
    account_id: str,
    runtime_kind: str,
    account_home: str | None = None,
    resume_scope_id: str | None = None,
    resume_model: str | None = None,
) -> Path:
    path = slot_marker_path(session_home)
    payload = {
        "cwd": os.path.realpath(cwd),
        "project_key": project_key_value,
        "account_id": account_id or "",
        "resume_scope_id": resume_scope_id or account_id or "",
        "resume_model": resume_model or "",
        "runtime_kind": runtime_kind,
        "account_home": os.path.realpath(account_home) if account_home else "",
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


def ensure_claude_project_store(cwd: str | None = None, *, account_id: str | None = None) -> dict:
    canonical = canonical_project_path(cwd)
    normalized_account_id = _normalize_account_id(account_id)
    key = project_key(canonical, account_id=normalized_account_id)
    projects_dir = get_projects_dir()
    root = claude_project_root(canonical, account_id=normalized_account_id)
    raw_root = claude_raw_root(canonical, account_id=normalized_account_id)
    state_root = claude_state_root(canonical, account_id=normalized_account_id)
    state_sessions = claude_state_sessions_root(
        canonical,
        account_id=normalized_account_id,
    )

    for path in (projects_dir, root, raw_root, state_root, state_sessions):
        path.mkdir(parents=True, exist_ok=True)

    for entry in CLAUDE_PERSISTENT_ENTRIES:
        target = raw_root / entry
        if entry.endswith(".jsonl"):
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.touch()
        else:
            target.mkdir(parents=True, exist_ok=True)

    meta_path = claude_project_metadata_path(
        canonical,
        account_id=normalized_account_id,
    )
    if not meta_path.exists():
        payload = {
            "project_key": key,
            "canonical_path": canonical,
            "account_id": normalized_account_id,
            "display_name": os.path.basename(canonical.rstrip(os.sep)) or canonical,
            "created_at": _utc_now(),
        }
        meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "project_key": key,
        "canonical_path": canonical,
        "account_id": normalized_account_id,
        "project_root": str(root),
        "raw_root": str(raw_root),
        "state_root": str(state_root),
    }
