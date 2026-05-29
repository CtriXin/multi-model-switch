"""Claude session settings materialization for MMS launchers.

The implementation resolves helpers through ``mms_launchers`` at call time so
existing tests and callers that monkeypatch launcher-private names keep working.
"""

from __future__ import annotations

import copy
import json
import os


def load_claude_settings_template(filename):
    template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    if not os.path.exists(template_path):
        return {}
    try:
        with open(template_path, encoding="utf-8") as f:
            loaded = json.load(f)
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def load_mms_claude_settings_template():
    import mms_launchers as _launchers

    return _launchers._load_claude_settings_template("claude-settings.template.json")


def load_global_claude_settings_template():
    import mms_launchers as _launchers

    return _launchers._load_claude_settings_template("claude-settings.global-template.json")


def global_claude_snapshot_path():
    import mms_launchers as _launchers

    state_root = os.environ.get("MMS_HOME") or os.path.join(_launchers._real_user_path(".mms"), "state")
    return os.path.join(state_root, "claude-global-managed-snapshot.json")


def normalize_hook_command(command):
    return " ".join(str(command or "").strip().split())


def extract_managed_claude_snapshot(settings_data, template_settings):
    import mms_launchers as _launchers

    settings_data = settings_data if isinstance(settings_data, dict) else {}
    template_settings = template_settings if isinstance(template_settings, dict) else {}
    snapshot = {}

    managed_scalar_keys = set(
        [
            "includeCoAuthoredBy",
            "skipDangerousModePermissionPrompt",
            "model",
            "promptSuggestionEnabled",
        ]
    )
    if isinstance(template_settings.get("statusLine"), dict):
        managed_scalar_keys.add("statusLine")
    if isinstance(template_settings.get("attribution"), dict):
        managed_scalar_keys.add("attribution")
    if isinstance(template_settings.get("permissions"), dict):
        managed_scalar_keys.add("permissions")

    for key in managed_scalar_keys:
        value = settings_data.get(key)
        if isinstance(value, dict):
            snapshot[key] = dict(value)
        elif isinstance(value, list):
            snapshot[key] = list(value)
        else:
            snapshot[key] = value

    current_hooks = settings_data.get("hooks") or {}
    template_hooks = template_settings.get("hooks") or {}
    snapshot_hooks = {}

    for event_name, current_groups in current_hooks.items():
        event_snapshot = []
        known_matchers = set()
        template_groups = template_hooks.get(event_name) or []
        for template_group in template_groups:
            if not isinstance(template_group, dict):
                continue
            known_matchers.add(str(template_group.get("matcher") or "").strip())
        for group in current_groups:
            if not isinstance(group, dict):
                continue
            matcher = str(group.get("matcher") or "").strip()
            commands = []
            for hook in group.get("hooks") or []:
                if not isinstance(hook, dict):
                    continue
                command = _launchers._normalize_hook_command(hook.get("command"))
                if command:
                    commands.append(command)
            if not commands:
                continue
            event_snapshot.append({"matcher": matcher, "commands": sorted(set(commands))})
            known_matchers.add(matcher)
        if event_snapshot:
            snapshot_hooks[event_name] = sorted(
                event_snapshot,
                key=lambda item: (item.get("matcher") or "", ",".join(item.get("commands") or [])),
            )
    snapshot["hooks"] = snapshot_hooks
    return snapshot


def snapshot_to_template(snapshot_data, seed_template):
    import mms_launchers as _launchers

    snapshot_data = snapshot_data if isinstance(snapshot_data, dict) else {}
    seed_template = seed_template if isinstance(seed_template, dict) else {}
    template = {}

    for key in [
        "includeCoAuthoredBy",
        "skipDangerousModePermissionPrompt",
        "model",
        "promptSuggestionEnabled",
        "statusLine",
        "attribution",
        "permissions",
    ]:
        if key in snapshot_data:
            value = snapshot_data.get(key)
        else:
            value = seed_template.get(key)
        if isinstance(value, dict):
            template[key] = dict(value)
        elif isinstance(value, list):
            template[key] = list(value)
        elif value is not None:
            template[key] = value

    hooks = {}
    snapshot_hooks = snapshot_data.get("hooks") or {}
    seed_hooks = seed_template.get("hooks") or {}
    all_events = sorted(set(snapshot_hooks.keys()) | set(seed_hooks.keys()))
    for event_name in all_events:
        groups = []
        seen = set()
        for source_groups in [seed_hooks.get(event_name) or [], snapshot_hooks.get(event_name) or []]:
            for group in source_groups:
                if not isinstance(group, dict):
                    continue
                matcher = str(group.get("matcher") or "").strip()
                commands = []
                if "commands" in group:
                    commands = [
                        _launchers._normalize_hook_command(command)
                        for command in group.get("commands") or []
                        if _launchers._normalize_hook_command(command)
                    ]
                else:
                    for hook in group.get("hooks") or []:
                        if not isinstance(hook, dict):
                            continue
                        command = _launchers._normalize_hook_command(hook.get("command"))
                        if command:
                            commands.append(command)
                commands = sorted(set(commands))
                if not commands:
                    continue
                group_key = (matcher, tuple(commands))
                if group_key in seen:
                    continue
                seen.add(group_key)
                groups.append(
                    {
                        "matcher": matcher,
                        "hooks": [
                            {"type": "command", "command": command} for command in commands
                        ],
                    }
                )
        if groups:
            hooks[event_name] = groups
    if hooks:
        template["hooks"] = hooks
    return template


def merge_snapshot_with_current(snapshot_data, current_settings):
    import mms_launchers as _launchers

    snapshot_data = snapshot_data if isinstance(snapshot_data, dict) else {}
    current_snapshot = _launchers._extract_managed_claude_snapshot(current_settings, snapshot_data)
    merged = dict(snapshot_data)

    for key, value in current_snapshot.items():
        if key == "hooks":
            continue
        if isinstance(value, dict):
            merged[key] = dict(value)
        elif isinstance(value, list):
            merged[key] = list(value)
        elif value is not None:
            merged[key] = value

    merged_hooks = {}
    known_events = set((snapshot_data.get("hooks") or {}).keys()) | set((current_snapshot.get("hooks") or {}).keys())
    for event_name in known_events:
        groups = []
        seen = set()
        for source_groups in [snapshot_data.get("hooks", {}).get(event_name) or [], current_snapshot.get("hooks", {}).get(event_name) or []]:
            for group in source_groups:
                if not isinstance(group, dict):
                    continue
                matcher = str(group.get("matcher") or "").strip()
                commands = sorted(
                    set(
                        _launchers._normalize_hook_command(command)
                        for command in group.get("commands") or []
                        if _launchers._normalize_hook_command(command)
                    )
                )
                if not commands:
                    continue
                group_key = (matcher, tuple(commands))
                if group_key in seen:
                    continue
                seen.add(group_key)
                groups.append({"matcher": matcher, "commands": commands})
        if groups:
            merged_hooks[event_name] = groups
    merged["hooks"] = merged_hooks
    return merged


def prune_session_only_snapshot_entries(snapshot_data):
    import mms_launchers as _launchers

    snapshot_data = snapshot_data if isinstance(snapshot_data, dict) else {}
    hooks = snapshot_data.get("hooks") or {}
    local_hooks_dir = _launchers._LOCAL_HOOKS_DIR
    session_only_commands = {
        _launchers._normalize_hook_command(_launchers._CLAUDE_FEISHU_WEBFETCH_GUARD_HOOK),
        _launchers._normalize_hook_command(f"bash {_launchers._CLAUDE_HIVE_COMPACT_HOOK}"),
        _launchers._normalize_hook_command(_launchers._CLAUDE_HIVE_COMPACT_HOOK),
        _launchers._normalize_hook_command(_launchers._CLAUDE_BRAINKEEPER_SESSION_START_HOOK),
        _launchers._normalize_hook_command(_launchers._CLAUDE_BRAINKEEPER_SESSION_END_HOOK),
        _launchers._normalize_hook_command(_launchers._CLAUDE_BRAINKEEPER_TOKEN_MONITOR_HOOK),
        _launchers._normalize_hook_command(_launchers._CLAUDE_MINDKEEPER_SESSION_START_HOOK),
        _launchers._normalize_hook_command(_launchers._CLAUDE_MINDKEEPER_SESSION_END_HOOK),
        _launchers._normalize_hook_command(_launchers._CLAUDE_MINDKEEPER_TOKEN_MONITOR_HOOK),
        _launchers._normalize_hook_command(_launchers._CLAUDE_CODEGRAPH_AUTO_INDEX_HOOK),
        _launchers._normalize_hook_command(_launchers._CLAUDE_MMS_RESUME_HINT_HOOK),
        _launchers._normalize_hook_command(_launchers._XMEM_SESSION_START_HOOK),
        _launchers._normalize_hook_command(_launchers._XMEM_SESSION_END_HOOK),
        _launchers._normalize_hook_command(_launchers._XMEM_GATEWAY_HOOK),
        _launchers._normalize_hook_command(_launchers._NSR_CLAUDE_HOOK),
        _launchers._normalize_hook_command(_launchers._NSR_CODEX_HOOK),
        _launchers._normalize_hook_command(f"python3 {_launchers._NSR_BUILTIN_HOOK}"),
        _launchers._normalize_hook_command(_launchers._NSR_BUILTIN_HOOK),
        _launchers._normalize_hook_command(os.path.join(local_hooks_dir, "claude-feishu-webfetch-guard.sh")),
        _launchers._normalize_hook_command(f"bash {os.path.join(local_hooks_dir, 'hive-compact-hook.sh')}"),
        _launchers._normalize_hook_command(os.path.join(local_hooks_dir, "hive-compact-hook.sh")),
        _launchers._normalize_hook_command(os.path.join(local_hooks_dir, "brainkeeper-session-start-hook.sh")),
        _launchers._normalize_hook_command(os.path.join(local_hooks_dir, "brainkeeper-session-end-hook.sh")),
        _launchers._normalize_hook_command(os.path.join(local_hooks_dir, "brainkeeper-token-monitor-hook.sh")),
        _launchers._normalize_hook_command(os.path.join(local_hooks_dir, "mindkeeper-session-start-hook.sh")),
        _launchers._normalize_hook_command(os.path.join(local_hooks_dir, "mindkeeper-session-end-hook.sh")),
        _launchers._normalize_hook_command(os.path.join(local_hooks_dir, "mindkeeper-token-monitor-hook.sh")),
        _launchers._normalize_hook_command(os.path.join(local_hooks_dir, "claude-codegraph-auto-index.sh")),
        _launchers._normalize_hook_command(os.path.join(local_hooks_dir, "mms-resume-hint.sh")),
        _launchers._normalize_hook_command(os.path.join(local_hooks_dir, "xmem-session-start-hook.sh")),
        _launchers._normalize_hook_command(os.path.join(local_hooks_dir, "xmem-session-end-hook.sh")),
        _launchers._normalize_hook_command(os.path.join(local_hooks_dir, "xmem-gateway-hook.sh")),
    }
    pruned_hooks = {}
    for event_name, groups in hooks.items():
        kept_groups = []
        for group in groups or []:
            if not isinstance(group, dict):
                continue
            commands = [
                command
                for command in group.get("commands") or []
                if _launchers._normalize_hook_command(command) not in session_only_commands
            ]
            if not commands:
                continue
            kept_groups.append({"matcher": str(group.get("matcher") or "").strip(), "commands": commands})
        if kept_groups:
            pruned_hooks[event_name] = kept_groups
    snapshot_data["hooks"] = pruned_hooks
    return snapshot_data


def sanitize_global_snapshot(snapshot_data):
    snapshot_data = snapshot_data if isinstance(snapshot_data, dict) else {}
    snapshot_data.pop("env", None)
    snapshot_data = prune_session_only_snapshot_entries(snapshot_data)
    mcp_servers = snapshot_data.get("mcpServers")
    if isinstance(mcp_servers, dict):
        pruned_servers = {
            name: copy.deepcopy(spec)
            for name, spec in mcp_servers.items()
            if name != "hive"
        }
        if pruned_servers:
            snapshot_data["mcpServers"] = pruned_servers
        else:
            snapshot_data.pop("mcpServers", None)
    return snapshot_data


def managed_snapshot_differs(previous_snapshot, current_settings, seed_template):
    import mms_launchers as _launchers

    previous_snapshot = _launchers._sanitize_global_snapshot(previous_snapshot)
    current_snapshot = _launchers._sanitize_global_snapshot(
        _launchers._extract_managed_claude_snapshot(current_settings, seed_template)
    )
    return previous_snapshot != current_snapshot


def managed_snapshot_template(previous_snapshot, seed_template, current_settings):
    import mms_launchers as _launchers

    merged_snapshot = _launchers._merge_snapshot_with_current(previous_snapshot, current_settings)
    sanitized_snapshot = _launchers._sanitize_global_snapshot(merged_snapshot)
    return sanitized_snapshot, _launchers._snapshot_to_template(sanitized_snapshot, seed_template)


def merge_claude_settings(base_settings, template_settings):
    import mms_launchers as _launchers

    settings_data = dict(base_settings) if isinstance(base_settings, dict) else {}
    template_settings = template_settings if isinstance(template_settings, dict) else {}

    hooks = _launchers._merge_claude_hooks(settings_data.get("hooks"), template_settings.get("hooks"))
    if hooks:
        settings_data["hooks"] = hooks

    if isinstance(template_settings.get("statusLine"), dict):
        settings_data["statusLine"] = _launchers._merge_claude_statusline(settings_data.get("statusLine"))
    if isinstance(template_settings.get("permissions"), dict):
        settings_data["permissions"] = _launchers._merge_claude_permissions(settings_data.get("permissions"))

    settings_data.setdefault(
        "includeCoAuthoredBy",
        template_settings.get("includeCoAuthoredBy", False),
    )
    settings_data.setdefault(
        "attribution",
        template_settings.get("attribution") if isinstance(template_settings.get("attribution"), dict) else {"commit": "", "pr": ""},
    )
    settings_data.setdefault(
        "promptSuggestionEnabled",
        template_settings.get("promptSuggestionEnabled", False),
    )
    if template_settings.get("model") and not settings_data.get("model"):
        settings_data["model"] = template_settings.get("model")
    if "skipDangerousModePermissionPrompt" in template_settings:
        settings_data["skipDangerousModePermissionPrompt"] = bool(
            template_settings.get("skipDangerousModePermissionPrompt")
        )
    return settings_data


def merge_claude_hook_groups(existing_groups, template_groups):
    import mms_launchers as _launchers

    groups = []
    if isinstance(existing_groups, list):
        groups.extend(existing_groups)
    if not isinstance(template_groups, list):
        return groups
    for template_group in template_groups:
        if not isinstance(template_group, dict):
            continue
        matcher = str(template_group.get("matcher") or "").strip()
        template_hooks = template_group.get("hooks")
        if not isinstance(template_hooks, list):
            continue
        target_group = None
        for group in groups:
            if not isinstance(group, dict):
                continue
            if str(group.get("matcher") or "").strip() == matcher:
                target_group = group
                break
        if target_group is None:
            target_group = {"matcher": matcher, "hooks": []}
            groups.append(target_group)
        hook_items = target_group.get("hooks")
        if not isinstance(hook_items, list):
            hook_items = []
            target_group["hooks"] = hook_items
        for hook in template_hooks:
            if not isinstance(hook, dict):
                continue
            command = str(hook.get("command") or "").strip()
            if not command or _launchers._hook_command_exists(hook_items, command):
                continue
            hook_items.append(dict(hook))
    return groups


def merge_claude_hooks(existing_hooks, template_hooks):
    import mms_launchers as _launchers

    merged = dict(existing_hooks) if isinstance(existing_hooks, dict) else {}
    if not isinstance(template_hooks, dict):
        return merged
    for event_name, template_groups in template_hooks.items():
        merged[event_name] = _launchers._merge_claude_hook_groups(
            merged.get(event_name),
            template_groups,
        )
    return merged


def merge_claude_statusline(existing):
    import mms_launchers as _launchers

    merged = dict(existing) if isinstance(existing, dict) else {}
    merged.update(_launchers._CLAUDE_STATUSLINE_CONFIG)
    return merged


def merge_claude_permissions(existing):
    import mms_launchers as _launchers

    base = dict(existing) if isinstance(existing, dict) else {}
    allow_existing = base.get("allow")
    deny_existing = base.get("deny")
    allow = []
    seen_allow = set()
    for item in list(allow_existing or []) + list(_launchers._CLAUDE_DEFAULT_PERMISSION_ALLOW):
        value = str(item or "").strip()
        if not value or value in seen_allow:
            continue
        seen_allow.add(value)
        allow.append(value)
    deny = []
    seen_deny = set()
    for item in list(deny_existing or []) + list(_launchers._CLAUDE_DEFAULT_PERMISSION_DENY):
        value = str(item or "").strip()
        if not value or value in seen_deny:
            continue
        seen_deny.add(value)
        deny.append(value)
    base["allow"] = allow
    base["deny"] = deny
    base["defaultMode"] = "bypassPermissions"
    return base


def hook_command_exists(hook_items, command_path):
    if not isinstance(hook_items, list):
        return False
    for hook in hook_items:
        if not isinstance(hook, dict):
            continue
        if str(hook.get("type") or "").strip() != "command":
            continue
        if str(hook.get("command") or "").strip() == command_path:
            return True
    return False


def append_command_hook(hooks_data, event_name, command_path, matcher=None, timeout=None, status_message=None):
    import mms_launchers as _launchers

    if not command_path or not os.path.isfile(command_path):
        return hooks_data

    merged = dict(hooks_data) if isinstance(hooks_data, dict) else {}
    event_groups = list(merged.get(event_name) or [])
    hook_payload = {"type": "command", "command": command_path}
    if timeout is not None:
        hook_payload["timeout"] = timeout
    if status_message:
        hook_payload["statusMessage"] = str(status_message)

    for group in event_groups:
        if not isinstance(group, dict):
            continue
        existing_matcher = str(group.get("matcher") or "").strip() if matcher is not None else ""
        target_matcher = str(matcher or "").strip()
        if existing_matcher != target_matcher:
            continue
        hook_items = group.get("hooks")
        if _launchers._hook_command_exists(hook_items, command_path):
            merged[event_name] = event_groups
            return merged
        if isinstance(hook_items, list):
            hook_items.append(dict(hook_payload))
            merged[event_name] = event_groups
            return merged

    new_group = {"hooks": [dict(hook_payload)]}
    if matcher is not None:
        new_group["matcher"] = matcher
    event_groups.append(new_group)
    merged[event_name] = event_groups
    return merged


def append_shell_command_hook(
    hooks_data,
    event_name,
    command_text,
    *,
    matcher=None,
    timeout=None,
    status_message=None,
):
    import mms_launchers as _launchers

    command_text = str(command_text or "").strip()
    if not command_text:
        return hooks_data

    merged = dict(hooks_data) if isinstance(hooks_data, dict) else {}
    event_groups = list(merged.get(event_name) or [])
    target_matcher = str(matcher or "").strip()
    hook_payload = {"type": "command", "command": command_text}
    if timeout is not None:
        hook_payload["timeout"] = timeout
    if status_message:
        hook_payload["statusMessage"] = str(status_message)

    for group in event_groups:
        if not isinstance(group, dict):
            continue
        existing_matcher = str(group.get("matcher") or "").strip() if matcher is not None else ""
        if existing_matcher != target_matcher:
            continue
        hook_items = group.get("hooks")
        if _launchers._hook_command_exists(hook_items, command_text):
            merged[event_name] = event_groups
            return merged
        if isinstance(hook_items, list):
            hook_items.append(dict(hook_payload))
            merged[event_name] = event_groups
            return merged

    new_group = {"hooks": [dict(hook_payload)]}
    if matcher is not None:
        new_group["matcher"] = matcher
    event_groups.append(new_group)
    merged[event_name] = event_groups
    return merged


def filter_hook_commands(hooks_data, predicate):
    hooks_data = hooks_data if isinstance(hooks_data, dict) else {}
    filtered = {}
    for event_name, groups in hooks_data.items():
        if not isinstance(groups, list):
            continue
        kept_groups = []
        for group in groups:
            if not isinstance(group, dict):
                kept_groups.append(group)
                continue
            hook_items = group.get("hooks")
            if not isinstance(hook_items, list):
                kept_groups.append(dict(group))
                continue
            kept_hooks = []
            for hook in hook_items:
                if not isinstance(hook, dict):
                    kept_hooks.append(hook)
                    continue
                if (
                    str(hook.get("type") or "").strip() == "command"
                    and predicate(str(hook.get("command") or ""))
                ):
                    continue
                kept_hooks.append(dict(hook))
            if not kept_hooks and hook_items:
                continue
            next_group = dict(group)
            next_group["hooks"] = kept_hooks
            kept_groups.append(next_group)
        if kept_groups:
            filtered[event_name] = kept_groups
    return filtered


def filter_missing_managed_hook_commands(hooks_data):
    import mms_launchers as _launchers

    return _launchers._filter_hook_commands(
        hooks_data,
        lambda command: _launchers._is_mms_managed_hook_command(command)
        and not _launchers._hook_command_targets_exist(command),
    )


def normalize_session_surface_disabled(disabled_session_surfaces):
    import mms_launchers as _launchers

    disabled_session_surfaces = disabled_session_surfaces if isinstance(disabled_session_surfaces, dict) else {}
    normalized = {"mcp": set(), "skills": set(), "hooks": set()}
    aliases = {
        "mcp": "mcp",
        "mcps": "mcp",
        "mcp_servers": "mcp",
        "skills": "skills",
        "skill": "skills",
        "hooks": "hooks",
        "hook": "hooks",
    }
    for raw_key, raw_values in disabled_session_surfaces.items():
        key = aliases.get(str(raw_key or "").strip().lower())
        if not key:
            continue
        values = raw_values
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, (list, tuple, set)):
            continue
        for item in values:
            value = str(item or "").strip()
            if not value:
                continue
            if key == "hooks":
                value = _launchers._normalize_hook_command(value)
            normalized[key].add(value)
    return normalized


def session_surface_disabled(disabled_session_surfaces, surface, value):
    import mms_launchers as _launchers

    surface = str(surface or "").strip()
    value = str(value or "").strip()
    if not surface or not value:
        return False
    disabled = _launchers._normalize_session_surface_disabled(disabled_session_surfaces)
    if surface == "hooks":
        value = _launchers._normalize_hook_command(value)
    return value in disabled.get(surface, set())


def filter_mcp_servers_by_disabled(mcp_servers, disabled_session_surfaces=None):
    import mms_launchers as _launchers

    if not isinstance(mcp_servers, dict):
        return {}
    disabled = _launchers._normalize_session_surface_disabled(disabled_session_surfaces)
    disabled_names = disabled.get("mcp", set())
    if not disabled_names:
        return mcp_servers
    return {
        name: spec
        for name, spec in mcp_servers.items()
        if str(name or "").strip() not in disabled_names
    }


def normalize_session_mcp_server_spec(name, spec, *, env=None):
    import mms_launchers as _launchers

    if not isinstance(spec, dict):
        return None
    normalized = copy.deepcopy(spec)
    url = normalized.get("url")
    if isinstance(url, str) and url.strip():
        return normalized

    command = str(normalized.get("command") or "").strip()
    if not command:
        return None
    if _launchers._mcp_command_has_path(command):
        if os.path.isabs(command) and (not os.path.isfile(command) or not os.access(command, os.X_OK)):
            return None
        normalized["command"] = command
        return normalized

    resolved = _launchers._resolve_real_home_command_path(command, env)
    if not resolved:
        return None
    normalized["command"] = resolved
    return normalized


def normalize_session_mcp_servers(mcp_servers, *, disabled_session_surfaces=None, env=None):
    import mms_launchers as _launchers

    filtered = _launchers._filter_mcp_servers_by_disabled(mcp_servers, disabled_session_surfaces)
    normalized = {}
    for name, spec in filtered.items():
        key = str(name or "").strip()
        if not key:
            continue
        safe_spec = _launchers._normalize_session_mcp_server_spec(key, spec, env=env)
        if safe_spec:
            normalized[key] = safe_spec
    return normalized


def filter_hooks_by_disabled(hooks_data, disabled_session_surfaces=None):
    import mms_launchers as _launchers

    if not isinstance(hooks_data, dict):
        return {}
    disabled = _launchers._normalize_session_surface_disabled(disabled_session_surfaces)
    disabled_commands = disabled.get("hooks", set())
    if "xmem" in disabled.get("skills", set()):
        disabled_commands = set(disabled_commands)
        disabled_commands.add(_launchers._normalize_hook_command(_launchers._XMEM_SESSION_START_HOOK))
        disabled_commands.add(_launchers._normalize_hook_command(_launchers._XMEM_SESSION_END_HOOK))
        disabled_commands.add(_launchers._normalize_hook_command(_launchers._XMEM_GATEWAY_HOOK))
    if not disabled_commands:
        return hooks_data
    return _launchers._filter_hook_commands(
        hooks_data,
        lambda command: _launchers._normalize_hook_command(command) in disabled_commands,
    )


def session_skill_disabled(disabled_session_surfaces, skill_name):
    import mms_launchers as _launchers

    return _launchers._session_surface_disabled(disabled_session_surfaces, "skills", skill_name)


def sanitize_claude_inherited_settings_payload(settings_data, *, allow_execution_surfaces=True):
    import mms_launchers as _launchers

    settings_data = settings_data if isinstance(settings_data, dict) else {}
    inherited = {}
    if allow_execution_surfaces:
        for key in _launchers._CLAUDE_SETTINGS_INHERIT_KEYS:
            value = settings_data.get(key)
            if isinstance(value, dict):
                inherited[key] = copy.deepcopy(value)
    for key in _launchers._CLAUDE_SETTINGS_INHERIT_SCALAR_KEYS:
        value = settings_data.get(key)
        if isinstance(value, (str, int, float, bool)):
            inherited[key] = copy.deepcopy(value)
    return inherited


def sanitize_account_claude_settings_payload(settings_data):
    import mms_launchers as _launchers

    return _launchers._sanitize_claude_inherited_settings_payload(settings_data)


def merge_mms_session_hooks(existing_hooks, template_hooks=None):
    import mms_launchers as _launchers

    hooks_data = _launchers._merge_claude_hooks(existing_hooks, template_hooks)
    hooks_data = _launchers._append_command_hook(
        hooks_data,
        "PreToolUse",
        _launchers._CLAUDE_FEISHU_WEBFETCH_GUARD_HOOK,
        matcher="WebFetch",
    )
    hooks_data = _launchers._append_command_hook(
        hooks_data,
        "SessionStart",
        _launchers._CLAUDE_BRAINKEEPER_SESSION_START_HOOK,
        matcher="",
    )
    hooks_data = _launchers._append_command_hook(
        hooks_data,
        "Stop",
        _launchers._CLAUDE_BRAINKEEPER_SESSION_END_HOOK,
        matcher="",
    )
    hooks_data = _launchers._append_command_hook(
        hooks_data,
        "Stop",
        _launchers._XMEM_SESSION_END_HOOK,
        matcher="",
        timeout=10,
        status_message="Closing xmem",
    )
    hooks_data = _launchers._append_command_hook(
        hooks_data,
        "UserPromptSubmit",
        _launchers._CLAUDE_BRAINKEEPER_TOKEN_MONITOR_HOOK,
        matcher="",
    )
    hooks_data = _launchers._append_command_hook(
        hooks_data,
        "UserPromptSubmit",
        _launchers._XMEM_GATEWAY_HOOK,
        matcher="",
        timeout=10,
    )
    hooks_data = _launchers._append_command_hook(
        hooks_data,
        "SessionStart",
        _launchers._CLAUDE_CODEGRAPH_AUTO_INDEX_HOOK,
        matcher="",
        timeout=20,
        status_message="Syncing CodeGraph",
    )
    hooks_data = _launchers._append_command_hook(
        hooks_data,
        "SessionStart",
        _launchers._XMEM_SESSION_START_HOOK,
        matcher="",
        timeout=10,
        status_message="Syncing xmem",
    )
    hooks_data = _launchers._append_command_hook(
        hooks_data,
        "SessionEnd",
        _launchers._CLAUDE_MMS_RESUME_HINT_HOOK,
        matcher="",
    )
    return hooks_data


def filter_claude_session_hooks(hooks_data, *, allow_execution_surfaces=True):
    import mms_launchers as _launchers

    hooks_data = hooks_data if isinstance(hooks_data, dict) else {}
    if not allow_execution_surfaces:
        return {}
    return _launchers._filter_missing_managed_hook_commands(hooks_data)


def configure_claude_nsr_hooks(hooks_data, *, enable_nsr=False):
    import mms_launchers as _launchers

    hooks_data = _launchers._filter_hook_commands(hooks_data, _launchers._is_loop_family_hook_command)
    if not enable_nsr or not _launchers._nsr_available_for_cli("claude"):
        return hooks_data
    for event_name, matcher in (
        ("SessionStart", "startup|resume|clear|compact"),
        ("UserPromptSubmit", ""),
        ("PermissionRequest", "*"),
        ("PreToolUse", "*"),
        ("PostToolUse", "*"),
        ("PreCompact", ""),
        ("PostCompact", ""),
        ("Stop", ""),
    ):
        hooks_data = _launchers._append_shell_command_hook(
            hooks_data,
            event_name,
            _launchers._NSR_CLAUDE_HOOK,
            matcher=matcher,
            timeout=10,
            status_message="Loading NSR",
        )
    return hooks_data


def configure_claude_caveman_hooks(hooks_data, *, enable_caveman=False):
    import mms_launchers as _launchers

    hooks_data = _launchers._filter_hook_commands(hooks_data, _launchers._is_caveman_hook_command)
    if not enable_caveman:
        return hooks_data
    caveman_root = _launchers._resolve_caveman_root()
    if not caveman_root:
        return hooks_data
    hooks_data = _launchers._append_shell_command_hook(
        hooks_data,
        "SessionStart",
        _launchers._caveman_claude_activate_command(caveman_root),
        timeout=5,
        status_message="Loading caveman mode...",
    )
    hooks_data = _launchers._append_shell_command_hook(
        hooks_data,
        "UserPromptSubmit",
        _launchers._caveman_claude_tracker_command(caveman_root),
        timeout=5,
        status_message="Tracking caveman mode...",
    )
    return hooks_data


def configure_claude_ecc_hooks(hooks_data, *, enable_ecc=False):
    import mms_launchers as _launchers

    hooks_data = _launchers._filter_hook_commands(hooks_data, _launchers._is_ecc_hook_command)
    if not enable_ecc:
        return hooks_data
    ecc_hooks = _launchers._load_ecc_claude_hooks()
    if not ecc_hooks:
        return hooks_data
    return _launchers._merge_claude_hooks(hooks_data, ecc_hooks)


def configure_claude_omc_hooks(hooks_data, *, enable_omc=False):
    import mms_launchers as _launchers

    hooks_data = _launchers._filter_hook_commands(hooks_data, _launchers._is_omc_hook_command)
    if not enable_omc:
        return hooks_data
    omc_hooks = _launchers._load_omc_claude_hooks()
    if not omc_hooks:
        return hooks_data
    return _launchers._merge_claude_hooks(hooks_data, omc_hooks)


def default_session_mcp_servers():
    import mms_launchers as _launchers

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(_launchers.__file__)))
    servers = {}
    candidates = [
        ("brainkeeper", os.path.join(repo_root, "brainkeeper", "dist", "server.js")),
        ("brainkeeper", _launchers._real_user_path(".local", "share", "brainkeeper", "dist", "server.js")),
        ("mindkeeper", os.path.join(repo_root, "mindkeeper", "dist", "server.js")),
        ("mindkeeper", _launchers._real_user_path(".local", "share", "mindkeeper", "dist", "server.js")),
    ]
    for key, server_path in candidates:
        if os.path.isfile(server_path):
            servers[key] = {
                "args": [server_path],
                "command": "node",
                "type": "stdio",
            }
            break

    return servers


def agent_pack_mcp_servers(agent_pack):
    import mms_launchers as _launchers

    pack = _launchers._normalize_agent_pack(agent_pack, default="none")
    if pack == "ecc":
        return _launchers._load_plugin_mcp_servers(_launchers._resolve_ecc_root())
    if pack == "omc":
        return _launchers._load_plugin_mcp_servers(_launchers._resolve_omc_root())
    return {}


def merge_agent_pack_mcp_servers(mcp_servers, *, agent_pack="none", disabled_session_surfaces=None):
    import mms_launchers as _launchers

    merged = copy.deepcopy(mcp_servers) if isinstance(mcp_servers, dict) else {}
    for name, spec in _launchers._agent_pack_mcp_servers(agent_pack).items():
        if _launchers._session_surface_disabled(disabled_session_surfaces, "mcp", name):
            continue
        merged.setdefault(name, copy.deepcopy(spec))
    return _launchers._filter_mcp_servers_by_disabled(merged, disabled_session_surfaces)


def ensure_session_only_claude_mcp_servers(settings_data, *, disabled_session_surfaces=None):
    import mms_launchers as _launchers

    settings_data = dict(settings_data) if isinstance(settings_data, dict) else {}
    mcp_servers = settings_data.get("mcpServers")
    merged = copy.deepcopy(mcp_servers) if isinstance(mcp_servers, dict) else {}

    hive_spec = _launchers._default_hive_session_mcp_server()
    if hive_spec and not (isinstance(merged.get("hive"), dict) and str(merged.get("hive", {}).get("command") or "").strip()):
        merged["hive"] = copy.deepcopy(hive_spec)
    pilot_spec = _launchers._default_pilot_session_mcp_server()
    if pilot_spec and not (isinstance(merged.get("pilot"), dict) and str(merged.get("pilot", {}).get("command") or "").strip()):
        merged["pilot"] = copy.deepcopy(pilot_spec)
    merged = _launchers._normalize_session_mcp_servers(
        merged,
        disabled_session_surfaces=disabled_session_surfaces,
    )

    if merged:
        settings_data["mcpServers"] = merged
    else:
        settings_data.pop("mcpServers", None)
    return settings_data


def session_managed_mcp_server_allowlist(*, allow_execution_surfaces=True):
    import mms_launchers as _launchers

    if allow_execution_surfaces:
        return _launchers._CLAUDE_SESSION_MCP_SERVER_ALLOWLIST
    return ()


def session_managed_mcp_servers(settings_data, *, allow_execution_surfaces=True, disabled_session_surfaces=None):
    import mms_launchers as _launchers

    settings_data = settings_data if isinstance(settings_data, dict) else {}
    inherited = {}
    allowlist = _launchers._session_managed_mcp_server_allowlist(
        allow_execution_surfaces=allow_execution_surfaces
    )
    mcp_servers = settings_data.get("mcpServers")
    if isinstance(mcp_servers, dict):
        for name in allowlist:
            spec = mcp_servers.get(name)
            if isinstance(spec, dict) and str(spec.get("command") or "").strip():
                inherited[name] = copy.deepcopy(spec)

    fallback = _launchers._default_session_mcp_servers()
    for name in allowlist:
        if name not in inherited and isinstance(fallback.get(name), dict):
            inherited[name] = copy.deepcopy(fallback[name])
    if allow_execution_surfaces:
        hive_spec = _launchers._default_hive_session_mcp_server()
        if isinstance(hive_spec, dict) and str(hive_spec.get("command") or "").strip():
            inherited.setdefault("hive", copy.deepcopy(hive_spec))
        pilot_spec = _launchers._default_pilot_session_mcp_server()
        if isinstance(pilot_spec, dict) and str(pilot_spec.get("command") or "").strip():
            inherited.setdefault("pilot", copy.deepcopy(pilot_spec))
    return _launchers._normalize_session_mcp_servers(
        inherited,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def build_claude_session_settings(
    base_settings=None,
    *,
    required_env=None,
    default_env=None,
    allow_execution_surfaces=True,
    enable_caveman=False,
    enable_nsr=False,
    enable_ecc=False,
    enable_omc=False,
    disabled_session_surfaces=None,
):
    import mms_launchers as _launchers

    agent_pack = "omc" if enable_omc else ("ecc" if enable_ecc else "none")
    enable_ecc = agent_pack == "ecc"
    enable_omc = agent_pack == "omc"
    template_settings = _launchers._load_mms_claude_settings_template()
    inherited_settings = _launchers._sanitize_claude_inherited_settings_payload(
        base_settings,
        allow_execution_surfaces=allow_execution_surfaces,
    )
    settings_data = _launchers._merge_claude_settings(
        inherited_settings,
        _launchers._load_global_claude_settings_template(),
    )
    managed_mcp_servers = _launchers._session_managed_mcp_servers(
        base_settings,
        allow_execution_surfaces=allow_execution_surfaces,
        disabled_session_surfaces=disabled_session_surfaces,
    )
    if allow_execution_surfaces:
        managed_mcp_servers = _launchers._merge_agent_pack_mcp_servers(
            managed_mcp_servers,
            agent_pack=agent_pack,
            disabled_session_surfaces=disabled_session_surfaces,
        )

    template_hooks = template_settings.get("hooks")
    hooks = _launchers._filter_claude_session_hooks(
        _launchers._merge_mms_session_hooks(
            _launchers._strip_agent_im_hooks(settings_data.get("hooks")),
            template_hooks,
        ),
        allow_execution_surfaces=allow_execution_surfaces,
    )
    hooks = _launchers._configure_claude_caveman_hooks(
        hooks,
        enable_caveman=bool(enable_caveman and allow_execution_surfaces),
    )
    hooks = _launchers._configure_claude_nsr_hooks(
        hooks,
        enable_nsr=bool(enable_nsr and allow_execution_surfaces),
    )
    hooks = _launchers._configure_claude_ecc_hooks(
        hooks,
        enable_ecc=bool(enable_ecc and allow_execution_surfaces),
    )
    hooks = _launchers._configure_claude_omc_hooks(
        hooks,
        enable_omc=bool(enable_omc and allow_execution_surfaces),
    )
    hooks = _launchers._filter_hooks_by_disabled(hooks, disabled_session_surfaces)
    if hooks:
        settings_data["hooks"] = hooks
    else:
        settings_data.pop("hooks", None)

    existing_env = settings_data.get("env")
    merged_env = dict(existing_env) if isinstance(existing_env, dict) else {}
    template_env = template_settings.get("env")
    if isinstance(template_env, dict):
        for key, value in template_env.items():
            merged_env.setdefault(key, value)
    if isinstance(default_env, dict):
        for key, value in default_env.items():
            merged_env.setdefault(key, value)
    if isinstance(required_env, dict):
        merged_env.update(required_env)
    settings_data["env"] = _launchers._configure_agent_pack_session_env(
        merged_env,
        agent_pack=agent_pack if allow_execution_surfaces else "none",
    )
    configured_shell_model = settings_data["env"].get("ANTHROPIC_MODEL")
    existing_settings_model = settings_data.get("model")
    fallback_settings_model = (
        existing_settings_model
        if _launchers._is_claude_family_model_name(existing_settings_model)
        else "claude-sonnet-4-6"
    )
    if configured_shell_model:
        selected_shell_model = _launchers._claude_visible_model_name(
            configured_shell_model,
            fallback_model=fallback_settings_model,
        )
        if selected_shell_model:
            settings_data["model"] = selected_shell_model
    elif existing_settings_model and not _launchers._is_claude_family_model_name(existing_settings_model):
        settings_data["model"] = fallback_settings_model

    if managed_mcp_servers:
        settings_data["mcpServers"] = managed_mcp_servers
    else:
        settings_data.pop("mcpServers", None)
    if allow_execution_surfaces:
        settings_data = _launchers._ensure_session_only_claude_mcp_servers(
            settings_data,
            disabled_session_surfaces=disabled_session_surfaces,
        )

    settings_data.setdefault(
        "includeCoAuthoredBy",
        template_settings.get("includeCoAuthoredBy", False),
    )
    settings_data.setdefault(
        "attribution",
        template_settings.get("attribution") if isinstance(template_settings.get("attribution"), dict) else {"commit": "", "pr": ""},
    )
    settings_data.setdefault(
        "promptSuggestionEnabled",
        template_settings.get("promptSuggestionEnabled", False),
    )
    if template_settings.get("model") and not settings_data.get("model"):
        settings_data["model"] = template_settings.get("model")
    settings_data["skipDangerousModePermissionPrompt"] = bool(
        template_settings.get("skipDangerousModePermissionPrompt", True)
    )
    if allow_execution_surfaces:
        settings_data["statusLine"] = _launchers._merge_claude_statusline(settings_data.get("statusLine"))
        settings_data["permissions"] = _launchers._merge_claude_permissions(settings_data.get("permissions"))
    else:
        settings_data.pop("statusLine", None)
        settings_data.pop("permissions", None)
    return settings_data


def write_claude_session_settings(
    session_claude_dir,
    *,
    required_env=None,
    default_env=None,
    base_settings=None,
    allow_execution_surfaces=True,
    enable_caveman=False,
    enable_nsr=False,
    enable_ecc=False,
    enable_omc=False,
    disabled_session_surfaces=None,
):
    import mms_launchers as _launchers

    os.makedirs(session_claude_dir, exist_ok=True)
    source_settings = (
        dict(base_settings) if isinstance(base_settings, dict) else _launchers._load_real_claude_settings()
    )
    settings_data = _launchers._build_claude_session_settings(
        source_settings,
        required_env=required_env,
        default_env=default_env,
        allow_execution_surfaces=allow_execution_surfaces,
        enable_caveman=enable_caveman,
        enable_nsr=enable_nsr,
        enable_ecc=enable_ecc,
        enable_omc=enable_omc,
        disabled_session_surfaces=disabled_session_surfaces,
    )
    settings_path = os.path.join(session_claude_dir, "settings.json")
    with _launchers.locked_state_file(settings_path):
        _launchers.atomic_write_json(settings_path, settings_data, mode=0o600)
    return settings_data, settings_path


def seed_oauth_claude_session_settings(account_claude_dir, session_claude_dir):
    import mms_launchers as _launchers

    account_settings = _launchers._load_claude_settings_from_dir(account_claude_dir)
    seeded_settings = _launchers._sanitize_claude_inherited_settings_payload(
        account_settings,
        allow_execution_surfaces=False,
    )
    if not seeded_settings:
        return None
    os.makedirs(session_claude_dir, exist_ok=True)
    settings_path = os.path.join(session_claude_dir, "settings.json")
    with _launchers.locked_state_file(settings_path):
        _launchers.atomic_write_json(settings_path, seeded_settings, mode=0o600)
    return seeded_settings
