"""OpenCode config file and environment materialization helpers."""

from __future__ import annotations

import os

from mms_opencode_config import opencode_config_slug


def opencode_write_config(path, runtime, model, *, build_config_content, atomic_write_text):
    config_content = build_config_content(runtime, model)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic_write_text(path, config_content + "\n", mode=0o600)
    return config_content


def opencode_set_soft_home(env, session_home, *, real_user_path, set_session_home_hint):
    """Keep real HOME for GUI/Keychain; keep OpenCode XDG state session-local."""
    real_home = real_user_path()
    env["HOME"] = real_home
    env["XDG_CONFIG_HOME"] = os.path.join(session_home, ".config")
    env["XDG_CACHE_HOME"] = os.path.join(session_home, ".cache")
    env["XDG_DATA_HOME"] = os.path.join(session_home, ".local", "share")
    env["XDG_STATE_HOME"] = os.path.join(session_home, ".local", "state")
    env["MMS_HOME_ISOLATION_MODE"] = "soft"
    env["MMS_SOFT_HOME"] = "1"
    env["MMS_OPENCODE_SOFT_HOME"] = "1"
    set_session_home_hint(env, session_home)
    return env


def opencode_export_config_path(runtime, model, *, real_user_path):
    runtime = runtime if isinstance(runtime, dict) else {}
    provider = opencode_config_slug(runtime.get("id") or runtime.get("name"), "provider")
    model_slug = opencode_config_slug(model or runtime.get("model"), "model")
    return real_user_path(
        ".config",
        "mms",
        "opencode-gateway",
        "exports",
        f"{provider}-{model_slug}.json",
    )


def opencode_gateway_env(
    runtime,
    model_info=None,
    *,
    resolve_model,
    real_user_path,
    cleanup_stale_sessions,
    link_shared_dotfiles,
    scrub_inherited_runtime_env,
    clear_opencode_config_env,
    inject_real_home_hints,
    inject_selected_model_name,
    set_opencode_soft_home,
    write_opencode_config,
    overlay_opencode_session_assets,
    apply_route_env,
    apply_bypass_env,
    apply_runtime_network_profile,
    apply_runtime_locale_profile,
    apply_runtime_ip_stack_profile,
    install_session_command_wrappers,
    install_session_packet_env,
    runtime_caveman_enabled,
    resolve_web_access_root,
    resolve_weber_root,
    resolve_codegraph_root,
    resolve_toon_root,
    resolve_token_saver_root,
    resolve_xmem_root,
    session_skill_disabled,
    opencode_rtk_plugin_enabled,
    opencode_xmem_plugin_enabled,
    environ=None,
    getpid=os.getpid,
):
    runtime = runtime if isinstance(runtime, dict) else {}
    model = resolve_model(model_info or runtime)
    disabled_session_surfaces = runtime.get("disabled_session_surfaces")
    enable_caveman = runtime_caveman_enabled(runtime)
    gateway_base = real_user_path(".config", "mms", "opencode-gateway")
    os.makedirs(gateway_base, exist_ok=True)
    sessions_dir = os.path.join(gateway_base, "s")
    session_home = os.path.join(sessions_dir, str(getpid()))
    os.makedirs(session_home, exist_ok=True)
    cleanup_stale_sessions(sessions_dir)

    link_shared_dotfiles(session_home)

    env = dict(os.environ if environ is None else environ)
    scrub_inherited_runtime_env(env, strip_openai=True, strip_proxy=True)
    clear_opencode_config_env(env)
    inject_real_home_hints(env)
    inject_selected_model_name(env, model, model_info=model_info)
    set_opencode_soft_home(env, session_home)

    config_dir = os.path.join(env["XDG_CONFIG_HOME"], "opencode")
    os.makedirs(config_dir, exist_ok=True)
    config_path = os.path.join(config_dir, "opencode.json")
    write_opencode_config(config_path, runtime, model)
    overlay_opencode_session_assets(
        config_dir,
        session_home,
        enable_caveman=enable_caveman,
        disabled_session_surfaces=disabled_session_surfaces,
        runtime=runtime,
    )

    apply_route_env(env, runtime, selected_model=model)
    env["OPENCODE_CONFIG"] = config_path
    env["OPENCODE_CONFIG_DIR"] = config_dir
    env["OPENCODE_DISABLE_AUTOUPDATE"] = "1"
    env["OPENCODE_CLIENT"] = "mms"
    apply_bypass_env(env, runtime)

    apply_runtime_network_profile(env, runtime, validate_proxy=False)
    apply_runtime_locale_profile(env, runtime)
    apply_runtime_ip_stack_profile(env, runtime)
    install_session_command_wrappers(session_home, env)
    install_session_packet_env(
        env,
        cli="opencode",
        runtime=runtime,
        model_info=model_info,
        session_home=session_home,
        features={
            "caveman": enable_caveman,
            "opencode_rtk": opencode_rtk_plugin_enabled(runtime),
            "web_access": bool(resolve_web_access_root()) and not session_skill_disabled(disabled_session_surfaces, "web-access"),
            "weber": bool(resolve_weber_root()) and not session_skill_disabled(disabled_session_surfaces, "weber"),
            "codegraph": bool(resolve_codegraph_root()) and not session_skill_disabled(disabled_session_surfaces, "codegraph"),
            "toon": bool(resolve_toon_root()) and not session_skill_disabled(disabled_session_surfaces, "toon"),
            "token_saver": bool(resolve_token_saver_root()) and not session_skill_disabled(disabled_session_surfaces, "token-saver"),
            "xmem": bool(resolve_xmem_root()) and not session_skill_disabled(disabled_session_surfaces, "xmem"),
            "opencode_xmem": opencode_xmem_plugin_enabled(runtime),
        },
    )
    return env


def opencode_global_omo_env(
    runtime,
    *,
    clear_opencode_config_env,
    inject_real_home_hints,
    real_user_path,
    apply_bypass_env,
    apply_runtime_network_profile,
    apply_runtime_locale_profile,
    apply_runtime_ip_stack_profile,
    environ=None,
):
    env = dict(os.environ if environ is None else environ)
    clear_opencode_config_env(env)
    inject_real_home_hints(env, include_xdg=True)
    env["HOME"] = real_user_path()
    env["XDG_CACHE_HOME"] = real_user_path(".cache")
    env["XDG_DATA_HOME"] = real_user_path(".local", "share")
    env["XDG_STATE_HOME"] = real_user_path(".local", "state")
    env["MMS_HOME_ISOLATION_MODE"] = "raw"
    env["OPENCODE_CLIENT"] = "mms"
    env["MMS_OPENCODE_PROFILE"] = "heavy_omo"
    apply_bypass_env(env, runtime)
    apply_runtime_network_profile(env, runtime, validate_proxy=False)
    apply_runtime_locale_profile(env, runtime)
    apply_runtime_ip_stack_profile(env, runtime)
    return env


def opencode_global_export_env(runtime, *, apply_bypass_env):
    exports = {
        "OPENCODE_CLIENT": "mms",
        "MMS_OPENCODE_PROFILE": "heavy_omo",
    }
    return apply_bypass_env(exports, runtime)


def opencode_provider_export_env(
    runtime,
    model,
    *,
    export_config_path,
    write_opencode_config,
    apply_route_env,
    apply_bypass_env,
):
    exports = {}
    config_path = export_config_path(runtime, model)
    write_opencode_config(config_path, runtime, model)
    apply_route_env(exports, runtime, selected_model=model)
    exports["OPENCODE_CONFIG"] = config_path
    exports["OPENCODE_CONFIG_DIR"] = os.path.dirname(config_path)
    exports["OPENCODE_DISABLE_AUTOUPDATE"] = "1"
    exports["OPENCODE_CLIENT"] = "mms"
    apply_bypass_env(exports, runtime)
    return exports


__all__ = [
    "opencode_export_config_path",
    "opencode_gateway_env",
    "opencode_global_export_env",
    "opencode_global_omo_env",
    "opencode_provider_export_env",
    "opencode_set_soft_home",
    "opencode_write_config",
]
