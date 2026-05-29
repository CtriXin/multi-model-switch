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
