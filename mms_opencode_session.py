"""OpenCode session-local environment and plugin helpers."""

from __future__ import annotations

import os
import shutil

from mms_opencode_config import opencode_env_bool, opencode_runtime_bool

OPENCODE_CONFIG_ENV_KEYS = (
    "OPENCODE_CONFIG",
    "OPENCODE_CONFIG_DIR",
    "OPENCODE_CONFIG_CONTENT",
    "OPENCODE_PERMISSION",
)


def opencode_session_plugin_runtime(runtime=None, disabled_session_surfaces=None):
    plugin_runtime = dict(runtime or {}) if isinstance(runtime, dict) else {}
    plugin_runtime["disabled_session_surfaces"] = disabled_session_surfaces
    return plugin_runtime


def clear_opencode_config_env(env):
    for key in OPENCODE_CONFIG_ENV_KEYS:
        env.pop(key, None)
    return env


def opencode_plugin_path(module_file, plugin_name):
    plugin_path = os.path.join(os.path.dirname(os.path.abspath(module_file)), "hooks", plugin_name)
    return plugin_path if os.path.isfile(plugin_path) else ""


def opencode_rtk_plugin_path(
    runtime=None,
    *,
    module_file,
    normalize_session_surface_disabled,
    runtime_bool=opencode_runtime_bool,
    env_bool=opencode_env_bool,
    which=shutil.which,
):
    disabled_hooks = normalize_session_surface_disabled(
        (runtime or {}).get("disabled_session_surfaces") if isinstance(runtime, dict) else None
    ).get("hooks", set())
    if "opencode-rtk" in disabled_hooks:
        return ""
    if not runtime_bool(runtime or {}, "opencode_rtk", True):
        return ""
    if not env_bool("MMS_OPENCODE_RTK", True):
        return ""
    if not which("rtk"):
        return ""
    return opencode_plugin_path(module_file, "opencode-rtk.ts")


def opencode_xmem_plugin_path(
    runtime=None,
    *,
    module_file,
    normalize_session_surface_disabled,
    session_skill_disabled,
    resolve_xmem_root,
    xmem_cli_path,
):
    disabled = normalize_session_surface_disabled(
        (runtime or {}).get("disabled_session_surfaces") if isinstance(runtime, dict) else None
    )
    if "opencode-xmem" in disabled.get("hooks", set()) or session_skill_disabled(disabled, "xmem"):
        return ""
    if not resolve_xmem_root() and not xmem_cli_path():
        return ""
    return opencode_plugin_path(module_file, "opencode-xmem.ts")


def overlay_opencode_plugin(config_dir, plugin_path, target_name):
    if not plugin_path:
        return False
    plugins_dir = os.path.join(config_dir, "plugins")
    os.makedirs(plugins_dir, exist_ok=True)
    target_path = os.path.join(plugins_dir, target_name)
    try:
        if os.path.islink(target_path) or os.path.isfile(target_path):
            os.unlink(target_path)
        elif os.path.isdir(target_path):
            shutil.rmtree(target_path)
        os.symlink(plugin_path, target_path)
    except OSError:
        shutil.copy2(plugin_path, target_path)
    return True


def overlay_opencode_session_assets(
    config_dir,
    session_home,
    *,
    enable_caveman=False,
    disabled_session_surfaces=None,
    runtime=None,
    overlay_opencode_rtk_plugin,
    overlay_caveman_session_entries,
    overlay_web_access_session_entries,
    overlay_weber_session_entries,
    overlay_toon_session_entries,
    overlay_token_saver_session_entries,
    overlay_xmem_session_entries,
    overlay_opencode_xmem_plugin,
    overlay_codegraph_session_entries=None,
):
    if not config_dir or not session_home:
        return
    os.makedirs(config_dir, exist_ok=True)
    plugin_runtime = opencode_session_plugin_runtime(runtime, disabled_session_surfaces)
    overlay_opencode_rtk_plugin(config_dir, plugin_runtime)
    if enable_caveman:
        overlay_caveman_session_entries(
            config_dir,
            session_home,
            enable_caveman=True,
            disabled_session_surfaces=disabled_session_surfaces,
        )
    overlay_web_access_session_entries(config_dir, session_home, disabled_session_surfaces=disabled_session_surfaces)
    overlay_weber_session_entries(config_dir, session_home, disabled_session_surfaces=disabled_session_surfaces)
    if overlay_codegraph_session_entries is not None:
        overlay_codegraph_session_entries(config_dir, session_home, disabled_session_surfaces=disabled_session_surfaces)
    overlay_toon_session_entries(config_dir, session_home, disabled_session_surfaces=disabled_session_surfaces)
    overlay_token_saver_session_entries(config_dir, session_home, disabled_session_surfaces=disabled_session_surfaces)
    overlay_xmem_session_entries(config_dir, session_home, disabled_session_surfaces=disabled_session_surfaces)
    overlay_opencode_xmem_plugin(config_dir, plugin_runtime)
