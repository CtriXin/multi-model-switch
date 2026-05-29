"""Claude session settings materialization for MMS launchers.

The implementation resolves helpers through ``mms_launchers`` at call time so
existing tests and callers that monkeypatch launcher-private names keep working.
"""

from __future__ import annotations

import os


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
