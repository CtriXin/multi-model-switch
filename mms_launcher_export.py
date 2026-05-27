"""Shared export-env helpers for MMS launcher entrypoints."""

from __future__ import annotations

import os


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
