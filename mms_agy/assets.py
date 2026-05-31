"""Antigravity session plugin asset helpers."""

from __future__ import annotations

import os


def _launchers():
    import mms_launchers as _module

    return _module


def agy_plugin_dir(account_home):
    return os.path.join(account_home, ".gemini", "antigravity-cli", "plugins", "mms-session")


def path_under(path, root):
    try:
        path_real = os.path.realpath(os.path.abspath(path))
        root_real = os.path.realpath(os.path.abspath(root))
        return os.path.commonpath([path_real, root_real]) == root_real
    except Exception:
        return False


def ensure_agy_plugin_dir(account_home):
    antigravity_dir = os.path.join(account_home, ".gemini", "antigravity-cli")
    plugin_root = os.path.join(antigravity_dir, "plugins")
    stable_plugin_root = os.path.join(account_home, ".gemini", "config", "plugins")
    sessions_dir = os.path.join(account_home, "s")

    os.makedirs(antigravity_dir, exist_ok=True)
    os.makedirs(stable_plugin_root, exist_ok=True)

    if os.path.islink(plugin_root):
        target = os.path.realpath(plugin_root)
        if path_under(target, sessions_dir):
            os.unlink(plugin_root)
            os.symlink(stable_plugin_root, plugin_root)
        elif not os.path.exists(target):
            os.makedirs(target, exist_ok=True)
    elif not os.path.exists(plugin_root):
        os.symlink(stable_plugin_root, plugin_root)

    plugin_dir = agy_plugin_dir(account_home)
    os.makedirs(plugin_dir, exist_ok=True)
    return plugin_dir


def write_agy_plugin_json(plugin_dir):
    os.makedirs(plugin_dir, exist_ok=True)
    payload = {
        "name": "mms-session",
        "displayName": "MMS Session",
        "version": "0.1.0",
        "description": "Session-local MMS skills, hooks, and MCP overlay.",
    }
    _launchers().atomic_write_json(os.path.join(plugin_dir, "plugin.json"), payload, mode=0o600, indent=2)


def remove_file_if_exists(path):
    try:
        if os.path.exists(path) or os.path.islink(path):
            os.remove(path)
    except OSError:
        pass


def write_agy_mcp_config(plugin_dir, *, disabled_session_surfaces=None):
    servers = _launchers()._session_managed_mcp_servers(
        {},
        allow_execution_surfaces=True,
        disabled_session_surfaces=disabled_session_surfaces,
    )
    path = os.path.join(plugin_dir, "mcp_config.json")
    if servers:
        _launchers().atomic_write_json(path, {"mcpServers": servers}, mode=0o600, indent=2)
    else:
        remove_file_if_exists(path)


def write_agy_hooks(plugin_dir, *, enable_caveman=False, caveman_level="light", disabled_session_surfaces=None):
    remove_file_if_exists(os.path.join(plugin_dir, "hooks.json"))
    hooks_data = _launchers()._merge_mms_session_hooks({})
    if enable_caveman:
        hooks_data = _launchers()._configure_claude_caveman_hooks(
            hooks_data,
            enable_caveman=True,
            caveman_level=caveman_level,
        )
    hooks_data = _launchers()._filter_hooks_by_disabled(hooks_data, disabled_session_surfaces)
    hooks_data = _launchers()._filter_missing_managed_hook_commands(hooks_data)
    hooks_dir = os.path.join(plugin_dir, "hooks")
    path = os.path.join(hooks_dir, "hooks.json")
    if hooks_data:
        os.makedirs(hooks_dir, exist_ok=True)
        _launchers().atomic_write_json(path, {"hooks": hooks_data}, mode=0o600, indent=2)
    else:
        remove_file_if_exists(path)


def overlay_agy_session_assets(
    account_home,
    session_home,
    *,
    enable_caveman=False,
    caveman_level="light",
    disabled_session_surfaces=None,
):
    if not account_home or not session_home:
        return
    plugin_dir = ensure_agy_plugin_dir(account_home)
    write_agy_plugin_json(plugin_dir)
    write_agy_mcp_config(plugin_dir, disabled_session_surfaces=disabled_session_surfaces)
    write_agy_hooks(
        plugin_dir,
        enable_caveman=enable_caveman,
        caveman_level=caveman_level,
        disabled_session_surfaces=disabled_session_surfaces,
    )
    if enable_caveman:
        _launchers()._overlay_caveman_session_entries(
            plugin_dir,
            session_home,
            enable_caveman=True,
            disabled_session_surfaces=disabled_session_surfaces,
        )
    _launchers()._overlay_web_access_session_entries(plugin_dir, session_home, disabled_session_surfaces=disabled_session_surfaces)
    _launchers()._overlay_weber_session_entries(plugin_dir, session_home, disabled_session_surfaces=disabled_session_surfaces)
    _launchers()._overlay_agent_browser_session_entries(plugin_dir, session_home, disabled_session_surfaces=disabled_session_surfaces)
    _launchers()._overlay_codegraph_session_entries(plugin_dir, session_home, disabled_session_surfaces=disabled_session_surfaces)
    _launchers()._overlay_toon_session_entries(plugin_dir, session_home, disabled_session_surfaces=disabled_session_surfaces)
    _launchers()._overlay_token_saver_session_entries(plugin_dir, session_home, disabled_session_surfaces=disabled_session_surfaces)
    _launchers()._overlay_xmem_session_entries(plugin_dir, session_home, disabled_session_surfaces=disabled_session_surfaces)
    _launchers()._overlay_auto_github_contributor_session_entries(plugin_dir, session_home, disabled_session_surfaces=disabled_session_surfaces)
