from __future__ import annotations

import argparse
import copy
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from mmc_project_store import (
    CLAUDE_PERSISTENT_ENTRIES,
    claude_raw_entry_path,
    ensure_claude_project_store,
    get_primary_config_dir,
    read_slot_marker,
    write_slot_marker,
)
from mmc_session_index import (
    bind_claude_session_process,
    finalize_claude_session,
    list_indexed_sessions,
    record_claude_session_start,
    resolve_session_ref,
)
from mms_state_io import atomic_write_json, locked_state_file

_SAFE_PARENT_ENV_KEYS = (
    "TERM",
    "COLORTERM",
)
_SYSTEM_FALLBACK_PATH_DIRS = (
    "/usr/bin",
    "/bin",
    "/usr/sbin",
    "/sbin",
)
_PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
)
_ALLOWED_LAUNCH_ENV_KEYS = (
    "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_REASONING_MODEL",
    "CLAUDE_CODE_SUBAGENT_MODEL",
    "CLAUDE_CODE_AUTO_COMPACT_WINDOW",
    "CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE",
    "CLAUDE_CODE_ENABLE_SUBAGENT_PARALLELISM",
    "CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
    "CLAUDE_CODE_ATTRIBUTION_HEADER",
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS",
    "API_TIMEOUT_MS",
)
_TOP_LEVEL_STATE_ALLOWLIST = (
    "userID",
    "firstStartTime",
    "numStartups",
    "bypassPermissionsModeAccepted",
    "alwaysThinkingEnabled",
    "hasCompletedOnboarding",
    "lastOnboardingVersion",
    "lastReleaseNotesSeen",
    "installMethod",
    "deepLinkTerminal",
    "effortCalloutDismissed",
    "effortCalloutV2Dismissed",
    "migrationVersion",
    "officialMarketplaceAutoInstallAttempted",
    "officialMarketplaceAutoInstalled",
    "opus1mMergeNoticeSeenCount",
    "opusProMigrationComplete",
    "sonnet1m45MigrationComplete",
    "voiceNoticeSeenCount",
)
_STATE_SCALAR_DICT_ALLOWLIST = ("tipsHistory",)
_ACCOUNT_ALLOWLIST = (
    "accountCreatedAt",
    "accountUuid",
    "billingType",
    "displayName",
    "emailAddress",
    "hasExtraUsageEnabled",
    "organizationName",
    "organizationRole",
    "organizationUuid",
    "subscriptionCreatedAt",
    "workspaceRole",
)
_CLAUDE_AI_OAUTH_ALLOWLIST = (
    "accessToken",
    "refreshToken",
    "expiresAt",
    "expiresIn",
    "tokenType",
    "token_type",
    "emailAddress",
    "accountUuid",
    "organizationUuid",
)
_PROJECT_STATE_ALLOWLIST = (
    "hasTrustDialogAccepted",
    "hasCompletedProjectOnboarding",
    "hasClaudeMdExternalIncludesApproved",
    "hasClaudeMdExternalIncludesWarningShown",
    "projectOnboardingSeenCount",
    "lastGracefulShutdown",
)
_DEFAULT_TIPS_HISTORY = {
    "theme-command": 999,
    "terminal-setup": 999,
}
_MAX_LIVE_SESSIONS = 4
_FORBIDDEN_BINARY_PATH_PARTS = (
    "/.mms/",
    "/.config/mms/",
    "/ccswitch",
    "/hive",
)
_MINDKEEPER_SERVER_RELATIVE_PATH = (".local", "share", "mindkeeper", "dist", "server.js")
_CLAUDE_NO_PROXY_TOKENS = (
    "*",
    "anthropic.com",
    "api.anthropic.com",
    "claude.ai",
)
_CLAUDE_PROXY_GUARD_TARGETS = (
    ("anthropic", "https://api.anthropic.com"),
    ("claude", "https://claude.ai"),
)
_HOOK_DEPENDENCY_TOOL_NAMES = ("jq", "rtk")
_ALLOWED_SESSION_HOOK_FILES = (
    ("PreToolUse", "Bash", "rtk-rewrite.sh", ""),
    ("PreToolUse", "Read", "read-once-hook.sh", "READ_ONCE_DIFF=1 "),
    ("PostCompact", "", "read-once-compact.sh", ""),
)


def _real_user_home() -> Path:
    for key in ("MMC_REAL_HOME", "REAL_HOME", "ORIGINAL_HOME", "MMS_REAL_HOME"):
        value = str(os.environ.get(key) or "").strip()
        if value:
            return Path(os.path.abspath(os.path.expanduser(value)))
    return Path(os.path.abspath(os.path.expanduser("~")))


def _config_root() -> Path:
    return get_primary_config_dir()


def _account_home() -> Path:
    return _config_root() / "accounts" / "default"


def _account_claude_dir() -> Path:
    return _account_home() / ".claude"


def _account_state_path() -> Path:
    return _account_home() / ".claude.json"


def _account_settings_path() -> Path:
    return _account_claude_dir() / "settings.json"


def _tmp_root() -> Path:
    return _config_root() / "tmp"


def _session_slots_dir() -> Path:
    return _account_home() / "s"


def _session_slots_lock_path() -> Path:
    return _session_slots_dir() / ".reserve"


def _session_tmp_path(session_home: Path) -> Path:
    return _tmp_root() / session_home.name


def _repo_root() -> Path:
    return Path(__file__).resolve().parent


def _repo_hook_path(file_name: str) -> Path:
    return _repo_root() / "hooks" / file_name


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(int(pid), 0)
    except (ProcessLookupError, FileNotFoundError, ValueError, TypeError):
        return False
    except PermissionError:
        return True
    return True


def _remove_path_tree(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        try:
            path.unlink()
        except OSError:
            pass
        return
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)


def _cleanup_session_runtime_artifacts(session_home: Path) -> None:
    _remove_path_tree(_session_tmp_path(session_home))
    _remove_path_tree(session_home)


def _cleanup_stale_session_slots(sessions_dir: Path) -> list[Path]:
    sessions_dir.mkdir(parents=True, exist_ok=True)
    active_slots = []
    for entry in sessions_dir.iterdir():
        if not entry.is_dir():
            continue
        pid_text = str(entry.name).split("-", 1)[0]
        try:
            pid = int(pid_text)
        except ValueError:
            _cleanup_session_runtime_artifacts(entry)
            continue
        if _pid_alive(pid):
            active_slots.append(entry)
            continue
        _cleanup_session_runtime_artifacts(entry)
    return active_slots


def _reserve_session_home() -> tuple[Path | None, int, int]:
    sessions_dir = _session_slots_dir()
    with locked_state_file(_session_slots_lock_path()):
        active_slots = _cleanup_stale_session_slots(sessions_dir)
        active_before = len(active_slots)
        active_after = active_before + 1
        if active_after > _MAX_LIVE_SESSIONS:
            return None, active_before, active_after
        session_home = sessions_dir / f"{os.getpid()}-{int(time.time() * 1000)}"
        suffix = 0
        while session_home.exists():
            suffix += 1
            session_home = sessions_dir / f"{os.getpid()}-{int(time.time() * 1000)}-{suffix}"
        session_home.mkdir(parents=True, exist_ok=False)
        return session_home, active_before, active_after


def _copy_allowed_scalar_fields(payload, allowed_keys):
    payload = payload if isinstance(payload, dict) else {}
    copied = {}
    for key in allowed_keys:
        value = payload.get(key)
        if isinstance(value, (str, int, float, bool)):
            copied[key] = copy.deepcopy(value)
    return copied


def _copy_allowed_scalar_dict_fields(payload, allowed_keys):
    payload = payload if isinstance(payload, dict) else {}
    copied = {}
    for key in allowed_keys:
        value = payload.get(key)
        if not isinstance(value, dict):
            continue
        child = {}
        for child_key, child_value in value.items():
            if isinstance(child_value, (str, int, float, bool)):
                child[str(child_key)] = copy.deepcopy(child_value)
        if child:
            copied[key] = child
    return copied


def _builtin_mindkeeper_server_map() -> dict:
    server_script = _real_user_home().joinpath(*_MINDKEEPER_SERVER_RELATIVE_PATH)
    if not server_script.exists():
        return {}
    return {
        "mindkeeper": {
            "command": "node",
            "args": [str(server_script)],
        }
    }


def _sanitize_project_state_entry(entry):
    entry = entry if isinstance(entry, dict) else {}
    cleaned = _copy_allowed_scalar_fields(entry, _PROJECT_STATE_ALLOWLIST)
    for key in ("allowedTools", "mcpContextUris", "enabledMcpjsonServers", "disabledMcpjsonServers"):
        value = entry.get(key)
        if isinstance(value, list):
            cleaned[key] = copy.deepcopy(value)
    return cleaned


def _sanitize_project_state_map(projects_data):
    if not isinstance(projects_data, dict):
        return {}
    projects = {}
    for project_path, entry in projects_data.items():
        normalized_path = os.path.realpath(str(project_path or "").strip())
        if not normalized_path:
            continue
        cleaned = _sanitize_project_state_entry(entry)
        if cleaned:
            projects[normalized_path] = cleaned
    return projects


def _strip_restore_state(data):
    payload = dict(data) if isinstance(data, dict) else {}
    payload.pop("lastSessionId", None)
    payload.pop("lastCost", None)
    return payload


def _sanitize_source_claude_state_payload(data):
    payload = _strip_restore_state(data)
    cleaned = _copy_allowed_scalar_fields(payload, _TOP_LEVEL_STATE_ALLOWLIST)
    cleaned.update(_copy_allowed_scalar_dict_fields(payload, _STATE_SCALAR_DICT_ALLOWLIST))

    oauth_account = _copy_allowed_scalar_fields(payload.get("oauthAccount"), _ACCOUNT_ALLOWLIST)
    if oauth_account:
        cleaned["oauthAccount"] = oauth_account

    claude_ai_oauth = _copy_allowed_scalar_fields(payload.get("claudeAiOauth"), _CLAUDE_AI_OAUTH_ALLOWLIST)
    if claude_ai_oauth:
        cleaned["claudeAiOauth"] = claude_ai_oauth

    return cleaned


def _sanitize_mmc_account_state_payload(data):
    payload = _sanitize_source_claude_state_payload(data)
    projects = _sanitize_project_state_map((data or {}).get("projects"))
    if projects:
        payload["projects"] = projects
    return payload


def _merge_scalar_dict_entries(existing_payload, incoming_payload, *, prefer_max_numeric=False):
    existing_payload = existing_payload if isinstance(existing_payload, dict) else {}
    incoming_payload = incoming_payload if isinstance(incoming_payload, dict) else {}
    merged = copy.deepcopy(existing_payload)
    for key, incoming_value in incoming_payload.items():
        existing_value = existing_payload.get(key)
        if (
            prefer_max_numeric
            and isinstance(existing_value, (int, float))
            and not isinstance(existing_value, bool)
            and isinstance(incoming_value, (int, float))
            and not isinstance(incoming_value, bool)
        ):
            merged[key] = max(existing_value, incoming_value)
        else:
            merged[key] = copy.deepcopy(incoming_value)
    return merged


def _parse_iso8601_utc(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _merge_oauth_token_state(existing_payload, incoming_payload):
    existing_payload = existing_payload if isinstance(existing_payload, dict) else {}
    incoming_payload = incoming_payload if isinstance(incoming_payload, dict) else {}
    existing_expiry = _parse_iso8601_utc(existing_payload.get("expiresAt"))
    incoming_expiry = _parse_iso8601_utc(incoming_payload.get("expiresAt"))
    if existing_expiry and incoming_expiry:
        return copy.deepcopy(incoming_payload if incoming_expiry >= existing_expiry else existing_payload)
    if incoming_expiry:
        return copy.deepcopy(incoming_payload)
    if existing_expiry:
        return copy.deepcopy(existing_payload)
    incoming_has_tokens = any(
        str(incoming_payload.get(key) or "").strip()
        for key in ("accessToken", "refreshToken", "tokenType", "token_type")
    )
    if incoming_has_tokens:
        return copy.deepcopy(incoming_payload)
    return copy.deepcopy(existing_payload or incoming_payload)


def _merge_account_state(existing_data, incoming_data):
    existing = _sanitize_mmc_account_state_payload(existing_data)
    incoming = _sanitize_mmc_account_state_payload(incoming_data)
    merged = copy.deepcopy(existing)

    for key in _TOP_LEVEL_STATE_ALLOWLIST:
        existing_value = existing.get(key)
        incoming_value = incoming.get(key)
        if key == "firstStartTime":
            chosen = existing_value or incoming_value
            if isinstance(chosen, (str, int, float, bool)):
                merged[key] = copy.deepcopy(chosen)
            continue
        if key == "numStartups":
            numeric_values = [value for value in (existing_value, incoming_value) if isinstance(value, (int, float))]
            if numeric_values:
                merged[key] = max(numeric_values)
            continue
        if incoming_value is not None:
            merged[key] = copy.deepcopy(incoming_value)
        elif existing_value is not None:
            merged[key] = copy.deepcopy(existing_value)

    for key in _STATE_SCALAR_DICT_ALLOWLIST:
        merged[key] = _merge_scalar_dict_entries(
            existing.get(key),
            incoming.get(key),
            prefer_max_numeric=(key == "tipsHistory"),
        )
        if not merged[key]:
            merged.pop(key, None)

    merged_account = copy.deepcopy(existing.get("oauthAccount") or {})
    if isinstance(incoming.get("oauthAccount"), dict):
        merged_account.update(copy.deepcopy(incoming["oauthAccount"]))
    if merged_account:
        merged["oauthAccount"] = merged_account
    else:
        merged.pop("oauthAccount", None)

    merged_token = _merge_oauth_token_state(existing.get("claudeAiOauth"), incoming.get("claudeAiOauth"))
    if merged_token:
        merged["claudeAiOauth"] = merged_token
    else:
        merged.pop("claudeAiOauth", None)

    merged_projects = copy.deepcopy(existing.get("projects") or {})
    merged_projects.update(copy.deepcopy(incoming.get("projects") or {}))
    if merged_projects:
        merged["projects"] = merged_projects
    else:
        merged.pop("projects", None)

    merged.pop("mcpServers", None)

    return merged


def _default_ui_state_seed():
    return {
        "firstStartTime": _utc_now(),
        "numStartups": 1,
        "hasCompletedOnboarding": True,
        "lastOnboardingVersion": "mmc-v1",
        "lastReleaseNotesSeen": "mmc-v1",
        "installMethod": "mmc",
        "migrationVersion": 1,
        "tipsHistory": copy.deepcopy(_DEFAULT_TIPS_HISTORY),
    }


def _load_json_dict(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, payload: dict) -> None:
    with locked_state_file(path):
        atomic_write_json(str(path), payload, mode=0o600)


def _load_source_settings_theme(source_home: Path) -> str:
    settings_path = source_home / ".claude" / "settings.json"
    loaded = _load_json_dict(settings_path)
    theme = loaded.get("theme")
    return str(theme).strip() if isinstance(theme, str) else ""


def _bootstrap_account_state() -> None:
    account_home = _account_home()
    account_home.mkdir(parents=True, exist_ok=True)
    _account_claude_dir().mkdir(parents=True, exist_ok=True)

    state_path = _account_state_path()
    current_state = _load_json_dict(state_path)
    next_state = _merge_account_state(_default_ui_state_seed(), current_state)
    _write_json(state_path, next_state)

    settings_path = _account_settings_path()
    if not settings_path.exists():
        _write_json(settings_path, {})


def _import_legacy_auth_state(source_home: str) -> None:
    source_root = Path(os.path.abspath(os.path.expanduser(str(source_home or "").strip())))
    if not source_root.exists():
        raise SystemExit(f"mmc: legacy source 不存在: {source_root}")
    source_state = _load_json_dict(source_root / ".claude.json")
    sanitized = _sanitize_source_claude_state_payload(source_state)
    oauth_payload = {}
    for key in ("userID", "oauthAccount", "claudeAiOauth"):
        value = sanitized.get(key)
        if value:
            oauth_payload[key] = copy.deepcopy(value)
    if not oauth_payload:
        raise SystemExit(f"mmc: legacy source 未找到可导入的 OAuth state: {source_root}")

    _bootstrap_account_state()
    state_path = _account_state_path()
    merged = _merge_account_state(_load_json_dict(state_path), oauth_payload)
    _write_json(state_path, merged)

    theme = _load_source_settings_theme(source_root)
    if theme:
        _write_json(_account_settings_path(), {"theme": theme})


def _ensure_project_trust(data, project_path: str):
    payload = dict(data) if isinstance(data, dict) else {}
    normalized_project = os.path.realpath(str(project_path or "").strip())
    projects = payload.get("projects")
    if not isinstance(projects, dict):
        projects = {}
    entry = dict(projects.get(normalized_project) or {})
    entry = _sanitize_project_state_entry(entry)
    entry.setdefault("allowedTools", [])
    entry.setdefault("mcpContextUris", [])
    entry.setdefault("enabledMcpjsonServers", [])
    entry.setdefault("disabledMcpjsonServers", [])
    entry["hasTrustDialogAccepted"] = True
    entry["hasCompletedProjectOnboarding"] = True
    entry["hasClaudeMdExternalIncludesApproved"] = True
    entry["hasClaudeMdExternalIncludesWarningShown"] = True
    seen_count = entry.get("projectOnboardingSeenCount")
    if isinstance(seen_count, (int, float)) and not isinstance(seen_count, bool):
        entry["projectOnboardingSeenCount"] = max(int(seen_count), 1)
    else:
        entry["projectOnboardingSeenCount"] = 1
    entry.setdefault("lastGracefulShutdown", False)
    projects[normalized_project] = entry
    payload["projects"] = projects
    return payload


def _overlay_project_scoped_resume_state(data, project_path: str, explicit_session_id: str = ""):
    payload = dict(data) if isinstance(data, dict) else {}
    normalized_project = os.path.realpath(str(project_path or "").strip())
    if not normalized_project:
        return payload

    session_id = str(explicit_session_id or "").strip()
    if not session_id:
        candidates = []
        for session in list_indexed_sessions():
            session_project = os.path.realpath(
                str(session.get("project_path") or session.get("cwd") or "").strip()
            )
            if session_project != normalized_project:
                continue
            candidate_id = str(session.get("session_id") or "").strip()
            if not candidate_id or candidate_id.startswith("pid-"):
                continue
            sort_key = str(session.get("last_active_at") or session.get("started_at") or "").strip()
            candidates.append((sort_key, candidate_id))
        if candidates:
            candidates.sort(reverse=True)
            session_id = candidates[0][1]

    if not session_id:
        return payload

    projects = payload.get("projects")
    if not isinstance(projects, dict):
        projects = {}
    entry = dict(projects.get(normalized_project) or {})
    entry["lastSessionId"] = session_id
    projects[normalized_project] = entry
    payload["projects"] = projects
    return payload


def _build_session_state(project_path: str, *, explicit_session_id: str = "", bypass: bool = False):
    account_state = _load_json_dict(_account_state_path())
    state = _merge_account_state(_default_ui_state_seed(), account_state)
    state = _overlay_project_scoped_resume_state(state, project_path, explicit_session_id=explicit_session_id)
    state = _ensure_project_trust(state, project_path)
    builtin_mcp = _builtin_mindkeeper_server_map()
    if builtin_mcp:
        state["mcpServers"] = builtin_mcp
    else:
        state.pop("mcpServers", None)
    if bypass:
        state["bypassPermissionsModeAccepted"] = True
    else:
        state.pop("bypassPermissionsModeAccepted", None)
    return state


def _build_builtin_hook_settings() -> dict:
    hooks = {}
    for event_name, matcher, file_name, env_prefix in _ALLOWED_SESSION_HOOK_FILES:
        hook_path = _repo_hook_path(file_name).resolve()
        if not hook_path.exists():
            continue
        command = f"{env_prefix}/bin/bash {shlex.quote(str(hook_path))}".strip()
        hooks.setdefault(event_name, []).append(
            {
                "matcher": matcher,
                "hooks": [
                    {
                        "type": "command",
                        "command": command,
                    }
                ],
            }
        )
    return hooks


def _build_session_settings():
    settings = {}
    theme = _load_json_dict(_account_settings_path()).get("theme")
    if isinstance(theme, str) and theme.strip():
        settings["theme"] = theme.strip()
    # MMC only injects repo-owned hooks; it never inherits global/source hook state.
    hooks = _build_builtin_hook_settings()
    if hooks:
        settings["hooks"] = hooks
    return settings


def _prepare_session_tree(session_home: Path, workspace: str):
    workspace = os.path.realpath(workspace)
    store = ensure_claude_project_store(workspace)
    session_claude_dir = session_home / ".claude"
    session_claude_dir.mkdir(parents=True, exist_ok=True)
    for entry in list(session_claude_dir.iterdir()):
        if entry.name in CLAUDE_PERSISTENT_ENTRIES or entry.name == "settings.json":
            continue
        if entry.is_symlink() or entry.is_file():
            entry.unlink()
        elif entry.is_dir():
            shutil.rmtree(entry)
    for entry_name in CLAUDE_PERSISTENT_ENTRIES:
        dst = session_claude_dir / entry_name
        target = claude_raw_entry_path(entry_name, workspace)
        if not dst.exists() and not dst.is_symlink():
            os.symlink(target, dst)
    record_claude_session_start(cwd=workspace, pid=os.getpid(), slot_home=str(session_home))
    write_slot_marker(
        session_home,
        cwd=workspace,
        project_key_value=store["project_key"],
        account_home=str(_account_home()),
    )


def _link_keychains_only(session_home: Path):
    real_keychains = _real_user_home() / "Library" / "Keychains"
    if not real_keychains.exists():
        return
    library_dir = session_home / "Library"
    library_dir.mkdir(parents=True, exist_ok=True)
    target = library_dir / "Keychains"
    if target.exists() or target.is_symlink():
        return
    os.symlink(real_keychains, target)


def _sanitize_account_sync_payload(data):
    payload = data if isinstance(data, dict) else {}
    cleaned = {}
    for key in ("userID",):
        value = payload.get(key)
        if isinstance(value, (str, int, float, bool)):
            cleaned[key] = copy.deepcopy(value)
    oauth_account = _copy_allowed_scalar_fields(payload.get("oauthAccount"), _ACCOUNT_ALLOWLIST)
    if oauth_account:
        cleaned["oauthAccount"] = oauth_account
    claude_ai_oauth = _copy_allowed_scalar_fields(payload.get("claudeAiOauth"), _CLAUDE_AI_OAUTH_ALLOWLIST)
    if claude_ai_oauth:
        cleaned["claudeAiOauth"] = claude_ai_oauth
    projects = _sanitize_project_state_map(payload.get("projects"))
    if projects:
        cleaned["projects"] = projects
    return cleaned


def _sync_session_state_to_account_home(session_home: Path):
    session_state_path = session_home / ".claude.json"
    if session_state_path.exists():
        incoming = _sanitize_account_sync_payload(_load_json_dict(session_state_path))
        merged = _merge_account_state(_load_json_dict(_account_state_path()), incoming)
        _write_json(_account_state_path(), merged)

    settings_path = session_home / ".claude" / "settings.json"
    if settings_path.exists():
        loaded = _load_json_dict(settings_path)
        payload = {}
        if isinstance(loaded.get("theme"), str) and loaded["theme"].strip():
            payload["theme"] = loaded["theme"].strip()
        _write_json(_account_settings_path(), payload)


def _finalize_session(session_home: Path, *, exit_code: int, stale_cleanup: bool = False):
    marker = read_slot_marker(session_home)
    try:
        if marker and not stale_cleanup:
            _sync_session_state_to_account_home(session_home)
        finalize_claude_session(
            cwd=str(marker.get("cwd") or os.getcwd()) if marker else os.getcwd(),
            pid=os.getpid(),
            exit_code=exit_code,
            stale_cleanup=stale_cleanup,
        )
    finally:
        _cleanup_session_runtime_artifacts(session_home)


def _apply_proxy_env(env: dict[str, str], proxy_url: str, no_proxy: str = ""):
    proxy_url = str(proxy_url or "").strip()
    no_proxy = str(no_proxy or "").strip()
    if proxy_url:
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            env[key] = proxy_url
    if no_proxy:
        for key in ("NO_PROXY", "no_proxy"):
            env[key] = no_proxy
    return env


def _proxy_dns_mode(proxy_url: str) -> str:
    proxy_url = str(proxy_url or "").strip()
    if not proxy_url:
        return "direct"
    try:
        scheme = (urlsplit(proxy_url).scheme or "").strip().lower()
    except Exception:
        scheme = ""
    if scheme == "socks5h":
        return "remote"
    if scheme == "socks5":
        return "local-risk"
    if scheme in {"http", "https"}:
        return "proxy-likely"
    return scheme or "proxy"


def _split_no_proxy_values(no_proxy: str) -> list[str]:
    raw = str(no_proxy or "").strip()
    if not raw:
        return []
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def _claude_no_proxy_conflicts(no_proxy: str) -> list[str]:
    conflicts = []
    for item in _split_no_proxy_values(no_proxy):
        normalized = item.lstrip(".")
        if normalized in _CLAUDE_NO_PROXY_TOKENS:
            conflicts.append(item)
            continue
        for token in _CLAUDE_NO_PROXY_TOKENS:
            if token == "*":
                continue
            if normalized == token or normalized.endswith(f".{token}"):
                conflicts.append(item)
                break
    return sorted(set(conflicts))


def _run_proxy_probe(proxy_url: str, target_url: str, *, no_proxy: str = "", force_ipv4: bool = True) -> dict:
    curl_bin = shutil.which("curl")
    if not curl_bin:
        return {"ok": False, "detail": "curl missing"}
    cmd = [
        curl_bin,
        *(["-4"] if force_ipv4 else []),
        "--silent",
        "--show-error",
        "--head",
        "--location",
        "--max-time",
        "8",
        "--output",
        "/dev/null",
        "--write-out",
        "%{http_code}",
        "--proxy",
        str(proxy_url).strip(),
        target_url,
    ]
    if str(no_proxy or "").strip():
        cmd.extend(["--noproxy", str(no_proxy).strip()])
    result = subprocess.run(cmd, capture_output=True, text=True)
    http_code = str(result.stdout or "").strip()
    ok = result.returncode == 0 and bool(http_code) and http_code not in {"000", "407"}
    detail = str(result.stderr or "").strip()
    if http_code and http_code not in {"000"}:
        detail = f"HTTP {http_code}" + (f" · {detail}" if detail else "")
    if len(detail) > 200:
        detail = detail[:200] + "..."
    return {"ok": ok, "detail": detail, "http_code": http_code}


def _build_local_proxy_guard(proxy_url: str, no_proxy: str) -> dict:
    proxy_url = str(proxy_url or "").strip()
    no_proxy = str(no_proxy or "").strip()
    guard = {
        "status": "ok",
        "block_reason": "",
        "dns_mode": _proxy_dns_mode(proxy_url),
        "no_proxy_conflicts": _claude_no_proxy_conflicts(no_proxy),
        "targets": [],
    }
    if not proxy_url:
        guard["status"] = "blocked"
        guard["block_reason"] = "OAuth Claude / MMC 路线强制要求 proxy"
        return guard
    if guard["no_proxy_conflicts"]:
        guard["status"] = "blocked"
        guard["block_reason"] = "NO_PROXY 命中了 Claude 域名，存在直连泄漏风险"
        return guard
    if guard["dns_mode"] == "local-risk":
        guard["status"] = "blocked"
        guard["block_reason"] = "当前 proxy 为 socks5，本地 DNS 解析有风险；MMC 仅接受 remote DNS proxy"
        return guard
    failed_targets = []
    for label, url in _CLAUDE_PROXY_GUARD_TARGETS:
        probe = _run_proxy_probe(proxy_url, url, no_proxy=no_proxy, force_ipv4=True)
        guard["targets"].append(
            {
                "label": label,
                "url": url,
                "ok": bool(probe.get("ok")),
                "detail": probe.get("detail", ""),
            }
        )
        if not probe.get("ok"):
            failed_targets.append(label)
    if failed_targets:
        guard["status"] = "blocked"
        guard["block_reason"] = f"Claude 关键域名代理检测失败: {', '.join(failed_targets)}"
    return guard


def _enforce_proxy_guard_or_exit(args) -> None:
    guard = _build_local_proxy_guard(args.proxy, args.no_proxy)
    if guard.get("status") == "ok":
        return

    details = []
    if guard.get("block_reason"):
        details.append(str(guard["block_reason"]))
    if guard.get("targets"):
        failed = [
            f"{item.get('label')}: {item.get('detail')}".strip(": ")
            for item in guard.get("targets") or []
            if not item.get("ok")
        ]
        details.extend(failed)
    raise SystemExit("mmc: proxy guard 拒绝启动: " + " | ".join(detail for detail in details if detail))


def _assert_safe_binary_path(path_value: str, *, label: str) -> str:
    normalized = os.path.realpath(str(path_value or "").strip())
    if not normalized:
        raise SystemExit(f"mmc: 缺少 {label} binary")
    if not os.path.isabs(normalized):
        raise SystemExit(f"mmc: {label} binary 不是绝对路径: {normalized}")
    if not os.path.exists(normalized):
        raise SystemExit(f"mmc: {label} binary 不存在: {normalized}")
    lowered = normalized.lower()
    for token in _FORBIDDEN_BINARY_PATH_PARTS:
        if token.lower() in lowered:
            raise SystemExit(f"mmc: {label} binary 命中禁止路径: {normalized}")
    return normalized


def _resolve_safe_binary(command_name: str) -> str:
    search_dirs = []
    seen = set()
    preferred_dirs = (
        str((_real_user_home() / ".local" / "bin").resolve()),
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
        "/usr/sbin",
        "/sbin",
    )
    for item in (*preferred_dirs, *(str(os.environ.get("PATH") or os.defpath).split(os.pathsep))):
        normalized = os.path.realpath(str(item or "").strip())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        lowered = normalized.lower()
        if any(token.lower() in lowered for token in _FORBIDDEN_BINARY_PATH_PARTS):
            continue
        if not os.path.isdir(normalized):
            continue
        search_dirs.append(normalized)
    candidate = shutil.which(command_name, path=os.pathsep.join(search_dirs))
    if not candidate:
        raise SystemExit(f"mmc: 未找到 {command_name} 可执行文件")
    return _assert_safe_binary_path(candidate, label=command_name)


def _resolve_optional_safe_binary(command_name: str) -> str:
    try:
        return _resolve_safe_binary(command_name)
    except SystemExit:
        return ""


def _collect_safe_tool_path_dirs(command_names: tuple[str, ...]) -> list[str]:
    path_dirs = []
    seen = set()
    for command_name in command_names:
        binary_path = _resolve_optional_safe_binary(command_name)
        if not binary_path:
            continue
        parent_dir = os.path.realpath(str(Path(binary_path).parent))
        if not parent_dir or parent_dir in seen:
            continue
        lowered = parent_dir.lower()
        if any(token.lower() in lowered for token in _FORBIDDEN_BINARY_PATH_PARTS):
            continue
        seen.add(parent_dir)
        path_dirs.append(parent_dir)
    return path_dirs


def _ensure_private_tool_bin(session_home: Path, *, claude_bin: str, node_bin: str) -> str:
    private_bin = session_home / ".mmc" / "bin"
    private_bin.mkdir(parents=True, exist_ok=True)
    for link_name, target_path in (
        ("claude", claude_bin),
        ("node", node_bin),
    ):
        dst = private_bin / link_name
        if dst.exists() or dst.is_symlink():
            dst.unlink()
        os.symlink(target_path, dst)
    return str(private_bin)


def _build_process_env(args, session_home: Path) -> dict[str, str]:
    env = {}
    for key in _SAFE_PARENT_ENV_KEYS:
        value = str(os.environ.get(key) or "").strip()
        if value:
            env[key] = value

    claude_bin = _assert_safe_binary_path(args.claude_bin, label="claude") if args.claude_bin else _resolve_safe_binary("claude")
    node_bin = _assert_safe_binary_path(args.node_bin, label="node") if args.node_bin else _resolve_safe_binary("node")
    private_tool_path = _ensure_private_tool_bin(session_home, claude_bin=claude_bin, node_bin=node_bin)
    tmp_root = _tmp_root()
    tmp_root.mkdir(parents=True, exist_ok=True)
    session_tmp = _session_tmp_path(session_home)
    session_tmp.mkdir(parents=True, exist_ok=True)

    env["HOME"] = str(session_home)
    env["XDG_CONFIG_HOME"] = str(session_home / ".config")
    env["XDG_CACHE_HOME"] = str(session_home / ".cache")
    env["XDG_DATA_HOME"] = str(session_home / ".local" / "share")
    env["XDG_STATE_HOME"] = str(session_home / ".local" / "state")
    env["MMC_SESSION_HOME"] = str(session_home)
    env["MMC_CONFIG_HOME"] = str(_config_root())
    env["MMC_REAL_HOME"] = str(_real_user_home())
    env["TMPDIR"] = str(session_tmp)
    env["PATH"] = os.pathsep.join(
        (
            private_tool_path,
            *_collect_safe_tool_path_dirs(_HOOK_DEPENDENCY_TOOL_NAMES),
            *_SYSTEM_FALLBACK_PATH_DIRS,
        )
    )

    if args.proxy:
        _apply_proxy_env(env, args.proxy, args.no_proxy)
    if args.lang:
        env["LANG"] = args.lang
    if args.lc_all:
        env["LC_ALL"] = args.lc_all
    if args.lc_ctype:
        env["LC_CTYPE"] = args.lc_ctype
    if args.lc_messages:
        env["LC_MESSAGES"] = args.lc_messages
    if args.tz:
        env["TZ"] = args.tz
    if args.force_ipv4:
        raise SystemExit("mmc: OAuth/MMC 路线已禁用 force_ipv4 注入；请改系统层网络策略，不再透传 NODE_OPTIONS")

    for item in args.set_env or []:
        key, sep, raw_value = str(item or "").partition("=")
        key = key.strip()
        if not sep or key not in _ALLOWED_LAUNCH_ENV_KEYS:
            continue
        value = raw_value.strip()
        if value:
            env[key] = value
        else:
            env.pop(key, None)

    return env


def _resolve_claude_binary(env: dict[str, str]) -> str:
    path_value = str(env.get("PATH") or os.defpath)
    binary = shutil.which("claude", path=path_value)
    if binary:
        return _assert_safe_binary_path(binary, label="claude")
    raise SystemExit("mmc: 未找到 claude 可执行文件")


def _build_claude_cmd(args, env: dict[str, str]) -> list[str]:
    cmd = [_resolve_claude_binary(env)]
    seen_dirs = set()
    for path in args.allow_dir or []:
        normalized = os.path.realpath(str(path or "").strip())
        if not normalized or normalized in seen_dirs:
            continue
        seen_dirs.add(normalized)
        cmd.extend(["--add-dir", normalized])
    if args.bypass:
        cmd.append("--dangerously-skip-permissions")
    return cmd


def _add_common_launch_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace", default="", help="workspace 根目录；默认当前 cwd")
    parser.add_argument("--proxy", default="", help="显式 proxy")
    parser.add_argument("--no-proxy", default="", help="显式 no_proxy")
    parser.add_argument("--lang", default="", help="LANG")
    parser.add_argument("--lc-all", default="", help="LC_ALL")
    parser.add_argument("--lc-ctype", default="", help="LC_CTYPE")
    parser.add_argument("--lc-messages", default="", help="LC_MESSAGES")
    parser.add_argument("--tz", default="", help="TZ")
    parser.add_argument("--allow-dir", action="append", default=[], help="透传给 Claude 的 --add-dir")
    parser.add_argument("--bypass", action="store_true", help="启用 --dangerously-skip-permissions")
    parser.add_argument("--force-ipv4", action="store_true", help="保留占位；OAuth/MMC 路线默认拒绝")
    parser.add_argument("--set-env", action="append", default=[], help="仅允许 allowlist launch env，格式 KEY=VALUE")
    parser.add_argument("--claude-bin", default="", help="显式 Claude binary 绝对路径")
    parser.add_argument("--node-bin", default="", help="显式 Node binary 绝对路径")


def _run_claude(args, *, explicit_session_id: str = "") -> int:
    workspace = os.path.realpath(args.workspace or os.getcwd())
    if not os.path.isdir(workspace):
        print(f"mmc: workspace 不存在或不是目录: {workspace}", file=sys.stderr)
        return 1
    _enforce_proxy_guard_or_exit(args)
    _bootstrap_account_state()

    session_home, _active_before, active_after = _reserve_session_home()
    if session_home is None:
        print(f"mmc: 当前将达到 {active_after} 个并发 session，已超过安全上限 {_MAX_LIVE_SESSIONS}", file=sys.stderr)
        return 1
    (session_home / ".claude").mkdir(parents=True, exist_ok=True)
    _prepare_session_tree(session_home, workspace)
    _link_keychains_only(session_home)

    session_state = _build_session_state(
        workspace,
        explicit_session_id=explicit_session_id,
        bypass=bool(args.bypass),
    )
    _write_json(session_home / ".claude.json", session_state)
    _write_json(session_home / ".claude" / "settings.json", _build_session_settings())

    env = _build_process_env(args, session_home)
    cmd = _build_claude_cmd(args, env)

    print(f"mmc: launching Claude in isolated HOME {session_home}", flush=True)
    exit_code = 130
    child = None
    handled_signals = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
    previous_handlers = {}

    def _forward_signal(signum, _frame):
        nonlocal child
        if child is not None and child.poll() is None:
            try:
                child.send_signal(signum)
            except Exception:
                pass

    try:
        for signum in handled_signals:
            previous_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, _forward_signal)
        child = subprocess.Popen(cmd, env=env, cwd=workspace)
        bind_claude_session_process(
            cwd=workspace,
            pid=os.getpid(),
            child_pid=child.pid,
            launch_nonce=session_home.name,
        )
        exit_code = int(child.wait() or 0)
    except KeyboardInterrupt:
        exit_code = 130
    finally:
        for signum, handler in previous_handlers.items():
            try:
                signal.signal(signum, handler)
            except Exception:
                pass
        _finalize_session(session_home, exit_code=exit_code)
    return exit_code


def _run_resume(args) -> int:
    session_id, error = resolve_session_ref(args.session_ref)
    if not session_id:
        print(f"mmc: {error or '找不到 session'}", file=sys.stderr)
        return 1
    sessions = list_indexed_sessions()
    matched = next((item for item in sessions if str(item.get("session_id") or "").strip() == session_id), None)
    if matched and not args.workspace:
        args.workspace = str(matched.get("project_path") or matched.get("cwd") or "").strip()
    return _run_claude(args, explicit_session_id=session_id)


def _handle_session_ls() -> int:
    sessions = list_indexed_sessions()
    if not sessions:
        print("暂无 MMC session")
        return 0
    for index, item in enumerate(sessions, 1):
        session_id = str(item.get("session_id") or "").strip() or "-"
        project_path = str(item.get("project_path") or item.get("cwd") or "").strip() or "-"
        last_active = str(item.get("last_active_at") or item.get("started_at") or "").strip() or "-"
        print(f"{index}. {session_id} | {project_path} | {last_active}")
    return 0


def _handle_import_auth(source_home: str) -> int:
    _import_legacy_auth_state(source_home)
    print("mmc: legacy OAuth state 已导入到 MMC account home")
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="mmc", description="MMC - isolated OAuth Claude launcher")
    subparsers = parser.add_subparsers(dest="subcommand")

    run_parser = subparsers.add_parser("run", help="启动隔离的 OAuth Claude")
    _add_common_launch_args(run_parser)

    resume_parser = subparsers.add_parser("resume", help="恢复 MMC session")
    resume_parser.add_argument("session_ref", help="session id / 前缀 / 序号")
    _add_common_launch_args(resume_parser)

    import_parser = subparsers.add_parser("import-auth", help="显式导入一次旧 OAuth state 到 MMC")
    import_parser.add_argument("--from-home", required=True, help="旧 home_dir 路径；仅手动导入，不由 MMS 自动调用")

    session_parser = subparsers.add_parser("session", help="查看 MMC session")
    session_subparsers = session_parser.add_subparsers(dest="session_subcommand")
    session_subparsers.add_parser("ls", help="列出 session")

    args = parser.parse_args(argv)

    if args.subcommand == "run":
        sys.exit(_run_claude(args))
    if args.subcommand == "resume":
        sys.exit(_run_resume(args))
    if args.subcommand == "import-auth":
        sys.exit(_handle_import_auth(args.from_home))
    if args.subcommand == "session" and args.session_subcommand == "ls":
        sys.exit(_handle_session_ls())

    parser.print_help()


if __name__ == "__main__":
    main()
