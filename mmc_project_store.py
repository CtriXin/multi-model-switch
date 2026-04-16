"""Project-scoped storage helpers for MMC-managed Claude session data."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from mms_state_io import atomic_write_json, locked_state_file

DEFAULT_PRIMARY_CONFIG_DIR = Path(os.path.expanduser("~/.config/mmc"))
PRIMARY_CONFIG_DIR = DEFAULT_PRIMARY_CONFIG_DIR
DEFAULT_PROJECTS_DIR = DEFAULT_PRIMARY_CONFIG_DIR / "projects"
PROJECTS_DIR = DEFAULT_PROJECTS_DIR
CLAUDE_PERSISTENT_ENTRIES = (
    "history.jsonl",
    "sessions",
    "transcripts",
    "file-history",
)
SLOT_MARKER_NAME = ".mmc_slot.json"


def _real_user_home() -> Path:
    for key in ("MMC_REAL_HOME", "REAL_HOME", "ORIGINAL_HOME", "MMS_REAL_HOME"):
        value = str(os.environ.get(key) or "").strip()
        if value:
            return Path(os.path.abspath(os.path.expanduser(value)))

    home = os.path.abspath(os.path.expanduser("~"))
    markers = (
        f"{os.sep}.config{os.sep}mmc{os.sep}",
        f"{os.sep}.config{os.sep}mms{os.sep}",
    )
    for marker in markers:
        if marker in home:
            return Path(home.split(marker, 1)[0])
    return Path(home)


def get_primary_config_dir() -> Path:
    env_path = str(os.environ.get("MMC_CONFIG_HOME") or "").strip()
    if env_path:
        return Path(os.path.abspath(os.path.expanduser(env_path)))
    if PRIMARY_CONFIG_DIR != DEFAULT_PRIMARY_CONFIG_DIR:
        return PRIMARY_CONFIG_DIR
    return _real_user_home() / ".config" / "mmc"


def get_projects_dir() -> Path:
    if PROJECTS_DIR != DEFAULT_PROJECTS_DIR:
        return PROJECTS_DIR
    if PRIMARY_CONFIG_DIR != DEFAULT_PRIMARY_CONFIG_DIR:
        return PRIMARY_CONFIG_DIR / "projects"
    return get_primary_config_dir() / "projects"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked_state_file(path):
        atomic_write_json(str(path), payload, mode=0o600)


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
    return get_projects_dir() / project_key(cwd)


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


def write_slot_marker(
    session_home: str | Path,
    *,
    cwd: str,
    project_key_value: str,
    account_home: str | None = None,
) -> Path:
    path = slot_marker_path(session_home)
    payload = {
        "cwd": os.path.realpath(cwd),
        "project_key": project_key_value,
        "account_home": os.path.realpath(account_home) if account_home else "",
        "runtime_kind": "oauth",
        "written_at": _utc_now(),
    }
    _write_json(path, payload)
    return path


def ensure_claude_project_store(cwd: str | None = None) -> dict:
    canonical = canonical_project_path(cwd)
    key = project_key(canonical)
    projects_dir = get_projects_dir()
    root = claude_project_root(canonical)
    raw_root = claude_raw_root(canonical)
    state_root = claude_state_root(canonical)
    state_sessions = claude_state_sessions_root(canonical)

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

    meta_path = claude_project_metadata_path(canonical)
    if not meta_path.exists():
        payload = {
            "project_key": key,
            "canonical_path": canonical,
            "display_name": os.path.basename(canonical.rstrip(os.sep)) or canonical,
            "created_at": _utc_now(),
        }
        _write_json(meta_path, payload)

    return {
        "project_key": key,
        "canonical_path": canonical,
        "project_root": str(root),
        "raw_root": str(raw_root),
        "state_root": str(state_root),
    }
