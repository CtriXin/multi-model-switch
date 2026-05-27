"""Shared export-env helpers for MMS launcher entrypoints."""

from __future__ import annotations

import json
import os


def truthy(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enable", "enabled"}


def host_context_real_home(*, real_user_path, real_user_home):
    """Resolve the real user home used in launcher host-context payloads."""
    try:
        return real_user_path()
    except TypeError:
        return real_user_home()


def host_tool_context(
    session_home,
    env=None,
    *,
    real_home_wrapper_search_path,
    resolve_tool_bins,
    wrapper_commands,
):
    filtered_path = real_home_wrapper_search_path(session_home, env)
    tools = resolve_tool_bins(wrapper_commands, path=filtered_path)
    wrapper_dir = os.path.join(str(session_home or "").strip(), ".mms", "bin")
    for name, payload in tools.items():
        payload["wrapper"] = os.path.join(wrapper_dir, name)
    return tools


def inject_host_capability_hints(env, *, host_capability_env, host_context_real_home):
    if not isinstance(env, dict):
        return env
    try:
        env.update(host_capability_env(real_home=host_context_real_home()))
    except Exception:
        pass
    return env


def model_name_from_info(model_info):
    if isinstance(model_info, str):
        return model_info.strip()
    if not isinstance(model_info, dict):
        return ""
    for key in ("model", "sonnet", "opus", "haiku"):
        value = str(model_info.get(key) or "").strip()
        if value:
            return value
    return ""


def selected_model_name(*candidates, model_info=None):
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value:
            return value
    return model_name_from_info(model_info)


def inject_selected_model_name(env, *candidates, model_info=None):
    if not isinstance(env, dict):
        return env
    model_name = selected_model_name(*candidates, model_info=model_info)
    if model_name:
        env["MMS_MODEL_NAME"] = model_name
    else:
        env.pop("MMS_MODEL_NAME", None)
    return env


def set_session_home_hint(env, session_home):
    if session_home:
        env["MMS_SESSION_HOME"] = session_home
    return env


def set_codex_home_hint(env, session_home):
    if session_home:
        env["CODEX_HOME"] = os.path.join(session_home, ".codex")
    return env


def set_codex_soft_home(
    env,
    session_home,
    *,
    real_user_path,
    set_session_home_hint,
    set_codex_home_hint,
):
    real_home = real_user_path()
    env["HOME"] = real_home
    env["XDG_CONFIG_HOME"] = real_user_path(".config")
    env["MMS_HOME_ISOLATION_MODE"] = "soft"
    env["MMS_SOFT_HOME"] = "1"
    set_session_home_hint(env, session_home)
    set_codex_home_hint(env, session_home)
    return env


def rescue_default_fallback_config(*, environ, load_config, truthy):
    env_model = str(environ.get("MMS_RESCUE_FALLBACK_MODEL") or "").strip()
    env_cli = str(environ.get("MMS_RESCUE_FALLBACK_CLI") or "").strip()
    env_hot = environ.get("MMS_RESCUE_HOT_FALLBACK")
    if env_model:
        return {"model": env_model, "cli": env_cli, "hot_fallback_enabled": truthy(env_hot)}
    try:
        cfg = load_config() or {}
    except Exception:
        cfg = {}
    rescue_cfg = cfg.get("rescue") if isinstance(cfg, dict) and isinstance(cfg.get("rescue"), dict) else {}
    model = str(rescue_cfg.get("fallback_model") or rescue_cfg.get("default_fallback_model") or "").strip()
    cli = str(rescue_cfg.get("fallback_cli") or rescue_cfg.get("default_fallback_cli") or "").strip()
    hot = rescue_cfg.get("hot_fallback_enabled", rescue_cfg.get("enable_hot_fallback", False))
    return {"model": model, "cli": cli, "hot_fallback_enabled": truthy(hot)}


def rescue_bridge_kwargs(*, rescue_default_fallback_config):
    fallback = rescue_default_fallback_config()
    model = str(fallback.get("model") or "").strip()
    if not model:
        return {}
    return {
        "rescue_fallback_model": model,
        "rescue_fallback_cli": str(fallback.get("cli") or "").strip(),
        "rescue_hot_fallback_enabled": bool(fallback.get("hot_fallback_enabled")),
    }


def inject_rescue_launch_env(
    env,
    *,
    safe_getcwd,
    real_user_path,
    rescue_default_fallback_config,
):
    if not isinstance(env, dict):
        return env
    try:
        project_root = os.path.realpath(safe_getcwd())
    except Exception:
        project_root = os.path.realpath(os.getcwd())
    if project_root:
        env["MMS_PROJECT_ROOT"] = project_root
        env["MMS_CWD"] = project_root
    env.setdefault("MMS_RESCUE_CONFIG_ROOT", real_user_path(".config", "mms"))
    fallback = rescue_default_fallback_config()
    if fallback.get("model"):
        env["MMS_RESCUE_FALLBACK_MODEL"] = str(fallback.get("model") or "")
        if fallback.get("cli"):
            env["MMS_RESCUE_FALLBACK_CLI"] = str(fallback.get("cli") or "")
        else:
            env.pop("MMS_RESCUE_FALLBACK_CLI", None)
        env["MMS_RESCUE_HOT_FALLBACK"] = "1" if fallback.get("hot_fallback_enabled") else "0"
    return env


def inject_real_home_hints(
    env,
    *,
    include_xdg=False,
    real_user_home,
    real_user_path,
    inject_rescue_launch_env,
):
    real_home = real_user_home()
    env["MMS_REAL_HOME"] = real_home
    env["ORIGINAL_HOME"] = real_home
    env["REAL_HOME"] = real_home
    env["WEB_ACCESS_HOST_HOME"] = real_home
    env["HOST_HOME"] = real_home
    env["GH_CONFIG_DIR"] = real_user_path(".config", "gh")
    inject_rescue_launch_env(env)
    if include_xdg:
        env["XDG_CONFIG_HOME"] = real_user_path(".config")
    return env


def launcher_script_path(module_file, script_name):
    script_path = os.path.join(os.path.dirname(os.path.abspath(module_file)), "scripts", script_name)
    return script_path if os.path.isfile(script_path) else ""


def xmem_cli_path(*, environ, real_user_path, which):
    candidates = []
    for key in ("MMS_XMEM_BIN", "XMEM_BIN"):
        explicit = str(environ.get(key) or "").strip()
        if explicit:
            candidates.append(os.path.abspath(os.path.expanduser(explicit)))
    candidates.extend([
        real_user_path(".local", "bin", "xmem"),
        real_user_path("auto-skills", "CtriXin-repo", "xmem", "bin", "xmem"),
    ])
    found = which("xmem")
    if found:
        candidates.append(found)
    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return ""


def install_session_command_wrappers(
    session_home,
    env,
    *,
    real_user_home,
    real_user_path,
    real_home_wrapper_search_path,
    real_home_wrapper_scrub_lines,
    write_real_home_script,
    install_chrome_host_wrapper,
    wrapper_commands,
    mms_toon_script_path,
    mms_context_script_path,
    token_saver_script_path,
    xmem_cli_path,
):
    """Install wrappers for tools that must run against the real HOME."""
    wrapper_dir = os.path.join(session_home, ".mms", "bin")
    os.makedirs(wrapper_dir, exist_ok=True)

    real_home = real_user_home()
    current_path = real_home_wrapper_search_path(session_home, env)
    wrapper_path_env = json.dumps(current_path or os.defpath)
    xdg_config_home = json.dumps(real_user_path(".config"))
    xdg_cache_home = json.dumps(real_user_path(".cache"))
    xdg_data_home = json.dumps(real_user_path(".local", "share"))
    xdg_state_home = json.dumps(real_user_path(".local", "state"))
    for command_name in wrapper_commands:
        wrapper_path = os.path.join(wrapper_dir, command_name)
        extra_exports = []
        if command_name == "gh":
            extra_exports.append(f'export GH_CONFIG_DIR={json.dumps(real_user_path(".config", "gh"))}')
        if command_name == "pm2":
            extra_exports.append(f'export PM2_HOME={json.dumps(real_user_path(".pm2"))}')
        wrapper = "\n".join(
            [
                "#!/bin/sh",
                f'export HOME={json.dumps(real_home)}',
                f'export MMS_REAL_HOME={json.dumps(real_home)}',
                f'export REAL_HOME={json.dumps(real_home)}',
                f'export ORIGINAL_HOME={json.dumps(real_home)}',
                f"export PATH={wrapper_path_env}",
                f"export XDG_CONFIG_HOME={xdg_config_home}",
                f"export XDG_CACHE_HOME={xdg_cache_home}",
                f"export XDG_DATA_HOME={xdg_data_home}",
                f"export XDG_STATE_HOME={xdg_state_home}",
                *real_home_wrapper_scrub_lines(),
                *extra_exports,
                f'real_bin="$(command -v {json.dumps(command_name)} 2>/dev/null || true)"',
                'if [ -z "$real_bin" ]; then',
                f'  printf "%s\\n" "mms: command {command_name} not found in real HOME PATH" >&2',
                "  exit 127",
                "fi",
                'exec "$real_bin" "$@"',
                "",
            ]
        )
        write_real_home_script(wrapper_path, wrapper.splitlines())

    install_chrome_host_wrapper(wrapper_dir, env, wrapper_path_env)

    toon_script = mms_toon_script_path()
    if toon_script:
        toon_wrapper_path = os.path.join(wrapper_dir, "mms-toon")
        toon_wrapper = "\n".join(
            [
                "#!/bin/sh",
                f"exec {json.dumps(toon_script)} \"$@\"",
                "",
            ]
        )
        with open(toon_wrapper_path, "w", encoding="utf-8") as handle:
            handle.write(toon_wrapper)
        os.chmod(toon_wrapper_path, 0o755)
        if isinstance(env, dict):
            env["MMS_TOON_BIN"] = toon_wrapper_path

    context_script = mms_context_script_path()
    if context_script:
        context_wrapper_path = os.path.join(wrapper_dir, "mms-context")
        context_wrapper = "\n".join(
            [
                "#!/bin/sh",
                f"exec {json.dumps(context_script)} \"$@\"",
                "",
            ]
        )
        with open(context_wrapper_path, "w", encoding="utf-8") as handle:
            handle.write(context_wrapper)
        os.chmod(context_wrapper_path, 0o755)
        if isinstance(env, dict):
            env["MMS_CONTEXT_BIN"] = context_wrapper_path
            env["MMS_CONTEXT_DIR"] = os.path.join(session_home, ".mms", "context-store")

    token_saver_script = token_saver_script_path()
    if token_saver_script:
        token_saver_wrapper_path = os.path.join(wrapper_dir, "token-saver")
        token_saver_wrapper = "\n".join(
            [
                "#!/bin/sh",
                f"exec {json.dumps(token_saver_script)} \"$@\"",
                "",
            ]
        )
        with open(token_saver_wrapper_path, "w", encoding="utf-8") as handle:
            handle.write(token_saver_wrapper)
        os.chmod(token_saver_wrapper_path, 0o755)
        if isinstance(env, dict):
            env["TOKEN_SAVER_BIN"] = token_saver_wrapper_path
            env["MMS_TOKEN_SAVER_BIN"] = token_saver_wrapper_path
            env.setdefault("MMS_CONTEXT_DIR", os.path.join(session_home, ".mms", "context-store"))

    xmem_script = xmem_cli_path()
    if xmem_script:
        xmem_wrapper_path = os.path.join(wrapper_dir, "xmem")
        xmem_wrapper = "\n".join(
            [
                "#!/bin/sh",
                f"exec {json.dumps(xmem_script)} \"$@\"",
                "",
            ]
        )
        with open(xmem_wrapper_path, "w", encoding="utf-8") as handle:
            handle.write(xmem_wrapper)
        os.chmod(xmem_wrapper_path, 0o755)
        if isinstance(env, dict):
            env["XMEM_BIN"] = xmem_wrapper_path
            env["MMS_XMEM_BIN"] = xmem_wrapper_path

    session_path = env.get("PATH") or current_path
    env["PATH"] = wrapper_dir + os.pathsep + session_path if session_path else wrapper_dir


def install_host_context_env(
    env,
    *,
    cli,
    runtime=None,
    model_info=None,
    session_home="",
    host_context_real_home,
    selected_model_name,
    safe_getcwd,
    host_tool_context,
    write_host_context,
):
    if not isinstance(env, dict):
        env = {}
    session_home = str(session_home or "").strip()
    if not session_home:
        return {}
    try:
        host_env = write_host_context(
            session_home,
            real_home=host_context_real_home(),
            cli=cli,
            model=selected_model_name(model_info=model_info),
            cwd=safe_getcwd(),
            tool_bins=host_tool_context(session_home, env),
        )
    except Exception:
        return {}
    env.update(host_env)
    return host_env


def install_session_packet_env(
    env,
    *,
    cli,
    runtime,
    model_info=None,
    session_home="",
    features=None,
    extra_paths=None,
    write_session_packet,
):
    session_home = str(session_home or "").strip()
    if not session_home:
        return {}
    try:
        packet_env = write_session_packet(
            session_home,
            cli=cli,
            runtime=runtime,
            model_info=model_info,
            features=features,
            extra_paths=extra_paths,
        )
    except Exception:
        return {}
    if isinstance(env, dict):
        env.update(packet_env)
    return packet_env


def build_export_env(
    cli,
    runtime,
    *,
    is_opencode_global_profile_runtime,
    opencode_global_export_env,
    validate_account_for_cli,
    validate_provider_for_cli,
    anthropic_base_url,
    openai_base_url,
    resolve_model,
    opencode_provider_export_env,
    inject_host_capability_hints,
    mms_toon_script_path,
    mms_context_script_path,
    token_saver_script_path,
    xmem_cli_path,
    safe_getcwd,
):
    """Build export-only environment variables without launching a CLI."""
    runtime = runtime if isinstance(runtime, dict) else {}
    if is_opencode_global_profile_runtime(cli, runtime):
        return opencode_global_export_env(runtime)

    if runtime.get("auth_mode") == "broker_profile":
        return {}
    if runtime.get("auth_mode") == "oauth_bridge":
        return {}
    if runtime.get("auth_mode") == "oauth":
        validate_account_for_cli(runtime.get("cli", cli), runtime)
        return {}

    validate_provider_for_cli(cli, runtime)
    api_key = runtime["api_key"]
    exports = {}
    if cli == "claude":
        exports["ANTHROPIC_BASE_URL"] = anthropic_base_url(runtime)
        exports["ANTHROPIC_AUTH_TOKEN"] = api_key
        exports["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
        exports["API_TIMEOUT_MS"] = "3000000"
    elif cli == "codex":
        exports["OPENAI_API_KEY"] = api_key
        exports["OPENAI_BASE_URL"] = openai_base_url(runtime)
    elif cli == "opencode":
        model = resolve_model(runtime)
        exports.update(opencode_provider_export_env(runtime, model))
    if cli in {"claude", "codex"}:
        inject_host_capability_hints(exports)

    toon_script = mms_toon_script_path()
    context_script = mms_context_script_path()
    token_saver_script = token_saver_script_path()
    xmem_script = xmem_cli_path()
    if cli in {"claude", "codex", "opencode"}:
        if toon_script:
            exports["MMS_TOON_BIN"] = toon_script
        if context_script:
            exports["MMS_CONTEXT_BIN"] = context_script
            exports.setdefault("MMS_CONTEXT_DIR", os.path.join(safe_getcwd(), ".mms", "context-store"))
        if token_saver_script:
            exports["TOKEN_SAVER_BIN"] = token_saver_script
            exports["MMS_TOKEN_SAVER_BIN"] = token_saver_script
            exports.setdefault("MMS_CONTEXT_DIR", os.path.join(safe_getcwd(), ".mms", "context-store"))
        if xmem_script:
            exports["XMEM_BIN"] = xmem_script
            exports["MMS_XMEM_BIN"] = xmem_script
        first_script = toon_script or context_script or token_saver_script or xmem_script
        if first_script:
            exports["PATH"] = f"{os.path.dirname(first_script)}:$PATH"
    return exports
