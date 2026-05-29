"""Claude UI state sanitization and merge helpers for MMS launchers.

Imports from ``mms_launchers`` stay lazy so compatibility wrappers and existing
monkeypatch-based tests continue to observe the same private helper names.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import os


def copy_allowed_scalar_fields(payload, allowed_keys):
    payload = payload if isinstance(payload, dict) else {}
    copied = {}
    for key in allowed_keys:
        value = payload.get(key)
        if isinstance(value, (str, int, float, bool)):
            copied[key] = copy.deepcopy(value)
    return copied


def copy_allowed_scalar_dict_fields(payload, allowed_keys):
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


def sanitize_claude_ui_state_seed_payload(payload):
    import mms_launchers as _launchers

    payload = payload if isinstance(payload, dict) else {}
    seed = _launchers._copy_allowed_scalar_fields(payload, _launchers._CLAUDE_OAUTH_UI_STATE_SEED_KEYS)
    seed.update(
        _launchers._copy_allowed_scalar_dict_fields(
            payload,
            _launchers._CLAUDE_OAUTH_STATE_SCALAR_DICT_ALLOWLIST,
        )
    )
    mcp_servers = payload.get("mcpServers")
    if isinstance(mcp_servers, dict):
        seed["mcpServers"] = copy.deepcopy(mcp_servers)
    return seed


def merge_scalar_dict_entries(existing_payload, incoming_payload, *, prefer_max_numeric=False):
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


def merge_claude_ui_state_seed(target_payload, seed_payload):
    import mms_launchers as _launchers

    target_payload = dict(target_payload) if isinstance(target_payload, dict) else {}
    seed_payload = seed_payload if isinstance(seed_payload, dict) else {}
    for key, value in seed_payload.items():
        if key == "numStartups" and isinstance(value, (int, float)) and not isinstance(value, bool):
            existing_value = target_payload.get(key)
            if isinstance(existing_value, (int, float)) and not isinstance(existing_value, bool):
                target_payload[key] = max(existing_value, value)
            else:
                target_payload[key] = value
            continue
        if key in _launchers._CLAUDE_OAUTH_STATE_SCALAR_DICT_ALLOWLIST and isinstance(value, dict):
            target_payload[key] = _launchers._merge_scalar_dict_entries(
                target_payload.get(key),
                value,
                prefer_max_numeric=(key == "tipsHistory"),
            )
            continue
        if key == "mcpServers" and isinstance(value, dict):
            merged_servers = copy.deepcopy(value)
            existing_servers = target_payload.get(key)
            if isinstance(existing_servers, dict):
                merged_servers.update(copy.deepcopy(existing_servers))
            target_payload[key] = merged_servers
            continue
        target_payload.setdefault(key, copy.deepcopy(value))
    return target_payload


def merge_claude_gateway_ui_state_payload(existing_payload, incoming_payload):
    import mms_launchers as _launchers

    existing = _launchers._sanitize_claude_ui_state_seed_payload(existing_payload)
    incoming = _launchers._sanitize_claude_ui_state_seed_payload(incoming_payload)
    merged = copy.deepcopy(existing)

    for key in _launchers._CLAUDE_OAUTH_UI_STATE_SEED_KEYS:
        incoming_value = incoming.get(key)
        existing_value = existing.get(key)
        if key == "firstStartTime":
            chosen = existing_value or incoming_value
            if isinstance(chosen, (str, int, float, bool)):
                merged[key] = copy.deepcopy(chosen)
            continue
        if key == "numStartups":
            numeric_values = [
                value for value in (existing_value, incoming_value)
                if isinstance(value, (int, float)) and not isinstance(value, bool)
            ]
            if numeric_values:
                merged[key] = max(numeric_values)
            continue
        if key == "hasCompletedOnboarding":
            if existing_value or incoming_value:
                merged[key] = bool(existing_value or incoming_value)
            continue
        if isinstance(incoming_value, (str, int, float, bool)):
            merged[key] = copy.deepcopy(incoming_value)

    for key in _launchers._CLAUDE_OAUTH_STATE_SCALAR_DICT_ALLOWLIST:
        merged_dict = _launchers._merge_scalar_dict_entries(
            existing.get(key),
            incoming.get(key),
            prefer_max_numeric=(key == "tipsHistory"),
        )
        if merged_dict:
            merged[key] = merged_dict

    return _launchers._strip_claude_state_execution_surfaces(merged)


def strip_claude_state_execution_surfaces(payload):
    payload = dict(payload) if isinstance(payload, dict) else {}
    payload.pop("mcpServers", None)
    projects = payload.get("projects")
    if isinstance(projects, dict):
        stripped_projects = {}
        for project_path, entry in projects.items():
            if not isinstance(entry, dict):
                continue
            next_entry = dict(entry)
            next_entry.pop("mcpServers", None)
            next_entry["enabledMcpjsonServers"] = []
            next_entry["disabledMcpjsonServers"] = []
            stripped_projects[project_path] = next_entry
        payload["projects"] = stripped_projects
    return payload


def sanitize_claude_project_state_entry(entry):
    import mms_launchers as _launchers

    entry = entry if isinstance(entry, dict) else {}
    cleaned = _launchers._copy_allowed_scalar_fields(
        entry,
        (
            "hasTrustDialogAccepted",
            "hasCompletedProjectOnboarding",
            "hasClaudeMdExternalIncludesApproved",
            "hasClaudeMdExternalIncludesWarningShown",
            "projectOnboardingSeenCount",
            "lastGracefulShutdown",
        ),
    )
    for key in ("allowedTools", "mcpContextUris", "enabledMcpjsonServers", "disabledMcpjsonServers"):
        value = entry.get(key)
        if isinstance(value, list):
            cleaned[key] = copy.deepcopy(value)
    mcp_servers = entry.get("mcpServers")
    if isinstance(mcp_servers, dict):
        cleaned["mcpServers"] = copy.deepcopy(mcp_servers)
    return cleaned


def sanitize_claude_project_state_map(projects_data):
    import mms_launchers as _launchers

    projects = {}
    if not isinstance(projects_data, dict):
        return projects
    for project_path, entry in projects_data.items():
        normalized_path = os.path.realpath(str(project_path or "").strip())
        if not normalized_path:
            continue
        cleaned_entry = _launchers._sanitize_claude_project_state_entry(entry)
        if cleaned_entry:
            projects[normalized_path] = cleaned_entry
    return projects


def load_real_claude_ui_state_seed():
    import json as _json
    import mms_launchers as _launchers

    real_json = _launchers._real_user_path(".claude.json")
    if not os.path.exists(real_json):
        return {}
    try:
        with open(real_json, encoding="utf-8") as f:
            loaded = _json.load(f)
        if not isinstance(loaded, dict):
            return {}
        return _launchers._sanitize_claude_ui_state_seed_payload(loaded)
    except Exception:
        return {}


def load_real_claude_project_state(project_path):
    import json as _json
    import mms_launchers as _launchers

    real_json = _launchers._real_user_path(".claude.json")
    normalized_project = os.path.realpath(str(project_path or "").strip())
    if not normalized_project or not os.path.exists(real_json):
        return None
    try:
        with open(real_json, encoding="utf-8") as f:
            loaded = _json.load(f)
        if not isinstance(loaded, dict):
            return None
        projects = loaded.get("projects")
        if not isinstance(projects, dict):
            return None
        project_state = projects.get(normalized_project)
        if not isinstance(project_state, dict):
            return None
        cleaned = _launchers._sanitize_claude_project_state_entry(project_state)
        return cleaned or None
    except Exception:
        return None


def strip_claude_restore_state(data, *, strip_sensitive_auth=False):
    import mms_launchers as _launchers

    payload = dict(data) if isinstance(data, dict) else {}
    payload.pop("projects", None)
    payload.pop("lastSessionId", None)
    payload.pop("lastCost", None)
    if strip_sensitive_auth:
        for key in _launchers._CLAUDE_GATEWAY_SENSITIVE_STATE_KEYS:
            payload.pop(key, None)
    return payload


def sanitize_oauth_claude_state_payload(data):
    import mms_launchers as _launchers

    raw_data = data if isinstance(data, dict) else {}
    payload = _launchers._strip_claude_restore_state(raw_data)
    cleaned = _launchers._copy_allowed_scalar_fields(
        payload,
        _launchers._CLAUDE_OAUTH_STATE_TOP_LEVEL_ALLOWLIST,
    )
    cleaned.update(
        _launchers._copy_allowed_scalar_dict_fields(
            raw_data,
            _launchers._CLAUDE_OAUTH_STATE_SCALAR_DICT_ALLOWLIST,
        )
    )

    oauth_account = _launchers._copy_allowed_scalar_fields(
        payload.get("oauthAccount"),
        _launchers._CLAUDE_OAUTH_ACCOUNT_ALLOWLIST,
    )
    if oauth_account:
        cleaned["oauthAccount"] = oauth_account

    claude_ai_oauth = _launchers._copy_allowed_scalar_fields(
        payload.get("claudeAiOauth"),
        _launchers._CLAUDE_AI_OAUTH_ALLOWLIST,
    )
    if claude_ai_oauth:
        cleaned["claudeAiOauth"] = claude_ai_oauth

    projects = _launchers._sanitize_claude_project_state_map(raw_data.get("projects"))
    if projects:
        cleaned["projects"] = projects

    return cleaned


def sanitize_codex_claude_state_payload(data):
    import mms_launchers as _launchers

    payload = _launchers._strip_claude_restore_state(data, strip_sensitive_auth=True)
    return _launchers._copy_allowed_scalar_fields(
        payload,
        _launchers._CLAUDE_CODEX_STATE_TOP_LEVEL_ALLOWLIST,
    )


def ensure_claude_project_trust(
    data,
    project_path,
    project_state=None,
    *,
    allow_execution_surfaces=True,
    disabled_session_surfaces=None,
):
    import mms_launchers as _launchers

    payload = dict(data) if isinstance(data, dict) else {}
    project_path = os.path.realpath(str(project_path or "").strip())
    projects = payload.get("projects")
    if not isinstance(projects, dict):
        projects = {}

    entry = {}
    if isinstance(project_state, dict):
        entry.update(project_state)
    elif isinstance(projects.get(project_path), dict):
        entry.update(projects[project_path])

    entry.setdefault("allowedTools", [])
    entry.setdefault("mcpContextUris", [])
    entry.setdefault("mcpServers", {})
    entry.setdefault("enabledMcpjsonServers", [])
    entry.setdefault("disabledMcpjsonServers", [])
    if not allow_execution_surfaces:
        entry["mcpServers"] = {}
        entry["enabledMcpjsonServers"] = []
        entry["disabledMcpjsonServers"] = []
    else:
        entry["mcpServers"] = _launchers._filter_mcp_servers_by_disabled(
            entry.get("mcpServers"),
            disabled_session_surfaces,
        )
        disabled_mcp = _launchers._normalize_session_surface_disabled(disabled_session_surfaces).get("mcp", set())
        if disabled_mcp:
            entry["enabledMcpjsonServers"] = [
                name for name in entry.get("enabledMcpjsonServers", [])
                if str(name or "").strip() not in disabled_mcp
            ]
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

    projects[project_path] = entry
    payload["projects"] = projects
    return payload


def copy_claude_state_json(src, dst, *, mode="restore"):
    import json as _json
    import mms_launchers as _launchers

    payload = {}
    if os.path.exists(src):
        try:
            with open(src, encoding="utf-8") as f:
                loaded = _json.load(f)
            if isinstance(loaded, dict):
                payload = loaded
        except Exception:
            payload = {}
    if mode == "oauth":
        payload = _launchers._sanitize_oauth_claude_state_payload(payload)
    else:
        payload = _launchers._strip_claude_restore_state(payload)
    with _launchers.locked_state_file(dst):
        _launchers.atomic_write_json(dst, payload, mode=0o600)


def parse_iso8601_utc(value):
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


def merge_oauth_token_state(existing_payload, incoming_payload):
    import mms_launchers as _launchers

    existing_payload = existing_payload if isinstance(existing_payload, dict) else {}
    incoming_payload = incoming_payload if isinstance(incoming_payload, dict) else {}
    existing_expiry = _launchers._parse_iso8601_utc(existing_payload.get("expiresAt"))
    incoming_expiry = _launchers._parse_iso8601_utc(incoming_payload.get("expiresAt"))
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


def merge_oauth_claude_state_payload(existing_data, incoming_data):
    import mms_launchers as _launchers

    existing = _launchers._sanitize_oauth_claude_state_payload(existing_data)
    incoming = _launchers._sanitize_oauth_claude_state_payload(incoming_data)
    merged = copy.deepcopy(existing)

    for key in _launchers._CLAUDE_OAUTH_STATE_TOP_LEVEL_ALLOWLIST:
        incoming_value = incoming.get(key)
        existing_value = existing.get(key)
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
        if key in {"bypassPermissionsModeAccepted", "alwaysThinkingEnabled", "hasCompletedOnboarding"}:
            if existing_value or incoming_value:
                merged[key] = bool(existing_value or incoming_value)
            elif key in merged:
                merged[key] = bool(merged.get(key))
            continue
        if isinstance(incoming_value, (str, int, float, bool)):
            merged[key] = copy.deepcopy(incoming_value)

    for key in _launchers._CLAUDE_OAUTH_STATE_SCALAR_DICT_ALLOWLIST:
        merged_dict = _launchers._merge_scalar_dict_entries(
            existing.get(key),
            incoming.get(key),
            prefer_max_numeric=(key == "tipsHistory"),
        )
        if merged_dict:
            merged[key] = merged_dict

    merged_account = copy.deepcopy(existing.get("oauthAccount") or {})
    if isinstance(incoming.get("oauthAccount"), dict):
        merged_account.update(copy.deepcopy(incoming["oauthAccount"]))
    if merged_account:
        merged["oauthAccount"] = merged_account

    merged_token = _launchers._merge_oauth_token_state(
        existing.get("claudeAiOauth"),
        incoming.get("claudeAiOauth"),
    )
    if merged_token:
        merged["claudeAiOauth"] = merged_token

    merged_projects = copy.deepcopy(existing.get("projects") or {})
    for project_path, entry in (incoming.get("projects") or {}).items():
        current_entry = merged_projects.get(project_path)
        next_entry = dict(current_entry) if isinstance(current_entry, dict) else {}
        if isinstance(entry, dict):
            next_entry.update(copy.deepcopy(entry))
        if next_entry:
            merged_projects[project_path] = next_entry
    if merged_projects:
        merged["projects"] = merged_projects

    return merged
